# app/security/secret_policy.py
"""
One policy for every signing secret (Flask session key, JWT key).

Why this exists
---------------
`Config.SECRET_KEY` signs the Flask-Login session cookie. Every server-side
identity check in the app (get_current_user_role(), @require_session, ...)
trusts that cookie, so a SECRET_KEY that is published in the source tree lets
anyone forge a session for any user id and walk straight past them. The JWT key
had the same problem in a second place (a different committed default).

Rules
-----
* In production a missing, known-default, or too-short secret is a hard
  startup error (fail closed) — the process must not boot with a guessable key.
* Outside production a missing secret is replaced with a random per-process
  key (and a warning), never with a constant that is the same on every
  machine. Consequence: dev sessions/tokens do not survive a restart; set the
  env var if you want them to.

Deliberately free of heavy imports (no db, no flask) so app/config.py and
app/auth/jwt_handler.py can both import it without cycles.
"""
from __future__ import annotations

import logging
import os
import secrets

log = logging.getLogger(__name__)

# Every default string that has ever been committed to this repo. Presence of
# any of these as the configured value is treated the same as "unset".
KNOWN_INSECURE_SECRETS = frozenset({
    "dev-secret-key-CHANGE-IN-PRODUCTION",
    "Iamagoodboy9453",
    "your-jwt-secret-key-change-this",
    "change-me-in-production",
    "changeme",
    "secret",
})

MIN_PRODUCTION_SECRET_LENGTH = 32

# Per-process cache so every module asking for the same secret name gets the
# same ephemeral dev key (otherwise SECRET_KEY could differ between modules).
_EPHEMERAL: dict[str, str] = {}


def is_production() -> bool:
    """True on Render/Heroku-style platforms or when an env flag says production."""
    if os.getenv("RENDER") or os.getenv("DYNO"):
        return True
    return any(
        os.getenv(k, "").strip().lower() == "production"
        for k in ("APP_ENV", "FLASK_ENV", "ENV", "FLASK_CONFIG")
    )


def _problem_with(value: str | None) -> str | None:
    """Return why `value` is unacceptable in production, or None if it's fine."""
    if not value:
        return "is not set"
    if value in KNOWN_INSECURE_SECRETS:
        return "is a known default that is published in the source tree"
    if len(value) < MIN_PRODUCTION_SECRET_LENGTH:
        return f"is shorter than {MIN_PRODUCTION_SECRET_LENGTH} characters"
    return None


def resolve_secret(env_name: str) -> str:
    """
    Resolve the secret named by `env_name` according to the module policy.

    Raises RuntimeError in production if the value is unset/known/too short.
    """
    value = (os.getenv(env_name) or "").strip()
    problem = _problem_with(value)

    if problem is None:
        return value

    if is_production():
        raise RuntimeError(
            f"{env_name} {problem}. Refusing to start in a production "
            f"environment: set {env_name} to a long random value "
            f"(e.g. `python -c \"import secrets; print(secrets.token_urlsafe(48))\"`)."
        )

    if env_name not in _EPHEMERAL:
        _EPHEMERAL[env_name] = secrets.token_urlsafe(48)
        log.warning(
            "%s %s — using a random per-process key for this run. Sessions/tokens "
            "will not survive a restart. Set %s for stable local development; "
            "never deploy without it.",
            env_name, problem, env_name,
        )
    return _EPHEMERAL[env_name]
