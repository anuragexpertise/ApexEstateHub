# app/dash_apps/drilldown/loaders_enhanced.py
"""
Enhanced Data Loaders - Show Data Instead of IDs + IMAGE DEBUGGING
===================================================================
Returns human-readable data with proper joins and lookups.
ENHANCED: Comprehensive image path debugging for all entities.
"""

from __future__ import annotations
from datetime import datetime, date
import csv
import io
from database.db_manager import db
from pathlib import Path

PAGE_SIZE = 15


# ════════════════════════════════════════════════════════════════════════════
# IMAGE PATH DEBUGGING
# ════════════════════════════════════════════════════════════════════════════

def debug_image_in_profile(entity: str, pk: int, row: dict):
    """
    Print debug info for all image fields in a profile.
    """
    print(f"\n{'='*70}")
    print(f"🖼️  IMAGE DEBUG: {entity.upper()} Profile (PK={pk})")
    print(f"{'='*70}")
    
    society_id = row.get('society_id')
    print(f"Society ID: {society_id}")
    print(f"Record ID:  {pk}")
    print(f"Entity:     {entity}")
    
    # List of potential image fields by entity
    image_fields_map = {
        "society": ["logo", "login_background", "secretary_sign"],
        "apartment": ["photo", "id_proof", "owner_photo"],
        "vendor": ["logo", "license", "photo"],
        "security": ["photo", "id_proof"],
    }
    
    image_fields = image_fields_map.get(entity, [])
    
    if not image_fields:
        print(f"⚠️  No known image fields for entity '{entity}'")
        print(f"{'='*70}\n")
        return
    
    found_any = False
    for field in image_fields:
        if field in row:
            value = row[field]
            if value and str(value).strip():
                found_any = True
                print(f"\n  📁 Field: {field}")
                print(f"     Database Value: {value}")
                
                # Determine expected path
                if entity == "society":
                    expected_url = f"/assets/{society_id}/{value}"
                    expected_disk = Path(f"app/assets/{society_id}/{value}")
                elif entity in ("apartment", "vendor", "security"):
                    expected_url = f"/assets/{society_id}/{entity}/{pk}/{value}"
                    expected_disk = Path(f"app/assets/{society_id}/{entity}/{pk}/{value}")
                else:
                    expected_url = f"/assets/{society_id}/{entity}_{pk}/{value}"
                    expected_disk = Path(f"app/assets/{society_id}/{entity}_{pk}/{value}")
                
                print(f"     Expected URL:   {expected_url}")
                print(f"     Expected Disk:  {expected_disk}")
                print(f"     Folder Exists:  {expected_disk.parent.exists()}")
                print(f"     File Exists:    {expected_disk.exists()}")
                
                if not expected_disk.exists():
                    print(f"     ❌ FILE NOT FOUND!")
                    
                    # Check alternative locations
                    print(f"\n     🔍 Checking alternative locations...")
                    
                    # Check default folder
                    default_path = Path(f"app/assets/default/{entity}/{value}")
                    if default_path.exists():
                        print(f"        ✅ Found in default folder: {default_path}")
                    
                    # Check root society folder
                    if entity != "society":
                        root_path = Path(f"app/assets/{society_id}/{value}")
                        if root_path.exists():
                            print(f"        ✅ Found in society root: {root_path}")
                    
                    # List what's actually in the expected folder
                    if expected_disk.parent.exists():
                        actual_files = list(expected_disk.parent.glob("*"))
                        if actual_files:
                            print(f"        📂 Files in {expected_disk.parent}:")
                            for f in actual_files[:5]:
                                print(f"           - {f.name}")
                            if len(actual_files) > 5:
                                print(f"           ... and {len(actual_files) - 5} more")
                        else:
                            print(f"        📂 Folder exists but is empty")
                else:
                    print(f"     ✅ FILE FOUND!")
    
    if not found_any:
        print(f"\n  ℹ️  No image fields contain data")
    
    print(f"\n{'='*70}\n")


# ════════════════════════════════════════════════════════════════════════════
# DELETE HELPER
# ════════════════════════════════════════════════════════════════════════════

def delete_entity(entity_plural: str, pk, society_id=None) -> tuple:
    """Delete a record. Returns (ok, message)."""
    
    TABLE_MAP = {
        "apartments": ("apartments",   "id"),
        "vendors":    ("users",        "id"),
        "security":   ("users",        "id"),
        "events":     ("events",       "id"),
        "concerns":   ("concerns",     "id"),
        "gate_logs":  ("gate_access",  "id"),
        "receipts":   ("transactions", "id"),
        "expenses":   ("transactions", "id"),
        "cashbook":   ("transactions", "id"),
        "societies":  ("societies",    "id"),
        "accounts":   ("accounts",     "id"),
    }
    if entity_plural not in TABLE_MAP:
        return False, f"No delete handler for '{entity_plural}'"

    table, pk_col = TABLE_MAP[entity_plural]
    try:
        if society_id and table not in ("societies", "users"):
            db._execute(
                f"DELETE FROM {table} WHERE {pk_col} = %s AND society_id = %s",
                (pk, society_id),
            )
        else:
            db._execute(
                f"DELETE FROM {table} WHERE {pk_col} = %s", (pk,),
            )
        return True, "Record deleted"
    except Exception as e:
        return False, str(e)


# ════════════════════════════════════════════════════════════════════════════
# ENHANCED PROFILE LOADER (With Image Debugging)
# ════════════════════════════════════════════════════════════════════════════

def load_profile(entity: str, pk, society_id=None) -> dict | None:
    """Load profile with calculated fields and IMAGE DEBUGGING."""
    
    try:
        if entity == "apartment":
            row = db._execute(
                """
                WITH apartment_data AS (
                    SELECT 
                        a.*,
                        s.arrear_start_date,
                        EXTRACT(YEAR FROM AGE(CURRENT_DATE, s.arrear_start_date)) * 12 + 
                        EXTRACT(MONTH FROM AGE(CURRENT_DATE, s.arrear_start_date)) AS months_due,
                        3.0 AS rate_per_sqft
                    FROM apartments a
                    JOIN societies s ON a.society_id = s.id
                    WHERE a.id = %s
                ),
                payment_summary AS (
                    SELECT 
                        COALESCE(SUM(amount) FILTER (WHERE status='verified'), 0) AS paid,
                        COALESCE(SUM(amount) FILTER (WHERE status='pending'), 0) AS pending
                    FROM payments
                    WHERE apartment_id = %s
                ),
                late_fee_calc AS (
                    SELECT COALESCE(SUM(
                        CASE 
                            WHEN due_date < CURRENT_DATE 
                            THEN amount * 0.02 * EXTRACT(DAY FROM AGE(CURRENT_DATE, due_date)) / 30
                            ELSE 0 
                        END
                    ), 0) AS late_fee
                    FROM payments
                    WHERE apartment_id = %s AND status = 'pending'
                )
                SELECT 
                    ad.*,
                    ps.paid AS paid_amount,
                    ps.pending AS pending_amount,
                    lf.late_fee,
                    (ad.apartment_size * ad.rate_per_sqft * GREATEST(ad.months_due, 0)) AS total_maintenance_due,
                    (ad.apartment_size * ad.rate_per_sqft * GREATEST(ad.months_due, 0)) - ps.paid + lf.late_fee AS pending_dues
                FROM apartment_data ad, payment_summary ps, late_fee_calc lf
                """,
                (pk, pk, pk),
                fetch_one=True
            )
            
            if row:
                row["subtitle"] = f"Flat {row.get('flat_number', '?')} - {row.get('owner_name', '')}"
                debug_image_in_profile("apartment", pk, row)
            
            return row
        
        if entity == "vendor":
            row = db._execute(
                """
                SELECT 
                    u.id,
                    u.email,
                    u.society_id,
                    u.linked_id,
                    v.name AS business_name,
                    v.service_type,
                    v.mobile,
                    v.active,
                    COALESCE(SUM(p.amount) FILTER (WHERE p.status='pending'), 0) AS pending_dues,
                    COALESCE(SUM(p.amount) FILTER (WHERE p.status='verified'), 0) AS paid_amount
                FROM users u
                LEFT JOIN vendors v ON v.id = u.linked_id
                LEFT JOIN payments p ON p.user_id = u.id
                WHERE u.id = %s AND u.role = 'vendor'
                GROUP BY u.id, v.name, v.service_type, v.mobile, v.active
                """,
                (pk,),
                fetch_one=True
            )
            
            if row:
                row["subtitle"] = row.get("business_name", "Vendor")
                debug_image_in_profile("vendor", pk, row)
            
            return row
        
        if entity == "security":
            row = db._execute(
                """
                SELECT 
                    u.id,
                    u.email,
                    u.society_id,
                    u.linked_id,
                    s.name,
                    s.shift,
                    s.mobile,
                    s.active,
                    s.salary_per_shift,
                    s.joining_date,
                    EXTRACT(DAY FROM AGE(CURRENT_DATE, COALESCE(s.joining_date, CURRENT_DATE))) AS days_worked,
                    s.salary_per_shift * EXTRACT(DAY FROM AGE(CURRENT_DATE, COALESCE(s.joining_date, CURRENT_DATE))) AS total_salary_due,
                    COALESCE(SUM(p.amount) FILTER (WHERE p.status='verified' AND p.payment_type='salary'), 0) AS salary_paid,
                    (s.salary_per_shift * EXTRACT(DAY FROM AGE(CURRENT_DATE, COALESCE(s.joining_date, CURRENT_DATE)))) - 
                    COALESCE(SUM(p.amount) FILTER (WHERE p.status='verified' AND p.payment_type='salary'), 0) AS salary_pending
                FROM users u
                LEFT JOIN security_staff s ON s.id = u.linked_id
                LEFT JOIN payments p ON p.user_id = u.id
                WHERE u.id = %s AND u.role = 'security'
                GROUP BY u.id, s.name, s.shift, s.mobile, s.active, s.salary_per_shift, s.joining_date
                """,
                (pk,),
                fetch_one=True
            )
            
            if row:
                row["subtitle"] = row.get("name", "Security")
                debug_image_in_profile("security", pk, row)
            
            return row
        
        if entity == "society":
            # ═══ ENHANCED: Financial summary ═══
            row = db._execute(
                """
                SELECT 
                    s.*,
                    CASE 
                        WHEN s.plan = 'Free' THEN 'Free'
                        WHEN s.plan_validity >= CURRENT_DATE THEN 'Active'
                        ELSE 'Expired'
                    END AS plan_status,
                    (SELECT COUNT(*) FROM apartments WHERE society_id = s.id AND active = TRUE) AS total_apartments,
                    (SELECT COUNT(*) FROM users WHERE society_id = s.id) AS total_users,
                    (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE society_id = s.id AND status = 'pending') AS total_receivables
                FROM societies s
                WHERE s.id = %s
                """,
                (pk,),
                fetch_one=True
            )
            
            # ✅ CRITICAL: Add the record's own ID as society_id for image resolution
            if row:
                row['_image_society_id'] = row['id']  # Use society's own ID for images
            
            return row
        
        # Simple entities (no debugging for now)
        if entity == "event":
            return db._execute("SELECT * FROM events WHERE id=%s", (pk,), fetch_one=True)
        
        if entity == "concern":
            return db._execute("SELECT * FROM concerns WHERE id=%s", (pk,), fetch_one=True)
        
        if entity in ("receipt", "expense", "transaction"):
            return db._execute(
                """
                SELECT 
                    t.*,
                    acc.name AS account_name,
                    acc.tab_name AS account_group,
                    CASE 
                        WHEN a.id IS NOT NULL THEN CONCAT('Flat ', a.flat_number)
                        WHEN v.id IS NOT NULL THEN v.name
                        ELSE '—'
                    END AS entity_name
                FROM transactions t
                JOIN accounts acc ON t.acc_id = acc.id
                LEFT JOIN apartments a ON t.entity_id = a.id
                LEFT JOIN vendors v ON t.entity_id IN (
                    SELECT linked_id FROM users WHERE role='vendor' AND linked_id IS NOT NULL
                )
                WHERE t.id = %s
                """,
                (pk,),
                fetch_one=True
            )
        
        if entity == "gate_log":
            return db._execute(
                """
                SELECT 
                    g.*,
                    CASE 
                        WHEN g.role = 'a' THEN (SELECT CONCAT('Flat ', flat_number) FROM apartments WHERE id = g.entity_id)
                        WHEN g.role = 'v' THEN (SELECT name FROM vendors JOIN users ON users.linked_id = vendors.id WHERE users.id = g.entity_id)
                        WHEN g.role = 's' THEN (SELECT name FROM security_staff JOIN users ON users.linked_id = security_staff.id WHERE users.id = g.entity_id)
                        ELSE CONCAT('Guest #', g.entity_id)
                    END AS entity_name
                FROM gate_access g
                WHERE g.id = %s
                """,
                (pk,),
                fetch_one=True
            )
        
        if entity == "account":
            return db._execute(
                """
                SELECT 
                    a.*,
                    COALESCE(parent.name, '—') AS parent_account_name,
                    COALESCE(
                        (SELECT SUM(
                            CASE 
                                WHEN a.drcr_account = 'Cr' THEN t.amount
                                ELSE -t.amount
                            END
                        )
                        FROM transactions t
                        WHERE t.acc_id = a.id AND t.status = 'paid'),
                        0
                    ) + a.bf_amount AS current_balance
                FROM accounts a
                LEFT JOIN accounts parent ON a.parent_account_id = parent.id
                WHERE a.id = %s
                """,
                (pk,),
                fetch_one=True
            )
        
    except Exception as e:
        print(f"❌ load_profile({entity}, {pk}) error: {e}")
        import traceback
        traceback.print_exc()
    
    return None


# ════════════════════════════════════════════════════════════════════════════
# CSV EXPORT
# ════════════════════════════════════════════════════════════════════════════

def export_csv(entity: str, filters: dict) -> str:
    rows, _ = load_list(entity, filters, page=1, page_size=10_000)
    if not rows:
        return "No data"
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys(), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        safe = {k: (v.isoformat() if isinstance(v, (datetime, date)) else v)
                for k, v in row.items()}
        writer.writerow(safe)
    return buf.getvalue()

# ═══════════════════════════════════════════════════════════════════════
# LIST LOADERS
# ════════════════════════════════════════════════════════════════════════════

def load_list(entity: str, filters: dict, page: int = 1,
              search: str = "", page_size: int = PAGE_SIZE) -> tuple:
    loaders = {
        "apartments": _list_apartments,
        "vendors":    _list_vendors,
        "security":   _list_security,
        "events":     _list_events,
        "concerns":   _list_concerns,
        "gate_logs":  _list_gate_logs,
        "receipts":   _list_receipts,
        "cashbook":   _list_cashbook,
        "societies":  _list_societies,
        "accounts":   _list_accounts,
        "expenses":   _list_receipts,   # reuse
    }
    fn = loaders.get(entity)
    if fn is None:
        return [], 0
    return fn(filters, page, search, page_size)

def _list_apartments(filters, page, search, page_size):
    """Enhanced: Shows maintenance breakdown instead of just pending amount."""
    sid = filters.get("society_id")
    if not sid: return [], 0
    offset = (page - 1) * page_size
    
    where, params = ["a.society_id=%s"], [sid]
    if filters.get("has_dues") is True:
        where.append("EXISTS(SELECT 1 FROM payments p WHERE p.apartment_id=a.id AND p.status='pending')")
    if filters.get("has_dues") is False:
        where.append("NOT EXISTS(SELECT 1 FROM payments p WHERE p.apartment_id=a.id AND p.status='pending')")
    if search:
        where.append("(a.flat_number ILIKE %s OR a.owner_name ILIKE %s)")
        params += [f"%{search}%", f"%{search}%"]
    
    ws = " AND ".join(where)
    
    count = db._execute(
        f"SELECT COUNT(*) AS c FROM apartments a WHERE {ws}", 
        params, fetch_one=True
    ) or {"c": 0}
    
    # ═══ ENHANCED: Calculate full maintenance breakdown ═══
    rows = db._execute(
        f"""
        WITH apartment_maintenance AS (
            SELECT 
                a.id,
                a.flat_number,
                a.owner_name,
                a.mobile,
                a.apartment_size,
                a.active,
                s.arrear_start_date,
                -- Calculate months from arrear start
                EXTRACT(YEAR FROM AGE(CURRENT_DATE, s.arrear_start_date)) * 12 + 
                EXTRACT(MONTH FROM AGE(CURRENT_DATE, s.arrear_start_date)) AS months_due,
                -- Default rate
                3.0 AS rate_per_sqft
            FROM apartments a
            JOIN societies s ON a.society_id = s.id
            WHERE {ws}
        ),
        payments_summary AS (
            SELECT 
                am.id,
                COALESCE(SUM(CASE WHEN p.status='verified' THEN p.amount ELSE 0 END), 0) AS paid,
                COALESCE(SUM(CASE WHEN p.status='pending' THEN p.amount ELSE 0 END), 0) AS pending
            FROM apartment_maintenance am
            LEFT JOIN payments p ON p.apartment_id = am.id
            GROUP BY am.id
        ),
        late_fees AS (
            SELECT 
                apartment_id,
                COALESCE(SUM(
                    CASE 
                        WHEN due_date < CURRENT_DATE 
                        THEN amount * 0.02 * EXTRACT(DAY FROM AGE(CURRENT_DATE, due_date)) / 30
                        ELSE 0 
                    END
                ), 0) AS late_fee
            FROM payments
            WHERE status = 'pending' AND due_date IS NOT NULL
            GROUP BY apartment_id
        )
        SELECT 
            am.id,
            am.flat_number,
            am.owner_name,
            am.mobile,
            am.apartment_size,
            am.active,
            am.months_due,
            -- Calculate total maintenance due
            am.apartment_size * am.rate_per_sqft * GREATEST(am.months_due, 0) AS total_maintenance,
            COALESCE(ps.paid, 0) AS paid_amount,
            COALESCE(ps.pending, 0) AS pending_amount,
            COALESCE(lf.late_fee, 0) AS late_fee,
            -- Grand total = (total_maintenance - paid) + late_fee
            (am.apartment_size * am.rate_per_sqft * GREATEST(am.months_due, 0) - COALESCE(ps.paid, 0)) + COALESCE(lf.late_fee, 0) AS grand_total
        FROM apartment_maintenance am
        LEFT JOIN payments_summary ps ON ps.id = am.id
        LEFT JOIN late_fees lf ON lf.apartment_id = am.id
        ORDER BY am.flat_number 
        LIMIT %s OFFSET %s
        """,
        params + [page_size, offset], 
        fetch_all=True
    ) or []
    
    return rows, int(count.get("c", 0))


def _list_vendors(filters, page, search, page_size):
    """Enhanced: Shows vendor business name and service details."""
    sid = filters.get("society_id")
    if not sid: return [], 0
    offset = (page - 1) * page_size
    
    where, params = ["u.society_id=%s", "u.role='vendor'"], [sid]
    if search:
        where.append("(v.name ILIKE %s OR v.service_type ILIKE %s OR u.email ILIKE %s)")
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]
    
    ws = " AND ".join(where)
    
    count = db._execute(
        f"SELECT COUNT(*) AS c FROM users u LEFT JOIN vendors v ON v.id=u.linked_id WHERE {ws}",
        params, fetch_one=True
    ) or {"c": 0}
    
    # ═══ ENHANCED: Show business name, service type, contact ═══
    rows = db._execute(
        f"""
        SELECT 
            u.id,
            u.email,
            COALESCE(v.name, u.email) AS business_name,
            COALESCE(v.service_type, '—') AS service_type,
            COALESCE(v.mobile, '—') AS mobile,
            COALESCE(v.active, TRUE) AS active,
            -- Calculate pending dues
            COALESCE(SUM(p.amount) FILTER (WHERE p.status='pending'), 0) AS pending_dues,
            -- Calculate paid amount
            COALESCE(SUM(p.amount) FILTER (WHERE p.status='verified'), 0) AS paid_amount
        FROM users u
        LEFT JOIN vendors v ON v.id=u.linked_id
        LEFT JOIN payments p ON p.user_id=u.id
        WHERE {ws}
        GROUP BY u.id, v.name, v.service_type, v.mobile, v.active
        ORDER BY business_name LIMIT %s OFFSET %s
        """,
        params + [page_size, offset], 
        fetch_all=True
    ) or []
    
    return rows, int(count.get("c", 0))


def _list_security(filters, page, search, page_size):
    """Enhanced: Shows salary calculation and attendance."""
    sid = filters.get("society_id")
    if not sid: return [], 0
    offset = (page - 1) * page_size
    
    where, params = ["u.society_id=%s", "u.role='security'"], [sid]
    if search:
        where.append("(s.name ILIKE %s OR u.email ILIKE %s)")
        params += [f"%{search}%", f"%{search}%"]
    
    ws = " AND ".join(where)
    
    count = db._execute(
        f"SELECT COUNT(*) AS c FROM users u LEFT JOIN security_staff s ON s.id=u.linked_id WHERE {ws}",
        params, fetch_one=True
    ) or {"c": 0}
    
    # ═══ ENHANCED: Calculate salary due ═══
    rows = db._execute(
        f"""
        SELECT 
            u.id,
            u.email,
            COALESCE(s.name, u.email) AS name,
            COALESCE(s.shift, '—') AS shift,
            COALESCE(s.mobile, '—') AS mobile,
            COALESCE(s.active, TRUE) AS active,
            s.salary_per_shift,
            s.joining_date,
            -- Calculate days worked
            EXTRACT(DAY FROM AGE(CURRENT_DATE, COALESCE(s.joining_date, CURRENT_DATE))) AS days_worked,
            -- Total salary due
            s.salary_per_shift * EXTRACT(DAY FROM AGE(CURRENT_DATE, COALESCE(s.joining_date, CURRENT_DATE))) AS salary_due,
            -- Already paid
            COALESCE(SUM(p.amount) FILTER (WHERE p.status='verified' AND p.payment_type='salary'), 0) AS salary_paid,
            -- Pending salary
            (s.salary_per_shift * EXTRACT(DAY FROM AGE(CURRENT_DATE, COALESCE(s.joining_date, CURRENT_DATE)))) - 
            COALESCE(SUM(p.amount) FILTER (WHERE p.status='verified' AND p.payment_type='salary'), 0) AS salary_pending
        FROM users u
        LEFT JOIN security_staff s ON s.id=u.linked_id
        LEFT JOIN payments p ON p.user_id=u.id
        WHERE {ws}
        GROUP BY u.id, s.name, s.shift, s.mobile, s.active, s.salary_per_shift, s.joining_date
        ORDER BY name LIMIT %s OFFSET %s
        """,
        params + [page_size, offset], 
        fetch_all=True
    ) or []
    
    return rows, int(count.get("c", 0))


def _list_receipts(filters, page, search, page_size):
    """Enhanced: Shows account name and entity details instead of IDs."""
    sid = filters.get("society_id")
    if not sid: return [], 0
    offset = (page - 1) * page_size
    
    params = [sid]
    extra = ""
    if search:
        extra = "AND (acc.name ILIKE %s OR t.acc_particulars ILIKE %s)"
        params += [f"%{search}%", f"%{search}%"]
    
    count = db._execute(
        f"""
        SELECT COUNT(*) AS c 
        FROM transactions t
        JOIN accounts acc ON t.acc_id = acc.id
        WHERE t.society_id=%s 
          AND t.status='paid' 
          AND acc.drcr_account='Cr' 
          {extra}
        """,
        params, fetch_one=True
    ) or {"c": 0}
    
    # ═══ ENHANCED: Show account name, entity details ═══
    rows = db._execute(
        f"""
        SELECT 
            t.id,
            t.trx_date,
            acc.name AS account_name,
            acc.tab_name AS account_group,
            -- Show entity name (apartment/vendor)
            CASE 
                WHEN a.id IS NOT NULL THEN CONCAT('Flat ', a.flat_number, ' (', a.owner_name, ')')
                WHEN v.id IS NOT NULL THEN v.name
                ELSE '—'
            END AS entity_name,
            t.acc_particulars,
            t.amount,
            t.mode,
            t.status
        FROM transactions t
        JOIN accounts acc ON t.acc_id = acc.id
        LEFT JOIN apartments a ON t.entity_id = a.id
        LEFT JOIN vendors v ON t.entity_id IN (
            SELECT linked_id FROM users WHERE role='vendor' AND linked_id IS NOT NULL
        )
        WHERE t.society_id=%s 
          AND t.status='paid' 
          AND acc.drcr_account='Cr'
          {extra}
        ORDER BY t.trx_date DESC 
        LIMIT %s OFFSET %s
        """,
        params + [page_size, offset], 
        fetch_all=True
    ) or []
    
    return rows, int(count.get("c", 0))


def _list_cashbook(filters, page, search, page_size):
    """Enhanced: Full cashbook with running balance and account names."""
    sid = filters.get("society_id")
    if not sid: return [], 0
    offset = (page - 1) * page_size
    
    params = [sid]
    extra = ""
    if search:
        extra = "AND (acc.name ILIKE %s OR t.acc_particulars ILIKE %s)"
        params += [f"%{search}%", f"%{search}%"]
    
    count = db._execute(
        f"SELECT COUNT(*) AS c FROM transactions t JOIN accounts acc ON t.acc_id = acc.id WHERE t.society_id=%s {extra}",
        params, fetch_one=True
    ) or {"c": 0}
    
    # ═══ ENHANCED: Full cashbook with running balance ═══
    rows = db._execute(
        f"""
        WITH all_transactions AS (
            SELECT 
                t.id,
                t.trx_date,
                acc.name AS account_name,
                acc.tab_name AS account_group,
                acc.drcr_account,
                t.acc_particulars,
                t.amount,
                t.mode
            FROM transactions t
            JOIN accounts acc ON t.acc_id = acc.id
            WHERE t.society_id=%s 
              AND t.status='paid'
              {extra}
            ORDER BY t.trx_date DESC, t.id DESC
        )
        SELECT 
            id,
            trx_date,
            account_name,
            account_group,
            acc_particulars,
            CASE WHEN drcr_account='Dr' THEN amount ELSE NULL END AS debit,
            CASE WHEN drcr_account='Cr' THEN amount ELSE NULL END AS credit,
            mode,
            drcr_account
        FROM all_transactions
        LIMIT %s OFFSET %s
        """,
        params + [page_size, offset], 
        fetch_all=True
    ) or []
    
    # Calculate running balance
    if rows:
        # Get opening balance from accounts
        opening = db._execute(
            """
            SELECT COALESCE(SUM(
                CASE 
                    WHEN drcr_bf = 'Cr' THEN bf_amount
                    ELSE -bf_amount
                END
            ), 0) AS balance
            FROM accounts
            WHERE society_id = %s
            """,
            (sid,),
            fetch_one=True
        )
        
        balance = float(opening.get('balance', 0)) if opening else 0.0
        
        # Add balance column
        for row in reversed(rows):
            if row.get('credit'):
                balance += float(row['credit'])
            if row.get('debit'):
                balance -= float(row['debit'])
            row['balance'] = round(balance, 2)
        
        rows.reverse()
    
    return rows, int(count.get("c", 0))


def _list_events(filters, page, search, page_size):
    """No changes needed - already showing full data."""
    sid = filters.get("society_id")
    if not sid: return [], 0
    offset = (page - 1) * page_size
    
    where, params = ["society_id=%s"], [sid]
    if search:
        where.append("title ILIKE %s")
        params.append(f"%{search}%")
    
    ws = " AND ".join(where)
    count = db._execute(f"SELECT COUNT(*) AS c FROM events WHERE {ws}", params, fetch_one=True) or {"c": 0}
    rows = db._execute(
        f"SELECT id,event_date,title,venue,open_to,created_at FROM events WHERE {ws} ORDER BY event_date DESC LIMIT %s OFFSET %s",
        params + [page_size, offset], fetch_all=True
    ) or []
    
    return rows, int(count.get("c", 0))


def _list_concerns(filters, page, search, page_size):
    """No changes needed - already showing full data."""
    sid = filters.get("society_id")
    if not sid: return [], 0
    offset = (page - 1) * page_size
    
    where, params = ["society_id=%s"], [sid]
    if search:
        where.append("(flat_no ILIKE %s OR description ILIKE %s)")
        params += [f"%{search}%", f"%{search}%"]
    
    ws = " AND ".join(where)
    count = db._execute(f"SELECT COUNT(*) AS c FROM concerns WHERE {ws}", params, fetch_one=True) or {"c": 0}
    rows = db._execute(
        f"SELECT id,flat_no,concern_type,description,status,assigned_to,created_at FROM concerns WHERE {ws} ORDER BY created_at DESC LIMIT %s OFFSET %s",
        params + [page_size, offset], fetch_all=True
    ) or []
    
    return rows, int(count.get("c", 0))


def _list_gate_logs(filters, page, search, page_size):
    """Enhanced: Shows entity name instead of just ID."""
    sid = filters.get("society_id")
    if not sid: return [], 0
    offset = (page - 1) * page_size
    
    params = [sid]
    extra = ""
    if search:
        extra = "AND entity_id::text ILIKE %s"
        params.append(f"%{search}%")
    
    count = db._execute(
        f"SELECT COUNT(*) AS c FROM gate_access WHERE society_id=%s {extra}",
        params, fetch_one=True
    ) or {"c": 0}
    
    # ═══ ENHANCED: Show entity name based on role ═══
    rows = db._execute(
        f"""
        SELECT 
            g.id,
            g.role,
            g.entity_id,
            g.time_in,
            g.time_out,
            -- Show entity name
            CASE 
                WHEN g.role = 'a' THEN (
                    SELECT CONCAT('Flat ', a.flat_number, ' (', a.owner_name, ')')
                    FROM apartments a WHERE a.id = g.entity_id
                )
                WHEN g.role = 'v' THEN (
                    SELECT v.name 
                    FROM vendors v 
                    JOIN users u ON u.linked_id = v.id 
                    WHERE u.id = g.entity_id
                )
                WHEN g.role = 's' THEN (
                    SELECT s.name 
                    FROM security_staff s 
                    JOIN users u ON u.linked_id = s.id 
                    WHERE u.id = g.entity_id
                )
                ELSE CONCAT('Guest #', g.entity_id)
            END AS entity_name,
            -- Calculate duration
            EXTRACT(EPOCH FROM (COALESCE(g.time_out, NOW()) - g.time_in))/3600 AS hours
        FROM gate_access g
        WHERE g.society_id=%s {extra}
        ORDER BY g.time_in DESC 
        LIMIT %s OFFSET %s
        """,
        params + [page_size, offset], 
        fetch_all=True
    ) or []
    
    return rows, int(count.get("c", 0))


def _list_societies(filters, page, search, page_size):
    """Enhanced: Shows plan status and admin count."""
    offset = (page - 1) * page_size
    params = []
    extra = ""
    
    if filters.get("plan"):
        extra = "WHERE plan=%s"
        params.append(filters["plan"])
    
    if search:
        extra += " AND " if extra else "WHERE "
        extra += "name ILIKE %s"
        params.append(f"%{search}%")
    
    count = db._execute(f"SELECT COUNT(*) AS c FROM societies {extra}", params, fetch_one=True) or {"c": 0}
    
    # ═══ ENHANCED: Show plan status and user counts ═══
    rows = db._execute(
        f"""
        SELECT 
            s.id,
            s.name,
            s.email,
            s.phone,
            s.plan,
            s.plan_validity,
            CASE 
                WHEN s.plan = 'Free' THEN 'Free'
                WHEN s.plan_validity >= CURRENT_DATE THEN 'Active'
                ELSE 'Expired'
            END AS plan_status,
            s.created_at,
            -- Count users
            (SELECT COUNT(*) FROM users WHERE society_id = s.id) AS total_users,
            -- Count apartments
            (SELECT COUNT(*) FROM apartments WHERE society_id = s.id AND active = TRUE) AS total_apartments
        FROM societies s
        {extra}
        ORDER BY s.name 
        LIMIT %s OFFSET %s
        """,
        params + [page_size, offset], 
        fetch_all=True
    ) or []
    
    return rows, int(count.get("c", 0))


def _list_accounts(filters, page, search, page_size):
    """Enhanced: Shows parent account name instead of ID."""
    sid = filters.get("society_id")
    if not sid: return [], 0
    offset = (page - 1) * page_size
    
    params = [sid]
    extra = ""
    if search:
        extra = "AND (a.name ILIKE %s OR a.tab_name ILIKE %s)"
        params += [f"%{search}%", f"%{search}%"]
    
    count = db._execute(
        f"SELECT COUNT(*) AS c FROM accounts a WHERE a.society_id=%s {extra}",
        params, fetch_one=True
    ) or {"c": 0}
    
    # ═══ ENHANCED: Show parent account name ═══
    rows = db._execute(
        f"""
        SELECT 
            a.id,
            a.name,
            a.tab_name,
            a.header,
            a.drcr_account,
            a.bf_amount,
            -- Show parent account name
            COALESCE(parent.name, '—') AS parent_account_name,
            -- Calculate current balance from transactions
            COALESCE(
                (SELECT SUM(
                    CASE 
                        WHEN a.drcr_account = 'Cr' THEN t.amount
                        ELSE -t.amount
                    END
                )
                FROM transactions t
                WHERE t.acc_id = a.id AND t.status = 'paid'),
                0
            ) + a.bf_amount AS current_balance
        FROM accounts a
        LEFT JOIN accounts parent ON a.parent_account_id = parent.id
        WHERE a.society_id=%s {extra}
        ORDER BY a.name 
        LIMIT %s OFFSET %s
        """,
        params + [page_size, offset], 
        fetch_all=True
    ) or []
    
    return rows, int(count.get("c", 0))


