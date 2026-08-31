"""W6: extract (in memory) -> rewrite -> verify -> persist, on meeting 3687.

One controlled fetch already done (_3687.pdf). Items extracted deterministically
below from the verbatim text (item number + page range + text copied from the PDF,
artifacts intact). Runs the rewrite stage LIVE (Nova Lite) against a local DB, then
prints the full unsummarized output, retry/fallback counts, and actual pre-rounding
cost.
"""
from __future__ import annotations
import os
from pathlib import Path

from db import data_api
from porchlight.log import bind_context, generate_run_id
from porchlight.rewrite.stage import run_rewrite_stage
from porchlight.rewrite import model as rewrite_model
from porchlight.verify.models import SourceRecord

MODEL_ID = "amazon.nova-lite-v1:0"
DOC_URL = "https://www.cityofventura.ca.gov/AgendaCenter/ViewFile/Agenda/_08262026-3687"

# Verbatim item text copied from _3687.pdf (artifacts intact: û ô ö Æ). Page ranges
# from the PDF. Items 2 and 3 both begin on p2 and continue to p3.
ITEMS = [
    ("3687-1", "1", (2, 2),
     "1. Approval of the Minutes\n\nApproval of the draft minutes from the June 24, 2026 meeting.\n\n"
     "Recommendation:  Approve, as presented.\n\nMaterials: draft minutes"),
    ("3687-2", "2", (2, 3),
     "2. Prohousing Designation, Citywide\n\nThe City is applying for a Prohousing Designation to the State of "
     "California Department of Housing and Community Development. This designation recognizes jurisdictions that "
     "are committed to accelerating housing production, removing barriers to development, and implementing "
     "housing-friendly policies. Staff is presenting the draft application for comments and review.\n\n"
     "Recommendation: To approve the draft Prohousing Designation application and formal resolution.\n\n"
     "Staff:  Andrea Palmer, Senior Management Analyst; Rachel Wess, Management Analyst\nApplicant:  City of Ventura\n\n"
     "Materials: staff report, application, resolution, public comment"),
    ("3687-3", "3", (2, 3),
     "3. PROJ-25-0914 Loretta Court Apartments Located at APN: 073-0-058-030\n\n"
     "Request for Major Design Review to develop a new, 19-unit multi-family residential apartment development "
     "with 3 Warrants (Lot width, Tuck-Under Parking, & 60% 3rd story) and 1 Exception (Parking Setback), on a "
     "12,540-square foot site in the Urban General 1 (T4.1 Main St. Frontage) Zone within the Downtown Specific "
     "Plan and is commonly identified as AssessorÆs Parcel Number 073-0-058-030 (Project Site).\n\n"
     "California Environmental Quality Act: 15332 (Infill Projects)\n\n"
     "Recommendation: To approve the project, as conditioned.\n\n"
     "Planner:  Grant White, Acting Senior Planner\nApplicant:  Linda Blackbern of RRM Design Group on behalf of "
     "Merewether Trust\n\nMaterials: staff report, vicinity map, resolution, development standards, plans, public "
     "comment, public comment 2"),
    ("3687-4", "4", (3, 3),
     "4. PROJ-25-0933 1193 Colina Vista Addition\n\nRequest for a Major Variance to allow an increase in building "
     "height in the hillside area for a renovation project that includes construction of a 1,903-square-foot "
     "second-story addition to an existing single-story residence, along with interior renovations to the first "
     "floor (Project). The Project is located on a 0.28-acre lot in the R-1-10 (Single-Family Residential) zone "
     "with a land use designation of Neighborhood Very Low 2, located at 1193 Colina Vista and is commonly "
     "identified as Assessor's Parcel Number 065-0-224-095 (Project Site).\n\n"
     "California Environmental Quality Act: 15301 (Existing Facilities, Class 1)\n\n"
     "Recommendation: To continue to a date certain of October 28, 2026.\n\n"
     "Planner:  Adams Bernhardt, Senior Planner\nApplicant:  James McGarry, James McGarry Architecture\n\n"
     "Materials: continuance memo, public comment"),
]


def _records():
    out = []
    for item_id, num, pages, text in ITEMS:
        out.append((item_id, SourceRecord(
            body="planning_commission", meeting_date="2026-08-26", item_number=num,
            page_range=pages, text=text, deadline=None, source_url=DOC_URL)))
    return out


def _seed(be, run_id):
    be.execute(Path("db/schema.sql").read_text(encoding="utf-8"))
    for t in ("item_rewrites", "items", "documents", "meetings", "body_status", "bodies", "spend_ledger"):
        be.execute(f"DELETE FROM {t}")
    be.execute("INSERT INTO bodies (body_id, name_en, category) VALUES ('planning_commission','Planning Commission','advisory')")
    be.execute("INSERT INTO meetings (meeting_id, body_id, meeting_date, meeting_type) VALUES ('3687','planning_commission','2026-08-26'::date,'regular')")
    be.execute("INSERT INTO documents (document_id, meeting_id, url, role, status) VALUES ('doc3687','3687',%s,'agenda','done')", [DOC_URL])
    for item_id, num, pages, _ in ITEMS:
        be.execute("INSERT INTO items (item_id, document_id, item_number, page_start, page_end) VALUES (%s,'doc3687',%s,%s,%s)",
                   [item_id, num, pages[0], pages[1]])


def main():
    run_id = generate_run_id()
    bind_context(component="spike", run_id=run_id, model_id=MODEL_ID)
    be = data_api.get_backend()
    _seed(be, run_id)

    records = _records()
    summary = run_rewrite_stage(be, run_id, records, model_id=MODEL_ID,
                                client=rewrite_model.boto3.client("bedrock-runtime"))

    # Read back what was persisted and print FULL, unsummarized.
    print("\n" + "#" * 78)
    print(f"# W6 LIVE RUN — meeting 3687, Planning Commission, 2026-08-26")
    print(f"# run_id={run_id}  model={MODEL_ID}")
    print("#" * 78)
    for item_id, num, pages, _ in ITEMS:
        row = be.query("SELECT * FROM item_rewrites WHERE item_id=%s", [item_id]).rows[0]
        rec = next(r for iid, r in records if iid == item_id)
        print(f"\n{'='*78}\nITEM {num}  (item_id={item_id})")
        print(f"RECEIPT: Planning Commission | 2026-08-26 | Item {num} | pp. {pages[0]}-{pages[1]} | {DOC_URL}")
        print(f"  en_verified={row['en_verified']} (attempts {row['en_attempts']})  "
              f"es_verified={row['es_verified']} (attempts {row['es_attempts']})")
        print(f"\n--- ENGLISH ---\n{row['en_text']}")
        if row['note_en']:
            print(f"[EN NOTE] {row['note_en']}")
        print(f"\n--- SPANISH ---")
        if row['es_text']:
            print(row['es_text'])
        else:
            print(f"[ES ABSENT] {row['es_absent_note']}")

    print(f"\n{'#'*78}\n# COUNTS")
    print(f"  items: {summary.items}")
    print(f"  body_unnamed (EN did not name the record's body): {summary.body_unnamed}")
    print(f"  EN verified: {summary.en_verified}   EN fallback: {summary.en_fallback}")
    print(f"  ES verified: {summary.es_verified}   ES fallback: {summary.es_fallback}")
    print(f"  ES recovered on retry (verified on 2nd attempt): {summary.es_recovered_on_retry}")
    print(f"  actual cost (summed pre-rounding): ${summary.cost_usd:.6f}")
    print("#" * 78)


if __name__ == "__main__":
    main()
