"""Evidence schema, scan validation, bye-law xlsx, and checks that the retired print/sign/scan loops stay gone."""
from __future__ import annotations

import base64
import io
import re
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.services import onboarding_service as ob
from app.services import paper_evidence as pe
from app.services import xlsx_templates as xt

ROOT = Path(__file__).resolve().parents[1]
HDR = ["Flat no.", "Value receivable (₹)"]
ROWS = [["A-101", "1,000.00"], ["TOTAL", "1,000.00"]]
PDF_BYTES = b"%PDF-1.4 fake signed scan"


def _data_uri(raw: bytes) -> str:
    return "data:application/pdf;base64," + base64.b64encode(raw).decode()


# ── schema: the fresh-database bug ────────────────────────────────────────────────────────────────────────────
def _evidence_table_sql() -> str:
    text = (ROOT / "database" / "estatehub.sql").read_text(encoding="utf-8")
    m = re.search(r"CREATE TABLE onboarding_evidence \((.*?)\n\);", text, flags=re.S)
    assert m, "onboarding_evidence is not defined in estatehub.sql"
    return m.group(1)


def test_fresh_schema_accepts_every_evidence_purpose():
    """estatehub.sql is the single source of truth: a clean database must accept every purpose the code can write
    (it used to list only five, so every paper-signing upload failed the CHECK on a fresh schema)."""
    block = _evidence_table_sql()
    allowed = set(re.findall(r"'([a-z_]+)'", block))
    assert set(ob.EVIDENCE_PURPOSES) <= allowed, sorted(set(ob.EVIDENCE_PURPOSES) - allowed)


# ── TDS wording ───────────────────────────────────────────────────────────────────────────────────────────────
def test_tds_template_is_not_marked_provisional():
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(xt.build_tds_template([])))
    text = " ".join(str(r[0]) for r in wb["Instructions"].iter_rows(values_only=True) if r[0])
    assert "pending the CA" not in text and "not marked provisional" in text
    assert "effective_start_date" in text


# ── Society_bye_laws.xlsx ─────────────────────────────────────────────────────────────────────────────────────
CLAUSES = [("BL_01", "Short title"), ("BL_07", "Disqualification"), ("BL_08", "Voting")]


def _xlsx_uri(rows, sheet="Bye-laws") -> str:
    wb = Workbook(); ws = wb.active; ws.title = sheet
    for r in rows:
        ws.append(r)
    b = io.BytesIO(); wb.save(b)
    return "data:application/octet-stream;base64," + base64.b64encode(b.getvalue()).decode()


def test_bye_law_template_round_trips():
    data = xt.build_bye_laws_template(CLAUSES, {"BL_08": {"choice": "adopted_with_variation", "variation_text": "2/3"}}, ["BL_07"])
    uri = "data:x;base64," + base64.b64encode(data).decode()
    res = xt.parse_upload(uri, "Society_bye_laws.xlsx", "Bye-laws", ["clause_id", "choice"])
    assert res.errors == [] and [r["clause_id"] for r in res.rows] == ["BL_01", "BL_07", "BL_08"]
    ok = xt.validate_bye_law_rows(res.rows, [c for c, _ in CLAUSES], ["BL_07"])
    assert ok.errors == [] and ok.rows == [{"clause_id": "BL_08", "choice": "adopted_with_variation", "variation_text": "2/3"}]
    note = [r for r in res.rows if r["clause_id"] == "BL_07"][0]["note"]
    assert "cannot be 'not_adopted'" in note


@pytest.mark.parametrize("rec,frag", [
    ({"clause_id": "BL_99", "choice": "adopted_as_is"}, "unknown clause"),
    ({"clause_id": "BL_01", "choice": "maybe"}, "must be one of"),
    ({"clause_id": "BL_01", "choice": "adopted_with_variation", "variation_text": ""}, "variation_text is empty"),
    ({"clause_id": "BL_07", "choice": "not_adopted"}, "cannot be not_adopted"),
])
def test_bye_law_validation_errors(rec, frag):
    res = xt.validate_bye_law_rows([rec], [c for c, _ in CLAUSES], ["BL_07"])
    assert res.rows == [] and any(frag in e for e in res.errors), res.errors


def test_bye_law_validation_normalises_skips_blank_and_rejects_duplicates():
    rows = [{"clause_id": "bl_01", "choice": "Adopted As-Is"}, {"clause_id": "BL_08", "choice": ""}, {"clause_id": "", "choice": ""},
            {"clause_id": "BL_01", "choice": "adopted_as_is"}]
    res = xt.validate_bye_law_rows(rows, [c for c, _ in CLAUSES])
    assert res.rows == [{"clause_id": "BL_01", "choice": "adopted_as_is", "variation_text": ""}]
    assert any("more than once" in e for e in res.errors)


def test_bye_law_variation_text_is_dropped_unless_adopted_with_variation():
    res = xt.validate_bye_law_rows([{"clause_id": "BL_01", "choice": "adopted_as_is", "variation_text": "leftover"}],
                                   [c for c, _ in CLAUSES])
    assert res.rows[0]["variation_text"] == ""


def test_adoption_minutes_replace_the_generated_adoption_document():
    from app.dash_apps.callbacks import paper_sign_callbacks as ps
    assert ps.PURPOSE == "adoption_minutes" and "adoption_minutes" in ob.EVIDENCE_PURPOSES
    assert not hasattr(ps, "document_parts") and not hasattr(ps, "_stale_snapshot")


def test_bulk_enrol_print_and_scan_loop_is_gone():
    from app.dash_apps.callbacks import bulk_enroll_callbacks as be
    for name in ("_bulk_purpose", "_BULK_EVIDENCE_PURPOSE", "_REGISTER_HIDE", "bulk_register_print", "bulk_register_scan"):
        assert not hasattr(be, name), name
    src = (ROOT / "app" / "dash_apps" / "callbacks" / "bulk_enroll_callbacks.py").read_text(encoding="utf-8")
    assert "make_document" not in src and "store_signed_scan" not in src


def test_generated_document_plumbing_is_gone():
    for name in ("make_document", "store_signed_scan", "evidence_status", "snapshot_hash", "printable_html"):
        assert not hasattr(pe, name), name
    for name in ("record_document", "latest_document"):
        assert not hasattr(ob, name), name


def test_scan_validation_still_applies():
    with pytest.raises(ob.OnboardingError):
        pe.validate_scan("notes.txt", b"hello")
    with pytest.raises(ob.OnboardingError):
        pe.validate_scan("fake.pdf", b"not a pdf")
    with pytest.raises(ob.OnboardingError):
        pe.validate_scan("scan.pdf", None)
    assert pe.validate_scan("ok.pdf", PDF_BYTES)[0] == ".pdf"
