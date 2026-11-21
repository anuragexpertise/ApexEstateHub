"""ICAI4 I7: statement notes generator unit tests (default suite, no DB)."""

from app.services import icai_notes as notes


def _bs():
    return {
        "totals": {"Assets": "320850", "Liabilities": "70000", "Equity": "250850"},
    }


def _ie():
    return {
        "totals": {"Income": "120000", "Expenditure": "90000"},
    }


def test_notes_structure_and_figures():
    creditors = {"mse_dues": "40000", "other_dues": "30000", "total_dues": "70000"}
    out = notes.generate_statement_notes(1, 2026,
                                         balance_sheet=_bs(),
                                         income_expenditure=_ie(),
                                         creditors_split=creditors)
    titles = [n["title"] for n in out]
    assert "1. Accounting policies" in titles
    assert "2. MSME creditors disclosure (MSMED Act 2006)" in titles
    assert "3. Related parties" in titles
    assert "4. Contingent liabilities and commitments" in titles

    msme = next(n for n in out if n["title"].startswith("2. MSME"))
    text = " ".join(msme["content"])
    assert "Rs 40,000.00" in text          # MSE
    assert "Rs 30,000.00" in text          # other
    assert "Rs 70,000.00" in text          # total
    assert "45 days" in text


def test_accounting_policies_figures():
    out = notes.generate_statement_notes(1, 2026,
                                         balance_sheet=_bs(),
                                         income_expenditure=_ie(),
                                         creditors_split={"mse_dues": "0",
                                                          "other_dues": "0",
                                                          "total_dues": "0"})
    policies = next(n for n in out if n["title"].startswith("1. Accounting"))
    text = " ".join(policies["content"])
    assert "Rs 320,850.00" in text         # assets
    assert "Rs 320,850.00" in text         # liabilities + equity
    assert "Rs 120,000.00" in text         # income
    assert "Rs 90,000.00" in text          # expenditure
    assert "Rs 30,000.00" in text          # surplus


def test_zero_creditors_split_renders_zero():
    out = notes.generate_statement_notes(1, 2026,
                                         balance_sheet=_bs(),
                                         income_expenditure=_ie(),
                                         creditors_split={"mse_dues": "0",
                                                          "other_dues": "0",
                                                          "total_dues": "0"})
    msme = next(n for n in out if n["title"].startswith("2. MSME"))
    assert "Rs 0.00" in " ".join(msme["content"])
