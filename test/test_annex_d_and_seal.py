"""Annex D (data-protection and custody schedule) and the confirmation-gated seal."""
import pytest
from app.services import onboarding_service as ob


def _soc(**kw):
    base = {"name": "Green Apts", "grievance_officer_name": "R. Sharma", "grievance_officer_email": "r@x.in",
            "grievance_officer_phone": None, "stepup_password_hash": "hash", "signing_mode": "password"}
    base.update(kw)
    return base


def test_annex_d_content_and_roles():
    content, ctl = ob._annex_d(1, _soc())
    assert content["roles"]["data_fiduciary"] == "Green Apts"
    assert content["roles"]["data_processor"] == ob.OPERATOR_LEGAL_NAME_DEFAULT
    assert content["grievance_officer"]["email"] == "r@x.in"
    assert len(content["sub_processors"]) == len(ob.SUB_PROCESSOR_CATEGORIES)
    assert all(c["passed"] for c in ctl.values())


def test_annex_d_providers_come_from_environment_not_invented(monkeypatch):
    monkeypatch.setenv("HOSTING_PROVIDER", "Acme Cloud")
    monkeypatch.delenv("EMAIL_PROVIDER", raising=False)
    content, _ = ob._annex_d(1, _soc())
    providers = {c["category"]: c["provider"] for c in content["sub_processors"]}
    assert providers["Hosting and database"] == "Acme Cloud"
    assert providers["Transactional email and notifications"] == "as notified by the Operator"


@pytest.mark.parametrize("kw,control", [({"grievance_officer_name": None}, "grievance_officer"),
                                         ({"grievance_officer_email": "", "grievance_officer_phone": ""}, "grievance_contact"),
                                         ({"stepup_password_hash": ""}, "stepup_set")])
def test_annex_d_blocks_when_missing(kw, control):
    _, ctl = ob._annex_d(1, _soc(**kw))
    assert not ctl[control]["passed"] and ctl[control]["blocking"]


def test_every_control_has_a_fix_target():
    _, d_ctl = ob._annex_d(1, _soc())
    keys = {("D", k) for k in d_ctl}
    keys |= {("A", "regime_assigned"), ("A", "unverified_instruments"),
             ("B", "wizard_submitted"), ("B", "committee_seated"), ("B", "grievance_officer"), ("B", "rates_pending_ca"),
             ("C", "balanced"), ("C", "accounts_known"), ("C", "funds_backed"), ("C", "arrears_tie"), ("C", "bank_agrees")}
    assert keys <= set(ob.CONTROL_FIX)


def test_fix_targets_are_real_rail_keys_or_committee():
    from app.dash_apps.pages.setup_wizard import CATEGORIES
    assert all(v in CATEGORIES or v == "committee" for v in ob.CONTROL_FIX.values())


def test_seal_needs_exact_i_agree_and_password(monkeypatch):
    calls = []
    monkeypatch.setattr(ob, "seal_annexes", lambda sid, uid: calls.append((sid, uid)) or {"ok": 1})
    import app.services.auth_service as au
    monkeypatch.setattr(au, "verify_password_with_lockout", lambda uid, pw: (pw == "right", "Admin password is wrong."))
    for phrase in ("", "i agree", "I  AGREE", "AGREE"):
        with pytest.raises(ob.OnboardingError, match="I AGREE"):
            ob.seal_with_confirmation(1, 2, phrase, "right")
    with pytest.raises(ob.OnboardingError, match="password"):
        ob.seal_with_confirmation(1, 2, "I AGREE", "wrong")
    assert calls == []
    assert ob.seal_with_confirmation(1, 2, " I AGREE ", "right") == {"ok": 1} and calls == [(1, 2)]
