"""
Ledger anchors: signing and checking the head of a society's hash chain from OUTSIDE the database.

Why this exists
---------------
The ledger is a SHA-256 hash chain (transactions.ledger_hash). A chain is tamper-EVIDENT, not tamper-proof:
whoever can rewrite the table can recompute every hash. An *anchor* records the chain's head (sequence, hash,
row count) at a moment in time. Here the application signs it with an HMAC key the database never holds
(LEDGER_ANCHOR_SECRET), and `certificate_text` produces a page the Secretary and Treasurer sign and file with
the society's CA. If the chain is later rebuilt, its hashes no longer match the signed and filed head, and the
database owner cannot forge the signature.

What it does NOT do
-------------------
* It does not stop a rewrite; it makes an undetected one impossible without the signing key AND the filed copy.
* It guarantees nothing about entries made before the first anchor, or between anchors, beyond the chain itself.
* In development, without LEDGER_ANCHOR_SECRET, a random per-process key is used: signatures made in one run will
  not verify in the next. Production refuses to run without a real key (app/security/secret_policy.py).
* Losing the key means anchors can no longer be re-verified (the filed certificates still show the heads).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime

from app.security.secret_policy import resolve_secret

log = logging.getLogger(__name__)

SECRET_ENV = "LEDGER_ANCHOR_SECRET"


def _db(db=None):
    if db is not None:
        return db
    from database.db_manager import db as _default
    return _default


def sign_message(message: str) -> str:
    """HMAC-SHA256 (hex) of the anchor message under the application's key."""
    key = resolve_secret(SECRET_ENV).encode("utf-8")
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()


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
        anchor["signature"] = sign_message(anchor["message"])
        d._execute("SELECT fn_set_anchor_signature(%s, %s)", (anchor["anchor_id"], anchor["signature"]), fetch_one=True)
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
    """Recompute each anchor's HMAC. Returns one dict per problem (empty = every anchor is signed and genuine).
    Run it together with `SELECT * FROM fn_verify_ledger_chain(...)`, which checks the chain against the anchors."""
    d = _db(db)
    rows = d._execute(
        "SELECT id, society_id, ledger_seq, signature, fn_anchor_message(id) AS message FROM ledger_chain_anchors "
        "WHERE (%s IS NULL OR society_id = %s) ORDER BY society_id, ledger_seq",
        (society_id, society_id), fetch_all=True) or []
    problems = []
    for r in rows:
        if not r["signature"]:
            problems.append({"anchor_id": r["id"], "society_id": r["society_id"], "problem": "anchor was never signed"})
        elif not hmac.compare_digest(r["signature"], sign_message(r["message"])):
            problems.append({"anchor_id": r["id"], "society_id": r["society_id"],
                             "problem": "signature does not match: the anchor was altered, or the signing key changed"})
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
        f"Application signature (HMAC-SHA256): {anchor.get('signature') or '(unsigned)'}",
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
