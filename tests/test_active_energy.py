import pytest

from scripts.sync_xunji_recent import (
    REST_DAY_ACTIVE_KCAL,
    reported_calories,
    resolve_active_energy,
)


def _workout(window=None, cardio=None, tonnage=0.0):
    sets = [{"weight": tonnage, "reps": 1}] if tonnage else []
    return {
        "apple_health_workout_kcal": window,
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


def test_a_hand_entered_value_wins():
    assert resolve_active_energy(_workout(cardio=260), 832) == (832.0, "measured")


def test_the_session_note_is_ignored_however_plausible_it_looks():
    # It reads like Xunji's estimate of the session and is not: on 26 Aug it
    # held 812 while the app showed 572 for the same lift, it is empty on days
    # a model would have priced, and it changed by a kcal overnight. So it is
    # Apple Health's workout window, which is what the hand entries exist to
    # replace.
    workout = _workout(window=761, cardio=0, tonnage=15000)
    value, source = resolve_active_energy(workout, None)
    assert source == "estimated"
    assert value == pytest.approx(584.0 + 0.01 * 15000)


def test_volume_model_fills_in_when_xunji_reports_nothing():
    value, source = resolve_active_energy(_workout(tonnage=20000), None)
    assert source == "estimated"
    assert value == pytest.approx(584.0 + 0.01 * 20000)


def test_a_day_without_training_falls_back_to_the_rest_day_constant():
    assert resolve_active_energy(None, None) == (REST_DAY_ACTIVE_KCAL, "estimated")


def test_a_cardio_only_day_takes_the_larger_of_cardio_and_the_baseline():
    # Not their sum: a whole-day reading already contains the sessions, so
    # adding them overshot by hundreds on the two days that have any.
    value, source = resolve_active_energy(_workout(cardio=907), None)
    assert source == "estimated"
    assert value == pytest.approx(907)


def test_a_quiet_cardio_day_still_gets_the_rest_day_baseline():
    value, _ = resolve_active_energy(_workout(cardio=120), None)
    assert value == pytest.approx(REST_DAY_ACTIVE_KCAL)


def test_a_logged_day_with_no_cardio_and_no_lifting_reads_as_rest():
    assert resolve_active_energy(_workout(), None) == (REST_DAY_ACTIVE_KCAL, "estimated")


def _train(title, movements, note="", start=0, end=60000):
    return {"title": title, "note": note, "start": start, "end": end, "movements": movements}


def _movement(name, count=1):
    return {"name": name, "sets": [{"weight": "", "reps": "", "unit": ""} for _ in range(count)]}


def test_a_movement_in_two_sessions_becomes_one_entry():
    # 30 Aug: two Apple Health sessions each carrying one
    # TraditionalStrengthTraining set. Kept apart they repeat set_number 1 for
    # the same exercise and break the import's uniqueness key.
    from scripts.sync_xunji_recent import _workout

    workout = _workout(
        [
            _train("传统力量训练", [_movement("TraditionalStrengthTraining")]),
            _train("功能性力量训练", [_movement("TraditionalStrengthTraining")]),
        ],
        70,
    )
    names = [e["exercise_name"] for e in workout["exercises"]]
    assert names == ["TraditionalStrengthTraining"]
    assert [s["set_number"] for s in workout["exercises"][0]["sets"]] == [1, 2]


def test_distinct_movements_stay_apart_and_keep_their_order():
    from scripts.sync_xunji_recent import _workout

    workout = _workout(
        [_train("P1-腿", [_movement("杠铃深蹲", 3), _movement("坐姿腿弯举", 2)])], 70
    )
    assert [e["exercise_name"] for e in workout["exercises"]] == ["杠铃深蹲", "坐姿腿弯举"]
    assert [len(e["sets"]) for e in workout["exercises"]] == [3, 2]


def _cardio_set(kcal):
    return {"weight": "", "reps": "", "unit": "", "metrics": {"calories": str(kcal)}}


def test_cardio_is_recognised_by_its_data_not_its_name():
    # 7 Sep: a walk of 47 kcal and an "AppleHealthWorkout" of 81. Matching the
    # name "Walking" took the first and filed the second as a lift.
    from scripts.sync_xunji_recent import _workout

    workout = _workout(
        [
            _train("步行", [{"name": "Walking", "sets": [_cardio_set(47)]}]),
            _train("其他", [{"name": "AppleHealthWorkout", "sets": [_cardio_set(81)]}]),
        ],
        78,
    )
    assert workout["active_energy_kcal"] == 128.0
    assert workout["exercises"] == []


def test_a_lift_that_carries_calories_is_still_a_lift():
    from scripts.sync_xunji_recent import _workout

    loaded = {"weight": "100", "reps": "5", "unit": "kg", "metrics": {"calories": "9"}}
    workout = _workout([_train("P1-腿", [{"name": "杠铃深蹲", "sets": [loaded]}])], 78)
    assert [e["exercise_name"] for e in workout["exercises"]] == ["杠铃深蹲"]
    assert not workout["active_energy_kcal"]
