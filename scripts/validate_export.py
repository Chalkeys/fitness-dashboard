"""Validate Export Protocol v1 JSON files."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_history import validate_sources

REQUIRED_RECORD_FIELDS = {
    "daily_logs": (
        "date", "day_number", "is_training_day", "workout_type", "calories_in",
        "tdee", "calorie_balance", "protein_g", "total_carbs_g", "fiber_g",
        "net_carbs_g", "fat_g", "steps", "active_energy_kcal", "notes",
    ),
    "body_measurements": (
        "measured_at", "weight", "waist", "body_fat_percentage", "notes"
    ),
    "nutrition_entries": (
        "date", "meal_type", "food_name", "brand", "amount", "unit", "servings",
        "calories", "protein_g", "total_carbs_g", "fiber_g", "net_carbs_g",
        "fat_g", "notes",
    ),
    "workouts": (
        "date", "workout_name", "workout_type", "duration_minutes",
        "active_energy_kcal", "notes", "exercises",
    ),
}
DATASET_NAMES = tuple(REQUIRED_RECORD_FIELDS)


def normalize_export(payload: dict[str, Any], filename: str = "export.json") -> dict[str, Any]:
    """Validate envelope metadata and return normalized datasets."""
    if not isinstance(payload, dict):
        raise ValueError(f"{filename} 顶层必须是 JSON object")
    protocol = payload.get("protocol") or payload.get("export_protocol")
    if protocol not in ("fitness-dashboard-export-v1", "Export Protocol v1"):
        raise ValueError(f"{filename} 不是 Export Protocol v1")
    history_version = payload.get("history_version")
    if not isinstance(history_version, str) or not history_version.strip():
        raise ValueError(f"{filename} 缺少 history_version")
    review_status = payload.get("review_status", "pending")
    datasets = {name: payload.get(name, []) for name in DATASET_NAMES}
    errors: list[str] = []
    for name, records in datasets.items():
        if not isinstance(records, list):
            errors.append(f"{filename} 的 {name} 必须是数组")
            continue
        for index, record in enumerate(records, 1):
            if not isinstance(record, dict):
                errors.append(f"{filename} 的 {name} 第 {index} 条必须是 object")
                continue
            missing = [field for field in REQUIRED_RECORD_FIELDS[name] if field not in record]
            if missing:
                errors.append(
                    f"{filename} 的 {name} 第 {index} 条缺少字段：{', '.join(missing)}"
                )
    foods = payload.get("foods", [])
    if not isinstance(foods, list):
        errors.append(f"{filename} 的 foods 必须是数组")
        foods = []
    food_keys: set[tuple[str, str]] = set()
    for index, food in enumerate(foods, 1):
        if not isinstance(food, dict) or not food.get("food_name"):
            errors.append(f"{filename} 的 foods 第 {index} 条缺少 food_name")
            continue
        key = ((food.get("brand") or "").casefold(), food["food_name"].casefold())
        if key in food_keys:
            errors.append(f"{filename} 的 foods 重复：{food.get('brand', '')} / {food['food_name']}")
        food_keys.add(key)
    if errors:
        raise ValueError("；".join(errors))
    return {
        "filename": filename,
        "history_version": history_version.strip(),
        "review_status": review_status,
        "datasets": datasets,
        "foods": foods,
        "exported_at": payload.get("exported_at"),
    }


def validate_export(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    """Read one export and return document, errors, and warnings."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        document = normalize_export(payload, path.name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return {}, [str(error)], []
    if document["review_status"] != "approved":
        return document, [], []
    errors, warnings = validate_sources(document["datasets"])
    return document, errors, warnings


def print_export_report(path: Path, document: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    if errors:
        print(f"验证失败：{path.name}")
        for error in errors:
            print(f"- {error}")
        return
    status = document.get("review_status")
    if status != "approved":
        print(f"跳过：{path.name}（review_status={status!r}，需要 approved）")
    else:
        print(f"验证通过：{path.name}（history_version={document['history_version']}）")
    for warning in warnings:
        print(f"警告：{warning}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    failed = False
    for path in args.files:
        document, errors, warnings = validate_export(path)
        print_export_report(path, document, errors, warnings)
        failed = failed or bool(errors)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
