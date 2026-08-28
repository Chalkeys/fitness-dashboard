"""Sync recent Xunji training, nutrition, and body data into daily exports.

API keys are read from environment variables and are never stored in the
repository.  Generated exports remain ``needs_review`` when TDEE is absent.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "exports"
TRAIN_URL = "https://trains.xunjiapp.cn/api_trains_for_llm_v2"
FOOD_URL = "https://eatings.xunjiapp.cn/open/food/query_gzip"
BODY_URL = "https://api.xunjiapp.cn/open/body/query_gzip"


def _load_env_file(path: Path | None = None) -> None:
    """Read `.env` into the environment, without taking a dependency.

    Anything already exported wins, so a shell variable still overrides the
    file. The file is gitignored: keys belong on the machine, not in the repo.
    """
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        os.environ.setdefault(name.strip(), value.strip().strip("'\""))


def _key(name: str) -> str:
    _load_env_file()
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"缺少 {name}。把它写进项目根目录的 .env（可参考 .env.example），"
            "或导出为环境变量。"
        )
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


DEFAULT_BMR = 1820.0
ACTIVE_ENERGY_FILE = ROOT / "data_sources" / "active_energy.json"


def load_measured_active_energy() -> dict[str, float]:
    """Apple Health's whole-day Active Energy, where it has been supplied.

    Xunji only reports the calories of workouts synced into it, never the
    day's total, so this file is the only route for a measured figure.
    """
    try:
        payload = json.loads(ACTIVE_ENERGY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    days = payload.get("days") if isinstance(payload, dict) else None
    if not isinstance(days, dict):
        return {}
    return {
        datestr: float(value)
        for datestr, value in days.items()
        if isinstance(value, (int, float)) and value > 0
    }


PROFILE_FILE = ROOT / "data_sources" / "profile.json"
# Past this gap the two estimates disagree enough that the body-fat reading,
# which only Katch-McArdle depends on, is the likely culprit.
BMR_CROSS_CHECK_TOLERANCE = 150.0


def load_profile() -> dict[str, Any]:
    try:
        payload = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def mifflin_st_jeor(
    weight_kg: float | None, on: date, profile: dict[str, Any]
) -> float | None:
    """The general-population estimate, from height and age rather than fat.

    Kept as a cross-check: it shares no inputs with Katch-McArdle beyond
    weight, so agreement between them is evidence the body-fat figure is
    sound.
    """
    height = _number(profile.get("height_cm"))
    birth_year = _number(profile.get("birth_year"))
    if weight_kg is None or height is None or birth_year is None:
        return None
    age = on.year - int(birth_year)
    constant = -161 if str(profile.get("sex", "male")).lower() == "female" else 5
    return round(10 * weight_kg + 6.25 * height - 5 * age + constant, 1)


def estimate_bmr(weight_kg: float | None, body_fat_pct: float | None) -> float:
    """Katch-McArdle: 370 + 21.6 x lean mass.

    Chosen over Mifflin-St Jeor because it needs only weight and body fat,
    both of which are tracked here, and it reproduces the 1820 this project
    had been assuming (80.9 kg at 17.1% gives 1819).
    """
    if weight_kg is None or body_fat_pct is None:
        return DEFAULT_BMR
    lean = weight_kg * (1 - body_fat_pct / 100)
    return round(370 + 21.6 * lean, 1)


# Whole-day active energy regressed on lifting volume across the 58 logged
# days that have a watch reading: AE = 584 + 0.0100 x tonnage. R2 is only
# 0.198 — most of a day's activity is walking and fidgeting, which tonnage
# says nothing about — so this is a fallback, never a substitute for a
# measured figure. Duration fitted far worse (R2 0.045): time under the bar
# counts, time between sets does not, and a session is mostly the latter.
#
# Three independent routes agree on the scale, which is why these numbers are
# trusted over the two that disagree:
#
#   this fit, volume term          243 kcal   for the 24.3 t session of 26 Aug
#   published regression           189        see below
#   mechanical work                194        24.3 t through 0.5 m is 28 kcal
#                                             of work; ~190 metabolically once
#                                             efficiency and the eccentric
#                                             phase are allowed for
#   Xunji's own figure             812        3-4x what moving that mass costs
#   MET 3.5 (what this replaced)   880
#
# The published regression predicts the net cost of one session from volume
# load and body composition, R2 0.773, SEE 28.5 kcal:
#
#   kcal = 0.874 x height_cm - 0.596 x age - 1.016 x fat_kg
#          + 1.638 x lean_kg + 2.461 x tonnage/1000 - 110.742
#
# Scored against the same 58 days it comes out level with this fit — mean
# absolute error 103 kcal against 102, identical correlation of 0.412 — but
# carries a +24 kcal bias where this one sits at -2, so the local fit stays.
# Worth re-deriving both after enough new data, or if training style changes.
#
# The 584 intercept stands on the fit alone. It looks close to the 575 mean of
# the rest days, but that is coincidence — two of those days were yard work,
# and a true rest day reads about 450.
#
# Ranges in the literature are very wide — a 2024 scoping review reports
# 38-2957 kJ for multi-exercise sessions and measured METs of 3.0-8.0 against
# the Compendium's 3.5/5.0/6.0 — so treat any single equation as an order of
# magnitude. That review also notes indirect calorimetry alone can miss over
# 40% of the cost by ignoring the glycolytic contribution, so these figures
# may run low rather than high.
# https://pmc.ncbi.nlm.nih.gov/articles/PMC11393209/
VOLUME_BASELINE_KCAL = 584.0
KCAL_PER_KG_LIFTED = 0.0100
# Five days off the programme carry a watch reading, but only one of them is
# a rest day in the sense this constant needs:
#
#   19 Jul   450   nothing logged                 <- the only clean one
#   28 Jun   452   20 min mowing, an hour's       ~400 without the mowing
#                  shopping
#   04 Jul   205   watch not worn — an            unusable
#                  undercount, not a rest day
#   12 Jul   718   "a lot of yard work"           not a rest day
#   26 Jul  1050   90 min yard work               not a rest day
#
# So 450, from the one day that qualifies and the one that nearly does. Their
# mean of 575 is meaningless here: two yard-work days pull it up. It had been
# 200, inherited from before any measured figure existed.
#
# Note this is legitimately below the 584 intercept above, which is a training
# day extrapolated to zero tonnage and still carries the walking that going to
# the gym involves.
REST_DAY_ACTIVE_KCAL = 450.0


def _tonnage(workout: dict[str, Any] | None) -> float:
    """Kilograms moved across every set of the day."""
    total = 0.0
    for exercise in (workout or {}).get("exercises", []):
        for item in exercise.get("sets", []):
            weight, reps = item.get("weight"), item.get("reps")
            if weight and reps:
                total += float(weight) * float(reps)
    return total


# A session cannot cost less energy than the mechanical work it performed,
# divided by how efficiently muscle turns energy into work. Taking half a
# metre as the mean bar displacement and 25% efficiency — the generous end of
# the 18-26% range measured in cycling, and lifting sits at or below it — puts
# a hard floor under any figure claiming to price a session.
#
# The floor exists because Xunji's note is not always a session estimate. On
# 27 Aug it read 42 kcal for a three-hour push day moving 12.5 tonnes, which
# would need 35% efficiency: not merely low, but past what muscle can do. A
# figure that fails this test is not a bad estimate to be preferred over the
# volume model, it is not an estimate at all, so the model takes the day.
BAR_DISPLACEMENT_M = 0.5
MUSCLE_EFFICIENCY = 0.25
JOULES_PER_KCAL = 4184.0


def mechanical_floor_kcal(tonnage: float) -> float:
    """The least a session moving this much weight could possibly have cost."""
    return tonnage * BAR_DISPLACEMENT_M * 9.81 / JOULES_PER_KCAL / MUSCLE_EFFICIENCY


def estimate_active_energy(workout: dict[str, Any] | None) -> float:
    """Stand-in for a day's active energy when no watch reading is to hand."""
    if not workout:
        return REST_DAY_ACTIVE_KCAL
    tonnage = _tonnage(workout)
    cardio = float(workout.get("active_energy_kcal") or 0)
    if not tonnage:
        # No lifting, so the 584 intercept does not apply — it is a training
        # day extrapolated to zero tonnage and still carries the walking that
        # going to the gym involves. What is left on a day like this is NEAT
        # plus whatever cardio was measured, and those do add: the rest-day
        # constant comes from a day with nothing logged, so it double-counts
        # nothing. Checked against the three non-lifting days whose cardio
        # came from the API rather than from a whole-day figure copied in:
        #
        #   19 Jul   450 + 0   = 450   against 450    exact
        #   16 Aug   450 + 0   = 450   against 434     +16
        #   23 Aug   450 + 481 = 931   against 971     -40
        #
        # The old max() rule read 450, 584 and 584 for those same days, the
        # last of them 387 kcal light.
        return REST_DAY_ACTIVE_KCAL + cardio
    estimate = VOLUME_BASELINE_KCAL + KCAL_PER_KG_LIFTED * tonnage
    # Cardio synced from Apple Health is measured, so it displaces the
    # baseline's share of walking rather than adding to the lift.
    return max(estimate, cardio)


_CALORIE_NOTE = re.compile(r"calorie:\s*([0-9]+(?:\.[0-9]+)?)")


def reported_calories(note: str | None) -> float | None:
    """The kcal figure Xunji puts in a session's note, if it put one there."""
    match = _CALORIE_NOTE.search(note or "")
    return float(match.group(1)) if match else None


def xunji_active_energy(workout: dict[str, Any] | None) -> float | None:
    """Xunji's own view of a day: its lifting figure plus the cardio it synced.

    Only the lifting sessions carry a note. The walk's calories arrive as set
    metrics and are already summed into ``active_energy_kcal``, so reading a
    note off the walk as well would count it twice.

    A caveat on the note itself: up to and including 2026-08-26 it carried a
    figure imported from Apple Health rather than Xunji's own model, which is
    why 26 Aug reads 812 for a session three independent routes price at
    190-240. The import is being turned off so the field starts carrying
    Xunji's estimate, which has never been checked against the DEXA scans.
    Treat it as unproven until it has been.
    """
    if not workout:
        return None
    strength = workout.get("xunji_strength_kcal")
    if strength is None:
        return None
    if float(strength) < mechanical_floor_kcal(_tonnage(workout)):
        return None
    return round(float(strength) + float(workout.get("active_energy_kcal") or 0), 1)


def resolve_active_energy(
    workout: dict[str, Any] | None,
    measured_active_energy: float | None = None,
) -> tuple[float, str]:
    """The day's activity figure and where it came from.

    Three sources, in order of preference:

    1. the hand-entered value in ``active_energy.json`` — the user's own
       reading, and the only source that exists for days before the API sync;
    2. Xunji's own figure, its lifting note plus the cardio it synced;
    3. the volume model below, when Xunji reports no figure.

    The three are never added together. A hand-entered value already covers
    the whole day and Xunji's already covers both halves of the training, so
    putting an estimate on top of either would bill the session twice.
    """
    if measured_active_energy:
        return float(measured_active_energy), "measured"
    reported = xunji_active_energy(workout)
    if reported:
        return reported, "xunji"
    return estimate_active_energy(workout), "estimated"


def _active_energy_note(
    workout: dict[str, Any] | None, active_kcal: float, source: str
) -> str:
    """One sentence saying where the day's activity figure came from."""
    if source == "measured":
        return f"TDEE = BMR + 手工录入的 Active Energy {active_kcal:.0f} kcal。"
    if source == "xunji":
        strength = (workout or {}).get("xunji_strength_kcal") or 0
        cardio = (workout or {}).get("active_energy_kcal") or 0
        return (
            f"TDEE = BMR + 训记消耗 {active_kcal:.0f} kcal"
            f"（力量 {strength:.0f} + 有氧 {cardio:.0f}）；未手工录入实测值。"
        )
    return (
        f"TDEE 的活动部分按训练容量估算 {active_kcal:.0f} kcal"
        "（584 + 0.01×容量，由 58 天全天实测拟合）；训记与手工录入均无当日数值。"
    )


def _estimate_tdee(
    workout: dict[str, Any] | None,
    weight_kg: float | None,
    body_fat_pct: float | None = None,
    measured_active_energy: float | None = None,
) -> int:
    """TDEE as BMR plus activity, measured where possible."""
    bmr = estimate_bmr(weight_kg, body_fat_pct)
    active, _ = resolve_active_energy(workout, measured_active_energy)
    return round(bmr + active, -1)


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
    strength_kcal: float | None = None
    spans: list[int] = []
    for train in trains:
        if train.get("start") is not None and train.get("end") is not None:
            spans.append(int(train["end"]) - int(train["start"]))
        if train.get("title") != "步行":
            reported = reported_calories(train.get("note"))
            if reported is not None:
                strength_kcal = (strength_kcal or 0.0) + reported
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
    # Each session's own span, summed. Measuring from the first start to the
    # last end would bill the gap between lifting and a later walk as training
    # time, and charge all of it to the lifting session.
    duration = round(sum(spans) / 60000, 1) if spans else None
    workout_name = " + ".join(titles) if titles else "训记训练"
    return {
        "session_id": f"day-{day_number:03d}-xunji",
        "workout_name": workout_name,
        "workout_type": (titles[0].lower().replace("-", "_") if titles else None),
        "duration_minutes": duration,
        "active_energy_kcal": round(active_energy, 1) if active_energy else None,
        "xunji_strength_kcal": round(strength_kcal, 1) if strength_kcal else None,
        "notes": "训练动作来自训记 API；有氧消耗取 sets[].metrics.calories，力量消耗取课次 note 的 calorie 字段。",
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
            "include_latest": True,
            "include_records": True,
            "limit": 500,
            "offset": 0,
        },
    )
    measured_active_energy = load_measured_active_energy()
    profile = load_profile()
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
    # `latest` reaches back past the synced window, so a body-fat reading from
    # a week ago still informs today's BMR.
    latest = body_result.get("res", {}).get("latest") or {}
    latest_weight = _number((latest.get("weight") or {}).get("value"))
    latest_body_fat = _number((latest.get("bodyfat") or {}).get("value"))

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
        # Re-syncing a day must supersede what is already there: the importer
        # keeps the higher history_version and would otherwise ignore the
        # refresh, and normalization bumps the version of what it touches.
        history_version = 1
        if target.exists():
            try:
                previous = json.loads(target.read_text(encoding="utf-8"))
                history_version = int(previous.get("history_version", 0)) + 1
            except (OSError, ValueError):
                history_version = 2
        train_result = _post(
            TRAIN_URL,
            train_key,
            {"schema_version": "train_open_api_v2", "datestr": datestr, "include_full_data": True},
        )
        diet_day = food_days.get(datestr, {})
        totals = diet_day.get("totals") or {}
        body = body_by_date.get(datestr)
        workout = _workout(train_result.get("res", {}).get("trains", []), day_number)
        weight_kg = (body.get("weight_kg") if body else None) or latest_weight
        # Body fat is measured every week or two, so the last known value
        # stands in until the next reading.
        body_fat = (body.get("body_fat_percentage") if body else None) or latest_body_fat
        bmr = estimate_bmr(weight_kg, body_fat)
        cross_check = mifflin_st_jeor(weight_kg, current, profile)
        bmr_warning = (
            f"（Mifflin-St Jeor 交叉验证为 {cross_check:.0f}，相差 "
            f"{abs(cross_check - bmr):.0f} kcal，体脂读数可能不准）"
            if cross_check and abs(cross_check - bmr) > BMR_CROSS_CHECK_TOLERANCE
            else ""
        )
        measured_ae = measured_active_energy.get(datestr)
        active_kcal, active_source = resolve_active_energy(workout, measured_ae)
        estimated_tdee = _estimate_tdee(workout, weight_kg, body_fat, measured_ae)
        titles = [item.get("title") for item in train_result.get("res", {}).get("trains", []) if item.get("title") != "步行"]
        document = {
            "protocol_version": "1.0",
            "export_id": f"day-{day_number:03d}",
            "history_version": history_version,
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
                "active_energy_kcal": round(active_kcal, 1),
                "active_energy_source": active_source,
                "notes": (
                    f"膳食纤维暂按 0 g；净碳水按总碳水计算；BMR≈{bmr:.0f}"
                    f"（Katch-McArdle，按当日体重与最近体脂）{bmr_warning}。"
                    + _active_energy_note(workout, active_kcal, active_source)
                ),
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
