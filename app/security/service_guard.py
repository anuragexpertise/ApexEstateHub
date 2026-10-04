# app/security/service_guard.py
"""
Service-boundary authorization (RWA3.md WP2/WP3, PR 4).

`app/security/authorization.py` is the pure decision point. This module is the
glue that makes it usable at the callback / service boundary:

  current_principal()   server-resolved Principal (Flask-Login id -> DB row ->
                        linked ids -> active assignments). Browser stores are
                        never consulted. Re-read from the DB every request, so
                        a demotion or revoked role bites on the next request.
  check() / ensure()    evaluate authorize(); record a denial in audit_events;
                        `ensure` raises AuthorizationDenied in enforce mode.
  require_action()      decorator for callbacks / service functions.
  audit_event()         append-only audit row; pass `cur=` to write it in the
                        SAME transaction as the business change.
  scoped_get/_update    tenant-qualified resource primitives: lookup and
                        mutation are always `WHERE id = :id AND society_id =
                        :society` with a closed table/column registry, so a
                        client-supplied id can never cross a tenant boundary.
  authorize_resource()  load the record by (id, society) first, derive the
                        ownership attributes from the ROW, then authorize.

Rollout (RWA3 WP6)
------------------
Mode is resolved per action, most specific first:
  ESTATEHUB_AUTHZ_MODE_<ACTION>   e.g. ESTATEHUB_AUTHZ_MODE_POLL_VOTE
  ESTATEHUB_AUTHZ_MODE_<PREFIX>   e.g. ESTATEHUB_AUTHZ_MODE_POLL
  ESTATEHUB_AUTHZ_MODE            global
  built-in default                "shadow" for SHADOW_BY_DEFAULT actions, else "enforce"
Values: "enforce" (deny blocks the operation) or "shadow" (deny is logged as
`authz.shadow_denied` but the LEGACY check stays authoritative). Any other
value is treated as "enforce" - a typo must never silently disable a control.
Shadow mode never grants anything the legacy path did not already allow: every
wired call site keeps its existing role check and adds this one on top.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Mapping, Optional

from app.security import authorization as az
from app.security.authorization import (
    AuthorizationDecision, Cap, PolicyUnavailable, Principal,
)

log = logging.getLogger(__name__)

ENFORCE = "enforce"
SHADOW = "shadow"

# Resident-facing actions whose policy departs from legacy behaviour (e.g. only
# owners may vote). They start in shadow so the first staging replay shows who
# would be denied before enforcement is switched on.
SHADOW_BY_DEFAULT: frozenset[str] = frozenset({Cap.POLL_VOTE, Cap.GATE_VISITOR_PROCESS})


class AuthorizationDenied(PermissionError):
    def __init__(self, decision: AuthorizationDecision):
        super().__init__(decision.reason or "denied")
        self.decision = decision


def _db():
    # Resolved lazily so tests can patch `database.db_manager.db` / this attr.
    from database.db_manager import db
    return db


# ── mode ─────────────────────────────────────────────────────────────────────
def authz_mode(action: str) -> str:
    key = re.sub(r"[^A-Z0-9]+", "_", action.upper())
    prefix = re.sub(r"[^A-Z0-9]+", "_", action.split(".", 1)[0].upper())
    for name in (f"ESTATEHUB_AUTHZ_MODE_{key}", f"ESTATEHUB_AUTHZ_MODE_{prefix}",
                 "ESTATEHUB_AUTHZ_MODE"):
        raw = os.environ.get(name)
        if raw:
            return SHADOW if raw.strip().lower() == SHADOW else ENFORCE
    return SHADOW if action in SHADOW_BY_DEFAULT else ENFORCE


# ── request-scoped helpers ───────────────────────────────────────────────────
def _g():
    try:
        from flask import g, has_request_context
        return g if has_request_context() else None
    except Exception:  # noqa: BLE001
        return None


def correlation_id() -> str:
    """One id per request: ties the audit rows, workflow transitions and
    notifications produced by a single user action together."""
    g = _g()
    if g is not None:
        cid = getattr(g, "_authz_correlation_id", None)
        if cid is None:
            cid = g._authz_correlation_id = str(uuid.uuid4())
        return cid
    return str(uuid.uuid4())


def _session_user_id() -> Optional[int]:
    from app.security.audit_context import get_current_user_id
    return get_current_user_id()


def current_principal() -> Optional[Principal]:
    """Server-resolved principal for the current request, or None when there is
    no session / the user row is gone. Raises PolicyUnavailable if the
    assignment lookup fails (callers deny)."""
    uid = _session_user_id()
    if uid is None:
        return None
    g = _g()
    if g is not None:
        cached = getattr(g, "_authz_principal", None)
        if cached is not None and cached[0] == uid:
            return cached[1]
    db = _db()
    row = db._execute(
        "SELECT id, society_id, role, is_master_admin, user_type, linked_id "
        "FROM users WHERE id = %s", (uid,), fetch_one=True)
    if not row:
        return None
    assignments = az.load_assignments(db, uid, row.get("society_id")) \
        if row.get("society_id") is not None else ()
    role, linked_id = row.get("role"), row.get("linked_id")
    linked = {
        "unit_id": linked_id if role == "apartment" else None,
        "vendor_id": linked_id if role == "vendor" else None,
        "security_id": linked_id if role == "security" else None,
    }
    principal = az.build_principal(row, assignments, linked)
    if g is not None:
        g._authz_principal = (uid, principal)
    return principal


def _clear_principal_cache() -> None:
    g = _g()
    if g is not None and hasattr(g, "_authz_principal"):
        del g._authz_principal


# ── audit ────────────────────────────────────────────────────────────────────
_SENSITIVE_KEY = re.compile(
    r"(pass(word)?|secret|token|pin|pattern|hash|otp|signing|credential|authorization|cvv|"
    r"aadhaar|pan(_?number)?)", re.I)


def redact(value: Any, _depth: int = 0) -> Any:
    """Strip credential-like keys before anything reaches audit_events."""
    if _depth > 6:
        return "<truncated>"
    if isinstance(value, Mapping):
        return {str(k): ("<redacted>" if _SENSITIVE_KEY.search(str(k)) else redact(v, _depth + 1))
                for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [redact(v, _depth + 1) for v in value]
    return value


def _json(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(redact(value), default=str, sort_keys=True)


def _client_ip() -> Optional[str]:
    try:
        from flask import has_request_context, request
        if has_request_context():
            return (request.remote_addr or "")[:45] or None
    except Exception:  # noqa: BLE001
        pass
    return None


_AUDIT_SQL = (
    "INSERT INTO audit_events (society_id, actor_id, actor_role, action, resource_type, "
    "resource_id, before_value, after_value, reason, source, correlation_id, "
    "permission_used, policy_version, ip_address) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s)")


def audit_event(action: str, resource_type: str, resource_id: Any = None, *,
                before: Any = None, after: Any = None, reason: Optional[str] = None,
                permission_used: Optional[str] = None, principal: Optional[Principal] = None,
                actor_role: Optional[str] = None, society_id: Optional[int] = None,
                source: str = "app", cur=None) -> bool:
    """Append one audit row. Actor and society come from the SERVER principal.

    With `cur` (a DB cursor already inside the caller's transaction) the row
    commits or rolls back WITH the business change; if that insert fails the
    exception propagates so the change rolls back too (no un-audited write).
    Without `cur` it is a standalone best-effort write: returns False on
    failure and logs, because a missing audit row must not turn a denial into
    an outage."""
    if principal is None:
        try:
            principal = current_principal()
        except PolicyUnavailable:
            principal = None
    params = (
        society_id if society_id is not None else (principal.society_id if principal else None),
        principal.user_id if principal else None,
        (actor_role or (principal.base_role if principal else None) or "")[:20] or None,
        action[:60], resource_type[:60],
        None if resource_id is None else str(resource_id)[:64],
        _json(before), _json(after), reason, source, correlation_id(),
        (permission_used or "")[:60] or None, az.POLICY_VERSION, _client_ip(),
    )
    if cur is not None:
        cur.execute(_AUDIT_SQL, params)
        return True
    try:
        _db()._execute(_AUDIT_SQL, params)
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("audit_events write failed (%s %s): %s", action, resource_type, exc)
        return False


# ── check / ensure / decorator ───────────────────────────────────────────────
def check(action: str, resource_type: str, resource_id: Any = None, *,
          target_society_id: Optional[int] = None,
          attributes: Optional[Mapping[str, Any]] = None,
          audit_denials: bool = True) -> AuthorizationDecision:
    """Authorize the current request's principal. Never raises for a policy
    outcome; a policy-store outage is a denial."""
    try:
        principal = current_principal()
    except PolicyUnavailable:
        d = AuthorizationDecision(False, "policy unavailable", action, resource_type)
        if audit_denials:
            audit_event("authz.denied", resource_type, resource_id, reason=d.reason,
                        permission_used=action, principal=None)
        return d
    d = az.authorize(principal, action, resource_type, resource_id=resource_id,
                     target_society_id=target_society_id, attributes=attributes)
    if not d.allowed and audit_denials:
        mode = authz_mode(action)
        audit_event("authz.denied" if mode == ENFORCE else "authz.shadow_denied",
                    resource_type, resource_id, reason=d.reason,
                    permission_used=action, principal=principal)
    return d


def blocks(decision: AuthorizationDecision) -> bool:
    """True when this decision must stop the operation (denied AND the action
    is in enforce mode). Use after check()/authorize_resource() when the call
    site wants to render its own denial instead of catching an exception."""
    return (not decision.allowed) and authz_mode(decision.action) == ENFORCE


def ensure(action: str, resource_type: str, resource_id: Any = None, *,
           target_society_id: Optional[int] = None,
           attributes: Optional[Mapping[str, Any]] = None) -> AuthorizationDecision:
    """check() + raise AuthorizationDenied when the action's mode is enforce.
    In shadow mode a denial is logged and the (legacy-guarded) call proceeds."""
    d = check(action, resource_type, resource_id, target_society_id=target_society_id,
              attributes=attributes)
    if not d.allowed and authz_mode(action) == ENFORCE:
        raise AuthorizationDenied(d)
    return d


def require_action(action: str, resource_type: str, *,
                   resolve: Optional[Callable[..., Mapping[str, Any]]] = None,
                   on_deny: Optional[Callable[[AuthorizationDecision], Any]] = None):
    """Decorator for Dash callbacks and domain-service functions.

    `resolve(*args, **kwargs)` may return {"resource_id", "target_society_id",
    "attributes"} derived SERVER-side (never from a browser store). On denial
    the wrapped function does not run; `on_deny(decision)` supplies the
    callback's return value, otherwise Dash's PreventUpdate (or
    AuthorizationDenied outside Dash) is raised.

    Place it directly under @require_session:
        @app.callback(...)
        @require_session
        @require_action(Cap.POLL_MANAGE, "poll")
        def save_poll(...): ...
    """
    def deco(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            ctx = (resolve(*args, **kwargs) if resolve else {}) or {}
            d = check(action, resource_type, ctx.get("resource_id"),
                      target_society_id=ctx.get("target_society_id"),
                      attributes=ctx.get("attributes"))
            if not d.allowed and authz_mode(action) == ENFORCE:
                if on_deny is not None:
                    return on_deny(d)
                try:
                    from dash.exceptions import PreventUpdate
                except Exception:  # noqa: BLE001
                    raise AuthorizationDenied(d)
                raise PreventUpdate
            return f(*args, **kwargs)
        wrapped.__authz__ = (action, resource_type)      # read by the endpoint inventory
        return wrapped
    return deco


# ── tenant-scoped resource primitives ────────────────────────────────────────
class TenantTable:
    __slots__ = ("name", "pk", "tenant_col", "columns", "updatable")

    def __init__(self, name: str, columns, updatable, pk: str = "id", tenant_col: str = "society_id"):
        for ident in (name, pk, tenant_col, *columns, *updatable):
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", ident):
                raise ValueError(f"unsafe SQL identifier {ident!r}")
        if tenant_col in updatable or pk in updatable:
            raise ValueError("pk / tenant column must never be updatable")
        self.name, self.pk, self.tenant_col = name, pk, tenant_col
        self.columns = frozenset(columns) | {pk, tenant_col}
        self.updatable = frozenset(updatable)


TENANT_TABLES: dict[str, TenantTable] = {}


def register_tenant_table(spec: TenantTable) -> TenantTable:
    TENANT_TABLES[spec.name] = spec
    return spec


for _spec in (
    TenantTable("concerns", ("apartment_id", "created_by", "status", "concern_type"), ("status",)),
    TenantTable("polls", ("title", "status", "open_to", "ends_at"), ("status",)),
    TenantTable("concerns_assigns",
                ("concern_id", "role", "entity_id", "status", "assigned_by", "invited_by"),
                ("status",)),
    TenantTable("apartments", ("flat_number", "active"), ()),
    TenantTable("vendors", ("business_name", "active"), ()),
    TenantTable("security_staff", ("name", "active"), ()),
):
    register_tenant_table(_spec)


def _spec(table: str) -> TenantTable:
    spec = TENANT_TABLES.get(table)
    if spec is None:
        raise ValueError(f"table {table!r} is not registered as tenant-scoped")
    return spec


def _run(sql: str, params: tuple, cur, one: bool = True):
    if cur is not None:
        cur.execute(sql, params)
        if one:
            r = cur.fetchone()
            return dict(r) if r else None
        return [dict(r) for r in cur.fetchall()]
    return _db()._execute(sql, params, fetch_one=one, fetch_all=not one)


def scoped_get(table: str, pk_value: Any, society_id: Optional[int], *, columns=None,
               for_update: bool = False, cur=None) -> Optional[dict]:
    """SELECT one row by primary key AND tenant. A foreign-tenant id and a
    nonexistent id are indistinguishable (both None), so ids cannot be probed
    across societies. A missing society_id fails closed."""
    spec = _spec(table)
    if society_id is None or pk_value is None:
        return None
    cols = list(columns) if columns else sorted(spec.columns)
    bad = [c for c in cols if c not in spec.columns]
    if bad:
        raise ValueError(f"columns not registered for {table}: {bad}")
    sql = (f"SELECT {', '.join(cols)} FROM {spec.name} "
           f"WHERE {spec.pk} = %s AND {spec.tenant_col} = %s")
    if for_update:
        sql += " FOR UPDATE"
    return _run(sql, (pk_value, society_id), cur)


def scoped_update(table: str, pk_value: Any, society_id: Optional[int],
                  values: Mapping[str, Any], *, expect: Optional[Mapping[str, Any]] = None,
                  cur=None) -> Optional[dict]:
    """UPDATE ... WHERE pk AND tenant [AND expected-state] RETURNING pk.
    `expect` makes the state transition atomic (a conditional update): it
    returns None when the row is missing, belongs to another tenant, or is no
    longer in the expected state - the caller treats all three as "not
    applied". Only registered updatable columns may be set."""
    spec = _spec(table)
    if society_id is None or pk_value is None or not values:
        return None
    bad = [c for c in values if c not in spec.updatable]
    if bad:
        raise ValueError(f"columns not updatable for {table}: {bad}")
    sets, params = [], []
    for col, val in values.items():
        sets.append(f"{col} = %s")
        params.append(val)
    where = [f"{spec.pk} = %s", f"{spec.tenant_col} = %s"]
    params += [pk_value, society_id]
    for col, val in (expect or {}).items():
        if col not in spec.columns:
            raise ValueError(f"expect column not registered for {table}: {col}")
        if isinstance(val, (list, tuple, set, frozenset)):
            vals = list(val)
            where.append(f"{col} IN ({', '.join(['%s'] * len(vals))})")
            params += vals
        else:
            where.append(f"{col} = %s")
            params.append(val)
    sql = f"UPDATE {spec.name} SET {', '.join(sets)} WHERE {' AND '.join(where)} RETURNING {spec.pk}"
    return _run(sql, tuple(params), cur)


def authorize_resource(action: str, resource_type: str, table: str, pk_value: Any, *,
                       attr_map: Optional[Mapping[str, str]] = None,
                       extra: Optional[Mapping[str, Any]] = None
                       ) -> tuple[AuthorizationDecision, Optional[dict]]:
    """Resolve the record in the principal's OWN society, derive authorization
    attributes from the ROW (attr_map: attribute -> column), then authorize.
    Returns (decision, row). A missing / foreign-tenant record is a denial with
    the same reason either way."""
    try:
        principal = current_principal()
    except PolicyUnavailable:
        return AuthorizationDecision(False, "policy unavailable", action, resource_type), None
    if principal is None or principal.society_id is None:
        return AuthorizationDecision(False, "no tenant", action, resource_type), None
    row = scoped_get(table, pk_value, principal.society_id)
    if row is None:
        d = AuthorizationDecision(False, "resource not found in this society", action, resource_type)
        audit_event("authz.denied" if authz_mode(action) == ENFORCE else "authz.shadow_denied",
                    resource_type, pk_value, reason=d.reason, permission_used=action,
                    principal=principal)
        return d, None
    attrs = {a: row.get(c) for a, c in (attr_map or {}).items()}
    attrs.update(extra or {})
    return check(action, resource_type, pk_value, target_society_id=row.get("society_id"),
                 attributes=attrs), row


@contextmanager
def unit_of_work():
    """One DB transaction: yields a cursor; commits on success, rolls back on
    any exception (db._conn handles both). Put the business write and its
    audit_event(cur=cur) inside the same block so neither can exist alone."""
    with _db()._conn() as conn:
        yield conn.cursor()
