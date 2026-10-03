# test/test_identity_hardening.py
"""
Regression tests for the identity/authorization hardening:

  * the Flask-Login session is the only identity authority for Dash callbacks;
  * JWTs are a thin carrier — role/society are re-resolved from the database
    on every request, refresh tokens are not accepted as access tokens, and
    the signing key fails closed in production;
  * every Dash callback is session-guarded (or explicitly allowlisted);
  * the "printed / emailed" stamp callbacks and the autofill lookup are
    tenant-scoped; polls can only be voted by the apartment portal.

No live database is needed: the user lookup is patched and the rest is
static/structural.
"""
import importlib
import re
import subprocess
import sys
import time
from pathlib import Path

import jwt
import pytest
from flask import Flask, jsonify, request

ROOT = Path(__file__).resolve().parent.parent
CALLBACKS = ROOT / "app" / "dash_apps" / "callbacks"


# ── helpers ───────────────────────────────────────────────────────────────

class _FakeUser:
    def __init__(self, uid, role, society_id=1, linked_id=None, email="u@x.in"):
        self.id, self.role, self.society_id = uid, role, society_id
        self.linked_id, self.email = linked_id, email


def _token(handler, **claims):
    now = int(time.time())
    payload = {"user_id": 7, "type": "access", "iat": now, "exp": now + 600}
    payload.update(claims)
    return jwt.encode(payload, handler.JWT_SECRET, algorithm="HS256")


@pytest.fixture()
def handler(monkeypatch):
    from app.auth import jwt_handler
    return jwt_handler


# ── JWT: re-resolve identity from the DB ──────────────────────────────────

def test_forged_role_claim_is_ignored(handler, monkeypatch):
    """A token claiming role=master / society 99 resolves to the DB's truth."""
    monkeypatch.setattr(handler.User, "get", staticmethod(
        lambda uid: _FakeUser(uid, "apartment", society_id=1, linked_id=5)))
    token = _token(handler, role="master", society_id=99)
    user, err = handler.authenticate_bearer(token)
    assert err is None
    assert (user.role, user.society_id, user.linked_id) == ("apartment", 1, 5)


def test_demotion_takes_effect_immediately(handler, monkeypatch):
    token = _token(handler, role="admin")
    monkeypatch.setattr(handler.User, "get", staticmethod(lambda uid: _FakeUser(uid, "admin")))
    assert handler.authenticate_bearer(token)[0].role == "admin"
    monkeypatch.setattr(handler.User, "get", staticmethod(lambda uid: _FakeUser(uid, "apartment")))
    assert handler.authenticate_bearer(token)[0].role == "apartment"


def test_deleted_user_is_rejected(handler, monkeypatch):
    monkeypatch.setattr(handler.User, "get", staticmethod(lambda uid: None))
    user, err = handler.authenticate_bearer(_token(handler))
    assert user is None and err == "User not found"


def test_refresh_token_is_not_an_access_token(handler, monkeypatch):
    monkeypatch.setattr(handler.User, "get", staticmethod(lambda uid: _FakeUser(uid, "admin")))
    user, err = handler.authenticate_bearer(_token(handler, type="refresh"))
    assert user is None and err == "Invalid token type"


def test_expired_and_tampered_tokens_rejected(handler, monkeypatch):
    monkeypatch.setattr(handler.User, "get", staticmethod(lambda uid: _FakeUser(uid, "admin")))
    expired = _token(handler, exp=int(time.time()) - 10)
    assert handler.authenticate_bearer(expired)[1] == "Token expired"
    other_key = jwt.encode({"user_id": 7, "type": "access", "exp": int(time.time()) + 600},
                           "not-the-secret-key-not-the-secret-key", algorithm="HS256")
    assert handler.authenticate_bearer(other_key)[1] == "Invalid token"
    no_exp = jwt.encode({"user_id": 7, "type": "access"}, handler.JWT_SECRET, algorithm="HS256")
    assert handler.authenticate_bearer(no_exp)[0] is None


def test_token_required_injects_db_user_and_role_required_uses_current_role(handler, monkeypatch):
    monkeypatch.setattr(handler.User, "get", staticmethod(lambda uid: _FakeUser(uid, "vendor", society_id=3)))
    app = Flask(__name__)

    @app.route("/whoami")
    @handler.token_required
    def whoami(current_user):
        return jsonify(role=current_user.role, society=current_user.society_id,
                       payload_role=request.user_payload["role"])

    @app.route("/admin-only")
    @handler.role_required(["admin"])
    def admin_only(current_user):
        return jsonify(ok=True)

    c = app.test_client()
    good = {"Authorization": "Bearer " + _token(handler, role="master", society_id=1)}
    r = c.get("/whoami", headers=good)
    assert r.status_code == 200 and r.json == {"role": "vendor", "society": 3, "payload_role": "vendor"}
    assert c.get("/whoami").status_code == 401
    # token says admin, database says vendor -> 403
    assert c.get("/admin-only", headers={"Authorization": "Bearer " + _token(handler, role="admin")}).status_code == 403


def test_signing_key_fails_closed_in_production(monkeypatch):
    from app.auth import jwt_handler
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.setenv("RENDER", "true")
    with pytest.raises(RuntimeError):
        importlib.reload(jwt_handler)
    # an explicit default value is just as unsafe
    monkeypatch.setenv("JWT_SECRET_KEY", "your-jwt-secret-key-change-this")
    with pytest.raises(RuntimeError):
        importlib.reload(jwt_handler)
    # a real key boots fine, and dev (no RENDER) only warns
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 48)
    importlib.reload(jwt_handler)
    monkeypatch.delenv("RENDER")
    monkeypatch.delenv("JWT_SECRET_KEY")
    importlib.reload(jwt_handler)          # restore the module for later tests


# ── Dash callbacks: guards + server identity ──────────────────────────────

def test_every_dash_callback_is_guarded_or_allowlisted():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_callback_guards.py")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_poll_create_ignores_browser_auth_store(monkeypatch):
    from app.dash_apps.callbacks import poll_callbacks as pc
    forged = {"user_id": 1, "society_id": 99, "role": "admin"}

    monkeypatch.setattr(pc, "get_current_user_id", lambda: None)
    monkeypatch.setattr(pc, "get_current_society_id", lambda: None)
    assert pc._require_auth(forged, required_role="admin")[2] is not None      # no server session

    monkeypatch.setattr(pc, "get_current_user_id", lambda: 4)
    monkeypatch.setattr(pc, "get_current_society_id", lambda: 2)
    monkeypatch.setattr(pc, "get_current_user_role", lambda: "apartment")
    assert pc._require_auth(forged, required_role="admin")[2] is not None      # forged admin, real apartment

    monkeypatch.setattr(pc, "get_current_user_role", lambda: "admin")
    uid, sid, err = pc._require_auth(forged, required_role="admin")
    assert (uid, sid, err) == (4, 2, None)                                     # society 2, never forged 99


def test_stamp_callbacks_are_tenant_scoped():
    """Every UPDATE of last_printed_at / last_emailed_at must filter by society."""
    seen = 0
    for f in CALLBACKS.glob("*.py"):
        src = f.read_text()
        for m in re.finditer(r'UPDATE\s+\w+\s+SET\s+last_(?:printed|emailed)_at\s*=\s*NOW\(\)[^"\']*', src):
            seen += 1
            assert "society_id" in m.group(0), f"{f.name}: unscoped stamp -> {m.group(0)!r}"
    assert seen == 10


def test_autofill_account_lookup_is_tenant_scoped():
    src = (CALLBACKS / "form_autofill_callbacks.py").read_text()
    assert "FROM accounts WHERE id = %s AND society_id = %s" in src


def test_setup_and_notification_callbacks_do_not_read_client_identity():
    setup = (CALLBACKS / "setup_wizard_callbacks.py").read_text()
    assert not re.search(r'auth\.get\(\s*["\'](?:user_id|society_id|role)["\']', setup)
    shell = (CALLBACKS / "shell_callbacks.py").read_text()
    notif = shell[shell.index("def _load_notifications("):shell.index("# ── 11. DRILL-BACK")]
    assert 'auth["user_id"]' not in notif


# ── voting rule: only the apartment portal votes ──────────────────────────

def test_only_apartment_owners_can_vote_per_database_function():
    sql = (ROOT / "database" / "estatehub.sql").read_text()
    body = sql[sql.index("CREATE OR REPLACE FUNCTION fn_cast_vote("):]
    body = body[:body.index("$$;", body.index("BEGIN"))]
    assert "v_user.role != 'apartment'" in body and "v_user.user_type != 'owner'" in body
    assert "UNIQUE (poll_id, apartment_id)" in sql           # one vote per apartment
