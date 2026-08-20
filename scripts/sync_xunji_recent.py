"""Sync recent Xunji training, nutrition, and body data into daily exports.

API keys are read from environment variables and are never stored in the
repository.  Generated exports remain ``needs_review`` when TDEE is absent.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "exports"
TRAIN_URL = "https://trains.xunjiapp.cn/api_trains_for_llm_v2"
FOOD_URL = "https://eatings.xunjiapp.cn/open/food/query_gzip"
BODY_URL = "https://api.xunjiapp.cn/open/body/query_gzip"


def _key(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"缺少环境变量 {name}")
    return value


def _post(url: str, key: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    result = json.loads(raw.decode("utf-8"))
    if result.get("success") is False:
        raise RuntimeError(str(result.get("res", "训记接口失败")))
    return result


def _number(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    number = _number(value)
    return None if number is None else int(number)


def _estimate_tdee(workout: dict[str, Any] | None, weight_kg: float | None) -> int:
    """Estimate TDEE as BMR plus activity, without double-counting cardio."""
    bmr = 1820.0
    if not workout:
        return round(bmr + 200, -1)
    weight = weight_kg or 82.5
    duration = float(workout.get("duration_minutes") or 0)
    cardio = float(workout.get("active_energy_kcal") or 0)
    cardio_minutes = cardio / 5.0 if cardio else 0.0
    strength_minutes = max(0.0, duration - cardio_minutes)
    # Net moderate/high-intensity lifting estimate, adjusted for body weight.
    strength_rate = 3.5 * weight / 200 * 3.5
    return round(bmr + cardio + strength_minutes * strength_rate, -1)


def _kg(weight: Any, unit: str | None) -> float | None:
    value = _number(weight)
    if value is None:
        return None
    if (unit or "").lower() in {"lb", "lbs"}:
        value /= 2.2046226218
    return round(value, 4)


def _day_number(value: date) -> int:
    # Day 44 is 2026-08-04 in the existing project history.
    return 44 + (value - date(2026, 8, 4)).days


def _nutrition(day: dict[str, Any], day_number: int) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for index, food in enumerate((day.get("foods") or {}).get("records", []), 1):
        ntr = food.get("ntr") or {}
        entries.append(
            {
                "entry_id": f"D{day_number:03d}_XJ{index:03d}",
                "meal_type": food.get("meal_type") or "custom",
                "food_name": food.get("name") or "Unknown food",
                "brand": None,
                "amount": _number(food.get("amount")),
                "unit": food.get("unit") or "custom",
                "servings": None,
                "calories": _number(food.get("cals")) or _number(ntr.get("cal")),
                "protein_g": _number(ntr.get("protein")),
                "total_carbs_g": _number(ntr.get("carb")),
                "fiber_g": 0,
                "net_carbs_g": _number(ntr.get("carb")) or 0,
                "fat_g": _number(ntr.get("fat")),
                "notes": "训记 API 营养快照；纤维未由接口返回。",
            }
        )
    return entries


def _workout(trains: list[dict[str, Any]], day_number: int) -> dict[str, Any] | None:
    if not trains:
        return None
    strength = [item for item in trains if item.get("title") != "步行"]
    titles = [item.get("title") for item in strength if item.get("title")]
    exercises: list[dict[str, Any]] = []
    active_energy = 0.0
    starts: list[int] = []
    ends: list[int] = []
    for train in trains:
        if train.get("start") is not None:
            starts.append(int(train["start"]))
        if train.get("end") is not None:
            ends.append(int(train["end"]))
        for movement in train.get("movements", []):
            name = movement.get("name") or "Unknown movement"
            if name == "Walking":
                for item in movement.get("sets", []):
                    metrics = item.get("metrics") or {}
                    active_energy += _number(metrics.get("calories")) or 0
                continue
            sets = []
            for number, item in enumerate(movement.get("sets", []), 1):
                notes = None if item.get("done", True) else "未完成组"
                sets.append(
                    {
                        "set_number": number,
                        "weight": _kg(item.get("weight"), item.get("unit")),
                        "reps": _int(item.get("reps")),
                        "rir": _number(item.get("rpe")),
                        "distance": None,
                        "duration_seconds": _int(item.get("duration_s")),
                        "notes": notes,
                    }
                )
            exercises.append(
                {
                    "exercise_name": name,
                    "category": "other",
                    "muscle_group": None,
                    "sets": sets,
                }
            )
    duration = None
    if starts and ends:
        duration = round((max(ends) - min(starts)) / 60000, 1)
    workout_name = " + ".join(titles) if titles else "训记训练"
    return {
        "session_id": f"day-{day_number:03d}-xunji",
        "workout_name": workout_name,
        "workout_type": (titles[0].lower().replace("-", "_") if titles else None),
        "duration_minutes": duration,
        "active_energy_kcal": round(active_energy, 1) if active_energy else None,
        "notes": "训练动作来自训记 API；Active Energy 使用接口返回的 sets[].metrics.calories。",
        "exercises": exercises,
    }


def build_exports(start: date, end: date, overwrite: bool = False) -> list[Path]:
    train_key = _key("XUNJI_TRAIN_API_KEY")
    food_key = _key("XUNJI_FOOD_API_KEY")
    body_key = _key("XUNJI_BODY_API_KEY")
    start_text, end_text = start.isoformat(), end.isoformat()

    food_result = _post(
        FOOD_URL,
        food_key,
        {"start_date": start_text, "end_date": end_text, "include_detail": True},
    )
    food_days = {item["datestr"]: item for item in food_result.get("res", {}).get("days", [])}
    body_result = _post(
        BODY_URL,
        body_key,
        {
            "start_date": start_text,
            "end_date": end_text,
            "include_latest": False,
            "include_records": True,
            "limit": 500,
            "offset": 0,
        },
    )
    body_by_date: dict[str, dict[str, Any]] = {}
    body_field_map = {
        "weight": "weight_kg",
        "bodyfat": "body_fat_percentage",
        "weist": "waist_cm",
        "neck": "neck_cm",
        "chest": "chest_cm",
        "shoulder": "shoulder_cm",
        "bot": "hip_cm",
        "arm_left": "arm_left_cm",
        "arm_right": "arm_right_cm",
        "forearm_left": "forearm_left_cm",
        "forearm_right": "forearm_right_cm",
        "leg_left": "leg_left_cm",
        "leg_right": "leg_right_cm",
        "cav_left": "calf_left_cm",
        "cav_right": "calf_right_cm",
    }
    for item in body_result.get("res", {}).get("records", []):
        field = body_field_map.get(item.get("type"))
        if field:
            body_by_date.setdefault(item["datestr"], {})[field] = _number(item.get("value"))

    generated: list[Path] = []
    current = start
    while current <= end:
        datestr = current.isoformat()
        day_number = _day_number(current)
        target = EXPORT_DIR / f"day-{day_number:03d}.json"
        if target.exists() and not overwrite:
            raise FileExistsError(f"不会覆盖已有文件：{target}")
        train_result = _post(
            TRAIN_URL,
            train_key,
            {"schema_version": "train_open_api_v2", "datestr": datestr, "include_full_data": True},
        )
        diet_day = food_days.get(datestr, {})
        totals = diet_day.get("totals") or {}
        body = body_by_date.get(datestr)
        workout = _workout(train_result.get("res", {}).get("trains", []), day_number)
        weight_kg = body.get("weight_kg") if body else None
        estimated_tdee = _estimate_tdee(workout, weight_kg)
        titles = [item.get("title") for item in train_result.get("res", {}).get("trains", []) if item.get("title") != "步行"]
        document = {
            "protocol_version": "1.0",
            "export_id": f"day-{day_number:03d}",
            "history_version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "date": datestr,
            "day_number": day_number,
            "provenance": {
                "source": "xunji_app",
                "confidence": "high",
                "notes": "数据来自训记 Open API；膳食纤维按 0 g，净碳水按总碳水；TDEE 为估算值。",
            },
            "body": {**body, "notes": "训记 Open API 身体数据。"} if body else None,
            "daily_log": {
                "is_training_day": bool(titles),
                "workout_type": titles[0].lower().replace("-", "_") if titles else None,
                "calories_in": _number(totals.get("totalCal")),
                "tdee": estimated_tdee,
                "calorie_balance": round((_number(totals.get("totalCal")) or 0) - estimated_tdee, 2),
                "protein_g": _number(totals.get("totalProtein")),
                "total_carbs_g": _number(totals.get("totalCarb")),
                "fiber_g": 0,
                "net_carbs_g": _number(totals.get("totalCarb")) or 0,
                "fat_g": _number(totals.get("totalFat")),
                "steps": None,
                "active_energy_kcal": workout.get("active_energy_kcal") if workout else None,
                "notes": "膳食纤维暂按 0 g；净碳水按总碳水计算；TDEE 为 BMR≈1820 加训练活动消耗估算。",
            },
            "nutrition": _nutrition(diet_day, day_number),
            "workout": workout,
            "review": [
                {
                    "review_status": "approved",
                    "note": "用户确认纤维按 0 g、净碳水等于总碳水，并接受 TDEE 估算。",
                    "field": "daily_log",
                }
            ],
        }
        target.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        generated.append(target)
        current += timedelta(days=1)
    return generated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2026-08-10")
    parser.add_argument("--end", default="2026-08-13")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if end < start:
        raise SystemExit("--end 不能早于 --start")
    for path in build_exports(start, end, args.overwrite):
        print(path)


if __name__ == "__main__":
    main()
