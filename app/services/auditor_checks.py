# app/services/auditor_checks.py
"""
Read-only verification checks behind the Auditor portal.

Every check is a fixed SELECT against one of the SQL verification functions in
database/estatehub.sql. Nothing here writes, and nothing takes SQL text from the
caller: the only caller-supplied values are bound parameters (an account id, a
day, a resolution id). The society is always passed in by the callback from the
server-side session, and every resolution lookup is re-checked against it.

Each check returns a dict:
    {"status": "pass" | "finding" | "info" | "error" | "skipped",
     "columns": [...], "rows": [[...], ...], "total": int, "note": str}

"pass"    the check ran and found nothing wrong (an "empty = yes" query returned no rows)
"finding" the check ran and returned rows / a mismatch an auditor should look at
"info"    the check is a register or tally to read, not a pass/fail test
"""
from __future__ import annotations

from datetime import date, datetime

from database.db_manager import db

MAX_ROWS = 200

# Immutability triggers the schema is supposed to carry (estatehub.sql). Checking that they exist and are
# enabled is the read-only equivalent of attempting the UPDATE / DELETE / TRUNCATE in step 6.
TAMPER_GUARDS: tuple[tuple[str, str, str], ...] = (
    ("transactions", "trg_transactions_immutable", "blocks UPDATE / DELETE of posted ledger rows"),
    ("transactions", "trg_transactions_no_truncate", "blocks TRUNCATE of the ledger"),
    ("audit_events", "audit_events_immutable", "blocks UPDATE / DELETE of the audit log"),
    ("audit_events", "trg_audit_events_no_truncate", "blocks TRUNCATE of the audit log"),
    ("ledger_chain_anchors", "trg_anchor_immutable", "anchors are append-only"),
    ("regime_rule_audit", "regime_rule_audit_immutable", "rule-change audit is append-only"),
)

# Checks that need no input (run by "Run all").
SIMPLE_CHECKS = ("ledger_chain", "anchors", "integrity", "cash_vouchers", "receipt_chains", "tamper_guards", "legal")


def _cell(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat(sep=" ", timespec="seconds") if isinstance(v, datetime) else v.isoformat()
    if v is None:
        return ""
    return str(v)


def _result(status, rows, note="", columns=None):
    rows = rows or []
    cols = columns or (list(rows[0].keys()) if rows else [])
    return {
        "status": status,
        "columns": cols,
        "rows": [[_cell(r.get(c)) for c in cols] for r in rows[:MAX_ROWS]],
        "total": len(rows),
        "note": note,
    }


def _q(sql, params=()):
    return db.execute(sql, tuple(params), fetch_all=True) or []


def _empty_is_pass(rows, ok_note, bad_note):
    return _result("finding", rows, bad_note) if rows else _result("pass", [], ok_note)


# ── 2. ledger hash chain ───────────────────────────────────────────────────────
def ledger_chain(sid):
    rows = _q("SELECT * FROM fn_verify_ledger_chain(%s)", (sid,))
    return _empty_is_pass(rows, "Chain intact: every row matches its hash and links to the one before.",
                          "The ledger chain is broken at the rows below.")


# 2b. signed anchors (the HMAC needs the society's SIGNING_LEDGER key, so it is verified by scripts/anchor_ledgers.py --verify)
def anchors(sid):
    rows = _q("SELECT anchored_at, ledger_seq, row_count, method, "
              "       (signature IS NOT NULL) AS signed, external_ref "
              "  FROM ledger_chain_anchors WHERE society_id = %s ORDER BY ledger_seq DESC LIMIT 20", (sid,))
    note = ("Anchor register (latest 20). Signatures are HMAC-SHA256 under the society's SIGNING_LEDGER key "
            "and can only be checked by a host holding SECRET_VAULT_KEY: run `python scripts/anchor_ledgers.py --verify`.")
    if not rows:
        return _result("finding", [], "No anchor has ever been recorded for this society. " + note)
    unsigned = sum(1 for r in rows if not r["signed"])
    if unsigned:
        note = f"{unsigned} of the latest {len(rows)} anchors carry no signature. " + note
        return _result("finding", rows, note)
    return _result("info", rows, note)


# ── 3. journal balance ─────────────────────────────────────────────────────────
def integrity(sid):
    rows = _q("SELECT * FROM fn_ledger_integrity_report(%s)", (sid,))
    return _empty_is_pass(rows, "Every journal balances (Dr = Cr).", "Journals out of balance are listed below.")


# ── 4. cash vouchers and cash book ─────────────────────────────────────────────
def cash_vouchers(sid):
    rows = _q("SELECT * FROM fn_cash_voucher_report(%s) WHERE NOT amount_checked", (sid,))
    return _empty_is_pass(rows, "Every cash voucher is amount-checked against a source document.",
                          "Cash vouchers NOT amount-checked against a source document.")


def cashbook(sid, day):
    day = _parse_day(day) or date.today()
    rows = _q("SELECT * FROM fn_cashbook_reconciliation(%s, %s)", (sid, day))
    if not rows:
        return _result("error", [], "No result returned.")
    status = "pass" if (rows[0].get("status") or "").strip().lower() == "agrees" else "finding"
    return _result(status, rows, f"Cash book for {day.isoformat()}.")


# ── 5. receipt hash chains ─────────────────────────────────────────────────────
def receipt_chains(sid):
    rows = _q("SELECT * FROM fn_verify_all_receipt_chains(%s)", (sid,))
    if not rows:
        return _result("info", [], "No receipts on record for this society.")
    bad = [r for r in rows if not r.get("is_valid")]
    note = f"{len(rows)} account chain(s) checked, {len(bad)} broken."
    return _result("finding" if bad else "pass", rows, note)


def receipt_chain_one(sid, acc_id):
    try:
        acc = int(acc_id)
    except (TypeError, ValueError):
        return _result("skipped", [], "Enter an account id.")
    rows = _q("SELECT * FROM fn_verify_receipt_chain(%s, %s)", (sid, acc))
    if not rows:
        return _result("info", [], f"No receipts for account {acc}.")
    bad = [r for r in rows if not r.get("is_valid")]
    return _result("finding" if bad else "pass", rows, f"{len(rows)} receipt(s) in the chain, {len(bad)} broken.")


# ── 6. tamper guards (read-only: the triggers are present and enabled) ─────────
def tamper_guards(sid=None):
    names = [g[1] for g in TAMPER_GUARDS]
    found = {r["tgname"]: r for r in _q(
        "SELECT t.tgname, c.relname AS table_name, t.tgenabled "
        "  FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
        " WHERE NOT t.tgisinternal AND t.tgname = ANY(%s)", (names,))}
    rows, missing = [], 0
    for table, trg, purpose in TAMPER_GUARDS:
        r = found.get(trg)
        # 'O' = fires in origin mode (normal); 'A' = always. 'D' = disabled, 'R' = replica only: both let tampering through.
        ok = bool(r) and r["tgenabled"] in ("O", "A") and r["table_name"] == table
        missing += 0 if ok else 1
        rows.append({"table": table, "trigger": trg, "guards": purpose,
                     "state": "enabled" if ok else ("DISABLED / replica-only" if r else "MISSING")})
    note = ("Read-only check that the guards exist and are enabled. To see them refuse, run the UPDATE / DELETE / "
            "TRUNCATE statements from the reference panel on a COPY of the database, never on live books.")
    return _result("finding" if missing else "pass", rows, note)


# ── 7. resolution tally vs registers ───────────────────────────────────────────
def resolutions_for(sid):
    return _q("SELECT r.id, m.type, m.held_on, LEFT(COALESCE(r.text, r.body), 70) AS title "
              "  FROM resolutions r JOIN meetings m ON m.id = r.meeting_id "
              " WHERE m.society_id = %s ORDER BY m.held_on DESC, r.id DESC LIMIT 200", (sid,))


def resolution_tally(sid, resolution_id):
    try:
        rid = int(resolution_id)
    except (TypeError, ValueError):
        return _result("skipped", [], "Select a resolution.")
    own = _q("SELECT r.id, r.votes_for_pct, r.owners_present_pct, r.majority_required, r.status "
             "  FROM resolutions r JOIN meetings m ON m.id = r.meeting_id "
             " WHERE r.id = %s AND m.society_id = %s", (rid, sid))
    if not own:
        return _result("error", [], "That resolution does not belong to this society.")
    tally = _q("SELECT * FROM fn_resolution_vote_summary(%s)", (rid,))
    rows = []
    if tally:
        rows.append({"source": "Typed tally (vote + attendance registers)", **{k: tally[0].get(k) for k in (
            "weight_for", "weight_against", "weight_abstain", "weight_cast", "weight_present", "weight_registered",
            "votes_for_pct_of_cast", "owners_present_pct")}})
    o = own[0]
    rows.append({"source": f"Recorded on resolution ({o['status']}, majority required {o['majority_required']}%)",
                 "votes_for_pct_of_cast": o["votes_for_pct"], "owners_present_pct": o["owners_present_pct"]})
    cols = ["source", "weight_for", "weight_against", "weight_abstain", "weight_cast",
            "weight_present", "weight_registered", "votes_for_pct_of_cast", "owners_present_pct"]
    return _result("info", rows, "Compare the recorded percentages with the tally computed from the registers.", cols)


# ── tie-out: statements = ledger = source documents (Plan v3 3.2) ──────────────────────────────────────────────
def tieout(sid, fy=None):
    today = date.today()
    fy = int(fy) if fy else (today.year if today.month >= 4 else today.year - 1)
    rows = _q("SELECT * FROM fn_tieout_report(%s, %s)", (sid, fy))
    bad = [r for r in rows if not r["ok"]]
    note = f"Financial year {fy}-{str(fy + 1)[2:]}: " + ("every figure ties out." if not bad else f"{len(bad)} of {len(rows)} comparisons differ.")
    return _result("finding" if bad else "pass", rows, note,
                   ["label", "left_amount", "right_amount", "difference", "ok", "detail"])


# ── 8. legal instruments ───────────────────────────────────────────────────────
def legal(sid=None):
    rows = _q("SELECT instrument_type, title, status, last_verified_on, verification, notification_no, opinion_ref FROM legal_instrument_catalog "
              "ORDER BY display_order, instrument_type, title")
    unverified = sum(1 for r in rows if r.get("verification") != "verified")
    note = f"{len(rows)} instruments, {unverified} never verified." if rows else "Catalogue is empty."
    return _result("info", rows, note)


def _parse_day(v):
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v)[:10]).date()
    except (TypeError, ValueError):
        return None


def run(check: str, sid: int, day=None, acc_id=None, resolution_id=None) -> dict:
    """Dispatch one check. Unknown names are an error, never executed. Any DB error becomes an 'error' result."""
    try:
        if check == "cashbook":
            return cashbook(sid, day)
        if check == "receipt_chain_one":
            return receipt_chain_one(sid, acc_id)
        if check == "resolution":
            return resolution_tally(sid, resolution_id)
        fn = {"tieout": tieout, "ledger_chain": ledger_chain, "anchors": anchors, "integrity": integrity,
              "cash_vouchers": cash_vouchers, "receipt_chains": receipt_chains,
              "tamper_guards": tamper_guards, "legal": legal}.get(check)
        if fn is None:
            return _result("error", [], f"Unknown check '{check}'.")
        return fn(sid)
    except Exception as exc:  # a missing function / permission problem must show as an error, never a blank panel
        return _result("error", [], f"Check could not run: {exc}")
