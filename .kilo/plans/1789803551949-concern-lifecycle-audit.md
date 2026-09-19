# Concern Lifecycle Audit: `in_progress` vs `assigned` Discrepancy

## Summary

The concern aggregate status `in_progress` is used in seed data, test fakes, tests, and model enums — but the real SQL function `fn_sync_concern_status` (estatehub.sql:8410) **never produces `in_progress`**; it produces **`assigned`**. The value is a stale artifact from the pre-2026-07 `concerns_assigns` redesign. The application renderer (`_CONCERN_STATUS_BANNER`, renderers.py:1217) only recognizes `open`/`assigned`/`resolved`/`closed` and falls back to a generic "In progress" label for any unknown status.

## Affected Locations

| # | File | Line(s) | What | Severity |
|---|---|---|---|---|
| 1 | `database/estatehub.sql` | 287–302 | `concerns.status` column has NO CHECK constraint — `in_progress` is silently accepted on INSERT | Medium |
| 2 | `database/estatehub.sql` | 327–338 | SQL comment documents only `open`/`assigned`/`resolved`/`closed` | (doc — correct) |
| 3 | `database/estatehub.sql` | 8410–8446 | `fn_sync_concern_status` returns `open`/`assigned`/`resolved`/`closed` only — never `in_progress` | (source of truth — correct) |
| 4 | `database/seed.py` | 495, 502, 516 | 3 seed concerns use `status: "in_progress"` | High |
| 5 | `app/models/__init__.py` | 43–48 | `ConcernStatus` enum has `OPEN`, `INVITE`, `IN_PROGRESS`, `RESOLVED` — missing `ASSIGNED`, `CLOSED`; stale `INVITE` and `IN_PROGRESS` | Medium |
| 6 | `app/models/__init__.py` | 420–428 | `dict_to_concern` tries `ConcernStatus("assigned")` → `ValueError` (no such enum member) | Low (function is dead code — not called anywhere) |
| 7 | `app/utils/field_config.py` | 538 | Tooltip: "Current status: open, in_progress, resolved, closed" | Low |
| 8 | `test/fake_db.py` | 919, 921 | `_fn_sync_concern_status` returns `"in_progress"` where real SQL returns `"assigned"` | High |
| 9 | `test/test_scenario_c_concern_lifecycle.py` | 122 | Asserts `result["status"] == "in_progress"` after assigning a vendor | High |
| 10 | `app/dash_apps/drilldown/renderers.py` | 1217–1222 | `_CONCERN_STATUS_BANNER` has no `in_progress` key; falls back to `("In progress", "#1d74d8")` at line 1759 | Medium |
| 11 | `app/dash_apps/drilldown/renderers.py` | 268 | `_humanize_string` docstring cites `in_progress` as example | Trivial |
| 12 | `README.md` | 1082 | Documents `in_progress` as a concern status | Low |

## Root Cause Analysis

### The Real SQL (single source of truth)

`fn_sync_concern_status` (estatehub.sql:8420–8438) computes the aggregate by querying `concerns_assigns` rows joined to the concern:

- **No assignment rows** → `open`
- **Any row status in `('assigned','accepted','resolved','closed')`** → `assigned` (unless ALL are resolved/closed)
- **All rows `closed`** → `closed`
- **All rows `resolved`/`closed`** → `resolved`

`in_progress` is **never** produced.

### Seed Data Impact (seed.py:1311–1367)

The seed loop inserts a concern with the `status` from the seed dict, then conditionally inserts `concerns_assigns` rows (status `'assigned'` at line 1362). The `trg_concerns_assigns_sync` trigger fires on those inserts and overwrites `concerns.status` per `fn_sync_concern_status`.

For the 3 `in_progress` concerns:
- **B-202** (electrical): has `assign_role="SEC"` → assignment row inserted → trigger fires → status becomes **`assigned`** (overwrites `in_progress`)
- **A-103** (painting): has `assign_role="VND"` → assignment row inserted → trigger fires → status becomes **`assigned`**
- **B-102** (parking): **no** `assign_role` → no assignment row → **trigger never fires** → status stays **`in_progress`** in the database

Result: B-102 persists `in_progress` and renders with the generic blue "In progress" fallback banner (renderers.py:1760) instead of the intended orange "Assigned — work in progress" banner.

### Test Fake Mismatch (test/fake_db.py:908–924)

| Assignment rows | Real SQL | Test fake |
|---|---|---|
| None | `open` | `open` ✓ |
| Any `assigned`/`accepted`/etc. | `assigned` | **`in_progress`** ❌ (lines 919, 921) |
| All `closed` | `closed` | `closed` ✓ |
| All `resolved`/`closed` | `resolved` | `resolved` ✓ |

The fake checks `any(s == "assigned")` and `any(s == "bid_submitted")` separately, returning `in_progress` for each — but the real SQL treats both as producing `assigned`.

### Test Assertion (test_scenario_c_concern_lifecycle.py:118–122)

```python
def test_concern_status_aggregate_updates(self, patched_db):
    _seed_concern_world(patched_db)
    loaders.assign_concern(1, 1, "VND", 201, assigned_by=1)
    result = patched_db._fn_sync_concern_status({"p0": 1, "p1": 1}, ...)
    assert result["status"] == "in_progress"  # ❌ should be "assigned"
```

## Fix Plan (ordered tasks)

### Task 1 — Fix the test fake (`test/fake_db.py:919,921`)

Align `_fn_sync_concern_status` with the real SQL. Replace the two `return {"status": "in_progress"}` lines with `return {"status": "assigned"}`:

```python
# Current:
if any(s == "assigned" for s in statuses):
    return {"status": "in_progress"}
if any(s == "bid_submitted" for s in statuses):
    return {"status": "in_progress"}

# Fixed:
if any(s in ("assigned", "accepted", "bid_submitted") for s in statuses):
    return {"status": "assigned"}
```

This consolidates the two branches (the real SQL treats `bid_submitted` and `assigned` as producing the same `assigned` aggregate, since `bid_submitted` is not in the `v_touched` filter).

### Task 2 — Fix the test assertion (`test/test_scenario_c_concern_lifecycle.py:122`)

```python
# Current:
assert result["status"] == "in_progress"
# Fixed:
assert result["status"] == "assigned"
```

### Task 3 — Fix seed data (`database/seed.py:495,502,516`)

Change the 3 seed concerns' `"status": "in_progress"` to `"status": "assigned"`. This makes seed data match what the trigger would produce anyway for concerns with assignment rows (B-202 and A-103), and fixes B-102 (which has no assignment and would otherwise stay `in_progress`).

```python
# Line 495:
{"flat_number": "B-202", "type": "electrical", "status": "assigned", ...}
# Line 502:
{"flat_number": "A-103", "type": "painting", "status": "assigned", ...}
# Line 516:
{"flat_number": "B-102", "type": "parking", "status": "assigned", ...}
```

> Note: Since `fn_sync_concern_status` uses `status IS DISTINCT FROM v_new_status` (estatehub.sql:8443), setting seed status to `assigned` is safe — if the trigger computes the same value, the UPDATE is a no-op.

### Task 4 — Fix model enum (`app/models/__init__.py:43–48`)

Replace the stale `ConcernStatus` enum to match the real SQL valid values:

```python
class ConcernStatus(str, Enum):
    OPEN = "open"
    ASSIGNED = "assigned"       # was: IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"           # was missing
```

Remove `INVITE` (invalid — never a concern aggregate status) and `IN_PROGRESS` (not a real value). Add `ASSIGNED` and `CLOSED`.

This fixes the latent `dict_to_concern` crash (app/models/__init__.py:425) where `ConcernStatus('assigned')` would raise `ValueError`.

### Task 5 — Fix tooltip (`app/utils/field_config.py:538`)

```python
# Current:
"tooltip": "Current status: open, in_progress, resolved, closed",
# Fixed:
"tooltip": "Current status: open, assigned, resolved, closed",
```

### Task 6 — Fix docstring (`app/dash_apps/drilldown/renderers.py:268`)

The `_humanize_string` docstring is generic — change the example from `in_progress` to `bid_submitted` (a real value that would be humanized).

### Task 7 — Add DB CHECK constraint (optional hardening)

Add a CHECK constraint to `concerns.status` in estatehub.sql to reject invalid values at the database level:

```sql
ALTER TABLE concerns
  ADD CONSTRAINT chk_concerns_status
  CHECK (status IN ('open', 'assigned', 'resolved', 'closed'));
```

This ensures the stale `in_progress` can never be persisted going forward. Safe because:
- The `concerns.status` column is only written on INSERT (default `'open'`) or by `fn_sync_concern_status` (which only produces valid values).
- No application code writes `in_progress` directly (field_config.py:535 shows `editable: ADMIN_ONLY`, and schema_introspect.py:630 hides `status` from forms).

### Task 8 — Update README (`README.md:1082`)

Change the concern statuses listed from `open, in_progress, resolved, closed` to `open, assigned, resolved, closed`.

## Verification Steps

1. **Unit tests**: Run `pytest test/test_scenario_c_concern_lifecycle.py` — the `test_concern_status_aggregate_updates` test should pass with the corrected fake and assertion.
2. **Seed verification**: Load seed data into a fresh DB and verify all 3 previously-`in_progress` concerns now have correct statuses (B-202/A-103 → `assigned` via trigger; B-102 → `assigned` from seed default).
3. **Enum verification**: `ConcernStatus("assigned")` should now resolve correctly.
4. **Full test suite**: Run `pytest` to check for regressions.
