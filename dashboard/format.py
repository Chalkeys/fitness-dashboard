"""Presentation helpers that turn query results into display tables."""

from __future__ import annotations

import pandas as pd


def summarize_sets(session_sets: pd.DataFrame, weight_unit: str = "kg") -> pd.DataFrame:
    """One row per exercise: its sets collapsed into a `weight×reps` list.

    Sets are read in the order given, so callers sort by set number first.
    Weights are taken as already converted to `weight_unit`.
    """
    rows = []
    for exercise, group in session_sets.groupby("exercise", sort=False):
        parts = []
        for _, s in group.iterrows():
            reps = int(s["reps"]) if pd.notna(s["reps"]) else "—"
            if pd.notna(s["weight_kg"]) and s["weight_kg"] > 0:
                # Weights logged in pounds land here as long decimals; 0.1 is
                # finer than any plate.
                part = f"{round(s['weight_kg'], 1):g}×{reps}"
            else:
                part = f"自重×{reps}"
            if pd.notna(s["rir"]):
                part += f"(RIR {s['rir']:g})"
            parts.append(part)

        volume = (group["weight_kg"] * group["reps"]).sum()
        rows.append(
            {
                "动作": exercise,
                "肌群": group["muscle_group"].iloc[0],
                "组数": len(group),
                "明细": "  ".join(parts),
                f"容量 {weight_unit}": round(volume) if volume else None,
            }
        )
    return pd.DataFrame(rows)
