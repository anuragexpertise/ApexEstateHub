# ICAI build recon — `accounts` foreign keys and `audit_events` columns

Source: `database/estatehub.sql` (read statically; the local scratch Postgres was
not available in this environment, so `pg_constraint` could not be queried live
— see PROGRESS.md). Columns below are the real column names from the schema.

## Foreign keys referencing `accounts`

| FK constraint | Table | Column(s) | References | On delete |
|---|---|---|---|---|
| `fk_account_parent` | `accounts` | `(society_id, parent_account_id)` | `accounts(society_id, id)` | `SET NULL` |
| (asset class account) | `fixed_asset_register` | `(society_id, acc_id)` | `accounts(society_id, id)` | — |
| | `fixed_asset_register` | `(society_id, sale_acc_id)` | `accounts(society_id, id)` | — |
| | `investments` | `(society_id, acc_id)` | `accounts(society_id, id)` | — |
| | `investments` | `(society_id, sale_acc_id)` | `accounts(society_id, id)` | — |
| | `event_items` | `(society_id, account_id)` | `accounts(society_id, id)` | — |
| | `receipts` | `(society_id, acc_id)` | `accounts(society_id, id)` | — |
| | `receipts` | `(society_id, interest_acc_id)` | `accounts(society_id, id)` | — |
| `fk_bank_lines_account` | `bank_lines` | `(society_id, bank_acc_id)` | `accounts(society_id, id)` | `SET NULL` |
| | `receivable_entries` | `(society_id, acc_id)` | `accounts(society_id, id)` | — |
| | `repeating_charges` | `(society_id, acc_id)` | `accounts(society_id, id)` | — |
| | `fund_transfer` | `(society_id, fund_acc_id)` | `accounts(society_id, id)` | — |
| | `fund_transfer` | `(society_id, expense_acc_id)` | `accounts(society_id, id)` | — |
| | `fund_transfer` | `(society_id, fund_acc_id)` | `accounts(society_id, id)` | `CASCADE` |
| | `fund_transfer` | `(society_id, bank_acc_id)` | `accounts(society_id, id)` | `CASCADE` |
| | `expense_claims` | `(society_id, ...)` | `accounts(society_id, id)` | — |
| | `expense_claims` | `(society_id, to_fund_acc_id)` | `accounts(society_id, id)` | — |
| `fk_fy_closure_reserve_acc` | `fy_closures` | `(society_id, reserve_acc_id)` | `accounts(society_id, id)` | `SET NULL` |
| `fk_fy_closure_contra_acc` | `fy_closures` | `(society_id, contra_acc_id)` | `accounts(society_id, id)` | `SET NULL` |
| | `receivable_entries` | `(society_id, acc_id)` | `accounts(society_id, id)` | — |
| | `transactions` | `(society_id, acc_id)` | `accounts(society_id, id)` | — |
| | `brought_forward` | `(society_id, acc_id)` | `accounts(society_id, id)` | `CASCADE` |
| | `concern_bids` | `(society_id, ...)` | `accounts(society_id, id)` | — |
| | `concern_bids` | `(society_id, ...)` | `accounts(society_id, id)` | — |
| `fk_primary_bank_account` | `societies` | `(id, primary_bank_account_id)` | `accounts(society_id, id)` | — |

The two tables the C4 guards touch are `transactions` (`acc_id`) and
`brought_forward` (`acc_id`) — those are the "ledger or brought-forward"
references in `trg_accounts_guard`.

## `audit_events` columns

| Column | Type | Notes |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `society_id` | INT | REFERENCES societies(id) ON DELETE SET NULL |
| `actor_id` | INT | REFERENCES users(id) ON DELETE SET NULL |
| `actor_role` | VARCHAR(20) | |
| `action` | VARCHAR(60) NOT NULL | |
| `resource_type` | VARCHAR(60) NOT NULL | |
| `resource_id` | VARCHAR(64) | |
| `before_value` | JSONB | |
| `after_value` | JSONB | |
| `reason` | TEXT | |
| `source` | VARCHAR(30) NOT NULL DEFAULT 'app' | CHECK: app / seed / sql / migration / import / system |
| `correlation_id` | UUID | |
| `permission_used` | VARCHAR(60) | |
| `policy_version` | VARCHAR(20) | |
| `document_hash` | VARCHAR(128) | |
| `approval_ref` | VARCHAR(100) | |
| `ip_address` | VARCHAR(45) | |
| `created_at` | TIMESTAMP NOT NULL DEFAULT NOW() | |

Existing app code inserts `audit_events` with explicit `actor_id` (server-resolved,
never the browser auth-store — see `app/security/audit_context.py`). The DB-level
`trg_accounts_audit` trigger reads the actor from session variables
`current_setting('app.actor_id', TRUE)` / `current_setting('app.actor_role', TRUE)`,
falling back to NULL when no actor is bound (e.g. seed). The app is expected to
SET those variables per request.

## Assumptions carried into the C4 triggers

- `trg_accounts_guard`: a referenced account = any `transactions` or
  `brought_forward` row with the same `(society_id, id)`. DELETE and changes to
  `id` / `drcr_account` / `parent_account_id` are refused; everything else
  (including `is_active`) is allowed.
- `trg_accounts_audit`: fires AFTER INSERT/UPDATE/DELETE on `accounts`; one
  row per write with `to_jsonb(OLD)` / `to_jsonb(NEW)` as before/after.
- `trg_transactions_active_account`: BEFORE INSERT on `transactions`; rejects
  only when the target account's `is_active = FALSE`. Headers/hybrids are not
  rejected; FY closure is not consulted.
