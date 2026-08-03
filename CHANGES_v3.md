# Concerns Workflow — Fixes Re-Applied Against Latest Repo (2026-08-02)

This bundle is rebuilt against the **current** `github.com/anuragexpertise/
ApexEstateHub/tree/master` (pulled fresh for this round), not the earlier
baseline. It preserves every change you'd made yourselves since the last
round and layers the remaining Concerns-workflow fixes on top of them.

## What I found already in your repo (kept as-is, not touched)
- `assign_to_callbacks.py` — you'd already taken the role/ownership check
  and the §2.7 auto-decline-losing-bidders logic I gave earlier and
  **rewrote them yourselves** using `db._conn()` + a cursor + `SELECT ...
  FOR UPDATE` row locking, so concurrent assign submissions on the same
  concern now serialize properly instead of racing. Genuinely better than
  what I'd given you — left completely alone, only added the stage-badge
  UI on top (see below).
- `concern_bid_callbacks.py` — you'd added a log line for when a bid
  notification is skipped because the concern was deleted. Kept as-is.
- `app_shell.py` (Invite-card restyle) and `qr_callbacks.py` (new QR concern
  lookup flow) — unrelated to the Concerns workflow review, not touched at
  all.
- `drilldown_callbacks.py` — you'd added a `kpi_concerns_assigned_admin`
  filter (3 lines, unrelated to anything in the review). Preserved exactly;
  all my other fixes were layered in around it.

## What was still missing (now applied)
Everything else from both prior rounds was **not** present in the repo —
`loaders.py`, `profile_actions.py`, `renderers.py`, `invite_to_callbacks.py`,
`estatehub.sql`, and `migrate.py` were all byte-identical to the original
pre-fix baseline, and the `vendor_resolve`/`close_concern`/`assign`/`invite`
action handlers in `drilldown_callbacks.py` were too. Re-applied:

- **§3.1** — role + ownership check on the `assign`/`invite` action
  handlers in `drilldown_callbacks.py` (the modal-open gate; the actual
  write-path check in `assign_to_callbacks.py` was already there per above)
- **§2.3/§2.8** — Security can now bid + resolve (button roles in
  `profile_actions.py`, generalized handler in `drilldown_callbacks.py`)
- **§2.9** — `fn_sync_concern_status` no longer lets leftover un-selected
  bidders block a concern from reaching `resolved`
- **§2.6** — ownership check on Assign/Invite for the Owner portal
- **§3.2** — "Assigned To Me" KPI filter actually filters now
- **§2.2** — lifecycle-stage badges in Invite/Assign modals (added directly
  into your `FOR UPDATE`-locked `assign_to_callbacks.py` without touching
  its locking logic)
- **§2.4** — bid amount ceiling
- **§3.3** — `print()` → `logging.exception()` for swallowed notification
  failures (in the two spots that still had it)
- **§3.4** — `resolved_by`/`closed_by` audit columns, both inline in
  `estatehub.sql`'s `CREATE TABLE` and as the incremental `ALTER TABLE ...
  ADD COLUMN IF NOT EXISTS` in `migrate.py` for your already-deployed DB
- **Owner "New Concern" apartment lock** — `apartment_id` pinned
  server-side in `handle_form_submit`, dropdown hidden from the Owner
  portal's form
- **`visitors.host_apartment_id`** inlined into `estatehub.sql`'s
  `CREATE TABLE` (the one migrate.py alteration that wasn't already inline)

## Verified

- `python3 -m py_compile` on every `.py` file in the repo — clean
- `pglast.parse_sql()` on the full `estatehub.sql` — 311 statements, clean
- Ran the complete `estatehub.sql` against a real PostgreSQL 16 instance
  end-to-end — only the same two pre-existing, unrelated statement-ordering
  notices (`visitors`/`patrol_locations`), nothing introduced by this change
- Directly reproduced and then confirmed the fix for both errors you
  reported:
  - `SELECT * FROM fn_concern_profile('23')` — runs clean (was always a
    DB-migration issue, not a code bug — see below)
  - `UPDATE concerns_assigns SET status='resolved', resolved_by=2, ...` —
    now succeeds against the patched schema (previously
    `UndefinedColumn: resolved_by`)
- `git apply --check` — this patch applies cleanly to a fresh pull of the
  current repo

## Reminder on `fn_concern_profile`

This one was never a code bug — the function definition in `estatehub.sql`
has been correct all along. If you still see `function fn_concern_profile
(unknown) does not exist` after applying this, it means the **database**
your app is connected to hasn't had `estatehub.sql`/`migrate.py` run
against it — that's a deployment step, not something a code patch can fix
by itself. Run `python3 database/migrate.py` against the actual DB your
app's connection string points at.

## How to apply

**Patch:** `git apply concerns_fixes_v3.patch` from the repo root (verified
against a fresh clone of the current GitHub state).
**Or:** this zip *is* the entire codebase with everything already applied —
you can just use it directly / diff it against your local copy.
