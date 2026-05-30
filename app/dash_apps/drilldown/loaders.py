# app/dash_apps/drilldown/loaders.py
"""
THIN LOADERS - Just database queries, no business logic
All calculations done in PostgreSQL functions
"""

from __future__ import annotations
from database.db_manager import db
from app.models import (
    dict_to_apartment, dict_to_vendor, dict_to_security, dict_to_society,
    dict_to_account, dict_to_event, dict_to_concern, dict_to_transaction,
    dict_to_receivable, Apartment, Vendor, SecurityStaff, Society, Account,
    Event, Concern, Transaction, Receivable
)

PAGE_SIZE = 15

# ════════════════════════════════════════════════════════════════════════════
# GENERIC DISPATCHERS - Work with any entity
# ════════════════════════════════════════════════════════════════════════════

def load_list(entity: str, filters: dict, page: int = 1, search: str = "", page_size: int = PAGE_SIZE) -> tuple[list, int]:
    """Generic list loader that dispatches to entity-specific loaders."""
    society_id = filters.get("society_id")
    
    loaders_map = {
        "apartments": load_apartments_list,
        "vendors": load_vendors_list,
        "security": load_security_list,
        "events": load_events_list,
        "concerns": load_concerns_list,
        "accounts": load_accounts_list,
        "societies": load_societies_list,
        "cashbook": load_cashbook_list,
        "receivables": load_receivables_list,
    }
    
    loader = loaders_map.get(entity)
    if not loader:
        print(f"❌ No loader for entity: {entity}")
        return [], 0
    
    # Call the specific loader with appropriate params
    if entity == "societies":
        return loader(search, filters.get("plan"), page, page_size)
    elif entity in ("cashbook", "receivables"):
        status = filters.get("status", "pending")
        return loader(society_id, search, status, page, page_size)
    elif entity == "concerns":
        status = filters.get("status", "open")
        return loader(society_id, search, status, page, page_size)
    else:
        return loader(society_id, search, page, page_size)


def load_profile(entity: str, pk: any, society_id: int):
    """Generic profile loader that dispatches to entity-specific loaders."""
    loaders_map = {
        "apartment": load_apartment_profile,
        "vendor": load_vendor_profile,
        "security": load_security_profile,
        "event": load_event_profile,
        "concern": load_concern_profile,
        "account": load_account_profile,
        "society": load_society_profile,
        "transaction": lambda x: load_cashbook_profile(x),
        "receivable": load_receivable_profile,
    }
    
    loader = loaders_map.get(entity)
    if not loader:
        print(f"❌ No profile loader for entity: {entity}")
        return None
    
    return loader(pk)


def delete_entity(entity: str, pk: any, society_id: int) -> tuple[bool, str]:
    """Generic delete that uses SQL directly."""
    table_map = {
        "apartment": "apartments",
        "vendor": "vendors",
        "security": "security_staff",
        "event": "events",
        "concern": "concerns",
        "account": "accounts",
    }
    
    table = table_map.get(entity)
    if not table:
        return False, f"Cannot delete {entity}"
    
    try:
        db._execute(
            f"DELETE FROM {table} WHERE id = %s AND society_id = %s",
            (pk, society_id)
        )
        return True, f"{entity.title()} deleted"
    except Exception as e:
        return False, str(e)


def export_csv(entity: str, society_id: int) -> str:
    """Export entity list as CSV"""
    return export_list_as_csv(entity, society_id)

# ════════════════════════════════════════════════════════════════════════════
# SQL INTROSPECTION - For Customize Tab
# ════════════════════════════════════════════════════════════════════════════

def get_function_sql(function_name: str) -> str:
    """Get SQL definition of a PostgreSQL function"""
    try:
        row = db._execute(
            "SELECT get_function_sql(%s) as sql",
            (function_name,),
            fetch_one=True
        )
        return row['sql'] if row else "Function not found"
    except Exception as e:
        return f"Error: {str(e)}"


def get_kpi_functions() -> list[dict]:
    """Get all KPI functions with their definitions"""
    try:
        rows = db._execute(
            "SELECT * FROM get_kpi_functions()",
            fetch_all=True
        ) or []
        return rows
    except Exception as e:
        print(f"❌ Error fetching KPI functions: {e}")
        return []


def get_portal_kpis(portal: str = None) -> list[dict]:
    """Get all KPIs for a portal with their metadata"""
    try:
        if portal:
            rows = db._execute(
                "SELECT * FROM get_portal_kpis(%s)",
                (portal,),
                fetch_all=True
            ) or []
        else:
            rows = db._execute(
                "SELECT * FROM get_portal_kpis()",
                fetch_all=True
            ) or []
        return rows
    except Exception as e:
        print(f"❌ Error fetching portal KPIs: {e}")
        return []

# ════════════════════════════════════════════════════════════════════════════
# APARTMENTS
# ════════════════════════════════════════════════════════════════════════════

def load_apartments_list(
    society_id: int,
    search: str = "",
    has_dues: bool = None,
    page: int = 1,
    page_size: int = PAGE_SIZE
) -> tuple[list[Apartment], int]:
    """Load apartment list using SQL function"""
    offset = (page - 1) * page_size
    
    rows = db._execute(
        "SELECT * FROM fn_apartments_list(%s, %s) LIMIT %s OFFSET %s",
        (society_id, search if search else None, page_size, offset),
        fetch_all=True
    ) or []
    
    # Filter by has_dues if specified
    if has_dues is not None:
        rows = [r for r in rows if (has_dues and r['grand_total'] > 0) or 
                (not has_dues and r['grand_total'] == 0)]
    
    # Get total count
    count_row = db._execute(
        "SELECT COUNT(*) as cnt FROM fn_apartments_list(%s, %s)",
        (society_id, search if search else None),
        fetch_one=True
    )
    total = count_row['cnt'] if count_row else 0
    
    apartments = [dict_to_apartment(r) for r in rows]
    return apartments, total

def load_apartment_profile(apartment_id: int) -> Apartment | None:
    """Load apartment profile"""
    row = db._execute(
        "SELECT * FROM apartments WHERE id = %s",
        (apartment_id,),
        fetch_one=True
    )
    return dict_to_apartment(row) if row else None

# ════════════════════════════════════════════════════════════════════════════
# VENDORS
# ════════════════════════════════════════════════════════════════════════════

def load_vendors_list(
    society_id: int,
    search: str = "",
    page: int = 1,
    page_size: int = PAGE_SIZE
) -> tuple[list[Vendor], int]:
    """Load vendor list using SQL function"""
    offset = (page - 1) * page_size
    
    rows = db._execute(
        "SELECT * FROM fn_vendors_list(%s, %s) LIMIT %s OFFSET %s",
        (society_id, search if search else None, page_size, offset),
        fetch_all=True
    ) or []
    
    count_row = db._execute(
        "SELECT COUNT(*) as cnt FROM fn_vendors_list(%s, %s)",
        (society_id, search if search else None),
        fetch_one=True
    )
    total = count_row['cnt'] if count_row else 0
    
    vendors = [dict_to_vendor(r) for r in rows]
    return vendors, total

def load_vendor_profile(vendor_id: int) -> Vendor | None:
    """Load vendor profile"""
    row = db._execute(
        """SELECT u.id, u.email, u.society_id, v.name, v.logo, v.license,
                  v.photo, v.service_type, v.mobile, v.service_description,
                  v.active, v.created_at
           FROM users u
           LEFT JOIN vendors v ON v.id = u.linked_id
           WHERE u.id = %s AND u.role = 'vendor'""",
        (vendor_id,),
        fetch_one=True
    )
    return dict_to_vendor(row) if row else None

# ════════════════════════════════════════════════════════════════════════════
# SECURITY STAFF
# ════════════════════════════════════════════════════════════════════════════

def load_security_list(
    society_id: int,
    search: str = "",
    page: int = 1,
    page_size: int = PAGE_SIZE
) -> tuple[list[SecurityStaff], int]:
    """Load security staff list using SQL function"""
    offset = (page - 1) * page_size
    
    rows = db._execute(
        "SELECT * FROM fn_security_list(%s, %s) LIMIT %s OFFSET %s",
        (society_id, search if search else None, page_size, offset),
        fetch_all=True
    ) or []
    
    count_row = db._execute(
        "SELECT COUNT(*) as cnt FROM fn_security_list(%s, %s)",
        (society_id, search if search else None),
        fetch_one=True
    )
    total = count_row['cnt'] if count_row else 0
    
    security = [dict_to_security(r) for r in rows]
    return security, total

def load_security_profile(security_id: int) -> SecurityStaff | None:
    """Load security profile"""
    row = db._execute(
        """SELECT u.id, u.email, u.society_id, s.name, s.photo, s.id_proof,
                  s.mobile, s.joining_date, s.shift, s.salary_per_shift, s.active,
                  s.created_at
           FROM users u
           LEFT JOIN security_staff s ON s.id = u.linked_id
           WHERE u.id = %s AND u.role = 'security'""",
        (security_id,),
        fetch_one=True
    )
    return dict_to_security(row) if row else None

# ════════════════════════════════════════════════════════════════════════════
# SOCIETIES
# ════════════════════════════════════════════════════════════════════════════

def load_societies_list(
    search: str = "",
    plan: str = None,
    page: int = 1,
    page_size: int = PAGE_SIZE
) -> tuple[list[Society], int]:
    """Load societies list"""
    offset = (page - 1) * page_size
    
    rows = db._execute(
        "SELECT * FROM fn_societies_list(%s, %s) LIMIT %s OFFSET %s",
        (search if search else None, plan, page_size, offset),
        fetch_all=True
    ) or []
    
    count_row = db._execute(
        "SELECT COUNT(*) as cnt FROM fn_societies_list(%s, %s)",
        (search if search else None, plan),
        fetch_one=True
    )
    total = count_row['cnt'] if count_row else 0
    
    societies = [dict_to_society(r) for r in rows]
    return societies, total

def load_society_profile(society_id: int) -> Society | None:
    """Load society profile"""
    row = db._execute(
        "SELECT * FROM fn_society_profile(%s)",
        (society_id,),
        fetch_one=True
    )
    return dict_to_society(row) if row else None

# ════════════════════════════════════════════════════════════════════════════
# ACCOUNTS
# ════════════════════════════════════════════════════════════════════════════

def load_accounts_list(
    society_id: int,
    search: str = "",
    tab_name: str = None,
    page: int = 1,
    page_size: int = PAGE_SIZE
) -> tuple[list[Account], int]:
    """Load accounts list"""
    offset = (page - 1) * page_size
    
    rows = db._execute(
        "SELECT * FROM fn_accounts_list(%s, %s, %s) LIMIT %s OFFSET %s",
        (society_id, search if search else None, tab_name, page_size, offset),
        fetch_all=True
    ) or []
    
    count_row = db._execute(
        "SELECT COUNT(*) as cnt FROM fn_accounts_list(%s, %s, %s)",
        (society_id, search if search else None, tab_name),
        fetch_one=True
    )
    total = count_row['cnt'] if count_row else 0
    
    accounts = [dict_to_account(r) for r in rows]
    return accounts, total

def load_account_profile(account_id: int) -> Account | None:
    """Load account profile"""
    row = db._execute(
        "SELECT * FROM fn_account_profile(%s)",
        (account_id,),
        fetch_one=True
    )
    return dict_to_account(row) if row else None

# ════════════════════════════════════════════════════════════════════════════
# EVENTS
# ════════════════════════════════════════════════════════════════════════════

def load_events_list(
    society_id: int,
    search: str = "",
    page: int = 1,
    page_size: int = PAGE_SIZE
) -> tuple[list[Event], int]:
    """Load events list"""
    offset = (page - 1) * page_size
    
    rows = db._execute(
        "SELECT * FROM fn_events_list(%s, %s) LIMIT %s OFFSET %s",
        (society_id, search if search else None, page_size, offset),
        fetch_all=True
    ) or []
    
    count_row = db._execute(
        "SELECT COUNT(*) as cnt FROM fn_events_list(%s, %s)",
        (society_id, search if search else None),
        fetch_one=True
    )
    total = count_row['cnt'] if count_row else 0
    
    events = [dict_to_event(r) for r in rows]
    return events, total

def load_event_profile(event_id: int) -> Event | None:
    """Load event profile"""
    row = db._execute(
        "SELECT * FROM fn_event_profile(%s)",
        (event_id,),
        fetch_one=True
    )
    return dict_to_event(row) if row else None

# ════════════════════════════════════════════════════════════════════════════
# CONCERNS
# ════════════════════════════════════════════════════════════════════════════

def load_concerns_list(
    society_id: int,
    search: str = "",
    status: str = "open",
    page: int = 1,
    page_size: int = PAGE_SIZE
) -> tuple[list[Concern], int]:
    """Load concerns list"""
    offset = (page - 1) * page_size
    
    rows = db._execute(
        "SELECT * FROM fn_concerns_list(%s, %s, %s) LIMIT %s OFFSET %s",
        (society_id, search if search else None, status, page_size, offset),
        fetch_all=True
    ) or []
    
    count_row = db._execute(
        "SELECT COUNT(*) as cnt FROM fn_concerns_list(%s, %s, %s)",
        (society_id, search if search else None, status),
        fetch_one=True
    )
    total = count_row['cnt'] if count_row else 0
    
    concerns = [dict_to_concern(r) for r in rows]
    return concerns, total

def load_concern_profile(concern_id: int) -> Concern | None:
    """Load concern profile"""
    row = db._execute(
        "SELECT * FROM fn_concern_profile(%s)",
        (concern_id,),
        fetch_one=True
    )
    return dict_to_concern(row) if row else None

# ════════════════════════════════════════════════════════════════════════════
# RECEIVABLES
# ════════════════════════════════════════════════════════════════════════════

def load_receivables_list(
    society_id: int,
    search: str = "",
    status: str = "pending",
    page: int = 1,
    page_size: int = PAGE_SIZE
) -> tuple[list[Receivable], int]:
    """Load receivables list"""
    offset = (page - 1) * page_size
    
    rows = db._execute(
        "SELECT * FROM fn_receivables_list(%s, %s, %s) LIMIT %s OFFSET %s",
        (society_id, search if search else None, status, page_size, offset),
        fetch_all=True
    ) or []
    
    count_row = db._execute(
        "SELECT COUNT(*) as cnt FROM fn_receivables_list(%s, %s, %s)",
        (society_id, search if search else None, status),
        fetch_one=True
    )
    total = count_row['cnt'] if count_row else 0
    
    receivables = [dict_to_receivable(r) for r in rows]
    return receivables, total

def load_receivable_profile(receivable_id: int) -> Receivable | None:
    """Load receivable profile"""
    row = db._execute(
        "SELECT * FROM fn_receivable_profile(%s)",
        (receivable_id,),
        fetch_one=True
    )
    return dict_to_receivable(row) if row else None

# ════════════════════════════════════════════════════════════════════════════
# CASHBOOK
# ════════════════════════════════════════════════════════════════════════════

def load_cashbook_list(
    society_id: int,
    search: str = "",
    start_date = None,
    end_date = None,
    page: int = 1,
    page_size: int = PAGE_SIZE
) -> tuple[list[Transaction], int]:
    """Load cashbook transactions"""
    offset = (page - 1) * page_size
    
    rows = db._execute(
        "SELECT * FROM fn_cashbook_list(%s, %s, %s, %s) LIMIT %s OFFSET %s",
        (society_id, search if search else None, start_date, end_date, page_size, offset),
        fetch_all=True
    ) or []
    
    count_row = db._execute(
        "SELECT COUNT(*) as cnt FROM fn_cashbook_list(%s, %s, %s, %s)",
        (society_id, search if search else None, start_date, end_date),
        fetch_one=True
    )
    total = count_row['cnt'] if count_row else 0
    
    transactions = [dict_to_transaction(r) for r in rows]
    return transactions, total

def load_cashbook_profile(transaction_id: int) -> Transaction | None:
    """Load transaction profile"""
    row = db._execute(
        "SELECT * FROM fn_cashbook_profile(%s)",
        (transaction_id,),
        fetch_one=True
    )
    return dict_to_transaction(row) if row else None

# ════════════════════════════════════════════════════════════════════════════
# CSV EXPORT
# ════════════════════════════════════════════════════════════════════════════

def export_list_as_csv(entity: str, society_id: int) -> str:
    """Export list as CSV"""
    import csv
    import io
    
    loaders = {
        "apartments": lambda: load_apartments_list(society_id, page_size=10000)[0],
        "vendors": lambda: load_vendors_list(society_id, page_size=10000)[0],
        "security": lambda: load_security_list(society_id, page_size=10000)[0],
        "events": lambda: load_events_list(society_id, page_size=10000)[0],
        "concerns": lambda: load_concerns_list(society_id, page_size=10000)[0],
        "accounts": lambda: load_accounts_list(society_id, page_size=10000)[0],
    }
    
    loader = loaders.get(entity)
    if not loader:
        return "No data"
    
    rows = loader()
    if not rows:
        return "No records found"
    
    buf = io.StringIO()
    first_row = rows[0].to_dict(include_calculated=True)
    writer = csv.DictWriter(buf, fieldnames=first_row.keys())
    writer.writeheader()
    for row in rows:
        writer.writerow(row.to_dict(include_calculated=True))
    
    return buf.getvalue()
