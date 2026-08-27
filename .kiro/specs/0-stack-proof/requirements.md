# Requirements Document

## Introduction

Spec 0 proves the stack works end-to-end before any product code is written. It covers repo hygiene and hackathon compliance, a trivial Strands agent running locally and deployed to AgentCore, the local development database, cloud project creation, observability wiring, and cost allocation tags. Everything here is either impossible to add retroactively (run_id, tags) or is the riskiest unknown in the project (AgentCore deployment).

## Glossary

- **Agent**: A Strands Agents SDK (Python) application that uses a ReAct loop with scoped tools.
- **AgentCore**: AWS Bedrock AgentCore, the deployment target for agents. Accessed via the AgentCore CLI (`npm i -g @aws/agentcore`).
- **Spike**: A timeboxed experiment with pass/fail criteria written before starting.
- **Run_ID**: A unique identifier per agent run in the format `run_YYYYMMDDTHHMMSSZ_<short_random>`, propagated to every log line.
- **Cost_Tags**: AWS resource tags: Project=PorchLight, Env=<env>, Owner=shara, Purpose=hackathon-agents-for-humans.
- **Local_DB**: The Postgres+pgvector instance run via `docker compose up -d` for local development only.
- **Neon_Project**: The production Postgres+pgvector instance hosted on Neon.
- **Vercel_Project**: The frontend hosting project on Vercel.

## Requirements

### Requirement 1: Repository Compliance

**User Story:** As a hackathon judge, I want the repository to meet all "newly created" and disclosure rules, so that the submission is not disqualified.

#### Acceptance Criteria

1. THE Repo SHALL contain a file named LICENSE (or LICENSE.txt) whose full text is a valid MIT or Apache-2.0 license.
2. THE Repo SHALL contain a README with the line: "A prior weekend prototype of this idea exists at github.com/earlgreyhot1701D/civiq; none of its code is used here."
3. THE Repo SHALL contain a .gitignore that includes a pattern excluding `.env`.
4. THE Repo SHALL have its first commit dated on or after Aug 10, 2026. (Standing constraint: final commit on or before Sep 13, 2026, verified at Spec 7.)
5. THE Repo SHALL contain a pinned dependency lockfile for Python packages in which every dependency specifies an exact version (no open ranges).
6. THE README SHALL state the exact pinned version of the Strands Agents SDK, and that version SHALL match the version recorded in the lockfile.
7. IF `.env` or any file matching `*.pem`, `*.key`, or `credentials*` exists in the git history, THEN THE Repo SHALL fail compliance (no secrets may appear in any commit).

### Requirement 2: Spike A — Local Strands Agent

**User Story:** As a developer, I want a trivial Strands agent with two tools running locally, so that the SDK is proven to work before attempting deployment.

#### Acceptance Criteria

1. WHEN Spike A is invoked locally, THE Agent SHALL call both registered tools and return a response that includes each tool's output, demonstrating that the SDK tool-calling loop executed both.
2. THE Agent SHALL use the Strands Agents SDK at the version pinned in the lockfile.
3. WHEN Spike A completes successfully, THE Agent SHALL emit one or more structured JSON log lines, each containing at minimum a `run_id` field, to stdout or a local log file.
4. IF a tool call fails during Spike A execution, THEN THE Agent SHALL exit with a non-zero status and emit a JSON log line containing the `run_id` and an error indication.

### Requirement 3: Spike B — AgentCore Deployment

**User Story:** As a developer, I want the same trivial agent deployed to AgentCore via direct code deployment (.zip, no container), so that the riskiest unknown in the project is resolved first.

#### Acceptance Criteria

1. WHEN a request is sent to the deployed AgentCore endpoint, THE Agent SHALL return a non-error response containing the expected tool-generated output within 30 seconds.
2. THE Deployment SHALL use direct code deployment (.zip upload via the AgentCore CLI), not a container image.
3. IF Spike B fails to deploy or respond within 4 hours of effort, THEN THE Team SHALL stop and re-plan rather than push forward.
4. WHEN the deployed agent completes a request, THE System SHALL emit a structured JSON log line containing a `run_id` to the designated CloudWatch log group.

### Requirement 4: Local Development Environment

**User Story:** As a contributor cloning the repo for the first time, I want a single command to produce a working database, so that setup is frictionless.

#### Acceptance Criteria

1. WHEN `docker compose up -d` is run from a fresh clone with `.env.example` copied to `.env`, THE Local_DB SHALL reach Docker health status `healthy` within 60 seconds, with the `vector`, `pg_trgm`, and `unaccent` extensions enabled in the `porchlight` database.
2. THE Local_DB SHALL accept connections using the `DATABASE_URL` value in `.env.example` without modification to that value or to `docker-compose.yml`.
3. WHEN the `db` container health check passes, THE Local_DB SHALL accept SQL queries on `localhost:5432` using the `porchlight` user and database specified in `.env.example`.
4. WHEN the named volume `porchlight_pgdata` is removed and `docker compose up -d` is re-run, THE Local_DB SHALL re-execute `db/init/001-extensions.sql` and return to a healthy state with all three extensions enabled.

### Requirement 5: Cloud Projects Created

**User Story:** As a developer, I want Neon and Vercel projects to exist (empty but reachable), so that later specs can deploy without provisioning delays.

#### Acceptance Criteria

1. THE Neon_Project SHALL exist with the `vector` extension installed, verifiable by a successful `SELECT 1 FROM pg_extension WHERE extname = 'vector'` query over the production connection string.
2. THE Neon_Project connection string SHALL be documented in `.env.example` as a commented-out template showing the variable name and `postgresql://` URI format without real credentials.
3. THE Vercel_Project SHALL exist, be linked to the repository, and its default `.vercel.app` URL SHALL return a response served by Vercel (HTTP 200 or Vercel's own placeholder page), not a DNS resolution failure, within 10 seconds.
4. THE Repo SHALL NOT contain any secret values (tokens, passwords, API keys, or connection strings containing credentials); all credentials SHALL be referenced only via `.env` (excluded by `.gitignore`) with commented-out placeholder templates in `.env.example` that show variable name and value format only.

### Requirement 6: Observability Skeleton

**User Story:** As a developer, I want structured logging with run_id from the first line of code, so that observability does not need to be retrofitted.

#### Acceptance Criteria

1. THE Agent SHALL generate a Run_ID in the format `run_YYYYMMDDTHHMMSSZ_<random>` at the start of each run, where `<random>` is exactly 8 lowercase alphanumeric characters.
2. THE Agent SHALL emit logs as structured JSON, one event per line, where each event contains at minimum the fields: `timestamp` (ISO 8601), `level`, `component`, `run_id`, and `message`.
3. THE Agent SHALL include the Run_ID in every log line emitted during a run.
4. THE Agent SHALL write logs to a CloudWatch log group named `/porchlight/<env>/<component>`, where `<env>` is the deployment environment and `<component>` is one of `hunter`, `extractor`, `watcher`, or `spike` (the last valid for Spec 0 only; product components arrive in later specs).
5. IF an exception or error condition occurs during a run, THEN THE Agent SHALL emit a structured log event at level `error` containing the Run_ID and an indication of the failure before halting or continuing.

### Requirement 7: Cost Allocation Tags

**User Story:** As the project owner, I want cost allocation tags on every AWS resource from day one, so that spend is trackable and tags do not need to be retrofitted.

#### Acceptance Criteria

1. THE Deployment SHALL apply the following four tags to every AWS resource created by the project's infrastructure definitions: `Project`=`PorchLight`, `Env`=<the target environment identifier>, `Owner`=`shara`, `Purpose`=`hackathon-agents-for-humans`.
2. WHEN a new AWS resource is created by the deployment, THE resource SHALL be verifiable as carrying all four required tags via the AWS CLI (`aws resourcegroupstaggingapi get-resources`) or the resource's describe/list-tags API within 60 seconds of creation.
3. WHEN a spike deployment completes, THE Developer SHALL enumerate created resources via `aws resourcegroupstaggingapi get-resources` (or equivalent describe/list-tags API), confirm all four tags are present, and document any resource type that does not support tagging. (Automated enforcement becomes a requirement in a later spec once infrastructure-as-code exists to enforce it.)

### Requirement 8: Model Invocation Proven

**User Story:** As a developer, I want to confirm that Bedrock model invocation works in our target region before building agents that depend on it, so that access issues surface immediately rather than mid-build.

#### Acceptance Criteria

1. WHEN a Converse or InvokeModel call is made to the target Bedrock region using Amazon Nova Lite (`amazon.nova-lite-v1:0`), THE call SHALL return a successful (non-error) response. Nova Lite is the Spec 0 model because it has no AWS Marketplace subscription gate; the production model is chosen at Spec 3 on measured evidence.
2. THE README SHALL record the AWS region and that Spec 0 proved invocation on Nova Lite, and SHALL state that production model selection is deferred to Spec 3 with a documented comparison.
3. IF the call fails due to access, permissions, or subscription issues, THEN THE Team SHALL resolve the blocker before proceeding to Spec 1.
4. IF Nova Lite fails and cannot be resolved within the 2-hour timebox, THEN THE Team SHALL fall back to another non-Marketplace model family (Nova Micro, Mistral, Meta, DeepSeek, Qwen, or OpenAI on Bedrock), record the substitute in the README, and continue. The timebox applies to the entire model-proving effort, not per model.
5. THE README SHALL state that later specs MUST NOT assume a model provider that was never proven at invocation time.

### Requirement 9: AgentCore CLI Installed

**User Story:** As a developer, I want a single authoritative `agentcore` command from the current CLI, so that no naming conflict with the deprecated toolkit causes confusion during deployment.

#### Acceptance Criteria

1. THE AgentCore CLI (`@aws/agentcore`) SHALL be installed globally via npm.
2. THE legacy Python starter toolkit (`bedrock-agentcore-starter-toolkit`) SHALL NOT be present in any pip, pipx, or uv environment on the development machine.
3. WHEN `agentcore --version` is run, THE output SHALL resolve to the `@aws/agentcore` npm package and report a version number.

### Requirement 10: Agent Toolkit for AWS Configured

**User Story:** As a developer, I want the AWS MCP Server available in Kiro from day one, so that infrastructure tasks can use agent skills without mid-build setup delays.

#### Acceptance Criteria

1. THE Repo SHALL contain `.kiro/settings/mcp.json` with the AWS MCP Server configured using `uvx mcp-proxy-for-aws` pinned to an explicit version.
2. `uv` SHALL be installed as a prerequisite on the development machine.
3. AWS credentials SHALL be available locally (via environment, profile, or SSO) such that the MCP server can authenticate.
4. WHEN a documentation-search call is made through the configured MCP server, THE call SHALL return a successful response containing relevant content.

### Requirement 11: Spike Discipline

**User Story:** As a developer, I want pass/fail criteria written before starting each spike and a timebox enforced, so that spikes remain experiments rather than commitments.

#### Acceptance Criteria

1. WHEN a spike is started, THE Developer SHALL have documented pass/fail criteria and a timebox duration (maximum 60 minutes unless explicitly justified) in the spike's commit message or spec file before writing any spike code.
2. IF a spike exceeds its declared timebox without meeting its pass criteria, THEN THE Team SHALL stop work on the spike and record a decision to either allocate a new timebox with revised criteria, pivot to an alternative approach, or abandon the spike.
3. WHEN a spike passes its criteria within the timebox, THE Developer SHALL commit the result with a reference to the pass/fail criteria it satisfied.

### Requirement 12: Model Selection Is Deferred and Measurable

**User Story:** As the project owner, I want the production model chosen on evidence rather than assumption, so that cost and quality are both defensible.

#### Acceptance Criteria

1. THE Spec 0 code SHALL read the model id from configuration (environment variable), never hardcode it, so that swapping models at Spec 3 requires no code change.
2. THE README SHALL state that model selection is deferred to Spec 3 and name the two numbers that will decide it: verifier rejection rate on the same real packets, and measured cost per packet.
3. THE Spec 0 logging SHALL include the model id in structured log events, so that any measurement run is attributable to a specific model.

> **Clarification (does not conflict with never.md §7 / decisions §20f):** The ban on silent model fallback prohibits a degraded run quietly switching providers mid-flight and presenting the result as normal. A deliberate, documented, configuration-level model choice made on measured evidence is the opposite of that. The test: did a human choose it and write down why, or did the system substitute on its own during a run.

### Requirement 13: Live Smoke Tests

**User Story:** As a developer, I want live capability checks that re-run independently of the spike scripts, so that a broken deployment surfaces immediately rather than at demo time.

#### Acceptance Criteria

1. THE Repo SHALL register a `live` pytest marker in `pyproject.toml`, excluded from the default test run via `addopts = "-m 'not live'"`.
2. THE Repo SHALL contain a Makefile target `smoke` that runs `pytest -m live`.
3. `tests/live/test_smoke_model.py` SHALL make one real Converse call to the configured model in the configured region, assert a non-empty response, and assert the client's resolved region and model id against deliberate literal expected values (not derived from config) so that a misconfiguration is caught rather than confirmed.
4. `tests/live/test_smoke_agentcore.py` SHALL invoke the Spike B deployed endpoint, assert a response containing values only the remote system could produce (the Spike A greeting text, a UTC time, and a run_id matching the `run_YYYYMMDDTHHMMSSZ_<8 hex>` pattern). It SHALL skip with a clear message if the endpoint environment variable is unset, and FAIL on any error from an endpoint that exists. (Written as part of task 11, not before.)
5. THE README SHALL contain a section "Verifying a clean clone" documenting `make smoke`, roughly what it costs, that it makes real AWS calls and writes real CloudWatch log entries, and what a skip means versus a failure.
6. Each live test SHALL assert on at least one value that could only originate from the remote system (generated response text, a server-produced identifier, a non-zero measured latency). Assertions solely on values derived from local configuration do not satisfy this criterion.
7. THE live tests SHALL skip (not fail) ONLY when no credentials are configured at all (`NoCredentialsError` or no resolvable credential chain). Any other error (expired tokens, access denied, throttling, timeout, region errors) SHALL cause a test failure. A broad try/except that converts an error into a skip is forbidden.
8. THE default `pytest` run SHALL NOT execute any live test. Verify by running plain `pytest` after the marker is registered and confirming the live tests report as deselected.
