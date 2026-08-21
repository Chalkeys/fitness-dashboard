"""Shared visual language: palette, unit conversions, training categories.

Palette follows the validated reference instance — categorical slots in fixed
order (blue/orange/aqua), diverging blue<->red, recessive chrome.
"""

from __future__ import annotations

# Categorical slots (fixed order, never cycled)
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
YELLOW = "#eda100"

# Diverging pair
DIVERGING_NEG = "#2a78d6"  # deficit (below baseline)
DIVERGING_POS = "#e34948"  # surplus (above baseline)

# Chrome & ink
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"

FONT_FAMILY = 'system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif'

KG_TO_LB = 2.2046226218
CM_TO_IN = 1 / 2.54
G_TO_OZ = 1 / 28.3495

# Training calendar categories
CAL_CATEGORIES = ["休息", "推", "拉", "腿", "有氧", "其他"]
CAL_COLORS = {
    "休息": "#f0efec",
    "推": BLUE,
    "拉": ORANGE,
    "腿": AQUA,
    "有氧": YELLOW,
    "其他": MUTED,
}
CAL_LABEL_COLORS = {
    "休息": MUTED,
    "推": "#ffffff",
    "拉": "#ffffff",
    "腿": "#ffffff",
    "有氧": INK,
    "其他": "#ffffff",
}


def classify_training(training_type: str | None, is_training_day: int) -> str:
    if not is_training_day:
        return "休息"
    t = (training_type or "").lower()
    if "push" in t or "推" in t:
        return "推"
    if "pull" in t or "拉" in t:
        return "拉"
    if "leg" in t or "腿" in t:
        return "腿"
    if "cardio" in t or "有氧" in t or "walk" in t:
        return "有氧"
    return "其他"
