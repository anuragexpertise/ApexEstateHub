"""Remaining parts of ONBOARDING_SIMPLIFICATION_PLAN.md: Annex E election minutes, G/H auto-build, the F/G/H checklist,
SQL/Python agreement on A-E, and the F/G/H screen. Unit tests (no database)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services import onboarding_service as ob

ROOT = Path(__file__).resolve().parents[1]


# ── Annex E indexes the election minutes ──────────────────────────────────────────────────────────────────────
def test_annex_e_indexes_election_minutes_once(monkeypatch):
    def fake_rows(sql, params=None):
        if "FROM onboarding_evidence" in sql:
            return [{"id": 1, "purpose": "registration_certificate", "acc_id": None, "filename": "reg.pdf", "stored_name": "r",
                     "sha256": "r" * 64, "uploaded_by": 3, "uploaded_at": "2026-01-02"}]
        if "FROM committee_offices" in sql:
            return [{"evidence_hash": "m" * 64, "evidence_file": "m.pdf"}, {"evidence_hash": "m" * 64, "evidence_file": "m.pdf"}]
        return []
    monkeypatch.setattr(ob, "_rows", fake_rows)
    monkeypatch.setattr(ob, "_row", lambda sql, params=None: {"id": 3, "name": "Admin"})
    content, controls = ob._annex_e(5)
    mins = [d for d in content["documents"] if d["purpose"] == "election_results"]
    assert len(mins) == 1 and mins[0]["sha256"] == "m" * 64 and mins[0]["filename"] == "m.pdf"
    assert controls["registration_certificate"]["passed"] is True
    assert controls["index_complete"]["passed"] is False and "cash-count" in controls["index_complete"]["reason"]


# ── G and H are prepared at the stage changes; F stays as it was ─────────────────────────────────────────────
def test_advance_phase_builds_g_then_h(monkeypatch):
    built = []
    monkeypatch.setattr(ob, "_try_build_supplementary", lambda sid, code, actor: built.append(code) or True)
    monkeypatch.setattr(ob.db, "_execute", lambda *a, **k: None)
    monkeypatch.setattr(ob, "_audit", lambda *a, **k: None)
    monkeypatch.setattr(ob, "state_of", lambda sid: "active")
    monkeypatch.setattr(ob, "society_phase", lambda sid: "adoption")
    ob.advance_phase(5, 1, "advisers")
    monkeypatch.setattr(ob, "society_phase", lambda sid: "advisers")
    ob.advance_phase(5, 1, "complete")
    assert built == ["G", "H"]


def test_try_build_never_raises(monkeypatch):
    def boom(*a, **k):
        raise ob.OnboardingError("Annexure F must be signed and sealed before annexure G.")
    monkeypatch.setattr(ob, "build_supplementary_annex", boom)
    assert ob._try_build_supplementary(5, "G", 1) is False
    monkeypatch.setattr(ob, "build_supplementary_annex", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert ob._try_build_supplementary(5, "G", 1) is False
    monkeypatch.setattr(ob, "build_supplementary_annex", lambda *a, **k: {"id": 1})
    assert ob._try_build_supplementary(5, "G", 1) is True


def test_sealing_one_annexure_prepares_the_next():
    src = (ROOT / "app" / "services" / "onboarding_service.py").read_text(encoding="utf-8")
    assert ob._SUPP_NEXT == {"F": "G", "G": "H"}
    assert "_try_build_supplementary(society_id, nxt, actor_id)" in src


# ── checklist ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_checklist_orders_the_chain_and_marks_due(monkeypatch):
    monkeypatch.setattr(ob, "society_phase", lambda sid: "advisers")
    monkeypatch.setattr(ob, "supplementary_annex_status", lambda sid: {"F": {"id": 9, "status": "sealed", "content_hash": "a" * 64}})
    rows = ob.supplementary_checklist(5, None)
    by = {r["code"]: r for r in rows}
    assert [r["code"] for r in rows] == ["F", "G", "H"]
    assert by["F"]["status"] == "sealed" and by["F"]["due"] and by["F"]["blocked_by"] is None
    assert by["G"]["due"] is True and by["G"]["status"] == "not built" and by["G"]["blocked_by"] is None
    assert by["H"]["due"] is False and by["H"]["blocked_by"] == "G"


# ── screen ────────────────────────────────────────────────────────────────────────────────────────────────────
def _text(comp) -> str:
    out = []
    def walk(c):
        if isinstance(c, str):
            out.append(c)
        elif isinstance(c, (list, tuple)):
            for x in c:
                walk(x)
        elif c is not None:
            walk(getattr(c, "children", None))
    walk(comp)
    return " ".join(out)


def _ids(comp) -> list:
    found = []
    def walk(c):
        if isinstance(c, (list, tuple)):
            for x in c:
                walk(x)
        elif c is not None and not isinstance(c, str):
            if getattr(c, "id", None) is not None:
                found.append(c.id)
            walk(getattr(c, "children", None))
    walk(comp)
    return found


def test_screen_shows_build_for_admin_and_sign_for_office_bearer(monkeypatch):
    from app.dash_apps.pages import onboarding_page as op
    rows = [
        {"code": "F", "title": ob.SUPPLEMENTARY_TITLES["F"], "due": True, "status": "draft", "annex_id": 1, "content_hash": "a" * 64,
         "signed": ["president"], "mine": ["secretary"], "blocked_by": None},
        {"code": "G", "title": ob.SUPPLEMENTARY_TITLES["G"], "due": True, "status": "not built", "annex_id": None, "content_hash": None,
         "signed": [], "mine": [], "blocked_by": "F"},
        {"code": "H", "title": ob.SUPPLEMENTARY_TITLES["H"], "due": False, "status": "not built", "annex_id": None, "content_hash": None,
         "signed": [], "mine": [], "blocked_by": "G"},
    ]
    monkeypatch.setattr(ob, "supplementary_checklist", lambda sid, uid=None: rows)
    monkeypatch.setattr(ob, "supplementary_annex_content", lambda sid, code: {"flats": 2})
    admin = op.supplementary_section(5, "admin", 1)
    ids = _ids(admin)
    assert {"type": "onb-supp-build", "code": "F"} in ids and {"type": "onb-supp-sign", "code": "F"} in ids
    assert {"type": "onb-supp-build", "code": "G"} not in ids          # G waits for F
    assert "Waiting for Annexure F" in _text(admin) and "Operator is informed and does not sign" in _text(admin)
    other = _ids(op.supplementary_section(5, "apartment", 2))
    assert not [i for i in other if i.get("type") == "onb-supp-build"]


def test_callbacks_are_registered_in_the_hub_module():
    src = (ROOT / "app" / "dash_apps" / "callbacks" / "onboarding_callbacks.py").read_text(encoding="utf-8")
    assert "def onb_supp_build" in src and "def onb_supp_sign" in src
    assert "ob.sign_supplementary_annex(sid, code, uid" in src


# ── SQL and Python agree on A-E ───────────────────────────────────────────────────────────────────────────────
def test_sql_activation_requires_a_to_e_like_python():
    sql = (ROOT / "database" / "estatehub.sql").read_text(encoding="utf-8")
    assert "unnest(ARRAY['A','B','C','D','E'])" in sql and "ARRAY['A','B','C','D'])" not in sql
    assert tuple(ob.ANNEX_CODES) == ("A", "B", "C", "D", "E") if hasattr(ob, "ANNEX_CODES") else True
