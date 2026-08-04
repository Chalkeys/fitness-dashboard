import json
import shutil
from pathlib import Path

import pytest

from database.init_db import connect_database, initialize_database
from scripts.import_exports import import_exports
from scripts.seed_foods import seed_foods

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _export_dir(tmp_path: Path, review_status: str = "approved") -> Path:
    directory = tmp_path / "exports"
    directory.mkdir()
    source = PROJECT_ROOT / "data_sources"
    payload = {
        "protocol": "fitness-dashboard-export-v1",
        "history_version": "2026-08-03-v1",
        "review_status": review_status,
        "daily_logs": json.loads((source / "daily_logs.json").read_text(encoding="utf-8")),
        "body_measurements": json.loads(
            (source / "body_measurements.json").read_text(encoding="utf-8")
        ),
        "nutrition_entries": json.loads(
            (source / "nutrition_entries.json").read_text(encoding="utf-8")
        ),
        "workouts": json.loads((source / "workouts.json").read_text(encoding="utf-8")),
        "foods": [],
    }
    (directory / "approved.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return directory


def _scalar(database: Path, sql: str):
    connection = connect_database(database)
    try:
        return connection.execute(sql).fetchone()[0]
    finally:
        connection.close()


def test_export_import_and_sha256_skip(tmp_path: Path) -> None:
    exports = _export_dir(tmp_path)
    database = tmp_path / "fitness.db"
    first = import_exports(exports, database)
    second = import_exports(exports, database)
    assert first["files"] == 1
    assert first["new"] > 0
    assert second["skipped"] == 1
    assert _scalar(database, "SELECT COUNT(*) FROM import_log") == 1
    assert _scalar(database, "SELECT COUNT(*) FROM daily_logs") == 2


def test_history_version_replaces_same_day(tmp_path: Path) -> None:
    exports = _export_dir(tmp_path)
    database = tmp_path / "fitness.db"
    import_exports(exports, database)
    payload = json.loads((exports / "approved.json").read_text(encoding="utf-8"))
    payload["history_version"] = "2026-08-03-v2"
    payload["daily_logs"][1]["calories_in"] = 2500
    (exports / "approved-v2.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    import_exports(exports, database, file_filter="approved-v2")
    connection = connect_database(database)
    try:
        row = connection.execute(
            "SELECT calories_intake, history_version FROM daily_logs "
            "WHERE log_date = '2026-08-03'"
        ).fetchone()
    finally:
        connection.close()
    assert tuple(row) == (2500, "2026-08-03-v2")
    assert _scalar(database, "SELECT COUNT(*) FROM daily_logs") == 2


def test_unapproved_export_is_skipped(tmp_path: Path) -> None:
    exports = _export_dir(tmp_path, review_status="draft")
    database = tmp_path / "fitness.db"
    stats = import_exports(exports, database)
    assert stats["skipped"] == 1
    assert _scalar(database, "SELECT COUNT(*) FROM daily_logs") == 0
    assert _scalar(database, "SELECT status FROM import_log") == "skipped"


def test_dry_run_does_not_create_database(tmp_path: Path) -> None:
    exports = _export_dir(tmp_path)
    database = tmp_path / "fitness.db"
    stats = import_exports(exports, database, dry_run=True)
    assert stats["files"] == 1
    assert not database.exists()


def test_replace_preserves_seed_foods(tmp_path: Path) -> None:
    exports = _export_dir(tmp_path)
    database = tmp_path / "fitness.db"
    initialize_database(database)
    seed_count = seed_foods(database)
    import_exports(exports, database)
    import_exports(exports, database, replace=True)
    assert _scalar(database, "SELECT COUNT(*) FROM foods") == seed_count
    assert _scalar(database, "SELECT COUNT(*) FROM daily_logs") == 2


def test_invalid_export_fails_without_database_write(tmp_path: Path) -> None:
    exports = _export_dir(tmp_path)
    database = tmp_path / "fitness.db"
    payload = json.loads((exports / "approved.json").read_text(encoding="utf-8"))
    payload["daily_logs"][0]["date"] = "not-a-date"
    (exports / "invalid.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(ValueError):
        import_exports(exports, database, file_filter="invalid")
    assert not database.exists()


def test_database_failure_is_recorded_in_import_log(tmp_path: Path) -> None:
    exports = _export_dir(tmp_path)
    database = tmp_path / "fitness.db"
    payload = json.loads((exports / "approved.json").read_text(encoding="utf-8"))
    payload["nutrition_entries"][0]["unit"] = "invalid-unit"
    (exports / "database-error.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(Exception):
        import_exports(exports, database, file_filter="database-error")
    assert _scalar(database, "SELECT failed_count FROM import_log") == 1


def test_file_and_since_filters(tmp_path: Path) -> None:
    exports = _export_dir(tmp_path)
    database = tmp_path / "fitness.db"
    assert import_exports(exports, database, since="2026-08-04")["files"] == 0
    assert import_exports(exports, database, file_filter="missing")["files"] == 0
