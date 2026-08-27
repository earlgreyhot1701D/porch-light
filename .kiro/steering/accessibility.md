---
inclusion: fileMatch
fileMatchPattern: "**/*.{html,css,js}"
---
# Accessibility — WCAG 2.1 AA, judged

- Contrast computed, not eyeballed: 4.5:1 text, 3:1 large text/UI/focus indicators. Tokens in the accepted mock are pre-verified — do not alter their values. On the cream paper surfaces, focus rings use the dark variant (#175f87).
- Full keyboard operability (test with the mouse unused). Visible focus, min 3px outline with offset, never `outline: none`. Scrollable regions get `tabindex="0"` + `role="region"` + a label.
- `aria-live="polite"` on status and error regions — but never wrap a large re-rendered region in aria-live.
- One h1, ordered headings, landmarks. `<time datetime>`. 44px touch targets. Works at 320px, no horizontal scroll — and no `overflow-x: hidden` masking on body.
- Correct `lang` on every language-switched element, both directions.
- `prefers-reduced-motion` disables all animation.
- Links with identical text get distinct accessible names (aria-label with body + date).
- The demo video ships captioned.
