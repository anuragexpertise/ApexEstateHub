"""
Phase 5 (tasks 5.1 to 5.4): the database refuses what the evidence does not support. Real Postgres, rolled back.

    ESTATEHUB_LIVE_TESTS=1 PGHOST=... PGDATABASE=... PGUSER=... pytest test/test_assurance_live.py
"""
import hashlib
import os
from datetime import date, timedelta

import pytest

import psycopg2.extras  # noqa: F401
from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

psycopg2 = pytest.importorskip("psycopg2")
pytestmark = [pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON), pytest.mark.postgres_integration]

from app.services import assurance as a  # noqa: E402
from test.test_job_runner_live import SavepointTx  # noqa: E402

SHA = hashlib.sha256(b"report").hexdigest()
M = "master"


@pytest.fixture()
def tx():
    c = psycopg2.connect(host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"), dbname=os.getenv("PGDATABASE"),
                         user=os.getenv("PGUSER"), password=os.getenv("PGPASSWORD"))
    cur = c.cursor()
    cur.execute("SELECT to_regclass('assurance_engagements') IS NOT NULL")
    if not cur.fetchone()[0]:
        c.close()
        pytest.skip("estatehub.sql with Phase 5 assurance is not installed")
    yield SavepointTx(c)
    c.rollback()
    c.close()


def refused(fn, *args, **kw):
    with pytest.raises(Exception) as e:
        fn(*args, **kw)
    return a.refusal_text(e.value)


def engage(tx, task, commit=True):
    eid = a.create_engagement(M, task, f"Review {task}", "Examine the books engine and statements end to end.", "abc1234" if commit else None, db=tx)
    a.advance_engagement(M, None, eid, "in_progress", db=tx, reviewer_name="R. Sharma", reviewer_credential="ICAI 123456",
                         engaged_on=date.today(), independence_declared=True)
    return eid


def report(tx, eid, **extra):
    a.advance_engagement(M, None, eid, "report_received", db=tx, report_ref="REP/2026/1", report_sha256=SHA,
                         report_received_on=date.today(), **extra)


def cover_everything(tx, conclusion="confirms"):
    for r in a.rules_without_opinion(db=tx):
        a.record_rule_opinion(M, None, r["subject_kind"], r["subject_key"], "Advocate", "Adv. Rao", f"OP/{r['subject_key']}"[:100],
                              date.today(), SHA, conclusion, "Reviewed the figure against the Act and bye-laws.",
                              regime_code=r["regime_code"], db=tx)


# ── status starts provisional ───────────────────────────────────────────────────────────────────────────────────
def test_fresh_database_is_provisional_and_every_rule_is_on_the_worklist(tx):
    s = a.status(tx)
    assert s["audit_grade_allowed"] is False and s["label"].startswith("Provisional")
    assert {t["task"] for t in s["tasks"] if not t["satisfied"]} == {"5.1", "5.2", "5.3"}
    work = a.rules_without_opinion(tx)
    assert len(work) == s["rules_without_opinion"] > 0
    assert all("provisional" in w["assurance_state"] for w in work)


# ── 5.1 ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_5_1_needs_report_hash_independence_and_no_open_findings(tx):
    eid = a.create_engagement(M, "5.1", "CA review", "Examine the books engine and statements end to end.", db=tx)
    assert "reviewer" in refused(a.advance_engagement, M, None, eid, "in_progress", db=tx)
    a.advance_engagement(M, None, eid, "in_progress", db=tx, reviewer_name="R. Sharma", reviewer_credential="ICAI 123456", engaged_on=date.today())
    assert "report" in refused(a.advance_engagement, M, None, eid, "report_received", db=tx).lower()
    report(tx, eid)
    assert "independence" in refused(a.advance_engagement, M, None, eid, "closed", db=tx)
    a.advance_engagement(M, None, eid, "report_received", db=tx, independence_declared=True, report_ref="REP/2026/1", report_sha256=SHA, report_received_on=date.today())
    f1 = a.add_finding(M, eid, "F-1", "high", "Rounding differs in notes", db=tx)
    f2 = a.add_finding(M, eid, "F-2", "low", "Typo in schedule heading", db=tx)
    assert "still open" in refused(a.advance_engagement, M, None, eid, "closed", db=tx)
    assert "fix reference" in refused(a.close_finding, M, f1, "", db=tx)
    a.close_finding(M, f1, "commit 9f3c2ab", db=tx)
    assert "written-acceptance" in refused(a.accept_finding, M, f2, "", "Board", db=tx)
    a.accept_finding(M, f2, "Board res. 12/2026", "Secretary", db=tx)
    a.advance_engagement(M, None, eid, "closed", db=tx)
    s5 = [t for t in a.status(tx)["tasks"] if t["task"] == "5.1"][0]
    assert s5["satisfied"] and s5["report_ref"] == "REP/2026/1"


def test_closed_engagement_and_its_findings_are_frozen(tx):
    eid = engage(tx, "5.1")
    report(tx, eid)
    a.advance_engagement(M, None, eid, "closed", db=tx)
    assert "cannot be changed" in refused(tx._execute, "UPDATE assurance_engagements SET title='x' WHERE id=%s", (eid,))
    assert "cannot be deleted" in refused(tx._execute, "DELETE FROM assurance_engagements WHERE id=%s", (eid,))
    assert "fixed" in refused(a.add_finding, M, eid, "F-9", "low", "late finding", db=tx)


# ── 5.3 ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_5_3_findings_cannot_be_accepted_and_need_a_passed_retest(tx):
    eid = engage(tx, "5.3")
    report(tx, eid)
    f = a.add_finding(M, eid, "PT-1", "critical", "Verification page leaks key id", db=tx)
    assert "cannot be accepted" in refused(a.accept_finding, M, f, "Board res. 1", "Board", db=tx)
    a.close_finding(M, f, "commit 77aa", db=tx)
    assert "passed retest" in refused(a.advance_engagement, M, None, eid, "closed", db=tx)
    a.advance_engagement(M, None, eid, "report_received", db=tx, retest_passed_on=date.today(), report_ref="REP/2026/1", report_sha256=SHA, report_received_on=date.today())
    assert "retest" in refused(a.advance_engagement, M, None, eid, "closed", db=tx)       # finding itself not retested
    tx._execute("UPDATE assurance_findings SET retest_result='pass', retested_on=%s WHERE id=%s", (date.today(), f))
    a.advance_engagement(M, None, eid, "closed", db=tx)
    assert [t for t in a.status(tx)["tasks"] if t["task"] == "5.3"][0]["satisfied"]


def test_retest_result_only_on_closed_pen_test_findings(tx):
    eid = engage(tx, "5.1")
    f = a.add_finding(M, eid, "F-1", "low", "x finding", db=tx)
    assert "retest" in refused(a.close_finding, M, f, "commit abc123", retest_result="pass", retested_on=date.today(), db=tx)


# ── 5.2 ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_5_2_opinion_rules(tx):
    work = a.rules_without_opinion(tx)
    r = next(x for x in work if x["subject_kind"] == "rule")
    kw = dict(adviser_kind="Advocate", adviser_name="Adv. Rao", opinion_ref="OP/2026/9", opinion_date=date.today(),
              document_sha256=SHA, conclusion="confirms", covers="Figure matches bye-law text.", db=tx)
    assert "No platform rule" in refused(a.record_rule_opinion, M, None, "rule", "NO_SUCH_RULE", regime_code=r["regime_code"], **kw)
    assert "SHA-256" in refused(a.record_rule_opinion, M, None, "rule", r["subject_key"], regime_code=r["regime_code"], **{**kw, "document_sha256": "abc"})
    assert refused(a.record_rule_opinion, M, None, "rule", r["subject_key"], regime_code=r["regime_code"], **{**kw, "opinion_date": date.today() + timedelta(days=3)})  # future-dated opinion refused
    # a disputing opinion is stored but does not cover the rule
    a.record_rule_opinion(M, None, "rule", r["subject_key"], regime_code=r["regime_code"], **{**kw, "conclusion": "disputes"})
    row = [x for x in tx._execute("SELECT * FROM v_rule_assurance WHERE subject_key=%s AND regime_code=%s", (r["subject_key"], r["regime_code"]), fetch_all=True)][0]
    assert row["covered"] is False and "disputes" in row["assurance_state"]
    # a new opinion supersedes it, the history stays
    a.record_rule_opinion(M, None, "rule", r["subject_key"], regime_code=r["regime_code"], **kw)
    row = tx._execute("SELECT covered FROM v_rule_assurance WHERE subject_key=%s AND regime_code=%s", (r["subject_key"], r["regime_code"]), fetch_one=True)
    assert row["covered"] is True
    n = tx._execute("SELECT COUNT(*) FILTER (WHERE status='superseded') s, COUNT(*) FILTER (WHERE status='current') c FROM rule_opinion_references WHERE subject_key=%s", (r["subject_key"],), fetch_one=True)
    assert (n["s"], n["c"]) == (1, 1)
    assert "cannot be edited" in refused(tx._execute, "UPDATE rule_opinion_references SET opinion_ref='ALTERED-REF' WHERE status='current'")
    assert "cannot be deleted" in refused(tx._execute, "DELETE FROM rule_opinion_references")


def test_5_2_cannot_close_while_any_rule_is_uncovered_and_degrades_if_an_opinion_is_withdrawn(tx):
    eid = engage(tx, "5.2")
    assert "no stored opinion" in refused(a.advance_engagement, M, None, eid, "closed", db=tx)
    assert "closed by stored opinions" in refused(a.add_finding, M, eid, "F-1", "low", "no findings on 5.2", db=tx)
    cover_everything(tx)
    assert a.rules_without_opinion(tx) == []
    a.advance_engagement(M, None, eid, "closed", db=tx)
    assert [t for t in a.status(tx)["tasks"] if t["task"] == "5.2"][0]["satisfied"]
    tx._execute("UPDATE rule_opinion_references SET status='withdrawn' WHERE id=(SELECT MIN(id) FROM rule_opinion_references WHERE status='current')")
    assert [t for t in a.status(tx)["tasks"] if t["task"] == "5.2"][0]["satisfied"] is False


def test_5_2_disputing_opinions_block_closure(tx):
    eid = engage(tx, "5.2")
    cover_everything(tx, conclusion="disputes")
    assert "no stored opinion" in refused(a.advance_engagement, M, None, eid, "closed", db=tx)


# ── "audit-grade" only after 5.1 to 5.3 ───────────────────────────────────────────────────────────────────────────
def test_audit_grade_claim_needs_all_three_and_survives_only_while_they_hold(tx):
    e1, e3, e2 = engage(tx, "5.1"), engage(tx, "5.3"), engage(tx, "5.2")
    for e in (e1, e3):
        report(tx, e)
    a.advance_engagement(M, None, e3, "report_received", db=tx, retest_passed_on=date.today(), report_ref="REP/2026/1", report_sha256=SHA, report_received_on=date.today())
    a.advance_engagement(M, None, e1, "closed", db=tx)
    a.advance_engagement(M, None, e3, "closed", db=tx)
    assert a.status(tx)["audit_grade_allowed"] is False           # 5.2 still open
    cover_everything(tx)
    a.advance_engagement(M, None, e2, "closed", db=tx)
    s = a.status(tx)
    assert s["audit_grade_allowed"] is True and s["label"].startswith("Independently assured")
    tx._execute("UPDATE rule_opinion_references SET status='withdrawn' WHERE id=(SELECT MIN(id) FROM rule_opinion_references WHERE status='current')")
    assert a.status(tx)["audit_grade_allowed"] is False and a.claim_label(tx).startswith("Provisional")


# ── 5.4 ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_5_4_release_gate(tx):
    tag = "v-test-1"
    g = a.release_gate(tag, db=tx)
    assert g["ok"] is False and {i["reason"] for i in g["items"]} == {"no check recorded for this release"}
    src = "Notification 7098 of 13.07.2026 read in full"
    a.record_release_verification(M, None, tag, "it_act_2025_transition", "Income-tax Act 2025 s.186 text read", "no_change", db=tx)
    assert a.release_gate(tag, db=tx)["ok"] is False                 # only one of two
    a.record_release_verification(M, None, tag, "ifms_july_2026_amendment", src, "rules_updated", rules_touched=["ifms_rate"], db=tx)
    g = a.release_gate(tag, db=tx)
    assert g["ok"] is True and g["provisional"] is True              # engineer's reading only
    for item in a.RELEASE_ITEMS:
        a.record_release_verification(M, None, tag, item, src, "no_change", adviser_opinion_ref="CA/2026/31", db=tx)
    g = a.release_gate(tag, db=tx)
    assert g["ok"] is True and g["provisional"] is False
    a.record_release_verification(M, None, tag, "ifms_july_2026_amendment", src, "blocked", db=tx)
    assert a.release_gate(tag, db=tx)["ok"] is False                 # newest record wins
    # staleness
    a.record_release_verification(M, None, "v-old", "it_act_2025_transition", src, "no_change", checked_on=date.today() - timedelta(days=40), db=tx)
    old = {i["item"]: i for i in a.release_gate("v-old", db=tx)["items"]}
    assert "older than 30 days" in old["it_act_2025_transition"]["reason"]


def test_5_4_records_are_append_only_and_checked(tx):
    a.record_release_verification(M, None, "v-x", "it_act_2025_transition", "Income-tax Act 2025 s.186 text read", "no_change", db=tx)
    assert "dated record" in refused(tx._execute, "UPDATE release_verifications SET outcome='blocked'")
    assert "dated record" in refused(tx._execute, "DELETE FROM release_verifications")
    assert refused(a.record_release_verification, M, None, "v-x", "it_act_2025_transition", "too short", "no_change", db=tx)
    assert refused(a.record_release_verification, M, None, "v-x", "it_act_2025_transition", "Income-tax Act 2025 s.186 text read", "rules_updated", db=tx)  # touched rules missing
    assert refused(a.record_release_verification, M, None, "v-x", "it_act_2025_transition", "Income-tax Act 2025 s.186 text read", "no_change", checked_on=date.today() + timedelta(days=2), db=tx)


def test_assurance_actions_are_written_to_the_audit_log(tx):
    a.record_release_verification(M, None, "v-audit", "it_act_2025_transition", "Income-tax Act 2025 s.186 text read", "no_change", db=tx)
    eid = engage(tx, "5.1")
    report(tx, eid)
    acts = {r["action"] for r in tx._execute("SELECT action FROM audit_events WHERE action LIKE 'ASSURANCE_%%' OR action='RELEASE_VERIFIED'", fetch_all=True)}
    assert {"RELEASE_VERIFIED", "ASSURANCE_IN_PROGRESS", "ASSURANCE_REPORT_RECEIVED"} <= acts
