"""Create or update the fitness dashboard SQLite database."""

import argparse
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "fitness.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


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
