"""Pure checks: custom vote-weight parsing, and the State + Constitution -> regime helpers."""
import pytest

from app.dash_apps.callbacks.poll_callbacks import parse_custom_weights

FLATS = {"A-101": 1, "A-201": 2, "B-202": 3}


def test_custom_weights_parse_both_separators_and_blank_lines():
    out, err = parse_custom_weights("A-101=2\n\nA-201: 1.5\n B-202 = 0.5 ", FLATS)
    assert err is None and out == {"1": 2.0, "2": 1.5, "3": 0.5}


@pytest.mark.parametrize("text,needle", [
    ("A-101=2\nA-201=1", "No weight for: B-202"),
    ("A-101=2\nA-201=1\nB-202=x", "must be a number"),
    ("A-101=2\nA-201=1\nB-999=1", "not an active flat"),
    ("A-101=2\nA-101=3\nA-201=1\nB-202=1", "appears twice"),
    ("A-101=-1\nA-201=1\nB-202=1", "cannot be negative"),
    ("A-101 2", "FLAT=weight"),
    ("A-101=0\nA-201=0\nB-202=0", "add up to zero"),
    ("", "No weight for"),
])
def test_custom_weights_refuse_bad_input(text, needle):
    out, err = parse_custom_weights(text, FLATS)
    assert out is None and needle in err


def test_regime_selection_names_the_bundle(monkeypatch):
    from app.services import statutory_rules as sr
    monkeypatch.setattr(sr, "scheme_for", lambda state, const=None: "UP_AOA_2010" if (state, (const or "AOA").upper()) == ("UP", "AOA") else "GENERIC")
    monkeypatch.setattr(sr, "regime_profile", lambda code: (f"{code} profile", "active"))
    sel = sr.regime_selection("UP", "AOA")
    assert sel["regime"] == "UP_AOA_2010" and sel["dedicated"] and sel["constitution_label"].startswith("Apartment Owners")
    assert sr.regime_selection("UP", "COOP")["regime"] == "GENERIC" and not sr.regime_selection("UP", "COOP")["dedicated"]
    assert sr.regime_selection("", "AOA")["regime"] is None                      # nothing until a State is chosen
    opts = {o["constitution"]: o for o in sr.regime_options("UP")}
    assert set(opts) == {"AOA", "REG_SOCIETY", "COOP", "GENERIC"} and opts["AOA"]["dedicated"] and not opts["COOP"]["dedicated"]
