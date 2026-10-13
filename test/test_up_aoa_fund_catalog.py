"""UP AOA fund catalogue: every fund is labelled statutory / model bye-law / optional-provisional, the
Brought Forward fund accounts line up with the chart of accounts, and the catalogue agrees with the scheme pack.
No database, no Dash."""
import re
import tomllib
from pathlib import Path

from app.services.up_aoa_fund_catalog import (BF_FUND_INFO, STATUS_META, UP_AOA_FUNDS, VERIFY_META, bf_info,
                                              fund_facts)

ROOT = Path(__file__).resolve().parent.parent


def test_every_fund_has_status_verification_and_facts():
    for key, f in UP_AOA_FUNDS.items():
        assert f["status"] in STATUS_META, key
        assert f["verification"] in VERIFY_META, key
        for label, text in fund_facts(f):
            assert text and text.strip(), (key, label)


def test_prescribed_vs_optional_split():
    assert UP_AOA_FUNDS["ifms_corpus"]["status"] == "statutory"
    assert UP_AOA_FUNDS["major_repair"]["status"] == "model_bye_law"
    assert UP_AOA_FUNDS["reserve"]["status"] == "model_bye_law"
    # Neither the Act nor the Model Bye-Laws mention a sinking fund or a separate repair fund.
    assert UP_AOA_FUNDS["sinking"]["status"] == "optional"
    assert UP_AOA_FUNDS["repair"]["status"] == "optional"
    # Only the two optional funds take a rate on the Funds step.
    assert {k for k, f in UP_AOA_FUNDS.items() if f["rate_applicable"]} == {"sinking", "repair"}


def test_optional_and_unread_rates_are_never_marked_checked():
    assert UP_AOA_FUNDS["sinking"]["verification"] == "provisional"
    assert UP_AOA_FUNDS["repair"]["verification"] == "provisional"
    # IFMS rates come from press reports of the 2026 notification, not its text.
    assert UP_AOA_FUNDS["ifms_corpus"]["verification"] == "provisional"
    assert UP_AOA_FUNDS["reserve"]["verification"] == "provisional"   # 25% is an engine default


def test_transfer_fee_matches_scheme_pack():
    pack = tomllib.loads((ROOT / "schemes" / "UP_AOA_2010.toml").read_text(encoding="utf-8"))
    param = next(p for p in pack["parameter"] if p["key"] == "transfer_fee_pct")
    assert UP_AOA_FUNDS["major_repair"]["rate_pct"] == param["value"] == 0.5


def test_brought_forward_accounts_exist_in_chart_of_accounts():
    seed = (ROOT / "database" / "seed.py").read_text(encoding="utf-8")
    for acc_id in BF_FUND_INFO:
        m = re.search(rf"^\s*\({acc_id},\s*\"[^\"]*\",\s*\"[^\"]*\",\s*\"[^\"]*\",\s*\d+,\s*\"(Cr|Dr)\",\s*(True|False)", seed, re.M)
        assert m, f"account {acc_id} missing from ACCOUNTS"
        assert m.group(2) == "True", f"account {acc_id} cannot carry a brought-forward balance"


def test_bf_info_labels_and_tags():
    assert bf_info(3999) is None and bf_info(3240) is None
    ifms = bf_info(3230)
    assert "IFMS" in ifms["label"] and "Corpus Fund" in ifms["label"]
    assert any(t.endswith("Statutory") for t, _ in ifms["tags"])
    shared = bf_info(3220)       # one account carries both the Reserve Fund and the Repair & Maintenance Fund reserve
    texts = " ".join(t for t, _ in shared["tags"])
    assert "Model Bye-Law" in texts and "Optional" in texts
    major = bf_info(3270)
    assert "\u00bd%" in major["label"]
    assert bf_info(3210)["label"] == "Sinking Fund Reserve"
