---
inclusion: always
---
# Porch Light — Product

An agent that watches a city's public meeting agendas on behalf of one person and tells them when something they care about lands, in plain English and Spanish, with a receipt on every claim. It drafts the structure of a public comment. The human writes the position and sends it. There is no send capability anywhere in this codebase.

**Primary user:** the weekly watcher — a neighborhood volunteer, nonprofit staffer, or parent who checks twenty city pages every Friday and still misses the supplemental packet that posted Tuesday. **Secondary:** a resident searching in plain words ("can they put a bar next to my house"), public, free, no login.

**Scope:** City of Ventura only, built as a CivicEngage AgendaCenter vendor adapter (§34). Hackathon: AWS Agents for Humans, Good Neighbor track, submits Sep 13, 2026.

**Agent surface (§38):** three reasoning loops, **two of them genuine agents** — the extractor (rewrite + verify) and the watcher (relevance). The **hunter is deterministic by design** (finds and classifies documents by pure rules, no model); a model there would invent judgment where there is none. Two-of-three is deliberate, not a gap.

**The line that governs everything:** the model translates and it notices. It never asserts a fact you could miss a deadline over. Deadlines, dates, item numbers, and page ranges are copied from source or not shown.

**The most important screen is the quiet week.** Most weeks nothing happens, and saying so honestly is the product working, not failing.
