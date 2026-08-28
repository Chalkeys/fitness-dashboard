import pandas as pd
import pytest

from dashboard.energy import LEAN_GAIN_KG_PER_DAY, target_plan

TODAY = pd.Timestamp("2026-08-28")


def _daily():
    dates = pd.date_range("2026-08-14", "2026-08-27")
    return pd.DataFrame(
        {
            "log_date": dates,
            "tdee": 2600.0,
            "active_energy": 780.0,
            "calories_intake": 2000.0,
        }
    )


def _body(weighed_at="2026-08-27"):
    return pd.DataFrame(
        [
            {
                "measured_at": pd.Timestamp("2026-08-18"),
                "weight_kg": 81.45,
                "body_fat_percentage": 17.1,
            },
            {
                "measured_at": pd.Timestamp(weighed_at),
                "weight_kg": 80.8,
                "body_fat_percentage": None,
            },
        ]
    )


def _plan(horizon=30, weighed_at="2026-08-27"):
    return target_plan(_daily(), _body(weighed_at), 0.15, horizon, today=TODAY)


def test_the_deadline_is_the_horizon_from_today():
    assert _plan(30)["target_date"] == pd.Timestamp("2026-09-27")


def test_a_stale_weigh_in_gives_the_body_longer_than_the_horizon():
    # Weighed yesterday: 30 days of eating ahead, 31 days of change.
    plan = _plan(30, weighed_at="2026-08-27")
    assert plan["days_ahead"] == 31


def test_weighing_in_today_makes_the_two_spans_equal():
    plan = _plan(30, weighed_at="2026-08-28")
    assert plan["days_ahead"] == 30


def test_the_daily_figure_divides_by_the_days_left_to_eat():
    # Not by days_ahead: the elapsed day cannot be eaten through twice.
    plan = _plan(30, weighed_at="2026-08-27")
    lean_energy = LEAN_GAIN_KG_PER_DAY * plan["days_ahead"] * 1800
    stored = plan["fat_change"] * 7700 + lean_energy
    assert plan["balance_per_day"] == pytest.approx(stored / 30)


def test_a_stale_weigh_in_asks_for_slightly_more_each_day():
    # Erring toward a larger deficit is the safe direction.
    assert _plan(30, "2026-08-27")["balance_per_day"] < _plan(30, "2026-08-28")["balance_per_day"]


def test_lean_is_projected_over_the_days_the_body_has():
    plan = _plan(30, weighed_at="2026-08-27")
    assert plan["lean_end"] == pytest.approx(
        plan["lean_now"] + LEAN_GAIN_KG_PER_DAY * plan["days_ahead"]
    )


def test_a_longer_horizon_pushes_the_deadline_out_by_the_same_days():
    assert (_plan(60)["target_date"] - _plan(30)["target_date"]).days == 30


def test_no_scan_means_no_plan():
    body = _body()
    body["body_fat_percentage"] = None
    assert target_plan(_daily(), body, 0.15, 30, today=TODAY) is None
