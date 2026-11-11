"""Regression tests for the six Onboarding Review items finished in the second pass:
Annex D in fn_activate_society, DPDP seed rows, Acts & Rules offcanvas, review print link, AGREEMENT.md, Annex B signatures."""
import os
import re

from app.services import onboarding_service as ob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def test_activation_sql_requires_annexes_a_to_e():
    sql = _read("database", "estatehub.sql")
    start = sql.index("CREATE OR REPLACE FUNCTION fn_activate_society")
    body = sql[start:sql.index("CREATE OR REPLACE VIEW vw_apartment_users", start)]
    assert "ARRAY['A','B','C','D','E']" in body
    assert "ARRAY['A','B','C']" not in body
    assert "Annexes A, B, C, D and E must be sealed" in body


def test_dpdp_instruments_seeded_unverified_and_always_applicable():
    # The catalogue moved out of seed.py into database/legal_reference.py (installed by migrate.py /
    # reset_database.py), and its rows are dicts rather than positional tuples.
    from database import legal_reference as lr
    rows = {r["title"]: r for r in lr.INSTRUMENTS}
    act = rows["Digital Personal Data Protection Act, 2023"]
    rules = rows["Digital Personal Data Protection Rules, 2025"]
    assert act["regime_code"] == "CENTRAL" and act["instrument_type"] == "Central Act"
    assert rules["instrument_type"] == "Central Rules"
    assert act["applies_when"] == "always" and rules["applies_when"] == "always"
    # No row may claim verification: this file carries only researched leads, never source_url /
    # notification_no (what a human sets after opening the text) and never a verification state.
    assert all("verification" not in r and "source_url" not in r for r in lr.INSTRUMENTS)
    # uq_legal_instrument is (regime_code, title, enactment_year): no duplicates
    keys = [lr.key_of(r) for r in lr.INSTRUMENTS]
    assert len(keys) == len(set(keys))
    assert lr.validate_instruments() == []


def test_signature_path_and_url():
    assert ob.signature_path(7, None) is None
    assert ob.signature_path(7, "  ") is None
    assert ob.signature_path(7, "abc.webp") == "7/signatures/abc.webp"
    assert ob.signature_path(7, "7/signatures/abc.webp") == "7/signatures/abc.webp"
    assert ob.signature_url(7, "abc.webp") == "/assets/7/signatures/abc.webp"


def _officer(name, flat, sig):
    return {"holder_name": name, "flat_number": flat, "evidence_hash": "e" * 64, "resolution_ref": "R1",
            "signature_image": sig, "phone": "9999999999", "email": "x@y.z", "user_id": 1}


def test_annex_b_records_signature_images_and_blocks_incomplete(monkeypatch):
    officers = {"president": _officer("P", "A-1", "a" * 64 + ".webp"), "secretary": _officer("S", "A-2", "b" * 64 + ".webp"),
                "treasurer": _officer("T", "A-3", "c" * 64 + ".webp")}
    monkeypatch.setattr(ob, "seated_officers", lambda sid: officers)
    monkeypatch.setattr(ob, "_committee_complete", lambda sid: True)
    content, controls = ob._annex_b(5, {"name": "Soc", "grievance_officer_name": "G"}, {"x": 1})
    p = content["office_bearers"]["president"]
    assert p["signature_image"] == f"5/signatures/{'a' * 64}.webp"
    assert p["signature_sha256"] == "a" * 64
    assert controls["officers_complete"]["passed"] and controls["officers_complete"]["blocking"]

    monkeypatch.setattr(ob, "_committee_complete", lambda sid: False)
    _, controls = ob._annex_b(5, {"name": "Soc"}, {"x": 1})
    assert not controls["officers_complete"]["passed"] and controls["officers_complete"]["blocking"]
    assert ob.CONTROL_FIX[("B", "officers_complete")] == "committee"


def test_annex_b_hash_changes_when_signature_changes(monkeypatch):
    base = {"president": _officer("P", "A-1", "a" * 64 + ".webp"), "secretary": None, "treasurer": None}
    monkeypatch.setattr(ob, "_committee_complete", lambda sid: False)
    monkeypatch.setattr(ob, "seated_officers", lambda sid: base)
    c1, _ = ob._annex_b(5, {"name": "Soc"}, None)
    base["president"] = _officer("P", "A-1", "d" * 64 + ".webp")
    c2, _ = ob._annex_b(5, {"name": "Soc"}, None)
    assert ob._sha(ob.canonical(c1)) != ob._sha(ob.canonical(c2))


def test_agreement_text_execution_block_lists_flat_and_signature(monkeypatch):
    officers = {"president": _officer("Pat", "A-1", "a" * 64 + ".webp"), "secretary": _officer("Sam", "A-2", None), "treasurer": None}
    monkeypatch.setattr(ob, "seated_officers", lambda sid: officers)
    monkeypatch.setattr(ob, "_row", lambda *a, **k: {"name": "Soc", "plan": "x"})
    monkeypatch.setattr(ob, "_operator", lambda: ("Op LLP", "Agra"))
    hashes = {k: "h" * 64 for k in "ABCDE"}
    text = ob.agreement_text(5, "AG-1", hashes, {"A": {}, "B": {}, "C": {}, "D": {}, "E": {"documents": []}})
    assert "flat A-1 (signature image 5/signatures/" in text
    assert "Sam, flat A-2 (no signature image on record)" in text
    assert "Treasurer: ____" in text
    assert "Annex D" in text


def test_agreement_md_matches_generated_structure():
    md = _read("database", "AGREEMENT.md")
    for heading in ("## 1. Licence and term", "## 2. Society duties", "## 3. Data protection", "## 4. Key custody",
                    "## 5. Liability, indemnity and disputes", "## 6. Exit", "## 7. Declared legal basis", "## Execution"):
        assert heading in md, heading
    for annex in ("**A —", "**B —", "**C —", "**D —"):
        assert annex in md
    assert "EstateHub LLP" in md
    assert "Paper" in md and "eSign" in md and "Password" in md
    assert "nobody types a hash" in md
    assert re.search(r"signs last", md)
    assert "flat Rs 100" not in md          # the old unverified stamp-duty figure is gone


def test_offcanvas_and_review_print_link_are_in_the_hub_layout():
    page = _read("app", "dash_apps", "pages", "onboarding_page.py")
    assert 'dbc.Offcanvas' in page and 'id="onb-rules-canvas"' in page and 'id="onb-btn-rules"' in page
    assert 'href="/print_wizard/review"' in page
    cb = _read("app", "dash_apps", "callbacks", "onboarding_wizard_callbacks.py")
    assert "def wizard_rules_panel" in cb
    assert "@require_session\n    def wizard_rules_panel" in cb
