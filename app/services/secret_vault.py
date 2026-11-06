# app/services/secret_vault.py
"""
The vault: wraps each society's signing keys at rest under SECRET_VAULT_KEY.

SECRET_VAULT_KEY is one Fernet key, or several separated by commas. The FIRST key wraps new material; every key
listed can unwrap, which lets the host accept the old and new key during a rotation. It lives in the host
environment (.env) and never in the database, the repository, logs, chat or e-mail. A database dump alone
therefore yields only wrapped keys.

SECRET_MASTER_KEY is held by the platform operator, outside .env and the database. This module never reads it;
only scripts/rotate_vault_key.py (app/security/vault_rotation.py) does, and only to authorise a vault-key change.

Generate a vault key:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Production refuses to start without a valid vault key (`assert_vault_ready`).
"""
from __future__ import annotations

import hashlib
import logging
import os

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

log = logging.getLogger(__name__)

ENV_NAME = "SECRET_VAULT_KEY"


class SecretVaultError(RuntimeError):
    pass


def _raw_keys(value: str | None = None) -> list[str]:
    value = os.getenv(ENV_NAME, "") if value is None else value
    return [k.strip() for k in value.split(",") if k.strip()]


def _multi(value: str | None = None) -> MultiFernet:
    keys = _raw_keys(value)
    if not keys:
        raise SecretVaultError(f"{ENV_NAME} is not configured.")
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except (ValueError, TypeError) as e:
        raise SecretVaultError(f"{ENV_NAME} is not a valid Fernet key: {e}") from e


def fingerprint(vault_key: str | None = None) -> str:
    """SHA-256 of the FIRST (current) vault key. The key has 256 bits of entropy, so this reveals nothing usable."""
    keys = _raw_keys(vault_key)
    if not keys:
        raise SecretVaultError(f"{ENV_NAME} is not configured.")
    return hashlib.sha256(keys[0].encode()).hexdigest()


def wrap(raw: bytes, vault_key: str | None = None) -> str:
    return _multi(vault_key).encrypt(raw).decode("ascii")


def unwrap(token: str, vault_key: str | None = None) -> bytes:
    try:
        return _multi(vault_key).decrypt(token.encode("ascii"))
    except InvalidToken as e:
        raise SecretVaultError("A wrapped key could not be unwrapped: wrong SECRET_VAULT_KEY or damaged data.") from e


def assert_vault_ready(db=None, *, production: bool | None = None) -> None:
    """Fail closed. In production a missing or invalid vault key, or one that does not match the key the database
    was initialised with (platform_vault_meta), stops start-up. Outside production, problems are logged only."""
    from app.security.secret_policy import is_production
    production = is_production() if production is None else production
    try:
        _multi()
        problem = None
        if db is not None:
            row = db._execute("SELECT vault_fingerprint FROM platform_vault_meta WHERE id = 1", fetch_one=True)
            known = {hashlib.sha256(k.encode()).hexdigest() for k in _raw_keys()}
            if row and row["vault_fingerprint"] not in known:
                problem = "SECRET_VAULT_KEY does not match the key this database was initialised with."
    except SecretVaultError as e:
        problem = str(e)
    if problem:
        if production:
            raise RuntimeError(f"{problem} Refusing to start in production.")
        log.warning("%s (continuing: not production)", problem)
