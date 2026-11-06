"""Per-financial-year compliance certificate (Plan v3, task 2.6).

Generated from the data: each auditor check with pass / fail / exception and its date, plus every provisional item
(unverified statutes, provisional rule choices, items still waiting for ratification). The canonical text is signed
with the society's SIGNING_LEDGER key; the public page /verify/certificate/<id> shows only minimal fields. A newer
certificate for the same year supersedes the older one. This is a statement of what the system checked, not an audit
opinion: a CA still signs the paper copy.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime

from app.services import auditor_checks as ac
from app.services import signing_service

CHECK_LABELS = {
    "ledger_chain": "Ledger hash chain", "anchors": "Signed ledger anchors", "integrity": "Ledger integrity (balances)",
    "cash_vouchers": "Cash vouchers", "receipt_chains": "Receipt chains", "tamper_guards": "Tamper guards", "legal": "Legal instruments",
}


class CertificateRefused(RuntimeError):
    """Safe to show to the user."""


def _db(db=None):
    if db is not None:
        return db
    from database.db_manager import db as _d
    return _d


def fy_label(today: date | None = None) -> str:
    t = today or date.today()
    y = t.year if t.month >= 4 else t.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def _valid_fy(fy: str) -> bool:
    try:
        a, b = fy.split("-")
        return len(a) == 4 and len(b) == 2 and (int(a) + 1) % 100 == int(b)
    except ValueError:
        return False


def _status(raw: str) -> str:
    return {"pass": "pass", "finding": "fail", "error": "fail"}.get(raw, "exception")


def collect(society_id: int, db=None) -> dict:
    d = _db(db)
    checks = []
    for key in ac.SIMPLE_CHECKS:
        try:
            r = ac.run(key, society_id)
            st, note = _status(r.get("status")), (r.get("note") or "")[:300]
        except Exception as exc:                                          # noqa: BLE001  a check that cannot run is an exception, never a pass
            st, note = "fail", f"Check could not run: {str(exc)[:200]}"
        checks.append({"key": key, "label": CHECK_LABELS.get(key, key), "result": st, "note": note, "on": date.today().isoformat()})
    provisional = []
    for r in d._execute("SELECT title, notification_no FROM legal_instrument_catalog WHERE verification <> 'verified' ORDER BY id", fetch_all=True) or []:
        provisional.append({"kind": "statute_unverified", "item": r["title"]})
    for r in d._execute("SELECT rule_key FROM rule_parameter_defs WHERE society_id=%s AND approved_status='provisional' ORDER BY id", (society_id,), fetch_all=True) or []:
        provisional.append({"kind": "rule_provisional", "item": r["rule_key"]})
    for r in d._execute("SELECT id, kind, ratify_by FROM ratification_items WHERE society_id=%s AND status='pending' ORDER BY id", (society_id,), fetch_all=True) or []:
        provisional.append({"kind": "awaiting_ratification", "item": f"#{r['id']} {r['kind']} by {r['ratify_by']}"})
    if any(c["result"] == "fail" for c in checks):
        overall = "fail"
    elif provisional or any(c["result"] == "exception" for c in checks):
        overall = "exceptions"
    else:
        overall = "pass"
    return {"checks": checks, "provisional": provisional, "overall": overall}


def _canonical(society_id: int, fy: str, generated_on: str, body: dict) -> str:
    return json.dumps({"v": 1, "society_id": society_id, "fy": fy, "generated_on": generated_on, **body},
                      sort_keys=True, separators=(",", ":"), default=str)


def generate(society_id: int, user_id: int, fy: str | None = None, db=None) -> dict:
    d = _db(db)
    fy = fy or fy_label()
    if not _valid_fy(fy):
        raise CertificateRefused("The financial year must look like 2026-27.")
    from app.services import document_signing as ds
    u = d._execute("SELECT role FROM users WHERE id=%s AND society_id=%s", (user_id, society_id), fetch_one=True) or {}
    if u.get("role") not in ("admin", "auditor") and not ds.serving_offices(society_id, user_id, db=d):
        raise CertificateRefused("Only the administrator, an auditor or a serving office-bearer can generate the certificate.")
    body = collect(society_id, d)
    text = _canonical(society_id, fy, date.today().isoformat(), body)
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    sig = signing_service.sign(society_id, "SIGNING_LEDGER", f"compliance|{society_id}|{fy}|{h}", db=d)
    d._execute("UPDATE compliance_certificates SET status='superseded' WHERE society_id=%s AND fy=%s AND status='valid'", (society_id, fy))
    row = d._execute("""INSERT INTO compliance_certificates (society_id, fy, generated_by, body_text, item_hash, overall, signature, key_version, key_id, algorithm)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                     (society_id, fy, user_id, text, h, body["overall"], sig["signature"], sig["key_version"], sig["key_id"], sig["algorithm"]), fetch_one=True)
    d._execute("INSERT INTO audit_events (society_id, actor_id, action, resource_type, resource_id, after_value, source) "
               "VALUES (%s,%s,'COMPLIANCE_CERTIFICATE_SIGNED','compliance_certificate',%s,%s::jsonb,'app')",
               (society_id, user_id, str(row["id"]), json.dumps({"fy": fy, "overall": body["overall"], "item_hash": h})))
    return {"id": row["id"], "fy": fy, "overall": body["overall"], "item_hash": h}


def verify(cert_id: int, db=None) -> dict:
    """'valid' | 'superseded' | 'revoked' | 'tampered' | 'untrusted' | 'unknown', with minimal public fields."""
    d = _db(db)
    r = d._execute("SELECT * FROM compliance_certificates WHERE id=%s", (cert_id,), fetch_one=True)
    if not r:
        return {"status": "unknown"}
    base = {"fy": r["fy"], "overall": r["overall"], "generated_on": r["generated_at"]}
    if r["status"] != "valid":
        return {"status": r["status"], **base}
    if hashlib.sha256(r["body_text"].encode("utf-8")).hexdigest() != r["item_hash"]:
        return {"status": "tampered", **base}
    res = signing_service.verify(r["society_id"], "SIGNING_LEDGER", f"compliance|{r['society_id']}|{r['fy']}|{r['item_hash']}",
                                 r["signature"], r["key_version"], r["generated_at"], db=d)
    return {"status": "valid" if res["valid"] else ("untrusted" if res["status"] == "untrusted" else "tampered"), **base}


def render_text(cert_id: int, society_id: int, db=None) -> str:
    """Plain-text copy for the society's own officers (full detail); the public page never shows this."""
    r = _db(db)._execute("SELECT body_text, fy FROM compliance_certificates WHERE id=%s AND society_id=%s", (cert_id, society_id), fetch_one=True)
    if not r:
        raise CertificateRefused("Certificate not found.")
    b = json.loads(r["body_text"])
    lines = [f"Compliance certificate {r['fy']} (generated {b['generated_on']}); overall: {b['overall']}", ""]
    lines += [f"[{c['result'].upper():9}] {c['label']} - {c['on']} - {c['note']}" for c in b["checks"]]
    if b["provisional"]:
        lines += ["", "Provisional items:"] + [f"  - {p['kind']}: {p['item']}" for p in b["provisional"]]
    return "\n".join(lines)
