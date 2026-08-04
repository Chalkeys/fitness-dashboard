"""Validate and transactionally import historical fitness data."""

import argparse
import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.init_db import DEFAULT_DATABASE, connect_database, initialize_database  # noqa: E402
from scripts.validate_history import (  # noqa: E402
    DEFAULT_SOURCE_DIR,
    SOURCE_FILES,
    HistoryValidationError,
    load_sources,
    print_report,
    source_stats,
    validate_sources,
)

ImportFunction = Callable[[Any, list[dict[str, Any]], str | None], int]


def import_history(
    database_path: Path = DEFAULT_DATABASE,
    source_dir: Path = DEFAULT_SOURCE_DIR,
    selected: str | None = None,
    dry_run: bool = False,
    replace: bool = False,
) -> dict[str, int]:
    """Import selected history files atomically and return processed counts."""
    sources = load_sources(Path(source_dir), selected)
    errors, warnings = validate_sources(sources)
    if errors:
        raise HistoryValidationError(errors, warnings)
    stats = source_stats(sources)
    if dry_run:
        return stats

    initialize_database(Path(database_path))
    connection = connect_database(Path(database_path))
    connection.row_factory = __import__("sqlite3").Row
    try:
        connection.execute("BEGIN")
        if replace:
            _clear_history(connection, sources)
        importers: dict[str, ImportFunction] = {
            "daily_logs": _import_daily_logs,
            "body_measurements": _import_measurements,
            "nutrition_entries": _import_nutrition,
            "workouts": _import_workouts,
        }
        for name, records in sources.items():
            source_path = Path(source_dir) / SOURCE_FILES[name]
            source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
            if not replace and _already_imported(connection, name, source_hash):
                stats[name] = 0
                continue
            count = importers[name](connection, records, None)
            stats[name] = count
            connection.execute(
                """
                INSERT INTO import_runs (
                    source_name, source_hash, record_count, status, notes
                ) VALUES (?, ?, ?, 'success', ?)
                ON CONFLICT (source_name, source_hash) DO UPDATE SET
                    imported_at = CURRENT_TIMESTAMP,
                    record_count = excluded.record_count,
                    status = excluded.status,
                    notes = excluded.notes
                """,
                (name, source_hash, count, "Historical JSON import"),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return stats


def _already_imported(connection: Any, source_name: str, source_hash: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM import_runs WHERE source_name = ? AND source_hash = ? "
            "AND status = 'success'",
            (source_name, source_hash),
        ).fetchone()
        is not None
    )


def _clear_history(connection: Any, sources: dict[str, list[dict[str, Any]]]) -> None:
    if "nutrition_entries" in sources:
        connection.execute("DELETE FROM nutrition_entries WHERE source_key LIKE 'history:%'")
    if "workouts" in sources:
        session_ids = connection.execute(
            "SELECT id FROM workout_sessions WHERE source_key LIKE 'history:%'"
        ).fetchall()
        for row in session_ids:
            connection.execute(
                "DELETE FROM exercise_sets WHERE workout_session_id = ?", (row[0],)
            )
        connection.execute("DELETE FROM workout_sessions WHERE source_key LIKE 'history:%'")
    if "body_measurements" in sources:
        connection.execute("DELETE FROM body_measurements WHERE source_key LIKE 'history:%'")
    if "daily_logs" in sources:
        dates = [record.get("date") for record in sources["daily_logs"]]
        connection.executemany("DELETE FROM daily_logs WHERE log_date = ?", [(d,) for d in dates])
    connection.executemany(
        "DELETE FROM import_runs WHERE source_name = ?",
        [(name,) for name in sources],
    )


def _value(record: dict[str, Any], name: str, default: Any = 0) -> Any:
    value = record.get(name)
    return default if value is None else value


def _net_carbs(record: dict[str, Any]) -> float:
    value = record.get("net_carbs_g")
    if value is not None:
        return value
    return max(0, _value(record, "total_carbs_g") - _value(record, "fiber_g"))


def _source_key(kind: str, record: dict[str, Any]) -> str:
    canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"history:{kind}:{digest}"


def _ensure_daily_log(connection: Any, date: str) -> int:
    connection.execute(
        "INSERT INTO daily_logs (log_date) VALUES (?) ON CONFLICT (log_date) DO NOTHING",
        (date,),
    )
    return connection.execute(
        "SELECT id FROM daily_logs WHERE log_date = ?", (date,)
    ).fetchone()[0]


def _import_daily_logs(
    connection: Any, records: list[dict[str, Any]], history_version: str | None = None
) -> int:
    for record in records:
        calories = _value(record, "calories_in")
        tdee = _value(record, "tdee")
        training = int(bool(_value(record, "is_training_day", False)))
        connection.execute(
            """
            INSERT INTO daily_logs (
                log_date, day_number, is_training_day, training_type,
                calories_intake, tdee, calorie_balance, protein_g,
                total_carbs_g, fiber_g, net_carbs_g, fat_g, steps,
                active_energy, notes, history_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (log_date) DO UPDATE SET
                day_number = excluded.day_number,
                is_training_day = excluded.is_training_day,
                training_type = excluded.training_type,
                calories_intake = excluded.calories_intake,
                tdee = excluded.tdee,
                calorie_balance = excluded.calorie_balance,
                protein_g = excluded.protein_g,
                total_carbs_g = excluded.total_carbs_g,
                fiber_g = excluded.fiber_g,
                net_carbs_g = excluded.net_carbs_g,
                fat_g = excluded.fat_g,
                steps = excluded.steps,
                active_energy = excluded.active_energy,
                notes = excluded.notes,
                history_version = excluded.history_version,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                record["date"],
                record.get("day_number"),
                training,
                record.get("workout_type") if training else None,
                calories,
                tdee,
                calories - tdee,
                _value(record, "protein_g"),
                _value(record, "total_carbs_g"),
                _value(record, "fiber_g"),
                _net_carbs(record),
                _value(record, "fat_g"),
                _value(record, "steps"),
                _value(record, "active_energy_kcal"),
                record.get("notes"),
                history_version,
            ),
        )
    return len(records)


def _import_measurements(
    connection: Any, records: list[dict[str, Any]], history_version: str | None = None
) -> int:
    for record in records:
        measured_at = record["measured_at"]
        daily_log_id = _ensure_daily_log(connection, measured_at)
        existing = connection.execute(
            "SELECT id FROM body_measurements WHERE measured_at = ? "
            "OR (measured_at IS NULL AND daily_log_id = ?)",
            (measured_at, daily_log_id),
        ).fetchone()
        values = (
            daily_log_id,
            record.get("weight"),
            record.get("body_fat_percentage"),
            record.get("waist"),
            record.get("notes"),
            _source_key("measurement", record),
            history_version,
        )
        if existing:
            connection.execute(
                """
                UPDATE body_measurements SET
                    daily_log_id = ?, weight_kg = ?, body_fat_percentage = ?,
                    waist_cm = ?, notes = ?, source_key = ?, history_version = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                values + (existing[0],),
            )
        else:
            connection.execute(
                """
                INSERT INTO body_measurements (
                    daily_log_id, weight_kg, body_fat_percentage, waist_cm,
                    notes, source_key, history_version, measured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values + (measured_at,),
            )
    return len(records)


def _food_id(connection: Any, record: dict[str, Any]) -> int:
    brand = record.get("brand") or ""
    name = record["food_name"].strip()
    existing = connection.execute(
        "SELECT id FROM foods WHERE brand = ? COLLATE NOCASE "
        "AND food_name = ? COLLATE NOCASE",
        (brand, name),
    ).fetchone()
    if existing:
        return existing[0]
    unit = record.get("unit") or "serving"
    allowed_units = {"g", "serving", "bottle", "piece", "custom"}
    default_unit = unit if unit in allowed_units else "custom"
    cursor = connection.execute(
        """
        INSERT INTO foods (
            food_name, brand, default_unit, calories, protein_g,
            total_carbs_g, fiber_g, net_carbs_g, fat_g, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            brand,
            default_unit,
            _value(record, "calories"),
            _value(record, "protein_g"),
            _value(record, "total_carbs_g"),
            _value(record, "fiber_g"),
            _net_carbs(record),
            _value(record, "fat_g"),
            f"[history snapshot] {record.get('notes') or ''}".rstrip(),
        ),
    )
    return cursor.lastrowid


def _import_nutrition(
    connection: Any, records: list[dict[str, Any]], history_version: str | None = None
) -> int:
    occurrences: dict[tuple[str, str, str, str], int] = {}
    for record in records:
        _ensure_daily_log(connection, record["date"])
        food_id = _food_id(connection, record)
        identity = (
            record["date"],
            record.get("meal_type") or "unknown",
            record.get("brand") or "",
            record["food_name"].strip(),
        )
        occurrences[identity] = occurrences.get(identity, 0) + 1
        identity_text = json.dumps(
            identity + (occurrences[identity],), ensure_ascii=False, separators=(",", ":")
        )
        key = "history:nutrition:" + hashlib.sha256(
            identity_text.encode("utf-8")
        ).hexdigest()
        values = (
            record["date"],
            record.get("meal_type") or "unknown",
            food_id,
            _value(record, "amount", 1),
            record.get("unit") or "serving",
            _value(record, "calories"),
            _value(record, "protein_g"),
            _value(record, "total_carbs_g"),
            _value(record, "fiber_g"),
            _net_carbs(record),
            _value(record, "fat_g"),
            record.get("servings"),
            record.get("notes"),
            key,
            history_version,
        )
        existing = connection.execute(
            """
            SELECT id FROM nutrition_entries
            WHERE source_key = ?
               OR (
                    source_key IS NULL AND log_date = ? AND meal_type = ?
                    AND food_id = ? AND amount = ? AND unit = ?
               )
            """,
            (key, values[0], values[1], values[2], values[3], values[4]),
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE nutrition_entries SET
                    log_date = ?, meal_type = ?, food_id = ?, amount = ?, unit = ?,
                    calories = ?, protein_g = ?, carbs_g = ?, fiber_g = ?,
                    net_carbs_g = ?, fat_g = ?, servings = ?, notes = ?,
                    source_key = ?, history_version = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                values + (existing[0],),
            )
        else:
            connection.execute(
                """
                INSERT INTO nutrition_entries (
                    log_date, meal_type, food_id, amount, unit, calories,
                    protein_g, carbs_g, fiber_g, net_carbs_g, fat_g,
                    servings, notes, source_key, history_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
    return len(records)


def _import_workouts(
    connection: Any, records: list[dict[str, Any]], history_version: str | None = None
) -> int:
    for workout in records:
        daily_log_id = _ensure_daily_log(connection, workout["date"])
        name = workout.get("workout_name") or "Workout"
        existing = connection.execute(
            "SELECT id FROM workout_sessions WHERE daily_log_id = ? AND name = ?",
            (daily_log_id, name),
        ).fetchone()
        session_values = (
            workout.get("workout_type"),
            workout.get("duration_minutes"),
            workout.get("active_energy_kcal"),
            workout.get("notes"),
            _source_key("workout", workout),
            history_version,
        )
        if existing:
            session_id = existing[0]
            connection.execute(
                """
                UPDATE workout_sessions SET
                    workout_type = ?, duration_minutes = ?, active_energy_kcal = ?,
                    notes = ?, source_key = ?, history_version = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                session_values + (session_id,),
            )
            connection.execute(
                "DELETE FROM exercise_sets WHERE workout_session_id = ?", (session_id,)
            )
        else:
            cursor = connection.execute(
                """
                INSERT INTO workout_sessions (
                    daily_log_id, name, workout_type, duration_minutes,
                    active_energy_kcal, notes, source_key, history_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (daily_log_id, name) + session_values,
            )
            session_id = cursor.lastrowid
        for exercise in workout.get("exercises") or []:
            exercise_name = exercise.get("exercise_name") or "Unknown Exercise"
            connection.execute(
                """
                INSERT INTO exercises (name, category, muscle_group)
                VALUES (?, ?, ?)
                ON CONFLICT (name) DO UPDATE SET
                    category = excluded.category,
                    muscle_group = excluded.muscle_group,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    exercise_name,
                    exercise.get("category") or "other",
                    exercise.get("muscle_group"),
                ),
            )
            exercise_id = connection.execute(
                "SELECT id FROM exercises WHERE name = ? COLLATE NOCASE",
                (exercise_name,),
            ).fetchone()[0]
            for item in exercise.get("sets") or []:
                connection.execute(
                    """
                    INSERT INTO exercise_sets (
                        workout_session_id, exercise_id, set_number, reps, rir,
                        weight_kg, distance_meters, duration_seconds, notes,
                        history_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        exercise_id,
                        item["set_number"],
                        item.get("reps"),
                        item.get("rir"),
                        item.get("weight"),
                        item.get("distance"),
                        item.get("duration_seconds"),
                        item.get("notes"),
                        history_version,
                    ),
                )
    return len(records)


def _print_stats(stats: dict[str, int], dry_run: bool) -> None:
    prefix = "Dry-run 验证通过" if dry_run else "导入完成"
    print(f"{prefix}：")
    print(f"- {stats['daily_logs']} 个 daily logs")
    print(f"- {stats['body_measurements']} 个 body measurements")
    print(f"- {stats['nutrition_entries']} 个 nutrition entries")
    print(f"- {stats['workouts']} 个 workouts")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--file", choices=SOURCE_FILES)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    try:
        stats = import_history(
            database_path=args.database.resolve(),
            source_dir=args.source_dir.resolve(),
            selected=args.file,
            dry_run=args.dry_run,
            replace=args.replace,
        )
    except HistoryValidationError as error:
        sources = load_sources(args.source_dir.resolve(), args.file)
        print_report(sources, error.errors, error.warnings)
        raise SystemExit(1) from error
    _print_stats(stats, args.dry_run)


if __name__ == "__main__":
    main()
