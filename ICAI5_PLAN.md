# ICAI5 Plan: fix the export gate, make status honest, close ICAI4 leftovers

Basis: review of commit `4287db3` (22 Nov 2026). This plan is written from that review. Where a task names a file or function, confirm the exact location with a grep before editing.

## 0. Ground rules (apply to every task)

1. **Done means evidence.** A task is "done" in `PROGRESS.md` only when its done-when line is met and the test or command output is pasted next to it. Anything partly built is "partial", with the gap written beside it.
2. **One final report.** After ICAI5 there is exactly one `FINAL_REPORT`. Older ones are marked superseded at the top and point to it.
3. **No silent fallbacks.** No `except: return []`, no hard-coded zero standing in for a missing input. If an input is unknown, the code raises or the gate says "cannot verify".
4. **Tests encode the correct behaviour**, not the current behaviour. A test that passes because the bug exists is itself a bug.
5. **Money stays `Decimal`** via `database/money.py`.

## Phase A: correctness bugs in the export gate (do first)

### A1. Real declared arrears in `export_gate` (I6 regression)
- **Problem:** `export_gate` calls `bc.three_controls(totals, Decimal(0))`. `arrears_tie` passes only when brought-forward receivables are exactly 0, so any society with opening debtors is refused export.
- **Work:**
  - Add a function that returns the society's declared Apt-Arrears total for the FY (from the Apt-Arrears source the engine already uses; confirm which table or function holds it).
  - Pass that figure into `three_controls`.
  - If the figure cannot be read, the gate returns `cannot_verify` with the reason. It does not pass and does not substitute 0.
- **Tests:**
  - Rewrite `test_export_refuses_when_arrears_tie_fails`: use a fixture where debtors (5,000) and declared arrears are different non-zero numbers, and assert refusal.
  - Add `test_export_allows_when_arrears_tie`: debtors 5,000, declared arrears 5,000, export allowed.
  - Add `test_export_allows_zero_opening_debtors`: both 0, allowed.
  - Add `test_gate_cannot_verify_when_arrears_unreadable`.
- **Done when:** the four tests pass, and a live run on the seeded society with opening debtors exports successfully.

### A2. Fix inverted `fy_locked`
- **Problem:** `fy_locked = not can_lock` reports a year with blockers as locked, and may report a genuinely locked year as unlocked.
- **Work:**
  - Read the real lock state from `fy_locks` (via `fn_check_fy_lock` or a direct existence check).
  - Report three separate fields: `locked` (a row exists), `can_lock` (preview has no blockers), `blockers` (list).
  - Update every consumer of `fy_locked` (templates, JSON, tests).
- **Tests:** locked year; unlocked year with blockers; unlocked year with no blockers; each asserts all three fields.
- **Done when:** the three-case test passes and a live check against a year locked through the Treasurer screen returns `locked = true`.

### A3. Wire the gate into FY close (I6.2)
- **Problem:** the gate only calls `fn_fy_lock_preview`; FY close does not use it.
- **Work:**
  - Decide and record which checks block FY close (proposal: books balance, ledger chain verifies, arrears tie, creditors tie once A4 lands).
  - Call the shared gate from the FY close path in the service layer (not only in the UI), so no entry path skips it.
  - A blocked close returns the list of failed controls.
- **Tests:** close refused for each failing control; close allowed when all pass; idempotent second close still reports `already_closed`.
- **Done when:** tests pass and the decision is written into `DEPLOY.md` or the compliance section of the README.

### A4. Use `creditors_tie` and add the creditors split (I3.2, I3.5)
- **Work:**
  - Add the creditors split to `balance_sheet()` (as the plan for I3 specified).
  - Add `creditors_tie` to the gate's controls and to FY close (A3).
- **Tests:** creditors tie and not-tie fixtures; balance sheet shows the split and totals still equal.
- **Done when:** tests pass and the balance sheet on the seed still balances.

## Phase B: audit attribution

### B1. Set `app.actor_id` and `app.actor_role` per request (I8)
- **Problem:** nothing in `app/` sets them, so audit rows record NULL. The ICAI4 commit only documented this.
- **Work:**
  - In the DB access layer, at the start of each transaction, run `SELECT set_config('app.actor_id', %s, true), set_config('app.actor_role', %s, true)` with values from the server session (`app/security/audit_context.py`), never from `auth-store`.
  - `true` makes it transaction-local, which is correct for the pooler described in `DEPLOY.md` (transaction-scoped settings). Confirm it works on the NeonDB pooled endpoint.
  - Scheduled jobs set a fixed system actor (`system:<job>`).
- **Tests:**
  - Hermetic: the helper issues the `set_config` with the session's values.
  - Live: change one audited record, read back the audit row, assert actor id and role are not NULL and match the session. Repeat for one change per audited table.
- **Done when:** the live test shows one audit row per change with non-NULL actor, and the claim is recorded with the output.

## Phase C: data fixes

### C1. Apply the `3280` fix (I9)
- **Cause (credible per review):** `ILIKE 'Depreciation%' LIMIT 1` with no `ORDER BY` matches "Depreciation Fund".
- **Work:**
  - Replace the name lookup with the account's statutory mapping or fixed code, and add a deterministic order as a fallback.
  - Write a data-correction migration for the seed and a **reversal-based** correction for existing societies (the ledger is append-only: post a reversal journal, do not update rows). The ₹79,525 depreciation debit on the fund account is moved to the depreciation expense account.
  - Add a check query that lists any depreciation postings on fund accounts.
- **Tests:** depreciation posts to the depreciation account on a society that also has a "Depreciation Fund" account; the check query returns empty after the fix.
- **Done when:** the seed no longer has a depreciation debit on a fund account, statements still balance, and the fund balance is correct.

## Phase D: finish what ICAI4 marked done

### D1. I3: vendor MSME create, edit, profile UI
- Add fields to the vendor form and profile, validated server-side, saved by the existing `_save_vendor` handler.
- **Tests:** save round trip; invalid value refused; the profile shows the value.
- **Done when:** the form works end to end on the seeded database and the test passes.

### D2. I7: notes pages and Dash tile and callback tests
- Add the notes pages that use the existing notes generator.
- Add a real tile for the new pages to the relevant `DEFAULT_LAYOUTS` entry. The "6 Statements tile" cited before was pre-existing, so it does not count.
- Add callback tests that render the tile and the notes page, and that `@require_session` is present (`scripts/check_callback_guards.py`).
- **Done when:** a layout file actually changed, tests pass, and the callback guard script exits 0.

### D3. I8: TDS completeness test and F-22 decision
- Add the TDS completeness test the plan asked for (every payment type that can carry TDS resolves a section or is explicitly exempt).
- Record an explicit decision on F-22: restore or drop, with the reason, in `PROGRESS.md`. "Not restored" without a decision is not enough.
- **Done when:** the test passes and the decision is written.

## Phase E: access control and deployment documentation

### E1. Role gating on the new routes
- Decide whether `auditor` and `adviser` should read the statements routes. Proposal: `auditor` yes (read-only is the purpose of that portal); `adviser` only through the existing masked export path, so no.
- Record the decision.
- Move the routes from coarse role checks to the `policy.py` capability check (`can(...)`), keeping the tenant-isolation hard deny and the master `society_id` rule.
- **Tests:** allowed and denied for each of accountant, auditor, adviser, admin, master (valid and invalid society), vendor, apartment.
- **Done when:** the matrix test passes.

### E2. `DEPLOY.md` and `render.yaml`
- Add a table: each environment variable the code reads (see README section 22), whether it is in `render.yaml`, and what is missing.
- Add the missing variables to `render.yaml`. Secrets are declared with `sync: false`, never given values.
- Confirm the host naming is consistent (the README says ApexWeave and NeonDB; `render.yaml` suggests Render). State which is current and what the other file is for.
- **Done when:** the table has no "unknown" cells.

## Phase F: honest status

### F1. Reset `PROGRESS.md`
- Re-grade every ICAI4 item (I1 to I9) as done / partial / not done, each with evidence. Start with I3, I7 and I8, which were marked done wrongly.
- Mark open items in the same row as the status, so the file cannot contradict itself.

### F2. One final report
- Write `docs/icai_build/FINAL_REPORT_ICAI5.md` at the end.
- Mark `FINAL_REPORT.md` and `FINAL_REPORT_ICAI4.md` as superseded at the top; correct the F-23 and F-25 lines in the old report or point to the new one.
- The report lists only what the evidence supports. Anything unverified is listed as unverified.

## Order and dependencies

1. A1, A2 (independent, small, highest user impact: A1 blocks real societies).
2. A4, then A3 (A3 uses the creditors control).
3. B1 and C1 in parallel.
4. D1, D2, D3.
5. E1, E2.
6. F1, F2 last.

## Exit criteria for ICAI5

- Hermetic suite passes; live suite passes on a fresh seeded database (new tests included).
- `scripts/check_callback_guards.py`, `scripts/inventory_endpoints.py --check` and `scripts/build_scheme_sql.py --check` exit 0; new endpoints are classified in `docs/authz_manifest.json`.
- Export works for a society with opening debtors and is refused when the arrears or creditors tie genuinely fails.
- `fy_locked` agrees with `fy_locks` in a live check.
- Audit rows carry actor id and role in a live check.
- No depreciation posting sits on a fund account.
- `PROGRESS.md` and the single final report agree with each other and with the evidence.

## Not in scope (stay open, stated plainly)

Per-society gap-free voucher series, the cash-count screen, guarding `payables` and `receivables`, 26AS reconciliation, and independent assurance remain open items in the README and are not touched here.
