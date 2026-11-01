"""Plan v5.2 (real Postgres): a society created from the master form's payload lands registered, with its regime inputs and
no state or certificate yet (the society's wizard sets those)."""
import uuid

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

pytestmark = [pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON), pytest.mark.postgres_integration]

PDF = b"%PDF-1.4\n" + b"live certificate " * 40


def test_master_form_payload_creates_a_registered_society():
    from app.services import society_service as ss
    from database.db_manager import db
    tag = uuid.uuid4().hex[:8]
    form = {"name": f"Master Form {tag}", "address": "Agra", "pan": "ABCDE1234F", "registration": f"REG/{tag}",
            "validity_date": "2027-03-31", "plan": "Free",
            "admin_username": f"admin-{tag}@example.in", "admin_password": "Str0ngPass!"}
    sid = ss.create_society_checked(ss.payload_from_master_form(form, created_by=None))
    row = db._execute("SELECT state, constitution, registration_certificate_hash AS h, onboarding_state FROM societies WHERE id=%s",
                      (sid,), fetch_one=True)
    # State / certificate are left for the society's setup wizard; constitution takes its AOA default.
    assert (row["state"], row["constitution"], row["h"], row["onboarding_state"]) == (None, "AOA", None, "registered")
    assert db._execute("SELECT count(*) n FROM users WHERE society_id=%s AND role='admin'", (sid,), fetch_one=True)["n"] == 1
