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


def test_fy_int_rejects_non_integers():
    from app.services import onboarding_service as ob
    assert ob._fy_int(2026) == 2026 and ob._fy_int("2026") == 2026 and ob._fy_int(2026.0) == 2026
    for bad in (None, "", "abc", "2026.5", 2026.5, True, 12, 99999, "1e3"):
        assert ob._fy_int(bad) is None


def test_needs_review_surfaces_in_rail(monkeypatch):
    from app.services import onboarding_service as ob
    monkeypatch.setattr(ob, "declaration", lambda sid: {"steps": {
        "funds": {"status": "done", "needs_review": True},
        "gst": {"status": "done", "needs_review": False},
        "tds": {"status": "skipped", "needs_review": True}}})
    st = ob.step_statuses(1)
    assert st["funds"]["status"] == "needs_review"
    assert st["gst"]["status"] == "done" and st["tds"]["status"] == "skipped"
    assert wr.status_of(st, "Funds") == "needs_review"


def _admin_save(monkeypatch, values):
    from app.services import onboarding_service as ob
    saved = {}
    monkeypatch.setattr(ob, "declaration", lambda sid: {})
    monkeypatch.setattr(ob, "_save_declaration", lambda sid, d, aid: saved.update(d))
    monkeypatch.setattr(ob, "_committee_complete", lambda sid: True)
    return ob.save_step(1, 1, "administrator", values), saved


def test_blank_or_missing_confirmation_is_rejected(monkeypatch):
    for vals in ({"stepup_secret": "Str0ng!Passw0rd#1"},
                 {"stepup_secret": "Str0ng!Passw0rd#1", "stepup_confirm": ""},
                 {"stepup_secret": "Str0ng!Passw0rd#1", "stepup_confirm": "Str0ng!Passw0rd#2"}):
        res, saved = _admin_save(monkeypatch, vals)
        assert not res["ok"] and any("confirm" in e.lower() for e in res["errors"])
        assert not (saved.get("draft", {}).get("administrator") or {}).get("stepup_hash")


def test_stage_tracker_is_one_chevron_row(monkeypatch):
    from app.dash_apps.pages import onboarding_page as op
    rows = [{"n": i, "code": f"c{i}", "label": f"L{i}", "text": f"t{i}",
             "status": "done" if i < 3 else "current" if i == 3 else "todo"} for i in range(1, 8)]
    monkeypatch.setattr(op.ob, "stage_report", lambda sid: rows)
    t = op.tracker(1)
    assert t.className == "onb-chev" and len(t.children) == 7
    assert t.children[1].className == "onb-chev-item done" and t.children[2].className == "onb-chev-item current"


def test_rail_styles_only_set_cursor(monkeypatch):
    from app.dash_apps.callbacks import onboarding_wizard_callbacks as cb
    styles = cb._rail_item_styles({"tds": {"status": "skipped"}}, 0)
    assert len(styles) == len(CATEGORIES) and all(set(s) == {"cursor"} for s in styles)
    assert styles[CATEGORIES.index("TAN & TDS Rates")]["cursor"] == "default"
