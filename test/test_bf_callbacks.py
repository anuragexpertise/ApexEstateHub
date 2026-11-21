"""Brought Forward wizard: tests that call the REAL callbacks and render the REAL screen.

``test_bf_wizard_tasks.py`` covers the pure functions behind the screen. These tests go one level up:
they register the wizard callbacks on a recording fake app, then invoke them with the payload shapes
Dash really sends (``ctx.inputs_list`` / ``ctx.outputs_list`` are lists of ``{id, property, value}``
dicts), so a callback that breaks on a real payload fails here.

No database: ``ob.load_draft`` / ``ob.known_flat_numbers`` and the session are monkeypatched.
"""
import base64
import io

import pytest
from openpyxl import load_workbook

from app.dash_apps.callbacks import onboarding_wizard_callbacks as cb
from app.dash_apps.pages import setup_wizard as sw
from app.services import bf_layout as bl
from app.services import onboarding_service as ob
from app.services import paired_intake as pi

# ── harness ──────────────────────────────────────────────────────────────


class _FakeApp:
    """Records each registered callback by function name."""

    def __init__(self):
        self.fns = {}

    def callback(self, *_a, **_kw):
        def deco(f):
            self.fns[f.__name__] = f
            return f
        return deco


class _Ctx:
    def __init__(self, inputs_list=None, outputs_list=None):
        self.inputs_list = inputs_list or []
        self.outputs_list = outputs_list or []


@pytest.fixture(scope="module")
def callbacks():
    app = _FakeApp()
    cb.register_onboarding_wizard_callbacks(app)
    # @require_session wraps with functools.wraps; __wrapped__ is the raw callback body.
    return {name: getattr(f, "__wrapped__", f) for name, f in app.fns.items()}


@pytest.fixture(autouse=True)
def _admin_session(monkeypatch):
    monkeypatch.setattr(cb, "_session", lambda: (1, 1, "admin"))
    monkeypatch.setattr(ob, "known_flat_numbers", lambda sid: ["101", "102"])


def _walk_nodes(nodes):
    for n in nodes:
        if isinstance(n, int):
            yield n
            continue
        if n.get("acc") is not None:
            yield n["acc"]
        yield from _walk_nodes(n.get("children") or [])


def _all_acc_ids():
    ids = []
    for side in ("Cr", "Dr"):
        ids += list(_walk_nodes(bl.side_nodes(side, lambda a: False)))
    return ids


def _group_keys():
    keys = []
    for side in ("Cr", "Dr"):
        keys += [g["key"] for g in cb._group_nodes(bl.side_nodes(side, lambda a: False))]
    return keys


def _balanced():
    """Assets = Liabilities + Equity = 1,000,000; receivables control = 330,000 (SDrDig)."""
    return {3100: "1000000", 1330: "300000", 1311: "300000", 1312: "50000",
            1120: "10000", 1200: "10000", 1510: "330000"}


def _arrears(total="330000.00"):
    return [{"flat_number": "101", "amount": total, "overdue_days": "", "remarks": ""}]


def _run_rollup(callbacks, monkeypatch, amounts, arrears, key_order=None):
    """Invoke sw_bf_rollup with a Dash-shaped context; returns ({node key: text}, cr_total, dr_total, controls)."""
    keys = list(key_order or _group_keys())
    inputs = [{"id": {"type": "sw-bf-amt", "acc_id": a}, "property": "value", "value": amounts.get(a)}
              for a in _all_acc_ids()]
    outputs = [{"id": {"type": "sw-bf-total", "node": k}, "property": "children"} for k in keys]
    monkeypatch.setattr(cb, "ctx", _Ctx(inputs_list=[inputs, {"id": "sw-bf-arrears-grid", "property": "data",
                                                              "value": arrears}],
                                        outputs_list=[outputs]))
    totals, cr_total, dr_total, controls = callbacks["sw_bf_rollup"]([amounts.get(a) for a in _all_acc_ids()],
                                                                     arrears)
    return dict(zip(keys, totals)), cr_total, dr_total, controls


def _texts(comp):
    out = []

    def walk(c):
        if c is None:
            return
        if isinstance(c, (list, tuple)):
            for x in c:
                walk(x)
            return
        if isinstance(c, str):
            out.append(c)
            return
        walk(getattr(c, "children", None))
    walk(comp)
    return " | ".join(out)


# ── roll-up callback ─────────────────────────────────────────────────────


def test_rollup_edit_updates_group_totals_side_totals_and_controls(callbacks, monkeypatch):
    by_key, cr_total, dr_total, controls = _run_rollup(callbacks, monkeypatch, _balanced(), _arrears())
    assert by_key["eq"] == "₹1,000,000.00"
    assert by_key["res"] == "₹0.00"
    assert by_key["nca"] == "₹20,000.00"
    assert by_key["fa"] == "₹10,000.00"          # nested group: Fixed Assets has its own total
    assert by_key["bank"] == "₹350,000.00"       # nested group: Bank A/c has its own total
    assert by_key["ca"] == "₹650,000.00"
    assert by_key["sdr"] == "₹330,000.00"
    assert cr_total == "₹1,000,000.00" and dr_total == "₹1,000,000.00"
    text = _texts(controls)
    assert "balanced: OK" in text and "funds_backed: OK" in text and "arrears_tie: OK" in text


def test_rollup_totals_follow_the_output_key_not_the_position(callbacks, monkeypatch):
    forward, *_ = _run_rollup(callbacks, monkeypatch, _balanced(), _arrears())
    backward, *_ = _run_rollup(callbacks, monkeypatch, _balanced(), _arrears(), key_order=_group_keys()[::-1])
    assert forward == backward                     # same total on the same heading, whatever the order
    assert backward["bank"] == "₹350,000.00" and backward["fa"] == "₹10,000.00"


def test_rollup_each_control_reacts_to_its_own_edit(callbacks, monkeypatch):
    # balanced breaks: 1,000 more liabilities than assets
    amounts = {**_balanced(), 2240: "1000"}
    *_, controls = _run_rollup(callbacks, monkeypatch, amounts, _arrears())
    assert "balanced: FAIL" in _texts(controls)
    # funds_backed breaks: a 400,000 Corpus Fund with no bank at all
    *_, controls = _run_rollup(callbacks, monkeypatch, {3230: "400000"}, [])
    assert "funds_backed: FAIL" in _texts(controls)
    # arrears_tie breaks: arrears grid disagrees with the receivables control, and says why
    *_, controls = _run_rollup(callbacks, monkeypatch, _balanced(), _arrears("100.00"))
    text = _texts(controls)
    assert "arrears_tie: FAIL" in text and "does not match" in text


@pytest.mark.parametrize("amounts,arrears", [
    ({}, []),                                                   # empty grid
    ({3100: "", 1330: None}, None),                             # blank cells, no arrears data
    ({3100: "abc", 1330: "12,5", 1200: "10.00"}, _arrears()),   # non-numeric cells
    ({1510: "5"}, [{"flat_number": "101", "amount": "", "overdue_days": "", "remarks": ""},
                   {"flat_number": "", "amount": "x"}]),        # blank / garbage arrears rows
])
def test_rollup_never_raises_on_blank_or_invalid_input(callbacks, monkeypatch, amounts, arrears):
    _, cr_total, dr_total, controls = _run_rollup(callbacks, monkeypatch, amounts, arrears)
    assert cr_total.startswith("₹") and dr_total.startswith("₹")
    assert "balanced:" in _texts(controls)


# ── arrears grid callbacks ───────────────────────────────────────────────


def test_add_row_callback_appends_one_blank_row(callbacks):
    data = _arrears("100.00")
    out = callbacks["sw_bf_arrears_add"](1, data)
    assert len(out) == 2 and out[0] == data[0]
    assert out[1] == {"flat_number": "", "amount": "", "overdue_days": "", "remarks": ""}
    assert callbacks["sw_bf_arrears_add"](1, None) == [out[1]]       # empty / untouched grid


def test_total_callback_follows_edit_add_and_delete(callbacks):
    total = callbacks["sw_bf_arrears_total"]
    rows = [{"flat_number": "101", "amount": "100.00"}, {"flat_number": "102", "amount": "200.00"}]
    assert total(rows) == "₹300.00"
    rows[0]["amount"] = "500.00"                                      # edit
    assert total(rows) == "₹700.00"
    rows = callbacks["sw_bf_arrears_add"](1, rows)                    # add a blank row: amount is ""
    assert total(rows) == "₹700.00"
    rows.pop(1)                                                       # delete
    assert total(rows) == "₹500.00"
    assert total(None) == "₹0.00" and total([]) == "₹0.00"


def test_arrears_total_feeds_the_arrears_tie_control_live(callbacks, monkeypatch):
    rows = _arrears("330000.00")
    *_, ok = _run_rollup(callbacks, monkeypatch, _balanced(), rows)
    assert "arrears_tie: OK" in _texts(ok)
    rows = callbacks["sw_bf_arrears_add"](1, rows)
    rows[-1].update(flat_number="102", amount="50.00")                # a second flat pushes the total over
    *_, bad = _run_rollup(callbacks, monkeypatch, _balanced(), rows)
    text = _texts(bad)
    assert "arrears_tie: FAIL" in text and "330050" in text


# ── the screen, as the admin sees it ─────────────────────────────────────

_SAVED_ROWS = [{"acc_id": a, "bf_amount": v, "remarks": ""} for a, v in _balanced().items()]


def _saved_draft(monkeypatch, receivables):
    monkeypatch.setattr(ob, "load_draft", lambda sid: {"brought_forward": {
        "fy": "2026", "as_on_date": "2026-09-30", "rows": _SAVED_ROWS, "receivables": receivables}})
    monkeypatch.setattr(sw.db, "_execute", lambda *a, **k: None)


def _render(is_current=True):
    return sw.render_category_content("Brought Forward", 1, is_current=is_current)


def _find(comp, cid):
    found = []

    def walk(c):
        if c is None or isinstance(c, str):
            return
        if isinstance(c, (list, tuple)):
            for x in c:
                walk(x)
            return
        if getattr(c, "id", None) == cid:
            found.append(c)
        walk(getattr(c, "children", None))
    walk(comp)
    return found[0] if found else None


def _tokens(comp):
    """Document-order sequence of string ids and plain-text children."""
    seq = []

    def walk(c):
        if c is None:
            return
        if isinstance(c, str):
            seq.append(c)
            return
        if isinstance(c, (list, tuple)):
            for x in c:
                walk(x)
            return
        cid = getattr(c, "id", None)
        if isinstance(cid, str):
            seq.append(cid)
        walk(getattr(c, "children", None))
    walk(comp)
    return seq


def test_screen_sections_are_in_the_planned_order(monkeypatch):
    _saved_draft(monkeypatch, _arrears())
    seq = _tokens(_render())
    order = ["sw-bf-fy", "Funds selected for this society", "sw-bf-tpl", "sw-bf-file", "sw-bf-pr-tpl",
             "sw-bf-pr-file", "sw-bf-arrears-grid", "sw-bf-arrears-add", "sw-bf-controls",
             "Brought Forward Accounts"]
    pos = []
    for marker in order:
        assert marker in seq, f"{marker!r} missing from the screen"
        pos.append(seq.index(marker))
    assert pos == sorted(pos), dict(zip(order, pos))
    # the arrears grid sits with its own buttons: no other section heading in between
    between = seq[seq.index("sw-bf-pr-file"):seq.index("sw-bf-arrears-grid")]
    assert "Brought Forward Accounts" not in between and "Funds selected for this society" not in between


def test_screen_button_labels_are_exact(monkeypatch):
    _saved_draft(monkeypatch, [])
    body = _render()
    labels = {"sw-bf-tpl": "Download 'Statement' template", "sw-bf-file": "Fill 'Brought Forward' Grid",
              "sw-bf-pr-tpl": "Download 'Apt-Arrears' template", "sw-bf-pr-file": "Fill 'Apt-Arrears' Grid",
              "sw-bf-arrears-add": "+ Add row"}
    for cid, label in labels.items():
        btn = _find(body, cid)
        assert btn is not None, cid
        assert btn.children == label, (cid, btn.children)


def test_screen_shows_saved_arrears_and_controls_on_first_load(monkeypatch):
    saved = _arrears("330000.00")
    _saved_draft(monkeypatch, saved)
    body = _render()
    assert _find(body, "sw-bf-arrears-grid").data == saved            # grid is seeded, not empty
    text = _texts(_find(body, "sw-bf-controls"))                       # panel present before any edit
    assert "balanced: OK" in text and "funds_backed: OK" in text and "arrears_tie: OK" in text
    assert _find(body, "sw-bf-side-total-Cr").children == "₹1,000,000.00"
    assert _find(body, "sw-bf-side-total-Dr").children == "₹1,000,000.00"


def test_screen_with_nothing_saved_still_has_a_controls_panel(monkeypatch):
    _saved_draft(monkeypatch, [])
    monkeypatch.setattr(ob, "load_draft", lambda sid: {})
    panel = _find(_render(), "sw-bf-controls")
    assert panel is not None and "balanced:" in _texts(panel)
    assert _find(_render(), "sw-bf-arrears-grid").data == []


# ── Next: the grid's contents are what gets saved ────────────────────────


def _next_form(grid):
    """What wizard_nav builds: _gather(ctx.states_list) for the Brought Forward step."""
    states = [{"id": "sw-bf-fy", "property": "value", "value": 2026},
              {"id": "sw-bf-as-on", "property": "date", "value": "2026-09-30"},
              {"id": "sw-bf-arrears-grid", "property": "data", "value": grid}]
    return cb._gather(states)


def test_next_with_an_untouched_grid_resaves_the_filed_arrears(monkeypatch):
    saved = _arrears("330000.00")
    _saved_draft(monkeypatch, saved)
    grid = _find(_render(), "sw-bf-arrears-grid").data                 # the admin never touches it
    v = cb._raw_step_values("brought_forward", _next_form(grid))
    assert v["receivables"] == saved


def test_next_saves_edits_and_drops_blank_rows(monkeypatch):
    _saved_draft(monkeypatch, _arrears("330000.00"))
    grid = [{"flat_number": "101", "amount": "400.00", "overdue_days": "", "remarks": "edited"},
            {"flat_number": "", "amount": "", "overdue_days": "", "remarks": ""}]
    v = cb._raw_step_values("brought_forward", _next_form(grid))
    assert v["receivables"] == [grid[0]]
    assert v["fy"] == 2026 and v["as_on_date"] == "2026-09-30"


# ── template downloads (NMF task A) ──────────────────────────────────────


def _xlsx_from_download(res):
    assert res["base64"] is True
    return load_workbook(io.BytesIO(base64.b64decode(res["content"])))


def test_apt_arrears_download_uses_the_saved_year_and_as_on_date(callbacks, monkeypatch):
    monkeypatch.setattr(ob, "load_draft", lambda sid: {"brought_forward": {"fy": 2027, "as_on_date": "2027-03-31"}})
    res = callbacks["sw_bf_pr_tpl"](1)
    assert res["filename"] == "Apt-Arrears 2027.xlsx"
    wb = _xlsx_from_download(res)
    ws = wb["2027"]
    assert [c.value for c in ws[1]] == ["flat_no", "amount", "due_days", "remarks", "as_on_date"]
    assert ws["E2"].value == "2027-03-31"
    assert "Receivables" not in wb.sheetnames


def test_apt_arrears_download_falls_back_to_the_default_year(callbacks, monkeypatch):
    monkeypatch.setattr(ob, "load_draft", lambda sid: {})
    monkeypatch.setattr(cb, "fy_start_year", lambda: 2031)
    res = callbacks["sw_bf_pr_tpl"](1)
    assert res["filename"] == "Apt-Arrears 2031.xlsx"
    assert _xlsx_from_download(res).sheetnames[0] == "2031"


def test_statement_download_uses_the_saved_year_and_as_on_date(callbacks, monkeypatch):
    monkeypatch.setattr(ob, "load_draft", lambda sid: {"brought_forward": {"fy": 2027, "as_on_date": "2027-03-31"}})
    monkeypatch.setattr(pi, "eligible_accounts", lambda: [
        {"account_id": 1311, "account_tab": "SBI", "account_name": "SBI A/c", "side": "Dr"}])
    step = cb.CATEGORIES.index("Brought Forward")
    res = callbacks["sw_bf_template"](1, step)
    assert res["filename"] == "Statement 2027.xlsx"
    ws = _xlsx_from_download(res)["2027"]
    assert ws["G2"].value == "2027-03-31"


def test_statement_download_works_with_the_real_account_list(callbacks, monkeypatch):
    """Regression: eligible_accounts() lacked the account_id/account_tab/account_name keys the template builder reads,
    so the download raised KeyError. Nothing is stubbed here."""
    monkeypatch.setattr(ob, "load_draft", lambda sid: {"brought_forward": {"fy": 2027, "as_on_date": "2027-03-31"}})
    step = cb.CATEGORIES.index("Brought Forward")
    res = callbacks["sw_bf_template"](1, step)
    ws = _xlsx_from_download(res)["2027"]
    accounts = pi.eligible_accounts()
    assert accounts and ws.max_row == len(accounts) + 1
    assert [ws.cell(row=r, column=1).value for r in range(2, ws.max_row + 1)] == [a["id"] for a in accounts]
    assert ws["C2"].value == accounts[0]["name"] and ws["B2"].value == accounts[0]["tab"]
