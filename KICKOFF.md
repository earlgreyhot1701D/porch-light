# Porch Light — Kiro Kickoff Prompt

*Paste everything below the line as your first message to Kiro in this workspace.*
*Last updated Aug 22, 2026 — reflects decisions §25 (fixtures) and §26 (deployment).*

---

You are building **Porch Light** with me. Before doing anything, read your steering files in `.kiro/steering/`. Eight load on every interaction; `accessibility.md` loads when you touch html, css, or js. They are binding. Then read `docs/agenda-watch-decisions.md` (the product source of truth, 26 sections) and `docs/porch-light-build-plan.md` (the dated schedule). The accepted UI is `design/porch-light-ui-v1.html` — a design contract for later, not code to import now.

## What this is

A Strands Agents SDK build for the AWS "Agents for Humans" hackathon (Good Neighbor track, submitting Sep 13). An agent that watches City of Ventura's public meeting agendas for one person, summarizes matches in English and Spanish with a receipt on every claim, and drafts the structure of a public comment that only the human can finish and send.

Python. Three agents (hunter, extractor, watcher) with three least-privilege IAM roles. Deterministic verifiers on every model output. Deployment topology per §26: agents to **Bedrock AgentCore via direct code deployment** (a .zip — **no Docker in the deploy path**), frontend and read-only API to **Vercel**, schedule on **EventBridge**, database on **Neon** Postgres with pgvector. `docker-compose.yml` exists for local development only.

## How we work — this is a contract

- **Spec-driven, one block at a time.** We start at Spec 0. You write `requirements.md`, I approve it, then `design.md`, I approve, then `tasks.md`, then we implement task by task.
- **Propose, then wait.** Never deliver an implementation of anything I have not approved. Present options with trade-offs rather than pre-building your preference.
- **Do not refactor code outside the current task's scope.** Ever.
- If anything I ask for contradicts `never.md` or the decisions doc, refuse and cite the file.
- Every block ends with a PASS/FAIL check against its gate before the next begins.
- Verify against actual files and the actual live site, not memory.

## Your first job: Spec 0 — Stack proof

Create `.kiro/specs/0-stack-proof/requirements.md` and **stop for my approval**. Spec 0 covers:

1. **Repo hygiene.** MIT or Apache license file. README skeleton carrying the disclosure line: "A prior weekend prototype of this idea exists at github.com/earlgreyhot1701D/civiq; none of its code is used here." A `.gitignore` that excludes `.env`. Lockfile discipline. Git from commit one — commit dates inside the hackathon window are the compliance evidence for the "newly created" rule.

2. **Spike A.** A trivial Strands agent with two tools, running locally. Pass: it calls both tools correctly. Pin the Strands SDK version and record it in the README.

3. **Spike B.** The same trivial agent deployed to AgentCore using **direct code deployment** (.zip, no container). Pass: it responds from the deployed endpoint. **This is the riskiest unknown in the project.** If it fights us, we stop and re-plan rather than push on.

4. **Local development environment.** `docker compose up -d` brings up Postgres with pgvector using the existing `docker-compose.yml` and `db/init/`. Pass: a clean clone reaches a working database in one command. This is for the "a stranger can clone and run it" gate, never for deployment.

5. **Cloud projects created.** A Neon project (Postgres + pgvector) and a Vercel project, both empty but existing, with connection details recorded in `.env` from `.env.example`. No secrets in the repo.

6. **Observability skeleton.** A `run_id` generated per run in the sortable format `run_YYYYMMDDTHHMMSSZ_<short random>`, propagated to every log line. Structured JSON logging, one event per line. CloudWatch log group naming `/porchlight/<env>/<component>`.

7. **Cost allocation tags active** on every resource the spikes create: `Project=PorchLight`, `Env`, `Owner=shara`, `Purpose=hackathon-agents-for-humans`. This and the `run_id` wiring are both impossible to add retroactively, which is why they are in Spec 0 rather than later.

8. **Spike discipline.** Write pass/fail criteria before starting each spike, and timebox the setup before we reassess.

Write requirements as testable acceptance criteria, not implementation. Do not write `design.md` yet. Do not scaffold the rest of the project. Ask me about anything genuinely ambiguous rather than assuming.
