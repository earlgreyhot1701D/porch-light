"""The no-store invariant — structural (Spec 5 task 6.2, R3, never.md #8).

Asserted BY CONSTRUCTION, the way the draft's empty-stance is: the watch package
contains no persistence call and no shared/public-watchlist path. A watchlist is an
argument in and an answer out; nothing about the user is written anywhere.
"""
from __future__ import annotations

import pathlib

WATCH_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "porchlight" / "watch"

# Tokens that would indicate persistence or a shared/public watchlist path. If the
# watcher ever grows one of these, this test goes red — the invariant is enforced by
# the absence of the mechanism, not by a promise.
# Code patterns (calls/identifiers), not prose. The docstrings legitimately use the
# WORD "persistence" to state the invariant ("no table, no cache, no persistence"),
# so we match executable tokens, not English. To avoid flagging our own docstrings,
# each token is a call/DDL/identifier form that only appears in real persistence code.
FORBIDDEN_TOKENS = (
    "INSERT INTO",
    "UPDATE ",
    "DELETE FROM",
    "backend.execute",
    "get_backend(",
    "import data_api",
    "from db ",
    ".execute(",
    "shared_watchlist",
    "public_watchlist",
    "save_watchlist",
    "store_watchlist",
    "def persist",
)


def _watch_sources() -> list[pathlib.Path]:
    return sorted(WATCH_DIR.glob("*.py"))


def test_watch_package_has_no_persistence_or_shared_list_path():
    offenders = []
    for path in _watch_sources():
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_TOKENS:
            if token in text:
                offenders.append(f"{path.name}: {token!r}")
    assert not offenders, (
        "watch package must not persist anything about the user or build a shared "
        f"watchlist (never.md #8). Found: {offenders}"
    )


def test_matcher_takes_watchlist_as_argument_and_returns_answer():
    # The signature itself is the guarantee: terms come in, an answer goes out.
    import inspect

    from porchlight.watch.matcher import match_watchlist

    params = list(inspect.signature(match_watchlist).parameters)
    assert params[0] == "terms" and params[1] == "items"
    assert "WatchAnswer" in str(inspect.signature(match_watchlist).return_annotation)


def test_invariant_is_documented_in_the_package():
    # The no-store rule is stated in the package, like the draft's empty-stance note.
    init_text = (WATCH_DIR / "__init__.py").read_text(encoding="utf-8")
    matcher_text = (WATCH_DIR / "matcher.py").read_text(encoding="utf-8")
    assert "never.md #8" in (init_text + matcher_text)
    assert "writes nothing" in init_text.lower() or "writes nothing" in matcher_text.lower()
