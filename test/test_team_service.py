"""Hermetic tests for Team Logins: validation, scoping, and that a disabled login cannot sign in."""
import pytest

from app.services import team_service as ts


class _Cur:
    def __init__(self, db):
        self.db, self.last = db, None

    def execute(self, sql, params=None):
        self.db.calls.append((sql, params))
        self.last = sql

    def fetchone(self):
        if "lower(email) = %s" in (self.last or ""):
            return {"x": 1} if self.db.email_taken else None
        if "INSERT INTO users" in (self.last or ""):
            return {"id": 77}
        if "FROM role_definitions" in (self.last or ""):
            return {"id": 5}
        return None


class _Conn:
    def __init__(self, db): self.db = db
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def cursor(self): return _Cur(self.db)


class _DB:
    def __init__(self, member=None, email_taken=False):
        self.calls, self.member, self.email_taken = [], member, email_taken

    def _conn(self): return _Conn(self)

    def _execute(self, *a, **k):
        return self.execute(*a, **k)

    def execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        self.calls.append((sql, params))
        return self.member if fetch_one else []


@pytest.fixture
def mk(monkeypatch):
    def make(**kw):
        d = _DB(**kw)
        monkeypatch.setattr(ts, "db", d)
        return d
    return make


def test_only_the_admin_of_the_same_society_may_create(mk):
    mk()
    with pytest.raises(PermissionError):
        ts.create_login(1, "admin", 5, "auditor", "A", "a@x.com", "longpassword", actor_society_id=6)
    with pytest.raises(PermissionError):
        ts.create_login(1, "apartment", 5, "auditor", "A", "a@x.com", "longpassword", actor_society_id=5)
    with pytest.raises(PermissionError):
        ts.create_login(1, "master", 5, "auditor", "A", "a@x.com", "longpassword", actor_society_id=None)


@pytest.mark.parametrize("role,name,email,pw", [
    ("admin", "A", "a@x.com", "longpassword"),        # not a team role: no way to mint an admin here
    ("vendor", "A", "a@x.com", "longpassword"),
    ("auditor", "", "a@x.com", "longpassword"),
    ("auditor", "A", "not-an-email", "longpassword"),
    ("auditor", "A", "a@x.com", "short"),
])
def test_bad_input_is_refused_and_nothing_is_written(mk, role, name, email, pw):
    d = mk()
    ok, _msg = ts.create_login(1, "admin", 5, role, name, email, pw, actor_society_id=5)
    assert ok is False
    assert not any("INSERT" in sql for sql, _ in d.calls)


def test_duplicate_email_is_refused(mk):
    d = mk(email_taken=True)
    ok, msg = ts.create_login(1, "admin", 5, "staff", "S", "s@x.com", "longpassword", actor_society_id=5)
    assert ok is False and "already" in msg
    assert not any("INSERT INTO users" in sql for sql, _ in d.calls)


@pytest.mark.parametrize("role", ts.ROLE_CODES)
def test_create_makes_a_scoped_hashed_must_change_login(mk, role):
    d = mk()
    ok, _ = ts.create_login(9, "admin", 5, role, " Asha ", " ASHA@X.com ", "longpassword", actor_society_id=5)
    assert ok
    sql, params = next(c for c in d.calls if "INSERT INTO users" in c[0])
    assert "must_change_password" in sql and "TRUE" in sql
    sid, email, pwhash, r, name, by = params
    assert (sid, email, r, name, by) == (5, "asha@x.com", role, "Asha", 9)
    assert pwhash != "longpassword" and pwhash.startswith(("scrypt:", "pbkdf2:"))
    assert any("user_role_assignments" in s for s, _ in d.calls) == (role == "accountant")


def test_manage_only_reaches_team_logins_of_own_society(mk):
    d = mk(member=None)                         # not found: foreign society, or not a team role
    assert ts.set_active(1, "admin", 5, 99, False, actor_society_id=5) == (False, "That login was not found.")
    assert ts.reset_password(1, "admin", 5, 99, "longpassword", actor_society_id=5)[0] is False
    assert not any(s.lstrip().upper().startswith("UPDATE") for s, _ in d.calls)
    sql, params = d.calls[0]
    assert "society_id = %s" in sql and "role = ANY(%s)" in sql and params[1] == 5


def test_reset_validates_password_and_forces_change(mk):
    d = mk(member={"id": 3, "name": "N", "email": "n@x.com", "role": "staff", "active": True})
    assert ts.reset_password(1, "admin", 5, 3, "short", actor_society_id=5)[0] is False
    ok, _ = ts.reset_password(1, "admin", 5, 3, "longpassword", actor_society_id=5)
    assert ok
    sql, _ = next(c for c in d.calls if c[0].lstrip().upper().startswith("UPDATE"))
    assert "must_change_password = TRUE" in sql and "reset_token = NULL" in sql


def test_disable_sets_the_active_flag_not_a_lockout(mk):
    d = mk(member={"id": 3, "name": "N", "email": "n@x.com", "role": "auditor", "active": True})
    ok, msg = ts.set_active(1, "admin", 5, 3, False, actor_society_id=5)
    assert ok and "disabled" in msg
    sql, params = next(c for c in d.calls if c[0].lstrip().upper().startswith("UPDATE"))
    assert "active = %s" in sql and "locked_until" not in sql and params[0] is False


# ── a disabled login cannot sign in ──────────────────────────────────────────
def test_disabled_login_is_treated_as_unknown(monkeypatch):
    from app.services import auth_service as au
    monkeypatch.setattr(au, "_fetch_user_row", lambda e, s: {"id": 1, "active": False, "password_hash": "x"})
    assert au._fetch_user("a@x.com", 5) is None
    assert au.authenticate_user("a@x.com", "whatever", 5) is None
    monkeypatch.setattr(au, "_fetch_user_row", lambda e, s: {"id": 1, "active": True})
    assert au._fetch_user("a@x.com", 5)["id"] == 1


def test_disabled_user_ends_an_open_session(monkeypatch):
    from app.models import user as um
    monkeypatch.setattr(um, "active_select", lambda: ", active")
    row = {"id": 4, "email": "a@x.com", "role": "auditor", "society_id": 5, "linked_id": None,
           "is_master_admin": False, "active": False}
    monkeypatch.setattr(um.db, "_execute", lambda *a, **k: row)
    assert um.User.get(4) is None
    row["active"] = True
    assert um.User.get(4).role == "auditor"


def test_team_page_is_admin_only_and_has_the_form():
    from app.dash_apps.pages.team_page import team_tab
    assert "Only the society admin" in str(team_tab("auditor", 5))
    assert "Only the society admin" in str(team_tab("apartment", 5))
