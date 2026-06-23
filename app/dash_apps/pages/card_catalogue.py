# app/dash_apps/pages/card_catalogue.py
"""
KPI Card Catalogue — EstateHub v3
===================================
All financial KPIs now query the authoritative tables directly:
  receivables  → credits (auto-generated monthly dues + interest)
  payments     → debits  (auto-generated security payroll per roster shift)
  receipts     → manual credits (fines, donations, pass sales, etc.)
  expenses     → manual debits  (vendor payments, utilities, etc.)
  transactions → the ledger (source of truth for cashbook / balances)

drcr_account semantics:
  'Cr'  → income account  (Society Maintenance, Interest, Society Charge …)
  'Dr'  → expense account (Salary, Electricity, Repairs …)
  ''    → balance-sheet / asset account (can appear on either side)
  NULL  → same as ''

Running balance = SUM(Cr transactions) - SUM(Dr transactions) + BF balance.
"""

from dash import html, dcc
import dash_bootstrap_components as dbc

# ════════════════════════════════════════════════════════════════════════════
# KPI CARDS — each entry has:
#   query    : parametrised SQL returning a single column 'v'
#   params   : number of %s placeholders (all filled with society_id)
#   format   : 'currency' | 'number' | 'date'
#   icon / color / title / group : display metadata
# ════════════════════════════════════════════════════════════════════════════

KPI_CARDS = {

    # ══════════════════════════════════════════════════════════════════════
    # RECEIVABLES (auto-generated maintenance dues)
    # ══════════════════════════════════════════════════════════════════════

    "kpi_receivables_total": {
        "query": """
            SELECT COALESCE(SUM(amount - paid_amount), 0) AS v
            FROM receivables
            WHERE society_id=%s AND status IN ('pending','partial')
        """,
        "params": 1, "format": "currency",
        "icon": "fa-hand-holding-usd", "color": "#17976e",
        "title": "Total Receivables", "group": "pending dues",
    },

    "kpi_receivables_overdue": {
        "query": """
            SELECT COALESCE(SUM(amount - paid_amount), 0) AS v
            FROM receivables
            WHERE society_id=%s AND status IN ('pending','partial')
              AND due_date < CURRENT_DATE
        """,
        "params": 1, "format": "currency",
        "icon": "fa-exclamation-circle", "color": "#de5c52",
        "title": "Overdue Dues", "group": "overdue",
    },

    "kpi_advance_credits": {
        "query": """
            SELECT COALESCE(SUM(amount - paid_amount), 0) AS v
            FROM receivables
            WHERE society_id=%s AND status='credit'
        """,
        "params": 1, "format": "currency",
        "icon": "fa-hand-point-down", "color": "#0ea5a8",
        "title": "Advance Credits", "group": "prepaid",
    },

    "kpi_apartments_dues": {
        "query": """
            SELECT COUNT(DISTINCT entity_id) AS v
            FROM receivables
            WHERE society_id=%s AND role='apartment'
              AND status IN ('pending','partial')
              AND due_date < CURRENT_DATE
        """,
        "params": 1, "format": "number",
        "icon": "fa-exclamation-triangle", "color": "#de5c52",
        "title": "Apts With Overdue", "group": "failing gate-pass",
    },

    "kpi_apartments_no_dues": {
        "query": """
            SELECT COUNT(*) AS v FROM apartments a
            WHERE a.society_id=%s AND a.active=TRUE
              AND NOT EXISTS (
                SELECT 1 FROM receivables r
                WHERE r.entity_id=a.id AND r.role='apartment'
                  AND r.status IN ('pending','partial')
                  AND r.due_date < CURRENT_DATE
              )
        """,
        "params": 1, "format": "number",
        "icon": "fa-check-circle", "color": "#17976e",
        "title": "Apts Dues Clear", "group": "gate-pass OK",
    },

    # ══════════════════════════════════════════════════════════════════════
    # PAYMENTS (security payroll — auto-generated, pending verification)
    # ══════════════════════════════════════════════════════════════════════

    "kpi_payables_total": {
        "query": """
            SELECT COALESCE(SUM(amount), 0) AS v
            FROM payments
            WHERE society_id=%s AND status='pending'
        """,
        "params": 1, "format": "currency",
        "icon": "fa-wallet", "color": "#de5c52",
        "title": "Total Payables", "group": "pending salary",
    },

    "kpi_security_salaries_due": {
        "query": """
            SELECT COALESCE(SUM(amount), 0) AS v
            FROM payments
            WHERE society_id=%s AND role='security' AND status='pending'
        """,
        "params": 1, "format": "currency",
        "icon": "fa-user-shield", "color": "#b63b3b",
        "title": "Security Salary Due", "group": "unpaid shifts",
    },

    "kpi_security_salaries_paid": {
        "query": """
            SELECT COALESCE(SUM(amount), 0) AS v
            FROM payments
            WHERE society_id=%s AND role='security' AND status='verified'
        """,
        "params": 1, "format": "currency",
        "icon": "fa-check-double", "color": "#17976e",
        "title": "Security Salary Paid", "group": "verified",
    },

    # ══════════════════════════════════════════════════════════════════════
    # RECEIPTS (manual credits — this month)
    # ══════════════════════════════════════════════════════════════════════

    "kpi_receipts_month": {
        "query": """
            SELECT COALESCE(SUM(r.amount), 0) AS v
            FROM receipts r
            WHERE r.society_id=%s AND r.status='confirmed'
              AND r.receipt_date >= DATE_TRUNC('month', CURRENT_DATE)
        """,
        "params": 1, "format": "currency",
        "icon": "fa-receipt", "color": "#17976e",
        "title": "Receipts (Month)", "group": "manual credits",
    },

    "kpi_receipts_total": {
        "query": """
            SELECT COALESCE(SUM(amount), 0) AS v
            FROM receipts
            WHERE society_id=%s AND status='confirmed'
        """,
        "params": 1, "format": "currency",
        "icon": "fa-receipt", "color": "#17976e",
        "title": "Receipts (All)", "group": "all time",
    },

    # ══════════════════════════════════════════════════════════════════════
    # EXPENSES (manual debits — this month)
    # ══════════════════════════════════════════════════════════════════════

    "kpi_expenses_month": {
        "query": """
            SELECT COALESCE(SUM(e.amount), 0) AS v
            FROM expenses e
            WHERE e.society_id=%s AND e.status='confirmed'
              AND e.expense_date >= DATE_TRUNC('month', CURRENT_DATE)
        """,
        "params": 1, "format": "currency",
        "icon": "fa-wallet", "color": "#de5c52",
        "title": "Expenses (Month)", "group": "manual debits",
    },

    # ══════════════════════════════════════════════════════════════════════
    # CASHBOOK / BALANCE — derived from transactions (the ledger)
    # drcr_account = '' treated as NULL (balance-sheet / asset accounts)
    # for running balance they are routed by source_table in fn_cashbook_paired
    # For KPI purposes: Cr transactions = income, Dr transactions = outflow
    # ══════════════════════════════════════════════════════════════════════

    "kpi_bank_balance": {
        "query": """
            WITH cr AS (
                SELECT COALESCE(SUM(t.amount),0) AS amt
                FROM transactions t JOIN accounts a ON a.id=t.acc_id
                WHERE t.society_id=%s AND t.status='paid' AND a.drcr_account='Cr'
            ),
            dr AS (
                SELECT COALESCE(SUM(t.amount),0) AS amt
                FROM transactions t JOIN accounts a ON a.id=t.acc_id
                WHERE t.society_id=%s AND t.status='paid' AND a.drcr_account='Dr'
            ),
            bf AS (
                SELECT COALESCE(SUM(CASE WHEN drcr_bf='Cr' THEN bf_amount ELSE -bf_amount END),0) AS amt
                FROM accounts WHERE society_id=%s AND has_bf=TRUE
            )
            SELECT (bf.amt + cr.amt - dr.amt) AS v FROM cr, dr, bf
        """,
        "params": 3, "format": "currency",
        "icon": "fa-coins", "color": "#2c3e50",
        "title": "Current Balance", "group": "net position",
    },

    "kpi_cash_in_hand": {
        "query": """
            WITH cr AS (
                SELECT COALESCE(SUM(t.amount),0) AS amt
                FROM transactions t JOIN accounts a ON a.id=t.acc_id
                WHERE t.society_id=%s AND t.status='paid'
                  AND a.drcr_account='Cr' AND t.mode='cash'
            ),
            dr AS (
                SELECT COALESCE(SUM(t.amount),0) AS amt
                FROM transactions t JOIN accounts a ON a.id=t.acc_id
                WHERE t.society_id=%s AND t.status='paid'
                  AND a.drcr_account='Dr' AND t.mode='cash'
            )
            SELECT (cr.amt - dr.amt) AS v FROM cr, dr
        """,
        "params": 2, "format": "currency",
        "icon": "fa-money-bill-wave", "color": "#27ae60",
        "title": "Cash in Hand", "group": "physical cash",
    },

    # ══════════════════════════════════════════════════════════════════════
    # ENTITY COUNTS
    # ══════════════════════════════════════════════════════════════════════

    "kpi_apartments_total": {
        "query": "SELECT COUNT(*) AS v FROM apartments WHERE society_id=%s AND active=TRUE",
        "params": 1, "format": "number",
        "icon": "fa-home", "color": "#1859b8",
        "title": "Apartments", "group": "active",
    },

    "kpi_vendors_total": {
        "query": "SELECT COUNT(*) AS v FROM vendors WHERE society_id=%s AND active=TRUE",
        "params": 1, "format": "number",
        "icon": "fa-truck", "color": "#b98a07",
        "title": "Vendors", "group": "registered",
    },

    "kpi_vendors_passes": {
        "query": """
            SELECT COUNT(DISTINCT user_id) AS v
            FROM vendor_passes
            WHERE society_id=%s AND status='active' AND valid_until>=CURRENT_DATE
        """,
        "params": 1, "format": "number",
        "icon": "fa-id-card", "color": "#b98a07",
        "title": "Vendors w/ Pass", "group": "active pass",
    },

    "kpi_security_total": {
        "query": "SELECT COUNT(*) AS v FROM security_staff WHERE society_id=%s AND active=TRUE",
        "params": 1, "format": "number",
        "icon": "fa-user-shield", "color": "#b63b3b",
        "title": "Security Staff", "group": "active",
    },

    "kpi_security_on_duty": {
        "query": """
            SELECT COUNT(*) AS v FROM gate_access
            WHERE society_id=%s AND role='s' AND time_out IS NULL
        """,
        "params": 1, "format": "number",
        "icon": "fa-shield-alt", "color": "#691b1b",
        "title": "On Duty Now", "group": "active guards",
    },

    "kpi_security_shifts_pending": {
        "query": """
            SELECT COUNT(*) AS v FROM payments
            WHERE society_id=%s AND role='security' AND status='pending'
        """,
        "params": 1, "format": "number",
        "icon": "fa-clock", "color": "#e59620",
        "title": "Shifts Unpaid", "group": "awaiting verify",
    },

    # ══════════════════════════════════════════════════════════════════════
    # EVENTS & CONCERNS
    # ══════════════════════════════════════════════════════════════════════

    "kpi_events_total": {
        "query": """
            SELECT COUNT(*) AS v FROM events
            WHERE society_id=%s AND event_date>=CURRENT_DATE
        """,
        "params": 1, "format": "number",
        "icon": "fa-calendar-check", "color": "#8e44ad",
        "title": "Upcoming Events", "group": "scheduled",
    },

    "kpi_concerns_open": {
        "query": """
            SELECT COUNT(*) AS v FROM concerns
            WHERE society_id=%s AND status IN ('open','in_progress')
        """,
        "params": 1, "format": "number",
        "icon": "fa-hand-point-up", "color": "#de5c52",
        "title": "Open Concerns", "group": "pending issues",
    },

    # ══════════════════════════════════════════════════════════════════════
    # GATE LOGS
    # ══════════════════════════════════════════════════════════════════════

    "kpi_gate_logs": {
        "query": """
            SELECT COUNT(*) AS v FROM gate_access
            WHERE society_id=%s AND time_in>=CURRENT_DATE
        """,
        "params": 1, "format": "number",
        "icon": "fa-receipt", "color": "#1abc9c",
        "title": "Gate Logs Today", "group": "entries",
    },

    # ══════════════════════════════════════════════════════════════════════
    # ASSETS
    # ══════════════════════════════════════════════════════════════════════

    "kpi_assets_count": {
        "query": """
            SELECT COUNT(*) AS v FROM asset_register
            WHERE society_id=%s AND disposed=FALSE
        """,
        "params": 1, "format": "number",
        "icon": "fa-boxes", "color": "#6c5ce7",
        "title": "Active Assets", "group": "inventory",
    },

    "kpi_assets_value": {
        "query": """
            SELECT COALESCE(SUM(purchase_value), 0) AS v
            FROM asset_register WHERE society_id=%s AND disposed=FALSE
        """,
        "params": 1, "format": "currency",
        "icon": "fa-coins", "color": "#6c5ce7",
        "title": "Assets at Cost", "group": "gross value",
    },

    # ══════════════════════════════════════════════════════════════════════
    # SETTINGS / CHARGES
    # ══════════════════════════════════════════════════════════════════════

    "kpi_societies_calc_start_date": {
        "query": "SELECT calc_start_date AS v FROM societies WHERE id=%s",
        "params": 1, "format": "date",
        "icon": "fa-clock", "color": "#34ee45",
        "title": "Calc Start Date", "group": "billing from",
    },

    "kpi_plan_validity": {
        "query": "SELECT plan_validity AS v FROM societies WHERE id=%s",
        "params": 1, "format": "date",
        "icon": "fa-calendar-times", "color": "#e67e22",
        "title": "Plan Expires", "group": "validity",
    },

    "kpi_accounts_count": {
        "query": "SELECT COUNT(*) AS v FROM accounts WHERE society_id=%s",
        "params": 1, "format": "number",
        "icon": "fa-book-open", "color": "#6c5ce7",
        "title": "Accounts", "group": "chart",
    },

    "kpi_apt_charges_count": {
        "query": "SELECT COUNT(*) AS v FROM apt_charges_fines_basis WHERE society_id=%s AND apt_status=TRUE",
        "params": 1, "format": "number",
        "icon": "fa-file-invoice", "color": "#1859b8",
        "title": "Apt Charge Rules", "group": "active",
    },

    "kpi_ven_charges_count": {
        "query": "SELECT COUNT(*) AS v FROM ven_charges_fines_basis WHERE society_id=%s AND ven_status=TRUE",
        "params": 1, "format": "number",
        "icon": "fa-file-invoice", "color": "#b98a07",
        "title": "Vendor Charge Rules", "group": "active",
    },

    # ══════════════════════════════════════════════════════════════════════
    # MASTER ADMIN
    # ══════════════════════════════════════════════════════════════════════

    "kpi_societies_total":    {"query": "SELECT COUNT(*) AS v FROM societies",                  "params": 0, "format": "number",   "icon": "fa-building",            "color": "#c96a19", "title": "Total Societies",  "group": "platform"},
    "kpi_societies_free":     {"query": "SELECT COUNT(*) AS v FROM societies WHERE plan='Free'", "params": 0, "format": "number",   "icon": "fa-circle",              "color": "#7d8ea3", "title": "Free Plans",       "group": "total"},
    "kpi_societies_9Apts":    {"query": "SELECT COUNT(*) AS v FROM societies WHERE plan='9Apts' AND plan_validity>=CURRENT_DATE", "params": 0, "format": "number", "icon": "fa-star", "color": "#17976e", "title": "9Apts Plans", "group": "active"},
    "kpi_societies_99Apts":   {"query": "SELECT COUNT(*) AS v FROM societies WHERE plan='99Apts' AND plan_validity>=CURRENT_DATE", "params": 0, "format": "number", "icon": "fa-star", "color": "#17976e", "title": "99Apts Plans", "group": "active"},
    "kpi_societies_999Apts":  {"query": "SELECT COUNT(*) AS v FROM societies WHERE plan='999Apts' AND plan_validity>=CURRENT_DATE", "params": 0, "format": "number", "icon": "fa-star", "color": "#17976e", "title": "999Apts Plans", "group": "active"},
    "kpi_societies_unlimited":{"query": "SELECT COUNT(*) AS v FROM societies WHERE plan='unlimited' AND plan_validity>=CURRENT_DATE", "params": 0, "format": "number", "icon": "fa-star", "color": "#17976e", "title": "Unlimited Plans", "group": "active"},
    "kpi_societies_expired":  {"query": "SELECT COUNT(*) AS v FROM societies WHERE plan_validity<CURRENT_DATE", "params": 0, "format": "number", "icon": "fa-exclamation-triangle", "color": "#de5c52", "title": "Expired Plans", "group": "renewal needed"},
    "kpi_master_apartments_total": {"query": "SELECT COUNT(*) AS v FROM apartments WHERE active=TRUE", "params": 0, "format": "number", "icon": "fa-home",       "color": "#1859b8", "title": "Apartments",    "group": "across all"},
    "kpi_master_vendors_total":    {"query": "SELECT COUNT(*) AS v FROM vendors WHERE active=TRUE",    "params": 0, "format": "number", "icon": "fa-truck",      "color": "#b98a07", "title": "Vendors",       "group": "across all"},
    "kpi_master_security_total":   {"query": "SELECT COUNT(*) AS v FROM security_staff WHERE active=TRUE", "params": 0, "format": "number", "icon": "fa-user-shield", "color": "#b63b3b", "title": "Security", "group": "across all"},

    # ══════════════════════════════════════════════════════════════════════
    # OWNER / APARTMENT PORTAL
    # ══════════════════════════════════════════════════════════════════════

    "kpi_my_pending_dues": {
        "query": """
            SELECT COALESCE(SUM(amount - paid_amount), 0) AS v
            FROM receivables
            WHERE society_id=%s AND entity_id=%s AND role='apartment'
              AND status IN ('pending','partial')
        """,
        "params": 2, "format": "currency",    # second %s = apartment_id
        "icon": "fa-rupee-sign", "color": "#de5c52",
        "title": "My Pending Dues", "group": "to pay",
    },

    "kpi_my_overdue_dues": {
        "query": """
            SELECT COALESCE(SUM(amount - paid_amount), 0) AS v
            FROM receivables
            WHERE society_id=%s AND entity_id=%s AND role='apartment'
              AND status IN ('pending','partial') AND due_date<CURRENT_DATE
        """,
        "params": 2, "format": "currency",
        "icon": "fa-exclamation-circle", "color": "#de5c52",
        "title": "My Overdue Dues", "group": "overdue",
    },

    "kpi_maintainence_charges": {
        "query": "SELECT COUNT(*) AS v FROM apt_charges_fines_basis WHERE society_id=%s AND apt_status=TRUE",
        "params": 1, "format": "number",
        "icon": "fa-file-invoice", "color": "#e59620",
        "title": "Maintenance Rules", "group": "monthly",
    },

    # ══════════════════════════════════════════════════════════════════════
    # SECURITY PORTAL
    # ══════════════════════════════════════════════════════════════════════

    "kpi_security_shift_count": {
        "query": """
            SELECT COUNT(*) AS v FROM gate_access
            WHERE society_id=%s AND role='s' AND time_out IS NULL
        """,
        "params": 1, "format": "number",
        "icon": "fa-hand-point-up", "color": "#de5c52",
        "title": "Shifts Active", "group": "on duty",
    },

    "kpi_receipts_in_hand_total": {
        "query": """
            SELECT COALESCE(SUM(t.amount), 0) AS v
            FROM transactions t JOIN accounts a ON a.id=t.acc_id
            WHERE t.society_id=%s AND t.status='paid' AND a.drcr_account='Cr'
        """,
        "params": 1, "format": "currency",
        "icon": "fa-money-bill-wave", "color": "#27ae60",
        "title": "Receipts-in-hand", "group": "total Cr",
    },

    "kpi_security_date": {
        "query": "SELECT joining_date AS v FROM security_staff WHERE society_id=%s AND active=TRUE LIMIT 1",
        "params": 1, "format": "date",
        "icon": "fa-calendar-alt", "color": "#de5c52",
        "title": "Joined", "group": "profile",
    },

    "kpi_security_salary_per_shift": {
        "query": "SELECT salary_per_shift AS v FROM security_staff WHERE society_id=%s AND active=TRUE LIMIT 1",
        "params": 1, "format": "currency",
        "icon": "fa-rupee-sign", "color": "#b63b3b",
        "title": "Salary per Shift", "group": "profile",
    },

    # ══════════════════════════════════════════════════════════════════════
    # VENDOR PORTAL
    # ══════════════════════════════════════════════════════════════════════

    "kpi_vendor_date": {
        "query": "SELECT created_at::DATE AS v FROM vendors WHERE society_id=%s AND active=TRUE LIMIT 1",
        "params": 1, "format": "date",
        "icon": "fa-calendar-alt", "color": "#de5c52",
        "title": "Registered", "group": "profile",
    },

    "kpi_my_pass_expiry": {
        "query": """
            SELECT MAX(valid_until) AS v FROM vendor_passes vp
            JOIN users u ON u.id=vp.user_id
            WHERE u.society_id=%s AND vp.status='active'
        """,
        "params": 1, "format": "date",
        "icon": "fa-id-card", "color": "#b98a07",
        "title": "Pass Expiry", "group": "gate-pass",
    },
}


# ════════════════════════════════════════════════════════════════════════════
# DEFAULT LAYOUTS  — which KPIs appear on each portal's default dashboard
# ════════════════════════════════════════════════════════════════════════════

DEFAULT_LAYOUTS = {
    "admin": [
        "kpi_apartments_total",
        "kpi_apartments_dues",
        "kpi_receivables_total",
        "kpi_receivables_overdue",
        "kpi_advance_credits",
        "kpi_vendors_total",
        "kpi_security_total",
        "kpi_security_on_duty",
        "kpi_events_total",
        "kpi_concerns_open",
        "kpi_gate_logs",
        "kpi_receipts_month",
        "kpi_expenses_month",
        "kpi_payables_total",
        "kpi_cash_in_hand",
        "kpi_bank_balance",
    ],
    "apartment": [
        "kpi_my_pending_dues",
        "kpi_my_overdue_dues",
        "kpi_advance_credits",
        "kpi_concerns_open",
        "kpi_events_total",
        "kpi_gate_logs",
    ],
    "vendor": [
        "kpi_my_pass_expiry",
        "kpi_concerns_open",
        "kpi_events_total",
        "kpi_gate_logs",
    ],
    "security": [
        "kpi_apartments_total",
        "kpi_vendors_total",
        "kpi_security_total",
        "kpi_security_on_duty",
        "kpi_security_shift_count",
        "kpi_security_salaries_due",
        "kpi_receipts_in_hand_total",
        "kpi_gate_logs",
    ],
    "master": [
        "kpi_societies_total",
        "kpi_societies_free",
        "kpi_societies_9Apts",
        "kpi_societies_99Apts",
        "kpi_societies_999Apts",
        "kpi_societies_unlimited",
        "kpi_societies_expired",
        "kpi_master_apartments_total",
        "kpi_master_vendors_total",
        "kpi_master_security_total",
    ],
}

# ════════════════════════════════════════════════════════════════════════════
# CARD CATALOGUE  (master dict — referenced by KPI audit and customize tabs)
# ════════════════════════════════════════════════════════════════════════════
CARD_CATALOGUE = {**KPI_CARDS}


# ════════════════════════════════════════════════════════════════════════════
# KPI CARD RENDERER  — matches the shell in portal_pages._kpi()
# ════════════════════════════════════════════════════════════════════════════

def make_kpi_card(card_id: str, value) -> html.Div:
    cfg     = KPI_CARDS.get(card_id, {})
    color   = cfg.get("color", "#3498db")
    icon    = cfg.get("icon", "fa-chart-bar")
    title   = cfg.get("title", card_id)
    subtitle = cfg.get("group", "")
    return html.Div(
        [
            html.Div("⠿", className="dnd-handle", style={
                "position": "absolute", "top": "7px", "left": "9px",
                "fontSize": "16px", "color": "#ccc", "cursor": "grab",
                "userSelect": "none",
            }),
            html.Div([
                html.I(className=f"fas {icon}", style={"color": color, "fontSize": "20px"}),
                html.Div(title, style={
                    "fontSize": "11px", "fontWeight": "500",
                    "color": "#888", "marginTop": "5px",
                }),
                html.Div(
                    value,
                    id={"type": "kpi-value", "card_id": card_id},
                    style={"fontSize": "20px", "fontWeight": "700",
                           "color": "#2c3e50", "margin": "2px 0"},
                ),
                html.Div(subtitle, style={"fontSize": "10px", "color": "#aaa"}),
            ], style={"textAlign": "center"}),
        ],
        id={"type": "kpi-card", "card_id": card_id},
        n_clicks=0,
        **{"data-card-id": card_id, "data-card-type": "kpi"},
        className="dnd-card",
        style={
            "position": "relative", "background": "white", "borderRadius": "12px",
            "padding": "16px 12px 12px", "borderLeft": f"4px solid {color}",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
            "cursor": "pointer", "userSelect": "none",
            "transition": "transform 0.1s, box-shadow 0.1s",
        },
    )
