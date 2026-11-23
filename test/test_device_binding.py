"""PIN / pattern sign-in is bound to trusted devices — the parts that need no database.

The SQL itself (atomic attempt counting, revocation, the password-login rules) is covered against a real Postgres in
test_device_binding_live.py. Here: input validation, what the sign-in screen renders, the cookie attributes, and that
authenticate_pin / authenticate_pattern refuse without a trusted device and never touch the account's lockout counter.
"""
import pytest
from flask import Flask
from werkzeug.security import generate_password_hash

from app.services import auth_service, device_service


# ── validation ──────────────────────────────────────────────────

@pytest.mark.parametrize("pin", ["7391", "48201", "2580", "902417"])
def test_acceptable_pins(pin):
    assert auth_service.validate_pin(pin) is None


@pytest.mark.parametrize("pin", ["", "12", "1234567", "12a4", "1111", "1234", "4321", "123456", "1212", "123123"])
def test_rejected_pins(pin):
    assert auth_service.validate_pin(pin)


@pytest.mark.parametrize("raw,canonical", [("1-4-5-9", "1-4-5-9"), (" 3-5-7-8 ", "3-5-7-8"), ("1-2-3-4-5-6-7-8-9", "1-2-3-4-5-6-7-8-9")])
def test_valid_patterns(raw, canonical):
    assert auth_service.normalize_pattern(raw) == canonical


@pytest.mark.parametrize("raw", [None, "", "1-2-3", "1-1-2-3", "1-2-3-0", "a-b-c-d", "12-3-4-5", "1,2,3,4"])
def test_invalid_patterns(raw):
    assert auth_service.normalize_pattern(raw) is None


# ── what the sign-in screen shows ───────────────────────────────

def _ids(node, acc):
    if isinstance(node, (list, tuple)):
        for n in node:
            _ids(n, acc)
    elif node is not None and not isinstance(node, (str, int, float)):
        if getattr(node, "id", None):
            acc.add(node.id)
        _ids(getattr(node, "children", None), acc)
    return acc


def test_new_device_sees_only_the_password_form():
    from app.dash_apps.pages.login_system import login_layout
    ids = _ids(login_layout("Society"), set())
    assert {"login-email", "login-password", "remember-device-checkbox"} <= ids
    assert not ids & {"login-pin", "login-pattern", "pattern-grid"}


def test_trusted_device_gets_its_quick_methods_and_the_email():
    from app.dash_apps.pages.login_system import login_layout
    layout = login_layout("Society", None, {"email": "a@b.c", "has_pin": True, "has_pattern": True})
    assert {"login-pin", "login-pattern", "pattern-grid", "login-password"} <= _ids(layout, set())
    tabs = next(c for c in layout[0].children if getattr(c, "id", None) == "login-method-tabs")
    assert tabs.active_tab == "tab-pin"
    assert [t.tab_id for t in tabs.children][-1] == "tab-password"


def test_pattern_pad_markup_matches_what_pattern_js_looks_for():
    """pattern.js once looked for a canvas / .pattern-dot / data-dot-num that the layout did not render."""
    from app.dash_apps.pages.login_system import pattern_pad
    pad = pattern_pad("p", "in", "clr", "prev", confirm_input_id="conf").to_plotly_json()["props"]
    assert pad["className"] == "pattern-pad"
    assert pad["data-input-id"] == "in" and pad["data-clear-id"] == "clr" and pad["data-confirm-id"] == "conf"
    kids = pad["children"]
    assert kids[0].className == "pattern-canvas"
    dots = kids[1:]
    assert [d.className for d in dots] == ["pattern-dot"] * 9
    assert [d.to_plotly_json()["props"]["data-dot-num"] for d in dots] == [str(i) for i in range(1, 10)]


# ── cookie ──────────────────────────────────────────────────────

def _app():
    return Flask(__name__)


def test_device_cookie_is_httponly_lax_and_path_wide():
    app = _app()
    with app.test_request_context("/"):
        device_service.set_cookie("tok123")
        resp = app.process_response(app.response_class("ok"))
    cookie = resp.headers["Set-Cookie"]
    assert cookie.startswith("eh_device=tok123")
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie and "Path=/" in cookie and "Max-Age=7776000" in cookie


def test_clear_cookie_expires_it():
    app = _app()
    with app.test_request_context("/"):
        device_service.clear_cookie()
        resp = app.process_response(app.response_class("ok"))
    assert "eh_device=;" in resp.headers["Set-Cookie"] and "Expires=Thu, 01 Jan 1970" in resp.headers["Set-Cookie"]


def test_current_token_reads_the_cookie_and_ignores_absurd_values():
    app = _app()
    with app.test_request_context("/", headers={"Cookie": "eh_device=abc"}):
        assert device_service.current_token() == "abc"
    with app.test_request_context("/", headers={"Cookie": "eh_device=" + "x" * 500}):
        assert device_service.current_token() is None
    with app.test_request_context("/"):
        assert device_service.current_token() is None


# ── authenticate_* gating ───────────────────────────────────────

def _seed(patched_db, pin="7391", pattern="1-4-5-9"):
    patched_db.tables.setdefault("users", []).append({
        "id": 10, "email": "u@test.com", "role": "admin", "society_id": 1, "linked_id": None,
        "password_hash": generate_password_hash("Pass1234"),
        "pin_hash": generate_password_hash(pin) if pin else None,
        "pattern_hash": generate_password_hash(pattern) if pattern else None,
        "failed_login_attempts": 0, "locked_until": None,
        "reset_token": None, "reset_token_expires": None,
    })


@pytest.fixture
def device(monkeypatch):
    """A stand-in device table: token 'good' is trusted for user 10 and may fail 3 times."""
    calls = {"claims": 0, "success": 0, "revoked": []}

    def claim(token, user_id):
        calls["claims"] += 1
        if token == "good" and user_id == 10:
            return {"id": 5, "user_id": 10, "failed_attempts": 1}
        return None
    monkeypatch.setattr(device_service, "claim_attempt", claim)
    monkeypatch.setattr(device_service, "mark_success", lambda _id: calls.__setitem__("success", calls["success"] + 1))
    monkeypatch.setattr(device_service, "revoke_by_id", lambda _id: calls["revoked"].append(_id))
    return calls


def test_pin_works_on_a_trusted_device(patched_db, device):
    _seed(patched_db)
    auth = auth_service.authenticate_pin("u@test.com", "7391", 1, device_token="good")
    assert auth and auth["user_id"] == 10
    assert device["success"] == 1


def test_pin_refused_without_a_trusted_device(patched_db, device):
    _seed(patched_db)
    assert auth_service.authenticate_pin("u@test.com", "7391", 1, device_token=None) is None
    assert auth_service.authenticate_pin("u@test.com", "7391", 1, device_token="someone-elses") is None


def test_wrong_pin_never_feeds_the_account_lockout(patched_db, device):
    _seed(patched_db)
    for _ in range(8):
        assert auth_service.authenticate_pin("u@test.com", "0042", 1, device_token="good") is None
    row = patched_db._execute("SELECT failed_login_attempts, locked_until FROM users WHERE id = :i", {"i": 10}, fetch_one=True)
    assert row["failed_login_attempts"] == 0 and row["locked_until"] is None


def test_device_is_untrusted_when_the_attempt_limit_is_reached(patched_db, monkeypatch, device):
    _seed(patched_db)
    monkeypatch.setattr(device_service, "claim_attempt",
                        lambda t, u: {"id": 5, "user_id": 10, "failed_attempts": device_service.MAX_DEVICE_FAILURES})
    assert auth_service.authenticate_pin("u@test.com", "0042", 1, device_token="good") is None
    assert device["revoked"] == [5]


def test_pin_not_set_is_not_an_attempt(patched_db, device):
    _seed(patched_db, pin=None)
    assert auth_service.authenticate_pin("u@test.com", "7391", 1, device_token="good") is None
    assert device["claims"] == 0


def test_malformed_input_is_not_an_attempt(patched_db, device):
    _seed(patched_db)
    assert auth_service.authenticate_pin("u@test.com", "12ab", 1, device_token="good") is None
    assert auth_service.authenticate_pattern("u@test.com", "1-2", 1, device_token="good") is None
    assert device["claims"] == 0


def test_pattern_works_on_a_trusted_device_and_is_canonicalised(patched_db, device):
    _seed(patched_db)
    assert auth_service.authenticate_pattern("u@test.com", " 1-4-5-9 ", 1, device_token="good")
    assert auth_service.authenticate_pattern("u@test.com", "9-5-4-1", 1, device_token="good") is None


def test_locked_account_refuses_quick_sign_in(patched_db, device):
    _seed(patched_db)
    for _ in range(5):
        auth_service.authenticate_user("u@test.com", "wrong", 1)
    assert auth_service.authenticate_pin("u@test.com", "7391", 1, device_token="good") is None
    assert device["claims"] == 0
