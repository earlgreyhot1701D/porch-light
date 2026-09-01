"""Honest quiet vs degraded — never fail open (Spec 5 task 5.2, R5, never.md #7/#12)."""
from __future__ import annotations

from porchlight.watch import matcher as M
from porchlight.watch.matcher import match_watchlist
from porchlight.watch.models import WatchAnswer


class _RecordingLog:
    def __init__(self):
        self.events = []
    def info(self, event, **k): self.events.append(("info", event))
    def warning(self, event, **k): self.events.append(("warning", event))
    def error(self, event, **k): self.events.append(("error", event))


def test_quiet_and_degraded_are_distinguishable():
    quiet = WatchAnswer()
    degraded = WatchAnswer(degraded=True, note="could not check")
    assert quiet.is_quiet and not quiet.degraded
    assert degraded.degraded and not degraded.is_quiet
    # They must not both look like "all clear": degraded is never is_quiet.
    assert quiet.is_quiet != degraded.is_quiet


def test_forced_model_failure_is_degraded_and_logs_to_failure_log(monkeypatch):
    log = _RecordingLog()
    def boom(*a, **k):
        raise RuntimeError("model down")
    monkeypatch.setattr(M, "build_agent", boom)
    ans = match_watchlist(["the pier"], {"3685-6": "a pier item"}, log=log)
    # never.md #7: degraded, not a fabricated match, not a silent all-clear.
    assert ans.degraded and not ans.matches and not ans.is_quiet
    # never.md #12: the caught error was written to the failure log, not swallowed.
    assert ("error", "watch_degraded") in log.events


def test_empty_result_is_quiet_not_degraded(monkeypatch):
    log = _RecordingLog()
    ans = match_watchlist([], {"3685-6": "x"}, log=log)
    assert ans.is_quiet and not ans.degraded
    assert ("info", "watch_quiet") in log.events


def test_degraded_answer_carries_an_honest_note():
    ans = WatchAnswer(degraded=True, note="The watcher could not fully check your list right now.")
    assert ans.note and "could not" in ans.note.lower()
