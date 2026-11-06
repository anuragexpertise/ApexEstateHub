"""
Changing SECRET_VAULT_KEY (Gold-Standard Plan v3, tasks 1.2 and 4.5). Run from the operator's own machine via
scripts/rotate_vault_key.py, never from the web host.

* SECRET_MASTER_KEY authorises every change. It is checked against a salted scrypt verifier stored in
  platform_vault_meta; a wrong master key is refused before anything is touched.
* Re-wrapping all keys happens in ONE transaction on a separate database login (a member of
  estatehub_keyrotator), and a sample is unwrapped under the new key and used to verify before commit.
* A recovery file holds the vault key sealed under the master key. Keep it with the sealed backups.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

from cryptography.fernet import Fernet, InvalidToken

from app.services import secret_vault as vault

_LABEL = b"ApexEstateHub/v1/MASTER-VERIFIER"
_SEAL_LABEL = b"ApexEstateHub/v1/VAULT-SEAL"


class MasterKeyError(RuntimeError):
    pass


def _derive(master: str, salt: bytes) -> bytes:
    return hashlib.scrypt(master.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)


def _verifier(master: str, salt: bytes) -> str:
    return hmac.new(_derive(master, salt), _LABEL, hashlib.sha256).hexdigest()


def new_vault_key() -> str:
    return Fernet.generate_key().decode()


def init_meta(conn, master_key: str, vault_key: str, commit: bool = True) -> None:
    """First-time set-up: record the master verifier and the vault fingerprint. Refuses to overwrite."""
    if len(master_key) < 24:
        raise MasterKeyError("SECRET_MASTER_KEY must be at least 24 characters.")
    salt = os.urandom(16)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM platform_vault_meta WHERE id = 1")
        if cur.fetchone():
            raise MasterKeyError("The vault is already initialised.")
        cur.execute("INSERT INTO platform_vault_meta (id, master_salt, master_verifier, vault_fingerprint) "
                    "VALUES (1, %s, %s, %s)", (salt.hex(), _verifier(master_key, salt), vault.fingerprint(vault_key)))
    if commit:
        conn.commit()


def check_master(conn, master_key: str) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT master_salt, master_verifier FROM platform_vault_meta WHERE id = 1")
        row = cur.fetchone()
    if not row:
        raise MasterKeyError("The vault is not initialised (platform_vault_meta is empty).")
    if not hmac.compare_digest(_verifier(master_key or "", bytes.fromhex(row[0])), row[1]):
        raise MasterKeyError("SECRET_MASTER_KEY is wrong: the vault key will not be changed.")


def seal_vault_key(vault_key: str, master_key: str) -> bytes:
    """The recovery file's contents: the vault key, openable only with the master key."""
    salt = os.urandom(16)
    f = Fernet(base64.urlsafe_b64encode(_derive(master_key, salt)))
    return b"ESTATEHUB-SEAL1:" + salt.hex().encode() + b":" + f.encrypt(_SEAL_LABEL + b"|" + vault_key.encode())


def unseal_vault_key(sealed: bytes, master_key: str) -> str:
    try:
        _, salt_hex, token = sealed.strip().split(b":", 2)
        f = Fernet(base64.urlsafe_b64encode(_derive(master_key, bytes.fromhex(salt_hex.decode()))))
        label, _, key = f.decrypt(token).partition(b"|")
    except (ValueError, InvalidToken) as e:
        raise MasterKeyError("The recovery file cannot be opened with this master key.") from e
    if label != _SEAL_LABEL:
        raise MasterKeyError("The recovery file is not a vault-key seal.")
    return key.decode()


def rotate_vault_key(conn, old_vault_key: str, master_key: str, new_vault_key: str | None = None,
                     commit: bool = True) -> dict:
    """Re-wrap every signing key under a new vault key. `conn` must be the rotation tool's login.
    Returns {'new_vault_key', 'sealed', 'rewrapped'}. Nothing is committed unless a sample verifies."""
    check_master(conn, master_key)
    if vault.fingerprint(old_vault_key) != _stored_fingerprint(conn):
        raise MasterKeyError("The old vault key does not match the one this database was initialised with.")
    new_key = new_vault_key or new_vault_key_value()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, society_id, purpose, version, wrapped_key FROM society_signing_keys ORDER BY id FOR UPDATE")
            rows = cur.fetchall()
            for rid, _sid, _p, _v, wrapped in rows:
                raw = vault.unwrap(wrapped, old_vault_key)
                cur.execute("UPDATE society_signing_keys SET wrapped_key = %s WHERE id = %s",
                            (vault.wrap(raw, new_key), rid))
            if rows:                                              # a sample must unwrap under the NEW key
                cur.execute("SELECT wrapped_key FROM society_signing_keys ORDER BY id LIMIT 1")
                vault.unwrap(cur.fetchone()[0], new_key)
            cur.execute("UPDATE platform_vault_meta SET vault_fingerprint = %s, vault_version = vault_version + 1, "
                        "updated_at = NOW() WHERE id = 1", (vault.fingerprint(new_key),))
        if commit:
            conn.commit()
    except Exception:
        if commit:
            conn.rollback()
        raise
    return {"new_vault_key": new_key, "sealed": seal_vault_key(new_key, master_key), "rewrapped": len(rows)}


def new_vault_key_value() -> str:
    return new_vault_key()


def _stored_fingerprint(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT vault_fingerprint FROM platform_vault_meta WHERE id = 1")
        return cur.fetchone()[0]
