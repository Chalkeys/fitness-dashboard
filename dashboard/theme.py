"""Shared visual language: palette, unit conversions, training categories.

Categorical slots in a fixed order, a diverging pair for signed values, and
recessive chrome. The slots are muted on purpose but stop where the validator
does — see the note above them.
"""

from __future__ import annotations

# Categorical slots (fixed order, never cycled).
#
# From a research-figure scheme the user picked: #F9FAFE, #E7E9EF, #8DC4D9,
# #DA6D6D, #045B98, #F1D492. Unlike the warm scheme tried before it, this one
# is already built for categories — its own figures run five groups off it —
# and its five carriers clear the gates untouched, worst pair 18.6 ΔE with
# normal vision and 12.5 under colour blindness. So three of the six slots are
# its colours verbatim, and the near-white and pale grey go to the page and
# the calendar's rest day.
#
# Two changes. The gold is lifted off L .88, where it sits at 1.4:1 against
# white and reads as a stain rather than a line; the figures only ever fill
# with it. And two hues are added, since six categories need six and the
# scheme carries four. Worst adjacent pair on white: 21.4 ΔE with normal
# vision, 15.1 under protanopia and deuteranopia.
BLUE = "#045b98"   # verbatim.  OKLCH L .46 C .122 h 248
SKY = "#8dc4d9"    # verbatim.  L .79 C .064 h 224
CORAL = "#da6d6d"  # verbatim.  L .66 C .137 h  21
AMBER = "#dcb453"  # #F1D492 taken down to L .79 C .124 h 87
TEAL = "#63c8a8"   # added.     L .76 C .107 h 170
LILAC = "#a674ca"  # added.     L .64 C .135 h 310

# Diverging pair. The scheme's own correlation matrix and heat map run blue
# against red, and say so in the caption; the red is its red, and the blue is
# a step along the ramp between its two blues — the deep one is 7:1 against
# white, too heavy for a wall of bars.
DIVERGING_NEG = "#4a92bd"  # deficit (below baseline)
DIVERGING_POS = CORAL      # surplus (above baseline)

# The scheme's two near-neutrals, in the role its figures give them: filling
# an area, where size carries a colour too faint to draw a line with.
TINT_PAGE = "#f9fafe"
TINT_GREY = "#e7e9ef"

# Chrome & ink, cooled to match
INK = "#12203a"
INK_SECONDARY = "#4c5769"
MUTED = "#89909f"
GRID = "#e7e9ef"
BASELINE = "#c9ccd6"
SURFACE = "#ffffff"
PAGE = "#f9fafe"

FONT_FAMILY = 'system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif'

KG_TO_LB = 2.2046226218
CM_TO_IN = 1 / 2.54
G_TO_OZ = 1 / 28.3495

# Training calendar categories, in the palette's fixed slot order
CAL_CATEGORIES = ["休息", "推", "拉", "腿", "手臂", "核心", "有氧"]
CAL_COLORS = {
    "休息": TINT_GREY,
    "推": BLUE,
    "拉": AMBER,
    "腿": TEAL,
    "手臂": LILAC,
    "核心": SKY,
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
