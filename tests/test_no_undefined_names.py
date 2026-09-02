"""A name that does not exist is a page that does not load.

The pages are not importable outside a Streamlit runtime, so nothing in this
suite exercises `app.py`. Threading a new argument through it broke two call
sites in two days, each time reaching the server before anyone saw it —
`_pinned_progression` and then `_corrected_balance_section`, both raising
NameError on the one page that called them. pyflakes reads the source without
running it and finds exactly this class of mistake.
"""

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCES = ["app.py", "dashboard", "scripts", "database", "tests"]


def _pyflakes() -> list[str]:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pyflakes", *SOURCES],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):  # pragma: no cover
        pytest.skip("pyflakes is not available")
    if result.returncode > 1:  # pragma: no cover
        pytest.skip(f"pyflakes could not run: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line.strip()]


def test_no_undefined_names():
    # Only undefined names, not unused imports: this guards against a page
    # that will not load, and is not a style gate.
    bad = [line for line in _pyflakes() if "undefined name" in line]
    assert not bad, "\n".join(bad)


def test_no_redefined_or_unreachable_code():
    # A second def of the same name silently replaces the first, and the
    # earlier one goes unreachable — the kind of thing a large edit leaves.
    bad = [
        line
        for line in _pyflakes()
        if "redefinition of unused" in line or "unable to detect undefined" in line
    ]
    assert not bad, "\n".join(bad)
