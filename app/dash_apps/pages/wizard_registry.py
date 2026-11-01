# app/dash_apps/pages/wizard_registry.py
"""
Step registry for the Setup Wizard (Gold-Standard Plan v5, onboarding review).

The 12 wizard steps stay pre-rendered and hidden (as the old modal did) so the
restored multi-output callbacks never target missing ids. The Next callback
receives every registered State, but the server persists only the fields of the
step being left (None from not-rendered ids must never overwrite the draft).

Internal key (in CATEGORIES) -> draft key -> component (id, prop) map, plus the
dependency graph: when a step's saved values change, its dependents are marked
needs_review.
"""
from __future__ import annotations

from app.dash_apps.pages.setup_wizard import CATEGORIES, step_label

# Display label -> internal key (as listed in CATEGORIES)
STEP_KEYS = {cat: cat for cat in CATEGORIES}

# Draft key -> [(draft_field, component_id, prop)]
# component_id may be a plain string id or a dict-id pattern; the prop is what
# save_step reads back into the draft field.
STEP_FIELDS = {
    "society_details": [
        ("address", "sw-society-address", "value"),
        ("email", "sw-society-email", "value"),
        ("phone", "sw-society-phone", "value"),
        ("state", "sw-society-state", "value"),
        ("constitution", "sw-society-constitution", "value"),
        ("gate_logic", "sw-gate-logic", "value"),
        ("duty_hrs", "sw-duty-hrs", "value"),
        ("logo", {"type": "form-upload", "entity": "society", "field": "logo"}, "value"),
        ("bg", {"type": "form-upload", "entity": "society", "field": "bg"}, "value"),
    ],
    "administrator": [
        ("stepup_hash", "sw-qr-secret", "value"),     # hashed at save time by the callback
    ],
    "legal_regime": [
        ("central_it_tan", "sw-central-it-tan", "value"),
        ("central_tds", "sw-central-tds", "value"),
        ("central_gst", "sw-central-gst", "value"),
        ("central_rera", "sw-central-rera", "value"),
        ("has_employees", "sw-central-employees", "value"),
        ("has_security_agency", "sw-central-security-agency", "value"),
    ],
    "funds": [
        ("apt_cost", "sw-apt-cost", "value"),
        ("apt_budget", "sw-apt-budget", "value"),
        ("apt_rate", "sw-apt-rate", "value"),
        ("apt_amt", "sw-apt-amt", "value"),
        ("apt_billing_basis", "sw-apt-billing-basis", "value"),
        ("apt_due_day", "sw-apt-due", "value"),
        ("apt_interest", "sw-apt-interest", "value"),
        ("apt_sinking", "sw-apt-sinking", "value"),
        ("apt_repair", "sw-apt-repair", "value"),
    ],
    "tds": [
        ("tan", "sw-society-tan", "value"),
        ("effective_date", "sw-tds-effective-date", "date"),
    ],
    "gst": [
        ("gstin", "sw-society-gstin", "value"),
        ("cgst", "sw-cgst", "value"),
        ("sgst", "sw-sgst", "value"),
    ],
    "apartment": [
        ("vendor_1day", "sw-ven-1day", "value"),
        ("vendor_7day", "sw-ven-7day", "value"),
        ("vendor_1mth", "sw-ven-1mth", "value"),
    ],
    "vendor": [
        ("vendor_1day", "sw-ven-1day", "value"),
        ("vendor_7day", "sw-ven-7day", "value"),
        ("vendor_1mth", "sw-ven-1mth", "value"),
    ],
    "accounts": [
        ("calc_start", "sw-calc-start-date", "date"),
        ("pay_qr", {"type": "form-upload", "entity": "society", "field": "pay_qr"}, "value"),
    ],
    "brought_forward": [
        ("fy", "sw-bf-fy", "value"),
    ],
    "review": [],
}

# When upstream changes, mark these dependents needs_review (only if values changed).
DEPENDS = {
    "society_details": ["legal_regime", "funds", "tds", "gst", "apartment"],
    "legal_regime": ["tds", "gst", "funds"],
    "funds": ["apartment", "brought_forward"],
    "apartment": ["brought_forward"],
    "brought_forward": ["review"],
}

# Skipped when (draft_key -> condition key in legal_regime answers)
SKIPPED_WHEN = {
    "tds": "central_tds",
    "gst": "central_gst",
}

def draft_get(draft: dict, dotted: str, default=None):
    """Read a dotted path out of the draft (e.g. "society.address")."""
    cur = draft or {}
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(part)
        if cur is None:
            return default
    return cur


def step_label_for(key: str) -> str:
    return step_label(key)
