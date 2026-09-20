"""The two palettes, and the charts following whichever one is active."""

import pandas as pd
import pytest

from dashboard import notes, theme


@pytest.fixture(autouse=True)
def _light_by_default():
    """Every test starts in light and leaves the next one there too."""
    theme.set_mode("light")
    yield
    theme.set_mode("light")


def _charts():
    """The option builders, or a skip.

    `streamlit_echarts` registers its component at import time, and that
    registration needs a Streamlit runtime to resolve the component's own
    files. Under a bare pytest there is none, which is why nothing else in
    this suite imports the module either.
    """
    try:
        from dashboard import echarts_charts
    except Exception as exc:  # pragma: no cover - depends on the runtime
        pytest.skip(f"streamlit-echarts needs a Streamlit runtime: {exc}")
    return echarts_charts


def _sets():
    return pd.DataFrame(
        [
            {
                "exercise": "杠铃卧推",
                "log_date": pd.Timestamp(day),
                "session_id": f"s{i}",
                "weight_kg": 60.0 + i,
                "reps": 5,
                "muscle_group": "胸",
            }
            for i, day in enumerate(["2026-09-01", "2026-09-04", "2026-09-08"])
        ]
    )


def test_an_unknown_mode_is_light():
    assert theme.set_mode(None) == "light"
    assert theme.set_mode("Solarized") == "light"
    assert theme.active() is theme.LIGHT


def test_dark_is_selected_not_flipped():
    theme.set_mode("dark")
    assert theme.active() is theme.DARK
    # The same hues at different steps: a dark palette that reused the light
    # ones would fail its own contrast check against the dark surface.
    assert theme.DARK.carriers != theme.LIGHT.carriers


def test_every_dark_carrier_stays_readable_on_its_surface():
    # 3:1 is the mark floor. The light set sits under it on three slots and is
    # allowed to, because every fill it colours is labelled; the dark set was
    # stepped to clear it outright, and should stay that way.
    for colour in theme.DARK.carriers:
        assert theme.contrast(colour, theme.DARK.surface) >= 3.0


def test_calendar_labels_are_readable_on_their_cells():
    for palette in (theme.LIGHT, theme.DARK):
        for name, fill in palette.cal_colors.items():
            assert theme.contrast(palette.cal_label_colors[name], fill) >= 3.0


def test_a_chart_takes_the_active_palette():
    ec = _charts()
    light = ec.weekly_tonnage_option(_sets())
    theme.set_mode("dark")
    dark = ec.weekly_tonnage_option(_sets())

    assert light["backgroundColor"] == theme.LIGHT.surface
    assert dark["backgroundColor"] == theme.DARK.surface
    assert light["series"][0]["itemStyle"]["color"] == theme.LIGHT.blue
    assert dark["series"][0]["itemStyle"]["color"] == theme.DARK.blue


def test_bars_start_at_the_baseline():
    ec = _charts()
    assert ec.weekly_tonnage_option(_sets())["yAxis"]["scale"] is False


def test_notes_annotate_a_chart_that_has_two_plots():
    """The exercise panel carries one x-axis per plot; marks go on the first."""
    dates = ["2026-09-01", "2026-09-04", "2026-09-08"]
    option = {
        "xAxis": [{"data": list(dates)}, {"data": list(dates)}],
        "series": [{"name": "最重一组", "data": [1, 2, 3]}],
    }
    marked = notes.annotate(
        option, {"2026-09-04": {"text": "换握距", "pinned": True, "label": "换握距"}}
    )
    assert [m["name"] for m in marked["series"][0]["markLine"]["data"]] == ["2026-09-04"]
