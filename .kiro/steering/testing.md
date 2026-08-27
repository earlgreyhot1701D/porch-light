---
inclusion: fileMatch
fileMatchPattern: "tests/**|**/test_*.py|Makefile"
---

# Testing contract

Source: decisions doc §28. The lesson behind this file: a suite can be green while the live workflow is broken, because every test was watching for the failure we imagined.

## The rule

**Any test whose subject is a system we do not control is either run against that system, or built from a captured artifact of it. Never from a description of it.**

Systems we do not control: Bedrock, the Strands SDK, boto3, AgentCore, Neon, the City of Ventura's website, any PDF we did not write.

Pure functions over our own data structures are exempt and stay property-based with Hypothesis. Do not add real-data tests to a string formatter.

## Three obligations

**1. Live capability leaves a smoke test.**
Every spec that proves a live capability leaves a test marked `@pytest.mark.live`, excluded from the default `pytest` run, run by `make smoke`. A capability proven once in a checkpoint and never re-checked is not proven for the rest of the build.

**2. Boundary behavior is built from captured artifacts.**
Retry logic, error classification, and fallback behavior are tested against exceptions and responses captured from a real call, stored in `tests/contracts/` with the SDK version and capture date in the filename. A version guard fails the build when the installed `strands-agents` or `boto3` version differs from the recorded one. That failure means re-capture, not bump the pin.

Where a failure cannot be provoked cheaply against the real service, copy the shape from vendor documentation, include the doc URL and retrieval date as a header comment, and label it `source: documented, not observed`. Never present a guessed shape as an observed one.

**3. Hostile fixtures are generated, not typed.**
`fixtures/ugly.json` comes out of a script run against real ingested data. The 95th-percentile summary length is computed and recorded in the fixture header. Any category with no real instance yet is marked `synthetic: true` in the file so the gap is visible.

## Forbidden

- A fake Bedrock or Strands client that stands in for the real one. It will pass against an SDK signature that no longer exists.
- Asserting on an exception type or error string that was written from memory rather than captured.
- Marking a test as covering a real-data case when its input was hand-authored.

## Stop and report

If a live smoke test or a contract-version guard fails, stop and report. Do not repair the test to make it pass. The failure is the signal.
