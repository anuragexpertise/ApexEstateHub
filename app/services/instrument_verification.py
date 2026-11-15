"""Statute catalogue verification (Plan v3, task 2.7).

Only the Treasurer (a serving office-bearer) or an Auditor can mark an instrument verified, and only with the source link,
notification number, date and an opinion reference. The database refuses a 'verified' row that lacks any of these, and
returns a row to 'unverified' when its substance is edited. Unverified rows are labelled in the wizard and carry no link."""
from __future__ import annotations

import json
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


# ── Shared by the tick-box path and the verified.xlsx path ────────────────────────────────────────────────────────

# regime_code -> label used in messages. Only these two regimes can be verified by the platform master in bulk.
MASTER_REGIMES = {"CENTRAL": "Central", "UP_AOA_2010": "UP"}

NOTIFICATION_MAX = 500     # legal_instrument_catalog.notification_no (VARCHAR(500) in estatehub.sql)
OPINION_MAX = 255          # legal_instrument_catalog.opinion_ref

_MIGRATION_HINT = " (apply database/migrations/002_master_instrument_verification.sql first)"
_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


def _clean_date(verified_on):
    """-> (date | None, problem | None). A blank date means today (IST)."""
    on = verified_on or today_ist()
    if isinstance(on, str):
        try:
            on = date.fromisoformat(on[:10])
        except ValueError:
            return None, "The verified date is not a valid date."
    if on > today_ist():
        return on, "The verified date must not be in the future."
    return on, None


def _check_header(opinion_ref, verified_on) -> tuple[str, date | None, list[str]]:
    """Opinion + date checks common to every bulk path. Returns (opinion, date, problems)."""
    opinion = (opinion_ref or "").strip()
    on, bad_date = _clean_date(verified_on)
    problems = []
    if not opinion:
        problems.append("Enter the opinion reference (advocate or CA).")
    elif len(opinion) > OPINION_MAX:
        problems.append(f"The opinion reference is too long (max {OPINION_MAX} characters).")
    if bad_date:
        problems.append(bad_date)
    return opinion, on, problems


def _check_notification_and_url(label: str, notification_no, source_url) -> list[str]:
    notif = str(notification_no or "").strip()
    url = str(source_url or "").strip()
    out = []
    if not notif:
        out.append(f"{label}: notification number is required.")
    elif len(notif) > NOTIFICATION_MAX:
        out.append(f"{label}: notification number is {len(notif)} characters (max {NOTIFICATION_MAX}).")
    if not _URL_RE.match(url):
        out.append(f"{label}: a link (https://) to the source text is required.")
    return out


def _refuse(problems: list[str]):
    shown = " ".join(problems[:12]) + (f" (+{len(problems) - 12} more)" if len(problems) > 12 else "")
    raise ds.SigningRefused("Nothing was verified. " + shown)


def _write_verified(d, user_id: int, regime_code: str, rows: list[dict], opinion: str, on: date,
                    audit_action: str, extra: dict | None = None) -> int:
    """Mark every row verified and write ONE audit row, in ONE transaction: all of it commits or none of it does.

    rows: [{"id", "notification_no", "source_url"}], already validated. audit_events.resource_id is VARCHAR(64), so it holds the
    regime code; the instrument ids go in after_value (a long list of ids in resource_id overflowed it)."""
    ids = [int(r["id"]) for r in rows]
    payload = {"regime": regime_code, "opinion_ref": opinion, "verified_on": str(on), "count": len(ids), "ids": ids}
    payload.update(extra or {})
    try:
        with d._conn() as conn:
            cur = conn.cursor()
            for r in rows:
                cur.execute("SELECT fn_verify_instrument(%s,%s,%s,%s,%s,%s,%s)",
                            (int(r["id"]), user_id, "master", str(r["notification_no"]).strip(), str(r["source_url"]).strip(),
                             opinion, on))
            cur.execute("INSERT INTO audit_events (society_id, actor_id, actor_role, action, resource_type, resource_id, after_value, source) "
                        "VALUES (NULL,%s,'master',%s,'legal_instrument_catalog',%s,%s::jsonb,'app')",
                        (user_id, audit_action, regime_code, json.dumps(payload)))
    except ds.SigningRefused:
        raise
    except Exception as exc:  # noqa: BLE001 - the transaction has rolled back; say so, with the database's own reason
        msg = str(exc).split("\n")[0].replace("ERROR:", "").strip()
        if "Only the Treasurer or an Auditor" in msg or "verifier_role" in msg:
            msg += _MIGRATION_HINT
        raise ds.SigningRefused("Nothing was verified. " + msg) from exc
    return len(ids)


def verify_many_as_master(user_id, items, opinion_ref, verified_on=None, db=None, regime_code: str = "CENTRAL") -> int:
    """Platform master verifies several catalogue instruments of ONE regime (CENTRAL by default, or UP_AOA_2010) at once.

    items: [{"id", "notification_no", "source_url"}]. One shared opinion reference and date, but each instrument still needs its
    own notification number and https:// source link. Only unverified instruments of that regime can be selected (re-verifying a
    verified row would send it back to 'unverified' through trg_instrument_unverify). All or nothing: every problem is reported
    together and nothing is written unless all pass; the writes and the audit row share one transaction. Returns how many were
    verified."""
    d = _db(db)
    if not is_master(user_id, d):
        raise ds.SigningRefused("Only the platform master can verify instruments in bulk.")
    if regime_code not in MASTER_REGIMES:
        raise ds.SigningRefused(f"Unknown regime '{regime_code}'.")
    label_regime = MASTER_REGIMES[regime_code]
    items = [i for i in (items or []) if i.get("id") is not None]
    if not items:
        raise ds.SigningRefused("Select at least one instrument.")
    ids = [int(i["id"]) for i in items]
    if len(set(ids)) != len(ids):
        raise ds.SigningRefused("The same instrument is selected twice.")
    opinion, on, problems = _check_header(opinion_ref, verified_on)
    known = {r["id"]: r for r in (d._execute(
        "SELECT id, title, verification, regime_code FROM legal_instrument_catalog WHERE id = ANY(%s)", (ids,), fetch_all=True) or [])}
    for i in items:
        r = known.get(int(i["id"]))
        label = (r or {}).get("title") or f"#{i['id']}"
        if not r or r["regime_code"] != regime_code:
            problems.append(f"{label}: not a {label_regime} instrument.")
        elif r["verification"] == "verified":
            problems.append(f"{label}: already verified.")
        problems += _check_notification_and_url(label, i.get("notification_no"), i.get("source_url"))
    if problems:
        _refuse(problems)
    return _write_verified(d, user_id, regime_code, items, opinion, on, "INSTRUMENTS_VERIFIED_BULK")


# ── verified.xlsx: template (download) → fill → upload → mark instruments verified ─────────────────────────────────

_XLSX_SHEET_FOR_REGIME = {
    "CENTRAL": "Central Acts Rules",
    "UP_AOA_2010": "UP Acts Rules",
}

_XLSX_REQUIRED_COLS = ["title", "notification / gazette no.", "official url (complete)"]

_MIN_SUBSTRING_TITLE = 15   # a catalogue title shorter than this is only ever matched exactly (it would sit inside unrelated titles)


def _norm(s) -> str:
    """Case-, space- and punctuation-insensitive form of a title."""
    return " ".join(re.sub(r"[^0-9a-z]+", " ", str(s or "").lower()).split())


def _as_year(v):
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def _match_instrument(rows_db, xlsx_title: str, xlsx_year=None):
    """Match one xlsx row to one catalogue instrument by title (and enactment year when the sheet gives it).

    Order: exact normalised title, then one title contained in the other (catalogue titles of at least 15 characters only).
    A year in the sheet narrows candidates when it can. Returns (instrument | None, "ok" | "none" | "ambiguous")."""
    t = _norm(xlsx_title)
    if not t:
        return None, "none"
    year = _as_year(xlsx_year)

    def narrow(cands):
        if year is not None and len(cands) > 1:
            same = [r for r in cands if r.get("enactment_year") == year]
            if same:
                return same
        return cands

    exact = narrow([r for r in rows_db if _norm(r["title"]) == t])
    if len(exact) == 1:
        return exact[0], "ok"
    if len(exact) > 1:
        return None, "ambiguous"
    loose = narrow([r for r in rows_db
                    if len(_norm(r["title"])) >= _MIN_SUBSTRING_TITLE and (_norm(r["title"]) in t or t in _norm(r["title"]))])
    if len(loose) == 1:
        return loose[0], "ok"
    if len(loose) > 1:
        # one candidate that is strictly the longest title and whose year agrees is not a guess
        loose.sort(key=lambda r: len(_norm(r["title"])), reverse=True)
        if len(_norm(loose[0]["title"])) > len(_norm(loose[1]["title"])) and (year is None or loose[0].get("enactment_year") == year):
            return loose[0], "ok"
        return None, "ambiguous"
    return None, "none"


def template_rows(regime_code: str, db=None) -> list[list]:
    """Rows for the downloadable verified.xlsx template: every UNVERIFIED instrument of the regime, with its title, year,
    authority and applies_when filled in. The master only adds the notification number and the https:// source link
    (rows left blank are skipped on upload)."""
    d = _db(db)
    if regime_code == "CENTRAL":
        where, args = "regime_code = %s AND instrument_type IN ('Central Act', 'Central Rules')", (regime_code,)
    else:
        where, args = "regime_code = %s", (regime_code,)
    rows = d._execute(
        "SELECT instrument_type, title, enactment_year, issuing_authority, applies_when FROM legal_instrument_catalog "
        f"WHERE {where} AND verification <> 'verified' ORDER BY display_order, id", args, fetch_all=True) or []
    return [[n, regime_code, r["instrument_type"], r["title"], r["enactment_year"], r["issuing_authority"] or "",
             "", "", r.get("applies_when") or "", "", ""] for n, r in enumerate(rows, 1)]


def verify_from_uploaded_xlsx(user_id: int, regime_code: str, contents: str, filename: str,
                              opinion_ref: str, verified_on, db=None) -> dict:
    """Verify instruments from an uploaded verified.xlsx file (platform master only).

    Parses the sheet for `regime_code`, matches rows by title (+ year) to unverified catalogue instruments and marks them verified
    with the row's notification number and source URL, the shared opinion reference and date.

    All or nothing: every matched row is validated first and the writes plus the audit row share one transaction. A row that is
    blank in notification number or URL is skipped (so a half-filled template is fine); a row that is filled in wrongly (bad URL,
    over-long notification number), is ambiguous, or repeats an instrument stops the whole upload and is reported.

    Returns {"verified": n, "matched": n, "unmatched": [titles], "skipped_verified": [titles], "skipped_incomplete": [titles]}."""
    d = _db(db)
    if not is_master(user_id, d):
        raise ds.SigningRefused("Only the platform master can verify instruments from an upload.")
    if regime_code not in _XLSX_SHEET_FOR_REGIME:
        raise ds.SigningRefused(f"Unknown regime '{regime_code}'.")
    opinion, on, problems = _check_header(opinion_ref, verified_on)
    if problems:
        _refuse(problems)

    parsed = parse_upload(contents, filename, _XLSX_SHEET_FOR_REGIME[regime_code], _XLSX_REQUIRED_COLS)
    if parsed.errors:
        raise ds.SigningRefused("; ".join(parsed.errors))

    rows_db = d._execute(
        "SELECT id, title, enactment_year, verification FROM legal_instrument_catalog WHERE regime_code = %s",
        (regime_code,), fetch_all=True) or []

    to_write, claimed = [], {}
    unmatched, skipped_verified, skipped_incomplete = [], [], []
    for n, rec in enumerate(parsed.rows, start=2):                     # n = the sheet row number
        title = str(rec.get("title") or "").strip()
        notif = str(rec.get("notification / gazette no.") or "").strip()
        url = str(rec.get("official url (complete)") or "").strip()
        if not title:
            continue
        inst, how = _match_instrument(rows_db, title, rec.get("enactment year"))
        if how == "ambiguous":
            problems.append(f"Row {n} ({title}): matches more than one catalogue instrument; use the exact title and enactment year.")
            continue
        if not inst:
            unmatched.append(title)
            continue
        if inst["verification"] == "verified":
            skipped_verified.append(inst["title"])
            continue
        if not notif or not url:
            skipped_incomplete.append(inst["title"])
            continue
        if inst["id"] in claimed:
            problems.append(f"Row {n} ({title}): the same instrument as row {claimed[inst['id']]}; remove one of them.")
            continue
        bad = _check_notification_and_url(f"Row {n} ({inst['title']})", notif, url)
        if bad:
            problems += bad
            continue
        claimed[inst["id"]] = n
        to_write.append({"id": inst["id"], "notification_no": notif, "source_url": url})

    if problems:
        _refuse(problems)
    verified = _write_verified(d, user_id, regime_code, to_write, opinion, on, "INSTRUMENTS_VERIFIED_XLSX",
                               {"file": str(filename or "")[:120], "unmatched": unmatched[:50],
                                "skipped_verified": len(skipped_verified), "skipped_incomplete": len(skipped_incomplete)}) if to_write else 0
    return {"verified": verified, "matched": len(to_write), "unmatched": unmatched,
            "skipped_verified": skipped_verified, "skipped_incomplete": skipped_incomplete}
