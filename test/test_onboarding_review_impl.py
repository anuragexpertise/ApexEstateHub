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


def test_missing_migration_column_does_not_crash_the_hub(monkeypatch):
    from app.services import onboarding_service as ob

    def boom(sql, params=None, fetch_one=False):
        if "onboarding_phase" in sql or "signing_mode" in sql:
            raise Exception('column "onboarding_phase" does not exist (signing_mode)')
        return {"esign_required": False}
    monkeypatch.setattr(ob, "_row", lambda sql, params=None, **k: boom(sql, params))
    assert ob.society_phase(1) == "complete"          # un-migrated DB: nothing is phase-locked
    assert ob.signing_mode(1) == "password"


def _capture_callbacks(module, register_name):
    """Register a callback module against a stub app and return {function name: undecorated function}."""
    got = {}

    class StubApp:
        def callback(self, *a, **k):
            def deco(f):
                got[f.__name__] = getattr(f, "__wrapped__", f)
                return f
            return deco

        def clientside_callback(self, *a, **k):
            return None
    getattr(module, register_name)(StubApp())
    return got


def test_signature_preview_reads_inputs_list_and_returns_one_entry_per_box(monkeypatch):
    """Regression: ctx.states_list holds only States, so reading states_list[1] raised IndexError (500 on picking a signature)."""
    from dash import no_update
    from app.dash_apps.callbacks import onboarding_callbacks as oc

    fn = _capture_callbacks(oc, "register_onboarding_callbacks")["onb_sig_preview"]

    def ident(office, field):
        return {"type": f"{oc.P}-f", "office": office, "field": field}

    class FakeCtx:
        triggered_id = ident("president", "sig")
        inputs_list = [[{"id": ident("president", "sig"), "value": "data:image/png;base64,AAAA"},
                        {"id": ident("secretary", "sig"), "value": None}]]
        states_list = [[{"id": ident("president", "sig"), "value": "p.png"},
                        {"id": ident("secretary", "sig"), "value": None}]]
        outputs_list = [{"id": ident("president", "sig-preview")}, {"id": ident("secretary", "sig-preview")}]
    monkeypatch.setattr(oc, "ctx", FakeCtx)
    out = fn(["data:image/png;base64,AAAA", None], ["p.png", None])
    assert isinstance(out, list) and len(out) == 2
    assert out[0] is not no_update and out[1] is no_update
