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
    "apartments": "id",
    "vendors": "id",
    "security": "id",
    "events": "id",
    "concerns": "id",
    "gate_logs": "id",
    "receipts": "id",
    "expenses": "id",
    "cashbook": "id",
    "societies": "id",
    "accounts": "id",
    "apt_charges": "id",
    "ven_charges": "id",
    "sec_charges": "id",
    "attendance": "id",
    "receivables": "id",
    "payables": "id",
    "assets": "id",
    "security_roster": "id",
}


# ══════════════════════════════════════════════════════════════════════════════
# ENTITY MAP  — plural → singular
# ══════════════════════════════════════════════════════════════════════════════
ENTITY_MAP: dict = {
    "apartments": "apartment",
    "vendors": "vendor",
    "security": "security",
    "events": "event",
    "concerns": "concern",
    "gate_logs": "gate_log",
    "receipts": "receipt_entry",
    "expenses": "expense_entry",
    "cashbook": "transaction",
    "societies": "society",
    "accounts": "account",
    "apt_charges": "apt_charge",
    "ven_charges": "ven_charge",
    "sec_charges": "sec_charge",
    "attendance": "attendance_entry",
    "receivables": "receivable",
    "payables": "payment",
    "assets": "asset",
    "security_roster": "security_roster",
}

ENTITY_MAP_REV: dict = {v: k for k, v in ENTITY_MAP.items()}


# ══════════════════════════════════════════════════════════════════════════════
# ROLE FILTERS
# ══════════════════════════════════════════════════════════════════════════════
ROLE_FILTERS: dict = {
    "master": [],
    "admin": ["society_id"],
    "apartment": ["society_id", "apartment_id"],
    "vendor": ["society_id", "vendor_id"],
    "security": ["society_id", "security_id"],
}


# ══════════════════════════════════════════════════════════════════════════════
# DRILL-DOWN NAVIGATION MAP
# ══════════════════════════════════════════════════════════════════════════════
DRILLDOWN_MAP: dict = {
    # ── KPI → LIST ────────────────────────────────────────────────────────────
    "kpi_apartments_total": {
        "target": "list_apartments",
        "label": "All Apartments"
    },
    "kpi_apartments_dues": {
        "target": "list_apartments",
        "label": "Apartments With Dues",
        "filter": {"pending_dues": {"gt":0.0}},
    },
    "kpi_apartments_no_dues": {
        "target": "list_apartments",
        "label": "Apartments No Dues",
        "filter": {"pending_dues": {"eq":0.0}},
    },
    "kpi_vendors_total": {"target": "list_vendors", "label": "All Vendors"},
    "kpi_vendors_dues": {
        "target": "list_vendors",
        "label": "Vendors With Dues",
        "filter": {"has_dues": True},
    },
    "kpi_vendors_passes": {
        "target": "list_vendors",
        "label": "Vendors With Passes",
        "filter": {"active_passes": {"gt": 0}},
    },
    "kpi_my_pass_expiry": {
        "target": "list_vendors",
        "label": "My Pass & Vendor Details",
    },
    "kpi_security_total": {"target": "list_security", "label": "Security Staff"},
    "kpi_security_on_duty": {
        "target": "list_gate_logs",
        "label": "Security On Duty",
        "filter": {"on_duty": True},
    },
    "kpi_events_total": {"target": "list_events", "label": "Upcoming Events"},
    "kpi_concerns_open": {"target": "list_concerns", "label": "Open Concerns"},
    "kpi_gate_logs": {"target": "list_gate_logs", "label": "Gate Logs Today"},
    "kpi_receipts_month": {
        "target": "list_receipts",
        "label": "Receipts This Month",
    },
    "kpi_receipts_total": {
        "target": "list_receipts",
        "label": "All Receipts",
    },
    "kpi_expenses_month": {
        "target": "list_expenses",
        "label": "Expenses This Month",
    },
    "kpi_expenses_total": {
        "target": "list_expenses",
        "label": "All Expenses",
    },
    "kpi_bank_balance": {"target": "list_cashbook", "label": "Cashbook"},
    "kpi_cash_in_hand": {"target": "list_cashbook", "label": "Cash in Hand"},
    "kpi_societies_calc_start_date": {
        "target": "list_societies",
        "label": "Calc Start Date",
    },
    "kpi_receivables_total": {
        "target": "list_receivables",
        "label": "Receivables Total",
    },
    "kpi_receivables_overdue": {
        "target": "list_receivables",
        "label": "Overdue Receivables",
    },
    "kpi_advance_credits": {
        "target": "list_receivables",
        "label": "Advance Credits",
        "filter": {"status": "credit"},
    },
    "kpi_my_pending_dues": {
        "target": "list_receivables",
        "label": "My Pending Dues",
    },
    "kpi_my_overdue_dues": {
        "target": "list_receivables",
        "label": "My Overdue Dues",
    },
    "kpi_receipts_pending": {
        "target": "list_receipts",
        "label": "Receipts Pending Confirmation",
        "filter": {"status": "pending"},
    },

    "kpi_payables_total": {"target": "list_payables", "label": "Payables Total"},
    "kpi_vendor_payables_due": {
        "target": "list_payables",
        "label": "Vendor Payables Due",
    },
    "kpi_security_salaries_due": {
        "target": "list_payables",
        "label": "Security Salaries Due",
    },
    "kpi_security_salaries_paid": {
        "target": "list_payables",
        "label": "Security Salaries Paid",
    },
    "kpi_amc_due": {"target": "list_expenses", "label": "AMC Due"},
    "kpi_maintainence_charges": {
        "target": "list_apt_charges",
        "label": "Maintenance Charges",
    },
    "kpi_apartment_fines": {"target": "list_receivables", "label": "Apartment Fines"},
    "kpi_apartment_other_charges": {
        "target": "list_apt_charges",
        "label": "Other Charges",
    },
    "kpi_vendor_fines": {"target": "list_receipts", "label": "Vendor Fines"},
    "kpi_vendor_other_charges": {
        "target": "list_ven_charges",
        "label": "Other Charges",
    },

    "kpi_security_fines": {"target": "list_payables", "label": "Security Fines"},
    "kpi_security_other_charges": {
        "target": "list_payables",
        "label": "Other Charges",
    },
    "kpi_vendor_other_charges": {
        "target": "list_ven_charges",
        "label": "Other Charges",
    },
    "kpi_security_fines": {"target": "list_sec_charges", "label": "Security Fines"},
    "kpi_security_other_charges": {
        "target": "list_sec_charges",
        "label": "Other Charges",
    },
    "kpi_receipts_in_hand_total": {
        "target": "list_cashbook",
        "label": "Receipts in Hand",
    },
    "kpi_security_shift_count": {"target": "list_gate_logs", "label": "Shift Count"},
    "kpi_security_shifts_pending": {
        "target": "list_payables",
        "label": "Shifts Unpaid",
        "filter": {"role": "security", "status": "pending"},
    },
    "kpi_security_salary_due": {"target": "list_payables", "label": "Salary Due"},
    "kpi_security_bonus_due": {"target": "list_payables", "label": "Bonus Due"},
    # MASTER PORTAL KPIs
    "kpi_societies_total": {"target": "list_societies", "label": "All Societies"},
    "kpi_societies_9Apts": {
        "target": "list_societies",
        "label": "Paid Plan Societies",
        "filter": {"plan": "9Apts"},
    },
    "kpi_societies_99Apts": {
        "target": "list_societies",
        "label": "Paid Plan Societies",
        "filter": {"plan": "99Apts"},
    },
    "kpi_societies_999Apts": {
        "target": "list_societies",
        "label": "Paid Plan Societies",
        "filter": {"plan": "999Apts"},
    },
    "kpi_societies_unlimited": {
        "target": "list_societies",
        "label": "Unlimited Plans",
        "filter": {"plan": "unlimited"},
    },
    "kpi_societies_free": {
        "target": "list_societies",
        "label": "Free Plan Societies",
        "filter": {"plan": "Free"},
    },
    "kpi_societies_paid": {
        "target": "list_societies",
        "label": "All Paid Plans",
        "filter": {"plans": ["9Apts", "99Apts", "999Apts", "unlimited"]},
    },
    "kpi_societies_expired": {
        "target": "list_societies",
        "label": "Expired Plans",
        "filter": {"status": "expired"},
    },
    "kpi_master_apartments_total": {
        "target": "list_apartments",
        "label": "All Apartments",
    },
    "kpi_master_vendors_total": {"target": "list_vendors", "label": "All Vendors"},
    "kpi_master_security_total": {"target": "list_security", "label": "Security Staff"},
    # OWNER PORTAL KPIs
    "kpi_apartment_date": {"target": "list_apartments", "label": "Managed Apartments"},
    # VENDOR PORTAL KPIs
    "kpi_vendor_date": {"target": "list_vendors", "label": "Managed Vendors"},
    # SECURITY PORTAL KPIs
    "kpi_security_date": {"target": "list_security", "label": "Managed Security"},
    "kpi_security_salary_per_shift": {
        "target": "list_security",
        "label": "Security Salary",
    },
    "kpi_security_shift": {"target": "list_gate_logs", "label": "Completed Shifts"},
    # ── SETTINGS TAB KPIs → LIST ──────────────────────────────────────────────
    "kpi_societies_calc_start_date": {
        "target": "list_societies",
        "label": "Calc Start Date",
    },
    "kpi_plan_validity": {"target": "list_societies", "label": "Society Plan Validity"},
    "kpi_accounts_count": {"target": "list_accounts", "label": "Chart of Accounts"},
    # NOTE: "kpi_assets_total" doesn't exist in KPI_CARDS — the real card id
    # is "kpi_assets_count" (titled "Active Assets" in card_catalogue.py).
    "kpi_assets_count": {"target": "list_assets", "label": "All Assets"},
    "kpi_assets_value": {"target": "list_assets", "label": "All Assets"},
    "kpi_apt_charges_count": {
        "target": "list_apt_charges",
        "label": "Apartment Charges Rules",
    },
    "kpi_ven_charges_count": {
        "target": "list_ven_charges",
        "label": "Vendor Charges Rules",
    },
    "kpi_sec_charges_count": {
        "target": "list_payables",
        "label": "Security Charges Rules",
    },
    "kpi_attendance_count": {
        "target": "list_attendance",
        "label": "Attendance Records",
    },
    "kpi_security_roster_count": {
        "target": "list_security_roster",
        "label": "Security Roster",
    },


    "kpi_late_fees_due": {"target": "list_receivables", "label": "Late Fees Due"},
    "kpi_maintenance_due": {"target": "list_receivables", "label": "Maintenance Due"},
    # ── LIST → PROFILE ────────────────────────────────────────────────────────
    "list_apartments": {"target": "profile_apartment", "label": "Apartment Profile"},
    "list_vendors": {"target": "profile_vendor", "label": "Vendor Profile"},
    "list_security": {"target": "profile_security", "label": "Security Profile"},
    "list_events": {"target": "profile_event", "label": "Event Details"},
    "list_concerns": {"target": "profile_concern", "label": "Concern Details"},
    "list_gate_logs": {"target": "profile_gate_log", "label": "Gate Log Details"},
    "list_receipts": {
        "target": "profile_receipt_entry",
        "label": "Receipt Details",
    },
    "list_expenses": {
        "target": "profile_expense_entry",
        "label": "Expense Details",
    },
    "list_cashbook": {"target": "profile_transaction", "label": "Transaction Details"},
    "list_societies": {"target": "profile_society", "label": "Society Profile"},
    "list_accounts": {"target": "profile_account", "label": "Account Details"},
    "list_assets": {"target": "profile_asset", "label": "Asset Details"},
    "list_apt_charges": {
        "target": "profile_apt_charge",
        "label": "Apartment Charge Details",
    },
    "list_ven_charges": {
        "target": "profile_ven_charge",
        "label": "Vendor Charge Details",
    },
    "list_sec_charges": {
        "target": "profile_sec_charge",
        "label": "Security Charge Details",
    },
    "list_attendance": {
        "target": "profile_attendance_entry",
        "label": "Attendance Details",
    },
    "list_security_roster": {
        "target": "profile_security_roster",
        "label": "Roster Details",
    },
    "list_receivables": {
        "target": "profile_receivable",
        "label": "Receivable Details"
    },
    # ── PROFILE ACTIONS → FORM ────────────────────────────────────────────────
    "profile_apartment": {
        "actions": {
            # NOTE: "Gate Pass" is NOT routed through this map. It uses
            # action_id="show_qr" (see profile_actions.py), which
            # route_drilldown() in drilldown_callbacks.py intercepts with
            # an early return before DRILLDOWN_MAP is ever consulted. A
            # "gate_pass" entry here was dead code, and its role constant
            # was also wrong (_const_a maps to admin's gate code "a", not
            # apartment's "o" — see role_code_map in qr_callbacks.py).
            "new_concern": {
                "target": "form_concern_new",
                "prefill": {"flat_no": "flat_number"},
            },
            "edit": {"target": "form_apartment_edit", "prefill": {"*": "*"}},
        }
    },
    "profile_vendor": {
        "actions": {
            # See note above profile_apartment — same dead "gate_pass" entry removed.
            "edit": {"target": "form_vendor_edit", "prefill": {"*": "*"}},
        }
    },
    "profile_security": {
        "actions": {
            # See note above profile_apartment — same dead "gate_pass" entry removed.
            # "edit" is auto-populated by the post-processing loop below.
        }
    },
    "profile_concern": {
        "actions": {
            "assign": {
                "target": "form_concern_edit",
                "prefill": {"*": "*", "status": "_const_in_progress"},
            },
            "resolve": {
                "target": "form_concern_edit",
                "prefill": {"*": "*", "status": "_const_resolved"},
            },
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
    return ENTITY_MAP.get(entity_plural, entity_plural.rstrip("s"))


def to_plural(entity_singular: str) -> str:
    """Convert singular → plural via reverse map."""
    return ENTITY_MAP_REV.get(entity_singular, entity_singular + "s")


def build_breadcrumb(nav_stack: list) -> list:
    """Build breadcrumb from navigation stack."""
    crumbs = []
    for i, item in enumerate(nav_stack):
        crumbs.append(
            {
                "label": item.get("entity_label") or item.get("label", "—"),
                "card_id": item.get("card_id"),
                "index": i,
                "active": i == len(nav_stack) - 1,
            }
        )
    return crumbs


# Ensure profile action mappings exist for entities.
# This programmatically adds sensible defaults (edit prefill) and
# a `show_transactions` action for financial entities when missing.
try:
    for plural, singular in ENTITY_MAP.items():
        profile_key = f"profile_{singular}"
        # ensure entry exists
        if profile_key not in DRILLDOWN_MAP:
            DRILLDOWN_MAP[profile_key] = {"actions": {}}
        # ensure actions dict exists
        actions = DRILLDOWN_MAP.get(profile_key, {}).get("actions") or {}
        # add default edit mapping if not present
        if "edit" not in actions:
            actions["edit"] = {"target": f"form_{singular}_edit", "prefill": {"*": "*"}}
        # financial show_transactions action for financial-like entities
        if plural in (
            "receipts",
            "expenses",
            "receivables",
            "payables",
            "cashbook",
            "transactions",
        ):
            if "show_transactions" not in actions:
                actions["show_transactions"] = {
                    "target": "list_cashbook",
                    "prefill": {},
                }
        # write back
        DRILLDOWN_MAP[profile_key]["actions"] = actions
    # also ensure list-level receivables mapping exists
    if "list_receivables" not in DRILLDOWN_MAP:
        DRILLDOWN_MAP["list_receivables"] = {
            "target": "profile_receivable",
            "label": "Receivable Details",
        }
except Exception:
    pass


def propagate_filters(auth_data: dict, extra: dict = None) -> dict:
    """Merge auth filters with extra filters."""
    filters = {
        "society_id": auth_data.get("society_id"),
        "user_id": auth_data.get("user_id"),
        "role": auth_data.get("role"),
        "apartment_id": auth_data.get("apartment_id"),
        "vendor_id": auth_data.get("vendor_id"),
        "security_id": auth_data.get("security_id"),
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
            result[target_field] = profile_data.get(
                source, profile_data.get(target_field)
            )

    return result
