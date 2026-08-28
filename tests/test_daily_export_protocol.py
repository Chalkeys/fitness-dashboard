import json
import shutil
from pathlib import Path

from scripts.convert_legacy_history import convert_legacy
from scripts.import_exports import import_exports
from scripts.validate_exports import validate_document, validate_exports

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (PROJECT_ROOT / "schemas" / "daily_export_v1.schema.json").read_text(encoding="utf-8")
)


def _copy_examples(tmp_path: Path) -> Path:
    destination = tmp_path / "exports"
    destination.mkdir()
    for name in ("day-001.json", "2026-07-21.json"):
        shutil.copy(PROJECT_ROOT / "exports" / "examples" / name, destination / name)
    return destination


def _scalar(database: Path, sql: str):
    import sqlite3

    connection = sqlite3.connect(database)
    try:
        return connection.execute(sql).fetchone()[0]
    finally:
        connection.close()


def test_json_schema_and_examples_are_valid() -> None:
    result = validate_exports(PROJECT_ROOT / "exports" / "examples")
    assert result["valid"] is True
    assert len(result["files"]) == 2
    assert all(not report["errors"] for report in result["files"])


def test_date_null_is_staged_and_approved_day_imported(tmp_path: Path) -> None:
    exports = _copy_examples(tmp_path)
    database = tmp_path / "fitness.db"
    stats = import_exports(exports, database, include_needs_review=True)
    assert stats["files"] == 2
    assert _scalar(database, "SELECT COUNT(*) FROM staged_daily_exports") == 1
    assert _scalar(database, "SELECT COUNT(*) FROM daily_logs") == 1


def test_needs_review_is_skipped_by_default(tmp_path: Path) -> None:
    exports = _copy_examples(tmp_path)
    database = tmp_path / "fitness.db"
    stats = import_exports(exports, database)
    assert stats["skipped"] == 1
    assert _scalar(database, "SELECT COUNT(*) FROM staged_daily_exports") == 0
    assert _scalar(database, "SELECT COUNT(*) FROM daily_logs") == 1


def test_same_hash_and_entry_session_ids_are_idempotent(tmp_path: Path) -> None:
    exports = _copy_examples(tmp_path)
    shutil.copy(exports / "2026-07-21.json", exports / "duplicate-copy.json")
    database = tmp_path / "fitness.db"
    first = import_exports(exports, database)
    second = import_exports(exports, database)
    assert first["files"] == 1
    assert first["skipped"] == 2
    assert second["skipped"] == 3
    assert _scalar(database, "SELECT COUNT(*) FROM nutrition_entries") == 1
    assert _scalar(database, "SELECT COUNT(*) FROM export_runs WHERE status = 'imported'") == 1


def test_new_history_version_replaces_old_version(tmp_path: Path) -> None:
    exports = _copy_examples(tmp_path)
    dated = exports / "2026-07-21.json"
    database = tmp_path / "fitness.db"
    import_exports(exports, database)
    payload = json.loads(dated.read_text(encoding="utf-8"))
    payload["history_version"] = 2
    payload["daily_log"]["calories_in"] = 2200
    dated.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    import_exports(exports, database, file_filter="2026-07-21")
    assert _scalar(database, "SELECT COUNT(*) FROM daily_logs") == 1
    assert _scalar(database, "SELECT calories_intake FROM daily_logs") == 2200
    assert _scalar(database, "SELECT COUNT(*) FROM nutrition_entries") == 1


def test_bad_file_does_not_block_good_file(tmp_path: Path) -> None:
    exports = _copy_examples(tmp_path)
    bad = json.loads((exports / "2026-07-21.json").read_text(encoding="utf-8"))
    bad["protocol_version"] = "0.9"
    (exports / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
    database = tmp_path / "fitness.db"
    stats = import_exports(exports, database)
    assert stats["files"] == 1
    assert stats["failed"] == 1
    assert _scalar(database, "SELECT COUNT(*) FROM daily_logs") == 1


def test_replace_rebuilds_export_without_deleting_seed_library(tmp_path: Path) -> None:
    from database.init_db import initialize_database
    from scripts.seed_foods import seed_foods

    exports = _copy_examples(tmp_path)
    database = tmp_path / "fitness.db"
    initialize_database(database)
    seed_count = seed_foods(database)
    import_exports(exports, database)
    import_exports(exports, database, replace=True)
    assert _scalar(database, "SELECT COUNT(*) FROM foods") == seed_count
    assert _scalar(database, "SELECT COUNT(*) FROM daily_logs") == 1


def test_calorie_and_nutrition_differences_are_warnings(tmp_path: Path) -> None:
    exports = _copy_examples(tmp_path)
    path = exports / "2026-07-21.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["daily_log"]["calorie_balance"] = 0
    payload["daily_log"]["calories_in"] = 5000
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = validate_document(path, SCHEMA)
    assert not report["errors"]
    assert any("calorie_balance" in warning for warning in report["warnings"])
    assert any("nutrition 合计" in warning for warning in report["warnings"])


def test_legacy_conversion_does_not_guess_missing_dates(tmp_path: Path) -> None:
    source = tmp_path / "data_sources"
    shutil.copytree(PROJECT_ROOT / "data_sources", source)
    daily_path = source / "daily_logs.json"
    records = json.loads(daily_path.read_text(encoding="utf-8"))
    records[0]["date"] = None
    daily_path.write_text(json.dumps(records), encoding="utf-8")
    output = tmp_path / "converted"
    result = convert_legacy(source, output, dry_run=True)
    assert result["missing_dates"] == 1
    assert result["created"] >= 1
    assert not output.exists()


def test_schema_accepts_the_active_energy_provenance_fields(tmp_path: Path):
    # The schema closes both objects to unknown keys, so a new field on either
    # fails the import with no message beyond a count. Keep these two pinned.
    source = PROJECT_ROOT / "exports" / "examples" / "2026-07-21.json"
    document = json.loads(source.read_text(encoding="utf-8"))
    document["daily_log"]["active_energy_source"] = "estimated"
    document["workout"] = {
        "session_id": "example-xunji",
        "workout_name": "P1-腿",
        "workout_type": "p1_腿",
        "duration_minutes": 90.0,
        "active_energy_kcal": 260.0,
        "apple_health_workout_kcal": 572.0,
        "notes": None,
        "exercises": [],
    }
    path = tmp_path / "2026-07-21.json"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    assert validate_document(path, SCHEMA)["errors"] == []


def test_a_rejected_file_says_why_on_stderr(tmp_path: Path, capsys):
    # The summary line only counts failures. Without this the reason lives in
    # export_runs and a whole deploy reads as a bare "失败 1".
    exports = tmp_path / "exports"
    exports.mkdir()
    source = PROJECT_ROOT / "exports" / "examples" / "2026-07-21.json"
    document = json.loads(source.read_text(encoding="utf-8"))
    document["daily_log"]["unexpected_field"] = 1
    (exports / "2026-07-21.json").write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    stats = import_exports(exports, tmp_path / "test.db")

    assert stats["failed"] == 1
    stderr = capsys.readouterr().err
    assert "unexpected_field" in stderr
    assert "2026-07-21.json" in stderr
