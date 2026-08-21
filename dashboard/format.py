"""Presentation helpers that turn query results into display tables."""

from __future__ import annotations

import numpy as np
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
            has_reps = pd.notna(s["reps"])
            duration = s.get("duration_seconds")

            if pd.notna(s["weight_kg"]) and s["weight_kg"] > 0 and has_reps:
                # Weights logged in pounds land here as long decimals; 0.1 is
                # finer than any plate.
                part = f"{round(s['weight_kg'], 1):g}×{int(s['reps'])}"
            elif has_reps:
                part = f"自重×{int(s['reps'])}"
            elif duration is not None and pd.notna(duration):
                part = f"自重·{int(duration)}秒"
            else:
                part = "—"

            if pd.notna(s["rir"]):
                part += f"(RIR {s['rir']:g})"
            parts.append(part)

        volume = (group["weight_kg"] * group["reps"]).sum()
        muscle = group["muscle_group"].iloc[0]
        rows.append(
            {
                "动作": exercise,
                "肌群": muscle if pd.notna(muscle) else "",
                "组数": len(group),
                "明细": "  ".join(parts),
                f"容量 {weight_unit}": round(volume) if volume else np.nan,
            }
        )
    return pd.DataFrame(rows)
