"""
card_catalogue.py - ENHANCED VERSION
═══════════════════════════════════════════════════════════════
Master catalogue of every KPI, Form and List card.
ENHANCED: Full support for number, text, date, percent, and currency formats
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
    
    "kpi_apartments_dues": {
        "query": """
            SELECT COUNT(DISTINCT a.id) AS v 
            FROM apartments a
            INNER JOIN payments p ON p.apartment_id = a.id
            WHERE a.society_id = %s 
              AND p.status = 'pending'
              AND a.active = TRUE
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-exclamation-triangle",
        "color": "#de5c52",
        "title": "With Dues",
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
                  WHERE p.apartment_id = a.id 
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
            INNER JOIN apartments a ON a.id = p.apartment_id
            WHERE a.society_id = %s 
              AND p.status = 'pending'
        """,
        "params": 1,
        "format": "currency",
        "icon": "fa-rupee-sign",
        "color": "#e59620",
        "title": "Total Pending Dues",
        "group": "all apartments",
    },
    
    # ──────────────────────────────────────────────────────────────────────
    # VENDORS KPIs
    # ──────────────────────────────────────────────────────────────────────
    "kpi_vendors_total": {
        "query": """
            SELECT COUNT(*) AS v 
            FROM users u
            INNER JOIN vendors v ON v.id = u.linked_id
            WHERE u.society_id = %s 
              AND u.role = 'vendor'
              AND v.active = TRUE
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-truck",
        "color": "#b98a07",
        "title": "Active Vendors",
        "group": "registered",
    },
    
    "kpi_vendors_dues": {
        "query": """
            SELECT COUNT(DISTINCT u.id) AS v 
            FROM users u
            INNER JOIN payments p ON p.user_id = u.id
            WHERE u.society_id = %s 
              AND u.role = 'vendor'
              AND p.status = 'pending'
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-exclamation-circle",
        "color": "#de5c52",
        "title": "Vendors With Dues",
        "group": "pending",
    },
    
    # ──────────────────────────────────────────────────────────────────────
    # SECURITY KPIs
    # ──────────────────────────────────────────────────────────────────────
    "kpi_security_total": {
        "query": """
            SELECT COUNT(*) AS v 
            FROM users u
            INNER JOIN security_staff s ON s.id = u.linked_id
            WHERE u.society_id = %s 
              AND u.role = 'security'
              AND s.active = TRUE
        """,
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
              AND time_in >= CURRENT_DATE
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-shield-alt",
        "color": "#17976e",
        "title": "On Duty Now",
        "group": "active shift",
    },
    
    # ──────────────────────────────────────────────────────────────────────
    # EVENTS KPIs
    # ──────────────────────────────────────────────────────────────────────
    "kpi_events_total": {
        "query": """
            SELECT COUNT(*) AS v 
            FROM events 
            WHERE society_id = %s 
              AND event_date >= CURRENT_DATE
            ORDER BY event_date
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-calendar-check",
        "color": "#8e44ad",
        "title": "Upcoming Events",
        "group": "scheduled",
    },
    
    "kpi_events_next_date": {
        "query": """
            SELECT MIN(event_date) AS v 
            FROM events 
            WHERE society_id = %s 
              AND event_date >= CURRENT_DATE
        """,
        "params": 1,
        "format": "date",
        "icon": "fa-calendar-day",
        "color": "#8e44ad",
        "title": "Next Event",
        "group": "upcoming",
    },
    
    # ──────────────────────────────────────────────────────────────────────
    # CONCERNS KPIs
    # ──────────────────────────────────────────────────────────────────────
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
        "group": "needs attention",
    },
    
    "kpi_concerns_resolved": {
        "query": """
            SELECT COUNT(*) AS v 
            FROM concerns 
            WHERE society_id = %s 
              AND status = 'resolved'
              AND created_at >= DATE_TRUNC('month', CURRENT_DATE)
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-check-double",
        "color": "#17976e",
        "title": "Resolved (Month)",
        "group": "this month",
    },
    
    # ──────────────────────────────────────────────────────────────────────
    # GATE LOGS KPIs
    # ──────────────────────────────────────────────────────────────────────
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
    
    "kpi_gate_active": {
        "query": """
            SELECT COUNT(*) AS v 
            FROM gate_access 
            WHERE society_id = %s 
              AND time_out IS NULL
              AND time_in >= CURRENT_DATE
        """,
        "params": 1,
        "format": "number",
        "icon": "fa-door-open",
        "color": "#1abc9c",
        "title": "Currently Inside",
        "group": "active",
    },
    
    # ──────────────────────────────────────────────────────────────────────
    # FINANCIAL KPIs (TRANSACTIONS)
    # ──────────────────────────────────────────────────────────────────────
    "kpi_receipts_month": {
        "query": """
            SELECT COALESCE(SUM(t.amount), 0) AS v 
            FROM transactions t
            INNER JOIN accounts a ON a.id = t.acc_id
            WHERE t.society_id = %s 
              AND a.drcr_account = 'Cr'
              AND t.status = 'paid'
              AND t.trx_date >= DATE_TRUNC('month', CURRENT_DATE)
        """,
        "params": 1,
        "format": "currency",
        "icon": "fa-receipt",
        "color": "#17976e",
        "title": "Receipts (Month)",
        "group": "income",
    },
    
    "kpi_expenses_month": {
        "query": """
            SELECT COALESCE(SUM(t.amount), 0) AS v 
            FROM transactions t
            INNER JOIN accounts a ON a.id = t.acc_id
            WHERE t.society_id = %s 
              AND a.drcr_account = 'Dr'
              AND t.status = 'paid'
              AND t.trx_date >= DATE_TRUNC('month', CURRENT_DATE)
        """,
        "params": 1,
        "format": "currency",
        "icon": "fa-wallet",
        "color": "#de5c52",
        "title": "Expenses (Month)",
        "group": "outgoing",
    },
    
    "kpi_balance": {
        "query": """
            SELECT COALESCE(SUM(
                CASE 
                    WHEN a.drcr_account = 'Cr' THEN t.amount 
                    WHEN a.drcr_account = 'Dr' THEN -t.amount 
                    ELSE 0 
                END
            ), 0) AS v 
            FROM transactions t
            INNER JOIN accounts a ON a.id = t.acc_id
            WHERE t.society_id = %s 
              AND t.status = 'paid'
        """,
        "params": 1,
        "format": "currency",
        "icon": "fa-wallet",
        "color": "#2c3e50",
        "title": "Net Balance",
        "group": "total",
    },
    
    "kpi_cash_in_hand": {
        "query": """
            SELECT COALESCE(SUM(
                CASE 
                    WHEN a.drcr_account = 'Cr' THEN t.amount 
                    WHEN a.drcr_account = 'Dr' THEN -t.amount 
                    ELSE 0 
                END
            ), 0) AS v 
            FROM transactions t
            INNER JOIN accounts a ON a.id = t.acc_id
            WHERE t.society_id = %s 
              AND t.status = 'paid'
              AND t.mode = 'cash'
        """,
        "params": 1,
        "format": "currency",
        "icon": "fa-money-bill-wave",
        "color": "#27ae60",
        "title": "Cash in Hand",
        "group": "physical",
    },
    "kpi_apartments_total": {
        "query": "SELECT COUNT(*) AS v FROM apartments WHERE society_id = %s AND active = TRUE",
        "params": 1,
        "format": "number",
        "icon": "fa-home",
        "color": "#1859b8",
        "title": "Total Apartments",
        "group": "active units",
    },
    "kpi_collection_rate": {
        "query": """
            SELECT 
                CASE 
                    WHEN total_due.amount > 0 
                    THEN ROUND((collected.amount::NUMERIC / total_due.amount::NUMERIC) * 100, 1)
                    ELSE 100.0 
                END AS v
            FROM 
                (SELECT COALESCE(SUM(amount), 0) AS amount 
                 FROM payments 
                 WHERE society_id = %s 
                   AND due_date <= CURRENT_DATE) AS total_due,
                (SELECT COALESCE(SUM(amount), 0) AS amount 
                 FROM payments 
                 WHERE society_id = %s 
                   AND status = 'verified' 
                   AND due_date <= CURRENT_DATE) AS collected
        """,
        "params": 2,
        "format": "percent",
        "icon": "fa-percent",
        "color": "#3498db",
        "title": "Collection Rate",
        "group": "efficiency",
    },
    
    # ──────────────────────────────────────────────────────────────────────
    # MASTER ADMIN KPIs
    # ──────────────────────────────────────────────────────────────────────
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
    
    "kpi_societies_expiring": {
        "query": """
            SELECT COUNT(*) AS v 
            FROM societies 
            WHERE plan != 'Free' 
              AND plan_validity BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days'
        """,
        "params": 0,
        "format": "number",
        "icon": "fa-exclamation-triangle",
        "color": "#e59620",
        "title": "Expiring Soon",
        "group": "30 days",
    },
    
    # ──────────────────────────────────────────────────────────────────────
    # TEXT-BASED KPIs (Status/Names)
    # ──────────────────────────────────────────────────────────────────────
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


# ... (Rest of the file remains the same - FORM_CARDS, etc.)
