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
