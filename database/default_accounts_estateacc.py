# ═══════════════════════════════════════════════════════════════════════════
# DEFAULT ACCOUNTS HELPERS
# ═══════════════════════════════════════════════════════════════════════════
# All runtime helpers in this file read from the `accounts` table.
# The canonical chart-of-accounts lives in `database/seed.py` and is
# inserted by `seed_accounts()` during bootstrap.
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# ACCOUNT DROPDOWN HELPER
# ═══════════════════════════════════════════════════════════════════════════

def get_accounts_for_dropdown(db, society_id: int, transaction_type: str = None) -> list:
    """
    Get accounts for dropdown in transaction forms.

    Args:
        society_id: Society ID
        transaction_type: 'receipt', 'expense', or None for all

    Returns:
        List of dicts: [{"id": 1, "name": "Cash", "tab": "Assets", "drcr": None}, ...]

    Logic:
    ──────
    • RECEIPTS (money IN):
      - Show Income accounts (drcr_account = 'Cr')

    • EXPENSES (money OUT):
      - Show Expense accounts (drcr_account = 'Dr')

    • ALL:
      - Show all accounts
    """

    try:
        if transaction_type == 'receipt':
            accounts = db._execute(
                """
                SELECT id, name, tab_name, drcr_account
                FROM accounts
                WHERE society_id=%s
                  AND drcr_account = 'Cr'
                ORDER BY tab_name, name
                """,
                (society_id,),
                fetch_all=True
            ) or []

        elif transaction_type == 'expense':
            accounts = db._execute(
                """
                SELECT id, name, tab_name, drcr_account
                FROM accounts
                WHERE society_id=%s
                  AND drcr_account = 'Dr'
                ORDER BY tab_name, name
                """,
                (society_id,),
                fetch_all=True
            ) or []

        else:
            accounts = db._execute(
                """
                SELECT id, name, tab_name, drcr_account
                FROM accounts
                WHERE society_id=%s
                ORDER BY tab_name, name
                """,
                (society_id,),
                fetch_all=True
            ) or []

        # Format for dropdown with grouping
        formatted = []
        for acc in accounts:
            drcr_label = acc.get("drcr_account") or ""
            label = f"{acc['name']} ({acc['tab_name']}) [{drcr_label}]"
            formatted.append({
                "value": acc["id"],
                "label": label,
                "tab": acc.get("tab_name"),
                "drcr": acc.get("drcr_account"),
            })

        return formatted

    except Exception as e:
        print(f"Error loading accounts: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════
# TRANSACTION VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

def validate_transaction_account(db, acc_id: int, society_id: int, transaction_type: str) -> tuple:
    """
    Validate that the selected account is appropriate for the transaction type.

    Args:
        acc_id: Account ID
        society_id: Society ID
        transaction_type: 'receipt' or 'expense'

    Returns:
        (is_valid: bool, error_message: str)

    Validation Logic:
    ─────────────────
    • RECEIPTS (money IN):
      ✓Income accounts (drcr_account = 'Cr')
      ✗ Expense accounts (drcr_account = 'Dr')

    • EXPENSES (money OUT):
      ✓Expense accounts (drcr_account = 'Dr')
      ✗ Income accounts (drcr_account = 'Cr')
    """

    try:
        account = db._execute(
            "SELECT id, name, drcr_account, tab_name FROM accounts WHERE id=%s AND society_id=%s",
            (acc_id, society_id),
            fetch_one=True
        )

        if not account:
            return False, "Invalid account for this society"

        drcr = account.get("drcr_account")
        name = account.get("name")

        if transaction_type == 'receipt':
            if drcr == 'Dr':
                return False, f"Cannot use Expense account '{name}' for receipts. Select an Income account."
            return True, ""

        elif transaction_type == 'expense':
            if drcr == 'Cr':
                return False, f"Cannot use Income account '{name}' for expenses. Select an Expense account."
            return True, ""

        return True, ""

    except Exception as e:
        return False, f"Validation error: {str(e)}"


# ═══════════════════════════════════════════════════════════════════════════
# PARTICULARS TEMPLATES — hard-coded in Python, NOT stored in the database.
#
# These strings is what appears in receipts.particulars / expenses.particulars
# / receivables.description / payables.description, and flow through to
# transactions.acc_particulars.
#
# Usage in renderers.py / drilldown_callbacks.py:
#   from database.default_accounts_estateacc import (
#       get_receipt_particulars, get_expense_particulars,
#       RECEIPT_ACCOUNT_HINTS, EXPENSE_ACCOUNT_HINTS
#   )
#
# ACCOUNT HINTS tell the form which acc_id to pre-select in the dropdown.
# The actual dropdown options come from get_accounts_for_dropdown() above;
# the hints just drive the default selection.
# ═══════════════════════════════════════════════════════════════════════════

from datetime import date as _date

def _month_year(d=None):
    d = d or _date.today()
    return d.strftime('%b-%Y')          # e.g. "Apr-2025"

def _dd_mon_yyyy(d=None):
    d = d or _date.today()
    return d.strftime('%d-%b-%Y')       # e.g. "05-Apr-2025"


# ── Receipt particulars ──────────────────────────────────────────────────
# Each entry: (template_fn(record, date) -> str, suggested_account_name)
# record is the dict the UI currently has in prefill (apartment/vendor/security row).

RECEIPT_PARTICULARS_TEMPLATES = {
    # Maintenance collected manually (not via Pay-Dues FIFO — that uses fn_pay_apartment_dues_fifo)
    'maintenance': {
        'label': 'Maintenance Receipt',
        'particulars': lambda r, d=None: (
            f"Maintenance {_month_year(d)} — Flat {r.get('flat_number','')}"
            + (f" ({r.get('owner_name','')})" if r.get('owner_name') else '')
        ),
        'account_hint': 'Society Maintenance Charge',   # acc 2311
        'role': 'apartment',
    },
    'interest': {
        'label': 'Interest on Dues',
        'particulars': lambda r, d=None: (
            f"Interest {_month_year(d)} — Flat {r.get('flat_number','')}"
        ),
        'account_hint': 'Interest Income',              # acc 211
        'role': 'apartment',
    },
    'fine_apartment': {
        'label': 'Fine on Apartment',
        'particulars': lambda r, d=None: (
            f"Fine — Flat {r.get('flat_number','')} — {_dd_mon_yyyy(d)}"
        ),
        'account_hint': 'Society Fine',                 # acc 2317
        'role': 'apartment',
    },
    'fine_vendor': {
        'label': 'Fine on Vendor',
        'particulars': lambda r, d=None: (
            f"Fine — {r.get('name','')} — {_dd_mon_yyyy(d)}"
        ),
        'account_hint': 'Society Fine',                 # acc 2317
        'role': 'vendor',
    },
    'vendor_pass_1day': {
        'label': 'Vendor 1-Day Pass',
        'particulars': lambda r, d=None: (
            f"Vendor Pass (1day) — {r.get('name','')} — {_dd_mon_yyyy(d)}"
        ),
        'account_hint': 'Society Charge',               # acc 2318
        'role': 'vendor',
    },
    'vendor_pass_7day': {
        'label': 'Vendor 7-Day Pass',
        'particulars': lambda r, d=None: (
            f"Vendor Pass (7day) — {r.get('name','')} — {_dd_mon_yyyy(d)}"
        ),
        'account_hint': 'Society Charge',               # acc 2318
        'role': 'vendor',
    },
    'vendor_pass_1mth': {
        'label': 'Vendor 1-Month Pass',
        'particulars': lambda r, d=None: (
            f"Vendor Pass (1mth) — {r.get('name','')} — {_dd_mon_yyyy(d)}"
        ),
        'account_hint': 'Society Charge',               # acc 2318
        'role': 'vendor',
    },
    'donation': {
        'label': 'Donation / Gift Received',
        'particulars': lambda r, d=None: f"Donation — {_dd_mon_yyyy(d)}",
        'account_hint': 'Gifts Received',               # acc 22
        'role': 'other',
    },
    'event_income': {
        'label': 'Event Income',
        'particulars': lambda r, d=None: (
            f"Event Income — {r.get('title', _dd_mon_yyyy(d))}"
        ),
        'account_hint': 'Society Charge',               # acc 2318 (or event-specific)
        'role': 'other',
    },
    'asset_sale': {
        'label': 'Asset Sale',
        'particulars': lambda r, d=None: (
            f"Asset Sale — {r.get('asset_name','')} — {_dd_mon_yyyy(d)}"
        ),
        'account_hint': 'Selling Asset',                # acc 212
        'role': 'other',
    },
    'other_income': {
        'label': 'Other Income',
        'particulars': lambda r, d=None: f"Income — {_dd_mon_yyyy(d)}",
        'account_hint': 'Income Other Source',          # acc 21
        'role': 'other',
    },
}


# ── Expense particulars ───────────────────────────────────────────────────

EXPENSE_PARTICULARS_TEMPLATES = {
    'salary': {
        'label': 'Security Salary',
        'particulars': lambda r, d=None: (
            f"Salary {_month_year(d)} — {r.get('name','')}"
        ),
        'account_hint': 'Salary',                       # acc 235
        'role': 'security',
    },
    'security_bonus': {
        'label': 'Security Bonus',
        'particulars': lambda r, d=None: (
            f"Bonus {_month_year(d)} — {r.get('name','')}"
        ),
        'account_hint': 'Miscellaneous',                # acc 233
        'role': 'security',
    },
    'vendor_payment': {
        'label': 'Vendor Service Payment',
        'particulars': lambda r, d=None: (
            f"Payment — {r.get('name','')} ({r.get('service_type','')}) — {_dd_mon_yyyy(d)}"
        ),
        'account_hint': 'Repair and Maintenance',       # acc 2312
        'role': 'vendor',
    },
    'pass_reversal': {
        'label': 'Pass Reversal / Refund',
        'particulars': lambda r, d=None: (
            f"Pass Reversal — {r.get('name','')} — {_dd_mon_yyyy(d)}"
        ),
        'account_hint': 'Miscellaneous',                # acc 233
        'role': 'vendor',
    },
    'asset_purchase': {
        'label': 'Asset Purchase',
        'particulars': lambda r, d=None: (
            f"Asset Purchase — {r.get('asset_name','')} — {_dd_mon_yyyy(d)}"
        ),
        'account_hint': 'Miscellaneous',                # acc 233; acc_id on asset row matters more
        'role': 'assets',
    },
    'depreciation': {
        'label': 'Depreciation',
        'particulars': lambda r, d=None: (
            f"Depreciation — {r.get('asset_name','')} — {_dd_mon_yyyy(d)}"
        ),
        'account_hint': 'Depreciation',                 # acc 234
        'role': 'assets',
    },
    'electricity': {
        'label': 'Electricity Bill',
        'particulars': lambda r, d=None: f"Electricity — {_month_year(d)}",
        'account_hint': 'Electricity',                  # acc 237
        'role': 'other',
    },
    'water_tax': {
        'label': 'Water Tax',
        'particulars': lambda r, d=None: f"Water Tax — {_month_year(d)}",
        'account_hint': 'Water Tax',                    # acc 238
        'role': 'other',
    },
    'repairs': {
        'label': 'Repair & Maintenance',
        'particulars': lambda r, d=None: f"R&M — {_dd_mon_yyyy(d)}",
        'account_hint': 'Repair and Maintenance',       # acc 2312
        'role': 'other',
    },
    'other_expense': {
        'label': 'Other Expense',
        'particulars': lambda r, d=None: f"Expense — {_dd_mon_yyyy(d)}",
        'account_hint': 'Miscellaneous',                # acc 233
        'role': 'other',
    },
}


def get_receipt_particulars(template_key: str, record: dict, d=None) -> str:
    """Generate the particulars string for a receipt from a template key."""
    tmpl = RECEIPT_PARTICULARS_TEMPLATES.get(template_key)
    if not tmpl:
        return f"Receipt — {_dd_mon_yyyy(d)}"
    try:
        return tmpl['particulars'](record, d)
    except Exception:
        return tmpl['label']


def get_expense_particulars(template_key: str, record: dict, d=None) -> str:
    """Generate the particulars string for an expense from a template key."""
    tmpl = EXPENSE_PARTICULARS_TEMPLATES.get(template_key)
    if not tmpl:
        return f"Expense — {_dd_mon_yyyy(d)}"
    try:
        return tmpl['particulars'](record, d)
    except Exception:
        return tmpl['label']


def resolve_account_hint(db, society_id: int, account_hint: str) -> int | None:
    """
    Look up an account by a partial name hint, returning its id or None.
    Used to pre-select the correct acc_id in receipt/expense forms.

    Example:
        acc_id = resolve_account_hint(db, society_id, 'Society Maintenance Charge')
    """
    try:
        row = db._execute(
            "SELECT id FROM accounts WHERE society_id=%s AND name ILIKE %s LIMIT 1",
            (society_id, f'%{account_hint}%'),
            fetch_one=True,
        )
        return row['id'] if row else None
    except Exception:
        return None
