"""Legal-amendment helper for the master's "Edit a catalog entry" form.

An Act, rule or notification changes (for example the GST exemption of Rs 7,500 per member per month becomes
Rs 10,000). The catalog entry records WHAT the law now says; the figures the engine actually uses live
elsewhere: dated rows in ``state_compliance_thresholds`` or ``regime_rule_parameters``, fallbacks hard-coded in
SQL functions, and text in the application. This module

* finds where a figure is used (``find_usages``),
* writes the prompt the master gives Claude to produce the SQL (``build_prompt``),
* runs the SQL Claude returns, first in a transaction that is rolled back (``dry_run_sql``) and then for real
  (``apply_sql``), with the same guard rails as the KPI Inspector.

Nothing here decides what the law says; the master and an advocate do.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from app.services.regime_rules_admin import is_protected_rule_sql

_ROOT = Path(__file__).resolve().parent.parent.parent
_SCAN_DIRS = ("app", "database")
_SCAN_SUFFIXES = (".py", ".sql")
_MAX_ROWS = 25
_MAX_SQL = 60_000
# Files that would only ever match because they are this feature itself or demo-statement generators.
_SKIP_FILES = {"app/services/amendment_prompt.py", "app/dash_apps/pages/master_rules_page.py",
               "database/make_sbi_statement.py"}

# The pasted SQL is wrapped in the app's own transaction, so it must not end or start one itself.
_TXN_RE = re.compile(r"(?im)^\s*(COMMIT|ROLLBACK|START\s+TRANSACTION|SAVEPOINT|RELEASE)\b")
_DESTRUCTIVE_RE = re.compile(r"(?i)\b(DROP\s+(TABLE|SCHEMA|DATABASE|VIEW|INDEX)|TRUNCATE|DELETE\s+FROM)\b")


# ── finding where a figure is used ────────────────────────────────────────────
def figure_patterns(figure: str) -> list[str]:
    """'7500' -> ['7500', '7,500', '7_500']; non-numbers are used as typed."""
    f = (figure or "").strip().replace(",", "").replace("_", "")
    if not f:
        return []
    out = [f]
    if re.fullmatch(r"\d{4,}", f):
        out += [f"{int(f):,}", f"{f[:-3]}_{f[-3:]}"]
    return out


def _regex_for(patterns: list[str]) -> str:
    # not preceded/followed by a digit, so 7500 does not match 17500 or 75000
    return r"(?<![0-9])(?:" + "|".join(re.escape(p) for p in patterns) + r")(?![0-9])"


def find_usages(db, figure: str) -> dict:
    """Where `figure` appears: dated threshold rows, rule parameters, SQL functions, source files."""
    pats = figure_patterns(figure)
    out = {"figure": (figure or "").strip(), "thresholds": [], "rules": [], "functions": [], "files": []}
    if not pats:
        return out
    rx = _regex_for(pats)
    num = None
    try:
        num = float(pats[0])
    except ValueError:
        pass
    if num is not None:
        out["thresholds"] = db._execute(
            """SELECT state, threshold_key, value, unit, effective_from, effective_to, is_active
                 FROM state_compliance_thresholds WHERE value = %s ORDER BY threshold_key, state, effective_from""",
            (num,), fetch_all=True) or []
        out["rules"] = db._execute(
            """SELECT regime_code, rule_key, value, unit, effective_from, effective_to
                 FROM regime_rule_parameters WHERE value = %s ORDER BY rule_key, effective_from""",
            (num,), fetch_all=True) or []
    funcs = db._execute(
        """SELECT p.proname, p.prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public' AND p.prosrc ~ %s ORDER BY p.proname""",
        (rx,), fetch_all=True) or []
    for f in funcs[:_MAX_ROWS]:
        lines = [(i, ln.strip()) for i, ln in enumerate(f["prosrc"].splitlines(), 1) if re.search(rx, ln)]
        out["functions"].append({"name": f["proname"],
                                 "lines": [{"line": i, "text": t[:160]} for i, t in lines[:3]]})
    out["files"] = _scan_files(rx)
    return out


def _scan_files(rx: str) -> list[dict]:
    hits: list[dict] = []
    pat = re.compile(rx)
    for d in _SCAN_DIRS:
        base = _ROOT / d
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if (path.suffix not in _SCAN_SUFFIXES or "__pycache__" in path.parts
                    or "migrations" in path.parts or not path.is_file()
                    or str(path.relative_to(_ROOT)) in _SKIP_FILES):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for i, ln in enumerate(text.splitlines(), 1):
                if pat.search(ln):
                    hits.append({"file": str(path.relative_to(_ROOT)), "line": i, "text": ln.strip()[:160]})
                    if len(hits) >= _MAX_ROWS:
                        return hits
    return hits


# ── the prompt ────────────────────────────────────────────────────────────────
def _md_cell(v) -> str:
    return "" if v is None else str(v).replace("|", "/").replace("\n", " ")


def _usages_markdown(u: dict | None) -> str:
    if not u or not u.get("figure"):
        return ("_The Master did not give a figure to search for. Work out from section 1 which figure, "
                "rate or limit the amendment changes and say what you inferred._\n")
    parts = [f"Search for **{u['figure']}** in this database and codebase found:\n"]
    t = u.get("thresholds") or []
    parts.append("**`state_compliance_thresholds` rows with that value**\n")
    if t:
        parts.append("| state | threshold_key | value | unit | effective_from | effective_to | active |\n|---|---|---|---|---|---|---|")
        parts += [f"| {_md_cell(r['state'])} | {_md_cell(r['threshold_key'])} | {_md_cell(r['value'])} | {_md_cell(r['unit'])} "
                  f"| {_md_cell(r['effective_from'])} | {_md_cell(r['effective_to'])} | {_md_cell(r['is_active'])} |" for r in t]
    else:
        parts.append("_none_")
    parts.append("\n**`regime_rule_parameters` rows with that value** (protected: see rule 3)\n")
    r_ = u.get("rules") or []
    if r_:
        parts.append("| regime | rule_key | value | unit | effective_from | effective_to |\n|---|---|---|---|---|---|")
        parts += [f"| {_md_cell(r['regime_code'])} | {_md_cell(r['rule_key'])} | {_md_cell(r['value'])} | {_md_cell(r['unit'])} "
                  f"| {_md_cell(r['effective_from'])} | {_md_cell(r['effective_to'])} |" for r in r_]
    else:
        parts.append("_none_")
    parts.append("\n**SQL functions whose source contains it** (hard-coded; need CREATE OR REPLACE FUNCTION)\n")
    f_ = u.get("functions") or []
    if f_:
        for f in f_:
            parts.append(f"- `{f['name']}`: " + "; ".join(f"line {x['line']}: `{x['text']}`" for x in f["lines"]))
    else:
        parts.append("_none_")
    parts.append("\n**Application source / schema files** (display text or fallbacks; edit in the repository, not by SQL)\n")
    fl = u.get("files") or []
    parts += [f"- `{x['file']}:{x['line']}`  `{x['text']}`" for x in fl] if fl else ["_none_"]
    return "\n".join(parts) + "\n"


def build_prompt(entry: dict, change: dict, usages: dict | None) -> str:
    """The text the master pastes into Claude. `entry` is the saved catalog form, `change` the figure."""
    def g(k, default="(not filled in)"):
        v = (entry.get(k) or "")
        v = str(v).strip()
        return v if v else default

    old, new = (change.get("old") or "").strip(), (change.get("new") or "").strip()
    eff = (change.get("effective") or "").strip()
    if old and new:
        what = f"The figure **{old}** becomes **{new}**" + (f", effective **{eff}**." if eff else
                                                          " (the effective date was not given: ask me for it).")
    else:
        what = ("The Master has not stated the old and new figure. Infer them from section 1, say exactly what you "
                "inferred, and ask if anything is unclear.")
    ex_old, ex_new = old or "OLD", new or "NEW"
    ex_eff = eff or "YYYY-MM-DD"
    return f"""# Task: write the SQL that applies a legal amendment to the EstateHub database

You are helping the Master of EstateHub, a multi-tenant housing-society platform (Flask + Dash, PostgreSQL 16).
Statutory figures are held as dated database rows and, in a few places, hard-coded in SQL functions. The catalog
entry below records an amendment. Write the SQL that makes the engine use the amended figure from the date it
takes effect, and nothing else. I am not relying on you for what the law says; I will confirm it with an advocate.

## 1. The amendment (the catalog entry as saved)
- Instrument: {g('title')}  (catalog id {g('id')}, type {g('instrument_type')}, regime {g('regime')})
- Status: {g('status')}
- Last verified: {g('last_verified')}
- Applicability: {g('applicability')}
- Key provisions: {g('provisions')}
- Source: {g('source')}
- Reason for the change: {g('reason')}

## 2. What changes
{what}

## 3. Where that figure lives today
{_usages_markdown(usages)}
## 4. Rules for the SQL
1. PostgreSQL 16, one script, idempotent (safe to run twice). The app runs it inside its own transaction: do not
   write BEGIN, COMMIT, ROLLBACK or SAVEPOINT (a `DO $$ ... BEGIN ... END $$` block is fine).
2. Never overwrite history. Close the row in force (`effective_to` = new effective date minus one day) and add a new
   row with the new value, using `INSERT ... ON CONFLICT` on the table's unique key. For
   `state_compliance_thresholds` the unique key is `(state, threshold_key, effective_from)` and the columns are
   `state, threshold_key, value, value_text, unit, effective_from, effective_to, notes, is_active`. Put the
   notification number and the date in `notes`.
3. Do NOT write to these protected tables: `regime_rule_parameters`, `legal_instrument_catalog`,
   `legal_regime_profiles`, `society_legal_regime`, `regime_rule_audit`, `rule_parameter_defs`,
   `society_rule_decisions`. Those change only through Master → AOA Rule Editor, which validates, dates and audits
   them. If the figure is held there, do not write SQL for it: tell me the rule key and the exact value to enter.
4. If a function has the figure hard-coded (section 3), do not rewrite it from memory. Ask me to run
   `SELECT pg_get_functiondef('fn_name'::regproc);` and paste the result, then return a complete
   `CREATE OR REPLACE FUNCTION` that changes only that figure.
5. No `DROP`, `TRUNCATE` or `DELETE FROM`.
6. Where a society's own copy or a cached value would still show the old figure, say so.

## 5. Pattern to follow (threshold rows)
```sql
UPDATE state_compliance_thresholds
   SET effective_to = DATE '{ex_eff}' - 1, updated_at = NOW()
 WHERE threshold_key = '<key>' AND state = '<state>' AND is_active
   AND effective_to IS NULL AND effective_from < DATE '{ex_eff}';

INSERT INTO state_compliance_thresholds
       (state, threshold_key, value, unit, effective_from, notes, is_active)
VALUES ('<state>', '<key>', {ex_new}, '<unit>', DATE '{ex_eff}', '<notification no.>; was {ex_old}', TRUE)
ON CONFLICT (state, threshold_key, effective_from)
DO UPDATE SET value = EXCLUDED.value, notes = EXCLUDED.notes, is_active = TRUE, updated_at = NOW();
```

## 6. Reply in exactly this order
1. **Which variable or function must change**, one line each, and whether it is SQL (I can integrate it) or code
   (needs a repository change, with file and line).
2. **The SQL script**, in one code block.
3. **A verification query** that returns the row(s) now in force on the effective date.
4. **A rollback script** that restores the previous state.
5. **Follow-ups that are not SQL** (labels and text that still show the old figure).

I will paste the script into the amendment panel: Test SQL runs it and rolls it back, Export .sql saves it,
Integrate to DB applies it.
"""


# ── running the SQL ───────────────────────────────────────────────────────────
def sql_digest(sql: str) -> str:
    return hashlib.sha256((sql or "").strip().encode("utf-8")).hexdigest()


def check_sql(sql: str, *, confirmed_destructive: bool = False) -> str | None:
    """Reason the SQL must not run, else None."""
    s = (sql or "").strip()
    if not s:
        return "Paste the SQL Claude returned first."
    if len(s) > _MAX_SQL:
        return "That script is too long to run from this box."
    if _TXN_RE.search(s):
        return "Remove COMMIT / ROLLBACK / SAVEPOINT lines: the app runs the script in its own transaction."
    hit = is_protected_rule_sql(s)
    if hit:
        return (f"'{hit}' is a legal-regime rule table. Change it from Master → AOA Rule Editor so the change is "
                "validated, dated and audited.")
    if _DESTRUCTIVE_RE.search(re.sub(r"--[^\n]*", " ", s)) and not confirmed_destructive:
        return "Destructive statement (DROP / TRUNCATE / DELETE FROM) detected. Amendments only add or close dated rows."
    return None


def _run(db, sql: str, commit: bool) -> dict:
    """Run the script in one transaction; roll it back unless `commit`. -> {rowcount, rows, notices}."""
    rows, rowcount = [], None
    with db._conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(sql)
            rowcount = cur.rowcount
            if cur.description:
                cols = [c[0] for c in cur.description]
                rows = [dict(r) if isinstance(r, dict) else dict(zip(cols, r)) for r in cur.fetchmany(20)]
        except Exception:
            conn.rollback()
            raise
        if not commit:
            conn.rollback()
    return {"rowcount": rowcount, "rows": rows}


def dry_run_sql(db, sql: str) -> dict:
    return _run(db, sql.strip(), commit=False)


def apply_sql(db, sql: str) -> dict:
    return _run(db, sql.strip(), commit=True)
