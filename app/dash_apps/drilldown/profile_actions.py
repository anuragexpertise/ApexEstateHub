# app/dash_apps/drilldown/profile_actions.py
"""
Profile action buttons — application WORKFLOW layer.
These cannot be derived from schema introspection; they encode which
button on a profile card triggers which navigation or server-side action.

v3 changes:
  - apartments: added 'issue_noc', kept 'pay_dues' (now routes to FIFO form)
  - vendors:    added 'sell_vendor_pass'
  - receivables: added 'verify_receivable' (admin-only; enforced in renderers.py)
  - payments:    added 'verify_payment'    (admin-only)
  - assets:      added 'dispose_asset'     (admin-only)
  - Removed:     sec_charges (table dropped in v3)
"""

PROFILE_ACTIONS: dict[str, list[dict]] = {

    # ── APARTMENTS ──────────────────────────────────────────────────────────
    "apartments": [
        {
            "label": "Pay Dues",
            "action_id": "pay_dues",
            "target_card": "form_pay_dues_new",
            "icon": "fa-rupee-sign",
            "color": "success",
            "roles": ["admin"],          # only admin can apply a payment
        },
        {
            "label": "Show Cashbook",
            "action_id": "show_cashbook",
            "target_card": "list_cashbook",
            "icon": "fa-book",
            "color": "info",
        },
        {
            "label": "Gate Pass",
            "action_id": "show_qr",
            "target_card": "modal_qr",
            "icon": "fa-qrcode",
            "color": "primary",
        },
        {
            "label": "Raise Concern",
            "action_id": "new_concern",
            "target_card": "form_concern_new",
            "icon": "fa-comment-alt",
            "color": "warning",
        },
        {
            "label": "Issue NOC",
            "action_id": "issue_noc",
            "target_card": "form_noc_print",
            "icon": "fa-certificate",
            "color": "dark",
            "roles": ["admin"],          # admin only; eligibility checked server-side
        },
    ],

    # ── VENDORS ─────────────────────────────────────────────────────────────
    "vendors": [
        {
            "label": "Sell Pass",
            "action_id": "sell_vendor_pass",
            "target_card": "form_vendor_pass_new",
            "icon": "fa-id-card",
            "color": "success",
            "roles": ["admin"],
        },
        {
            "label": "Show Cashbook",
            "action_id": "show_cashbook",
            "target_card": "list_cashbook",
            "icon": "fa-book",
            "color": "info",
        },
        {
            "label": "Gate Pass",
            "action_id": "show_qr",
            "target_card": "modal_qr",
            "icon": "fa-qrcode",
            "color": "primary",
        },
    ],

    # ── SECURITY ─────────────────────────────────────────────────────────────
    "security": [
        {
            "label": "Show Cashbook",
            "action_id": "show_cashbook",
            "target_card": "list_cashbook",
            "icon": "fa-book",
            "color": "info",
        },
        {
            "label": "Gate Pass",
            "action_id": "show_qr",
            "target_card": "modal_qr",
            "icon": "fa-qrcode",
            "color": "primary",
        },
    ],

    # ── CONCERNS ─────────────────────────────────────────────────────────────
    "concerns": [
        {
            "label": "Assign",
            "action_id": "assign",
            "target_card": "form_concern_edit",
            "icon": "fa-user-check",
            "color": "warning",
        },
        {
            "label": "Resolve",
            "action_id": "resolve",
            "target_card": "form_concern_edit",
            "icon": "fa-check",
            "color": "success",
        },
    ],

    # ── RECEIVABLES  (read-only tab — Verify is the only action) ────────────
    "receivables": [
        {
            "label": "Verify",
            "action_id": "verify_receivable",
            "target_card": None,         # server-side only — no navigation
            "icon": "fa-check-double",
            "color": "success",
            "roles": ["admin"],          # admin-only; enforced in renderers.py
        },
        {
            "label": "Pay Due",
            "action_id": "pay_due_receivable",
            "target_card": "form_pay_dues_new",
            "icon": "fa-rupee-sign",
            "color": "primary",
            "roles": ["admin"],
        },
    ],

    # ── PAYMENTS  (read-only tab — Verify is the only action) ───────────────
    "payments": [
        {
            "label": "Verify",
            "action_id": "verify_payment",
            "target_card": None,         # server-side only — no navigation
            "icon": "fa-check-double",
            "color": "success",
            "roles": ["admin"],
        },
    ],
    # ── RECEIPTS ─────────────────────────────────────────────────────────────
    "receipts_tbl": [
        {
            "label": "Verify & Post",
            "action_id": "verify_receipt",
            "target_card": None,        # server-side only
            "icon": "fa-check-double",
            "color": "success",
            "roles": ["admin"],
        },
    ],
    # ── ASSETS ───────────────────────────────────────────────────────────────
    "assets": [
        {
            "label": "Sell / Dispose",
            "action_id": "dispose_asset",
            "target_card": "form_asset_dispose_new",
            "icon": "fa-sign-out-alt",
            "color": "danger",
            "roles": ["admin"],
        },
    ],

    # ── APT CHARGES ──────────────────────────────────────────────────────────
    "apt_charges": [
        {
            "label": "Show Transactions",
            "action_id": "show_transactions",
            "target_card": "list_cashbook",
            "icon": "fa-book",
            "color": "info",
        },
    ],

    # ── VEN CHARGES ──────────────────────────────────────────────────────────
    "ven_charges": [
        {
            "label": "Show Transactions",
            "action_id": "show_transactions",
            "target_card": "list_cashbook",
            "icon": "fa-book",
            "color": "info",
        },
    ],
}


# ── Per-field RBAC ───────────────────────────────────────────────────────────
# Only fields that are MORE restrictive than the rest of their entity's row
# need an entry here. Everything else inherits from the portal permission matrix.
FIELD_VISIBILITY: dict[str, dict[str, set[str]]] = {
    "security": {
        "salary_per_shift": {"admin", "master"},
        "salary_due":       {"admin", "master"},
        "salary_paid":      {"admin", "master"},
    },
    "vendors": {
        "mobile":  {"admin", "master", "vendor"},
    },
    "apartments": {
        "mobile":  {"admin", "master", "apartment"},
    },
    "receivables": {
        # All portals can VIEW their own receivables;
        # 'confirmed_by' and 'confirmed_at' are admin-only columns
        "confirmed_by": {"admin", "master"},
        "confirmed_at": {"admin", "master"},
    },
    "payments": {
        "confirmed_by": {"admin", "master"},
        "confirmed_at": {"admin", "master"},
    },
}
