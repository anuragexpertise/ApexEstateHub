"""Regression tests for the onboarding-audit fixes that are pure logic (no DB)."""
from datetime import date

import pytest

from app.security import password_policy as pp
from app.security import plan_guard
from app.utils import fiscal


@pytest.mark.parametrize("pwd,ok", [
    (None, False), ("", False), ("1234567", False), ("12345678", True), ("a long passphrase", True),
])
def test_login_password_minimum(pwd, ok):
    assert (pp.validate_password(pwd) is None) is ok


@pytest.mark.parametrize("secret,ok", [
    ("Abcdef1!", True),
    ("abcdef1!", False),     # no uppercase
    ("ABCDEF1!", False),     # no lowercase
    ("Abcdefg!", False),     # no digit  (the old live check accepted this)
    ("Abcdefg1", False),     # no special
    ("Ab1!", False),         # too short
    ("", False), (None, False),
])
def test_signing_secret_single_validator(secret, ok):
    assert (pp.validate_signing_secret(secret) is None) is ok


@pytest.mark.parametrize("today,start", [
    (date(2026, 10, 5), date(2026, 4, 1)),
    (date(2026, 4, 1), date(2026, 4, 1)),
    (date(2026, 3, 31), date(2025, 4, 1)),
    (date(2027, 1, 15), date(2026, 4, 1)),
])
def test_financial_year_start(today, start):
    assert fiscal.fy_start_date(today) == start
    assert fiscal.fy_start_year(today) == start.year


def test_plan_guard_grace_days(monkeypatch):
    monkeypatch.delenv("PLAN_GRACE_DAYS", raising=False)
    assert plan_guard.grace_days() == plan_guard.DEFAULT_GRACE_DAYS
    monkeypatch.setenv("PLAN_GRACE_DAYS", "0")
    assert plan_guard.grace_days() == 0
    monkeypatch.setenv("PLAN_GRACE_DAYS", "-5")
    assert plan_guard.grace_days() == 0
    monkeypatch.setenv("PLAN_GRACE_DAYS", "abc")
    assert plan_guard.grace_days() == plan_guard.DEFAULT_GRACE_DAYS


def test_plan_guard_master_and_no_society_never_expired():
    assert plan_guard.society_plan_expired(None) is False
    assert plan_guard.society_plan_expired(0) is False


def test_schema_email_columns_are_wide_enough():
    from pathlib import Path
    sql = (Path(__file__).resolve().parent.parent / "database" / "estatehub.sql").read_text()
    assert "email VARCHAR(30)" not in sql
    assert "::VARCHAR(30)" not in sql.split("fn_societies_list", 1)[1][:3000]
