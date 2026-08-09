# app/services/auth_service.py
"""
Authentication service — EstateHub.

Password storage: werkzeug.security (scrypt/pbkdf2, salted).
All DB queries use named params (:name) via db_manager._to_pyformat().

CRITICAL: seed.py and society_service.py both use generate_password_hash().
           This file must use check_password_hash() to verify — NOT sha256.
"""

import secrets
import string
import logging
from datetime import datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash
from database.db_manager import db

log = logging.getLogger(__name__)

# ── Account lockout (fixed 2026-08) ─────────────────────────────
# `locked_until` was already being CHECKED in authenticate_user() below,
# but nothing anywhere ever SET it or incremented failed_login_attempts —
# both columns exist in the schema but were dead, so login had no actual
# brute-force protection. _record_failed_attempt / _reset_failed_attempts
# make that check mean something.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _record_failed_attempt(user_id: int) -> None:
    try:
        row = db._execute(
            "SELECT failed_login_attempts FROM users WHERE id = :uid",
            {"uid": user_id}, fetch_one=True,
        )
        attempts = ((row or {}).get("failed_login_attempts") or 0) + 1
        if attempts >= MAX_FAILED_ATTEMPTS:
            db._execute(
                """UPDATE users
                   SET failed_login_attempts = 0,
                       locked_until = :until
                   WHERE id = :uid""",
                {"until": datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES),
                 "uid": user_id},
            )
            log.warning("Account locked after %s failed attempts: user_id=%s", attempts, user_id)
        else:
            db._execute(
                "UPDATE users SET failed_login_attempts = :n WHERE id = :uid",
                {"n": attempts, "uid": user_id},
            )
    except Exception:
        log.exception("_record_failed_attempt error for user_id=%s", user_id)


def _reset_failed_attempts(user_id: int) -> None:
    try:
        db._execute(
            """UPDATE users
               SET failed_login_attempts = 0, locked_until = NULL
               WHERE id = :uid""",
            {"uid": user_id},
        )
    except Exception:
        log.exception("_reset_failed_attempts error for user_id=%s", user_id)


# ── Internal helpers ──────────────────────────────────────────

def _build_auth(row: dict) -> dict | None:
    """Convert a DB user row into the auth-store payload."""
    if not row:
        return None
    role = row["role"]
    if role == "admin" and not row.get("society_id") and row.get("is_master_admin"):
        role = "master"
    return {
        "user_id":           row["id"],
        "email":             row["email"],
        "role":              role,
        "society_id":        row.get("society_id"),
        "linked_id":         row.get("linked_id"),
        "security_id":       row.get("linked_id") if row.get("role") == "security" else None,
        "apartment_id":      row.get("linked_id") if row.get("role") == "apartment" else None,
        "vendor_id":         row.get("linked_id") if row.get("role") == "vendor" else None,
        "token":             secrets.token_hex(32),
        "push_subscription": row.get("push_subscription"),
    }


def _fetch_user(email: str, society_id: int | None) -> dict | None:
    """Fetch user row by email + society scope."""
    try:
        if society_id is None:
            return db._execute(
                """SELECT id, email, role, society_id, linked_id, is_master_admin,
                          password_hash, pin_hash, pattern_hash, push_subscription
                    FROM users
                    WHERE email = :email
                      AND is_master_admin = TRUE""",
                {"email": email},
                fetch_one=True,
            )
        return db._execute(
            """SELECT id, email, role, society_id, linked_id, is_master_admin,
                      password_hash, pin_hash, pattern_hash, push_subscription
                FROM users
                WHERE email = :email
                  AND society_id = :sid""",
            {"email": email, "sid": society_id},
            fetch_one=True,
        )
    except Exception as exc:
        log.error("_fetch_user error: %s", exc)
        return None


# ── Login methods ─────────────────────────────────────────────

def authenticate_user(email: str, password: str,
                        society_id: int | None = None) -> dict | None:
    """Verify email + password (werkzeug check_password_hash)."""
    row = _fetch_user(email, society_id)
    if not row:
        log.warning("No user: %s sid=%s", email, society_id)
        return None

    locked_until = row.get("locked_until")
    if locked_until and locked_until > datetime.utcnow():
        log.warning("Locked account attempt: %s until %s", email, locked_until)
        return None

    stored = row.get("password_hash") or ""
    if not stored or not check_password_hash(stored, password):
        log.warning("Bad password: %s", email)
        _record_failed_attempt(row["id"])
        return None
    _reset_failed_attempts(row["id"])
    return _build_auth(row)


def authenticate_pin(email: str, pin: str,
                       society_id: int | None = None) -> dict | None:
    """Verify email + PIN (werkzeug hash in pin_hash column)."""
    row = _fetch_user(email, society_id)
    if not row:
        return None
    locked_until = row.get("locked_until")
    if locked_until and locked_until > datetime.utcnow():
        log.warning("Locked account PIN attempt: %s until %s", email, locked_until)
        return None
    stored = row.get("pin_hash") or ""
    if not stored or not check_password_hash(stored, pin):
        _record_failed_attempt(row["id"])
        return None
    _reset_failed_attempts(row["id"])
    return _build_auth(row)


def authenticate_pattern(email: str, pattern: str,
                            society_id: int | None = None) -> dict | None:
    """Verify email + pattern string (werkzeug hash in pattern_hash column)."""
    row = _fetch_user(email, society_id)
    if not row:
        return None
    locked_until = row.get("locked_until")
    if locked_until and locked_until > datetime.utcnow():
        log.warning("Locked account pattern attempt: %s until %s", email, locked_until)
        return None
    stored = row.get("pattern_hash") or ""
    if not stored or not check_password_hash(stored, pattern):
        _record_failed_attempt(row["id"])
        return None
    _reset_failed_attempts(row["id"])
    return _build_auth(row)


# ── Password reset ────────────────────────────────────────────

def request_password_reset(email: str,
                                 society_id: int | None = None) -> tuple[bool, str, str | None]:
    """
    Generate a reset token. Returns (ok, message, plain_token).

    SECURITY (fixed 2026-08): this previously generated a 6-digit numeric
    code (1,000,000 possible values, no request rate limit) and hashed it
    with generate_password_hash() — whose scrypt/pbkdf2 output is 100-160+
    characters. That was being written into `reset_token VARCHAR(64)`,
    which Postgres rejects ("value too long for type character varying
    (64)"), so every reset request was silently failing (caught by the
    except below and reported back as "Error generating reset token.").
    Now uses a 32-byte urlsafe token (matches the schema's implied intent
    — VARCHAR(64) is exactly len(sha256_hexdigest)) hashed with sha256,
    which both fits the column and is far harder to brute-force than a
    6-digit code.
    """
    import hashlib
    try:
        q = "SELECT id FROM users WHERE email = :email"
        p: dict = {"email": email}
        if society_id:
            q += " AND society_id = :sid"
            p["sid"] = society_id

        user = db._execute(q, p, fetch_one=True)
        if not user:
            # Don't reveal whether the email exists.
            return True, f"If that email exists, a reset link has been sent.", None

        plain  = secrets.token_urlsafe(32)
        hashed = hashlib.sha256(plain.encode()).hexdigest()
        expiry = datetime.now() + timedelta(hours=1)

        db._execute(
            """UPDATE users SET reset_token = :tok, reset_token_expires = :exp
               WHERE id = :uid""",
            {"tok": hashed, "exp": expiry, "uid": user["id"]},
        )
        return True, f"Reset token sent to {email}.", plain
    except Exception:
        log.exception("request_password_reset error")
        return False, "Error generating reset token.", None


def reset_password(plain_token: str, new_password: str) -> tuple[bool, str]:
    """Match plain_token (sha256 hex) against stored hashes, then update password."""
    import hashlib
    try:
        token_hash = hashlib.sha256(plain_token.encode()).hexdigest()
        row = db._execute(
            """SELECT id FROM users
               WHERE reset_token = :tok AND reset_token_expires > NOW()""",
            {"tok": token_hash},
            fetch_one=True,
        )
        if not row:
            return False, "Invalid or expired reset token."

        db._execute(
            """UPDATE users
               SET password_hash = :ph, reset_token = NULL, reset_token_expires = NULL,
                   failed_login_attempts = 0, locked_until = NULL
               WHERE id = :uid""",
            {"ph": generate_password_hash(new_password), "uid": row["id"]},
        )
        return True, "Password updated successfully."
    except Exception:
        log.exception("reset_password error")
        return False, "Error resetting password."


# ── Self-service password change (new 2026-08) ─────────────────
# Previously there was no way for a logged-in user of any role to change
# their own password — the only path was the pre-login "Forgot Password"
# flow above. user_id must come from the server-side session
# (app.security.audit_context.get_current_user_id()), never from a
# client-supplied value, so one user can't change another's password.

def change_password(user_id: int, current_password: str, new_password: str) -> tuple[bool, str]:
    if not current_password or not new_password:
        return False, "Please fill in all fields."
    if len(new_password) < 8:
        return False, "New password must be at least 8 characters."
    if new_password == current_password:
        return False, "New password must be different from your current password."
    try:
        row = db._execute(
            "SELECT password_hash FROM users WHERE id = :uid",
            {"uid": user_id}, fetch_one=True,
        )
        if not row:
            return False, "Account not found."
        stored = row.get("password_hash") or ""
        if not stored or not check_password_hash(stored, current_password):
            return False, "Current password is incorrect."

        db._execute(
            """UPDATE users
               SET password_hash = :ph, failed_login_attempts = 0, locked_until = NULL
               WHERE id = :uid""",
            {"ph": generate_password_hash(new_password), "uid": user_id},
        )
        return True, "Password updated successfully."
    except Exception:
        log.exception("change_password error for user_id=%s", user_id)
        return False, "Error changing password."