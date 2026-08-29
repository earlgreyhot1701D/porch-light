"""Ventura adapter — body registry (R1).

A static list of body IDENTITIES, not URLs (§35 finding): enumeration reads the
single combined AgendaCenter index and attributes each meeting to a body by the
index grouping. The registry is used to (a) give each body a stable id, (b)
validate that an attributed body name is one we recognize, and (c) categorize.

Maintenance (§11, R9.2): this is a rot point. The roster changes as ad hoc
committees are created and retired. It has a named owner and a verification date.
An unrecognized body name in the index is surfaced for review, never dropped and
never fabricated.

Source: the 21 bodies rendered in the combined /AgendaCenter index, verified by
hand on the date below. Matches the "21 bodies" figure in decisions §3.
"""

from __future__ import annotations

from porchlight.adapters.ventura.models import Body

# --- Maintenance metadata (R9.2) ---
REGISTRY_OWNER = "shara"
REGISTRY_VERIFIED_DATE = "2026-08-27"  # hand-verified against the live AgendaCenter index.

# Category constants.
_LEG = "legislative"
_ADV = "advisory"

# The 21 bodies, exact English names as the city renders them (copied, not
# paraphrased — never.md #1). body_id is a stable slug we own.
BODIES: tuple[Body, ...] = (
    Body("city_council", "City Council", _LEG),
    Body("planning_commission", "Planning Commission", _ADV),
    Body("design_review_committee", "Design Review Committee", _ADV),
    Body("historic_preservation_committee", "Historic Preservation Committee", _ADV),
    Body("arts_culture_commission", "Arts & Culture Commission", _ADV),
    Body("parks_recreation_commission", "Parks & Recreation Commission", _ADV),
    Body("water_commission", "Water Commission", _ADV),
    Body("parking_advisory_committee", "Parking Advisory Committee", _ADV),
    Body("directors_hearing", "Director's Hearing (Administrative Hearing)", _ADV),
    Body("housing_homelessness_subcommittee", "Housing and Homelessness Subcommittee", _ADV),
    Body("main_street_moves_ad_hoc", "Main Street Moves Ad Hoc Subcommittee", _ADV),
    Body("appointments_recommendation_committee", "Appointments Recommendation Committee", _ADV),
    Body("committee_reviewing_standing_committees", "Committee Reviewing City Council Standing Committees", _ADV),
    Body("economic_development_subcommittee", "Economic Development Subcommittee", _ADV),
    Body("general_plan_advisory_committee", "General Plan Advisory Committee", _ADV),
    Body("finance_audit_budget_committee", "Finance, Audit & Budget Committee", _ADV),
    Body("measure_o_oversight_committee", "Measure O Citizens Oversight Committee", _ADV),
    Body("streetlighting_ad_hoc", "City Council  Streetlighting Ad Hoc Committee", _ADV),
    Body("city_council_rules_committee", "City Council Rules Committee", _ADV),
    Body("mobile_home_rent_review_board", "Mobile Home Rent Review Board", _ADV),
    Body("city_hall_east_boiler_committee", "Council Committee Reviewing City Hall East Boiler Project", _ADV),
)

# Lookup by exact rendered name, for attributing index rows to a known body.
_BY_NAME = {b.name_en: b for b in BODIES}


def body_for_name(name: str) -> Body | None:
    """Return the registered Body for an exact rendered name, or None if unknown.

    A None result means the index carried a body name we do not recognize: the
    caller surfaces it for review (registry is a rot point), never fabricates a
    body and never silently drops the meeting.
    """
    return _BY_NAME.get(name)
