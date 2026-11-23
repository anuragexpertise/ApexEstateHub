# app/services/auth_service.py
"""
Authentication service — EstateHub.

Password storage: werkzeug.security (scrypt/pbkdf2, salted).
All DB queries use named params (:name) via db_manager._to_pyformat().

CRITICAL: seed.py and society_service.py both use generate_password_hash().
           This file must use check_password_hash() to verify — NOT sha256.
"""

import logging
import re
import secrets
from datetime import timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from app.models.user import active_select
from app.security.password_policy import validate_password
from app.security.roles import resolve_role
from app.services import device_service
from app.utils import as_ist, now_ist
from database.db_manager import db

log = logging.getLogger(__name__)

# ── Account lockout (fixed 2026-08) ─────────────────────────────
# `locked_until` was already being CHECKED in authenticate_user() below,
# but nothing anywhere ever SET it or incremented failed_login_attempts —
# both columns exist in the schema but were dead, so login had no actual
# brute-force protection. _record_failed_attempt / _reset_failed_attempts
# make that check mean something.
MAX_FAILED_ATTEMPTS = 5
RESET_TOKEN_HOURS = 1

# One message for every outcome (account found / not found / mail not delivered),
# so the forgot-password form cannot be used to discover which emails exist.
RESET_REQUEST_MESSAGE = "Reset mail sent if account available in database."
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
                {"until": now_ist() + timedelta(minutes=LOCKOUT_MINUTES),
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
    role = resolve_role(row["role"], row.get("society_id"), row.get("is_master_admin"))
    return {
        "user_id":           row["id"],
        "email":             row["email"],
        "role":              role,
        "user_type":         row.get("user_type"),
        "society_id":        row.get("society_id"),
        "linked_id":         row.get("linked_id"),
        "security_id":       row.get("linked_id") if row.get("role") == "security" else None,
        "apartment_id":      row.get("linked_id") if row.get("role") == "apartment" else None,
        "vendor_id":         row.get("linked_id") if row.get("role") == "vendor" else None,
        "token":             secrets.token_hex(32),
    }


def _fetch_user(email: str, society_id: int | None) -> dict | None:
    """Fetch user row by email + society scope. A disabled login (users.active = FALSE) is returned as "no such
    user", so password, PIN and pattern sign-in all refuse it with the same answer as an unknown email."""
    row = _fetch_user_row(email, society_id)
    if row and row.get("active") is False:
        log.warning("Disabled account attempt: %s", email)
        return None
    if row and row.get("role") == "adviser":                      # V5.9: an adviser signs in only while the appointment is in force
        from app.security import adviser_access
        if not adviser_access.in_force(row["id"]):
            log.warning("Adviser sign-in outside an appointment: %s", email)
            return None
    return row


def _fetch_user_row(email: str, society_id: int | None) -> dict | None:
    try:
        if society_id is None:
            return db._execute(
                """SELECT id, email, role, society_id, linked_id, is_master_admin, user_type,
                          password_hash, pin_hash, pattern_hash, locked_until""" + active_select() + """
                    FROM users
                   WHERE lower(email) = lower(:email)
                     AND (society_id IS NULL OR is_master_admin = TRUE)""",
                {"email": (email or "").strip()},
                fetch_one=True,
            )
        return db._execute(
            """SELECT id, email, role, society_id, linked_id, is_master_admin, user_type,
                      password_hash, pin_hash, pattern_hash, locked_until""" + active_select() + """
                FROM users
               WHERE lower(email) = lower(:email)
                 AND society_id = :sid""",
            {"email": (email or "").strip(), "sid": society_id},
            fetch_one=True,
        )
    except Exception as exc:  # noqa: BLE001
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
    if locked_until and as_ist(locked_until) > now_ist():
        log.warning("Locked account attempt: %s until %s", email, locked_until)
        return None

    stored = row.get("password_hash") or ""
    if not stored or not check_password_hash(stored, password):
        log.warning("Bad password: %s", email)
        _record_failed_attempt(row["id"])
        return None
    _reset_failed_attempts(row["id"])
    return _build_auth(row)


# ── PIN / pattern: quick sign-in on a trusted device ───────────
#
# A PIN (4-6 digits) or pattern (>= 4 of 9 dots) is a short secret, so it is only ever checked on a device this
# account already signed in on with its password (see device_service). Compared with the password path:
#   * no usable device token for THIS account  -> refuse straight away. Nothing is counted, so a stranger who types
#     someone's email into the PIN tab can neither guess the PIN nor lock the account out;
#   * wrong PIN/pattern -> counted on that DEVICE (device_service.claim_attempt), not on the account; at
#     MAX_DEVICE_FAILURES the device is untrusted and the password is needed again. The account's own lockout is still
#     honoured (a locked account refuses quick sign-in too) but quick-sign-in mistakes do not feed it.

_PIN_RE = re.compile(r"^\d{4,6}$")
PIN_RULE_MESSAGE = "Use 4-6 digits that are not all the same or a simple run like 1234."


def validate_pin(pin: str) -> str | None:
    """None when acceptable, else the reason."""
    pin = pin or ""
    if not _PIN_RE.match(pin):
        return "PIN must be 4-6 digits."
    if len(set(pin)) == 1 or pin in "0123456789" or pin in "9876543210" or pin[: len(pin) // 2] * 2 == pin:
        return PIN_RULE_MESSAGE
    return None


def normalize_pattern(pattern: str) -> str | None:
    """Canonical "1-4-5-9" form of a drawn pattern, or None if it is not a valid one (4+ distinct dots, each 1-9)."""
    dots = (pattern or "").strip().split("-")
    if len(dots) < 4 or len(set(dots)) != len(dots) or not all(d in "123456789" and len(d) == 1 for d in dots):
        return None
    return "-".join(dots)


def _authenticate_on_device(hash_column: str, secret: str, email: str, society_id: int | None,
                            device_token: str | None) -> dict | None:
    row = _fetch_user(email, society_id)
    if not row:
        return None
    locked_until = row.get("locked_until")
    if locked_until and as_ist(locked_until) > now_ist():
        log.warning("Locked account quick sign-in attempt: %s until %s", email, locked_until)
        return None
    stored = row.get(hash_column) or ""
    if not stored or not secret:
        return None                                       # nothing set (or nothing typed): not an attempt
    token = device_token if device_token is not None else device_service.current_token()
    device = device_service.claim_attempt(token, row["id"])
    if not device:
        log.warning("Quick sign-in refused (device not trusted for this account): %s", email)
        return None
    if not check_password_hash(stored, secret):
        if device["failed_attempts"] >= device_service.MAX_DEVICE_FAILURES:
            device_service.revoke_by_id(device["id"])
            log.warning("Device untrusted after %s wrong quick sign-in tries: user_id=%s", device["failed_attempts"], row["id"])
        return None
    device_service.mark_success(device["id"])
    return _build_auth(row)


def authenticate_pin(email: str, pin: str, society_id: int | None = None,
                       device_token: str | None = None) -> dict | None:
    """Verify email + PIN on a trusted device. ``device_token`` defaults to the request's ``eh_device`` cookie."""
    if not _PIN_RE.match(pin or ""):
        return None
    return _authenticate_on_device("pin_hash", pin, email, society_id, device_token)


def authenticate_pattern(email: str, pattern: str, society_id: int | None = None,
                            device_token: str | None = None) -> dict | None:
    """Verify email + pattern on a trusted device. ``device_token`` defaults to the request's ``eh_device`` cookie."""
    canonical = normalize_pattern(pattern)
    if not canonical:
        return None
    return _authenticate_on_device("pattern_hash", canonical, email, society_id, device_token)


def set_pin(user_id: int, current_password: str, pin: str) -> tuple[bool, str]:
    """Set / replace the account's PIN. Needs the current password (same lockout as login). user_id must come from the
    server session, never from the client."""
    ok, err = verify_password_with_lockout(user_id, current_password)
    if not ok:
        return False, err
    reason = validate_pin(pin)
    if reason:
        return False, reason
    try:
        db._execute("UPDATE users SET pin_hash = :h WHERE id = :uid",
                    {"h": generate_password_hash(pin), "uid": user_id})
        return True, "PIN saved."
    except Exception:
        log.exception("set_pin error for user_id=%s", user_id)
        return False, "Error saving the PIN."


def set_pattern(user_id: int, current_password: str, pattern: str) -> tuple[bool, str]:
    """Set / replace the account's pattern. Same rules as set_pin."""
    ok, err = verify_password_with_lockout(user_id, current_password)
    if not ok:
        return False, err
    canonical = normalize_pattern(pattern)
    if not canonical:
        return False, "Connect at least 4 different dots."
    try:
        db._execute("UPDATE users SET pattern_hash = :h WHERE id = :uid",
                    {"h": generate_password_hash(canonical), "uid": user_id})
        return True, "Pattern saved."
    except Exception:
        log.exception("set_pattern error for user_id=%s", user_id)
        return False, "Error saving the pattern."


def disable_quick_signin(user_id: int, current_password: str) -> tuple[bool, str]:
    """Remove the PIN and pattern and untrust EVERY device of this account."""
    ok, err = verify_password_with_lockout(user_id, current_password)
    if not ok:
        return False, err
    try:
        db._execute("UPDATE users SET pin_hash = NULL, pattern_hash = NULL WHERE id = :uid", {"uid": user_id})
    except Exception:
        log.exception("disable_quick_signin error for user_id=%s", user_id)
        return False, "Error turning off quick sign-in."
    device_service.revoke_all(user_id)
    return True, "PIN and pattern removed; all devices now need your password."


def request_password_reset(email: str,
                                 society_id: int | None = None) -> tuple[bool, str, str | None]:
    """
    Generate a reset token. Returns (ok, message, plain_token). The token is also emailed (or logged when
    SMTP is unavailable); UI callers must never display or return it to the browser.
    `message` is always RESET_REQUEST_MESSAGE, whatever happened.

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
        q = "SELECT id FROM users WHERE lower(email) = lower(:email)"
        p: dict = {"email": (email or "").strip()}
        if society_id:
            q += " AND society_id = :sid"
            p["sid"] = society_id

        user = db._execute(q, p, fetch_one=True)
        if not user:
            # Don't reveal whether the email exists.
            return True, RESET_REQUEST_MESSAGE, None

        plain  = secrets.token_urlsafe(32)
        hashed = hashlib.sha256(plain.encode()).hexdigest()
        expiry = now_ist() + timedelta(hours=RESET_TOKEN_HOURS)

        db._execute(
            """UPDATE users SET reset_token = :tok, reset_token_expires = :exp
               WHERE id = :uid""",
            {"tok": hashed, "exp": expiry, "uid": user["id"]},
        )
        # A1: the token used to be returned to a caller that discarded it, so
        # it reached nobody. Deliver it by email; if SMTP is not configured or
        # the send fails, log it (so an operator can relay it) and say so
        # honestly instead of claiming it was sent.
        from app.services.mailer import send_email
        body = (
            "A password reset was requested for your EstateHub account.\n\n"
            f"Reset token: {plain}\n\n"
            f"It is valid for {RESET_TOKEN_HOURS} hour(s). If you did not request "
            "this, ignore this email."
        )
        if send_email(email, "EstateHub password reset", body):
            return True, RESET_REQUEST_MESSAGE, plain
        log.warning("Password reset token for user_id=%s could not be emailed "
                    "(SMTP not configured or send failed); token omitted from log",
                    user["id"])
        # Same message as every other outcome: do not reveal that the account exists.
        return True, RESET_REQUEST_MESSAGE, plain
    except Exception:
        log.exception("request_password_reset error")
        return False, "Error generating reset token.", None


def reset_password(plain_token: str, new_password: str) -> tuple[bool, str]:
    """Match plain_token (sha256 hex) against stored hashes, then update password."""
    import hashlib
    if not plain_token or not new_password:
        return False, "Please fill in all fields."
    _pw_err = validate_password(new_password)
    if _pw_err:
        return False, _pw_err
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
                   failed_login_attempts = 0, locked_until = NULL,
                   must_change_password = FALSE,
                   pin_hash = NULL, pattern_hash = NULL
               WHERE id = :uid""",
            {"ph": generate_password_hash(new_password), "uid": row["id"]},
        )
        # A reset means the old credentials may be compromised: the PIN/pattern are gone (above) and every device that
        # trusted them is untrusted too, so a token copied before the reset can never be paired with a new PIN.
        device_service.revoke_all(row["id"])
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
    _pw_err = validate_password(new_password)
    if _pw_err:
        return False, _pw_err
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
               SET password_hash = :ph, failed_login_attempts = 0, locked_until = NULL,
                   must_change_password = FALSE
               WHERE id = :uid""",
            {"ph": generate_password_hash(new_password), "uid": user_id},
        )
        return True, "Password updated successfully."
    except Exception:
        log.exception("change_password error for user_id=%s", user_id)
        return False, "Error changing password."


def must_change_password(user_id: int) -> bool:
    """True while the account still has the password someone else chose (A4)."""
    try:
        row = db._execute(
            "SELECT must_change_password FROM users WHERE id = :uid",
            {"uid": user_id}, fetch_one=True,
        )
        return bool((row or {}).get("must_change_password"))
    except Exception:
        log.exception("must_change_password lookup failed for user_id=%s", user_id)
        return False



def verify_password_with_lockout(user_id: int, password: str) -> tuple[bool, str]:
    """Check a logged-in user's password against the SAME lockout counter as login (A11).

    Used by sensitive confirmations (e.g. the Setup Wizard's final submit) so
    guessing the admin password there is throttled exactly like at the login
    screen. Returns (ok, error_message).
    """
    try:
        row = db._execute(
            "SELECT password_hash, locked_until FROM users WHERE id = :uid",
            {"uid": user_id}, fetch_one=True,
        )
    except Exception:
        log.exception("verify_password_with_lockout lookup failed for user_id=%s", user_id)
        return False, "Unable to verify the password. Please try again."
    if not row:
        return False, "Invalid Admin Password."
    locked_until = row.get("locked_until")
    if locked_until and as_ist(locked_until) > now_ist():
        return False, f"Account temporarily locked after too many wrong attempts. Try again in {LOCKOUT_MINUTES} minutes."
    stored = row.get("password_hash") or ""
    if not stored or not check_password_hash(stored, password or ""):
        _record_failed_attempt(user_id)
        return False, "Invalid Admin Password."
    _reset_failed_attempts(user_id)
    return True, ""
