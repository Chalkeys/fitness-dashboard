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
MAGENTA = "#e87ba4"
GREEN = "#008300"

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

# Training calendar categories, in the palette's fixed slot order
CAL_CATEGORIES = ["休息", "推", "拉", "腿", "手臂", "核心", "有氧"]
CAL_COLORS = {
    "休息": "#e8e6df",
    "推": BLUE,
    "拉": ORANGE,
    "腿": AQUA,
    "手臂": MAGENTA,
    "核心": GREEN,
    "有氧": YELLOW,
}
CAL_LABEL_COLORS = {
    "休息": MUTED,
    "推": "#ffffff",
    "拉": "#ffffff",
    "腿": "#ffffff",
    "手臂": INK,
    "核心": "#ffffff",
    "有氧": INK,
}


# A day off the programme still counts as cardio when it burned this much.
# Logged cardio days run 476–675 kcal of active energy, while genuinely idle
# days sit at 200–450, so the split lands between them. Yard work and long
# walks are the usual reason a rest day clears it.
CARDIO_ACTIVE_ENERGY = 500.0


def classify_training(
    training_type: str | None, is_training_day: int, active_energy: float = 0.0
) -> str:
    """Split a day by the training type recorded against it.

    Lifting splits get their own bucket. Walking, running, functional strength
    work, and anything else that does not name a split all count as cardio, as
    does an unprogrammed day whose active energy reaches a cardio session's.
    """
    if not is_training_day:
        if active_energy and active_energy >= CARDIO_ACTIVE_ENERGY:
            return "有氧"
        return "休息"
    t = (training_type or "").lower()
    if "push" in t or "推" in t:
        return "推"
    if "pull" in t or "拉" in t:
        return "拉"
    # Checked before core so a combined leg-and-core day stays a leg day.
    if "leg" in t or "腿" in t:
        return "腿"
    if "arm" in t or "臂" in t:
        return "手臂"
    if "core" in t or "核心" in t or "腹" in t:
        return "核心"
    return "有氧"
