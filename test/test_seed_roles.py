"""The seed's Managing Committee and society-employee logins.

Hermetic tests read the seed's data (no database). The live tests need a seeded throwaway Postgres and explicit
opt-in (see test/live_db_gate.py):  ESTATEHUB_LIVE_TESTS=1 PGHOST=... pytest test/test_seed_roles.py
"""
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database"))
import seed  # noqa: E402

from app.security import authorization as az  # noqa: E402
from app.security.roles import PERSISTED_ROLES, portal_home  # noqa: E402
from test.live_db_gate import LIVE_DB_REASON, live_db_enabled  # noqa: E402


def by(**kw):
    return [u for u in seed.USERS if all(u.get(k) == v for k, v in kw.items())]


# ── seed data (hermetic) ──────────────────────────────────────────────────────────────────────────────────────
def test_committee_is_one_president_one_secretary_ten_members():
    assert len(by(office="president")) == 1
    assert len(by(office="secretary")) == 1
    assert len(by(office="working_committee_member")) == seed.COMMITTEE_SIZE == 10


def test_secretary_is_the_person_named_on_the_society_record():
    sec = by(office="secretary")[0]
    assert sec["name"] == seed.SOCIETY["secretary_name"] and sec["email"] == seed.SOCIETY["secretary_email"]


def test_accountant_auditor_supervisor_staff_logins_exist_with_valid_roles():
    for role in ("accountant", "auditor", "supervisor", "staff"):
        assert len(by(role=role)) == 1, role
        assert role in PERSISTED_ROLES
        assert portal_home(role).endswith(f"{role}-portal")


def test_every_office_bearer_is_an_owner_of_their_own_flat():
    flats = [u["flat_number"] for u in seed.USERS if u.get("office")]
    assert len(flats) == len(set(flats)) == 12
    assert all(u["role"] == "apartment" and u.get("user_type", "owner") == "owner" for u in seed.USERS if u.get("office"))
    assert not set(flats) & {u["flat_number"] for u in seed.USERS if not u.get("office") and u["role"] == "apartment"}


def test_seed_users_validate_and_reject_a_broken_committee(monkeypatch):
    seed._validate_users()
    monkeypatch.setattr(seed, "USERS", [u for u in seed.USERS if u.get("office") != "president"])
    with pytest.raises(ValueError, match="Managing Committee"):
        seed._validate_users()


def test_validation_rejects_an_unknown_role(monkeypatch):
    monkeypatch.setattr(seed, "USERS", seed.USERS + [{"role": "janitor", "email": "j@x.com", "password": "Janitor@2024", "name": "J"}])
    with pytest.raises(ValueError, match="role the schema does not allow"):
        seed._validate_users()


def test_office_bearer_billing_starts_next_month():
    from datetime import date
    assert seed._next_month_start(date(2026, 10, 19)) == date(2026, 11, 1)
    assert seed._next_month_start(date(2026, 12, 31)) == date(2027, 1, 1)
    assert seed._calc_start(by(office="president")[0]) == seed._next_month_start()
    assert seed._calc_start(by(email="owner1@sunriseresidency.com")[0]) == "2026-04-01"
    assert seed._calc_start(by(email="owner4@sunriseresidency.com")[0]) == "2026-04-01"


def test_owner_admissions_use_the_real_owner_names():
    owners = {u["email"]: u["name"] for u in seed.USERS}
    assert owners["owner1@sunriseresidency.com"] == "Rajesh Sharma" and owners["owner3@sunriseresidency.com"] == "Priya Gupta"


# ── what each seeded role may do (hermetic, pure policy) ──────────────────────────────────────────────────────
def principal(role, rbac=(), user_type=None):
    return az.Principal(user_id=1, society_id=1, base_role=role, user_type=user_type,
                        assignments=tuple(az.Assignment(r, 1, effective_from=datetime(2026, 4, 1)) for r in rbac))


def caps(*a, **k):
    return az.capabilities_of(principal(*a, **k), now=datetime(2026, 10, 19))


def test_president_approves_payments_but_cannot_prepare_them():
    c = caps("apartment", ("society_president",), "owner")
    assert az.Cap.FINANCE_PAYMENT_APPROVE in c and az.Cap.CONCERN_ASSIGN in c
    assert az.Cap.FINANCE_PAYMENT_PREPARE not in c and az.Cap.FINANCE_POST not in c


def test_committee_member_can_triage_but_not_approve_money():
    c = caps("apartment", ("committee_member",), "owner")
    assert az.Cap.CONCERN_TRIAGE in c and az.Cap.FINANCE_PAYMENT_APPROVE not in c


def test_accountant_prepares_auditor_only_reads_neither_does_both():
    acct, aud = caps("accountant", ("accountant",)), caps("auditor")
    assert az.Cap.FINANCE_PAYMENT_PREPARE in acct and az.Cap.FINANCE_PAYMENT_APPROVE not in acct
    assert aud == {az.Cap.AUDIT_VIEW, az.Cap.REPORT_EXPORT, az.Cap.NOTIFICATION_SELF_READ}


def test_supervisor_has_no_finance_power_and_staff_only_the_baseline():
    sup = caps("supervisor")
    assert az.Cap.STAFF_ROSTER_MANAGE in sup and not any(c.startswith("finance.") for c in sup)
    assert caps("staff") == {az.Cap.NOTIFICATION_SELF_READ}


# ── the seeded database (live) ────────────────────────────────────────────────────────────────────────────────
live = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)


@pytest.fixture()
def cur():
    psycopg2 = pytest.importorskip("psycopg2")
    conn = psycopg2.connect(host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"), dbname=os.getenv("PGDATABASE"),
                            user=os.getenv("PGUSER"), password=os.getenv("PGPASSWORD", ""))
    c = conn.cursor()
    c.execute("SELECT 1 FROM committee_offices LIMIT 1")
    if not c.fetchone():
        conn.close()
        pytest.skip("database was not seeded with the committee")
    yield c
    conn.rollback()
    conn.close()


@live
def test_seeded_committee_is_seated_and_in_good_standing(cur):
    cur.execute("SELECT office_code, count(*), bool_or(ineligible_stand), bool_and(user_id IS NOT NULL) "
                "FROM fn_committee_current(1) GROUP BY office_code")
    got = {r[0]: r[1:] for r in cur.fetchall()}
    assert got == {"president": (1, False, True), "secretary": (1, False, True),
                   "working_committee_member": (10, False, True)}


@live
def test_seeded_roles_are_assigned_and_the_admin_does_not_hold_secretary(cur):
    cur.execute("""SELECT rd.code, count(*) FROM user_role_assignments ura
                     JOIN role_definitions rd ON rd.id = ura.role_definition_id
                    WHERE ura.society_id = 1 AND ura.status = 'active' GROUP BY rd.code""")
    got = dict(cur.fetchall())
    assert got["society_president"] == got["society_secretary"] == got["accountant"] == 1
    assert got["committee_member"] == 10
    cur.execute("""SELECT count(*) FROM user_role_assignments ura JOIN users u ON u.id = ura.user_id
                     JOIN role_definitions rd ON rd.id = ura.role_definition_id
                    WHERE rd.code = 'society_secretary' AND u.role = 'admin'""")
    assert cur.fetchone()[0] == 0


@live
def test_every_seeded_login_has_the_role_and_flat_the_seed_declares(cur):
    cur.execute("SELECT email, role, linked_id FROM users WHERE society_id = 1")
    rows = {r[0]: r[1:] for r in cur.fetchall()}
    for u in seed.USERS:
        role, linked = rows[u["email"]]
        assert role == u["role"]
        assert (linked is not None) == (u["role"] in ("apartment", "vendor", "security")), u["email"]


@live
def test_receipt_chain_checks_run_after_the_ambiguity_fix(cur):
    cur.execute("SELECT count(*) FROM fn_verify_all_receipt_chains(1) WHERE NOT is_valid")
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT count(*) FROM fn_verify_receipt_chain(1, 4230)")
    assert cur.fetchone()[0] >= 1


@live
def test_entrance_fee_due_runs(cur):
    cur.execute("SELECT is_paid FROM fn_entrance_fee_due(1, (SELECT linked_id FROM users WHERE email='owner1@sunriseresidency.com'))")
    assert cur.fetchone()[0] is True
