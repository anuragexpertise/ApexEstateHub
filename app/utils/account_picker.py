"""
account_picker.py — Searchable account hierarchy picker for Receipts/Expenses.

Provides a grouped, searchable picker for the chart of accounts that
respects the account hierarchy (tab_name -> header -> account name).
"""

from __future__ import annotations
from database.db_manager import db


def list_account_hierarchy(society_id: int, search: str | None = None) -> list[dict]:
    """Return accounts grouped by tab_name and header for the picker.

    Returns a flat list of dicts with level markers for rendering:
      level=1 → tab group header (e.g., "Income", "Expenses")
      level=2 → header subgroup (e.g., "Society Maintenance Charge")
      level=3 → actual account (selectable)
    """
    try:
        rows = db._execute(
            """SELECT id, name, tab_name, header, parent_account_id,
                      drcr_account, has_bf
               FROM accounts
               WHERE society_id = %s
               ORDER BY tab_name NULLS LAST, header NULLS LAST, name""",
            (society_id,), fetch_all=True,
        ) or []
    except Exception as e:
        print(f"⚠️ list_account_hierarchy: {e}")
        return []

    if search:
        s = search.strip().lower()
        rows = [r for r in rows if s in str(r.get("name", "")).lower()
                or s in str(r.get("header", "")).lower()
                or s in str(r.get("tab_name", "")).lower()]

    # Build hierarchy
    result = []
    tabs: dict[str, dict] = {}

    for r in rows:
        tab = r.get("tab_name") or "Other"
        header = r.get("header") or "General"
        parent_id = r.get("parent_account_id")

        # Skip header/parent accounts (those that are parents of others)
        is_parent = any(r2.get("parent_account_id") == r.get("id") for r2 in rows)

        if tab not in tabs:
            tabs[tab] = {"headers": {}, "accounts": []}
            result.append({
                "level": 1,
                "type": "tab",
                "key": tab,
                "label": _TAB_LABELS.get(tab, tab),
                "count": 0,
            })

        if header not in tabs[tab]["headers"]:
            tabs[tab]["headers"][header] = []
            result.append({
                "level": 2,
                "type": "header",
                "key": f"{tab}.{header}",
                "label": header,
                "tab": tab,
            })

        if not is_parent:
            result.append({
                "level": 3,
                "type": "account",
                "id": r.get("id"),
                "name": r.get("name"),
                "tab": tab,
                "header": header,
                "drcr": r.get("drcr_account"),
                "has_bf": r.get("has_bf"),
            })
            tabs[tab]["accounts"].append(r)

    # Update counts
    for item in result:
        if item["level"] == 1:
            item["count"] = len(tabs[item["key"]]["accounts"])

    return result


def get_account_by_id(account_id: int, society_id: int) -> dict | None:
    """Get a single account by id."""
    try:
        return db._execute(
            """SELECT id, name, tab_name, header, drcr_account, has_bf
               FROM accounts WHERE id=%s AND society_id=%s""",
            (account_id, society_id), fetch_one=True,
        )
    except Exception as e:
        print(f"⚠️ get_account_by_id: {e}")
        return None


def get_account_short_name(account_id: int, society_id: int) -> str:
    """Get a short display name for an account."""
    acc = get_account_by_id(account_id, society_id)
    if not acc:
        return ""
    return acc.get("name", "")


# User-friendly labels for account tabs
_TAB_LABELS = {
    "Bal": "Balance Sheet",
    "CapAc": "Capital & Reserves",
    "IncOther": "Other Income",
    "IncInt": "Interest Income",
    "IncExmpt": "Exempt Income",
    "SellAs": "Asset Sales",
    "PropInc": "Property Income",
    "Gifts": "Gifts Received",
    "InExp": "Income & Expenditure",
    "Dep": "Depreciation",
    "rent": "Rent",
    "misc": "Miscellaneous",
    "vehexp": "Vehicle Expenses",
    "Salary": "Salary",
    "Phone": "Phone",
    "Elec": "Electricity",
    "WTax": "Water Tax",
    "HTax": "House Tax",
    "Insur": "Insurance",
    "SocM": "Society Maintenance",
    "RM": "Repairs & Maintenance",
    "Stationery": "Stationery",
    "Gen": "Generator",
    "Accountant": "Accountant",
    "AuditF": "Audit Fee",
    "SocF": "Society Fine",
    "SocC": "Society Charges",
    "EventT": "Event Tickets",
    "Holi": "Holi",
    "Diwali": "Diwali",
    "LiftAMC": "Lift AMC",
    "IntercomAMC": "Intercom AMC",
    "CCTVAMC": "CCTV AMC",
    "DutyP": "Duties Paid",
    "TaxP": "Taxes Paid",
    "Prov": "Provisions",
    "GiftGiven": "Gifts Given",
    "ITax": "Income Tax",
    "TDSIT": "TDS to IT",
    "LAT": "Loans Taken",
    "CurLb": "Current Liabilities",
    "ImAs": "Immovable Assets",
    "MAs": "Movable Assets",
    "Fur": "Furniture",
    "Inv": "Investments",
    "BkAc": "Bank Accounts",
    "SBI": "SBI Account",
    "ICICI": "ICICI Account",
    "Dp": "Deposits",
    "CiH": "Cash-in-Hand",
    "Inst": "Instruments",
    "Car": "Car",
    "LAG": "Loans Given",
    "SDr": "Sundry Debtors",
    "SDrDig": "Sundry Debtors (Digital)",
    "SDrCash": "Sundry Debtors (Cash)",
    "SCr": "Sundry Creditors",
    "SinkFund": "Sinking Fund",
    "RepFund": "Repair Fund",
    "CorpusFund": "Corpus Fund",
    "CGST": "CGST Payable",
    "SGST": "SGST Payable",
}
