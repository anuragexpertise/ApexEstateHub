"""Plan v5, DPDP: a walk-in visitor has no login, so the gate notice is logged against the visit (real Postgres)."""
import os

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

pytestmark = [pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON), pytest.mark.postgres_integration]

SID = 1                                                    # the seeded, active demo society


def _consents(db, vid):
    return db._execute("SELECT * FROM consent_records WHERE society_id=%s AND person_key=%s", (SID, f"visitor:{vid}"), fetch_all=True)


def test_walk_in_visitor_gets_a_gate_notice_record():
    from database.db_manager import db
    from app.services import alert_service as al, dpdp_service as dp
    n = dp.ensure_notice(SID)
    vid, _msg = al.create_walk_in_visitor(SID, "Ravi Courier", "9800000001", "Delivery")
    assert vid
    rows = _consents(db, vid)
    assert len(rows) == 1
    r = rows[0]
    assert (r["person_role"], r["purpose"], r["lawful_basis"], r["notice_version"]) == ("visitor", "gate_safety", "legitimate_use", n["version"])


def test_recording_twice_does_not_duplicate():
    from database.db_manager import db
    from app.services import alert_service as al, dpdp_service as dp
    dp.ensure_notice(SID)
    vid, _ = al.create_walk_in_visitor(SID, "Meena Plumber", "9800000002", "Repair")
    dp.record_visitor_notice(SID, vid)
    assert len(_consents(db, vid)) == 1


def test_a_failure_to_log_never_blocks_the_visit(monkeypatch):
    from app.services import alert_service as al, dpdp_service as dp
    monkeypatch.setattr(dp, "current_notice", lambda sid: (_ for _ in ()).throw(RuntimeError("boom")))
    vid, msg = al.create_walk_in_visitor(SID, "Sunil Guest", "9800000003", "Meeting")
    assert vid and "created" in msg
