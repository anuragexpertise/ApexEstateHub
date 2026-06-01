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


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_auth(row: dict) -> dict | None:
    """Convert a DB user row into the auth-store payload."""
    if not row:
        return None
    return {
        "user_id":           row["id"],
        "email":             row["email"],
        "role":              row["role"],
        "society_id":        row.get("society_id"),
        "linked_id":         row.get("linked_id"),
        "token":             secrets.token_hex(32),
        "push_subscription": row.get("push_subscription"),
    }


def _fetch_user(email: str, society_id: int | None) -> dict | None:
    """Fetch user row by email + society scope."""
    try:
        if society_id is None:
            return db.execute(
                """SELECT id, email, role, society_id, linked_id,
                          password_hash, pin_hash, pattern_hash, push_subscription
                   FROM users
                   WHERE email = :email
                     AND is_master_admin = TRUE""",
                {"email": email},
                fetch_one=True,
            )
        return db.execute(
            """SELECT id, email, role, society_id, linked_id,
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


# ── Login methods ─────────────────────────────────────────────────────────────

def authenticate_user(email: str, password: str,
                      society_id: int | None = None) -> dict | None:
    """Verify email + password (werkzeug check_password_hash)."""
    row = _fetch_user(email, society_id)
    if not row:
        log.warning("No user: %s sid=%s", email, society_id)
        return None
    stored = row.get("password_hash") or ""
    if not stored or not check_password_hash(stored, password):
        log.warning("Bad password: %s", email)
        return None
    return _build_auth(row)


def authenticate_pin(email: str, pin: str,
                     society_id: int | None = None) -> dict | None:
    """Verify email + PIN (werkzeug hash in pin_hash column)."""
    row = _fetch_user(email, society_id)
    if not row:
        return None
    stored = row.get("pin_hash") or ""
    if not stored or not check_password_hash(stored, pin):
        return None
    return _build_auth(row)


def authenticate_pattern(email: str, pattern: str,
                         society_id: int | None = None) -> dict | None:
    """Verify email + pattern string (werkzeug hash in pattern_hash column)."""
    row = _fetch_user(email, society_id)
    if not row:
        return None
    stored = row.get("pattern_hash") or ""
    if not stored or not check_password_hash(stored, pattern):
        return None
    return _build_auth(row)


# ── Password reset ────────────────────────────────────────────────────────────

def request_password_reset(email: str,
                           society_id: int | None = None) -> tuple[bool, str, str | None]:
    """Generate 6-digit reset token. Returns (ok, message, plain_token)."""
    try:
        q = "SELECT id FROM users WHERE email = :email"
        p: dict = {"email": email}
        if society_id:
            q += " AND society_id = :sid"
            p["sid"] = society_id

        user = db.execute(q, p, fetch_one=True)
        if not user:
            return False, "No account found with that email.", None

        plain  = "".join(secrets.choice(string.digits) for _ in range(6))
        hashed = generate_password_hash(plain)
        expiry = datetime.now() + timedelta(hours=1)

        db.execute(
            """UPDATE users SET reset_token = :tok, reset_token_expiry = :exp
               WHERE id = :uid""",
            {"tok": hashed, "exp": expiry, "uid": user["id"]},
        )
        return True, f"Reset token sent to {email}.", plain
    except Exception:
        log.exception("request_password_reset error")
        return False, "Error generating reset token.", None


def reset_password(plain_token: str, new_password: str) -> tuple[bool, str]:
    """Match plain_token against stored hashes, then update password."""
    try:
        rows = db.execute(
            """SELECT id, reset_token FROM users
               WHERE reset_token IS NOT NULL AND reset_token_expiry > NOW()""",
            fetch_all=True,
        ) or []

        uid = next(
            (r["id"] for r in rows if check_password_hash(r["reset_token"], plain_token)),
            None,
        )
        if not uid:
            return False, "Invalid or expired reset token."

        db.execute(
            """UPDATE users
               SET password_hash = :ph, reset_token = NULL, reset_token_expiry = NULL
               WHERE id = :uid""",
            {"ph": generate_password_hash(new_password), "uid": uid},
        )
        return True, "Password updated successfully."
    except Exception:
        log.exception("reset_password error")
        return False, "Error resetting password."
