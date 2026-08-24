"""Energy-balance arithmetic, including bias-corrected calorie balance.

Logged TDEE and logged intake are both estimates, and they err in different
places. Resting metabolism tracks body mass and barely moves day to day, so the
expenditure error sits in the activity estimate on top of it; hand-logged food
tends to understate intake. TDEE is therefore split at a resting baseline and
only the activity remainder is scaled.
"""

from __future__ import annotations

import pandas as pd

# Energy density of body-mass change. Fat tissue takes the usual dietetics
# approximation; lean tissue is mostly water and costs a fraction of it.
FAT_KCAL_PER_KG = 7700.0
LEAN_KCAL_PER_KG = 1800.0
KCAL_PER_KG = FAT_KCAL_PER_KG  # kept for callers that only price fat

# Lean mass accrues from training and protein rather than from the size of the
# deficit, so it is modelled as a rate rather than a share of the weight
# change. Measured between the DEXA scans of 16 July and 18 August: 1.19 kg
# over 34 days. Re-derive it after the next scan.
LEAN_GAIN_KG_PER_DAY = 1.19 / 34


def split_weight_change(total_kg: float, days: int) -> tuple[float, float]:
    """Divide a scale change into its fat and lean parts.

    Scale weight understates what is happening during recomposition: over the
    DEXA window the scale moved 0.65 kg while 1.84 kg of fat left and 1.19 kg
    of lean arrived. Pricing the whole change as fat would have valued that
    period at a third of its real energy cost.
    """
    lean_kg = LEAN_GAIN_KG_PER_DAY * days
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
    fed = daily[daily["tdee"] > 0]
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
    fed = daily[daily["tdee"] > 0]
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
    fed = daily[daily["tdee"] > 0]
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
    actual_fat_kg, lean_kg = split_weight_change(actual_kg, days)

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
