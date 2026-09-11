"""Build the database from the exports when there is none to read.

The database is not in the repository; the exports are. A machine that has
only cloned the repo — Streamlit Community Cloud on every fresh instance —
has to make one before the first page can load. Eighty-odd days import in
about two seconds, so this runs at startup rather than being a step anyone
has to remember.

A database that already exists is left alone, whatever it holds. Rebuilding
on every start would discard anything imported since, and the owner's own
machine and the home server both carry state the exports do not.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dashboard.data import DB_PATH

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPORTS = PROJECT_ROOT / "exports"

_checked = False


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
    if path.exists() and _has_rows(path):
        return None

    # Imported lazily: the importer pulls in jsonschema and the export
    # validator, neither of which a page needs once the database is there.
    from database.init_db import initialize_database
    from scripts.import_exports import import_exports

    initialize_database(path)
    # needs_review days are included because they were on the machines that
    # built the reference database by hand, and a fresh build should match.
    stats = import_exports(EXPORTS, path, include_needs_review=True)
    return f"已从 {stats['files']} 个导出重建数据库（{stats['inserted']} 条记录）"
