import pytest

from scripts.sync_xunji_recent import (
    REST_DAY_ACTIVE_KCAL,
    reported_calories,
    resolve_active_energy,
    xunji_active_energy,
)


def _workout(strength=None, cardio=None, tonnage=0.0):
    sets = [{"weight": tonnage, "reps": 1}] if tonnage else []
    return {
        "xunji_strength_kcal": strength,
        "active_energy_kcal": cardio,
        "exercises": [{"sets": sets}],
    }


@pytest.mark.parametrize(
    ("note", "expected"),
    [
        ("calorie:812", 812.0),
        ("calorie: 812.5", 812.5),
        ("腿日 calorie:600 累", 600.0),
        ("", None),
        (None, None),
        ("no figure here", None),
    ],
)
def test_reported_calories_reads_the_note(note, expected):
    assert reported_calories(note) == expected


def test_xunji_figure_adds_lifting_to_cardio():
    assert xunji_active_energy(_workout(strength=572, cardio=260)) == 832.0


def test_xunji_figure_absent_without_a_note():
    assert xunji_active_energy(_workout(cardio=260)) is None
    assert xunji_active_energy(None) is None


def test_hand_entered_value_wins_over_xunji():
    workout = _workout(strength=812, cardio=260)
    assert resolve_active_energy(workout, 832) == (832.0, "measured")


def test_xunji_wins_over_the_volume_model():
    workout = _workout(strength=572, cardio=260, tonnage=20000)
    assert resolve_active_energy(workout, None) == (832.0, "xunji")


def test_volume_model_fills_in_when_xunji_reports_nothing():
    value, source = resolve_active_energy(_workout(tonnage=20000), None)
    assert source == "estimated"
    assert value == pytest.approx(584.0 + 0.01 * 20000)


def test_a_day_without_training_falls_back_to_the_rest_day_constant():
    assert resolve_active_energy(None, None) == (REST_DAY_ACTIVE_KCAL, "estimated")


def test_a_cardio_only_day_adds_neat_to_the_measured_cardio():
    # No lifting means nothing stands in for the day's NEAT, so the rest-day
    # constant carries it and the measured cardio adds on top.
    value, source = resolve_active_energy(_workout(cardio=481), None)
    assert source == "estimated"
    assert value == pytest.approx(REST_DAY_ACTIVE_KCAL + 481)


def test_a_logged_day_with_no_cardio_and_no_lifting_reads_as_rest():
    assert resolve_active_energy(_workout(), None) == (REST_DAY_ACTIVE_KCAL, "estimated")
