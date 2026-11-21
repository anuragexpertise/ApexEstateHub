# 05 Audit-trail and control design (Task 5)

**Rule label:** `general accounting principle` unless an ICAI paragraph is cited; ICAI audit documents were not obtained, so findings are `unverified against source text`.

## 5.1 Immutability of posted accounts

| # | Question | Answer | Evidence |
|---|----------|--------|----------|
| F-05-1 | Can an account that has postings be deleted, renumbered, or have its nature changed? | No enforced prevention found; accounts are admin-only create/edit but no immutability guard on accounts with postings. | `estatehub.sql:351`–`395` `accounts` table has no `is_active`/`is_deleted` column and no check preventing edits on posted accounts. `app/security/audit_context.py` and `app/security/service_guard.py` log edits but do not block them. |
| F-05-2 | Is there an active/inactive flag? | No. There is no `is_active` column on `accounts`. | `estatehub.sql:351`–`404` — no active/inactive column. |

**Proposed change:** add `is_active BOOLEAN DEFAULT TRUE` (or `status`) to `accounts`; block delete/renumber/nature-change when postings exist (check `transactions`/`expenses`/`receipts` for the acc_id). Soft-deprecate instead of hard delete.

**Migration impact:** existing accounts stay active; no data migration. New societies get the flag.

## 5.2 Change history

| # | Question | Answer | Evidence |
|---|----------|--------|----------|
| F-05-3 | Is every chart edit logged (who, when, before/after) through `audit_context`? | Partially — some edits write `audit_events` directly, but there is no centralized chart-of-accounts audit trigger guaranteeing before/after for every edit. | `app/security/audit_context.py` provides `get_current_user_id`/`get_current_society_id`; `service_guard.audit_event` writes rows; no account-specific trigger found. |

**Proposed change:** add a DB trigger on `accounts` (UPDATE/DELETE) writing `audit_events` with before/after, actor, society, time. Route all account edits through `service_guard.audit_event`.

**Migration impact:** none.

## 5.3 Per-society divergence

| # | Question | Answer | Evidence |
|---|----------|--------|----------|
| F-05-4 | Are accounts copied per society? Can a society's chart drift from the seed? Is there a check? | Yes — `seed_accounts` inserts per society (`accounts.id` scoped per `society_id`, `estatehub.sql:353`–`354`). No check that a society's chart matches the seed. | `seed_accounts` `database/seed.py:1407` inserts per society; `accounts` PK is `(society_id, id)`. |

**Proposed change:** add a periodic/on-demand check comparing each society's `accounts` rows to the seed `ACCOUNTS` (ids, names, drcr, has_bf, parent) and report drift.

**Migration impact:** none.

## 5.4 Control accounts tie to sub-ledgers

| # | Control | Answer | Evidence |
|---|---------|--------|----------|
| F-05-5 | Sundry Debtors ties to apartment-wise arrears (`arrears_tie`) | Yes — `bf_controls.three_controls` `arrears_tie` compares `debtors_dr` to `arrears_total`. | `bf_controls.py:64`–`68`. |
| F-05-6 | What ties Sundry Creditors to vendor-wise payables? | No equivalent control found; no `creditors_tie` comparing Sundry Creditors to vendor-wise payables. | Searched `bf_controls.py` — only `balanced`, `funds_backed`, `arrears_tie`. |
| F-05-7 | What ties funds to earmarked assets (`funds_backed`)? | Partially — `funds_backed` compares `fund_cr` to `bank_dr` (funds covered by bank/cash/deposits). | `bf_controls.py:59`–`63`. |

**Proposed change:** add `creditors_tie` control comparing Sundry Creditors (`2240`) to vendor-wise payables; strengthen `funds_backed` to tie each fund to its earmarked assets.

**Migration impact:** none.

## 5.5 Completeness — trial balance and statement coverage

| # | Question | Answer | Evidence |
|---|----------|--------|----------|
| F-05-8 | Does a trial balance always sum to zero across the whole chart? | The `balanced` control requires `dr == cr` only over declared BF accounts, not the full posted ledger. No whole-chart trial-balance check found. | `bf_controls.py:53`–`58`. |
| F-05-9 | Does any account reach no statement line? | Yes — several accounts have no mapping (e.g. `1340` ITC RCM to `OTHER_ASSETS` is present but some income/expense leaves lack clear R1/R2 lines); see `03_mapping.csv` rows marked N/A. | `docs/coa_audit/03_mapping.csv`. |

**Proposed change:** add a whole-ledger trial-balance test (sum of all `transactions` Dr = Cr per society); ensure every postable account maps to exactly one statement line per format.

**Migration impact:** none.

## 5.6 Comparatives

| # | Question | Answer | Evidence |
|---|----------|--------|----------|
| F-05-10 | Does Brought Forward plus the chart support prior-period figures (R1 requires comparatives)? | Partially — `brought_forward` carries opening balances per account per FY (`seed_brought_forward` `database/seed.py:1776`), so prior-year closing = current-year opening. Comparatives across multiple locked years depend on `fy_lock_service` and the ledger chain. | `brought_forward` table; `fy_lock_service.py`. |

**Proposed change:** confirm `fn_fy_close` rolls each `has_bf` account forward as the next FY's opening balance; verify comparatives render for each statement line.

**Migration impact:** none.

## 5.7 Creditors — MSME vs other dues

| # | Question | Answer | Evidence |
|---|----------|--------|----------|
| F-05-11 | Can the creditors balance be split into MSME and other dues (ICAI requirement on delayed MSME payments)? | No — Sundry Creditors (`2240`) is a single account with no MSME/other split. | `seed.py:315` `(2240, "Sundry Creditors", ...)`; no MSME flag on vendors or creditors. |

**Proposed change:** add an MSME indicator on vendors and a creditors ageing split (MSME vs other) in the Balance Sheet / creditors report.

**Migration impact:** new vendor field; existing vendors default to non-MSME.

## 5.8 Period lock

| # | Question | Answer | Evidence |
|---|----------|--------|----------|
| F-05-12 | Does `fy_lock_service` stop postings to a closed year, including to accounts added later? | Yes — `fn_lock_fy` is enforced in the database; the service re-runs the preview server-side and anchors before locking. | `fy_lock_service.py:59`–`111`; `fn_lock_fy` in `estatehub.sql`. Accounts added later inherit the lock because the lock is on the year, not the account. |

**Proposed change:** confirm (test) that posting to any account in a locked year is rejected, including newly added accounts.

**Migration impact:** none.
