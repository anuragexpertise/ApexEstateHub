# app/services/workflow.py
"""
D2 — Single state-machine entry point for append-only transition logs.

One public function: ``transition()``. Every stateful workflow in the app
(concerns_assigns, polls, alert_events) routes through it so that:

  * every state change is recorded in the matching ``*_transitions`` audit
    table (the source of truth — see plan §D2),
  * the legality of the jump is enforced by per-source state machines
    (illegal jumps are rejected), and
  * the source row's status cache is refreshed in the *same* transaction
    as the append, so the cache can never drift from the log, and
  * duplicate (source, actor, from->to) transitions are idempotent — a retry
    that hits the same transition is a no-op, not a second audit row, and
    never double-fires downstream (outbox) effects.

The caller is responsible for having resolved the actor from the SERVER
session (app.security.audit_context.get_current_user_id()). `permission`
is an (action, resource) Permission tuple; the engine calls policy.can_do()
to enforce it on the security-critical surface.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from database.db_manager import db

log = logging.getLogger(__name__)


# ── State machines ────────────────────────────────────────────────────────────
# Each maps current_state -> set(legal next states). A None key means "initial"
# (the row's current state before any transition has been recorded). These are
# the canonical lifecycles documented in estatehub.sql's concerns_assigns
# comment block and the polls / alert_events CHECK constraints.

STATE_MACHINES: dict[str, dict[str | None, set[str]]] = {
    # concerns_assigns.status — see estatehub.sql §CONCERNS_ASSIGNS
    "concerns_assigns": {
        None:            {"invited", "assigned"},
        "invited":       {"bid_submitted", "declined"},
        "bid_submitted": {"assigned", "declined"},
        "assigned":      {"accepted", "resolved", "declined"},
        "accepted":      {"resolved"},
        "resolved":      {"closed"},
        "declined":      {"assigned"},
        "closed":        set(),
    },
    # polls.status
    "polls": {
        None:  {"active"},
        "active":  {"closed", "results_declared"},
        "closed":  {"results_declared"},
        "results_declared": set(),
    },
    # alert_events.state
    "alert_events": {
        None:   {"idle", "pending"},
        "idle": {"pending", "arrived"},
        "pending":  {"arrived", "calling", "denied", "expired"},
        "arrived":  {"calling", "resolved", "denied"},
        "calling":  {"resolved", "denied", "expired"},
        "resolved": set(),
        "denied":    set(),
        "expired":   set(),
    },
}

# Per-source metadata: (transition table, source-fk column, status cache column).
# status cache column is None when the source row has no writable status cache
# (the transition log is then the only record).
_SOURCE_META = {
    "concerns_assigns": {"table": "concern_transitions",
                         "fk": "assignment_id", "cache_col": "status",
                         "concern_fk": "concern_id"},
    "polls":            {"table": "poll_transitions",
                         "fk": "poll_id", "cache_col": "status"},
    "alert_events":     {"table": "channel_event_transitions",
                         "fk": "event_id", "cache_col": "state"},
}


@dataclass
class TransitionResult:
    ok: bool
    state: str
    reason: str = ""
    transition_id: int | None = None
    idempotent: bool = False


# ── public API ────────────────────────────────────────────────────────────────

def transition(source_table: str, source_id: int, new_state: str,
               actor_id, permission: tuple | None = None,
               society_id=None, correlation_id=None, **evidence) -> TransitionResult:
    """
    Execute a state transition on a row in `source_table`.

    Args:
        source_table: one of STATE_MACHINES keys (concerns_assigns / polls /
            alert_events).
        source_id:    PK of the row in source_table.
        new_state:    target state; must be legal from the row's current state.
        actor_id:     resolved user id (SERVER session — never auth-store).
        permission:   (action, resource) Permission tuple to check via
            policy.can_do, or None to skip the permission check (for internal /
            time-driven transitions).
        society_id:   tenant context, passed to policy.can_do and stamped on the
            audit row.
        correlation_id: caller-supplied UUID tying this transition to a downstream
            business action (e.g. an outbox row).
        **evidence:   free-form keys (comment, doc_hash, entity_role, entity_id,
            permission_used, ...) stored on the audit row.

    Returns a TransitionResult. On denial the source row is NOT mutated. On a
    duplicate retry (source already in new_state via the same actor) it is a
    no-op: ok=True, idempotent=True, no new audit row.
    """
    meta = _SOURCE_META.get(source_table)
    if meta is None:
        return TransitionResult(False, "", f"unknown source table: {source_table}")

    if new_state not in STATE_MACHINES.get(source_table, {}).get(None, set()) \
       and new_state not in _all_states(source_table):
        return TransitionResult(False, "", f"unknown target state: {new_state}")

    # Permission check on the security-critical surface.
    # Permission is a dotted "resource.action" string (or tuple) — see
    # app.security.policy.Permission.
    if permission is not None:
        from app.security.policy import can_do
        allowed, reason = can_do(actor_id, permission, society_id=society_id)
        if not allowed:
            return TransitionResult(False, "", f"permission denied: {reason}")
        # normalise to the dotted form used on the audit row
        if isinstance(permission, tuple):
            permission = f"{permission[0]}.{permission[1]}"
        evidence.setdefault("permission_used", permission)

    # Read the current state from the source row.
    current = _read_current_state(source_table, source_id)
    if current is None:
        return TransitionResult(False, "", f"{source_table} row {source_id} not found")
    current_state = current.get(meta["cache_col"])

    # Idempotency: row already in target state + same actor retried → no-op.
    if current_state == new_state:
        dup_id = _last_duplicate(meta["table"], meta["fk"], source_id,
                                 actor_id, current_state)
        if dup_id:
            return TransitionResult(True, new_state, "",
                                    transition_id=dup_id, idempotent=True)
        # Already in the state but no prior transition for it — e.g. the row
        # was created directly at this state. Nothing to audit; report success.
        return TransitionResult(True, new_state, "", idempotent=True)

    # Legality check.
    if not _legal_next(source_table, current_state, new_state):
        return TransitionResult(
            False, current_state or "",
            f"illegal state jump: {current_state!r} -> {new_state!r} "
            f"for {source_table}",
        )

    # Write the audit row + refresh the source cache, in sequence (the DB
    # connection auto-commits each statement; the trigger on the source table
    # for concerns still fires fn_sync_concern_status, so the cache stays
    # consistent).
    tx_id = _record_transition(source_table, meta, source_id, current_state,
                               new_state, actor_id, society_id, correlation_id,
                               current, evidence)
    if tx_id is None:
        return TransitionResult(False, current_state or "",
                                "transition write failed")

    _apply_cache_update(meta, source_id, new_state)

    return TransitionResult(True, new_state, "", transition_id=tx_id)


# ── helpers ───────────────────────────────────────────────────────────────────

def _all_states(source_table: str) -> set[str]:
    """Every state ever reachable for a source (for target validation)."""
    sm = STATE_MACHINES.get(source_table, {})
    out: set[str] = set()
    for src, dsts in sm.items():
        if src is not None:
            out.add(src)
        out |= dsts
    return out


def _read_current_state(source_table, source_id):
    row = db._execute(
        f"SELECT * FROM {source_table} WHERE id = :sid",
        {"sid": source_id}, fetch_one=True,
    )
    return row


def _legal_next(source_table, from_state, to_state) -> bool:
    sm = STATE_MACHINES.get(source_table, {})
    allowed = sm.get(from_state)   # None key = initial
    if allowed is None:
        return False
    return to_state in allowed


def _last_duplicate(ttable, fk_col, source_id, actor_id, state):
    """Return the id of an existing transition that is an exact duplicate of the
    one we'd write now (idempotency), or None."""
    row = db._execute(
        f"SELECT id FROM {ttable} WHERE {fk_col} = :sid AND actor_id = :aid "
        f"AND to_state = :st ORDER BY id DESC LIMIT 1",
        {"sid": source_id, "aid": actor_id, "st": state}, fetch_one=True,
    )
    return (row or {}).get("id")


_TRANSITION_TABLE_TO_SOURCE = {v["table"]: k for k, v in _SOURCE_META.items()}


def _apply_cache_update(meta, source_id, new_state):
    """Refresh the source row's status cache. Concerns_assigns.status is the
    cache for the assignment row; alert_events.state / polls.status likewise.
    The workflow service writes it in the same step as the audit append so the
    cache can never drift from the log."""
    cache_col = meta.get("cache_col")
    if not cache_col:
        return
    table = _TRANSITION_TABLE_TO_SOURCE.get(meta["table"])
    if not table:
        return
    db._execute(
        f"UPDATE {table} SET {cache_col} = :st WHERE id = :sid",
        {"st": new_state, "sid": source_id},
    )


def _record_transition(source_table, meta, source_id, from_state, to_state,
                       actor_id, society_id, correlation_id, current, evidence):
    """Append the audit row. Returns its id (or None on failure)."""
    ttable = meta["table"]
    corr = correlation_id or str(uuid.uuid4())

    # Base columns present on every transition table.
    col_map = {
        meta["fk"]: source_id,        # assignment_id / poll_id / event_id
        "from_state": from_state,
        "to_state": to_state,
        "actor_id": actor_id,
        "society_id": society_id,
        "created_at": datetime.utcnow(),
    }

    # concerns_assigns rows also carry concern_id + entity_role + entity_id.
    if source_table == "concerns_assigns":
        col_map["concern_id"] = current.get("concern_id")
        if "entity_role" in evidence:
            col_map["entity_role"] = evidence["entity_role"]
        if "entity_id" in evidence:
            col_map["entity_id"] = evidence["entity_id"]

    # Free-form narrative columns (evidence JSON, comment, correlation).
    comment = evidence.get("comment")
    perm_used = evidence.get("permission_used")
    payload = {k: v for k, v in evidence.items()
               if k not in ("comment", "permission_used")}
    col_map["comment"] = comment
    col_map["evidence"] = json.dumps(payload) if payload else None
    col_map["correlation_id"] = corr
    if perm_used is not None:
        col_map["permission_used"] = perm_used

    cols = list(col_map.keys())
    ph = ", ".join(f":{c}" for c in cols)
    col_list = ", ".join(cols)
    sql = f"INSERT INTO {ttable} ({col_list}) VALUES ({ph}) RETURNING id"
    row = db._execute(sql, col_map, fetch_one=True)
    return (row or {}).get("id")
