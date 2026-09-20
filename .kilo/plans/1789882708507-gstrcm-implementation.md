# Implementation Plan: GST Reverse Charge Mechanism (RCM)

## Context

Implement self-invoiced GST liability on payments to unregistered contractors, advocates, GTA services, and other notified categories under RCM (Indian GST Notification No. 13/2017-Central Tax (Rate)). The design specification is in `GSTRCM.md`.

## Scope

Three phases, ordered by dependency:

- **Phase A** — Database schema + SQL functions (foundation)
- **Phase B** — Application layer integration (expense form, vendor autofill, save handler)
- **Phase C** — Exports/compliance (GSTR export extension + new RCM export)

---

## Phase A: Database Schema & SQL Functions

### A1. Schema changes (`database/estatehub.sql`)

**A1a. Add `rcm_applicable` column to `expenses` table** (GSTRCM.md Data Model §1)
- `ALTER TABLE expenses ADD COLUMN rcm_applicable BOOLEAN DEFAULT FALSE;`
- Location: after `tds_section` column (~line 673) in existing `CREATE TABLE expenses`

**A1b. Add `rcm_category` column to `vendors` table** (GSTRCM.md Data Model §3)
- `ALTER TABLE vendors ADD COLUMN rcm_category VARCHAR(50);`
- Location: after `gstin` column (~line 207) in existing `CREATE TABLE vendors`

**A1c. Create `rcm_liability` table** (GSTRCM.md Data Model §2)
- Full DDL as specified in the design note
- Place near end of schema definitions, before the function sections

### A2. New SQL functions (`database/estatehub.sql`)

**A2a. Modify `fn_save_expense`** — add two params:
- `p_rcm_applicable BOOLEAN DEFAULT FALSE`
- `p_rcm_category VARCHAR DEFAULT NULL`
- When `p_rcm_applicable = TRUE` and expense is `confirmed`:
  - Call `fn_compute_rcm_liability(p_society_id, p_expense_id)` → get CGST/SGST amounts
  - Call `fn_post_rcm_liability(p_society_id, p_expense_id, p_cgst, p_sgst)` → insert rcm_liability row + post journal entries
- Journal entries follow `fn_asset_gst_disposal_liability` pattern but with Dr Expense (ITC claimable) instead of Dr GST Cost

**A2b. Create `fn_compute_rcm_liability(p_society_id INT, p_expense_id INT)`**
- Returns: `{taxable_value, cgst_amount, sgst_amount}`
- Looks up expense amount, vendor's rcm_category (or expense form selection)
- Determines applicable GST rate from category mapping (GTA=5%, Advocate=18%, etc.)
- Resolves CGST/SGST payable accounts via `fn_resolve_gst_accounts`
- Returns 0 amounts if no RCM applicable or no accounts configured

**A2c. Create `fn_post_rcm_liability(p_society_id INT, p_expense_id INT, p_cgst NUMERIC, p_sgst NUMERIC)`**
- Inserts into `rcm_liability` table with category, taxable_value, cgst_amount, sgst_amount, liability_date
- Posts two journal entries (same journal_id as expense):
  - Dr Expense Account / Cr CGST Payable (RCM)
  - Dr Expense Account / Cr SGST Payable (RCM)
- Uses defensive name-resolution for accounts (same pattern as fn_dispose_asset)

### A3. Update `test/fake_db.py`

Add fake implementations for:
- `_fn_compute_rcm_liability` — returns dummy `{taxable_value: 0, cgst_amount: 0, sgst_amount: 0}`
- `_fn_post_rcm_liability` — no-op returning success

---

## Phase B: Application Layer Integration

### B1. Field configuration (`app/utils/field_config.py`)

**B1a. Add RCM fields to `expenses` entity** (GSTRCM.md Implementation §B)
- `rcm_applicable`: visible=ADMIN_MASTER, editable=ADMIN_ONLY, default=False
- `rcm_category`: visible=ADMIN_MASTER, editable=ADMIN_ONLY, default=""

**B1b. Add RCM field to `vendors` entity** (GSTRCM.md Implementation §B)
- `rcm_category`: visible=ADMIN_MASTER, editable=ADMIN_ONLY, default=""

### B2. Schema introspection (`app/dash_apps/drilldown/schema_introspect.py`)

**B2a. Add `_NEW_FORM_DEFAULTS` entries for expenses**:
- `rcm_applicable: False`
- `rcm_category: ""`

**B2b. Add boolean field handling for `rcm_applicable`** in the introspection dynamic field builder — when column is boolean, render as select with options ["true", "false"] (already handled at line 598-600, no change needed).

**B2c. Ensure `rcm_category` renders as a select with dynamic options** — add an `elif` branch for `(table, name) == ("expenses", "rcm_category")` or `("vendors", "rcm_category")` with static options: `["gta", "advocate", "arbitration", "sponsorship", "government", "director", "insurance", "recovery", "other"]`.

### B3. Expense save callback (`app/dash_apps/callbacks/drilldown_callbacks.py`)

**B3a. Modify `_save_expense_v3`**:
- Extract `rcm_applicable` and `rcm_category` from form data `d`
- Pass them as additional params to `fn_save_expense` call
- Extend the SQL call signature from 14 params to 16 params:
  ```
  SELECT * FROM fn_save_expense(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
  ```
- New params at end: `p_rcm_applicable`, `p_rcm_category`

**B3b. Vendor autofill logic** (GSTRCM.md Implementation §B):
- In `_save_user_entity` vendor save path OR in a dedicated vendor save handler:
  - When vendor is saved with `rcm_category` set, subsequent expense form should auto-check `rcm_applicable` and prefill `rcm_category`
- Implementation: Add logic in `_save_expense_v3` that queries vendor's `rcm_category` when `entity_id` (vendor) is set and `rcm_applicable` is not explicitly set:
  ```python
  if not d.get("rcm_applicable") and vendor_id:
      v_rcm = db._execute("SELECT rcm_category FROM vendors WHERE id=%s", (vendor_id,), fetch_one=True)
      if v_rcm and v_rcm.get("rcm_category"):
          d["rcm_applicable"] = True
          d["rcm_category"] = v_rcm["rcm_category"]
  ```

### B4. Test updates (`test/test_scenario_gst_summary.py` or new test file)

- Test `_save_expense_v3` with RCM fields → verifies RCM params passed to fn_save_expense
- Test vendor autofill → selecting RCM vendor auto-checks RCM on expense form

---

## Phase C: Exports & Compliance

### C1. Extend `database/gst_export.py`

**C1a. Add RCM liability section** to `generate_gst_summary_excel`:
- New sheet "RCM Liability" showing monthly RCM liabilities
- Or extend Summary sheet with RCM totals row
- Data source: `SELECT * FROM rcm_liability WHERE society_id = p_society_id AND liability_date BETWEEN ...`

### C2. Create `database/rcm_export.py` (new file)

Per GSTRCM.md §C, implement three reports:
1. **Monthly RCM Liability Register** — all RCM entries for a given month with vendor details
2. **Vendor-wise RCM Summary** — aggregated by vendor with total taxable value, CGST, SGST
3. **ITC Claimed vs GST Paid Reconciliation** — compare ITC entries against RCM GST payable entries

Follow the same `generate_rcm_excel(db, society_id, month)` signature pattern as `generate_gst_summary_excel`.

### C3. Wire RCM export into dispatch (`app/dash_apps/callbacks/drilldown_callbacks.py`)

**C3a. Add export dispatch entry** (~line 2484 area):
```python
elif entity == "rcm_liability":
    data = rcm_export.generate_rcm_excel(None, sid, fy)
    filename = f"RCMLiability_FY{fy}-{fy+1}.xlsx"
```

**C3b. Add UI button** (`app/dash_apps/drilldown/renderers.py` near line 3690):
```python
dbc.Button([html.I(className="fas fa-file-excel me-2"), "Export RCM Liability"],
    id={"type": "btn-fy-export", "entity": "rcm_liability"}, ...)
dcc.Download(id={"type": "fy-export-trigger", "entity": "rcm_liability"})
```

### C4. Add RCM Liability Register card to GST Reports (`app/dash_apps/drilldown/renderers.py` or admin callbacks)

- Add "RCM Liability Register" card to the GST reports section
- Show current month's RCM liability total with "Mark GSTR Filed" action button
- The "Mark GSTR Filed" action updates `rcm_liability.gstr_filed = TRUE` for the month

---

## Files to Modify

| File | Change | Phase |
|------|--------|-------|
| `database/estatehub.sql` | Add columns, table, 3 functions, modify fn_save_expense | A |
| `app/utils/field_config.py` | Add rcm_applicable + rcm_category to expenses & vendors | B |
| `app/dash_apps/drilldown/schema_introspect.py` | New form defaults, select options for rcm_category | B |
| `app/dash_apps/callbacks/drilldown_callbacks.py` | _save_expense_v3 RCM params + vendor autofill + export dispatch | B+C |
| `app/dash_apps/drilldown/renderers.py` | RCM export button + RCM register card | C |
| `database/gst_export.py` | Extend with RCM sheet/section | C |
| `database/rcm_export.py` | NEW — RCM export module | C |
| `test/fake_db.py` | Add _fn_compute_rcm_liability, _fn_post_rcm_liability | A |
| `test/test_scenario_gst_summary.py` | Add RCM tests | B |

---

## Verification Plan

1. **SQL functions**: Run `fn_compute_rcm_liability` and `fn_post_rcm_liability` against test data — verify liability amounts and journal entry posting
2. **Expense save**: Create expense with RCM checkbox → verify `rcm_liability` row inserted and journal entries posted with correct Dr/Cr legs
3. **Vendor autofill**: Create vendor with `rcm_category='advocate'` → create expense for that vendor → verify RCM auto-checked
4. **GSTR export**: Run `generate_gst_summary_excel` → verify RCM sheet present with correct amounts
5. **RCM export**: Run `generate_rcm_excel` → verify all three reports present with correct aggregation
6. **Balance Sheet**: Verify GST Payable accounts include RCM amounts

## Open Questions (carry over from design note)

1. RCM category selection is manual (checkbox + vendor pre-classification) — no auto-detection from account code
2. ITC claimed in same month as RCM liability (per Rule 36)
3. Same CGST/SGST payable accounts used for RCM and regular GST — tracking via `rcm_liability` table
4. Phase 1: full invoice RCM or not (no partial RCM)
5. No integration with `fn_auto_generate_receivables` (different side — expense vs income)
