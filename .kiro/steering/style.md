---
inclusion: always
---
# Working style — how we build

- **Approval is risk-gated, not task-gated.** Three tiers:
  - **Do it, then report:** anything fully specified by approved requirements/design, reversible, local, costs nothing, creates no state outside the repo. Work continuously through it.
  - **Propose and wait:** anything that spends money, creates persistent external state (cloud projects, deployments), or where the design deliberately left a choice open. Present options with trade-offs rather than pre-building your preference.
  - **Stop and report immediately:** a checkpoint, any failure, any moment you want to act outside the current task's scope, and **any surprise where the design says X and reality is Y**. Never quietly work around a contradiction — that is the single most expensive thing you can do here.
- At the design stage the old rule still holds: never deliver a finished implementation of an approach not yet approved.
- **DO NOT refactor code outside the current task's scope.** This is the single most important rule in this file.
- If something contradicts the decisions doc or a steering file, say so instead of going along with it. If a task asks for anything in never.md, refuse and cite it.
- Verify against the actual files and the actual live site, not memory.
- Block-by-block with a PASS/FAIL QA checkpoint before the next block. Spikes before commitments: 15-minute reality checks with pass/fail criteria written first.
- Stub, don't half-build. One file, one responsibility. Every threshold gets a value AND a one-line rationale (guessed is fine, unlabeled is not).
- Git from commit one; commits dated inside the hackathon window are the compliance evidence for the "newly created" rule.
