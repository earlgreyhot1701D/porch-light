---
inclusion: always
---
# Model authority — where the LLM is allowed

Deterministic structure, AI reasoning at the edges. Before putting a model anywhere, ask: is this deterministic or does it genuinely need the model, can the output be verified against a source, and what happens when it is wrong.

**The model has exactly three jobs:**
1. Rewrite staff language into plain English, then translate the verified English into Spanish (chain; both outputs verified against the original source by deterministic code).
2. Decide whether an item is relevant to one person's watchlist, emitting the match and its plain-language reason in one structured output. Errs toward showing: a false negative is a missed deadline, a false positive is a mild annoyance.
3. Assemble the structure of a comment draft — facts, receipt, logistics. Never its stance.

**Everything else is code:** fetching, hashing, change detection, document role classification, item numbers, page ranges, deadlines, the vocabulary bridge, search ranking, every status string, every receipt, the spend ledger, the run log, all retry decisions.

**The verifier is code, not a model.** Six checks on every rewrite: schema, entity preservation (every number/date/name in output exists in the source page range), no new entities, containment (ids and deadlines attached from the extraction record, never read from model output), reading level, both languages against source. Fail once → one retry with the failure attached. Fail twice → show original staff text with a note. The model never grades its own output.

**A loop is the model choosing its next action** (hunter, extractor, watcher only). **A retry is code deciding after checking.** The rewrite gets retries, never a loop.
