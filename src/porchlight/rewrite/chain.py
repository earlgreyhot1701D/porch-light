"""The rewrite chain (§21a): source -> EN -> verify -> ES -> verify-against-source.

Code-directed, not an agent. Both languages verify against the ORIGINAL source,
never EN-vs-ES (§21d); the one allowed hop is ES-from-verified-EN, still checked
against source.

THE PROMPT IS A CONTROLLED VARIABLE (task 9 amendment 2). Both models receive the
IDENTICAL instruction below, and it matches the guidance the golden rewrites were
written to: plain language for a neighbor, preserve every entity, add nothing not
in the source, do not imply an outcome where the body has options. If two models
got different prompts we would be measuring prompt engineering, not models.
"""

from __future__ import annotations

# --- The controlled rewrite prompts. Identical across models. ---
# English rewrite instruction. Mirrors the golden-rewrite guidance verbatim in
# intent (plain-for-a-neighbor; preserve entities; add nothing; do not imply an
# outcome where the body has options).
REWRITE_PROMPT_EN = (
    "Rewrite the following city agenda item in plain English a neighbor could read. "
    "Rules you must follow exactly:\n"
    "- Use plain, everyday language. Explain what the item is and what the body will do.\n"
    "- Preserve EVERY entity from the source: every date, dollar amount, number, "
    "item number, street name, place name, person name, company or organization "
    "name, and identifier. Copy them exactly; do not change, round, or reformat them.\n"
    "- Add NOTHING that is not in the source. Do not explain jargon using outside "
    "knowledge, do not add facts, do not name anything the source does not name.\n"
    "- If the body has options or a choice to make, describe the options neutrally. "
    "Do NOT imply or predict an outcome. Do not say the body 'will' do a thing it is "
    "only being asked to consider.\n"
    "- Do not add any opinion, recommendation, or position.\n"
    "- Do not repeat or echo the source text.\n"
    "- Do not include headers, labels, or section markers from the source such as "
    "RECOMMENDATION, Staff, or the item number line.\n"
    "- Write it as prose a person reads, not as a restructured agenda entry.\n"
    "- Name the public body that is acting on the item, using the name the record "
    "gives it; do not substitute a different body.\n"
    "Return only the rewritten text, nothing else."
)

# Spanish stage: translate the VERIFIED English into Spanish, same rules, plus the
# raw-name rule that keeps street/place/code names untranslated (check 6).
REWRITE_PROMPT_ES = (
    "Translate the following verified plain-English summary into plain Spanish a "
    "neighbor could read. Rules you must follow exactly:\n"
    "- Use plain, everyday Spanish.\n"
    "- Preserve EVERY entity: every date, amount, number, and identifier keeps its "
    "value (dates and amounts may use Spanish convention, but the value must not "
    "change).\n"
    "- Do NOT translate proper names: street names, place names, body/code names, "
    "person names, and company names stay exactly as written in the English "
    "(e.g. 'Victoria Avenue' stays 'Victoria Avenue', never 'Avenida Victoria').\n"
    "- Add nothing not in the English. Do not imply an outcome where there are options.\n"
    "- Do not repeat or echo the source text.\n"
    "- Do not include headers, labels, or section markers from the source such as "
    "RECOMMENDATION, Staff, or the item number line.\n"
    "- Write it as prose a person reads, not as a restructured agenda entry.\n"
    "- Name the public body that is acting on the item, using the name the record "
    "gives it; do not substitute a different body.\n"
    "Return only the Spanish text, nothing else."
)


def build_user_text(source_text: str) -> str:
    """The user message for the EN stage: just the source item text."""
    return f"Agenda item:\n\n{source_text}"


def build_es_user_text(verified_en: str) -> str:
    """The user message for the ES stage: the VERIFIED English (§21a chain hop)."""
    return f"Verified English summary:\n\n{verified_en}"

# NOTE ON SCOPE: the full retry/fallback wiring (verify -> one retry -> original
# text) is `verify.verifier.verify_with_retry`, which takes a rewrite_fn. The
# task-9 comparison harness composes THIS prompt + `rewrite.model.invoke` into that
# rewrite_fn per model, so the chain, the verifier, and the model are exercised
# together without duplicating the retry logic here. Production wiring of the chain
# into the pipeline is a later task; this module is the controlled prompt + the two
# message builders, which is what the comparison needs.
