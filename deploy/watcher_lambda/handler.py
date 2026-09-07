"""AWS Lambda handler for the Porch Light watcher (Block B, §26c live-invoke).

A judge types a watch term; this runs the REAL Nova Lite matcher at request time
and returns matches with the model's own reasons. Behind a Function URL, CORS
restricted to the Vercel origin, reserved concurrency 2.

NO-STORE (never.md #8, the privacy line on the page) — audited paths, all closed:
  - structlog context / log events: matcher.py logs only counts, run_id, model_id,
    tool_name. This handler logs only static events + counts. NO watch term or item
    text is ever passed to log.*.
  - exception traceback: every failure is caught here and logged as a STATIC event
    with the exception CLASS NAME only — never format_exc(), never the message body
    (a traceback could contain the prompt/terms). There is no `print(...)` anywhere.
  - Function URL access log: the watchlist arrives in the POST BODY, never the query
    string, so the access log records method/path/IP only, never the terms.
  - third-party DEBUG: root + noisy libs pinned to WARNING at import (security.md).

BUDGET (never.md #7): the real Aurora-backed `search` sub-budget is checked BEFORE
the model call. FAIL CLOSED — if the ledger is unreachable for ANY reason, we do
NOT call the model and return the honest paused state. No budget check, no spend.

ITEMS: Aurora first (hard 3s), baked items.json fallback; the response says which
source it used ("source": "aurora" | "baked") so a live/baked divergence is never
silent.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from collections import deque

# db/ is shipped alongside the package in the zip.
sys.path.insert(0, "db")

# Silence third-party DEBUG at the root so nothing downstream can log request text
# (security.md: third-party DEBUG is a packet/term egress path).
logging.getLogger().setLevel(logging.WARNING)
for _n in ("botocore", "boto3", "urllib3", "strands", "bedrock"):
    logging.getLogger(_n).setLevel(logging.WARNING)

from porchlight.log import bind_context, generate_run_id, get_logger  # noqa: E402
from porchlight.watch.validate import validate_watchlist  # noqa: E402

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
CORS_ORIGIN = os.environ.get("PORCHLIGHT_CORS_ORIGIN", "https://porch-light-ventura.vercel.app")
AURORA_READ_TIMEOUT_S = 3.0

log = get_logger("porchlight.watcher.lambda")

# --- IP rate limit: SECOND layer only. Reserved concurrency (2) is the real cap;
# this per-instance in-memory window resets on cold start (documented in
# KNOWN-LIMITATIONS). 10 requests / 60s / IP per warm instance. ---
_RATE_MAX = 10
_RATE_WINDOW_S = 60
_ip_hits: dict[str, deque] = {}


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    dq = _ip_hits.setdefault(ip, deque())
    while dq and now - dq[0] > _RATE_WINDOW_S:
        dq.popleft()
    if len(dq) >= _RATE_MAX:
        return True
    dq.append(now)
    return False


def _cors_headers() -> dict:
    return {
        "content-type": "application/json",
        "access-control-allow-origin": CORS_ORIGIN,       # never "*"
        "access-control-allow-methods": "POST, OPTIONS",
        "access-control-allow-headers": "content-type",
        "vary": "Origin",
    }


def _resp(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": _cors_headers(), "body": json.dumps(body, ensure_ascii=False)}


def _baked_items() -> dict[str, str]:
    """The verified items baked into the zip at build time (fallback source)."""
    try:
        with open(os.path.join(os.path.dirname(__file__), "items.json"), encoding="utf-8") as f:
            data = json.load(f)
        return {row["item_id"]: row["en_text"] for row in data if row.get("en_text")}
    except Exception:
        return {}


def _aurora_items_with_timeout() -> dict[str, str] | None:
    """Read verified items from Aurora, but never block longer than 3s (§ answer 1).

    Returns the item map on success, or None on timeout/error (caller falls back to
    baked). Runs the query in a worker thread and abandons it after the timeout so a
    paused-cluster resume can never hang the request.
    """
    import threading

    result: dict = {}

    def _work():
        try:
            import data_api  # from db/
            be = data_api.get_backend()
            r = be.query(
                "SELECT i.item_id, ir.en_text FROM item_rewrites ir "
                "JOIN items i ON i.item_id = ir.item_id "
                "WHERE ir.en_verified = true AND ir.en_text IS NOT NULL"
            )
            result["items"] = {row["item_id"]: row["en_text"] for row in r.rows}
        except Exception as exc:  # logged as class name only, no message
            result["error"] = type(exc).__name__

    th = threading.Thread(target=_work, daemon=True)
    th.start()
    th.join(AURORA_READ_TIMEOUT_S)
    if th.is_alive() or "items" not in result:
        return None
    return result["items"] or None


def _aurora_window_with_timeout() -> dict | None:
    """Read the corpus window the watcher actually searches — earliest/latest
    meeting_date across stored documents + the document count — from Aurora, bounded
    by the same 3s guard as the items read. Returns {earliest, latest,
    document_count} (ISO date strings copied from source, never generated) or None.

    The window travels AS DATA on the response so the page can name the range it
    holds without parsing rendered text (never.md #1: dates copied, not generated).
    None -> the page renders no window note rather than guessing one.
    """
    import threading

    result: dict = {}

    def _work():
        try:
            import data_api  # from db/
            be = data_api.get_backend()
            r = be.query(
                "SELECT min(m.meeting_date)::text AS earliest, "
                "max(m.meeting_date)::text AS latest, "
                "count(DISTINCT d.document_id) AS document_count "
                "FROM meetings m JOIN documents d ON d.meeting_id = m.meeting_id"
            )
            if r.rows:
                result["window"] = r.rows[0]
        except Exception as exc:  # logged as class name only, no message
            result["error"] = type(exc).__name__

    th = threading.Thread(target=_work, daemon=True)
    th.start()
    th.join(AURORA_READ_TIMEOUT_S)
    if th.is_alive() or "window" not in result:
        return None
    w = result["window"] or {}
    if not w.get("earliest") or not w.get("latest"):
        return None
    return {"earliest": w["earliest"], "latest": w["latest"],
            "document_count": w.get("document_count")}


def _budget_ok_or_paused() -> bool | None:
    """Check the real search sub-budget. FAIL CLOSED (§ answer 2):
    - True  -> budget available, proceed.
    - False -> budget exhausted, return paused.
    - None  -> ledger UNREACHABLE; treat as paused, do NOT call the model.
    """
    try:
        import data_api
        from porchlight.pipeline import ledger

        be = data_api.get_backend()
        ledger.check_before_run(be, "search")   # raises BudgetExhausted if spent
        return True
    except Exception as exc:
        name = type(exc).__name__
        if name == "BudgetExhausted":
            log.warning("watch_budget_exhausted")
            return False
        # Ledger unreachable for any other reason: fail closed, no model call.
        log.warning("watch_budget_unreachable", error=name)
        return None


def _record_spend(cost_usd: float, run_id: str) -> None:
    """Best-effort spend record against the search sub-budget. Never raises into the
    response path (a failed record must not turn a good answer into a 500)."""
    if cost_usd <= 0:
        return
    try:
        import data_api
        from porchlight.pipeline import ledger

        be = data_api.get_backend()
        ledger.record_model_spend(be, run_id, cost_usd, MODEL_ID, "search")
    except Exception as exc:
        log.warning("watch_spend_record_failed", error=type(exc).__name__)


def _client_ip(event: dict) -> str:
    ctx = (event.get("requestContext") or {}).get("http") or {}
    return ctx.get("sourceIp") or "unknown"


def handler(event, context):
    """Function URL invokes this. Body: {"terms": [str, ...]}. Returns the view."""
    method = ((event.get("requestContext") or {}).get("http") or {}).get("method", "POST")
    if method == "OPTIONS":
        return {"statusCode": 204, "headers": _cors_headers(), "body": ""}

    run_id = generate_run_id()
    bind_context(component="watcher", run_id=run_id, model_id=MODEL_ID)

    # Rate limit (second layer; reserved concurrency is the real cap).
    ip = _client_ip(event)
    if _rate_limited(ip):
        log.warning("watch_rate_limited")   # no IP in the log line
        return _resp(429, {"degraded": True, "reason": "rate_limited",
                           "note": "Too many requests. Please wait a moment."})

    # Parse + validate the body. Terms are DATA — never logged, never executed.
    try:
        payload = json.loads(event.get("body") or "{}")
        raw_terms = payload.get("terms", [])
    except Exception:
        return _resp(400, {"degraded": True, "reason": "bad_request", "note": "Invalid request."})

    result = validate_watchlist(raw_terms if isinstance(raw_terms, list) else [])
    if not result.ok:
        # Validation reasons may echo a term; return generic, do not log the terms.
        return _resp(400, {"degraded": True, "reason": "invalid_watchlist",
                           "note": "Please check your watch terms (max 10, 100 characters each)."})
    terms = list(result.terms)
    if not terms:
        return _resp(200, {"matches": [], "is_quiet": True, "source": "none"})

    # Budget gate BEFORE the model call, fail closed.
    ok = _budget_ok_or_paused()
    if ok is not True:
        return _resp(200, {"degraded": True, "reason": "paused", "source": "none",
                           "note": "The live watcher is paused right now."})

    # Items: Aurora first (3s), baked fallback. Say which source.
    items = _aurora_items_with_timeout()
    source = "aurora"
    corpus_window = None
    if items:
        # Same request, same DB: the window the watcher actually searched. Bounded by
        # its own 3s guard; None on any failure (the page then shows no window note).
        corpus_window = _aurora_window_with_timeout()
    if not items:
        items = _baked_items()
        source = "baked"
    if not items:
        return _resp(200, {"degraded": True, "reason": "no_items", "source": "none",
                           "note": "No agenda items are available right now."})

    log.info("watch_request", term_count=len(terms), item_count=len(items), source=source)

    # Run the REAL matcher (allowlist hook + turn cap enforced inside).
    try:
        from porchlight.watch.matcher import match_watchlist

        answer = match_watchlist(terms, items, model_id=MODEL_ID, log=log)
    except Exception as exc:
        # Static error only — never the traceback, never the message, never terms.
        log.error("watch_handler_error", error_type=type(exc).__name__)
        return _resp(200, {"degraded": True, "reason": "error", "source": source,
                           "note": "The live watcher could not answer right now."})

    if getattr(answer, "degraded", False):
        return _resp(200, {"degraded": True, "reason": "matcher_degraded", "source": source,
                           "note": "The live watcher could not fully check your list."})

    # Bug 1 + Bug 8, site (b): the response-boundary trust check. An item is a match
    # only if it has non-empty matched_terms AND at least one term shares a content
    # word with the item's stored text — the same single predicate record_match uses,
    # given the same item text (items[m.item_id]). A different trust boundary (what
    # leaves the proxy), so it earns its own placement.
    from porchlight.watch.matcher import is_recordable_match

    matches = [
        {
            "item_id": m.item_id,
            "matched_terms": list(m.matched_terms),
            "reason": {"en": m.reason.en, "es": m.reason.es},
        }
        for m in answer.matches
        if is_recordable_match(m.matched_terms, items.get(m.item_id, ""))
    ]
    log.info("watch_response", matches=len(matches), is_partial=answer.is_partial, source=source)
    body = {
        "matches": matches,
        "is_quiet": len(matches) == 0,
        "is_partial": answer.is_partial,
        "source": source,
        "model_id": MODEL_ID,
    }
    if corpus_window:
        body["window"] = corpus_window
    return _resp(200, body)
