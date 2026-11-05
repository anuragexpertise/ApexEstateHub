"""Setup Wizard, 'Legal Regime Selection' step: Your Legal Regime card, Central Act / Operational-law answers,
informational Central Acts block and the Legal Hierarchy (Precedence Order) table (Level | Name | Status)."""
import json
import re

import pytest

w = pytest.importorskip("app.dash_apps.pages.setup_wizard")
sr = pytest.importorskip("app.services.statutory_rules")


# ── helpers ────────────────────────────────────────────────────────────────────────────────────────────
def _walk(c):
    if isinstance(c, (list, tuple)):
        for x in c:
            yield from _walk(x)
        return
    yield c
    kids = getattr(c, "children", None)
    if kids is not None:
        yield from _walk(kids)


def _text(c):
    return "".join(x for x in _walk(c) if isinstance(x, str))


def _by_id(c, cid):
    return next((x for x in _walk(c) if getattr(x, "id", None) == cid), None)


def _table(rows):
    """[(level, name text, status text)] with the Level carried down to the group's later rows."""
    out, level = [], None
    for tr in rows:
        lv, name, st = tr.children
        if _text(lv):
            level = _text(lv)
        out.append((level, _text(name), _text(st)))
    return out


def _by_title(rows, level=None):
    """{instrument title: status} (the name cell reads 'Title (year)unverified \u2014 note')."""
    title = lambda n: re.split(r"(?: \(\d{4}\))?(?:un)?verified", n)[0].strip()
    return {title(n): st for lv, n, st in _table(rows) if level is None or lv == level}


def inst(itype, title, applies_when="always", verification="unverified", status="active", url=None, year=2000):
    return {"instrument_type": itype, "title": title, "enactment_year": year, "applies_when": applies_when,
            "verification": verification, "status": status, "source_url": url}


CATALOG = [
    inst("Central Act", "Central GST Act", "central_gst"),
    inst("Central Act", "Income-tax Act, 1961", "central_it_tan", status="superseded"),
    inst("Central Act", "Income-tax Act, 2025", "central_it_tan", year=2025),
    inst("Central Act", "Digital Personal Data Protection Act", "always", verification="verified", url="https://example.org/dpdp"),
    inst("Central Act", "Bharatiya Sakshya Adhiniyam", "info"),
    inst("Central Act", "Code on Wages", "has_employees"),
    inst("Central Act", "PSARA", "has_security_agency"),
    inst("Central Rules", "DPDP Rules", "always"),
    inst("Act", "UP Apartment Act", "always", verification="verified", url="https://example.org/upa"),
    inst("Rules", "UP Apartment Rules", "always", status="draft"),
    inst("Bye-laws", "Model Bye-Laws", "always"),
]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(w.db, "_execute", lambda *a, **k: None)
    seen = {}

    def fake_instruments(regime=sr.DEFAULT_REGIME):
        seen["regime"] = regime
        return list(CATALOG) if regime != "GENERIC" else [r for r in CATALOG if r["title"] != "UP Apartment Act"]

    monkeypatch.setattr(sr, "instruments_for_regime", fake_instruments)
    monkeypatch.setattr(sr, "regime_selection", lambda st, const: (
        {"regime": "UP_AOA_2010", "dedicated": True, "name": "UP Apartment Act 2010 pack", "status": "active",
         "constitution_label": sr.CONSTITUTION_LABELS.get((const or "AOA").upper(), const)} if (st, (const or "AOA")) == ("UP", "AOA") else
        {"regime": "GENERIC" if st else None, "dedicated": False, "name": None, "status": None,
         "constitution_label": sr.CONSTITUTION_LABELS.get((const or "AOA").upper(), const)}))
    return seen


YES = {"central_it_tan": True, "central_tds": True, "central_gst": True, "central_rera": True,
       "has_employees": False, "has_security_agency": False}


def _rows(answers=None, state="UP", constitution="AOA"):
    rows, _ = w.legal_hierarchy_rows(None, state, answers or YES, constitution)
    return rows


# ── Legal Hierarchy table ─────────────────────────────────────────────────────────────────────────────
def test_table_has_level_name_status_columns_and_three_cells_per_row():
    assert all(len(tr.children) == 3 for tr in _rows())


def test_status_labels_use_the_four_required_words():
    statuses = {s for _, _, s in _table(_rows())}
    assert statuses == {"Locked", "In-active", "Provisional", "Normal"}


def test_status_badge_colours():
    colours = {k: w.legal_status_badge(k).color for k in w.LEGAL_STATUS}
    assert colours == {"locked": "success", "inactive": "secondary", "provisional": "warning", "normal": "info"}


def test_answering_no_makes_the_triggered_acts_in_active_with_the_reason():
    rows = _rows({**YES, "central_gst": False})
    assert _by_title(rows)["Central GST Act"] == "In-active"
    reason = next(n for _, n, _ in _table(rows) if n.startswith("Central GST Act"))
    assert "not triggered: you answered" in reason
    assert _by_title(_rows())["Central GST Act"] == "Locked"                 # Yes brings it back


def test_superseded_and_draft_rows():
    t = _by_title(_rows())
    assert t["Income-tax Act, 1961"] == "In-active"        # repealed: never Locked, even with TAN = Yes
    assert t["Income-tax Act, 2025"] == "Locked"
    assert t["UP Apartment Rules"] == "Provisional"        # draft catalog row


def test_year_is_not_repeated_when_the_title_already_carries_it():
    rows = _table(_rows())
    name = next(n for _, n, _ in rows if n.startswith("Income-tax Act, 2025"))
    assert name.startswith("Income-tax Act, 2025unverified")          # no "(2025)" after "2025"
    assert next(n for _, n, _ in rows if n.startswith("Model Bye-Laws")).startswith("Model Bye-Laws (2000)")   # year still shown otherwise


def test_info_instrument_is_locked_and_labelled_informational():
    row = next(r for r in _table(_rows()) if r[1].startswith("Bharatiya Sakshya Adhiniyam"))
    assert row[2] == "Locked" and "informational" in row[1]


def test_verified_and_unverified_badges_and_links():
    rows = _rows()
    badges = [b for tr in rows for b in _walk(tr.children[1]) if getattr(b, "children", None) in ("verified", "unverified")]
    colour = {b.children: b.color for b in badges}
    assert colour == {"verified": "success", "unverified": "warning"}
    links = [a.href for tr in rows for a in _walk(tr.children[1]) if getattr(a, "href", None)]
    assert links == ["https://example.org/dpdp", "https://example.org/upa"]      # only verified rows link out


def test_operational_instruments_sit_in_the_operational_group_not_central_acts():
    rows = _rows({**YES, "has_employees": True})
    assert _by_title(rows, "L0 Operational laws") == {"Code on Wages": "Locked", "PSARA": "In-active"}
    assert not {"Code on Wages", "PSARA"} & set(_by_title(rows, "L0 Central Acts"))


def test_operational_placeholders_when_the_catalog_has_no_operational_rows(monkeypatch):
    monkeypatch.setattr(sr, "instruments_for_regime",
                        lambda regime: [r for r in CATALOG if r["applies_when"] not in ("has_employees", "has_security_agency")])
    ops = [s for lvl, n, s in _table(_rows({**YES, "has_employees": True})) if lvl == "L0 Operational laws"]
    assert ops == ["Locked", "In-active"]                  # employees = Yes, security agency = No


def test_levels_run_in_precedence_order_and_only_the_first_row_carries_the_badge():
    rows = _rows()
    order = [_text(tr.children[0]) for tr in rows if _text(tr.children[0])]
    assert order == ["L0 Central Acts", "L0 Central Rules & Notifications", "L0 State Acts", "L0 State Rules",
                     "L0 Model Bye-laws (notified)", "L0 Operational laws", "L1 Society-adopted Bye-laws",
                     "L2 General Body Resolutions", "L3 Board / Managing Committee"]
    assert _table(rows)[-3][2] == "Provisional" and _table(rows)[-2][2] == "Normal" and _table(rows)[-1][2] == "Normal"


def test_empty_group_says_so_and_is_in_active(monkeypatch):
    monkeypatch.setattr(sr, "instruments_for_regime", lambda regime: [r for r in CATALOG if r["instrument_type"] == "Central Act"])
    row = next(r for r in _table(_rows()) if r[0] == "L0 State Acts")
    assert row[1] == "None recorded for this regime." and row[2] == "In-active"


def test_no_researched_pack_shows_central_laws_only(_env):
    rows = _rows(state="KA", constitution="AOA")       # fake regime_selection: KA + AOA has no pack -> GENERIC
    assert _env["regime"] == "GENERIC"
    assert next(r for r in _table(rows) if r[0] == "L0 State Acts")[2] == "In-active"


def test_no_state_chosen_falls_back_to_the_default_state(_env):
    # _picked_state_constitution: "State defaults to DEFAULT_STATE when unset" (a society part-way through the wizard).
    _rows(state=None)
    assert _env["regime"] == "UP_AOA_2010"


# ── Your Legal Regime card ─────────────────────────────────────────────────────────────────────────────
def test_card_shows_state_constitution_and_regime():
    txt = _text(w.legal_regime_live(None, "UP", "AOA"))
    assert "Your Legal Regime" in txt and "Uttar Pradesh" in txt
    assert "Apartment Owners' Association (AOA)" in txt and "UP_AOA_2010" in txt
    assert "Society Details step" in txt


def test_card_without_a_state_shows_the_default_state():
    txt = _text(w.legal_regime_live(None, None, "AOA"))
    assert "Uttar Pradesh" in txt and "UP_AOA_2010" in txt
    assert "Choose a State on the Society Details step" not in txt


def test_card_for_a_state_without_a_pack_warns_central_only():
    txt = _text(w.legal_regime_live(None, "KA", "AOA"))
    assert "Karnataka" in txt and "only the Central Acts" in txt and "GENERIC" in txt


# ── the step itself ────────────────────────────────────────────────────────────────────────────────────
def _step(society_id=None, state="UP", constitution="AOA"):
    return w.render_category_content("Legal Regime Selection", society_id, state, constitution=constitution)


def test_step_sections_are_in_the_requested_order():
    txt = _text(_step())
    marks = ["Your Legal Regime", "Central Act Settings", "Operational Laws (Yes / No)",
             "Central Acts (Layer 0 - apply to every society, not a choice)", "informational",
             "Master Settings → RWA Compliance verifies", "Legal Hierarchy (Precedence Order)"]
    pos = [txt.index(m) for m in marks]
    assert pos == sorted(pos)


def test_step_renders_the_table_body_on_first_paint_with_headers():
    step = _step()
    body = _by_id(step, "sw-legal-hierarchy-body")
    assert body is not None and len(body.children) > 9           # was empty until a radio changed
    table = next(t for t in _walk(step) if type(t).__name__ == "Table" and _by_id(t, "sw-legal-hierarchy-body") is not None)
    assert [_text(th) for th in _walk(table) if type(th).__name__ == "Th"] == ["Level", "Name", "Status"]


def test_step_has_the_six_answer_radios_with_defaults():
    step = _step()
    got = {cid: _by_id(step, cid).value for cid in ("sw-central-it-tan", "sw-central-tds", "sw-central-gst", "sw-central-rera",
                                                    "sw-central-employees", "sw-central-security-agency")}
    assert got == {"sw-central-it-tan": True, "sw-central-tds": True, "sw-central-gst": True, "sw-central-rera": True,
                   "sw-central-employees": False, "sw-central-security-agency": False}


def test_saved_draft_answers_restore_the_radios_and_the_table(monkeypatch):
    from app.services import onboarding_service as ob
    monkeypatch.setattr(ob, "load_draft", lambda sid: {"legal_regime": {"central_gst": False, "has_employees": True}})
    step = _step(society_id=7)
    assert _by_id(step, "sw-central-gst").value is False and _by_id(step, "sw-central-employees").value is True
    assert _by_title(_by_id(step, "sw-legal-hierarchy-body").children)["Code on Wages"] == "Locked"


def test_step_keeps_unique_component_ids():
    ids = [json.dumps(c.id, sort_keys=True) if isinstance(c.id, dict) else c.id for c in _walk(_step()) if getattr(c, "id", None) is not None]
    assert len(ids) == len(set(ids))


def test_a_table_failure_does_not_break_the_step(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("catalog down")
    monkeypatch.setattr(w, "legal_hierarchy_rows", boom)
    step = _step()
    assert _by_id(step, "sw-legal-hierarchy-body").children == []
    assert "Your Legal Regime" in _text(step)


# ── callback wiring ────────────────────────────────────────────────────────────────────────────────────
def test_refresh_callback_is_registered_for_card_and_table_with_state_and_constitution_inputs():
    import dash
    from app.dash_apps.callbacks.onboarding_wizard_callbacks import register_onboarding_wizard_callbacks
    app = dash.Dash(__name__, suppress_callback_exceptions=True)
    register_onboarding_wizard_callbacks(app)
    key = next(k for k in app.callback_map if "sw-legal-hierarchy-body" in k)
    assert "sw-legal-regime-live" in key
    inputs = {i["id"] for i in app.callback_map[key]["inputs"]}
    assert {"sw-society-state", "sw-society-constitution", "sw-central-gst", "sw-central-security-agency"} <= inputs
