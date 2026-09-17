# Action System Columns — Save Handler Audit

Ensure all action timestamp and actor columns (`created_at`, `updated_at`, `confirmed_at`, `disposed_at`, `last_printed_at`, `last_emailed_at`, `results_announced_at`, `reminder_sent_at`, `created_by`, `updated_by`, `confirmed_by`, `disposed_by`, `revoked_by`, `resolved_by`, etc.) are correctly stamped at the right moment by the Python save handlers.

---

## Findings

### ✅ Already Correct — No Changes Needed

| Handler / Entity | Action Columns | Where stamped |
|---|---|---|
| `fn_save_receipt` (SQL) | `confirmed_by`, `confirmed_at`, `created_by`, hash chain | SQL function — correct |
| `fn_save_expense` (SQL) | `confirmed_by`, `confirmed_at`, `created_by` | SQL function — correct |
| `fn_pay_apartment_dues_fifo` (SQL) | `confirmed_by`, `confirmed_at` | SQL function — correct |
| `fn_dispose_asset` (SQL) | `disposed_by`, `disposed_at` | SQL function — correct |
| `fn_declare_results` (SQL) | `results_announced_at`, `updated_at` | SQL function — correct |
| `fn_close_poll` (SQL) | `updated_at` | SQL function — correct |
| `receipt_callbacks.py` | `last_printed_at`, `last_emailed_at` | Already stamped on print/email action |
| `expense_callbacks.py` | `last_printed_at`, `last_emailed_at` | Already stamped on print/email action |
| `noc_callbacks.py` | `last_printed_at`, `last_emailed_at` | Already stamped on print/email action |
| `agreement_callbacks.py` | `last_printed_at`, `last_emailed_at` | Already stamped on print/email action |
| `scheduler.py` | `reminder_sent_at` | Stamped after push send — correct |
| `_save_concern` (new) | `created_by`, `created_at` in INSERT | Correct |
| `_save_concern` (edit) | `updated_by` via `_upd_by_clause` | Correct |
| `_save_apt_charge` | `created_by` (INSERT), `updated_by` (UPDATE) | Correct |
| `_save_ven_charge` | `created_by` (INSERT), `updated_by` (UPDATE) | Correct |
| `_save_user_entity` (apartment/vendor/security) | `created_by` on INSERT; `updated_by` on UPDATE | Correct |
| `_save_account` | `created_by` (INSERT), `updated_by` (UPDATE) | Correct |
| `_save_asset` (edit) | `updated_by`, `disposed_by`, `disposed_at` passed from form | Correct |
| `_save_asset` (new via fn_buy_asset) | `created_by` via `user_id` param | Correct |
| `_save_gate_log` | `created_by` | Correct |
| `_get_or_create_active_noc` | `created_by` | Correct |
| `_get_or_create_agreement` | `created_by` | Correct |
| `_upsert_brought_forward` | `created_by`, `updated_by` | Correct |
| `_save_patrol_location` (new) | `created_by` via `get_current_user_id()` | Correct |
| `loaders.py` (assign/close/resolve concern) | `resolved_by`, `closed_by`, `updated_at=NOW()` in SQL | Correct |
| `loaders.py` (delete entity actions) | `updated_by` | Correct |

---

### ❌ Issues Found — Fixes Required

#### 1. `_save_patrol_location` — edit branch missing `updated_by`

**Table:** `patrol_locations`  
**Columns available in schema:** `created_by`, `created_at` (no `updated_at`/`updated_by` in schema — no trigger either)  
**Problem:** The UPDATE branch doesn't stamp anything.  
**Fix:** `patrol_locations` has no `updated_by`/`updated_at` columns — no fix needed to SQL, but the comment in code should note it.

> [!NOTE]
> `patrol_locations` has no `updated_at`/`updated_by`. No change required.

---

#### 2. `_save_society` — both master and admin branches missing `updated_by`

**Table:** `societies`  
**Schema:** `societies` has `created_at` with `DEFAULT CURRENT_TIMESTAMP` but **no `updated_by`/`updated_at`** columns.  
**Fix:** No schema column to stamp. No change required.

> [!NOTE]
> `societies` table has no `updated_by`/`updated_at` columns. No change required.

---

#### 3. `_save_security_roster` — edit branch missing `updated_by`

**Table:** `security_roster`  
**Schema columns:** `assigned_by`, `created_at`, `created_by` — **no `updated_at`/`updated_by`**  
**Fix:** No schema column to stamp. No change required.

---

#### 4. `_save_tds_rate` — no `updated_by`/`updated_at` in either branch

**Table:** `tds_section_rates`  
**Schema columns:** `created_at` — **no `updated_at`, `updated_by`, `created_by`**  
**Fix:** No schema columns to stamp. No change required.

---

#### 5. `_save_compliance_settings` — `updated_at=NOW()` present but **no `updated_by`**

**Table:** `society_compliance_settings`  
**Schema columns:** `created_at`, `updated_at` — **no `updated_by`, `created_by`**  
**Status:** `updated_at=NOW()` already stamped in `_save_compliance_settings`. No `updated_by` column in schema.  
**Fix:** No change required.

---

#### 6. `_save_event` — edit branch missing `updated_by`

**Table:** `events`  
**Schema columns:** `created_at`, `updated_at` (via trigger `trg_events_updated`), `created_by`, **`updated_by`**  
**Problem:** The UPDATE query in `_save_event` (is_edit branch) does NOT include `updated_by=%s`.  
**Fix:** Add `updated_by=%s` to the UPDATE SET clause, passing `d.get("user_id")`.

---

#### 7. `poll_callbacks.save_poll` — edit branch missing `updated_by`

**Table:** `polls`  
**Schema columns:** `created_by`, `updated_at`, **`updated_by`** (line 1216)  
**Problem:** `fn_edit_poll` (SQL) and `save_poll` (Python) do not stamp `updated_by`.  
**Fix:** Update `fn_edit_poll` in `estatehub.sql` to accept and set `updated_by`. Update `save_poll` in `poll_callbacks.py` to pass `user_id`.

---

#### 8. `poll_callbacks.save_poll` — create branch missing stamping of `created_at`

**Table:** `polls`  
**Status:** `fn_create_poll` already handles `created_by`. Checking now...

Actually `fn_create_poll` is called with `user_id` as second arg. ✅ Correct.

---

#### 9. `event_ticket_callbacks` / `fn_sell_event_ticket` — `last_printed_at`/`last_emailed_at`

**Table:** `event_ticket_items`  
**Schema columns:** `last_printed_at`, `last_emailed_at`  
**Problem:** `event_ticket_callbacks.py` mentions these columns in its module docstring but it's unclear if print/email callbacks stamp them. Need to verify.

---

#### 10. `qr_reissue_callbacks.py` — `revoked_by` on vendor_passes

**Table:** `vendor_passes`  
**Schema columns:** `revoked_by`  
**Need to verify:** Does the revoke action stamp `revoked_by`?

---

## Proposed Changes

### ► [MODIFY] [drilldown_callbacks.py](file:///home/at/Documents/ApexEstateHub/app/dash_apps/callbacks/drilldown_callbacks.py)

#### `_save_event` — add `updated_by` to edit UPDATE

```python
# BEFORE (line ~4775)
"UPDATE events SET title=%s, description=%s, event_date=%s, "
f"event_time=%s, venue=%s, open_to=%s, account_id=%s, "
f"ticket_name=%s, ticket_price=%s, ticket_name2=%s, ticket_price2=%s"
f"{_img_clause} "
"WHERE id=%s AND society_id=%s",

# AFTER — add updated_by=%s to SET
"UPDATE events SET title=%s, description=%s, event_date=%s, "
f"event_time=%s, venue=%s, open_to=%s, account_id=%s, "
f"ticket_name=%s, ticket_price=%s, ticket_name2=%s, ticket_price2=%s, "
f"updated_by=%s"
f"{_img_clause} "
"WHERE id=%s AND society_id=%s",
# + add d.get("user_id") to _img_param before (pk, sid)
```

---

### ► [MODIFY] [estatehub.sql](file:///home/at/Documents/ApexEstateHub/database/estatehub.sql)

#### `fn_edit_poll` — add `p_updated_by` parameter and stamp `updated_by`

```sql
-- BEFORE: fn_edit_poll(p_poll_id INT, p_society_id INT, ...)
-- AFTER:  fn_edit_poll(p_poll_id INT, p_society_id INT, ..., p_updated_by INT)
-- Add: updated_by = p_updated_by, updated_at = NOW() to UPDATE SET
```

---

### ► [MODIFY] [poll_callbacks.py](file:///home/at/Documents/ApexEstateHub/app/dash_apps/callbacks/poll_callbacks.py)

#### `save_poll` — pass `user_id` to `fn_edit_poll`

```python
# Pass user_id as the new p_updated_by arg to fn_edit_poll call
```

---

### ► [VERIFY] event_ticket_callbacks — `last_printed_at`/`last_emailed_at`

Inspect and fix if needed.

---

### ► [VERIFY] qr_reissue_callbacks — `revoked_by`

Inspect and fix if needed.

---

## Verification Plan

### Automated Tests
- Run `python3 database/reset_database.py --yes --after seed` to confirm schema is intact after changes.

### Manual Verification
- Edit an event → check `events.updated_by` is set in DB.
- Declare poll results → check `polls.results_announced_at` is set (already works via SQL function).
- Edit poll → check `polls.updated_by` is set.
- Print a receipt → check `receipts.last_printed_at` is set (already works).
