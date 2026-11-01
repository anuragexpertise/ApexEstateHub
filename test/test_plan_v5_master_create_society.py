"""The master portal's Create Society form sets only name, address, PAN, registration number, plan and validity.
State, regime (constitution) and the registration certificate are completed by the society in its setup wizard."""
import hashlib

import pytest

from app.services import society_service as ss

PDF = b"%PDF-1.4\n" + b"certificate body " * 50


@pytest.fixture(autouse=True)
def _cert_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "_cert_folder", lambda: tmp_path / "registration")
    return tmp_path


# ── certificate storage and verification ─────────────────────────────────────────────────────────────────────────
def test_certificate_is_stored_under_its_own_sha256():
    stored, digest = ss.store_registration_certificate("Reg Cert.PDF", PDF)
    assert digest == hashlib.sha256(PDF).hexdigest() and stored == digest + ".pdf"
    assert ss.verify_registration_certificate(stored, digest) == digest


@pytest.mark.parametrize("name,data,why", [
    ("cert.exe", PDF, "PDF, PNG or JPG"),
    ("cert.pdf", b"not a pdf at all", "real PDF"),
    ("cert.pdf", b"", "between 1 byte and 5 MB"),
    ("cert.pdf", b"%PDF-" + b"x" * (5 * 1024 * 1024), "between 1 byte and 5 MB"),
])
def test_bad_certificate_files_are_refused_with_a_reason(name, data, why):
    with pytest.raises(ss.SocietyCreateError, match=why):
        ss.store_registration_certificate(name, data)


def test_a_forged_hash_or_filename_is_rejected():
    stored, digest = ss.store_registration_certificate("reg.pdf", PDF)
    with pytest.raises(ss.SocietyCreateError):
        ss.verify_registration_certificate(stored, "0" * 64)                     # right file, wrong hash
    with pytest.raises(ss.SocietyCreateError):
        ss.verify_registration_certificate("../../etc/passwd", digest)           # path games
    with pytest.raises(ss.SocietyCreateError):
        ss.verify_registration_certificate("", digest)
    (ss._cert_folder() / stored).write_bytes(b"%PDF-tampered")                   # file changed after upload
    with pytest.raises(ss.SocietyCreateError, match="does not match"):
        ss.verify_registration_certificate(stored, digest)


# ── form -> create_society_checked payload ───────────────────────────────────────────────────────────────────────
def _form(**over):
    """What the master's form submits: name, address, PAN, registration number, plan, validity, admin login."""
    f = {"name": "Sunrise Heights", "address": "Agra", "pan": "ABCDE1234F", "registration": "REG/2026/77",
         "validity_date": "2027-03-31", "plan": "Free",
         "admin_username": "admin@sunrise.example", "admin_password": "Str0ngPass!"}
    f.update(over)
    return f


def test_payload_carries_only_what_the_master_sets():
    p = ss.payload_from_master_form(_form(), created_by=9)
    assert (p["name"], p["pan"], p["reg_num"], p["plan"], p["validity"], p["created_by"]) == (
        "Sunrise Heights", "ABCDE1234F", "REG/2026/77", "Free", "2027-03-31", 9)
    assert p["admin_email"] == "admin@sunrise.example"
    # State, regime and certificate belong to the society's own setup wizard.
    for k in ("state", "constitution", "reg_cert_hash", "reg_cert_file"):
        assert k not in p


@pytest.mark.parametrize("field,label", [("registration", "Registration number"), ("name", "Society name"),
                                         ("address", "Address"), ("pan", "PAN"), ("validity_date", "Validity date"),
                                         ("admin_username", "Admin email")])
def test_missing_fields_are_named_for_the_master(field, label):
    with pytest.raises(ss.SocietyCreateError, match=label):
        ss.payload_from_master_form(_form(**{field: ""}), 1)


def test_weak_password_gets_the_policy_message():
    with pytest.raises(ss.SocietyCreateError):
        ss.payload_from_master_form(_form(admin_password="abc"), 1)


# ── the form itself ──────────────────────────────────────────────────────────────────────────────────────────────
def test_form_has_no_state_regime_or_certificate_fields():
    from app.dash_apps.drilldown.renderers import render_form_master_society_new
    text = str(render_form_master_society_new())
    for needle in ("'field': 'state'", "'field': 'constitution'", "master-society-cert-upload", "master-society-cert-status",
                   "'field': 'reg_cert_file'", "'field': 'reg_cert_hash'"):
        assert needle not in text, needle
    for needle in ("'field': 'name'", "'field': 'address'", "'field': 'pan'", "'field': 'registration'",
                   "'field': 'plan'", "'field': 'validity_date'"):
        assert needle in text, needle


def test_certificate_upload_callback_is_gone():
    """The fixed-id certificate callback overlapped the generic MATCH image callbacks and halted Dash's callback registration."""
    import app.dash_apps.callbacks.drilldown_callbacks as dc
    from dash import Dash
    captured = {}

    class Rec(Dash):
        def callback(self, *a, **k):
            def deco(fn):
                captured[fn.__name__] = fn
                return fn
            return deco
    dc.register_drilldown_callbacks(Rec(__name__))
    assert "handle_master_cert_upload" not in captured
