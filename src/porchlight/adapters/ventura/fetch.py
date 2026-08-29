"""Ventura adapter — good-citizen HTTP fetch layer (R7).

The ONLY module that touches the network. Everything else is pure.

Posture (§7, §security, §34):
- Host allowlist: the permitted host only. The Granicus host is excluded, and
  off-domain redirects are blocked rather than followed (SSRF).
- Descriptive User-Agent naming the project with a contact URL.
- Conditional GET (If-Modified-Since / If-None-Match) so unchanged documents are
  not re-downloaded; a 304 returns the cached marker, not a body.
- Max 1 concurrent fetch (enforced by a module-level lock), exponential backoff
  on 429/503.
- Every failure writes to the failure log — never a silently swallowed exception
  (never.md #12).

robots.txt: the permitted host allows /AgendaCenter; the Granicus host disallows
'/'. We obey robots.txt as a matter of trust even though it is a convention, not
law (§34 note). The allowlist below encodes "permitted host only", which is the
enforcement of that decision.
"""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

from porchlight.log import get_logger

log = get_logger("porchlight.adapters.ventura.fetch")

# §34: the single permitted host. Everything else, including the Granicus host, is refused.
PERMITTED_HOST = "www.cityofventura.ca.gov"

# R7.2: descriptive UA with a contact URL. The contact comes from config in the
# real run (FETCH_USER_AGENT_CONTACT); this default names the project and repo.
USER_AGENT = "PorchLight/0.1 (+https://github.com/earlgreyhot1701D/porch-light)"

# T6: HTTP fetch timeout (seconds).
FETCH_TIMEOUT_S = 30

# Backoff schedule for 429/503 (seconds). Exponential, bounded.
_BACKOFF_SCHEDULE = (2, 5, 15)

# Max 1 concurrent fetch (§7 good-citizen posture): a single process-wide lock.
_fetch_lock = threading.Lock()


class DisallowedHostError(Exception):
    """Raised when a URL targets any host other than the permitted host (§34)."""


@dataclass(frozen=True)
class FetchResult:
    """Outcome of a conditional GET."""

    url: str
    status: int
    """200 with a body, or 304 when unchanged (body is None)."""
    body: bytes | None
    last_modified: str | None
    etag: str | None


def _assert_permitted(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    if host != PERMITTED_HOST:
        # Do not fetch. This is the SSRF / allowlist guard (R7.1) and the §34
        # Granicus exclusion in one check.
        raise DisallowedHostError(
            f"Refusing to fetch host '{host}': only '{PERMITTED_HOST}' is permitted (§34)."
        )


class _NoRedirectToOtherHost(urllib.request.HTTPRedirectHandler):
    """Block redirects that leave the permitted host (R7.1). Same-host redirects OK."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host = (urlparse(newurl).hostname or "").lower()
        if host != PERMITTED_HOST:
            raise DisallowedHostError(
                f"Refusing off-domain redirect to '{host}' (§34)."
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_NoRedirectToOtherHost())


def fetch(
    url: str,
    *,
    if_modified_since: str | None = None,
    if_none_match: str | None = None,
) -> FetchResult:
    """Conditional GET against the permitted host, one at a time, with backoff.

    Args:
        url: absolute URL on the permitted host.
        if_modified_since: prior Last-Modified value for conditional GET (R7.3).
        if_none_match: prior ETag value for conditional GET (R7.3).

    Returns:
        FetchResult with status 200 (body present) or 304 (unchanged, body None).

    Raises:
        DisallowedHostError: URL or a redirect targets a non-permitted host.
        urllib.error.URLError / HTTPError: after backoff is exhausted. The caller
        logs the failure state; we log here too so nothing is swallowed silently.
    """
    _assert_permitted(url)

    headers = {"User-Agent": USER_AGENT}
    if if_modified_since:
        headers["If-Modified-Since"] = if_modified_since
    if if_none_match:
        headers["If-None-Match"] = if_none_match

    last_err: Exception | None = None
    # One attempt plus the backoff schedule for transient 429/503.
    for attempt, delay in enumerate((0, *_BACKOFF_SCHEDULE)):
        if delay:
            time.sleep(delay)
        try:
            with _fetch_lock:  # max 1 concurrent
                req = urllib.request.Request(url, headers=headers, method="GET")
                with _opener.open(req, timeout=FETCH_TIMEOUT_S) as resp:
                    body = resp.read()
                    log.info(
                        "fetch_ok",
                        url=url,
                        status=resp.status,
                        bytes=len(body),
                    )
                    return FetchResult(
                        url=url,
                        status=resp.status,
                        body=body,
                        last_modified=resp.headers.get("Last-Modified"),
                        etag=resp.headers.get("ETag"),
                    )
        except urllib.error.HTTPError as e:
            if e.code == 304:
                log.info("fetch_not_modified", url=url, status=304)
                return FetchResult(
                    url=url,
                    status=304,
                    body=None,
                    last_modified=if_modified_since,
                    etag=if_none_match,
                )
            if e.code in (429, 503) and attempt < len(_BACKOFF_SCHEDULE):
                log.warning("fetch_retry", url=url, status=e.code, attempt=attempt)
                last_err = e
                continue
            log.error("fetch_http_error", url=url, status=e.code)
            raise
        except DisallowedHostError:
            log.error("fetch_disallowed_host", url=url)
            raise
        except Exception as e:  # noqa: BLE001 - we log then re-raise; never swallow
            log.error("fetch_error", url=url, error=type(e).__name__)
            last_err = e
            if attempt < len(_BACKOFF_SCHEDULE):
                continue
            raise
    # Exhausted backoff.
    assert last_err is not None
    raise last_err
