# app/dash_apps/drilldown/profile_actions.py
"""
Profile action buttons — application WORKFLOW, not data structure.
A database has no concept of "clicking Pay Dues opens a pre-filled
receipt form", so this can't be derived from information_schema. Kept
separate from schema_introspect.py so it's obvious this is the one
hand-maintained piece, and it stays small (a few lines per entity, not
full field definitions).
"""

PROFILE_ACTIONS: dict[str, list[dict]] = {
    "apartments": [
        {"label": "Pay Dues", "action_id": "pay_dues", "target_card": "form_receipt_new", "icon": "fa-rupee-sign", "color": "success"},
        {"label": "Show Cashbook", "action_id": "show_cashbook", "target_card": "list_cashbook", "icon": "fa-book", "color": "info"},
        {"label": "Gate Pass", "action_id": "show_qr", "target_card": "modal_qr", "icon": "fa-qrcode", "color": "primary"},
        {"label": "Raise Issue", "action_id": "new_concern", "target_card": "form_concern_new", "icon": "fa-comment-alt", "color": "warning"},
    ],
    "vendors": [
        {"label": "Pay Dues", "action_id": "pay_dues", "target_card": "form_receipt_new", "icon": "fa-rupee-sign", "color": "success"},
        {"label": "Show Cashbook", "action_id": "show_cashbook", "target_card": "list_cashbook", "icon": "fa-book", "color": "info"},
        {"label": "Gate Pass", "action_id": "show_qr", "target_card": "modal_qr", "icon": "fa-qrcode", "color": "primary"},
    ],
    "security": [
        {"label": "Show Cashbook", "action_id": "show_cashbook", "target_card": "list_cashbook", "icon": "fa-book", "color": "info"},
        {"label": "Gate Pass", "action_id": "show_qr", "target_card": "modal_qr", "icon": "fa-qrcode", "color": "primary"},
    ],
    "concerns": [
        {"label": "Assign", "action_id": "assign", "target_card": "form_concern_edit", "icon": "fa-user-check", "color": "warning"},
        {"label": "Resolve", "action_id": "resolve", "target_card": "form_concern_edit", "icon": "fa-check", "color": "success"},
    ],
    "apt_charges": [
        {"label": "Show Transactions", "action_id": "show_transactions", "target_card": "list_cashbook", "icon": "fa-book", "color": "info"},
    ],
    "ven_charges": [
        {"label": "Show Transactions", "action_id": "show_transactions", "target_card": "list_cashbook", "icon": "fa-book", "color": "info"},
    ],
}
# Per-field RBAC, keyed by PLURAL entity name (matches list/loader keys).
# Most fields inherit visibility from the list/profile permission matrix in
# renderers.py — only add an entry here for a field that's more sensitive
# than the rest of its row. Empty/missing entry = visible to anyone who can
# already see the list or profile.
FIELD_VISIBILITY: dict[str, dict[str, set[str]]] = {
    "security": {
        "salary_per_shift": {"admin", "master"},
    },
    "vendors": {
        "mobile": {"admin", "master", "vendor"},
    },
    "apartments": {
        "mobile": {"admin", "master", "apartment"},
    },
}