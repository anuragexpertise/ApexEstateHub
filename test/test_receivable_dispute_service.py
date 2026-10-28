"""Task 1.5 service layer: who may act, safe messages, audit. The rules themselves are tested live in
test_phase1_leftovers_live.py; this file needs no database."""
import pytest

from app.services import receivable_dispute_service as svc


class FakeDB:
    def __init__(self, role="admin", offices=(), error=None, result=None):
        self.role, self.offices, self.error, self.result, self.calls = role, list(offices), error, result, []

    def _execute(self, sql, params=(), fetch_one=False, fetch_all=False):
        self.calls.append((sql, params))
        if "FROM users" in sql:
            return {"role": self.role}
        if "FROM committee_offices" in sql:
            return self.offices
        if self.error and "fn_" in sql:
            raise self.error
        return self.result


@pytest.fixture(autouse=True)
def _no_audit(monkeypatch):
    import app.security.service_guard as sg
    monkeypatch.setattr(sg, "audit_event", lambda *a, **k: True)


def test_admin_can_raise_and_the_database_function_gets_every_argument():
    d = FakeDB(result={"id": 7})
    assert svc.raise_dispute(1, 55, 9, "charged for a vacant flat", "MC-1", db=d) == 7
    sql, params = d.calls[-1]
    assert "fn_raise_receivable_dispute" in sql and params == (1, 55, 9, "charged for a vacant flat", "MC-1")


def test_a_serving_office_bearer_may_act_but_an_ordinary_user_may_not():
    ok = FakeDB(role="staff", offices=[{"id": 3, "office_code": "treasurer"}], result={"id": 1})
    assert svc.raise_dispute(1, 5, 9, "a proper reason", "MC-1", db=ok) == 1
    with pytest.raises(svc.DisputeRefused, match="administrator or a serving office-bearer"):
        svc.raise_dispute(1, 5, 9, "a proper reason", "MC-1", db=FakeDB(role="apartment"))
    with pytest.raises(svc.DisputeRefused, match="administrator or a serving office-bearer"):
        svc.decide(1, 5, "dismissed", 9, "r", "x", db=FakeDB(role="apartment"))


def test_a_database_refusal_becomes_a_clean_message():
    d = FakeDB(error=Exception("ERROR:  This bill is already under dispute.\nCONTEXT:  PL/pgSQL function ..."))
    with pytest.raises(svc.DisputeRefused) as e:
        svc.raise_dispute(1, 5, 9, "a proper reason", "MC-1", db=d)
    assert str(e.value) == "This bill is already under dispute." and "CONTEXT" not in str(e.value)


def test_the_unique_open_index_is_translated():
    d = FakeDB(error=Exception('duplicate key value violates unique constraint "uq_receivable_dispute_open"'))
    with pytest.raises(svc.DisputeRefused, match="already under dispute"):
        svc.raise_dispute(1, 5, 9, "a proper reason", "MC-1", db=d)


def test_unknown_outcome_is_refused_before_touching_the_database():
    d = FakeDB()
    with pytest.raises(svc.DisputeRefused, match="upheld, dismissed or withdrawn"):
        svc.decide(1, 5, "maybe", 9, "r", "x", db=d)
    assert d.calls == []


def test_decide_returns_the_database_message():
    d = FakeDB(result={"msg": "dismissed; the bill stands and interest resumes"})
    assert svc.decide(1, 5, "dismissed", 9, "r", "x", db=d).startswith("dismissed")


def test_register_lists_open_disputes_first():
    d = FakeDB(result=[{"id": 1}])
    assert svc.register(1, db=d) == [{"id": 1}]
    assert "(d.status = 'open') DESC" in d.calls[-1][0]
