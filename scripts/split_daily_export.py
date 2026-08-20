"""Normalize a ChatGPT daily-export array into one protocol file per day."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DAILY_FIELDS = (
    "is_training_day", "workout_type", "calories_in", "tdee", "calorie_balance",
    "protein_g", "total_carbs_g", "fiber_g", "net_carbs_g", "fat_g", "steps",
    "active_energy_kcal", "notes",
)
NUTRITION_FIELDS = (
    "entry_id", "meal_type", "food_name", "brand", "amount", "unit", "servings",
    "calories", "protein_g", "total_carbs_g", "fiber_g", "net_carbs_g", "fat_g", "notes",
)


def split_export(input_path: Path, output_dir: Path, *, dry_run: bool = False, force: bool = False) -> dict[str, int]:
    records = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("输入文件必须是每日导出对象数组")
    documents = [_normalize(record) for record in records]
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        existing = [output_dir / f"day-{doc['day_number']:03d}.json" for doc in documents]
        conflicts = [path for path in existing if path.exists() and not force]
        if conflicts:
            names = ", ".join(path.name for path in conflicts)
            raise FileExistsError(f"目标文件已存在（如需覆盖请使用 --force）：{names}")
        for path, document in zip(existing, documents):
            path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"files": len(documents), "dated": sum(doc["date"] is not None for doc in documents)}


def _normalize(record: dict[str, Any]) -> dict[str, Any]:
    day_number = record.get("day_number")
    if not isinstance(day_number, int) or day_number < 1:
        raise ValueError("每条记录都必须包含正整数 day_number")
    provenance = record.get("provenance") or {}
    exported_at = record.get("exported_at") or "1970-01-01T00:00:00Z"
    provenance_notes = provenance.get("review_notes")
    if not record.get("exported_at"):
        provenance_notes = _join_notes(provenance_notes, "原始 exported_at 缺失；使用协议哨兵时间 1970-01-01T00:00:00Z。")
    document = {
        "protocol_version": "1.0",
        "export_id": record.get("export_id") or f"day-{day_number:03d}",
        "history_version": int(record.get("history_version") or 1),
        "exported_at": exported_at,
        "date": record.get("date"),
        "day_number": day_number,
        "provenance": {
            "source": provenance.get("source") or "chat_history",
            "confidence": provenance.get("confidence") if provenance.get("confidence") in {"low", "medium", "high"} else "low",
            "notes": provenance_notes,
        },
        "body": _body(record.get("body")),
        "daily_log": _daily_log(record.get("daily_log")),
        "nutrition": [_nutrition_entry(item) for item in record.get("nutrition") or []],
        "workout": _workout(record.get("workout")),
        "review": _review(record, provenance),
    }
    return document


def _body(body: dict[str, Any] | None) -> dict[str, Any] | None:
    if body is None:
        return None
    return {
        "weight_kg": body.get("weight_kg", body.get("morning_weight_kg")),
        "waist_cm": body.get("waist_cm"),
        "body_fat_percentage": body.get("body_fat_percentage", body.get("body_fat_percent")),
        "notes": body.get("notes"),
    }


def _daily_log(daily: dict[str, Any] | None) -> dict[str, Any] | None:
    if daily is None:
        return None
    return {field: daily.get(field) for field in DAILY_FIELDS}


def _nutrition_entry(item: dict[str, Any]) -> dict[str, Any]:
    result = {field: item.get(field) for field in NUTRITION_FIELDS}
    extras = []
    for field in ("source", "confidence", "review_status"):
        if item.get(field) is not None:
            extras.append(f"{field}={item[field]}")
    if extras:
        result["notes"] = _join_notes(result.get("notes"), "原始字段：" + "; ".join(extras))
    return result


def _workout(workout: dict[str, Any] | None) -> dict[str, Any] | None:
    if workout is None:
        return None
    exercises = []
    for exercise in workout.get("exercises") or []:
        sets = []
        for item in exercise.get("sets") or []:
            weight = item.get("weight")
            notes = item.get("notes")
            unit = item.get("weight_unit")
            if weight is not None and unit == "lb":
                weight = round(weight * 0.45359237, 4)
                notes = _join_notes(notes, f"原始重量：{item['weight']} lb；已转换为 kg。")
            elif unit and unit != "kg":
                notes = _join_notes(notes, f"原始重量单位：{unit}。")
            sets.append({
                "set_number": item.get("set_number"), "weight": weight, "reps": item.get("reps"),
                "rir": item.get("rir"), "distance": item.get("distance"),
                "duration_seconds": item.get("duration_seconds"), "notes": notes,
            })
        exercises.append({
            "exercise_name": exercise.get("exercise_name"), "category": exercise.get("category"),
            "muscle_group": exercise.get("muscle_group"), "sets": sets,
        })
    return {
        "session_id": workout.get("session_id"), "workout_name": workout.get("workout_name"),
        "workout_type": workout.get("workout_type"), "duration_minutes": workout.get("duration_minutes"),
        "active_energy_kcal": workout.get("active_energy_kcal"), "notes": workout.get("notes"),
        "exercises": exercises,
    }


def _review(record: dict[str, Any], provenance: dict[str, Any]) -> list[dict[str, Any]]:
    reviews = []
    for item in record.get("review") or []:
        status = item.get("status") if item.get("status") in {"approved", "needs_review", "rejected"} else "needs_review"
        field = ".".join(str(part) for part in (item.get("entity_type"), item.get("field")) if part)
        note = _join_notes(item.get("issue"), item.get("suggested_action"))
        if item.get("current_value") is not None:
            note = _join_notes(note, "当前值=" + json.dumps(item["current_value"], ensure_ascii=False))
        reviews.append({"review_status": status, "note": note, "field": field or None})
    if not reviews:
        status = provenance.get("review_status") if provenance.get("review_status") in {"approved", "needs_review", "rejected"} else "needs_review"
        reviews.append({"review_status": status, "note": provenance.get("review_notes"), "field": None})
    return reviews


def _join_notes(*values: Any) -> str | None:
    parts = [str(value).strip() for value in values if value not in (None, "")]
    return " ".join(parts) or None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("exports"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = split_export(args.input.resolve(), args.output_dir.resolve(), dry_run=args.dry_run, force=args.force)
    action = "将生成" if args.dry_run else "已生成"
    print(f"{action} {result['files']} 个每日 JSON（其中有日期 {result['dated']} 个）")


if __name__ == "__main__":
    main()
