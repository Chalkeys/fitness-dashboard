"""Implementation for the daily Export Protocol v1 importer."""

import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from scripts.import_history import _net_carbs, _value
from scripts.validate_exports import (
    DEFAULT_EXPORT_DIR,
    export_paths,
    review_status,
    validate_document,
)

MAX_REPORTED_REASONS = 5


def import_daily_exports(
    target: Path = DEFAULT_EXPORT_DIR,
    database_path: Path | None = None,
    dry_run: bool = False,
    replace: bool = False,
    since: str | None = None,
    file_filter: str | None = None,
    include_needs_review: bool = False,
) -> dict[str, int]:
    from database.init_db import DEFAULT_DATABASE, connect_database, initialize_database

    database_path = database_path or DEFAULT_DATABASE
    paths = _filtered_paths(target, file_filter)
    stats = {"files": 0, "inserted": 0, "updated": 0, "skipped": 0, "failed": 0}
    for path in paths:
        report = validate_document(path, _schema())
        document = report.get("document")
        if report["errors"]:
            stats["failed"] += 1
            _report(path, "校验失败", report["errors"])
            if not dry_run:
                _record_run_failure(database_path, path, document, report["errors"])
            continue
        if since and document.get("date") and document["date"] < since:
            stats["skipped"] += 1
            continue
        source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        status = review_status(document)
        if status != "approved" and not (include_needs_review and status == "needs_review"):
            stats["skipped"] += 1
            _report(path, "跳过", [f"review_status 为 {status}"])
            if not dry_run:
                _record_run(
                    database_path, document, path, source_hash, "skipped", 0, 0, 1, None
                )
            continue
        if dry_run:
            stats["files"] += 1
            stats["inserted"] += _document_count(document)
            continue
        initialize_database(database_path)
        connection = connect_database(database_path)
        try:
            connection.execute("BEGIN")
            if not replace and _same_hash(connection, path.name, source_hash):
                connection.rollback()
                stats["skipped"] += 1
                continue
            if not replace and _version_is_stale(connection, document):
                _report(path, "跳过", ["history_version 不比库里的新"])
                _record_run_on_connection(
                    connection, document, path, source_hash, "skipped", 0, 0, 1, "older history_version"
                )
                connection.commit()
                stats["skipped"] += 1
                continue
            if replace or _has_export(connection, document["export_id"]):
                _clear_export(connection, document["export_id"])
            before = _formal_count(connection, document["export_id"])
            _import_document(connection, document, path.read_text(encoding="utf-8"))
            after = _formal_count(connection, document["export_id"])
            inserted = max(0, after - before)
            processed = _document_count(document)
            updated = max(0, processed - inserted)
            _record_run_on_connection(
                connection, document, path, source_hash, "imported", inserted, updated, 0, None
            )
            connection.commit()
            stats["files"] += 1
            stats["inserted"] += inserted
            stats["updated"] += updated
        except Exception as error:
            connection.rollback()
            _report(path, "导入出错", [str(error)])
            _record_run_failure(database_path, path, document, [str(error)], source_hash)
            stats["failed"] += 1
        finally:
            connection.close()
    return stats


def _report(path: Path, headline: str, reasons: list[str]) -> None:
    """Say why a file did not go in.

    The summary line at the end counts failures and skips but never explains
    them, and the reasons only reach the ``export_runs`` table, where nobody
    looks unless they already suspect something. A schema change that closed
    the door on two new fields once read as a bare "失败 1" for a whole
    deploy. Diagnostics go to stderr so the summary line stays parseable.
    """
    for reason in reasons[:MAX_REPORTED_REASONS]:
        print(f"{headline}：{path.name}：{reason}", file=sys.stderr)
    remaining = len(reasons) - MAX_REPORTED_REASONS
    if remaining > 0:
        print(f"{headline}：{path.name}：另有 {remaining} 条未列出", file=sys.stderr)


def _schema() -> dict[str, Any]:
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "daily_export_v1.schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _filtered_paths(target: Path, file_filter: str | None) -> list[Path]:
    if file_filter:
        candidate = Path(file_filter)
        if candidate.is_file():
            return [candidate]
        return export_paths(target) if candidate.name == "" else [
            path for path in export_paths(target)
            if path.name == candidate.name or path.stem == candidate.stem
        ]
    return export_paths(target)


def _document_count(document: dict[str, Any]) -> int:
    nutrition_count = len(document.get("nutrition", []))
    workout = document.get("workout")
    set_count = sum(len(exercise.get("sets", [])) for exercise in (workout or {}).get("exercises", []))
    return 1 + nutrition_count + (1 if workout else 0) + (1 if document.get("body") else 0) + set_count


def _same_hash(connection: sqlite3.Connection, filename: str, file_hash: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM export_runs WHERE file_hash = ? AND status = 'imported'",
        (file_hash,),
    ).fetchone() is not None


def _has_export(connection: sqlite3.Connection, export_id: str) -> bool:
    for table in ("daily_logs", "nutrition_entries", "workout_sessions", "body_measurements"):
        if connection.execute(f"SELECT 1 FROM {table} WHERE export_id = ? LIMIT 1", (export_id,)).fetchone():
            return True
    return False


def _version_is_stale(connection: sqlite3.Connection, document: dict[str, Any]) -> bool:
    row = connection.execute(
        "SELECT MAX(history_version) FROM export_runs "
        "WHERE export_id = ? AND status = 'imported'",
        (document["export_id"],),
    ).fetchone()[0]
    return row is not None and int(row) >= int(document["history_version"])


def _clear_export(connection: sqlite3.Connection, export_id: str) -> None:
    connection.execute("DELETE FROM nutrition_entries WHERE export_id = ?", (export_id,))
    session_ids = connection.execute(
        "SELECT id FROM workout_sessions WHERE export_id = ?", (export_id,)
    ).fetchall()
    for row in session_ids:
        connection.execute("DELETE FROM exercise_sets WHERE workout_session_id = ?", (row[0],))
    connection.execute("DELETE FROM workout_sessions WHERE export_id = ?", (export_id,))
    connection.execute("DELETE FROM body_measurements WHERE export_id = ?", (export_id,))
    connection.execute("DELETE FROM daily_logs WHERE export_id = ?", (export_id,))
    connection.execute("DELETE FROM staged_daily_exports WHERE export_id = ?", (export_id,))
    connection.execute("DELETE FROM export_runs WHERE export_id = ?", (export_id,))


def _formal_count(connection: sqlite3.Connection, export_id: str) -> int:
    return sum(
        connection.execute(f"SELECT COUNT(*) FROM {table} WHERE export_id = ?", (export_id,)).fetchone()[0]
        for table in ("daily_logs", "body_measurements", "nutrition_entries", "workout_sessions", "exercise_sets")
    )


def _daily_id(connection: sqlite3.Connection, date_value: str) -> int:
    connection.execute(
        "INSERT INTO daily_logs (log_date) VALUES (?) ON CONFLICT (log_date) DO NOTHING",
        (date_value,),
    )
    return connection.execute("SELECT id FROM daily_logs WHERE log_date = ?", (date_value,)).fetchone()[0]


def _metadata(document: dict[str, Any]) -> tuple[Any, ...]:
    provenance = document.get("provenance") or {}
    notes = [item.get("note") for item in document.get("review", []) if item.get("note")]
    return (
        document["export_id"],
        document["history_version"],
        provenance.get("source"),
        provenance.get("confidence"),
        review_status(document),
        "; ".join(notes) or None,
    )


def _import_document(connection: sqlite3.Connection, document: dict[str, Any], raw_json: str) -> None:
    metadata = _metadata(document)
    if document.get("date") is None:
        connection.execute(
            """
            INSERT INTO staged_daily_exports (
                export_id, history_version, day_number, date, raw_json, review_status
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (export_id, history_version) DO UPDATE SET
                day_number = excluded.day_number, raw_json = excluded.raw_json,
                review_status = excluded.review_status, created_at = CURRENT_TIMESTAMP
            """,
            (document["export_id"], document["history_version"], document.get("day_number"), None, raw_json, metadata[4]),
        )
        return
    date_value = document["date"]
    daily_id = _daily_id(connection, date_value)
    daily = document.get("daily_log") or {}
    calories = _value(daily, "calories_in")
    tdee = _value(daily, "tdee")
    connection.execute(
        """
        UPDATE daily_logs SET
            day_number = ?, is_training_day = ?, training_type = ?, calories_intake = ?,
            tdee = ?, calorie_balance = ?, protein_g = ?, total_carbs_g = ?, fiber_g = ?,
            net_carbs_g = ?, fat_g = ?, steps = ?, active_energy = ?, notes = ?,
            history_version = ?, export_id = ?, source = ?, confidence = ?,
            review_status = ?, review_notes = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            document.get("day_number"), int(bool(_value(daily, "is_training_day", False))),
            daily.get("workout_type"), calories, tdee, calories - tdee,
            _value(daily, "protein_g"), _value(daily, "total_carbs_g"), _value(daily, "fiber_g"),
            _value(daily, "net_carbs_g", _value(daily, "total_carbs_g") - _value(daily, "fiber_g")),
            _value(daily, "fat_g"), _value(daily, "steps"), _value(daily, "active_energy_kcal"),
            daily.get("notes"), metadata[1], metadata[0], metadata[2], metadata[3], metadata[4], metadata[5], daily_id,
        ),
    )
    _import_body(connection, document, daily_id, metadata)
    _import_nutrition(connection, document, date_value, metadata)
    _import_workout(connection, document, daily_id, metadata)


def _import_body(connection: sqlite3.Connection, document: dict[str, Any], daily_id: int, metadata: tuple[Any, ...]) -> None:
    body = document.get("body")
    if not body:
        return
    connection.execute(
        "DELETE FROM body_measurements WHERE export_id = ? OR measured_at = ?",
        (metadata[0], document["date"]),
    )
    connection.execute(
        """
        INSERT INTO body_measurements (
            daily_log_id, measured_at, weight_kg, waist_cm, body_fat_percentage,
            neck_cm, chest_cm, shoulder_cm, hip_cm, arm_left_cm, arm_right_cm,
            forearm_left_cm, forearm_right_cm, leg_left_cm, leg_right_cm,
            calf_left_cm, calf_right_cm, notes, history_version, export_id,
            source, confidence, review_status, review_notes
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            daily_id,
            document["date"],
            body.get("weight_kg"),
            body.get("waist_cm"),
            body.get("body_fat_percentage"),
            body.get("neck_cm"),
            body.get("chest_cm"),
            body.get("shoulder_cm"),
            body.get("hip_cm"),
            body.get("arm_left_cm"),
            body.get("arm_right_cm"),
            body.get("forearm_left_cm"),
            body.get("forearm_right_cm"),
            body.get("leg_left_cm"),
            body.get("leg_right_cm"),
            body.get("calf_left_cm"),
            body.get("calf_right_cm"),
            body.get("notes"),
            metadata[1],
            metadata[0],
            *metadata[2:],
        ),
    )


def _food_id(connection: sqlite3.Connection, entry: dict[str, Any]) -> int:
    brand = entry.get("brand") or ""
    name = entry["food_name"]
    row = connection.execute("SELECT id FROM foods WHERE brand = ? AND food_name = ?", (brand, name)).fetchone()
    if row:
        return row[0]
    default_unit = {
        "grams": "g", "servings": "serving", "bottles": "bottle", "pieces": "piece"
    }.get(entry.get("unit"), entry.get("unit") or "custom")
    if default_unit not in {"g", "serving", "bottle", "piece", "custom"}:
        default_unit = "custom"
    cursor = connection.execute(
        """
        INSERT INTO foods (food_name, brand, default_unit, calories, protein_g, total_carbs_g, fiber_g, net_carbs_g, fat_g, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (name, brand, default_unit, entry.get("calories") or 0, entry.get("protein_g") or 0, entry.get("total_carbs_g") or 0, entry.get("fiber_g") or 0, entry.get("net_carbs_g") or 0, entry.get("fat_g") or 0, "[daily export snapshot]"),
    )
    return cursor.lastrowid


def _import_nutrition(connection: sqlite3.Connection, document: dict[str, Any], date_value: str, metadata: tuple[Any, ...]) -> None:
    for entry in document.get("nutrition", []):
        food_id = _food_id(connection, entry)
        unit = {
            "grams": "g", "servings": "serving", "bottles": "bottle", "pieces": "piece"
        }.get(entry.get("unit"), entry.get("unit") or "custom")
        values = (date_value, entry["meal_type"], food_id, entry.get("amount") or 0, unit, entry.get("calories") or 0, entry.get("protein_g") or 0, entry.get("total_carbs_g") or 0, entry.get("fiber_g") or 0, entry.get("net_carbs_g") if entry.get("net_carbs_g") is not None else (entry.get("total_carbs_g") or 0) - (entry.get("fiber_g") or 0), entry.get("fat_g") or 0, entry.get("servings"), entry.get("notes"), metadata[1], metadata[0], *metadata[2:], entry["entry_id"])
        connection.execute("DELETE FROM nutrition_entries WHERE export_id = ? AND entry_id = ?", (metadata[0], entry["entry_id"]))
        connection.execute(
            """
            INSERT INTO nutrition_entries (
                log_date, meal_type, food_id, amount, unit, calories, protein_g, carbs_g,
                fiber_g, net_carbs_g, fat_g, servings, notes, history_version, export_id,
                source, confidence, review_status, review_notes, entry_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )


def _import_workout(connection: sqlite3.Connection, document: dict[str, Any], daily_id: int, metadata: tuple[Any, ...]) -> None:
    workout = document.get("workout")
    if not workout:
        return
    connection.execute("DELETE FROM workout_sessions WHERE export_id = ?", (metadata[0],))
    cursor = connection.execute(
        """
        INSERT INTO workout_sessions (
            daily_log_id, name, workout_type, duration_minutes, active_energy_kcal, notes,
            history_version, export_id, session_id, source, confidence, review_status, review_notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            daily_id,
            workout["workout_name"],
            workout.get("workout_type"),
            workout.get("duration_minutes"),
            workout.get("active_energy_kcal"),
            workout.get("notes"),
            metadata[1],
            metadata[0],
            workout["session_id"],
            *metadata[2:],
        ),
    )
    session_id = cursor.lastrowid
    for exercise in workout.get("exercises", []):
        connection.execute(
            "INSERT INTO exercises (name, category, muscle_group) VALUES (?, ?, ?) ON CONFLICT(name) DO UPDATE SET category=excluded.category, muscle_group=excluded.muscle_group",
            (exercise["exercise_name"], exercise.get("category") or "other", exercise.get("muscle_group")),
        )
        exercise_id = connection.execute("SELECT id FROM exercises WHERE name = ?", (exercise["exercise_name"],)).fetchone()[0]
        for item in exercise.get("sets", []):
            connection.execute(
                """
                INSERT INTO exercise_sets (
                    workout_session_id, exercise_id, set_number, weight_kg, reps, rir,
                    distance_meters, duration_seconds, notes, history_version, export_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, exercise_id, item["set_number"], item.get("weight"), item.get("reps"), item.get("rir"), item.get("distance"), item.get("duration_seconds"), item.get("notes"), metadata[1], metadata[0]),
            )


def _record_run_on_connection(connection: sqlite3.Connection, document: dict[str, Any], path: Path, file_hash: str, status: str, inserted: int, updated: int, skipped: int, error: str | None) -> None:
    connection.execute(
        """
        INSERT INTO export_runs (export_id, history_version, filename, file_hash, status, inserted_count, updated_count, skipped_count, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(export_id, history_version) DO UPDATE SET
            filename=excluded.filename, file_hash=excluded.file_hash, imported_at=CURRENT_TIMESTAMP,
            status=excluded.status, inserted_count=excluded.inserted_count, updated_count=excluded.updated_count,
            skipped_count=excluded.skipped_count, error_message=excluded.error_message
        """,
        (document["export_id"], document["history_version"], path.name, file_hash, status, inserted, updated, skipped, error),
    )


def _record_run(database_path: Path, document: dict[str, Any], path: Path, file_hash: str, status: str, inserted: int, updated: int, skipped: int, error: str | None) -> None:
    from database.init_db import connect_database
    connection = connect_database(database_path)
    try:
        _record_run_on_connection(connection, document, path, file_hash, status, inserted, updated, skipped, error)
        connection.commit()
    finally:
        connection.close()


def _record_run_failure(database_path: Path, path: Path, document: dict[str, Any] | None, errors: list[str], file_hash: str | None = None) -> None:
    if not document:
        return
    _record_run(database_path, document, path, file_hash or hashlib.sha256(path.read_bytes()).hexdigest(), "failed", 0, 0, 0, "; ".join(errors))
