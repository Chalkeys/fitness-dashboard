"""Build the database from the exports when there is none to read.

The database is not in the repository; the exports are. A machine that has
only cloned the repo — Streamlit Community Cloud on every fresh instance —
has to make one before the first page can load. Eighty-odd days import in
about two seconds, so this runs at startup rather than being a step anyone
has to remember.

The import runs on every start, not only when there is no database. It is
idempotent — a file already imported is recognised by its hash and skipped,
so a complete database costs about a second to confirm — and that is what
makes it safe against the one failure a first start can suffer: the process
being killed part-way through, leaving a database with fifty of eighty-one
days in it. Checking only whether rows existed would have taken that for
finished, and it stayed that way on the public instance until noticed. An
existing database is never rebuilt, only brought up to the exports.
"""

from __future__ import annotations

import sqlite3
import subprocess
import threading
import time
from pathlib import Path

from dashboard.data import DB_PATH

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPORTS = PROJECT_ROOT / "exports"

_checked = False

# How often a running instance looks for new commits. The public instance
# does not redeploy on the sync's pushes — neither the repository token nor a
# personal one made it — so it keeps itself current instead: on a page view,
# at most this often, it fetches, pulls if behind, imports, and clears the
# caches. Nobody looking means nothing pulled, which is fine; the first
# visitor after a quiet spell pays a couple of seconds.
REFRESH_INTERVAL_SECONDS = 600
_refresh_lock = threading.Lock()
_last_refresh = 0.0


def _has_rows(path: Path) -> bool:
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            return connection.execute("SELECT COUNT(*) FROM daily_logs").fetchone()[0] > 0
    except sqlite3.Error:
        return False


def ensure_database() -> str | None:
    """Make sure a database exists. Returns what was done, or None if nothing."""
    global _checked
    if _checked:
        return None
    _checked = True

    path = Path(DB_PATH)
    fresh = not (path.exists() and _has_rows(path))

    # Imported lazily: the importer pulls in jsonschema and the export
    # validator, neither of which a page needs once the database is there.
    from database.init_db import initialize_database
    from scripts.import_exports import import_exports

    initialize_database(path)
    # needs_review days are included because they were on the machines that
    # built the reference database by hand, and a fresh build should match.
    stats = import_exports(EXPORTS, path, include_needs_review=True)
    if fresh:
        return f"已从 {stats['files']} 个导出重建数据库（{stats['inserted']} 条记录）"
    if stats["files"]:
        return f"已补入 {stats['files']} 个导出（{stats['inserted']} 条记录）"
    return None


def _git(*args: str) -> str | None:
    """Run git in the checkout; None when it fails or there is no git."""
    try:
        done = subprocess.run(
            ["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def refresh_from_origin() -> str | None:
    """Pull new commits into the running checkout and import what changed.

    Returns what happened, or None when there was nothing to do or it was too
    soon to look. Never raises: a machine without git, without network, or
    with a checkout that will not fast-forward keeps serving what it has.

    ``--autostash`` carries anything edited on this machine — notes, settings
    — across the pull, which matters on the home server. Where a rebase
    cannot apply cleanly it is abandoned and the working tree left as it was.
    """
    global _last_refresh
    with _refresh_lock:
        now = time.monotonic()
        if now - _last_refresh < REFRESH_INTERVAL_SECONDS:
            return None
        _last_refresh = now

        head = _git("rev-parse", "HEAD")
        if head is None or _git("fetch", "-q", "origin", "main") is None:
            return None
        remote = _git("rev-parse", "origin/main")
        if not remote or remote == head:
            return None
        if _git("pull", "-q", "--rebase", "--autostash", "origin", "main") is None:
            _git("rebase", "--abort")
            return None

        from scripts.import_exports import import_exports

        stats = import_exports(EXPORTS, Path(DB_PATH), include_needs_review=True)
        try:
            import streamlit as st

            st.cache_data.clear()
        except Exception:  # noqa: BLE001 — outside a Streamlit runtime there is nothing to clear
            pass
        return f"已更新到 {remote[:7]}，导入 {stats['files']} 个导出"


def running_version() -> str:
    """The commit this instance is serving, for the corner of the page.

    Which version a page is showing is worth knowing on any instance, and on
    one that updates itself it is the only way to see that it did.
    """
    return _git("rev-parse", "--short", "HEAD") or "未知"

