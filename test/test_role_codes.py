"""
New role codes: ACC / SPV / STF (employees), ADT / ADV / MST (always PASS), plus SEC and ADM which already existed.

Hermetic: no database. The database is replaced by an object that fails the test if it is touched, so the
"always PASS" claim is proven as "needs nothing from the database", not merely "happens to pass".
"""
import hashlib
import hmac

import pytest

from app.security import roles
from app.services import qr_service


class _NoDB:
    """Stands in for database.db_manager.db. Any use is a test failure."""
    def _execute(self, *a, **k):
        raise AssertionError("the database must not be touched here")


@pytest.fixture
def no_db(monkeypatch):
    monkeypatch.setattr(qr_service, "db", _NoDB())


# ── the registry ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_six_requested_codes_map_to_their_roles():
    assert roles.ROLE_CODES["ACC"] == "accountant"
    assert roles.ROLE_CODES["SPV"] == "supervisor"
    assert roles.ROLE_CODES["STF"] == "staff"
    assert roles.ROLE_CODES["ADT"] == "auditor"
    assert roles.ROLE_CODES["ADV"] == "adviser"
    assert roles.ROLE_CODES["MST"] == "master"


def test_registry_and_qr_maps_agree_for_every_person_code():
    """roles.py and qr_service keep separate maps (qr_service also holds document codes like RPT); they must not drift."""
    for code, role in roles.ROLE_CODES.items():
        assert qr_service.ROLE_CODE_MAP[code] == role, code
        assert qr_service.ROLE_CODE_MAP_REV[role] == code, role


def test_employee_codes_are_exactly_acc_spv_stf_sec():
    assert set(roles.EMPLOYEE_CODES) == {"ACC", "SPV", "STF", "SEC"}
    assert set(roles.EMPLOYEE_ROLES) == {"accountant", "supervisor", "staff", "security"}


def test_always_pass_codes_are_exactly_adt_adv_mst():
    assert set(roles.ALWAYS_PASS_CODES) == {"ADT", "ADV", "MST"}


def test_employee_and_always_pass_groups_do_not_overlap():
    assert not set(roles.EMPLOYEE_CODES) & set(roles.ALWAYS_PASS_CODES)


# ── parsing: the platform codes ───────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("code,role", [("ADT", "auditor"), ("ADV", "adviser"), ("MST", "master")])
def test_platform_code_parses(code, role):
    p = qr_service.parse_qr_payload(f"0-{code}-None")
    assert "error" not in p
    assert (p["society_id"], p["role_code"], p["role"], p["entity_id"]) == (0, code, role, None)
    assert p["qr_version"] is None and p["sig"] is None


def test_platform_code_is_case_and_space_tolerant_for_manual_entry():
    p = qr_service.parse_qr_payload("  0-mst-none  ")
    assert p["role_code"] == "MST" and p["entity_id"] is None


@pytest.mark.parametrize("bad", [
    "1-MST-None",             # a platform code belongs to society 0 only
    "0-MST-7",                # and has no entity
    "0-MST-0",
    "0-ADT-None-1-abc12",     # and is never signed
    "0-ADV-",                 # entity missing
    "0-ADT",                  # too short
])
def test_malformed_platform_codes_are_rejected(bad):
    assert "error" in qr_service.parse_qr_payload(bad)


@pytest.mark.parametrize("code", ["APT", "VND", "SEC", "ACC", "SPV", "STF", "ADM"])
def test_none_is_not_an_entity_for_any_other_role(code):
    """'None' is legal ONLY for the three platform codes; everywhere else the entity must be a number."""
    assert "error" in qr_service.parse_qr_payload(f"1-{code}-None")


# ── parsing: the employee codes ───────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("code,role", [("ACC", "accountant"), ("SPV", "supervisor"), ("STF", "staff")])
def test_employee_code_parses_plain_and_signed(code, role):
    plain = qr_service.parse_qr_payload(f"3-{code}-41")
    assert (plain["society_id"], plain["role_code"], plain["role"], plain["entity_id"]) == (3, code, role, 41)
    signed = qr_service.parse_qr_payload(f"3-{code}-41-1234-abcdef0123")
    assert signed["qr_version"] == 1234 and signed["sig"] == "abcdef0123"


def test_unknown_role_codes_are_still_rejected():
    assert "error" in qr_service.parse_qr_payload("1-XYZ-5")


# ── always PASS ───────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("code,label,role", [("ADT", "Auditor", "auditor"), ("ADV", "Adviser", "adviser"),
                                              ("MST", "Master", "master")])
@pytest.mark.parametrize("gate_society", [None, 0, 1, 2, 987654])
def test_platform_pass_is_accepted_at_every_gate_without_touching_the_database(no_db, code, label, role, gate_society):
    res = qr_service.validate_qr_code(f"0-{code}-None", gate_society)
    assert res["status"] == "PASS"
    assert res["gate_action"] == "allow"
    assert res["user"]["role"] == role
    assert res["user"]["name"] == label
    assert res["user"]["id"] is None


@pytest.mark.parametrize("mode", ["entry", "exit"])
def test_platform_pass_passes_in_both_directions(no_db, mode):
    assert qr_service.validate_qr_code("0-MST-None", 1, mode=mode)["status"] == "PASS"


def test_a_malformed_platform_code_is_denied_not_passed(no_db):
    for bad in ("1-MST-None", "0-MST-7", "0-ADT-None-1-abc12"):
        res = qr_service.validate_qr_code(bad, 1)
        assert res["status"] == "FAIL" and res["gate_action"] == "deny", bad


def test_platform_codes_generate_as_the_literal_text_and_are_never_signed(no_db):
    for code in ("ADT", "ADV", "MST"):
        img, payload = qr_service.generate_qr_code(0, code, None)
        assert payload == f"0-{code}-None"
        assert img.startswith("data:image/png;base64,")
        assert "error" not in qr_service.parse_qr_payload(payload)


def test_platform_codes_are_not_signable():
    assert not set(roles.ALWAYS_PASS_CODES) & qr_service._QR_SIGNABLE_ROLES


# ── employee passes are signed like SEC ───────────────────────────────────────────────────────────────────────────
def test_employee_team_codes_are_signable():
    assert {"ACC", "SPV", "STF"} <= qr_service._QR_SIGNABLE_ROLES


@pytest.mark.parametrize("code", ["ACC", "SPV", "STF"])
def test_team_pass_is_signed_over_society_role_entity_version(monkeypatch, code):
    monkeypatch.setattr(qr_service, "_get_signing_secret", lambda _sid: "k")
    monkeypatch.setattr(qr_service, "_current_qr_version", lambda role, eid: 4321)
    _, payload = qr_service.generate_qr_code(2, code, 17)
    expected = hmac.new(b"k", f"2-{code}-17-4321".encode(), hashlib.sha256).hexdigest()[:10]
    assert payload == f"2-{code}-17-4321-{expected}"


@pytest.mark.parametrize("code", ["ACC", "SPV", "STF"])
def test_unsigned_team_pass_is_refused_when_the_society_has_a_signing_key(monkeypatch, no_db, code):
    """No legacy printed team passes exist, so there is no transition window: a typed '<society>-ACC-<id>' must not
    get past signing just because a user id is easy to guess."""
    monkeypatch.setattr(qr_service, "_get_signing_secret", lambda _sid: "k")
    res = qr_service.validate_qr_code(f"1-{code}-5", 1)
    assert res["status"] == "FAIL" and res["gate_action"] == "deny"
    assert "not signed" in res["reason"]


def test_team_pass_with_a_stale_version_is_revoked(monkeypatch, no_db):
    monkeypatch.setattr(qr_service, "_get_signing_secret", lambda _sid: "k")
    monkeypatch.setattr(qr_service, "_current_qr_version", lambda role, eid: 9999)  # reissued since printing
    sig = hmac.new(b"k", b"1-ACC-5-1111", hashlib.sha256).hexdigest()[:10]
    res = qr_service.validate_qr_code(f"1-ACC-5-1111-{sig}", 1)
    assert res["status"] == "FAIL" and "revoked" in res["reason"].lower()


def test_team_pass_with_a_forged_signature_is_refused(monkeypatch, no_db):
    monkeypatch.setattr(qr_service, "_get_signing_secret", lambda _sid: "k")
    monkeypatch.setattr(qr_service, "_current_qr_version", lambda role, eid: 1111)
    res = qr_service.validate_qr_code("1-ACC-5-1111-0000000000", 1)
    assert res["status"] == "FAIL" and "revoked" in res["reason"].lower()


def test_a_pass_for_another_society_is_refused_at_this_gate(no_db):
    res = qr_service.validate_qr_code("2-ACC-5", 1)
    assert res["status"] == "FAIL" and "society" in res["reason"].lower()
