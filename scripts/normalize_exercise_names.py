"""Normalize exercise aliases to Xunji's official Chinese movement names.

The historical exports contain both manually entered English names and names
returned by Xunji.  This script updates the source exports and the local
SQLite exercise dimension without changing any set values.

Ambiguous names are intentionally left unchanged and reported instead of
being guessed.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPORT_DIR = ROOT / "exports"
DEFAULT_DATABASES = (ROOT / "fitness.db", ROOT / "data" / "fitness.db")


# Only high-confidence aliases are included. Values are names from the
# official Xunji movement table (Foveluy/Xunji-movements), plus the explicit
# user-confirmed label “下斜卷腹”, which is not listed as a separate official
# entry.
ALIASES: dict[str, str] = {
    "Alternating hammer curl": "锤式弯举",
    "Barbell bench press": "杠铃卧推",
    "Barbell squat": "杠铃深蹲",
    "Bulgarian split squat": "哑铃保加利亚蹲",
    "Cable curl": "绳索弯举",
    "Cable lateral raise": "绳索侧平举（单边）",
    "Cable pushdown": "绳索臂屈伸",
    "Calf raise": "坐姿器械提踵",
    "Crunch": "下斜卷腹",
    "Dead bug": "死虫",
    "Decline chest press": "下斜悍马机推胸",
    "Decline Hammer Strength chest press": "下斜悍马机推胸",
    "Decline crunch": "下斜卷腹",
    "Dumbbell curl": "哑铃弯举",
    "Dumbbell lateral raise": "侧平举",
    "Dumbbell squat": "哑铃深蹲",
    "EZ-bar curl": "EZ杆二头弯举",
    "Face pull": "面拉",
    "Hammer curl": "锤式弯举",
    "Hammer strength chest press": "下斜悍马机推胸",
    "Hammer strength decline chest press": "下斜悍马机推胸",
    "Hammer strength seated shoulder press": "悍马机坐姿推举",
    "Hammer strength shoulder press": "悍马机坐姿推举",
    "Hanging crunch": "悬挂抬腿",
    "Hanging leg raise": "悬挂抬腿",
    "Hip adduction": "坐姿髋内收",
    "Hip thrust": "臀冲架臀冲",
    "Horizontal leg press": "器械倒蹬",
    "Incline barbell bench press": "上斜杠铃卧推",
    "Incline dumbbell bench press": "上斜哑铃卧推",
    "Incline dumbbell curl": "上斜哑铃弯举",
    "Lat pulldown": "宽距高位下拉",
    "Lateral raise": "侧平举",
    "Leg curl": "坐姿腿弯举",
    "Leg extension": "坐姿腿屈伸",
    "Leg press": "器械倒蹬",
    "Machine chest press": "下斜悍马机推胸",
    "Machine fly": "把手式蝴蝶机飞鸟",
    "Machine shoulder press": "悍马机坐姿推举",
    "Overhead triceps extension": "绳索过头臂屈伸",
    "Pallof press": "绳索Pallof推",
    "Plank": "平板支撑_计时",
    "Preacher EZ-bar curl": "牧师凳弯举",
    "Preacher barbell curl": "牧师凳弯举",
    "Preacher curl": "牧师凳弯举",
    "ProMaxima T-bar row": "T杆划船",
    "Reverse fly": "器械坐姿反向飞鸟",
    "Reverse pec deck": "器械坐姿反向飞鸟",
    "Reverse-grip cable pushdown": "站姿绳索反握弯举_直杆",
    "Romanian deadlift": "杠铃罗马尼亚硬拉",
    "Rope overhead triceps extension": "绳索过头臂屈伸",
    "Russian twist": "俄罗斯转体",
    "Seated cable row": "坐姿划船",
    "Seated calf raise": "坐姿器械提踵",
    "Seated leg curl": "坐姿腿弯举",
    "Seated leg extension": "坐姿腿屈伸",
    "Seated shoulder press": "悍马机坐姿推举",
    "Single-arm cable lateral raise": "绳索侧平举（单边）",
    "Single-arm incline dumbbell curl": "上斜哑铃弯举",
    "Spider curl": "蜘蛛弯举",
    "Squat": "杠铃深蹲",
    "Standing plate-loaded T-bar row": "T杆划船",
    "Straight-arm pulldown": "绳索直臂下压",
    "Straight-bar pushdown": "直杆绳索下压",
    "Superset cable curl": "绳索弯举",
    "Superset cable pushdown": "绳索臂屈伸",
    "T-bar row": "T杆划船",
    "Triceps pushdown": "绳索臂屈伸",
    "V-bar pulldown": "V-bar下拉",
    "Wide grip lat pulldown": "宽距高位下拉",
    "Wide-stance horizontal leg press": "器械倒蹬",
    "Zercher squat": "泽奇深蹲",
    "[步行] Walking": "快走",
}


# One movement logged under two Chinese names in different periods. None of
# these pairs ever share a training day, and their loads overlap, so each is
# a rename rather than a second exercise. Confirmed against the training log.
_SAME_MOVEMENT: dict[str, str] = {
    "俯身飞鸟": "器械坐姿反向飞鸟",
    "器械推胸": "下斜悍马机推胸",
    "站姿器械提踵": "坐姿器械提踵",
    "绳索侧平举": "绳索侧平举（单边）",
    "卷腹": "下斜卷腹",
    "哑铃锤式交替弯举": "锤式弯举",
    "器械下拉": "宽距高位下拉",
    "器械坐姿推举": "悍马机坐姿推举",
    "悍马机推胸": "下斜悍马机推胸",
    "挂片器划船": "T杆划船",
    "罗马尼亚硬拉": "杠铃罗马尼亚硬拉",
    "腿举": "器械倒蹬",
    "腿弯举": "坐姿腿弯举",
    "蝴蝶机反向飞鸟": "器械坐姿反向飞鸟",
    "蝴蝶机飞鸟": "把手式蝴蝶机飞鸟",
}

ALIASES.update(_SAME_MOVEMENT)


# Which muscle the movement is logged against. The Xunji sync writes no muscle
# group at all, and an import overwrites the column from the export, so the
# mapping lives here and is re-applied on every run rather than being typed
# into the database once.
MUSCLE_GROUPS: dict[str, str] = {
    # 胸
    "杠铃卧推": "胸",
    "上斜杠铃卧推": "胸",
    "上斜哑铃卧推": "胸",
    "下斜悍马机推胸": "胸",
    "把手式蝴蝶机飞鸟": "胸",
    # 背
    "坐姿划船": "背",
    "宽距高位下拉": "背",
    "分动式高位划船": "背",
    "T杆划船": "背",
    "绳索直臂下压": "背",
    # 肩：三角肌前中束与后束分开，后束跟着背练但要单独看量
    "悍马机坐姿推举": "肩",
    "绳索侧平举（单边）": "肩",
    "侧平举": "肩",
    "面拉": "后束",
    "器械坐姿反向飞鸟": "后束",
    # 手臂
    "绳索弯举": "二头",
    "上斜哑铃弯举": "二头",
    "锤式弯举": "二头",
    "蜘蛛弯举": "二头",
    "牧师凳弯举": "二头",
    "EZ杆二头弯举": "二头",
    "哑铃弯举": "二头",
    "绳索臂屈伸": "三头",
    "绳索过头臂屈伸": "三头",
    "直杆绳索下压": "三头",
    # 腿
    "泽奇深蹲": "股四头",
    "杠铃深蹲": "股四头",
    "哑铃深蹲": "股四头",
    "哑铃保加利亚蹲": "股四头",
    "器械倒蹬": "股四头",
    "坐姿腿屈伸": "股四头",
    "杠铃罗马尼亚硬拉": "腘绳",
    "坐姿腿弯举": "腘绳",
    "臀冲架臀冲": "臀",
    "坐姿髋内收": "内收肌",
    "坐姿器械提踵": "小腿",
    # 核心
    "悬挂抬腿": "核心",
    "平板蝴蝶收腹": "核心",
    "平板支撑_计时": "核心",
    "绳索Pallof推": "核心",
    "下斜卷腹": "核心",
    "死虫": "核心",
    "俄罗斯转体": "核心",
    "登山者-Tabata": "核心",
    # 有氧：功能性力量训练按用户的口径也算有氧
    "快走": "有氧",
    "功能性力量训练": "有氧",
}


# These names are valid historical data but have no unambiguous one-to-one
# official movement equivalent.  They are reported for manual review.
UNRESOLVED = {
    "Chest supported row",
    "Mountain climber",
    "TraditionalStrengthTraining",
}


def _json_paths(export_dir: Path) -> list[Path]:
    return sorted(export_dir.rglob("*.json"))


def _normalise_history_version(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def update_exports(export_dir: Path, dry_run: bool) -> tuple[int, int, dict[str, int]]:
    changed_files = 0
    changed_actions = 0
    action_counts: dict[str, int] = {}
    grouped_actions = [0]
    for path in _json_paths(export_dir):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        workout = payload.get("workout")
        if not isinstance(workout, dict):
            continue
        changed = False
        for exercise in workout.get("exercises", []):
            if not isinstance(exercise, dict):
                continue
            old = exercise.get("exercise_name")
            new = ALIASES.get(old)
            if new and old != new:
                exercise["exercise_name"] = new
                changed = True
                changed_actions += 1
                action_counts[f"{old} -> {new}"] = action_counts.get(f"{old} -> {new}", 0) + 1
            group = MUSCLE_GROUPS.get(exercise.get("exercise_name"))
            if group and exercise.get("muscle_group") != group:
                exercise["muscle_group"] = group
                changed = True
                grouped_actions[0] += 1
        if changed:
            changed_files += 1
            if not dry_run:
                payload["history_version"] = _normalise_history_version(payload.get("history_version")) + 1
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed_files, changed_actions, action_counts, grouped_actions[0]


def normalize_database(database: Path, dry_run: bool) -> tuple[int, int, int]:
    """Merge aliases in one DB, returning (merged_names, moved_sets, remaining)."""
    if not database.exists():
        return 0, 0, 0
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA foreign_keys = ON")
    merged_names = moved_sets = 0
    try:
        connection.execute("BEGIN")
        # Group aliases that converge on one official name.  Some historical
        # sessions contain two aliases for the same movement; append those
        # sets after the existing target sets so the UNIQUE(session, exercise,
        # set_number) constraint is preserved without dropping data.
        grouped: dict[str, list[str]] = {}
        for old, new in ALIASES.items():
            grouped.setdefault(new, []).append(old)
        for new, old_names in grouped.items():
            target_row = connection.execute("SELECT id FROM exercises WHERE name = ?", (new,)).fetchone()
            if target_row:
                target_id = target_row[0]
            else:
                first_name = None
                first = None
                for old in old_names:
                    first = connection.execute("SELECT id FROM exercises WHERE name = ?", (old,)).fetchone()
                    if first:
                        first_name = old
                        break
                if not first:
                    continue
                target_id = first[0]
                connection.execute("UPDATE exercises SET name = ? WHERE id = ?", (new, target_id))
                merged_names += 1
                old_names = [old for old in old_names if old != first_name]
            for old in old_names:
                old_row = connection.execute("SELECT id FROM exercises WHERE name = ?", (old,)).fetchone()
                if not old_row or old == new:
                    continue
                old_id = old_row[0]
                rows = connection.execute(
                    "SELECT id, workout_session_id FROM exercise_sets "
                    "WHERE exercise_id = ? ORDER BY workout_session_id, set_number, id",
                    (old_id,),
                ).fetchall()
                by_session: dict[int, list[int]] = {}
                for set_id, session_id in rows:
                    by_session.setdefault(session_id, []).append(set_id)
                for session_id, set_ids in by_session.items():
                    next_number = connection.execute(
                        "SELECT COALESCE(MAX(set_number), 0) FROM exercise_sets "
                        "WHERE workout_session_id = ? AND exercise_id = ?",
                        (session_id, target_id),
                    ).fetchone()[0]
                    for offset, set_id in enumerate(set_ids, 1):
                        connection.execute(
                            "UPDATE exercise_sets SET exercise_id = ?, set_number = ? WHERE id = ?",
                            (target_id, next_number + offset, set_id),
                        )
                moved_sets += len(rows)
                connection.execute("DELETE FROM exercises WHERE id = ?", (old_id,))
                merged_names += 1
        for name, group in MUSCLE_GROUPS.items():
            connection.execute(
                "UPDATE exercises SET muscle_group = ? WHERE name = ? "
                "AND (muscle_group IS NOT ?)",
                (group, name, group),
            )
        remaining = connection.execute(
            "SELECT COUNT(*) FROM exercises WHERE name IN (%s)" % ",".join("?" * len(ALIASES)),
            tuple(ALIASES),
        ).fetchone()[0]
        if dry_run:
            connection.rollback()
        else:
            connection.commit()
        return merged_names, moved_sets, remaining
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT_DIR)
    parser.add_argument("--database", type=Path, action="append", dest="databases")
    parser.add_argument("--dry-run", action="store_true", help="只报告，不写文件或数据库")
    args = parser.parse_args()
    databases = tuple(args.databases or DEFAULT_DATABASES)

    files, actions, counts, groups = update_exports(args.export_dir, args.dry_run)
    print(
        f"导出文件：{files} 个文件，{actions} 个动作名称将标准化，"
        f"{groups} 处肌群将补全" + ("（dry-run）" if args.dry_run else "")
    )
    for mapping, count in sorted(counts.items()):
        print(f"  {count} × {mapping}")
    print("未自动修改：" + "、".join(sorted(UNRESOLVED)))
    for database in databases:
        merged, moved, remaining = normalize_database(database, args.dry_run)
        print(f"数据库 {database}: 合并/改名 {merged} 个，迁移 {moved} 组，未匹配旧别名 {remaining} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
