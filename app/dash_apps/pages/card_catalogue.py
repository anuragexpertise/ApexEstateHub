"""
card_catalogue.py
Master catalogue of every KPI, Form and List card.
Drop into: app/dash_apps/pages/card_catalogue.py
"""

import base64
import json
from dash import html, dcc
import dash_bootstrap_components as dbc

"""
Enhanced KPI Definitions for EsateHub
=====================================
All KPIs with auto-calculated receivables (credits) and payables (debits).
 
RECEIVABLES (Credits Due):
- Maintenance charges (from arrear_start_date to current)
- Late fees on overdue payments
- Vendor pass fees
- Pending fines
 
PAYABLES (Debits Due):
- Security salaries
- Vendor payments
- Utility bills (if tracked)
- Other recurring expenses
"""
 
# ════════════════════════════════════════════════════════════════════════════
# CORE FINANCIAL KPIs (Auto-Calculated)
# ════════════════════════════════════════════════════════════════════════════
 
# FIXED KPI DEFINITIONS
# Drop this into: app/dash_apps/pages/card_catalogue.py (replace KPI_CARDS dict)

"""
Enhanced KPI Definitions - COMPLETE & TESTED
============================================
All auto-calculated receivables and payables with proper SQL.
"""

KPI_CARDS = {
    # ══════════════════════════════════════════════════════════════
    # RECEIVABLES (Money Society Should Receive)
    # ══════════════════════════════════════════════════════════════
    
    "kpi_receivables_total": {
        "query": """
            WITH maintenance_calculation AS (
                SELECT 
                    a.id,
                    a.apartment_size,
                    s.arrear_start_date,
                    EXTRACT(YEAR FROM AGE(CURRENT_DATE, s.arrear_start_date)) * 12 + 
                    EXTRACT(MONTH FROM AGE(CURRENT_DATE, s.arrear_start_date)) AS months_due,
                    3.0 AS rate_per_sqft
                FROM apartments a
                JOIN societies s ON a.society_id = s.id
                WHERE a.society_id = %s AND a.active = TRUE
            ),
            total_maintenance_due AS (
                SELECT COALESCE(SUM(apartment_size * rate_per_sqft * GREATEST(months_due, 0)), 0) AS amount
                FROM maintenance_calculation
            ),
            payments_made AS (
                SELECT COALESCE(SUM(amount), 0) AS amount
                FROM payments
                WHERE society_id = %s 
                  AND payment_type = 'maintenance' 
                  AND status = 'verified'
            ),
            late_fees AS (
                SELECT COALESCE(SUM(
                    CASE 
                        WHEN due_date < CURRENT_DATE 
                        THEN amount * 0.02 * (CURRENT_DATE - due_date) / 30
                        ELSE 0 
                    END
                ), 0) AS amount
                FROM payments
                WHERE society_id = %s 
                  AND status = 'pending' 
                  AND due_date IS NOT NULL
            ),
            vendor_dues AS (
                SELECT COALESCE(SUM(amount), 0) AS amount
                FROM payments
                WHERE society_id = %s 
                  AND payment_type = 'vendor_pass' 
                  AND status = 'pending'
            )
            SELECT COALESCE(tmd.amount - pm.amount + lf.amount + vd.amount, 0) AS v
            FROM total_maintenance_due tmd, payments_made pm, late_fees lf, vendor_dues vd
        """,
        "params": 4,
        "format": "currency",
        "icon": "fa-hand-holding-usd",
        "color": "#17976e",
        "title": "Total Receivables",
        "group": "pending income",
    },
    
    "kpi_apartments_dues": {
        "query": """
            SELECT COUNT(DISTINCT p.entity_id) AS v 
            FROM payments p
            WHERE p.society_id = %s 
              AND p.entity_type = 'apartment'
              AND p.status = 'pending'
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-exclamation-triangle",
        "color": "#de5c52",
        "title": "Apts With Dues",
        "group": "pending payments",
    },
    
    "kpi_apartments_no_dues": {
        "query": """
            SELECT COUNT(*) AS v 
            FROM apartments a
            WHERE a.society_id = %s 
              AND a.active = TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM payments p 
                  WHERE p.entity_id = a.id 
                    AND p.entity_type = 'apartment'
                    AND p.status = 'pending'
              )
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-check-circle",
        "color": "#17976e",
        "title": "Dues Clear",
        "group": "up to date",
    },

    "kpi_apartments_total_dues": {
        "query": """
            SELECT COALESCE(SUM(p.amount), 0) AS v 
            FROM payments p
            WHERE p.society_id = %s 
              AND p.entity_type = 'apartment'
              AND p.status = 'pending'
        """,
        "params": 1,
        "format": "currency",
        "icon": "fa-rupee-sign",
        "color": "#e59620",
        "title": "Total Pending",
        "group": "all apartments",
    },
    
    "kpi_maintenance_due": {
        "query": """
            WITH maintenance_calculation AS (
                SELECT 
                    a.apartment_size,
                    s.arrear_start_date,
                    EXTRACT(YEAR FROM AGE(CURRENT_DATE, s.arrear_start_date)) * 12 + 
                    EXTRACT(MONTH FROM AGE(CURRENT_DATE, s.arrear_start_date)) AS months_due,
                    3.0 AS rate_per_sqft
                FROM apartments a
                JOIN societies s ON a.society_id = s.id
                WHERE a.society_id = %s AND a.active = TRUE
            )
            SELECT COALESCE(SUM(apartment_size * rate_per_sqft * GREATEST(months_due, 0)), 0) AS v
            FROM maintenance_calculation
        """,
        "params": 1,
        "format": "currency",
        "icon": "fa-home",
        "color": "#1859b8",
        "title": "Maintenance Due",
        "group": "from arrear date",
    },
    
    "kpi_maintenance_paid": {
        "query": """
            SELECT COALESCE(SUM(amount), 0) AS v
            FROM payments
            WHERE society_id = %s 
              AND payment_type = 'maintenance' 
              AND status = 'verified'
        """,
        "params": 1,
        "format": "currency",
        "icon": "fa-check-square",
        "color": "#17976e",
        "title": "Maintenance Paid",
        "group": "collected",
    },
    
    "kpi_late_fees_due": {
        "query": """
            SELECT COALESCE(SUM(
                CASE 
                    WHEN due_date < CURRENT_DATE 
                    THEN amount * 0.02 * (CURRENT_DATE - due_date) / 30
                    ELSE 0 
                END
            ), 0) AS v
            FROM payments
            WHERE society_id = %s 
              AND status = 'pending' 
              AND due_date IS NOT NULL
        """,
        "params": 1,
        "format": "currency",
        "icon": "fa-clock",
        "color": "#e59620",
        "title": "Late Fees Due",
        "group": "2% per month",
    },
    
    # ══════════════════════════════════════════════════════════════
    # PAYABLES (Money Society Needs to Pay)
    # ══════════════════════════════════════════════════════════════
    
    "kpi_payables_total": {
        "query": """
            WITH security_salaries AS (
                SELECT COALESCE(SUM(
                    ss.salary_per_shift * 
                    GREATEST(EXTRACT(DAY FROM AGE(CURRENT_DATE, COALESCE(ss.joining_date, CURRENT_DATE))), 0)
                ), 0) AS amount
                FROM security_staff ss
                WHERE ss.society_id = %s 
                  AND ss.active = TRUE
            ),
            security_paid AS (
                SELECT COALESCE(SUM(p.amount), 0) AS amount
                FROM payments p
                WHERE p.society_id = %s
                  AND p.payment_type = 'salary'
                  AND p.status = 'verified'
            ),
            vendor_payments AS (
                SELECT COALESCE(SUM(amount), 0) AS amount
                FROM payments
                WHERE society_id = %s 
                  AND entity_type = 'vendor'
                  AND status = 'pending'
            ),
            pending_expenses AS (
                SELECT COALESCE(SUM(amount), 0) AS amount
                FROM expenses
                WHERE society_id = %s 
                  AND status = 'pending'
            )
            SELECT COALESCE(ss.amount - sp.amount + vp.amount + pe.amount, 0) AS v
            FROM security_salaries ss, security_paid sp, vendor_payments vp, pending_expenses pe
        """,
        "params": 4,
        "format": "currency",
        "icon": "fa-wallet",
        "color": "#de5c52",
        "title": "Total Payables",
        "group": "pending payments",
    },
    
    "kpi_security_salaries_due": {
        "query": """
            WITH security_total_due AS (
                SELECT COALESCE(SUM(
                    ss.salary_per_shift * 
                    GREATEST(EXTRACT(DAY FROM AGE(CURRENT_DATE, COALESCE(ss.joining_date, CURRENT_DATE))), 0)
                ), 0) AS amount
                FROM security_staff ss
                WHERE ss.society_id = %s 
                  AND ss.active = TRUE
            ),
            security_paid AS (
                SELECT COALESCE(SUM(p.amount), 0) AS amount
                FROM payments p
                WHERE p.society_id = %s
                  AND p.payment_type = 'salary'
                  AND p.status = 'verified'
            )
            SELECT COALESCE(std.amount - sp.amount, 0) AS v
            FROM security_total_due std, security_paid sp
        """,
        "params": 2,
        "format": "currency",
        "icon": "fa-user-shield",
        "color": "#b63b3b",
        "title": "Security Salary Due",
        "group": "unpaid wages",
    },
    
    "kpi_vendor_payments_due": {
        "query": """
            SELECT COALESCE(SUM(amount), 0) AS v
            FROM payments
            WHERE society_id = %s 
              AND entity_type = 'vendor'
              AND status = 'pending'
        """,
        "params": 1,
        "format": "currency",
        "icon": "fa-truck",
        "color": "#b98a07",
        "title": "Vendor Payments",
        "group": "pending",
    },
    
    # ══════════════════════════════════════════════════════════════
    # CASHBOOK & BALANCE
    # ══════════════════════════════════════════════════════════════
    
    "kpi_receipts_month": {
        "query": """
            SELECT COALESCE(SUM(t.amount), 0) AS v
            FROM transactions t
            JOIN accounts a ON t.acc_id = a.id
            WHERE t.society_id = %s 
              AND t.status = 'paid'
              AND a.drcr_account = 'Cr'
              AND t.trx_date >= DATE_TRUNC('month', CURRENT_DATE)
        """,
        "params": 1,
        "format": "currency",
        "icon": "fa-receipt",
        "color": "#17976e",
        "title": "Receipts (Month)",
        "group": "credits",
    },
    
    "kpi_expenses_month": {
        "query": """
            SELECT COALESCE(SUM(t.amount), 0) AS v
            FROM transactions t
            JOIN accounts a ON t.acc_id = a.id
            WHERE t.society_id = %s 
              AND t.status = 'paid'
              AND a.drcr_account = 'Dr'
              AND t.trx_date >= DATE_TRUNC('month', CURRENT_DATE)
        """,
        "params": 1,
        "format": "currency",
        "icon": "fa-wallet",
        "color": "#de5c52",
        "title": "Expenses (Month)",
        "group": "debits",
    },
    
    "kpi_balance": {
        "query": """
            WITH receipts AS (
                SELECT COALESCE(SUM(t.amount), 0) AS amount
                FROM transactions t
                JOIN accounts a ON t.acc_id = a.id
                WHERE t.society_id = %s 
                  AND t.status = 'paid'
                  AND a.drcr_account = 'Cr'
            ),
            expenses AS (
                SELECT COALESCE(SUM(t.amount), 0) AS amount
                FROM transactions t
                JOIN accounts a ON t.acc_id = a.id
                WHERE t.society_id = %s 
                  AND t.status = 'paid'
                  AND a.drcr_account = 'Dr'
            ),
            opening_balance AS (
                SELECT COALESCE(SUM(
                    CASE 
                        WHEN drcr_bf = 'Cr' THEN bf_amount
                        ELSE -bf_amount
                    END
                ), 0) AS amount
                FROM accounts
                WHERE society_id = %s
            )
            SELECT COALESCE(ob.amount + r.amount - e.amount, 0) AS v
            FROM receipts r, expenses e, opening_balance ob
        """,
        "params": 3,
        "format": "currency",
        "icon": "fa-coins",
        "color": "#2c3e50",
        "title": "Current Balance",
        "group": "net position",
    },
    
    "kpi_cash_in_hand": {
        "query": """
            WITH cash_receipts AS (
                SELECT COALESCE(SUM(t.amount), 0) AS amount
                FROM transactions t
                JOIN accounts a ON t.acc_id = a.id
                WHERE t.society_id = %s 
                  AND t.status = 'paid'
                  AND a.drcr_account = 'Cr'
                  AND t.mode = 'cash'
            ),
            cash_expenses AS (
                SELECT COALESCE(SUM(t.amount), 0) AS amount
                FROM transactions t
                JOIN accounts a ON t.acc_id = a.id
                WHERE t.society_id = %s 
                  AND t.status = 'paid'
                  AND a.drcr_account = 'Dr'
                  AND t.mode = 'cash'
            )
            SELECT COALESCE(r.amount - e.amount, 0) AS v
            FROM cash_receipts r, cash_expenses e
        """,
        "params": 2,
        "format": "currency",
        "icon": "fa-money-bill-wave",
        "color": "#27ae60",
        "title": "Cash in Hand",
        "group": "physical cash",
    },
    
    # ══════════════════════════════════════════════════════════════
    # ENTITY COUNTS
    # ══════════════════════════════════════════════════════════════
    
    "kpi_apartments_total": {
        "query": "SELECT COUNT(*) AS v FROM apartments WHERE society_id = %s AND active = TRUE",
        "params": 1,
        "format": "number",
        "icon": "fa-home",
        "color": "#1859b8",
        "title": "Apartments",
        "group": "active",
    },
    
    "kpi_vendors_total": {
        "query": "SELECT COUNT(*) AS v FROM vendors WHERE society_id = %s AND active = TRUE",
        "params": 1,
        "format": "number",
        "icon": "fa-truck",
        "color": "#b98a07",
        "title": "Vendors",
        "group": "registered",
    },
    
    "kpi_vendors_dues": {
        "query": """
            SELECT COUNT(DISTINCT entity_id) AS v
            FROM payments
            WHERE society_id = %s 
              AND entity_type = 'vendor'
              AND status = 'pending'
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-exclamation-circle",
        "color": "#e59620",
        "title": "Vendors w/ Dues",
        "group": "pending",
    },
    
    "kpi_security_total": {
        "query": "SELECT COUNT(*) AS v FROM security_staff WHERE society_id = %s AND active = TRUE",
        "params": 1,
        "format": "number",
        "icon": "fa-user-shield",
        "color": "#b63b3b",
        "title": "Security Staff",
        "group": "active",
    },
    
    "kpi_security_on_duty": {
        "query": """
            SELECT COUNT(*) AS v 
            FROM gate_access 
            WHERE society_id = %s 
              AND role = 's' 
              AND time_out IS NULL
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-shield-alt",
        "color": "#691b1b",
        "title": "On Duty Now",
        "group": "active guards",
    },
    
    # ══════════════════════════════════════════════════════════════
    # EVENTS & CONCERNS
    # ══════════════════════════════════════════════════════════════
    
    "kpi_events_total": {
        "query": """
            SELECT COUNT(*) AS v 
            FROM events 
            WHERE society_id = %s 
              AND event_date >= CURRENT_DATE
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-calendar-check",
        "color": "#8e44ad",
        "title": "Upcoming Events",
        "group": "scheduled",
    },
    
    "kpi_concerns_open": {
        "query": """
            SELECT COUNT(*) AS v 
            FROM concerns 
            WHERE society_id = %s 
              AND status IN ('open', 'in_progress')
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-hand-point-up",
        "color": "#de5c52",
        "title": "Open Concerns",
        "group": "pending issues",
    },
    
    # ══════════════════════════════════════════════════════════════
    # GATE LOGS
    # ══════════════════════════════════════════════════════════════
    
    "kpi_gate_logs": {
        "query": """
            SELECT COUNT(*) AS v 
            FROM gate_access 
            WHERE society_id = %s 
              AND time_in >= CURRENT_DATE
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-receipt",
        "color": "#1abc9c",
        "title": "Gate Logs Today",
        "group": "entries",
    },
    
    # ══════════════════════════════════════════════════════════════
    # SETTINGS KPIs
    # ══════════════════════════════════════════════════════════════
    
    "kpi_society_plan": {
        "query": "SELECT plan AS v FROM societies WHERE id = %s",
        "params": 1,
        "format": "text",
        "icon": "fa-award",
        "color": "#8e44ad",
        "title": "Current Plan",
        "group": "subscription",
    },
    
    "kpi_plan_validity": {
        "query": "SELECT plan_validity AS v FROM societies WHERE id = %s",
        "params": 1,
        "format": "date",
        "icon": "fa-calendar-times",
        "color": "#e67e22",
        "title": "Plan Expires",
        "group": "validity",
    },
    
    "kpi_accounts_count": {
        "query": "SELECT COUNT(*) AS v FROM accounts WHERE society_id = %s",
        "params": 1,
        "format": "number",
        "icon": "fa-book-open",
        "color": "#6c5ce7",
        "title": "Accounts",
        "group": "chart",
    },
    
    "kpi_apt_charges": {
        "query": "SELECT COUNT(*) AS v FROM apt_charges_fines WHERE society_id = %s AND apt_status = TRUE",
        "params": 1,
        "format": "number",
        "icon": "fa-rupee-sign",
        "color": "#1859b8",
        "title": "Apt Charge Rules",
        "group": "active",
    },
    
    "kpi_ven_charges": {
        "query": "SELECT COUNT(*) AS v FROM ven_charges_fines WHERE society_id = %s AND ven_status = TRUE",
        "params": 1,
        "format": "number",
        "icon": "fa-rupee-sign",
        "color": "#b98a07",
        "title": "Vendor Charges",
        "group": "active",
    },
    
    "kpi_sec_charges": {
        "query": "SELECT COUNT(*) AS v FROM security_charges_fines WHERE society_id = %s AND sec_status = TRUE",
        "params": 1,
        "format": "number",
        "icon": "fa-rupee-sign",
        "color": "#b63b3b",
        "title": "Security Charges",
        "group": "active",
    },
    
    "kpi_attendance": {
        "query": """
            SELECT COUNT(*) AS v 
            FROM attendance 
            WHERE society_id = %s 
              AND time_in >= CURRENT_DATE - INTERVAL '30 days'
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-clock",
        "color": "#6638bd",
        "title": "Attendance (30d)",
        "group": "records",
    },
    
    # ══════════════════════════════════════════════════════════════
    # MASTER ADMIN KPIs
    # ══════════════════════════════════════════════════════════════
    
    "kpi_societies_total": {
        "query": "SELECT COUNT(*) AS v FROM societies",
        "params": 0,
        "format": "number",
        "icon": "fa-building",
        "color": "#c96a19",
        "title": "Total Societies",
        "group": "platform",
    },
    
    "kpi_societies_paid": {
        "query": """
            SELECT COUNT(*) AS v 
            FROM societies 
            WHERE plan != 'Free' 
              AND plan_validity >= CURRENT_DATE
        """,
        "params": 0,
        "format": "number",
        "icon": "fa-star",
        "color": "#17976e",
        "title": "Paid Plans",
        "group": "active",
    },
    
    "kpi_societies_free": {
        "query": "SELECT COUNT(*) AS v FROM societies WHERE plan = 'Free'",
        "params": 0,
        "format": "number",
        "icon": "fa-circle",
        "color": "#7d8ea3",
        "title": "Free Plans",
        "group": "total",
    },
    
    "kpi_societies_expired": {
        "query": """
            SELECT COUNT(*) AS v 
            FROM societies 
            WHERE plan != 'Free' 
              AND plan_validity < CURRENT_DATE
        """,
        "params": 0,
        "format": "number",
        "icon": "fa-exclamation-triangle",
        "color": "#de5c52",
        "title": "Expired Plans",
        "group": "needs renewal",
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
            {"id": "soc-logo",      "label": "Society Logo", "type": "upload", "accept": "image/*", "preview": True},
            {"id": "soc-name",      "label": "Society Name *", "type": "text"},
            {"id": "soc-email",     "label": "Email",          "type": "email"},
            {"id": "soc-phone",     "label": "Phone",          "type": "tel"},
            {"id": "soc-address",   "label": "Address",        "type": "textarea"},
            {"id": "soc-sec-name",  "label": "Secretary Name", "type": "text"},
            {"id": "soc-sec-phone", "label": "Secretary Phone","type": "tel"},
            {"id": "soc-sec-sign",  "label": "Secretary Sign", "type": "upload", "accept": "image/*", "preview": True},
            {"id": "soc-plan",      "label": "Plan",           "type": "select", "options": ["Free","9Apts","99Apts","999Apts","unlimited"]},
            {"id": "soc-validity",  "label": "Plan Validity",  "type": "date"},
            {"id": "arrear-start",   "label": "Arrear Start Date","type": "date"},
            {"id": "soc-bg",        "label": "Login Background", "type": "upload", "accept": "image/*", "preview": True},
        ],
        "save_btn": "save-society-profile-btn",
        "load_output": ["soc-logo","soc-name","soc-email","soc-phone","soc-address",
                        "soc-sec-name","soc-sec-phone","soc-sec-sign","soc-plan",
                        "soc-validity","arrear-start","soc-bg"],
    },
    "society_create": {
        "group": "Society", "title": "Create Society", "icon": "fa-plus-circle",
        "type": "create", "entity": "society",
        "fields": [
            {"id": "soc-logo",      "label": "Society Logo", "type": "upload", "accept": "image/*", "preview": True},
            {"id": "soc-name",      "label": "Society Name *", "type": "text"},
            {"id": "soc-email",     "label": "Email",          "type": "email"},
            {"id": "soc-phone",     "label": "Phone",          "type": "tel"},
            {"id": "soc-address",   "label": "Address",        "type": "textarea"},
            {"id": "soc-sec-name",  "label": "Secretary Name", "type": "text"},
            {"id": "soc-sec-phone", "label": "Secretary Phone","type": "tel"},
            {"id": "soc-sec-sign",  "label": "Secretary Sign", "type": "upload", "accept": "image/*", "preview": True},
            {"id": "soc-plan",      "label": "Plan",           "type": "select", "options": ["Free","9Apts","99Apts","999Apts","unlimited"]},
            {"id": "soc-validity",  "label": "Plan Validity",  "type": "date"},
            {"id": "arrear-start",   "label": "Arrear Start Date","type": "date"},
            {"id": "soc-bg",        "label": "Login Background", "type": "upload", "accept": "image/*", "preview": True},
        
            {"id": "new-admin-email",   "label": "Admin Email *",  "type": "email"},
            {"id": "new-admin-pass",    "label": "Admin Password *","type": "password"},
        ],
        "save_btn": "create-society-btn",
    },
    "society_list": {
        "group": "Society", "title": "Societies List", "icon": "fa-list",
        "type": "list", "entity": "society",
        "columns": ["logo","name","secretary_name","email","secretary_phone","Plan","Plan_Validity","Created","Actions"],
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
            {"id": "acc-name",   "label": "Account Name *", "type": "text"},
            {"id": "acc-tab",    "label": "Tab Name",    "type": "text"},
            {"id": "acc-header", "label": "Header",         "type": "text"},
            {"id": "acc-parent", "label": "Parent Account", "type": "text"},
            {"id": "acc-drcr",   "label": "Dr / Cr Ac",        "type": "select",
             "options": ["Dr","Cr"]},
            {"id": "acc-bf-amt", "label": "Opening Balance","type": "number"},
            {"id": "acc-bf-type","label": "Dr / Cr BF","type": "select",
             "options": ["Dr","Cr"]},
            {"id": "acc-dep-pct","label": "Depreciation %", "type": "number"},
        ],
        "save_btn": "save-account-profile-btn",
    },
    "account_create": {
        "group": "Accounts", "title": "Create Account", "icon": "fa-plus-circle",
        "type": "create", "entity": "account",
        "fields": [
            {"id": "new-acc-name",   "label": "Account Name *", "type": "text"},
            {"id": "new-acc-tab",    "label": "Tab Name",    "type": "text"},
            {"id": "new-acc-header", "label": "Header",         "type": "text"},
            {"id": "new-acc-parent", "label": "Parent Account", "type": "text"},
            {"id": "new-acc-drcr",   "label": "Dr / Cr Ac *",      "type": "select",
             "options": ["Dr","Cr"]},
            {"id": "new-acc-bf-amt", "label": "BF","type": "number"},
            {"id": "new-acc-bf-type","label": "Dr /Cr BF","type": "select",
             "options": ["Dr","Cr"]},
            {"id": "new-acc-dep-pct","label": "Depreciation %", "type": "number"},
        ],
        "save_btn": "create-account-btn",
    },
    "account_list": {
        "group": "Accounts", "title": "Accounts List", "icon": "fa-list",
        "type": "list", "entity": "account",
        "columns": ["name","tab_name","header","Dr/Cr Ac","Opening Bal","Depreciation %","Actions"],
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

# ================================================================
# ── CUSTOMIZATION CATALOGUE
# ================================================================
# A normalized catalogue for UI customization and saved layout state.
# This separates KPIs, forms, and lists so customization data can be
# stored independently and later wired back into the drilldown engine.
LIST_CARDS = {cid: cfg for cid, cfg in FORM_CARDS.items() if cfg.get("type") == "list"}
FORM_CARDS_ONLY = {cid: cfg for cid, cfg in FORM_CARDS.items() if cfg.get("type") in ("profile", "create")}
CUSTOMIZABLE_CARD_CATALOGUE = {
    "kpis": KPI_CARDS,
    "forms": FORM_CARDS_ONLY,
    "lists": LIST_CARDS,
}

# ── Default dashboard cards per portal ─────────────────────────
DEFAULT_LAYOUTS = {
    "admin": [
        "kpi_apartments_total",
        "kpi_apartments_dues",
        "kpi_receipts_month",
        "kpi_balance",
    ],
    "apartment": [
        "kpi_apartments_no_dues",
        "kpi_gate_logs",
        "kpi_events_total",
        "kpi_concerns_open",
    ],
    "vendor": [
        "kpi_vendors_total",
        "kpi_gate_logs",
        "kpi_events_total",
        "kpi_concerns_open",
    ],
    "security": [
        "kpi_security_on_duty",
        "kpi_security_total",
        "kpi_gate_logs",
        "kpi_concerns_open",
    ],
    "master": [
        "kpi_societies_total",
        "kpi_societies_paid",
        "kpi_receipts_month",
        "kpi_balance",
    ],
}


# ================================================================
# ── RENDERERS
# ================================================================

def make_kpi_card(card_id: str, value) -> html.Div:
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
                            # playsInline=True,
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

# ════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS FOR AUTO-CALCULATION
# ════════════════════════════════════════════════════════════════════════════
 
def calculate_maintenance_for_apartment(db, apartment_id: int, society_id: int) -> dict:
    """
    Calculate complete maintenance breakdown for a single apartment.
    
    Returns:
        {
            'base_maintenance': float,       # Monthly rate × sqft
            'months_due': int,               # From arrear_start_date
            'total_maintenance': float,      # base × months
            'paid_amount': float,            # Already paid
            'pending_maintenance': float,    # total - paid
            'late_fee': float,               # 2% per month on overdue
            'grand_total': float             # pending + late_fee
        }
    """
    
    result = db._execute(
        """
        WITH apartment_info AS (
            SELECT 
                a.apartment_size,
                s.arrear_start_date,
                EXTRACT(YEAR FROM AGE(CURRENT_DATE, s.arrear_start_date)) * 12 + 
                EXTRACT(MONTH FROM AGE(CURRENT_DATE, s.arrear_start_date)) AS months_due,
                3.0 AS rate_per_sqft
            FROM apartments a
            JOIN societies s ON a.society_id = s.id
            WHERE a.id = %s AND a.society_id = %s
        ),
        payments_made AS (
            SELECT COALESCE(SUM(amount), 0) AS paid
            FROM payments
            WHERE apartment_id = %s 
              AND payment_type = 'maintenance'
              AND status = 'verified'
        ),
        late_fees AS (
            SELECT COALESCE(SUM(
                CASE 
                    WHEN due_date < CURRENT_DATE 
                    THEN amount * 0.02 * EXTRACT(DAY FROM AGE(CURRENT_DATE, due_date)) / 30
                    ELSE 0 
                END
            ), 0) AS late_fee
            FROM payments
            WHERE apartment_id = %s 
              AND status = 'pending'
              AND due_date IS NOT NULL
        )
        SELECT 
            ai.apartment_size * ai.rate_per_sqft AS base_maintenance,
            GREATEST(ai.months_due, 0) AS months_due,
            ai.apartment_size * ai.rate_per_sqft * GREATEST(ai.months_due, 0) AS total_maintenance,
            pm.paid,
            lf.late_fee
        FROM apartment_info ai, payments_made pm, late_fees lf
        """,
        (apartment_id, society_id, apartment_id, apartment_id),
        fetch_one=True
    )
    
    if not result:
        return {
            'base_maintenance': 0, 'months_due': 0, 'total_maintenance': 0,
            'paid_amount': 0, 'pending_maintenance': 0, 'late_fee': 0, 'grand_total': 0
        }
    
    pending = result['total_maintenance'] - result['paid']
    
    return {
        'base_maintenance': float(result['base_maintenance']),
        'months_due': int(result['months_due']),
        'total_maintenance': float(result['total_maintenance']),
        'paid_amount': float(result['paid']),
        'pending_maintenance': float(pending),
        'late_fee': float(result['late_fee']),
        'grand_total': float(pending + result['late_fee'])
    }
 
 
def calculate_security_salary_due(db, security_id: int, society_id: int) -> dict:
    """
    Calculate salary due for a security staff member.
    
    Returns:
        {
            'salary_per_shift': float,
            'shifts_worked': int,           # Days since joining
            'total_due': float,             # salary × shifts
            'paid_amount': float,           # Already paid salaries
            'pending_salary': float         # total - paid
        }
    """
    
    result = db._execute(
        """
        WITH security_info AS (
            SELECT 
                ss.salary_per_shift,
                EXTRACT(DAY FROM AGE(CURRENT_DATE, COALESCE(ss.joining_date, CURRENT_DATE))) AS shifts_worked
            FROM security_staff ss
            WHERE ss.id = %s AND ss.society_id = %s
        ),
        salaries_paid AS (
            SELECT COALESCE(SUM(amount), 0) AS paid
            FROM payments
            WHERE society_id = %s
              AND payment_type = 'salary'
              AND status = 'verified'
              AND user_id IN (
                  SELECT id FROM users 
                  WHERE linked_id = %s AND role = 'security'
              )
        )
        SELECT 
            si.salary_per_shift,
            si.shifts_worked,
            si.salary_per_shift * si.shifts_worked AS total_due,
            sp.paid
        FROM security_info si, salaries_paid sp
        """,
        (security_id, society_id, society_id, security_id),
        fetch_one=True
    )
    
    if not result:
        return {
            'salary_per_shift': 0, 'shifts_worked': 0, 
            'total_due': 0, 'paid_amount': 0, 'pending_salary': 0
        }
    
    pending = result['total_due'] - result['paid']
    
    return {
        'salary_per_shift': float(result['salary_per_shift']),
        'shifts_worked': int(result['shifts_worked']),
        'total_due': float(result['total_due']),
        'paid_amount': float(result['paid']),
        'pending_salary': float(pending)
    }
 

# ════════════════════════════════════════════════════════════════════════════
# ── FORMAT HELPERS (ENHANCED)
# ════════════════════════════════════════════════════════════════════════════

def format_kpi_value(value, format_type: str) -> str:
    """
    Format a KPI value based on its type.
    
    Supported formats:
    - number: Plain integer with thousand separators
    - currency: ₹ symbol with 2 decimals
    - percent: % symbol with 1 decimal
    - date: DD MMM YYYY format
    - text: Plain text (unchanged)
    """
    from datetime import date, datetime
    
    # Handle None/NULL values
    if value is None or value == "":
        return "—"
    
    try:
        if format_type == "number":
            # Plain number with thousand separators
            v = int(float(value))
            return f"{v:,}"
        
        elif format_type == "currency":
            # Currency with ₹ symbol
            v = float(value)
            if v >= 10_000_000:  # 1 Crore
                return f"₹{v/10_000_000:.2f}Cr"
            elif v >= 100_000:  # 1 Lakh
                return f"₹{v/100_000:.2f}L"
            elif v >= 1000:
                return f"₹{v/1000:.1f}K"
            else:
                return f"₹{v:,.2f}"
        
        elif format_type == "percent":
            # Percentage with 1 decimal
            v = float(value)
            return f"{v:.1f}%"
        
        elif format_type == "date":
            # Date formatting
            if isinstance(value, str):
                # Try parsing common date formats
                for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"]:
                    try:
                        value = datetime.strptime(value, fmt).date()
                        break
                    except:
                        continue
            
            if isinstance(value, (date, datetime)):
                if isinstance(value, datetime):
                    value = value.date()
                
                # Check if date is in the past/future
                today = date.today()
                if value < today:
                    days_ago = (today - value).days
                    if days_ago == 0:
                        return "Today"
                    elif days_ago == 1:
                        return "Yesterday"
                    elif days_ago < 7:
                        return f"{days_ago}d ago"
                    else:
                        return value.strftime("%d %b %Y")
                elif value > today:
                    days_left = (value - today).days
                    if days_left == 1:
                        return "Tomorrow"
                    elif days_left < 7:
                        return f"in {days_left}d"
                    elif days_left < 30:
                        return f"in {days_left//7}w"
                    else:
                        return value.strftime("%d %b %Y")
                else:
                    return "Today"
            else:
                return str(value)
        
        elif format_type == "text":
            # Plain text (no formatting)
            return str(value).strip()
        
        else:
            # Unknown format - return as string
            return str(value)
    
    except (TypeError, ValueError) as e:
        print(f"Format error for value '{value}' with format '{format_type}': {e}")
        return "—"
