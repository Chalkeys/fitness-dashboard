"""Shared visual language: two palettes, unit conversions, training categories.

One set of slots in a fixed order, stepped twice — once for the white chart
surface, once for the dark one. A mode is chosen per run from whatever theme
the browser is showing (see `active`), and every colour on the page and in the
charts is read off the palette it returns, so nothing has to be flipped by hand.

Both sets clear `validate_palette.js` (the data-viz skill's six checks) on the
calendar's slot order, which is the order the legend puts the fills in and
therefore the only adjacency that ever touches:

    light  (surface #ffffff)  worst adjacent CVD ΔE 9.7, normal vision 15.5
    dark   (surface #161c26)  worst adjacent CVD ΔE 11.2, normal vision 16.0

The light set carries a contrast WARN — amber, teal and sky sit at 2.0–2.3:1
against white. That is legal only with relief, and the relief is real: every
calendar cell is labelled with its own category, and the tables under the
charts carry the numbers.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field

# --- The slots ---------------------------------------------------------------
#
# From a research-figure scheme the user picked: #F9FAFE, #E7E9EF, #8DC4D9,
# #DA6D6D, #045B98, #F1D492. Blue, coral and the two near-neutrals are its
# colours verbatim; the near-white and the pale grey go to the page and to the
# calendar's rest day. Two hues were added, since six categories need six and
# the scheme carries four.
#
# Two of the scheme's own colours had to be re-stepped to clear the gates,
# both for the same reason — they were mixed for filling large areas in a
# figure, not for carrying identity on a 10px mark:
#
#   #8DC4D9 -> #55b9db  chroma .064 is under the .10 floor: it reads as grey.
#   #F1D492 -> #d2aa46  L .88, 1.4:1 on white — a stain rather than a line.
#                       (An earlier pass took it to #dcb453, still L .79 and
#                       still outside the light band's .77 ceiling.)
#
# The dark column is the same six hues stepped into the dark band (L .48–.67),
# not a second palette: lilac drops furthest (L .64 -> .55) because under
# deuteranopia purple and cyan-blue separate only by lightness, and at equal
# lightness that pair collapses to ΔE 3.5.

_LIGHT_SLOTS = {
    "blue": "#045b98",   # verbatim.  OKLCH L .46 C .122 h 248
    "sky": "#55b9db",    # re-stepped. L .74 C .105 h 224
    "coral": "#da6d6d",  # verbatim.  L .66 C .137 h  21
    "amber": "#d2aa46",  # re-stepped. L .76 C .126 h  87
    "teal": "#63c8a8",   # added.     L .76 C .107 h 170
    "lilac": "#a674ca",  # added.     L .64 C .135 h 310
}
_DARK_SLOTS = {
    "blue": "#388bd3",   # L .62 C .135 h 248
    "sky": "#3aa1c3",    # L .66 C .105 h 224
    "coral": "#d76c6b",  # L .66 C .135 h  22
    "amber": "#b38c21",  # L .66 C .125 h  87
    "teal": "#30a786",   # L .66 C .115 h 170
    "lilac": "#8a57ae",  # L .55 C .140 h 310
}

FONT_FAMILY = 'system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif'

KG_TO_LB = 2.2046226218
CM_TO_IN = 1 / 2.54
G_TO_OZ = 1 / 28.3495

# Training calendar categories, in the palette's fixed slot order
CAL_CATEGORIES = ["休息", "推", "拉", "腿", "手臂", "核心", "有氧"]
_CAL_SLOTS = {
    "休息": "tint_grey",
    "推": "blue",
    "拉": "amber",
    "腿": "teal",
    "手臂": "lilac",
    "核心": "sky",
    "有氧": "coral",
}


def _relative_luminance(hex_colour: str) -> float:
    channels = []
    for i in (0, 2, 4):
        c = int(hex_colour.lstrip("#")[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_relative_luminance(a), _relative_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@dataclass
class Palette:
    """Every colour one mode uses, by the job it does rather than its hue."""

    mode: str

    blue: str
    sky: str
    coral: str
    amber: str
    teal: str
    lilac: str

    # Diverging pair. The source scheme's own correlation matrix and heat map
    # run blue against red, and say so in the caption; the red is its red, and
    # the blue is a step along the ramp between its two blues — the deep one is
    # 7:1 against white, too heavy for a wall of bars.
    diverging_neg: str
    diverging_pos: str

    # The rest day's fill, and the area a bar chart's own colour is too faint
    # to draw a line with.
    tint_grey: str

    ink: str
    ink_secondary: str
    muted: str
    grid: str
    baseline: str
    surface: str
    page: str
    border: str
    shadow: str
    # The body diagram's silhouette: a shape to write numbers on, not a mark.
    figure: str

    cal_colors: dict[str, str] = field(init=False, default_factory=dict)
    cal_label_colors: dict[str, str] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self.cal_colors = {
            name: getattr(self, slot) for name, slot in _CAL_SLOTS.items()
        }
        # Derived rather than listed: a repalette moves the fills, and hand-kept
        # label colours would quietly go unreadable on the ones that shifted.
        self.cal_label_colors = {
            name: self.label_on(fill) for name, fill in self.cal_colors.items()
        }
        # Rest stays quieter than a training day, but muted grey on the rest
        # fill is only 2.9:1 — too little for a 10px mark.
        self.cal_label_colors["休息"] = self.ink_secondary

    def label_on(self, background: str) -> str:
        """Whichever of the two inks reads better on that fill."""
        light, dark = (self.page, self.ink) if self.mode == "dark" else (self.ink, self.page)
        return dark if contrast(dark, background) >= contrast(light, background) else light

    @property
    def carriers(self) -> list[str]:
        """The categorical slots, in the order they are assigned."""
        return [self.blue, self.amber, self.teal, self.lilac, self.sky, self.coral]


LIGHT = Palette(
    mode="light",
    **_LIGHT_SLOTS,
    diverging_neg="#4a92bd",
    diverging_pos=_LIGHT_SLOTS["coral"],
    tint_grey="#e7e9ef",
    ink="#12203a",
    ink_secondary="#4c5769",
    # 4.50:1 on white: axis labels are small text and were at 3.2:1 before.
    muted="#6e7789",
    grid="#e7e9ef",
    baseline="#c9ccd6",
    surface="#ffffff",
    page="#f9fafe",
    border="#e3e6ee",
    shadow="rgba(18, 32, 58, 0.06)",
    figure="#e0e3ec",
)

# Chrome for the dark surface, stepped to the same ratios the light one holds:
# grid 1.22:1 against the surface where light is 1.21, baseline 1.56 where
# light is 1.60, muted 4.50 where light is 4.50.
DARK = Palette(
    mode="dark",
    **_DARK_SLOTS,
    diverging_neg="#5aa0cb",
    diverging_pos=_DARK_SLOTS["coral"],
    tint_grey="#222a36",
    ink="#e8ecf3",
    ink_secondary="#a8b2c2",
    muted="#79839a",
    grid="#242c39",
    baseline="#333d4d",
    surface="#161c26",
    page="#0f141c",
    border="#232c3a",
    shadow="rgba(0, 0, 0, 0.36)",
    figure="#2b3443",
)

PALETTES = {"light": LIGHT, "dark": DARK}

# Per-run rather than per-process: two browsers on different themes are two
# sessions, each running the script on its own thread, and a context variable
# is the one kind of global that does not leak between them.
_MODE: ContextVar[str] = ContextVar("theme_mode", default="light")


def set_mode(mode: str | None) -> str:
    """Fix the palette for this run. Anything but 'dark' means light."""
    chosen = "dark" if str(mode).lower() == "dark" else "light"
    _MODE.set(chosen)
    return chosen


def active() -> Palette:
    """The palette this run draws with."""
    return PALETTES[_MODE.get()]


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
