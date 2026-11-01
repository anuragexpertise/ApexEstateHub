"""Onboarding Review implementation: step-key mapping, xlsx parsing, signing modes, phases, portal lock (no DB needed)."""
from decimal import Decimal

from app.dash_apps.pages.setup_wizard import CATEGORIES
from app.dash_apps.pages import wizard_registry as wr


def test_every_wizard_step_maps_to_a_draft_key():
    assert set(wr.STEP_KEYS) == set(CATEGORIES)
    assert wr.draft_key("Instructions") is None
    assert wr.draft_key("TAN & TDS Rates") == "tds"


def test_status_of_uses_draft_keys():
    st = {"tds": {"status": "done"}, "gst": {"status": "skipped"}}
    assert wr.status_of(st, "TAN & TDS Rates") == "done"
    assert wr.status_of(st, "GSTIN & GST Rate") == "skipped"
    assert wr.status_of(st, "Instructions") == "done"
    assert wr.status_of(st, "Funds") == "todo"


def test_removed_steps_are_gone():
    import app.services.statutory_rules as sr
    for k in ("State Act & Rules", "Model Bye-Laws Adoption"):
        assert k not in CATEGORIES and k not in sr.STEP_ROWS and k not in sr.STEP_LINK_CATEGORIES


def test_form_to_draft_values():
    from app.dash_apps.callbacks import onboarding_wizard_callbacks as cb
    form = {"tds-section": {0: "194C", 1: "194J"}, "tds-discriminator": {0: "", 1: ""},
            "tds-nature": {0: "x", 1: "y"}, "tds-rate": {0: 2, 1: None}, "tds-rate-no-pan": {0: None, 1: None},
            "tds-single-bill": {0: None, 1: None}, "tds-agg-bill": {0: None, 1: None},
            "sw-society-tan": "ABCD12345E"}
    v = cb._to_step_values("tds", form)
    assert v["tan"] == "ABCD12345E"
    assert [r["section"] for r in v["rows"]] == ["194C"]      # blank rows are "not entered", never a silent default
    assert cb._to_step_values("administrator", {"sw-qr-secret": "a", "sw-qr-secret-confirm": "b"}) == {"stepup_secret": "a", "stepup_confirm": "b"}


def test_dec_parser():
    from app.dash_apps.callbacks.onboarding_wizard_callbacks import _dec
    assert _dec("2.5", Decimal(0), Decimal(100)) == Decimal("2.50")
    assert _dec("") is None
    for bad in ("abc", "-1", "101"):
        try:
            _dec(bad, Decimal(0), Decimal(100)); assert False, bad
        except ValueError:
            pass


def test_signing_modes_and_phases_declared():
    from app.services import onboarding_service as ob
    assert ob.SIGNING_MODES == ("password", "esign", "paper")
    assert ob.ONBOARDING_PHASES == ("enrollment", "adoption", "advisers", "complete")


def test_enrollment_lock_roles():
    from app.security.setup_guard import ENROLLMENT_LOCKED_ROLES
    assert set(ENROLLMENT_LOCKED_ROLES) == {"apartment", "vendor", "security"}
