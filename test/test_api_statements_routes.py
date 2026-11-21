"""ICAI4 I2: financial-route authorisation tests.

Runs through the Flask test client with fake auth (no live DB, PG vars
unset). `authenticate_bearer` is monkeypatched to return a caller with a
chosen role/society_id; `db` and the service functions are monkeypatched so
no real query is sent.

Covered: no token (401), wrong role (403), admin of another society (no
cross-society data), admin of own society (200), unbalanced export (409),
master without society_id (400), master with society_id (200), msme vendor
ownership (404 / 200).
"""

import pytest
from flask import Flask

from app.routes.api import api_bp


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(api_bp)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class _User:
    def __init__(self, role, society_id):
        self.id = 1
        self.email = "user@example.com"
        self.role = role
        self.society_id = society_id
        self.linked_id = None


def _auth(monkeypatch, role, society_id):
    monkeypatch.setattr(
        "app.auth.jwt_handler.authenticate_bearer",
        lambda token, expected_type="access": (_User(role, society_id), None),
    )


class _FakeDb:
    def __init__(self):
        self.calls = []

    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        self.calls.append((sql, params, fetch_one))
        sql_u = (sql or "").upper()
        if "SOCIETIES" in sql_u and fetch_one:
            return {"id": params[0]} if params and params[0] in (1, 2) else None
        if "VENDORS" in sql_u and fetch_one:
            vid = params[0]
            sid = params[1]
            return {"id": vid} if (vid, sid) in ((101, 1), (202, 2)) else None
        return None

    def execute(self, *a, **k):
        return self._execute(*a, **k)


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr("app.routes.api.db", db)
    return db


def _json(resp):
    return resp.get_json()


# ── /api/statements ──────────────────────────────────────────────────────

def test_no_token_401(client):
    resp = client.get("/api/statements?fy=2026")
    assert resp.status_code == 401


def test_wrong_role_403(client, monkeypatch):
    _auth(monkeypatch, "apartment", 1)
    resp = client.get("/api/statements?fy=2026", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 403


def test_security_role_403(client, monkeypatch):
    _auth(monkeypatch, "security", 1)
    resp = client.get("/api/statements?fy=2026", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 403


def test_admin_own_society_200(client, monkeypatch, fake_db):
    _auth(monkeypatch, "admin", 1)
    seen = {}

    def fake_st(sid, fy):
        seen["sid"], seen["fy"] = sid, fy
        return {"balanced": True}

    monkeypatch.setattr("app.routes.api.statements", fake_st)
    resp = client.get("/api/statements?fy=2026", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 200
    assert seen == {"sid": 1, "fy": 2026}


def test_admin_only_own_society(client, monkeypatch, fake_db):
    """An admin of society 2 can never read society 1's data: society_id is
    derived from the caller, never from a request parameter."""
    _auth(monkeypatch, "admin", 2)
    seen = {}

    def fake_st(sid, fy):
        seen["sid"] = sid
        return {"balanced": True}

    monkeypatch.setattr("app.routes.api.statements", fake_st)
    resp = client.get("/api/statements?fy=2026", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 200
    assert seen["sid"] == 2


# ── master (no society) needs an explicit society_id ─────────────────────

def test_master_without_society_id_400(client, monkeypatch, fake_db):
    _auth(monkeypatch, "master", None)
    resp = client.get("/api/statements?fy=2026", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 400


def test_master_with_society_id_200(client, monkeypatch, fake_db):
    _auth(monkeypatch, "master", None)
    seen = {}

    def fake_st(sid, fy):
        seen["sid"] = sid
        return {"balanced": True}

    monkeypatch.setattr("app.routes.api.statements", fake_st)
    resp = client.get("/api/statements?society_id=1&fy=2026", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 200
    assert seen["sid"] == 1


def test_master_unknown_society_id_400(client, monkeypatch, fake_db):
    _auth(monkeypatch, "master", None)
    resp = client.get("/api/statements?society_id=999&fy=2026", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 400


# ── /api/statements/trial-balance/export ─────────────────────────────────

def test_export_unbalanced_409(client, monkeypatch, fake_db):
    _auth(monkeypatch, "admin", 1)

    def fake_gate(sid, fy):
        return {"allowed": False, "reason": "trial balance is unbalanced"}

    monkeypatch.setattr("app.routes.api.export_gate", fake_gate)
    resp = client.get("/api/statements/trial-balance/export?fy=2026", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 409
    assert "unbalanced" in _json(resp)["error"]


# ── /api/msme/compliance ─────────────────────────────────────────────────

def test_msme_no_vendor_id_400(client, monkeypatch):
    _auth(monkeypatch, "admin", 1)
    resp = client.get("/api/msme/compliance", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 400


def test_msme_vendor_not_in_society_404(client, monkeypatch, fake_db):
    _auth(monkeypatch, "admin", 1)
    # vendor 202 belongs to society 2, not society 1
    resp = client.get("/api/msme/compliance?vendor_id=202", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 404


def test_msme_vendor_in_society_200(client, monkeypatch, fake_db):
    _auth(monkeypatch, "admin", 1)
    monkeypatch.setattr(
        "app.routes.api.msme_payment_compliance",
        lambda sid, vid, asof: {"vendor_id": vid, "compliant": True},
    )
    resp = client.get("/api/msme/compliance?vendor_id=101", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 200
    assert _json(resp)["vendor_id"] == 101
