# ApexEstateHub — Functional Audit & Test Plan
Repo audited: `github.com/anuragexpertise/ApexEstateHub` (HEAD at time of audit, Aug 14 2026)
Method: static cross-reference of every layout-defined `id=` against every `Input()`/`clientside_callback` reference in `app/dash_apps/callbacks/*.py`, plus manual review of `DEFAULT_LAYOUTS` (KPI-per-tab source of truth) and push-notification call sites.

---

## 1. Critical findings — dead/unwired buttons

These elements exist in the layout with `n_clicks`/click handlers expected, but **no callback in the entire codebase listens to them.** Clicking does nothing.

| Button / control | Portal · Tab | File | Impact |
|---|---|---|---|
| `master-create-society-btn` ("Create Society") | Master · Dashboard | `portal_pages.py:280` | Master admin cannot onboard a new society from the UI at all — the entire "Create Society" form (also check `new-society-name`, `new-society-email`, `new-society-password`, `master-create-result` — none referenced either) is decorative. |
| `master-clear-btn` ("Clear") | Master · Dashboard | `portal_pages.py:281` | Minor — form-clear convenience only. |
| `poll-clear-btn` ("Clear") | Admin/Owner · Polls | `poll_page.py:139` | Minor — form-clear convenience only. |
| `drill-back-btn` (drilldown "Back") | All portals · any drilldown | `app_shell.py:798` | Users can drill into a KPI's list/profile but the dedicated Back control does not navigate back (breadcrumb-based nav may still work — needs live check). |
| `close-forgot-modal` ("Cancel") | Login (all portals) | `login_system.py:321` | "Forgot password" modal's Cancel button doesn't close the modal. |
| `close-reset-modal` ("Cancel") | Login (all portals) | `login_system.py:353` | "Reset password" modal's Cancel button doesn't close the modal. |
| `channel-create-btn` ("Create Channel") + its **entire form** (`channel-name-input`, `channel-identifier-input`, `channel-type-input`, `channel-apartment-input`, `channel-recurring-switch`) | Admin/Owner/Security · Channels | `renderers.py:3293-3327` | **The whole "Create Channel" feature (bus/taxi/visitor channel provisioning) is non-functional.** No callback in `channel_callbacks.py` (or anywhere else) reads these inputs or handles the click. This is the single biggest gap found — Channels is otherwise a fully built subscribe/approve workflow, but there's no way to originate a channel from the UI. |

**Note on method:** the diff is a static one-callback-file scan, so it will not catch dynamic string-built ids or ids matched only via pattern-matching `dict` ids (`{"type": ..., "index": ...}`) — those were excluded to avoid false positives. Treat this list as "confirmed dead," not "the complete list of every bug."

---

## 2. KPI-per-tab audit

Your requirement — *"each tab must have at least one logical KPI"* — checked against `DEFAULT_LAYOUTS` in `card_catalogue.py`, the single source of truth read by `_kpi_row_dynamic()`.

**Result: 2 tabs currently ship with zero KPIs:**

| Portal | Tab | Current KPIs | Suggested fix |
|---|---|---|---|
| Owner | `cashbook` | `[]` (empty) | Add `kpi_receipts_month` / `kpi_expenses_month` (own transactions) — mirrors what `security.cashbook` already does with `kpi_receipts_month`, `kpi_expenses_month`. |
| Vendor | `cashbook` | `[]` (empty) | Add `kpi_receipts_total` (vendor's own receipts) or a vendor-scoped payables figure — mirrors `vendor.vendor_receipts` pattern. |

Every other tab across all five portals (Master, Admin, Owner, Vendor, Security — 33 tabs total) has at least one KPI wired. Full tab inventory:

- **Master:** dashboard (10 KPIs), master-settings (1)
- **Admin:** dashboard (9), enroll (3), financials (9), events (2), concerns (2), polls (2), assets (2), receipts (4), expenses (4), settings (6), channels (3)
- **Owner:** dashboard (7), channels (3), financials (4), receivables (2), cashbook (**0**), owner_receipts (1), charges (2), concerns (2), events (2), polls (2), settings (1)
- **Vendor:** dashboard (5), financials (2), vendor_passes (1), vendor_receipts (1), cashbook (**0**), concerns (3), charges (2), events (1), settings (1)
- **Security:** dashboard (3), payables (1), cashbook (4), security_receipt (1), security_receipts (1), security_events (1), security_concerns (2), security_channels (5), pass_evaluation (2), settings (1)

---

## 3. Push notification wiring — where it fires and where it's silent

Confirmed push call sites (`push_service.py` / `send_push`) exist in:
`assign_to_callbacks.py`, `concern_bid_callbacks.py`, `invite_to_callbacks.py`, `poll_callbacks.py`, `drilldown_callbacks.py`, `alert_service.py`.

**Gap:** `channel_callbacks.py` has **no** push call site. Even once §1's Create-Channel button is wired up, subscribed apartment owners won't get a push when a new bus/taxi channel is created or when a channel is approved — only the in-app list will change on next poll/refresh. Worth deciding if that's intentional (channels are opt-in browse/subscribe, not push-worthy) or a gap to close alongside the button fix.

`noc_callbacks.py` and `receipt_callbacks.py` (print/PDF/email actions) correctly have no push wiring — that's expected, those are pull-on-demand actions, not events.

---

## 4. Suggested real-world test scenarios

Organized as end-to-end flows a real housing society would actually run, spanning multiple portals so the cross-portal data flow (and push notifications) get exercised, not just isolated screens.

### Scenario A — New society onboarding (currently blocked by §1)
1. Master logs in → Dashboard → **Create Society** (blocked today — flag as P0 before further master-portal testing).
2. Once fixed: create society with a plan tier, verify `kpi_societies_total`/`kpi_societies_free` increment and the correct plan-tier KPI (`kpi_societies_9apts` etc.) increments.
3. Bulk-enroll 10 apartments + 2 vendors + 3 security staff via Admin → Enroll (CSV upload) → confirm `kpi_apartments_total`, `kpi_vendors_total`, `kpi_security_total` update and rollback behavior holds if one row in the CSV is malformed (per your existing rollback logic).

### Scenario B — Dues → Receipt → Ledger loop
1. Owner portal: check `kpi_my_pending_dues` on Dashboard.
2. Admin creates a receipt against that owner (Receipts tab) → status should be `pending` for non-admin actors, `confirmed` for admin/master per your existing logic.
3. Verify → Post the receipt (`fn_verify_receipt`) → confirm `kpi_receipts_total`, `kpi_cash_in_hand`/`kpi_bank_balance` move, and the owner's `kpi_my_pending_dues` drops on next login.
4. Pull Financials → FY Closing Report for the current FY and confirm the receipt shows up under the right Dr/Cr side (this is the area flagged in your own notes as still using the legacy `drcr_account` column in some functions — good candidate to specifically stress-test given the known pre-existing bug).

### Scenario C — Concern lifecycle with push
1. Owner raises a concern (Concerns tab) → Admin assigns it to a Vendor → **confirm vendor receives push** (assign_to_callbacks.py path).
2. Vendor bids or accepts (concern_bid_callbacks.py) → confirm Admin/Owner sees status flip through `invited → bid_submitted → assigned → resolved → closed`.
3. Vendor marks resolved → Owner/Admin closes → confirm `kpi_concerns_not_closed` decrements on both Admin and Owner dashboards, and `kpi_concerns_resolved` on Vendor's.

### Scenario D — Gate pass / QR flow
1. Owner or Vendor opens their signed QR pass (`show-qr-btn` — confirmed wired).
2. Security scans it (`qr-validate-btn`) → confirm `fn_evaluate_gate_pass` respects the `vendors.active` check and rejects a deactivated vendor's pass.
3. Confirm `kpi_gate_logs` updates on the relevant dashboards and a gate-log profile entry is created with the right `entity_id`.

### Scenario E — Channels (bus/taxi subscription) — blocked by §1
Once the Create Channel button is wired: Admin creates a "DPS Bus #12" channel → Owners in the linked apartments subscribe → Security's Channels tab shows it under `kpi_channels_pending_bus` until approved → approve → confirm it moves to `kpi_channels_active` and (decide per §3) whether subscribers get a push.

### Scenario F — Login edge cases
1. Trigger "Forgot password" → confirm reset email/token flow works, then click Cancel (**currently broken**, `close-forgot-modal`) — verify it at least doesn't crash, and file as a UX bug even though it's non-blocking.
2. Same for "Reset password" → Cancel (`close-reset-modal`).
3. Exercise account lockout: 5 failed logins → confirm `locked_until`/`failed_login_attempts` actually locks the account, then confirm it unlocks after the timeout.

### Scenario G — Financial Year close
1. Run Admin → Financials → FY Closing Report for a completed FY.
2. Cross-check the Balance Sheet total against a manual sum from the ledger for at least one Dr and one Cr account, specifically targeting the six functions your own notes flag as still deriving from `accounts.drcr_account` instead of per-transaction `entry_side` (`fn_accounts_list`, `fn_account_profile`, `v_financial_trial_balance`, `fn_trial_balance`, `fn_balance_sheet`, `fn_account_ledger_fy`) — this is the most likely place real numbers will be wrong under a mixed-transaction-direction test case.

---

## 5. Suggested priority order

1. **P0** — `channel-create-btn` + form (feature is entirely inaccessible).
2. **P0** — `master-create-society-btn` (blocks all onboarding testing downstream).
3. **P1** — Owner/Vendor `cashbook` empty KPI tabs.
4. **P2** — `drill-back-btn`, modal Cancel buttons (`close-forgot-modal`, `close-reset-modal`), `poll-clear-btn`, `master-clear-btn` — all minor UX, none data-integrity-affecting.
5. **P2** — decide + implement (or explicitly skip) push notification on channel creation/approval.

This list is a static-analysis pass, not a substitute for actually clicking through each portal in a running instance — recommend running Scenarios A–G against a seeded test DB to confirm these findings and catch anything the grep-based cross-reference couldn't (pattern-matching `dict` ids, JS-only wiring in `app/static`, etc.).
