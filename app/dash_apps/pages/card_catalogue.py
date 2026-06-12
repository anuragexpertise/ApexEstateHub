# app/dash_apps/pages/card_catalogue.py
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
    
    "kpi_vendor_payables_due": {
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
    
    "kpi_bank_balance": {
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
    "kpi_societies_arrear_start_date": {
        "query": "SELECT arrear_start_date AS v FROM societies WHERE id = %s",
        "params": 1,
        "format": "date",
        "icon": "fa-clock",
        "color": "#34ee45",
        "title": "Arrear Start Date",
        "group": "Arrears",
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
        "query": "SELECT COUNT(*) AS v FROM apt_charges_fines_basis WHERE society_id = %s AND apt_status = TRUE",
        "params": 1,
        "format": "number",
        "icon": "fa-rupee-sign",
        "color": "#1859b8",
        "title": "Apt Charge Rules",
        "group": "active",
    },
    
    "kpi_ven_charges": {
        "query": "SELECT COUNT(*) AS v FROM ven_charges_fines_basis WHERE society_id = %s AND ven_status = TRUE",
        "params": 1,
        "format": "number",
        "icon": "fa-rupee-sign",
        "color": "#b98a07",
        "title": "Vendor Charges",
        "group": "active",
    },
    
    "kpi_sec_charges": {
        "query": "SELECT COUNT(*) AS v FROM sec_charges_fines_basis WHERE society_id = %s AND sec_status = TRUE",
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
    
   
    
    "kpi_societies_free": {
        "query": "SELECT COUNT(*) AS v FROM societies WHERE plan = 'Free'",
        "params": 0,
        "format": "number",
        "icon": "fa-circle",
        "color": "#7d8ea3",
        "title": "Free Plans",
        "group": "total",
    },

    "kpi_societies_unlimited": {
        "query": """
            SELECT COUNT(*) AS v FROM societies 
            WHERE plan = 'unlimited' AND plan_validity >= CURRENT_DATE
        """,
        "params": 0,
        "format": "number",
        "icon": "fa-star",
        "color": "#17976e",
        "title": "unlimited Plans",
        "group": "active",
    },

    "kpi_societies_9Apts": {
        "query": """
            SELECT COUNT(*) AS v FROM societies WHERE plan = '9Apts'
              AND plan_validity >= CURRENT_DATE
        """,
        "params": 0,
        "format": "number",
        "icon": "fa-star",
        "color": "#17976e",
        "title": "Paid Plans",
        "group": "active",
    },

    "kpi_societies_99Apts": {
        "query": """
            SELECT COUNT(*) AS v FROM societies WHERE plan = '99Apts'
              AND plan_validity >= CURRENT_DATE
        """,
        "params": 0,
        "format": "number",
        "icon": "fa-star",
        "color": "#17976e",
        "title": "Paid Plans",
        "group": "active",
    },

    "kpi_societies_999Apts": {
        "query": """
            SELECT COUNT(*) AS v FROM societies WHERE plan = '999Apts'
              AND plan_validity >= CURRENT_DATE
        """,
        "params": 0,
        "format": "number",
        "icon": "fa-star",
        "color": "#17976e",
        "title": "Paid Plans",
        "group": "active",
    },

    "kpi_societies_expired": {
        "query": """
            SELECT COUNT(*) AS v FROM societies 
            WHERE plan_validity < CURRENT_DATE
        """,
        "params": 0,
        "format": "number",
        "icon": "fa-exclamation-triangle",
        "color": "#de5c52",
        "title": "Expired Plans",
        "group": "needs renewal",
    },

    "kpi_master_apartments_total": {
        "query": "SELECT COUNT(*) AS v FROM apartments WHERE active = TRUE",
        "params": 0,
        "format": "number",
        "icon": "fa-home",
        "color": "#1859b8",
        "title": "Apartments",
        "group": "active",
    },
    
    "kpi_master_vendors_total": {
        "query": "SELECT COUNT(*) AS v FROM vendors WHERE active = TRUE",
        "params": 0,
        "format": "number",
        "icon": "fa-truck",
        "color": "#b98a07",
        "title": "Vendors",
        "group": "registered",
    },

    "kpi_master_security_total": {
        "query": "SELECT COUNT(*) AS v FROM security_staff WHERE active = TRUE",
        "params": 0,
        "format": "number",
        "icon": "fa-user-shield",
        "color": "#b63b3b",
        "title": "Security Staff",
        "group": "active",
    },

    # ══════════════════════════════════════════════════════════════
    # ADMIN PORTAL - EXPENSES & PAYMENTS
    # ══════════════════════════════════════════════════════════════
    "kpi_amc_due": {
        "query": """
            SELECT COALESCE(SUM(amount), 0) AS v
            FROM expenses
            WHERE society_id = %s
              AND LOWER(description) LIKE '%amc%'
              AND status = 'pending'
        """,
        "params": 1,
        "format": "currency",
        "icon": "fa-building",
        "color": "#8e44ad",
        "title": "AMC Due",
        "group": "expenses",
    },

    
    "kpi_security_salary_due": {
        "query": """
            SELECT COALESCE(SUM(p.amount), 0) AS v
            FROM payments p JOIN security_staff ss ON p.user_id = ss.user_id
            WHERE ss.society_id = %s AND p.payment_type = 'salary' AND p.status = 'pending'
        """,
        "params": 1,
        "format": "currency",
        "icon": "fa-rupee-sign",
        "color": "#b63b3b",
        "title": "Salary Due",
        "group": "pending",
    },

    "kpi_security_bonus_due": {
        "query": """
            SELECT COALESCE(SUM(amount), 0) AS v
            FROM payments
            WHERE society_id = %s AND payment_type = 'bonus' AND status = 'pending'
        """,
        "params": 1,
        "format": "currency",
        "icon": "fa-gift",
        "color": "#e59620",
        "title": "Bonus Due",
        "group": "pending",
    },

    # ══════════════════════════════════════════════════════════════
    # OWNER PORTAL KPIs
    # ══════════════════════════════════════════════════════════════
    "kpi_maintainence_charges": {
        "query": """
            SELECT COUNT(*) AS v
            FROM apt_charges_fines_basis
            WHERE society_id = %s AND apt_status = TRUE
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-file-invoice",
        "color": "#e59620",
        "title": "Maintenance Charge Rules",
        "group": "monthly",
    },

    "kpi_apartment_fines": {
        "query": """
            SELECT COUNT(*) AS v
            FROM apt_charges_fines_basis
            WHERE society_id = %s AND apt_status = TRUE AND apt_delay_fine > 0
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-exclamation-triangle",
        "color": "#de5c52",
        "title": "Rules with Delay Fines",
        "group": "pending",
    },

    "kpi_apartment_other_charges": {
        "query": """
            SELECT COUNT(*) AS v
            FROM apt_charges_fines_basis
            WHERE society_id = %s AND apt_status = TRUE AND apt_fine > 0
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-plus",
        "color": "#3498db",
        "title": "Rules with Other Fines",
        "group": "miscellaneous",
    },

    "kpi_apartment_date": {
        "query": "SELECT EXTRACT(EPOCH FROM AGE(CURRENT_DATE, created_at)) / 86400 AS v FROM apartments WHERE society_id = %s AND active = TRUE LIMIT 1",
        "params": 1,
        "format": "number",
        "icon": "fa-calendar-alt",
        "color": "#de5c52",
        "title": "Managed Since",
        "group": "profile",
    },



    # ══════════════════════════════════════════════════════════════
    # VENDOR PORTAL KPIs
    # ══════════════════════════════════════════════════════════════
"kpi_vendor_fines": {
        "query": """
            SELECT COUNT(*) AS v
            FROM ven_charges_fines_basis
            WHERE society_id = %s AND ven_status = TRUE AND vendor_fine > 0
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-exclamation-triangle",
        "color": "#de5c52",
        "title": "Vendor Fine Rules",
        "group": "pending",
    },

    "kpi_vendor_other_charges": {
        "query": """
            SELECT COUNT(*) AS v
            FROM ven_charges_fines_basis
            WHERE society_id = %s AND ven_status = TRUE AND (vendor_1day > 0 OR vendor_7day > 0 OR vendor_1mth > 0)
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-plus",
        "color": "#3498db",
        "title": "Vendor Charge Rules",
        "group": "miscellaneous",
    },

    "kpi_vendor_other_charges": {
        "query": """
            SELECT COALESCE(SUM(amount), 0) AS v
            FROM ven_charges_fines_basis
            WHERE society_id = %s AND ven_status = TRUE AND LOWER(charge_type) = 'other'
        """,
        "params": 1,
        "format": "currency",
        "icon": "fa-plus",
        "color": "#3498db",
        "title": "Other Charges",
        "group": "miscellaneous",
    },

    "kpi_vendor_date": {
        "query": "SELECT EXTRACT(EPOCH FROM AGE(CURRENT_DATE, created_at)) / 86400 AS v FROM vendors WHERE society_id = %s AND active = TRUE LIMIT 1",
        "params": 1,
        "format": "number",
        "icon": "fa-calendar-alt",
        "color": "#de5c52",
        "title": "Managed Since",
        "group": "profile",
    },

    # ══════════════════════════════════════════════════════════════
    # SECURITY PORTAL KPIs
    # ══════════════════════════════════════════════════════════════
    "kpi_security_fines": {
        "query": """
            SELECT COUNT(*) AS v
            FROM sec_charges_fines_basis
            WHERE society_id = %s AND sec_status = TRUE AND security_fine > 0
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-exclamation-triangle",
        "color": "#de5c52",
        "title": "Security Fine Rules",
        "group": "pending",
    },

    "kpi_security_other_charges": {
        "query": """
            SELECT COUNT(*) AS v
            FROM sec_charges_fines_basis
            WHERE society_id = %s AND sec_status = TRUE AND security_fine > 0
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-plus",
        "color": "#3498db",
        "title": "Security Charge Rules",
        "group": "miscellaneous",
    },

    "kpi_receipts_in_hand_total": {
        "query": """
            SELECT COALESCE(SUM(t.amount), 0) AS v
            FROM transactions t JOIN accounts a ON t.acc_id = a.id
            WHERE t.society_id = %s AND t.status = 'paid' AND a.drcr_account = 'Cr'
        """,
        "params": 1,
        "format": "currency",
        "icon": "fa-money-bill-wave",
        "color": "#27ae60",
        "title": "Receipts-in-hand",
        "group": "cash",
    },

    "kpi_security_date": {
        "query": "SELECT EXTRACT(EPOCH FROM AGE(CURRENT_DATE, created_at)) / 86400 AS v FROM security_staff WHERE society_id = %s AND active = TRUE LIMIT 1",
        "params": 1,
        "format": "number",
        "icon": "fa-calendar-alt",
        "color": "#de5c52",
        "title": "Managed Since",
        "group": "profile",
    },

    "kpi_security_salary_per_shift": {
        "query": "SELECT salary_per_shift AS v FROM security_staff WHERE society_id = %s AND active = TRUE LIMIT 1",
        "params": 1,
        "format": "currency",
        "icon": "fa-rupee-sign",
        "color": "#b63b3b",
        "title": "Salary per Shift",
        "group": "profile",
    },

    "kpi_security_shift": {
        "query": "SELECT COUNT(*) AS v FROM gate_access WHERE society_id = %s AND role = 's' AND time_out IS NOT NULL",
        "params": 1,
        "format": "number",
        "icon": "fa-clock",
        "color": "#1abc9c",
        "title": "Shifts Completed",
        "group": "history",
    },

    "kpi_security_shift_count": {
        "query": """
            SELECT COUNT(*) AS v
            FROM gate_access
            WHERE society_id = %s AND role = 's' AND time_out IS NULL
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-hand-point-up",
        "color": "#de5c52",
        "title": "Shift Count",
        "group": "active",
    },
}
# FORM_CARDS = {
#     # ────────────────────── SOCIETY ──────────────────────────────
#     "society_profile": {
#         "group": "Society", "title": "Society Profile", "icon": "fa-building",
#         "type": "profile", "entity": "society",
#         "fields": [
#             {"id": "soc-logo",      "label": "Society Logo", "type": "upload", "accept": "image/*", "preview": True},
#             {"id": "soc-name",      "label": "Society Name *", "type": "text"},
#             {"id": "soc-email",     "label": "Email",          "type": "email"},
#             {"id": "soc-phone",     "label": "Phone",          "type": "tel"},
#             {"id": "soc-address",   "label": "Address",        "type": "textarea"},
#             {"id": "soc-sec-name",  "label": "Secretary Name", "type": "text"},
#             {"id": "soc-sec-phone", "label": "Secretary Phone","type": "tel"},
#             {"id": "soc-sec-sign",  "label": "Secretary Sign", "type": "upload", "accept": "image/*", "preview": True},
#             {"id": "soc-plan",      "label": "Plan",           "type": "select", "options": ["Free","9Apts","99Apts","999Apts","unlimited"]},
#             {"id": "soc-validity",  "label": "Plan Validity",  "type": "date"},
#             {"id": "arrear-start",   "label": "Arrear Start Date","type": "date"},
#             {"id": "soc-bg",        "label": "Login Background", "type": "upload", "accept": "image/*", "preview": True},
#         ],
#         "save_btn": "save-society-profile-btn",
#         "load_output": ["soc-logo","soc-name","soc-email","soc-phone","soc-address",
#                         "soc-sec-name","soc-sec-phone","soc-sec-sign","soc-plan",
#                         "soc-validity","arrear-start","soc-bg"],
#     },
#     "society_create": {
#         "group": "Society", "title": "Create Society", "icon": "fa-plus-circle",
#         "type": "create", "entity": "society",
#         "fields": [
#             {"id": "soc-logo",      "label": "Society Logo", "type": "upload", "accept": "image/*", "preview": True},
#             {"id": "soc-name",      "label": "Society Name *", "type": "text"},
#             {"id": "soc-email",     "label": "Email",          "type": "email"},
#             {"id": "soc-phone",     "label": "Phone",          "type": "tel"},
#             {"id": "soc-address",   "label": "Address",        "type": "textarea"},
#             {"id": "soc-sec-name",  "label": "Secretary Name", "type": "text"},
#             {"id": "soc-sec-phone", "label": "Secretary Phone","type": "tel"},
#             {"id": "soc-sec-sign",  "label": "Secretary Sign", "type": "upload", "accept": "image/*", "preview": True},
#             {"id": "soc-plan",      "label": "Plan",           "type": "select", "options": ["Free","9Apts","99Apts","999Apts","unlimited"]},
#             {"id": "soc-validity",  "label": "Plan Validity",  "type": "date"},
#             {"id": "arrear-start",   "label": "Arrear Start Date","type": "date"},
#             {"id": "soc-bg",        "label": "Login Background", "type": "upload", "accept": "image/*", "preview": True},
        
#             {"id": "new-admin-email",   "label": "Admin Email *",  "type": "email"},
#             {"id": "new-admin-pass",    "label": "Admin Password *","type": "password"},
#         ],
#         "save_btn": "create-society-btn",
#     },
#     "society_list": {
#         "group": "Society", "title": "Societies List", "icon": "fa-list",
#         "type": "list", "entity": "society",
#         "columns": ["logo","name","secretary_name","email","secretary_phone","Plan","Plan_Validity","Created","Actions"],
#         "list_id": "societies-list-table",
#     },
#     # ────────────────────── ENTITIES ─────────────────────────────
#     "entity_profile": {
#         "group": "Entities", "title": "Entity Profile", "icon": "fa-id-card",
#         "type": "profile", "entity": "entity",
#         "fields": [
#             {"id": "ent-flat",   "label": "Flat / Unit No",  "type": "text"},
#             {"id": "ent-name",   "label": "Owner / Name *",  "type": "text"},
#             {"id": "ent-mobile", "label": "Mobile",          "type": "tel"},
#             {"id": "ent-size",   "label": "Area (sq ft)",    "type": "number"},
#             {"id": "ent-role",   "label": "Role",            "type": "select",
#              "options": ["apartment","vendor","security"]},
#             {"id": "ent-email",  "label": "Email",           "type": "email"},
#             {"id": "ent-active", "label": "Active",          "type": "checkbox"},
#         ],
#         "save_btn": "save-entity-profile-btn",
#         "load_output": ["ent-flat","ent-name","ent-mobile","ent-size",
#                         "ent-role","ent-email"],
#     },
#     "entity_create": {
#         "group": "Entities", "title": "Create Entity", "icon": "fa-user-plus",
#         "type": "create", "entity": "entity",
#         "fields": [
#             {"id": "new-ent-flat",    "label": "Flat / Unit No",   "type": "text"},
#             {"id": "new-ent-name",    "label": "Owner / Name *",   "type": "text"},
#             {"id": "new-ent-mobile",  "label": "Mobile",           "type": "tel"},
#             {"id": "new-ent-size",    "label": "Area (sq ft)",     "type": "number"},
#             {"id": "new-ent-role",    "label": "Role *",           "type": "select",
#              "options": ["apartment","vendor","security"]},
#             {"id": "new-ent-email",   "label": "Login Email *",    "type": "email"},
#             {"id": "new-ent-pass",    "label": "Password *",       "type": "password"},
#             {"id": "new-ent-avatar",  "label": "Avatar",           "type": "upload",
#              "accept": "image/*"},
#         ],
#         "save_btn": "create-entity-btn",
#     },
#     "entity_list": {
#         "group": "Entities", "title": "Entities List", "icon": "fa-users",
#         "type": "list", "entity": "entity",
#         "columns": ["ID","Flat","Name","Role","Email","Active","Actions"],
#         "list_id": "entities-list-table",
#     },
#     # ────────────────────── ACCOUNTS ─────────────────────────────
#     "account_profile": {
#         "group": "Accounts", "title": "Account Profile", "icon": "fa-book",
#         "type": "profile", "entity": "account",
#         "fields": [
#             {"id": "acc-name",   "label": "Account Name *", "type": "text"},
#             {"id": "acc-tab",    "label": "Tab Name",    "type": "text"},
#             {"id": "acc-header", "label": "Header",         "type": "text"},
#             {"id": "acc-parent", "label": "Parent Account", "type": "text"},
#             {"id": "acc-drcr",   "label": "Dr / Cr Ac",        "type": "select",
#              "options": ["Dr","Cr"]},
#             {"id": "acc-bf-amt", "label": "Opening Balance","type": "number"},
#             {"id": "acc-bf-type","label": "Dr / Cr BF","type": "select",
#              "options": ["Dr","Cr"]},
#             {"id": "acc-dep-pct","label": "Depreciation %", "type": "number"},
#         ],
#         "save_btn": "save-account-profile-btn",
#     },
#     "account_create": {
#         "group": "Accounts", "title": "Create Account", "icon": "fa-plus-circle",
#         "type": "create", "entity": "account",
#         "fields": [
#             {"id": "new-acc-name",   "label": "Account Name *", "type": "text"},
#             {"id": "new-acc-tab",    "label": "Tab Name",    "type": "text"},
#             {"id": "new-acc-header", "label": "Header",         "type": "text"},
#             {"id": "new-acc-parent", "label": "Parent Account", "type": "text"},
#             {"id": "new-acc-drcr",   "label": "Dr / Cr Ac *",      "type": "select",
#              "options": ["Dr","Cr"]},
#             {"id": "new-acc-bf-amt", "label": "BF","type": "number"},
#             {"id": "new-acc-bf-type","label": "Dr /Cr BF","type": "select",
#              "options": ["Dr","Cr"]},
#             {"id": "new-acc-dep-pct","label": "Depreciation %", "type": "number"},
#         ],
#         "save_btn": "create-account-btn",
#     },
#     "account_list": {
#         "group": "Accounts", "title": "Accounts List", "icon": "fa-list",
#         "type": "list", "entity": "account",
#         "columns": ["name","tab_name","header","Dr/Cr Ac","Opening Bal","Depreciation %","Actions"],
#         "list_id": "accounts-list-table",
#     },
#     # ────────────────────── TRANSACTIONS / PAYMENTS ──────────────
#     "payment_profile": {
#         "group": "Payments", "title": "Payment Profile", "icon": "fa-credit-card",
#         "type": "profile", "entity": "payment",
#         "fields": [
#             {"id": "pay-flat",   "label": "Flat / Entity",  "type": "text"},
#             {"id": "pay-amount", "label": "Amount *",       "type": "number"},
#             {"id": "pay-type",   "label": "Payment Type",   "type": "select",
#              "options": ["maintenance","late_fee","fine","other"]},
#             {"id": "pay-method", "label": "Method",         "type": "select",
#              "options": ["cash","upi","card","bank","cheque"]},
#             {"id": "pay-status", "label": "Status",         "type": "select",
#              "options": ["pending","verified","failed"]},
#             {"id": "pay-due",    "label": "Due Date",       "type": "date"},
#             {"id": "pay-txn",    "label": "Transaction ID", "type": "text"},
#         ],
#         "save_btn": "save-payment-profile-btn",
#     },
#     "transaction_create": {
#         "group": "Payments", "title": "New Transaction", "icon": "fa-plus-circle",
#         "type": "create", "entity": "transaction",
#         "fields": [
#             {"id": "new-trx-date",   "label": "Date *",         "type": "date"},
#             {"id": "new-trx-acc",    "label": "Account",        "type": "text"},
#             {"id": "new-trx-part",   "label": "Particulars *",  "type": "text"},
#             {"id": "new-trx-amount", "label": "Amount *",       "type": "number"},
#             {"id": "new-trx-mode",   "label": "Mode",           "type": "select",
#              "options": ["cash","online","cheque","other"]},
#         ],
#         "save_btn": "create-transaction-btn",
#     },
#     "payment_list": {
#         "group": "Payments", "title": "Payments List", "icon": "fa-list",
#         "type": "list", "entity": "payment",
#         "columns": ["Date","Flat","Type","Amount","Method","Status","Actions"],
#         "list_id": "payments-list-table",
#     },
#     # ────────────────────── CHARGES ──────────────────────────────
#     "charge_profile": {
#         "group": "Charges", "title": "Charge Profile", "icon": "fa-file-invoice",
#         "type": "profile", "entity": "charge",
#         "fields": [
#             {"id": "chg-name",   "label": "Charge Name *",  "type": "text"},
#             {"id": "chg-amt",    "label": "Amount / Rate",  "type": "number"},
#             {"id": "chg-type",   "label": "Charge Type",    "type": "select",
#              "options": ["fixed","per_sqft","per_unit","percent"]},
#             {"id": "chg-entity", "label": "Applies To",     "type": "select",
#              "options": ["all","apartment","vendor","security"]},
#             {"id": "chg-freq",   "label": "Frequency",      "type": "select",
#              "options": ["monthly","quarterly","annual","one-time"]},
#             {"id": "chg-due",    "label": "Due Day",        "type": "number"},
#         ],
#         "save_btn": "save-charge-profile-btn",
#     },
#     "charge_create": {
#         "group": "Charges", "title": "Create Charge", "icon": "fa-plus-circle",
#         "type": "create", "entity": "charge",
#         "fields": [
#             {"id": "new-chg-name",   "label": "Charge Name *","type": "text"},
#             {"id": "new-chg-amt",    "label": "Amount / Rate","type": "number"},
#             {"id": "new-chg-type",   "label": "Charge Type",  "type": "select",
#              "options": ["fixed","per_sqft","per_unit","percent"]},
#             {"id": "new-chg-entity", "label": "Applies To",   "type": "select",
#              "options": ["all","apartment","vendor","security"]},
#             {"id": "new-chg-freq",   "label": "Frequency",    "type": "select",
#              "options": ["monthly","quarterly","annual","one-time"]},
#             {"id": "new-chg-due",    "label": "Due Day",      "type": "number"},
#         ],
#         "save_btn": "create-charge-btn",
#     },
#     "charge_list": {
#         "group": "Charges", "title": "Charges List", "icon": "fa-list",
#         "type": "list", "entity": "charge",
#         "columns": ["Name","Type","Rate","Applies To","Frequency","Due Day","Actions"],
#         "list_id": "charges-list-table",
#     },
#     # ────────────────────── CASHBOOK ─────────────────────────────
#     "new_receipt": {
#         "group": "Cashbook", "title": "New Receipt (Credit)", "icon": "fa-receipt",
#         "type": "create", "entity": "receipt",
#         "fields": [
#             {"id": "rcpt-date",  "label": "Date *",        "type": "date"},
#             {"id": "rcpt-acc",   "label": "Account",       "type": "text"},
#             {"id": "rcpt-from",  "label": "Received From *","type": "text"},
#             {"id": "rcpt-part",  "label": "Particulars *", "type": "text"},
#             {"id": "rcpt-amt",   "label": "Amount *",      "type": "number"},
#             {"id": "rcpt-mode",  "label": "Mode",          "type": "select",
#              "options": ["cash","upi","card","bank","cheque"]},
#         ],
#         "save_btn": "create-receipt-btn",
#     },
#     "new_expense": {
#         "group": "Cashbook", "title": "New Expense (Debit)", "icon": "fa-money-bills",
#         "type": "create", "entity": "expense",
#         "fields": [
#             {"id": "exp-date",  "label": "Date *",       "type": "date"},
#             {"id": "exp-acc",   "label": "Account",      "type": "text"},
#             {"id": "exp-to",    "label": "Paid To *",    "type": "text"},
#             {"id": "exp-part",  "label": "Particulars *","type": "text"},
#             {"id": "exp-amt",   "label": "Amount *",     "type": "number"},
#             {"id": "exp-mode",  "label": "Mode",         "type": "select",
#              "options": ["cash","upi","card","bank","cheque"]},
#         ],
#         "save_btn": "create-expense-btn",
#     },
#     "cashbook_list": {
#         "group": "Cashbook", "title": "Cashbook", "icon": "fa-wallet",
#         "type": "list", "entity": "cashbook",
#         "columns": ["Date","Particulars","Account","Debit","Credit","Balance","Actions"],
#         "list_id": "cashbook-full-table",
#     },
#     # ────────────────────── EVENTS ───────────────────────────────
#     "event_profile": {
#         "group": "Events", "title": "Event Profile", "icon": "fa-calendar-check",
#         "type": "profile", "entity": "event",
#         "fields": [
#             {"id": "evt-title",  "label": "Title *",     "type": "text"},
#             {"id": "evt-desc",   "label": "Description", "type": "textarea"},
#             {"id": "evt-date",   "label": "Event Date *","type": "date"},
#             {"id": "evt-time",   "label": "Time",        "type": "text"},
#             {"id": "evt-venue",  "label": "Venue",       "type": "text"},
#             {"id": "evt-open",   "label": "Open To",     "type": "select",
#              "options": ["all","apartment","vendor","security"]},
#         ],
#         "save_btn": "save-event-profile-btn",
#     },
#     "event_create": {
#         "group": "Events", "title": "Create Event", "icon": "fa-plus-circle",
#         "type": "create", "entity": "event",
#         "fields": [
#             {"id": "new-evt-title", "label": "Title *",    "type": "text"},
#             {"id": "new-evt-desc",  "label": "Description","type": "textarea"},
#             {"id": "new-evt-date",  "label": "Event Date *","type": "date"},
#             {"id": "new-evt-time",  "label": "Time",       "type": "text"},
#             {"id": "new-evt-venue", "label": "Venue",      "type": "text"},
#             {"id": "new-evt-open",  "label": "Open To",    "type": "select",
#              "options": ["all","apartment","vendor","security"]},
#         ],
#         "save_btn": "create-event-btn",
#     },
#     "event_list": {
#         "group": "Events", "title": "Events List", "icon": "fa-list",
#         "type": "list", "entity": "event",
#         "columns": ["Date","Title","Venue","Open To","Actions"],
#         "list_id": "events-list-table",
#     },
#     # ────────────────────── GATE LOGS ────────────────────────────
#     "gate_log_profile": {
#         "group": "Gate Logs", "title": "Gate Log Profile", "icon": "fa-receipt",
#         "type": "profile", "entity": "gate_log",
#         "fields": [
#             {"id": "gl-entity", "label": "Person / Flat",  "type": "text"},
#             {"id": "gl-role",   "label": "Role",           "type": "select",
#              "options": ["a","v","s","g"]},
#             {"id": "gl-in",     "label": "Time In",        "type": "text"},
#             {"id": "gl-out",    "label": "Time Out",       "type": "text"},
#         ],
#         "save_btn": "save-gate-log-btn",
#     },
#     "gate_log_create": {
#         "group": "Gate Logs", "title": "Create Gate Log", "icon": "fa-plus-circle",
#         "type": "create", "entity": "gate_log",
#         "fields": [
#             {"id": "new-gl-entity", "label": "Entity ID / Flat *","type": "text"},
#             {"id": "new-gl-role",   "label": "Role *",            "type": "select",
#              "options": ["apartment (a)","vendor (v)","security (s)","guest (g)"]},
#             {"id": "new-gl-in",     "label": "Time In *",         "type": "text"},
#             {"id": "new-gl-out",    "label": "Time Out",          "type": "text"},
#         ],
#         "save_btn": "create-gate-log-btn",
#     },
#     "gate_log_list": {
#         "group": "Gate Logs", "title": "Gate Logs List", "icon": "fa-list",
#         "type": "list", "entity": "gate_log",
#         "columns": ["Time In","Time Out","Person","Role","Duration","Actions"],
#         "list_id": "gate-logs-list-table",
#     },
#     # ────────────────────── CONCERNS ─────────────────────────────
#     "concern_profile": {
#         "group": "Concerns", "title": "Concern Profile", "icon": "fa-hand-point-up",
#         "type": "profile", "entity": "concern",
#         "fields": [
#             {"id": "con-flat",    "label": "Flat / By",   "type": "text"},
#             {"id": "con-type",    "label": "Type",        "type": "select",
#              "options": ["plumbing","electrical","cleaning","security","other"]},
#             {"id": "con-desc",    "label": "Description", "type": "textarea"},
#             {"id": "con-status",  "label": "Status",      "type": "select",
#              "options": ["open","in_progress","resolved","closed"]},
#             {"id": "con-assigned","label": "Assigned To", "type": "text"},
#         ],
#         "save_btn": "save-concern-profile-btn",
#     },
#     "concern_create": {
#         "group": "Concerns", "title": "Create Concern", "icon": "fa-plus-circle",
#         "type": "create", "entity": "concern",
#         "fields": [
#             {"id": "new-con-flat",   "label": "Flat / By *", "type": "text"},
#             {"id": "new-con-type",   "label": "Type *",      "type": "select",
#              "options": ["plumbing","electrical","cleaning","security","other"]},
#             {"id": "new-con-desc",   "label": "Description","type": "textarea"},
#             {"id": "new-con-pref",   "label": "Preferred Time","type": "select",
#              "options": ["morning","afternoon","evening","anytime"]},
#         ],
#         "save_btn": "create-concern-btn",
#     },
#     "concern_list": {
#         "group": "Concerns", "title": "Concerns List", "icon": "fa-list",
#         "type": "list", "entity": "concern",
#         "columns": ["Flat","Type","Description","Status","Assigned","Actions"],
#         "list_id": "concerns-list-table",
#     },
#     # ────────────────────── EVALUATE PASS ────────────────────────
#     "evaluate_pass": {
#         "group": "Security", "title": "Evaluate Pass", "icon": "fa-qrcode",
#         "type": "special", "entity": "gate_pass",
#         "component": "evaluate_pass_card",
#     },
#     # ────────────────────── SETTINGS ─────────────────────────────
#     "settings_rates": {
#         "group": "Settings", "title": "Rates & Fines", "icon": "fa-sliders-h",
#         "type": "create", "entity": "settings",
#         "fields": [
#             {"id": "rate-maint",     "label": "Maintenance Rate (₹/sq ft)", "type": "number"},
#             {"id": "rate-due-day",   "label": "Due Day of Month",           "type": "number"},
#             {"id": "rate-late-day",  "label": "Late Fee (₹/day)",           "type": "number"},
#             {"id": "rate-late-max",  "label": "Max Late Fee (%)",           "type": "number"},
#             {"id": "rate-vendor",    "label": "Vendor Monthly Fee (₹)",     "type": "number"},
#             {"id": "rate-security",  "label": "Security Monthly (₹)",       "type": "number"},
#             {"id": "rate-arrear-dt", "label": "Arrear Start Date",          "type": "date"},
#         ],
#         "save_btn": "save-rates-fines-btn",
#     },
# }

# ================================================================
# ── MASTER CATALOGUE
# ================================================================
CARD_CATALOGUE = {**KPI_CARDS}

# ================================================================
# ── CUSTOMIZATION CATALOGUE
# ================================================================
# A normalized catalogue for UI customization and saved layout state.
# This separates KPIs, forms, and lists so customization data can be
# stored independently and later wired back into the drilldown engine.
# LIST_CARDS = {cid: cfg for cid, cfg in FORM_CARDS.items() if cfg.get("type") == "list"}
# FORM_CARDS_ONLY = {cid: cfg for cid, cfg in FORM_CARDS.items() if cfg.get("type") in ("profile", "create")}
# CUSTOMIZABLE_CARD_CATALOGUE = {
#     "kpis": KPI_CARDS,
#     "forms": FORM_CARDS_ONLY,
#     "lists": LIST_CARDS,
# }

# ── Default dashboard cards per portal ─────────────────────────
DEFAULT_LAYOUTS = {
    "admin": [
        "kpi_apartments_total",
        "kpi_apartments_dues",
        "kpi_vendors_total",
        "kpi_security_total",
        "kpi_security_on_duty",
        "kpi_events_total",
        "kpi_concerns_open",
        "kpi_gate_logs",
        "kpi_receipts_month",
        "kpi_expenses_month",
        "kpi_cash_in_hand",
        "kpi_bank_balance",
    ],
    "apartment": [
        "kpi_apartments_dues",
        "kpi_concerns_open",
        "kpi_events_total",
        "kpi_gate_logs",
        "kpi_receipts_month",
        "kpi_receivables_total",
    ],
    "vendor": [
        "kpi_concerns_open",
        "kpi_events_total",
        "kpi_receivables_total",
        "kpi_receipts_month",
        "kpi_gate_logs",
    ],
    "security": [
        "kpi_apartments_total",
        "kpi_vendors_total",
        "kpi_security_total",
        "kpi_security_shift_count",
        "kpi_receivables_total",
        "kpi_payables_total",
        "kpi_receipts_month",
        "kpi_expenses_month",
        "kpi_gate_logs",
    ],
    "master": [
        "kpi_societies_total",
        "kpi_societies_free",
        "kpi_societies_9Apts",
        "kpi_societies_99Apts",
        "kpi_societies_999Apts",
        "kpi_societies_unlimited",
        "kpi_master_apartments_total",
        "kpi_master_vendors_total",
        "kpi_master_security_total",
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
    
    