# Security & Functional Review: Creation of Receipts by Admin

**Scope:** Admin-initiated receipt creation flow in Esatehub.
**Review type:** Security + functional code review (no implementation performed; plan only).
**Status:** Implementation-ready plan.

---

## 1. Context — How Receipt Creation Works Today

| Layer | File | Key function |
|-------|------|--------------|
| Page/UI | `app/dash_apps/drilldown/renderers.py` | `render_list_card()` → "New" button → `form_receipt_new` |
| Form submit | `app/dash_apps/callbacks/drilldown_callbacks.py` | `handle_form_submit()` → `_save_receipt_v3()` (line 4192) |
| Persistence | `database/estatehub.sql` | `fn_save_receipt()` (line 7588) |
| Permission gate | `app/dash_apps/drilldown/renderers.py` | `_perms_for(role, entity)` — `_PORTAL_PERMS` matrix |
| Authorization | `app/security/authorization.py` | `authorize()` — deny-by-default, `_MAKER_CHECKED` SoD |
| Session identity | `app/security/audit_context.py` | `get_current_user_id/role/society_id` (Flask-Login, server session) |
| Audit trail | `database/estatehub.sql` | `audit_events` table (line 2539) |

**Flow:** Admin clicks "New" on receipts list → form renders → submit → `handle_form_submit()` validates permissions via `_perms_for("admin","receipts")` → collects form data from `ctx.states` → `_save_receipt_v3(db, d, sid)` → calls `fn_save_receipt()` → inserts into `receipts` + `transactions` (if confirmed).

**Status logic in `fn_save_receipt`:** If `p_created_by` maps to an admin user → `status='confirmed'` (journal posted immediately). Otherwise → `status='pending'` (awaits "Verify & Post" by admin).

---

## 2. Security Findings

### F1 (Critical) — Client-controlled `user_id` drives auto-confirmation
`_save_receipt_v3` (drilldown_callbacks.py:4244) passes `d.get("user_id")` as `p_created_by` to `fn_save_receipt`. `fn_save_receipt` (estatehub.sql:7651-7658) queries `users WHERE id = p_created_by` to decide `v_is_admin` → confirmed vs pending.

**Risk:** If the receipt form exposes `user_id` as an editable or hidden field, a non-admin actor can set it to an admin's user ID and bypass the maker/checker workflow, getting the receipt auto-confirmed and journal-posted without any reviewer.

**Gap:** `_save_receipt_v3` never compares `d.get("user_id")` against the server-resolved `get_current_user_id()`. It trusts client-supplied form data for the security-critical `created_by` / `user_id` value.

### F2 (Critical) — Client-controlled `role` bypasses entity existence checks
`_save_receipt_v3` (line 4241) passes `d.get("role", "other")` as `p_role`. `fn_save_receipt` (estatehub.sql:7639-7649) validates `entity_id` existence against the role-specific table (`apartments`, `vendors`, `security_staff`, `assets`).

**Risk:** A malicious actor can set `role='other'` to skip entity existence validation entirely, or set a mismatched role to target an entity in another table (IDOR-adjacent). Since `role` also drives which table is checked, role spoofing can bypass tenant-scoped entity validation.

### F3 (Critical) — Client-controlled `mode` weakens cash-limit enforcement
`_save_receipt_v3` (line 4242) passes `d.get("mode", "cash")` as `p_mode`. `fn_save_receipt` calls `fn_check_cash_receipt_limit()` (estatehub.sql:7623) which enforces Income-tax Act s.186 / s.269ST (₹2,00,000 cash receipt limit).

**Risk:** Setting `mode='cheque'`/`'upi'`/`'bank'` avoids the cash-limit check entirely. A cash receipt could be misclassified as a non-cash mode to evade the statutory cash-receipt prohibition. The Python layer validates `mode` only against a CHECK constraint list, not against business legitimacy.

### F4 (High) — No maker/checker (SoD) enforcement for admin-created receipts
`fn_save_receipt` auto-confirms when `p_created_by` is an admin (status='confirmed', journal posted immediately). The `_MAKER_CHECKED` SoD guard in `authorization.py:413-414` (`FINANCE_POST` → maker cannot act on own item) is **not invoked** anywhere in the receipt save path. The SQL function performs both make and check in one call.

**Risk:** A single admin can create and confirm a receipt with no independent review — no separation of duties for money-in. This contradicts the capability model in `authorization.py` where `accountant` holds `FINANCE_RECEIPT_PREPARE` and `FINANCE_POST` separately, implying prepare/post should be separable.

### F5 (Medium) — No upper bound on receipt date
`_save_receipt_v3` (line 4223-4228) validates `receipt_date >= calc_start_date` but allows any future date.

**Risk:** Future-dated receipts can be used to manipulate cash-flow reporting, period cut-offs, or FY-closure figures. No "not later than today" guard.

### F6 (Medium) — Hardcoded amount ceiling, not society-configurable
`_save_receipt_v3` (line 4200) hardcodes `amt > 1,000,000` rejection.

**Risk:** Societies with different governance policies cannot set their own per-receipt ceiling. Limit is baked into code, not configurable via `societies` table or `master_rules`.

### F7 (Medium) — No duplicate receipt detection
No check for an existing receipt with the same `entity_id`, `amount`, `receipt_date`, and `particulars` within a short window.

**Risk:** Double-entry / duplicate receipts can be created accidentally or deliberately (e.g., re-submitting a form).

### F8 (Low) — Audit-event writing not verified for receipt creation
The code calls `_notify_receipt_saved()` (line 4255) but it is unclear whether `audit_events` receives a write for receipt creation. `audit_events` (estatehub.sql:2539) is append-only and should record creator, amount, account, status, and outcome.

**Risk:** If audit is not written, there is no tamper-evident trail of who created which receipt and when — critical for financial forensics and RERA/auditor compliance.

---

## 3. Functional Findings

### F9 — Receipt form field exposure needs audit
The receipt `form_receipt_new` is rendered by `renderers.py` via the drill-down form pipeline. Need to confirm which fields are rendered as editable vs hidden: `user_id`, `role`, `mode`, `acc_id`, `entity_id`, `cheque_no`, `transaction_id`, `source_reference`. Fields that are security-critical (`user_id`, `role`, `mode`) should be server-set or server-validated, not client-editable.

### F10 — Cash warning surfacing
`fn_save_receipt` returns `cash_warning` and `_save_receipt_v3` appends it to the success toast (line 4260-4261). In 'block' mode the exception prevents save; in 'warn' mode the receipt saves with a warning. Need to confirm the warning is prominently displayed and not dismissible without acknowledgment.

### F11 — Status lifecycle: pending → confirmed
Non-admin creators produce `status='pending'` receipts. Admin "Verify & Post" (profile_actions.py:301-309) confirms them. Need to confirm the verify path re-runs `fn_save_receipt` or a separate `fn_verify_receipt`, and that the verifier cannot be the same user who created (SoD).

### F12 — Role-based UI vs write-time enforcement mismatch
`_PORTAL_PERMS` shows `("accountant","receipts")`: `{"view","new"}` and `("admin","receipts")`: full CRUD. But `_save_receipt_v3` does not re-check `_perms_for` for the specific actor — it relies on `handle_form_submit`'s gate (drilldown_callbacks.py:2040-2105) which does check `_perms_for`. However, `_save_receipt_v3` itself is also callable from other code paths (e.g., bulk operations) that may not repeat the gate.

---

## 4. Recommendations

### R1 (Critical) — Server-set `created_by`; reject client-supplied `user_id`
In `_save_receipt_v3`, ignore `d.get("user_id")` and pass `get_current_user_id()` (server session) as `p_created_by`. If `d.get("user_id")` is present and differs from the current user, reject with an error (or log and override). Never trust client-supplied `user_id` for security decisions.

### R2 (Critical) — Server-validate `role` against actor's permitted roles
Do not pass `d.get("role")` directly to `fn_save_receipt`. Resolve the actor's role from the server session (`get_current_user_role()`) and map to an allowed receipt role set (`apartment`, `vendor`, `security`, `assets`, `other`). Reject mismatched or spoofed `role`.

### R3 (Critical) — Server-validate `mode` for cash-limit integrity
Restrict `mode` to a server-defined allowlist. If cash-limit enforcement (s.269ST) is required, do not allow the client to downgrade `cash` → `cheque/upi/bank` to evade the check. Consider deriving mode from the instrument actually used (cheque_no present → cheque, transaction_id present → upi/neft/rtgs/imp, otherwise cash).

### R4 (High) — Enforce maker/checker (SoD) for receipt confirmation
When an admin creates a receipt, set `status='pending'` and require a separate admin (or treasurer/accountant with `FINANCE_POST`) to "Verify & Post". Apply the `_MAKER_CHECKED` guard: `creator_user_id != verifier_user_id`. This aligns with the capability model (`FINANCE_RECEIPT_PREPARE` vs `FINANCE_POST`).

**Alternative:** Keep admin auto-confirm but document it as an explicit override requiring a second admin's countersignature via a separate verification action.

### R5 (Medium) — Bound receipt date to `[calc_start_date, today]`
Reject `receipt_date > today` (or allow a small grace period configured per society). Prevent future-dating.

### R6 (Medium) — Make amount ceiling society-configurable
Move the ₹1,000,000 ceiling to a society-level setting (e.g., `societies.max_receipt_amount` or `master_rules`). Default to ₹1,000,000 if unset.

### R7 (Medium) — Duplicate receipt detection
Before insert, check for an existing receipt with same `society_id`, `entity_id`, `amount`, `receipt_date`, `particulars` within N hours (configurable, default 24). Return a warning or block.

### R8 (Low) — Write audit_events for every receipt creation
Insert into `audit_events` (action='receipt_create', resource_type='receipts', resource_id=receipt_id, actor_user_id, society_id, before/after JSON, outcome, IP if available) inside `fn_save_receipt` or in `_save_receipt_v3` post-insert.

### R9 (Low) — Review `form_receipt_new` field visibility
Ensure `user_id`, `role`, `mode` are not editable by the client. Render them as read-only display fields or exclude from the form entirely; set them server-side in `_save_receipt_v3`.

---

## 5. Implementation Tasks (for implementation-capable agent)

1. **Audit form fields** — Inspect `renderers.py` receipt form rendering to confirm which fields (`user_id`, `role`, `mode`) are client-editable. Document findings.

2. **Patch `_save_receipt_v3`** — Replace `d.get("user_id")` with `get_current_user_id()`; validate `d.get("role")` against actor's server-resolved role; validate `d.get("mode")` against server allowlist; reject mismatches.

3. **Add SoD / pending-by-default** — Change admin-created receipts to `status='pending'` unless a separate verification action confirms. Implement creator != verifier check.

4. **Add date upper bound** — Reject `receipt_date > today`.

5. **Add duplicate detection** — Pre-insert check for same entity/amount/date/particulars within 24h.

6. **Add audit_events write** — Insert audit row on receipt create (and on verify/post).

7. **Add society-configurable amount ceiling** — Read from `societies` or `master_rules`, default ₹1,000,000.

8. **Add tests** — Extend `test/test_cash_receipt_limit_live.py`, `test/test_scenario_b_receipt_ledger.py`, or create `test/test_receipt_creation_security_live.py` covering: non-admin impersonation attempt, cash-limit evasion via mode spoofing, future-date rejection, duplicate detection, admin auto-confirm vs pending, audit write.

---

## 6. Validation Plan

| Test | Expected result |
|------|-----------------|
| Non-admin submits receipt with `user_id` = admin ID | Rejected or creator overridden to actual user; status = 'pending' |
| Receipt with `mode='cheque'` for a cash transaction | Accepted only if instrument evidence present; cash-limit logic not bypassable by mode alone |
| Receipt with future date | Rejected |
| Duplicate receipt (same entity/amount/date/particulars within 24h) | Rejected or warned |
| Admin creates receipt | Status = 'pending' (after R4) — requires separate verifier; creator cannot verify own receipt |
| Audit event present after receipt create | Row in `audit_events` with action='receipt_create' |
| Cross-society entity_id | Rejected by `fn_save_receipt` (existing F-01 guard) |
| Cash ≥ ₹2,00,000 in 'block' mode | Rejected by `fn_check_cash_receipt_limit` |

---

## 7. Open Questions (to resolve before implementation)

1. Should admin-created receipts remain auto-confirmed (status='confirmed') with a documented override, or switch to pending-by-default requiring a second admin's "Verify & Post"? — *Recommended: pending-by-default with SoD.*

2. Is `user_id` currently rendered as a field in `form_receipt_new`? If yes, remove it from the form and set server-side.

3. What is the desired duplicate-detection window (hours)? — *Recommended: 24 hours, configurable.*

4. Should the amount ceiling be per-society in `societies` table or in `master_rules`? — *Recommended: `societies.max_receipt_amount` NUMERIC.*

---

## 8. Files Affected

| File | Change |
|------|--------|
| `app/dash_apps/callbacks/drilldown_callbacks.py` | `_save_receipt_v3` — R1, R2, R3, R4, R5, R6, R7, R8 |
| `database/estatehub.sql` | `fn_save_receipt` — possibly move date/amount/duplicate/audit logic here or keep in Python |
| `app/dash_apps/drilldown/renderers.py` | `form_receipt_new` field visibility — R9 |
| `app/security/authorization.py` | Possibly expose `FINANCE_RECEIPT_POST` if splitting prepare/post |
| `test/test_receipt_creation_security_live.py` | New test file |

---

## 9. References

- `drilldown_callbacks.py:4192` — `_save_receipt_v3`
- `drilldown_callbacks.py:2040-2105` — `handle_form_submit` permission gate
- `estatehub.sql:7588-7719` — `fn_save_receipt`
- `estatehub.sql:7619-7626` — Cash receipt limit (s.269ST)
- `profile_actions.py:301-320` — Receipt profile actions (Verify & Post)
- `renderers.py:90-276` — `_PORTAL_PERMS` matrix
- `authorization.py:413-414` — `_MAKER_CHECKED` SoD guard
- `authorization.py:198-202` — Accountant capabilities (prepare/post)