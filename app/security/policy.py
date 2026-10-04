# app/security/policy.py
"""
Fine-grained, society-scoped authorization engine (Phase 1 — D1 = Option B).

Decision boundary
-----------------
`users.role` is the PORTAL gate (which dashboard the user lands on). That gate
is coarse and lives in `app/security/roles.py`. Once inside a portal, the
*actions* a user may perform are decided here, on the security-critical surface:
financial actions, role grants, period close, concern resolution, poll
declaration — NOT every callback at once (see plan §D1).

The engine answers one question:

    can(user_id, action, resource, society_id=?, entity_id=?, amount=?) -> (bool, reason)

Truth source
------------
A user's effective permissions come from active `user_role_assignments` rows
(effective-dated, status='active'), joined to `role_permissions` grants on
`permissions(resource, action)`. A grant matches the request when:

  * the user holds an active assignment whose society_id is NULL (platform
    role — applies everywhere) or equals the requested society_id;
  * the grant's scope_society_id is NULL (applies wherever the role is held) or
    equals the requested society_id (society-pinned grant); and
  * any min_amount on the grant is satisfied — an amount at/above min_amount
    cannot be approved by this role alone (requires escalation).

Delegations (maker/checker hand-over) are folded in: a delegatee with an active
delegation for the (permission, society) may act on behalf of a delegator.

Never trust the client
----------------------
`user_id` must be the SERVER-resolved id (from
`app/security/audit_context.get_current_user_id()`), never the browser's
auth-store value — see get_server_auth().

Caching
-------
Per-request grant lookups are cached on `flask.g`. The cache is discarded the
moment a write touches user_role_assignments / role_permissions / delegations,
so a grant/revoke within the same request is visible to the next can() call.
"""
from __future__ import annotations

import logging

from database.db_manager import db

log = logging.getLogger(__name__)


class Permission:
    """Dotted-string permission keys (the form used at call sites, e.g.
    policy.can(user, Permission.CONCERN_ASSIGN, society_id=1)). The legacy
    `can()` ALSO accepts a (resource, action) tuple for backward compatibility."""
    CONCERN_ASSIGN          = "concern.assign"
    CONCERN_RESOLVE         = "concern.resolve"
    POLL_DECLARE_RESULTS    = "poll.declare_results"
    FINANCE_RECEIPT_VIEW    = "finance.receipt.view_own"
    FINANCE_PAYMENT_APPROVE = "finance.payment.approve"
    FINANCE_PERIOD_CLOSE    = "finance.period.close"
    ENROLLMENT_IMPORT       = "enrollment.import"
    ROLE_GRANT              = "role.grant"
    VISITOR_APPROVE         = "visitor.approve"


def _split_permission(permission):
    """Normalize a permission arg to (resource, action). Accepts a dotted
    'resource.action' string or a (resource, action) tuple."""
    if isinstance(permission, tuple):
        return permission[0], permission[1]
    if isinstance(permission, str) and "." in permission:
        resource, _, action = permission.partition(".")
        return resource, action
    raise ValueError(f"invalid permission spec: {permission!r}")


_CACHE_ATTR = "_rbac_grants_cache"
_INVALIDATE_FLAG = "_rbac_policy_invalidated"


def _invalidate_cache() -> None:
    """Drop the per-request grant cache. Call after writing to any of the
    user_role_assignments / role_permissions / delegations tables."""
    try:
        from flask import g, has_request_context
        if has_request_context():
            setattr(g, _INVALIDATE_FLAG, True)
            g.__dict__.pop(_CACHE_ATTR, None)
    except Exception:
        pass


def _user_grants(user_id, society_id):
    """Resolve the user's effective grants in `society_id` (or globally when
    society_id is None) from the DB, cached per-request on flask.g.

    Returns a list of dicts:
        {role_code, role_scope, society_id, effective_to,
         scope_society_id, min_amount, approval_threshold,
         resource, action}

    Natural join scoping enforces cross-society isolation: a society-scoped
    assignment only matches the society it belongs to (ura.society_id = :society
    or NULL for platform roles), and a society-pinned grant only matches its
    scope_society_id.
    """
    try:
        from flask import g, has_request_context
        if has_request_context() and getattr(g, _INVALIDATE_FLAG, False):
            g.__dict__.pop(_CACHE_ATTR, None)
        cache = getattr(g, _CACHE_ATTR, None) if has_request_context() else None
        if cache is not None and (user_id, society_id) in cache:
            return cache[(user_id, society_id)]
    except Exception:
        cache = None

    grants = _query_grants(user_id, society_id)
    if cache is not None:
        cache[(user_id, society_id)] = grants
    return grants


def _query_grants(user_id, society_id) -> list[dict]:
    """The actual DB query behind the cache. Returns the joined grant
    descriptors for _user_grants."""
    rows = db._execute(
        """SELECT p.resource, p.action, rp.scope_society_id, rp.min_amount,
                  rp.approval_threshold, rd.code AS role_code, rd.scope AS role_scope,
                  ura.society_id AS ura_society, ura.effective_to, ura.entity_link
             FROM user_role_assignments ura
             JOIN role_definitions rd   ON rd.id = ura.role_definition_id
             JOIN role_permissions rp   ON rp.role_definition_id = rd.id
             JOIN permissions p         ON p.id = rp.permission_id
            WHERE ura.user_id = :uid
              AND ura.status = 'active'
              AND (ura.effective_to IS NULL OR ura.effective_to > NOW())
              AND (ura.society_id IS NULL OR ura.society_id = :society)""",
        {"uid": user_id, "society": society_id},
        fetch_all=True,
    ) or []
    return rows


def _has_delegated_permission(user_id, resource, action, society_id) -> bool:
    """True if the user holds an active delegation covering (resource, action)
    for this society (or for all societies if the delegation is platform-scoped)."""
    row = db._execute(
        """SELECT 1 FROM delegations d
             JOIN permissions p ON p.id = d.permission_id
            WHERE d.delegatee_id = :uid
              AND p.resource = :resource AND p.action = :action
              AND d.revoked_at IS NULL
              AND (d.effective_to IS NULL OR d.effective_to > NOW())
              AND (d.society_id IS NULL OR d.society_id = :society)
            LIMIT 1""",
        {"uid": user_id, "resource": resource, "action": action, "society": society_id},
        fetch_one=True,
    )
    return bool(row)


def _resolve_role_definition_id(code, scope):
    row = db._execute(
        "SELECT id FROM role_definitions WHERE code = :code AND scope = :scope",
        {"code": code, "scope": scope}, fetch_one=True,
    )
    return (row or {}).get("id")


# ── public API ────────────────────────────────────────────────────────────────

def can(user_id, permission, society_id=None, entity_id=None, amount=None):
    """
    Decide whether `user_id` may perform `permission` in `society_id`.

    Args:
        permission: a dotted "resource.action" string (e.g. "concern.assign") or
            a (resource, action) tuple.
        society_id: tenant scope. NULL => platform-scope; a platform role or a
            platform-pinned grant is required to answer.
        entity_id: entity the action targets (apartment/vendor/security). Honoured
            when grants/s assignments carry an entity_link; currently informational
            for cross-entity ownership checks.
        amount: money amount for threshold checks (min_amount).

    Returns (allowed: bool, reason: str). ``reason`` is "" on allow and a
    human-readable denial cause otherwise.

    Denials, in priority order:
      * no authenticated user (None id)            -> "no authenticated user"
      * nothing granted and no delegation          -> "no role grants '<p>'"
      * expired assignment (matching role+society) -> "assignment expired <date>"
      * role held only in a different society       -> "role <x> is not permitted
                                                      in this society"
      * amount >= min_amount on the matching grant    -> "amount X >= floor Y —
                                                      requires higher approval"
    """
    if user_id is None:
        return False, "no authenticated user"
    resource, action = _split_permission(permission)

    grants = _user_grants(user_id, society_id)
    granted = _match_grant(grants, resource, action, society_id)

    if not granted:
        delegated = _has_delegated_permission(user_id, resource, action, society_id)
        if not delegated:
            return False, _denial_reason(grants, resource, action, society_id)

    # Money threshold check on the matching grant(s).
    if amount is not None and amount > 0:
        ok, reason = _check_threshold(grants, resource, action, society_id, amount)
        if not ok:
            return False, reason

    return True, ""


def can_do(user_id, permission, society_id=None, entity_id=None, amount=None):
    """Alias for can() — the plan and call sites use `policy.can_do(...)`."""
    return can(user_id, permission, society_id=society_id,
               entity_id=entity_id, amount=amount)


def _match_grant(grants, resource, action, society_id):
    """True if any grant matches (resource, action) AND its scope_society_id
    is NULL (wherever the role is held) or equals the requested society."""
    for g in grants:
        if g.get("resource") != resource or g.get("action") != action:
            continue
        scope = g.get("scope_society_id")
        if scope is None or scope == society_id:
            return True
    return False


def _check_threshold(grants, resource, action, society_id, amount):
    """If any matching grant carries a min_amount and the amount is at/above it,
    the role alone cannot approve — escalate."""
    for g in grants:
        if g.get("resource") != resource or g.get("action") != action:
            continue
        scope = g.get("scope_society_id")
        if scope is not None and scope != society_id:
            continue
        min_amt = g.get("min_amount")
        if min_amt is not None and float(amount) >= float(min_amt):
            return False, (
                f"amount {amount} >= approval floor {min_amt} for role "
                f"{g.get('role_code') or ''} — requires higher approval"
            )
    return True, ""


def _denial_reason(grants, resource, action, society_id):
    """Produce a concise, prioritized denial reason."""
    now_active = []
    expired = []
    for g in grants:
        if g.get("resource") != resource or g.get("action") != action:
            continue
        exp = g.get("effective_to")
        if exp is not None and exp <= _now():
            expired.append(g)
        else:
            now_active.append(g)

    # Expired assignment for a matching role+society.
    if expired:
        g = expired[0]
        return f"assignment expired on {g.get('effective_to')} for role {g.get('role_code')}"

    # Matching role but only in a different society.
    held = None
    for g in grants:
        if g.get("resource") == resource and g.get("action") == action:
            held = g
            break
    if held:
        return f"role {held.get('role_code')} is not permitted in this society"
    return f"no role grants '{resource}.{action}'"


def _now():
    from datetime import datetime
    return datetime.utcnow()


def effective_roles(user_id, society_id=None) -> list[dict]:
    """Return the user's active role_definition codes (with society context).
    Convenience helper for UI rendering / debugging."""
    grants = _user_grants(user_id, society_id)
    seen = {}
    for g in grants:
        key = (g.get("role_code"), g.get("ura_society"), g.get("entity_link"))
        seen[key] = {
            "code": g.get("role_code"),
            "society_id": g.get("ura_society"),
            "entity_link": g.get("entity_link"),
        }
    return list(seen.values())


def grant_role(user_id, role_code, society_id=None, granted_by=None, source="grant",
               entity_link=None) -> tuple[bool, str, int | None]:
    """Grant a role_definition to a user. The caller MUST have already passed
    policy.can(user, *Permission.ROLE_GRANT, society_id). Returns
    (ok, message, assignment_id)."""
    scope = "platform" if society_id is None else "society"
    rd_id = _resolve_role_definition_id(role_code, scope)
    if rd_id is None:
        return False, f"unknown role_definition code: {role_code}", None
    row = db._execute(
        """INSERT INTO user_role_assignments
             (user_id, role_definition_id, society_id, entity_link, granted_by, source, status)
           VALUES (:uid, :rd, :sid, :elink, :by, :src, 'active')
           RETURNING id""",
        {"uid": user_id, "rd": rd_id, "sid": society_id, "elink": entity_link,
         "by": granted_by, "src": source},
        fetch_one=True,
    )
    if row:
        _invalidate_cache()
        return True, "role granted", row.get("id")
    return False, "grant failed", None


def revoke_role(user_id, role_code, society_id=None) -> tuple[bool, str]:
    """Revoke an active assignment by setting status='revoked'."""
    scope = "platform" if society_id is None else "society"
    rd_id = _resolve_role_definition_id(role_code, scope)
    if rd_id is None:
        return False, f"unknown role_definition code: {role_code}"
    db._execute(
        """UPDATE user_role_assignments
              SET status = 'revoked', effective_to = NOW()
            WHERE user_id = :uid AND role_definition_id = :rd
              AND (society_id IS NULL AND :sid IS NULL
                   OR society_id = :sid)
              AND status = 'active'""",
        {"uid": user_id, "rd": rd_id, "sid": society_id},
    )
    _invalidate_cache()
    return True, "role revoked"
