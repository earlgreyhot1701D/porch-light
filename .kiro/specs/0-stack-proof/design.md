# Design Document: Spec 0 — Stack Proof

## Overview

Spec 0 produces proof that the stack works end-to-end before any product code is written. The deliverables are:

1. A **logging module** (production code, imported by later agents)
2. A **trivial spike agent** exercising that logging module locally and deployed to AgentCore
3. **Repository hygiene** (license, disclosure, lockfile, .gitignore)
4. **Local dev database** (already exists via docker-compose.yml)
5. **Cloud projects** created (Neon with pgvector, Vercel placeholder)
6. **Cost tags** on every AWS resource
7. **Model invocation proven** (Nova Lite via Bedrock Converse)
8. **Tooling installed** (AgentCore CLI, Agent Toolkit MCP config)

The only code that survives past Spec 0 is the logging module and config module. Everything else is either a one-time proof (spikes), infrastructure provisioning (Neon/Vercel/tags), or configuration (.kiro/settings/mcp.json).

### Scope boundary

This design does NOT cover: hunter/extractor/watcher agents (Specs 2-5), database schema (later spec), the full observability stack (OTEL traces arrive later), or any product UI.

---

## Decisions (approved)

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Logging library | **structlog** | contextvars binding lets run_id attach once and appear on every log line during a run, including stdlib logs from boto3 and Strands internals (Req 6.3). Processor pipeline is the secondary benefit. |
| 2 | Log routing | **stdout-first** | Simplest path. Fallback ladder defined below. |
| 3 | Package layout | **src/porchlight/** | Standard Python src layout. Prevents accidental local imports. |
| 4 | Lockfile | **uv.lock authoritative** | Export to requirements.txt for deploy zip as a build step, never by hand. |

---

## Architecture

```
porch-light/
├── src/
│   └── porchlight/
│       ├── __init__.py
│       ├── log.py              ← PRODUCTION CODE. The structured logger.
│       └── config.py           ← Reads env vars, provides typed config.
├── spikes/
│   └── spike_a/
│       ├── __init__.py
│       ├── agent.py            ← Trivial Strands agent with 2 tools.
│       └── tools.py            ← Two trivial tools.
├── deploy/
│   └── spike_b/
│       ├── main.py             ← AgentCore entrypoint
│       └── agentcore/
│           └── agentcore.json  ← AgentCore deployment config
├── scripts/
│   └── build_deploy_zip.py    ← Build step: install package + export reqs → staging → zip
├── tests/
│   └── test_log.py            ← Property tests for the logging module.
├── pyproject.toml
├── uv.lock                     ← Pinned lockfile (exact versions, authoritative)
├── .env.example                ← EXISTS (no secrets, templates only)
├── docker-compose.yml          ← EXISTS
├── db/init/001-extensions.sql  ← EXISTS
├── .gitignore
├── LICENSE
├── README.md
└── .kiro/
    └── settings/
        └── mcp.json            ← Agent Toolkit for AWS config
```

### Key decisions reflected here

- `src/porchlight/` is the importable package. Later specs add `agents/`, `adapters/`, `verify/`, etc. as sibling packages or submodules under `src/`.
- `spikes/` is throwaway. It proves things work but is not imported by production code.
- `deploy/spike_b/` is the AgentCore deployment artifact directory. The build step produces the zip.
- Module is named `log.py`, not `logging.py`, to avoid shadowing stdlib `logging` when structlog routes through it.

---

## Components and Interfaces

### Component 1: Logging Module (`src/porchlight/log.py`)

This is the most important deliverable. It is production code that all later agents import.

**Responsibilities:**
- Generate a `run_id` at the start of each agent run
- Emit structured JSON log events (one per line) with required fields
- Bind `run_id`, `component`, and `model_id` to contextvars so they appear on every log line during a run, including logs from third-party libraries (boto3, Strands internals) that use stdlib logging
- Enforce the redaction rule: extra fields are size-capped, and any field flagged as document content is refused (security.md: logs never contain packet text)
- Write to stdout (local dev and deployed; CloudWatch captures stdout)

**Why the module is allowed to fail open:** §7 bans failing open for user-facing results. Observability is not a user-facing result. A dropped log line is acceptable; a fabricated or silently-degraded search result, match, or draft is not. The logger never raises, never crashes the caller, and never suppresses a user-facing error to protect itself. This distinction is stated here so it is not later cited against the code incorrectly.

**Public interface:**

```python
# Valid components. Validated at bind time.
VALID_COMPONENTS = {"spike", "hunter", "extractor", "watcher"}

def generate_run_id() -> str:
    """Returns run_YYYYMMDDTHHMMSSZ_<8 char lowercase alphanumeric>"""

def bind_context(*, component: str, run_id: str, model_id: str | None = None) -> None:
    """Binds run_id, component, and model_id to contextvars.
    Configures structlog to route stdlib logging through the same processor chain.
    Raises ValueError if component not in VALID_COMPONENTS.
    """

def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Returns a structlog logger. Context (run_id, component, model_id)
    is injected automatically from contextvars on every event."""
```

Every log event emits one JSON line containing at minimum:
```json
{
  "timestamp": "2026-08-23T14:30:00.123Z",
  "level": "info",
  "component": "spike",
  "run_id": "run_20260823T143000Z_a1b2c3d4",
  "message": "Tool hello_tool completed",
  "model_id": "amazon.nova-lite-v1:0"
}
```

`model_id` is included when bound; field absent (not null) when not applicable.

**structlog configuration:**
- Processor chain: contextvars injection → extra field redaction/size-cap → timestamper (UTC, ISO 8601) → JSON renderer
- stdlib logging integration: `structlog.stdlib.ProcessorFormatter` applied to the root logger, so boto3/Strands/any stdlib logger's output passes through the same chain and inherits the bound context
- Output: stdout only. No boto3 CloudWatch dependency in the logger.

**Redaction rules (enforces security.md: "logs never contain packet text"):**
- Extra fields have a size cap (default: 512 characters). Exceeded fields are truncated with a `"[truncated:{original_length}]"` marker.
- Any field whose key contains `source_text`, `packet_text`, `document_content`, or `page_content` is omitted entirely, replaced with `"[redacted:document_content]"`.
- Rationale: this is the structural enforcement point. Individual callers cannot accidentally log packet text through this module.

---

### Component 2: Config Module (`src/porchlight/config.py`)

Reads environment variables, provides typed access. Keeps the rest of the codebase free of `os.environ` calls.

```python
@dataclass(frozen=True)
class PorchlightConfig:
    env: str                # dev | staging | prod
    aws_region: str         # us-east-1 (§29: AgentCore Runtime + Agent Registry availability)
    model_id: str           # amazon.nova-lite-v1:0 (from BEDROCK_MODEL_ID env var)
    component: str          # spike | hunter | extractor | watcher (validated)
    log_group: str          # computed: /porchlight/{env}/{component}

def load_config(component: str) -> PorchlightConfig:
    """Load from environment. Component is passed at the call site, not from env.
    Raises ValueError if component not in VALID_COMPONENTS.
    Raises on missing required env vars with a clear message naming the var."""
```

The `model_id` comes from the `BEDROCK_MODEL_ID` environment variable. This satisfies Requirement 12.1: swapping models at Spec 3 requires only changing the env var.

`component` is passed as an argument to `load_config()`, not read from the environment. There is one source of truth for this value: the call site.

---

### Component 3: Spike A Agent (`spikes/spike_a/`)

A trivial Strands agent with two tools. Its only job is to prove the SDK works locally and that logging emits correctly.

```python
# spikes/spike_a/tools.py
from strands import tool
from datetime import datetime, timezone

@tool
def hello_tool(name: str) -> str:
    """Returns a greeting."""
    return f"Hello, {name}!"

@tool
def time_tool() -> str:
    """Returns current UTC time."""
    return datetime.now(timezone.utc).isoformat()
```

```python
# spikes/spike_a/agent.py
from strands import Agent
from porchlight.log import generate_run_id, bind_context, get_logger
from porchlight.config import load_config
from spikes.spike_a.tools import hello_tool, time_tool

config = load_config(component="spike")
run_id = generate_run_id()
bind_context(component=config.component, run_id=run_id, model_id=config.model_id)
logger = get_logger(__name__)

logger.info("spike_a_start")
agent = Agent(tools=[hello_tool, time_tool])
result = agent("Say hello to Porch Light and tell me the time.")
logger.info("spike_a_complete", result_preview=str(result)[:200])
```

**Note on Strands API:** The exact constructor parameters (`Agent(tools=..., ...)`) and model configuration must be verified against the pinned SDK version before writing task code. The design uses the documented public API shape; if the pinned version differs, the task implementation adjusts.

Pass criteria (written before code, per Requirement 11):
- Agent calls both tools (visible in response)
- At least one structured JSON log line emitted with valid `run_id`
- Exit 0 on success, non-zero on failure

---

### Component 4: Spike B Deployment (`deploy/spike_b/`)

Same agent logic, packaged for AgentCore direct code deployment.

**Entrypoint pattern** (shape from AgentCore docs; exact import paths verified at task time):

```python
# deploy/spike_b/main.py
from strands import Agent
from porchlight.log import generate_run_id, bind_context, get_logger
from porchlight.config import load_config
from tools import hello_tool, time_tool

# AgentCore entrypoint (exact decorator/app pattern verified against CLI version at task time)
def handler(prompt: str) -> str:
    config = load_config(component="spike")
    run_id = generate_run_id()
    bind_context(component=config.component, run_id=run_id, model_id=config.model_id)
    logger = get_logger(__name__)

    logger.info("spike_b_invocation_start", prompt_length=len(prompt))
    agent = Agent(tools=[hello_tool, time_tool])
    result = agent(prompt)
    logger.info("spike_b_invocation_complete")
    return str(result)
```

#### Build step: packaging the zip

Symlinks in zip archives are unreliable across tooling. The build step uses `uv pip install`:

```bash
# scripts/build_deploy_zip.py (or equivalent shell)
# 1. Create a clean staging directory
# 2. Install the porchlight package into it:
#    uv pip install . --target deploy/spike_b/_staging
# 3. Export requirements for the runtime:
#    uv export --format requirements-txt > deploy/spike_b/_staging/requirements.txt
# 4. Copy entrypoint + tools + agentcore.json into staging
# 5. Zip the staging directory contents
```

This guarantees `porchlight` is importable at the zip root without path hacks. The build is a single script, not a manual action.

#### Drift guard (Requirement 1.6)

The Strands SDK version lives in three places: `uv.lock`, the exported `requirements.txt`, and the README. To prevent drift:
- The export (`uv export`) is regenerated as part of the deploy build, never by hand.
- A check in the build script verifies `requirements.txt` matches `uv.lock` before packaging. If they differ, the build fails with a clear message.
- The README records the version; updating it is a task step whenever the lockfile changes.

#### Deployment config (`agentcore.json`)

```json
{
  "name": "porchlight-dev-spike",
  "framework": "strands",
  "entrypoint": "main.py",
  "deploymentType": "codeZip",
  "runtime": "python3.12",
  "tags": {
    "Project": "PorchLight",
    "Env": "dev",
    "Owner": "shara",
    "Purpose": "hackathon-agents-for-humans"
  }
}
```

**Runtime:** `python3.12`. The design uses 3.12 rather than 3.13 because AgentCore and Strands SDK support for 3.13 is unverified. If both are confirmed to support 3.13 before task implementation, it can be bumped. A runtime mismatch would surface as a Spike B failure that looks like a deployment problem, which is exactly why we verify first.

Pass criteria for Spike B:
- `agentcore deploy` succeeds
- Invoking the deployed endpoint returns a non-error response within 30 seconds
- CloudWatch contains at least one structured JSON line with a valid `run_id` and `component: "spike"`
- All four cost tags visible on created resources

---

### Component 5: CloudWatch Log Routing

**Chosen approach: stdout-first.**

For local development, logs go to stdout. When deployed to AgentCore, logs written to stdout are captured by CloudWatch automatically.

**Fallback ladder (written now, not discovered later):**

1. **First attempt:** Configure the log group name in `agentcore.json` (if supported). Spike B proves or disproves this.
2. **If agentcore.json cannot control the log group name:** Keep stdout. Accept AgentCore's auto-generated group name. Rely on `component` in the JSON payload for filtering. Amend Requirement 6.4 to match reality (component as the discriminator, not group name).
3. **Only if the payload approach also fails** (AgentCore strips or reformats stdout): Fall back to a direct boto3 CloudWatch Logs sink in the logging module.

**Regardless of which level the fallback reaches:** `component` is in every log event as the primary discriminator. Filtering works at every level of the ladder because the structured payload always contains it.

---

## Data Models

### Run ID

```
Format: run_YYYYMMDDTHHMMSSZ_<random>
Example: run_20260823T143000Z_a1b2c3d4

Components:
- Prefix: "run_" (literal)
- Timestamp: UTC, compact ISO 8601 (no separators except T and Z)
- Separator: "_"
- Random: exactly 8 lowercase alphanumeric chars [a-z0-9]
```

Generated once at the start of each agent invocation using `datetime.now(timezone.utc)`. Propagated to every log line, every downstream call, every trace span.

### Structured Log Event

```json
{
  "timestamp": "string (ISO 8601 with milliseconds, UTC)",
  "level": "string (debug | info | warning | error)",
  "component": "string (spike | hunter | extractor | watcher)",
  "run_id": "string (run_id format)",
  "message": "string (event description)",
  "model_id": "string (optional, present when a model is in use)",
  "...extra": "any additional structured fields (size-capped, redaction-filtered)"
}
```

Rules:
- One event per line (JSONL format)
- No multiline values (stack traces are single-line escaped)
- `model_id` included when bound in context; field absent (not null) otherwise
- Extra fields are passed through as top-level keys, subject to size cap (512 chars) and redaction filtering
- `component` is validated against `VALID_COMPONENTS`; invalid values are rejected at bind time

### Cost Tags

Applied to every AWS resource:

| Tag Key | Value | Notes |
|---------|-------|-------|
| Project | PorchLight | Fixed |
| Env | dev / staging / prod | From config |
| Owner | shara | Fixed |
| Purpose | hackathon-agents-for-humans | Fixed |

### Environment Variables (additions to .env.example)

```bash
# ---- Model (Spec 0: Nova Lite; Spec 3 decides production model) ----
BEDROCK_MODEL_ID=amazon.nova-lite-v1:0
```

Note: `PORCHLIGHT_COMPONENT` is NOT in .env.example. Component is passed at the call site via `load_config(component="spike")`. One source of truth.

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

The logging module is the only production code in Spec 0 and the primary target for property-based testing. The spikes, infrastructure provisioning, and compliance checks are integration/smoke tests.

### Property 1: Run ID format validity

*For any* invocation of `generate_run_id()`, the returned string SHALL match the pattern `run_\d{8}T\d{6}Z_[a-z0-9]{8}`, the timestamp portion SHALL represent a valid UTC datetime, and the random suffix SHALL be exactly 8 lowercase alphanumeric characters.

**Validates: Requirements 6.1**

### Property 2: Structured log event completeness

*For any* valid combination of level (from {debug, info, warning, error}), component (from VALID_COMPONENTS), run_id (valid format), message string, and optional model_id, formatting the event SHALL produce a single line of valid JSON containing at minimum the fields `timestamp`, `level`, `component`, `run_id`, and `message` with their provided values, plus `model_id` when supplied.

**Validates: Requirements 6.2, 6.3, 6.5, 2.3, 2.4, 12.3**

### Property 3: Log group name derivation

*For any* valid environment name (from {dev, staging, prod}) and component name (from VALID_COMPONENTS), the log group path SHALL equal `/porchlight/{env}/{component}` with no leading/trailing whitespace and no double slashes.

**Validates: Requirements 6.4**

### Property 4: Run ID uniqueness

*For any* set of 1000 sequential calls to `generate_run_id()`, no two returned values SHALL be identical.

**Validates: Requirements 6.1**

### Property 5: Redaction and size-cap enforcement

*For any* extra field value exceeding the size cap (512 characters), or *for any* extra field whose key matches a document-content pattern (`source_text`, `packet_text`, `document_content`, `page_content`), the emitted log event SHALL contain a truncation marker (`[truncated:{original_length}]`) or omission marker (`[redacted:document_content]`) in place of the original value, and SHALL NOT contain the original content.

**Validates: Requirements 6.2, 6.3**

---

## Error Handling

### Logging module errors

The logger itself must never raise (see "Why the module is allowed to fail open" above). If JSON serialization fails on an extra field, the logger:
1. Falls back to a safe representation (repr of the value, still size-capped)
2. Emits the event with a `_serialization_warning` field
3. Never drops the event, never crashes the caller

### Component validation

`bind_context()` and `load_config()` validate that `component` is in `VALID_COMPONENTS`. A typo'd component raises `ValueError` immediately rather than silently creating a new log group. This prevents the kind of thing that costs an hour at 11pm.

### Spike agent errors

- Tool failure: log at level `error` with the exception info, exit non-zero (Requirement 2.4)
- Model invocation failure: log at level `error`, include model_id, exit non-zero
- Missing environment variable: `load_config()` raises immediately with a clear message naming the missing var

### Deployment errors

- `agentcore deploy` failure: captured in spike pass/fail log, triggers re-plan per Requirement 3.3
- CloudWatch delivery failure: does not crash the agent. Logs remain on stdout. This is observability degrading, not results degrading. Acceptable per the fail-open distinction above.

---

## Testing Strategy

### Property-based tests (logging module)

Library: **Hypothesis** (the standard Python PBT library).

Each property test runs a minimum of 100 iterations with generated inputs. Tests live in `tests/test_log.py`.

| Property | What's generated | What's asserted |
|----------|-----------------|-----------------|
| 1: Run ID format | (nothing - pure function, called repeatedly) | Regex match, valid datetime parse, 8-char random |
| 2: Log event completeness | Random level (from enum), component (from VALID_COMPONENTS), run_id (valid format), message (text), optional model_id (text or None) | Valid JSON, all required fields present with correct values |
| 3: Log group name | Random env (from {dev, staging, prod}), component (from VALID_COMPONENTS) | Matches `/porchlight/{env}/{component}` exactly |
| 4: Run ID uniqueness | 1000 calls | Set size equals list size (no duplicates) |
| 5: Redaction/size-cap | Random field key (some matching document-content patterns), random field value (some exceeding 512 chars) | Emitted event contains markers, never raw content |

Tag format: `# Feature: 0-stack-proof, Property {N}: {title}`

### Unit tests (specific examples)

- Config loading with all vars set
- Config loading with missing required var (raises with var name)
- Config loading with invalid component (raises ValueError)
- Logger creation and single event output
- Error-level event includes error indication
- Redaction of a field named `source_text`
- Truncation of a 1000-char extra field

### Integration tests (spike pass/fail)

- Spike A: invoke locally, verify both tools called, verify log output
- Spike B: deploy to AgentCore, invoke, verify response, verify CloudWatch log
- Docker: `docker compose up -d` from clean state, verify health + extensions
- Tags: after Spike B deploy, enumerate resources, verify all four tags
- Model: Converse call to Nova Lite succeeds

### Smoke tests (compliance)

- LICENSE file exists and matches MIT or Apache-2.0
- README contains disclosure line
- .gitignore excludes .env
- uv.lock contains exact versions (no open ranges)
- requirements.txt matches uv.lock (drift guard)
- No secrets in git history
- `agentcore --version` resolves to @aws/agentcore
- `.kiro/settings/mcp.json` exists with pinned mcp-proxy-for-aws version
- MCP documentation-search call succeeds

### Live smoke tests (`@pytest.mark.live`)

Driven by `.kiro/steering/testing.md` obligation 1: every spec that proves a live capability leaves a re-runnable test marked `@pytest.mark.live`.

**Infrastructure:**
- `pyproject.toml`: register `live` marker, add `addopts = "-m 'not live'"` so `pytest` never hits the network by default
- `Makefile`: target `smoke` runs `pytest -m live -v`
- `tests/live/__init__.py` + individual test modules

**test_smoke_model.py** (written at Spec 0):
```python
# Deliberate literals — these are the expected values, not derived from config.
# Tests are allowed to hardcode expected values. That is what an assertion is.
EXPECTED_REGION = "us-east-1"
EXPECTED_MODEL_ID = "amazon.nova-lite-v1:0"

@pytest.mark.live
def test_bedrock_converse_responds():
    """One real Converse call. Asserts non-empty response, correct region, correct model."""
    # Skip ONLY on NoCredentialsError (no credentials configured at all).
    # Fail on everything else: expired tokens, access denied, throttling, timeout.
    # Assert:
    #   - client.meta.region_name == EXPECTED_REGION
    #   - config.aws_region == EXPECTED_REGION (catches config drift)
    #   - response text is non-empty (value from remote system)
    #   - model_id in response matches EXPECTED_MODEL_ID
```

**test_smoke_agentcore.py** (written as part of task 11):
```python
@pytest.mark.live
def test_agentcore_endpoint_responds():
    """Invoke deployed Spike B endpoint. Assert response from the remote system."""
    # Skip ONLY if AGENTCORE_SPIKE_ENDPOINT env var is unset.
    # Fail on any error from an endpoint that exists.
    # Assert:
    #   - response contains Spike A greeting text and a UTC time
    #   - response or its log carries a run_id matching run_YYYYMMDDTHHMMSSZ_<8 hex>
    #   - non-zero measured latency (value only the remote could produce)
```

**Skip vs Fail boundary (Requirement 13.7):**
- SKIP: `botocore.exceptions.NoCredentialsError` or unset endpoint env var. Meaning: "not proven on this machine."
- FAIL: everything else (expired, denied, throttled, timeout, region mismatch). Meaning: "the live system is broken or unreachable."
- Never wrap the call in a broad try/except that converts errors into skips.

**README section "Verifying a clean clone":**
```
## Verifying a clean clone

make smoke

Runs live smoke tests against AWS. Makes real AWS calls and writes real
CloudWatch log entries. Costs < $0.01 per run (one Converse call + one
AgentCore invoke).

Tests skip (not fail) if credentials or endpoint are absent.
A skip means "not proven on this machine."
A failure means "the live system is broken or unreachable."
```
