"""Energy-balance arithmetic, including bias-corrected calorie balance.

Logged TDEE and logged intake are both estimates: activity trackers tend to
overstate expenditure, and hand-logged food tends to understate intake. Each
gets a bias factor so the balance can be re-scaled and checked against measured
weight change.
"""

from __future__ import annotations

import pandas as pd

# Energy density of body-mass change; the usual dietetics approximation for
# fat tissue. Real change mixes fat, glycogen, and water, so treat any
# prediction from it as a trend, not a scale reading.
KCAL_PER_KG = 7700.0


def corrected_balance(
    daily: pd.DataFrame, tdee_bias: float = 0.0, intake_bias: float = 0.0
) -> pd.Series:
    """Daily balance after scaling both sides by their bias factors.

    Biases are fractions: -0.1 shrinks that side by 10%.
    """
    fed = daily[daily["tdee"] > 0]
    return fed["calories_intake"] * (1 + intake_bias) - fed["tdee"] * (1 + tdee_bias)


def calibration(
    daily: pd.DataFrame,
    body: pd.DataFrame,
    tdee_bias: float = 0.0,
    intake_bias: float = 0.0,
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

    balance = corrected_balance(fed, tdee_bias, intake_bias)
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
