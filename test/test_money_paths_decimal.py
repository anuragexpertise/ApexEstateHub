"""Plan v4, C.9 -- the converted money paths hand back Decimal, never a binary float."""
from decimal import Decimal


def test_fund_drawable_amount_is_decimal_and_matches_the_database_rounding():
    from app.dash_apps.callbacks.fund_management_callbacks import fund_drawable_amount
    v = fund_drawable_amount({"balance": Decimal("1000.10"), "statutory_lock_pct": Decimal("33.33")})
    assert isinstance(v, Decimal)
    assert v == Decimal("1000.10") - Decimal("333.33")           # 33.33% of 1000.10 = 333.3333, to the paisa 333.33
    assert fund_drawable_amount({"balance": 500, "available_amount": Decimal("120.50")}) == Decimal("120.50")
    assert fund_drawable_amount({"balance": 0}) == 0


def test_spreadsheet_amount_parser_gives_decimal_or_none():
    from app.dash_apps.callbacks.bulk_enroll_callbacks import _safe_float
    assert _safe_float("1,234.5") == Decimal("1234.50") and isinstance(_safe_float(0.1), Decimal)
    assert _safe_float(0.1) == Decimal("0.10")                    # not 0.1000000000000000055
    assert _safe_float("") is None and _safe_float("abc") is None


def test_security_form_amount_parser_gives_decimal():
    from app.dash_apps.callbacks.drilldown_callbacks import _safe_float
    assert _safe_float("700") == Decimal("700.00") and _safe_float(None, 0) == 0 and isinstance(_safe_float("x"), Decimal)


def test_income_expenditure_totals_do_not_drift():
    from database.money import D
    rows = [{"amount": 0.1}] * 10 + [{"amount": "0.20"}]
    assert sum((D(r["amount"]) for r in rows), Decimal(0)) == Decimal("1.20")
