"""Setup Wizard audit fixes (Oct 2026): billing-basis gate, no duplicate component ids, live Review."""
import collections
import json

import pytest

w = pytest.importorskip("app.dash_apps.pages.setup_wizard")


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    monkeypatch.setattr(w.db, "_execute", lambda *a, **k: None)


def _ids(component, out):
    if isinstance(component, (list, tuple)):
        for c in component:
            _ids(c, out)
        return
    cid = getattr(component, "id", None)
    if cid is not None:
        out.append(json.dumps(cid, sort_keys=True) if isinstance(cid, dict) else cid)
    kids = getattr(component, "children", None)
    if kids is not None:
        _ids(kids, out)


def test_no_duplicate_component_ids_across_steps():
    ids = []
    for cat in w.CATEGORIES:
        _ids(w.render_category_content(cat, None), ids)
    assert [k for k, n in collections.Counter(ids).items() if n > 1] == []


@pytest.mark.parametrize("basis,budget,rate,amt,ok", [
    ("undivided_interest", 0, 9, 9, False), ("undivided_interest", 50000, 0, 0, True),
    ("per_sqft", 0, 0, 0, False), ("per_sqft", 0, 3.5, 0, True),
    ("fixed", 0, 0, 0, False), ("fixed", 0, 0, 1200, True), (None, 1, 0, 0, True),
])
def test_billing_basis_gate(basis, budget, rate, amt, ok):
    assert (w.apt_charges_error(basis, budget, rate, amt) is None) is ok


def test_review_shows_live_values_and_flags_gaps():
    body = w.render_review({"state": "UP", "address": "", "apt_basis": "undivided_interest", "apt_budget": 0,
                            "apt_interest": 2.5, "central_tds": True, "tan": "", "bf_ids": [], "bf_amts": []}, None)
    text = json.dumps(body, default=lambda o: o.to_plotly_json() if hasattr(o, "to_plotly_json") else str(o))
    assert "2.5%" in text and "Address is empty" in text and "Monthly Common-Expense Budget" in text


def test_interest_has_no_wizard_cap():
    assert not hasattr(w, "MAX_INTEREST_RATE_PCT")


# ── fund collection modes (regime parameters) ──────────────────────────────────
def test_scheme_packs_define_fund_parameters():
    from schemes.loader import load_all
    packs = {p.code: {x.key: x for x in p.params} for p in load_all()}
    assert packs["UP_AOA_2010"]["fund_collection_mode"].value_text == "fy_close"
    assert packs["UP_AOA_2010"]["fund_allocation_basis"].value_text == "undivided_interest"
    assert packs["GENERIC"]["fund_collection_mode"].value_text == "on_bill"
    assert packs["GENERIC"]["fund_allocation_basis"].value_text == "per_sq_ft"
    for code in ("UP_AOA_2010", "GENERIC"):
        assert set(packs[code]["fund_collection_mode"].choices) == {"on_bill", "fy_close", "none"}
        assert set(packs[code]["fund_allocation_basis"].choices) == {"per_sq_ft", "construction_cost", "undivided_interest", "none"}


def test_generated_sql_block_is_current():
    import subprocess, sys
    r = subprocess.run([sys.executable, "scripts/build_scheme_sql.py", "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_fund_collection_fallback_matches_packs():
    from app.services.statutory_rules import fund_collection_for_regime
    assert fund_collection_for_regime("UP_AOA_2010") == ("fy_close", "undivided_interest")
    assert fund_collection_for_regime("GENERIC") == ("on_bill", "per_sq_ft")


def test_up_fund_note_says_not_billed_by_default():
    flags = {"sinking": False, "repair": False,
             "rules": {"sinking": {"mode": "optional", "min_pct": None}, "repair": {"mode": "optional", "min_pct": None}}}
    assert "year" in w.fund_note(flags, "UP_AOA_2010") and "nothing is added to the monthly bill" in w.fund_note(flags, "UP_AOA_2010")


# ── Funds step: prescribed / opted funds, collection mode, allocation basis ─────
UP_DEFAULT = ("fy_close", "undivided_interest")      # UP_AOA_2010 scheme defaults
GENERIC_DEFAULT = ("on_bill", "per_sq_ft")           # GENERIC scheme defaults


@pytest.mark.parametrize("statutory,regime,levy,cm,bp,expected", [
    # a state-prescribed fund: always on the bill, shared by construction cost, whatever else is chosen
    (True, UP_DEFAULT, "no", "none", "per_sq_ft", ("on_bill", "construction_cost")),
    (True, GENERIC_DEFAULT, "no", "regime_default", "regime_default", ("on_bill", "construction_cost")),
    # UP: not collected until the society opts in; opting in with no other choice follows the regime (year close)
    (False, UP_DEFAULT, "no", "regime_default", "regime_default", ("none", "undivided_interest")),
    (False, UP_DEFAULT, "yes", "regime_default", "regime_default", ("fy_close", "undivided_interest")),
    (False, UP_DEFAULT, "yes", "on_bill", "regime_default", ("on_bill", "undivided_interest")),
    (False, UP_DEFAULT, "yes", "on_bill", "per_sq_ft", ("on_bill", "per_sq_ft")),
    (False, UP_DEFAULT, "yes", "none", "regime_default", ("none", "undivided_interest")),
    # GENERIC no longer bills a fund the society has not opted into; opting in follows the regime (on the bill)
    (False, GENERIC_DEFAULT, "no", "regime_default", "regime_default", ("none", "per_sq_ft")),
    (False, GENERIC_DEFAULT, "yes", "regime_default", "construction_cost", ("on_bill", "construction_cost")),
    (False, GENERIC_DEFAULT, "no", "none", "regime_default", ("none", "per_sq_ft")),
    # a regime that collects nothing, opted in: needs a concrete way to bill
    (False, ("none", "none"), "yes", "regime_default", "regime_default", ("on_bill", "per_sq_ft")),
])
def test_fund_effective(statutory, regime, levy, cm, bp, expected):
    assert w.fund_effective(statutory, regime[0], regime[1], levy, cm, bp) == expected


def _plan(**kw):
    base = {"statutory": False, "min_pct": None, "mode": "on_bill", "basis": "per_sq_ft"}
    return {"sinking": {**base, **kw.get("sinking", {})}, "repair": {**base, **kw.get("repair", {"mode": "none"})}}


def test_funds_error_rules():
    assert w.funds_error(_plan(), 0, 0, 0).startswith("Funds: the Sinking Fund is collected on every bill")
    assert w.funds_error(_plan(), 2, 0, 0) is None
    assert w.funds_error(_plan(sinking={"mode": "fy_close"}), 0, 0, 0) is None            # not on the bill: no rate asked
    assert "below the statutory minimum" in w.funds_error(_plan(sinking={"statutory": True, "min_pct": 0.25, "basis": "construction_cost"}), 0.1, 0, 5e7)
    assert "Construction Cost of Project" in w.funds_error(_plan(sinking={"basis": "construction_cost"}), 0.25, 0, 0)
    assert w.funds_error(_plan(sinking={"basis": "construction_cost"}), 0.25, 0, 5e7) is None


def test_funds_step_is_registered_after_apartment_charges():
    assert w.CATEGORIES.index("Funds") == w.CATEGORIES.index("Apartment Charges") + 1


def test_fund_rate_inputs_live_only_on_the_funds_step():
    for cat in w.CATEGORIES:
        ids = []
        _ids(w.render_category_content(cat, None, "UP"), ids)
        assert ("sw-apt-sinking" in ids) == (cat == "Funds"), cat


def test_prescribed_state_locks_the_fund_questions():
    ids = []
    _ids(w.render_category_content("Funds", None, "MH"), ids)
    assert not any("sw-pol-choice" in i for i in ids)          # nothing to choose: the state prescribes both funds
    assert "sw-apt-sinking" in ids and "sw-apt-repair" in ids


def test_optional_state_asks_levy_mode_and_basis():
    ids = []
    _ids(w.render_category_content("Funds", None, "UP"), ids)
    for key in ("levy_sinking_fund", "sinking_fund_collection", "sinking_fund_basis",
                "levy_repair_fund", "repair_fund_collection", "repair_fund_basis"):
        assert json.dumps({"type": "sw-pol-choice", "key": key}, sort_keys=True) in ids, key


def test_fund_policy_values_are_valid_choices():
    from app.services import regime_rules_admin as rra
    for fund in ("sinking", "repair"):
        assert {v for v, _ in rra.POLICY_SPECS[f"{fund}_fund_collection"][2]} == {"regime_default", "on_bill", "fy_close", "none"}
        assert {v for v, _ in rra.POLICY_SPECS[f"{fund}_fund_basis"][2]} == {"regime_default", "per_sq_ft", "construction_cost", "undivided_interest"}
        assert rra.policy_default(f"{fund}_fund_collection") == "regime_default"


def test_layout_builds_and_every_callback_registers():
    """Guards two crashes that stopped the wizard loading: dbc.Spinner(style=...) and a callback decorator that read
    _hidden_spinner before it was defined."""
    dash = pytest.importorskip("dash")
    dbc = pytest.importorskip("dash_bootstrap_components")
    from app.dash_apps.callbacks.setup_wizard_callbacks import register_setup_wizard_callbacks
    app = dash.Dash(__name__, suppress_callback_exceptions=True, external_stylesheets=[dbc.themes.BOOTSTRAP])
    app.layout = w.get_setup_wizard_layout(None)
    register_setup_wizard_callbacks(app)
    assert len(app.callback_map) >= 12
