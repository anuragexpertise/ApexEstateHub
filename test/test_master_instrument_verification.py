"""Platform master verifies Central instruments in bulk: master only, all-or-nothing, per-act notification no. and source link."""
from contextlib import contextmanager
import pytest
from app.services import document_signing as ds
from app.services import instrument_verification as iv


class FakeCur:
    def __init__(self, db): self.db = db
    def execute(self, sql, params=None):
        self.db.writes.append((sql, params))
        if self.db.fail_on and self.db.fail_on in sql:
            raise RuntimeError("ERROR: boom")


class FakeDB:
    def __init__(self, master=True, rows=None):
        self.master, self.writes, self.fail_on = master, [], None
        self.rows = rows if rows is not None else {1: ("Act One", "unverified", "CENTRAL"), 2: ("Act Two", "unverified", "CENTRAL")}

    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        if "is_master_admin" in sql:
            return {"is_master_admin": self.master, "society_id": None}
        return [{"id": i, "title": t, "verification": v, "regime_code": r} for i, (t, v, r) in self.rows.items() if i in params[0]]

    @contextmanager
    def _conn(self):
        class C:
            def cursor(s): return FakeCur(self)
        yield C()


def _items(*ids):
    return [{"id": i, "notification_no": f"N-{i}", "source_url": f"https://example.gov.in/act{i}"} for i in ids]


def test_master_verifies_all_selected_in_one_go():
    db = FakeDB()
    assert iv.verify_many_as_master(9, _items(1, 2), "ADV/2026/14", "2026-11-01", db=db) == 2
    calls = [w for w in db.writes if "fn_verify_instrument" in w[0]]
    assert len(calls) == 2 and calls[0][1][2] == "master" and calls[0][1][5] == "ADV/2026/14"
    assert any("INSTRUMENTS_VERIFIED_BULK" in w[0] for w in db.writes)


def test_only_the_master_may_do_it():
    with pytest.raises(ds.SigningRefused):
        iv.verify_many_as_master(9, _items(1), "ADV/1", db=FakeDB(master=False))


def test_all_or_nothing_reports_every_problem_and_writes_nothing():
    db = FakeDB()
    items = [{"id": 1, "notification_no": "", "source_url": "https://ok.in"}, {"id": 2, "notification_no": "N", "source_url": "ftp://bad"}]
    with pytest.raises(ds.SigningRefused) as e:
        iv.verify_many_as_master(9, items, "", db=db)
    msg = str(e.value)
    assert "Nothing was verified" in msg and "opinion reference" in msg and "Act One: notification number" in msg and "Act Two: a link" in msg
    assert db.writes == []


def test_already_verified_and_non_central_are_refused():
    db = FakeDB(rows={1: ("Done", "verified", "CENTRAL"), 2: ("UP act", "unverified", "UP_AOA_2010")})
    with pytest.raises(ds.SigningRefused) as e:
        iv.verify_many_as_master(9, _items(1, 2), "ADV/1", db=db)
    assert "already verified" in str(e.value) and "not a Central instrument" in str(e.value) and db.writes == []


def test_future_date_and_empty_selection_refused():
    with pytest.raises(ds.SigningRefused):
        iv.verify_many_as_master(9, _items(1), "ADV/1", "2999-01-01", db=FakeDB())
    with pytest.raises(ds.SigningRefused):
        iv.verify_many_as_master(9, [], "ADV/1", db=FakeDB())


def test_missing_migration_gives_a_clear_hint():
    db = FakeDB(); db.fail_on = "fn_verify_instrument"
    db.fail_on = "fn_verify_instrument"
    class Boom(FakeCur):
        def execute(self, sql, params=None):
            raise RuntimeError("ERROR: Only the Treasurer or an Auditor can verify an instrument.")
    @contextmanager
    def conn():
        class C:
            def cursor(s): return Boom(db)
        yield C()
    db._conn = conn
    with pytest.raises(ds.SigningRefused) as e:
        iv.verify_many_as_master(9, _items(1), "ADV/1", db=db)
    assert "002_master_instrument_verification.sql" in str(e.value)
