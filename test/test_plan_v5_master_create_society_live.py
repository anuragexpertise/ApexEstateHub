"""Plan v5.2 (real Postgres): a society created from the master form's payload lands registered, with its regime inputs and
a certificate hash that the stored file proves."""
import hashlib
import uuid

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

pytestmark = [pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON), pytest.mark.postgres_integration]

PDF = b"%PDF-1.4\n" + b"live certificate " * 40


def test_master_form_payload_creates_a_registered_society(tmp_path, monkeypatch):
    from app.services import society_service as ss
    from database.db_manager import db
    monkeypatch.setattr(ss, "_cert_folder", lambda: tmp_path / "registration")
    tag = uuid.uuid4().hex[:8]
    stored, digest = ss.store_registration_certificate("reg.pdf", PDF + tag.encode())
    form = {"name": f"Master Form {tag}", "address": "Agra", "pan": "ABCDE1234F", "registration": f"REG/{tag}",
            "state": "MH", "constitution": "COOP", "validity_date": "2027-03-31", "plan": "Free",
            "admin_username": f"admin-{tag}@example.in", "admin_password": "Str0ngPass!",
            "reg_cert_file": stored, "reg_cert_hash": digest}
    sid = ss.create_society_checked(ss.payload_from_master_form(form, created_by=None))
    row = db._execute("SELECT state, constitution, registration_certificate_hash AS h, onboarding_state FROM societies WHERE id=%s",
                      (sid,), fetch_one=True)
    assert (row["state"], row["constitution"], row["onboarding_state"]) == ("MH", "COOP", "registered")
    assert row["h"] == digest == hashlib.sha256(PDF + tag.encode()).hexdigest()
    assert db._execute("SELECT count(*) n FROM users WHERE society_id=%s AND role='admin'", (sid,), fetch_one=True)["n"] == 1
