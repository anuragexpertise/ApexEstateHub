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
                        THEN amount * 0.02 * EXTRACT(DAY FROM AGE(CURRENT_DATE, due_date)) / 30
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
            SELECT 
                (tmd.amount - pm.amount + lf.amount + vd.amount) AS v
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
            SELECT 
                COALESCE(SUM(apartment_size * rate_per_sqft * GREATEST(months_due, 0)), 0) AS v
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
                    THEN amount * 0.02 * EXTRACT(DAY FROM AGE(CURRENT_DATE, due_date)) / 30
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
            SELECT 
                (ss.amount - sp.amount + vp.amount + pe.amount) AS v
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
            SELECT (std.amount - sp.amount) AS v
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
            SELECT (ob.amount + r.amount - e.amount) AS v
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
            SELECT (r.amount - e.amount) AS v
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
