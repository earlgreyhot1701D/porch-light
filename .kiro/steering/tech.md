---
inclusion: always
---
# Porch Light — Tech

- **Python version: 3.14.** Chosen to match AgentCore Runtime's deployed environment (`PYTHON_3_14`). We run what we ship. All dependencies (strands-agents, boto3, bedrock-agentcore, structlog, hypothesis) declare `>=3.10`, verified at their pinned versions. pyproject.toml sets `requires-python = ">=3.14"`. Local dev uses the same version via `uv python pin 3.14`.

- **Language:** Python. **Agent framework:** Strands Agents SDK (required by the hackathon; pin the exact version in the lockfile and record it in the README).
- **Deploy topology (§26):** agents → **AgentCore via direct code deployment** (.zip, **no Docker in the deploy path**; CodeBuild builds remotely if a container is ever needed). Frontend + read-only API → **Vercel**. Schedule → **EventBridge**, never Vercel Cron. Database → **Neon** Postgres+pgvector.
- **Docker is local-dev only:** `docker-compose.yml` runs Postgres+pgvector so a stranger can clone and run it. It is never the deployment path.
- AgentCore CLI is `npm i -g @aws/agentcore`. Never install the legacy `bedrock-agentcore-starter-toolkit` — same command name, deprecated.
- **The watcher is invoked live, not scheduled (§26c).** Hunter and extractor run hourly on a schedule. The watcher runs when a person opens the page: the browser sends the watchlist, the agent answers, **nothing is stored**. Vercel therefore invokes AgentCore at request time using credentials scoped to the watcher alone — a fourth, narrower identity than the three execution roles. No AWS credentials ever reach the browser.
- **Models (§27):** Spec 0 proves invocation on **Amazon Nova Lite** (`amazon.nova-lite-v1:0`) — no Marketplace subscription gate, fastest path to a proven pipe, commits nothing. **The production model is chosen at Spec 3 on measured evidence**: verifier rejection rate on identical real packets, and cost per packet. **Read the model id from configuration, never hardcode it**, and include it in every structured log event so measurement runs are attributable.
- Rewrite runs at temperature ~0, structured output, no tools. Whether the rewrite goes through Strands or direct Converse is decided at Spec 3 — do not assume.
- A deliberate, documented, config-level model choice is **not** the silent fallback `never.md` bans. The test: did a human choose it and write down why, or did the system substitute on its own mid-run.
- **Store:** Postgres + pgvector. Content-hash document ids. Search = vocabulary bridge (deterministic table) → lexical → vector → rank fusion.
- **Three loops, two of them agents (§38), three least-privilege identities:** the **hunter is deterministic** (a scheduled Lambda — fetch allowlisted host, classify by pure rules, write documents; no model, no ReAct); the **extractor** (AgentCore agent: read documents, write items, **no network egress at all**) and the **watcher** (AgentCore agent: read items, write matches) are the two genuine agents. Extractor and watcher wired Agent-as-Tool; watcher may call extractor; nothing calls outward. The hunter runs on Lambda, not AgentCore, and is not an agent.
- **Turn caps (the two agents only):** extractor 6, watcher 5. Hard token caps. Caps firing is logged and surfaced, it is a feature. The hunter has no turn cap because it is not an agent (§38) — it is a deterministic loop over a fixed work list.
- **Observability:** structured JSON logs, one event per line, `run_id` on every line, per-component CloudWatch log groups `/porchlight/<env>/<component>`, OTEL traces. Resources named `porchlight-<env>-<component>`, tagged Project/Env/Owner/Purpose.
- **Infra assistance:** Agent Toolkit for AWS (build-time only; not part of the product architecture).
- Frontend is plain HTML/CSS/JS matching the accepted mock `porch-light-ui-v1.html`. No framework, no build step.
