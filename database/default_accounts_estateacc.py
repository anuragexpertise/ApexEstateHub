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
        # ─────────────────────────────────────────────────────────────────
        # ROOT & MAJOR GROUPS
        # ─────────────────────────────────────────────────────────────────
        (1,   "Balance Sheet Root",      "Bal",    "Balance Sheet",           1,    None,  False, "Dr", 0,    100),
        (2,   "Current Liabilities",     "CurLb",  "Current Liabilities",     1,    None,  False, "Dr", 0,    100),
        (3,   "Immovable Assets",        "ImAs",   "Immovable Assets",        1,    None,  False, "Dr", 0,    100),
        (4,   "Movable Assets",          "MAs",    "Movable Assets",          1,    None,  False, "Dr", 0,    100),
        (5,   "Capital Account",         "CapAc",  "Capital Account",         1,    None,  True,  "Cr", 0,    100),
        (41,  "Loans & Advances Taken",  "LAT",    "Loans And Advances Taken",1,    None,  False, "Dr", 0,    100),
        (125, "Loans & Advances Given",  "LAG",    "Loans & Advances Given",  1,    None,  False, "Dr", 0,    100),
        
        # ─────────────────────────────────────────────────────────────────
        # CAPITAL ACCOUNT ITEMS (Balance Sheet)
        # ─────────────────────────────────────────────────────────────────
        (19,  "Duties Paid",             "DutyP",  "Duties Paid",             5,    None,  False, "Dr", 0,    100),
        (20,  "Taxes Paid",              "TaxP",   "Taxes paid",              5,    None,  False, "Dr", 0,    100),
        (21,  "Provisions",              "Prov",   "Provisions",              5,    None,  False, "Dr", 0,    100),
        (106, "Income Tax",              "ITax",   "Income Tax",              5,    None,  False, "Dr", 0,    100),
        (121, "TDS to IT",               "TDSIT",  "TDS Paid",                5,    None,  True,  "Dr", 0,    100),
        (145, "TDS to IT",               "TDStoIT","TDStoIT",                 5,    None,  False, "Dr", 0,    100),
        
        # ─────────────────────────────────────────────────────────────────
        # MOVABLE ASSETS (drcr_account = NULL)
        # ─────────────────────────────────────────────────────────────────
        (6,   "Furniture",               "Fur",    "Furniture",               4,    None,  True,  "Dr", 0,    10),
        (12,  "Investments",             "Inv",    "Investments",             4,    None,  False, "Dr", 0,    100),
        (14,  "Current Assets",          "CurAs",  "Current Assets",          4,    None,  False, "Dr", 0,    100),
        (66,  "Instruments",             "Inst",   "Instruments",             4,    None,  True,  "Dr", 0,    15),
        (70,  "Car",                     "Car",    "Car",                     4,    None,  True,  "Dr", 0,    15),
        (114, "Generator",               "Gen.",   "Generator",              18,    None,  False, "Dr", 0,    15),
        (154, "Water Harvesting",        "WaterHarv","Water Harvesting",     66,    None,  False, "Dr", 0,    40),
        
        # ─────────────────────────────────────────────────────────────────
        # CURRENT ASSETS (drcr_account = NULL)
        # ─────────────────────────────────────────────────────────────────
        (15,  "Bank Accounts",           "BkAc",   "Bank Accounts",          14,    None,  False, "Dr", 0,    100),
        (16,  "Deposits (Assets)",       "Dp",     "Deposits (Assets)",      14,    None,  False, "Dr", 0,    100),
        (40,  "Cash-in-hand",            "CiH",    "Cash-in-hand",           14,    None,  True,  "Dr", 0,    100),
        (43,  "SBI A/c – Society",       "SBI",    "SBI A/c – Society",      15,    None,  True,  "Dr", 0,    100),
        
        # ─────────────────────────────────────────────────────────────────
        # SUNDRY DEBTORS & CREDITORS (drcr_account = NULL)
        # ─────────────────────────────────────────────────────────────────
        (10,  "Sundry Creditors",        "SCr",    "Sundry Creditors",      124,    None,  False, "Cr", 0,    100),
        (60,  "Sundry Debitors",         "SDr",    "Sundry Debitors",       125,    None,  True,  "Dr", 0,    100),
        
        # ─────────────────────────────────────────────────────────────────
        # LOANS & ADVANCES (drcr_account = NULL)
        # ─────────────────────────────────────────────────────────────────
        (57,  "Loans Given",             "LoanG",  "Loans Given",           125,    None,  False, "Dr", 0,    100),
        (59,  "Advances Given",          "AdvG",   "Advances Given",        125,    None,  False, "Dr", 0,    100),
        (61,  "Draft Given",             "DraftG", "Draft Given",           125,    None,  False, "Dr", 0,    100),
        
        # ─────────────────────────────────────────────────────────────────
        # INCOME ACCOUNTS (drcr_account = 'Cr')
        # ─────────────────────────────────────────────────────────────────
        (7,   "Income Other Source",     "IncOther","Income other source",    5,    "Cr",  False, "Cr", 0,    100),
        (13,  "Gifts Received",          "Gifts",  "Gifts Received",          5,    "Cr",  False, "Cr", 0,    100),
        (18,  "Income Expenditure A/c",  "InExp",  "Income Expenditure Account",5,   "Cr",  False, "Cr", 0,    100),
        (8,   "Interest Income",         "IncInt", "Interest Income",         7,    "Cr",  False, "Cr", 0,    100),
        (24,  "Selling Asset",           "SellAs", "Selling Asset",           7,    "Cr",  False, "Cr", 0,    100),
        (27,  "Property Income",         "PropInc","Property Income",         7,    "Cr",  False, "Cr", 0,    100),
        (9,   "Bank Interest",           "IntBK",  "Bank Interest",           8,    "Cr",  False, "Cr", 0,    100),
        (11,  "Exempt Income",           "IncExmpt","Exempt Income",          8,    "Cr",  False, "Cr", 0,    100),
        (28,  "Saving Interest",         "IntSav", "Saving Interest",         9,    "Cr",  False, "Cr", 0,    100),
        (29,  "FD Interest",             "IntFD",  "FD Interest",             8,    "Cr",  False, "Cr", 0,    100),
        (108, "Maintenance",             "Mantainenece","Maintainence",      18,    "Cr",  False, "Cr", 0,    100),
        
        # ─────────────────────────────────────────────────────────────────
        # EXPENSE ACCOUNTS (drcr_account = 'Dr')
        # ─────────────────────────────────────────────────────────────────
        (98,  "Gifts Given",             "GiftGiven","Gifts Given",           5,    "Dr",  False, "Dr", 0,    100),
        (52,  "Vehicle Expenditure",     "vehexp", "Vehicle Expenditure",    18,    "Dr",  False, "Dr", 0,    100),
        (53,  "Rent",                    "rent",   "Rent",                   18,    "Dr",  False, "Dr", 0,    100),
        (54,  "Miscellaneous",           "misc",   "Miscellaneous",          18,    "Dr",  False, "Dr", 0,    100),
        (56,  "Depreciation",            "Dep",    "Depreciation Account",   18,    "Dr",  False, "Dr", 0,    100),
        (71,  "Salary",                  "Salary", "Salary",                 18,    "Dr",  False, "Dr", 0,    100),
        (74,  "Phone",                   "Phone",  "Phone",                  18,    "Dr",  False, "Dr", 0,    100),
        (78,  "Electricity",             "Elec",   "Electricity",            18,    "Dr",  False, "Dr", 0,    100),
        (80,  "Water Tax",               "WTax",   "Water Tax",              18,    "Dr",  False, "Dr", 0,    100),
        (81,  "House Tax",               "HTax",   "House Tax",              18,    "Dr",  False, "Dr", 0,    100),
        (112, "Repair and Maintenance",  "RM",     "Repair and Maintanence", 18,    "Dr",  False, "Dr", 0,    100),
        (113, "Stationery",              "Stationery","Stationery",          18,    "Dr",  False, "Dr", 0,    100),
        (147, "Accountant",              "Accountant","Accountant",          18,    "Dr",  False, "Dr", 0,    100),
        (104, "Insurance",               "Insur",  "Insurance",              18,    "Dr",  False, "Dr", 0,    100),
        (158, "Audit Fee",               "AuditF", "Audit Fee",              18,    "Dr",  False, "Dr", 0,    100),
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
                    created_at
                )
                VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                (acc_id, society_id, name, tab, header, parent,
                 drcr_ac, has_bf, drcr_bf, bf_amt, dep_pct),
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
      ✓ Income accounts (drcr_account = 'Cr')
      ✓ Assets/Liabilities (drcr_account = NULL) - selling asset, receiving loan
      ✗ Expense accounts (drcr_account = 'Dr')
    
    • EXPENSES (money OUT):
      ✓ Expense accounts (drcr_account = 'Dr')
      ✓ Assets/Liabilities (drcr_account = NULL) - buying asset, repaying loan
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
