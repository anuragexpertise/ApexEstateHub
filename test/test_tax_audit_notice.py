"""Task 1.8: the Sec 44AB prompt on the compliance card. Hidden below 80%, a warning from 80%, red at the limit,
always worded as a question for the CA. No database needed."""
import pytest

from app.dash_apps.pages.up_compliance_card import _tax_audit_notice, render_up_compliance_card


def _t(flag, income, thr=10_000_000):
    return {"flag": flag, "total_income": income, "threshold": thr, "pct_of_threshold": income / thr * 100}


def _text(node) -> str:
    return str(node)


@pytest.mark.parametrize("data", [{}, {"tax_audit": None}, {"tax_audit": _t("ok", 1_000_000)}])
def test_no_notice_below_80_percent_or_when_unknown(data):
    assert _tax_audit_notice(data) is None


def test_warn_and_flag_are_worded_as_a_question_for_the_ca():
    w = _text(_tax_audit_notice({"tax_audit": _t("warn", 8_500_000)}))
    assert "ask your CA" in w and "is approaching" in w and "provisional" in w and "'warning'" in w
    f = _text(_tax_audit_notice({"tax_audit": _t("flag", 10_000_000)}))
    assert "has reached" in f and "'danger'" in f and "for the CA to say" in f


def test_the_notice_shows_on_the_card_even_when_up_rules_are_off():
    card = _text(render_up_compliance_card({"rules_on": False, "society": {"name": "X"}, "tax_audit": _t("flag", 12_000_000)}))
    assert "upc-tax-audit" in card
    assert "upc-tax-audit" not in _text(render_up_compliance_card({"rules_on": False, "society": {"name": "X"}}))
