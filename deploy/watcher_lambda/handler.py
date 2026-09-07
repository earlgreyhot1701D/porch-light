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


def _baked_items():
    """The verified items baked into the zip at build time (fallback source).

    Returns (text_map, card_map). items.json is a list of card-shaped dicts (Option
    A): each carries `id`, `heading.en` (the text the matcher reads), plus the full
    render fields. Tolerates the older {item_id, en_text} shape so an old zip still
    works (text only, empty cards)."""
    try:
        with open(os.path.join(os.path.dirname(__file__), "items.json"), encoding="utf-8") as f:
            data = json.load(f)
        text_map: dict = {}
        card_map: dict = {}
        for row in data:
            if "heading" in row and isinstance(row.get("heading"), dict):
                iid = row.get("id")
                en = (row["heading"].get("en") or "").strip()
                if iid and en:
                    text_map[iid] = en
                    card_map[iid] = row
            elif row.get("en_text"):  # legacy shape
                text_map[row["item_id"]] = row["en_text"]
        return (text_map or None, card_map)
    except Exception:
        return (None, {})


def _shape_meeting_meta(row: dict) -> dict:
    """Meeting metadata for shape_item, from a joined row. Body name is a proper
    NAME (copied raw, not translated); no ES body name is stored, so the English
    name stands in both languages. The meeting date is copied from the record and
    only its month word is localized by shape_item."""
    from porchlight.web.build_fixture import _fmt_date

    mdate = str(row.get("meeting_date") or "")
    return {
        "meeting_id": row["meeting_id"],
        "body_en": row.get("body_en") or row.get("body_id") or "",
        "body_es": None,  # no stored ES body name -> English name used in both
        "meeting_date_en": _fmt_date(mdate, "en"),
        "meeting_date_es": _fmt_date(mdate, "es"),
        "url": row.get("url") or "",
    }


def _aurora_items_with_timeout():
    """Read verified items from Aurora, but never block longer than 3s (§ answer 1).

    Returns (text_map, card_map) on success, or None on timeout/error (caller falls
    back to baked). `text_map` is {item_id: en_text} — the text the matcher reads.
    `card_map` is {item_id: card_dict} — the full card-shaped payload the page
    renders (Option A), assembled from the SAME request via the shared shape_item so
    any extracted item is renderable, not just the two seeded into sample.json.
    Runs in a worker thread and is abandoned after the timeout so a paused-cluster
    resume can never hang the request.
    """
    import threading

    from porchlight.web.build_fixture import shape_item

    result: dict = {}

    def _work():
        try:
            import data_api  # from db/
            be = data_api.get_backend()
            r = be.query(
                "SELECT i.item_id, i.item_number, i.page_start, i.page_end, "
                "ir.en_text, ir.es_text, ir.en_verified, ir.es_verified, "
                "ir.note_en, ir.es_absent_note, "
                "m.meeting_id, m.meeting_date::text AS meeting_date, "
                "b.name_en AS body_en, d.url "
                "FROM item_rewrites ir "
                "JOIN items i ON i.item_id = ir.item_id "
                "JOIN documents d ON d.document_id = i.document_id "
                "JOIN meetings m ON m.meeting_id = d.meeting_id "
                "JOIN bodies b ON b.body_id = m.body_id "
                "WHERE ir.en_verified = true AND ir.en_text IS NOT NULL"
            )
            text_map = {}
            card_map = {}
            for row in r.rows:
                iid = row["item_id"]
                text_map[iid] = row["en_text"]
                shaped = shape_item(
                    {
                        "num": row["item_number"], "ps": row["page_start"], "pe": row["page_end"],
                        "env": row["en_verified"], "esv": row["es_verified"],
                        "en": row["en_text"], "es": row.get("es_text"),
                        "note_en": row.get("note_en") or "",
                        "es_absent": row.get("es_absent_note") or "",
                    },
                    _shape_meeting_meta(row),
                )
                card_map[iid] = shaped
            result["text"] = text_map
            result["cards"] = card_map
        except Exception as exc:  # logged as class name only, no message
            result["error"] = type(exc).__name__

    th = threading.Thread(target=_work, daemon=True)
    th.start()
    th.join(AURORA_READ_TIMEOUT_S)
    if th.is_alive() or "text" not in result:
        return None
    return (result["text"] or None, result["cards"] or {})


def _aurora_window_with_timeout() -> dict | None:
    """Read the corpus window the watcher actually searches, from Aurora, bounded by
    the same 3s guard as the items read. Returns:
      - earliest, latest: the meeting-date range (ISO, copied from source, never
        generated — never.md #1);
      - meetings_total: meetings in the window;
      - meetings_with_items: meetings that have a READABLE agenda with extracted
        items (the honest coverage number — 11 of 14 today, NOT a document count).
        The gap is the cancellations, which correctly have nothing to extract.
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
                "count(DISTINCT m.meeting_id) AS meetings_total, "
                "count(DISTINCT m.meeting_id) FILTER (WHERE i.item_id IS NOT NULL) "
                "  AS meetings_with_items "
                "FROM meetings m "
                "LEFT JOIN documents d ON d.meeting_id = m.meeting_id "
                "LEFT JOIN items i ON i.document_id = d.document_id"
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
    return {
        "earliest": w["earliest"], "latest": w["latest"],
        "meetings_total": w.get("meetings_total"),
        "meetings_with_items": w.get("meetings_with_items"),
    }


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

    # Items: Aurora first (3s), baked fallback. Say which source. `text_items` is
    # {item_id: en_text} for the matcher; `card_items` is {item_id: card_dict} for
    # the response (Option A — the page renders from the response, not sample.json).
    aurora = _aurora_items_with_timeout()
    source = "aurora"
    corpus_window = None
    if aurora:
        text_items, card_items = aurora
        # Same request, same DB: the window the watcher actually searched. Bounded by
        # its own 3s guard; None on any failure (the page then shows no window note).
        corpus_window = _aurora_window_with_timeout()
    else:
        text_items, card_items = _baked_items()
        source = "baked"
    if not text_items:
        return _resp(200, {"degraded": True, "reason": "no_items", "source": "none",
                           "note": "No agenda items are available right now."})

    log.info("watch_request", term_count=len(terms), item_count=len(text_items), source=source)

    # Run the REAL matcher (allowlist hook + turn cap enforced inside).
    try:
        from porchlight.watch.matcher import match_watchlist

        answer = match_watchlist(terms, text_items, model_id=MODEL_ID, log=log)
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

    matches = []
    for m in answer.matches:
        if not is_recordable_match(m.matched_terms, text_items.get(m.item_id, "")):
            continue
        entry = {
            "item_id": m.item_id,
            "matched_terms": list(m.matched_terms),
            "reason": {"en": m.reason.en, "es": m.reason.es},
        }
        # Option A: the full card-shaped item travels WITH the match so the page
        # renders any extracted item, not just the two seeded into sample.json. If a
        # card is somehow missing (shouldn't happen — same source as the text), the
        # match still returns without it and the page falls back to its sample join.
        card = card_items.get(m.item_id)
        if card:
            entry["item"] = card
        matches.append(entry)
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
