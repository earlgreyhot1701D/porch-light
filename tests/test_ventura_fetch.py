"""Tests for the Ventura fetch allowlist (R7.1) — working rigor, not property.

The allowlist is a security control (SSRF + §34 Granicus exclusion). These assert
the excluded host and off-domain redirects are refused before any network call.
"""

from __future__ import annotations

import pytest

from porchlight.adapters.ventura.fetch import (
    PERMITTED_HOST,
    DisallowedHostError,
    _assert_permitted,
    _NoRedirectToOtherHost,
)


def test_permitted_host_passes():
    # Should not raise.
    _assert_permitted(f"https://{PERMITTED_HOST}/AgendaCenter/ViewFile/Agenda/_02102026-3569")


def test_granicus_host_refused():
    with pytest.raises(DisallowedHostError):
        _assert_permitted("https://cityofventura.granicus.com/JSON.php")


def test_arbitrary_host_refused():
    with pytest.raises(DisallowedHostError):
        _assert_permitted("https://evil.example.com/AgendaCenter")


def test_off_domain_redirect_blocked():
    handler = _NoRedirectToOtherHost()
    with pytest.raises(DisallowedHostError):
        handler.redirect_request(
            req=None, fp=None, code=302, msg="Found", headers={},
            newurl="https://cityofventura.granicus.com/somewhere",
        )


def test_same_host_redirect_allowed(monkeypatch):
    # A same-host redirect should be permitted (delegates to super()).
    handler = _NoRedirectToOtherHost()
    called = {}

    def fake_super(*args, **kwargs):
        called["ok"] = True
        return "redirect-request"

    monkeypatch.setattr(
        "urllib.request.HTTPRedirectHandler.redirect_request", fake_super
    )
    result = handler.redirect_request(
        req=None, fp=None, code=302, msg="Found", headers={},
        newurl=f"https://{PERMITTED_HOST}/AgendaCenter/Other",
    )
    assert called.get("ok") is True
    assert result == "redirect-request"
