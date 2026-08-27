# Porch Light — Build Plan and Schedule

**Written:** Sat, Aug 22, 2026 (PT). **Submission closes:** Mon, Sep 14, 5:00 PM PT. **23 days.**
**Internal deadline: submit Sun, Sep 13.** The last day is for nothing. That is the point of it.

**Where the PRD lives, decided:** `agenda-watch-decisions.md` is the source of truth and is not duplicated. Under spec-driven development, each Kiro spec's `requirements.md` is generated from the decisions doc one block at a time and is the executable PRD for that block. This document is the schedule: what happens when, and what gates it.

Method reminders that govern every block: propose → approve → implement. QA checkpoint PASS/FAIL before the next block starts. Mock data first, then wire. Stub, don't half-build. Verify against actual files and the live site.

---

## The calendar

| Dates | Spec | Work | Pass gate |
| --- | --- | --- | --- |
| **Aug 23–25** | **0 — Stack proof** | Repo (license, civiq disclosure, first commit). Kiro steering ×9. Agent Toolkit + rule file. AgentCore CLI. **Spike A** (trivial Strands agent, 2 tools, local). **Spike B** (same agent deployed to AgentCore via **direct code deploy — no Docker**, §26). `docker compose up -d` for local Postgres+pgvector. Neon project created. Vercel project created. Cost tags + `run_id` wiring. | Hello-world responds from AgentCore. `docker compose up -d` gives a working DB from a clean clone. Tags visible in Cost Explorer. One log line with a run_id in the right log group. |
| **Aug 25–27** | **1 — Ventura adapter** | Read ToU + robots.txt first. Real body list, real URLs. Deterministic parsing, all edge cases (cancelled / amended / supplemental / Spanish variants). Ingestion horizon + surfacing rules with tests from real documents. **Set all 14 thresholds before Spec 2.** | Correct meeting list for a known week, checked by hand against the live site. Stale-agenda tests pass. |
| **Aug 27–29** | **2 — Ingestion + hunter** | Hash change detection, run lock with TTL + heartbeat, idempotency, run log, good-citizen fetch posture, hunter loop with hooks. | Second run on unchanged data does nothing and says so. Crashed-and-restarted run double-writes nothing. |
| **Aug 29–Sep 2** | **3 — Extraction + rewrite + verifier** | Extractor loop, scoped tools, caps that demonstrably fire. Rewrite chain (EN → verify → ES → verify against source). Six-check verifier. **Measure cost per packet, extrapolate to a month.** Decide rewrite call path (Strands vs Converse) at spec start. **Choose the production model on measured evidence (§27): run Nova Lite and a Claude model against identical packets, compare verifier rejection rate and cost per packet.** **Define the view contract and convert the mock to `fixtures/sample.json` + hostile `fixtures/ugly.json` (§25).** Build deadline rendering (city local time, labeled, DST test). Decide what the packet panel shows with real data. **Draft the video script here** — if the demo can't be narrated in 5 minutes, cut scope now. | Page ranges spot-checked by hand against the PDF. Caps fire on an oversized packet. Verifier rejects a corrupted rewrite in both languages. Cost math works. **The mock renders correctly from both fixtures, including the ugly one. The model comparison is recorded with both numbers.** |
| **Sep 2–4** | **4 — Search** | Vocabulary bridge, lexical, pgvector, rank fusion. Fail-closed on embedding provider outage. Rate limit + embedding cache + search sub-budget. | "Can they put a bar next to my house" returns the permit item. Provider offline → honest empty state, never a fabricated result. |
| **Sep 4–7** | **5 — The watch** | Watcher **invoked live from the web layer, not scheduled (§26c)** — watchlist transmitted, never stored. Required reasons in the same output. First-open baseline. Draft scaffold (no stance fields). Local-storage watchlist + drafts, fragment share links with confirm-before-apply. Watcher rate limit + client-side match cache + its own spend sub-budget. Guardrails on the two narrow surfaces. Three execution roles + the fourth narrow Vercel-invoke identity, all verified distinct. **Ship the corrected privacy string (§26c).** | Briefing carries a plain-language reason on every match. Crafted share link shows contents, never auto-applies. Scaffold contains no position. Extractor role has no egress. Reopening the page does not re-run the agent. |
| **Sep 7–9** | **6 — UI wiring** | Deploy the web layer to **Vercel**. Because of §25 this is now a **path swap**: point the UI at the live endpoint instead of `fixtures/sample.json`. Remaining nine §16b failure states wired and `aria-live`'d. Public reading log. Honest dormancy. | Full WCAG 2.1 AA sweep. Every failure state reachable and announced. Real packet, real receipt, real jump-to-page. Nothing in the layout breaks that the ugly fixture did not already catch. |
| **Sep 9–12** | **7 — Package** | Golden set + published accuracy number (AgentCore evaluators). Poisoned PDF with passing containment test incl. draft-steering case. README with clean-clone setup + seeded sample data. Architecture diagram. **Record + caption the video.** builder.aws.com post (the 0.6). Devpost text. Pre-submission checklist end to end. | A stranger can clone and run it. Video under 5:00, captioned. Checklist in the brief passes. |
| **Sep 12–13** | **Buffer + submit** | Fix what the checklist caught. **Submit Sep 13.** | Submitted, confirmed, screenshot kept. |
| Sep 14 | Held empty | The day is the margin. | — |
| Oct 15 | **8 — Wind-down** | Execute §13 as written on day one: keep / park / take down, handoff note, WINS.md entry. | Written record exists either way. |

**Slack analysis:** roughly 1.5 days of real buffer. Spec 3 absorbed the fixture-contract work from §25, which makes it the fullest block in the plan; if anything slips, it slips here. That is the right place for it to slip, because the alternative was discovering the same work at Spec 6 with no room left. The two places most likely to eat it are Spec 3 (cost surprises) and Spec 7 (the video always takes longer than planned). The mitigations are already scheduled: cost is measured at Spec 3 with a fallback decision (daily cadence, narrower corpus) made *there*, and the video script is drafted at Spec 3 so recording at Spec 7 is execution, not invention.

## Standing items, not date-bound

- LinkedIn URL and repo URL → About footer placeholders.
- Fluent Spanish reviewer; first question is the gendered greeting (§23). Fallback if none found: README states the Spanish surface is unverified (§8).
- "Human approved" badge wording on the social card: reconsider before anything public.
- USPTO check on the name before brand investment beyond the hackathon.
- Devto/build-story notes: capture as you go, not at the end (feeds both the builder.aws post and the dev.to writeup).
- **builder.aws.com posts are 0.2 each, up to 0.6 for three.** Planned three: (1) the build kickoff and the deterministic-verifier thesis, (2) **the Nova vs Claude comparison with rejection-rate data (§27d)**, (3) the ship post. Post 1 can go up as early as Spec 2.

## Done already

Housekeeping (Builder ID, Devpost registration, credits form). UI v1 both states + scaffold. Brand kit. All planning docs.
