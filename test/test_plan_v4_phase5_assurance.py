"""
Plan v4 - Phase 5: independent assurance (tasks 5.1 to 5.4). Hermetic part: runs with no database.

The database rules themselves are proved in test/test_assurance_live.py.
"""
import hashlib
import os
import re
from datetime import date

import pytest

from app.services import assurance as a

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SHA = hashlib.sha256(b"report").hexdigest()


class Recorder:
    def __init__(self, row=None):
        self.calls, self.row = [], row or {"id": 7}

    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        self.calls.append((sql, params))
        return [] if fetch_all else self.row


class Broken:
    def _execute(self, *args, **kwargs):
        raise RuntimeError("database down")


@pytest.mark.parametrize("call", [
    lambda: a.create_engagement("admin", "5.1", "t", "x" * 30, db=Recorder()),
    lambda: a.advance_engagement("admin", 1, 1, "in_progress", db=Recorder()),
    lambda: a.add_finding("accountant", 1, "F-1", "high", "t", db=Recorder()),
    lambda: a.close_finding("admin", 1, "abc123", db=Recorder()),
    lambda: a.accept_finding("admin", 1, "ref-1", "Board", db=Recorder()),
    lambda: a.record_rule_opinion("admin", 1, "decision_type", "K", "CA", "n", "ref-1", date.today(), SHA, "confirms", "x" * 12, db=Recorder()),
    lambda: a.record_release_verification("admin", 1, "v1", "it_act_2025_transition", "notification 1234 read", "no_change", db=Recorder()),
])
def test_only_master_may_write_platform_assurance_records(call):
    with pytest.raises(PermissionError):
        call()


def test_input_is_validated_before_the_database_is_touched():
    rec = Recorder()
    with pytest.raises(ValueError):
        a.create_engagement("master", "5.9", "t", "x" * 30, db=rec)
    with pytest.raises(ValueError):
        a.create_engagement("master", "5.1", "t", "short", db=rec)
    with pytest.raises(ValueError):
        a.advance_engagement("master", 1, 1, "closed", db=rec, report_sha256="not-a-hash")
    with pytest.raises(ValueError):
        a.advance_engagement("master", 1, 1, "closed", db=rec, status_override="x")
    with pytest.raises(ValueError):
        a.record_rule_opinion("master", 1, "rule", "K", "CA", "n", "ref-1", date.today(), SHA, "confirms", "x" * 12, db=rec)  # rule needs regime
    with pytest.raises(ValueError):
        a.record_rule_opinion("master", 1, "decision_type", "K", "Lawyer", "n", "ref-1", date.today(), SHA, "confirms", "x" * 12, db=rec)
    with pytest.raises(ValueError):
        a.record_release_verification("master", 1, "v1", "gst_rates", "notification 1234 read", "no_change", db=rec)
    assert rec.calls == []


def test_close_sets_closer_and_date_and_only_whitelisted_columns():
    rec = Recorder()
    a.advance_engagement("master", 42, 3, "closed", db=rec, report_ref="CA/2026/14", report_sha256=SHA.upper())
    sql, params = rec.calls[0]
    assert "closed_by=%s" in sql and "closed_on=%s" in sql
    assert params[0] == "closed" and 42 in params and SHA in params  # hash normalised to lower case
    assert re.fullmatch(r"UPDATE assurance_engagements SET [a-z0-9_=%s, ]+ WHERE id=%s", sql)


def test_status_fails_closed_when_the_evidence_cannot_be_read():
    s = a.status(Broken())
    assert s["audit_grade_allowed"] is False
    assert s["label"].startswith(a.PROVISIONAL_LABEL_PREFIX)
    assert a.claim_label(Broken()).startswith("Provisional")


def test_sha256_file_matches_hashlib(tmp_path):
    p = tmp_path / "opinion.pdf"
    p.write_bytes(b"%PDF opinion")
    assert a.sha256_file(str(p)) == hashlib.sha256(b"%PDF opinion").hexdigest()


def test_refusal_text_keeps_first_line_only():
    assert a.refusal_text(Exception("Task 5.2 cannot close.\nCONTEXT: PL/pgSQL function x")) == "Task 5.2 cannot close."


def test_schema_has_every_phase5_object_inline_in_the_one_sql_file():
    sql = open(os.path.join(ROOT, "database", "estatehub.sql"), encoding="utf-8").read()
    for obj in ("CREATE TABLE assurance_engagements", "CREATE TABLE assurance_findings",
                "CREATE TABLE rule_opinion_references", "CREATE TABLE release_verifications",
                "VIEW v_rule_assurance", "VIEW v_assurance_status", "FUNCTION fn_audit_grade_claim_allowed",
                "FUNCTION fn_release_gate"):
        assert obj in sql, obj
    # engineering gate 4: no IF NOT EXISTS guards on new columns/tables
    phase5 = sql[sql.index("Phase 5 (Plan v4)"):]
    assert "IF NOT EXISTS" not in phase5.replace("IF NOT EXISTS (SELECT", "")


def test_release_check_script_and_runbook_exist_and_state_the_limit():
    assert os.path.exists(os.path.join(ROOT, "scripts", "release_check.py"))
    doc = open(os.path.join(ROOT, "docs", "PHASE5_ASSURANCE.md"), encoding="utf-8").read()
    for needle in ("5.1", "5.2", "5.3", "5.4", "Provisional", "[Verify]", "audit-grade"):
        assert needle in doc, needle
