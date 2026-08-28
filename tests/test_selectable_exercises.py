import pandas as pd
import pytest

from dashboard.data import selectable_exercises

TODAY = pd.Timestamp("2026-08-27")


def _sets(rows, weight_kg=60.0):
    """rows: (exercise, 'YYYY-MM-DD', session_id) per set."""
    return pd.DataFrame(
        [
            {"exercise": e, "log_date": pd.Timestamp(d), "session_id": s, "weight_kg": weight_kg}
            for e, d, s in rows
        ]
    )


def _one_off(name, date, sets=3):
    return [(name, date, f"{name}-1")] * sets


def _regular(name, dates):
    return [(name, d, f"{name}-{i}") for i, d in enumerate(dates)]


def test_stale_and_rare_is_dropped():
    sets = _sets(_one_off("哑铃深蹲", "2026-06-22") + _regular("杠铃卧推", ["2026-08-26"] * 3))
    assert "哑铃深蹲" not in selectable_exercises(sets, today=TODAY)


def test_stale_but_well_recorded_is_kept():
    # Four sessions, last in mid-July: a real lift between blocks, not clutter.
    sets = _sets(_regular("杠铃深蹲", ["2026-06-24", "2026-07-01", "2026-07-08", "2026-07-15"]))
    assert selectable_exercises(sets, today=TODAY) == ["杠铃深蹲"]


def test_rare_but_recent_is_kept():
    # Every movement starts at one session; recency alone earns a place.
    sets = _sets(_one_off("新动作", "2026-08-25"))
    assert selectable_exercises(sets, today=TODAY) == ["新动作"]


def test_rarity_counts_sessions_not_sets():
    # Four sets in one afternoon is one data point, not four.
    sets = _sets(_one_off("哑铃深蹲", "2026-06-22", sets=4))
    assert selectable_exercises(sets, today=TODAY) == []


def test_a_kept_name_survives_the_filter():
    sets = _sets(_one_off("哑铃深蹲", "2026-06-22"))
    assert selectable_exercises(sets, today=TODAY, keep=("哑铃深蹲",)) == ["哑铃深蹲"]


def test_the_month_is_measured_from_today_not_from_the_data():
    sets = _sets(_one_off("哑铃深蹲", "2026-06-22"))
    assert selectable_exercises(sets, today=pd.Timestamp("2026-07-10")) == ["哑铃深蹲"]
    assert selectable_exercises(sets, today=pd.Timestamp("2026-07-23")) == []


def test_order_is_by_how_much_was_recorded():
    sets = _sets(_regular("多", ["2026-08-20"] * 5) + _regular("少", ["2026-08-21"] * 2))
    assert selectable_exercises(sets, today=TODAY) == ["多", "少"]


def test_no_data_is_no_options():
    empty = pd.DataFrame(columns=["exercise", "log_date", "session_id", "weight_kg"])
    assert selectable_exercises(empty) == []


def test_an_exercise_with_no_weight_anywhere_is_not_offered():
    # Yard work carries one set with no weight, reps, time or distance on it,
    # and the panel plots a top set against volume — both of them weight.
    sets = _sets(_regular("庭院劳作", ["2026-08-23"]), weight_kg=None)
    assert selectable_exercises(sets, today=TODAY) == []


def test_cardio_and_bodyweight_work_are_not_offered_either():
    # Brisk walking has time and distance, the decline crunch has reps. Both
    # progress; neither does so on an axis this panel has.
    rows = _regular("快走", ["2026-08-10", "2026-08-13", "2026-08-16"])
    assert selectable_exercises(_sets(rows, weight_kg=None), today=TODAY) == []


def test_a_weightless_pick_is_dropped_even_when_kept():
    # keep exists so a quiet pinned lift stays selectable, not so an empty
    # chart can be pinned.
    sets = _sets(_regular("庭院劳作", ["2026-08-23"]), weight_kg=None)
    assert selectable_exercises(sets, today=TODAY, keep=("庭院劳作",)) == []


def test_one_weighted_set_is_enough_to_qualify():
    rows = _regular("悬挂抬腿", ["2026-08-10", "2026-08-17", "2026-08-24"])
    sets = _sets(rows, weight_kg=None)
    sets.loc[0, "weight_kg"] = 10.0
    assert selectable_exercises(sets, today=TODAY) == ["悬挂抬腿"]
