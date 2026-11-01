"""Regression tests for the Treasurer-step fixes (offline: no database needed)."""
import ast
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def test_seat_callback_passes_flat_area_by_keyword():
    """The flat area used to land in the signature_name slot and was silently dropped."""
    tree = ast.parse(_read("app/dash_apps/callbacks/onboarding_callbacks.py"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "seat_founding_officer"]
    assert calls, "onb_seat must call seat_founding_officer"
    assert any(k.arg == "apartment_size" for k in calls[0].keywords)
    assert len(calls[0].args) <= 11


def test_policy_lookup_is_one_query_per_render(monkeypatch):
    pytest.importorskip("psycopg2")
    from app.services import regime_rules_admin as rra

    n = {"q": 0}

    def fake_rows(sql, params=None):
        n["q"] += 1
        return []

    monkeypatch.setattr(rra, "_rows", fake_rows)
    rra._POLICY_CACHE.clear()
    first_key = next(iter(rra.POLICY_SPECS))
    for _ in range(35):
        rra.policy_intent(1, first_key)
    assert n["q"] == 1
    rra._policy_cache_clear(1)
    rra.policy_intent(1, first_key)
    assert n["q"] == 2


def test_pool_default_keeps_idle_connections():
    src = _read("database/db_manager.py")
    assert 'os.getenv("DB_POOL_MIN", "4")' in src


def test_one_person_one_core_office_is_enforced():
    src = _read("app/services/onboarding_service.py")
    assert "three different people" in src and "co.office_code <> %s" in src
