"""
Independent assurance records (Gold-Standard Plan v4, Phase 5: tasks 5.1 to 5.4).

A review, an opinion and a penetration test are done by people outside this repository. This module records that they
happened and refuses to let anyone claim more than the evidence supports. Everything is PROVISIONAL until stored:

  5.1 / 5.3  engagements + findings: a report hash, every finding closed (or, for 5.1 only, accepted in writing), and for
             5.3 a passed retest. The reviewer must declare independence.
  5.2        one stored advocate/CA opinion per platform rule and per bye-law decision type.
  5.4        a dated check of the Income-tax Act 2025 transition and the July 2026 IFMS amendment, per release.

The database enforces the rules (see "Phase 5" at the end of database/estatehub.sql). This module is the thin layer that
the scripts and, later, a master screen call. Platform-level records are MASTER-only: they describe the platform's own
rule packs and code, not one society's books. A society's own adviser decisions stay in app/services/adviser_decisions.py.

Limit, stated plainly: a stored reference and document hash show that evidence was filed. They do not show the opinion or
report is sound. A person has to read it.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date

log = logging.getLogger(__name__)

TASKS = ("5.1", "5.2", "5.3")
SEVERITIES = ("critical", "high", "medium", "low", "info")
ADVISERS = ("Advocate", "CA")
CONCLUSIONS = ("confirms", "confirms_with_change", "disputes")
RELEASE_ITEMS = ("it_act_2025_transition", "ifms_july_2026_amendment")
OUTCOMES = ("no_change", "rules_updated", "blocked")
# Fields a caller may set while moving an engagement forward. Status goes through the database guard.
ENGAGEMENT_FIELDS = (
    "reviewer_name", "reviewer_firm", "reviewer_credential", "independence_declared", "engaged_on",
    "report_received_on", "report_ref", "report_sha256", "retest_passed_on", "closed_on", "reviewed_commit", "note",
)
_SHA = re.compile(r"^[0-9a-f]{64}$")
PROVISIONAL_LABEL_PREFIX = "Provisional"


def _db(db=None):
    if db is not None:
        return db
    from database.db_manager import db as _default
    return _default


def _require_master(role) -> None:
    if role != "master":
        raise PermissionError("Master role required: assurance records describe the platform, not one society.")


def refusal_text(exc) -> str:
    """The database's own refusal, first line only (psycopg2 appends CONTEXT lines naming SQL functions)."""
    text = str(exc or "").strip()
    return (text.splitlines() or [""])[0][:600]


def sha256_file(path: str) -> str:
    """SHA-256 of a report or opinion file, to store beside its reference."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha(value: str | None, what: str) -> str:
    v = (value or "").strip().lower()
    if not _SHA.match(v):
        raise ValueError(f"{what}: give the 64-character SHA-256 of the file (use sha256_file).")
    return v


def _pick(kind: str, value: str, allowed: tuple) -> str:
    if value not in allowed:
        raise ValueError(f"{kind} must be one of: {', '.join(allowed)}.")
    return value


# ── status: what may be said ─────────────────────────────────────────────────────────────────────────────────────
def status(db=None) -> dict:
    """Where 5.1 to 5.3 stand, and whether the words 'audit-grade' may be used. Fails closed: any error means 'no'."""
    d = _db(db)
    try:
        tasks = d._execute("SELECT * FROM v_assurance_status ORDER BY task", fetch_all=True) or []
        uncovered = d._execute("SELECT COUNT(*) AS n FROM v_rule_assurance WHERE NOT covered", fetch_one=True)
        label = d._execute("SELECT fn_assurance_label() AS l", fetch_one=True)["l"]
        allowed = bool(d._execute("SELECT fn_audit_grade_claim_allowed() AS ok", fetch_one=True)["ok"])
    except Exception as exc:  # fail closed: if we cannot read the evidence, nothing is claimed
        log.warning("assurance status unreadable: %s", refusal_text(exc))
        return {"audit_grade_allowed": False, "label": f"{PROVISIONAL_LABEL_PREFIX}: assurance status unreadable",
                "tasks": [], "rules_without_opinion": None}
    return {"audit_grade_allowed": allowed, "label": label, "tasks": [dict(t) for t in tasks],
            "rules_without_opinion": int(uncovered["n"])}


def claim_label(db=None) -> str:
    """The only wording the product may use for its assurance level."""
    return status(db)["label"]


def rules_without_opinion(db=None) -> list[dict]:
    """The 5.2 worklist: every rule or decision type that has no covering opinion, with its current provisional state."""
    return [dict(r) for r in (_db(db)._execute(
        "SELECT subject_kind, regime_code, subject_key, verification, assurance_state FROM v_rule_assurance "
        "WHERE NOT covered ORDER BY subject_kind, regime_code NULLS LAST, subject_key", fetch_all=True) or [])]


# ── 5.1 and 5.3: engagements and findings ─────────────────────────────────────────────────────────────────────────
def create_engagement(role, task: str, title: str, scope: str, reviewed_commit: str | None = None, db=None) -> int:
    _require_master(role)
    _pick("task", task, TASKS)
    if not (title or "").strip():
        raise ValueError("Give the engagement a title.")
    if len((scope or "").strip()) < 20:
        raise ValueError("Write the scope in at least 20 characters: what the reviewer was asked to examine.")
    row = _db(db)._execute(
        "INSERT INTO assurance_engagements (task, title, scope, reviewed_commit) VALUES (%s,%s,%s,%s) RETURNING id",
        (task, title.strip(), scope.strip(), (reviewed_commit or None)), fetch_one=True)
    return int(row["id"])


def advance_engagement(role, actor_id: int | None, engagement_id: int, status: str, db=None, **fields) -> None:
    """Move an engagement to `status`, setting any of ENGAGEMENT_FIELDS. The database refuses a status the evidence
    does not support (no report hash, open findings, no retest, an uncovered rule for 5.2, no independence)."""
    _require_master(role)
    _pick("status", status, ("in_progress", "report_received", "closed", "withdrawn"))
    bad = set(fields) - set(ENGAGEMENT_FIELDS)
    if bad:
        raise ValueError(f"Not editable here: {', '.join(sorted(bad))}.")
    if "report_sha256" in fields and fields["report_sha256"] is not None:
        fields["report_sha256"] = _sha(fields["report_sha256"], "Report")
    sets, args = ["status=%s"], [status]
    for k, v in fields.items():
        sets.append(f"{k}=%s")
        args.append(v)
    if status == "closed":
        sets.append("closed_by=%s")
        args.append(actor_id)
        if "closed_on" not in fields:
            sets.append("closed_on=%s")
            args.append(date.today())
    args.append(engagement_id)
    _db(db)._execute(f"UPDATE assurance_engagements SET {', '.join(sets)} WHERE id=%s", tuple(args))  # nosec B608: column names come from ENGAGEMENT_FIELDS only


def add_finding(role, engagement_id: int, ref: str, severity: str, title: str, detail: str | None = None, db=None) -> int:
    _require_master(role)
    _pick("severity", severity, SEVERITIES)
    if not (ref or "").strip() or not (title or "").strip():
        raise ValueError("A finding needs the reviewer's reference and a title.")
    row = _db(db)._execute(
        "INSERT INTO assurance_findings (engagement_id, ref, severity, title, detail) VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (engagement_id, ref.strip(), severity, title.strip(), detail), fetch_one=True)
    return int(row["id"])


def close_finding(role, finding_id: int, closure_ref: str, closed_on: date | None = None,
                  retest_result: str | None = None, retested_on: date | None = None, db=None) -> None:
    """Mark a finding fixed. For 5.3, pass the retest result and date too."""
    _require_master(role)
    if retest_result is not None:
        _pick("retest_result", retest_result, ("pass", "fail"))
    _db(db)._execute(
        "UPDATE assurance_findings SET status='closed', closure_ref=%s, closed_on=%s, retest_result=%s, retested_on=%s WHERE id=%s",
        (closure_ref, closed_on or date.today(), retest_result, retested_on, finding_id))


def accept_finding(role, finding_id: int, accepted_ref: str, accepted_by: str, accepted_on: date | None = None, db=None) -> None:
    """Accept a 5.1 finding in writing. Never available for a penetration-test (5.3) finding."""
    _require_master(role)
    _db(db)._execute(
        "UPDATE assurance_findings SET status='accepted', accepted_ref=%s, accepted_by=%s, accepted_on=%s WHERE id=%s",
        (accepted_ref, accepted_by, accepted_on or date.today(), finding_id))


# ── 5.2: opinions against rules ───────────────────────────────────────────────────────────────────────────────────
def record_rule_opinion(role, actor_id: int | None, subject_kind: str, subject_key: str, adviser_kind: str,
                        adviser_name: str, opinion_ref: str, opinion_date: date, document_sha256: str,
                        conclusion: str, covers: str, regime_code: str | None = None, db=None) -> int:
    """Store an adviser's opinion against one rule ('rule', needs regime_code) or decision type ('decision_type').
    A new opinion supersedes the old one. A 'disputes' conclusion is stored but does not cover the rule."""
    _require_master(role)
    _pick("subject_kind", subject_kind, ("rule", "decision_type"))
    _pick("adviser_kind", adviser_kind, ADVISERS)
    _pick("conclusion", conclusion, CONCLUSIONS)
    if (subject_kind == "rule") != bool(regime_code):
        raise ValueError("A rule opinion needs its regime_code; a decision-type opinion must not have one.")
    row = _db(db)._execute(
        "INSERT INTO rule_opinion_references (subject_kind, regime_code, subject_key, adviser_kind, adviser_name, opinion_ref, "
        "opinion_date, document_sha256, conclusion, covers, recorded_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (subject_kind, regime_code, subject_key, adviser_kind, adviser_name, opinion_ref, opinion_date,
         _sha(document_sha256, "Opinion"), conclusion, covers, actor_id), fetch_one=True)
    return int(row["id"])


# ── 5.4: the release check ────────────────────────────────────────────────────────────────────────────────────────
def record_release_verification(role, actor_id: int | None, release_tag: str, item: str, source_ref: str, outcome: str,
                                checked_on: date | None = None, rules_touched: list[str] | None = None,
                                adviser_opinion_ref: str | None = None, note: str | None = None, db=None) -> int:
    """Record that `item` was re-read against its source before `release_tag`. Without adviser_opinion_ref the record is
    the engineer's reading only and the gate reports it as provisional."""
    _require_master(role)
    _pick("item", item, RELEASE_ITEMS)
    _pick("outcome", outcome, OUTCOMES)
    row = _db(db)._execute(
        "INSERT INTO release_verifications (release_tag, item, checked_on, checked_by, source_ref, outcome, rules_touched, "
        "adviser_opinion_ref, note) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (release_tag, item, checked_on or date.today(), actor_id, source_ref, outcome, list(rules_touched or []),
         adviser_opinion_ref or None, note), fetch_one=True)
    return int(row["id"])


def release_gate(release_tag: str, max_age_days: int = 30, db=None) -> dict:
    """{'ok': bool, 'provisional': bool, 'items': [...]}. ok only if both items were checked recently and none is blocked."""
    rows = [dict(r) for r in (_db(db)._execute(
        "SELECT * FROM fn_release_gate(%s, %s)", (release_tag, max_age_days), fetch_all=True) or [])]
    return {"ok": bool(rows) and all(r["ok"] for r in rows), "provisional": any(r["provisional"] for r in rows), "items": rows}
