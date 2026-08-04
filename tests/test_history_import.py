import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from database.init_db import connect_database, initialize_database
from scripts.import_history import import_history
from scripts.seed_foods import seed_foods
from scripts.validate_history import HistoryValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    destination = tmp_path / "data_sources"
    shutil.copytree(PROJECT_ROOT / "data_sources", destination)
    return destination


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "fitness.db"


def _read_json(source_dir: Path, name: str) -> list[dict]:
    return json.loads((source_dir / f"{name}.json").read_text(encoding="utf-8"))


def _write_json(source_dir: Path, name: str, records: list[dict]) -> None:
    (source_dir / f"{name}.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _scalar(database_path: Path, sql: str, parameters: tuple = ()):
    connection = connect_database(database_path)
    try:
        return connection.execute(sql, parameters).fetchone()[0]
    finally:
        connection.close()


def test_dry_run_does_not_write_database(database_path: Path, source_dir: Path) -> None:
    stats = import_history(database_path, source_dir, dry_run=True)
    assert stats["daily_logs"] == 2
    assert not database_path.exists()


def test_normal_import_and_automatic_calculations(
    database_path: Path, source_dir: Path
) -> None:
    stats = import_history(database_path, source_dir)
    assert stats == {
        "daily_logs": 2,
        "body_measurements": 2,
        "nutrition_entries": 5,
        "workouts": 1,
    }
    connection = connect_database(database_path)
    try:
        daily = connection.execute(
            "SELECT calorie_balance, net_carbs_g FROM daily_logs "
            "WHERE log_date = '2026-08-02'"
        ).fetchone()
        entry_net_carbs = connection.execute(
            "SELECT net_carbs_g FROM nutrition_entries "
            "WHERE log_date = '2026-08-02' AND meal_type = 'lunch'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert daily == (-250, 170)
    assert entry_net_carbs == 0


def test_repeated_import_and_same_hash_do_not_duplicate(
    database_path: Path, source_dir: Path
) -> None:
    import_history(database_path, source_dir)
    second_stats = import_history(database_path, source_dir)
    assert second_stats == {
        "daily_logs": 0,
        "body_measurements": 0,
        "nutrition_entries": 0,
        "workouts": 0,
    }
    assert _scalar(database_path, "SELECT COUNT(*) FROM nutrition_entries") == 5
    assert _scalar(database_path, "SELECT COUNT(*) FROM import_runs") == 4


def test_replace_reimports_without_duplicates(
    database_path: Path, source_dir: Path
) -> None:
    import_history(database_path, source_dir)
    connection = connect_database(database_path)
    try:
        connection.execute(
            "UPDATE daily_logs SET notes = 'changed' WHERE log_date = '2026-08-02'"
        )
        connection.commit()
    finally:
        connection.close()
    stats = import_history(database_path, source_dir, replace=True)
    assert stats["daily_logs"] == 2
    assert _scalar(database_path, "SELECT COUNT(*) FROM daily_logs") == 2
    assert _scalar(database_path, "SELECT COUNT(*) FROM nutrition_entries") == 5
    assert (
        _scalar(
            database_path,
            "SELECT notes FROM daily_logs WHERE log_date = '2026-08-02'",
        )
        == "Milestone 3 sample rest day."
    )


def test_invalid_date_rolls_back_entire_import(
    database_path: Path, source_dir: Path
) -> None:
    initialize_database(database_path)
    seeded_count = seed_foods(database_path)
    records = _read_json(source_dir, "daily_logs")
    records[1]["date"] = "08/03/2026"
    _write_json(source_dir, "daily_logs", records)
    with pytest.raises(HistoryValidationError):
        import_history(database_path, source_dir)
    assert _scalar(database_path, "SELECT COUNT(*) FROM daily_logs") == 0
    assert _scalar(database_path, "SELECT COUNT(*) FROM foods") == seeded_count
    assert _scalar(database_path, "SELECT COUNT(*) FROM import_runs") == 0


def test_nutrition_links_seed_food_and_unknown_food_is_ad_hoc(
    database_path: Path, source_dir: Path
) -> None:
    initialize_database(database_path)
    seed_foods(database_path)
    seed_hash = hashlib.sha256(
        (PROJECT_ROOT / "database" / "seed_foods.json").read_bytes()
    ).hexdigest()
    records = _read_json(source_dir, "nutrition_entries")
    records.append(
        {
            "date": "2026-08-03",
            "meal_type": "dinner",
            "food_name": "Homemade Soup",
            "brand": "",
            "amount": 1,
            "unit": "serving",
            "servings": None,
            "calories": 250,
            "protein_g": 20,
            "total_carbs_g": 25,
            "fiber_g": 5,
            "net_carbs_g": None,
            "fat_g": 8,
            "notes": None,
        }
    )
    _write_json(source_dir, "nutrition_entries", records)
    import_history(database_path, source_dir)
    connection = connect_database(database_path)
    try:
        linked = connection.execute(
            """
            SELECT f.brand FROM nutrition_entries n
            JOIN foods f ON f.id = n.food_id
            WHERE f.food_name = 'Tyson Chicken Breast'
            """
        ).fetchone()[0]
        ad_hoc_note = connection.execute(
            "SELECT notes FROM foods WHERE food_name = 'Homemade Soup'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert linked == "Tyson"
    assert ad_hoc_note.startswith("[history snapshot]")
    assert hashlib.sha256(
        (PROJECT_ROOT / "database" / "seed_foods.json").read_bytes()
    ).hexdigest() == seed_hash


def test_workouts_exercises_and_sets_are_linked(
    database_path: Path, source_dir: Path
) -> None:
    import_history(database_path, source_dir)
    assert _scalar(database_path, "SELECT COUNT(*) FROM workout_sessions") == 1
    assert _scalar(database_path, "SELECT COUNT(*) FROM exercises") == 2
    assert _scalar(database_path, "SELECT COUNT(*) FROM exercise_sets") == 3
    assert _scalar(database_path, "SELECT rir FROM exercise_sets WHERE set_number = 2") == 1


def test_null_fields_import_successfully(database_path: Path, source_dir: Path) -> None:
    daily = _read_json(source_dir, "daily_logs")
    for field in (
        "workout_type",
        "calories_in",
        "tdee",
        "calorie_balance",
        "protein_g",
        "total_carbs_g",
        "fiber_g",
        "net_carbs_g",
        "fat_g",
        "steps",
        "active_energy_kcal",
        "notes",
    ):
        daily[0][field] = None
    _write_json(source_dir, "daily_logs", daily)
    nutrition = _read_json(source_dir, "nutrition_entries")
    nutrition[0]["servings"] = None
    nutrition[0]["notes"] = None
    _write_json(source_dir, "nutrition_entries", nutrition)
    import_history(database_path, source_dir)
    assert _scalar(database_path, "SELECT COUNT(*) FROM daily_logs") == 2


def test_corrected_source_updates_stable_nutrition_entry(
    database_path: Path, source_dir: Path
) -> None:
    import_history(database_path, source_dir)
    records = _read_json(source_dir, "nutrition_entries")
    records[0]["calories"] = 215
    _write_json(source_dir, "nutrition_entries", records)
    import_history(database_path, source_dir, selected="nutrition_entries")
    assert _scalar(database_path, "SELECT COUNT(*) FROM nutrition_entries") == 5
    assert (
        _scalar(
            database_path,
            "SELECT calories FROM nutrition_entries "
            "WHERE log_date = '2026-08-02' AND meal_type = 'breakfast'",
        )
        == 215
    )
