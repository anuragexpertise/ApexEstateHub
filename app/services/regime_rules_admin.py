# app/services/regime_rules_admin.py
"""
Master-only maintenance of the legal-regime rule tables behind the UP AOA compliance layer.

What master can change here, and how:
  * regime_rule_parameters  — NEVER edited in place. A change is a new row with a later
    effective_from; the row it replaces is closed the day before. fn_regime_param_* already
    select by effective date, so history stays queryable and nothing past is rewritten.
  * legal_instrument_catalog — status / provisions / applicability / source / last-verified.
    Rows are retired (status='superseded'), never deleted.
  * societies.cash_limit_mode — per-society warn | block | regime default.

Every write is ONE SQL statement (data-modifying CTE) that also appends to regime_rule_audit,
so a change and its audit row commit or fail together. Every function takes the actor's role
and refuses anything but 'master' — callers must resolve that from the server-side session
(app.security.audit_context), never from the browser's auth-store.

SQL passed to db._execute with a dict uses :name conversion, so this module avoids '::' casts
and bare colons inside SQL text (CAST(... AS date) instead).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from database.db_manager import db

DEFAULT_REGIME = "UP_AOA_2010"
MIN_TEXT = 10  # reason / source must say something real; matches the audit table's CHECK


@dataclass(frozen=True)
class RuleSpec:
    kind: str                       # 'int' | 'num' | 'text'
    lo: float | None = None
    hi: float | None = None
    choices: tuple[str, ...] = ()
    statutory: bool = True          # False = engine policy, not a statute figure
    label: str = ""


# Only keys seeded in estatehub.sql can be edited: a new key would have no SQL function reading it.
RULE_SPECS: dict[str, RuleSpec] = {
    "transfer_fee_pct":              RuleSpec("num", 0.0001, 5, label="Bye-law 39 transfer fee (% of value)"),
    "nodues_deemed_days":            RuleSpec("int", 1, 90, label="No Dues deemed granted after (days)"),
    "petty_cash_limit":              RuleSpec("num", 1, 10_000_000, label="Petty cash ceiling (INR)"),
    "cash_payment_cheque_threshold": RuleSpec("num", 1, 10_000_000, label="Cash payments above this breach (INR)"),
    "cash_limit_default_mode":       RuleSpec("text", choices=("warn", "block"), statutory=False,
                                              label="Cash-limit enforcement default (engine policy)"),
    "statement_publish_due_month":   RuleSpec("int", 1, 12, label="Bye-law 49 publish deadline — month"),
    "statement_publish_due_day":     RuleSpec("int", 1, 31, label="Bye-law 49 publish deadline — day"),
    "authority_copy_due_month":      RuleSpec("int", 1, 12, label="Bye-law 49 authority copy — month"),
    "authority_copy_due_day":        RuleSpec("int", 1, 31, label="Bye-law 49 authority copy — day"),
    "owner_summary_days":            RuleSpec("int", 1, 90, label="Bye-law 49 owner summary within (days)"),
    "arrears_disqualify_days":       RuleSpec("int", 1, 365, label="Bye-law 7 arrears bar after (days)"),
    "owner_loan_blocks_nodues":      RuleSpec("int", 0, 1, statutory=False,
                                              label="Outstanding owner loan blocks issuing No Dues (1 = yes)"),
    "owner_loan_counts_bye_law7":    RuleSpec("int", 0, 1, statutory=False,
                                              label="Overdue owner loan counts as bye-law 7 arrears (1 = yes)"),
    "owner_loan_counts_s22":         RuleSpec("int", 0, 1, statutory=False,
                                              label="Overdue owner loan counts toward the s.22 dues test (1 = yes)"),
    "bye_law7_year_basis":           RuleSpec("text", choices=("financial_year", "calendar_year"), statutory=False,
                                              label="Bye-law 7 'year' basis (contested; default)"),
    "s22_default_months":            RuleSpec("int", 1, 60, label="s.22 default must exceed (months)"),
    "s22_notice_days":               RuleSpec("int", 1, 90, label="s.22 notice to defaulter (days)"),
    "s22_wait_months":               RuleSpec("int", 1, 12, label="s.22 wait after certified copy (months)"),
    "s22_appeal_days":               RuleSpec("int", 1, 90, label="s.22 appeal window (days)"),
    "s20_recovery_months":           RuleSpec("int", 1, 60, label="s.20 recovery after unpaid (months)"),
}

CATALOG_STATUSES = ("active", "superseded", "draft")
CASH_MODES = ("warn", "block")

# Tables the raw-SQL "Integrate to DB" box must not touch: edits there skip validation and the audit log.
PROTECTED_TABLES = ("regime_rule_parameters", "legal_instrument_catalog", "legal_regime_profiles",
                    "society_legal_regime", "regime_rule_audit")
_PROTECTED_RE = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE(?:\s+TABLE)?|ALTER\s+TABLE|DROP\s+TABLE|COPY)\s+"
    r"(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?\"?(?:public\"?\.\"?)?(" + "|".join(PROTECTED_TABLES) + r")\b",
    re.IGNORECASE,
)


def is_protected_rule_sql(sql: str) -> str | None:
    """Name of the protected table a write statement targets, else None. A guardrail against
    accidents, not a security boundary (a DO block or function can still reach the tables)."""
    cleaned = re.sub(r"/\*.*?\*/", " ", sql or "", flags=re.S)
    cleaned = re.sub(r"--[^\n]*", " ", cleaned)
    m = _PROTECTED_RE.search(cleaned)
    return m.group(2).lower() if m else None


# ── helpers ───────────────────────────────────────────────────────────────────
def _require_master(role):
    if role != "master":
        raise PermissionError("Master role required.")


def _require_writer(actor_role, actor_society_id, society_id, *, master_ok: bool = True):
    """Who may write a society-level record.

    A society admin may write ONLY their own society. Master may write any society only where master_ok is
    True (cash-limit mode). Bye-law adoption, meetings, resolutions and enactment are the society's own
    governance, so they pass master_ok=False: admin of that society only."""
    if actor_role == "master" and master_ok:
        return
    if actor_role == "admin":
        try:
            same = int(actor_society_id) == int(society_id)
        except (TypeError, ValueError):
            same = False
        if same:
            return
        raise PermissionError("You can only change records of your own society.")
    raise PermissionError("Admin role required." if not master_ok else "Master role required.")


def _d(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date() if value else None
    except ValueError:
        return None


def _text(value, minimum=0) -> str | None:
    s = (value or "").strip()
    return s if len(s) >= minimum else None


def _rows(sql, params=None) -> list[dict]:
    return db._execute(sql, params, fetch_all=True) or []


def _row(sql, params=None) -> dict | None:
    return db._execute(sql, params, fetch_one=True)


def _md(month, day) -> tuple[int, int] | None:
    """(month, day) if it exists in a leap year (so 29 Feb is tolerated), else None."""
    try:
        date(2024, int(month), int(day))
        return int(month), int(day)
    except (TypeError, ValueError):
        return None


# ── validation (pure; unit-tested without a database) ────────────────────────
def validate_rule_value(rule_key: str, raw) -> tuple[bool, str, float | None, str | None]:
    """-> (ok, message, value, value_text). Exactly one of value / value_text is set on success."""
    spec = RULE_SPECS.get(rule_key)
    if not spec:
        return False, f"'{rule_key}' is not an editable rule.", None, None
    if spec.kind == "text":
        v = (str(raw).strip().lower() if raw is not None else "")
        if v not in spec.choices:
            return False, f"{rule_key} must be one of: {', '.join(spec.choices)}.", None, None
        return True, "", None, v
    try:
        num = float(str(raw).strip())
    except (TypeError, ValueError):
        return False, f"{rule_key} must be a number.", None, None
    if num != num or num in (float("inf"), float("-inf")):
        return False, f"{rule_key} must be a finite number.", None, None
    if spec.kind == "int" and num != int(num):
        return False, f"{rule_key} must be a whole number.", None, None
    if (spec.lo is not None and num < spec.lo) or (spec.hi is not None and num > spec.hi):
        return False, f"{rule_key} must be between {spec.lo:g} and {spec.hi:g}.", None, None
    return True, "", (int(num) if spec.kind == "int" else num), None


def check_cross_rules(rule_key: str, new_value, effective: dict[str, float | str | None]) -> str | None:
    """Rules that only make sense together. `effective` = every rule value in force on the new
    row's effective_from. Returns an error message or None."""
    ev = dict(effective)
    ev[rule_key] = new_value
    for m, d, label in (("statement_publish_due_month", "statement_publish_due_day", "Bye-law 49 publish deadline"),
                        ("authority_copy_due_month", "authority_copy_due_day", "Bye-law 49 authority-copy deadline")):
        if rule_key in (m, d) and (ev.get(m) is not None and ev.get(d) is not None):
            if not _md(ev[m], ev[d]):
                return f"{label}: month {int(ev[m])} / day {int(ev[d])} is not a real calendar date."
    pub = _md(ev.get("statement_publish_due_month"), ev.get("statement_publish_due_day"))
    auth = _md(ev.get("authority_copy_due_month"), ev.get("authority_copy_due_day"))
    if rule_key.startswith(("statement_publish_due", "authority_copy_due")) and pub and auth and auth < pub:
        return "The authority-copy deadline cannot fall before the statement-publication deadline."
    return None


# ── reads ─────────────────────────────────────────────────────────────────────
def effective_rules(regime_code: str, on: date | None = None) -> list[dict]:
    """The row in force for each rule on `on` (default today)."""
    on = on or date.today()
    return _rows(
        """SELECT DISTINCT ON (rule_key) rule_key, value, value_text, unit, source_reference,
                  effective_from, effective_to
           FROM regime_rule_parameters
           WHERE regime_code = %(r)s AND effective_from <= %(d)s AND (effective_to IS NULL OR effective_to >= %(d)s)
           ORDER BY rule_key, effective_from DESC""",
        {"r": regime_code, "d": on})


def scheduled_rules(regime_code: str) -> list[dict]:
    return _rows(
        """SELECT rule_key, value, value_text, unit, source_reference, effective_from
           FROM regime_rule_parameters WHERE regime_code = %(r)s AND effective_from > CURRENT_DATE
           ORDER BY effective_from, rule_key""", {"r": regime_code})


def rule_history(regime_code: str, rule_key: str) -> list[dict]:
    return _rows(
        """SELECT value, value_text, unit, source_reference, effective_from, effective_to
           FROM regime_rule_parameters WHERE regime_code = %(r)s AND rule_key = %(k)s
           ORDER BY effective_from DESC""", {"r": regime_code, "k": rule_key})


def societies_on_regime(regime_code: str) -> int:
    row = _row("SELECT count(*) AS n FROM society_legal_regime WHERE regime_code = %(r)s", {"r": regime_code})
    return int((row or {}).get("n") or 0)


def list_instruments(regime_code: str) -> list[dict]:
    return _rows(
        """SELECT id, instrument_type, title, enactment_year, issuing_authority, applicability,
                  key_provisions, source_reference, status, last_verified_on
           FROM legal_instrument_catalog WHERE regime_code = %(r)s ORDER BY display_order, id""",
        {"r": regime_code})


def list_societies_cash_mode(regime_code: str) -> list[dict]:
    return _rows(
        """SELECT s.id, s.name, s.cash_limit_mode
           FROM societies s JOIN society_legal_regime slr ON slr.society_id = s.id
           WHERE slr.regime_code = %(r)s ORDER BY s.name""", {"r": regime_code})


def recent_audit(limit: int = 25, society_id: int | None = None) -> list[dict]:
    """Newest audit rows. With society_id: that society's own rows plus regime-wide rule changes
    (which apply to it); never another society's rows."""
    where, params = "", {"n": int(limit)}
    if society_id is not None:
        where = "WHERE a.society_id = %(s)s OR (a.society_id IS NULL AND a.target_table = 'regime_rule_parameters')"
        params["s"] = int(society_id)
    return _rows(
        f"""SELECT a.changed_at, a.target_table, a.regime_code, a.society_id, a.rule_key, a.action,
                   a.old_value, a.new_value, a.reason, a.changed_by, a.changed_by_role
            FROM regime_rule_audit a {where} ORDER BY a.id DESC LIMIT %(n)s""", params)


def society_regime(society_id) -> str | None:
    """The legal regime a society is on (None if not on one)."""
    row = _row("SELECT regime_code FROM society_legal_regime WHERE society_id = %(s)s LIMIT 1", {"s": society_id})
    return (row or {}).get("regime_code")


def society_cash_mode(society_id) -> str | None:
    row = _row("SELECT cash_limit_mode FROM societies WHERE id = %(s)s", {"s": society_id})
    return (row or {}).get("cash_limit_mode")


# ── writes ────────────────────────────────────────────────────────────────────
def save_rule_version(actor_id, actor_role, regime_code: str, rule_key: str, raw_value, effective_from,
                      source_reference, reason, confirmed: bool = False) -> tuple[bool, str]:
    """Add a new dated version of one rule. Returns (ok, message)."""
    _require_master(actor_role)
    spec = RULE_SPECS.get(rule_key)
    ok, msg, value, value_text = validate_rule_value(rule_key, raw_value)
    if not ok:
        return False, msg
    start = _d(effective_from)
    if not start:
        return False, "Choose the date the new value takes effect."
    if start < date.today():
        return False, "A rule change cannot be back-dated: it would silently re-grade filings and eligibility already reported."
    source = _text(source_reference, MIN_TEXT)
    why = _text(reason, MIN_TEXT)
    if not source:
        return False, f"Cite the amending Act / notification / bye-law (at least {MIN_TEXT} characters)."
    if not why:
        return False, f"Say why the rule is changing (at least {MIN_TEXT} characters)."

    latest = _row("""SELECT value, value_text, source_reference, effective_from FROM regime_rule_parameters
                     WHERE regime_code = %(r)s AND rule_key = %(k)s ORDER BY effective_from DESC LIMIT 1""",
                  {"r": regime_code, "k": rule_key})
    if not latest:
        return False, f"{rule_key} is not defined for {regime_code}; only existing rules can be versioned."
    if start <= latest["effective_from"]:
        return False, (f"The new version must start after the latest existing one "
                       f"({latest['effective_from']:%d %b %Y}).")
    cur_val = latest["value"] if spec.kind != "text" else latest["value_text"]
    if (spec.kind == "text" and value_text == cur_val) or (spec.kind != "text" and cur_val is not None
                                                           and float(cur_val) == float(value)):
        return False, "That is already the value in force; nothing to change."
    if spec.statutory:
        if not confirmed:
            return False, "Tick the confirmation: this is a statutory figure and should only change with an amendment."
        if source.strip().lower() == (latest["source_reference"] or "").strip().lower():
            return False, "The source must cite the amending instrument, not the one already on file."

    in_force = {r["rule_key"]: (r["value_text"] if RULE_SPECS.get(r["rule_key"], RuleSpec("num")).kind == "text"
                                else (float(r["value"]) if r["value"] is not None else None))
                for r in effective_rules(regime_code, start)}
    err = check_cross_rules(rule_key, value if spec.kind != "text" else value_text, in_force)
    if err:
        return False, err

    row = _row(
        """WITH prev AS (
               SELECT value, value_text, unit, source_reference, effective_from FROM regime_rule_parameters
               WHERE regime_code = %(r)s AND rule_key = %(k)s ORDER BY effective_from DESC LIMIT 1
           ), closed AS (
               UPDATE regime_rule_parameters SET effective_to = CAST(%(start)s AS date) - 1
               WHERE regime_code = %(r)s AND rule_key = %(k)s AND effective_from < %(start)s
                 AND (effective_to IS NULL OR effective_to >= %(start)s)
               RETURNING effective_from
           ), ins AS (
               INSERT INTO regime_rule_parameters
                      (regime_code, rule_key, value, value_text, unit, source_reference, effective_from)
               SELECT %(r)s, %(k)s, %(v)s, %(vt)s, prev.unit, %(src)s, %(start)s FROM prev
               RETURNING regime_code, rule_key, value, value_text, unit, source_reference, effective_from
           )
           INSERT INTO regime_rule_audit
                  (target_table, regime_code, rule_key, action, old_value, new_value, reason, changed_by, changed_by_role)
           SELECT 'regime_rule_parameters', %(r)s, %(k)s, 'new_version',
                  (SELECT to_jsonb(prev) FROM prev), to_jsonb(ins), %(why)s, %(uid)s, 'master'
           FROM ins RETURNING id""",
        {"r": regime_code, "k": rule_key, "v": value, "vt": value_text, "src": source,
         "start": start, "why": why, "uid": actor_id})
    if not row:
        return False, "Nothing was saved."
    n = societies_on_regime(regime_code)
    return True, (f"{rule_key} will change from {start:%d %b %Y} for {n} society(ies) on {regime_code}.")


def update_instrument(actor_id, actor_role, instrument_id, status, applicability, key_provisions,
                      source_reference, last_verified_on, reason) -> tuple[bool, str]:
    _require_master(actor_role)
    if status not in CATALOG_STATUSES:
        return False, f"Status must be one of: {', '.join(CATALOG_STATUSES)}."
    prov, src, why = _text(key_provisions, 1), _text(source_reference, 1), _text(reason, MIN_TEXT)
    if not prov or not src:
        return False, "Key provisions and the source reference cannot be blank."
    if not why:
        return False, f"Say why the entry is changing (at least {MIN_TEXT} characters)."
    verified = _d(last_verified_on)
    if last_verified_on and not verified:
        return False, "Last-verified date is not a valid date."
    if verified and verified > date.today() + timedelta(days=1):
        return False, "Last-verified date cannot be in the future."
    try:
        iid = int(instrument_id)
    except (TypeError, ValueError):
        return False, "Choose an instrument."
    row = _row(
        """WITH before_row AS (SELECT * FROM legal_instrument_catalog WHERE id = %(id)s),
                upd AS (
                    UPDATE legal_instrument_catalog c
                    SET status = %(st)s, applicability = %(app)s, key_provisions = %(prov)s,
                        source_reference = %(src)s, last_verified_on = %(ver)s, updated_at = NOW()
                    FROM before_row b WHERE c.id = b.id RETURNING c.*)
           INSERT INTO regime_rule_audit
                  (target_table, regime_code, rule_key, action, old_value, new_value, reason, changed_by, changed_by_role)
           SELECT 'legal_instrument_catalog', upd.regime_code, upd.title, 'update',
                  to_jsonb(b), to_jsonb(upd), %(why)s, %(uid)s, 'master'
           FROM upd JOIN before_row b ON b.id = upd.id RETURNING id""",
        {"id": iid, "st": status, "app": _text(applicability) or None, "prov": prov, "src": src,
         "ver": verified, "why": why, "uid": actor_id})
    return (True, "Catalog entry updated.") if row else (False, "That instrument no longer exists.")


def set_cash_limit_mode(actor_id, actor_role, society_id, mode, reason, actor_society_id=None) -> tuple[bool, str]:
    """mode: 'warn' | 'block' | '' (clear -> regime default). Society-specific, so only that society's admin."""
    _require_writer(actor_role, actor_society_id, society_id, master_ok=False)
    mode = (mode or "").strip().lower() or None
    if mode is not None and mode not in CASH_MODES:
        return False, "Mode must be warn, block, or blank for the regime default."
    why = _text(reason, MIN_TEXT)
    if not why:
        return False, f"Say why the mode is changing (at least {MIN_TEXT} characters)."
    try:
        sid = int(society_id)
    except (TypeError, ValueError):
        return False, "Choose a society."
    row = _row(
        """WITH before_row AS (SELECT id, cash_limit_mode FROM societies WHERE id = %(sid)s),
                upd AS (UPDATE societies s SET cash_limit_mode = %(m)s FROM before_row b
                        WHERE s.id = b.id RETURNING s.id, s.cash_limit_mode)
           INSERT INTO regime_rule_audit
                  (target_table, society_id, rule_key, action, old_value, new_value, reason, changed_by, changed_by_role)
           SELECT 'societies.cash_limit_mode', upd.id, 'cash_limit_mode', 'set',
                  to_jsonb(b), to_jsonb(upd), %(why)s, %(uid)s, %(role)s
           FROM upd JOIN before_row b ON b.id = upd.id RETURNING id""",
        {"sid": sid, "m": mode, "why": why, "uid": actor_id, "role": actor_role})
    if not row:
        return False, "Society not found."
    return True, f"Cash-limit mode set to {mode or 'regime default'}."


# ════════════════════════════════════════════════════════════════════════════════
# Society Bye-Laws (Phase 3) — clause-level acceptance register
# ════════════════════════════════════════════════════════════════════════════════

BYE_LAW_STATUSES = ("adopted_as_is", "adopted_with_variation", "not_adopted", "provisional")
BYE_LAW_LAYERS = (1, 2, 3)
# What an admin/master can *choose* for a clause. Whether the choice is provisional or active is not
# a choice: it is provisional until a passed resolution of the right type is linked (see _check_resolution).
ADOPTION_CHOICES = ("adopted_as_is", "adopted_with_variation", "not_adopted")
# Clauses the engine itself enforces (fn_resolve_rule's Layer-0 baseline): 7 (arrears bar), 39 (No Dues / transfer
# fee), 49 (cash and cheque limits, statement filings), 55 (the Act prevails over the bye-laws). A society cannot opt
# out of these by default; the Setup Wizard's droppable_* policy can lift that, with a resolution. Numbering was
# checked against the notified text; whether each clause is really non-droppable is a legal call - ask an advocate.
STATUTE_BACKED_CLAUSES = ("BL_07", "BL_39", "BL_49", "BL_55")

# Society-resolution policies chosen from drop-downs in the Setup Wizard. Stored in society_policy_settings as
# PROVISIONAL rows; the engine (fn_society_policy) only reads a row once a passed resolution backs it (recording
# that resolution activates it automatically - see _auto_activate).
# key -> (label, clause the resolution must be about, ((value, label), ...)); the FIRST choice is the default.
POLICY_SPECS: dict[str, tuple] = {
    "nodues_blocks_on": ("What blocks issuing a No Dues Certificate", "BL_39",
                         (("loans_only", "Outstanding owner loans only (default)"),
                          ("dues_and_loans", "Ordinary dues and owner loans"))),
    "vote_ineligibility_basis": ("Overdue bills that bar a 'no dues' poll vote", "BL_08",
                                 (("any_overdue", "Any overdue bill (default)"),
                                  ("margin_60_days", "Only arrears over 60 days (bye-law 7 margin)"))),
    "vote_loan_basis": ("Owner loans that bar a 'no dues' poll vote", "BL_08",
                        (("margin_60_days", "Only a loan over 60 days past its due date (default)"),
                         ("any_overdue", "Any loan past its due date"))),
}
for _bl in STATUTE_BACKED_CLAUSES:
    POLICY_SPECS[f"droppable_{_bl}"] = (
        f"{_bl} may be recorded as 'not adopted'", _bl,
        (("locked", "Enforced by the engine - cannot be dropped (default)"),
         ("droppable", "Society may drop this clause")))
del _bl


def policy_default(policy_key: str) -> str:
    return POLICY_SPECS[policy_key][2][0][0]


def society_policy(society_id, policy_key: str) -> str:
    """Active value of a society policy (resolution-backed), else the default. Never raises."""
    if policy_key not in POLICY_SPECS:
        raise KeyError(policy_key)
    try:
        row = _row("SELECT fn_society_policy(%s, %s) AS v", (int(society_id), policy_key))
        if row and row.get("v"):
            return row["v"]
    except Exception:
        pass
    return policy_default(policy_key)


def clause_is_locked(society_id, clause_id: str) -> bool:
    """True if this society cannot record the clause as 'not adopted'."""
    if clause_id not in STATUTE_BACKED_CLAUSES:
        return False
    return society_policy(society_id, f"droppable_{clause_id}") != "droppable"

# Model Bye-Laws for UP Apartment Owners' Associations, notified 16 Nov 2011 (No. 3977/8-1-11-115D.A./02T.C.-I) under
# s.14(6) of the 2010 Act: 58 clauses, numbered and titled as in the notification.
MODEL_BYE_LAW_CLAUSES = [
    ("BL_01", "Short title and application"),
    ("BL_02", "Definitions"),
    ("BL_03", "Objects of Association"),
    ("BL_04", "Members of Association"),
    ("BL_05", "Joint Apartment Owners"),
    ("BL_06", "Holding one share compulsory"),
    ("BL_07", "Disqualification (arrears over 60 days)"),
    ("BL_08", "Voting"),
    ("BL_09", "Quorum"),
    ("BL_10", "Votes to be cast in person"),
    ("BL_11", "Powers and duties of Association"),
    ("BL_12", "Place of Meetings"),
    ("BL_13", "Annual Meetings"),
    ("BL_14", "Special Meetings"),
    ("BL_15", "Notice of Meetings"),
    ("BL_16", "Adjourned Meeting"),
    ("BL_17", "Order of Business"),
    ("BL_18", "Management of Association (Board)"),
    ("BL_19", "President"),
    ("BL_20", "Vice-President"),
    ("BL_21", "Secretary"),
    ("BL_22", "Treasurer"),
    ("BL_23", "Manager"),
    ("BL_24", "Powers and Duties of the Board"),
    ("BL_25", "Other Duties of the Board"),
    ("BL_26", "Election and term of office"),
    ("BL_27", "Vacancies"),
    ("BL_28", "Removal of office bearers"),
    ("BL_29", "Organisation of meeting"),
    ("BL_30", "Regular Meetings of the Board"),
    ("BL_31", "Special Meetings of the Board"),
    ("BL_32", "Waiver of notice"),
    ("BL_33", "Quorum of the Board"),
    ("BL_34", "Fidelity Bonds"),
    ("BL_35", "Assessments"),
    ("BL_36", "Maintenance and Repairs"),
    ("BL_37", "Major repairs"),
    ("BL_38", "Use of Dwelling Units - internal changes"),
    ("BL_39", "Transfer of an Apartment - No Dues Certificate, transfer fee"),
    ("BL_40", "Use of Apartments, Common Areas and Facilities"),
    ("BL_41", "Right of Entry"),
    ("BL_42", "Rules of Conduct"),
    ("BL_43", "Damages"),
    ("BL_44", "Unlawful activities"),
    ("BL_45", "Visitors and Guests"),
    ("BL_46", "Funds"),
    ("BL_47", "Investment"),
    ("BL_48", "Affiliation"),
    ("BL_49", "Accounts - petty cash, cheque limit, audited statement filings"),
    ("BL_50", "Publication of Accounts and Reports"),
    ("BL_51", "Appointment of Auditors"),
    ("BL_52", "Power of Auditor"),
    ("BL_53", "Notice to Association of mortgage"),
    ("BL_54", "Notice of un-paid assessments"),
    ("BL_55", "Compliance - the Act prevails over the bye-laws"),
    ("BL_56", "Seal of the Association"),
    ("BL_57", "Power of competent authority to inspect the building"),
    ("BL_58", "Amendment of Bye-Laws"),
]


def governance_snapshot(society_id) -> dict:
    """Numbers for the Settings summary strip: choices still awaiting a resolution, last meeting, open enactments."""
    out = {"pending_choices": 0, "last_meeting": None, "pending_enactments": 0}
    try:
        r = _row("""SELECT (SELECT COUNT(*) FROM society_bye_laws WHERE society_id = %(s)s AND status = 'provisional') AS bl,
                           (SELECT COUNT(*) FROM society_policy_settings WHERE society_id = %(s)s AND resolution_id IS NULL) AS pol,
                           (SELECT MAX(held_on) FROM meetings WHERE society_id = %(s)s) AS last_meeting""",
                 {"s": int(society_id)}) or {}
        out["pending_choices"] = int(r.get("bl") or 0) + int(r.get("pol") or 0)
        out["last_meeting"] = r.get("last_meeting")
    except Exception:
        pass
    try:
        out["pending_enactments"] = len(list_pending_enactments(society_id))
    except Exception:
        pass
    return out


def clause_title(clause_id: str) -> str:
    return dict(MODEL_BYE_LAW_CLAUSES).get(clause_id, clause_id)


def clause_rules(society_id, clause_id: str) -> dict:
    """What an admin may choose for a clause: locked (cannot be 'not adopted') / fixed (cannot be varied)."""
    try:
        locked = clause_is_locked(society_id, clause_id)
    except Exception:
        locked = clause_id in STATUTE_BACKED_CLAUSES
    return {"title": clause_title(clause_id), "locked": locked, "fixed": clause_id == "BL_55"}


MODEL_BYE_LAWS_REFERENCE = "UP Model Bye-Laws, notified 16 Nov 2011 (No. 3977/8-1-11-115D.A./02T.C.-I) under s.14(6) of the Act"
# Official copy of the notification, hosted by UP-RERA. It is only the fallback: Master sets the link that
# every society sees by putting an https:// URL in the Model Bye-Laws entry's 'Source reference'
# (RWA Compliance (UP) -> Edit a catalog entry).
MODEL_BYE_LAWS_DEFAULT_URL = "https://up-rera.in/pdf/Model-By-Laws.pdf"
_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def model_bye_laws_source(regime_code: str = DEFAULT_REGIME) -> dict:
    """{'reference', 'url'} for the notified Model Bye-Laws. The link is the first http(s) URL in the catalog's
    Bye-laws entry 'Source reference' (editable by Master); if there is none, the official UP-RERA copy."""
    url = None
    try:
        row = _row("""SELECT source_reference FROM legal_instrument_catalog
                      WHERE regime_code = %(r)s AND instrument_type = 'Bye-laws' ORDER BY display_order, id LIMIT 1""",
                   {"r": regime_code})
    except Exception:
        row = None
    if row:
        m = _URL_RE.search(row.get("source_reference") or "")
        if m:
            url = m.group(0).rstrip(".,;)")
    return {"reference": MODEL_BYE_LAWS_REFERENCE, "url": url or MODEL_BYE_LAWS_DEFAULT_URL}


def _validate_bye_law_save(society_id: int, clause_id: str, layer: int, choice: str, variation_text: str | None) -> str | None:
    """Validate a society_bye_laws choice. Returns an error message or None."""
    if layer not in BYE_LAW_LAYERS:
        return f"Layer must be one of {BYE_LAW_LAYERS}."
    if choice not in ADOPTION_CHOICES:
        return f"Choice must be one of {ADOPTION_CHOICES}."
    if clause_id not in {c[0] for c in MODEL_BYE_LAW_CLAUSES}:
        return f"Unknown clause {clause_id}."
    if clause_id == "BL_55" and choice == "adopted_with_variation":
        return "BL_55 says the Act prevails over the bye-laws; it cannot be varied. Adopt it as-is."
    if choice == "adopted_with_variation" and not (variation_text or "").strip():
        return "Variation text is required when a clause is adopted with a variation."
    if choice != "adopted_with_variation" and variation_text:
        return "Variation text can only be set when a clause is adopted with a variation."
    if choice == "not_adopted":
        if layer != 1:
            return "Only a Model Bye-Law (Layer 1) clause can be recorded as not adopted."
        if clause_is_locked(society_id, clause_id):
            return f"{clause_id} is backed by the Act/Rules and the engine enforces it; it cannot be 'not adopted'."
    if layer in (2, 3) and choice != "adopted_with_variation":
        return "A society policy / board decision is a variation of an adopted clause; choose 'adopted with variation'."
    return None


def _check_resolution(society_id: int, clause_id: str, layer: int, resolution_id: int) -> tuple[dict | None, str | None]:
    """A resolution can activate a choice only if it is this society's, passed, for this clause, of the right type
    and (for GBM-bodied types) taken at a quorate GBM/EGM. Returns (resolution_row, error)."""
    res = _row("""SELECT r.id, r.clause_id, r.passed, r.majority_required, dt.code AS dt_code, dt.required_body,
                         dt.majority_pct, m.type AS meeting_type, m.quorum_met
                    FROM resolutions r
                    JOIN decision_types dt ON dt.id = r.decision_type_id
                    JOIN meetings m ON m.id = r.meeting_id
                   WHERE r.id = %(res)s AND m.society_id = %(s)s""", {"res": resolution_id, "s": society_id})
    if not res:
        return None, "Resolution not found for this society."
    if not res["passed"]:
        return None, "Resolution has not been passed."
    if res["clause_id"] != clause_id:
        return None, f"Resolution clause ({res['clause_id']}) does not match bye-law clause ({clause_id})."
    allowed = {1: ("ADOPT_BYE_LAW", "VARY_BYE_LAW", "REJECT_BYE_LAW"),
               2: ("SET_SOCIETY_POLICY",), 3: ("SET_BOARD_PARAM",)}[layer]
    if res["dt_code"] not in allowed:
        return None, f"Layer {layer} needs a resolution of type {' / '.join(allowed)}, not {res['dt_code']}."
    if not res["quorum_met"]:
        return None, "The meeting that passed this resolution did not record a quorum."
    if res["required_body"] == "GBM" and res["meeting_type"] not in ("GBM", "EGM"):
        return None, "This decision type needs a General Body meeting (GBM/EGM)."
    return res, None


def save_bye_law_version(actor_id, actor_role, society_id: int, clause_id: str, layer: int, choice: str,
                        variation_text: str | None, effective_from, reason: str, resolution_id: int | None = None,
                        actor_society_id=None) -> tuple[bool, str]:
    """Record a society's choice for a bye-law clause. Returns (ok, message).

    With no resolution the row is stored as 'provisional' (remembering the intended outcome in proposed_status)
    and changes nothing in the engine; with a valid passed resolution it is stored active. Admin of that society
    only. Normally the admin saves it as provisional and it is activated automatically when a matching passed
    resolution is recorded (see create_resolution / _auto_activate)."""
    _require_writer(actor_role, actor_society_id, society_id, master_ok=False)
    err = _validate_bye_law_save(society_id, clause_id, layer, choice, variation_text)
    if err:
        return False, err
    start = _d(effective_from)
    if not start:
        return False, "Choose the date the new value takes effect."
    if start < date.today():
        return False, "A bye-law change cannot be back-dated."
    why = _text(reason, MIN_TEXT)
    if not why:
        return False, f"Say why the bye-law is changing (at least {MIN_TEXT} characters)."
    if resolution_id:
        _, rerr = _check_resolution(society_id, clause_id, layer, resolution_id)
        if rerr:
            return False, rerr
        status, proposed = choice, None
    else:
        status, proposed = "provisional", choice

    latest = _row("""SELECT status, proposed_status, variation_text, effective_from FROM society_bye_laws
                      WHERE society_id = %(s)s AND clause_id = %(c)s AND layer = %(l)s
                      ORDER BY effective_from DESC LIMIT 1""",
                  {"s": society_id, "c": clause_id, "l": layer})
    if latest and start <= latest["effective_from"]:
        return False, (f"The new version must start after the latest existing one "
                       f"({latest['effective_from']:%d %b %Y}).")
    if latest and (latest["status"], latest["proposed_status"], latest["variation_text"]) == (status, proposed, variation_text):
        return False, "That is already the value in force; nothing to change."

    row = _row(
        """WITH closed AS (
               UPDATE society_bye_laws SET effective_to = CAST(%(start)s AS date) - 1
               WHERE society_id = %(s)s AND clause_id = %(c)s AND layer = %(l)s
                 AND effective_from < %(start)s AND (effective_to IS NULL OR effective_to >= %(start)s)
               RETURNING effective_from
           ), ins AS (
               INSERT INTO society_bye_laws
                      (society_id, clause_id, layer, status, proposed_status, variation_text, resolution_id, effective_from, created_by)
               SELECT %(s)s, %(c)s, %(l)s, %(st)s, %(pr)s, %(vt)s, %(res)s, %(start)s, %(uid)s
               RETURNING society_id, clause_id, layer, status, proposed_status, variation_text, resolution_id, effective_from
           )
           INSERT INTO regime_rule_audit
                  (target_table, society_id, rule_key, action, old_value, new_value, reason, changed_by, changed_by_role)
           SELECT 'society_bye_laws', ins.society_id, ins.clause_id, 'new_version',
                  (SELECT to_jsonb(closed) FROM closed), to_jsonb(ins), %(why)s, %(uid)s, %(role)s
           FROM ins RETURNING id""",
        {"s": society_id, "c": clause_id, "l": layer, "st": status, "pr": proposed, "vt": variation_text,
         "res": resolution_id, "start": start, "why": why, "uid": actor_id, "role": actor_role})
    if not row:
        return False, "Nothing was saved."
    state = "provisional until you record the passed resolution" if status == "provisional" else "active"
    return True, f"Bye-law {clause_id} (layer {layer}) saved from {start:%d %b %Y} — {state}."


def record_wizard_adoption(actor_id, actor_role, actor_society_id, society_id: int, clause_id: str,
                           choice: str, variation_text: str | None) -> tuple[bool, str]:
    """Setup Wizard: a society admin records which Model Bye-Law clauses the society intends to adopt.

    Always provisional, always Layer 1, effective immediately but inert in the engine until a passed GBM
    resolution is recorded (Settings -> Society governance -> Meetings & Resolutions). An admin can only write their own society, and can only re-choose a clause
    that has no active (resolution-backed) row."""
    _require_writer(actor_role, actor_society_id, society_id, master_ok=False)
    err = _validate_bye_law_save(society_id, clause_id, 1, choice, (variation_text or "").strip() or None)
    if err:
        return False, err
    vt = (variation_text or "").strip() or None
    active = _row("""SELECT 1 AS x FROM society_bye_laws WHERE society_id = %s AND clause_id = %s AND layer = 1
                      AND status <> 'provisional' AND resolution_id IS NOT NULL
                      AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)""", (society_id, clause_id))
    if active:
        return False, (f"{clause_id} is already backed by a resolution; to change it, use Settings → Society governance → "
                       f"Society By-laws (save a new choice, then record the resolution).")
    why = "Recorded in the Setup Wizard; awaiting GBM resolution"
    row = _row(
        """WITH upd AS (
               UPDATE society_bye_laws SET proposed_status = %(pr)s, variation_text = %(vt)s, updated_at = NOW()
                WHERE society_id = %(s)s AND clause_id = %(c)s AND layer = 1 AND status = 'provisional'
               RETURNING id
           ), ins AS (
               INSERT INTO society_bye_laws (society_id, clause_id, layer, status, proposed_status, variation_text, created_by)
               SELECT %(s)s, %(c)s, 1, 'provisional', %(pr)s, %(vt)s, %(uid)s
                WHERE NOT EXISTS (SELECT 1 FROM upd)
               RETURNING id
           )
           INSERT INTO regime_rule_audit
                  (target_table, society_id, rule_key, action, old_value, new_value, reason, changed_by, changed_by_role)
           SELECT 'society_bye_laws', %(s)s, %(c)s, 'set', NULL,
                  jsonb_build_object('proposed_status', CAST(%(pr)s AS text), 'variation_text', CAST(%(vt)s AS text)), %(why)s, %(uid)s, %(role)s
           RETURNING id""",
        {"s": society_id, "c": clause_id, "pr": choice, "vt": vt, "uid": actor_id, "why": why, "role": actor_role})
    return (True, f"{clause_id} noted as provisional ({choice.replace('_', ' ')}).") if row else (False, "Nothing was saved.")


def list_society_policies(society_id: int) -> dict[str, dict]:
    """policy_key -> {value, active, proposed}: value is what the engine uses now, proposed is a pending choice."""
    out = {k: {"value": policy_default(k), "active": False, "proposed": None} for k in POLICY_SPECS}
    rows = _rows("""SELECT policy_key, value_text, resolution_id FROM society_policy_settings
                     WHERE society_id = %s AND effective_from <= CURRENT_DATE
                     ORDER BY effective_from DESC, id DESC""", (int(society_id),))
    seen_active, seen_prov = set(), set()
    for r in rows:
        k = r["policy_key"]
        if k not in out:
            continue
        if r["resolution_id"] and k not in seen_active:
            out[k]["value"], out[k]["active"] = r["value_text"], True
            seen_active.add(k)
        elif not r["resolution_id"] and k not in seen_prov and k not in seen_active:
            out[k]["proposed"] = r["value_text"]
            seen_prov.add(k)
    return out


def record_wizard_policy(actor_id, actor_role, actor_society_id, society_id: int,
                         policy_key: str, value: str, source: str = "Setup Wizard") -> tuple[bool, str]:
    """Record a society-resolution policy choice (Setup Wizard, or Settings -> Society governance -> Society
    By-laws). Always provisional - inert in the engine until a passed resolution is recorded for the clause
    (activated automatically). Admin of that society only."""
    _require_writer(actor_role, actor_society_id, society_id, master_ok=False)
    spec = POLICY_SPECS.get(policy_key)
    if not spec:
        return False, f"Unknown policy {policy_key}."
    if value not in {v for v, _ in spec[2]}:
        return False, f"Choose one of: {', '.join(v for v, _ in spec[2])}."
    row = _row(
        """WITH upd AS (
               UPDATE society_policy_settings SET value_text = %(v)s, updated_at = NOW()
                WHERE society_id = %(s)s AND policy_key = %(k)s AND resolution_id IS NULL
               RETURNING id
           ), ins AS (
               INSERT INTO society_policy_settings (society_id, policy_key, value_text, created_by)
               SELECT %(s)s, %(k)s, %(v)s, %(uid)s WHERE NOT EXISTS (SELECT 1 FROM upd)
               RETURNING id
           )
           INSERT INTO regime_rule_audit (target_table, society_id, rule_key, action, old_value, new_value,
                                          reason, changed_by, changed_by_role)
           SELECT 'society_policy_settings', %(s)s, %(k)s, 'set', NULL,
                  jsonb_build_object('proposed', CAST(%(v)s AS text)),
                  %(why)s, %(uid)s, %(role)s
           RETURNING id""",
        {"s": int(society_id), "k": policy_key, "v": value, "uid": actor_id, "role": actor_role,
         "why": f"Recorded in the {source}; awaiting resolution"})
    return (True, "Noted as provisional until you record the passed resolution.") if row else (False, "Nothing was saved.")


def _pending_policies(society_id: int, clause_id: str) -> list[str]:
    """Policy keys of this society that belong to `clause_id` and still have a provisional (unresolved) choice."""
    rows = _rows("SELECT policy_key FROM society_policy_settings WHERE society_id = %s AND resolution_id IS NULL",
                 (int(society_id),))
    return [r["policy_key"] for r in rows if POLICY_SPECS.get(r["policy_key"], (None, None))[1] == clause_id]


def _activate_policy(actor_id, actor_role, society_id: int, policy_key: str, resolution_id: int,
                     why: str) -> tuple[bool, str]:
    """Make the society's provisional policy choice active, backed by a passed Layer-2 resolution."""
    row = _row(
        """WITH upd AS (
               UPDATE society_policy_settings SET resolution_id = %(r)s, effective_from = GREATEST(effective_from, CURRENT_DATE),
                      updated_at = NOW()
                WHERE society_id = %(s)s AND policy_key = %(k)s AND resolution_id IS NULL
               RETURNING id, value_text
           )
           INSERT INTO regime_rule_audit (target_table, society_id, rule_key, action, old_value, new_value,
                                          reason, changed_by, changed_by_role)
           SELECT 'society_policy_settings', %(s)s, %(k)s, 'confirm_provisional', NULL,
                  jsonb_build_object('value', upd.value_text, 'resolution_id', %(r)s),
                  %(why)s, %(uid)s, %(role)s
             FROM upd RETURNING id""",
        {"s": int(society_id), "k": policy_key, "r": int(resolution_id), "uid": actor_id, "role": actor_role, "why": why})
    label = POLICY_SPECS[policy_key][0]
    return ((True, f"Policy '{label}' is now active via resolution #{resolution_id}.") if row
            else (False, "No provisional choice to activate."))


def link_policy_resolution(actor_id, actor_role, society_id: int, policy_key: str, resolution_id: int,
                           actor_society_id=None) -> tuple[bool, str]:
    """Manually link a provisional policy choice to a passed Layer-2 resolution (service-level; the UI relies on
    automatic activation when the resolution is recorded). Admin of that society only."""
    _require_writer(actor_role, actor_society_id, society_id, master_ok=False)
    spec = POLICY_SPECS.get(policy_key)
    if not spec:
        return False, f"Unknown policy {policy_key}."
    _, rerr = _check_resolution(int(society_id), spec[1], 2, int(resolution_id))
    if rerr:
        return False, rerr
    return _activate_policy(actor_id, actor_role, society_id, policy_key, resolution_id, "Linked to passed resolution")


def list_society_bye_laws(society_id: int, on: date | None = None) -> list[dict]:
    """List all bye-law clauses for a society, with effective version on `on` (default today)."""
    on = on or date.today()
    # Build the VALUES clause for clause titles (avoid % conflicts with psycopg2)
    values_clause = ",".join([f"('{c[0]}', '{c[1].replace(chr(39), chr(39)+chr(39))}')" for c in MODEL_BYE_LAW_CLAUSES])
    return _rows(
        f"""SELECT sbl.clause_id, sbl.layer, sbl.status, sbl.proposed_status, sbl.variation_text, sbl.effective_from, sbl.effective_to,
                  sbl.resolution_id, m.title as clause_title
           FROM society_bye_laws sbl
           LEFT JOIN (VALUES {values_clause}) AS m(clause_id, title) ON m.clause_id = sbl.clause_id
           WHERE sbl.society_id = %(s)s
             AND sbl.effective_from <= %(d)s AND (sbl.effective_to IS NULL OR sbl.effective_to >= %(d)s)
           ORDER BY sbl.clause_id, sbl.layer, sbl.effective_from DESC""",
        {"s": society_id, "d": on})


def list_society_bye_laws_all_versions(society_id: int, clause_id: str | None = None, layer: int | None = None) -> list[dict]:
    """Full history of bye-law versions for a society."""
    params = {"s": society_id}
    where = "WHERE sbl.society_id = %(s)s"
    if clause_id:
        where += " AND sbl.clause_id = %(c)s"
        params["c"] = clause_id
    if layer:
        where += " AND sbl.layer = %(l)s"
        params["l"] = layer
    return _rows(
        f"""SELECT sbl.clause_id, sbl.layer, sbl.status, sbl.variation_text, sbl.effective_from, sbl.effective_to,
                  sbl.resolution_id, sbl.created_at, sbl.created_by
           FROM society_bye_laws sbl
           {where}
           ORDER BY sbl.clause_id, sbl.layer, sbl.effective_from DESC""",
        params)


def _activate_provisional(actor_id, actor_role, society_id: int, prov: dict, clause_id: str, layer: int,
                          resolution_id: int, why: str) -> tuple[bool, str]:
    """Turn one provisional society_bye_laws row into an active one, backed by `resolution_id`."""
    import json
    new_status = prov.get("proposed_status") or ("adopted_with_variation" if prov.get("variation_text") else "adopted_as_is")
    row = _row(
        """UPDATE society_bye_laws
              SET status = %(st)s, proposed_status = NULL, resolution_id = %(res)s, updated_at = NOW()
            WHERE id = %(id)s RETURNING *""",
        {"st": new_status, "res": resolution_id, "id": prov["id"]})
    if not row:
        return False, "Failed to update provisional choice."

    def _json_safe(d):
        return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in d.items()}
    db._execute(
        """INSERT INTO regime_rule_audit
               (target_table, society_id, rule_key, action, old_value, new_value, reason, changed_by, changed_by_role)
           VALUES ('society_bye_laws', %s, %s, 'confirm_provisional', %s::jsonb, %s::jsonb, %s, %s, %s)""",
        (society_id, clause_id, json.dumps(_json_safe(prov)), json.dumps(_json_safe(dict(row))), why, actor_id, actor_role))
    return True, f"{clause_id} (layer {layer}) is now active as {new_status.replace('_', ' ')} via resolution #{resolution_id}."


def _latest_provisional(society_id: int, clause_id: str, layer: int) -> dict | None:
    return _row("""SELECT * FROM society_bye_laws
                   WHERE society_id = %(s)s AND clause_id = %(c)s AND layer = %(l)s AND status = 'provisional'
                   ORDER BY effective_from DESC LIMIT 1""", {"s": society_id, "c": clause_id, "l": layer})


# Which stored choices each Layer-1 decision type can confirm.
_LAYER1_DECISION_CHOICES = {
    "ADOPT_BYE_LAW": ("adopted_as_is", "adopted_with_variation"),
    "VARY_BYE_LAW": ("adopted_with_variation",),
    "REJECT_BYE_LAW": ("not_adopted",),
}


def _auto_activate(actor_id, actor_role, society_id: int, resolution_id: int) -> list[str]:
    """After a PASSED resolution naming a clause is recorded: activate the society's provisional choice for that
    clause when the resolution is valid for it (_check_resolution: passed, same clause, right decision type for
    the layer, quorum, right body) AND its decision type fits the choice (adopt/vary/reject). A resolution backs
    at most one choice, so an old resolution can never confirm a newer choice. Returns user-facing notes."""
    res = _row("""SELECT r.clause_id, dt.code AS dt_code FROM resolutions r
                  JOIN decision_types dt ON dt.id = r.decision_type_id WHERE r.id = %s""", (resolution_id,))
    if not res or not res["clause_id"]:
        return []
    if _row("""SELECT 1 AS x FROM society_bye_laws WHERE resolution_id = %s
               UNION ALL SELECT 1 FROM society_policy_settings WHERE resolution_id = %s LIMIT 1""",
            (resolution_id, resolution_id)):
        return []
    clause = res["clause_id"]
    notes: list[str] = []
    for layer in BYE_LAW_LAYERS:
        prov = _latest_provisional(society_id, clause, layer)
        if not prov:
            continue
        _, err = _check_resolution(society_id, clause, layer, resolution_id)
        if err:
            continue      # this resolution is not the right kind for this layer
        want = prov.get("proposed_status") or ("adopted_with_variation" if prov.get("variation_text") else "adopted_as_is")
        if layer == 1 and want not in _LAYER1_DECISION_CHOICES.get(res["dt_code"], ()):
            notes.append(f"{clause} stays provisional: a {res['dt_code']} resolution cannot confirm "
                         f"'{want.replace('_', ' ')}'.")
            continue
        ok, msg = _activate_provisional(actor_id, actor_role, society_id, prov, clause, layer, resolution_id,
                                        f"Activated automatically by passed resolution #{resolution_id}")
        notes.append(msg if ok else f"{clause}: {msg}")

    # Society policy choices (Setup Wizard) on this clause are Layer-2 decisions. One valid resolution on the
    # clause confirms every pending policy choice of that clause (e.g. both BL_08 voting settings).
    pending = _pending_policies(society_id, clause)
    if pending:
        _, err = _check_resolution(society_id, clause, 2, resolution_id)
        if not err:
            for key in pending:
                ok, msg = _activate_policy(actor_id, actor_role, society_id, key, resolution_id,
                                           f"Activated automatically by passed resolution #{resolution_id}")
                notes.append(msg if ok else f"{key}: {msg}")
    return notes


def link_provisional_to_resolution(actor_id, actor_role, society_id: int, clause_id: str, layer: int,
                                   resolution_id: int, reason: str, actor_society_id=None) -> tuple[bool, str]:
    """Manually link a provisional choice to a passed resolution (service-level; the UI no longer offers this
    because recording the resolution activates the choice automatically)."""
    _require_writer(actor_role, actor_society_id, society_id, master_ok=False)
    why = _text(reason, MIN_TEXT)
    if not why:
        return False, f"Say why the choice is being confirmed (at least {MIN_TEXT} characters)."
    _, rerr = _check_resolution(society_id, clause_id, layer, resolution_id)
    if rerr:
        return False, rerr
    prov = _latest_provisional(society_id, clause_id, layer)
    if not prov:
        return False, "No provisional choice found for this clause/layer."
    return _activate_provisional(actor_id, actor_role, society_id, prov, clause_id, layer, resolution_id, why)


# ═════════════════════════════════════════════════════════════════════════════════
# Phase 5: Meetings & Resolutions
# ═════════════════════════════════════════════════════════════════════════════════

def list_meetings(society_id: int) -> list[dict]:
    """List all meetings for a society."""
    return _rows("""SELECT m.*, u.email as created_by_email
                    FROM meetings m
                    LEFT JOIN users u ON u.id = m.created_by
                    WHERE m.society_id = %(s)s
                    ORDER BY m.held_on DESC, m.created_at DESC""",
                 {"s": society_id})


def create_meeting(actor_id, actor_role, society_id: int, type: str, held_on, quorum_met: bool,
                  minutes_pdf: str | None, reason: str, actor_society_id=None) -> tuple[bool, str]:
    """Create a new meeting record (admin of that society only)."""
    _require_writer(actor_role, actor_society_id, society_id, master_ok=False)
    why = _text(reason, MIN_TEXT)
    if not why:
        return False, f"Say why the meeting is being recorded (at least {MIN_TEXT} characters)."
    if type not in ("GBM", "EGM", "MC"):
        return False, "Meeting type must be GBM, EGM, or MC."
    held = _d(held_on)
    if not held:
        return False, "Meeting date is required."
    if held > date.today():
        return False, "Meeting date cannot be in the future."
    
    row = _row(
        """WITH ins AS (
               INSERT INTO meetings (society_id, type, held_on, quorum_met, minutes_pdf, created_by)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING id
           )
           INSERT INTO regime_rule_audit
                  (target_table, society_id, rule_key, action, old_value, new_value, reason, changed_by, changed_by_role)
           SELECT 'meetings', %s, 'meeting#' || ins.id, 'new_version',
                  '{}'::jsonb, to_jsonb(ins), %s, %s, %s
           FROM ins RETURNING rule_key""",
        (society_id, type, held, quorum_met, minutes_pdf, actor_id, society_id, why, actor_id, actor_role))
    if not row:
        return False, "Failed to create meeting."
    return True, f"Meeting #{row['rule_key'].split('#')[1]} ({type}) recorded for {held:%d %b %Y}."


def list_resolutions(society_id: int) -> list[dict]:
    """List all resolutions for a society with decision type info."""
    return _rows("""SELECT r.*, dt.code as decision_type_code, dt.label as decision_type_label,
                          m.type as meeting_type, m.held_on as meeting_date
                    FROM resolutions r
                    JOIN decision_types dt ON dt.id = r.decision_type_id
                    JOIN meetings m ON m.id = r.meeting_id
                    WHERE m.society_id = %(s)s
                    ORDER BY r.created_at DESC""",
                 {"s": society_id})


def list_decision_types() -> list[dict]:
    """List all decision types."""
    return _rows("""SELECT id, code, label, required_body, majority_pct, description
                    FROM decision_types
                    ORDER BY code""")


def create_resolution(actor_id, actor_role, society_id: int, meeting_id: int, decision_type_id: int,
                      clause_id: str | None, body: str, majority_required: float,
                      passed: bool, passed_on, reason: str, actor_society_id=None) -> tuple[bool, str]:
    """Create a new resolution record (admin of that society only). If it is passed and names a clause, any
    matching provisional bye-law choice of the society is activated automatically."""
    _require_writer(actor_role, actor_society_id, society_id, master_ok=False)
    why = _text(reason, MIN_TEXT)
    if not why:
        return False, f"Say why the resolution is being recorded (at least {MIN_TEXT} characters)."
    if not body or not body.strip():
        return False, "Resolution body is required."
    
    # Verify meeting exists and belongs to society
    meeting = _row("SELECT id FROM meetings WHERE id = %s AND society_id = %s", (meeting_id, society_id))
    if not meeting:
        return False, "Meeting not found for this society."
    
    # Verify decision type exists
    dt = _row("SELECT id, majority_pct FROM decision_types WHERE id = %s", (decision_type_id,))
    if not dt:
        return False, "Decision type not found."
    
    # A resolution can never be recorded as passed on a smaller majority than its decision type requires
    # (e.g. 2/3 to adopt a bye-law), nor at a meeting that was not quorate, nor at the wrong kind of meeting.
    maj = float(majority_required) if majority_required else float(dt["majority_pct"])
    if maj < float(dt["majority_pct"]):
        return False, f"This decision type needs at least {float(dt['majority_pct']):g}% to pass."
    if passed:
        mt = _row("SELECT type, quorum_met FROM meetings WHERE id = %s", (meeting_id,))
        body_needed = _row("SELECT required_body FROM decision_types WHERE id = %s", (decision_type_id,))["required_body"]
        if not mt["quorum_met"]:
            return False, "A resolution cannot be recorded as passed at a meeting without a quorum."
        if body_needed == "GBM" and mt["type"] not in ("GBM", "EGM"):
            return False, "This decision type needs a General Body meeting (GBM/EGM)."
        if not _d(passed_on):
            return False, "Give the date the resolution was passed."
    
    passed_date = _d(passed_on) if passed else None
    
    row = _row(
        """WITH ins AS (
               INSERT INTO resolutions (meeting_id, clause_id, decision_type_id, body, majority_required, passed, passed_on, created_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id
           )
           INSERT INTO regime_rule_audit
                  (target_table, society_id, rule_key, action, old_value, new_value, reason, changed_by, changed_by_role)
           SELECT 'resolutions', %s, 'resolution#' || ins.id, 'new_version',
                  '{}'::jsonb, to_jsonb(ins), %s, %s, %s
           FROM ins RETURNING rule_key""",
        (meeting_id, clause_id, decision_type_id, body, maj, passed, passed_date, actor_id, society_id, why, actor_id, actor_role))
    if not row:
        return False, "Failed to create resolution."
    new_id = int(row["rule_key"].split("#")[1])
    msg = f"Resolution #{new_id} created."
    if passed and clause_id:
        try:
            notes = _auto_activate(actor_id, actor_role, society_id, new_id)
        except Exception as exc:   # the resolution is saved; activation can be retried by recording again
            notes = [f"Resolution saved, but automatic activation failed: {exc}"]
        if notes:
            msg += " " + " ".join(notes)
    return True, msg


def list_pending_enactments(society_id: int) -> list[dict]:
    """List pending resolution effects for a society."""
    return _rows("""SELECT re.*, r.meeting_id, r.clause_id, dt.code as decision_type_code
                    FROM resolution_effects re
                    JOIN resolutions r ON r.id = re.resolution_id
                    JOIN decision_types dt ON dt.id = r.decision_type_id
                    WHERE r.meeting_id IN (SELECT id FROM meetings WHERE society_id = %(s)s)
                      AND re.status = 'pending'
                    ORDER BY re.created_at""",
                 {"s": society_id})


def execute_enactment(actor_id, actor_role, effect_id: int, actor_society_id=None) -> tuple[bool, str]:
    """Execute a pending resolution effect.

    Admin: only effects of their own society, and only society-scoped handlers (set_society_policy,
    set_board_param). set_regime_param changes the rule for every society on the regime, so only Master may
    apply it; an admin attempt is refused WITHOUT marking the effect failed."""
    if actor_role not in ("admin", "master"):
        raise PermissionError("Admin role required.")

    effect = _row("""SELECT re.*, r.meeting_id, r.clause_id, m.society_id, dt.code as decision_type_code
                     FROM resolution_effects re
                     JOIN resolutions r ON r.id = re.resolution_id
                     JOIN meetings m ON m.id = r.meeting_id
                     JOIN decision_types dt ON dt.id = r.decision_type_id
                     WHERE re.id = %s AND re.status = 'pending'""",
                  (effect_id,))
    if not effect:
        return False, "Pending enactment not found."

    society_id = effect["society_id"]
    if actor_role == "admin":
        _require_writer("admin", actor_society_id, society_id, master_ok=False)
        if effect["handler_name"] == "set_regime_param":
            return False, "A regime-wide rule change can only be applied by Master."
    elif effect["handler_name"] != "set_regime_param":
        raise PermissionError("Society enactments are executed by that society's admin.")
    
    # Execute based on handler
    try:
        if effect["handler_name"] == "set_regime_param":
            import json
            payload = effect["payload_json"] if isinstance(effect["payload_json"], dict) else json.loads(effect["payload_json"])
            # payload: {"rule_key": "...", "value_text": "...", "effective_from": "...", "source_reference": "..."}
            rule_key = payload.get("rule_key")
            value_text = payload.get("value_text")
            effective_from = payload.get("effective_from")
            source_reference = payload.get("source_reference", f"Resolution #{effect['resolution_id']}")
            if not rule_key or not value_text or not effective_from:
                raise ValueError("Missing required payload fields for set_regime_param")
            ok, msg = save_rule_version(actor_id, actor_role, DEFAULT_REGIME, rule_key, value_text, effective_from, source_reference, f"Enacted via resolution #{effect['resolution_id']}", False)
            if not ok:
                raise ValueError(msg)
            
        elif effect["handler_name"] == "set_society_policy":
            import json
            payload = effect["payload_json"] if isinstance(effect["payload_json"], dict) else json.loads(effect["payload_json"])
            # payload: {"society_id": ..., "clause_id": "...", "layer": 2, "status": "adopted_with_variation", "variation_text": "...", "effective_from": "...", "resolution_id": ...}
            clause_id = payload.get("clause_id")
            layer = payload.get("layer", 2)
            status = payload.get("status", "adopted_with_variation")
            variation_text = payload.get("variation_text")
            effective_from = payload.get("effective_from")
            resolution_id = payload.get("resolution_id", effect["resolution_id"])
            if not clause_id or not effective_from:
                raise ValueError("Missing required payload fields for set_society_policy")
            ok, msg = save_bye_law_version(actor_id, actor_role, society_id, clause_id, layer, status, variation_text, effective_from, f"Enacted via resolution #{effect['resolution_id']}", resolution_id,
                                      actor_society_id=actor_society_id)
            if not ok:
                raise ValueError(msg)
            
        elif effect["handler_name"] == "set_board_param":
            import json
            payload = effect["payload_json"] if isinstance(effect["payload_json"], dict) else json.loads(effect["payload_json"])
            # payload: {"society_id": ..., "clause_id": "...", "layer": 3, "status": "adopted_with_variation", "variation_text": "...", "effective_from": "...", "resolution_id": ...}
            clause_id = payload.get("clause_id")
            layer = payload.get("layer", 3)
            status = payload.get("status", "adopted_with_variation")
            variation_text = payload.get("variation_text")
            effective_from = payload.get("effective_from")
            resolution_id = payload.get("resolution_id", effect["resolution_id"])
            if not clause_id or not effective_from:
                raise ValueError("Missing required payload fields for set_board_param")
            ok, msg = save_bye_law_version(actor_id, actor_role, society_id, clause_id, layer, status, variation_text, effective_from, f"Enacted via resolution #{effect['resolution_id']}", resolution_id,
                                      actor_society_id=actor_society_id)
            if not ok:
                raise ValueError(msg)
        
        else:
            raise ValueError(f"Unknown handler: {effect['handler_name']}")
        
        # Mark as executed
        db._execute("""UPDATE resolution_effects SET status = 'executed', executed_at = NOW() WHERE id = %s""", (effect_id,))
        return True, f"Enactment #{effect_id} executed successfully."
    except Exception as e:
        db._execute("""UPDATE resolution_effects SET status = 'failed', error_message = %s WHERE id = %s""", (str(e), effect_id))
        return False, f"Execution failed: {e}"
