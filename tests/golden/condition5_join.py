"""Condition-5 join: two real meetings, storage -> deployed extractor -> verified
rewrites persisted in Aurora. Real fetches, real runtime invoke, real rows.

Steps per meeting (3685 City Council, 3687 Planning Commission):
  1. Seed document_pages: ONE controlled fetch of the agenda (respects the fetch
     module's host allowlist, single lock, backoff), verify the content hash matches
     the stored document_id, extract + upsert per-page text. Idempotent.
  2. Invoke the DEPLOYED extractor runtime with the stored pages; collect the
     structured items from the porchlight_result envelope.
  3. Persist items rows (item_id = "<meeting>-<n>").
  4. Build (item_id, SourceRecord) and run the rewrite+verify+persist stage.

Prints the full unsummarized output + counts + cost. Captures the deployed response
envelope for the contract test.

Run: AURORA_CLUSTER_ARN=... AURORA_SECRET_ARN=... AURORA_DATABASE=porchlight \
     BEDROCK_MODEL_ID=amazon.nova-lite-v1:0 AWS_REGION=us-east-1 \
     uv run python tests/golden/condition5_join.py
"""
from __future__ import annotations

import json
import os
import time

import boto3

from db import data_api
from porchlight.adapters.ventura import fetch as vfetch
from porchlight.adapters.ventura.hash import document_id
from porchlight.adapters.ventura.pdftext import extract_pages
from porchlight.log import bind_context, generate_run_id, get_logger
from porchlight.rewrite import model as rewrite_model
from porchlight.rewrite.stage import run_rewrite_stage
from porchlight.verify.models import SourceRecord

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
# The deployed extractor runtime ARN — from env only (no account id in the repo,
# same posture as the deployed-state.json / .cli logs, which are gitignored).
EXTRACTOR_ARN = os.environ.get("AGENTCORE_EXTRACTOR_RUNTIME_ARN")
REGION = os.environ.get("AWS_REGION", "us-east-1")
CONTRACT_DIR = "tests/contracts"

if not EXTRACTOR_ARN:
    raise SystemExit(
        "Set AGENTCORE_EXTRACTOR_RUNTIME_ARN to the deployed extractor runtime ARN. "
        "Not hardcoded: the ARN carries the account id, which never enters a tracked file."
    )

MEETINGS = [
    {
        "meeting_id": "3685", "body_id": "city_council", "body_name": "City Council",
        "meeting_date": "2026-08-25",
        "document_id": "doc_sha256_5cde9f5a484b22df96d45cceb25dc22bdb92ec6fee623e20662ce8b81b79f909",
        "url": "https://www.cityofventura.ca.gov/AgendaCenter/ViewFile/Agenda/_08252026-3685",
    },
    {
        "meeting_id": "3687", "body_id": "planning_commission", "body_name": "Planning Commission",
        "meeting_date": "2026-08-26",
        "document_id": "doc_sha256_d17d08a52bab0e87f2b2f4ce5ea5c222785a1c30cab77a4afbf81226b4dfe457",
        "url": "https://www.cityofventura.ca.gov/AgendaCenter/ViewFile/Agenda/_08262026-3687",
    },
]


def seed_pages(be, m, log) -> int:
    """One controlled fetch; verify hash matches stored id; upsert per-page text."""
    result = vfetch.fetch(m["url"])  # 200 with body; host-allowlisted, single-lock, backoff
    if result.body is None:
        raise RuntimeError(f"{m['meeting_id']}: fetch returned no body (status {result.status})")
    got_id = document_id(result.body)
    if got_id != m["document_id"]:
        # Design-vs-reality guard: the stored id must match, or the page text would
        # not correspond to the stored document. Stop rather than persist mismatched.
        raise RuntimeError(
            f"{m['meeting_id']}: fetched content hash {got_id} != stored {m['document_id']}; "
            f"document changed on the site. Stopping (not persisting mismatched pages)."
        )
    pages = extract_pages(result.body)
    for n, text in enumerate(pages, start=1):
        be.execute(
            "INSERT INTO document_pages (document_id, page_number, text) VALUES (%s, %s, %s) "
            "ON CONFLICT (document_id, page_number) DO UPDATE SET text = EXCLUDED.text",
            [m["document_id"], n, text],
        )
    log.info("pages_seeded", meeting_id=m["meeting_id"], document_id=m["document_id"], pages=len(pages))
    return len(pages)


def read_pages(be, document_id_val: str) -> list[str]:
    r = be.query(
        "SELECT page_number, text FROM document_pages WHERE document_id = %s ORDER BY page_number",
        [document_id_val],
    )
    return [row["text"] for row in r.rows]


def invoke_extractor(pages: list[str], m) -> dict:
    """Invoke the DEPLOYED runtime; return the porchlight_result envelope."""
    client = boto3.client("bedrock-agentcore", region_name=REGION)
    resp = client.invoke_agent_runtime(
        agentRuntimeArn=EXTRACTOR_ARN,
        contentType="application/json",
        accept="application/json",
        payload=json.dumps({
            "pages": pages, "document_id": m["document_id"], "source_url": m["url"],
        }).encode("utf-8"),
    )
    raw = resp["response"].read().decode("utf-8")
    envelope = None
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data: "):
            line = line[6:]
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "porchlight_result" in obj:
            envelope = obj["porchlight_result"]
    if envelope is None:
        raise RuntimeError(f"{m['meeting_id']}: no porchlight_result in deployed response:\n{raw[:800]}")
    return envelope


def persist_items(be, m, items: list[dict], run_id: str) -> list[tuple[str, SourceRecord]]:
    records = []
    for it in items:
        num = it["item_number"]
        pr = it["page_range"]
        item_id = f"{m['meeting_id']}-{num.rstrip('.')}"
        be.execute(
            "INSERT INTO items (item_id, document_id, item_number, page_start, page_end) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (item_id) DO UPDATE SET "
            "document_id=EXCLUDED.document_id, item_number=EXCLUDED.item_number, "
            "page_start=EXCLUDED.page_start, page_end=EXCLUDED.page_end",
            [item_id, m["document_id"], num, pr[0], pr[1]],
        )
        records.append((item_id, SourceRecord(
            body=m["body_id"], meeting_date=m["meeting_date"], item_number=num,
            page_range=(pr[0], pr[1]), text=it["text"], deadline=None, source_url=m["url"],
        )))
    return records


def main() -> None:
    run_id = generate_run_id()
    bind_context(component="spike", run_id=run_id, model_id=MODEL_ID)
    log = get_logger("porchlight.condition5")
    be = data_api.get_backend()
    os.makedirs(CONTRACT_DIR, exist_ok=True)

    all_summaries = {}
    for m in MEETINGS:
        print("\n" + "#" * 78)
        print(f"# {m['meeting_id']} — {m['body_name']} — {m['meeting_date']}")
        print("#" * 78)

        n_pages = seed_pages(be, m, log)
        pages = read_pages(be, m["document_id"])
        print(f"document_pages seeded: {n_pages}")

        envelope = invoke_extractor(pages, m)
        # Capture the deployed response for the contract test (once, from 3687 which
        # has the richer multi-item structure).
        cap = os.path.join(
            CONTRACT_DIR,
            f"extractor_response_{m['meeting_id']}_strands-1.53.0_2026-08-31.json",
        )
        with open(cap, "w", encoding="utf-8") as f:
            json.dump({"porchlight_result": envelope}, f, indent=2, ensure_ascii=False)
        omissions = envelope.get("omissions", [])
        print(f"extractor: accepted={len(envelope['items'])} rejected={len(envelope['rejected'])} "
              f"omissions={len(omissions)} turns={envelope['turns_used']} tokens={envelope['tokens_used']} "
              f"partial={envelope['status']['partially_read']}  (captured -> {cap})")
        for om in omissions:
            # The extractor recorded a deliberate omission; the pipeline logs it so a
            # skipped numbered item is never silent (§46).
            log.warning("pipeline_extractor_omission", meeting_id=m["meeting_id"],
                        item_number=om.get("item_number"), reason=om.get("reason"))
            print(f"  OMISSION: item {om.get('item_number')} — {om.get('reason')}")

        records = persist_items(be, m, envelope["items"], run_id)
        summary = run_rewrite_stage(
            be, run_id, records, model_id=MODEL_ID,
            client=rewrite_model.boto3.client("bedrock-runtime"),
        )
        all_summaries[m["meeting_id"]] = (m, records, summary)

        # Full unsummarized output.
        for item_id, rec in records:
            row = be.query("SELECT * FROM item_rewrites WHERE item_id=%s", [item_id]).rows[0]
            print(f"\n{'='*78}\nITEM {rec.item_number}  (item_id={item_id})")
            print(f"RECEIPT: {m['body_name']} | {m['meeting_date']} | Item {rec.item_number} | "
                  f"pp. {rec.page_range[0]}-{rec.page_range[1]} | {m['url']}")
            print(f"  en_verified={row['en_verified']} (attempts {row['en_attempts']})  "
                  f"es_verified={row['es_verified']} (attempts {row['es_attempts']})")
            print(f"\n--- ENGLISH ---\n{row['en_text']}")
            if row['note_en']:
                print(f"[EN NOTE] {row['note_en']}")
            print("\n--- SPANISH ---")
            print(row['es_text'] if row['es_text'] else f"[ES ABSENT] {row['es_absent_note']}")

    print("\n" + "#" * 78 + "\n# COUNTS PER MEETING\n" + "#" * 78)
    grand_cost = 0.0
    for mid, (m, records, s) in all_summaries.items():
        grand_cost += s.cost_usd
        print(f"\n{mid} {m['body_name']}:")
        print(f"  items: {s.items}")
        print(f"  EN verified: {s.en_verified}  EN fallback: {s.en_fallback}")
        print(f"  ES verified: {s.es_verified}  ES fallback: {s.es_fallback}  "
              f"ES recovered on retry: {s.es_recovered_on_retry}")
        print(f"  body_unnamed: {s.body_unnamed}")
        print(f"  cost (pre-rounding): ${s.cost_usd:.6f}")
    total_items = sum(s.items for _, _, s in all_summaries.values())
    print(f"\nGRAND TOTAL cost (pre-rounding): ${grand_cost:.6f}")
    if total_items:
        print(f"PER-AGENDA cost: ${grand_cost/len(all_summaries):.6f}  "
              f"({len(all_summaries)} agendas, {total_items} items)")


if __name__ == "__main__":
    main()
