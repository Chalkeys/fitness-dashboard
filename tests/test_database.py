import sqlite3
import tempfile
import unittest
from pathlib import Path

from database.init_db import connect_database, initialize_database

REQUIRED_TABLES = {
    "daily_logs",
    "body_measurements",
    "workout_sessions",
    "exercises",
    "exercise_sets",
    "foods",
    "nutrition_entries",
    "nutrition_daily_totals",
}


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "fitness.db"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_initialization_succeeds_and_can_be_rerun(self) -> None:
        initialize_database(self.database_path)
        initialize_database(self.database_path)
        self.assertTrue(self.database_path.is_file())

    def test_required_tables_exist(self) -> None:
        tables = set(initialize_database(self.database_path))
        self.assertEqual(REQUIRED_TABLES, tables)

    def test_foreign_keys_are_enabled(self) -> None:
        initialize_database(self.database_path)
        connection = connect_database(self.database_path)
        try:
            enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(1, enabled)

    def test_duplicate_daily_dates_are_rejected(self) -> None:
        initialize_database(self.database_path)
        connection = connect_database(self.database_path)
        try:
            connection.execute(
                "INSERT INTO daily_logs (log_date) VALUES (?)", ("2026-08-03",)
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO daily_logs (log_date) VALUES (?)",
                    ("2026-08-03",),
                )
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
