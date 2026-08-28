"""Cached read-only queries against the fitness SQLite database."""

from __future__ import annotations

import os
import sqlite3

import pandas as pd
import streamlit as st

DB_PATH = os.environ.get("FITNESS_DB", "fitness.db")

CACHE_TTL = 300


def _connect() -> sqlite3.Connection:
    # Read-only URI so the dashboard can never mutate the database.
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def _read_sql(query: str, params: tuple = ()) -> pd.DataFrame:
    with _connect() as con:
        return pd.read_sql_query(query, con, params=params)


@st.cache_data(ttl=CACHE_TTL)
def load_daily_logs() -> pd.DataFrame:
    df = _read_sql(
        """
        SELECT log_date, day_number, is_training_day, training_type,
               calories_intake, tdee, calorie_balance,
               protein_g, total_carbs_g, fiber_g, net_carbs_g, fat_g,
               active_energy, notes
        FROM daily_logs
        ORDER BY log_date
        """
    )
    df["log_date"] = pd.to_datetime(df["log_date"])
    return df


@st.cache_data(ttl=CACHE_TTL)
def load_body_measurements() -> pd.DataFrame:
    df = _read_sql(
        """
        SELECT measured_at, weight_kg, body_fat_percentage, resting_heart_rate,
               neck_cm, shoulder_cm, chest_cm, waist_cm, hip_cm,
               arm_left_cm, arm_right_cm, forearm_left_cm, forearm_right_cm,
               leg_left_cm, leg_right_cm, calf_left_cm, calf_right_cm
        FROM body_measurements
        WHERE measured_at IS NOT NULL
        ORDER BY measured_at
        """
    )
    df["measured_at"] = pd.to_datetime(df["measured_at"])
    return df


@st.cache_data(ttl=CACHE_TTL)
def load_nutrition_entries() -> pd.DataFrame:
    df = _read_sql(
        """
        SELECT n.log_date, n.meal_type, f.food_name, f.brand,
               n.amount, n.unit, n.calories, n.protein_g, n.carbs_g,
               n.fiber_g, n.net_carbs_g, n.fat_g
        FROM nutrition_entries n
        JOIN foods f ON f.id = n.food_id
        ORDER BY n.log_date, n.id
        """
    )
    df["log_date"] = pd.to_datetime(df["log_date"])
    return df


@st.cache_data(ttl=CACHE_TTL)
def load_workout_sessions() -> pd.DataFrame:
    df = _read_sql(
        """
        SELECT w.id, d.log_date, w.name, w.workout_type,
               w.duration_minutes, w.active_energy_kcal
        FROM workout_sessions w
        JOIN daily_logs d ON d.id = w.daily_log_id
        ORDER BY d.log_date
        """
    )
    df["log_date"] = pd.to_datetime(df["log_date"])
    return df


@st.cache_data(ttl=CACHE_TTL)
def load_exercise_sets() -> pd.DataFrame:
    df = _read_sql(
        """
        SELECT d.log_date, w.id AS session_id, e.name AS exercise,
               e.category, e.muscle_group,
               s.set_number, s.reps, s.rir, s.weight_kg,
               s.distance_meters, s.duration_seconds
        FROM exercise_sets s
        JOIN workout_sessions w ON w.id = s.workout_session_id
        JOIN daily_logs d ON d.id = w.daily_log_id
        JOIN exercises e ON e.id = s.exercise_id
        ORDER BY d.log_date, w.id, s.set_number
        """
    )
    df["log_date"] = pd.to_datetime(df["log_date"])
    return df


STALE_AFTER = pd.DateOffset(months=1)
RARE_BELOW_SESSIONS = 3


def selectable_exercises(
    sets: pd.DataFrame,
    today: pd.Timestamp | None = None,
    keep: tuple[str, ...] = (),
) -> list[str]:
    """Exercise names worth offering in a picker, most-recorded first.

    A name drops out only when it is both stale and rare — nothing logged in
    the last month and fewer than three sessions ever. Either test alone would
    take too much: a staple sits out a month during a deload, and every
    movement starts at one session. Together they describe something tried
    once and dropped, which in a picker is only clutter to scroll past.

    Sessions, not sets, decide rarity. One afternoon of an exercise is one
    data point however many sets it ran to, and counting sets would keep a
    single four-set outing while dropping a two-set one.

    The month is measured from today rather than from the last day in the
    data, so the list thins out on its own between imports. Anything in
    ``keep`` survives regardless, so a pinned exercise that has gone quiet
    stays in the options that its own panel is drawn from.
    """
    if sets.empty:
        return []
    by_exercise = sets.groupby("exercise")
    order = by_exercise.size().sort_values(ascending=False).index
    sessions = by_exercise["session_id"].nunique()
    last_seen = by_exercise["log_date"].max()
    cutoff = (today or pd.Timestamp.today()).normalize() - STALE_AFTER
    kept = set(keep)
    return [
        name
        for name in order
        if name in kept
        or not (last_seen[name] < cutoff and sessions[name] < RARE_BELOW_SESSIONS)
    ]


def filter_by_range(df: pd.DataFrame, date_col: str, days: int | None) -> pd.DataFrame:
    """Keep the trailing `days` window; None means the full history."""
    if days is None or df.empty:
        return df
    cutoff = df[date_col].max() - pd.Timedelta(days=days - 1)
    return df[df[date_col] >= cutoff]
