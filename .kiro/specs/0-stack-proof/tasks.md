# Implementation Plan: Spec 0 — Stack Proof

## Overview

This plan proves the stack end-to-end before product code is written. The only permanent code is the logging module (`src/porchlight/log.py`) and config module (`src/porchlight/config.py`). Everything else is either throwaway (spikes), infrastructure (Neon/Vercel/tags), or configuration.

Ordering prioritizes riskiest unknowns first: repo hygiene and the logger (cheap, everything imports it), then model invocation (proves Bedrock access), then Spike A (proves SDK locally), then Spike B (proves AgentCore deploy). Infrastructure tasks (Neon, Vercel, docker compose, Agent Toolkit) are independent of the spike chain and sit after.

## Tasks

- [x] 1. Repository hygiene and project skeleton [PERMANENT]
  - [x] 1.1 Create LICENSE, README with disclosure line, .gitignore with `.env` exclusion
    - LICENSE: MIT full text
    - README: include disclosure line verbatim: "A prior weekend prototype of this idea exists at github.com/earlgreyhot1701D/civiq; none of its code is used here."
    - .gitignore: `.env`, `*.pem`, `*.key`, `credentials*`, `__pycache__/`, `.venv/`, `dist/`, `_staging/`
    - _Requirements: 1.1, 1.2, 1.3, 1.7_

  - [x] 1.2 Create `pyproject.toml` with src layout, dependencies (structlog, strands-agents, hypothesis), and generate `uv.lock`
    - Package name: `porchlight`
    - src layout pointing to `src/porchlight/`
    - Pin strands-agents to exact version in lockfile
    - Record pinned Strands version in README (must match lockfile)
    - _Requirements: 1.5, 1.6, 2.2_

  - [x] 1.3 Create `src/porchlight/__init__.py` (empty) and directory structure
    - Create `src/porchlight/`, `spikes/spike_a/`, `deploy/spike_b/`, `scripts/`, `tests/`
    - _Requirements: 1.5_

- [x] 2. Verification: Python 3.12 runtime support [VERIFICATION]
  - [x] 2.1 Verify that both strands-agents and structlog support Python 3.12 at their pinned versions
    - RESULT: PASS. Python 3.12.10, strands-agents 1.53.0, structlog 26.1.0 all import cleanly.
    - _Requirements: 3.2 (zip deploy assumes compatible runtime)_

- [x] 3. Verification: Strands Agent() constructor parameters [VERIFICATION]
  - [x] 3.1 Verify the exact `Agent()` constructor signature at the pinned SDK version
    - RESULT: Agent(model=..., tools=[...]). Parameter is `model` (accepts str), not `model_id`.
    - _Requirements: 2.1, 2.2_

- [x] 4. Logging module: run_id generator [PERMANENT]
  - [x] 4.1 Implement `generate_run_id()` in `src/porchlight/log.py`
    - Format: `run_YYYYMMDDTHHMMSSZ_<8 lowercase alphanumeric>`
    - Use `datetime.now(timezone.utc)` for timestamp
    - Use `secrets.token_hex(4)` or equivalent for random suffix (8 hex chars, lowercase)
    - Pure function, no side effects
    - _Requirements: 6.1_

  - [x] 4.2 Write property test: Run ID format validity (Property 1)
    - **Property 1: Run ID format validity**
    - **Validates: Requirements 6.1**
    - RESULT: 200 iterations, PASS.
    - Tag: `# Feature: 0-stack-proof, Property 1: Run ID format validity`

  - [x] 4.3 Write property test: Run ID uniqueness (Property 4)
    - **Property 4: Run ID uniqueness**
    - **Validates: Requirements 6.1**
    - RESULT: 1000 IDs, 0 duplicates, PASS.
    - Tag: `# Feature: 0-stack-proof, Property 4: Run ID uniqueness`

- [x] 5. Logging module: contextvars binding and stdlib routing [PERMANENT]
  - [x] 5.1 Implement `bind_context()` and `get_logger()` in `src/porchlight/log.py`
    - structlog configured with contextvars injection, stdlib routing via ProcessorFormatter
    - boto3/Strands logs inherit run_id, component, model_id automatically
    - Root logger set to INFO (DEBUG suppressed to avoid boto3 noise)
    - _Requirements: 6.2, 6.3, 6.5, 12.3_

  - [x] 5.2 Write property test: Structured log event completeness (Property 2)
    - **Property 2: Structured log event completeness**
    - **Validates: Requirements 6.2, 6.3, 6.5, 2.3, 2.4, 12.3**
    - RESULT: 200 iterations, PASS.
    - Tag: `# Feature: 0-stack-proof, Property 2: Structured log event completeness`

  - [x] 5.3 Write property test: Log group name derivation (Property 3)
    - **Property 3: Log group name derivation**
    - **Validates: Requirements 6.4**
    - RESULT: 200 iterations, PASS.
    - Tag: `# Feature: 0-stack-proof, Property 3: Log group name derivation`

- [x] 6. Logging module: redaction and size-cap enforcement [PERMANENT]
  - [x] 6.1 Implement redaction processor in `src/porchlight/log.py`
    - Case-insensitive key matching, recursive into nested dicts and lists
    - Size cap: 512 chars, document-content pattern rejection
    - _Requirements: 6.2, 6.3 (security.md: logs never contain packet text)_

  - [x] 6.2 Write property test: Redaction and size-cap enforcement (Property 5)
    - **Property 5: Redaction and size-cap enforcement**
    - **Validates: Requirements 6.2, 6.3**
    - RESULT: 100+ iterations each (size cap, document patterns, mixed case, nested dicts, nested lists, deeply nested), PASS.
    - Tag: `# Feature: 0-stack-proof, Property 5: Redaction and size-cap enforcement`

- [x] 7. Config module [PERMANENT]
  - [x] 7.1 Implement `src/porchlight/config.py` with `PorchlightConfig` dataclass and `load_config()`
    - BEDROCK_MODEL_ID from env (no default — raises if missing)
    - ENV defaults to dev, AWS_REGION defaults to us-east-1
    - Component passed as argument, validated against VALID_COMPONENTS
    - _Requirements: 12.1, 12.3, 6.4_

  - [x] 7.2 Write unit tests for config module
    - 5 unit tests, all PASS.
    - _Requirements: 12.1_

- [x] 8. Checkpoint
  - 22 tests passing. Checkpoint approved.

- [x] 9. Model invocation proven [THROWAWAY]
  - [x] 9.1 Write a standalone script proving Bedrock Converse call to Nova Lite succeeds
    - Region: us-east-1 (§29). us-west-2 result superseded.
    - RESULT: PASS. Nova Lite responded in us-east-1. See below for final latency/tokens.
    - spikes/prove_model.py created. Structured JSON log with run_id and model_id emitted.
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 10. Spike A: local Strands agent [THROWAWAY]
  - [x] 10.1 Implement `spikes/spike_a/tools.py` with `hello_tool` and `time_tool`
    - Two `@tool` decorated functions, both working.
    - _Requirements: 2.1_

  - [x] 10.2 Implement `spikes/spike_a/agent.py` using verified Agent() signature from task 3.1
    - Agent(model=config.model_id, tools=[hello_tool, time_tool])
    - Uses logging module correctly. Exit non-zero on failure.
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 11.1, 11.3_

  - [x] 10.3 Run Spike A, verify pass criteria
    - RESULT: PASS. Both tools called (hello_tool → "Hello, Porch Light!", time_tool → UTC timestamp).
    - Structured JSON log with run_id emitted. Exit 0.
    - _Requirements: 2.1, 2.3, 11.1, 11.3_

- [ ] 11. Spike B: AgentCore deployment [THROWAWAY]
  - [ ] 11.1 Create `deploy/spike_b/agentcore.json` with deployment config
    - runtime: `python3.12` (confirmed in task 2.1)
    - All four cost tags included
    - deploymentType: `codeZip`
    - framework: `strands`
    - _Requirements: 3.2, 7.1_

  - [ ] 11.2 Create `deploy/spike_b/main.py` entrypoint and copy tools
    - Handler function per AgentCore entrypoint pattern
    - Import porchlight logging and config
    - Same tool logic as Spike A
    - _Requirements: 3.1, 3.4_

  - [ ] 11.3 Implement `scripts/build_deploy_zip.py` build step
    - Install porchlight package into staging dir via `uv pip install . --target`
    - Export requirements via `uv export --format requirements-txt`
    - Verify requirements.txt matches uv.lock (drift guard)
    - Copy entrypoint, tools, agentcore.json into staging
    - Zip staging directory
    - _Requirements: 1.6, 3.2_

  - [ ] 11.4 Deploy Spike B via `agentcore deploy` and verify pass criteria
    - Deploy succeeds
    - Invoke endpoint returns non-error response within 30 seconds
    - CloudWatch contains structured JSON with valid run_id and component "spike"
    - All four cost tags visible on created resources
    - IF fails within 4 hours: stop and re-plan (Req 3.3)
    - Record pass/fail in commit message
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 7.1, 7.2, 11.1, 11.3_

- [ ] 12. Checkpoint
  - Ensure all tests pass, ask the user if questions arise. Spikes proven. If Spike B failed and triggered re-plan, stop here.

- [ ] 13. Cost tag verification [INFRASTRUCTURE]
  - [ ] 13.1 Enumerate resources created by Spike B deploy, verify all four tags present
    - Use `aws resourcegroupstaggingapi get-resources` or describe/list-tags API
    - Document any resource type that does not support tagging
    - _Requirements: 7.2, 7.3_

- [ ] 14. Local development environment verification [INFRASTRUCTURE]
  - [ ] 14.1 Verify `docker compose up -d` reaches healthy with extensions enabled
    - From clean state (remove `porchlight_pgdata` volume first)
    - Verify health status `healthy` within 60 seconds
    - Verify `vector`, `pg_trgm`, `unaccent` extensions enabled
    - Verify connection on `localhost:5432` with porchlight user/db from `.env.example`
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ] 15. Cloud projects created [INFRASTRUCTURE]
  - [ ] 15.1 Create Neon project with pgvector extension
    - Verify `SELECT 1 FROM pg_extension WHERE extname = 'vector'` succeeds
    - Add connection string template to `.env.example` (commented-out, no real credentials)
    - _Requirements: 5.1, 5.2, 5.4_

  - [ ] 15.2 Create Vercel project linked to repository
    - Verify default `.vercel.app` URL returns HTTP 200 or Vercel placeholder within 10 seconds
    - _Requirements: 5.3_

- [ ] 16. AgentCore CLI and Agent Toolkit configuration [INFRASTRUCTURE]
  - [ ] 16.1 Verify AgentCore CLI installed and legacy toolkit absent
    - `agentcore --version` resolves to `@aws/agentcore`
    - Confirm `bedrock-agentcore-starter-toolkit` not in pip/pipx/uv
    - _Requirements: 9.1, 9.2, 9.3_

  - [ ] 16.2 Create `.kiro/settings/mcp.json` with Agent Toolkit for AWS config
    - Configure `uvx mcp-proxy-for-aws` pinned to explicit version
    - Verify documentation-search call returns successful response
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 17. Update .env.example with model config [PERMANENT]
  - [x] 17.1 Add `BEDROCK_MODEL_ID=amazon.nova-lite-v1:0` to `.env.example`
    - Do NOT add `PORCHLIGHT_COMPONENT` (component passed at call site, not from env)
    - _Requirements: 12.1_

- [x] 20. Live smoke test infrastructure [PERMANENT]
  - [x] 20.1 Register `live` marker in pyproject.toml, add `addopts = "-m 'not live'"`
    - RESULT: plain `pytest` reports 25 passed, 1 deselected.
    - _Requirements: 13.1, 13.8_

  - [x] 20.2 Create Makefile with `smoke` target running `pytest -m live -v`
    - _Requirements: 13.2_

  - [x] 20.3 Write `tests/live/test_smoke_model.py`
    - Real Converse call, asserts non-empty response text, region and model_id against deliberate literals
    - Skips ONLY on NoCredentialsError; fails on all other errors
    - RESULT: PASS in us-east-1.
    - _Requirements: 13.3, 13.6, 13.7_

  - [ ] 20.4 Write `tests/live/test_smoke_agentcore.py` (deferred to task 11)
    - _Requirements: 13.4_

  - [x] 20.5 Add "Verifying a clean clone" section to README
    - Documents make smoke, cost, real AWS calls, skip vs fail semantics
    - _Requirements: 13.5_

- [ ] 18. Final README updates and compliance check [PERMANENT]
  - [ ] 18.1 Update README with model invocation proof, deferred selection statement, and Strands version
    - State: AWS region used, Spec 0 proved invocation on Nova Lite
    - State: production model selection deferred to Spec 3, decided by verifier rejection rate and cost per packet
    - State: later specs must not assume a model provider never proven at invocation time
    - Record exact pinned Strands SDK version (must match lockfile)
    - _Requirements: 8.2, 8.5, 12.2, 1.6_

- [ ] 19. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise. Verify: no secrets in git history, LICENSE present, README complete, .gitignore correct, lockfile has exact versions.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

## Notes

- Tasks marked with `*` are optional property/unit test sub-tasks and can be skipped for faster MVP
- Tags: [PERMANENT] = survives past Spec 0 in `src/porchlight/`. [THROWAWAY] = proves something and stops mattering (`spikes/`, standalone scripts). [INFRASTRUCTURE] = one-time provisioning/config. [VERIFICATION] = confirms an assumption before depending on it.
- Spike B (task 11) is intentionally NOT the last task. If it triggers the 4-hour re-plan (Req 3.3), infrastructure tasks 13-16 are still completable independently.
- Verification tasks (2, 3) are placed before the tasks that depend on their results. Do not fold them into implementation.
- The redaction processor (task 6) is NOT optional and is NOT deferred to polish. It enforces security.md's "logs never contain packet text" rule.
- Property tests use Hypothesis. Tag format: `# Feature: 0-stack-proof, Property {N}: {title}`
- Each task references specific requirements for traceability.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "3.1"] },
    { "id": 2, "tasks": ["4.1"] },
    { "id": 3, "tasks": ["4.2", "4.3", "5.1"] },
    { "id": 4, "tasks": ["6.1"] },
    { "id": 5, "tasks": ["5.2", "5.3", "6.2", "7.1"] },
    { "id": 6, "tasks": ["7.2", "9.1"] },
    { "id": 7, "tasks": ["10.1"] },
    { "id": 8, "tasks": ["10.2"] },
    { "id": 9, "tasks": ["10.3"] },
    { "id": 10, "tasks": ["11.1", "11.2"] },
    { "id": 11, "tasks": ["11.3"] },
    { "id": 12, "tasks": ["11.4"] },
    { "id": 13, "tasks": ["13.1", "14.1", "15.1", "15.2", "16.1", "16.2", "17.1"] },
    { "id": 14, "tasks": ["18.1"] }
  ]
}
```
