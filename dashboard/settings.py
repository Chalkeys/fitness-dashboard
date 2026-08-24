"""User preferences that outlive a browser session.

The dashboard opens its database read-only, so tunable settings live in their
own small JSON file beside it. Single user, so no locking or per-user keying.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dashboard.energy import DEFAULT_BMR

SETTINGS_PATH = Path(os.environ.get("FITNESS_SETTINGS", "settings.json"))

DEFAULTS: dict[str, object] = {
    # Back-figured from two DEXA scans: over the 34 days between them the
    # logged deficit and the measured change in fat and lean mass reconcile
    # near here. Not -30%, which dated from when TDEE estimated activity from
    # session length rather than reading a watch.
    "bias_active": -5,
    "bias_intake": 5,
    "bias_bmr": int(DEFAULT_BMR),
    "balance_mode": "纠偏后",
    # Intake against TDEE opens corrected: the raw pair shows a deficit the
    # measured weight contradicts.
    "intake_mode": "纠偏后",
    "target_body_fat": 15.0,
    "target_horizon": 30,
    "pinned_columns": 2,
    # Two per movement pattern, kept on the training page permanently. The
    # order is the order the panels appear in, so it is stored, not derived
    # from the picker.
    "pinned_exercises": [
        "杠铃卧推",
        "上斜杠铃卧推",
        "坐姿划船",
        "宽距高位下拉",
        "杠铃罗马尼亚硬拉",
        "泽奇深蹲",
    ],
}


# What each setting is allowed to be. The file is written by the app and read
# back on the next run, so a bad write would otherwise stick forever: a
# segmented control returns None when its selection is cleared, and that None
# overrode the default every session after.
MODES = ("原始", "纠偏后")
_CHOICES: dict[str, tuple] = {"balance_mode": MODES, "intake_mode": MODES}
_RANGES: dict[str, tuple[float, float]] = {
    "bias_active": (-80, 20),
    "bias_intake": (-10, 30),
    "bias_bmr": (1000, 3000),
    "target_body_fat": (5.0, 35.0),
    "target_horizon": (7, 365),
    "pinned_columns": (1, 3),
}


def is_valid(key: str, value: object) -> bool:
    if value is None:
        return False
    if key in _CHOICES:
        return value in _CHOICES[key]
    if key in _RANGES:
        low, high = _RANGES[key]
        return isinstance(value, (int, float)) and not isinstance(value, bool) and low <= value <= high
    if key == "pinned_exercises":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    return True


def load() -> dict:
    """Stored settings merged over the defaults; defaults alone if unreadable."""
    try:
        stored = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULTS)
    if not isinstance(stored, dict):
        return dict(DEFAULTS)
    return {
        **DEFAULTS,
        **{k: v for k, v in stored.items() if k in DEFAULTS and is_valid(k, v)},
    }


def save(values: dict) -> None:
    """Write the known keys. A failure here must not take the page down."""
    # Never let an invalid value reach the file: it would be read back next run.
    payload = {k: v for k, v in values.items() if k in DEFAULTS and is_valid(k, v)}
    try:
        SETTINGS_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        pass
