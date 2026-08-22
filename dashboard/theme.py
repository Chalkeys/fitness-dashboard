"""Shared visual language: palette, unit conversions, training categories.

Categorical slots in a fixed order, a diverging pair for signed values, and
recessive chrome. The slots are muted on purpose but stop where the validator
does — see the note above them.
"""

from __future__ import annotations

# Categorical slots (fixed order, never cycled).
#
# Muted, Morandi-leaning steps: chroma sits just above the 0.10 floor below
# which a hue stops reading as identity, and lightness alternates between
# neighbouring slots so pairs that collapse in hue under red-green colour
# blindness still separate by brightness. Validated on the light surface —
# worst adjacent pair 10.8 ΔE under protanopia, 22.9 with normal vision.
# Softening further means failing the chroma floor; these are as grey as the
# hues can go while still telling series apart.
BLUE = "#5479be"   # OKLCH L .58 C .115 h 262
AMBER = "#e4a067"  # L .76 C .11  h 60
TEAL = "#11957c"   # L .60 C .11  h 175
LILAC = "#af95df"  # L .72 C .11  h 300
MOSS = "#54803a"   # L .55 C .11  h 135
CORAL = "#ed8d7d"  # L .74 C .12  h 30

# Diverging pair: the categorical blue against a dusty brick red
DIVERGING_NEG = BLUE       # deficit (below baseline)
DIVERGING_POS = "#c8635d"  # surplus (above baseline), darker than the coral slot

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
