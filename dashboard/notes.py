"""Training notes, one per day, written from the page or straight into the file.

The store is a plain JSON file under ``data_sources`` rather than a table in
the database, for the same reason ``active_energy.json`` is: the exports are
rebuilt from the Xunji API with ``--overwrite``, and anything the importer
writes from them is rewritten with them. A note is the one thing here nobody
can re-derive, so it lives where no sync reaches.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from dashboard.theme import BASELINE, CORAL, INK, INK_SECONDARY, SURFACE

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTES_PATH = Path(
    os.environ.get("FITNESS_NOTES", PROJECT_ROOT / "data_sources" / "training_notes.json")
)

# A pinned note draws a labelled line across the charts, so its label has to
# stay short enough to sit above one without covering its neighbour.
MAX_LABEL = 12

# How much of the chart a mark is allowed to take. A milestone has to be
# findable without hunting, but it is annotation over someone else's data and
# a solid line at full strength cuts the series in two where it crosses.
PINNED_OPACITY = 0.42
ORDINARY_OPACITY = 0.28
LABEL_OPACITY = 0.75
MAX_TEXT = 2000

_README = [
    "每天的训练备注，按日期存。网页上「每日详情」页可以直接写，也可以手改这个文件。",
    "",
    "  text    备注正文。",
    "  pinned  true 表示时间节点：图上画一条带标签的竖线。",
    "          false 只在图上留一条淡线，鼠标悬停才显示内容。",
    "  label   竖线上的短标签，最多 12 字；不填就截 text 的开头。",
    "",
    "这个文件不会被训记同步覆盖——导出是按 API 重建的，备注是唯一重建不出来的东西。",
]


def _clean(entry: object) -> dict | None:
    """One stored day, or None if it is not shaped like a note."""
    if isinstance(entry, str):
        entry = {"text": entry}
    if not isinstance(entry, dict):
        return None
    text = str(entry.get("text") or "").strip()[:MAX_TEXT]
    if not text:
        return None
    label = str(entry.get("label") or "").strip()[:MAX_LABEL]
    return {"text": text, "pinned": bool(entry.get("pinned")), "label": label or text[:MAX_LABEL]}


def _is_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def load() -> dict[str, dict]:
    """Every note, keyed by ISO date. Unreadable or malformed entries are dropped."""
    try:
        raw = json.loads(NOTES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    days = raw.get("days") if isinstance(raw, dict) else None
    if not isinstance(days, dict):
        return {}
    cleaned = {}
    for day, entry in days.items():
        note = _clean(entry) if _is_date(str(day)) else None
        if note:
            cleaned[str(day)] = note
    return dict(sorted(cleaned.items()))


def save(notes: dict[str, dict]) -> bool:
    """Write the whole store back. False if the file could not be written."""
    payload = {"_readme": _README, "days": {}}
    for day, entry in sorted(notes.items()):
        note = _clean(entry) if _is_date(str(day)) else None
        if note:
            payload["days"][str(day)] = note
    try:
        NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
        NOTES_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        return False
    return True


def put(day: str, text: str, pinned: bool = False, label: str = "") -> bool:
    """Add or replace one day's note. Empty text deletes it."""
    notes = load()
    entry = _clean({"text": text, "pinned": pinned, "label": label})
    if entry is None:
        notes.pop(day, None)
    else:
        notes[day] = entry
    return save(notes)


def _as_date(value: str) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _nearest(day: str, dates: list[str], span: tuple) -> str | None:
    """The axis category to hang a note on, or None if it falls outside."""
    when = _as_date(day)
    first, last = span
    if when is None or first is None or last is None or not (first <= when <= last):
        return None
    parsed = [(d, _as_date(d)) for d in dates]
    candidates = [(abs((d - when).days), text) for text, d in parsed if d is not None]
    return min(candidates)[1] if candidates else None


def annotate(option: dict, notes: dict[str, dict]) -> dict:
    """Draw the day's notes onto a chart that already has a date axis.

    One mechanism, two weights. A pinned note is a moment worth seeing without
    looking for it, so it gets a solid line and a label standing on the axis.
    An ordinary note gets the faintest line the grid will carry and no label
    until the pointer is on it — enough to say something was written that day,
    not enough to compete with the data.

    A note whose day the axis does not hold snaps to the nearest day it does.
    Body measurements are taken every few days, so an exact match would drop a
    milestone from the weight chart while keeping it on the calorie one, and a
    line a day or two off still points at the right place. Notes outside the
    range the axis covers are dropped instead of being pinned to whichever end
    they were nearest.
    """
    axis = option.get("xAxis") or {}
    dates = list(axis.get("data") or ())
    series = list(option.get("series") or ())
    if not dates or not series:
        return option
    span = (_as_date(dates[0]), _as_date(dates[-1]))

    lines = []
    for day, note in sorted(notes.items()):
        at = _nearest(day, dates, span)
        if at is None:
            continue
        pinned = note.get("pinned")
        colour = CORAL if pinned else BASELINE
        lines.append(
            {
                "xAxis": at,
                # The day the note is actually about, which is not always the
                # day it is drawn on — a click has to land on the real one.
                "name": day,
                "label": {
                    "show": bool(pinned),
                    "formatter": note.get("label") or note.get("text", "")[:MAX_LABEL],
                    "position": "insideEndTop",
                    # ECharts turns a mark label to run along its line, which
                    # for a vertical one means reading it sideways.
                    "rotate": 0,
                    "color": INK_SECONDARY,
                    "opacity": LABEL_OPACITY,
                    "fontSize": 11,
                    "padding": [0, 4, 5, 4],
                },
                "lineStyle": {
                    "color": colour,
                    "width": 2 if pinned else 1,
                    "type": "solid" if pinned else "dotted",
                    "opacity": PINNED_OPACITY if pinned else ORDINARY_OPACITY,
                },
                "emphasis": {
                    "label": {
                        "show": True,
                        "formatter": note.get("text", ""),
                        "position": "insideEndTop",
                        "rotate": 0,
                        "color": INK,
                        "fontSize": 11,
                        "backgroundColor": SURFACE,
                        "borderColor": BASELINE,
                        "borderWidth": 1,
                        "borderRadius": 4,
                        "padding": [4, 6, 4, 6],
                    }
                },
            }
        )
    if not lines:
        return option

    # markLine hangs off a series rather than the chart, so it goes on the
    # first one and is told to keep out of the tooltip and the legend.
    series[0] = {
        **series[0],
        "markLine": {
            "silent": False,
            "symbol": "none",
            "animation": False,
            "data": lines,
            "tooltip": {"show": False},
        },
    }
    return {**option, "series": series}
