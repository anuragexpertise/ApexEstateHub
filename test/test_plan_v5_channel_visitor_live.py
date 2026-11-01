"""Visitor channels (real Postgres): an owner's answer is final, an expired alert cannot admit anyone, and every answer is audited."""
import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

pytestmark = [pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON), pytest.mark.postgres_integration]

SID = 1


@pytest.fixture()
def owner_and_event():
    from database.db_manager import db
    from app.services import alert_service as al
    apt = db._execute("SELECT a.id, u.id AS uid FROM apartments a JOIN users u ON u.linked_id=a.id AND u.role='apartment' "
                      "WHERE a.society_id=%s ORDER BY a.id LIMIT 1", (SID,), fetch_one=True)
    cid, _ = al.create_alert_channel(SID, "visitor", "Test helper", "T-1", apt["id"], True)
    ok, _m, data = al.trigger_channel_alert(cid, None, SID)
    assert ok
    return apt["uid"], data["event_id"], db, al


def _state(db, ev):
    return db._execute("SELECT state FROM alert_events WHERE id=%s", (ev,), fetch_one=True)["state"]


def test_an_answered_alert_cannot_be_flipped(owner_and_event):
    uid, ev, db, al = owner_and_event
    assert al.respond_to_alert(ev, uid, "approve")[0] is True
    ok, msg = al.respond_to_alert(ev, uid, "deny")
    assert ok is False and "already answered" in msg and _state(db, ev) == "resolved"


def test_a_denied_alert_stays_denied(owner_and_event):
    uid, ev, db, al = owner_and_event
    assert al.respond_to_alert(ev, uid, "deny")[0] is True
    assert al.respond_to_alert(ev, uid, "approve")[0] is False and _state(db, ev) == "denied"


def test_an_expired_alert_cannot_admit_anyone(owner_and_event):
    uid, ev, db, al = owner_and_event
    db._execute("UPDATE alert_events SET expires_at = NOW() - interval '1 hour' WHERE id=%s", (ev,))
    ok, msg = al.respond_to_alert(ev, uid, "approve")
    assert ok is False and "expired" in msg and _state(db, ev) == "pending"


def test_another_flats_owner_still_cannot_answer(owner_and_event):
    uid, ev, db, al = owner_and_event
    other = db._execute("SELECT id FROM users WHERE society_id=%s AND role='apartment' AND id<>%s LIMIT 1", (SID, uid), fetch_one=True)
    if not other:
        pytest.skip("only one owner login in the demo data")
    assert al.respond_to_alert(ev, other["id"], "approve")[0] is False and _state(db, ev) == "pending"


def test_every_answer_is_audited(owner_and_event):
    uid, ev, db, al = owner_and_event
    al.respond_to_alert(ev, uid, "approve")
    al.respond_to_alert(ev, uid, "deny")                                          # refused, so it must leave no second row
    rows = db._execute("SELECT from_state, to_state, actor_id FROM channel_event_transitions WHERE event_id=%s", (ev,), fetch_all=True)
    assert [(r["from_state"], r["to_state"], r["actor_id"]) for r in rows] == [("pending", "resolved", uid)]
