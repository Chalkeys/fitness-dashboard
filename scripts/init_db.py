"""Create the fitness dashboard SQLite database from the project schema."""

import argparse
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "fitness.db"
SCHEMA_PATH = PROJECT_ROOT / "database" / "schema.sql"


def initialize_database(database_path: Path = DEFAULT_DATABASE) -> Path:
    """Create missing tables and indexes, then return the database path."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    with sqlite3.connect(database_path) as connection:
        connection.executescript(schema)

    return database_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help=f"database path (default: {DEFAULT_DATABASE})",
    )
    args = parser.parse_args()
    database_path = initialize_database(args.database.resolve())
    print(f"Initialized database at {database_path}")


if __name__ == "__main__":
    main()
