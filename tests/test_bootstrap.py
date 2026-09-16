"""The self-refresh keys on what was imported, not on what was pulled."""

from __future__ import annotations

import pytest

from dashboard import bootstrap


@pytest.fixture
def fake(monkeypatch):
    """A checkout with a scriptable git and importer."""
    state = {"head": "aaa", "remote": "aaa", "pull_ok": True, "failed": 0, "imports": 0}

    def git(*args):
        if args == ("rev-parse", "HEAD"):
            return state["head"]
        if args == ("rev-parse", "origin/main"):
            return state["remote"]
        if args[0] == "fetch":
            return ""
        if args[0] == "pull":
            if not state["pull_ok"]:
                return None
            state["head"] = state["remote"]
            return ""
        return ""

    def import_exports(*_, **__):
        state["imports"] += 1
        return {"files": 1, "inserted": 3, "updated": 0, "skipped": 0, "failed": state["failed"]}

    monkeypatch.setattr(bootstrap, "_git", git)
    monkeypatch.setattr("scripts.import_exports.import_exports", import_exports)
    monkeypatch.setattr(bootstrap, "_last_refresh", 0.0)
    monkeypatch.setattr(bootstrap, "_imported_head", None)
    monkeypatch.setattr(bootstrap, "REFRESH_INTERVAL_SECONDS", 0)
    return state


def test_first_check_imports_even_without_new_commits(fake):
    outcome = bootstrap.refresh_from_origin()
    assert outcome is not None and outcome.ok
    assert fake["imports"] == 1
    assert bootstrap.refresh_from_origin() is None


def test_new_commit_is_pulled_and_imported(fake):
    bootstrap.refresh_from_origin()
    fake["remote"] = "bbb"
    outcome = bootstrap.refresh_from_origin()
    assert outcome is not None and "bbb" in outcome.message
    assert fake["head"] == "bbb"
    assert fake["imports"] == 2


def test_failed_import_is_reported_and_retried(fake):
    fake["failed"] = 1
    outcome = bootstrap.refresh_from_origin()
    assert outcome is not None and not outcome.ok
    fake["failed"] = 0
    outcome = bootstrap.refresh_from_origin()
    assert outcome is not None and outcome.ok
    assert fake["imports"] == 2
    assert bootstrap.refresh_from_origin() is None


def test_failed_pull_still_imports_what_is_there(fake):
    fake["remote"] = "bbb"
    fake["pull_ok"] = False
    outcome = bootstrap.refresh_from_origin()
    assert outcome is not None and "aaa" in outcome.message
    assert fake["head"] == "aaa"
