"""Initialize the database and optionally seed the personal food library."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.init_db import DEFAULT_DATABASE, initialize_database  # noqa: E402
from scripts.seed_foods import seed_foods  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument(
        "--seed",
        action="store_true",
        help="import database/seed_foods.json after creating the schema",
    )
    args = parser.parse_args()
    database_path = args.database.resolve()
    tables = initialize_database(database_path)
    print(f"Initialized database at {database_path}")
    print("Created tables:")
    for table in tables:
        print(f"- {table}")
    if args.seed:
        count = seed_foods(database_path)
        print(f"Seeded {count} foods")


if __name__ == "__main__":
    main()
