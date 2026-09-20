# Design Note: GST Reverse Charge Mechanism (RCM) (P2 Item 2)

## Objective
Implement self-invoiced GST liability on payments to unregistered contractors, advocates, GTA services, and other notified categories under RCM.

---

## Current State
- No RCM handling exists in the codebase
- Regular GST is applied via `fn_auto_generate_receivables` on maintenance charges
- Expense GST (ITC) is not currently tracked on purchase side

---

## RCM Trigger Categories (Indian GST Law)

Based on Notification No. 13/2017-Central Tax (Rate) and subsequent amendments, RCM applies to:

| Category | Service Provider | GST Rate | Notes |
|----------|------------------|----------|-------|
| **GTA (Goods Transport Agency)** | Unregistered transporter | 5% (2.5% CGST + 2.5% SGST) / 12% | If society pays freight |
| **Advocate / Legal Services** | Individual advocate / firm | 18% | Legal fees paid to advocates |
| **Arbitral Tribunal** | Arbitrator | 18% | |
| **Sponsorship Services** | Any person | 18% | |
| **Government Services** | Govt. dept (except renting) | 18% | |
| **Director Services** | Director to company | 18% | Sitting fees |
| **Insurance Agent** | Individual agent | 18% | Commission |
| **Recovery Agent** | Recovery agent | 18% | |
| **Transport of Goods by Vessel** | Unregistered | 5% | |
| **Renting of Immovable Property** | Govt. to registered person | 18% | |

**For housing societies, most relevant:**
1. **GTA Services** — society pays freight for materials/equipment
2. **Advocate Fees** — legal cases, bye-law drafting
3. **Arbitration** — dispute resolution
4. **Sponsorship** — event sponsorships paid to unregistered vendors

---

## Data Model Changes

### 1. New Column on `expenses` table
```sql
ALTER TABLE expenses ADD COLUMN rcm_applicable BOOLEAN DEFAULT FALSE;
```
- Set TRUE when expense falls under RCM category
- UI: checkbox on expense form (admin only), default FALSE

### 2. New Table: `rcm_liability`
```sql
CREATE TABLE rcm_liability (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    expense_id INT REFERENCES expenses(id) ON DELETE SET NULL,
    vendor_id INT REFERENCES vendors(id) ON DELETE SET NULL,
    rcm_category VARCHAR(50) NOT NULL, -- 'gta', 'advocate', 'arbitration', 'sponsorship', 'other'
    taxable_value NUMERIC(12,2) NOT NULL,
    cgst_amount NUMERIC(12,2) NOT NULL,
    sgst_amount NUMERIC(12,2) NOT NULL,
    liability_date DATE NOT NULL,
    gstr_filed BOOLEAN DEFAULT FALSE,
    gstr_filed_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    created_by INT REFERENCES users(id)
);
```

### 3. New Column on `vendors` table (optional)
```sql
ALTER TABLE vendors ADD COLUMN rcm_category VARCHAR(50); -- NULL = not RCM
```
- Pre-classify vendors at master data level
- Auto-populate expense form when vendor selected

---

## Posting Logic (Mirroring `fn_asset_gst_disposal_liability` Pattern)

When an RCM-applicable expense is **confirmed** (status='confirmed'):

```
Dr  Expense Account (e.g., Legal Fees)     ₹100,000
Cr  Cash/Bank                               ₹100,000

-- RCM Liability (self-invoice):
Dr  Expense Account (same as above)         ₹18,000  (ITC claimable)
    Cr  CGST Payable (RCM)                   ₹9,000
    Cr  SGST Payable (RCM)                   ₹9,000
```

**Key difference from asset disposal:**
- Asset disposal: Dr GST Disposal / Cr Asset (no ITC)
- RCM: Dr Expense (ITC) / Cr GST Payable — **ITC is claimable** in same month

---

## Implementation Approach

### Phase A: SQL Functions (in `database/estatehub.sql`)

#### `fn_compute_rcm_liability(p_society_id INT, p_expense_id INT)`
- Called from `fn_save_expense` when `p_rcm_applicable = TRUE`
- Returns: `{cgst_amt, sgst_amt, cgst_acc_id, sgst_acc_id}`
- Looks up vendor's RCM category or uses expense form selection
- Resolves CGST/SGST payable accounts (reuse `fn_resolve_gst_accounts`)

#### `fn_post_rcm_liability(p_society_id INT, p_expense_id INT, p_cgst NUMERIC, p_sgst NUMERIC)`
- Inserts into `rcm_liability` table
- Posts journal entries:
  - Dr Expense Account (ITC) / Cr CGST Payable
  - Dr Expense Account (ITC) / Cr SGST Payable
- Same journal_id as the expense for traceability

### Phase B: Expense Form Integration

**Form changes** (in `app/utils/field_config.py`):
```python
"rcm_applicable": {
    "visible": ADMIN_MASTER,
    "editable": ADMIN_ONLY,
    "default": False,
    "validation": {},
    "tooltip": "Reverse Charge Mechanism applicable — society pays GST directly to govt",
},
"rcm_category": {
    "visible": ADMIN_MASTER,
    "editable": ADMIN_ONLY,
    "default": "",
    "validation": {},
    "tooltip": "RCM category: gta, advocate, arbitration, sponsorship, other",
},
```

**Autofill**: When vendor selected, if vendor.rcm_category is set, auto-check rcm_applicable and fill category.

### Phase C: Exports / Compliance

#### GSTR-1 / GSTR-3B Export
- Add RCM liability section to existing `database/gst_export.py`
- RCM liability appears in:
  - GSTR-3B: Table 3.1(d) — Inward supplies liable to RCM
  - GSTR-1: Not applicable (B2B only, but RCM is reported by recipient)

#### New Export: `database/rcm_export.py`
- Monthly RCM liability register
- Vendor-wise RCM summary
- ITC claimed vs. GST paid reconciliation

---

## UI Surface

1. **Expense Form**: RCM checkbox + category dropdown (admin only)
2. **Vendor Master**: RCM category field (admin only) — pre-classify known RCM vendors
3. **Reports → GST**: Add "RCM Liability Register" card
4. **Monthly Compliance Dashboard**: Show RCM liability for the month with "Mark GSTR Filed" action

---

## Open Questions / Decisions Needed

1. **Should RCM be auto-detected from account code (tds_section / account name) or manual?**
   - **Recommendation**: Manual checkbox + vendor pre-classification. Auto-detection is error-prone.

2. **ITC on RCM — claim in same month or next?**
   - **Law**: ITC can be claimed in same month RCM liability is discharged (Rule 36).
   - **Implementation**: Post ITC entry (Dr Expense / Cr GST Payable) in same journal as expense.

3. **Separate CGST/SGST payable accounts for RCM vs. regular?**
   - **Recommendation**: Use same accounts — liability is same nature. Add `rcm_liability` table for tracking.

4. **What about partial RCM (e.g., mixed invoice)?**
   - **Phase 1**: Full invoice RCM or not. Partial = separate expense lines.

5. **Integration with existing `fn_auto_generate_receivables`?**
   - **No overlap** — RCM is on **expense/purchase** side, receivables are **income/sales** side.

---

## Dependencies

- `fn_save_expense` — add `p_rcm_applicable`, `p_rcm_category` params
- `fn_resolve_gst_accounts` — reuse for CGST/SGST payable accounts
- Vendor master — add `rcm_category` column
- Expense form — add RCM fields
- GST exports — extend for RCM reporting

---

## Testing Checklist

- [ ] Create expense with RCM (GTA, Advocate) → liability posted correctly
- [ ] ITC entry appears in same journal (Dr Expense / Cr GST Payable)
- [ ] RCM liability register shows correct amounts
- [ ] GSTR-3B export includes RCM in Table 3.1(d)
- [ ] Balance Sheet: GST Payable includes RCM amounts
- [ ] Vendor pre-classification auto-fills RCM on expense form

---

## Priority Note

**This is a design note only — do not implement in this pass.** Flag back for prioritization against:
- GST annual return (GSTR-9) automation
- E-invoicing integration
- Multi-state GST compliance
- Existing Phase 4/5 TDS/GST work completion