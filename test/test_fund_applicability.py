"""Sinking / Repair funds are a Setup Wizard question only where the state prescribes them."""
from app.services.statutory_rules import fund_rules_for_state, regime_for_society, state_has_own_regime


def test_up_has_no_statutory_fund_rates():
    r = fund_rules_for_state("UP")
    assert regime_for_society(None, "UP") == "UP_AOA_2010"
    assert r["sinking"]["mode"] == "optional" and r["repair"]["mode"] == "optional"
    assert r["corpus"]["mode"] == "optional"          # never a setup rate


def test_full_state_name_resolves_like_the_code():
    assert fund_rules_for_state("Uttar Pradesh") == fund_rules_for_state("UP")


def test_mh_prescribes_sinking_and_repair():
    r = fund_rules_for_state("MH")
    assert (r["sinking"]["mode"], r["sinking"]["min_pct"]) == ("statutory", 0.25)
    assert (r["repair"]["mode"], r["repair"]["min_pct"]) == ("statutory", 0.75)


def test_unseeded_state_is_flagged_as_fallback():
    assert not state_has_own_regime("KA")
