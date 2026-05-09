"""
card_catalogue.py
Master catalogue of every KPI, Form and List card.
Drop into: app/dash_apps/pages/card_catalogue.py
"""

import base64
import json
from dash import html, dcc
import dash_bootstrap_components as dbc

# ================================================================
# ── KPI CARD DEFINITIONS
# ================================================================

KPI_CARDS = {
    "kpi_apartments_total": {
        "query": "SELECT COUNT(*) AS v FROM apartments WHERE society_id = %s",
        "params": 1, "format": "count",
    },
    "kpi_apartments_dues": {
        "query": "SELECT COUNT(DISTINCT apartment_id) AS v FROM payments WHERE society_id = %s AND status = 'pending'",
        "params": 1, "format": "count",
    },
    "kpi_apartments_no_dues": {
        "query": "SELECT COUNT(*) AS v FROM apartments WHERE society_id = %s AND id NOT IN (SELECT DISTINCT apartment_id FROM payments WHERE society_id = %s AND status = 'pending' AND apartment_id IS NOT NULL)",
        "params": 2, "format": "count",   # note: params=2
    },
    "kpi_vendors_total": {
        "query": "SELECT COUNT(*) AS v FROM users WHERE society_id = %s AND role = 'vendor'",
        "params": 1, "format": "count",
    },
    "kpi_vendors_dues": {
        "query": "SELECT COUNT(DISTINCT user_id) AS v FROM payments WHERE society_id = %s AND status = 'pending' AND user_id IS NOT NULL",
        "params": 1, "format": "count",
    },
    "kpi_security_total": {
        "query": "SELECT COUNT(*) AS v FROM users WHERE society_id = %s AND role = 'security'",
        "params": 1, "format": "count",
    },
    "kpi_security_on_duty": {
        "query": "SELECT COUNT(*) AS v FROM gate_access WHERE society_id = %s AND role = 's' AND time_out IS NULL",
        "params": 1, "format": "count",
    },
    "kpi_events_total": {
        "query": "SELECT COUNT(*) AS v FROM events WHERE society_id = %s AND event_date >= CURRENT_DATE",
        "params": 1, "format": "count",
    },
    "kpi_concerns_open": {
        "query": "SELECT COUNT(*) AS v FROM concerns WHERE society_id = %s AND status = 'open'",
        "params": 1, "format": "count",
    },
    "kpi_gate_logs_today": {
        "query": "SELECT COUNT(*) AS v FROM gate_access WHERE society_id = %s AND time_in >= CURRENT_DATE",
        "params": 1, "format": "count",
    },
    "kpi_receipts_month": {
        "query": "SELECT COALESCE(SUM(amount), 0) AS v FROM transactions WHERE society_id = %s AND status = 'paid' AND trx_date >= DATE_TRUNC('month', CURRENT_DATE)",
        "params": 1, "format": "currency",
    },
    "kpi_expenses_month": {
        "query": "SELECT COALESCE(SUM(amount), 0) AS v FROM transactions WHERE society_id = %s AND status = 'paid' AND trx_date >= DATE_TRUNC('month', CURRENT_DATE)",
        "params": 1, "format": "currency",
    },
    "kpi_balance": {
        "query": "SELECT COALESCE(SUM(amount), 0) AS v FROM transactions WHERE society_id = %s AND status = 'paid'",
        "params": 1, "format": "currency",
    },
    "kpi_societies_total": {
        "query": "SELECT COUNT(*) AS v FROM societies",
        "params": 0, "format": "count",
    },
    "kpi_societies_paid": {
        "query": "SELECT COUNT(*) AS v FROM societies WHERE plan != 'Free'",
        "params": 0, "format": "count",
    },
    "kpi_societies_free": {
        "query": "SELECT COUNT(*) AS v FROM societies WHERE plan = 'Free'",
        "params": 0, "format": "count",
    },
}

# ================================================================
# ── FORM / LIST CARD DEFINITIONS
# ================================================================
FORM_CARDS = {
    # ────────────────────── SOCIETY ──────────────────────────────
    "society_profile": {
        "group": "Society", "title": "Society Profile", "icon": "fa-building",
        "type": "profile", "entity": "society",
        "fields": [
            {"id": "soc-name",      "label": "Society Name *", "type": "text"},
            {"id": "soc-email",     "label": "Email",          "type": "email"},
            {"id": "soc-phone",     "label": "Phone",          "type": "tel"},
            {"id": "soc-address",   "label": "Address",        "type": "textarea"},
            {"id": "soc-sec-name",  "label": "Secretary Name", "type": "text"},
            {"id": "soc-sec-phone", "label": "Secretary Phone","type": "tel"},
            {"id": "soc-plan",      "label": "Plan",           "type": "select",
             "options": ["Free","Basic","Pro","Enterprise"]},
        ],
        "save_btn": "save-society-profile-btn",
        "load_output": ["soc-name","soc-email","soc-phone","soc-address",
                        "soc-sec-name","soc-sec-phone","soc-plan"],
    },
    "society_create": {
        "group": "Society", "title": "Create Society", "icon": "fa-plus-circle",
        "type": "create", "entity": "society",
        "fields": [
            {"id": "new-soc-name",      "label": "Society Name *", "type": "text"},
            {"id": "new-soc-email",     "label": "Email",          "type": "email"},
            {"id": "new-soc-phone",     "label": "Phone",          "type": "tel"},
            {"id": "new-soc-address",   "label": "Address",        "type": "textarea"},
            {"id": "new-soc-sec-name",  "label": "Secretary Name", "type": "text"},
            {"id": "new-soc-sec-phone", "label": "Secretary Phone","type": "tel"},
            {"id": "new-soc-plan",      "label": "Plan",           "type": "select",
             "options": ["Free","Basic","Pro","Enterprise"]},
            {"id": "new-soc-validity",  "label": "Plan Validity",  "type": "date"},
            {"id": "new-admin-email",   "label": "Admin Email *",  "type": "email"},
            {"id": "new-admin-pass",    "label": "Admin Password *","type": "password"},
            {"id": "soc-logo-upload",   "label": "Logo",           "type": "upload",
             "accept": "image/*"},
            {"id": "soc-sign-upload",   "label": "Secretary Sign", "type": "upload",
             "accept": "image/*"},
            {"id": "soc-bg-upload",     "label": "Login Background","type": "upload",
             "accept": "image/*"},
        ],
        "save_btn": "create-society-btn",
    },
    "society_list": {
        "group": "Society", "title": "Societies List", "icon": "fa-list",
        "type": "list", "entity": "society",
        "columns": ["ID","Name","Email","Phone","Plan","Created","Actions"],
        "list_id": "societies-list-table",
    },
    # ────────────────────── ENTITIES ─────────────────────────────
    "entity_profile": {
        "group": "Entities", "title": "Entity Profile", "icon": "fa-id-card",
        "type": "profile", "entity": "entity",
        "fields": [
            {"id": "ent-flat",   "label": "Flat / Unit No",  "type": "text"},
            {"id": "ent-name",   "label": "Owner / Name *",  "type": "text"},
            {"id": "ent-mobile", "label": "Mobile",          "type": "tel"},
            {"id": "ent-size",   "label": "Area (sq ft)",    "type": "number"},
            {"id": "ent-role",   "label": "Role",            "type": "select",
             "options": ["apartment","vendor","security"]},
            {"id": "ent-email",  "label": "Email",           "type": "email"},
            {"id": "ent-active", "label": "Active",          "type": "checkbox"},
        ],
        "save_btn": "save-entity-profile-btn",
        "load_output": ["ent-flat","ent-name","ent-mobile","ent-size",
                        "ent-role","ent-email"],
    },
    "entity_create": {
        "group": "Entities", "title": "Create Entity", "icon": "fa-user-plus",
        "type": "create", "entity": "entity",
        "fields": [
            {"id": "new-ent-flat",    "label": "Flat / Unit No",   "type": "text"},
            {"id": "new-ent-name",    "label": "Owner / Name *",   "type": "text"},
            {"id": "new-ent-mobile",  "label": "Mobile",           "type": "tel"},
            {"id": "new-ent-size",    "label": "Area (sq ft)",     "type": "number"},
            {"id": "new-ent-role",    "label": "Role *",           "type": "select",
             "options": ["apartment","vendor","security"]},
            {"id": "new-ent-email",   "label": "Login Email *",    "type": "email"},
            {"id": "new-ent-pass",    "label": "Password *",       "type": "password"},
            {"id": "new-ent-avatar",  "label": "Avatar",           "type": "upload",
             "accept": "image/*"},
        ],
        "save_btn": "create-entity-btn",
    },
    "entity_list": {
        "group": "Entities", "title": "Entities List", "icon": "fa-users",
        "type": "list", "entity": "entity",
        "columns": ["ID","Flat","Name","Role","Email","Active","Actions"],
        "list_id": "entities-list-table",
    },
    # ────────────────────── ACCOUNTS ─────────────────────────────
    "account_profile": {
        "group": "Accounts", "title": "Account Profile", "icon": "fa-book",
        "type": "profile", "entity": "account",
        "fields": [
            {"id": "acc-name",   "label": "Account Code *", "type": "text"},
            {"id": "acc-tab",    "label": "Tab / Group",    "type": "text"},
            {"id": "acc-header", "label": "Header",         "type": "text"},
            {"id": "acc-parent", "label": "Parent Account", "type": "text"},
            {"id": "acc-drcr",   "label": "Dr / Cr",        "type": "select",
             "options": ["Dr","Cr"]},
            {"id": "acc-bf-amt", "label": "Opening Balance","type": "number"},
            {"id": "acc-bf-type","label": "Opening Bal Type","type": "select",
             "options": ["Dr","Cr"]},
            {"id": "acc-dep-pct","label": "Depreciation %", "type": "number"},
        ],
        "save_btn": "save-account-profile-btn",
    },
    "account_create": {
        "group": "Accounts", "title": "Create Account", "icon": "fa-plus-circle",
        "type": "create", "entity": "account",
        "fields": [
            {"id": "new-acc-name",   "label": "Account Code *", "type": "text"},
            {"id": "new-acc-tab",    "label": "Tab / Group",    "type": "text"},
            {"id": "new-acc-header", "label": "Header",         "type": "text"},
            {"id": "new-acc-parent", "label": "Parent Account", "type": "text"},
            {"id": "new-acc-drcr",   "label": "Dr / Cr *",      "type": "select",
             "options": ["Dr","Cr"]},
            {"id": "new-acc-bf-amt", "label": "Opening Balance","type": "number"},
            {"id": "new-acc-bf-type","label": "Opening Bal Type","type": "select",
             "options": ["Dr","Cr"]},
        ],
        "save_btn": "create-account-btn",
    },
    "account_list": {
        "group": "Accounts", "title": "Accounts List", "icon": "fa-list",
        "type": "list", "entity": "account",
        "columns": ["Code","Group","Header","Dr/Cr","Opening Bal","Actions"],
        "list_id": "accounts-list-table",
    },
    # ────────────────────── TRANSACTIONS / PAYMENTS ──────────────
    "payment_profile": {
        "group": "Payments", "title": "Payment Profile", "icon": "fa-credit-card",
        "type": "profile", "entity": "payment",
        "fields": [
            {"id": "pay-flat",   "label": "Flat / Entity",  "type": "text"},
            {"id": "pay-amount", "label": "Amount *",       "type": "number"},
            {"id": "pay-type",   "label": "Payment Type",   "type": "select",
             "options": ["maintenance","late_fee","fine","other"]},
            {"id": "pay-method", "label": "Method",         "type": "select",
             "options": ["cash","upi","card","bank","cheque"]},
            {"id": "pay-status", "label": "Status",         "type": "select",
             "options": ["pending","verified","failed"]},
            {"id": "pay-due",    "label": "Due Date",       "type": "date"},
            {"id": "pay-txn",    "label": "Transaction ID", "type": "text"},
        ],
        "save_btn": "save-payment-profile-btn",
    },
    "transaction_create": {
        "group": "Payments", "title": "New Transaction", "icon": "fa-plus-circle",
        "type": "create", "entity": "transaction",
        "fields": [
            {"id": "new-trx-date",   "label": "Date *",         "type": "date"},
            {"id": "new-trx-acc",    "label": "Account",        "type": "text"},
            {"id": "new-trx-part",   "label": "Particulars *",  "type": "text"},
            {"id": "new-trx-amount", "label": "Amount *",       "type": "number"},
            {"id": "new-trx-mode",   "label": "Mode",           "type": "select",
             "options": ["cash","online","cheque","other"]},
        ],
        "save_btn": "create-transaction-btn",
    },
    "payment_list": {
        "group": "Payments", "title": "Payments List", "icon": "fa-list",
        "type": "list", "entity": "payment",
        "columns": ["Date","Flat","Type","Amount","Method","Status","Actions"],
        "list_id": "payments-list-table",
    },
    # ────────────────────── CHARGES ──────────────────────────────
    "charge_profile": {
        "group": "Charges", "title": "Charge Profile", "icon": "fa-file-invoice",
        "type": "profile", "entity": "charge",
        "fields": [
            {"id": "chg-name",   "label": "Charge Name *",  "type": "text"},
            {"id": "chg-amt",    "label": "Amount / Rate",  "type": "number"},
            {"id": "chg-type",   "label": "Charge Type",    "type": "select",
             "options": ["fixed","per_sqft","per_unit","percent"]},
            {"id": "chg-entity", "label": "Applies To",     "type": "select",
             "options": ["all","apartment","vendor","security"]},
            {"id": "chg-freq",   "label": "Frequency",      "type": "select",
             "options": ["monthly","quarterly","annual","one-time"]},
            {"id": "chg-due",    "label": "Due Day",        "type": "number"},
        ],
        "save_btn": "save-charge-profile-btn",
    },
    "charge_create": {
        "group": "Charges", "title": "Create Charge", "icon": "fa-plus-circle",
        "type": "create", "entity": "charge",
        "fields": [
            {"id": "new-chg-name",   "label": "Charge Name *","type": "text"},
            {"id": "new-chg-amt",    "label": "Amount / Rate","type": "number"},
            {"id": "new-chg-type",   "label": "Charge Type",  "type": "select",
             "options": ["fixed","per_sqft","per_unit","percent"]},
            {"id": "new-chg-entity", "label": "Applies To",   "type": "select",
             "options": ["all","apartment","vendor","security"]},
            {"id": "new-chg-freq",   "label": "Frequency",    "type": "select",
             "options": ["monthly","quarterly","annual","one-time"]},
            {"id": "new-chg-due",    "label": "Due Day",      "type": "number"},
        ],
        "save_btn": "create-charge-btn",
    },
    "charge_list": {
        "group": "Charges", "title": "Charges List", "icon": "fa-list",
        "type": "list", "entity": "charge",
        "columns": ["Name","Type","Rate","Applies To","Frequency","Due Day","Actions"],
        "list_id": "charges-list-table",
    },
    # ────────────────────── CASHBOOK ─────────────────────────────
    "new_receipt": {
        "group": "Cashbook", "title": "New Receipt (Credit)", "icon": "fa-receipt",
        "type": "create", "entity": "receipt",
        "fields": [
            {"id": "rcpt-date",  "label": "Date *",        "type": "date"},
            {"id": "rcpt-acc",   "label": "Account",       "type": "text"},
            {"id": "rcpt-from",  "label": "Received From *","type": "text"},
            {"id": "rcpt-part",  "label": "Particulars *", "type": "text"},
            {"id": "rcpt-amt",   "label": "Amount *",      "type": "number"},
            {"id": "rcpt-mode",  "label": "Mode",          "type": "select",
             "options": ["cash","upi","card","bank","cheque"]},
        ],
        "save_btn": "create-receipt-btn",
    },
    "new_expense": {
        "group": "Cashbook", "title": "New Expense (Debit)", "icon": "fa-money-bills",
        "type": "create", "entity": "expense",
        "fields": [
            {"id": "exp-date",  "label": "Date *",       "type": "date"},
            {"id": "exp-acc",   "label": "Account",      "type": "text"},
            {"id": "exp-to",    "label": "Paid To *",    "type": "text"},
            {"id": "exp-part",  "label": "Particulars *","type": "text"},
            {"id": "exp-amt",   "label": "Amount *",     "type": "number"},
            {"id": "exp-mode",  "label": "Mode",         "type": "select",
             "options": ["cash","upi","card","bank","cheque"]},
        ],
        "save_btn": "create-expense-btn",
    },
    "cashbook_list": {
        "group": "Cashbook", "title": "Cashbook", "icon": "fa-wallet",
        "type": "list", "entity": "cashbook",
        "columns": ["Date","Particulars","Account","Debit","Credit","Balance","Actions"],
        "list_id": "cashbook-full-table",
    },
    # ────────────────────── EVENTS ───────────────────────────────
    "event_profile": {
        "group": "Events", "title": "Event Profile", "icon": "fa-calendar-check",
        "type": "profile", "entity": "event",
        "fields": [
            {"id": "evt-title",  "label": "Title *",     "type": "text"},
            {"id": "evt-desc",   "label": "Description", "type": "textarea"},
            {"id": "evt-date",   "label": "Event Date *","type": "date"},
            {"id": "evt-time",   "label": "Time",        "type": "text"},
            {"id": "evt-venue",  "label": "Venue",       "type": "text"},
            {"id": "evt-open",   "label": "Open To",     "type": "select",
             "options": ["all","apartment","vendor","security"]},
        ],
        "save_btn": "save-event-profile-btn",
    },
    "event_create": {
        "group": "Events", "title": "Create Event", "icon": "fa-plus-circle",
        "type": "create", "entity": "event",
        "fields": [
            {"id": "new-evt-title", "label": "Title *",    "type": "text"},
            {"id": "new-evt-desc",  "label": "Description","type": "textarea"},
            {"id": "new-evt-date",  "label": "Event Date *","type": "date"},
            {"id": "new-evt-time",  "label": "Time",       "type": "text"},
            {"id": "new-evt-venue", "label": "Venue",      "type": "text"},
            {"id": "new-evt-open",  "label": "Open To",    "type": "select",
             "options": ["all","apartment","vendor","security"]},
        ],
        "save_btn": "create-event-btn",
    },
    "event_list": {
        "group": "Events", "title": "Events List", "icon": "fa-list",
        "type": "list", "entity": "event",
        "columns": ["Date","Title","Venue","Open To","Actions"],
        "list_id": "events-list-table",
    },
    # ────────────────────── GATE LOGS ────────────────────────────
    "gate_log_profile": {
        "group": "Gate Logs", "title": "Gate Log Profile", "icon": "fa-receipt",
        "type": "profile", "entity": "gate_log",
        "fields": [
            {"id": "gl-entity", "label": "Person / Flat",  "type": "text"},
            {"id": "gl-role",   "label": "Role",           "type": "select",
             "options": ["a","v","s","g"]},
            {"id": "gl-in",     "label": "Time In",        "type": "text"},
            {"id": "gl-out",    "label": "Time Out",       "type": "text"},
        ],
        "save_btn": "save-gate-log-btn",
    },
    "gate_log_create": {
        "group": "Gate Logs", "title": "Create Gate Log", "icon": "fa-plus-circle",
        "type": "create", "entity": "gate_log",
        "fields": [
            {"id": "new-gl-entity", "label": "Entity ID / Flat *","type": "text"},
            {"id": "new-gl-role",   "label": "Role *",            "type": "select",
             "options": ["apartment (a)","vendor (v)","security (s)","guest (g)"]},
            {"id": "new-gl-in",     "label": "Time In *",         "type": "text"},
            {"id": "new-gl-out",    "label": "Time Out",          "type": "text"},
        ],
        "save_btn": "create-gate-log-btn",
    },
    "gate_log_list": {
        "group": "Gate Logs", "title": "Gate Logs List", "icon": "fa-list",
        "type": "list", "entity": "gate_log",
        "columns": ["Time In","Time Out","Person","Role","Duration","Actions"],
        "list_id": "gate-logs-list-table",
    },
    # ────────────────────── CONCERNS ─────────────────────────────
    "concern_profile": {
        "group": "Concerns", "title": "Concern Profile", "icon": "fa-hand-point-up",
        "type": "profile", "entity": "concern",
        "fields": [
            {"id": "con-flat",    "label": "Flat / By",   "type": "text"},
            {"id": "con-type",    "label": "Type",        "type": "select",
             "options": ["plumbing","electrical","cleaning","security","other"]},
            {"id": "con-desc",    "label": "Description", "type": "textarea"},
            {"id": "con-status",  "label": "Status",      "type": "select",
             "options": ["open","in_progress","resolved","closed"]},
            {"id": "con-assigned","label": "Assigned To", "type": "text"},
        ],
        "save_btn": "save-concern-profile-btn",
    },
    "concern_create": {
        "group": "Concerns", "title": "Create Concern", "icon": "fa-plus-circle",
        "type": "create", "entity": "concern",
        "fields": [
            {"id": "new-con-flat",   "label": "Flat / By *", "type": "text"},
            {"id": "new-con-type",   "label": "Type *",      "type": "select",
             "options": ["plumbing","electrical","cleaning","security","other"]},
            {"id": "new-con-desc",   "label": "Description","type": "textarea"},
            {"id": "new-con-pref",   "label": "Preferred Time","type": "select",
             "options": ["morning","afternoon","evening","anytime"]},
        ],
        "save_btn": "create-concern-btn",
    },
    "concern_list": {
        "group": "Concerns", "title": "Concerns List", "icon": "fa-list",
        "type": "list", "entity": "concern",
        "columns": ["Flat","Type","Description","Status","Assigned","Actions"],
        "list_id": "concerns-list-table",
    },
    # ────────────────────── EVALUATE PASS ────────────────────────
    "evaluate_pass": {
        "group": "Security", "title": "Evaluate Pass", "icon": "fa-qrcode",
        "type": "special", "entity": "gate_pass",
        "component": "evaluate_pass_card",
    },
    # ────────────────────── SETTINGS ─────────────────────────────
    "settings_rates": {
        "group": "Settings", "title": "Rates & Fines", "icon": "fa-sliders-h",
        "type": "create", "entity": "settings",
        "fields": [
            {"id": "rate-maint",     "label": "Maintenance Rate (₹/sq ft)", "type": "number"},
            {"id": "rate-due-day",   "label": "Due Day of Month",           "type": "number"},
            {"id": "rate-late-day",  "label": "Late Fee (₹/day)",           "type": "number"},
            {"id": "rate-late-max",  "label": "Max Late Fee (%)",           "type": "number"},
            {"id": "rate-vendor",    "label": "Vendor Monthly Fee (₹)",     "type": "number"},
            {"id": "rate-security",  "label": "Security Monthly (₹)",       "type": "number"},
            {"id": "rate-arrear-dt", "label": "Arrear Start Date",          "type": "date"},
        ],
        "save_btn": "save-rates-fines-btn",
    },
}

# ================================================================
# ── MASTER CATALOGUE
# ================================================================
CARD_CATALOGUE = {**KPI_CARDS, **FORM_CARDS}

# ── Default dashboard cards per portal ─────────────────────────
DEFAULT_LAYOUTS = {
    "admin":    ["apts_with_dues","pending_dues","receipts_month","balance"],
    "apartment":["apts_no_dues","gate_logs_today","events_count","concerns_open"],
    "vendor":   ["vendors_no_dues","gate_logs_today","events_count","concerns_open"],
    "security": ["security_on_duty","security_off_duty","gate_logs_today","concerns_open"],
    "master":   ["apts_total","vendors_total","receipts_month","balance"],
}


# ================================================================
# ── RENDERERS
# ================================================================

def make_kpi_card(card_id: str, value: str = "—") -> html.Div:
    cfg = KPI_CARDS.get(card_id, {})
    color  = cfg.get("color", "#3498db")
    icon   = cfg.get("icon", "fa-chart-bar")
    title  = cfg.get("title", card_id)
    subtitle = cfg.get("group", "")
    return html.Div(
        [
            html.Div("⠿", className="dnd-handle",
                     style={"position":"absolute","top":"7px","left":"9px",
                            "fontSize":"16px","color":"#ccc","cursor":"grab",
                            "userSelect":"none","letterSpacing":"2px"}),
            html.Div([
                html.I(className=f"fas {icon}",
                       style={"color": color, "fontSize": "20px"}),
                html.Div(title, style={"fontSize":"11px","fontWeight":"500",
                                       "color":"#888","marginTop":"5px"}),
                html.Div(
                    value,
                    id={"type": "kpi-value", "card_id": card_id},
                    style={"fontSize":"20px","fontWeight":"700",
                        "color":"#2c3e50","margin":"2px 0"}
                ),
                html.Div(subtitle, style={"fontSize":"10px","color":"#aaa"}),
            ], style={"textAlign":"center"}),
        ],
        # ─── CHANGED: Dict ID for pattern matching + n_clicks ───
        id={"type": "kpi-card", "card_id": card_id},
        n_clicks=0,
        # ─────────────────────────────────────────────────────────
        **{"data-card-id": card_id, "data-card-type": "kpi"},
        className="dnd-card",
        style={
            "position":"relative","background":"white","borderRadius":"12px",
            "padding":"16px 12px 12px","borderLeft":f"4px solid {color}",
            "boxShadow":"0 2px 8px rgba(0,0,0,0.07)",
            "cursor":"pointer", 
            "userSelect":"none",
            "transition": "transform 0.1s, box-shadow 0.1s",  # ← ADDED
        },
    )

def _make_field(f: dict) -> dbc.Row:
    """Render a single form field."""
    fid  = f["id"]
    lbl  = f.get("label", fid)
    ftype = f.get("type", "text")

    if ftype == "select":
        opts = [{"label": o.title(), "value": o} for o in f.get("options", [])]
        ctrl = dcc.Dropdown(id=fid, options=opts,
                            placeholder=f"Select {lbl.rstrip(' *')}",
                            clearable=False,
                            style={"fontSize":"13px"})
    elif ftype == "textarea":
        ctrl = dbc.Textarea(id=fid, rows=2,
                            placeholder=lbl.rstrip(" *"),
                            style={"fontSize":"13px"})
    elif ftype == "upload":
        ctrl = dcc.Upload(
            id=fid,
            children=html.Div([
                html.I(className="fas fa-cloud-upload-alt me-1"),
                html.Span(f.get("accept", "file"), style={"fontSize":"11px"})
            ]),
            accept=f.get("accept", "*"),
            style={"border":"1px dashed #ccc","borderRadius":"6px",
                   "padding":"6px 10px","textAlign":"center","cursor":"pointer",
                   "background":"#fafafa","fontSize":"12px"},
        )
    elif ftype == "checkbox":
        ctrl = dbc.Checkbox(id=fid, label=lbl.rstrip(" *"))
    elif ftype == "date":
        ctrl = dcc.DatePickerSingle(id=fid, style={"width":"100%"})
    else:
        ctrl = dbc.Input(id=fid, type=ftype,
                         placeholder=lbl.rstrip(" *"),
                         style={"fontSize":"13px"})

    return dbc.Row([
        dbc.Col(html.Label(lbl,
                           style={"fontSize":"12px","color":"#666",
                                  "marginBottom":"0","paddingTop":"6px"}),
                width=4),
        dbc.Col(ctrl, width=8),
    ], className="mb-2")


def _evaluate_pass_card_body():
    """
    Evaluate Pass card body.

    Features
    --------
    • Manual QR input + Validate button
    • Camera preview with animated scan-line overlay
    • Defaults to BACK camera (facingMode: environment) — ideal for QR
    • Flip button: toggles front ↔ back, label updates to show next option
    • Torch / flashlight button (appears only when device supports it)
    • Auto-stops camera immediately after a QR is decoded (saves battery)
    • "Start Camera" button re-activates it
    • Running log of the last 10 scan results (Recent Scans panel)

    DOM IDs consumed by camera_callbacks.py
    ----------------------------------------
    eval-qr-input       dcc.Input (debounce=True)
    eval-validate-btn   dbc.Button
    eval-result         html.Div  — result display
    eval-scan-status    html.Small — status line
    eval-video          html.Video
    eval-canvas         html.Canvas (hidden)
    eval-scanline       html.Div  — animated overlay
    eval-start-btn      dbc.Button
    eval-stop-btn       dbc.Button
    eval-switch-btn     dbc.Button
    eval-torch-btn      dbc.Button
   
    eval-recent-scans   dbc.ListGroup — rendered log
    """
    return dbc.CardBody(
        [


            # ── Manual entry row ──────────────────────────────────────
            dcc.Input(
                id="eval-qr-input",
                type="text",
                placeholder="Scan QR or type code manually…",
                debounce=True,          # fires on Enter / blur
                style={
                    "width": "100%", "padding": "9px 12px",
                    "fontSize": "13px", "borderRadius": "7px",
                    "border": "1px solid #ddd", "marginBottom": "8px",
                    "outline": "none",
                },
            ),
            dbc.Button(
                [html.I(className="fas fa-check-circle me-2"), "Validate"],
                id="eval-validate-btn",
                color="primary", size="sm",
                className="w-100 mb-3",
            ),

            # ── Result panel ──────────────────────────────────────────
            html.Div(
                id="eval-result",
                style={
                    "minHeight": "72px",
                    "borderRadius": "10px",
                    "padding": "8px",
                    "transition": "background 0.3s",
                },
            ),

            html.Hr(style={"margin": "10px 0"}),

            # ── Camera section ────────────────────────────────────────
            html.Div([

                # Video + scan-line overlay wrapper
                html.Div(
                    style={
                        "position": "relative",
                        "borderRadius": "10px",
                        "overflow": "hidden",
                        "background": "#111",
                    },
                    children=[
                        # Live video feed
                        html.Video(
                            id="eval-video",
                            autoPlay=True,
                            playsInline=True,
                            muted=True,
                            style={
                                "width": "100%",
                                "maxHeight": "220px",
                                "objectFit": "cover",
                                "display": "none",          # shown by JS
                                "borderRadius": "10px",
                            },
                        ),

                        # Scan-line animation (shown while scanning)
                        html.Div(
                            id="eval-scanline",
                            style={
                                "display": "none",          # shown by JS
                                "position": "absolute",
                                "left": "0", "right": "0",
                                "top": "0",
                                "height": "3px",
                                "background": (
                                    "linear-gradient(90deg,"
                                    "transparent 0%,"
                                    "#667eea 50%,"
                                    "transparent 100%)"
                                ),
                                "animation": "evalScanLine 1.8s ease-in-out infinite",
                            },
                        ),

                        # Corner markers (decorative targeting UI)
                        html.Div(
                            id="eval-corners",
                            style={"display": "none"},      # shown by JS
                            children=[
                                html.Div(style={
                                    "position": "absolute",
                                    "width": "22px", "height": "22px",
                                    "border": "3px solid #667eea",
                                    "borderRight": "none", "borderBottom": "none",
                                    "top": "10px", "left": "10px",
                                    "borderRadius": "3px 0 0 0",
                                }),
                                html.Div(style={
                                    "position": "absolute",
                                    "width": "22px", "height": "22px",
                                    "border": "3px solid #667eea",
                                    "borderLeft": "none", "borderBottom": "none",
                                    "top": "10px", "right": "10px",
                                    "borderRadius": "0 3px 0 0",
                                }),
                                html.Div(style={
                                    "position": "absolute",
                                    "width": "22px", "height": "22px",
                                    "border": "3px solid #667eea",
                                    "borderRight": "none", "borderTop": "none",
                                    "bottom": "10px", "left": "10px",
                                    "borderRadius": "0 0 0 3px",
                                }),
                                html.Div(style={
                                    "position": "absolute",
                                    "width": "22px", "height": "22px",
                                    "border": "3px solid #667eea",
                                    "borderLeft": "none", "borderTop": "none",
                                    "bottom": "10px", "right": "10px",
                                    "borderRadius": "0 0 3px 0",
                                }),
                            ],
                        ),

                        # Hidden canvas — frame capture for jsQR decode
                        html.Canvas(id="eval-canvas", style={"display": "none"}),
                    ],
                ),

                # Status text line
                html.Small(
                    id="eval-scan-status",
                    children="📷 Camera off — tap Start to scan",
                    style={
                        "display": "block",
                        "textAlign": "center",
                        "fontSize": "11px",
                        "color": "#888",
                        "margin": "7px 0 5px",
                    },
                ),

                # ── Camera control buttons ───────────────────────────
                html.Div(
                    style={
                        "display": "flex",
                        "justifyContent": "center",
                        "gap": "6px",
                        "flexWrap": "wrap",
                    },
                    children=[

                        # Start (visible initially)
                        dbc.Button(
                            [html.I(className="fas fa-camera me-1"), "Start Camera"],
                            id="eval-start-btn",
                            color="primary", size="sm",
                        ),

                        # Flip front ↔ back  (hidden until camera active)
                        dbc.Button(
                            [html.I(className="fas fa-sync-alt me-1"), "Front"],
                            id="eval-switch-btn",
                            color="info", size="sm", outline=True,
                            style={"display": "none"},
                            title="Switch to front camera",
                        ),

                        # Torch / flashlight  (hidden; appears if hw supports it)
                        dbc.Button(
                            [html.I(className="fas fa-lightbulb me-1"), "Light"],
                            id="eval-torch-btn",
                            color="warning", size="sm", outline=True,
                            style={"display": "none"},
                            title="Toggle flashlight",
                        ),

                        # Stop  (hidden until camera active)
                        dbc.Button(
                            [html.I(className="fas fa-stop-circle me-1"), "Stop"],
                            id="eval-stop-btn",
                            color="danger", size="sm", outline=True,
                            style={"display": "none"},
                        ),
                    ],
                ),

            ]),  # /camera section

            html.Hr(style={"margin": "10px 0"}),

            # ── Recent scans log ──────────────────────────────────────
            html.Div(
                [
                    html.Small(
                        [
                            html.I(className="fas fa-history me-1"),
                            "Recent Scans",
                        ],
                        style={
                            "fontSize": "11px", "fontWeight": "600",
                            "color": "#666", "display": "block",
                            "marginBottom": "5px",
                        },
                    ),
                    dbc.ListGroup(
                        id="eval-recent-scans",
                        children=[
                            dbc.ListGroupItem(
                                "No scans yet",
                                className="text-muted text-center",
                                style={"fontSize": "11px", "padding": "6px"},
                            )
                        ],
                        flush=True,
                        style={"maxHeight": "160px", "overflowY": "auto"},
                    ),
                ]
            ),

            # ── CSS: scan-line + corner animations ────────────────────
            html.Style("""
                @keyframes evalScanLine {
                    0%   { top: 2%;   opacity: 0;   }
                    10%  { opacity: 1;               }
                    90%  { opacity: 1;               }
                    100% { top: 96%;  opacity: 0;   }
                }
                #eval-corners { display: none; }
                #eval-video:not([style*="display: none"]) ~ #eval-corners {
                    display: block !important;
                }
                /* Touch-target minimum for mobile */
                #eval-start-btn, #eval-stop-btn,
                #eval-switch-btn, #eval-torch-btn {
                    min-height: 38px;
                }
            """),

        ],
        style={"padding": "10px"},
    )


def make_form_card(card_id: str) -> html.Div:
    """Render a Form or List card shell."""
    cfg   = FORM_CARDS.get(card_id)
    if not cfg:
        return html.Div(f"Unknown card: {card_id}")

    ctype = cfg.get("type")
    icon  = cfg.get("icon", "fa-square")
    title = cfg.get("title", card_id)
    color_map = {
        "profile": "#3498db", "create": "#27ae60",
        "list": "#8e44ad",    "special": "#e67e22",
    }
    hdr_color = color_map.get(ctype, "#555")

    # ── Card header ─────────────────────────────────────────────
    header = dbc.CardHeader(
        html.Div([
            html.Div("⠿", className="dnd-handle",
                     style={"fontSize":"15px","color":"#ccc","cursor":"grab",
                            "marginRight":"8px","letterSpacing":"2px"}),
            html.I(className=f"fas {icon} me-2",
                   style={"color": hdr_color}),
            html.Strong(title, style={"fontSize":"13px"}),
        ], style={"display":"flex","alignItems":"center"}),
        style={"padding":"8px 12px","background":"#fafafa"},
    )

    # ── Card body ────────────────────────────────────────────────
    if ctype == "list":
        cols = cfg.get("columns", [])
        body = dbc.CardBody([
            dbc.Table([
                html.Thead(html.Tr([html.Th(c, style={"fontSize":"11px","fontWeight":"500"})
                                    for c in cols])),
                html.Tbody(id=cfg["list_id"],
                           children=[html.Tr([
                               html.Td("Loading…", colSpan=len(cols),
                                       className="text-center text-muted",
                                       style={"fontSize":"12px"})
                           ])]),
            ], bordered=True, hover=True, responsive=True, size="sm",
               style={"fontSize":"12px"}),
        ], style={"padding":"8px", "maxHeight":"320px","overflowY":"auto"})

    elif ctype == "special" and cfg.get("component") == "evaluate_pass_card":
        # ── NEW: full camera-capable evaluate pass card ───────────
        body = _evaluate_pass_card_body()

    else:
        # profile / create form
        fields = cfg.get("fields", [])
        save_btn = cfg.get("save_btn", f"save-{card_id}-btn")
        rows = [_make_field(f) for f in fields]
        body = dbc.CardBody(
            rows + [
                html.Div(id=f"form-status-{card_id}"),
                dbc.Button(
                    [html.I(className="fas fa-save me-1"),
                     "Save" if ctype == "profile" else "Create"],
                    id=save_btn, color="primary", size="sm",
                    className="mt-2 w-100",
                ),
            ],
            style={"padding":"10px","maxHeight":"380px","overflowY":"auto"},
        )

    return html.Div(
        [dbc.Card([header, body],
                  className="h-100",
                  style={"borderRadius":"10px","boxShadow":"0 2px 8px rgba(0,0,0,0.07)",
                         "border":"1px solid #e9ecef"})],
        id=f"dnd-card-{card_id}",
        **{"data-card-id": card_id, "data-card-type": ctype},
        className="dnd-card",
        style={"userSelect":"none"},
    )


def make_card(card_id: str, value: str = "—") -> html.Div:
    """Universal dispatcher — returns KPI or Form card."""
    if card_id in KPI_CARDS:
        return make_kpi_card(card_id, value)
    if card_id in FORM_CARDS:
        return make_form_card(card_id)
    return html.Div(f"Unknown card: {card_id}")
