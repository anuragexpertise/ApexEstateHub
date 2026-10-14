"""UP AOA fund register: only prescribed funds and funds the society opts into; each with status, parameters and the
accounts it is appropriated to; consistent with seed.py and estatehub.sql. No database, no Dash."""
import re
import tomllib
from pathlib import Path

import pytest

from schemes import fund_register as fr

ROOT = Path(__file__).resolve().parent.parent
SQL = (ROOT / "database" / "estatehub.sql").read_text(encoding="utf-8")


def _seed():
    import database.seed as seed
    return seed


def test_register_lists_only_prescribed_and_optional_funds():
    assert set(fr.FUND_ORDER) == {"ifms_corpus", "major_repair", "reserve", "sinking", "repair", "depreciation"}
    for key, f in fr.FUNDS.items():
        assert f["status"] in fr.STATUS_META and f["verification"] in fr.VERIFY_META, key
        assert f["parameters"] and f["appropriations"], key
    prescribed = {k for k in fr.FUND_ORDER if fr.is_prescribed(k)}
    assert prescribed == {"ifms_corpus", "major_repair", "reserve"}
    assert {k for k in fr.FUND_ORDER if fr.FUNDS[k]["opt_in_policy"]} == {"sinking", "repair", "depreciation"}   # exactly the optional ones


def test_optional_funds_are_active_only_once_opted():
    assert fr.active_keys({"sinking": "none", "repair": "none"}) == prescribed_keys()
    assert fr.active_keys({"sinking": "on_bill"}) == prescribed_keys() | {"sinking"}
    assert fr.active_keys({"repair": "fy_close"}) == prescribed_keys() | {"repair"}
    assert fr.active_keys({"depreciation": "fy_close"}) == prescribed_keys() | {"depreciation"}
    assert fr.active_keys(None) == set(fr.FUND_ORDER)          # None means 'no filtering'


def prescribed_keys():
    return {k for k in fr.FUND_ORDER if fr.is_prescribed(k)}


def test_unread_or_unprescribed_figures_are_never_marked_checked():
    for key in ("sinking", "repair", "depreciation", "reserve"):
        assert fr.FUNDS[key]["verification"] == "provisional", key
    assert fr.FUNDS["major_repair"]["verification"] == "checked"
    # IFMS slabs are the regulation text as supplied; the notification itself was not read, so never 'checked'
    assert fr.FUNDS["ifms_corpus"]["verification"] == "supplied"


def test_transfer_fee_matches_scheme_pack():
    pack = tomllib.loads((ROOT / "schemes" / "UP_AOA_2010.toml").read_text(encoding="utf-8"))
    param = next(p for p in pack["parameter"] if p["key"] == "transfer_fee_pct")
    assert fr.FUNDS["major_repair"]["rate_pct"] == param["value"] == 0.5


def test_seed_takes_its_fund_mappings_and_locks_from_the_register():
    seed = _seed()
    mapped = {a: h for a, h, _ in seed.UP_AOA_ACCOUNT_MAPPINGS}
    for acc, head, _ in fr.account_mappings():
        assert mapped[acc] == head
    assert seed.STATUTORY_PRINCIPAL_LOCKS == fr.principal_locks() == {3230: 100.0}


def test_fund_accounts_exist_in_the_chart_and_billing_finds_them_by_name():
    seed = _seed()
    by_id = {a[0]: a for a in seed.ACCOUNTS}
    for key in fr.FUND_ORDER:
        acc = fr.FUNDS[key]["account"]
        assert acc["id"] in by_id, key
        # ACCOUNTS row = (id, name, tab, header label, parent, Dr/Cr, has_bf, ...): [1] is accounts.name
        assert by_id[acc["id"]][1] == acc["seed_name"], f"{key}: seed names it {by_id[acc['id']][1]!r}"
        assert by_id[acc["id"]][6], f"{key}: account cannot carry a brought-forward balance"
    # fn_auto_generate_receivables finds the on-bill funds by NAME, so the names are load-bearing
    assert "%Sinking Fund Reserve%" in SQL and "%Repair & Maintenance Fund Reserve%" in SQL
    assert "Sinking Fund Reserve" in by_id[3210][1] and "Repair & Maintenance Fund Reserve" in by_id[3220][1]


def test_reserve_and_repair_share_one_account_and_the_register_says_so():
    assert fr.FUNDS["reserve"]["account"]["id"] == fr.FUNDS["repair"]["account"]["id"] == 3220
    rows = {r["key"]: r for r in fr.register_rows({"sinking": "none", "repair": "on_bill"})}
    assert rows["repair"]["shares_account"] and rows["reserve"]["shares_account"]


def test_register_rows_show_only_held_funds_and_the_route_for_the_chosen_mode():
    names = {3210: "Sinking Fund Reserve", 3220: "Repair & Maintenance Fund Reserve"}
    held = fr.register_rows({"sinking": "on_bill", "repair": "none"}, names, {"apt_sinking_fund_rate": 0.5})
    assert [r["key"] for r in held] == ["ifms_corpus", "major_repair", "reserve", "sinking"]
    sinking = held[-1]
    assert [r["trigger"] for r in sinking["routes"]] == ["Monthly bill (collection = on_bill)"]
    assert sinking["routes"][0]["cr"] == "Sinking Fund Reserve (3210)"
    yr = fr.register_rows({"sinking": "fy_close"}, names)[-1]
    assert yr["routes"][0]["cr"].endswith("(3220)")             # surplus pool, not the sinking account


def test_billing_channels_cover_the_nine_ways_money_arrives():
    assert [c["no"] for c in fr.BILLING_CHANNELS] == list(range(9))
    for c in fr.BILLING_CHANNELS:
        assert c["support"] in fr.SUPPORT_META and set(c["funds"]) <= set(fr.FUNDS)
    manual = {c["no"] for c in fr.BILLING_CHANNELS if c["support"] == "manual"}
    assert manual == {4, 7, 8}          # special levy, common-area rent, non-mutual income: the admin records them


def test_sql_functions_named_in_the_register_exist():
    for key in fr.FUND_ORDER:
        for r in fr.FUNDS[key]["appropriations"]:
            for fn in re.findall(r"\bfn_[a-z_]+", r["function"]):
                assert f"FUNCTION {fn}(" in SQL, f"{key}: {fn} is not defined in estatehub.sql"
    for c in fr.BILLING_CHANNELS:
        for fn in re.findall(r"\bfn_[a-z_]+", c["engine"]):
            assert f"FUNCTION {fn}" in SQL or fn == "fn_ensure_major_repair_fund", f"channel {c['no']}: {fn}"


def test_wizard_brought_forward_hides_unopted_optional_funds():
    from app.services.up_aoa_fund_catalog import active_keys, bf_info
    held = active_keys({"sinking": "none", "repair": "none"})
    assert bf_info(3210, held)["hidden"] is True                     # sinking not opted: no row
    assert bf_info(3220, held)["label"] == "Reserve Fund"
    assert bf_info(3230, held)["hidden"] is False and bf_info(3270, held)["hidden"] is False
    both = active_keys({"sinking": "on_bill", "repair": "on_bill"})
    assert bf_info(3210, both)["hidden"] is False
    assert bf_info(3220, both)["label"] == "Reserve Fund / Repair & Maintenance Fund Reserve"
    assert bf_info(3100, held) is None and bf_info(3240, held) is None  # ordinary accounts
    other = bf_info(3230, held, up=False)                             # not the UP regime: no UP labels or badges
    assert other["label"] is None and other["tags"] == []
    assert bf_info(3210, held, up=False)["hidden"] is True
    assert bf_info(3280, held)["hidden"] is True                          # depreciation fund not opted: no row
    opted = active_keys({"depreciation": "fy_close"})
    assert bf_info(3280, opted)["hidden"] is False and bf_info(3280, opted)["label"] == "Depreciation Fund (DepFund)"


def test_ifms_is_statutory_major_repair_is_model_bye_law_sinking_is_optional():
    from app.services.up_aoa_fund_catalog import bf_info
    tags = lambda acc: " ".join(t for t, _ in bf_info(acc)["tags"])
    assert "Statutory" in tags(3230) and "Model Bye-Law" in tags(3270) and "Optional" in tags(3210)
    assert "notification not read" in tags(3230)      # IFMS slabs are the supplied regulation text, not the notification itself


# ── Depreciation Fund: its own account, a correct citation ─────────────────────────────────────────────────────────
def test_depreciation_fund_has_its_own_account_not_the_expense_or_gifts():
    seed = _seed()
    by_id = {a[0]: a for a in seed.ACCOUNTS}
    acc = fr.FUNDS["depreciation"]["account"]
    assert acc["id"] == 3280 and acc["id"] not in (5110, 3240)
    row = by_id[3280]
    assert row[1] == "Depreciation Fund" and row[2] == "DepFund" and row[4] == 3200 and row[5] == "Cr" and row[6]
    assert by_id[5110][1] == "Depreciation" and by_id[3240][1] == "Gifts Received"      # untouched
    assert (3280, "DEPRECIATION_FUND") in {(a, h) for a, h, _ in seed.UP_AOA_ACCOUNT_MAPPINGS}
    assert any(h[1] == "DEPRECIATION_FUND" for h in seed.STATUTORY_HEADS_UP_AOA)         # the head the mapping needs exists


def test_sql_depreciation_function_uses_3280_and_real_columns():
    i = SQL.index("CREATE OR REPLACE FUNCTION fn_ensure_depreciation_fund")
    j = SQL.index("CREATE OR REPLACE FUNCTION fn_appropriate_depreciation_fund")
    ensure = SQL[i:j]
    assert "3280" in ensure and "3240" not in ensure and "'DepFund'" in ensure
    assert "built_up_area" not in SQL                     # apartments has apartment_size, not built_up_area


def test_depreciation_params_no_longer_cite_bye_law_46d_as_their_source():
    pack = tomllib.loads((ROOT / "schemes" / "UP_AOA_2010.toml").read_text(encoding="utf-8"))
    dep = [p for p in pack["parameter"] if p["key"].startswith("depreciation_fund_")]
    assert len(dep) == 3
    for p in dep:
        assert p["provision"] == "-" and "clause" not in p
        assert p["base_source"] == "engine_default" and p["enforcement"] == "policy" and p["verification"] == "provisional"
        assert "loans" in p["source"] and "46(d)" in p["source"]       # says what 46(d) really is
        assert "bye-law 46(d)" not in p["provision"]


# ── IFMS slabs: UP RERA Reg. 47(d), as supplied ─────────────────────────────────────────────────────────────────────
def test_ifms_slabs_match_the_supplied_regulation_text():
    g = {r["code"]: (r["rate_min"], r["rate_max"], r["area_sqm_from"], r["area_sqm_to"]) for r in fr.IFMS_SLABS["group_housing"]}
    assert g == {"EWS": (20, 30, 30, 40), "LIG": (30, 40, 35, 45), "STUDIO": (30, 40, 35, 45), "MIG": (40, 50, 45, 90),
                 "HIG": (50, 60, 90, 200), "LUXURY": (70, 80, 200, 300), "ULTRA_LUXURY": (90, 100, 300, None)}
    for ptype in ("plotted_housing", "plotted_commercial"):
        assert {r["code"]: (r["rate_min"], r["rate_max"]) for r in fr.IFMS_SLABS[ptype]} == {"PLOT_LE_100": (20, 30), "PLOT_GT_100": (30, 40)}
    assert {r["code"]: (r["rate_min"], r["rate_max"]) for r in fr.IFMS_SLABS["commercial"]} == {"NON_CENTRAL_AC": (40, 40), "CENTRAL_AC": (50, 50)}
    assert set(fr.IFMS_SLABS) == set(fr.IFMS_PROJECT_TYPES)
    assert all(r["rate_min"] <= r["rate_max"] for rows in fr.IFMS_SLABS.values() for r in rows)


def test_ifms_lookup_and_amounts():
    assert fr.ifms_rate_range("group_housing", "HIG") == (50, 60)
    assert fr.ifms_rate_range("commercial", "CENTRAL_AC") == (50, 50)
    assert fr.ifms_amount_range("group_housing", "MIG", 1000) == (40000, 50000)
    with pytest.raises(KeyError):
        fr.ifms_rate_range("group_housing", "NOPE")
    with pytest.raises(KeyError):
        fr.ifms_rate_range("hotel", "HIG")


def test_ifms_notes_say_what_the_text_leaves_open():
    notes = " ".join(fr.IFMS_NOTES)
    assert "which area" in notes and "overlap" in notes and "who picks" in notes
