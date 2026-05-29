# app/dash_apps/drilldown/registry.py
"""
Card Registry & Drill-Down Navigation Map
==========================================
CARD ID CONVENTION:
  kpi_<entity>_<metric>       e.g. kpi_apartments_total
  list_<entity>               e.g. list_apartments       (PLURAL)
  profile_<entity>            e.g. profile_apartment     (SINGULAR)
  form_<entity>_<action>      e.g. form_receipt_new      (SINGULAR)

NAMING STANDARDS:
  - List/loader keys use PLURAL   (apartments, gate_logs)
  - Profile/form/save keys use SINGULAR (apartment, gate_log)
  - PK_MAP and ENTITY_MAP are the single source of truth
"""


# ══════════════════════════════════════════════════════════════════════════════
# PRIMARY KEY MAP  — plural entity name → PK column in DB row
# ══════════════════════════════════════════════════════════════════════════════
PK_MAP: dict = {
    "apartments":  "id",
    "vendors":     "id",
    "security":    "id",
    "events":      "id",
    "concerns":    "id",
    "gate_logs":   "id",
    "receipts_tbl": "id",
    "expenses_tbl": "id",
    "cashbook":    "id",
    "societies":   "id",
    "accounts":    "id",
    "apt_charges": "id",
    "ven_charges": "id",
    "sec_charges": "id",
    "attendance":  "id",
    "receivables": "id",
}


# ══════════════════════════════════════════════════════════════════════════════
# ENTITY MAP  — plural → singular
# ══════════════════════════════════════════════════════════════════════════════
ENTITY_MAP: dict = {
    "apartments":  "apartment",
    "vendors":     "vendor",
    "security":    "security",
    "events":      "event",
    "concerns":    "concern",
    "gate_logs":   "gate_log",
    "receipts_tbl": "receipt_entry",
    "expenses_tbl": "expense_entry",
    "cashbook":    "transaction",
    "societies":   "society",
    "accounts":    "account",
    "apt_charges": "apt_charge",
    "ven_charges": "ven_charge",
    "sec_charges": "sec_charge",
    "attendance":  "attendance_entry",
    "receivables": "receivable",
}

ENTITY_MAP_REV: dict = {v: k for k, v in ENTITY_MAP.items()}


# ══════════════════════════════════════════════════════════════════════════════
# ROLE FILTERS
# ══════════════════════════════════════════════════════════════════════════════
ROLE_FILTERS: dict = {
    "master":    [],
    "admin":     ["society_id"],
    "apartment": ["society_id", "apartment_id"],
    "vendor":    ["society_id", "vendor_id"],
    "security":  ["society_id", "security_id"],
}


# ══════════════════════════════════════════════════════════════════════════════
# DRILL-DOWN NAVIGATION MAP
# ══════════════════════════════════════════════════════════════════════════════
DRILLDOWN_MAP: dict = {

    # ── KPI → LIST ───────────────────────────────────────────────────────────
    "kpi_apartments_total":   {"target": "list_apartments",  "label": "All Apartments"},
    "kpi_apartments_dues":    {"target": "list_apartments",  "label": "Apartments With Dues",  "filter": {"has_dues": True}},
    "kpi_apartments_no_dues": {"target": "list_apartments",  "label": "Apartments Cleared",    "filter": {"has_dues": False}},
    "kpi_vendors_total":      {"target": "list_vendors",     "label": "All Vendors"},
    "kpi_vendors_dues":       {"target": "list_vendors",     "label": "Vendors With Dues",     "filter": {"has_dues": True}},
    "kpi_security_total":     {"target": "list_security",    "label": "Security Staff"},
    "kpi_security_on_duty":   {"target": "list_security",    "label": "Security On Duty",      "filter": {"on_duty": True}},
    "kpi_events_total":       {"target": "list_events",      "label": "Upcoming Events"},
    "kpi_concerns_open":      {"target": "list_concerns",    "label": "Open Concerns"},
    "kpi_gate_logs":          {"target": "list_gate_logs",   "label": "Gate Logs Today"},
    "kpi_receipts_month":     {"target": "list_receipts_tbl","label": "Receipts This Month"},
    "kpi_expenses_month":     {"target": "list_expenses_tbl","label": "Expenses This Month"},
    "kpi_balance":            {"target": "list_cashbook",    "label": "Cashbook"},
    "kpi_societies_total":    {"target": "list_societies",   "label": "All Societies"},
    "kpi_societies_paid":     {"target": "list_societies",   "label": "Paid Plan Societies",   "filter": {"plan": "Paid"}},
    "kpi_societies_free":     {"target": "list_societies",   "label": "Free Plan Societies",   "filter": {"plan": "Free"}},
    "kpi_cash_in_hand":       {"target": "list_cashbook",    "label": "Cash in Hand"},
    
    # ── SETTINGS TAB KPIs → LIST ──────────────────────────────────────────────
    "kpi_plan_validity":      {"target": "list_societies",   "label": "Society Plan Validity"},
    "kpi_accounts_count":     {"target": "list_accounts",    "label": "Chart of Accounts"},
    "kpi_apt_charges":        {"target": "list_apt_charges", "label": "Apartment Charges"},
    "kpi_ven_charges":        {"target": "list_ven_charges", "label": "Vendor Charges"},
    "kpi_sec_charges":        {"target": "list_sec_charges", "label": "Security Charges"},
    "kpi_attendance":         {"target": "list_attendance",  "label": "Attendance Records"},

    # ── LIST → PROFILE ────────────────────────────────────────────────────────
    "list_apartments":    {"target": "profile_apartment",      "label": "Apartment Profile"},
    "list_vendors":       {"target": "profile_vendor",         "label": "Vendor Profile"},
    "list_security":      {"target": "profile_security",       "label": "Security Profile"},
    "list_events":        {"target": "profile_event",          "label": "Event Details"},
    "list_concerns":      {"target": "profile_concern",        "label": "Concern Details"},
    "list_gate_logs":     {"target": "profile_gate_log",       "label": "Gate Log Details"},
    "list_receipts_tbl":  {"target": "profile_receipt_entry",  "label": "Receipt Details"},
    "list_expenses_tbl":  {"target": "profile_expense_entry",  "label": "Expense Details"},
    "list_cashbook":      {"target": "profile_transaction",    "label": "Transaction Details"},
    "list_societies":     {"target": "profile_society",        "label": "Society Profile"},
    "list_accounts":      {"target": "profile_account",        "label": "Account Details"},
    "list_apt_charges":   {"target": "profile_apt_charge",     "label": "Apartment Charge Details"},
    "list_ven_charges":   {"target": "profile_ven_charge",     "label": "Vendor Charge Details"},
    "list_sec_charges":   {"target": "profile_sec_charge",     "label": "Security Charge Details"},
    "list_attendance":    {"target": "profile_attendance_entry","label": "Attendance Details"},
    "list_receivables":   {"target": "profile_receivable",     "label": "Receivable Details"},

    # ── PROFILE ACTIONS → FORM ────────────────────────────────────────────────
    "profile_apartment": {
        "actions": {
            "pay_dues":    {"target": "form_receipt_entry_new", "prefill": {"entity_id": "id", "entity_type": "_const_apartment", "amount": "pending_dues"}},
            "gate_pass":   {"target": "modal_qr",               "prefill": {"entity_id": "id", "role": "_const_a"}},
            "new_concern": {"target": "form_concern_new",       "prefill": {"flat_no": "flat_number"}},
            "edit":        {"target": "form_apartment_edit",    "prefill": {"*": "*"}},
        }
    },
    "profile_vendor": {
        "actions": {
            "pay":       {"target": "form_receipt_entry_new", "prefill": {"entity_id": "id", "entity_type": "_const_vendor", "amount": "pending_dues"}},
            "gate_pass": {"target": "modal_qr",               "prefill": {"entity_id": "id", "role": "_const_v"}},
            "edit":      {"target": "form_vendor_edit",       "prefill": {"*": "*"}},
        }
    },
    "profile_security": {
        "actions": {
            "gate_pass": {"target": "modal_qr", "prefill": {"entity_id": "id", "role": "_const_s"}},
        }
    },
    "profile_concern": {
        "actions": {
            "assign":  {"target": "form_concern_edit", "prefill": {"*": "*", "status": "_const_in_progress"}},
            "resolve": {"target": "form_concern_edit", "prefill": {"*": "*", "status": "_const_resolved"}},
        }
    },
    "profile_event": {
        "actions": {
            "edit": {"target": "form_event_edit", "prefill": {"*": "*"}},
        }
    },
    "profile_society": {
        "actions": {
            "edit": {"target": "form_society_edit", "prefill": {"*": "*"}},
        }
    },
    "profile_apt_charge": {
        "actions": {
            "edit": {"target": "form_apt_charge_edit", "prefill": {"*": "*"}},
        }
    },
    "profile_ven_charge": {
        "actions": {
            "edit": {"target": "form_ven_charge_edit", "prefill": {"*": "*"}},
        }
    },
    "profile_sec_charge": {
        "actions": {
            "edit": {"target": "form_sec_charge_edit", "prefill": {"*": "*"}},
        }
    },
    "profile_attendance_entry": {
        "actions": {
            "edit": {"target": "form_attendance_entry_edit", "prefill": {"*": "*"}},
        }
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_pk(entity_plural: str, row: dict):
    """Extract PK value from a DB row using PK_MAP."""
    pk_field = PK_MAP.get(entity_plural, "id")
    return row.get(pk_field) or row.get("id")


def to_singular(entity_plural: str) -> str:
    """Convert plural → singular via ENTITY_MAP."""
    return ENTITY_MAP.get(entity_plural, entity_plural.rstrip('s'))


def to_plural(entity_singular: str) -> str:
    """Convert singular → plural via reverse map."""
    return ENTITY_MAP_REV.get(entity_singular, entity_singular + 's')


def build_breadcrumb(nav_stack: list) -> list:
    """Build breadcrumb from navigation stack."""
    crumbs = []
    for i, item in enumerate(nav_stack):
        crumbs.append({
            "label":   item.get("entity_label") or item.get("label", "—"),
            "card_id": item.get("card_id"),
            "index":   i,
            "active":  i == len(nav_stack) - 1,
        })
    return crumbs


def propagate_filters(auth_data: dict, extra: dict = None) -> dict:
    """Merge auth filters with extra filters."""
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
    return {k: v for k, v in filters.items() if v is not None}


def build_prefill(profile_data: dict, prefill_map: dict) -> dict:
    """
    Map profile fields → form fields.
    
    Special source values:
      "_const_<value>"  →  inject literal string
      "*"               →  copy ALL profile fields first
    """
    result: dict = {}

    if prefill_map.get("*") == "*":
        result = dict(profile_data)

    for target_field, source in prefill_map.items():
        if target_field == "*":
            continue
        if isinstance(source, str) and source.startswith("_const_"):
            result[target_field] = source[7:]
        else:
            result[target_field] = profile_data.get(source, profile_data.get(target_field))

    return result
