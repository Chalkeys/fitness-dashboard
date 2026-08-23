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
    "bias_active": -30,
    "bias_intake": 10,
    "bias_bmr": int(DEFAULT_BMR),
    "balance_mode": "纠偏后",
    # Intake against TDEE opens corrected: the raw pair shows a deficit the
    # measured weight contradicts.
    "intake_mode": "纠偏后",
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


def load() -> dict:
    """Stored settings merged over the defaults; defaults alone if unreadable."""
    try:
        stored = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULTS)
    if not isinstance(stored, dict):
        return dict(DEFAULTS)
    return {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}


def save(values: dict) -> None:
    """Write the known keys. A failure here must not take the page down."""
    payload = {k: v for k, v in values.items() if k in DEFAULTS}
    try:
        SETTINGS_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        pass
