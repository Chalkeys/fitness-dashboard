"""Import approved Export Protocol v1 JSON files from a directory."""

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.init_db import DEFAULT_DATABASE, connect_database, initialize_database  # noqa: E402
from scripts.import_history import (  # noqa: E402
    _import_daily_logs,
    _import_measurements,
    _import_nutrition,
    _import_workouts,
)
from scripts.validate_export import validate_export  # noqa: E402

DEFAULT_EXPORT_DIR = PROJECT_ROOT / "exports"
DATASET_IMPORTERS = {
    "daily_logs": _import_daily_logs,
    "body_measurements": _import_measurements,
    "nutrition_entries": _import_nutrition,
    "workouts": _import_workouts,
}


def scan_exports(export_dir: Path, file_filter: str | None = None) -> list[Path]:
    files = sorted(Path(export_dir).glob("*.json"))
    if file_filter:
        files = [
            path for path in files
            if path.name == file_filter or path.stem == file_filter
        ]
    return files


def import_exports(
    export_dir: Path = DEFAULT_EXPORT_DIR,
    database_path: Path = DEFAULT_DATABASE,
    dry_run: bool = False,
    replace: bool = False,
    since: str | None = None,
    file_filter: str | None = None,
    include_needs_review: bool = False,
) -> dict[str, int]:
    """Validate and import all selected approved exports atomically."""
    if since:
        try:
            if datetime.strptime(since, "%Y-%m-%d").strftime("%Y-%m-%d") != since:
                raise ValueError
        except ValueError as error:
            raise ValueError("--since 必须使用 YYYY-MM-DD") from error
    requested_file = Path(file_filter) if file_filter else None
    paths = [requested_file] if requested_file and requested_file.is_file() else scan_exports(export_dir, file_filter)
    if any(_is_daily_protocol(path) for path in paths):
        from scripts.daily_export_import import import_daily_exports

        return import_daily_exports(
            Path(file_filter) if file_filter and Path(file_filter).is_file() else Path(export_dir),
            database_path,
            dry_run,
            replace,
            since,
            file_filter,
            include_needs_review,
        )
    documents: list[tuple[Path, dict[str, Any], str]] = []
    errors: list[str] = []
    for path in scan_exports(export_dir, file_filter):
        document, file_errors, warnings = validate_export(path)
        if file_errors:
            errors.extend(f"{path.name}: {error}" for error in file_errors)
            continue
        if since and document["history_version"] < since:
            continue
        source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        documents.append((path, document, source_hash))
        if warnings:
            for warning in warnings:
                print(f"警告：{path.name}：{warning}")
    if errors:
        raise ValueError("\n".join(errors))
    documents.sort(key=lambda item: (item[1]["history_version"], item[0].name))
    stats = {"files": 0, "new": 0, "modified": 0, "skipped": 0, "failed": 0}
    if dry_run:
        for path, document, source_hash in documents:
            if document["review_status"] != "approved":
                stats["skipped"] += 1
            else:
                stats["files"] += 1
                stats["new"] += _document_record_count(document)
        return stats

    initialize_database(Path(database_path))
    connection = connect_database(Path(database_path))
    try:
        connection.execute("BEGIN")
        if replace:
            _replace_imported_history(connection, {path.name for path, _, _ in documents})
        for path, document, source_hash in documents:
            result = _import_one(connection, path, document, source_hash, replace)
            for key, value in result.items():
                stats[key] += value
        connection.commit()
    except Exception as error:
        connection.rollback()
        stats["failed"] = len(documents)
        _record_failed_imports(Path(database_path), documents, str(error))
        raise
    finally:
        connection.close()
    return stats


def _document_record_count(document: dict[str, Any]) -> int:
    return sum(len(records) for records in document["datasets"].values()) + len(document["foods"])


def _import_one(
    connection: Any,
    path: Path,
    document: dict[str, Any],
    source_hash: str,
    replace: bool,
) -> dict[str, int]:
    filename = path.name
    if document["review_status"] != "approved":
        _write_import_log(connection, filename, source_hash, 0, 0, 1, 0, "skipped", "review_status is not approved")
        return {"files": 0, "new": 0, "modified": 0, "skipped": 1, "failed": 0}
    if not replace and connection.execute(
        "SELECT 1 FROM import_log WHERE filename = ? AND sha256 = ?",
        (filename, source_hash),
    ).fetchone():
        return {"files": 0, "new": 0, "modified": 0, "skipped": 1, "failed": 0}
    if not replace and _older_than_existing(connection, document):
        _write_import_log(connection, filename, source_hash, 0, 0, 1, 0, "skipped", "older history_version")
        return {"files": 0, "new": 0, "modified": 0, "skipped": 1, "failed": 0}

    before = _history_counts(connection)
    for name, records in document["datasets"].items():
        DATASET_IMPORTERS[name](connection, records, document["history_version"])
    _upsert_export_foods(connection, document["foods"])
    after = _history_counts(connection)
    new_count = sum(max(0, after[name] - before[name]) for name in before)
    processed = _document_record_count(document)
    modified_count = max(0, processed - new_count)
    _write_import_log(
        connection, filename, source_hash, new_count, modified_count, 0, 0, "imported", "approved"
    )
    return {"files": 1, "new": new_count, "modified": modified_count, "skipped": 0, "failed": 0}


def _history_counts(connection: Any) -> dict[str, int]:
    return {
        "daily_logs": connection.execute(
            "SELECT COUNT(*) FROM daily_logs WHERE history_version IS NOT NULL"
        ).fetchone()[0],
        "body_measurements": connection.execute(
            "SELECT COUNT(*) FROM body_measurements WHERE history_version IS NOT NULL"
        ).fetchone()[0],
        "nutrition_entries": connection.execute(
            "SELECT COUNT(*) FROM nutrition_entries WHERE history_version IS NOT NULL"
        ).fetchone()[0],
        "workouts": connection.execute(
            "SELECT COUNT(*) FROM workout_sessions WHERE history_version IS NOT NULL"
        ).fetchone()[0],
    }


def _older_than_existing(connection: Any, document: dict[str, Any]) -> bool:
    version = document["history_version"]
    dates = [record.get("date") for record in document["datasets"]["daily_logs"]]
    dates += [record.get("measured_at") for record in document["datasets"]["body_measurements"]]
    for date in dates:
        existing = connection.execute(
            "SELECT MAX(history_version) FROM daily_logs WHERE log_date = ?",
            (date,),
        ).fetchone()[0]
        if existing and existing > version:
            return True
    for workout in document["datasets"]["workouts"]:
        existing = connection.execute(
            """
            SELECT MAX(s.history_version) FROM workout_sessions s
            JOIN daily_logs d ON d.id = s.daily_log_id
            WHERE d.log_date = ? AND s.name = ?
            """,
            (workout.get("date"), workout.get("workout_name") or "Workout"),
        ).fetchone()[0]
        if existing and existing > version:
            return True
    return False


def _replace_imported_history(connection: Any, filenames: set[str]) -> None:
    connection.execute("DELETE FROM nutrition_entries WHERE history_version IS NOT NULL")
    session_ids = connection.execute(
        "SELECT id FROM workout_sessions WHERE history_version IS NOT NULL"
    ).fetchall()
    for row in session_ids:
        connection.execute("DELETE FROM exercise_sets WHERE workout_session_id = ?", (row[0],))
    connection.execute("DELETE FROM workout_sessions WHERE history_version IS NOT NULL")
    connection.execute("DELETE FROM body_measurements WHERE history_version IS NOT NULL")
    connection.execute("DELETE FROM daily_logs WHERE history_version IS NOT NULL")
    if filenames:
        marks = ",".join("?" for _ in filenames)
        connection.execute(f"DELETE FROM import_log WHERE filename IN ({marks})", tuple(filenames))


def _upsert_export_foods(connection: Any, foods: list[dict[str, Any]]) -> None:
    for food in foods:
        connection.execute(
            """
            INSERT INTO foods (
                food_name, brand, default_unit, calories, protein_g,
                total_carbs_g, fiber_g, net_carbs_g, fat_g, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (brand, food_name) DO UPDATE SET
                default_unit = excluded.default_unit,
                calories = excluded.calories,
                protein_g = excluded.protein_g,
                total_carbs_g = excluded.total_carbs_g,
                fiber_g = excluded.fiber_g,
                net_carbs_g = excluded.net_carbs_g,
                fat_g = excluded.fat_g,
                notes = excluded.notes,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                food["food_name"],
                food.get("brand") or "",
                food.get("default_unit") or "serving",
                food.get("calories") or 0,
                food.get("protein_g") or 0,
                food.get("total_carbs_g") or 0,
                food.get("fiber_g") or 0,
                food.get("net_carbs_g") or 0,
                food.get("fat_g") or 0,
                food.get("notes"),
            ),
        )


def _write_import_log(
    connection: Any,
    filename: str,
    source_hash: str,
    new_count: int,
    modified_count: int,
    skipped_count: int,
    failed_count: int,
    status: str,
    notes: str,
) -> None:
    connection.execute(
        """
        INSERT INTO import_log (
            filename, sha256, new_count, modified_count, skipped_count,
            failed_count, status, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (filename, sha256) DO UPDATE SET
            imported_at = CURRENT_TIMESTAMP,
            new_count = excluded.new_count,
            modified_count = excluded.modified_count,
            skipped_count = excluded.skipped_count,
            failed_count = excluded.failed_count,
            status = excluded.status,
            notes = excluded.notes
        """,
        (filename, source_hash, new_count, modified_count, skipped_count, failed_count, status, notes),
    )


def _record_failed_imports(
    database_path: Path,
    documents: list[tuple[Path, dict[str, Any], str]],
    notes: str,
) -> None:
    connection = connect_database(database_path)
    try:
        for path, _, source_hash in documents:
            _write_import_log(connection, path.name, source_hash, 0, 0, 0, 1, "failed", notes)
        connection.commit()
    finally:
        connection.close()


def _print_stats(stats: dict[str, int], dry_run: bool) -> None:
    prefix = "Dry-run 完成" if dry_run else "导入完成"
    inserted = stats.get("inserted", stats.get("new", 0))
    updated = stats.get("updated", stats.get("modified", 0))
    print(f"{prefix}：文件 {stats['files']}，新增 {inserted}，修改 {updated}，跳过 {stats['skipped']}，失败 {stats['failed']}")


def _is_daily_protocol(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("protocol_version") == "1.0"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=DEFAULT_EXPORT_DIR)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--since", help="只处理 history_version 不早于 YYYY-MM-DD 的文件")
    parser.add_argument("--file", help="文件名或不带扩展名的文件 stem")
    parser.add_argument("--include-needs-review", action="store_true")
    parser.add_argument(
        "--no-normalize",
        action="store_true",
        help="跳过导入后的动作名与肌群标准化",
    )
    args = parser.parse_args()
    try:
        stats = import_exports(
            args.directory.resolve(), args.database.resolve(), args.dry_run,
            args.replace, args.since, args.file,
            args.include_needs_review,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"导入失败：{error}")
        raise SystemExit(1) from error
    _print_stats(stats, args.dry_run)

    if not args.dry_run and not args.no_normalize:
        _normalize_after_import(args.directory.resolve(), args.database.resolve())


def _normalize_after_import(export_dir: Path, database: Path) -> None:
    """Re-apply the exercise aliases and muscle groups the import just undid.

    An export carries `muscle_group: null` for anything the training-app sync
    wrote, and the import copies that straight over the column, so a fresh day
    blanks the groups for every exercise it mentions. Running it here means
    that cannot be forgotten.
    """
    from scripts.normalize_exercise_names import normalize_database, update_exports

    print()
    files, actions, _, groups = update_exports(export_dir, dry_run=False)
    merged, moved, _ = normalize_database(database, dry_run=False)
    print(
        f"标准化：导出 {files} 个文件（{actions} 个名称、{groups} 处肌群），"
        f"数据库合并 {merged} 个动作、迁移 {moved} 组"
    )


if __name__ == "__main__":
    main()
