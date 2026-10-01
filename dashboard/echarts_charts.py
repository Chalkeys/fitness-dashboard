"""ECharts option builders for every dashboard chart.

Shares one visual language via `dashboard.theme`: fixed categorical slots,
diverging blue<->red for signed values, recessive grid and axes. Every builder
reads the palette at call time rather than at import, so the same option code
draws the light and the dark board.
"""

from __future__ import annotations

import pandas as pd
from streamlit_echarts import JsCode

from dashboard import data, energy
from dashboard.theme import (
    CAL_CATEGORIES,
    CM_TO_IN,
    FONT_FAMILY,
    KG_TO_LB,
    Palette,
    active,
    classify_training,
)

# Drag pans the chart; the wheel is left to the page so scrolling never snags.
PAN_ZOOM = [{"type": "inside", "zoomOnMouseWheel": False, "moveOnMouseWheel": False}]

_DATE_LABEL = JsCode("function (v) { return v.slice(5); }").js_code


def _text_style(p: Palette) -> dict:
    return {"fontFamily": FONT_FAMILY, "color": p.ink_secondary}


def _value_formatter(unit: str, decimals: int = 0, signed: bool = False) -> str:
    sign = "(v > 0 ? '+' : '') + " if signed else ""
    return JsCode(
        "function (v) {"
        "  if (v == null) { return '-'; }"
        f"  return {sign}v.toFixed({decimals})"
        f"    .replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, ',') + ' {unit}';"
        "}"
    ).js_code


def _tooltip_chrome(p: Palette) -> dict:
    """The floating box itself: a card, not a bordered rectangle.

    ECharts' default is a white box with a 1px grey border, which sits wrong on
    a dark surface and looks dated on a light one. A shadow does the lifting
    instead, and the text takes the palette's ink.
    """
    return {
        "backgroundColor": p.surface,
        "borderWidth": 0,
        "borderRadius": 10,
        "padding": [8, 12, 8, 12],
        "textStyle": {"color": p.ink, "fontSize": 12},
        "extraCssText": f"box-shadow: 0 6px 20px {p.shadow};",
    }


def _base(
    p: Palette,
    *,
    legend: bool = False,
    left: int = 52,
    right: int = 16,
    top: int = 44,
    bottom: int = 32,
) -> dict:
    option = {
        "animationDuration": 500,
        "animationEasing": "cubicOut",
        # The canvas paints its own background: ECharts' default is white, and
        # a white rectangle is the last thing a dark page needs.
        "backgroundColor": p.surface,
        "textStyle": _text_style(p),
        "grid": {"left": left, "right": right, "top": top, "bottom": bottom},
    }
    if legend:
        option["legend"] = {
            "left": 0,
            "top": 0,
            "icon": "roundRect",
            "itemWidth": 10,
            "itemHeight": 10,
            "itemGap": 16,
            "textStyle": {"color": p.ink_secondary, "fontSize": 12},
            "inactiveColor": p.baseline,
        }
    return option


def _date_axis(p: Palette, dates: list[str]) -> dict:
    return {
        "type": "category",
        "data": dates,
        "boundaryGap": False,
        "axisLine": {"lineStyle": {"color": p.baseline}},
        "axisTick": {"show": False},
        "axisLabel": {"color": p.muted, "formatter": _DATE_LABEL},
    }


def _value_axis(p: Palette, name: str | None = None, *, zero: bool = False, **extra) -> dict:
    """A value axis. `zero` anchors it at the baseline, which bars need.

    A line whose values never go near zero is read for its shape, so it may
    start where the data does; a bar is read for its length, and cutting the
    bottom off one makes a 5% difference look like a fivefold one.
    """
    axis = {
        "type": "value",
        "scale": not zero,
        # Dashed gridlines read as scaffolding rather than as data.
        "splitLine": {"lineStyle": {"color": p.grid, "type": "dashed"}},
        "axisLabel": {"color": p.muted},
        "axisLine": {"show": False},
        "axisTick": {"show": False},
    }
    if name:
        axis["name"] = name
        axis["nameGap"] = 8
        axis["nameTextStyle"] = {"color": p.muted, "align": "right"}
    axis.update(extra)
    return axis


def _axis_tooltip(p: Palette, unit: str, decimals: int = 0, signed: bool = False) -> dict:
    return _tooltip_chrome(p) | {
        "trigger": "axis",
        "axisPointer": {"type": "line", "lineStyle": {"color": p.baseline}},
        "valueFormatter": _value_formatter(unit, decimals, signed),
    }


def _bar_tooltip(p: Palette, unit: str, decimals: int = 0, signed: bool = False) -> dict:
    """Bars get a band pointer: the hit target is the column, not a hairline."""
    return _axis_tooltip(p, unit, decimals, signed) | {
        "axisPointer": {
            "type": "shadow",
            "shadowStyle": {"color": _rgba(p.ink, 0.05 if p.mode == "light" else 0.12)},
        }
    }


def _rgba(colour: str, alpha: float) -> str:
    rgb = ", ".join(str(int(colour.lstrip("#")[i : i + 2], 16)) for i in (0, 2, 4))
    return f"rgba({rgb}, {alpha})"


def _gradient(colour: str, top: float = 0.22) -> dict:
    """Vertical fade from the mark's own colour to nothing."""
    return {
        "type": "linear",
        "x": 0,
        "y": 0,
        "x2": 0,
        "y2": 1,
        "colorStops": [
            {"offset": 0, "color": _rgba(colour, top)},
            {"offset": 1, "color": _rgba(colour, 0)},
        ],
    }


def _line(p: Palette, name: str, values: list, colour: str, **extra) -> dict:
    """A trend line: 2.5px, no symbols until hovered, its own colour faded under."""
    series = {
        "name": name,
        "type": "line",
        "data": values,
        "smooth": True,
        "showSymbol": False,
        "symbol": "circle",
        "symbolSize": 8,
        "lineStyle": {"width": 2.5, "color": colour},
        "itemStyle": {"color": colour, "borderColor": p.surface, "borderWidth": 2},
        "emphasis": {"focus": "series", "scale": 1.4},
    }
    series.update(extra)
    return series


def _end_label(p: Palette, unit: str, decimals: int = 0) -> dict:
    """The latest value, written at the end of the line.

    One direct label rather than a number on every point: the last value is
    the one being looked for, and the rest are read off the shape.
    """
    return {
        "show": True,
        "color": p.ink,
        "fontSize": 12,
        "fontWeight": "bold",
        "distance": 6,
        "formatter": JsCode(
            "function (o) {"
            "  if (o.value == null) { return ''; }"
            f"  return o.value.toFixed({decimals}) + ' {unit}';"
            "}"
        ).js_code,
    }


# --- Body ------------------------------------------------------------------


def weight_trend_option(body: pd.DataFrame, imperial: bool = False) -> dict:
    p = active()
    df = body.dropna(subset=["weight_kg"]).copy()
    unit = "lb" if imperial else "kg"
    if imperial:
        df["weight_kg"] = df["weight_kg"] * KG_TO_LB
    df["rolling"] = df["weight_kg"].rolling(7, min_periods=3).mean()

    option = _base(p, legend=True, right=68)
    option |= {
        "tooltip": _axis_tooltip(p, unit, 2),
        "dataZoom": PAN_ZOOM,
        "xAxis": _date_axis(p, df["measured_at"].dt.strftime("%Y-%m-%d").tolist()),
        "yAxis": _value_axis(p, unit),
        "series": [
            {
                "name": "每日称重",
                "type": "scatter",
                "data": df["weight_kg"].round(2).tolist(),
                "symbolSize": 8,
                "itemStyle": {"color": p.baseline, "opacity": 0.9},
                "emphasis": {"focus": "series"},
            },
            _line(
                p,
                "7 日均值",
                [None if pd.isna(v) else round(v, 2) for v in df["rolling"]],
                p.blue,
                lineStyle={"width": 3, "color": p.blue},
                areaStyle={"color": _gradient(p.blue)},
                endLabel=_end_label(p, unit, 1),
                z=3,
            ),
        ],
    }
    return option


def waist_trend_option(body: pd.DataFrame, imperial: bool = False) -> dict:
    p = active()
    df = body.dropna(subset=["waist_cm"]).copy()
    unit = "in" if imperial else "cm"
    if imperial:
        df["waist_cm"] = df["waist_cm"] * CM_TO_IN

    option = _base(p, right=68)
    option |= {
        "tooltip": _axis_tooltip(p, unit, 1),
        "dataZoom": PAN_ZOOM,
        "xAxis": _date_axis(p, df["measured_at"].dt.strftime("%Y-%m-%d").tolist()),
        "yAxis": _value_axis(p, unit),
        "series": [
            _line(
                p,
                "腰围",
                df["waist_cm"].round(2).tolist(),
                p.blue,
                showSymbol=True,
                lineStyle={"width": 3, "color": p.blue},
                areaStyle={"color": _gradient(p.blue)},
                endLabel=_end_label(p, unit, 1),
            )
        ],
    }
    return option


# --- Nutrition -------------------------------------------------------------


def intake_vs_tdee_option(
    daily: pd.DataFrame,
    active_bias: float = 0.0,
    intake_bias: float = 0.0,
    bmr: float = energy.DEFAULT_BMR,
) -> dict:
    """Intake against TDEE, optionally corrected on activity and intake."""
    p = active()
    df = data.fed(daily)
    tdee = energy.corrected_tdee(daily, active_bias, bmr)
    intake = df["calories_intake"] * (1 + intake_bias)
    suffix = "（纠偏）" if (active_bias or intake_bias) else ""

    option = _base(p, legend=True)
    option |= {
        "tooltip": _axis_tooltip(p, "kcal"),
        "dataZoom": PAN_ZOOM,
        "xAxis": _date_axis(p, df["log_date"].dt.strftime("%Y-%m-%d").tolist()),
        "yAxis": _value_axis(p, "kcal"),
        "series": [
            _line(
                p,
                f"TDEE{suffix}",
                tdee.round(0).tolist(),
                p.baseline,
                lineStyle={"width": 2, "color": p.baseline, "type": "dashed"},
            ),
            _line(
                p,
                f"摄入{suffix}",
                intake.round(0).tolist(),
                p.blue,
                lineStyle={"width": 3, "color": p.blue},
                areaStyle={"color": _gradient(p.blue)},
                z=3,
            ),
        ],
    }
    return option


def _balance_bars(p: Palette, values) -> list[dict]:
    return [
        {
            "value": v,
            "itemStyle": {
                "color": p.diverging_pos if v > 0 else p.diverging_neg,
                "borderRadius": [4, 4, 0, 0] if v > 0 else [0, 0, 4, 4],
            },
        }
        for v in values
    ]


def _rolling(series: pd.Series, window: int = 7) -> list:
    rolled = series.rolling(window, min_periods=3).mean()
    return [None if pd.isna(v) else round(v) for v in rolled]


def calorie_balance_option(
    daily: pd.DataFrame,
    active_bias: float = 0.0,
    intake_bias: float = 0.0,
    bmr: float = energy.DEFAULT_BMR,
) -> dict:
    """Daily calorie balance, raw or corrected, with a 7-day mean over it."""
    p = active()
    df = data.fed(daily).copy()
    df["balance"] = energy.corrected_balance(
        daily, active_bias, intake_bias, bmr
    ).round(0)

    option = _base(p, legend=True)
    option |= {
        "tooltip": _bar_tooltip(p, "kcal", signed=True),
        "dataZoom": PAN_ZOOM,
        "xAxis": _date_axis(p, df["log_date"].dt.strftime("%Y-%m-%d").tolist())
        | {"boundaryGap": True},
        "yAxis": _value_axis(p, "kcal"),
        "series": [
            {
                "name": "热量差",
                "type": "bar",
                # Bars colour themselves by sign; without this the legend
                # swatch would take a series colour the chart never uses.
                "color": p.diverging_neg,
                "data": _balance_bars(p, df["balance"]),
                "barMaxWidth": 18,
            },
            _line(p, "7 日均值", _rolling(df["balance"]), p.ink, z=3),
        ],
    }
    return option


def corrected_balance_option(
    daily: pd.DataFrame,
    active_bias: float,
    intake_bias: float,
    bmr: float = energy.DEFAULT_BMR,
) -> dict:
    """Calorie balance after correcting activity expenditure and intake."""
    p = active()
    df = data.fed(daily).copy()
    df["raw"] = df["calories_intake"] - df["tdee"]
    df["corrected"] = energy.corrected_balance(
        daily, active_bias, intake_bias, bmr
    ).round(0)

    option = _base(p, legend=True)
    option |= {
        "tooltip": _bar_tooltip(p, "kcal", signed=True),
        "dataZoom": PAN_ZOOM,
        "xAxis": _date_axis(p, df["log_date"].dt.strftime("%Y-%m-%d").tolist())
        | {"boundaryGap": True},
        "yAxis": _value_axis(p, "kcal"),
        "series": [
            {
                "name": "纠偏后热量差",
                "type": "bar",
                # Bars colour themselves by sign; without this the legend
                # swatch would take a series colour the chart never uses.
                "color": p.diverging_neg,
                "data": _balance_bars(p, df["corrected"]),
                "barMaxWidth": 18,
            },
            _line(p, "纠偏后 7 日均值", _rolling(df["corrected"]), p.ink, z=3),
            _line(
                p,
                "原始 7 日均值",
                _rolling(df["raw"]),
                p.baseline,
                lineStyle={"width": 2, "color": p.baseline, "type": "dashed"},
                z=2,
            ),
        ],
    }
    return option


def macro_stack_option(daily: pd.DataFrame) -> dict:
    p = active()
    stack = [("protein_g", "蛋白质", p.blue), ("net_carbs_g", "净碳水", p.amber), ("fat_g", "脂肪", p.teal)]
    # A 2px gap in the surface colour separates the stacked segments — but the
    # border it is drawn with runs round all four sides, so on a 90-day window,
    # where a column is about 8px wide, it eats the column from both sides as
    # well. Past that many days the colours have to carry the split alone.
    gap = 2 if len(daily) <= 45 else 0
    series = []
    for index, (col, label, colour) in enumerate(stack):
        series.append(
            {
                "name": label,
                "type": "bar",
                "stack": "macros",
                "data": daily[col].round(0).tolist(),
                "barMaxWidth": 18,
                "itemStyle": {
                    "color": colour,
                    "borderColor": p.surface,
                    "borderWidth": gap,
                    # A rounded cap on the segment that ends the column.
                    "borderRadius": [4, 4, 0, 0] if index == len(stack) - 1 else 0,
                },
                "emphasis": {"focus": "series"},
            }
        )

    option = _base(p, legend=True)
    option |= {
        "tooltip": _bar_tooltip(p, "g"),
        "dataZoom": PAN_ZOOM,
        "xAxis": _date_axis(p, daily["log_date"].dt.strftime("%Y-%m-%d").tolist())
        | {"boundaryGap": True},
        "yAxis": _value_axis(p, "g", zero=True),
        "series": series,
    }
    return option


def protein_trend_option(daily: pd.DataFrame) -> dict:
    p = active()
    option = _base(p, right=64)
    option |= {
        "tooltip": _axis_tooltip(p, "g"),
        "dataZoom": PAN_ZOOM,
        "xAxis": _date_axis(p, daily["log_date"].dt.strftime("%Y-%m-%d").tolist()),
        "yAxis": _value_axis(p, "g"),
        "series": [
            _line(
                p,
                "蛋白质",
                daily["protein_g"].round(0).tolist(),
                p.blue,
                lineStyle={"width": 3, "color": p.blue},
                areaStyle={"color": _gradient(p.blue)},
                endLabel=_end_label(p, "g"),
            )
        ],
    }
    return option


# --- Training --------------------------------------------------------------


def weekly_tonnage_option(sets: pd.DataFrame, imperial: bool = False) -> dict:
    p = active()
    df = sets.dropna(subset=["weight_kg", "reps"]).copy()
    unit = "lb" if imperial else "kg"
    df["tonnage"] = df["weight_kg"] * df["reps"]
    if imperial:
        df["tonnage"] = df["tonnage"] * KG_TO_LB
    weekly = (
        df.set_index("log_date")
        .resample("W-MON", label="left", closed="left")["tonnage"]
        .sum()
        .reset_index()
    )

    option = _base(p, left=64)
    option |= {
        "tooltip": _bar_tooltip(p, unit),
        "xAxis": _date_axis(p, weekly["log_date"].dt.strftime("%Y-%m-%d").tolist())
        | {"boundaryGap": True},
        "yAxis": _value_axis(p, f"{unit}（重量×次数）", zero=True),
        "series": [
            {
                "name": "周总容量",
                "type": "bar",
                "data": weekly["tonnage"].round(0).tolist(),
                "barMaxWidth": 40,
                "itemStyle": {"color": p.blue, "borderRadius": [4, 4, 0, 0]},
                "emphasis": {"itemStyle": {"color": p.blue, "opacity": 0.85}},
            }
        ],
    }
    return option


def exercise_progression_option(
    sets: pd.DataFrame, exercise: str, imperial: bool = False
) -> dict:
    p = active()
    df = sets[sets["exercise"] == exercise].dropna(subset=["weight_kg", "reps"])
    unit = "lb" if imperial else "kg"
    if df.empty:
        return _base(p) | {"xAxis": _date_axis(p, []), "yAxis": _value_axis(p, unit)}

    top = (
        df.sort_values(["log_date", "weight_kg"])
        .groupby("log_date")
        .last()
        .reset_index()
    )
    weights = top["weight_kg"] * KG_TO_LB if imperial else top["weight_kg"]

    option = _base(p)
    option |= {
        "tooltip": _tooltip_chrome(p)
        | {
            "trigger": "axis",
            "axisPointer": {"type": "line", "lineStyle": {"color": p.baseline}},
            "formatter": JsCode(
                "function (ps) {"
                "  var p = ps[0];"
                f"  return p.axisValue + '<br/>' + p.data.value.toFixed(1) + ' {unit} × '"
                "    + p.data.reps + ' 次';"
                "}"
            ).js_code,
        },
        "dataZoom": PAN_ZOOM,
        "xAxis": _date_axis(p, top["log_date"].dt.strftime("%Y-%m-%d").tolist()),
        "yAxis": _value_axis(p, unit),
        "series": [
            _line(
                p,
                "最重一组",
                [
                    {"value": round(w, 1), "reps": int(r)}
                    for w, r in zip(weights, top["reps"])
                ],
                p.blue,
                showSymbol=True,
                lineStyle={"width": 3, "color": p.blue},
                areaStyle={"color": _gradient(p.blue)},
            )
        ],
    }
    return option


def exercise_panel_option(
    sets: pd.DataFrame, exercise: str, imperial: bool = False
) -> dict:
    """Top set over a volume strip: one exercise, two stacked plots, one x-axis.

    These were one plot with two y-scales, which cannot be read honestly —
    where the line crosses the bars means nothing, and the reader has to be
    told which mark belongs to which side. Splitting them keeps both numbers
    and asks nothing: the strip under the line is session volume on its own
    scale, aligned day for day, and the axis pointer walks both together.
    """
    p = active()
    df = sets[sets["exercise"] == exercise].dropna(subset=["weight_kg", "reps"])
    unit = "lb" if imperial else "kg"
    if df.empty:
        return _base(p) | {"xAxis": _date_axis(p, []), "yAxis": _value_axis(p, unit)}

    factor = KG_TO_LB if imperial else 1.0
    df = df.assign(volume=df["weight_kg"] * df["reps"] * factor)
    top = (
        df.sort_values(["log_date", "weight_kg"]).groupby("log_date").last().reset_index()
    )
    volume = df.groupby("log_date")["volume"].sum().reindex(top["log_date"]).tolist()
    dates = top["log_date"].dt.strftime("%Y-%m-%d").tolist()
    weights = (top["weight_kg"] * factor).round(1)

    compact = {"color": p.muted, "fontSize": 10}
    date_axis = _date_axis(p, dates) | {
        "boundaryGap": True,
        "axisLabel": {**compact, "formatter": _DATE_LABEL},
    }
    return {
        "animationDuration": 500,
        "animationEasing": "cubicOut",
        "backgroundColor": p.surface,
        "textStyle": _text_style(p),
        "title": [
            {
                "text": exercise,
                "left": 0,
                "top": 0,
                "textStyle": {"fontSize": 13, "fontWeight": 600, "color": p.ink},
            },
            # The strip's own caption, over its right end. An axis name would
            # have to share the left margin with the tick labels, and at this
            # size that is exactly where the two collide.
            {
                "text": "容量",
                "right": 16,
                "top": "63%",
                "textStyle": {"fontSize": 10, "fontWeight": "normal", "color": p.muted},
            },
        ],
        # One pointer for both plots: hovering the line highlights the same
        # day's volume bar under it.
        "axisPointer": {"link": [{"xAxisIndex": "all"}], "label": {"show": False}},
        "tooltip": _tooltip_chrome(p)
        | {
            "trigger": "axis",
            "axisPointer": {"type": "line", "lineStyle": {"color": p.baseline}},
            "formatter": JsCode(
                "function (ps) {"
                "  var d = ps[0].axisValue, out = d, seen = {};"
                "  ps.forEach(function (p) {"
                "    if (seen[p.seriesName]) { return; }"
                "    seen[p.seriesName] = 1;"
                "    var v = p.data && p.data.value !== undefined ? p.data.value : p.data;"
                f"    if (p.seriesName === '最重一组') {{"
                f"      out += '<br/>最重一组 ' + v.toFixed(1) + ' {unit}'"
                "        + (p.data.reps ? ' × ' + p.data.reps + ' 次' : '');"
                "    } else {"
                f"      out += '<br/>容量 ' + Math.round(v).toLocaleString() + ' {unit}';"
                "    }"
                "  });"
                "  return out;"
                "}"
            ).js_code,
        },
        # Both grids are placed from the top in percentages, so the strip's
        # caption can be put just above the second one whatever height the
        # panel is given.
        "grid": [
            {"left": 46, "right": 16, "top": 40, "height": "42%"},
            {"left": 46, "right": 16, "top": "70%", "height": "18%"},
        ],
        "xAxis": [
            # The upper plot's dates are read off the strip below it.
            date_axis | {"gridIndex": 0, "axisLabel": {"show": False}},
            date_axis | {"gridIndex": 1},
        ],
        "yAxis": [
            _value_axis(p, f"最重一组 {unit}", gridIndex=0)
            | {
                "nameGap": 10,
                "nameTextStyle": {"color": p.muted, "fontSize": 10, "align": "left"},
                "axisLabel": compact,
            },
            _value_axis(p, zero=True, gridIndex=1)
            | {
                "splitLine": {"show": False},
                "splitNumber": 2,
                "axisLabel": {
                    **compact,
                    "formatter": JsCode(
                        "function (v) { return v >= 1000 ? (v / 1000).toFixed(1) + 'k' : v; }"
                    ).js_code,
                },
            },
        ],
        "series": [
            _line(
                p,
                "最重一组",
                [{"value": w, "reps": int(r)} for w, r in zip(weights, top["reps"])],
                p.blue,
                showSymbol=True,
                symbolSize=7,
                areaStyle={"color": _gradient(p.blue, 0.16)},
                xAxisIndex=0,
                yAxisIndex=0,
                z=3,
            ),
            {
                "name": "容量",
                "type": "bar",
                "xAxisIndex": 1,
                "yAxisIndex": 1,
                "data": [round(v) for v in volume],
                "barMaxWidth": 16,
                "itemStyle": {
                    "color": p.teal,
                    "borderRadius": [3, 3, 0, 0],
                    "opacity": 0.75,
                },
            },
        ],
    }


def muscle_group_sets_option(sets: pd.DataFrame) -> dict:
    p = active()
    counts = sets.dropna(subset=["muscle_group"]).groupby("muscle_group").size()
    counts = counts.sort_values()

    option = _base(p, left=110, top=16, bottom=32)
    option |= {
        "tooltip": _tooltip_chrome(p)
        | {"trigger": "item", "valueFormatter": _value_formatter("组")},
        "xAxis": _value_axis(p, zero=True),
        "yAxis": {
            "type": "category",
            "data": counts.index.tolist(),
            "axisLine": {"show": False},
            "axisTick": {"show": False},
            "axisLabel": {"color": p.ink_secondary},
        },
        "series": [
            {
                "name": "组数",
                "type": "bar",
                "data": counts.values.tolist(),
                "barMaxWidth": 16,
                "itemStyle": {"color": p.blue, "borderRadius": [0, 4, 4, 0]},
                # Every bar is labelled, so the length never has to be measured
                # against the axis.
                "label": {
                    "show": True,
                    "position": "right",
                    "color": p.ink_secondary,
                    "fontSize": 11,
                },
            }
        ],
    }
    return option


def training_calendar_option(daily: pd.DataFrame) -> dict:
    p = active()
    cat_index = {c: i for i, c in enumerate(CAL_CATEGORIES)}

    cells = []
    for _, row in daily.iterrows():
        cat = classify_training(
            row["training_type"], row["is_training_day"], row.get("active_energy", 0.0)
        )
        cells.append(
            {
                "value": [
                    row["log_date"].strftime("%Y-%m-%d"),
                    cat_index[cat],
                    row["training_type"] or cat,
                ],
                "label": {"color": p.cal_label_colors[cat]},
            }
        )

    return {
        "animationDuration": 500,
        "backgroundColor": p.surface,
        "textStyle": _text_style(p),
        "tooltip": _tooltip_chrome(p)
        | {
            "formatter": JsCode(
                "function (p) { return p.value[0] + '<br/>' + p.value[2]; }"
            ).js_code
        },
        "visualMap": {
            "type": "piecewise",
            "dimension": 1,
            "orient": "horizontal",
            "left": 0,
            "top": 0,
            # Seven swatches and their labels have to fit a phone's width in
            # one row, because the legend does not wrap.
            "itemWidth": 12,
            "itemHeight": 12,
            "itemGap": 8,
            "textGap": 5,
            "textStyle": {"color": p.ink_secondary, "fontSize": 11},
            "pieces": [
                {"value": i, "label": c, "color": p.cal_colors[c]}
                for i, c in enumerate(CAL_CATEGORIES)
            ],
        },
        "calendar": {
            "top": 64,
            "left": 44,
            "right": 8,
            "bottom": 8,
            "range": [
                daily["log_date"].min().strftime("%Y-%m-%d"),
                daily["log_date"].max().strftime("%Y-%m-%d"),
            ],
            "cellSize": ["auto", "auto"],
            "splitLine": {"show": False},
            # The gap between cells is the surface showing through.
            "itemStyle": {
                "color": p.page,
                "borderWidth": 3,
                "borderColor": p.surface,
                "borderRadius": 6,
            },
            "dayLabel": {"nameMap": "ZH", "color": p.muted, "firstDay": 1},
            "monthLabel": {"nameMap": "ZH", "color": p.ink_secondary},
            "yearLabel": {"show": False},
        },
        "series": [
            {
                "type": "heatmap",
                "coordinateSystem": "calendar",
                "data": cells,
                "label": {
                    "show": True,
                    # Rest days are labelled too: an unlabelled pale cell is
                    # indistinguishable from a day with no record at all.
                    "formatter": JsCode(
                        "function (p) {"
                        f"  var names = {CAL_CATEGORIES!r};"
                        "  return names[p.value[1]] === '休息' ? '休' : names[p.value[1]];"
                        "}"
                    ).js_code,
                    "fontSize": 10,
                },
                "itemStyle": {"borderRadius": 6},
            }
        ],
    }
