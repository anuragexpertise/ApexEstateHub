"""Device-bound PIN / pattern sign-in against a REAL Postgres: the atomic attempt counter, token lifecycle, the
password-login rules (other account's token removed, remember-this-device, multiple devices), manual sign-out touching
only one device, and password reset voiding PIN, pattern and devices. Needs the explicit opt-in (test/live_db_gate.py):

    ESTATEHUB_LIVE_TESTS=1 PGHOST=... PGDATABASE=... PGUSER=... PGPASSWORD=... pytest test/test_device_binding_live.py

It creates a throwaway society with two logins and removes it afterwards (which also proves the ON DELETE CASCADE).
"""
import threading

import pytest
from flask import Flask

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

pytestmark = [pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON), pytest.mark.postgres_integration]

psycopg2 = pytest.importorskip("psycopg2")

PASSWORD = "Str0ng!Pass1"


@pytest.fixture
def world():
    from werkzeug.security import generate_password_hash

    from database.db_manager import db
    if not db._execute("SELECT to_regclass('user_devices') AS t", fetch_one=True)["t"]:
        pytest.skip("user_devices is not installed in this database (database/migrations/013_user_devices.sql)")
    sid = db._execute("INSERT INTO societies (name) VALUES ('Device Test Society') RETURNING id", fetch_one=True)["id"]
    users = {}
    for key in ("alice", "bob"):
        users[key] = db._execute(
            "INSERT INTO users (email, password_hash, role, society_id, pin_hash, pattern_hash, must_change_password) "
            "VALUES (%s, %s, 'admin', %s, %s, %s, FALSE) RETURNING id",
            (f"{key}-{sid}@example.test", generate_password_hash(PASSWORD), sid,
             generate_password_hash("7391"), generate_password_hash("1-4-5-9")), fetch_one=True)["id"]
    yield {"sid": sid, "alice": users["alice"], "bob": users["bob"],
           "alice_email": f"alice-{sid}@example.test", "bob_email": f"bob-{sid}@example.test", "db": db}
    db._execute("DELETE FROM societies WHERE id = %s", (sid,))
    leftovers = db._execute("SELECT count(*) AS n FROM user_devices WHERE user_id = ANY(%s)",
                            ([users["alice"], users["bob"]],), fetch_one=True)["n"]
    assert leftovers == 0, "ON DELETE CASCADE should have removed the devices with their users"


class Browser:
    """One browser: keeps its device cookie between requests, like the real thing."""

    def __init__(self):
        self.app = Flask(__name__)
        self.cookie = None

    def request(self, fn):
        headers = {"Cookie": f"eh_device={self.cookie}"} if self.cookie else {}
        with self.app.test_request_context("/", headers=headers):
            out = fn()
            resp = self.app.process_response(self.app.response_class("ok"))
        for header in resp.headers.getlist("Set-Cookie"):
            if header.startswith("eh_device="):
                value = header.split(";", 1)[0].split("=", 1)[1]
                self.cookie = value or None
        return out


def device_count(world, user):
    return world["db"]._execute("SELECT count(*) AS n FROM user_devices WHERE user_id = %s",
                                (world[user],), fetch_one=True)["n"]


def test_password_login_with_remember_trusts_the_browser_and_pin_then_works(world):
    from app.services import auth_service, device_service
    b = Browser()
    assert b.request(lambda: auth_service.authenticate_pin(world["alice_email"], "7391", world["sid"])) is None   # new device
    b.request(lambda: device_service.after_password_login(world["alice"], remember=True))
    assert b.cookie and device_count(world, "alice") == 1
    stored = world["db"]._execute("SELECT token_hash FROM user_devices WHERE user_id = %s", (world["alice"],), fetch_one=True)
    assert stored["token_hash"] == device_service.hash_token(b.cookie) and stored["token_hash"] != b.cookie
    assert b.request(lambda: auth_service.authenticate_pin(world["alice_email"], "7391", world["sid"]))["user_id"] == world["alice"]
    assert b.request(lambda: auth_service.authenticate_pattern(world["alice_email"], "1-4-5-9", world["sid"]))


def test_without_remember_nothing_is_trusted(world):
    from app.services import auth_service, device_service
    b = Browser()
    b.request(lambda: device_service.after_password_login(world["alice"], remember=False))
    assert b.cookie is None and device_count(world, "alice") == 0
    assert b.request(lambda: auth_service.authenticate_pin(world["alice_email"], "7391", world["sid"])) is None


def test_a_stranger_cannot_use_a_pin_for_someone_elses_account_and_costs_nothing(world):
    from app.services import auth_service, device_service
    victim_browser, stranger = Browser(), Browser()
    victim_browser.request(lambda: device_service.after_password_login(world["alice"], remember=True))
    for _ in range(20):                                             # a stranger hammering the PIN tab for alice
        assert stranger.request(lambda: auth_service.authenticate_pin(world["alice_email"], "0042", world["sid"])) is None
    row = world["db"]._execute("SELECT failed_login_attempts, locked_until FROM users WHERE id = %s", (world["alice"],), fetch_one=True)
    assert row["failed_login_attempts"] == 0 and row["locked_until"] is None     # no lockout-DoS
    assert victim_browser.request(lambda: auth_service.authenticate_pin(world["alice_email"], "7391", world["sid"]))


def test_bobs_device_cannot_sign_in_as_alice(world):
    from app.services import auth_service, device_service
    b = Browser()
    b.request(lambda: device_service.after_password_login(world["bob"], remember=True))
    assert b.request(lambda: auth_service.authenticate_pin(world["alice_email"], "7391", world["sid"])) is None
    assert b.request(lambda: auth_service.authenticate_pin(world["bob_email"], "7391", world["sid"]))


def test_five_wrong_pins_untrust_the_device_and_the_right_pin_no_longer_works(world):
    from app.services import auth_service, device_service
    b = Browser()
    b.request(lambda: device_service.after_password_login(world["alice"], remember=True))
    for _ in range(device_service.MAX_DEVICE_FAILURES):
        assert b.request(lambda: auth_service.authenticate_pin(world["alice_email"], "0042", world["sid"])) is None
    assert device_count(world, "alice") == 0
    assert b.request(lambda: auth_service.authenticate_pin(world["alice_email"], "7391", world["sid"])) is None
    # ...and the password route still works, and can trust the device again
    assert auth_service.authenticate_user(world["alice_email"], PASSWORD, world["sid"])
    b.request(lambda: device_service.after_password_login(world["alice"], remember=True))
    assert b.request(lambda: auth_service.authenticate_pin(world["alice_email"], "7391", world["sid"]))


def test_a_correct_pin_gives_the_attempts_back(world):
    from app.services import auth_service, device_service
    b = Browser()
    b.request(lambda: device_service.after_password_login(world["alice"], remember=True))
    for _ in range(device_service.MAX_DEVICE_FAILURES - 1):
        b.request(lambda: auth_service.authenticate_pin(world["alice_email"], "0042", world["sid"]))
    assert b.request(lambda: auth_service.authenticate_pin(world["alice_email"], "7391", world["sid"]))
    n = world["db"]._execute("SELECT failed_attempts FROM user_devices WHERE user_id = %s", (world["alice"],), fetch_one=True)["failed_attempts"]
    assert n == 0


def test_parallel_guesses_cannot_exceed_the_attempt_limit(world):
    """The counter is a single guarded UPDATE: however many requests race, at most MAX_DEVICE_FAILURES get to compare."""
    from app.services import device_service
    b = Browser()
    token = b.request(lambda: device_service.after_password_login(world["alice"], remember=True))
    granted, lock = [], threading.Lock()

    def attempt():
        row = device_service.claim_attempt(token, world["alice"])
        with lock:
            granted.append(bool(row))
    threads = [threading.Thread(target=attempt) for _ in range(40)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(granted) == device_service.MAX_DEVICE_FAILURES


def test_signing_in_with_a_password_as_another_account_removes_the_old_token_only_there(world):
    from app.services import device_service
    shared, alice_phone = Browser(), Browser()
    alice_phone.request(lambda: device_service.after_password_login(world["alice"], remember=True))
    shared.request(lambda: device_service.after_password_login(world["alice"], remember=True))
    assert device_count(world, "alice") == 2
    shared.request(lambda: device_service.after_password_login(world["bob"], remember=False))   # bob signs in on that browser
    assert device_count(world, "alice") == 1 and shared.cookie is None                          # its token gone, cookie cleared
    assert device_count(world, "bob") == 0                                                       # remember was off
    assert device_service.lookup(alice_phone.cookie)                                             # alice's phone untouched


def test_manual_sign_out_removes_only_this_devices_token(world):
    from app.services import auth_service, device_service
    phone, laptop = Browser(), Browser()
    phone.request(lambda: device_service.after_password_login(world["alice"], remember=True))
    laptop.request(lambda: device_service.after_password_login(world["alice"], remember=True))
    assert device_count(world, "alice") == 2
    laptop.request(device_service.sign_out_this_device)
    assert laptop.cookie is None and device_count(world, "alice") == 1
    assert laptop.request(lambda: auth_service.authenticate_pin(world["alice_email"], "7391", world["sid"])) is None
    assert phone.request(lambda: auth_service.authenticate_pin(world["alice_email"], "7391", world["sid"]))


def test_many_devices_per_account_and_remember_twice_reuses_the_token(world):
    from app.services import device_service
    a, b = Browser(), Browser()
    a.request(lambda: device_service.after_password_login(world["alice"], remember=True))
    first = a.cookie
    b.request(lambda: device_service.after_password_login(world["alice"], remember=True))
    a.request(lambda: device_service.after_password_login(world["alice"], remember=True))
    assert device_count(world, "alice") == 2 and a.cookie == first and a.cookie != b.cookie


def test_expired_device_is_not_trusted(world):
    from app.services import auth_service, device_service
    b = Browser()
    b.request(lambda: device_service.after_password_login(world["alice"], remember=True))
    world["db"]._execute("UPDATE user_devices SET expires_at = NOW() - INTERVAL '1 minute' WHERE user_id = %s", (world["alice"],))
    assert b.request(lambda: auth_service.authenticate_pin(world["alice_email"], "7391", world["sid"])) is None
    assert b.request(lambda: device_service.trusted_user(world["sid"])) is None


def test_trusted_user_feeds_the_sign_in_screen_and_respects_society_and_active(world):
    from app.services import device_service
    b = Browser()
    b.request(lambda: device_service.after_password_login(world["alice"], remember=True))
    got = b.request(lambda: device_service.trusted_user(world["sid"]))
    assert got == {"email": world["alice_email"], "has_pin": True, "has_pattern": True}
    assert b.request(lambda: device_service.trusted_user(world["sid"] + 9999)) is None        # a different society
    world["db"]._execute("UPDATE users SET active = FALSE WHERE id = %s", (world["alice"],))
    assert b.request(lambda: device_service.trusted_user(world["sid"])) is None               # login switched off


def test_password_reset_clears_pin_pattern_and_every_device(world):
    import hashlib

    from app.services import auth_service, device_service
    phone, laptop = Browser(), Browser()
    phone.request(lambda: device_service.after_password_login(world["alice"], remember=True))
    laptop.request(lambda: device_service.after_password_login(world["alice"], remember=True))
    plain = "reset-token-for-test"
    world["db"]._execute("UPDATE users SET reset_token = %s, reset_token_expires = NOW() + INTERVAL '1 hour' WHERE id = %s",
                         (hashlib.sha256(plain.encode()).hexdigest(), world["alice"]))
    ok, _ = auth_service.reset_password(plain, "An0ther!Passw0rd")
    assert ok
    row = world["db"]._execute("SELECT pin_hash, pattern_hash FROM users WHERE id = %s", (world["alice"],), fetch_one=True)
    assert row["pin_hash"] is None and row["pattern_hash"] is None
    assert device_count(world, "alice") == 0
    assert phone.request(lambda: auth_service.authenticate_pin(world["alice_email"], "7391", world["sid"])) is None
    # bob is unaffected
    assert world["db"]._execute("SELECT pin_hash FROM users WHERE id = %s", (world["bob"],), fetch_one=True)["pin_hash"]


def test_set_pin_needs_the_current_password_and_validates(world):
    from app.services import auth_service
    ok, _ = auth_service.set_pin(world["alice"], "wrong-password", "5826")
    assert not ok
    ok, msg = auth_service.set_pin(world["alice"], PASSWORD, "1234")
    assert not ok and "simple run" in msg
    ok, _ = auth_service.set_pin(world["alice"], PASSWORD, "5826")
    assert ok
    b = Browser()
    from app.services import device_service
    b.request(lambda: device_service.after_password_login(world["alice"], remember=True))
    assert b.request(lambda: auth_service.authenticate_pin(world["alice_email"], "5826", world["sid"]))
    assert b.request(lambda: auth_service.authenticate_pin(world["alice_email"], "7391", world["sid"])) is None   # replaced


def test_set_pattern_and_disable_quick_signin(world):
    from app.services import auth_service, device_service
    ok, _ = auth_service.set_pattern(world["alice"], PASSWORD, "1-2")
    assert not ok
    ok, _ = auth_service.set_pattern(world["alice"], PASSWORD, "3-5-7-8")
    assert ok
    b = Browser()
    b.request(lambda: device_service.after_password_login(world["alice"], remember=True))
    assert b.request(lambda: auth_service.authenticate_pattern(world["alice_email"], "3-5-7-8", world["sid"]))
    ok, _ = auth_service.disable_quick_signin(world["alice"], "wrong-password")
    assert not ok and device_count(world, "alice") == 1
    ok, _ = auth_service.disable_quick_signin(world["alice"], PASSWORD)
    assert ok and device_count(world, "alice") == 0
    row = world["db"]._execute("SELECT pin_hash, pattern_hash FROM users WHERE id = %s", (world["alice"],), fetch_one=True)
    assert row["pin_hash"] is None and row["pattern_hash"] is None


@pytest.mark.parametrize("how", ["reset_password", "update_member"])
def test_team_service_admin_set_password_voids_quick_signin(world, how):
    """An admin-set password (team_service) is a reset too."""
    from app.services import device_service, team_service
    world["db"]._execute("UPDATE users SET role = 'accountant' WHERE id = %s", (world["bob"],))
    b = Browser()
    b.request(lambda: device_service.after_password_login(world["bob"], remember=True))
    assert device_count(world, "bob") == 1
    if how == "reset_password":
        ok, msg = team_service.reset_password(world["alice"], "admin", world["sid"], world["bob"], "Fresh!Passw0rd9", world["sid"])
    else:
        ok, msg = team_service.update_member(world["alice"], "admin", world["sid"], world["bob"],
                                             new_password="Fresh!Passw0rd9", actor_society_id=world["sid"])
    assert ok, msg
    row = world["db"]._execute("SELECT pin_hash, pattern_hash FROM users WHERE id = %s", (world["bob"],), fetch_one=True)
    assert row["pin_hash"] is None and row["pattern_hash"] is None and device_count(world, "bob") == 0
