# app/services/auth_service.py
"""
Authentication service for EstateHub.

All DB calls use SQLAlchemy-style named params (:name).
Supports password, PIN, pattern login and password reset.
"""

import hashlib
import secrets
import string
from datetime import datetime, timedelta

from database.db_manager import db


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _build_user(row: dict) -> dict | None:
    if not row:
        return None
    return {
        "user_id":          row["id"],
        "email":            row["email"],
        "role":             row["role"],
        "society_id":       row.get("society_id"),
        "linked_id":        row.get("linked_id"),
        "token":            secrets.token_hex(32),
        "push_subscription": row.get("push_subscription"),
    }


# ── Login methods ─────────────────────────────────────────────────────────────

def authenticate_user(email: str, password: str, society_id: int | None = None) -> dict | None:
    """Verify email + password. society_id=None means master admin."""
    try:
        ph = _hash(password)
        if society_id is None:
            row = db.execute(
                """SELECT id, email, role, society_id, linked_id, push_subscription
                   FROM users
                   WHERE email = :email
                     AND password_hash = :ph
                     AND (society_id IS NULL OR role = 'admin')""",
                {"email": email, "ph": ph},
                fetch_one=True,
            )
        else:
            row = db.execute(
                """SELECT id, email, role, society_id, linked_id, push_subscription
                   FROM users
                   WHERE email = :email
                     AND password_hash = :ph
                     AND society_id = :sid""",
                {"email": email, "ph": ph, "sid": society_id},
                fetch_one=True,
            )
        return _build_user(row)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("authenticate_user error: %s", exc)
        return None


def authenticate_pin(email: str, pin: str, society_id: int | None = None) -> dict | None:
    try:
        ph = _hash(pin)
        row = db.execute(
            """SELECT id, email, role, society_id, linked_id, push_subscription
               FROM users
               WHERE email = :email
                 AND pin_hash = :ph
                 AND society_id = :sid""",
            {"email": email, "ph": ph, "sid": society_id},
            fetch_one=True,
        )
        return _build_user(row)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("authenticate_pin error: %s", exc)
        return None


def authenticate_pattern(email: str, pattern: str, society_id: int | None = None) -> dict | None:
    try:
        ph = _hash(pattern)
        row = db.execute(
            """SELECT id, email, role, society_id, linked_id, push_subscription
               FROM users
               WHERE email = :email
                 AND pattern_hash = :ph
                 AND society_id = :sid""",
            {"email": email, "ph": ph, "sid": society_id},
            fetch_one=True,
        )
        return _build_user(row)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("authenticate_pattern error: %s", exc)
        return None


# ── Password reset ────────────────────────────────────────────────────────────

def request_password_reset(email: str, society_id: int | None = None) -> tuple[bool, str, str | None]:
    """Generate a reset token. Returns (success, message, token)."""
    try:
        q = "SELECT id FROM users WHERE email = :email"
        p: dict = {"email": email}
        if society_id:
            q += " AND society_id = :sid"
            p["sid"] = society_id

        user = db.execute(q, p, fetch_one=True)
        if not user:
            return False, "No account found with that email", None

        token = "".join(secrets.choice(string.digits) for _ in range(6))
        expiry = datetime.now() + timedelta(hours=1)

        db.execute(
            """UPDATE users
               SET reset_token = :token, reset_token_expiry = :expiry
               WHERE id = :uid""",
            {"token": _hash(token), "expiry": expiry, "uid": user["id"]},
        )
        # In production: send token by email/SMS
        return True, f"Reset token sent to {email}", token
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("request_password_reset error: %s", exc)
        return False, "Error generating reset token", None


def reset_password(token: str, new_password: str) -> tuple[bool, str]:
    try:
        th = _hash(token)
        user = db.execute(
            """SELECT id FROM users
               WHERE reset_token = :th
                 AND reset_token_expiry > NOW()""",
            {"th": th},
            fetch_one=True,
        )
        if not user:
            return False, "Invalid or expired reset token"

        db.execute(
            """UPDATE users
               SET password_hash = :ph,
                   reset_token = NULL,
                   reset_token_expiry = NULL
               WHERE id = :uid""",
            {"ph": _hash(new_password), "uid": user["id"]},
        )
        return True, "Password updated successfully"
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("reset_password error: %s", exc)
        return False, "Error resetting password"
