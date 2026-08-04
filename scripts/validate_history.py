"""Validate human-editable historical fitness JSON files."""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = PROJECT_ROOT / "data_sources"
SOURCE_FILES = {
    "daily_logs": "daily_logs.json",
    "body_measurements": "body_measurements.json",
    "nutrition_entries": "nutrition_entries.json",
    "workouts": "workouts.json",
}
MACRO_FIELDS = ("protein_g", "total_carbs_g", "fiber_g", "net_carbs_g", "fat_g")


class HistoryValidationError(ValueError):
    """Raised when one or more source records are invalid."""

    def __init__(self, errors: list[str], warnings: list[str] | None = None):
        super().__init__("; ".join(errors))
        self.errors = errors
        self.warnings = warnings or []


def load_sources(
    source_dir: Path = DEFAULT_SOURCE_DIR,
    selected: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Load all source files, or one source selected by its stem."""
    if selected and selected not in SOURCE_FILES:
        raise ValueError(f"未知数据文件：{selected}")
    names = [selected] if selected else list(SOURCE_FILES)
    loaded: dict[str, list[dict[str, Any]]] = {}
    for name in names:
        path = Path(source_dir) / SOURCE_FILES[name]
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"{path.name} 的顶层必须是 JSON 数组")
        loaded[name] = data
    return loaded


def validate_sources(
    sources: dict[str, list[dict[str, Any]]],
) -> tuple[list[str], list[str]]:
    """Return validation errors and non-blocking warnings."""
    errors: list[str] = []
    warnings: list[str] = []
    _validate_daily_logs(sources.get("daily_logs", []), errors, warnings)
    _validate_measurements(sources.get("body_measurements", []), errors)
    _validate_nutrition(sources.get("nutrition_entries", []), errors, warnings)
    _validate_workouts(sources.get("workouts", []), errors)
    return errors, warnings


def validate_or_raise(
    sources: dict[str, list[dict[str, Any]]],
) -> list[str]:
    """Raise for validation errors and return warnings otherwise."""
    errors, warnings = validate_sources(sources)
    if errors:
        raise HistoryValidationError(errors, warnings)
    return warnings


def source_stats(sources: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    return {name: len(sources.get(name, [])) for name in SOURCE_FILES}


def _valid_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d") == value
    except ValueError:
        return False


def _check_date(value: Any, label: str, errors: list[str]) -> None:
    if not _valid_date(value):
        errors.append(f"{label} 日期必须为 YYYY-MM-DD：{value!r}")


def _check_nonnegative(
    record: dict[str, Any], fields: tuple[str, ...], label: str, errors: list[str]
) -> None:
    for field in fields:
        value = record.get(field)
        if value is not None and (not isinstance(value, (int, float)) or value < 0):
            errors.append(f"{label} 的 {field} 不能为负数：{value!r}")


def _check_carbs(
    record: dict[str, Any], label: str, errors: list[str], warnings: list[str]
) -> None:
    total = record.get("total_carbs_g")
    fiber = record.get("fiber_g")
    net = record.get("net_carbs_g")
    if fiber is None:
        warnings.append(f"{label} 缺少 fiber 数据")
    if total is not None and net is not None and net > total + 0.1:
        errors.append(f"{label} 的 net carbs 明显大于 total carbs")


def _check_calorie_estimate(
    record: dict[str, Any], calories_field: str, label: str, warnings: list[str]
) -> None:
    calories = record.get(calories_field)
    protein = record.get("protein_g")
    carbs = record.get("total_carbs_g")
    fat = record.get("fat_g")
    if not calories or any(value is None for value in (protein, carbs, fat)):
        return
    estimate = protein * 4 + carbs * 4 + fat * 9
    difference = abs(calories - estimate) / calories
    if difference > 0.20:
        warnings.append(f"{label} 热量与宏量估算相差 {difference:.0%}")


def _validate_daily_logs(
    records: list[dict[str, Any]], errors: list[str], warnings: list[str]
) -> None:
    dates: set[str] = set()
    day_numbers: set[int] = set()
    for index, record in enumerate(records, 1):
        label = f"daily_logs 第 {index} 条"
        date = record.get("date")
        _check_date(date, label, errors)
        if date in dates:
            errors.append(f"daily_logs 日期重复：{date}")
        dates.add(date)
        day_number = record.get("day_number")
        if day_number is not None:
            if not isinstance(day_number, int) or isinstance(day_number, bool) or day_number <= 0:
                errors.append(f"{label} 的 day_number 必须为正整数")
            elif day_number in day_numbers:
                errors.append(f"day_number 重复：{day_number}")
            day_numbers.add(day_number)
        _check_nonnegative(record, MACRO_FIELDS, label, errors)
        _check_carbs(record, label, errors, warnings)
        _check_calorie_estimate(record, "calories_in", label, warnings)


def _validate_measurements(
    records: list[dict[str, Any]], errors: list[str]
) -> None:
    dates: set[str] = set()
    for index, record in enumerate(records, 1):
        label = f"body_measurements 第 {index} 条"
        measured_at = record.get("measured_at")
        _check_date(measured_at, label, errors)
        if measured_at in dates:
            errors.append(f"body_measurements 日期重复：{measured_at}")
        dates.add(measured_at)
        _check_nonnegative(
            record, ("weight", "waist", "body_fat_percentage"), label, errors
        )


def _validate_nutrition(
    records: list[dict[str, Any]], errors: list[str], warnings: list[str]
) -> None:
    for index, record in enumerate(records, 1):
        label = f"nutrition_entries 第 {index} 条"
        _check_date(record.get("date"), label, errors)
        if not isinstance(record.get("food_name"), str) or not record["food_name"].strip():
            errors.append(f"{label} 缺少 food_name")
        _check_nonnegative(record, MACRO_FIELDS + ("calories",), label, errors)
        _check_carbs(record, label, errors, warnings)
        _check_calorie_estimate(record, "calories", label, warnings)


def _validate_workouts(records: list[dict[str, Any]], errors: list[str]) -> None:
    workout_keys: set[tuple[Any, Any]] = set()
    for workout_index, workout in enumerate(records, 1):
        label = f"workouts 第 {workout_index} 条"
        date = workout.get("date")
        _check_date(date, label, errors)
        key = (date, workout.get("workout_name"))
        if key in workout_keys:
            errors.append(f"workout 重复：{date} / {key[1]}")
        workout_keys.add(key)
        for exercise in workout.get("exercises") or []:
            set_numbers: set[int] = set()
            name = exercise.get("exercise_name") or "未命名动作"
            for item in exercise.get("sets") or []:
                number = item.get("set_number")
                if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
                    errors.append(f"{label} / {name} 的 set_number 必须为正整数")
                elif number in set_numbers:
                    errors.append(f"{label} / {name} 的组号重复：{number}")
                set_numbers.add(number)


def print_report(
    sources: dict[str, list[dict[str, Any]]],
    errors: list[str],
    warnings: list[str],
) -> None:
    stats = source_stats(sources)
    heading = "验证失败：" if errors else "验证通过："
    print(heading)
    print(f"- {stats['daily_logs']} 个 daily logs")
    print(f"- {stats['body_measurements']} 个 body measurements")
    print(f"- {stats['nutrition_entries']} 个 nutrition entries")
    print(f"- {stats['workouts']} 个 workouts")
    if warnings:
        print("\n警告：")
        for warning in warnings:
            print(f"- {warning}")
    if errors:
        print("\n错误：")
        for error in errors:
            print(f"- {error}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--file", choices=SOURCE_FILES)
    args = parser.parse_args()
    try:
        sources = load_sources(args.source_dir, args.file)
        errors, warnings = validate_sources(sources)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"验证失败：\n- {error}")
        raise SystemExit(1) from error
    print_report(sources, errors, warnings)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
