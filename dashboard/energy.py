"""Energy-balance arithmetic, including bias-corrected calorie balance.

Logged TDEE and logged intake are both estimates, and they err in different
places. Resting metabolism tracks body mass and barely moves day to day, so the
expenditure error sits in the activity estimate on top of it; hand-logged food
tends to understate intake. TDEE is therefore split at a resting baseline and
only the activity remainder is scaled.
"""

from __future__ import annotations

import pandas as pd

from dashboard import data

# Energy density of body-mass change. Fat tissue takes the usual dietetics
# approximation; lean tissue is mostly water and costs a fraction of it.
FAT_KCAL_PER_KG = 7700.0
LEAN_KCAL_PER_KG = 1800.0
KCAL_PER_KG = FAT_KCAL_PER_KG  # kept for callers that only price fat

# Lean mass accrues from training and protein rather than from the size of the
# deficit, so it is modelled as a rate rather than a share of the weight
# change. Measured across the whole DEXA record, 16 July to 17 September:
# +1.13 kg (141.0 → 143.5 lb) over 63 days. This is the rate used when the
# balance it ran under is not known; where it is, ``lean_rate`` below.
LEAN_GAIN_KG_PER_DAY = 1.13 / 63

# The same record, one scan interval at a time, as (raw balance kcal/day,
# lean kg/day). 16 Jul → 18 Aug ran at −479 a day and gained 45 g of lean a
# day; 18 Aug → 17 Sep at −688 lost 12. Two points fix a line, whose zero is
# where a deficit stops leaving room for muscle; a third scan bends it. Each
# scan's lean reading is good to about ±0.5 kg, so the slope is known to
# about ±15 g/day at either end — enough to say that −500 grew and −700 did
# not, not enough to place the crossing closer than a hundred or so.
LEAN_RATE_POINTS: tuple[tuple[float, float], ...] = ((-479.0, 1.50 / 33), (-688.0, -0.36 / 30))


def lean_rate(balance_per_day: float) -> float:
    """Lean gained per day under a given raw daily balance, kg.

    Linear between the measured points and beyond the deeper one. Shallower
    than the shallowest, the rate is held rather than extrapolated: nothing
    measured says a smaller deficit grows muscle faster, and the line's
    intercept at maintenance would say 175 g a day, which is not a thing.
    """
    (b0, r0), (b1, r1) = LEAN_RATE_POINTS[0], LEAN_RATE_POINTS[-1]
    if balance_per_day >= b0:
        return r0
    return r0 + (r1 - r0) / (b1 - b0) * (balance_per_day - b0)


def lean_neutral_balance() -> float:
    """The daily balance below which lean mass starts to go, kcal."""
    (b0, r0), (b1, r1) = LEAN_RATE_POINTS[0], LEAN_RATE_POINTS[-1]
    return b0 - r0 * (b1 - b0) / (r1 - r0)


def split_weight_change(
    total_kg: float, days: int, balance_per_day: float | None = None
) -> tuple[float, float]:
    """Divide a scale change into its fat and lean parts.

    Scale weight understates what is happening during recomposition: over the
    first DEXA window the scale moved 0.65 kg while 1.86 kg of fat left and
    1.50 kg of lean arrived. Pricing the whole change as fat would have valued
    that period at a third of its real energy cost. Given the balance the
    days ran under, the lean part follows ``lean_rate``; without it, the
    long-run average.
    """
    rate = LEAN_GAIN_KG_PER_DAY if balance_per_day is None else lean_rate(balance_per_day)
    lean_kg = rate * days
    return total_kg - lean_kg, lean_kg


def energy_of_weight_change(total_kg: float, days: int) -> float:
    fat_kg, lean_kg = split_weight_change(total_kg, days)
    return fat_kg * FAT_KCAL_PER_KG + lean_kg * LEAN_KCAL_PER_KG


# Resting baseline the logged TDEE was built on. Weight-driven, so it drifts by
# only ~20 kcal across a couple of kilos.
DEFAULT_BMR = 1820.0


def split_tdee(
    daily: pd.DataFrame, bmr: float = DEFAULT_BMR
) -> tuple[pd.Series, pd.Series]:
    """Logged TDEE split into its resting baseline and activity remainder.

    Deriving activity from the `active_energy` column would be preferable, but
    it is missing on some days, where the subtraction would credit the whole
    day to resting metabolism. Subtracting a fixed baseline is defined for
    every day. A day logged below the baseline keeps its own value as resting
    and contributes no activity.
    """
    fed = data.fed(daily)
    active = (fed["tdee"] - bmr).clip(lower=0)
    return fed["tdee"] - active, active


def corrected_tdee(
    daily: pd.DataFrame, active_bias: float = 0.0, bmr: float = DEFAULT_BMR
) -> pd.Series:
    """Logged TDEE with only its activity part scaled by `active_bias`."""
    base, active = split_tdee(daily, bmr)
    return base + active * (1 + active_bias)


def corrected_balance(
    daily: pd.DataFrame,
    active_bias: float = 0.0,
    intake_bias: float = 0.0,
    bmr: float = DEFAULT_BMR,
) -> pd.Series:
    """Daily balance after correcting activity expenditure and intake.

    Biases are fractions: -0.4 shrinks that side by 40%.
    """
    fed = data.fed(daily)
    return fed["calories_intake"] * (1 + intake_bias) - corrected_tdee(
        daily, active_bias, bmr
    )


def calibration(
    daily: pd.DataFrame,
    body: pd.DataFrame,
    active_bias: float = 0.0,
    intake_bias: float = 0.0,
    bmr: float = DEFAULT_BMR,
    smoothing: int = 1,
) -> dict | None:
    """Compare the balance's predicted weight change with the measured one.

    Returns None when the window holds too little data to compare.

    Weigh-ins are taken as they came in rather than smoothed: a DEXA scan
    measures the body on its own morning, so pairing its composition with an
    average of the surrounding week is not comparing like with like. The cost
    is that day-to-day water swings ride on the endpoints — raise `smoothing`
    to trade that noise back against the bias.
    """
    fed = data.fed(daily)
    if fed.empty or body.empty:
        return None

    start, end = fed["log_date"].min(), fed["log_date"].max()
    weights = (
        body[body["measured_at"].between(start, end)]
        .dropna(subset=["weight_kg"])
        .set_index("measured_at")["weight_kg"]
        .rolling(smoothing, min_periods=min(2, smoothing))
        .mean()
        .dropna()
    )
    if len(weights) < 2:
        return None

    balance = corrected_balance(fed, active_bias, intake_bias, bmr)
    days = len(balance)
    actual_kg = float(weights.iloc[-1] - weights.iloc[0])
    actual_fat_kg, lean_kg = split_weight_change(actual_kg, days, float(balance.mean()))

    # What the logged balance buys, once the lean gained over the same days is
    # paid for: the rest lands on fat, which is what the scale change is then
    # compared against.
    predicted_fat_kg = (balance.sum() - lean_kg * LEAN_KCAL_PER_KG) / FAT_KCAL_PER_KG
    predicted_kg = float(predicted_fat_kg + lean_kg)

    # One equation, two unknowns: this is the net daily error across both
    # sides, not a split between them.
    measured_energy = energy_of_weight_change(actual_kg, days)
    residual_per_day = (measured_energy - balance.sum()) / days

    return {
        "days": days,
        "predicted_kg": predicted_kg,
        "actual_kg": actual_kg,
        "actual_fat_kg": float(actual_fat_kg),
        "lean_kg": float(lean_kg),
        "residual_per_day": float(residual_per_day),
        "mean_balance": float(balance.mean()),
    }


def target_plan(
    daily: pd.DataFrame,
    body: pd.DataFrame,
    target_body_fat: float,
    horizon_days: int,
    active_bias: float = 0.0,
    intake_bias: float = 0.0,
    active_energy_window: int = 14,
    today: pd.Timestamp | None = None,
) -> dict | None:
    """What to eat to reach a body-fat target by a date.

    Anchored on the most recent body-fat measurement rather than the scale:
    weight alone cannot say how much of it is fat. Lean is carried forward at
    the measured accrual rate, which is what makes the target a moving one —
    gaining lean raises the fat mass a given percentage allows.

    The deadline is ``horizon_days`` from today, not from the last reading.
    Those are two different spans whenever the scale has not been stepped on
    yet: the body has from its last known state until the deadline to change,
    which is the longer one and what the lean projection runs over, while the
    eating that has to cause the change only has from today, which is what the
    daily figure divides by. The elapsed day still counts for lean at the
    planned rate, so a stale weigh-in moves the figure by a few kcal only.

    Fat and lean stay paired at the last weight reading rather than being
    projected to today, because that weight was measured on the same morning
    as the mass it is split into.
    """
    scans = body.dropna(subset=["body_fat_percentage"])
    weights = body.dropna(subset=["weight_kg"])
    fed = data.fed(daily)
    if scans.empty or weights.empty or fed.empty:
        return None

    scan = scans.iloc[-1]
    latest = weights.iloc[-1]
    days_since_scan = max((latest["measured_at"] - scan["measured_at"]).days, 0)

    lean_at_scan = scan["weight_kg"] * (1 - scan["body_fat_percentage"] / 100)
    # Lean since the scan grew at whatever the days since then were run at.
    since_scan = fed[fed["log_date"] > scan["measured_at"]]
    rate_since = (
        lean_rate(float((since_scan["calories_intake"] - since_scan["tdee"]).mean()))
        if not since_scan.empty
        else LEAN_GAIN_KG_PER_DAY
    )
    lean_now = lean_at_scan + rate_since * days_since_scan
    fat_now = latest["weight_kg"] - lean_now

    start = (today or pd.Timestamp.today()).normalize()
    target_date = start + pd.Timedelta(int(horizon_days), unit="D")
    days_ahead = max((target_date - latest["measured_at"]).days, horizon_days)

    # Lean over the horizon is projected at the long-run rate, not at the
    # rate the planned deficit would allow. Solving the two together is a
    # loop with a gain near one — a deeper deficit costs lean, less lean
    # allows less fat, which asks for a deeper deficit — and it multiplies a
    # −800 need into −1400 on the strength of a slope known to ±15 g/day.
    # What the deficit would do to lean is reported, not fed back.
    lean_end = lean_now + LEAN_GAIN_KG_PER_DAY * days_ahead
    # Fat allowed at the target, given the lean mass there will be by then.
    fat_target = target_body_fat / (1 - target_body_fat) * lean_end
    fat_change = fat_target - fat_now

    stored = fat_change * FAT_KCAL_PER_KG + LEAN_GAIN_KG_PER_DAY * days_ahead * LEAN_KCAL_PER_KG
    balance_per_day = stored / horizon_days

    recent = fed.tail(active_energy_window)
    active_logged = float(recent["active_energy"].mean()) if "active_energy" in recent else 0.0
    bmr = 370 + 21.6 * (lean_now + lean_end) / 2
    tdee_true = bmr + active_logged * (1 + active_bias)
    intake_true = tdee_true + balance_per_day
    intake_logged = intake_true / (1 + intake_bias)

    return {
        "scan_date": scan["measured_at"],
        "days_since_scan": days_since_scan,
        "target_date": target_date,
        "days_ahead": int(days_ahead),
        "weighed_at": latest["measured_at"],
        "weight_now": float(latest["weight_kg"]),
        "fat_now": float(fat_now),
        "lean_now": float(lean_now),
        "body_fat_now": float(fat_now / latest["weight_kg"]),
        "fat_target": float(fat_target),
        "lean_end": float(lean_end),
        "weight_end": float(fat_target + lean_end),
        "fat_change": float(fat_change),
        "balance_per_day": float(balance_per_day),
        "lean_rate_implied": lean_rate(float(balance_per_day)),
        "bmr": float(bmr),
        "active_logged": active_logged,
        "tdee_true": float(tdee_true),
        "intake_true": float(intake_true),
        "intake_logged": float(intake_logged),
        "recent_intake_logged": float(recent["calories_intake"].mean()),
    }
