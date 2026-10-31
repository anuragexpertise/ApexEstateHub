"""
Plan v5 society onboarding and DPDP, proved against a REAL Postgres (plan task V5.13: replaces the structural checks in
test_plan_v5_onboarding.py with behaviour). One society is taken through the whole journey in order:

    registered -> committee seated -> setup draft -> annexes sealed -> three signatures -> platform signature -> active

Only the password confirmation is stubbed (it is not what is under test). Each run creates fresh societies and, because the
ledger, audit and signature tables are append-only, leaves them behind: use a throwaway database.

    ESTATEHUB_LIVE_TESTS=1 PGHOST=localhost PGDATABASE=... PGUSER=... PGPASSWORD=... PGSSLMODE=disable \
        SECRET_VAULT_KEY=... pytest test/test_plan_v5_onboarding_live.py
"""
import json
import os
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

pytestmark = [pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON), pytest.mark.postgres_integration]

PDF = b"%PDF-1.4\n% signed minutes of the general body meeting\n"
MASTER_ID = 1


def _drop_society(db, sid):
    """Best effort. Ledger, audit and signature tables are append-only by design, so a society that got far enough to hold
    them cannot be deleted. These tests therefore leave their societies behind: run them on a throwaway database."""
    try:
        db._execute("DELETE FROM societies WHERE id=%s", (sid,))
    except Exception:                                                      # noqa: BLE001
        pass


@pytest.fixture(scope="module")
def world():
    os.environ["OPERATOR_LEGAL_NAME"] = "Test Operator Pvt Ltd"
    os.environ["OPERATOR_ADDRESS"] = "1 Test Road, Lucknow"
    from database.db_manager import db
    from app.services import document_signing as ds
    from app.services import onboarding_service as ob
    from app.services import society_service as ss
    p = patch.object(ds, "_confirm_password", lambda user_id, password: None)
    p.start()
    sid = ss.create_society_checked({
        "name": f"V5 Live Test {date.today().isoformat()} {os.getpid()}", "address": "Gomti Nagar, Lucknow", "pan": "ABCDE1234F",
        "reg_num": "REG/2026/777", "reg_cert_hash": "a" * 64, "reg_cert_file": "cert.pdf", "state": "UP", "constitution": "AOA",
        "plan": "Free", "validity": str(date.today() + timedelta(days=365)), "admin_email": f"adm{os.getpid()}@v5test.example",
        "admin_password": "Admin@12345", "created_by": MASTER_ID})
    admin = db._execute("SELECT id FROM users WHERE society_id=%s AND role='admin'", (sid,), fetch_one=True)["id"]
    w = {"sid": sid, "admin": admin, "db": db, "ds": ds, "ob": ob, "ids": {}}
    yield w
    p.stop()
    _drop_society(db, sid)


def seat(w, office, flat, email):
    return w["ob"].seat_founding_officer(w["admin"], w["sid"], office, flat, f"{office.title()} Person", email, "9876543210",
                                         "Temp@12345", f"GBM 1-Oct-2026 Res {flat}", "minutes.pdf", PDF, 1200)


def _post_voucher(db, sid, dr_acc, cr_acc, amount, journal, entity=None):
    """One balanced voucher (both legs in one statement, as the double-entry trigger requires)."""
    db._execute("INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, entity_id, role, amount, mode, status, journal_id, source_table) "
                "VALUES (%s,'Dr',CURRENT_DATE,%s,%s,'other',%s,'journal','paid',%s,'t'), (%s,'Cr',CURRENT_DATE,%s,%s,'other',%s,'journal','paid',%s,'t')",
                (sid, dr_acc, entity, amount, journal, sid, cr_acc, entity, amount, journal))


def refused(db, sql, args=()):
    with pytest.raises(Exception) as e:
        db._execute(sql, args)
    return str(e.value)


# ── V5.1 / V5.2 ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_01_new_society_is_registered_with_a_regime(world):
    db, sid = world["db"], world["sid"]
    assert world["ob"].state_of(sid) == "registered"
    assert db._execute("SELECT regime_code FROM society_legal_regime WHERE society_id=%s", (sid,), fetch_one=True)["regime_code"] == "UP_AOA_2010"


def test_02_registered_society_cannot_post(world):
    db, sid = world["db"], world["sid"]
    from database.seed import seed_accounts
    with db._conn() as conn:
        seed_accounts(conn.cursor(), conn, sid, commit=False)
    acc = db._execute("SELECT id FROM accounts WHERE society_id=%s LIMIT 1", (sid,), fetch_one=True)["id"]
    msg = refused(db, "INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, role, amount, mode, status, journal_id, source_table) "
                      "VALUES (%s,'Dr',CURRENT_DATE,%s,'other',10,'journal','paid',999001,'t')", (sid, acc))
    assert "not active" in msg


# ── V5.3 founding committee ───────────────────────────────────────────────────────────────────────────────────────
def test_03_seating_needs_evidence_and_a_valid_file(world):
    ob, sid = world["ob"], world["sid"]
    with pytest.raises(ob.OnboardingError, match="minutes"):
        ob.seat_founding_officer(world["admin"], sid, "president", "A-101", "P", "p@v5test.example", None, "Temp@12345", "GBM 1", "m.pdf", None)
    with pytest.raises(ob.OnboardingError, match="does not look"):
        ob.seat_founding_officer(world["admin"], sid, "president", "A-101", "P", "p@v5test.example", None, "Temp@12345", "GBM 1", "m.pdf", b"not a pdf")
    assert world["db"]._execute("SELECT 1 AS x FROM apartments WHERE society_id=%s AND flat_number='A-101'", (sid,), fetch_one=True) is None  # nothing left behind


def test_04_three_seats_move_the_society_to_committee_seated(world):
    ob, sid = world["ob"], world["sid"]
    seat(world, "president", "A-101", f"pres{os.getpid()}@v5test.example")
    assert ob.state_of(sid) == "registered"
    seat(world, "secretary", "A-102", f"sec{os.getpid()}@v5test.example")
    msg = seat(world, "treasurer", "A-103", f"tre{os.getpid()}@v5test.example")
    assert "Setup Wizard is next" in msg
    assert ob.state_of(sid) == "committee seated"
    off = ob.seated_officers(sid)
    assert all(off[o] and len(off[o]["evidence_hash"]) == 64 for o in ob.CORE_OFFICES)


def test_05_grievance_officer(world):
    world["ob"].set_grievance_officer(world["sid"], "Meera Rao", "meera@v5test.example", "9811111111")
    with pytest.raises(world["ob"].OnboardingError):
        world["ob"].set_grievance_officer(world["sid"], "", "bad", None)


# ── V5.4 wizard draft posts nothing ───────────────────────────────────────────────────────────────────────────────
def test_06_wizard_draft_posts_nothing(world):
    db, sid, ob = world["db"], world["sid"], world["ob"]
    from app.services.signing_service import ensure_society_keys
    ensure_society_keys(sid, world["admin"])
    acc = {r["tab_name"]: r["id"] for r in db._execute("SELECT id, tab_name FROM accounts WHERE society_id=%s", (sid,), fetch_all=True)}
    bf = [{"acc_id": acc["SBI"], "bf_amount": "100000.00", "remarks": "bank"},
          {"acc_id": acc["SinkFund"], "bf_amount": "40000.00", "remarks": "sinking"},
          {"acc_id": acc["CapAc"], "bf_amount": "60000.00", "remarks": "capital"}]
    fy = date.today().year if date.today().month >= 4 else date.today().year - 1
    res = db._execute("SELECT fn_complete_society_setup(%s,'x',NULL,'Gomti Nagar',NULL,NULL,NULL,NULL,NULL,%s,'Sec','9','s@x.com',NULL,"
                      "'[]'::jsonb,NULL,NULL,0,0,'per_sqft',10,0,0,0,0,0,%s,%s::jsonb,%s, p_state := 'UP', p_draft := TRUE) AS r",
                      (sid, date(fy, 4, 1), fy, json.dumps(bf), world["admin"]), fetch_one=True)["r"]
    assert res == "OK"
    db._execute("INSERT INTO onboarding_declarations (society_id, declaration_json, status, submitted_at) VALUES (%s,%s::jsonb,'submitted',NOW()) "
                "ON CONFLICT (society_id) DO UPDATE SET declaration_json=EXCLUDED.declaration_json", (sid, json.dumps({"bf": {"fy": fy, "rows": bf}})))
    assert ob.state_of(sid) == "setup draft"
    assert db._execute("SELECT COUNT(*) AS n FROM brought_forward WHERE society_id=%s", (sid,), fetch_one=True)["n"] == 0
    assert db._execute("SELECT COUNT(*) AS n FROM transactions WHERE society_id=%s", (sid,), fetch_one=True)["n"] == 0
    world["bf"], world["fy"], world["acc"] = bf, fy, acc


# ── V5.5 annexes ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_07_failing_control_blocks_sealing(world):
    ob, sid = world["ob"], world["sid"]
    ob.save_annex_inputs(sid, "", False, None, None)                       # bank not attested
    ob.build_annexes(sid, world["admin"])
    c = world["db"]._execute("SELECT blocking, controls_json FROM onboarding_annexes WHERE society_id=%s AND annex_code='C'", (sid,), fetch_one=True)
    assert c["blocking"] and not c["controls_json"]["bank_agrees"]["passed"]
    with pytest.raises(ob.OnboardingError, match="Fix the failing controls"):
        ob.seal_annexes(sid, world["admin"])


def test_08_unbalanced_or_unbacked_opening_is_caught(world):
    ob, sid, db = world["ob"], world["sid"], world["db"]
    d = ob.declaration(sid)
    good = json.loads(json.dumps(d))
    d["bf"]["rows"][0]["bf_amount"] = "30000.00"                          # bank 30k < fund 40k and Dr != Cr
    db._execute("UPDATE onboarding_declarations SET declaration_json=%s::jsonb WHERE society_id=%s", (json.dumps(d), sid))
    ob.build_annexes(sid, world["admin"])
    ctl = db._execute("SELECT controls_json FROM onboarding_annexes WHERE society_id=%s AND annex_code='C'", (sid,), fetch_one=True)["controls_json"]
    assert not ctl["balanced"]["passed"] and not ctl["funds_backed"]["passed"]
    db._execute("UPDATE onboarding_declarations SET declaration_json=%s::jsonb WHERE society_id=%s", (json.dumps(good), sid))


def test_09_agreement_cannot_be_signed_before_annexes_are_sealed(world):
    ds, sid, db = world["ds"], world["sid"], world["db"]
    from app.dash_apps.callbacks.drilldown_callbacks import _get_or_create_agreement
    ag = _get_or_create_agreement(db, sid)
    pres = world["ob"].seated_officers(sid)["president"]["user_id"]
    with pytest.raises(ds.SigningRefused, match="Annexes A, B and C must be sealed"):
        ds.sign("agreement", ag["id"], pres, "pw")


def test_10_seal_annexes_puts_their_hashes_in_the_agreement(world):
    ob, sid, db = world["ob"], world["sid"], world["db"]
    ob.save_annex_inputs(sid, "", True, None, None)
    ob.build_annexes(sid, world["admin"])
    st = ob.seal_annexes(sid, world["admin"])
    assert {k: v["status"] for k, v in st.items()} == {"A": "sealed", "B": "sealed", "C": "sealed"}
    text = db._execute("SELECT body_text FROM society_agreements WHERE society_id=%s", (sid,), fetch_one=True)["body_text"]
    assert all(v["content_hash"] in text for v in st.values())
    assert "Test Operator Pvt Ltd" in text and "Treasurer" in text and "DATA PROTECTION" in text
    ob.assert_ready_to_sign(sid)


# ── V5.6 / V5.7 signing and activation ────────────────────────────────────────────────────────────────────────────
def test_11_platform_cannot_sign_first_and_society_is_not_active_early(world):
    ds, sid, db, ob = world["ds"], world["sid"], world["db"], world["ob"]
    ag = db._execute("SELECT id FROM society_agreements WHERE society_id=%s", (sid,), fetch_one=True)
    with pytest.raises(ds.SigningRefused, match="platform signs last"):
        ds.sign("agreement", ag["id"], MASTER_ID, "pw")
    assert ob.state_of(sid) == "setup draft"


def test_12_the_admin_cannot_sign(world):
    ds, sid, db = world["ds"], world["sid"], world["db"]
    ag = db._execute("SELECT id FROM society_agreements WHERE society_id=%s", (sid,), fetch_one=True)
    with pytest.raises(ds.SigningRefused, match="do not hold an office"):
        ds.sign("agreement", ag["id"], world["admin"], "pw")


def test_13_three_office_bearers_then_platform_activate(world):
    ds, sid, db, ob = world["ds"], world["sid"], world["db"], world["ob"]
    ag = db._execute("SELECT id FROM society_agreements WHERE society_id=%s", (sid,), fetch_one=True)["id"]
    off = ob.seated_officers(sid)
    for o in ("president", "secretary", "treasurer"):
        st = ds.sign("agreement", ag, off[o]["user_id"], "pw")
        assert not st["sealed"]
        assert ob.state_of(sid) == "setup draft"
    st = ds.sign("agreement", ag, MASTER_ID, "pw")
    assert st["sealed"] and st["activation"]["ok"], st.get("activation")
    assert ob.state_of(sid) == "active"
    assert {x["office_code"] for x in st["signed"]} == {"president", "secretary", "treasurer", "platform"}
    assert ds.verify("agreement", ag)["status"] == "valid"


def test_14_activation_posted_the_opening_position(world):
    db, sid = world["db"], world["sid"]
    rows = db._execute("SELECT acc_id, drcr_bf, bf_amount FROM brought_forward WHERE society_id=%s AND financial_year=%s ORDER BY acc_id",
                       (sid, world["fy"]), fetch_all=True)
    assert sum(r["bf_amount"] for r in rows if r["drcr_bf"] == "Dr") == sum(r["bf_amount"] for r in rows if r["drcr_bf"] == "Cr") == 100000
    assert db._execute("SELECT status FROM onboarding_declarations WHERE society_id=%s", (sid,), fetch_one=True)["status"] == "posted"
    assert db._execute("SELECT 1 AS x FROM audit_events WHERE society_id=%s AND action='SOCIETY_ACTIVATED'", (sid,), fetch_one=True)


def test_15_active_society_can_now_post(world):
    db, sid = world["db"], world["sid"]
    _post_voucher(db, sid, world["acc"]["SBI"], world["acc"]["CapAc"], 10, 999002)


def test_16_editing_the_sealed_agreement_is_blocked(world):
    db, sid = world["db"], world["sid"]
    assert "sealed" in refused(db, "UPDATE society_agreements SET body_text='changed' WHERE society_id=%s", (sid,)).lower()


# ── bye-law 7 re-check at activation ──────────────────────────────────────────────────────────────────────────────
def test_17_office_bearer_arrears_declared_in_annex_c_block_activation(world):
    db, ob = world["db"], world["ob"]
    from app.services import society_service as ss
    sid2 = ss.create_society_checked({"name": f"V5 Arrears {os.getpid()}", "address": "x", "pan": "ABCDE1234G", "reg_num": "R2", "reg_cert_hash": "b" * 64,
                                      "state": "UP", "constitution": "AOA", "validity": str(date.today() + timedelta(days=30)),
                                      "created_by": MASTER_ID})
    try:
        db._execute("UPDATE societies SET onboarding_state='setup draft' WHERE id=%s", (sid2,))
        db._execute("INSERT INTO onboarding_annexes (society_id, annex_code, content, content_hash, status) VALUES "
                    "(%s,'A','{}','a','sealed'),(%s,'B','{}','b','sealed'),(%s,'C',%s::jsonb,'c','sealed')",
                    (sid2, sid2, sid2, json.dumps({"financial_year": 2026, "opening_balances": [],
                                                   "arrears_by_flat": [{"flat_number": "B-1", "amount": "5000", "overdue_days": 120}]})))
        ag = db._execute("INSERT INTO society_agreements (society_id, body_text) VALUES (%s,'t') RETURNING id", (sid2,), fetch_one=True)["id"]
        db._execute("INSERT INTO signed_records (society_id, subject_kind, subject_id, purpose, item_hash, signature, key_version, key_id, algorithm, signers) "
                    "VALUES (%s,'agreement',%s,'SIGNING_AGREEMENT','h','s',1,'k','HMAC-SHA256','[]'::jsonb)", (sid2, ag))
        for i, off in enumerate(("president", "secretary", "treasurer"), start=1):
            apt = db._execute("INSERT INTO apartments (society_id, flat_number, owner_name, active) VALUES (%s,%s,'P',TRUE) RETURNING id",
                              (sid2, f"B-{i}"), fetch_one=True)["id"]
            uid = db._execute("INSERT INTO users (society_id, email, password_hash, role, linked_id) VALUES (%s,%s,'x','apartment',%s) RETURNING id",
                              (sid2, f"o{i}{os.getpid()}@v5test.example", apt), fetch_one=True)["id"]
            db._execute("INSERT INTO committee_offices (society_id, apartment_id, office_code, holder_name, status, user_id) VALUES (%s,%s,%s,'X','active',%s)",
                        (sid2, apt, off, uid))
            db._execute("INSERT INTO document_signatures (society_id, subject_kind, subject_id, user_id, office_code, item_hash) VALUES (%s,'agreement',%s,%s,%s,'h')",
                        (sid2, ag, uid, off))
        db._execute("INSERT INTO document_signatures (society_id, subject_kind, subject_id, user_id, office_code, item_hash) VALUES (%s,'agreement',%s,%s,'platform','h')",
                    (sid2, ag, MASTER_ID))
        res = ob.try_activate(sid2, MASTER_ID)
        assert not res["ok"] and "Bye-law 7" in res["error"] and "president" in res["error"]
        assert ob.state_of(sid2) == "setup draft"
    finally:
        _drop_society(db, sid2)


# ── V5.11 / V5.12 DPDP ────────────────────────────────────────────────────────────────────────────────────────────
def test_20_first_privacy_notice_was_published_at_activation(world):
    from app.services import dpdp_service as dp
    n = dp.current_notice(world["sid"])
    assert n and n["version"] == 1 and "Meera Rao" in n["body_text"] and "WHO TO ASK" in n["body_text"]


def test_21_dashboard_is_gated_until_the_notice_is_accepted(world):
    from app.services import dpdp_service as dp
    uid = world["ob"].seated_officers(world["sid"])["president"]["user_id"]
    assert dp.needs_notice(world["sid"], uid)
    dp.accept_notice(world["sid"], uid, ["announcements"])
    assert not dp.needs_notice(world["sid"], uid)
    got = {c["purpose"]: c["lawful_basis"] for c in dp.my_consents(world["sid"], uid)}
    assert got == {"notice_ack": "consent", "dues": "legitimate_use", "gate_safety": "legitimate_use", "announcements": "consent"}


def test_22_a_new_notice_version_asks_everyone_again(world):
    from app.services import dpdp_service as dp
    uid = world["ob"].seated_officers(world["sid"])["president"]["user_id"]
    dp.publish_notice(world["sid"], "Updated notice", "x" * 150, world["admin"])
    assert dp.current_notice(world["sid"])["version"] == 2 and dp.needs_notice(world["sid"], uid)


def test_23_optional_consent_can_be_withdrawn_but_statutory_cannot(world):
    from app.services import dpdp_service as dp
    uid = world["ob"].seated_officers(world["sid"])["president"]["user_id"]
    dp.accept_notice(world["sid"], uid, ["announcements"])
    dp.set_optional_consent(world["sid"], uid, "announcements", False)
    live = {c["purpose"] for c in dp.my_consents(world["sid"], uid) if not c["withdrawn_at"] and c["notice_version"] == 2}
    assert "announcements" not in live and "dues" in live
    with pytest.raises(dp.DpdpError):
        dp.set_optional_consent(world["sid"], uid, "dues", False)


def test_24_rights_request_has_a_due_date_and_needs_a_reasoned_answer(world):
    from app.services import dpdp_service as dp
    db, sid = world["db"], world["sid"]
    sec = world["ob"].seated_officers(sid)["secretary"]["user_id"]
    apt = db._execute("INSERT INTO apartments (society_id, flat_number, owner_name, active) VALUES (%s,'D-1','Plain Owner',TRUE) RETURNING id", (sid,), fetch_one=True)["id"]
    owner = db._execute("INSERT INTO users (society_id, email, password_hash, role, linked_id) VALUES (%s,%s,'x','apartment',%s) RETURNING id",
                        (sid, f"owner{os.getpid()}@v5test.example", apt), fetch_one=True)["id"]
    r = dp.raise_request(sid, owner, "access", "Please send me everything you hold about my flat.")
    assert r["due_date"] == date.today() + timedelta(days=dp.RESPONSE_DAYS) and r["outcome"] == "pending"
    with pytest.raises(dp.DpdpError, match="Only the administrator or the Secretary"):
        dp.respond(sid, r["id"], owner, "apartment", "granted", "I answer my own request.")
    with pytest.raises(dp.DpdpError, match="at least 10"):
        dp.respond(sid, r["id"], sec, "apartment", "granted", "ok")
    dp.respond(sid, r["id"], sec, "apartment", "granted", "A copy of the data was sent by email.")
    assert not [x for x in dp.list_requests(sid, owner) if x["open_request"]]


def test_25_erasure_keeps_the_ledger_and_waits_for_notice_and_blockers(world):
    from app.services import dpdp_service as dp
    db, sid = world["db"], world["sid"]
    apt = db._execute("INSERT INTO apartments (society_id, flat_number, owner_name, mobile, active) VALUES (%s,'C-1','Leaver','9000000001',TRUE) RETURNING id",
                      (sid,), fetch_one=True)["id"]
    uid = db._execute("INSERT INTO users (society_id, email, password_hash, role, linked_id, name) VALUES (%s,%s,'x','apartment',%s,'Leaver') RETURNING id",
                      (sid, f"leaver{os.getpid()}@v5test.example", apt), fetch_one=True)["id"]
    _post_voucher(db, sid, world["acc"]["SBI"], world["acc"]["CapAc"], 500, 999003, entity=apt)
    chain_before = db._execute("SELECT * FROM fn_verify_ledger_chain(%s)", (sid,), fetch_all=True)
    req = dp.raise_request(sid, uid, "erasure", "I have sold my flat; please erase my profile.")
    assert any("still an enrolled member" in b for b in dp.erasure_blockers(sid, req["id"]))
    with pytest.raises(dp.DpdpError, match="held"):
        dp.give_erasure_notice(sid, req["id"], world["admin"], "admin")
    db._execute("UPDATE apartments SET active=FALSE WHERE id=%s", (apt,))
    assert dp.erasure_blockers(sid, req["id"]) == []
    with pytest.raises(dp.DpdpError, match="notice"):
        dp.erase(sid, req["id"], world["admin"], "admin")                                 # no 48-hour notice yet
    dp.give_erasure_notice(sid, req["id"], world["admin"], "admin")
    with pytest.raises(dp.DpdpError, match="notice"):
        dp.erase(sid, req["id"], world["admin"], "admin")                                 # notice given just now: too soon
    db._execute("UPDATE rights_requests SET erasure_notice_at = NOW() - INTERVAL '49 hours' WHERE id=%s", (req["id"],))
    assert dp.erase(sid, req["id"], world["admin"], "admin") == "OK"
    a = db._execute("SELECT owner_name, mobile FROM apartments WHERE id=%s", (apt,), fetch_one=True)
    assert a["owner_name"] == "Former member" and a["mobile"] is None
    assert db._execute("SELECT email, active FROM users WHERE id=%s", (uid,), fetch_one=True)["email"].endswith("@erased.invalid")
    assert db._execute("SELECT COUNT(*) AS n FROM transactions WHERE entity_id=%s", (apt,), fetch_one=True)["n"] == 2
    assert db._execute("SELECT * FROM fn_verify_ledger_chain(%s)", (sid,), fetch_all=True) == chain_before


def test_26_breach_register(world):
    from app.services import dpdp_service as dp
    with pytest.raises(dp.DpdpError):
        dp.log_breach(world["sid"], world["admin"], "admin", None, "short", 0)
    b = dp.log_breach(world["sid"], world["admin"], "admin", None, "A laptop with the member list was lost at the office.", 12)
    dp.update_breach(world["sid"], b["id"], world["admin"], "admin", "remediated", True)
    row = dp.list_breaches(world["sid"])[0]
    assert row["status"] == "remediated" and row["intimation_sent"] and row["intimation_at"]
