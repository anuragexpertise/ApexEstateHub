"""
Phase 0 (Plan v3): society-scoped adviser decisions and the engine block.

Live tests against a REAL, SEEDED Postgres, rolled back. Society 1 is the demo society, whose decisions
seed_demo_adviser_confirmations has confirmed from 2000-01-01.

    ESTATEHUB_LIVE_TESTS=1 PGHOST=localhost PGDATABASE=... PGUSER=... pytest test/test_society_decisions_live.py
"""
import os

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

psycopg2 = pytest.importorskip("psycopg2")
pytestmark = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)

SOC = 1
PDF = b"%PDF-1.4\n% test\n%%EOF\n"
EARLY = "1999-01-01"      # before the demo decisions start: nothing confirmed is in force


@pytest.fixture()
def conn():
    c = psycopg2.connect(host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"), dbname=os.getenv("PGDATABASE"),
                         user=os.getenv("PGUSER"), password=os.getenv("PGPASSWORD"), sslmode=os.getenv("PGSSLMODE", "prefer"))
    cur = c.cursor()
    cur.execute("SELECT to_regproc('fn_require_confirmed') IS NOT NULL")
    if not cur.fetchone()[0]:
        c.close()
        pytest.skip("estatehub.sql with society-scoped adviser decisions is not installed in this database")
    cur.execute("SELECT 1 FROM society_decision_types WHERE society_id=%s LIMIT 1", (SOC,))
    if not cur.fetchone():
        c.close()
        pytest.skip("database was not seeded with the demo adviser decisions")
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    # The demo society leaves the Treasurer seat vacant; seat one for the length of the test (rolled back).
    cur.execute("SELECT 1 FROM committee_offices WHERE society_id=%s AND office_code='treasurer' AND status='active'", (SOC,))
    if not cur.fetchone():
        cur.execute("""INSERT INTO committee_offices (society_id, apartment_id, office_code, holder_name, user_id, term_start)
                       SELECT society_id, apartment_id, 'treasurer', holder_name, user_id, CURRENT_DATE - 30
                         FROM committee_offices WHERE society_id=%s AND office_code='working_committee_member' AND status='active'
                        ORDER BY id LIMIT 1""", (SOC,))
    yield c
    c.rollback()
    c.close()


@pytest.fixture()
def cur(conn):
    return conn.cursor()


def one(cur, sql, args=()):
    cur.execute(sql, args)
    r = cur.fetchone()
    return r[0] if r else None


def fails(cur, sql, args=(), match=None):
    """The statement is refused. A savepoint keeps the transaction usable."""
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error) as ei:
        cur.execute(sql, args)
    cur.execute("ROLLBACK TO SAVEPOINT s")
    if match:
        assert match.lower() in str(ei.value).lower(), str(ei.value)
    return ei.value


def holder(cur, office):
    return one(cur, "SELECT user_id FROM committee_offices WHERE society_id=%s AND office_code=%s AND status='active' LIMIT 1", (SOC, office))


def doc(cur, content=PDF):
    return one(cur, """INSERT INTO adviser_reference_documents (society_id, file_name, size_bytes, sha256, content)
                       VALUES (%s,'t.pdf',%s,encode(sha256(%s::bytea),'hex'),%s) RETURNING id""",
               (SOC, len(content), content, content))


def new_decision(cur, code="SET_SOCIETY_POLICY", majority=51, start="2030-01-01"):
    """A fresh PROVISIONAL decision for the demo society starting in the future (so it does not disturb today's)."""
    return one(cur, """INSERT INTO society_decision_types (society_id, decision_code, choice_options, default_choice, majority_pct,
                                                           majority_basis, start_date)
                       SELECT %s, code, majority_choices, majority_pct, %s, majority_basis, %s FROM decision_types WHERE code=%s
                       RETURNING id""", (SOC, majority, start, code))


def attach(cur, did, on="Advocate", ref="ADV/2026/17"):
    cur.execute("UPDATE society_decision_types SET on_behalf_of=%s, reference_text=%s, reference_doc_id=%s WHERE id=%s",
                (on, ref, doc(cur), did))


def sign(cur, did, role, user=None):
    return one(cur, "SELECT fn_sign_society_decision('decision',%s,%s,%s)", (did, role, user or holder(cur, role)))


def status(cur, did):
    return one(cur, "SELECT approved_status FROM society_decision_types WHERE id=%s", (did,))


# ── the gate and the loud message ────────────────────────────────────────────────────────────────────────────────
def test_demo_society_decisions_are_confirmed(cur):
    assert one(cur, "SELECT fn_decision_gate(%s,'rule','cash_receipt_limit')", (SOC,)) == "ok"
    assert one(cur, "SELECT fn_decision_gate(%s,'decision','SET_SOCIETY_POLICY')", (SOC,)) == "ok"


def test_catalogue_entries_that_are_checked_need_nothing(cur):
    assert one(cur, "SELECT fn_decision_gate(%s,'decision','GENERAL_RESOLUTION')", (SOC,)) == "not_required"


def test_ratification_route_is_never_blocked(cur):
    assert one(cur, "SELECT fn_decision_gate(%s,'decision','RATIFY_VOTING_THRESHOLDS',%s)", (SOC, EARLY)) == "not_required"


def test_unconfirmed_decision_gives_a_loud_message(cur):
    e = fails(cur, "SELECT fn_require_confirmed(%s,'rule','cash_receipt_limit',%s)", (SOC, EARLY), "DECISION REQUIRED")
    msg = str(e)
    assert "BLOCKED" in msg and "Adviser Decisions" in msg and "Secretary" in msg and "Treasurer" in msg
    assert e.pgcode == "EH001"


def test_provisional_row_waiting_for_approval_says_so(cur):
    new_decision(cur, "APPROVE_LOAN", 66.67, "2031-01-01")
    # Before the confirmed row starts nothing is in force, and a provisional row exists: it is waiting, not missing.
    assert one(cur, "SELECT fn_decision_gate(%s,'decision','APPROVE_LOAN',%s)", (SOC, EARLY)) == "awaiting_approval"
    fails(cur, "SELECT fn_require_confirmed(%s,'decision','APPROVE_LOAN',%s)", (SOC, EARLY), "waiting for approval")


# ── engines refuse ───────────────────────────────────────────────────────────────────────────────────────────────
def test_cash_receipt_check_refuses_until_confirmed(cur):
    fails(cur, "SELECT fn_check_cash_receipt_limit(%s, 100, 'cash', NULL, NULL, %s)", (SOC, EARLY), "DECISION REQUIRED")
    assert one(cur, "SELECT fn_check_cash_receipt_limit(%s, 100, 'cash', NULL, NULL, CURRENT_DATE)", (SOC,)) is None
    assert one(cur, "SELECT fn_check_cash_receipt_limit(%s, 9999999, 'upi')", (SOC,)) is None     # non-cash is untouched


def test_bye_law7_eligibility_refuses_until_the_year_basis_is_confirmed(cur):
    cur.execute("SELECT count(*) FROM fn_bye_law7_eligibility(%s, CURRENT_DATE)", (SOC,))   # confirmed: runs
    assert cur.fetchone()[0] >= 0
    # Moving the start date changes what was approved, so the approval lapses and the engine blocks again.
    cur.execute("UPDATE rule_parameter_defs SET start_date = CURRENT_DATE + 365 WHERE society_id=%s AND rule_key='bye_law7_year_basis'", (SOC,))
    assert one(cur, "SELECT approved_status FROM rule_parameter_defs WHERE society_id=%s AND rule_key='bye_law7_year_basis'", (SOC,)) == "provisional"
    fails(cur, "SELECT * FROM fn_bye_law7_eligibility(%s, CURRENT_DATE)", (SOC,), "DECISION REQUIRED")
    cur.execute("SELECT count(*) FROM fn_bye_law7_eligibility(%s, CURRENT_DATE, 'financial_year')", (SOC,))   # an explicit basis bypasses the reading
    assert cur.fetchone()[0] >= 0


def test_resolution_cannot_be_recorded_before_the_decision_is_confirmed(cur):
    mid = one(cur, "INSERT INTO meetings (society_id, type, held_on) VALUES (%s,'GBM',CURRENT_DATE) RETURNING id", (SOC,))
    dt = one(cur, "SELECT id FROM decision_types WHERE code='SET_SOCIETY_POLICY'")
    fails(cur, "INSERT INTO resolutions (meeting_id, decision_type_id, body, majority_required, passed_on) VALUES (%s,%s,'x',66.67,%s)",
          (mid, dt, EARLY), "DECISION REQUIRED")
    rid = one(cur, "INSERT INTO resolutions (meeting_id, decision_type_id, body, majority_required) VALUES (%s,%s,'x',66.67) RETURNING id",
              (mid, dt))
    assert rid


def test_resolution_majority_cannot_be_below_the_confirmed_one(cur):
    mid = one(cur, "INSERT INTO meetings (society_id, type, held_on) VALUES (%s,'GBM',CURRENT_DATE) RETURNING id", (SOC,))
    dt = one(cur, "SELECT id FROM decision_types WHERE code='SET_SOCIETY_POLICY'")
    fails(cur, "INSERT INTO resolutions (meeting_id, decision_type_id, body, majority_required) VALUES (%s,%s,'x',51)",
          (mid, dt), "needs at least 66.67")


# ── approval: two different office-bearers, on an adviser's behalf, with a PDF ───────────────────────────────────
def test_new_decision_is_provisional_and_cannot_be_inserted_confirmed(cur):
    did = new_decision(cur)
    assert status(cur, did) == "provisional"
    fails(cur, """INSERT INTO society_decision_types (society_id, decision_code, choice_options, default_choice, majority_pct,
                  majority_basis, start_date, approved_status, confirmed_at)
                  VALUES (%s,'APPROVE_LOAN','{51,66.67}',66.67,66.67,'all_votes','2032-01-01','confirmed',NOW())""", (SOC,))


def test_chosen_majority_must_be_one_of_the_offered_choices(cur):
    fails(cur, "UPDATE society_decision_types SET majority_pct = 40 WHERE id = %s", (new_decision(cur),), "ck_sdt_choice")


def test_cannot_confirm_by_setting_the_status(cur):
    did = new_decision(cur)
    attach(cur, did)
    fails(cur, "UPDATE society_decision_types SET approved_status='confirmed' WHERE id=%s", (did,), "Secretary and the Treasurer")


def test_both_secretary_and_treasurer_must_approve(cur):
    did = new_decision(cur)
    attach(cur, did)
    assert "Waiting for the Treasurer" in sign(cur, did, "secretary")
    assert status(cur, did) == "provisional"
    assert "Confirmed" in sign(cur, did, "treasurer")
    assert status(cur, did) == "confirmed"
    assert one(cur, "SELECT confirmed_at IS NOT NULL FROM society_decision_types WHERE id=%s", (did,))


def test_signing_needs_reference_text_and_pdf_first(cur):
    did = new_decision(cur)
    fails(cur, "SELECT fn_sign_society_decision('decision',%s,'secretary',%s)", (did, holder(cur, "secretary")), "upload their PDF")
    cur.execute("UPDATE society_decision_types SET on_behalf_of='CA', reference_doc_id=%s WHERE id=%s", (doc(cur), did))
    fails(cur, "SELECT fn_sign_society_decision('decision',%s,'secretary',%s)", (did, holder(cur, "secretary")), "reference number")


def test_adviser_must_be_advocate_ca_or_auditor(cur):
    fails(cur, "UPDATE society_decision_types SET on_behalf_of='Cousin' WHERE id=%s", (new_decision(cur),))


def test_only_the_serving_office_holder_can_sign(cur):
    did = new_decision(cur)
    attach(cur, did)
    fails(cur, "SELECT fn_sign_society_decision('decision',%s,'secretary',%s)", (did, holder(cur, "president")), "do not hold the office")
    fails(cur, "SELECT fn_sign_society_decision('decision',%s,'treasurer',%s)", (did, holder(cur, "secretary")), "do not hold the office")


def test_one_person_holding_both_offices_counts_once(cur):
    sec, tre = holder(cur, "secretary"), holder(cur, "treasurer")
    apt = one(cur, "SELECT apartment_id FROM committee_offices WHERE society_id=%s AND office_code='secretary' AND status='active'", (SOC,))
    cur.execute("UPDATE committee_offices SET user_id=%s WHERE society_id=%s AND office_code='treasurer' AND status='active'", (sec, SOC))
    did = new_decision(cur)
    attach(cur, did)
    sign(cur, did, "secretary")
    fails(cur, "SELECT fn_sign_society_decision('decision',%s,'treasurer',%s)", (did, sec), "two different people")
    assert status(cur, did) == "provisional"
    assert tre != sec and apt


def test_editing_after_confirmation_voids_the_approval(cur):
    did = new_decision(cur, "SET_SOCIETY_POLICY", 51)
    attach(cur, did)
    sign(cur, did, "secretary"); sign(cur, did, "treasurer")
    assert status(cur, did) == "confirmed"
    cur.execute("UPDATE society_decision_types SET majority_pct = 66.67 WHERE id = %s", (did,))
    assert status(cur, did) == "provisional"
    assert one(cur, "SELECT confirmed_at IS NULL FROM society_decision_types WHERE id=%s", (did,))
    assert one(cur, "SELECT signed_roles FROM fn_society_decision_status(%s) WHERE subject_id=%s AND kind='decision'", (SOC, did)) == []


def test_replacing_the_pdf_voids_the_approval(cur):
    did = new_decision(cur)
    attach(cur, did)
    sign(cur, did, "secretary"); sign(cur, did, "treasurer")
    cur.execute("UPDATE society_decision_types SET reference_doc_id=%s WHERE id=%s", (doc(cur, PDF + b"x"), did))
    assert status(cur, did) == "provisional"


def test_confirmed_decision_cannot_be_unconfirmed_or_deleted(cur):
    did = new_decision(cur)
    attach(cur, did)
    sign(cur, did, "secretary"); sign(cur, did, "treasurer")
    fails(cur, "UPDATE society_decision_types SET approved_status='provisional' WHERE id=%s", (did,), "cannot be un-confirmed")
    fails(cur, "DELETE FROM society_decision_types WHERE id=%s", (did,), "cannot be deleted")


def test_a_confirmed_row_changes_the_majority_from_its_start_date(cur):
    did = new_decision(cur, "SET_SOCIETY_POLICY", 51, "2030-01-01")
    attach(cur, did)
    sign(cur, did, "secretary"); sign(cur, did, "treasurer")
    assert float(one(cur, "SELECT fn_decision_majority(%s,'SET_SOCIETY_POLICY',DATE '2031-01-01')", (SOC,))) == 51
    assert float(one(cur, "SELECT fn_decision_majority(%s,'SET_SOCIETY_POLICY',DATE '2029-12-31')", (SOC,))) == 66.67


def test_an_unconfirmed_newer_row_changes_nothing(cur):
    new_decision(cur, "SET_SOCIETY_POLICY", 51, "2030-01-01")
    assert float(one(cur, "SELECT fn_decision_majority(%s,'SET_SOCIETY_POLICY',DATE '2031-01-01')", (SOC,))) == 66.67


# ── rules ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_rule_rows_are_scoped_and_the_platform_row_is_unique(cur):
    assert one(cur, "SELECT count(*) FROM rule_parameter_defs WHERE society_id IS NULL AND rule_key='poll_majority_of'") == 1
    assert one(cur, "SELECT count(*) FROM rule_parameter_defs WHERE society_id=%s AND rule_key='poll_majority_of'", (SOC,)) == 1
    fails(cur, """INSERT INTO rule_parameter_defs (regime_code, rule_key, label, instrument, provision, nature, base_source, value_type,
                  enforcement) SELECT regime_code, rule_key, label, instrument, provision, nature, base_source, value_type, enforcement
                  FROM rule_parameter_defs WHERE society_id IS NULL AND rule_key='poll_majority_of'""")


def test_fn_rule_still_returns_one_row_per_rule(cur):
    for key in ("cash_receipt_limit", "poll_majority_of", "bye_law7_year_basis"):
        assert one(cur, "SELECT count(*) FROM fn_rule(%s,%s)", (SOC, key)) == 1


def test_rule_reading_follows_the_same_two_signature_path(cur):
    rid = one(cur, """INSERT INTO rule_parameter_defs (regime_code, rule_key, label, instrument, provision, clause_id, nature, base_source,
                         value_type, unit, min_value, max_value, vary_min, vary_max, choices, layers, tighten, droppable, enforcement,
                         feeds, verification, verified_on, needs_decision, implemented, description, society_id, start_date,
                         on_behalf_of, reference_text, reference_doc_id)
                      SELECT regime_code, rule_key, label, instrument, provision, clause_id, nature, base_source, value_type, unit,
                         min_value, max_value, vary_min, vary_max, choices, layers, tighten, droppable, enforcement, feeds, verification,
                         verified_on, needs_decision, implemented, description, society_id, DATE '2030-01-01', 'CA', 'CA/77', %s
                        FROM rule_parameter_defs WHERE society_id=%s AND rule_key='poll_majority_of' RETURNING id""", (doc(cur), SOC))
    assert "Waiting" in one(cur, "SELECT fn_sign_society_decision('rule',%s,'treasurer',%s)", (rid, holder(cur, "treasurer")))
    assert "Confirmed" in one(cur, "SELECT fn_sign_society_decision('rule',%s,'secretary',%s)", (rid, holder(cur, "secretary")))


# ── evidence is immutable and must be a PDF ──────────────────────────────────────────────────────────────────────
def test_reference_document_must_be_a_pdf(cur):
    fails(cur, """INSERT INTO adviser_reference_documents (society_id, file_name, size_bytes, sha256, content)
                  VALUES (%s,'x.pdf',9,encode(sha256('not a pdf'::bytea),'hex'),'not a pdf')""", (SOC,), "ck_adviser_doc_is_pdf")


def test_reference_document_hash_and_size_are_checked(cur):
    fails(cur, """INSERT INTO adviser_reference_documents (society_id, file_name, size_bytes, sha256, content)
                  VALUES (%s,'x.pdf',99,encode(sha256(%s::bytea),'hex'),%s)""", (SOC, PDF, PDF), "ck_adviser_doc_size")
    fails(cur, """INSERT INTO adviser_reference_documents (society_id, file_name, size_bytes, sha256, content)
                  VALUES (%s,'x.pdf',%s,repeat('0',64),%s)""", (SOC, len(PDF), PDF), "ck_adviser_doc_hash")


def test_documents_and_approvals_cannot_be_edited_or_deleted(cur):
    did = new_decision(cur)
    attach(cur, did)
    sign(cur, did, "secretary")
    fails(cur, "UPDATE adviser_reference_documents SET file_name='y.pdf'", match="evidence")
    fails(cur, "DELETE FROM adviser_reference_documents")
    fails(cur, "UPDATE society_decision_approvals SET role='treasurer'", match="cannot be changed")
    fails(cur, "DELETE FROM society_decision_approvals")


def test_approvals_are_audited(cur):
    did = new_decision(cur)
    attach(cur, did)
    sign(cur, did, "secretary")
    assert one(cur, "SELECT count(*) FROM audit_events WHERE action='ADVISER_DECISION_APPROVED' AND resource_type='society_decision' AND resource_id=%s", (str(did),)) == 1


def test_init_is_idempotent(cur):
    assert one(cur, "SELECT fn_init_society_decisions(%s)", (SOC,)) == 0
