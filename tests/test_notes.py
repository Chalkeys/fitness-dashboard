import json
from pathlib import Path

import pytest

from dashboard import notes


@pytest.fixture()
def store(tmp_path, monkeypatch):
    path = tmp_path / "training_notes.json"
    monkeypatch.setattr(notes, "NOTES_PATH", path)
    return path


def _option(dates):
    return {"xAxis": {"data": list(dates)}, "series": [{"name": "体重", "data": [1] * len(dates)}]}


def test_a_note_survives_a_round_trip(store):
    assert notes.put("2026-09-01", "硬拉换六角杠", pinned=True, label="换硬拉")
    assert notes.load() == {
        "2026-09-01": {"text": "硬拉换六角杠", "pinned": True, "label": "换硬拉"}
    }


def test_an_empty_text_deletes_the_day(store):
    notes.put("2026-09-01", "写了点什么")
    notes.put("2026-09-01", "   ")
    assert notes.load() == {}


def test_the_label_falls_back_to_the_start_of_the_text(store):
    notes.put("2026-09-01", "换了训练计划，改成上下肢分化")
    assert notes.load()["2026-09-01"]["label"] == "换了训练计划，改成上下肢"


def test_a_missing_file_is_not_an_error(store):
    assert notes.load() == {}


def test_junk_entries_are_dropped_not_raised(store):
    store.write_text(
        json.dumps({"days": {"2026-09-01": {"text": "好"}, "not-a-date": {"text": "坏"},
                             "2026-09-02": 17, "2026-09-03": {"text": "  "}}}),
        encoding="utf-8",
    )
    assert list(notes.load()) == ["2026-09-01"]


def test_a_bare_string_is_read_as_a_note(store):
    # Hand-editing the file, the obvious thing to type is just the text.
    store.write_text(json.dumps({"days": {"2026-09-01": "腰有点酸"}}), encoding="utf-8")
    assert notes.load()["2026-09-01"]["text"] == "腰有点酸"


def test_a_pinned_note_is_drawn_with_its_label_showing():
    option = notes.annotate(
        _option(["2026-08-31", "2026-09-01"]),
        {"2026-09-01": {"text": "硬拉换六角杠", "pinned": True, "label": "换硬拉"}},
    )
    (line,) = option["series"][0]["markLine"]["data"]
    assert line["xAxis"] == "2026-09-01"
    assert line["label"]["show"] is True
    assert line["label"]["formatter"] == "换硬拉"


def test_an_ordinary_note_keeps_its_label_for_the_hover():
    option = notes.annotate(
        _option(["2026-09-01"]),
        {"2026-09-01": {"text": "睡得不好", "pinned": False, "label": "睡得不好"}},
    )
    (line,) = option["series"][0]["markLine"]["data"]
    assert line["label"]["show"] is False
    assert line["emphasis"]["label"]["formatter"] == "睡得不好"


def test_a_note_outside_the_axis_is_not_drawn():
    # Otherwise ECharts pins an unmatched category to one end of the axis.
    option = notes.annotate(
        _option(["2026-09-01"]), {"2026-07-01": {"text": "早的", "pinned": True, "label": "早"}}
    )
    assert "markLine" not in option["series"][0]


def test_annotating_leaves_the_original_option_alone():
    original = _option(["2026-09-01"])
    notes.annotate(original, {"2026-09-01": {"text": "x", "pinned": True, "label": "x"}})
    assert "markLine" not in original["series"][0]


def test_a_chart_with_no_series_is_returned_untouched():
    assert notes.annotate({"xAxis": {"data": ["2026-09-01"]}}, {"2026-09-01": {"text": "x"}}) == {
        "xAxis": {"data": ["2026-09-01"]}
    }


def test_a_note_snaps_to_the_nearest_day_the_axis_holds():
    # Body measurements are days apart; an exact match would drop the note.
    option = notes.annotate(
        _option(["2026-08-15", "2026-08-20", "2026-08-25"]),
        {"2026-08-18": {"text": "DEXA", "pinned": True, "label": "DEXA"}},
    )
    (line,) = option["series"][0]["markLine"]["data"]
    assert line["xAxis"] == "2026-08-20"


def test_a_note_past_either_end_is_still_dropped():
    option = notes.annotate(
        _option(["2026-08-15", "2026-08-20"]),
        {"2026-09-30": {"text": "later", "pinned": True, "label": "l"},
         "2026-01-01": {"text": "earlier", "pinned": True, "label": "e"}},
    )
    assert "markLine" not in option["series"][0]


def test_labels_are_told_not_to_run_along_the_line():
    option = notes.annotate(
        _option(["2026-09-01"]), {"2026-09-01": {"text": "x", "pinned": True, "label": "x"}}
    )
    (line,) = option["series"][0]["markLine"]["data"]
    assert line["label"]["rotate"] == 0


def test_a_milestone_line_stays_out_of_the_way():
    # It annotates someone else's data; at full strength it cuts the series.
    option = notes.annotate(
        _option(["2026-09-01"]),
        {"2026-09-01": {"text": "x", "pinned": True, "label": "x"}},
    )
    (line,) = option["series"][0]["markLine"]["data"]
    assert line["lineStyle"]["opacity"] == notes.PINNED_OPACITY
    assert notes.ORDINARY_OPACITY < notes.PINNED_OPACITY < 0.6
