"""Validate one-file-per-day Export Protocol v1 documents."""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SCHEMA_PATH = PROJECT_ROOT / "schemas" / "daily_export_v1.schema.json"
DEFAULT_EXPORT_DIR = PROJECT_ROOT / "exports"


def export_paths(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(target.glob("*.json"))


def review_status(document: dict[str, Any]) -> str:
    statuses = [item.get("review_status") for item in document.get("review", [])]
    if statuses and all(status == "approved" for status in statuses):
        return "approved"
    if "rejected" in statuses:
        return "rejected"
    return "needs_review"


def validate_document(path: Path, schema: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return {"file": str(path), "errors": [str(error)], "warnings": []}

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for error in sorted(validator.iter_errors(document), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path) or "$"
        errors.append(f"{location}: {error.message}")
    if errors or not isinstance(document, dict):
        return {"file": str(path), "errors": errors, "warnings": warnings}

    _validate_filename(path, document, errors)
    _validate_unique_entries(document, errors)
    _validate_workout_sets(document, errors)
    _validate_nutrition_warnings(document, warnings)
    _validate_daily_warnings(document, warnings)
    return {
        "file": str(path),
        "export_id": document.get("export_id"),
        "history_version": document.get("history_version"),
        "review_status": review_status(document),
        "document": document,
        "errors": errors,
        "warnings": warnings,
    }


def _validate_filename(path: Path, document: dict[str, Any], errors: list[str]) -> None:
    stem = path.stem
    if stem.startswith("day-"):
        try:
            expected = int(stem[4:])
        except ValueError:
            errors.append("文件名 day-NNN 中的 NNN 必须是整数")
            return
        if document.get("day_number") != expected:
            errors.append("文件名 day_number 与 JSON day_number 不一致")
    else:
        try:
            expected_date = date.fromisoformat(stem).isoformat()
        except ValueError:
            return
        if document.get("date") != expected_date:
            errors.append("文件名日期与 JSON date 不一致")


def _validate_unique_entries(document: dict[str, Any], errors: list[str]) -> None:
    entry_ids: set[str] = set()
    for entry in document.get("nutrition", []):
        entry_id = entry.get("entry_id")
        if entry_id in entry_ids:
            errors.append(f"nutrition entry_id 重复：{entry_id}")
        entry_ids.add(entry_id)
    export_ids = [document.get("export_id")]
    if len(export_ids) != len(set(export_ids)):
        errors.append("export_id 重复")


def _validate_workout_sets(document: dict[str, Any], errors: list[str]) -> None:
    workout = document.get("workout")
    if not workout:
        return
    session_id = workout.get("session_id")
    if not session_id:
        errors.append("workout 缺少 session_id")
    for exercise in workout.get("exercises", []):
        seen: set[int] = set()
        for item in exercise.get("sets", []):
            number = item.get("set_number")
            if number in seen:
                errors.append(f"动作 {exercise.get('exercise_name')} 的 set_number 重复：{number}")
            seen.add(number)


def _validate_nutrition_warnings(document: dict[str, Any], warnings: list[str]) -> None:
    totals = {"calories": 0.0, "protein_g": 0.0, "total_carbs_g": 0.0, "fiber_g": 0.0, "net_carbs_g": 0.0, "fat_g": 0.0}
    for entry in document.get("nutrition", []):
        total_carbs = entry.get("total_carbs_g")
        net_carbs = entry.get("net_carbs_g")
        if total_carbs is not None and net_carbs is not None and net_carbs > total_carbs + 0.1:
            warnings.append(f"entry {entry.get('entry_id')} net_carbs 大于 total_carbs")
        for field in totals:
            totals[field] += entry.get(field) or 0
    daily = document.get("daily_log") or {}
    for field, actual in totals.items():
        expected = daily.get(field if field != "calories" else "calories_in")
        if expected is not None and expected > 0 and abs(actual - expected) / expected > 0.20:
            warnings.append(f"nutrition 合计 {field} 与 daily_log 差异超过 20%")


def _validate_daily_warnings(document: dict[str, Any], warnings: list[str]) -> None:
    daily = document.get("daily_log") or {}
    calories = daily.get("calories_in")
    tdee = daily.get("tdee")
    balance = daily.get("calorie_balance")
    if calories is not None and tdee is not None and balance is not None:
        if abs(balance - (calories - tdee)) > 0.1:
            warnings.append("daily_log calorie_balance 不等于 calories_in - tdee")


def validate_exports(target: Path = DEFAULT_EXPORT_DIR) -> dict[str, Any]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    reports = [validate_document(path, schema) for path in export_paths(target)]
    seen_export_ids: dict[tuple[str, int], Path] = {}
    for report in reports:
        export_id = report.get("export_id")
        key = (export_id, report.get("history_version")) if export_id else None
        if key and key in seen_export_ids:
            report["errors"].append(
                f"export_id + history_version 与 {seen_export_ids[key].name} 重复：{export_id} / {report.get('history_version')}"
            )
        elif key:
            seen_export_ids[key] = Path(report["file"])
    return {"files": reports, "valid": not any(report["errors"] for report in reports)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", type=Path, default=DEFAULT_EXPORT_DIR)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = validate_exports(args.target.resolve())
    if args.as_json:
        serializable = {"valid": result["valid"], "files": []}
        for report in result["files"]:
            copy = {key: value for key, value in report.items() if key != "document"}
            serializable["files"].append(copy)
        print(json.dumps(serializable, ensure_ascii=False, indent=2))
    else:
        for report in result["files"]:
            label = "通过" if not report["errors"] else "失败"
            print(f"{label}：{Path(report['file']).name}")
            for warning in report["warnings"]:
                print(f"警告：{warning}")
            for error in report["errors"]:
                print(f"错误：{error}")
    has_warnings = any(report["warnings"] for report in result["files"])
    raise SystemExit(1 if not result["valid"] or (args.strict and has_warnings) else 0)


if __name__ == "__main__":
    main()
