import pandas as pd
import pytest

from dashboard.data import selectable_exercises

TODAY = pd.Timestamp("2026-08-27")


def _sets(rows):
    """rows: (exercise, 'YYYY-MM-DD', session_id) per set."""
    return pd.DataFrame(
        [{"exercise": e, "log_date": pd.Timestamp(d), "session_id": s} for e, d, s in rows]
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
    assert selectable_exercises(pd.DataFrame(columns=["exercise", "log_date", "session_id"])) == []
