"""SPIKE (15 min, pass/fail): does Nova Lite reliably call tools and return
parseable structured output? Reality check on the model, NOT a tuning session.

Two trivial tools + one page of REAL meeting-3687 text. Ask the model to use both.
Run 3 attempts. PASS = tools called AND parseable structured result, 3/3.
FAIL = anything less. Do NOT iterate the prompt to rescue a FAIL.

Run: BEDROCK_MODEL_ID=amazon.nova-lite-v1:0 AWS_REGION=us-east-1 uv run python tests/golden/spike_tooluse.py
"""
from __future__ import annotations

import json
import os

from strands import Agent, tool

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

# One page of REAL 3687 text (verbatim from _3687.pdf, artifacts intact), the same
# source W6 used. Not synthetic.
PAGE_1 = (
    "PLANNING COMMISSION REGULAR MEETING AGENDA\n"
    "August 26, 2026\n\n"
    "1. Approval of the Minutes\n"
    "Approval of the draft minutes from the June 24, 2026 meeting.\n"
    "Recommendation: Approve, as presented.\n\n"
    "2. Prohousing Designation, Citywide\n"
    "The City is applying for a Prohousing Designation to the State of California "
    "Department of Housing and Community Development.\n"
    "Recommendation: To approve the draft Prohousing Designation application and formal resolution.\n"
)

# Two trivial tools that RECORD that they were called. The spike measures whether
# the model calls them, not what they compute.
_calls: list[str] = []


@tool
def count_agenda_items(page_text: str) -> int:
    """Count how many numbered agenda items appear in the given page text."""
    _calls.append("count_agenda_items")
    import re
    return len(re.findall(r"(?m)^\s*\d+\.", page_text))


@tool
def get_item_title(page_text: str, item_number: int) -> str:
    """Return the title line of the given numbered agenda item from the page text."""
    _calls.append("get_item_title")
    import re
    m = re.search(rf"(?m)^\s*{item_number}\.\s*(.+)$", page_text)
    return m.group(1).strip() if m else ""


PROMPT = (
    "Here is one page of a city meeting agenda:\n\n"
    f"{PAGE_1}\n\n"
    "Use the count_agenda_items tool to count the items on this page, then use the "
    "get_item_title tool to get the title of item 1. Then respond with ONLY a JSON "
    'object of the form {"item_count": <int>, "item_1_title": "<string>"}.'
)


def _parseable_structured(text: str) -> dict | None:
    """Try to pull a JSON object out of the model's final text. Lenient on fences."""
    t = text.strip()
    if "```" in t:
        # strip a ```json ... ``` fence if present
        parts = t.split("```")
        for p in parts:
            p = p.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{"):
                t = p
                break
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        obj = json.loads(t[start : end + 1])
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def main() -> None:
    print(f"SPIKE tool-use — model={MODEL_ID}, 3 attempts, PASS=3/3\n")
    passes = 0
    for attempt in range(1, 4):
        _calls.clear()
        agent = Agent(model=MODEL_ID, tools=[count_agenda_items, get_item_title])
        result = agent(PROMPT)
        final_text = str(result)
        called = list(_calls)
        parsed = _parseable_structured(final_text)
        tools_ok = ("count_agenda_items" in called) and ("get_item_title" in called)
        struct_ok = parsed is not None
        ok = tools_ok and struct_ok
        passes += int(ok)
        print(f"--- attempt {attempt}: {'PASS' if ok else 'FAIL'} ---")
        print(f"  tools called: {called}  (both required: {tools_ok})")
        print(f"  parseable structured output: {struct_ok}  parsed={parsed}")
        print(f"  raw final text: {final_text[:400]!r}\n")

    print("=" * 60)
    print(f"RESULT: {passes}/3  ->  {'PASS' if passes == 3 else 'FAIL'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
