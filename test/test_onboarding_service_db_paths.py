"""link_opening_receivable / void_pending_receivable / store_evidence_file against a scripted fake DB."""
from contextlib import contextmanager
import pytest
from app.services import onboarding_service as ob


class FakeCur:
    def __init__(self, script, log):
        self.script, self.log, self.cur = script, log, None

    def execute(self, sql, params=None):
        self.log.append((" ".join(sql.split()), params))
        for key, rows in self.script:
            if key in sql:
                self.cur = list(rows)
                return
        self.cur = []

    def fetchone(self):
        return self.cur.pop(0) if self.cur else None


class FakeDB:
    def __init__(self, script):
        self.script, self.log = script, []

    @contextmanager
    def _conn(self):
        db = self

        class C:
            def cursor(self_inner):
                return FakeCur(db.script, db.log)
        yield C()

    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        self.log.append((" ".join(sql.split()), params))
        for key, rows in self.script:
            if key in sql:
                return (rows[0] if rows else None) if fetch_one else rows
        return None


def _wire(monkeypatch, script):
    fake = FakeDB(script)
    monkeypatch.setattr(ob, "db", fake)
    return fake


def test_link_creates_receivable_with_real_columns(monkeypatch):
    fake = _wire(monkeypatch, [
        ("FROM opening_receivables_pending", [{"id": 7, "amount": 5000}]),
        ("tab_name='SDr'", [{"id": 42}]),
        ("as_at_date", [{"as_at": "2026-03-31"}]),
        ("INSERT INTO receivables", [{"id": 99}]),
    ])
    assert ob.link_opening_receivable(1, 10, " A-101 ") == 99
    ins = next(q for q in fake.log if q[0].startswith("INSERT INTO receivables"))
    assert "entity_id" in ins[0] and "'apartment'" in ins[0] and "'pending'" in ins[0]
    assert "flat_number" not in ins[0] and "apartment_id" not in ins[0]
    assert ins[1][1] == 10 and ins[1][2] == 42
    assert any("status='linked'" in q[0] for q in fake.log)


def test_link_is_idempotent_when_nothing_pending(monkeypatch):
    fake = _wire(monkeypatch, [])
    assert ob.link_opening_receivable(1, 10, "A-101") is None
    assert not any(q[0].startswith("INSERT") for q in fake.log)


def test_link_refuses_without_sdr_account(monkeypatch):
    _wire(monkeypatch, [("FROM opening_receivables_pending", [{"id": 7, "amount": 5}])])
    with pytest.raises(ob.OnboardingError):
        ob.link_opening_receivable(1, 10, "A-101")


def test_void_needs_reason_and_an_existing_pending_row(monkeypatch):
    with pytest.raises(ob.OnboardingError):
        ob.void_pending_receivable(1, 2, "A-1", "short")
    _wire(monkeypatch, [])
    with pytest.raises(ob.OnboardingError):
        ob.void_pending_receivable(1, 2, "A-1", "flat was merged into A-2")
    fake = _wire(monkeypatch, [("UPDATE opening_receivables_pending", [{"id": 3}]), ("INSERT INTO audit_events", [])])
    ob.void_pending_receivable(1, 2, "A-1", "flat was merged into A-2")
    assert any("RETURNING id" in q[0] for q in fake.log)


def test_store_evidence_returns_id_and_sha(monkeypatch, tmp_path):
    import hashlib
    _wire(monkeypatch, [("INSERT INTO onboarding_evidence", [{"id": 5}])])
    import app.dash_apps.callbacks.drilldown_callbacks as dc
    monkeypatch.setattr(dc, "ASSETS_ROOT", tmp_path)            # never write into the repo's assets
    data = b"%PDF-1.4 test"
    out = ob.store_evidence_file(1, "bank_statement", 3, "stmt.pdf", data, 2, {})
    assert out["id"] == 5 and out["sha256"] == hashlib.sha256(data).hexdigest()
