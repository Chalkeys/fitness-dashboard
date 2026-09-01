"""Shared visual language: palette, unit conversions, training categories.

Categorical slots in a fixed order, a diverging pair for signed values, and
recessive chrome. The slots are muted on purpose but stop where the validator
does — see the note above them.
"""

from __future__ import annotations

# Categorical slots (fixed order, never cycled).
#
# Derived from a research-figure scheme the user picked out: #F4C7C7,
# #E6ECF2, #E57373, #F29A8E, #7FB3B0, #FFF1D6. Taken literally it cannot
# carry seven categories — #E57373 against #F29A8E is 9.9 ΔE with normal
# vision and 7.5 under deuteranopia, so the two read as one colour, and its
# three pale tints sit under 1.5:1 against the page. That is not a fault in
# the scheme: the figures use the pale three as fills, where area carries
# them, and the red against the teal as a diverging pair. Both of those uses
# are kept below, verbatim.
#
# What the slots take from it is its hues — teal 192, red 21, cream 84, the
# blue-grey 255 — pushed to a chroma that reads as identity and laid on a
# lightness ladder. Red-green blindness collapses the warm three into one
# another and the cool three into one another, so lightness inside each of
# those groups is what keeps them apart. Worst adjacent pair on the light
# surface: 24.4 ΔE with normal vision, 14.1 under protanopia, 15.2 under
# deuteranopia — against 15.5 / 6.3 / 5.7 for the palette this replaced,
# measured the same way. Tritanopia stays the weak axis at 2.1 for
# 拉/有氧, up from 0.3.
BLUE = "#5088cf"   # OKLCH L .62 C .123 h 255
AMBER = "#a97f14"  # L .62 C .122 h 84
TEAL = "#008d89"   # L .58 C .100 h 192
LILAC = "#e69dc6"  # L .78 C .101 h 345
MOSS = "#6ac17f"   # L .74 C .128 h 150
CORAL = "#b25e5e"  # L .58 C .109 h 21

# Diverging pair, straight out of the source scheme, which pairs exactly
# these two across its correlation matrix and its heat map.
DIVERGING_NEG = "#7fb3b0"  # deficit (below baseline)
DIVERGING_POS = "#e57373"  # surplus (above baseline)

# The scheme's three pale tints, in the role its own figures give them:
# filling an area, where size carries a colour too faint to draw a line with.
TINT_WARM = "#f4c7c7"
TINT_COOL = "#e6ecf2"
TINT_CREAM = "#fff1d6"

# Chrome & ink, warmed towards the cream so the page and the data agree
INK = "#14110c"
INK_SECONDARY = "#57534a"
MUTED = "#8d877c"
GRID = "#e9e3d8"
BASELINE = "#d6cec0"
SURFACE = "#fdfbf7"
PAGE = "#f6f2ea"

FONT_FAMILY = 'system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif'

KG_TO_LB = 2.2046226218
CM_TO_IN = 1 / 2.54
G_TO_OZ = 1 / 28.3495

# Training calendar categories, in the palette's fixed slot order
CAL_CATEGORIES = ["休息", "推", "拉", "腿", "手臂", "核心", "有氧"]
CAL_COLORS = {
    "休息": TINT_COOL,
    "推": BLUE,
    "拉": AMBER,
    "腿": TEAL,
    "手臂": LILAC,
    "核心": MOSS,
    "有氧": CORAL,
}


def _relative_luminance(hex_colour: str) -> float:
    channels = []
    for i in (0, 2, 4):
        c = int(hex_colour.lstrip("#")[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    la, lb = sorted((_relative_luminance(a), _relative_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def label_on(background: str) -> str:
    """Whichever of ink or white reads better on that fill."""
    return INK if _contrast(INK, background) >= _contrast("#ffffff", background) else "#ffffff"


# Derived rather than listed: a repalette moves the fills, and hand-kept label
# colours would quietly go unreadable on the ones that got lighter.
CAL_LABEL_COLORS = {name: label_on(fill) for name, fill in CAL_COLORS.items()}
# Rest stays quieter than a training day, but muted grey on the rest fill is
# only 2.9:1 — too little for a 10px mark.
CAL_LABEL_COLORS["休息"] = INK_SECONDARY


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
