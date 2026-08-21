"""Energy-balance arithmetic, including bias-corrected calorie balance.

Logged TDEE and logged intake are both estimates, and they err in different
places. Resting metabolism tracks body mass and barely moves day to day, so the
expenditure error sits in the activity estimate on top of it; hand-logged food
tends to understate intake. TDEE is therefore split at a resting baseline and
only the activity remainder is scaled.
"""

from __future__ import annotations

import pandas as pd

# Energy density of body-mass change; the usual dietetics approximation for
# fat tissue. Real change mixes fat, glycogen, and water, so treat any
# prediction from it as a trend, not a scale reading.
KCAL_PER_KG = 7700.0

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
    smoothing: int = 7,
) -> dict | None:
    """Compare the balance's predicted weight change with the measured one.

    Returns None when the window holds too little data to compare. Weight is
    smoothed first so a single noisy weigh-in cannot drive the answer.
    """
    fed = daily[daily["tdee"] > 0]
    if fed.empty or body.empty:
        return None

    start, end = fed["log_date"].min(), fed["log_date"].max()
    weights = (
        body[body["measured_at"].between(start, end)]
        .dropna(subset=["weight_kg"])
        .set_index("measured_at")["weight_kg"]
        .rolling(smoothing, min_periods=2)
        .mean()
        .dropna()
    )
    if len(weights) < 2:
        return None

    balance = corrected_balance(fed, active_bias, intake_bias, bmr)
    days = len(balance)
    actual_kg = float(weights.iloc[-1] - weights.iloc[0])
    predicted_kg = float(balance.sum() / KCAL_PER_KG)

    # One equation, two unknowns: this is the net daily error across both
    # sides, not a split between them.
    residual_per_day = (actual_kg * KCAL_PER_KG - balance.sum()) / days

    return {
        "days": days,
        "predicted_kg": predicted_kg,
        "actual_kg": actual_kg,
        "residual_per_day": float(residual_per_day),
        "mean_balance": float(balance.mean()),
    }
