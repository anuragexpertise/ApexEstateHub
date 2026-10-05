"""
Master "create society" is atomic and reports a readable reason (onboarding audit).

Real Postgres only (test/live_db_gate.py). Uses unique names and removes what it creates.
"""
import uuid

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

pytestmark = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)


@pytest.fixture()
def made():
    ids = []
    yield ids
    from database.db_manager import db
    for sid in ids:
        db._execute("DELETE FROM users WHERE society_id = %s", (sid,))
        db._execute("DELETE FROM societies WHERE id = %s", (sid,))


def _data(tag, **kw):
    d = {"name": f"Soc {tag}", "address": "A", "pan": "ABCDE1234F", "reg_num": "R1",
         "plan": "Free", "validity": "2027-03-31",
         "admin_email": f"adm_{tag}@example.com", "admin_password": "Passw0rd!"}
    d.update(kw)
    return d


def test_creates_society_and_admin_together(made):
    from app.services.society_service import create_society_checked
    from database.db_manager import db
    tag = uuid.uuid4().hex[:8]
    sid = create_society_checked(_data(tag))
    made.append(sid)
    u = db._execute("SELECT role, society_id, must_change_password FROM users WHERE email = %s",
                    (f"adm_{tag}@example.com",), fetch_one=True)
    assert u["role"] == "admin" and u["society_id"] == sid and u["must_change_password"] is True


def test_duplicate_admin_email_creates_nothing(made):
    from app.services.society_service import create_society_checked, SocietyCreateError
    from database.db_manager import db
    tag = uuid.uuid4().hex[:8]
    made.append(create_society_checked(_data(tag)))
    with pytest.raises(SocietyCreateError, match="already registered"):
        create_society_checked(_data(tag + "b", admin_email=f"adm_{tag}@example.com"))
    assert db._execute("SELECT 1 FROM societies WHERE name = %s", (f"Soc {tag}b",), fetch_one=True) is None


def test_duplicate_society_name_has_clear_message(made):
    from app.services.society_service import create_society_checked, SocietyCreateError
    tag = uuid.uuid4().hex[:8]
    made.append(create_society_checked(_data(tag)))
    with pytest.raises(SocietyCreateError, match="already exists"):
        create_society_checked(_data(tag, admin_email=f"other_{tag}@example.com"))


def test_legacy_wrapper_still_returns_none_on_rejection(made):
    from app.services.society_service import create_society, create_society_checked
    tag = uuid.uuid4().hex[:8]
    made.append(create_society_checked(_data(tag)))
    assert create_society(_data(tag, admin_email=f"x_{tag}@example.com")) is None


def test_admin_email_is_lowercased_and_login_is_case_insensitive(made):
    from app.services.society_service import create_society_checked, SocietyCreateError
    from app.services.auth_service import authenticate_user
    from database.db_manager import db
    tag = uuid.uuid4().hex[:8]
    sid = create_society_checked(_data(tag, admin_email=f"  Adm_{tag}@Example.COM "))
    made.append(sid)
    stored = db._execute("SELECT email FROM users WHERE society_id = %s", (sid,), fetch_one=True)["email"]
    assert stored == f"adm_{tag}@example.com"
    assert authenticate_user(f"ADM_{tag}@example.com", "Passw0rd!", sid)
    with pytest.raises(SocietyCreateError, match="already registered"):
        create_society_checked(_data(tag + "b", admin_email=f"ADM_{tag}@example.com"))


def test_bulk_reupload_keeps_enrolled_rows_and_tables_errors(made):
    from app.services.society_service import create_society_checked
    from app.dash_apps.callbacks import bulk_enroll_callbacks as be
    from database.db_manager import db
    tag = uuid.uuid4().hex[:8]
    sid = create_society_checked(_data(tag))
    made.append(sid)

    def row(flat, email, owner, pw="Passw0rd!"):
        return {"flat_number": flat, "email": email, "password": pw, "owner_name": owner}

    first = be._bulk_insert_apartments(
        [row("A-1", f"a1_{tag}@x.com", "Asha"), row("A-2", f"A2_{tag}@x.com", "Bela", pw="short")], sid, None)
    assert first["success"] == 1 and len(first["failed"]) == 1
    assert first["failed"][0][0] == 3 and "8 characters" in first["failed"][0][1]

    # corrected file re-uploaded with A-1 changed in the sheet: A-1 must stay as first enrolled
    second = be._bulk_insert_apartments(
        [row("A-1", f"a1_{tag}@x.com", "CHANGED"), row("A-2", f"A2_{tag}@x.com", "Bela")], sid, None)
    assert second["success"] == 1 and second["failed"] == [] and len(second["skipped"]) == 1
    owner = db._execute("SELECT owner_name FROM apartments WHERE society_id=%s AND flat_number='A-1'",
                        (sid,), fetch_one=True)["owner_name"]
    assert owner == "Asha"
    assert db._execute("SELECT email FROM users WHERE society_id=%s AND linked_id IS NOT NULL ORDER BY id",
                       (sid,), fetch_all=True)[1]["email"] == f"a2_{tag}@x.com"

    # the on-screen result is a table of the rows to fix
    html = str(be._render_results({"success": 0, "failed": first["failed"], "skipped": []}, "f.xlsx"))
    assert "Table" in html and "What to fix" in html
