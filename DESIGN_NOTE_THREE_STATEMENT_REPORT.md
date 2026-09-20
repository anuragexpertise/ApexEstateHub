# Design Note: Three-Statement Financial Report (P2 Item 1)

## Objective
Generate three statutory financial statements required for registered society annual filing:
1. **Receipts & Payments Account** (Cash basis)
2. **Income & Expenditure Account** (Accrual basis)
3. **Balance Sheet** (Position statement)

---

## Current State Analysis

The existing `fn_fy_closing_report` function already produces a consolidated closing tree with:
- Opening balances (brought_forward)
- Current period transactions (receipts, expenses, receivables accruals, payables)
- Closing balances per account
- Derived net surplus/deficit

This data is **already correct and tested** — we must **reuse** it rather than re-derive from raw transactions.

---

## Proposed Design

### 1. New SQL Functions (in `database/estatehub.sql`)

#### `fn_receipts_payments_fy(p_society_id INT, p_fy INT)`
Returns a table with columns:
```sql
line_type      VARCHAR -- 'Opening', 'Receipt', 'Payment', 'Closing'
account_code   INT
account_name   VARCHAR
dr_amount      NUMERIC(15,2)
cr_amount      NUMERIC(15,2)
```

**Logic:**
- Start with `fn_fy_closing_report` opening balances (Dr/Cr)
- Add all **cash/bank receipts** (mode in cash, cheque, upi, card, bank, crypto) as Receipt lines (Cr to income accounts, Dr to cash/bank)
- Add all **cash/bank expenses** as Payment lines (Dr to expense accounts, Cr to cash/bank)
- Include journal entries marked `mode='journal'` as internal transfers
- End with closing balances from `fn_fy_closing_report`

**Key distinction from Income & Expenditure:**
- Only actual cash/bank movements (no accruals, no receivables/payables)
- `mode='journal'` entries excluded (they're book entries, not cash)

---

#### `fn_income_expenditure_fy(p_society_id INT, p_fy INT)`
Returns a table with columns:
```sql
statement_section VARCHAR -- 'Income', 'Expenditure', 'Surplus/Deficit'
account_code      INT
account_name      VARCHAR
amount            NUMERIC(15,2)
```

**Logic:**
- **Income**: All accounts under Income & Expenditure branch (tab='InExp' and drcr='Cr') 
  - Include receivables accruals (fn_auto_generate_receivables posts to income accounts)
  - Include confirmed receipts credited to income accounts
- **Expenditure**: All accounts under Income & Expenditure branch (tab='InExp' and drcr='Dr')
  - Include confirmed expenses debited to expense accounts
  - Include payables verified (salary, etc.)
  - Include depreciation journal (Dr Depreciation / Cr Asset)
- **Surplus/Deficit**: Total Income - Total Expenditure

**Reuse:** Pull net movement per account from `fn_fy_closing_report` and classify by account tab/drcr.

---

#### `fn_balance_sheet_fy(p_society_id INT, p_fy INT)`
Returns a table with columns:
```sql
statement_section VARCHAR -- 'Assets', 'Liabilities', 'Equity'
account_code      INT
account_name      VARCHAR
amount            NUMERIC(15,2)
```

**Logic:**
- **Assets**: All accounts with drcr='Dr' on Balance Sheet branch (tab NOT 'InExp')
  - Cash-in-hand, Bank, Sundry Debtors, Fixed Assets, Investments, Loans & Advances Given
- **Liabilities**: All accounts with drcr='Cr' on Balance Sheet branch
  - Sundry Creditors, Sinking Fund, Repair Fund, Corpus Fund, Loans Taken, Provisions
- **Equity**: Capital Account + Current Year Surplus/Deficit (from Income & Expenditure)

**Reuse:** Directly use closing balances from `fn_fy_closing_report`.

---

### 2. Python Export Module (new file: `database/financial_statements_export.py`)

Following the pattern of `database/income_tax_export.py` and `database/asset_export.py`:

```python
def export_receipts_payments(db, society_id: int, fy: int, format: str = "xlsx") -> bytes:
    """Generate Receipts & Payments Account export."""
    
def export_income_expenditure(db, society_id: int, fy: int, format: str = "xlsx") -> bytes:
    """Generate Income & Expenditure Account export."""
    
def export_balance_sheet(db, society_id: int, fy: int, format: str = "xlsx") -> bytes:
    """Generate Balance Sheet export."""
    
def export_all_three_statements(db, society_id: int, fy: int) -> bytes:
    """Generate combined workbook with three sheets."""
```

Each export:
- Calls the corresponding SQL function
- Formats as structured Excel with proper headers
- Includes society name, FY period, generation timestamp
- Uses existing `export_utils` for styling/number formatting

---

### 3. UI Integration

**Location:** Add a new "Financial Statements" card under the **Drilldown → Reports** section (alongside existing "Trial Balance", "FY Closing Report", "26Q Export").

**Card config** (in `app/dash_apps/drilldown/registry.py`):
```python
"financial_statements": {
    "label": "Financial Statements",
    "icon": "fas fa-file-invoice-dollar",
    "color": "#2c3e50",
    "entity": "reports",
    "requires": ["admin"],
    "handler": "financial_statements_export",
}
```

**Callback** (in `app/dash_apps/callbacks/drilldown_callbacks.py`):
- FY selector dropdown (reuse existing FY picker pattern)
- Format selector (xlsx / pdf)
- "Generate" button → triggers export → returns file download

---

### 4. Data Flow Summary

```
User selects FY → clicks Generate
       ↓
Python calls fn_receipts_payments_fy / fn_income_expenditure_fy / fn_balance_sheet_fy
       ↓
Each SQL function queries fn_fy_closing_report + classifies by account.tab / drcr
       ↓
Python formats results → Excel workbook (3 sheets) → file download
```

---

### 5. Implementation Order

1. **Add three SQL functions** to `estatehub.sql` (alongside `fn_fy_closing_report`)
2. **Create `database/financial_statements_export.py`** with three export functions
3. **Register card** in `drilldown/registry.py` and `drilldown/card_catalogue.py`
4. **Add callback** in `drilldown_callbacks.py` for the export handler
5. **Test** against seeded demo data (FY 2026)

---

### 6. Open Questions / Decisions Needed

1. **Should journal entries (`mode='journal'`) appear in Receipts & Payments?**
   - **Recommendation**: No — they're non-cash. But show as a memo note at bottom.

2. **Format of Receipts & Payments — single column or Dr/Cr columns?**
   - **Recommendation**: Traditional two-column (Receipts left / Payments right) format per ICAI guidance.

3. **Include schedules/notes?**
   - **Phase 1**: No — just the three statements. Schedules can be Phase 2.

4. **FY period display format?**
   - **Recommendation**: "1 April 2026 – 31 March 2027" (standard Indian FY format).

---

### 7. Dependencies

- `fn_fy_closing_report` must be working correctly (already is)
- Account chart structure (tab_name, drcr_account) must be accurate (already is)
- Brought-forward balances must be seeded (already is)

---

### 8. Testing Checklist

- [ ] Receipts & Payments opening + closing balances match
- [ ] Income & Expenditure surplus = Balance Sheet equity movement
- [ ] Balance Sheet balances (Assets = Liabilities + Equity)
- [ ] Cross-verification with `fn_cashbook_paired_v3` cash/bank totals
- [ ] Demo society (FY 2026) produces plausible numbers