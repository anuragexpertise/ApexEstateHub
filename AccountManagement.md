# Account Management System Specification
## ApexEstateHub - Society Accounting Module

---

## 📋 Overview

Based on the uploaded Excel files, this document specifies the complete accounting system structure for ApexEstateHub, including:

1. **Accounts Master** - Chart of accounts with parent_account_id
2. **Cashbook** - Dual-entry receipt/payment register with running balance
3. **Ledger** - Account-wise transaction history
4. **Receipt & Expense Management** - With account selection

---

## 🗂️ Database Schema

### 1. **accounts** table

Stores the chart of accounts with hierarchical structure.

```sql
CREATE TABLE accounts (
    id INT NOT NULL PRIMARY KEY,
    society_id INTEGER REFERENCES societies(id) ON DELETE CASCADE,
    
    name VARCHAR(100) NOT NULL,                -- Account Name (e.g., "Patients", "Salary")
    tab_name VARCHAR(50),                      -- Tab/Group (e.g., "IncOther", "Salary")
    header VARCHAR(200),                       -- Full Header Name (e.g., "Income Other")
    parent_account_id INTEGER DEFAULT 0,               -- parent_account_id Level (0=root, 1=parent, 2=child, etc.)
    
    -- Dr/Cr designation (from columns K-L)
    drcr_account VARCHAR(2) NOT NULL,          -- 'Dr' or 'Cr' (from society's perspective)
    drcr_bf VARCHAR(2) DEFAULT 'Dr',           -- Opening balance side: 'Dr' or 'Cr'
    
    -- Opening balance (from columns M-N)
    bf_amount DECIMAL(15,2) DEFAULT 0.00,      -- Brought Forward (opening balance) amount
    bf_year VARCHAR(20),                       -- Financial year of B/F (e.g., "2016-2017")
    
    -- Depreciation (from column O)
    depreciation_percent DECIMAL(5,2) DEFAULT 0.00,  -- Annual depreciation % (e.g., 10.0)
    
    -- Status
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Constraints
    UNIQUE(society_id, id),
    CHECK(drcr_account IN ('Dr', 'Cr')),
    CHECK(drcr_bf IN ('Dr', 'Cr'))
);

CREATE INDEX idx_accounts_society ON accounts(society_id);
CREATE INDEX idx_accounts_tab ON accounts(society_id, tab_name);
CREATE INDEX idx_accounts_hierarchy ON accounts(society_id, parent_account_id);
```

**Sample Data:**
```
| id | name      | tab_name  | header                 | parent_account_id | drcr_account | drcr_bf | bf_amount | bf_year   | dep% |
|-------|-----------|-----------|------------------------|-----------|--------------|---------|-----------|-----------|------|
| 1     | Bal       | Bal       | Balance Sheet          | 0         | Dr           | Dr      | 111339.00 | 2016-2017 | 100  |
| 5     | CapAc     | CapAc     | Capital Account        | 1         | Cr           | Cr      | 66042.44  | 2016-2017 | 100  |
| 6     | Furniture | Fur       | Furniture              | 4         | Dr           | Dr      | 19051.76  | 2016-2017 | 10   |
| 7     | Inc Other | IncOther  | Income Other           | 5         | Cr           | Cr      | 0.00      | 2016-2017 | 100  |
| 17    | Salary    | Salary    | Salary                 | 5         | Dr           | Dr      | 0.00      | 2016-2017 | 100  |
```

---

### 2. **transactions** table (Updated)

Stores ALL financial transactions (receipts + expenses). This is your **Cashbook**.

```sql
CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    society_id INTEGER REFERENCES societies(id) ON DELETE CASCADE,
    
    -- Transaction basics
    trx_date DATE NOT NULL,                          -- Transaction date
    acc_id INTEGER REFERENCES accounts(id),          -- Link to accounts table (REQUIRED)
    entity_id INTEGER,                               -- Optional: link to apartment/vendor/user
    
    -- Transaction details
    acc_particulars TEXT NOT NULL,                   -- Description/Particulars
    amount DECIMAL(15,2) NOT NULL,                   -- Amount
    
    -- Payment mode
    mode VARCHAR(20) DEFAULT 'cash',                 -- 'cash', 'cheque', 'upi', 'card', 'bank', 'crypto'
    cheque_no VARCHAR(50),                           -- Cheque number (if mode=cheque)
    
    -- Transaction type (derived from account's drcr_account)
    -- If account is 'Cr' -> Receipt (credit to society)
    -- If account is 'Dr' -> Payment (debit from society)
    
    -- Status
    status VARCHAR(20) DEFAULT 'paid',               -- 'pending', 'paid', 'cancelled'
    
    -- Audit
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    
    CHECK(amount > 0)
);

CREATE INDEX idx_transactions_society_date ON transactions(society_id, trx_date DESC);
CREATE INDEX idx_transactions_account ON transactions(acc_id);
CREATE INDEX idx_transactions_entity ON transactions(entity_id);
```

**Key Changes from Original:**
- **acc_id is MANDATORY** - Every transaction MUST be linked to an account
- Removed `acc_code` (redundant - we have `acc_id`)
- Mode includes 'crypto' for modern payments
- `cheque_no` field for cheque payments

---

### 3. **payments** table (Unchanged - for dues tracking)

This tracks **pending payments** (maintenance dues, vendor payments, etc.) - separate from transactions.

```sql
-- Keep existing payments table as-is for dues management
-- Only verified payments create transaction records
```

---

## 📊 How the System Works

### **Receipt Entry Flow**

1. User selects **Receipt** from menu
2. System shows form:
   - **Date** (date picker, default: today)
   - **Account** (dropdown from accounts where `drcr_account='Cr'`)
     - Shows: "Patients (IncOther)", "Donations (IncOther)", "Maintenance (MF)" etc.
   - **Particulars** (text input)
   - **Amount** (number input)
   - **Mode** (dropdown: Cash/Cheque/UPI/Card/Bank/Crypto)
   - **Cheque No** (if mode=cheque)
3. On submit:
   ```python
   db._execute("""
       INSERT INTO transactions 
       (society_id, trx_date, acc_id, acc_particulars, amount, mode, cheque_no, status)
       VALUES (%s, %s, %s, %s, %s, %s, %s, 'paid')
   """, (society_id, date, account_id, particulars, amount, mode, cheque_no))
   ```

### **Expense Entry Flow**

1. User selects **Expense** from menu
2. System shows form:
   - **Date** (date picker, default: today)
   - **Account** (dropdown from accounts where `drcr_account='Dr'`)
     - Shows: "Salary (Salary)", "Rent (Rent)", "Electricity (Util)" etc.
   - **Particulars** (text input)
   - **Amount** (number input)
   - **Mode** (dropdown: Cash/Cheque/UPI/Card/Bank/Crypto)
   - **Cheque No** (if mode=cheque)
3. On submit (same as receipt)

---

## 📖 Cashbook View

**Cashbook** shows all transactions in chronological order with running balance.

### Cashbook Structure (from cb.xlsx):

```
| Date       | Receipt A/c | Receipt Particulars      | Cash | Cheque | Total | Payment A/c | Payment Particulars | Cash | Cheque | Total | Balance |
|------------|-------------|--------------------------|------|--------|-------|-------------|---------------------|------|--------|-------|---------|
| 2016-04-01 | Balance     | B/F                      | -    | -      | 0     | -           | -                   | -    | -      | 0     | 0       |
| 2016-04-01 | Anurag      | Loan taken from Anurag   | -    | -      | 0     | -           | -                   | -    | -      | 0     | 15000   |
| 2016-04-22 | Patients    | CMS/LIPL PMT APR16       | -    | 400    | 0     | -           | -                   | -    | -      | 0     | 15000   |
| 2016-04-29 | -           | -                        | -    | -      | 0     | Electricity | Current bill        | 500  | -      | 500   | 14500   |
```

### Query for Cashbook:

```python
def get_cashbook(society_id, start_date=None, end_date=None):
    """
    Returns cashbook with running balance.
    Separates receipts (Cr accounts) and payments (Dr accounts).
    """
    query = """
    WITH cashbook AS (
        SELECT 
            t.trx_date,
            a.name AS account_name,
            a.tab_name,
            a.drcr_account,
            t.acc_particulars,
            t.amount,
            t.mode,
            t.cheque_no,
            t.id
        FROM transactions t
        JOIN accounts a ON t.acc_id = a.id
        WHERE t.society_id = %s
          AND t.status = 'paid'
    """
    
    if start_date:
        query += " AND t.trx_date >= %s"
    if end_date:
        query += " AND t.trx_date <= %s"
    
    query += """
        ORDER BY t.trx_date, t.id
    )
    SELECT 
        trx_date,
        CASE WHEN drcr_account='Cr' THEN account_name END AS receipt_account,
        CASE WHEN drcr_account='Cr' THEN acc_particulars END AS receipt_particulars,
        CASE WHEN drcr_account='Cr' AND mode='cash' THEN amount END AS receipt_cash,
        CASE WHEN drcr_account='Cr' AND mode IN ('cheque','bank') THEN amount END AS receipt_cheque,
        CASE WHEN drcr_account='Cr' THEN amount END AS receipt_total,
        
        CASE WHEN drcr_account='Dr' THEN account_name END AS payment_account,
        CASE WHEN drcr_account='Dr' THEN acc_particulars END AS payment_particulars,
        CASE WHEN drcr_account='Dr' AND mode='cash' THEN amount END AS payment_cash,
        CASE WHEN drcr_account='Dr' AND mode IN ('cheque','bank') THEN amount END AS payment_cheque,
        CASE WHEN drcr_account='Dr' THEN amount END AS payment_total,
        
        SUM(CASE WHEN drcr_account='Cr' THEN amount ELSE -amount END) OVER (ORDER BY trx_date, id) AS balance
    FROM cashbook
    """
    
    params = [society_id]
    if start_date:
        params.append(start_date)
    if end_date:
        params.append(end_date)
    
    return db._execute(query, tuple(params), fetch_all=True)
```

---

## 📘 Ledger View

**Ledger** shows all transactions for a **specific account**.

### Ledger Structure (from ld.xlsx):

```
| Date       | A/c         | Description              | CB F No. | Debit  | Credit | Dr or Cr | Balance |
|------------|-------------|--------------------------|----------|--------|--------|----------|---------|
| 2016-04-22 | Patients    | CMS/LIPL PMT APR16       | 1        | -      | 400    | Cr       | 400     |
| 2016-05-06 | Patients    | Payment received         | 5        | -      | 600    | Cr       | 1000    |
| 2016-05-23 | Patients    | May consulting           | 8        | -      | 1100   | Cr       | 2100    |
```

### Query for Ledger:

```python
def get_ledger(society_id, account_id, start_date=None, end_date=None):
    """
    Returns ledger for a specific account with running balance.
    """
    # Get account info
    account = db._execute(
        "SELECT name, drcr_account, bf_amount, drcr_bf FROM accounts WHERE id=%s",
        (account_id,),
        fetch_one=True
    )
    
    if not account:
        return []
    
    # Get opening balance
    opening_balance = account['bf_amount'] if account['drcr_bf'] == account['drcr_account'] else -account['bf_amount']
    
    query = """
    SELECT 
        t.trx_date AS date,
        a.name AS account_name,
        t.acc_particulars AS description,
        t.id AS cb_ref,
        CASE 
            WHEN a.drcr_account='Dr' THEN t.amount 
            ELSE NULL 
        END AS debit,
        CASE 
            WHEN a.drcr_account='Cr' THEN t.amount 
            ELSE NULL 
        END AS credit,
        a.drcr_account AS dr_or_cr
    FROM transactions t
    JOIN accounts a ON t.acc_id = a.id
    WHERE t.society_id = %s
      AND t.acc_id = %s
      AND t.status = 'paid'
    """
    
    params = [society_id, account_id]
    
    if start_date:
        query += " AND t.trx_date >= %s"
        params.append(start_date)
    if end_date:
        query += " AND t.trx_date <= %s"
        params.append(end_date)
    
    query += " ORDER BY t.trx_date, t.id"
    
    rows = db._execute(query, tuple(params), fetch_all=True) or []
    
    # Calculate running balance
    balance = opening_balance
    result = []
    
    for row in rows:
        if row['debit']:
            balance += row['debit']
        else:
            balance += row['credit']
        
        result.append({
            **row,
            'balance': balance
        })
    
    return result
```

---

## 🎨 UI Implementation

### **1. Account Master Management**

**Page: Admin → Settings → Accounts**

- **List View:**
  - Show: Ac No, Name, Tab, Header, Dr/Cr, Opening Balance
  - Actions: View, Edit, Activate/Deactivate
  - Filter by: Tab, parent_account_id Level
  - Search by: Name

- **Create/Edit Form:**
  ```
  Account Number: [____] (auto-increment suggestion)
  Account Name:   [________________]
  Tab/Group:      [dropdown: existing tabs + "Create new"]
  Header:         [________________]
  parent_account_id:      [0-5] (0=root)
  Dr/Cr Account:  [Dr ○] [Cr ○]
  Opening Balance:
    - BF Amount:  [₹ ______]
    - BF Side:    [Dr ○] [Cr ○]
    - BF Year:    [2024-2025 ▼]
  Depreciation %: [__.__] % (0-100)
  ```

### **2. Receipt Entry**

**Quick Access: Dashboard → New Receipt**

```
┌─────────────────────────────────────────┐
│  💰 New Receipt                         │
├─────────────────────────────────────────┤
│  Date:          [2024-01-15 📅]         │
│  Account:       [Patients (IncOther) ▼] │  ← Only shows Cr accounts
│  Particulars:   [________________]      │
│  Amount:        [₹ ______]              │
│  Mode:          [Cash ▼]                │  ← Cash/Cheque/UPI/Card/Bank/Crypto
│  Cheque No:     [______] (if cheque)    │
│                                         │
│        [Cancel]  [💾 Save Receipt]      │
└─────────────────────────────────────────┘
```

### **3. Expense Entry**

**Quick Access: Dashboard → New Expense**

```
┌─────────────────────────────────────────┐
│  💸 New Expense                         │
├─────────────────────────────────────────┤
│  Date:          [2024-01-15 📅]         │
│  Account:       [Salary (Salary) ▼]     │  ← Only shows Dr accounts
│  Particulars:   [________________]      │
│  Amount:        [₹ ______]              │
│  Mode:          [Bank ▼]                │
│  Cheque No:     [______] (if cheque)    │
│                                         │
│        [Cancel]  [💾 Save Expense]      │
└─────────────────────────────────────────┘
```

### **4. Cashbook View**

**Page: Admin → Cashbook**

- Filters:
  - Date Range: [From: ___] [To: ___]
  - Account: [All ▼]
  - Mode: [All ▼]

- Display as table (similar to cb.xlsx):
  ```
  | Date       | Receipt Account | Particulars | Cash | Cheque | Total | Payment Account | Particulars | Cash | Cheque | Total | Balance |
  |------------|-----------------|-------------|------|--------|-------|-----------------|-------------|------|--------|-------|---------|
  | 2024-01-15 | Patients        | Consultation| 500  | -      | 500   | -               | -           | -    | -      | -     | 15500   |
  | 2024-01-16 | -               | -           | -    | -      | -     | Electricity     | Bill        | 800  | -      | 800   | 14700   |
  ```

- Export: [📊 Export to Excel]

### **5. Ledger View**

**Page: Admin → Accounts → [Select Account] → View Ledger**

- Header:
  ```
  Account: Patients (IncOther)
  Opening Balance: ₹ 12,000 (Cr)
  Period: 2024-04-01 to 2025-03-31
  ```

- Display as table (similar to ld.xlsx):
  ```
  | Date       | Description              | Ref | Debit | Credit | Balance |
  |------------|--------------------------|-----|-------|--------|---------|
  | 2024-04-01 | Opening Balance          | -   | -     | -      | 12000   |
  | 2024-04-15 | Consultation - Mr. Kumar | 125 | -     | 500    | 12500   |
  | 2024-04-22 | Treatment - Mrs. Sharma  | 138 | -     | 1500   | 14000   |
  ```

- Export: [📊 Export to Excel]

---

## ⚙️ Backend Implementation

### Service: `app/services/account_service.py`

```python
from datetime import date
from database.db_manager import db

# ── Account Management ────────────────────────────────────────

def create_account(society_id: int, data: dict) -> tuple[bool, str, int]:
    """Create new account in chart of accounts."""
    try:
        result = db._execute(
            """
            INSERT INTO accounts (
                society_id, ac_no, name, tab_name, header, parent_account_id,
                drcr_account, drcr_bf, bf_amount, bf_year, depreciation_percent
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                society_id,
                data['ac_no'],
                data['name'],
                data.get('tab_name'),
                data.get('header'),
                data.get('parent_account_id', 0),
                data['drcr_account'],
                data.get('drcr_bf', data['drcr_account']),
                data.get('bf_amount', 0),
                data.get('bf_year'),
                data.get('depreciation_percent', 0)
            ),
            fetch_one=True
        )
        
        return True, f"Account '{data['name']}' created", result['id']
    except Exception as e:
        return False, str(e), 0


def get_accounts_for_receipt(society_id: int) -> list:
    """Get all Cr accounts (income/receipt accounts)."""
    return db._execute(
        """
        SELECT id, ac_no, name, tab_name, header
        FROM accounts
        WHERE society_id = %s AND drcr_account = 'Cr' AND active = TRUE
        ORDER BY name
        """,
        (society_id,),
        fetch_all=True
    ) or []


def get_accounts_for_expense(society_id: int) -> list:
    """Get all Dr accounts (expense/payment accounts)."""
    return db._execute(
        """
        SELECT id, ac_no, name, tab_name, header
        FROM accounts
        WHERE society_id = %s AND drcr_account = 'Dr' AND active = TRUE
        ORDER BY name
        """,
        (society_id,),
        fetch_all=True
    ) or []


# ── Receipt & Expense Recording ───────────────────────────────

def record_receipt(society_id: int, data: dict, created_by: int) -> tuple[bool, str]:
    """Record a receipt (credit to society)."""
    try:
        # Validate account is Cr type
        account = db._execute(
            "SELECT drcr_account FROM accounts WHERE id=%s AND society_id=%s",
            (data['acc_id'], society_id),
            fetch_one=True
        )
        
        if not account or account['drcr_account'] != 'Cr':
            return False, "Invalid account selected (must be a Credit account)"
        
        db._execute(
            """
            INSERT INTO transactions (
                society_id, trx_date, acc_id, acc_particulars,
                amount, mode, cheque_no, status, created_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'paid', %s)
            """,
            (
                society_id,
                data.get('trx_date', date.today()),
                data['acc_id'],
                data['acc_particulars'],
                data['amount'],
                data.get('mode', 'cash'),
                data.get('cheque_no'),
                created_by
            )
        )
        
        return True, f"Receipt of ₹{data['amount']:,.2f} recorded"
    except Exception as e:
        return False, str(e)


def record_expense(society_id: int, data: dict, created_by: int) -> tuple[bool, str]:
    """Record an expense (debit from society)."""
    try:
        # Validate account is Dr type
        account = db._execute(
            "SELECT drcr_account FROM accounts WHERE id=%s AND society_id=%s",
            (data['acc_id'], society_id),
            fetch_one=True
        )
        
        if not account or account['drcr_account'] != 'Dr':
            return False, "Invalid account selected (must be a Debit account)"
        
        db._execute(
            """
            INSERT INTO transactions (
                society_id, trx_date, acc_id, acc_particulars,
                amount, mode, cheque_no, status, created_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'paid', %s)
            """,
            (
                society_id,
                data.get('trx_date', date.today()),
                data['acc_id'],
                data['acc_particulars'],
                data['amount'],
                data.get('mode', 'cash'),
                data.get('cheque_no'),
                created_by
            )
        )
        
        return True, f"Expense of ₹{data['amount']:,.2f} recorded"
    except Exception as e:
        return False, str(e)


# ── Cashbook & Ledger Queries ─────────────────────────────────

def get_cashbook(society_id: int, start_date=None, end_date=None) -> list:
    """Get cashbook with running balance."""
    # (implementation as shown above)
    pass


def get_ledger(society_id: int, account_id: int, start_date=None, end_date=None) -> list:
    """Get ledger for specific account."""
    # (implementation as shown above)
    pass
```

---

## 🔄 Integration Points

### **1. Payments → Transactions**

When a payment (due) is verified/paid, create a transaction:

```python
# In app/services/payment_service.py

def verify_payment(payment_id: int, society_id: int, transaction_data: dict):
    """Mark payment as verified and record in cashbook."""
    
    # Get payment details
    payment = db._execute(
        "SELECT * FROM payments WHERE id=%s AND society_id=%s",
        (payment_id, society_id),
        fetch_one=True
    )
    
    # Update payment status
    db._execute(
        "UPDATE payments SET status='verified', paid_at=NOW() WHERE id=%s",
        (payment_id,)
    )
    
    # Record in transactions (cashbook)
    # Find appropriate account based on payment_type
    account_map = {
        'maintenance': 'Maintenance',
        'late_fee': 'Late Fee',
        'fine': 'Penalty'
    }
    
    account = db._execute(
        """
        SELECT id FROM accounts 
        WHERE society_id=%s AND name=%s AND drcr_account='Cr'
        """,
        (society_id, account_map.get(payment['payment_type'], 'Maintenance')),
        fetch_one=True
    )
    
    if account:
        db._execute(
            """
            INSERT INTO transactions (
                society_id, trx_date, acc_id, entity_id, acc_particulars,
                amount, mode, status
            ) VALUES (%s, NOW()::date, %s, %s, %s, %s, %s, 'paid')
            """,
            (
                society_id,
                account['id'],
                payment.get('apartment_id') or payment.get('user_id'),
                f"Payment #{payment_id} - {payment['payment_type']}",
                payment['amount'],
                transaction_data.get('payment_method', 'online')
            )
        )
    
    return True, "Payment verified and recorded"
```

### **2. Gate Pass Fees → Receipts**

If gate pass has a fee:

```python
def issue_gate_pass(user_id, society_id, pass_data):
    """Issue gate pass and record fee if applicable."""
    
    # Create gate pass
    # ...
    
    # If there's a fee
    if pass_data.get('fee_amount', 0) > 0:
        # Find "Gate Pass Fee" account
        account = db._execute(
            """
            SELECT id FROM accounts 
            WHERE society_id=%s AND name LIKE '%Gate Pass%' AND drcr_account='Cr'
            """,
            (society_id,),
            fetch_one=True
        )
        
        if account:
            # Record receipt
            db._execute(
                """
                INSERT INTO transactions (
                    society_id, trx_date, acc_id, entity_id,
                    acc_particulars, amount, mode, status
                ) VALUES (%s, NOW()::date, %s, %s, %s, %s, 'cash', 'paid')
                """,
                (
                    society_id,
                    account['id'],
                    user_id,
                    f"Gate pass fee - {pass_data['pass_type']}",
                    pass_data['fee_amount']
                )
            )
```

---

## 📝 Summary of Changes

### **What Changes:**

1. **transactions table**:
   - Add `acc_id INTEGER REFERENCES accounts(id)` - MANDATORY
   - Add `cheque_no VARCHAR(50)`
   - Update `mode` to include 'crypto'
   - Remove redundant `acc_code`

2. **New table: accounts**:
   - Complete implementation as specified above

3. **New service: account_service.py**:
   - Account CRUD
   - Receipt/Expense recording
   - Cashbook query
   - Ledger query

4. **Updated: payment_service.py**:
   - When payment verified → create transaction in cashbook

### **What Stays Same:**

- All existing services continue to work
- payments table unchanged (for dues tracking)
- All current UI flows remain functional

---

## 🎯 Implementation Checklist

- [ ] **Database Migration**
  - [ ] Create accounts table
  - [ ] Alter transactions table (add acc_id, cheque_no)
  - [ ] Seed default accounts (Balance, Capital, Income, Expense)

- [ ] **Backend Services**
  - [ ] Create account_service.py
  - [ ] Update payment_service.py (verify_payment integration)
  - [ ] Update crud_service.py (if needed)

- [ ] **UI Implementation**
  - [ ] Account Master List (admin/settings)
  - [ ] Account Create/Edit Form
  - [ ] Receipt Entry Form (with account dropdown)
  - [ ] Expense Entry Form (with account dropdown)
  - [ ] Cashbook View (dual-column layout)
  - [ ] Ledger View (account-wise)

- [ ] **Callbacks**
  - [ ] Register account_callbacks.py
  - [ ] Update drilldown_callbacks.py (add account routes)

- [ ] **Testing**
  - [ ] Create sample accounts
  - [ ] Record sample receipts
  - [ ] Record sample expenses
  - [ ] Verify cashbook balance calculation
  - [ ] Verify ledger balance calculation

---

## 🚀 Next Steps

Would you like me to:

1. **Create the database migration script** (SQL file to run)?
2. **Implement account_service.py** with all functions?
3. **Update ENTITY_META** in drilldown_callbacks.py for accounts/receipts/expenses?
4. **Create the Receipt/Expense entry forms** in the UI?

Let me know which part you'd like me to tackle first!
