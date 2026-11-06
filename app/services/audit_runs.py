"""Run the auditor's eight checks in one click; store each result dated and signed (Plan v3, task 3.1).

The eight: ledger hash chain, journal balance, cash vouchers, cash-book reconciliation, receipt chains, tamper guards,
vote summary (the latest passed resolution) and the legal-instrument catalogue. The signed anchors check and the tie-out (statements = ledger = source documents) are run as well.
Each stored row carries the society's SIGNING_LEDGER signature over the exact result text, so a result cannot be changed or
swapped afterwards without verification failing.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date

from app.services import auditor_checks as ac
from app.services import signing_service

CHECKS = ("ledger_chain", "integrity", "tieout", "cash_vouchers", "cashbook", "receipt_chains", "tamper_guards", "resolution", "legal", "anchors")
MAX_STORED_ROWS = 50


class AuditRunRefused(RuntimeError):
    """Safe to show to the user."""


def _db(db=None):
    if db is not None:
        return db
    from database.db_manager import db as _d
    return _d


def _message(society_id, key, run_at, h):
    return f"auditcheck|{society_id}|{key}|{run_at}|{h}"


def run_all(society_id: int, user_id: int, day=None, db=None) -> dict:
    d = _db(db)
    u = d._execute("SELECT role FROM users WHERE id=%s AND society_id=%s", (user_id, society_id), fetch_one=True) or {}
    if u.get("role") not in ("auditor", "admin"):
        raise AuditRunRefused("Only an auditor or the administrator can run the checks.")
    res = d._execute("SELECT r.id FROM resolutions r JOIN meetings m ON m.id=r.meeting_id WHERE m.society_id=%s AND r.status='passed' "
                     "ORDER BY m.held_on DESC, r.id DESC LIMIT 1", (society_id,), fetch_one=True)
    batch = str(uuid.uuid4())
    out = []
    for key in CHECKS:
        r = ac.run(key, society_id, day=day or date.today(), resolution_id=(res or {}).get("id"))
        body = {"check": key, "status": r["status"], "note": r.get("note", ""), "total": r.get("total", 0), "columns": r.get("columns", []),
                "rows": r.get("rows", [])[:MAX_STORED_ROWS], "run_on": date.today().isoformat()}
        text = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        # sign first (the signature covers the run time), then insert once: rows are append-only
        run_at = d._execute("SELECT NOW()::timestamp AS t", fetch_one=True)["t"]
        sig = signing_service.sign(society_id, "SIGNING_LEDGER", _message(society_id, key, run_at.isoformat(), h), db=d)
        row = d._execute("INSERT INTO audit_check_runs (society_id, batch_id, check_key, run_at, run_by, status, result_text, item_hash, signature, key_version, key_id, algorithm) "
                         "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                         (society_id, batch, key, run_at, user_id, r["status"], text, h, sig["signature"], sig["key_version"], sig["key_id"], sig["algorithm"]), fetch_one=True)
        out.append({"id": row["id"], "check": key, "status": r["status"]})
    return {"batch_id": batch, "results": out}


def verify_run(run_id: int, society_id: int | None = None, db=None) -> dict:
    d = _db(db)
    r = d._execute("SELECT * FROM audit_check_runs WHERE id=%s", (run_id,), fetch_one=True)
    if not r or (society_id is not None and r["society_id"] != society_id):
        return {"status": "unknown"}
    if hashlib.sha256(r["result_text"].encode("utf-8")).hexdigest() != r["item_hash"]:
        return {"status": "tampered"}
    res = signing_service.verify(r["society_id"], "SIGNING_LEDGER", _message(r["society_id"], r["check_key"], r["run_at"].isoformat(), r["item_hash"]),
                                 r["signature"], r["key_version"], r["run_at"], db=d)
    return {"status": "valid" if res["valid"] else ("untrusted" if res["status"] == "untrusted" else "tampered"), "check": r["check_key"], "run_at": r["run_at"]}


def latest(society_id: int, limit: int = 30, db=None) -> list[dict]:
    return _db(db)._execute("SELECT id, batch_id, check_key, run_at, status FROM audit_check_runs WHERE society_id=%s ORDER BY id DESC LIMIT %s",
                            (society_id, limit), fetch_all=True) or []
