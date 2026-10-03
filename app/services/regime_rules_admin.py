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


def recent_audit(limit: int = 25) -> list[dict]:
    return _rows(
        """SELECT a.changed_at, a.target_table, a.regime_code, a.society_id, a.rule_key, a.action,
                  a.old_value, a.new_value, a.reason, a.changed_by, a.changed_by_role
           FROM regime_rule_audit a ORDER BY a.id DESC LIMIT %(n)s""", {"n": int(limit)})


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


def set_cash_limit_mode(actor_id, actor_role, society_id, mode, reason) -> tuple[bool, str]:
    """mode: 'warn' | 'block' | '' (clear -> regime default)."""
    _require_master(actor_role)
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
                  to_jsonb(b), to_jsonb(upd), %(why)s, %(uid)s, 'master'
           FROM upd JOIN before_row b ON b.id = upd.id RETURNING id""",
        {"sid": sid, "m": mode, "why": why, "uid": actor_id})
    if not row:
        return False, "Society not found."
    return True, f"Cash-limit mode set to {mode or 'regime default'}."
