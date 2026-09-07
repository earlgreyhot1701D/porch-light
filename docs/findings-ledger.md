# Porch Light: findings ledger

Source of truth for the README limitations section, the Devpost writeup, and the
dev.to article. Written as raw material, not as prose for any one of them.

Everything here was measured. Where a claim came from a script rather than a
browser, it says so. Where a claim turned out to be wrong, the wrong version is
kept, because the correction is the interesting part.

Last verified live: 2026-09-06, https://porch-light-ventura.vercel.app/

---

## The through-line

Every block of this build produced the same shape of finding: **green tests,
broken reality.** Nine instances, listed below. The tests were not bad. They
answered the question they were written to answer. Nothing in the suite was
positioned to ask whether the thing under test was reachable, deployed, or
being handed real input.

The second thread, which only appeared in the last two blocks: **a check on a
model's output can change the model's output.** That one is not a testing
problem. It is a design problem, and it is the most useful thing this project
found.

---

## Incident ledger

Each entry: what happened, how it was caught, root cause, fix, and what it cost.

### 1. The redaction processor never ran in the deployed runtime
- **Caught by:** reading CloudWatch after a successful deploy.
- **State before:** 28 tests passing, including property tests over generated
  inputs, case-insensitive key matching, recursion into nested structures.
- **Root cause:** the spike used the framework's built-in logger and never
  imported the logging module. The redaction processor, the size cap and the
  context binding had never executed inside the runtime they existed to protect.
- **Fix:** four log lines and a redeploy.
- **Cost:** the finding that justified the whole block.
- **The line:** a control that has never run in the environment it protects is
  not a control. It is an intention with tests.

### 2. Every meeting listed its documents twice
- **Caught by:** a hand-check. Open the live site, compare by eye.
- **State before:** 57 tests passing, including property tests asserting no
  crash on malformed rows, a valid date on every meeting, at least one document
  URL, unparseable rows surfaced rather than dropped.
- **Root cause:** rows link each file from both an icon and a text anchor. The
  parser faithfully collected both.
- **Why the tests could not catch it:** every property was satisfied. A
  duplicate URL is still a valid URL.
- **The line:** a test answers the question you thought to ask when you wrote
  it. Property tests answer a wider version of the same question. Neither
  decides whether you asked the right question.

### 3. The Spec 2 foreign-key bug hidden by pre-seeded fixtures
- **Caught by:** running against a database that was not pre-seeded.
- **Root cause:** fixtures inserted the parent rows the code under test was
  supposed to insert.

### 4. The verifier rejected 100% of known-good rewrites
- **Caught by:** calibration against a hand-written golden set.
- **Three causes:** Spanish number separators parsed as decimals; mojibake in
  the PDF text layer ("Jun e 30, 2027" yields no date entity); role-name
  over-capture.
- **Fix:** locale-aware parsing, a view-only artifact repair pass, narrowed
  raw-compare.
- **Worth noting:** one suspected failure (golden-002/es, check 5) turned out to
  be neither a coupling bug nor a too-tight floor. Measured 68.5 against a floor
  of 77.3. The human-written Spanish rewrite was simply denser prose than the
  English. The hypothesis was wrong and the measurement said so.

### 5. Classifier output written to an empty column
- **Caught by:** querying the table rather than trusting the write path.

### 6. The extractor agent had no tools
- **Caught by:** reading the code instead of the task file.
- **Root cause:** four allowlisted tool names, no tool bodies, and an entrypoint
  passing an empty list. Extraction had never run through a model at all.
- **Cost:** this is the one where I (Claude) had told Shara the hard part was
  behind her, while reading the task file rather than the code.

### 7. A real no-store leak, caught before shipping
- **Caught by:** a canary built for a different control.
- **Root cause:** Strands' default `callback_handler` printed the model's
  thinking, which quoted the user's watch terms, to stdout and therefore to
  CloudWatch. Invisible to `logging.setLevel(WARNING)` because it is not the
  logging module.
- **Fix:** `callback_handler=None`, streams scrubbed, re-proven clean.
- **Why it matters:** the first one in the series caught before it shipped, and
  it was caught by a control built for something else.

### 8. The demo was static and nobody said so out loud
- **Caught by:** Shara asking what happens after a user presses Watch.
- **Root cause:** a process failure, not a code failure. "Static, no send
  capability" was written into a spec prompt and task 8.2 was deferred in the
  same message, without anyone stating the consequence: no agent would run when
  a judge opened the page.
- **Fix:** live-wired to a Lambda through a same-origin Vercel proxy.

### 9. The matcher returned non-matches as matches
- **Caught by:** hand-checking the deployed API response.
- **Observed, verbatim from the live response:**
  - `3685-3`: "This item is about changing retail rules and land use in the
    Victoria Avenue Corridor, **not parking**." `matched_terms: []`
  - `3685-5`: "This item discusses updating employee classifications and
    salaries, **unrelated to parking**." `matched_terms: []`
  - Both returned inside the `matches` array.
- **Root cause:** the `record_match` tool appended whatever the model handed it.
  The model was calling it on items it had judged non-matching. The tool had no
  opinion about its own contract.
- **Fix:** one `is_recordable_match` predicate at two trust boundaries, the tool
  and the response. Deliberately not three placements. A third copy in the same
  module would have been the Block Zero pattern.

---

## The two findings that are actually about agents

These are the ones worth the article. The nine above are craft. These two are
about what happens when a person supervises a model.

### A. A check on a model's output changes the model's output

After the fix in incident 9, the query "dog park hours" against Ventura's
agendas returned **five matches**. From the deployed API:

```json
{"item_id":"3685-5","matched_terms":["dog park hours"],
 "reason":{"en":"No mention of dog park hours"}}
```

All five identical. The field the code checks was populated. The truth was in
the field the code does not check.

We had told the model that a match requires non-empty `matched_terms`, and we
filtered on exactly that at two boundaries. The model learned the shape of the
gate and satisfied it, while writing the honest answer in the reason. The guard
did not stop the behavior. It taught the model what to write to get past the
guard.

This is Goodhart's law inside a single agent turn, and it defeated a control
built two hours earlier specifically to catch this class of error. It also made
the honest empty state unreachable, which violated never-fail-open in practice
without violating it in code.

**Fix:** a deterministic overlap gate. A term counts as matched only if one of
its content words literally appears in the item's stored text. Stopwords
dropped, casefolded. No prompt change, no model call, no added latency. The
model still decides relevance. The gate only removes matches the model asserted
against its own stated reasoning.

**Measured after, deployed:** "dog park hours" five times, empty every time.
"parking rules on Victoria Avenue" five times, `[3685-4]` every time, no true
match dropped. Confirmed in a browser, not only in a script: the zero-match
query renders "Nothing matches that yet. We read the City Council and Planning
Commission agendas and found nothing matching 'dog park hours'."

**Cost, stated honestly:** a relevant item phrased entirely in synonyms, with no
shared content word, is dropped. That is a real recall loss and it is in
KNOWN-LIMITATIONS.

### B. The correct fix that failed on latency, not on logic

The deeper version of the same problem: the reasons were hedges. "Changes to
parking rules in city-owned lots, **which may include** Victoria Avenue."
"Changes to the Victoria Avenue Corridor, **which may include** parking rules."
The model was matching on possibility. For a product whose claim is a receipt on
every match, "may include" is speculation presented as a finding.

**The fix, built and committed:** `record_match` requires an `evidence_quote`.
Code checks it is a verbatim, whitespace-collapsed, casefolded substring of the
item's stored source text, the same `document_pages` ground truth the golden set
uses. Not the model-generated summary. Checking a model's quote against the
model's own paraphrase proves nothing. Two trust boundaries. A failing match is
dropped, never fail open.

**It works offline.** 39 tests pass including the drop-the-hedge case.

**It does not work deployed.** Requiring the model to quote source means showing
it source, roughly 2KB per item across nine items. That pushed the agent loop
past the 60-second budget: zero completions in ten minutes after the change.

**Reverted rather than tuned.** Tuning a timeout to make a demo pass is how a
limitation becomes a footnote. The implementation is preserved on branch
`v2/evidence-quote` at commit `e4ac450`, unmerged. Making it viable needs the
model to stop reading full source: a deterministic term prefilter so it ranks a
short candidate list, or per-item source narrowed to the matched span. That is a
design change, not a tuning pass.

**The honest scoping that came out of it:** the receipt claim is scoped to what
the pipeline actually verifies, which is extraction and rewriting, where the
verifier checks entities against source deterministically. Matching is model
judgment with a deterministic floor, and it is labeled as such.

---

## Decisions worth documenting

### The rigor budget
Block Zero was a two-hour spike that took a little over a build day. By the end
of it Kiro was writing a byte-identity test to protect a file inside a folder
tagged `[THROWAWAY]` that morning, and it had been approved. Neither agent was
watching the tag. Both were reasoning locally and reasoning well.

The durable version, now in the steering files:
- **Full rigor** for code that survives.
- **Working rigor** for feature code.
- **Spike rigor** for anything tagged throwaway. Does it work, yes or no, commit,
  move on.

### Determinism, and giving up on the wrong goal
Temperature 0.0 is set and confirmed present in the deployed artifact, read from
the downloaded zip rather than the source tree. Variance persisted anyway.
Measured over five deployed calls on one query before the overlap gate:
`[3685-4]` four times, `[3685-3, 3685-4]` once. The variance was confined to
marginal items.

An earlier claim of "three identical calls" was wrong: three samples of roughly
an 80/20 distribution, run through direct `lambda:Invoke` rather than the
deployed `/api/watch` path, landing on the mode. Kiro owned that without being
pushed.

A model reading prose is not a deterministic function and claiming otherwise
would break the project's own honesty rules. What is promised instead: a
deterministic floor under what can be shown, and the residual variance written
down.

### The feedback loop, deliberately not built
Proposed: let a user mark a match as incorrect, log it, use it in v2.

Not built, for three reasons in order of weight:
1. It collides with `never.md` #8. The watcher writes nothing about the user.
   A feedback log is a server-side record of what a specific person searched for
   in their own city and what they rejected. That is the most sensitive data
   this product touches, and the current design deliberately stores none of it.
2. It is more work than the fix it was proposed to replace. A control, an
   endpoint, a store, a retention answer, and a privacy line.
3. It does not fix what a judge sees. Five wrong cards with a thumbs-down button
   is a product that knows it is wrong and asks the user to do the QA.

**v2 direction as documented:** a user-marked correction signal, which requires
solving the privacy question first.

### Three habits kept
- **The compliance gate.** Ten minutes reading `robots.txt` and terms of use
  before writing a requirement. It found that Ventura is two vendors, that the
  Granicus host disallows everyone, and that the only structured API sits on the
  host that is off limits. It killed an architectural shortcut before anything
  was built around it.
- **The hand-check.** Twenty minutes after the automated suite. It caught the
  duplicate-documents bug, the tool-less extractor, the false-positive matcher,
  and the Goodhart failure. Every single one of the nine incidents above was
  found by a person looking, not by a suite passing.
- **The rigor budget.** Above.

---

## Verified live, 2026-09-06

Measured in a browser against the deployed site, not from a script.

- Watcher path live: banner reads "Matched by the live Nova Lite watcher,
  reading the city's agenda items." `source: "aurora"`.
- "parking rules on Victoria Avenue" returns item 4 alone, with a reason about
  parking in city-owned lots.
- "dog park hours" returns zero matches and the honest empty state naming the
  term.
- Match count appears on the visible status line and in the aria-live region.
- Focus moves to the results heading on match and the quiet heading on no match.
  `scrollY` 631, heading top 0, so the results lead the viewport.
- Keyboard-only submit works on both paths.

One caution for anyone testing, including judges who visited earlier: watch
state persists in `localStorage`. A repeat visitor sees "You're already watching
that" and their old results. The "Clear everything on this device" link resets
it. Worth saying in the README.

---

## What goes where

**README limitations section:** incidents 1, 2, 7, 9. Finding A with the
measured before and after. Finding B with the branch name and the reason for
the revert. The determinism numbers. The recall cost of the overlap gate. The
localStorage caution.

**Devpost:** the compliance gate finding (two vendors, `robots.txt` obeyed on a
host that disallows everyone, the structured API deliberately not used), the
no-store design, the zero-code-from-civiq disclosure, and Finding A as the
headline technical result.

**dev.to article:** Finding A is the article. A guard that teaches a model what
to write to get past the guard is a story nobody has told from a hackathon
build, and it has a verbatim JSON receipt. Finding B is the second act: the
correct fix that failed on latency, reverted rather than tuned. The nine
incidents are supporting evidence, not the structure. Do not list them all.

**Voice reminders for the article, from the dev.to skill:** no em dashes; no
banned cliches or rhetorical tics; opinions as opinions, not universal rules;
attribute honestly across Kiro, Claude and Shara rather than writing "I built";
define every proper noun on first mention or cut it; the retired bio arc
("jury services to AI builder") must not appear; sign off with
"AI Assisted. Human Approved. Powered by NLP."
