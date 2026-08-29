---
inclusion: always
---
# Security — standing rules

- Input validation client-side AND server-side. Never trust the front end. Watch terms: length cap, count cap, character validation. Shared watch links are shown and confirmed before applying, never auto-applied.
- Secrets server-side only (Secrets Manager / env). Never in the repo; scan git history before the repo goes public.
- Credentials are never passed to an agent, never pasted into a prompt, and live only in local `.env` (or Secrets Manager in production). An agent that needs a live check reports what it needs; a human runs the query and reports results back. Connection strings, tokens, and keys do not enter the conversation.
- Prompt injection: the extractor reads untrusted PDFs. Its tools are allowlisted at the Strands hook layer AND its IAM role has no network egress — two independent layers. Blocked tool calls are logged as NEVER-trips. A poisoned test PDF lives in tests/ with a passing containment test, including a draft-steering case.
- SSRF: hunter fetch is host-allowlisted at the hook; off-domain redirects are blocked, not followed.
- Public surface is the read-only search/site only. Rate limit search per IP, cache query embeddings, and give search its own spend sub-budget so it cannot starve ingestion (the spend ledger halting the pipeline is otherwise an attack surface).
- try/catch on every fetch and tool call, meaningful error states, `aria-live` on them, never a blank screen or endless spinner.
- Good citizen of the city's server: robots.txt, conditional GET, hourly not continuous, exponential backoff, max 1 concurrent fetch, descriptive user-agent with contact URL.
- Timeout ordering: run timeout < lock TTL < schedule interval. The run lock has a TTL and heartbeat — a dead run must never deadlock the schedule.
- Logs never contain packet text. CORS locked to our origin. Cost tags on every resource from day one.
- Third-party DEBUG logging is a packet-text egress path. Field-level redaction does not cover it. Root and third-party logger levels are a security control.
