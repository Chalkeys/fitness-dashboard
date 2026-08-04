"""Convert legacy data_sources JSON into one daily Export Protocol v1 file per date."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_history import DEFAULT_SOURCE_DIR  # noqa: E402

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "exports" / "converted"


def convert_legacy(
    source_dir: Path = DEFAULT_SOURCE_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    dry_run: bool = False,
) -> dict[str, int]:
    sources = {
        name: json.loads((Path(source_dir) / f"{name}.json").read_text(encoding="utf-8"))
        for name in ("daily_logs", "body_measurements", "nutrition_entries", "workouts")
    }
    dates: set[str] = set()
    missing_dates = 0
    for record in sources["daily_logs"]:
        if record.get("date"):
            dates.add(record["date"])
        else:
            missing_dates += 1
    for record in sources["body_measurements"]:
        if record.get("measured_at"):
            dates.add(record["measured_at"])
        else:
            missing_dates += 1
    for record in sources["nutrition_entries"] + sources["workouts"]:
        if record.get("date"):
            dates.add(record["date"])
        else:
            missing_dates += 1
    if not dry_run:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
    created = 0
    for date_value in sorted(dates):
        payload = _build_export(date_value, sources)
        if not dry_run:
            (Path(output_dir) / f"{date_value}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        created += 1
    return {"created": created, "missing_dates": missing_dates}


def _build_export(date_value: str, sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    daily = next((item for item in sources["daily_logs"] if item.get("date") == date_value), None)
    body = next((item for item in sources["body_measurements"] if item.get("measured_at") == date_value), None)
    nutrition = [item for item in sources["nutrition_entries"] if item.get("date") == date_value]
    workouts = [item for item in sources["workouts"] if item.get("date") == date_value]
    daily_log = None
    if daily:
        daily_log = {key: daily.get(key) for key in (
            "is_training_day", "workout_type", "calories_in", "tdee", "calorie_balance",
            "protein_g", "total_carbs_g", "fiber_g", "net_carbs_g", "fat_g", "steps",
            "active_energy_kcal", "notes"
        )}
    body_payload = None if not body else {
        "weight_kg": body.get("weight"),
        "waist_cm": body.get("waist"),
        "body_fat_percentage": body.get("body_fat_percentage"),
        "notes": body.get("notes"),
    }
    entries = []
    for index, item in enumerate(nutrition, 1):
        entries.append({
            "entry_id": f"legacy-{date_value}-{index}",
            "meal_type": item.get("meal_type"),
            "food_name": item.get("food_name"),
            "brand": item.get("brand"),
            "amount": item.get("amount"),
            "unit": item.get("unit"),
            "servings": item.get("servings"),
            "calories": item.get("calories"),
            "protein_g": item.get("protein_g"),
            "total_carbs_g": item.get("total_carbs_g"),
            "fiber_g": item.get("fiber_g"),
            "net_carbs_g": item.get("net_carbs_g"),
            "fat_g": item.get("fat_g"),
            "notes": item.get("notes"),
        })
    workout_payload = None
    if workouts:
        old = workouts[0]
        workout_payload = {
            "session_id": f"legacy-{date_value}-session-1",
            "workout_name": old.get("workout_name"),
            "workout_type": old.get("workout_type"),
            "duration_minutes": old.get("duration_minutes"),
            "active_energy_kcal": old.get("active_energy_kcal"),
            "notes": old.get("notes"),
            "exercises": old.get("exercises", []),
        }
    day_number = daily.get("day_number") if daily else None
    return {
        "protocol_version": "1.0",
        "export_id": f"legacy-{date_value}",
        "history_version": 1,
        "exported_at": "1970-01-01T00:00:00Z",
        "date": date_value,
        "day_number": day_number,
        "provenance": {"source": "legacy data_sources", "confidence": "low", "notes": "Converted; review before import."},
        "body": body_payload,
        "daily_log": daily_log,
        "nutrition": entries,
        "workout": workout_payload,
        "review": [{"review_status": "needs_review", "note": "Legacy conversion requires review."}],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = convert_legacy(args.source_dir.resolve(), args.output_dir.resolve(), args.dry_run)
    action = "将生成" if args.dry_run else "已生成"
    print(f"{action} {result['created']} 个每日导出文件")
    print(f"未能确定日期的记录：{result['missing_dates']}（未猜测、未输出）")


if __name__ == "__main__":
    main()
