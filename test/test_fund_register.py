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
    assert set(fr.FUND_ORDER) == {"ifms_corpus", "major_repair", "reserve", "sinking", "repair"}
    for key, f in fr.FUNDS.items():
        assert f["status"] in fr.STATUS_META and f["verification"] in fr.VERIFY_META, key
        assert f["parameters"] and f["appropriations"], key
    prescribed = {k for k in fr.FUND_ORDER if fr.is_prescribed(k)}
    assert prescribed == {"ifms_corpus", "major_repair", "reserve"}
    assert {k for k in fr.FUND_ORDER if fr.FUNDS[k]["opt_in_policy"]} == {"sinking", "repair"}   # exactly the optional ones


def test_optional_funds_are_active_only_once_opted():
    assert fr.active_keys({"sinking": "none", "repair": "none"}) == prescribed_keys()
    assert fr.active_keys({"sinking": "on_bill"}) == prescribed_keys() | {"sinking"}
    assert fr.active_keys({"repair": "fy_close"}) == prescribed_keys() | {"repair"}
    assert fr.active_keys(None) == set(fr.FUND_ORDER)          # None means 'no filtering'


def prescribed_keys():
    return {k for k in fr.FUND_ORDER if fr.is_prescribed(k)}


def test_unread_or_unprescribed_figures_are_never_marked_checked():
    for key in ("sinking", "repair", "ifms_corpus", "reserve"):
        assert fr.FUNDS[key]["verification"] == "provisional", key
    assert fr.FUNDS["major_repair"]["verification"] == "checked"


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


def test_ifms_is_statutory_major_repair_is_model_bye_law_sinking_is_optional():
    from app.services.up_aoa_fund_catalog import bf_info
    tags = lambda acc: " ".join(t for t, _ in bf_info(acc)["tags"])
    assert "Statutory" in tags(3230) and "Model Bye-Law" in tags(3270) and "Optional" in tags(3210)
    assert "Provisional" in tags(3230)          # IFMS slabs come from reports of the notification, not its text
