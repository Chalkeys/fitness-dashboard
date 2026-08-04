"""Insert or update the personal food library from JSON."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.init_db import DEFAULT_DATABASE, connect_database  # noqa: E402

DEFAULT_SEED_PATH = PROJECT_ROOT / "database" / "seed_foods.json"
FOOD_COLUMNS = (
    "food_name",
    "brand",
    "default_unit",
    "calories",
    "protein_g",
    "total_carbs_g",
    "fiber_g",
    "net_carbs_g",
    "fat_g",
    "notes",
)


def seed_foods(
    database_path: Path = DEFAULT_DATABASE,
    seed_path: Path = DEFAULT_SEED_PATH,
) -> int:
    """Upsert the food library and return the number of processed foods."""
    foods = json.loads(Path(seed_path).read_text(encoding="utf-8"))
    connection = connect_database(Path(database_path))
    try:
        connection.executemany(
            """
            INSERT INTO foods (
                food_name, brand, default_unit, calories, protein_g,
                total_carbs_g, fiber_g, net_carbs_g, fat_g, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (brand, food_name) DO UPDATE SET
                default_unit = excluded.default_unit,
                calories = excluded.calories,
                protein_g = excluded.protein_g,
                total_carbs_g = excluded.total_carbs_g,
                fiber_g = excluded.fiber_g,
                net_carbs_g = excluded.net_carbs_g,
                fat_g = excluded.fat_g,
                notes = excluded.notes,
                updated_at = CURRENT_TIMESTAMP
            """,
            [tuple(food[column] for column in FOOD_COLUMNS) for food in foods],
        )
        connection.commit()
    finally:
        connection.close()
    return len(foods)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--seed-file", type=Path, default=DEFAULT_SEED_PATH)
    args = parser.parse_args()
    count = seed_foods(args.database.resolve(), args.seed_file.resolve())
    print(f"Seeded {count} foods into {args.database.resolve()}")


if __name__ == "__main__":
    main()
