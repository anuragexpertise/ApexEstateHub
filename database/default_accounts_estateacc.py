# ═══════════════════════════════════════════════════════════════════════════
# DEFAULT ACCOUNTS CREATION - Based on EstateAcc.xlsx
# ═══════════════════════════════════════════════════════════════════════════
# This creates the complete Chart of Accounts for a new society
# 
# IMPORTANT BALANCE SHEET LOGIC:
# ─────────────────────────────
# • Assets & Liabilities: drcr_account = NULL (can be both Dr and Cr)
#   - Assets: Dr when bought, Cr when sold
#   - Liabilities: Cr when borrowed, Dr when repaid
#   - Sundry Debtors: Dr when credit given, Cr when payment received
#   - Sundry Creditors: Cr when credit taken, Dr when paid
# 
# • Income: ALWAYS Cr (money coming IN)
# • Expenses: ALWAYS Dr (money going OUT)
# ═══════════════════════════════════════════════════════════════════════════

def create_default_accounts(db, society_id: int):
    """
    Create complete Chart of Accounts from EstateAcc.xlsx structure.
    
    Account Structure:
    ──────────────────
    1. Balance Sheet Items (Assets/Liabilities) → drcr_account = NULL
    2. Income Items → drcr_account = 'Cr'
    3. Expense Items → drcr_account = 'Dr'
    
    Args:
        db: Database connection
        society_id: Society ID
    """
    
    # ═══════════════════════════════════════════════════════════════════════
    # ACCOUNT DEFINITIONS FROM EstateAcc.xlsx
    # ═══════════════════════════════════════════════════════════════════════
    # Format: (id, name, tab_name, header, parent_id, drcr_account, has_bf, drcr_bf, bf_amount, depreciation_percent)
    
    accounts = [
        # ───────────────────────────────────────────────────────────────────
        # ROOT & BALANCE SHEET STRUCTURE
        # ───────────────────────────────────────────────────────────────────
        (1,     'Balance Sheet Root',        'Bal',         'Balance Sheet',               1,    'Dr',  True,  'Dr',  0,   100),
        (2,     'Capital Account',           'CapAc',       'Capital Account',             1,    'Cr',  True,  'Cr',  0,   100),
        
        # ───────────────────────────────────────────────────────────────────
        # INCOME ACCOUNTS (Under Capital Account - All Cr)
        # ───────────────────────────────────────────────────────────────────
        (21,    'Income Other Source',       'IncOther',    'Income other source',         2,    'Cr',  True,  'Cr',  0,   100),
        (211,   'Interest Income',           'IncInt',      'Interest Income',            21,    'Cr',  True,  'Cr',  0,   100),
        (2111,  'Bank Interest',             'IntBK',       'Bank Interest',             211,    'Cr',  True,  'Cr',  0,   100),
        (21111, 'Saving Interest',           'IntSav',      'Saving Interest',          2111,    'Cr',  True,  'Cr',  0,   100),
        (2112,  'Exempt Income',             'IncExmpt',    'Exempt Income',             211,    'Cr',  True,  'Cr',  0,   100),
        (21112, 'FD Interest',               'IntFD',       'FD Interest',              2111,    'Cr',  True,  'Cr',  0,   100),
        (212,   'Selling Asset',             'SellAs',      'Selling Asset',              21,    'Cr',  True,  'Cr',  0,   100),
        (213,   'Property Income',           'PropInc',     'Property Income',            21,    'Cr',  True,  'Cr',  0,   100),
        (22,    'Gifts Received',            'Gifts',       'Gifts Received',              2,    'Cr',  True,  'Cr',  0,   100),
        
        # ───────────────────────────────────────────────────────────────────
        # INCOME & EXPENSE ACCOUNT (Mixed)
        # ───────────────────────────────────────────────────────────────────
        (23,    'Income Expenditure A/c',    'InExp',       'Income Expenditure Account',  2,    'Cr',  True,  'Cr',  0,   100),
        
        # Sub-accounts under Income Expenditure (Expenses - Dr)
        (231,   'Vehicle Expenditure',       'vehexp',      'Vehicle Expenditure',        23,    'Dr',  False, 'Dr',  0,   100),
        (232,   'Rent',                      'rent',        'Rent',                       23,    'Dr',  False, 'Dr',  0,   100),
        (233,   'Miscellaneous',             'misc',        'Miscellaneous',              23,    'Dr',  False, 'Dr',  0,   100),
        (234,   'Depreciation',              'Dep',         'Depreciation Account',       23,    'Dr',  False, 'Dr',  0,   100),
        (235,   'Salary',                    'Salary',      'Salary',                     23,    'Dr',  False, 'Dr',  0,   100),
        (236,   'Phone',                     'Phone',       'Phone',                      23,    'Dr',  False, 'Dr',  0,   100),
        (237,   'Electricity',               'Elec',        'Electricity',                23,    'Dr',  False, 'Dr',  0,   100),
        (238,   'Water Tax',                 'WTax',        'Water Tax',                  23,    'Dr',  False, 'Dr',  0,   100),
        (239,   'House Tax',                 'HTax',        'House Tax',                  23,    'Dr',  False, 'Dr',  0,   100),
        (2310,  'Insurance',                 'Insur',       'Insurance',                  23,    'Dr',  False, 'Dr',  0,   100),
        (2312,  'Repair and Maintenance',    'RM',          'Repair and Maintanence',     23,    'Dr',  False, 'Dr',  0,   100),
        (2313,  'Stationery',                'Stationery',  'Stationery',                 23,    'Dr',  False, 'Dr',  0,   100),
        (2314,  'Generator',                 'Gen.',        'Generator',                  23,    'Dr',  False, 'Dr',  0,    15),
        (2315,  'Accountant',                'Accountant',  'Accountant',                 23,    'Dr',  False, 'Dr',  0,   100),
        (2316,  'Audit Fee',                 'AuditF',      'Audit Fee',                  23,    'Dr',  False, 'Dr',  0,   100),
        
        # Sub-accounts under Income Expenditure (Income - Cr)
        (2311,  'Society Maintenance Charge','SocM',        'Society Maintanence Charge', 23,    'Cr',  True,  'Cr',  0,   100),
        (2317,  'Society Fine',              'SocF',        'Society Fine Charge',        23,    'Cr',  True,  'Cr',  0,   100),
        (2318,  'Society Charge',            'SocC',        'Society Fees',               23,    'Cr',  True,  'Cr',  0,   100),
        
        # ───────────────────────────────────────────────────────────────────
        # OTHER CAPITAL ACCOUNT ITEMS
        # ───────────────────────────────────────────────────────────────────
        (24,    'Duties Paid',               'DutyP',       'Duties Paid',                 2,    'Cr',  False, 'Cr',  0,   100),
        (25,    'Taxes Paid',                'TaxP',        'Taxes paid',                  2,    'Cr',  False, 'Cr',  0,   100),
        (26,    'Provisions',                'Prov',        'Provisions',                  2,    'Cr',  True,  'Cr',  0,   100),
        (27,    'Gifts Given',               'GiftGiven',   'Gifts Given',                 2,    'Dr',  False, 'Dr',  0,   100),
        (28,    'Income Tax',                'ITax',        'Income Tax',                  2,    'Dr',  False, 'Dr',  0,   100),
        (29,    'TDS to IT',                 'TDSIT',       'TDS Paid',                    2,    'Dr',  False, 'Dr',  0,   100),
        
        # ───────────────────────────────────────────────────────────────────
        # LIABILITIES
        # ───────────────────────────────────────────────────────────────────
        (3,     'Loans & Advances Taken',    'LAT',         'Loans And Advances Taken',    1,    'Cr',  True,  'Cr',  0,   100),
        (4,     'Current Liabilities',       'CurLb',       'Current Liabilities',         1,    'Cr',  True,  'Cr',  0,   100),
        (9,     'Sundry Creditors',          'S Cr',        'Sundry Creditors',            1,    'Cr',  True,  'Cr',  0,   100),
        
        # ───────────────────────────────────────────────────────────────────
        # ASSETS
        # ───────────────────────────────────────────────────────────────────
        (5,     'Immovable Assets',          'ImAs',        'Immovable Assets',            1,    'Dr',  False, 'Dr',  0,   100),
        (6,     'Movable Assets',            'MAs',         'Movable Assets',              1,    'Dr',  False, 'Dr',  0,   100),
        
        # Movable Assets - Sub-accounts
        (61,    'Furniture',                 'Fur',         'Furniture',                   6,    'Dr',  False, 'Dr',  0,    10),
        (62,    'Investments',               'Inv',         'Investments',                 6,    'Dr',  False, 'Dr',  0,   100),
        (63,    'Current Assets',            'CurAs',       'Current Assets',              6,    'Dr',  False, 'Dr',  0,   100),
        (64,    'Instruments',               'Inst',        'Instruments',                 6,    'Dr',  False, 'Dr',  0,    15),
        (641,   'Water Harvesting',          'WaterHarv',   'Water Harvesting',           64,    'Cr',  False, 'Cr',  0,    40),
        (65,    'Car',                       'Car',         'Car',                         6,    'Dr',  False, 'Dr',  0,    15),
        
        # Current Assets - Sub-accounts
        (631,   'Bank Accounts',             'BkAc',        'Bank Accounts',              63,    'Dr',  False, 'Dr',  0,   100),
        (6311,  'SBI A/c – Society',         'SBI',         'SBI A/c – Society',         631,    'Dr',  False, 'Dr',  0,   100),
        (632,   'Deposits (Assets)',         'Dp',          'Deposits (Assets)',          63,    'Dr',  False, 'Dr',  0,   100),
        (633,   'Cash-in-hand',              'CiH',         'Cash-in-hand',               63,    'Dr',  False, 'Dr',  0,   100),
        
        # ───────────────────────────────────────────────────────────────────
        # LOANS & ADVANCES GIVEN (ASSETS)
        # ───────────────────────────────────────────────────────────────────
        (7,     'Loans & Advances Given',    'LAG',         'Loans  & Advances Given',     1,    'Dr',  False, 'Dr',  0,   100),
        (71,    'Loans Given',               'LoanG',       'Loans Given',                 7,    'Cr',  False, 'Cr',  0,   100),
        (72,    'Advances Given',            'AdvG',        'Advances Given',              6,    'Cr',  False, 'Cr',  0,   100),
        
        # ───────────────────────────────────────────────────────────────────
        # SUNDRY DEBTORS (ASSETS)
        # ───────────────────────────────────────────────────────────────────
        (8,     'Sundry Debtors',            'SDr',         'Sundry Debitors',             1,    'Dr',  False, 'Dr',  0,   100),
    ]


    # ═══════════════════════════════════════════════════════════════════════
    # INSERT ACCOUNTS INTO DATABASE
    # ═══════════════════════════════════════════════════════════════════════
    
    created_count = 0
    skipped_count = 0
    
    for acc_id, name, tab, header, parent, drcr_ac, has_bf, drcr_bf, bf_amt, dep_pct in accounts:
        try:
            # Check if account already exists
            existing = db._execute(
                "SELECT id FROM accounts WHERE id=%s AND society_id=%s",
                (acc_id, society_id),
                fetch_one=True
            )
            
            if existing:
                skipped_count += 1
                continue
            
            # Insert account
            db._execute(
                """
                INSERT INTO accounts(
                    id, society_id, name, tab_name, header, parent_account_id,
                    drcr_account, has_bf, drcr_bf, bf_amount, depreciation_percent,
                    is_depreciable,
                    created_at
                )
                VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                (acc_id, society_id, name, tab, header, parent,
                 drcr_ac, has_bf, drcr_bf, bf_amt, dep_pct, dep_pct < 100),
            )
            created_count += 1
            
        except Exception as e:
            print(f"Error creating account {acc_id} ({name}): {e}")
    
    print(f"✓ Created {created_count} accounts, skipped {skipped_count} existing")
    return created_count


# ═══════════════════════════════════════════════════════════════════════════
# ACCOUNT DROPDOWN HELPER - Updated for NULL drcr_account handling
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
      - Show Asset/Liability accounts (drcr_account = NULL) - for selling assets, receiving loans
    
    • EXPENSES (money OUT):
      - Show Expense accounts (drcr_account = 'Dr')
      - Show Asset/Liability accounts (drcr_account = NULL) - for buying assets, repaying loans
    
    • ALL:
      - Show all accounts
    """
    
    try:
        if transaction_type == 'receipt':
            # RECEIPTS: Cr accounts + NULL accounts (Assets/Liabilities)
            accounts = db._execute(
                """
                SELECT id, name, tab_name, drcr_account
                FROM accounts
                WHERE society_id=%s 
                  AND (drcr_account = 'Cr' OR drcr_account IS NULL)
                ORDER BY 
                    CASE 
                        WHEN drcr_account = 'Cr' THEN 1  -- Income first
                        ELSE 2                            -- Assets/Liabilities second
                    END,
                    tab_name, name
                """,
                (society_id,),
                fetch_all=True
            ) or []
        
        elif transaction_type == 'expense':
            # EXPENSES: Dr accounts + NULL accounts (Assets/Liabilities)
            accounts = db._execute(
                """
                SELECT id, name, tab_name, drcr_account
                FROM accounts
                WHERE society_id=%s 
                  AND (drcr_account = 'Dr' OR drcr_account IS NULL)
                ORDER BY 
                    CASE 
                        WHEN drcr_account = 'Dr' THEN 1   -- Expenses first
                        ELSE 2                             -- Assets/Liabilities second
                    END,
                    tab_name, name
                """,
                (society_id,),
                fetch_all=True
            ) or []
        
        else:
            # ALL accounts
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
            drcr_label = acc.get("drcr_account") or "Asset/Liability"
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
# TRANSACTION VALIDATION - Updated for Balance Sheet accounts
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
      ✓Assets/Liabilities (drcr_account = NULL) - selling asset, receiving loan
      ✗ Expense accounts (drcr_account = 'Dr')
    
    • EXPENSES (money OUT):
      ✓Expense accounts (drcr_account = 'Dr')
      ✓Assets/Liabilities (drcr_account = NULL) - buying asset, repaying loan
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
            # Receipts can use Cr (Income) or NULL (Assets/Liabilities)
            if drcr == 'Dr':
                return False, f"Cannot use Expense account '{name}' for receipts. Select an Income or Asset/Liability account."
            return True, ""
        
        elif transaction_type == 'expense':
            # Expenses can use Dr (Expense) or NULL (Assets/Liabilities)
            if drcr == 'Cr':
                return False, f"Cannot use Income account '{name}' for expenses. Select an Expense or Asset/Liability account."
            return True, ""
        
        return True, ""
    
    except Exception as e:
        return False, f"Validation error: {str(e)}"


# ═══════════════════════════════════════════════════════════════════════════
# USAGE IN drilldown_callbacks.py
# ═══════════════════════════════════════════════════════════════════════════

"""
# When creating a new society in _save_society():
if result and result.get("id"):
    soc_id = result["id"]
    # Create admin user
    db._execute(...)
    
    # Create default accounts
    create_default_accounts(db, soc_id)  # ← This creates all 50+ accounts

# When rendering receipt/expense forms in renderers.py:
if field_type == "account_dropdown_receipt":
    accounts = get_accounts_for_dropdown(db, society_id, transaction_type='receipt')
    options = [{"label": a["label"], "value": a["value"]} for a in accounts]
    control = dcc.Dropdown(id=..., options=options, ...)

elif field_type == "account_dropdown_expense":
    accounts = get_accounts_for_dropdown(db, society_id, transaction_type='expense')
    options = [{"label": a["label"], "value": a["value"]} for a in accounts]
    control = dcc.Dropdown(id=..., options=options, ...)

# When saving transactions in _save_transaction():
# Validate account selection
is_valid, error_msg = validate_transaction_account(db, acc_id, sid, transaction_type)
if not is_valid:
    return False, error_msg

# Then insert transaction...
"""
