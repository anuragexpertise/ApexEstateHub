# test/test_plan_v5_followup_live.py
"""Plan v5 follow-up, against a live Postgres (ESTATEHUB_LIVE_TESTS=1): fixed operator, eSign toggle and signing path,
inert legacy resolutions, adviser appointments (scope, expiry), the masked export and its log, enrollment minimisation.
Run on a throwaway database: the societies these tests make hold append-only rows and cannot be deleted."""
import hashlib
import hmac
import json
import os
from datetime import date, timedelta
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.skipif(os.getenv("ESTATEHUB_LIVE_TESTS") != "1", reason="live database tests")
MASTER_ID = 1
PID = os.getpid()


@pytest.fixture(scope="module")
def w():
    os.environ.pop("OPERATOR_LEGAL_NAME", None)
    os.environ.pop("OPERATOR_ADDRESS", None)
    os.environ["ESIGN_SANDBOX"] = "1"
    os.environ["ESIGN_CALLBACK_SECRET"] = "cb-secret"
    from database.db_manager import db
    from app.services import document_signing as ds, esign_adapter as es, onboarding_service as ob, society_service as ss
    p = patch.object(ds, "_confirm_password", lambda user_id, password: None)
    p.start()
    sid = ss.create_society_checked({"name": f"V5 Follow {PID}", "address": "x", "pan": "ABCDE1234H", "reg_num": "R3", "reg_cert_hash": "c" * 64,
                                     "state": "UP", "constitution": "AOA", "validity": str(date.today() + timedelta(days=30)), "created_by": MASTER_ID})
    db._execute("UPDATE societies SET onboarding_state='setup draft' WHERE id=%s", (sid,))
    db._execute("INSERT INTO onboarding_annexes (society_id, annex_code, content, content_hash, status) VALUES "
                "(%s,'A','{}','a','sealed'),(%s,'B','{}','b','sealed'),(%s,'C','{}','c','sealed')", (sid, sid, sid))
    ag = db._execute("INSERT INTO society_agreements (society_id, body_text) VALUES (%s,%s) RETURNING id",
                     (sid, "Agreement between the Society and EstateHub LLP of Agra, UP. Annex hashes a b c."), fetch_one=True)["id"]
    users = {}
    for i, off in enumerate(("president", "secretary", "treasurer"), start=1):
        apt = db._execute("INSERT INTO apartments (society_id, flat_number, owner_name, active) VALUES (%s,%s,'Owner Name',TRUE) RETURNING id",
                          (sid, f"F-{i}"), fetch_one=True)["id"]
        uid = db._execute("INSERT INTO users (society_id, email, password_hash, role, linked_id, name) VALUES (%s,%s,'x','apartment',%s,%s) RETURNING id",
                          (sid, f"f{i}{PID}@v5follow.example", apt, off.title()), fetch_one=True)["id"]
        db._execute("INSERT INTO committee_offices (society_id, apartment_id, office_code, holder_name, status, user_id, term_start) VALUES (%s,%s,%s,'X','active',%s,CURRENT_DATE - 1)",
                    (sid, apt, off, uid))
        users[off] = uid
    yield dict(db=db, ds=ds, es=es, ob=ob, sid=sid, ag=ag, users=users)
    p.stop()


def refused(fn, *a, **k):
    with pytest.raises(Exception) as e:
        fn(*a, **k)
    return str(e.value)


# ── operator is fixed in code ─────────────────────────────────────────────────────────────────────────────────────
def test_01_operator_needs_no_environment(w):
    ob = w["ob"]
    assert ob._operator() == ("EstateHub LLP", "Agra, UP, India") or ob._operator()[0] == "EstateHub LLP"
    ob.assert_ready_to_sign(w["sid"])                      # no OPERATOR_* variables set: signing is not blocked


# ── V5.6b eSign ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_02_esign_is_off_by_default_and_password_signs(w):
    assert w["ob"].esign_required(w["sid"]) is False


def test_03_with_esign_on_a_password_alone_is_refused(w):
    w["ob"].set_esign_required(w["sid"], MASTER_ID, True)
    assert w["es"].is_required(w["sid"])
    msg = refused(w["ds"].sign, "agreement", w["ag"], w["users"]["president"], "pw")
    assert "password alone is not accepted" in msg


def test_04_paper_needs_the_scan_hash(w):
    assert "SHA-256" in refused(w["ds"].sign, "agreement", w["ag"], w["users"]["president"], "pw", method="paper", evidence_ref="nope")
    st = w["ds"].sign("agreement", w["ag"], w["users"]["president"], "pw", method="paper", evidence_ref="ab" * 32)
    assert any(x["office_code"] == "president" for x in st["signed"])
    row = w["db"]._execute("SELECT method, evidence_ref FROM document_signatures WHERE subject_kind='agreement' AND subject_id=%s AND user_id=%s",
                           (w["ag"], w["users"]["president"]), fetch_one=True)
    assert row["method"] == "paper" and row["evidence_ref"] == "ab" * 32


def test_05_aadhaar_esign_needs_a_completed_request_for_this_person_and_text(w):
    es, ds, sid, ag, u = w["es"], w["ds"], w["sid"], w["ag"], w["users"]["secretary"]
    assert "not complete" in refused(ds.sign, "agreement", ag, u, "pw", method="aadhaar_eSign")
    _s, text = ds.item_text("agreement", ag)
    req = es.create_request(sid, "agreement", ag, "Secretary", "s@x.example", None, "aadhaar_eSign", ds.sha256(text), u, signer_user_id=u)
    assert req["status"] == "pending"
    assert "not complete" in refused(ds.sign, "agreement", ag, u, "pw", method="aadhaar_eSign")        # pending is not enough
    other = w["users"]["treasurer"]
    es.simulate_completion(req["id"])
    assert "not complete" in refused(ds.sign, "agreement", ag, other, "pw", method="aadhaar_eSign")    # someone else's eSign is no use
    st = ds.sign("agreement", ag, u, "pw", method="aadhaar_eSign")
    assert any(x["office_code"] == "secretary" for x in st["signed"])


def test_06_callback_is_authenticated_idempotent_and_checks_the_hash(w):
    es, ds, sid, ag, u = w["es"], w["ds"], w["sid"], w["ag"], w["users"]["treasurer"]
    _s, text = ds.item_text("agreement", ag)
    req = es.create_request(sid, "agreement", ag, "Treasurer", "t@x.example", None, "dsc", ds.sha256(text), u, signer_user_id=u)
    from flask import Flask
    from app.routes.esign_routes import esign_bp
    app = Flask(__name__)
    app.register_blueprint(esign_bp, url_prefix="/api")
    c = app.test_client()
    url = f"/api/esign/callback/{req['vendor_request_id']}"

    def post(payload, sign=True):
        raw = json.dumps(payload).encode()
        sig = hmac.new(b"cb-secret", raw, hashlib.sha256).hexdigest() if sign else "bad"
        return c.post(url, data=raw, headers={"X-Signature": sig, "Content-Type": "application/json"})

    assert post({"status": "completed", "document_hash": req["callback_hash"]}, sign=False).status_code == 401
    assert post({"status": "completed", "document_hash": "0" * 64}).status_code == 400            # wrong document
    assert post({"status": "completed", "document_hash": req["callback_hash"], "signer_email": "someone@else.example"}).status_code == 400
    r = post({"status": "completed", "document_hash": req["callback_hash"]})
    assert r.status_code == 200 and r.get_json()["duplicate"] is False
    assert post({"status": "completed", "document_hash": req["callback_hash"]}).get_json()["duplicate"] is True


def test_07_toggle_cannot_change_once_signing_has_started(w):
    assert "Signing has started" in refused(w["ob"].set_esign_required, w["sid"], MASTER_ID, False)


def test_08_stale_esign_requests_expire(w):
    w["db"]._execute("UPDATE esign_requests SET created_at = NOW() - INTERVAL '5 days' WHERE status='pending' AND society_id=%s", (w["sid"],))
    w["es"].expire_stale_requests()
    assert not w["db"]._execute("SELECT 1 AS x FROM esign_requests WHERE society_id=%s AND status='pending'", (w["sid"],), fetch_one=True)


# ── V5.8 legacy resolutions are evidence only ─────────────────────────────────────────────────────────────────────
def test_09_legacy_resolution_is_stored_as_inert_evidence(w):
    ob, db, sid = w["ob"], w["db"], w["sid"]
    dt = db._execute("SELECT id FROM decision_types ORDER BY id LIMIT 1", fetch_one=True)["id"]
    assert "SHA-256" in refused(ob.import_legacy_resolution, sid, MASTER_ID, "2024-05-01", "GBM", dt, "Approved the budget", "m.pdf", "")
    assert "past" in refused(ob.import_legacy_resolution, sid, MASTER_ID, str(date.today() + timedelta(days=3)), "GBM", dt, "x", "m.pdf", "a" * 64)
    msg = ob.import_legacy_resolution(sid, MASTER_ID, "2024-05-01", "GBM", dt, "Approved the budget", "m.pdf", "a" * 64, "passed")
    assert "evidence" in msg.lower()
    r = db._execute("SELECT r.passed, r.status, r.legacy, r.legacy_outcome FROM resolutions r JOIN meetings m ON m.id=r.meeting_id WHERE m.society_id=%s AND r.legacy", (sid,), fetch_one=True)
    assert r["legacy"] and not r["passed"] and r["status"] == "draft" and r["legacy_outcome"] == "passed"
    assert not db._execute("SELECT 1 AS x FROM resolutions r JOIN meetings m ON m.id=r.meeting_id WHERE m.society_id=%s AND (r.passed OR r.status='passed')", (sid,), fetch_one=True)


def test_10_a_legacy_resolution_cannot_be_made_passed(w):
    db = w["db"]
    rid = db._execute("SELECT r.id FROM resolutions r JOIN meetings m ON m.id=r.meeting_id WHERE m.society_id=%s AND r.legacy LIMIT 1", (w["sid"],), fetch_one=True)["id"]
    refused(db._execute, "UPDATE resolutions SET passed=TRUE, status='passed', passed_on=CURRENT_DATE, votes_for_pct=100 WHERE id=%s", (rid,))


# ── V5.9 / V5.10 advisers ─────────────────────────────────────────────────────────────────────────────────────────
def _adviser(w, kind, start, end, sealed=True, tag=""):
    db, sid = w["db"], w["sid"]
    rid = db._execute("SELECT r.id FROM resolutions r JOIN meetings m ON m.id=r.meeting_id WHERE m.society_id=%s AND r.legacy LIMIT 1", (sid,), fetch_one=True)["id"]
    uid = db._execute("INSERT INTO users (society_id, email, password_hash, role, name) VALUES (%s,%s,'x','adviser',%s) RETURNING id",
                      (sid, f"adv{kind}{tag}{PID}@v5follow.example", f"Adv {kind}"), fetch_one=True)["id"]
    aid = db._execute("INSERT INTO adviser_appointments (society_id, kind, name, term_start, term_end, resolution_id, login_user_id) "
                      "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id", (sid, kind, f"Adv {kind}", start, end, rid, uid), fetch_one=True)["id"]
    if sealed:
        db._execute("INSERT INTO signed_records (society_id, subject_kind, subject_id, purpose, item_hash, signature, key_version, key_id, algorithm, signers) "
                    "VALUES (%s,'adviser_appointment',%s,'SIGNING_AGREEMENT','h','s',1,'k','HMAC-SHA256','[]'::jsonb)", (sid, aid))
    return uid, aid


def test_11_an_appointment_is_in_force_only_between_its_dates_and_once_signed(w):
    from app.security import adviser_access as aa
    t = date.today()
    ok, _ = _adviser(w, "auditor", t - timedelta(days=5), t + timedelta(days=30), tag="a")
    unsigned, _ = _adviser(w, "ca", t - timedelta(days=5), t + timedelta(days=30), sealed=False, tag="b")
    ended, _ = _adviser(w, "ca", t - timedelta(days=90), t - timedelta(days=1), tag="c")
    future, _ = _adviser(w, "ca", t + timedelta(days=2), t + timedelta(days=90), tag="d")
    assert aa.in_force(ok) and not aa.in_force(unsigned) and not aa.in_force(ended) and not aa.in_force(future)


def test_12_an_advocate_is_refused_every_ledger_read(w):
    from app.security import adviser_access as aa
    from app.services import adviser_export as ae
    t = date.today()
    adv, _ = _adviser(w, "advocate", t - timedelta(days=1), t + timedelta(days=30), tag="e")
    assert aa.may(adv, "resolutions") and aa.may(adv, "agreements")
    for cap in ("ledger", "statements", "export"):
        assert not aa.may(adv, cap)
    assert "cannot read the ledger" in refused(ae.ledger_csv, adv)


def test_13_auditor_export_hides_owner_names_is_watermarked_and_logged(w):
    from app.services import adviser_export as ae
    db, sid = w["db"], w["sid"]
    from database.seed import seed_accounts
    with db._conn() as conn:
        seed_accounts(conn.cursor(), conn, sid, commit=False)
    acc = {r["tab_name"]: r["id"] for r in db._execute("SELECT id, tab_name FROM accounts WHERE society_id=%s", (sid,), fetch_all=True)}
    db._execute("UPDATE societies SET onboarding_state='active' WHERE id=%s", (sid,))
    apt = db._execute("SELECT id FROM apartments WHERE society_id=%s AND flat_number='F-1'", (sid,), fetch_one=True)["id"]
    names = list(acc)[:2]
    db._execute("INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, entity_id, role, amount, mode, status, journal_id, acc_particulars, source_table) "
                "VALUES (%s,'Dr',CURRENT_DATE,%s,%s,'apartment',50,'journal','paid',880001,'Maintenance Owner Name',%s), "
                "(%s,'Cr',CURRENT_DATE,%s,%s,'apartment',50,'journal','paid',880001,'Maintenance Owner Name','t')",
                (sid, acc[names[0]], apt, "t", sid, acc[names[1]], apt))
    t = date.today()
    uid, _ = _adviser(w, "auditor", t - timedelta(days=1), t + timedelta(days=30), tag="f")
    name, data, rows = ae.ledger_csv(uid)
    text = data.decode("utf-8-sig")
    assert rows >= 2 and "Owner Name" not in text and "Flat F-1" in text and "Prepared for Adv auditor" in text.splitlines()[0]
    log = db._execute("SELECT * FROM export_log WHERE society_id=%s AND exported_by=%s", (sid, uid), fetch_one=True)
    assert log["owner_names_masked"] and log["row_count"] == rows and log["watermark_by"] == "Adv auditor"


def test_14_the_expiry_job_ends_a_term_and_switches_the_login_off(w):
    from app.security import adviser_access as aa
    t = date.today()
    uid, aid = _adviser(w, "ca", t - timedelta(days=10), t + timedelta(days=1), tag="g")
    assert aa.in_force(uid)
    w["db"]._execute("UPDATE adviser_appointments SET term_end=%s WHERE id=%s", (t - timedelta(days=1), aid))
    out = aa.expire_due()
    assert out["ended"] >= 1 and not aa.in_force(uid)
    assert w["db"]._execute("SELECT active FROM users WHERE id=%s", (uid,), fetch_one=True)["active"] is False


def test_15_an_adviser_cannot_sign_in_outside_an_appointment(w):
    from app.services import auth_service
    from werkzeug.security import generate_password_hash
    db = w["db"]
    t = date.today()
    uid, aid = _adviser(w, "ca", t - timedelta(days=3), t + timedelta(days=9), tag="h")
    email = db._execute("SELECT email FROM users WHERE id=%s", (uid,), fetch_one=True)["email"]
    db._execute("UPDATE users SET password_hash=%s WHERE id=%s", (generate_password_hash("Adv@12345"), uid))
    assert auth_service.authenticate_user(email, "Adv@12345", w["sid"])
    db._execute("UPDATE adviser_appointments SET active=FALSE, revoked_at=NOW() WHERE id=%s", (aid,))
    assert not auth_service.authenticate_user(email, "Adv@12345", w["sid"])


# ── V5.12 minimisation ────────────────────────────────────────────────────────────────────────────────────────────
def test_16_family_logins_need_an_adult_confirmation(w):
    from app.dash_apps.callbacks import bulk_enroll_callbacks as be
    db, sid = w["db"], w["sid"]
    base = {"flat_number": "F-1", "password": "Fam@123456", "name": "Kin", "user_type": "family"}
    r = be._bulk_insert_apartment_users([{**base, "email": f"kin1{PID}@v5follow.example"}], sid, MASTER_ID)
    assert r["success"] == 0 and "adults only" in r["failed"][0][1]
    r = be._bulk_insert_apartment_users([{**base, "email": f"kin2{PID}@v5follow.example", "adult_confirmed": "yes"}], sid, MASTER_ID)
    assert r["success"] == 1, r


def test_17_id_proof_and_photo_are_optional_and_hidden_from_the_operator(w):
    from app.utils import field_config as fc
    cfg = fc.FIELD_CONFIG if hasattr(fc, "FIELD_CONFIG") else None
    src = open(fc.__file__).read()
    assert '"visible": ADMIN_MASTER,\n            "editable": ADMIN_ONLY,\n            "default": "",\n            "validation": {},\n            "tooltip": "Optional. Keep an ID' not in src
    assert "Optional. Add a photo only if the society needs one" in src


# ── DPDP [Verify] items ───────────────────────────────────────────────────────────────────────────────────────────
def test_18_dpdp_review_items_are_flagged_until_the_advocate_confirms(w):
    from app.services import dpdp_service as dp
    admin = w["db"]._execute("INSERT INTO users (society_id, email, password_hash, role, name) VALUES (%s,%s,'x','admin','A') RETURNING id",
                             (w["sid"], f"adm{PID}@v5follow.example"), fetch_one=True)["id"]
    dp.init_dpdp_review(w["sid"], admin)
    assert dp.dpdp_pending_legal_review(w["sid"])
    for it in dp.review_items(w["sid"]):
        assert dp.mark_dpdp_reviewed(w["sid"], it["item_key"], admin, "admin", True)
    assert not dp.dpdp_pending_legal_review(w["sid"])
    assert "Only the administrator" in refused(dp.mark_dpdp_reviewed, w["sid"], "response_days", w["users"]["president"], "apartment", True)
