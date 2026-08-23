"""ECharts option builders for every dashboard chart.

Shares one visual language via `dashboard.theme`: fixed categorical slots,
diverging blue<->red for signed values, recessive grid and axes.
"""

from __future__ import annotations

import pandas as pd
from streamlit_echarts import JsCode

from dashboard import energy
from dashboard.theme import (
    TEAL,
    BASELINE,
    BLUE,
    CAL_CATEGORIES,
    CAL_COLORS,
    CAL_LABEL_COLORS,
    CM_TO_IN,
    DIVERGING_NEG,
    DIVERGING_POS,
    FONT_FAMILY,
    GRID,
    INK,
    INK_SECONDARY,
    KG_TO_LB,
    MUTED,
    AMBER,
    PAGE,
    classify_training,
)

TEXT_STYLE = {"fontFamily": FONT_FAMILY, "color": INK_SECONDARY}

# Drag pans the chart; the wheel is left to the page so scrolling never snags.
PAN_ZOOM = [{"type": "inside", "zoomOnMouseWheel": False, "moveOnMouseWheel": False}]

_DATE_LABEL = JsCode("function (v) { return v.slice(5); }").js_code


def _value_formatter(unit: str, decimals: int = 0, signed: bool = False) -> str:
    sign = "(v > 0 ? '+' : '') + " if signed else ""
    return JsCode(
        "function (v) {"
        "  if (v == null) { return '-'; }"
        f"  return {sign}v.toFixed({decimals})"
        f"    .replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, ',') + ' {unit}';"
        "}"
    ).js_code


def _base(
    *,
    legend: bool = False,
    left: int = 52,
    top: int = 44,
    bottom: int = 32,
) -> dict:
    option = {
        "animationDuration": 600,
        "textStyle": TEXT_STYLE,
        "grid": {"left": left, "right": 16, "top": top, "bottom": bottom},
    }
    if legend:
        option["legend"] = {
            "left": 0,
            "top": 0,
            "icon": "circle",
            "itemGap": 16,
            "textStyle": {"color": INK_SECONDARY},
        }
    return option


def _date_axis(dates: list[str]) -> dict:
    return {
        "type": "category",
        "data": dates,
        "boundaryGap": False,
        "axisLine": {"lineStyle": {"color": BASELINE}},
        "axisTick": {"show": False},
        "axisLabel": {"color": MUTED, "formatter": _DATE_LABEL},
    }


def _value_axis(name: str | None = None, **extra) -> dict:
    axis = {
        "type": "value",
        "scale": True,
        "splitLine": {"lineStyle": {"color": GRID}},
        "axisLabel": {"color": MUTED},
        "axisLine": {"show": False},
        "axisTick": {"show": False},
    }
    if name:
        axis["name"] = name
        axis["nameGap"] = 8
        axis["nameTextStyle"] = {"color": MUTED, "align": "right"}
    axis.update(extra)
    return axis


def _axis_tooltip(unit: str, decimals: int = 0, signed: bool = False) -> dict:
    return {
        "trigger": "axis",
        "axisPointer": {"type": "line", "lineStyle": {"color": BASELINE}},
        "valueFormatter": _value_formatter(unit, decimals, signed),
    }


def _gradient(colour: str, top: float = 0.22) -> dict:
    """Vertical fade from the mark's own colour to nothing."""
    rgb = ", ".join(str(int(colour.lstrip("#")[i : i + 2], 16)) for i in (0, 2, 4))
    return {
        "type": "linear",
        "x": 0,
        "y": 0,
        "x2": 0,
        "y2": 1,
        "colorStops": [
            {"offset": 0, "color": f"rgba({rgb}, {top})"},
            {"offset": 1, "color": f"rgba({rgb}, 0)"},
        ],
    }


# --- Body ------------------------------------------------------------------


def weight_trend_option(body: pd.DataFrame, imperial: bool = False) -> dict:
    df = body.dropna(subset=["weight_kg"]).copy()
    unit = "lb" if imperial else "kg"
    if imperial:
        df["weight_kg"] = df["weight_kg"] * KG_TO_LB
    df["rolling"] = df["weight_kg"].rolling(7, min_periods=3).mean()

    option = _base(legend=True)
    option |= {
        "tooltip": _axis_tooltip(unit, 2),
        "dataZoom": PAN_ZOOM,
        "xAxis": _date_axis(df["measured_at"].dt.strftime("%Y-%m-%d").tolist()),
        "yAxis": _value_axis(unit),
        "series": [
            {
                "name": "每日称重",
                "type": "scatter",
                "data": df["weight_kg"].round(2).tolist(),
                "symbolSize": 7,
                "itemStyle": {"color": BASELINE},
            },
            {
                "name": "7 日均值",
                "type": "line",
                "data": [None if pd.isna(v) else round(v, 2) for v in df["rolling"]],
                "smooth": True,
                "showSymbol": False,
                "lineStyle": {"width": 3, "color": BLUE},
                "itemStyle": {"color": BLUE},
                "areaStyle": {"color": _gradient(BLUE)},
            },
        ],
    }
    return option


def waist_trend_option(body: pd.DataFrame, imperial: bool = False) -> dict:
    df = body.dropna(subset=["waist_cm"]).copy()
    unit = "in" if imperial else "cm"
    if imperial:
        df["waist_cm"] = df["waist_cm"] * CM_TO_IN

    option = _base()
    option |= {
        "tooltip": _axis_tooltip(unit, 1),
        "dataZoom": PAN_ZOOM,
        "xAxis": _date_axis(df["measured_at"].dt.strftime("%Y-%m-%d").tolist()),
        "yAxis": _value_axis(unit),
        "series": [
            {
                "name": "腰围",
                "type": "line",
                "data": df["waist_cm"].round(2).tolist(),
                "smooth": True,
                "symbolSize": 7,
                "lineStyle": {"width": 3, "color": BLUE},
                "itemStyle": {"color": BLUE},
                "areaStyle": {"color": _gradient(BLUE)},
            }
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
    df = daily[daily["tdee"] > 0]
    tdee = energy.corrected_tdee(daily, active_bias, bmr)
    intake = df["calories_intake"] * (1 + intake_bias)
    suffix = "（纠偏）" if (active_bias or intake_bias) else ""

    option = _base(legend=True)
    option |= {
        "tooltip": _axis_tooltip("kcal"),
        "dataZoom": PAN_ZOOM,
        "xAxis": _date_axis(df["log_date"].dt.strftime("%Y-%m-%d").tolist()),
        "yAxis": _value_axis("kcal"),
        "series": [
            {
                "name": f"TDEE{suffix}",
                "type": "line",
                "data": tdee.round(0).tolist(),
                "smooth": True,
                "showSymbol": False,
                "lineStyle": {"width": 2, "color": BASELINE, "type": "dashed"},
                "itemStyle": {"color": BASELINE},
            },
            {
                "name": f"摄入{suffix}",
                "type": "line",
                "data": intake.round(0).tolist(),
                "smooth": True,
                "showSymbol": False,
                "lineStyle": {"width": 3, "color": BLUE},
                "itemStyle": {"color": BLUE},
                "areaStyle": {"color": _gradient(BLUE)},
            },
        ],
    }
    return option


def _balance_bars(values) -> list[dict]:
    return [
        {
            "value": v,
            "itemStyle": {
                "color": DIVERGING_POS if v > 0 else DIVERGING_NEG,
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
    df = daily[daily["tdee"] > 0].copy()
    df["balance"] = energy.corrected_balance(
        daily, active_bias, intake_bias, bmr
    ).round(0)

    option = _base(legend=True)
    option |= {
        "tooltip": _axis_tooltip("kcal", signed=True),
        "dataZoom": PAN_ZOOM,
        "xAxis": _date_axis(df["log_date"].dt.strftime("%Y-%m-%d").tolist())
        | {"boundaryGap": True},
        "yAxis": _value_axis("kcal"),
        "series": [
            {
                "name": "热量差",
                "type": "bar",
                "data": _balance_bars(df["balance"]),
                "barMaxWidth": 18,
            },
            {
                "name": "7 日均值",
                "type": "line",
                "data": _rolling(df["balance"]),
                "smooth": True,
                "showSymbol": False,
                "lineStyle": {"width": 2.5, "color": INK},
                "itemStyle": {"color": INK},
                "z": 3,
            },
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
    df = daily[daily["tdee"] > 0].copy()
    df["raw"] = df["calories_intake"] - df["tdee"]
    df["corrected"] = energy.corrected_balance(
        daily, active_bias, intake_bias, bmr
    ).round(0)

    option = _base(legend=True)
    option |= {
        "tooltip": _axis_tooltip("kcal", signed=True),
        "dataZoom": PAN_ZOOM,
        "xAxis": _date_axis(df["log_date"].dt.strftime("%Y-%m-%d").tolist())
        | {"boundaryGap": True},
        "yAxis": _value_axis("kcal"),
        "series": [
            {
                "name": "纠偏后热量差",
                "type": "bar",
                "data": _balance_bars(df["corrected"]),
                "barMaxWidth": 18,
            },
            {
                "name": "纠偏后 7 日均值",
                "type": "line",
                "data": _rolling(df["corrected"]),
                "smooth": True,
                "showSymbol": False,
                "lineStyle": {"width": 2.5, "color": INK},
                "itemStyle": {"color": INK},
                "z": 3,
            },
            {
                "name": "原始 7 日均值",
                "type": "line",
                "data": _rolling(df["raw"]),
                "smooth": True,
                "showSymbol": False,
                "lineStyle": {"width": 2, "color": BASELINE, "type": "dashed"},
                "itemStyle": {"color": BASELINE},
                "z": 2,
            },
        ],
    }
    return option


def macro_stack_option(daily: pd.DataFrame) -> dict:
    series = []
    for col, label, color in [
        ("protein_g", "蛋白质", BLUE),
        ("net_carbs_g", "净碳水", AMBER),
        ("fat_g", "脂肪", TEAL),
    ]:
        series.append(
            {
                "name": label,
                "type": "bar",
                "stack": "macros",
                "data": daily[col].round(0).tolist(),
                "barMaxWidth": 18,
                "itemStyle": {
                    "color": color,
                    "borderColor": PAGE,
                    "borderWidth": 1.5,
                },
            }
        )

    option = _base(legend=True)
    option |= {
        "tooltip": _axis_tooltip("g"),
        "dataZoom": PAN_ZOOM,
        "xAxis": _date_axis(daily["log_date"].dt.strftime("%Y-%m-%d").tolist())
        | {"boundaryGap": True},
        "yAxis": _value_axis("g"),
        "series": series,
    }
    return option


def protein_trend_option(daily: pd.DataFrame) -> dict:
    option = _base()
    option |= {
        "tooltip": _axis_tooltip("g"),
        "dataZoom": PAN_ZOOM,
        "xAxis": _date_axis(daily["log_date"].dt.strftime("%Y-%m-%d").tolist()),
        "yAxis": _value_axis("g"),
        "series": [
            {
                "name": "蛋白质",
                "type": "line",
                "data": daily["protein_g"].round(0).tolist(),
                "smooth": True,
                "showSymbol": False,
                "lineStyle": {"width": 3, "color": BLUE},
                "itemStyle": {"color": BLUE},
                "areaStyle": {"color": _gradient(BLUE)},
            }
        ],
    }
    return option


# --- Training --------------------------------------------------------------


def weekly_tonnage_option(sets: pd.DataFrame, imperial: bool = False) -> dict:
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

    option = _base(left=64)
    option |= {
        "tooltip": _axis_tooltip(unit),
        "xAxis": _date_axis(weekly["log_date"].dt.strftime("%Y-%m-%d").tolist())
        | {"boundaryGap": True},
        "yAxis": _value_axis(f"{unit}（重量×次数）"),
        "series": [
            {
                "name": "周总容量",
                "type": "bar",
                "data": weekly["tonnage"].round(0).tolist(),
                "barMaxWidth": 40,
                "itemStyle": {"color": BLUE, "borderRadius": [4, 4, 0, 0]},
            }
        ],
    }
    return option


def exercise_progression_option(
    sets: pd.DataFrame, exercise: str, imperial: bool = False
) -> dict:
    df = sets[sets["exercise"] == exercise].dropna(subset=["weight_kg", "reps"])
    unit = "lb" if imperial else "kg"
    if df.empty:
        return _base() | {"xAxis": _date_axis([]), "yAxis": _value_axis(unit)}

    top = (
        df.sort_values(["log_date", "weight_kg"])
        .groupby("log_date")
        .last()
        .reset_index()
    )
    weights = top["weight_kg"] * KG_TO_LB if imperial else top["weight_kg"]

    option = _base()
    option |= {
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "line", "lineStyle": {"color": BASELINE}},
            "formatter": JsCode(
                "function (ps) {"
                "  var p = ps[0];"
                f"  return p.axisValue + '<br/>' + p.data.value.toFixed(1) + ' {unit} × '"
                "    + p.data.reps + ' 次';"
                "}"
            ).js_code,
        },
        "dataZoom": PAN_ZOOM,
        "xAxis": _date_axis(top["log_date"].dt.strftime("%Y-%m-%d").tolist()),
        "yAxis": _value_axis(unit),
        "series": [
            {
                "name": "最重一组",
                "type": "line",
                "data": [
                    {"value": round(w, 1), "reps": int(r)}
                    for w, r in zip(weights, top["reps"])
                ],
                "smooth": True,
                "symbolSize": 9,
                "lineStyle": {"width": 3, "color": BLUE},
                "itemStyle": {"color": BLUE},
                "areaStyle": {"color": _gradient(BLUE)},
            }
        ],
    }
    return option


def exercise_panel_option(
    sets: pd.DataFrame, exercise: str, imperial: bool = False
) -> dict:
    """Top set and session volume for one exercise on one plot, two y-axes.

    Two scales on one plot can be misread — where the line crosses the bars
    means nothing. Volume therefore sits behind as a washed-out bar while the
    top set keeps the foreground, and each axis name is tinted like the series
    it belongs to so which mark reads against which scale is never in doubt.
    """
    df = sets[sets["exercise"] == exercise].dropna(subset=["weight_kg", "reps"])
    unit = "lb" if imperial else "kg"
    if df.empty:
        return _base() | {"xAxis": _date_axis([]), "yAxis": _value_axis(unit)}

    factor = KG_TO_LB if imperial else 1.0
    df = df.assign(volume=df["weight_kg"] * df["reps"] * factor)
    top = (
        df.sort_values(["log_date", "weight_kg"]).groupby("log_date").last().reset_index()
    )
    volume = df.groupby("log_date")["volume"].sum().reindex(top["log_date"]).tolist()
    dates = top["log_date"].dt.strftime("%Y-%m-%d").tolist()
    weights = (top["weight_kg"] * factor).round(1)

    axis_line = {"lineStyle": {"color": BASELINE}}
    return {
        "animationDuration": 600,
        "textStyle": TEXT_STYLE,
        "title": {
            "text": exercise,
            "left": 0,
            "top": 0,
            "textStyle": {"fontSize": 13, "fontWeight": 600, "color": INK},
        },
        "axisPointer": {"link": [{"xAxisIndex": "all"}]},
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "line", "lineStyle": {"color": BASELINE}},
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
        "grid": {"left": 46, "right": 46, "top": 44, "bottom": 26},
        "xAxis": {
            "type": "category",
            "data": dates,
            "boundaryGap": True,
            "axisLine": axis_line,
            "axisTick": {"show": False},
            "axisLabel": {"color": MUTED, "fontSize": 10, "formatter": _DATE_LABEL},
        },
        "yAxis": [
            {
                "type": "value",
                "scale": True,
                "name": f"最重一组 {unit}",
                "nameGap": 10,
                "nameTextStyle": {"color": BLUE, "fontSize": 10, "align": "left"},
                "splitLine": {"lineStyle": {"color": GRID}},
                "axisLine": {"show": False},
                "axisTick": {"show": False},
                "axisLabel": {"color": MUTED, "fontSize": 10},
            },
            {
                "type": "value",
                "name": "容量",
                "nameGap": 10,
                "nameTextStyle": {"color": TEAL, "fontSize": 10, "align": "right"},
                # Only the left axis draws gridlines; two sets would fight.
                "splitLine": {"show": False},
                "axisLine": {"show": False},
                "axisTick": {"show": False},
                "splitNumber": 3,
                "axisLabel": {
                    "color": MUTED,
                    "fontSize": 10,
                    "formatter": JsCode(
                        "function (v) { return v >= 1000 ? (v / 1000).toFixed(1) + 'k' : v; }"
                    ).js_code,
                },
            },
        ],
        "series": [
            {
                "name": "容量",
                "type": "bar",
                "yAxisIndex": 1,
                "data": [round(v) for v in volume],
                "barMaxWidth": 16,
                "itemStyle": {"color": TEAL, "borderRadius": [3, 3, 0, 0], "opacity": 0.28},
                "z": 1,
            },
            {
                "name": "最重一组",
                "type": "line",
                "yAxisIndex": 0,
                "data": [
                    {"value": w, "reps": int(r)} for w, r in zip(weights, top["reps"])
                ],
                "smooth": True,
                "symbolSize": 7,
                "lineStyle": {"width": 2.5, "color": BLUE},
                "itemStyle": {"color": BLUE},
                "z": 3,
            },
        ],
    }


def muscle_group_sets_option(sets: pd.DataFrame) -> dict:
    counts = sets.dropna(subset=["muscle_group"]).groupby("muscle_group").size()
    counts = counts.sort_values()

    option = _base(left=110, top=16, bottom=32)
    option |= {
        "tooltip": {
            "trigger": "item",
            "valueFormatter": _value_formatter("组"),
        },
        "xAxis": _value_axis(splitLine={"lineStyle": {"color": GRID}}),
        "yAxis": {
            "type": "category",
            "data": counts.index.tolist(),
            "axisLine": {"show": False},
            "axisTick": {"show": False},
            "axisLabel": {"color": INK_SECONDARY},
        },
        "series": [
            {
                "name": "组数",
                "type": "bar",
                "data": counts.values.tolist(),
                "barMaxWidth": 16,
                "itemStyle": {"color": BLUE, "borderRadius": [0, 4, 4, 0]},
            }
        ],
    }
    return option


def training_calendar_option(daily: pd.DataFrame) -> dict:
    cat_index = {c: i for i, c in enumerate(CAL_CATEGORIES)}

    data = []
    for _, row in daily.iterrows():
        cat = classify_training(
            row["training_type"], row["is_training_day"], row.get("active_energy", 0.0)
        )
        data.append(
            {
                "value": [
                    row["log_date"].strftime("%Y-%m-%d"),
                    cat_index[cat],
                    row["training_type"] or cat,
                ],
                "label": {"color": CAL_LABEL_COLORS[cat]},
            }
        )

    return {
        "animationDuration": 600,
        "textStyle": TEXT_STYLE,
        "tooltip": {
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
            "itemWidth": 14,
            "itemHeight": 14,
            "textStyle": {"color": INK_SECONDARY},
            "pieces": [
                {"value": i, "label": c, "color": CAL_COLORS[c]}
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
            "itemStyle": {"borderWidth": 3, "borderColor": PAGE, "borderRadius": 4},
            "dayLabel": {"nameMap": "ZH", "color": MUTED, "firstDay": 1},
            "monthLabel": {"nameMap": "ZH", "color": INK_SECONDARY},
            "yearLabel": {"show": False},
        },
        "series": [
            {
                "type": "heatmap",
                "coordinateSystem": "calendar",
                "data": data,
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
            }
        ],
    }
