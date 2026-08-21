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
    "Alternating hammer curl": "哑铃锤式交替弯举",
    "Barbell bench press": "杠铃卧推",
    "Barbell squat": "杠铃深蹲",
    "Bulgarian split squat": "哑铃保加利亚蹲",
    "Cable curl": "绳索弯举",
    "Cable lateral raise": "绳索侧平举",
    "Cable pushdown": "绳索臂屈伸",
    "Calf raise": "站姿器械提踵",
    "Crunch": "卷腹",
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
    "Hammer strength chest press": "悍马机推胸",
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
    "Lat pulldown": "器械下拉",
    "Lateral raise": "侧平举",
    "Leg curl": "腿弯举",
    "Leg extension": "坐姿腿屈伸",
    "Leg press": "腿举",
    "Machine chest press": "器械推胸",
    "Machine fly": "蝴蝶机飞鸟",
    "Machine shoulder press": "器械坐姿推举",
    "Overhead triceps extension": "绳索过头臂屈伸",
    "Pallof press": "绳索Pallof推",
    "Plank": "平板支撑_计时",
    "Preacher EZ-bar curl": "牧师凳弯举",
    "Preacher barbell curl": "牧师凳弯举",
    "Preacher curl": "牧师凳弯举",
    "ProMaxima T-bar row": "T杆划船",
    "Reverse fly": "俯身飞鸟",
    "Reverse pec deck": "蝴蝶机反向飞鸟",
    "Reverse-grip cable pushdown": "站姿绳索反握弯举_直杆",
    "Romanian deadlift": "罗马尼亚硬拉",
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
    "Standing plate-loaded T-bar row": "挂片器划船",
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
        if changed:
            changed_files += 1
            if not dry_run:
                payload["history_version"] = _normalise_history_version(payload.get("history_version")) + 1
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed_files, changed_actions, action_counts


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

    files, actions, counts = update_exports(args.export_dir, args.dry_run)
    print(f"导出文件：{files} 个文件，{actions} 个动作名称将标准化" + ("（dry-run）" if args.dry_run else ""))
    for mapping, count in sorted(counts.items()):
        print(f"  {count} × {mapping}")
    print("未自动修改：" + "、".join(sorted(UNRESOLVED)))
    for database in databases:
        merged, moved, remaining = normalize_database(database, args.dry_run)
        print(f"数据库 {database}: 合并/改名 {merged} 个，迁移 {moved} 组，未匹配旧别名 {remaining} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
