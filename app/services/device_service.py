# app/services/device_service.py
"""
Trusted devices for PIN / pattern sign-in.

A PIN or pattern is a short secret, so on its own it is far too weak to be a login. It is therefore only accepted
together with a *device token*: a random value issued to one account after a PASSWORD sign-in on one browser, kept in an
httpOnly cookie (``eh_device``) that JavaScript cannot read. Only its sha256 is stored (table ``user_devices``).

Rules this module implements
  * Password stays the way in on any new device. PIN / pattern work only where this account signed in before.
  * An account can trust many devices (one row each). Nothing here ever touches another device's row.
  * Signing out by hand removes THAT device's token; so does signing in on that device as a different account.
    The next sign-in there needs the password.
  * Wrong PIN/pattern tries are counted per device, atomically, BEFORE the secret is checked (see claim_attempt), so
    parallel guesses cannot exceed the limit. At MAX_DEVICE_FAILURES the device is untrusted and needs the password.
  * Every function degrades safely: if the table is missing or the database errors, no device is trusted (PIN/pattern
    refuse) while password sign-in keeps working.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta

from app.utils import now_ist
from database.db_manager import db

log = logging.getLogger(__name__)

COOKIE_NAME = "eh_device"
DEVICE_TTL_DAYS = 90            # sliding: every successful use pushes it out again
MAX_DEVICE_FAILURES = 5


def hash_token(token: str) -> str:
    """sha256 hex. The token is 256 bits of randomness, so a fast hash is enough (same choice as reset tokens)."""
    return hashlib.sha256((token or "").encode()).hexdigest()


def _expiry():
    return now_ist() + timedelta(days=DEVICE_TTL_DAYS)


# ── Cookie plumbing (Flask request/response) ────────────────────────────────

def current_token() -> str | None:
    """The device token the browser sent with this request, if any."""
    try:
        from flask import request
        tok = request.cookies.get(COOKIE_NAME)
        return tok if tok and len(tok) <= 200 else None
    except Exception:  # noqa: BLE001 - no request context
        return None


def request_user_agent() -> str | None:
    try:
        from flask import request
        return request.user_agent.string or None
    except Exception:  # noqa: BLE001 - no request context
        return None


def set_cookie(token: str) -> None:
    """Attach the device cookie to whatever response this request ends up producing (Dash callbacks included)."""
    from flask import after_this_request, request

    from app.security.secret_policy import is_production
    secure = is_production() or request.is_secure

    @after_this_request
    def _attach(response):
        response.set_cookie(COOKIE_NAME, token, max_age=DEVICE_TTL_DAYS * 24 * 3600, path="/",
                            secure=secure, httponly=True, samesite="Lax")
        return response


def clear_cookie() -> None:
    from flask import after_this_request

    @after_this_request
    def _drop(response):
        response.delete_cookie(COOKIE_NAME, path="/")
        return response


# ── Token lifecycle ─────────────────────────────────────────────────────────

def issue(user_id: int, user_agent: str | None = None) -> str:
    """Create a trusted-device row for this account and return the PLAIN token (the only time it exists server-side)."""
    token = secrets.token_urlsafe(32)
    db._execute(
        """INSERT INTO user_devices (user_id, token_hash, label, expires_at)
           VALUES (:uid, :h, :label, :exp)""",
        {"uid": user_id, "h": hash_token(token), "label": (user_agent or "")[:160] or None, "exp": _expiry()},
    )
    return token


def lookup(token: str | None) -> dict | None:
    """The row for this token in ANY state (expired / over the failure limit included), or None."""
    if not token:
        return None
    try:
        return db._execute(
            "SELECT id, user_id, expires_at, failed_attempts FROM user_devices WHERE token_hash = :h",
            {"h": hash_token(token)}, fetch_one=True,
        )
    except Exception:  # noqa: BLE001
        log.exception("device lookup failed")
        return None


def is_usable(row: dict | None) -> bool:
    from app.utils import as_ist
    return bool(row) and as_ist(row["expires_at"]) > now_ist() and (row.get("failed_attempts") or 0) < MAX_DEVICE_FAILURES


def claim_attempt(token: str | None, user_id: int) -> dict | None:
    """Spend one PIN/pattern attempt on this device, atomically, and return the row; None = this device is not trusted
    for this account (unknown token, someone else's token, expired, or out of attempts).

    The attempt is counted *before* the secret is compared. A single guarded UPDATE is the whole gate, so N parallel
    requests can pass it at most MAX_DEVICE_FAILURES times between two successes — checking first and counting after
    would let a burst of parallel guesses all slip through. A correct secret then calls mark_success() to give it back.
    """
    if not token:
        return None
    try:
        return db._execute(
            """UPDATE user_devices
                  SET failed_attempts = failed_attempts + 1
                WHERE token_hash = :h AND user_id = :uid
                  AND expires_at > :now AND failed_attempts < :max
            RETURNING id, user_id, failed_attempts""",
            {"h": hash_token(token), "uid": user_id, "now": now_ist(), "max": MAX_DEVICE_FAILURES},
            fetch_one=True,
        )
    except Exception:  # noqa: BLE001
        log.exception("device claim_attempt failed")
        return None


def mark_success(device_id: int) -> None:
    """Correct secret: give the attempt back, stamp last use and slide the expiry."""
    try:
        db._execute(
            "UPDATE user_devices SET failed_attempts = 0, last_used_at = :now, expires_at = :exp WHERE id = :id",
            {"now": now_ist(), "exp": _expiry(), "id": device_id},
        )
    except Exception:  # noqa: BLE001
        log.exception("device mark_success failed")


def revoke_by_id(device_id: int) -> None:
    try:
        db._execute("DELETE FROM user_devices WHERE id = :id", {"id": device_id})
    except Exception:  # noqa: BLE001
        log.exception("device revoke_by_id failed")


def revoke_token(token: str | None) -> bool:
    """Remove exactly this browser's token (manual sign-out). Other devices are untouched."""
    if not token:
        return False
    try:
        db._execute("DELETE FROM user_devices WHERE token_hash = :h", {"h": hash_token(token)})
        return True
    except Exception:  # noqa: BLE001
        log.exception("device revoke_token failed")
        return False


def revoke_all(user_id: int) -> None:
    """Every trusted device of one account (password reset, 'turn off quick sign-in')."""
    try:
        db._execute("DELETE FROM user_devices WHERE user_id = :uid", {"uid": user_id})
    except Exception:  # noqa: BLE001
        log.exception("device revoke_all failed")


def revoke_for_users_where(where_sql: str, params) -> None:
    """Revoke the devices of every user matching a WHERE clause on ``users`` (admin-set passwords address users by
    linked_id/role, not by id). ``where_sql`` is code, never user input; values go in ``params``."""
    try:
        db._execute(f"DELETE FROM user_devices WHERE user_id IN (SELECT id FROM users WHERE {where_sql})", params)
    except Exception:  # noqa: BLE001
        log.exception("device revoke_for_users_where failed")


# ── What the sign-in rules need ─────────────────────────────────────────────

def after_password_login(user_id: int, remember: bool, user_agent: str | None = None) -> str | None:
    """Apply the device rules after a successful PASSWORD sign-in. Returns a freshly issued/refreshed plain token (or None).

      * this browser holds a token that belongs to a DIFFERENT account  -> that token is deleted (the device is no
        longer trusted for the previous account; the cookie is cleared);
      * remember=True -> make sure this browser holds a usable token for THIS account (reuse and refresh, else issue);
      * remember=False -> nothing is added; an existing token of this same account is left alone.
    Never raises: a device problem must not stop a correct password from signing in.
    """
    try:
        user_agent = user_agent or request_user_agent()
        token = current_token()
        row = lookup(token)
        if row and row["user_id"] != user_id:
            revoke_by_id(row["id"])
            clear_cookie()
            token, row = None, None
        elif token and not row:
            clear_cookie()                      # stale cookie whose row is gone
            token = None
        if not remember:
            return None
        if token and row:                       # same account: reuse, give back any spent attempts, slide the expiry
            mark_success(row["id"])
            set_cookie(token)
            return token
        new = issue(user_id, user_agent)
        set_cookie(new)
        return new
    except Exception:  # noqa: BLE001
        log.exception("after_password_login device handling failed (password sign-in is unaffected)")
        return None


def after_quick_login() -> None:
    """PIN/pattern sign-in succeeded: slide the browser cookie's lifetime to match the row's."""
    token = current_token()
    if token:
        try:
            set_cookie(token)
        except Exception:  # noqa: BLE001
            log.exception("could not refresh the device cookie")


def sign_out_this_device(explicit_token: str | None = None) -> None:
    """MANUAL sign-out: forget this device's token (server row + cookie). Other devices are not affected.
    ``explicit_token`` is for API clients that hold the token themselves instead of in the cookie."""
    cookie_token = current_token()
    for token in {t for t in (cookie_token, explicit_token) if t}:
        revoke_token(token)
    if cookie_token:
        try:
            clear_cookie()
        except Exception:  # noqa: BLE001
            log.exception("could not clear the device cookie")


def trusted_user(society_id: int | None) -> dict | None:
    """For the sign-in screen: who (email, which quick methods are set) does THIS browser's usable token belong to, within
    this society? None when there is no usable token, the account is switched off, or it belongs to another society."""
    token = current_token()
    if not token or not society_id:
        return None
    from app.models.user import active_select    # users.active may not exist on a database that predates it
    try:
        row = db._execute(
            """SELECT u.email, (u.pin_hash IS NOT NULL) AS has_pin, (u.pattern_hash IS NOT NULL) AS has_pattern,
                      d.expires_at, d.failed_attempts""" + active_select() + """
                 FROM user_devices d JOIN users u ON u.id = d.user_id
                WHERE d.token_hash = :h AND u.society_id = :sid""",
            {"h": hash_token(token), "sid": society_id}, fetch_one=True,
        )
    except Exception:  # noqa: BLE001
        log.exception("trusted_user lookup failed")
        return None
    if not is_usable(row) or row.get("active") is False or not (row["has_pin"] or row["has_pattern"]):
        return None
    return {"email": row["email"], "has_pin": bool(row["has_pin"]), "has_pattern": bool(row["has_pattern"])}
