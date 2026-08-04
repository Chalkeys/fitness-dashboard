"""Create or update the fitness dashboard SQLite database."""

import argparse
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "fitness.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")

MIGRATION_COLUMNS = {
    "daily_logs": {
        "day_number": "INTEGER CHECK (day_number IS NULL OR day_number > 0)",
    },
    "body_measurements": {
        "measured_at": "TEXT",
        "source_key": "TEXT",
    },
    "workout_sessions": {
        "workout_type": "TEXT",
        "active_energy_kcal": "REAL",
        "source_key": "TEXT",
    },
    "exercise_sets": {"rir": "REAL"},
    "nutrition_entries": {
        "net_carbs_g": "REAL NOT NULL DEFAULT 0",
        "servings": "REAL",
        "notes": "TEXT",
        "source_key": "TEXT",
    },
}

MIGRATION_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_logs_day_number "
    "ON daily_logs (day_number) WHERE day_number IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_body_measurements_measured_at "
    "ON body_measurements (measured_at) WHERE measured_at IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_body_measurements_source_key "
    "ON body_measurements (source_key) WHERE source_key IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_workout_sessions_source_key "
    "ON workout_sessions (source_key) WHERE source_key IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_nutrition_entries_source_key "
    "ON nutrition_entries (source_key) WHERE source_key IS NOT NULL",
)


def connect_database(database_path: Path) -> sqlite3.Connection:
    """Open a database connection with foreign-key enforcement enabled."""
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(database_path: Path = DEFAULT_DATABASE) -> list[str]:
    """Create missing schema objects without removing existing data."""
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    connection = connect_database(database_path)
    try:
        connection.executescript(schema)
        _apply_compatible_migrations(connection)
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        ]
    finally:
        connection.close()

    return tables


def _apply_compatible_migrations(connection: sqlite3.Connection) -> None:
    """Add Milestone 3 columns to databases created by older schemas."""
    for table, columns in MIGRATION_COLUMNS.items():
        existing = {
            row[1] for row in connection.execute(f"PRAGMA table_info({table})")
        }
        for column, definition in columns.items():
            if column not in existing:
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                )
    for statement in MIGRATION_INDEXES:
        connection.execute(statement)
    connection.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help=f"database path (default: {DEFAULT_DATABASE})",
    )
    args = parser.parse_args()
    database_path = args.database.resolve()
    tables = initialize_database(database_path)
    print(f"Initialized database at {database_path}")
    print("Created tables:")
    for table in tables:
        print(f"- {table}")


if __name__ == "__main__":
    main()
