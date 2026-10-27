"""
Ledger anchors: signing and checking the head of a society's hash chain from OUTSIDE the database.

Why this exists
---------------
The ledger is a SHA-256 hash chain (transactions.ledger_hash). A chain is tamper-EVIDENT, not tamper-proof:
whoever can rewrite the table can recompute every hash. An *anchor* records the chain's head (sequence, hash,
row count) at a moment in time. Here the application signs it with the society's SIGNING_LEDGER key (app/services/signing_service.py), wrapped
under SECRET_VAULT_KEY, which the database never holds, and `certificate_text` produces a page the Secretary and Treasurer sign and file with
the society's CA. If the chain is later rebuilt, its hashes no longer match the signed and filed head, and the
database owner cannot forge the signature.

What it does NOT do
-------------------
* It does not stop a rewrite; it makes an undetected one impossible without the signing key AND the filed copy.
* It guarantees nothing about entries made before the first anchor, or between anchors, beyond the chain itself.
* Each anchor records the key purpose, key VERSION, algorithm and time, so an anchor still verifies after the
  society's ledger key is rotated (old versions are retired, never deleted).
* Anchors signed before the vault existed carry `legacy_signature`. They verify only while the retired platform
  key LEDGER_ANCHOR_SECRET is still supplied; otherwise they are reported as legacy, not as forged.
* Losing SECRET_VAULT_KEY (and its sealed recovery file) means anchors can no longer be re-verified; the filed
  certificates still show the heads.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime

from app.services import signing_service

log = logging.getLogger(__name__)

LEGACY_SECRET_ENV = "LEDGER_ANCHOR_SECRET"      # retired: used only to verify anchors signed before the vault
PURPOSE = "SIGNING_LEDGER"


def _db(db=None):
    if db is not None:
        return db
    from database.db_manager import db as _default
    return _default


def _legacy_signature(message: str) -> str | None:
    key = (os.getenv(LEGACY_SECRET_ENV) or "").strip()
    return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest() if key else None


def anchor_society(society_id: int, user_id: int | None = None, method: str = "manual", db=None) -> dict:
    """Anchor (and sign) one society's chain head. Raises if the chain does not verify or has no entries.
    Anchoring an unchanged head returns the existing anchor, signing it if it is not yet signed."""
    d = _db(db)
    row = d._execute("SELECT * FROM fn_anchor_ledger_chain(%s, %s, %s)", (society_id, user_id, method), fetch_one=True)
    if not row:
        raise RuntimeError("The ledger could not be anchored.")
    anchor = dict(row)
    existing = d._execute("SELECT signature FROM ledger_chain_anchors WHERE id = %s",
                          (anchor["anchor_id"],), fetch_one=True)
    if existing and existing.get("signature"):
        anchor["signature"] = existing["signature"]
    else:
        rec = signing_service.sign(society_id, PURPOSE, anchor["message"], db=d)
        anchor["signature"] = rec["signature"]
        anchor["sig_key_version"] = rec["key_version"]
        d._execute("SELECT fn_set_anchor_signature(%s, %s, %s, %s, %s)",
                   (anchor["anchor_id"], rec["signature"], PURPOSE, rec["key_version"], rec["algorithm"]), fetch_one=True)
    return anchor


def anchor_all(user_id: int | None = None, method: str = "scheduled", db=None) -> list[dict]:
    """Anchor every society that has ledger entries. One society's failure does not stop the others: each result
    is {'society_id', 'ok', 'anchor' | 'error'}."""
    d = _db(db)
    societies = d._execute(
        "SELECT DISTINCT society_id FROM transactions WHERE ledger_seq IS NOT NULL ORDER BY 1", fetch_all=True) or []
    out = []
    for s in societies:
        sid = int(s["society_id"])
        try:
            out.append({"society_id": sid, "ok": True, "anchor": anchor_society(sid, user_id, method, d)})
        except Exception as exc:                                    # noqa: BLE001 - reported, not hidden
            log.error("anchoring society %s failed: %s", sid, exc)
            out.append({"society_id": sid, "ok": False, "error": str(exc).strip().splitlines()[0]})
    return out


def verify_signatures(society_id: int | None = None, db=None) -> list[dict]:
    """Recompute each anchor's HMAC under the key VERSION recorded on it. Returns one dict per problem (empty = every
    anchor is signed and genuine). Run it with `SELECT * FROM fn_verify_ledger_chain(...)`, which checks the chain
    against the anchors."""
    d = _db(db)
    rows = d._execute(
        "SELECT id, society_id, ledger_seq, signature, sig_purpose, sig_key_version, signed_at, legacy_signature, "
        "fn_anchor_message(id) AS message FROM ledger_chain_anchors "
        "WHERE (%s IS NULL OR society_id = %s) ORDER BY society_id, ledger_seq",
        (society_id, society_id), fetch_all=True) or []
    problems = []
    for r in rows:
        base = {"anchor_id": r["id"], "society_id": r["society_id"]}
        if not r["signature"]:
            problems.append({**base, "problem": "anchor was never signed"})
        elif r["legacy_signature"]:
            expected = _legacy_signature(r["message"])
            if expected is None:
                problems.append({**base, "problem": "legacy anchor (signed with the retired platform key): "
                                                    "set LEDGER_ANCHOR_SECRET to verify it"})
            elif not hmac.compare_digest(r["signature"], expected):
                problems.append({**base, "problem": "legacy signature does not match: the anchor was altered or the key differs"})
        else:
            res = signing_service.verify(r["society_id"], PURPOSE, r["message"], r["signature"],
                                         r["sig_key_version"], r["signed_at"], db=d)
            if res["status"] == "untrusted":
                problems.append({**base, "problem": "signed with a key later revoked as compromised: untrusted"})
            elif not res["valid"]:
                problems.append({**base, "problem": "signature does not match: the anchor was altered "
                                                    f"({res['status']}, key version {r['sig_key_version']})"})
    return problems


def certificate_text(anchor: dict, society_name: str = "") -> str:
    """A page to print, sign (Secretary and Treasurer) and file with the society's CA."""
    at = anchor.get("anchored_at")
    at = at.strftime("%d %b %Y %H:%M") if isinstance(at, datetime) else str(at)
    return "\n".join([
        "LEDGER ANCHOR CERTIFICATE",
        "=========================",
        f"Society            : {society_name or anchor.get('society_id', '')}",
        f"Anchored at        : {at}",
        f"Entries in ledger  : {anchor.get('row_count')}   (last sequence number {anchor.get('ledger_seq')})",
        f"Chain head (SHA-256): {anchor.get('head_hash')}",
        f"Society ledger-key signature (HMAC-SHA256): {anchor.get('signature') or '(unsigned)'}",
        "",
        "What this certifies: at the time above, the society's ledger had exactly the entries counted and its",
        "hash chain ended at the head shown. If the ledger is later rebuilt or altered, the chain head at this",
        "sequence number will no longer equal the value filed here.",
        "",
        "To check later, run:   SELECT * FROM fn_verify_ledger_chain(<society id>);   (empty result = intact)",
        "and compare the head hash at the sequence number above with this certificate.",
        "",
        "Secretary: ______________________   Treasurer: ______________________   Date: ______________",
        "Received by the society's CA (name / membership no. / date): _______________________________________",
    ])
