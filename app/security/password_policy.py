# app/security/password_policy.py
"""
One place for every credential rule (audit findings A4 and A5).

* Login passwords: one minimum everywhere (admin creation, bulk enrol,
  single enrol, reset, self-service change).
* SIGNING_SECRET: one validator used by the live field feedback, the
  Next-button gate and the final Submit, so a secret can no longer pass one
  check and fail another.

No heavy imports, so it is safe to import from anywhere.
"""
from __future__ import annotations

import re

MIN_PASSWORD_LENGTH = 8
MIN_SIGNING_SECRET_LENGTH = 8

PASSWORD_RULE_TEXT = f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
SIGNING_SECRET_RULE_TEXT = (
    f"SIGNING_SECRET must be at least {MIN_SIGNING_SECRET_LENGTH} characters with "
    "an uppercase letter, a lowercase letter, a digit and a special character."
)


def validate_password(pwd: str | None) -> str | None:
    """Return an error message, or None if the login password is acceptable."""
    if not pwd or len(pwd) < MIN_PASSWORD_LENGTH:
        return PASSWORD_RULE_TEXT
    return None


def validate_signing_secret(secret: str | None) -> str | None:
    """Return an error message, or None if the SIGNING_SECRET is acceptable."""
    if (
        not secret
        or len(secret) < MIN_SIGNING_SECRET_LENGTH
        or not re.search(r"[A-Z]", secret)
        or not re.search(r"[a-z]", secret)
        or not re.search(r"\d", secret)
        or not re.search(r"[^A-Za-z0-9]", secret)
    ):
        return SIGNING_SECRET_RULE_TEXT
    return None
