# app/dash_apps/drilldown/registry.py
"""
Card Registry & Drill-Down Navigation Map
==========================================
Defines the complete graph of card relationships:
  - Which card a KPI click leads to
  - Which card a list row double-click leads to
  - Which card an action button leads to
  - Pre-fill mappings between cards

CARD ID CONVENTION:
  kpi_<entity>_<metric>       e.g. kpi_apartments_total
  list_<entity>               e.g. list_apartments
  profile_<entity>            e.g. profile_apartment
  form_<entity>_<action>      e.g. form_receipt_new
"""

from typing import Optional


# ── Filter hierarchy per role ─────────────────────────────────────────────────
ROLE_FILTERS = {
    "master":    [],
    "admin":     ["society_id"],
    "apartment": ["society_id", "apartment_id"],
    "vendor":    ["society_id", "vendor_id"],
    "security":  ["society_id", "security_id"],
}


# ── Card navigation graph ─────────────────────────────────────────────────────
# Each entry: card_id → { "click": target_card_id, "prefill": {field: source_field} }
DRILLDOWN_MAP = {

    # ──────────────── KPI → LIST ────────────────────────────────────────────
    "kpi_apartments_total":      {"target": "list_apartments",    "label": "Apartments"},
    "kpi_apartments_dues":       {"target": "list_apartments",    "label": "Apartments (With Dues)", "filter": {"has_dues": True}},
    "kpi_apartments_no_dues":    {"target": "list_apartments",    "label": "Apartments (Cleared)",   "filter": {"has_dues": False}},
    "kpi_vendors_total":         {"target": "list_vendors",       "label": "Vendors"},
    "kpi_vendors_dues":          {"target": "list_vendors",       "label": "Vendors (With Dues)",    "filter": {"has_dues": True}},
    "kpi_security_total":        {"target": "list_security",      "label": "Security Staff"},
    "kpi_security_on_duty":      {"target": "list_security",      "label": "Security (On Duty)",     "filter": {"on_duty": True}},
    "kpi_events_total":          {"target": "list_events",        "label": "Events"},
    "kpi_concerns_open":         {"target": "list_concerns",      "label": "Open Concerns"},
    "kpi_gate_logs_today":       {"target": "list_gate_logs",     "label": "Gate Logs Today"},
    "kpi_receipts_month":        {"target": "list_receipts",      "label": "Receipts"},
    "kpi_expenses_month":        {"target": "list_expenses",      "label": "Expenses"},
    "kpi_balance":               {"target": "list_cashbook",      "label": "Cashbook"},
    "kpi_societies_total":       {"target": "list_societies",     "label": "Societies"},
    "kpi_societies_paid":        {"target": "list_societies",     "label": "Societies (Paid Plan)",  "filter": {"plan": "Paid"}},
    "kpi_societies_free":        {"target": "list_societies",     "label": "Societies (Free Plan)",  "filter": {"plan": "Free"}},

    # ──────────────── LIST ROW DBL-CLICK → PROFILE ───────────────────────────
    "list_apartments":    {"target": "profile_apartment",  "label": "Apartment Profile",  "pk": "apartment_id"},
    "list_vendors":       {"target": "profile_vendor",     "label": "Vendor Profile",     "pk": "vendor_id"},
    "list_security":      {"target": "profile_security",   "label": "Security Profile",   "pk": "security_id"},
    "list_events":        {"target": "profile_event",      "label": "Event Details",      "pk": "event_id"},
    "list_concerns":      {"target": "profile_concern",    "label": "Concern Details",    "pk": "concern_id"},
    "list_gate_logs":     {"target": "profile_gate_log",   "label": "Gate Log Details",   "pk": "log_id"},
    "list_receipts":      {"target": "profile_receipt",    "label": "Receipt Details",    "pk": "receipt_id"},
    "list_cashbook":      {"target": "profile_transaction","label": "Transaction",        "pk": "transaction_id"},
    "list_societies":     {"target": "profile_society",    "label": "Society Profile",    "pk": "society_id"},
    "list_accounts":      {"target": "profile_account",    "label": "Account Details",    "pk": "account_id"},

    # ──────────────── PROFILE ACTION → FORM ──────────────────────────────────
    "profile_apartment": {
        "actions": {
            "pay_dues":     {"target": "form_receipt_new",    "prefill": {"apartment_id": "id", "flat_number": "flat_number", "amount": "pending_dues"}},
            "edit":         {"target": "form_apartment_edit", "prefill": {"*": "*"}},
            "gate_pass":    {"target": "form_gate_pass_new",  "prefill": {"entity_id": "linked_user_id"}},
            "new_concern":  {"target": "form_concern_new",    "prefill": {"flat_no": "flat_number"}},
        }
    },
    "profile_vendor": {
        "actions": {
            "pay":          {"target": "form_receipt_new",    "prefill": {"vendor_id": "id", "amount": "pending_dues"}},
            "edit":         {"target": "form_vendor_edit",    "prefill": {"*": "*"}},
            "gate_pass":    {"target": "form_gate_pass_new",  "prefill": {"entity_id": "linked_user_id", "role": "v"}},
        }
    },
    "profile_concern": {
        "actions": {
            "assign":       {"target": "form_concern_edit",   "prefill": {"*": "*", "status": "in_progress"}},
            "resolve":      {"target": "form_concern_edit",   "prefill": {"*": "*", "status": "resolved"}},
        }
    },
    "profile_receipt": {
        "actions": {
            "verify":       {"target": "form_receipt_verify", "prefill": {"*": "*"}},
            "download":     {"action": "download_pdf"},
        }
    },
    "profile_society": {
        "actions": {
            "edit":         {"target": "form_society_edit",   "prefill": {"*": "*"}},
            "delete":       {"action": "confirm_delete",      "entity": "society"},
        }
    },
}


# ── Breadcrumb trail builder ───────────────────────────────────────────────────
def build_breadcrumb(nav_stack: list[dict]) -> list[dict]:
    """
    Convert a navigation stack into breadcrumb items.

    nav_stack = [
        {"card_id": "kpi_apartments_total", "label": "Dashboard"},
        {"card_id": "list_apartments",      "label": "Apartments"},
        {"card_id": "profile_apartment",    "label": "Flat A-101"},
    ]
    Returns list of {"label": str, "card_id": str, "index": int}
    """
    crumbs = []
    for i, item in enumerate(nav_stack):
        crumbs.append({
            "label":   item.get("label", item.get("card_id", "—")),
            "card_id": item.get("card_id"),
            "index":   i,
            "active":  i == len(nav_stack) - 1,
        })
    return crumbs


# ── Filter propagation helper ──────────────────────────────────────────────────
def propagate_filters(auth_data: dict, extra: dict | None = None) -> dict:
    """
    Build the complete filter context for a given auth session.
    extra = any drill-down-specific filters (e.g. has_dues=True)
    """
    filters = {
        "society_id":   auth_data.get("society_id"),
        "user_id":      auth_data.get("user_id"),
        "role":         auth_data.get("role"),
        "apartment_id": auth_data.get("apartment_id"),
        "vendor_id":    auth_data.get("vendor_id"),
        "security_id":  auth_data.get("security_id"),
    }
    if extra:
        filters.update(extra)
    return filters


# ── Pre-fill context builder ───────────────────────────────────────────────────
def build_prefill(profile_data: dict, prefill_map: dict) -> dict:
    """
    Map source fields from a profile record into target form fields.

    prefill_map = {"apartment_id": "id", "flat_number": "flat_number"}
    profile_data = {"id": 42, "flat_number": "A-101", ...}
    Returns: {"apartment_id": 42, "flat_number": "A-101"}
    """
    if prefill_map.get("*") == "*":
        result = dict(profile_data)
        # override specific fields if also specified
        for target, source in prefill_map.items():
            if target != "*" and source != "*":
                result[target] = profile_data.get(source, profile_data.get(target))
        return result

    result = {}
    for target_field, source_field in prefill_map.items():
        result[target_field] = profile_data.get(source_field)
    return result
