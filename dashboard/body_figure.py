"""A front-view body diagram with each girth labelled at its site.

The figure is inline SVG rather than a chart: the reader is locating a number
on a body, not comparing magnitudes, so the anatomy carries the meaning and the
numbers ride along as callouts. Each site draws a short rule across the part it
measures, the way a tape would sit.
"""

from __future__ import annotations

import pandas as pd

from dashboard.theme import (
    BLUE,
    CM_TO_IN,
    FONT_FAMILY,
    INK,
    INK_SECONDARY,
    MUTED,
)

WIDTH, HEIGHT = 520, 560
CENTRE = 260

_BODY_FILL = "#dedbd2"
_LEFT_TEXT_X, _RIGHT_TEXT_X = 150, 370

# key(s), label, which side the callout runs to, the height of the measuring
# rule, its centre, and its half-width — the part's own width at that height.
_SITES: list[dict] = [
    {"key": "neck_cm", "label": "颈围", "side": "left", "y": 92, "cx": CENTRE, "hw": 15},
    {"key": "shoulder_cm", "label": "肩宽", "side": "right", "y": 112, "cx": CENTRE, "hw": 64},
    {"key": "chest_cm", "label": "胸围", "side": "left", "y": 152, "cx": CENTRE, "hw": 59},
    {
        "key": ("arm_left_cm", "arm_right_cm"),
        "label": "上臂 左/右",
        "side": "right",
        "y": 205,
        "cx": 340,
        "hw": 15,
    },
    {"key": "waist_cm", "label": "腰围", "side": "left", "y": 215, "cx": CENTRE, "hw": 43},
    {
        "key": ("forearm_left_cm", "forearm_right_cm"),
        "label": "前臂 左/右",
        "side": "right",
        "y": 295,
        "cx": 352,
        "hw": 12,
    },
    {"key": "hip_cm", "label": "臀围", "side": "left", "y": 268, "cx": CENTRE, "hw": 53},
    {
        "key": ("leg_left_cm", "leg_right_cm"),
        "label": "大腿 左/右",
        "side": "right",
        "y": 350,
        "cx": 292,
        "hw": 22,
    },
    {
        "key": ("calf_left_cm", "calf_right_cm"),
        "label": "小腿 左/右",
        "side": "left",
        "y": 455,
        "cx": 228,
        "hw": 16,
    },
]


def _fmt(value: float | None, imperial: bool) -> str | None:
    if value is None or pd.isna(value):
        return None
    return f"{value * CM_TO_IN:.1f}" if imperial else f"{value:g}"


def _site_values(
    row: pd.Series, prev: pd.Series | None, site: dict, imperial: bool
) -> tuple[str, str]:
    """Rendered value text and its change against the previous session."""
    keys = site["key"] if isinstance(site["key"], tuple) else (site["key"],)
    values = [_fmt(row.get(k), imperial) for k in keys]
    if all(v is None for v in values):
        return "—", ""

    text = " / ".join(v if v is not None else "—" for v in values)

    deltas = []
    for k in keys:
        now, before = row.get(k), None if prev is None else prev.get(k)
        if pd.notna(now) and before is not None and pd.notna(before):
            change = (now - before) * (CM_TO_IN if imperial else 1)
            if abs(change) >= 0.05:
                deltas.append(f"{change:+.1f}")
    # Left and right usually move together; show one figure when they agree.
    return text, "  ".join(dict.fromkeys(deltas))


def _silhouette() -> str:
    """Flat figure: head, torso, and limbs as round-capped strokes."""
    return f"""
    <g fill="{_BODY_FILL}">
      <ellipse cx="{CENTRE}" cy="52" rx="24" ry="30"/>
      <path d="M247 78 h26 v30 h-26 z"/>
      <path d="M260 100
               C 292 100 316 106 322 118
               C 326 132 322 150 318 168
               L 306 206 C 302 218 300 228 302 240
               L 312 288 C 314 300 310 308 300 310
               L 220 310 C 210 308 206 300 208 288
               L 218 240 C 220 228 218 218 214 206
               L 202 168 C 198 150 194 132 198 118
               C 204 106 228 100 260 100 Z"/>
    </g>
    <g stroke="{_BODY_FILL}" fill="none" stroke-linecap="round" stroke-linejoin="round">
      <path d="M208 120 L 180 236 L 172 318" stroke-width="27"/>
      <path d="M312 120 L 340 236 L 348 318" stroke-width="27"/>
      <path d="M232 300 L 228 400 L 230 496" stroke-width="41"/>
      <path d="M288 300 L 292 400 L 290 496" stroke-width="41"/>
    </g>
    <g fill="{_BODY_FILL}">
      <ellipse cx="226" cy="510" rx="19" ry="11"/>
      <ellipse cx="294" cy="510" rx="19" ry="11"/>
      <circle cx="170" cy="330" r="11"/>
      <circle cx="350" cy="330" r="11"/>
    </g>
    """


def body_figure_svg(
    row: pd.Series, prev: pd.Series | None = None, imperial: bool = False
) -> str:
    unit = "in" if imperial else "cm"
    parts = [_silhouette()]

    for site in _SITES:
        value, delta = _site_values(row, prev, site, imperial)
        measured = value != "—"
        left = site["side"] == "left"
        y, cx, hw = site["y"], site["cx"], site["hw"]

        colour = BLUE if measured else MUTED
        dash = "" if measured else ' stroke-dasharray="3 3"'
        text_x = _LEFT_TEXT_X if left else _RIGHT_TEXT_X
        anchor = "end" if left else "start"
        # The rule sits across the part; a leader runs from its outer end.
        rule_end = cx - hw if left else cx + hw
        leader_x = text_x + 8 if left else text_x - 8

        parts.append(
            f'<g stroke="{colour}" stroke-width="1.5" opacity="0.9">'
            f'<line x1="{cx - hw}" y1="{y}" x2="{cx + hw}" y2="{y}"{dash}/>'
            f'<line x1="{cx - hw}" y1="{y - 4}" x2="{cx - hw}" y2="{y + 4}"/>'
            f'<line x1="{cx + hw}" y1="{y - 4}" x2="{cx + hw}" y2="{y + 4}"/>'
            f'<line x1="{rule_end}" y1="{y}" x2="{leader_x}" y2="{y}" '
            f'stroke-width="1" opacity="0.5" stroke-dasharray="2 3"/>'
            f"</g>"
        )
        parts.append(
            f'<text x="{text_x}" y="{y - 6}" text-anchor="{anchor}" '
            f'font-size="11" fill="{MUTED}">{site["label"]}</text>'
        )
        parts.append(
            f'<text x="{text_x}" y="{y + 12}" text-anchor="{anchor}" '
            f'font-size="15" font-weight="600" fill="{INK if measured else MUTED}">'
            f'{value}<tspan font-size="11" font-weight="400" fill="{MUTED}">'
            f'{" " + unit if measured else ""}</tspan></text>'
        )
        if delta:
            parts.append(
                f'<text x="{text_x}" y="{y + 26}" text-anchor="{anchor}" '
                f'font-size="11" fill="{INK_SECONDARY}">{delta}</text>'
            )

    body = "".join(parts)
    # The font stack carries double quotes, which would end an XML attribute
    # early and leave the document unparseable, so it goes in a style element.
    style = f"<style>text{{font-family:{FONT_FAMILY}}}</style>"
    return (
        # Intrinsic size as well as a viewBox, so the rendered image keeps its
        # aspect ratio instead of collapsing to a default height.
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'width="{WIDTH}" height="{HEIGHT}" preserveAspectRatio="xMidYMid meet" '
        f'role="img" aria-label="身体围度示意图">{style}{body}</svg>'
    )
