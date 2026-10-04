# app/services/workflow_service.py
"""
D2 — authorization-aware wiring over app.services.workflow.transition().

Decision boundary & concurrency note
-------------------------------------
`database.db_manager.execute` wraps EACH call in its own
`with self._conn(): conn.commit()` block, so consecutive `db._execute` calls are
NOT in the same transaction: an advisory lock (or `FOR UPDATE`) acquired by a
guard-read is released before the next statement runs. The existing concern
loaders therefore rely on a single-statement conditional UPDATE
(`UPDATE concerns_assigns ... WHERE status = <from> RETURNING id`) as their
atomic compare-and-swap — the only race-safe write primitive available here.

This module therefore does NOT try to replace those atomic writers with
`workflow.transition()` (which read-checks then writes in separate statements
and would reintroduce a lost-update window on double-clicks). Instead it provides
the two D2 guarantees the state-changing call sites were missing:

  1. Delegation-aware authorization — `authorize()` keys off the SERVER-resolved
     actor_id (never the browser auth-store role) and runs `policy.can_do`, which
     in turn checks active `user_role_assignments` grants AND `delegations`
     (maker/checker hand-over). This is what "delegations maker/checker
     enforcement at those call sites" means — the path now runs for real, not
     only under unit test.

  2. Idempotent audit — `append_audit()` writes exactly one row to the matching
     `*_transitions` log per (source, to_state), mirroring transition()'s
     idempotency contract, without touching the source row's status cache (the
     loader's conditional UPDATE owns that).

The poll/visitor-leg call sites keep `fn_declare_results` / the conditional
`alert_events` UPDATE as their writers (quorum math and first-click-wins /
expires_at guards live there); this module only adds the authorize gate in front
of them.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from database.db_manager import db

import app.security.policy as policy
from app.security.policy import Permission


# ── 1. authorization gate ────────────────────────────────────────────────────
#
# Fail-open semantics for legacy / not-yet-seeded databases:
# `authorize()` keys off the SERVER-resolved actor_id (never the browser
# auth-store role) and runs `policy.can_do`, which honors active grants AND
# delegating (maker/checker) delegations. But on a database that has been
# migrated (RBAC tables exist) but whose `role_definitions` have NOT been seeded
# by `database/seed.seed_rbac_roles`, every user would look "ungranted" and be
# denied — silently breaking existing admin portals after a migrate-only deploy.
# So we detect the "no policy configured" state (empty role_definitions, or the
# table itself absent on a pre-migration DB) and short-circuit to allow, exactly
# preserving legacy behaviour until the RBAC backfill runs. Once seeded, the
# gate is fail-closed: a missing/expired/revoked grant is a denial.

def _rbac_enabled() -> bool:
    """True once the RBAC vocabulary has been seeded (role_definitions non-empty).
    On a legacy DB where the table is missing entirely, the SELECT errors and we
    treat that as 'disabled' (fail-open) so existing behaviour is preserved."""
    try:
        row = db._execute("SELECT id FROM role_definitions LIMIT 1",
                          fetch_one=True)
        return bool(row)
    except Exception:
        return False


def authorize(actor_id, permission, society_id, **ctx) -> tuple[bool, str]:
    """Return (allowed, reason). `permission` is None => skip (self-service leg).
    Delegates to policy.can_do, which honors active grants AND delegations."""
    if permission is None:
        return True, ""
    if actor_id is None:
        return False, "no authenticated user"
    if not _rbac_enabled():
        return True, ""   # legacy / unseeded DB — no fine-grained policy configured
    return policy.can_do(actor_id, permission, society_id=society_id, **ctx)


def concern_permission(action: str) -> str | None:
    return _CONCERN_PERMISSION.get(action)


# ── 2. idempotent audit append ────────────────────────────────────────────────

def _existing_audit_id(table, dedup_cols, dedup_vals) -> int | None:
    """Return the id of an existing audit row for the dedup key, else None.
    Best-effort idempotency (transition()'s contract): a retry that hits the
    same (source, to_state) is collapsed to one audit row."""
    where = " AND ".join(f"{c} = :v{i}" for i, c in enumerate(dedup_cols))
    params = {f"v{i}": v for i, v in enumerate(dedup_vals)}
    row = db._execute(
        f"SELECT id FROM {table} WHERE {where} ORDER BY id DESC LIMIT 1",
        params, fetch_one=True,
    )
    return (row or {}).get("id")


def append_audit(table, row: dict, dedup_cols=None) -> int | None:
    """Idempotently append an audit row to a `*_transitions` table.

    `row` is the exact column->value map to insert. `dedup_cols` (subset of row's
    keys) defines the uniqueness key used to skip an already-logged transition;
    when omitted, every call inserts (used for genuinely non-idempotent logs)."""
    if dedup_cols:
        key = tuple(row.get(c) for c in dedup_cols)
        if any(v is None for v in key):
            return None
        existing = _existing_audit_id(table, dedup_cols, key)
        if existing:
            return existing
    cols = list(row.keys())
    ph = ", ".join(f":{c}" for c in cols)
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({ph}) RETURNING id"
    res = db._execute(sql, row, fetch_one=True)
    return (res or {}).get("id")


def log_concern_transition(actor_id, assignment_id, concern_id,
                           from_state, to_state, role, entity_id,
                           permission, society_id,
                           comment: str | None = None,
                           correlation_id: str | None = None,
                           **evidence) -> int | None:
    """Append one concern_transitions row. Idempotent on (assignment_id, to_state).
    Evidence is JSON-serialised into the `evidence` JSONB column; free-form
    caller keys (doc_hash, before_snapshot, etc.) land there."""
    payload = {k: v for k, v in evidence.items()
               if k not in ("comment", "correlation_id")}
    row = {
        "assignment_id":  assignment_id,
        "concern_id":     concern_id,
        "from_state":     from_state,
        "to_state":       to_state,
        "actor_id":       actor_id,
        "society_id":     society_id,
        "entity_role":    role,
        "entity_id":      entity_id,
        "permission_used": permission,
        "comment":        comment,
        "evidence":       json.dumps(payload) if payload else None,
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "created_at":     datetime.utcnow(),
    }
    return append_audit("concern_transitions", row,
                        dedup_cols=["assignment_id", "to_state"])


# ── poll-results declaration gate ────────────────────────────────────────────

def authorize_poll_declaration(actor_id, society_id) -> tuple[bool, str]:
    """Authorize declaring poll results. The actual state write + quorum math
    still happens in `fn_declare_results` (a DB function we deliberately do not
    replace); this gate enforces the society_secretary/treasurer grant (or an
    active delegation) before that function runs."""
    return authorize(actor_id, Permission.POLL_DECLARE_RESULTS, society_id)
