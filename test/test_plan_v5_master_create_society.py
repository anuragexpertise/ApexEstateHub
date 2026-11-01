"""Plan v5.2: the master portal's Create Society form must supply everything create_society_checked() now demands.
Before this, the only UI path to a new society was refused with 'State is required' every time."""
import base64
import hashlib

import pytest

from app.services import society_service as ss

PDF = b"%PDF-1.4\n" + b"certificate body " * 50


@pytest.fixture(autouse=True)
def _cert_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "_cert_folder", lambda: tmp_path / "registration")
    return tmp_path


def _form(**over):
    stored, digest = ss.store_registration_certificate("reg.pdf", PDF)
    f = {"name": "Sunrise Heights", "address": "Agra", "pan": "ABCDE1234F", "registration": "REG/2026/77",
         "state": "UP", "constitution": "AOA", "validity_date": "2027-03-31", "plan": "Free",
         "admin_username": "admin@sunrise.example", "admin_password": "Str0ngPass!",
         "reg_cert_file": stored, "reg_cert_hash": digest}
    f.update(over)
    return f


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
def test_payload_carries_the_v5_fields():
    f = _form()
    p = ss.payload_from_master_form(f, created_by=9)
    assert (p["state"], p["constitution"], p["reg_num"], p["reg_cert_hash"], p["created_by"]) == ("UP", "AOA", "REG/2026/77", f["reg_cert_hash"], 9)
    assert p["admin_email"] == "admin@sunrise.example" and p["validity"] == "2027-03-31"


@pytest.mark.parametrize("field,label", [("state", "State"), ("constitution", "Constitution"), ("registration", "Registration number"),
                                         ("name", "Society name"), ("admin_username", "Admin email")])
def test_missing_fields_are_named_for_the_master(field, label):
    with pytest.raises(ss.SocietyCreateError, match=label):
        ss.payload_from_master_form(_form(**{field: ""}), 1)


def test_no_certificate_means_no_society():
    with pytest.raises(ss.SocietyCreateError, match="Upload the registration certificate"):
        ss.payload_from_master_form(_form(reg_cert_file="", reg_cert_hash=""), 1)


def test_weak_password_gets_the_policy_message():
    with pytest.raises(ss.SocietyCreateError):
        ss.payload_from_master_form(_form(admin_password="abc"), 1)


# ── the form itself ──────────────────────────────────────────────────────────────────────────────────────────────
def test_form_offers_state_constitution_and_certificate_upload():
    from app.dash_apps.drilldown.renderers import render_form_master_society_new
    text = str(render_form_master_society_new())
    for needle in ("'field': 'state'", "'field': 'constitution'", "master-society-cert-upload", "master-society-cert-status",
                   "'field': 'reg_cert_file'", "'field': 'reg_cert_hash'", "Uttar Pradesh", "Co-operative Housing Society"):
        assert needle in text, needle


def test_upload_callback_stores_hashes_and_reports(monkeypatch):
    import app.dash_apps.callbacks.drilldown_callbacks as dc
    from dash import Dash
    captured = {}

    class Rec(Dash):
        def callback(self, *a, **k):
            def deco(fn):
                captured[fn.__name__] = fn
                return fn
            return deco
    app = Rec(__name__)
    dc.register_drilldown_callbacks(app)
    fn = captured["handle_master_cert_upload"]
    raw = getattr(fn, "__wrapped__", fn)
    monkeypatch.setattr(dc, "get_current_user_role", lambda: "master")
    status, stored, digest = raw("data:application/pdf;base64," + base64.b64encode(PDF).decode(), "reg.pdf")
    assert digest == hashlib.sha256(PDF).hexdigest() and stored == digest + ".pdf" and "attached" in str(status)
    status, stored, digest = raw("data:application/pdf;base64," + base64.b64encode(b"junk").decode(), "reg.pdf")
    assert (stored, digest) == ("", "") and "real PDF" in str(status)
    monkeypatch.setattr(dc, "get_current_user_role", lambda: "admin")
    _s, stored, digest = raw("data:application/pdf;base64," + base64.b64encode(PDF).decode(), "reg.pdf")
    assert (stored, digest) == ("", "")                                          # only the master may register a society
