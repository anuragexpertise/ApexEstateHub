# app/services/team_service.py
"""
Logins for the society's own employees and reviewers: Accountant, Supervisor, Staff and Auditor.

These are NOT residents, vendors or guards, so they have no flat / vendors / security_staff record behind them: a
login is one `users` row whose `role` routes the person to their own portal. This service is what lets the society
admin create, disable, re-enable and reset those logins.

  * Admin of the SAME society only (rra._require_writer, master_ok=False) and the caller needs `roles.manage`:
    creating a login confers powers. The society always comes from the caller's server-side session.
  * A new login is created with a password the admin chose, so `must_change_password` is TRUE: the person must set
    their own at first sign-in (same rule as every other account the admin creates).
  * An accountant login is also given the `accountant` RBAC role, so the database-grant engine (policy.py) agrees
    with the capability matrix in authorization.py. Disabling the login revokes nothing; it simply cannot sign in.
  * Disabling uses users.active. That is a different thing from a lockout: locked_until is cleared by a password
    reset, so it must not be how an account is switched off.
"""
from __future__ import annotations

import re

from flask import has_request_context
from werkzeug.security import generate_password_hash

from app.security.authorization import Cap
from app.security.password_policy import validate_password
from app.security.service_guard import audit_event
from app.services.regime_rules_admin import _require_writer
from database.db_manager import db

# (role, label, colour, what the role can do) - the colours are the portal themes.
TEAM_ROLES = (
    ("accountant", "Accountant", "#7c3aed",
     "Prepares receipts, expenses and cashbook entries; reads dues, ledgers and the year-end reports. "
     "Cannot approve payments or close a year."),
    ("supervisor", "Supervisor", "#ea580c",
     "Runs the gate and security staff: sets the shift roster and watches concerns, events and alert channels. "
     "No finance access."),
    ("staff", "Staff", "#94a3b8",
     "Read-only view of day-to-day concerns and events. No finance, no member data."),
    ("auditor", "Auditor", "#dc2626",
     "Independent, read-only: runs the verification checks and browses the books. Cannot change anything."),
)
ROLE_CODES = tuple(r[0] for r in TEAM_ROLES)
ROLE_LABEL = {r[0]: r[1] for r in TEAM_ROLES}
ROLE_COLOR = {r[0]: r[2] for r in TEAM_ROLES}
ROLE_BLURB = {r[0]: r[3] for r in TEAM_ROLES}

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _audit(cur, action, user_id, after):
    if has_request_context():
        audit_event(action, "user", user_id, after=after, permission_used=Cap.ROLES_MANAGE, cur=cur)


def _invalidate_permission_cache() -> None:
    try:
        from app.security import policy
        policy._invalidate_cache()
    except Exception:
        pass


def _db_message(exc: Exception) -> str:
    primary = getattr(getattr(exc, "diag", None), "message_primary", None)
    return primary or "The login could not be saved."


# ── reading ──────────────────────────────────────────────────────────────────────────────────────────────────────
def list_team(society_id: int) -> list[dict]:
    return db._execute(
        "SELECT id, name, email, role, active, last_login, created_at, must_change_password "
        "  FROM users WHERE society_id = %s AND role = ANY(%s) "
        " ORDER BY role, lower(COALESCE(name, email))",
        (int(society_id), list(ROLE_CODES)), fetch_all=True) or []


def get_member(society_id: int, user_id) -> dict | None:
    """One team login of THIS society, or None (a foreign or non-team id gets the same answer)."""
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    return db._execute(
        "SELECT id, name, email, role, active FROM users WHERE id = %s AND society_id = %s AND role = ANY(%s)",
        (uid, int(society_id), list(ROLE_CODES)), fetch_one=True)


# ── writing ──────────────────────────────────────────────────────────────────────────────────────────────────────
def create_login(actor_id, actor_role, society_id, role, name, email, password, actor_society_id=None) -> tuple[bool, str]:
    """Create a login for `role`. Returns (ok, message). Raises PermissionError for a caller who may not."""
    _require_writer(actor_role, actor_society_id, society_id, master_ok=False)
    if role not in ROLE_CODES:
        return False, "Choose a role."
    name = (name or "").strip()
    email = (email or "").strip().lower()
    if not name:
        return False, "Enter the person's full name."
    if not _EMAIL.match(email) or len(email) > 100:
        return False, "Enter a valid email address; it is the login."
    err = validate_password(password)
    if err:
        return False, err
    sid = int(society_id)
    try:
        with db._conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 AS x FROM users WHERE lower(email) = %s", (email,))
            if cur.fetchone():
                return False, "That email already has a login. Use a different email."
            cur.execute(
                "INSERT INTO users (society_id, email, password_hash, role, name, login_method, "
                "                   must_change_password, created_by) "
                "VALUES (%s, %s, %s, %s, %s, 'password', TRUE, %s) RETURNING id",
                (sid, email, generate_password_hash(password), role, name, actor_id))
            uid = (cur.fetchone() or {}).get("id")
            if role == "accountant" and uid:
                cur.execute("SELECT id FROM role_definitions WHERE code = 'accountant' AND scope = 'society'")
                rd = cur.fetchone()
                if rd:
                    cur.execute(
                        "INSERT INTO user_role_assignments (user_id, role_definition_id, society_id, source, status, "
                        "                                   granted_by) VALUES (%s, %s, %s, 'grant', 'active', %s)",
                        (uid, rd["id"], sid, actor_id))
            _audit(cur, "team.login.create", uid, {"role": role, "society_id": sid})
    except Exception as exc:
        return False, _db_message(exc)
    _invalidate_permission_cache()
    return True, (f"{ROLE_LABEL[role]} login created for {name}. They sign in with {email} and must choose a new "
                  "password at first sign-in.")


def set_active(actor_id, actor_role, society_id, user_id, active: bool, actor_society_id=None) -> tuple[bool, str]:
    _require_writer(actor_role, actor_society_id, society_id, master_ok=False)
    member = get_member(society_id, user_id)
    if not member:
        return False, "That login was not found."
    try:
        with db._conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE users SET active = %s WHERE id = %s AND society_id = %s AND role = ANY(%s)",
                        (bool(active), member["id"], int(society_id), list(ROLE_CODES)))
            _audit(cur, "team.login.enable" if active else "team.login.disable", member["id"], {"role": member["role"]})
    except Exception as exc:
        return False, _db_message(exc)
    who = member.get("name") or member["email"]
    return True, (f"{who} can sign in again." if active else f"{who} is disabled and can no longer sign in.")


def reset_password(actor_id, actor_role, society_id, user_id, new_password, actor_society_id=None) -> tuple[bool, str]:
    _require_writer(actor_role, actor_society_id, society_id, master_ok=False)
    member = get_member(society_id, user_id)
    if not member:
        return False, "That login was not found."
    err = validate_password(new_password)
    if err:
        return False, err
    try:
        with db._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET password_hash = %s, must_change_password = TRUE, failed_login_attempts = 0, "
                "       locked_until = NULL, reset_token = NULL, reset_token_expires = NULL "
                " WHERE id = %s AND society_id = %s AND role = ANY(%s)",
                (generate_password_hash(new_password), member["id"], int(society_id), list(ROLE_CODES)))
            _audit(cur, "team.login.reset_password", member["id"], {"role": member["role"]})
    except Exception as exc:
        return False, _db_message(exc)
    return True, f"Password reset for {member.get('name') or member['email']}. They must choose a new one at next sign-in."


def update_member(actor_id, actor_role, society_id, user_id, name=None, active=None, new_password=None,
                  actor_society_id=None) -> tuple[bool, str]:
    """Edit one team login from its profile page: name, enabled/disabled and (optionally) a new password.

    Every change goes through the same checks as create/disable/reset, so the profile form cannot do anything the
    Team Logins tab could not."""
    _require_writer(actor_role, actor_society_id, society_id, master_ok=False)
    member = get_member(society_id, user_id)
    if not member:
        return False, "That login was not found."
    if active is not None and not active and actor_id is not None and int(member["id"]) == int(actor_id):
        return False, "You cannot disable your own login."
    new_name = (name or "").strip()
    if name is not None and not new_name:
        return False, "Enter the person's full name."
    pw = (new_password or "").strip()
    if pw:
        err = validate_password(pw)
        if err:
            return False, err
    try:
        with db._conn() as conn:
            cur = conn.cursor()
            if new_name and new_name != (member.get("name") or ""):
                cur.execute("UPDATE users SET name = %s WHERE id = %s AND society_id = %s AND role = ANY(%s)",
                            (new_name, member["id"], int(society_id), list(ROLE_CODES)))
                _audit(cur, "team.login.update", member["id"], {"role": member["role"], "name": new_name})
            if active is not None and bool(active) != bool(member.get("active")):
                cur.execute("UPDATE users SET active = %s WHERE id = %s AND society_id = %s AND role = ANY(%s)",
                            (bool(active), member["id"], int(society_id), list(ROLE_CODES)))
                _audit(cur, "team.login.enable" if active else "team.login.disable", member["id"],
                       {"role": member["role"]})
            if pw:
                cur.execute(
                    "UPDATE users SET password_hash = %s, must_change_password = TRUE, failed_login_attempts = 0, "
                    "       locked_until = NULL, reset_token = NULL, reset_token_expires = NULL "
                    " WHERE id = %s AND society_id = %s AND role = ANY(%s)",
                    (generate_password_hash(pw), member["id"], int(society_id), list(ROLE_CODES)))
                _audit(cur, "team.login.reset_password", member["id"], {"role": member["role"]})
    except Exception as exc:
        return False, _db_message(exc)
    return True, f"{ROLE_LABEL[member['role']]} login updated."
