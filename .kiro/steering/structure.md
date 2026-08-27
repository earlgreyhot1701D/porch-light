---
inclusion: always
---
# Porch Light — Structure

- One file, one responsibility. No god files. If a file needs "and" to describe it, split it.
- `adapters/` (CivicPlus/Ventura parsing, pure deterministic), `agents/` (hunter, extractor, watcher — one module each plus their tools), `verify/` (the six-check rewrite verifier, pure functions), `search/` (bridge table, lexical, vector, fusion), `web/` (public site + read-only API), `pipeline/` (scheduler entry, run lock, queue, spend ledger), `db/` (schema, migrations), `tests/` (including fixtures built from real Ventura documents and one deliberately poisoned PDF).
- Spec-driven: work moves as Kiro specs in `.kiro/specs/<block>/` — requirements.md, then design.md, then tasks.md, each approved before the next. One spec per block, in order: 0 stack-proof, 1 adapter, 2 ingestion, 3 extraction, 4 search, 5 watch, 6 ui, 7 package.
- **`design/porch-light-ui-v1.html` is the accepted UI and a strict copy contract, not inspiration.** See `ui-contract.md` (loads automatically on html/css/js work). Copy its structure, tokens, copy, and ARIA exactly; propose before deviating.
- Also at root: `docker-compose.yml` + `db/init/` (local Postgres+pgvector only, never deploy), `.env.example`, `fixtures/` (`sample.json` and hostile `ugly.json`, §25).
- Mock data first, then wire APIs. Never wire APIs to a broken layout. The bridge between them is the fixture: the mock reads `fixtures/sample.json` shaped to the real view contract, so wiring is a path swap (§25).
- Stub, don't half-build: out-of-scope means a comment stub with implementation notes, never partial behavior.
