---
inclusion: fileMatch
fileMatchPattern: "**/*.{html,css,js,jsx,ts,tsx}"
---
# UI contract — the mock is a contract, not inspiration

`design/porch-light-ui-v1.html` is the **accepted, approved UI**. It went through three design rounds, a QA pass, computed contrast verification, and a bilingual review. **Copy it. Do not redesign it, do not "improve" it, do not rebuild it from principles.**

If you find yourself deciding what a screen should look like, stop: that decision was already made and is in the file.

## Frozen — copy exactly

- **Layout and DOM structure.** The watch strip, the two main states (quiet week / changed), the packet panel, the side panels, the About footer. Same regions, same order, same nesting.
- **All colour tokens, by value.** Contrast was computed, not eyeballed. Do not alter a hex value. `--deadline` (`#F5B942`) appears on an approaching comment deadline the user can still act on and **nowhere else, ever**.
- **All copy, both languages**, unless `voice.md` says otherwise. `voice.md` wins over the mock if they ever disagree.
- **Every ARIA attribute, `lang` attribute, `role`, `tabindex`, and `aria-live`.** These were audited. Removing one is a regression.
- **Status treatments.** Shape plus word plus colour on every status. Meaning must survive greyscale.
- **The three status chips** and their adjacent official terms ("New material added / Official term: Supplemental packet").
- **The receipt component**, its mono typography, and the jump-to-page link.
- **The draft scaffold's two-group structure**: sourced facts filled in, stance fields visibly empty. There is no send button anywhere in it.
- **The quiet-week state.** It is the most-seen screen in the product and it was designed deliberately.

## Expected to change — these are not deviations

The mock was built as a standalone preview. Some of its properties are artifacts of that, not design decisions:

1. **Storage.** The mock holds all state in JavaScript variables and uses **no browser storage**, because it was built as a preview artifact where storage is unreliable. **The product requires `localStorage`** for the watchlist and the draft queue (§6). Do not faithfully copy the limitation.
2. **Data source.** Inline sample arrays → `fixtures/sample.json` at Spec 3 → live endpoint at Spec 6 (§25). The rendering code should not care which.
3. **City.** "Riverdale" placeholders → real City of Ventura data.
4. **Links.** LinkedIn and source-code placeholders → real URLs.
5. **Disabled nav.** "Calendar" and "All bodies" are honest stubs. They become real or stay visibly disabled; either is fine, silently removing them is not.
6. **Packet panel content.** What it shows with real data is decided at Spec 3 (§25), not assumed from the mock's styled sample.
7. **Sample-data notice.** Remove only when the data is real.

## If you believe something must change

Propose it, with the reason, and wait for approval. Do not change it and mention it afterwards. Three rounds of decisions are encoded in that file and most "improvements" are re-litigating something already settled.

## Verbatim strings

These are load-bearing and must match `voice.md` exactly:

- "Your list stays on your device. We use it to answer, and never store it."
- "Drafts are yours to finish and send."
- "Porch Light never writes your opinion and cannot send anything."
- "not located at [url] as of [timestamp]"

Note: the mock's privacy string was corrected on Aug 22 (§26c) because the original became untrue once the watcher began matching from a transmitted watchlist. If you find an older wording anywhere, `voice.md` is authoritative.
