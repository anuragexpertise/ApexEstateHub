"""Governance (bye-laws / meetings / resolutions) is the society ADMIN's; master keeps rules + catalog."""
import pytest
from dash import html

from app.services import regime_rules_admin as rra

GOOD = "a long enough reason"


# ── who may write ────────────────────────────────────────────────────────────
def test_writer_guard_allows_only_the_societys_own_admin():
    rra._require_writer("admin", 5, 5, master_ok=False)
    with pytest.raises(PermissionError):
        rra._require_writer("master", None, 5, master_ok=False)
    with pytest.raises(PermissionError):
        rra._require_writer("admin", 5, 6, master_ok=False)
    with pytest.raises(PermissionError):
        rra._require_writer("apartment", 5, 5, master_ok=False)


def test_cash_limit_mode_is_society_specific_so_master_cannot_set_it():
    with pytest.raises(PermissionError, match="Admin role required"):
        rra.set_cash_limit_mode(1, "master", 5, "block", GOOD)
    with pytest.raises(PermissionError, match="own society"):
        rra.set_cash_limit_mode(1, "admin", 5, "block", GOOD, actor_society_id=6)


def test_own_admin_really_gets_past_the_guard():
    """Guard passes -> the function reaches its own validation and returns (False, msg) instead of raising."""
    ok, msg = rra.create_meeting(1, "admin", 5, "XX", "2026-01-01", True, None, GOOD, actor_society_id=5)
    assert ok is False and "GBM, EGM, or MC" in msg
    ok, msg = rra.save_bye_law_version(1, "admin", 5, "BL_NOPE", 1, "adopted_as_is", None, "2099-01-01", GOOD,
                                       actor_society_id=5)
    assert ok is False and "Unknown clause" in msg


CALLS = {
    "save_bye_law_version": lambda role, own: rra.save_bye_law_version(
        1, role, 5, "BL_10", 1, "adopted_as_is", None, "2099-01-01", GOOD, actor_society_id=own),
    "create_meeting": lambda role, own: rra.create_meeting(1, role, 5, "GBM", "2026-01-01", True, None, GOOD,
                                                           actor_society_id=own),
    "create_resolution": lambda role, own: rra.create_resolution(1, role, 5, 1, 1, "BL_10", "body", 66.67, False,
                                                                 None, GOOD, actor_society_id=own),
    "link_provisional_to_resolution": lambda role, own: rra.link_provisional_to_resolution(
        1, role, 5, "BL_10", 1, 2, GOOD, actor_society_id=own),
    "link_policy_resolution": lambda role, own: rra.link_policy_resolution(
        1, role, 5, "nodues_blocks_on", 2, actor_society_id=own),
    "record_wizard_policy": lambda role, own: rra.record_wizard_policy(
        1, role, own, 5, "nodues_blocks_on", "loans_only"),
    "record_wizard_adoption": lambda role, own: rra.record_wizard_adoption(
        1, role, own, 5, "BL_10", "adopted_as_is", None),
}


@pytest.mark.parametrize("name", list(CALLS))
def test_master_cannot_edit_society_governance(name):
    with pytest.raises(PermissionError, match="Admin role required"):
        CALLS[name]("master", None)


@pytest.mark.parametrize("name", list(CALLS))
def test_admin_cannot_edit_another_society(name):
    with pytest.raises(PermissionError, match="own society"):
        CALLS[name]("admin", 99)


@pytest.mark.parametrize("name", list(CALLS))
@pytest.mark.parametrize("role", ["apartment", "vendor", "security", None])
def test_other_roles_cannot_edit_governance(name, role):
    with pytest.raises(PermissionError):
        CALLS[name](role, 5)


@pytest.mark.parametrize("fn,args", [
    (rra.save_rule_version, (1, "admin", "UP_AOA_2010", "k", "v", "2099-01-01", "src", "reason", True)),
    (rra.update_instrument, (1, "admin", 3, "active", "a", "p", "s", "2026-01-01", "reason")),
])
def test_rules_and_catalog_stay_master_only(fn, args):
    with pytest.raises(PermissionError):
        fn(*args)


# ── enactment ────────────────────────────────────────────────────────────────
class _DB:
    def __init__(self):
        self.calls = []

    def _execute(self, *a, **k):
        self.calls.append(a)


def _effect(handler, society=5):
    return {"id": 42, "resolution_id": 7, "handler_name": handler, "society_id": society, "payload_json": {}}


def test_admin_cannot_apply_regime_wide_change_and_effect_is_not_marked_failed(monkeypatch):
    spy = _DB()
    monkeypatch.setattr(rra, "db", spy)
    monkeypatch.setattr(rra, "_row", lambda *a, **k: _effect("set_regime_param"))
    ok, msg = rra.execute_enactment(1, "admin", 42, actor_society_id=5)
    assert ok is False and "Master" in msg
    assert spy.calls == []                       # nothing written, not 'failed'


def test_admin_cannot_execute_another_societys_enactment(monkeypatch):
    monkeypatch.setattr(rra, "_row", lambda *a, **k: _effect("set_board_param", society=6))
    with pytest.raises(PermissionError, match="own society"):
        rra.execute_enactment(1, "admin", 42, actor_society_id=5)


def test_master_cannot_execute_society_enactments(monkeypatch):
    monkeypatch.setattr(rra, "_row", lambda *a, **k: _effect("set_board_param"))
    with pytest.raises(PermissionError):
        rra.execute_enactment(1, "master", 42)


# ── auto-activation ──────────────────────────────────────────────────────────
@pytest.fixture()
def activation(monkeypatch):
    state = {"linked": False, "prov": {1: {"id": 11, "proposed_status": "adopted_as_is"}}, "dt": "ADOPT_BYE_LAW",
             "check_err": None, "activated": []}

    def fake_row(sql, params=None):
        if "FROM resolutions r" in sql:
            return {"clause_id": "BL_10", "dt_code": state["dt"]}
        if "resolution_id = %s" in sql:
            return {"x": 1} if state["linked"] else None
        return None

    monkeypatch.setattr(rra, "_row", fake_row)
    monkeypatch.setattr(rra, "_pending_policies", lambda s_, c: state.get("policies", []))
    monkeypatch.setattr(rra, "_activate_policy",
                        lambda *a: (state.setdefault("policy_done", []).append(a[3]), (True, f"Policy {a[3]} active."))[1])
    monkeypatch.setattr(rra, "_latest_provisional", lambda s, c, layer: state["prov"].get(layer))
    monkeypatch.setattr(rra, "_check_resolution", lambda s, c, layer, r: (None, state["check_err"]) if state["check_err"] else ({}, None))
    monkeypatch.setattr(rra, "_activate_provisional",
                        lambda *a: (state["activated"].append(a), (True, "BL_10 (layer 1) is now active."))[1])
    return state


def test_valid_resolution_activates_matching_provisional_choice(activation):
    notes = rra._auto_activate(1, "admin", 5, 7)
    assert len(activation["activated"]) == 1 and "now active" in notes[0]


def test_resolution_of_wrong_kind_for_the_choice_leaves_it_provisional(activation):
    activation["dt"] = "REJECT_BYE_LAW"          # cannot confirm 'adopt as-is'
    notes = rra._auto_activate(1, "admin", 5, 7)
    assert activation["activated"] == [] and "stays provisional" in notes[0]


def test_invalid_resolution_activates_nothing(activation):
    activation["check_err"] = "The meeting that passed this resolution did not record a quorum."
    assert rra._auto_activate(1, "admin", 5, 7) == [] and activation["activated"] == []


def test_a_resolution_backs_only_one_choice(activation):
    activation["linked"] = True
    assert rra._auto_activate(1, "admin", 5, 7) == [] and activation["activated"] == []


def test_no_provisional_choice_means_nothing_to_activate(activation):
    activation["prov"] = {}
    assert rra._auto_activate(1, "admin", 5, 7) == []


# ── policy choices (Setup Wizard) are activated by the same resolution ──────────
def test_passed_resolution_activates_every_pending_policy_of_that_clause(activation):
    activation["prov"] = {}
    activation["policies"] = ["vote_ineligibility_basis", "vote_loan_basis"]
    notes = rra._auto_activate(1, "admin", 5, 7)
    assert activation["policy_done"] == ["vote_ineligibility_basis", "vote_loan_basis"] and len(notes) == 2


def test_invalid_resolution_activates_no_policy(activation):
    activation["prov"] = {}
    activation["policies"] = ["vote_loan_basis"]
    activation["check_err"] = "The meeting that passed this resolution did not record a quorum."
    assert rra._auto_activate(1, "admin", 5, 7) == [] and "policy_done" not in activation


def test_a_resolution_already_backing_something_activates_no_policy(activation):
    activation["prov"] = {}
    activation["policies"] = ["vote_loan_basis"]
    activation["linked"] = True
    assert rra._auto_activate(1, "admin", 5, 7) == [] and "policy_done" not in activation


def test_pending_policies_are_matched_to_their_clause(monkeypatch):
    monkeypatch.setattr(rra, "_rows", lambda *a, **k: [{"policy_key": "vote_ineligibility_basis"},
                                                       {"policy_key": "vote_loan_basis"},
                                                       {"policy_key": "nodues_blocks_on"}])
    assert rra._pending_policies(5, "BL_08") == ["vote_ineligibility_basis", "vote_loan_basis"]
    assert rra._pending_policies(5, "BL_39") == ["nodues_blocks_on"]


# ── Record Policy Choice form ────────────────────────────────────────────────
def test_own_admin_can_record_a_policy_choice(monkeypatch):
    seen = {}
    monkeypatch.setattr(rra, "_row", lambda sql, params=None: (seen.update(params or {}), {"id": 1})[1])
    ok, msg = rra.record_wizard_policy(1, "admin", 5, 5, "nodues_blocks_on", "dues_and_loans", source="Settings")
    assert ok and "provisional" in msg and seen["k"] == "nodues_blocks_on" and seen["role"] == "admin"
    assert seen["why"] == "Recorded in the Settings; awaiting resolution"


def test_policy_choice_must_be_one_of_the_allowed_values():
    assert rra.record_wizard_policy(1, "admin", 5, 5, "nodues_blocks_on", "bogus")[0] is False
    assert rra.record_wizard_policy(1, "admin", 5, 5, "no_such_policy", "x")[0] is False


def test_policy_form_lists_every_setting_and_saves_provisionally(stub):
    tree = stub.render_governance_tabs("admin", 5)
    ids = _ids(tree)
    assert {"gov-pol-key", "gov-pol-value", "gov-pol-save", "gov-pol-info"} <= ids
    text = str(tree)
    assert "Record Policy Choice" in text and "Order matters: save the choice first" in text
    for key, (label, _clause, _c) in rra.POLICY_SPECS.items():
        assert label in text


def test_owner_has_no_policy_form(stub):
    assert not [i for i in _ids(stub.render_governance_tabs("apartment", 5)) if i.startswith("gov-pol-")]


def test_policy_choice_ui_preselects_pending_then_current_and_names_the_clause(stub, monkeypatch):
    monkeypatch.setattr(rra, "list_society_policies", lambda s: {
        "vote_loan_basis": {"value": "margin_60_days", "active": False, "proposed": "any_overdue"}})
    opts, value, info = stub.policy_choice_ui(5, "vote_loan_basis")
    assert value == "any_overdue" and {o["value"] for o in opts} == {"margin_60_days", "any_overdue"}
    assert "BL_08" in str(info) and "Set Society Policy" in str(info)
    monkeypatch.setattr(rra, "list_society_policies", lambda s: {
        "vote_loan_basis": {"value": "margin_60_days", "active": True, "proposed": None}})
    assert stub.policy_choice_ui(5, "vote_loan_basis")[1] == "margin_60_days"


def test_policy_choice_ui_without_a_setting_offers_nothing(stub):
    opts, value, info = stub.policy_choice_ui(5, None)
    assert value is None and info is None and opts[0]["disabled"]


def test_droppable_policy_carries_the_legal_advice_note(stub, monkeypatch):
    monkeypatch.setattr(rra, "list_society_policies", lambda s: {})
    key = next(k for k in rra.POLICY_SPECS if k.startswith("droppable_"))
    assert "advocate" in str(stub.policy_choice_ui(5, key)[2])


def test_wizard_message_no_longer_points_at_the_removed_master_screen(monkeypatch):
    monkeypatch.setattr(rra, "_validate_bye_law_save", lambda *a: None)
    monkeypatch.setattr(rra, "_row", lambda *a, **k: {"x": 1})            # clause already backed
    ok, msg = rra.record_wizard_adoption(1, "admin", 5, 5, "BL_10", "adopted_as_is", None)
    assert ok is False and "Society governance" in msg and "Master" not in msg


# ── Settings summary strip + policy register ─────────────────────────────────
def test_snapshot_counts_pending_choices_and_last_meeting(monkeypatch):
    import datetime
    monkeypatch.setattr(rra, "_row", lambda *a, **k: {"bl": 2, "pol": 1, "last_meeting": datetime.date(2026, 8, 12)})
    monkeypatch.setattr(rra, "list_pending_enactments", lambda s: [1])
    snap = rra.governance_snapshot(5)
    assert snap == {"pending_choices": 3, "last_meeting": datetime.date(2026, 8, 12), "pending_enactments": 1}


def test_snapshot_never_raises_when_tables_are_missing(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no table")
    monkeypatch.setattr(rra, "_row", boom)
    monkeypatch.setattr(rra, "list_pending_enactments", boom)
    assert rra.governance_snapshot(5) == {"pending_choices": 0, "last_meeting": None, "pending_enactments": 0}


def test_settings_summary_points_to_the_governance_section(stub, monkeypatch):
    import datetime
    monkeypatch.setattr(rra, "governance_snapshot",
                        lambda s: {"pending_choices": 3, "last_meeting": datetime.date(2026, 8, 12), "pending_enactments": 0})
    text = str(stub.render_governance_summary("admin", 5))
    assert "12 Aug 2026" in text and "Choices awaiting a resolution" in text and "'3'" in text
    assert "Society governance tabs" in text and "record meetings and resolutions" in text
    assert "view your society" in str(stub.render_governance_summary("apartment", 5))


def test_summary_is_empty_without_a_society(stub, monkeypatch):
    monkeypatch.setattr(stub, "get_current_society_id", lambda: None)
    assert stub.render_governance_summary("admin", None) is None


def test_bye_law_tab_shows_the_policy_register(stub, monkeypatch):
    monkeypatch.setattr(rra, "list_society_policies", lambda s: {
        k: {"value": rra.policy_default(k), "active": False, "proposed": None} for k in rra.POLICY_SPECS})
    text = str(stub.render_governance_tabs("admin", 5))
    assert "Society policy settings" in text and "Pending choice" in text


def test_setup_wizard_no_longer_says_master_links_resolutions():
    src = open("app/dash_apps/pages/setup_wizard.py", encoding="utf-8").read()
    for stale in ("linked by Master", "Master links", "Master → AOA Rule Editor → Society Bye-Laws"):
        assert stale not in src, stale
    assert "Settings → Society governance → Meetings & Resolutions" in src
    assert "Order matters: save the choice first, then record the resolution." in src


# ── guided bye-law form ──────────────────────────────────────────────────────
@pytest.fixture()
def stub(monkeypatch):
    from app.dash_apps.pages import governance_settings as gs
    monkeypatch.setattr(gs, "get_current_society_id", lambda: 5)
    monkeypatch.setattr(rra, "clause_is_locked", lambda s, c: c in rra.STATUTE_BACKED_CLAUSES)
    monkeypatch.setattr(rra, "society_regime", lambda s: "UP_AOA_2010")
    monkeypatch.setattr(rra, "society_cash_mode", lambda s: "warn")
    monkeypatch.setattr(rra, "effective_rules", lambda r, on=None: [])
    monkeypatch.setattr(rra, "scheduled_rules", lambda r: [])
    monkeypatch.setattr(rra, "recent_audit", lambda n=25, society_id=None: [])
    monkeypatch.setattr(rra, "societies_on_regime", lambda r: 1)
    monkeypatch.setattr(rra, "list_society_bye_laws", lambda s: [])
    monkeypatch.setattr(rra, "list_meetings", lambda s: [])
    monkeypatch.setattr(rra, "list_resolutions", lambda s: [])
    monkeypatch.setattr(rra, "list_pending_enactments", lambda s: [])
    monkeypatch.setattr(rra, "list_decision_types", lambda: [])
    monkeypatch.setattr(rra, "list_instruments", lambda r: [])
    monkeypatch.setattr(rra, "model_bye_laws_source",
                        lambda *a: {"reference": "UP Model Bye-Laws 2011", "url": "https://example.test/bl.pdf"})
    from app.dash_apps.pages import portal_pages
    monkeypatch.setattr(portal_pages, "_rwa_compliance_up_page", lambda c, role="master", embedded=False: html.Div("rwa"))
    return gs


def _enabled(opts):
    return {o["value"] for o in opts if not o.get("disabled")}


def test_ordinary_clause_offers_all_three_choices(stub):
    opts, value = stub.bye_choice_ui(5, "BL_10", 1)
    assert _enabled(opts) == {"adopted_as_is", "adopted_with_variation", "not_adopted"} and value == "adopted_as_is"


def test_statute_backed_clause_cannot_be_not_adopted(stub):
    opts, _ = stub.bye_choice_ui(5, "BL_07", 1)
    assert _enabled(opts) == {"adopted_as_is", "adopted_with_variation"}


def test_bl55_is_adopt_as_is_only(stub):
    opts, _ = stub.bye_choice_ui(5, "BL_55", 1)
    assert _enabled(opts) == {"adopted_as_is"}


@pytest.mark.parametrize("layer", [2, 3])
def test_policy_and_board_layers_are_variation_only(stub, layer):
    opts, value = stub.bye_choice_ui(5, "BL_10", layer)
    assert _enabled(opts) == {"adopted_with_variation"} and value == "adopted_with_variation"


def test_as_is_shows_title_and_link_but_no_text_box(stub):
    box, show_var = stub.bye_choice_panel("BL_10", 1, "adopted_as_is")
    assert show_var is False and "https://example.test/bl.pdf" in str(box) and "BL_10" in str(box)


def test_variation_shows_the_text_box(stub):
    _, show_var = stub.bye_choice_panel("BL_10", 1, "adopted_with_variation")
    assert show_var is True


def test_model_bye_laws_link_comes_from_the_catalog_source_reference(monkeypatch):
    monkeypatch.setattr(rra, "_row", lambda *a, **k: {
        "source_reference": "Notification 3977, 16 Nov 2011. Text: https://up.gov.test/model-bye-laws.pdf."})
    assert rra.model_bye_laws_source()["url"] == "https://up.gov.test/model-bye-laws.pdf"


@pytest.mark.parametrize("row", [None, {"source_reference": None}, {"source_reference": "Notification 3977, 16 Nov 2011"},
                                 {"source_reference": "javascript:alert(1)"}])
def test_model_bye_laws_link_falls_back_to_the_official_copy(monkeypatch, row):
    monkeypatch.setattr(rra, "_row", lambda *a, **k: row)
    assert rra.model_bye_laws_source()["url"] == "https://up-rera.in/pdf/Model-By-Laws.pdf"


def test_model_bye_laws_link_is_not_a_server_setting(monkeypatch):
    monkeypatch.setenv("MODEL_BYE_LAWS_URL", "https://example.test/env.pdf")
    monkeypatch.setattr(rra, "_row", lambda *a, **k: None)
    assert rra.model_bye_laws_source()["url"] == "https://up-rera.in/pdf/Model-By-Laws.pdf"


# ── layout ───────────────────────────────────────────────────────────────────
def _ids(node, acc=None):
    acc = set() if acc is None else acc
    if isinstance(node, (list, tuple)):
        for n in node:
            _ids(n, acc)
        return acc
    i = getattr(node, "id", None)
    if isinstance(i, str):
        acc.add(i)
    elif isinstance(i, dict):
        acc.add(i.get("type"))
    ch = getattr(node, "children", None)
    if ch is not None:
        _ids(ch, acc)
    return acc


def _labels(node, acc=None):
    acc = [] if acc is None else acc
    if isinstance(node, (list, tuple)):
        for n in node:
            _labels(n, acc)
        return acc
    if type(node).__name__ == "Tab":
        acc.append(node.label)
    ch = getattr(node, "children", None)
    if ch is not None:
        _labels(ch, acc)
    return acc


TABS = ["RWA Compliance (UP)", "Rules", "Society By-laws", "Meetings & Resolutions"]


def test_admin_has_the_four_tabs_and_the_governance_forms(stub):
    tree = stub.render_governance_tabs("admin", 5)
    assert _labels(tree) == TABS
    ids = _ids(tree)
    assert {"gov-cash-save", "gov-bye-save", "gov-bye-clause", "gov-bye-status", "gov-bye-var-wrap",
            "gov-mtg-save", "gov-res-save"} <= ids
    assert not {i for i in ids if "link" in i}                     # no manual link step any more
    assert "Order matters: save the choice first, then record the resolution." in str(tree)
    assert "An older resolution can't activate a newer choice." in str(tree)
    assert not ({"mrl-key", "mrl-save", "mrl-cat-save"} & ids)      # rule / catalog stay master-only


def test_regime_wide_enactment_is_labelled_not_given_an_execute_button(monkeypatch):
    from app.dash_apps.pages import master_rules_page as mrp
    monkeypatch.setattr(rra, "list_pending_enactments", lambda s: [
        {"id": 1, "resolution_id": 7, "decision_type_code": "X", "clause_id": None, "handler_name": "set_regime_param",
         "payload_json": "{}", "status": "pending"},
        {"id": 2, "resolution_id": 8, "decision_type_code": "SET_BOARD_PARAM", "clause_id": "BL_10",
         "handler_name": "set_board_param", "payload_json": "{}", "status": "pending"}])
    text = str(mrp.render_enactment_section(5, "gov", can_execute=True))
    assert "Regime-wide: Master changes it via Change a rule" in text
    assert text.count("'type': 'gov-enact'") == 1                  # only the society-level effect is executable


def test_owner_is_read_only(stub):
    tree = stub.render_governance_tabs("apartment", 5)
    assert _labels(tree) == TABS
    assert not [i for i in _ids(tree) if i.endswith("-save") or i == "gov-enact"]


def test_no_society_renders_a_message_not_forms(stub, monkeypatch):
    monkeypatch.setattr(stub, "get_current_society_id", lambda: None)
    assert not [i for i in _ids(stub.render_governance_tabs("admin", None)) if i.endswith("-save")]


def test_master_editor_is_rules_only(monkeypatch):
    from unittest import mock
    from app.dash_apps.pages import master_rules_page as mrp
    with mock.patch.multiple(rra, list_instruments=lambda r: [], list_societies_cash_mode=lambda r: [],
                             effective_rules=lambda r, on=None: [], scheduled_rules=lambda r: [],
                             recent_audit=lambda n=25, society_id=None: [], societies_on_regime=lambda r: 0):
        page = mrp.render_master_rules_page()
    ids = _ids(page)
    assert _labels(page) == []                                       # no sub-tabs
    assert "mrl-save" in ids
    assert not [i for i in ids if i.startswith(("mrl-bye", "mrl-mtg", "mrl-res", "mrl-link", "mrl-cat", "mrl-cash"))]


def test_rules_table_labels_kind_as_statute_or_policy(monkeypatch):
    from app.dash_apps.pages import master_rules_page as mrp
    key_stat = next(k for k, v in rra.RULE_SPECS.items() if v.statutory)
    key_pol = next(k for k, v in rra.RULE_SPECS.items() if not v.statutory)
    import datetime
    rows = [{"rule_key": k, "value": 1, "value_text": None, "unit": "", "source_reference": "",
             "effective_from": datetime.date(2026, 1, 1)} for k in (key_stat, key_pol)]
    monkeypatch.setattr(rra, "effective_rules", lambda r, on=None: rows)
    monkeypatch.setattr(rra, "scheduled_rules", lambda r: [])
    monkeypatch.setattr(rra, "recent_audit", lambda n=25, society_id=None: [])
    monkeypatch.setattr(rra, "societies_on_regime", lambda r: 1)
    text = str(mrp.render_rules_sections())
    assert "Statute" in text and "Policy" in text
