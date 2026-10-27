"""
The single signing service (Gold-Standard Plan v3, task 1.2).

Every society has four independent HMAC-SHA256 keys, one per purpose. Keys are made here from os.urandom, stored
wrapped under SECRET_VAULT_KEY (app/services/secret_vault.py) and unwrapped ONLY inside this module. They never
appear in logs, exports, error text or return values, apart from `raw_key_for_qr`, which exists because the QR
tag code takes its key as a string.

Rules enforced here:
* Purpose separation: every signed message starts with a label such as
  "ApexEstateHub/v1/SIGNING_NOC/society:123|", so a QR tag can never pass as a NOC signature.
* Every signature says how it was made: purpose, key version, key id, algorithm, time, hash of the signed text.
* Rotation retires the old version but keeps it, so old records still verify.
* A revoked key makes every signature at or after its compromise date "untrusted".
* Creation, rotation and revocation are written to audit_events.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime

from app.services import secret_vault as vault

log = logging.getLogger(__name__)

PURPOSES = ("SIGNING_QR", "SIGNING_NOC", "SIGNING_AGREEMENT", "SIGNING_LEDGER")
ALGORITHM = "HMAC-SHA256"
LABEL_VERSION = "v1"


class SigningError(RuntimeError):
    pass


def _db(db=None):
    if db is not None:
        return db
    from database.db_manager import db as _default
    return _default


def _check_purpose(purpose: str) -> None:
    if purpose not in PURPOSES:
        raise SigningError(f"Unknown signing purpose {purpose!r}.")


def label(purpose: str, society_id: int) -> bytes:
    _check_purpose(purpose)
    return f"ApexEstateHub/{LABEL_VERSION}/{purpose}/society:{int(society_id)}|".encode()


def _audit(d, society_id, actor_id, action, purpose, version, extra=None):
    d._execute(
        "INSERT INTO audit_events (society_id, actor_id, action, resource_type, resource_id, after_value, source) "
        "VALUES (%s, %s, %s, 'society_signing_key', %s, %s::jsonb, 'app')",
        (society_id, actor_id, action, f"{purpose}:v{version}", json.dumps({"purpose": purpose, "version": version, **(extra or {})})))


def _insert_key(d, society_id, purpose, version, actor_id):
    raw = os.urandom(32)
    d._execute(
        "INSERT INTO society_signing_keys (society_id, purpose, version, key_id, wrapped_key, algorithm, created_by) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (society_id, purpose, version, secrets.token_hex(12), vault.wrap(raw), ALGORITHM, actor_id))
    return raw


def ensure_society_keys(society_id: int, actor_id: int | None = None, db=None) -> list[str]:
    """Create any of the four keys the society lacks. Idempotent. Returns the purposes created.
    Raises SecretVaultError if the vault is not configured, so callers can fail BEFORE marking setup complete."""
    d = _db(db)
    have = {r["purpose"] for r in (d._execute(
        "SELECT purpose FROM society_signing_keys WHERE society_id = %s AND status = 'active'", (society_id,), fetch_all=True) or [])}
    made = []
    for purpose in PURPOSES:
        if purpose in have:
            continue
        top = d._execute("SELECT COALESCE(MAX(version), 0) AS v FROM society_signing_keys WHERE society_id = %s AND purpose = %s",
                         (society_id, purpose), fetch_one=True)["v"]
        _insert_key(d, society_id, purpose, top + 1, actor_id)
        _audit(d, society_id, actor_id, "SIGNING_KEY_CREATED", purpose, top + 1)
        made.append(purpose)
    return made


def _key_row(d, society_id, purpose, version=None):
    if version is None:
        return d._execute("SELECT * FROM society_signing_keys WHERE society_id = %s AND purpose = %s AND status = 'active'",
                          (society_id, purpose), fetch_one=True)
    return d._execute("SELECT * FROM society_signing_keys WHERE society_id = %s AND purpose = %s AND version = %s",
                      (society_id, purpose, version), fetch_one=True)


def _mac(raw: bytes, purpose: str, society_id: int, message: bytes) -> str:
    return hmac.new(raw, label(purpose, society_id) + message, hashlib.sha256).hexdigest()


def _as_bytes(message) -> bytes:
    return message if isinstance(message, bytes) else str(message).encode("utf-8")


def sign(society_id: int, purpose: str, message, db=None) -> dict:
    """Sign with the ACTIVE key. Returns a record to store beside the signed item."""
    _check_purpose(purpose)
    d = _db(db)
    row = _key_row(d, society_id, purpose)
    if not row:
        raise SigningError(f"Society {society_id} has no active {purpose} key.")
    msg = _as_bytes(message)
    raw = vault.unwrap(row["wrapped_key"])
    return {
        "purpose": purpose, "key_version": row["version"], "key_id": row["key_id"], "algorithm": row["algorithm"],
        "signature": _mac(raw, purpose, society_id, msg), "signed_at": datetime.now().isoformat(timespec="seconds"),
        "text_hash": hashlib.sha256(label(purpose, society_id) + msg).hexdigest(),
    }


def verify(society_id: int, purpose: str, message, signature: str, key_version: int,
           signed_at: datetime | str | None = None, db=None) -> dict:
    """Returns {'valid': bool, 'status': 'valid'|'invalid'|'untrusted'|'unknown_key', 'key_status': ...}.
    A signature made under a retired key still verifies. Under a revoked key it is 'untrusted' when made at or after
    the compromise date (or when either date is unknown)."""
    _check_purpose(purpose)
    d = _db(db)
    row = _key_row(d, society_id, purpose, key_version)
    if not row:
        return {"valid": False, "status": "unknown_key", "key_status": None}
    raw = vault.unwrap(row["wrapped_key"])
    ok = hmac.compare_digest(signature or "", _mac(raw, purpose, society_id, _as_bytes(message)))
    if not ok:
        return {"valid": False, "status": "invalid", "key_status": row["status"]}
    if row["status"] == "revoked":
        when = datetime.fromisoformat(signed_at) if isinstance(signed_at, str) else signed_at
        cd = row.get("compromise_date")
        if when is None or cd is None or when >= cd:
            return {"valid": False, "status": "untrusted", "key_status": "revoked"}
    return {"valid": True, "status": "valid", "key_status": row["status"]}


def _holds_office(d, society_id, user_id, office_code) -> bool:
    return bool(d._execute(
        "SELECT 1 FROM committee_offices WHERE society_id = %s AND user_id = %s AND office_code = %s AND status = 'active' "
        "AND term_start <= CURRENT_DATE AND (term_end IS NULL OR term_end >= CURRENT_DATE)",
        (society_id, user_id, office_code), fetch_one=True))


def rotate_key(society_id: int, purpose: str, actor_id: int, approver_user_ids=(), db=None) -> dict:
    """New active version; the old one is retired, never deleted. SIGNING_LEDGER also needs the active Secretary
    AND Treasurer among the approvers (two different people). The step-up password is checked by the caller."""
    _check_purpose(purpose)
    d = _db(db)
    if purpose == "SIGNING_LEDGER":
        ids = set(approver_user_ids or ())
        sec = any(_holds_office(d, society_id, u, "secretary") for u in ids)
        tre = any(_holds_office(d, society_id, u, "treasurer") for u in ids)
        if not (sec and tre):
            raise SigningError("Changing SIGNING_LEDGER needs the Secretary and the Treasurer, two different people.")
        sec_ids = {u for u in ids if _holds_office(d, society_id, u, "secretary")}
        tre_ids = {u for u in ids if _holds_office(d, society_id, u, "treasurer")}
        if not any(a != b for a in sec_ids for b in tre_ids):
            raise SigningError("The Secretary and the Treasurer must be two different people.")
    cur = _key_row(d, society_id, purpose)
    if not cur:
        raise SigningError(f"Society {society_id} has no active {purpose} key to rotate.")
    d._execute("UPDATE society_signing_keys SET status = 'retired', retired_at = NOW() WHERE id = %s", (cur["id"],))
    ver = cur["version"] + 1
    _insert_key(d, society_id, purpose, ver, actor_id)
    _audit(d, society_id, actor_id, "SIGNING_KEY_ROTATED", purpose, ver, {"previous": cur["version"]})
    return {"purpose": purpose, "version": ver, "previous": cur["version"]}


def revoke_key(society_id: int, purpose: str, version: int, actor_id: int, compromise_date: datetime,
               reason: str, db=None) -> None:
    """Mark a key revoked. Everything it signed at or after `compromise_date` becomes untrusted. The caller must
    then rotate (or create) a fresh active key; an active key is retired first so signing cannot continue on it."""
    _check_purpose(purpose)
    d = _db(db)
    if len((reason or "").strip()) < 10:
        raise SigningError("Say why the key is revoked (at least 10 characters).")
    row = _key_row(d, society_id, purpose, version)
    if not row:
        raise SigningError("No such key version.")
    d._execute("UPDATE society_signing_keys SET status = 'revoked', revoked_at = NOW(), compromise_date = %s, "
               "revoke_reason = %s, retired_at = COALESCE(retired_at, NOW()) WHERE id = %s",
               (compromise_date, reason, row["id"]))
    _audit(d, society_id, actor_id, "SIGNING_KEY_REVOKED", purpose, version,
           {"compromise_date": str(compromise_date), "reason": reason})


def raw_key_for_qr(society_id: int, db=None) -> str | None:
    """The active SIGNING_QR key as a hex string for the QR tag code, or None if the society has none yet."""
    row = _key_row(_db(db), society_id, "SIGNING_QR")
    return vault.unwrap(row["wrapped_key"]).hex() if row else None


# ── step-up password (signs nothing; confirms sensitive actions) ─────────────────────────────────────────────────
def set_stepup_password_hash(plain: str) -> str:
    from werkzeug.security import generate_password_hash
    return generate_password_hash(plain)


def verify_stepup_password(society_id: int, typed: str, db=None) -> bool:
    from werkzeug.security import check_password_hash
    if not society_id or not typed:
        return False
    row = _db(db)._execute("SELECT stepup_password_hash FROM societies WHERE id = %s", (society_id,), fetch_one=True)
    h = (row or {}).get("stepup_password_hash")
    return bool(h) and check_password_hash(h, typed)
