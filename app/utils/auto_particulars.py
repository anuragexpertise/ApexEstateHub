"""
auto_particulars.py — Auto-generate receipt/expense descriptions.

Generates human-readable particulars based on account type and context:
  - SocM → "Maintenance Apr-2026"
  - SellAs → "<asset_name> <asset_sno>"
  - Vendor pass → "<pass_type>"
  - events → "<event_title> <count> <ticket_name> + <count2> <ticket_name2>"
  - default → "<account_name>"
"""

from __future__ import annotations
from datetime import date
from database.db_manager import db

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def generate_particulars(acc_id: int, entity_id: int | None, role: str,
                         society_id: int, mode: str = "cash") -> str:
    """Generate a descriptive particular string for a receipt/expense."""
    if not acc_id:
        return ""

    acc = _get_account(acc_id, society_id)
    if not acc:
        return ""

    tab = acc.get("tab_name", "")
    acc_name = acc.get("name", "")

    if tab == "SocM":
        # "Maintenance Apr-2026"
        today = date.today()
        return f"Maintenance {MONTHS[today.month - 1]}-{today.year}"

    if tab == "SellAs":
        # "Sell <asset_name>"
        if entity_id:
            asset = _get_asset(entity_id, society_id)
            if asset:
                return f"Sell {asset.get('asset_name', '')}".strip()
        return f"Sale - {acc_name}"

    if tab == "EventT" or tab in ("Holi", "Diwali"):
        # "<event_title> <count> <ticket_name> + <count2> <ticket_name2>"
        if entity_id:
            event = _get_event(entity_id, society_id)
            if event:
                title = event.get("title", "Event")
                t1 = event.get("ticket_name", "Adult")
                t2 = event.get("ticket_name2", "Child")
                p1 = event.get("ticket_price", 0)
                p2 = event.get("ticket_price2", 0)
                parts = [title]
                if p1:
                    parts.append(f"1 {t1}")
                if p2:
                    parts.append(f"1 {t2}")
                return " + ".join(parts) if len(parts) > 1 else f"{title} - {t1}"
        return acc_name

    if mode in ("cheque",):
        return f"{acc_name} (Cheque)"

    # Default: "<account_name>"
    return acc_name


def generate_expense_particulars(acc_id: int, entity_id: int | None, role: str,
                                 society_id: int) -> str:
    """Generate a descriptive particular for an expense."""
    if not acc_id:
        return ""

    acc = _get_account(acc_id, society_id)
    if not acc:
        return ""

    tab = acc.get("tab_name", "")
    acc_name = acc.get("name", "")

    if tab == "Salary":
        today = date.today()
        entity_name = _get_entity_name(role, entity_id, society_id)
        prefix = f"{entity_name} - " if entity_name else ""
        return f"{prefix}Salary {MONTHS[today.month - 1]}-{today.year}"

    if tab in ("Elec", "WTax", "HTax", "Water"):
        today = date.today()
        return f"{acc_name} {MONTHS[today.month - 1]}-{today.year}"

    if tab in ("RM", "Repairs"):
        entity_name = _get_entity_name(role, entity_id, society_id)
        if entity_name:
            return f"{acc_name} - {entity_name}"
        return acc_name

    # Default
    return acc_name


def get_pending_balance(entity_id: int | None, role: str, society_id: int) -> float:
    """Get the outstanding balance for an entity."""
    if not entity_id:
        return 0.0
    try:
        row = db._execute(
            """SELECT COALESCE(SUM(amount - paid_amount), 0) AS balance
               FROM receivables
               WHERE society_id=%s AND entity_id=%s AND role=%s
                 AND status IN ('pending', 'partial')""",
            (society_id, entity_id, role), fetch_one=True,
        )
        return float(row.get("balance", 0)) if row else 0.0
    except Exception as e:
        print(f"⚠️ get_pending_balance: {e}")
        return 0.0


def get_entity_summary(entity_id: int | None, role: str, society_id: int) -> str:
    """Get a short summary of an entity for display."""
    return _get_entity_name(role, entity_id, society_id)


def _get_account(account_id: int, society_id: int) -> dict | None:
    try:
        return db._execute(
            "SELECT id, name, tab_name, header FROM accounts WHERE id=%s AND society_id=%s",
            (account_id, society_id), fetch_one=True,
        )
    except Exception:
        return None


def _get_asset(asset_id: int, society_id: int) -> dict | None:
    try:
        return db._execute(
            "SELECT asset_name, asset_SNo FROM assets WHERE id=%s AND society_id=%s",
            (asset_id, society_id), fetch_one=True,
        )
    except Exception:
        return None


def _get_event(event_id: int, society_id: int) -> dict | None:
    try:
        return db._execute(
            """SELECT title, ticket_name, ticket_price, ticket_name2, ticket_price2
               FROM events WHERE id=%s AND society_id=%s""",
            (event_id, society_id), fetch_one=True,
        )
    except Exception:
        return None


def _get_entity_name(role: str, entity_id: int | None, society_id: int) -> str:
    """Resolve entity display name by role."""
    if not entity_id:
        return ""
    table_map = {
        "apartment": ("apartments", "owner_name", "flat_number"),
        "vendor": ("vendors", "business_name", "name"),
        "security": ("security_staff", "name", None),
        "assets": ("assets", "asset_name", None),
    }
    info = table_map.get(role)
    if not info:
        return ""
    table, label_col, fallback_col = info
    try:
        row = db._execute(
            f"SELECT {label_col}, {fallback_col or label_col} FROM {table} WHERE id=%s AND society_id=%s",
            (entity_id, society_id), fetch_one=True,
        )
        if not row:
            return ""
        val = row.get(label_col) or (row.get(fallback_col) if fallback_col else None) or ""
        # For apartments, include flat number
        if table == "apartments":
            flat = row.get("flat_number") or ""
            return f"{flat} - {val}" if flat else str(val)
        return str(val)
    except Exception:
        return ""
