"""respond_to_alert: only an apartment login linked to the alert's flat, in the alert's society, may answer (hermetic)."""
import pytest

al = pytest.importorskip("app.services.alert_service")


def _fake_db(event, flat_id, logins):
    """logins: {(user_id): (role, linked_id, society_id)}"""
    def run(sql, params=None, fetch_one=False, fetch_all=False):
        s = " ".join(sql.split())
        if s.startswith("SELECT ae.*"):
            return event
        if "FROM visitors WHERE id" in s or "FROM alert_channels WHERE id" in s:
            return {"apartment_id": flat_id}
        if "FROM users" in s:
            uid, linked, soc = params
            row = logins.get(uid)
            return {"ok": 1} if row and row == ("apartment", linked, soc) else None
        if s.startswith("UPDATE alert_events"):
            return {"id": event["id"]}
        return None
    return run


@pytest.fixture
def ev():
    return {"id": 9, "society_id": 1, "channel_id": None, "visitor_id": 5, "state": "pending", "is_recurring": None}


def _call(monkeypatch, ev, flat_id, logins, uid):
    monkeypatch.setattr(al.db, "_execute", _fake_db(ev, flat_id, logins))
    monkeypatch.setattr(al, "_publish_alert_event", lambda *a, **k: None)
    return al.respond_to_alert(9, uid, "approve")[0]


def test_any_login_of_the_flat_may_answer(monkeypatch, ev):
    logins = {10: ("apartment", 7, 1), 11: ("apartment", 7, 1)}          # owner and a family login of flat 7
    assert _call(monkeypatch, ev, 7, logins, 10) is True
    assert _call(monkeypatch, ev, 7, logins, 11) is True


def test_another_flat_security_or_other_society_is_refused(monkeypatch, ev):
    logins = {20: ("apartment", 8, 1), 21: ("security", 7, 1), 22: ("apartment", 7, 2)}
    for uid in (20, 21, 22):
        assert _call(monkeypatch, ev, 7, logins, uid) is False


def test_an_alert_with_no_flat_cannot_be_answered(monkeypatch, ev):
    assert _call(monkeypatch, ev, None, {10: ("apartment", 7, 1)}, 10) is False
