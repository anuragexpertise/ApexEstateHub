"""Statute catalogue verification (Plan v3, task 2.7).

Only the Treasurer (a serving office-bearer) or an Auditor can mark an instrument verified, and only with the source link,
notification number, date and an opinion reference. The database refuses a 'verified' row that lacks any of these, and
returns a row to 'unverified' when its substance is edited. Unverified rows are labelled in the wizard and carry no link."""
from __future__ import annotations

import re
from datetime import date

from app.services import document_signing as ds
from app.services.xlsx_templates import parse_upload
from app.utils import today_ist


def _db(db=None):
    if db is not None:
        return db
    from database.db_manager import db as _d
    return _d


def verifier_role(society_id: int, user_id: int, db=None) -> str | None:
    d = _db(db)
    u = d._execute("SELECT role FROM users WHERE id=%s AND society_id=%s", (user_id, society_id), fetch_one=True) or {}
    if u.get("role") == "auditor":
        return "auditor"
    if any(o["office_code"] == "treasurer" for o in ds.serving_offices(society_id, user_id, db=d)):
        return "treasurer"
    return None


def verify(society_id, user_id, instrument_id, notification_no, source_url, opinion_ref, verified_on=None, db=None) -> str:
    d = _db(db)
    role = verifier_role(society_id, user_id, d)
    if not role:
        raise ds.SigningRefused("Only the Treasurer or an Auditor can verify an instrument.")
    try:
        r = d._execute("SELECT fn_verify_instrument(%s,%s,%s,%s,%s,%s,%s) AS r",
                       (int(instrument_id), user_id, role, (notification_no or "").strip(), (source_url or "").strip(),
                        (opinion_ref or "").strip(), verified_on or today_ist()), fetch_one=True)
    except Exception as exc:
        raise ds.SigningRefused(str(exc).split("\n")[0].replace("ERROR:", "").strip()) from exc
    d._execute("INSERT INTO audit_events (society_id, actor_id, action, resource_type, resource_id, after_value, source) "
               "VALUES (%s,%s,'INSTRUMENT_VERIFIED','legal_instrument_catalog',%s,%s::jsonb,'app')",
               (society_id, user_id, str(instrument_id), '{{"role": "{}", "notification_no": "{}"}}'.format(role, (notification_no or "").replace('"', ""))))
    return r["r"]


def is_master(user_id: int, db=None) -> bool:
    """The platform operator's login: is_master_admin with no society (the same test document_signing uses for 'platform')."""
    u = _db(db)._execute("SELECT is_master_admin, society_id FROM users WHERE id=%s", (user_id,), fetch_one=True) or {}
    return bool(u.get("is_master_admin")) and u.get("society_id") is None


def verify_many_as_master(user_id, items, opinion_ref, verified_on=None, db=None) -> int:
    """Platform master verifies several CENTRAL catalogue instruments at once.

    items: [{"id", "notification_no", "source_url"}]. One shared opinion reference and date, but each instrument still needs its
    own notification number and https:// source link. Only unverified instruments can be selected (re-verifying a verified row
    would send it back to 'unverified' through trg_instrument_unverify). All or nothing: every problem is reported together and
    nothing is written unless all pass; the writes and the audit row share one transaction. Returns how many were verified."""
    d = _db(db)
    if not is_master(user_id, d):
        raise ds.SigningRefused("Only the platform master can verify instruments in bulk.")
    items = [i for i in (items or []) if i.get("id") is not None]
    if not items:
        raise ds.SigningRefused("Select at least one instrument.")
    opinion = (opinion_ref or "").strip()
    on = verified_on or today_ist()
    if isinstance(on, str):
        try:
            on = date.fromisoformat(on[:10])
        except ValueError:
            raise ds.SigningRefused("The verified date is not a valid date.")
    problems = []
    if not opinion:
        problems.append("Enter the opinion reference (advocate or CA).")
    if on > today_ist():
        problems.append("The verified date must not be in the future.")
    ids = [int(i["id"]) for i in items]
    known = {r["id"]: r for r in (d._execute(
        "SELECT id, title, verification, regime_code FROM legal_instrument_catalog WHERE id = ANY(%s)", (ids,), fetch_all=True) or [])}
    for i in items:
        r = known.get(int(i["id"]))
        label = (r or {}).get("title") or f"#{i['id']}"
        if not r or r["regime_code"] != "CENTRAL":
            problems.append(f"{label}: not a Central instrument.")
        elif r["verification"] == "verified":
            problems.append(f"{label}: already verified.")
        if not (i.get("notification_no") or "").strip():
            problems.append(f"{label}: notification number is required.")
        if not re.match(r"^https?://\S+$", (i.get("source_url") or "").strip(), re.IGNORECASE):
            problems.append(f"{label}: a link (https://) to the source text is required.")
    if problems:
        raise ds.SigningRefused("Nothing was verified. " + " ".join(problems[:12]) + (f" (+{len(problems) - 12} more)" if len(problems) > 12 else ""))
    try:
        with d._conn() as conn:
            cur = conn.cursor()
            for i in items:
                cur.execute("SELECT fn_verify_instrument(%s,%s,%s,%s,%s,%s,%s)",
                            (int(i["id"]), user_id, "master", i["notification_no"].strip(), i["source_url"].strip(), opinion, on))
            cur.execute("INSERT INTO audit_events (society_id, actor_id, actor_role, action, resource_type, resource_id, after_value, source) "
                        "VALUES (NULL,%s,'master','INSTRUMENTS_VERIFIED_BULK','legal_instrument_catalog',%s,%s::jsonb,'app')",
                        (user_id, ",".join(str(x) for x in ids),
                         __import__("json").dumps({"opinion_ref": opinion, "verified_on": str(on), "count": len(ids)})))
    except ds.SigningRefused:
        raise
    except Exception as exc:
        msg = str(exc).split("\n")[0].replace("ERROR:", "").strip()
        if "Only the Treasurer or an Auditor" in msg or "verifier_role" in msg:
            msg += " (apply database/migrations/002_master_instrument_verification.sql first)"
        raise ds.SigningRefused("Nothing was verified. " + msg) from exc
    return len(ids)


# ── Upload verified.xlsx → mark instruments verified ──────────────────────────

_XLSX_SHEET_FOR_REGIME = {
    "CENTRAL": "Central Acts Rules",
    "UP_AOA_2010": "UP Acts Rules",
}

_XLSX_REQUIRED_COLS = ["title", "notification / gazette no.", "official url (complete)"]


def _norm(s) -> str:
    return " ".join(str(s or "").strip().lower().split())


def _match_instrument(rows_db, xlsx_title: str) -> dict | None:
    """Fuzzy match an xlsx row to a DB instrument by title (case-insensitive substring)."""
    t = _norm(xlsx_title)
    if not t:
        return None
    best = None
    best_len = 0
    for r in rows_db:
        db_t = _norm(r["title"])
        if not db_t:
            continue
        if db_t in t or t in db_t:
            if len(db_t) > best_len:
                best = r
                best_len = len(db_t)
    return best


def verify_from_uploaded_xlsx(user_id: int, regime_code: str, contents: str, filename: str,
                              opinion_ref: str, verified_on, db=None) -> dict:
    """Verify instruments from an uploaded verified.xlsx file.

    Parses the xlsx, matches rows by title to DB instruments in `regime_code`,
    and marks them verified via fn_verify_instrument (role = master). Returns
    {"verified": n, "matched": m, "unmatched": [titles], "errors": [...]}.
    """
    d = _db(db)
    if not is_master(user_id, d):
        raise ds.SigningRefused("Only the platform master can verify instruments from an upload.")
    opinion = (opinion_ref or "").strip()
    if not opinion:
        raise ds.SigningRefused("Enter the opinion reference (advocate or CA).")
    on = verified_on or today_ist()
    if isinstance(on, str):
        try:
            on = date.fromisoformat(on[:10])
        except ValueError:
            raise ds.SigningRefused("The verified date is not a valid date.")
    if on > today_ist():
        raise ds.SigningRefused("The verified date must not be in the future.")

    sheet = _XLSX_SHEET_FOR_REGIME.get(regime_code)
    result = parse_upload(contents, filename, sheet, _XLSX_REQUIRED_COLS)
    if result.errors:
        raise ds.SigningRefused("; ".join(result.errors))

    rows_db = d._execute(
        "SELECT id, title, verification, regime_code FROM legal_instrument_catalog WHERE regime_code = %s",
        (regime_code,), fetch_all=True) or []

    verified = 0
    matched = 0
    unmatched = []
    problems = []

    for rec in result.rows:
        title = rec.get("title")
        notif = rec.get("notification / gazette no.")
        url = rec.get("official url (complete)")
        if not title or not notif or not url:
            unmatched.append(str(title or "(no title)"))
            continue
        inst = _match_instrument(rows_db, title)
        if not inst:
            unmatched.append(str(title))
            continue
        if inst["verification"] == "verified":
            continue  # skip already-verified
        label = inst["title"]
        if not re.match(r"^https?://\S+$", str(url).strip(), re.IGNORECASE):
            problems.append(f"{label}: source URL must start with https://")
            continue
        try:
            d._execute("SELECT fn_verify_instrument(%s,%s,%s,%s,%s,%s,%s)",
                       (int(inst["id"]), user_id, "master", str(notif).strip(), str(url).strip(), opinion, on))
            verified += 1
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{label}: {str(exc).split(chr(10))[0].replace('ERROR:', '').strip()}")
            continue
        matched += 1

    if problems:
        raise ds.SigningRefused("Nothing was verified. " + " ".join(problems[:12]) +
                                (f" (+{len(problems) - 12} more)" if len(problems) > 12 else ""))

    # single audit row for the whole upload
    import json
    d._execute("INSERT INTO audit_events (society_id, actor_id, actor_role, action, resource_type, resource_id, after_value, source) "
               "VALUES (NULL,%s,'master','INSTRUMENTS_VERIFIED_XLSX','legal_instrument_catalog',%s::jsonb,'app')",
               (user_id, json.dumps({"regime": regime_code, "verified": verified, "matched": matched,
                                     "unmatched": unmatched, "opinion_ref": opinion, "verified_on": str(on)})))

    return {"verified": verified, "matched": matched, "unmatched": unmatched, "errors": []}
