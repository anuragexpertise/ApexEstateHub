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

KPI_CARDS = {
    
    # ── RECEIVABLES (Money Society Should Receive) ─────────────────────────
    
    "kpi_receivables_total": {
        "query": """
            WITH maintenance_due AS (
                -- Calculate maintenance from arrear_start_date to current
                SELECT 
                    a.id,
                    a.apartment_size,
                    s.arrear_start_date,
                    -- Number of months from arrear start to now
                    EXTRACT(YEAR FROM AGE(CURRENT_DATE, s.arrear_start_date)) * 12 + 
                    EXTRACT(MONTH FROM AGE(CURRENT_DATE, s.arrear_start_date)) AS months_due,
                    -- Default rate ₹3/sqft (should come from settings)
                    3.0 AS rate_per_sqft
                FROM apartments a
                JOIN societies s ON a.society_id = s.id
                WHERE a.society_id = %s AND a.active = TRUE
            ),
            total_maintenance AS (
                SELECT 
                    SUM(apartment_size * rate_per_sqft * GREATEST(months_due, 0)) AS amount
                FROM maintenance_due
            ),
            payments_made AS (
                -- Subtract already paid maintenance
                SELECT COALESCE(SUM(amount), 0) AS amount
                FROM payments
                WHERE society_id = %s 
                  AND payment_type = 'maintenance' 
                  AND status = 'verified'
            ),
            late_fees AS (
                -- Calculate late fees on overdue payments
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
                -- Vendor pass fees pending
                SELECT COALESCE(SUM(amount), 0) AS amount
                FROM payments
                WHERE society_id = %s 
                  AND payment_type = 'vendor_pass' 
                  AND status = 'pending'
            )
            SELECT 
                COALESCE(tm.amount, 0) - COALESCE(pm.amount, 0) + 
                COALESCE(lf.amount, 0) + COALESCE(vd.amount, 0) AS v
            FROM total_maintenance tm, payments_made pm, late_fees lf, vendor_dues vd
        """,
        "params": 4,  # society_id used 4 times
        "format": "currency",
        "description": "Total outstanding receivables (maintenance + late fees + vendor dues)",
    },
    
    "kpi_maintenance_due": {
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
            )
            SELECT 
                COALESCE(SUM(apartment_size * rate_per_sqft * GREATEST(months_due, 0)), 0) AS v
            FROM maintenance_calculation
        """,
        "params": 1,
        "format": "currency",
        "description": "Total maintenance charges due (from arrear_start_date)",
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
        "description": "Total maintenance collected",
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
        "description": "Late fees on overdue payments (2% per month)",
    },
    
    "kpi_apartments_dues": {
        "query": """
            SELECT COUNT(DISTINCT apartment_id) AS v
            FROM payments
            WHERE society_id = %s 
              AND status = 'pending' 
              AND apartment_id IS NOT NULL
        """,
        "params": 1,
        "format": "count",
        "description": "Number of apartments with pending dues",
    },
    
    "kpi_apartments_no_dues": {
        "query": """
            SELECT COUNT(*) AS v
            FROM apartments
            WHERE society_id = %s 
              AND active = TRUE
              AND id NOT IN (
                  SELECT DISTINCT apartment_id 
                  FROM payments 
                  WHERE society_id = %s 
                    AND status = 'pending' 
                    AND apartment_id IS NOT NULL
              )
        """,
        "params": 2,
        "format": "count",
        "description": "Apartments with no pending dues",
    },
    
    # ── PAYABLES (Money Society Needs to Pay) ──────────────────────────────
    
    "kpi_payables_total": {
        "query": """
            WITH security_salaries AS (
                -- Calculate unpaid security salaries
                SELECT COALESCE(SUM(
                    ss.salary_per_shift * 
                    EXTRACT(DAY FROM AGE(CURRENT_DATE, COALESCE(ss.joining_date, CURRENT_DATE)))
                ), 0) AS amount
                FROM security_staff ss
                WHERE ss.society_id = %s 
                  AND ss.active = TRUE
            ),
            vendor_payments AS (
                -- Pending vendor payments
                SELECT COALESCE(SUM(amount), 0) AS amount
                FROM payments
                WHERE society_id = %s 
                  AND user_id IN (
                      SELECT id FROM users 
                      WHERE society_id = %s AND role = 'vendor'
                  )
                  AND status = 'pending'
            ),
            pending_expenses AS (
                -- Other pending expenses
                SELECT COALESCE(SUM(amount), 0) AS amount
                FROM transactions
                WHERE society_id = %s 
                  AND status = 'pending'
                  AND acc_id IN (
                      SELECT id FROM accounts 
                      WHERE society_id = %s AND drcr_account = 'Dr'
                  )
            )
            SELECT 
                COALESCE(ss.amount, 0) + 
                COALESCE(vp.amount, 0) + 
                COALESCE(pe.amount, 0) AS v
            FROM security_salaries ss, vendor_payments vp, pending_expenses pe
        """,
        "params": 5,
        "format": "currency",
        "description": "Total payables (salaries + vendor payments + expenses)",
    },
    
    "kpi_security_salaries_due": {
        "query": """
            SELECT COALESCE(SUM(
                ss.salary_per_shift * 
                EXTRACT(DAY FROM AGE(CURRENT_DATE, COALESCE(ss.joining_date, CURRENT_DATE)))
            ), 0) AS v
            FROM security_staff ss
            LEFT JOIN payments p ON p.user_id IN (
                SELECT id FROM users WHERE linked_id = ss.id AND role = 'security'
            ) AND p.payment_type = 'salary' AND p.status = 'verified'
            WHERE ss.society_id = %s 
              AND ss.active = TRUE
              AND p.id IS NULL
        """,
        "params": 1,
        "format": "currency",
        "description": "Unpaid security salaries",
    },
    
    "kpi_vendor_payments_due": {
        "query": """
            SELECT COALESCE(SUM(amount), 0) AS v
            FROM payments
            WHERE society_id = %s 
              AND user_id IN (
                  SELECT id FROM users WHERE society_id = %s AND role = 'vendor'
              )
              AND status = 'pending'
        """,
        "params": 2,
        "format": "currency",
        "description": "Pending payments to vendors",
    },
    
    # ── CASHBOOK & BALANCE ──────────────────────────────────────────────────
    
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
        "description": "Total receipts this month (Cr accounts)",
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
        "description": "Total expenses this month (Dr accounts)",
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
            )
            SELECT (r.amount - e.amount) AS v
            FROM receipts r, expenses e
        """,
        "params": 2,
        "format": "currency",
        "description": "Current balance (Receipts - Expenses)",
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
        "description": "Cash in hand (cash receipts - cash expenses)",
    },
    
    # ── ENTITY COUNTS ───────────────────────────────────────────────────────
    
    "kpi_apartments_total": {
        "query": "SELECT COUNT(*) AS v FROM apartments WHERE society_id = %s AND active = TRUE",
        "params": 1,
        "format": "count",
        "description": "Total active apartments",
    },
    
    "kpi_vendors_total": {
        "query": "SELECT COUNT(*) AS v FROM users WHERE society_id = %s AND role = 'vendor'",
        "params": 1,
        "format": "count",
        "description": "Total vendors",
    },
    
    "kpi_vendors_dues": {
        "query": """
            SELECT COUNT(DISTINCT user_id) AS v
            FROM payments
            WHERE society_id = %s 
              AND status = 'pending' 
              AND user_id IN (
                  SELECT id FROM users WHERE society_id = %s AND role = 'vendor'
              )
        """,
        "params": 2,
        "format": "count",
        "description": "Vendors with pending dues",
    },
    
    "kpi_security_total": {
        "query": "SELECT COUNT(*) AS v FROM users WHERE society_id = %s AND role = 'security'",
        "params": 1,
        "format": "count",
        "description": "Total security staff",
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
        "format": "count",
        "description": "Security staff currently on duty",
    },
    
    # ── EVENTS & CONCERNS ───────────────────────────────────────────────────
    
    "kpi_events_total": {
        "query": """
            SELECT COUNT(*) AS v 
            FROM events 
            WHERE society_id = %s 
              AND event_date >= CURRENT_DATE
        """,
        "params": 1,
        "format": "count",
        "description": "Upcoming events",
    },
    
    "kpi_concerns_open": {
        "query": """
            SELECT COUNT(*) AS v 
            FROM concerns 
            WHERE society_id = %s 
              AND status IN ('open', 'in_progress')
        """,
        "params": 1,
        "format": "count",
        "description": "Open/active concerns",
    },
    
    # ── GATE LOGS ───────────────────────────────────────────────────────────
    
    "kpi_gate_logs": {
        "query": """
            SELECT COUNT(*) AS v 
            FROM gate_access 
            WHERE society_id = %s 
              AND time_in >= CURRENT_DATE
        """,
        "params": 1,
        "format": "count",
        "description": "Gate entries today",
    },
    
    # ── MASTER ADMIN KPIs ───────────────────────────────────────────────────
    
    "kpi_societies_total": {
        "query": "SELECT COUNT(*) AS v FROM societies",
        "params": 0,
        "format": "count",
        "description": "Total societies on platform",
    },
    
    "kpi_societies_paid": {
        "query": """
            SELECT COUNT(*) AS v 
            FROM societies 
            WHERE plan != 'Free' 
              AND plan_validity >= CURRENT_DATE
        """,
        "params": 0,
        "format": "count",
        "description": "Active paid societies",
    },
    
    "kpi_societies_free": {
        "query": "SELECT COUNT(*) AS v FROM societies WHERE plan = 'Free'",
        "params": 0,
        "format": "count",
        "description": "Free plan societies",
    },
    
    "kpi_societies_expired": {
        "query": """
            SELECT COUNT(*) AS v 
            FROM societies 
            WHERE plan != 'Free' 
              AND plan_validity < CURRENT_DATE
        """,
        "params": 0,
        "format": "count",
        "description": "Societies with expired plans",
    },
}


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
