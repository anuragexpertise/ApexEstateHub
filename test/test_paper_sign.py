"""Paper-signing workflow: schema, snapshot/document/scan binding, stale detection, PDF, bye-law xlsx, bulk register."""
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


def test_fresh_schema_has_binding_columns_and_documents_table():
    block = _evidence_table_sql()
    for col in ("doc_id", "document_sha256", "snapshot_sha256"):
        assert re.search(rf"\b{col}\b", block), col
    text = (ROOT / "database" / "estatehub.sql").read_text(encoding="utf-8")
    assert re.search(r"CREATE TABLE onboarding_documents\b", text)
    mig = (ROOT / "database" / "migrations" / "004_paper_sign_binding.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS doc_id" in mig and "CREATE TABLE IF NOT EXISTS onboarding_documents" in mig


# ── snapshot + Doc ID ─────────────────────────────────────────────────────────────────────────────────────────
def test_snapshot_is_deterministic_and_data_sensitive():
    a = pe.snapshot_hash("pending_receivables", "T", HDR, ROWS, ["m"])
    assert a == pe.snapshot_hash("pending_receivables", "T", HDR, [list(r) for r in ROWS], ["m"])
    assert a != pe.snapshot_hash("pending_receivables", "T", HDR, [["A-101", "1,001.00"], ["TOTAL", "1,001.00"]], ["m"])
    assert a != pe.snapshot_hash("pending_receivables", "T", HDR, ROWS, ["other meta"])
    assert a != pe.snapshot_hash("tds_rates", "T", HDR, ROWS, ["m"])
    with_sec = pe.snapshot_hash("pending_receivables", "T", HDR, ROWS, ["m"], [{"heading": "h", "headers": ["x"], "rows": [["1"]]}])
    assert with_sec != a


def test_doc_id_is_stable_and_readable():
    snap = pe.snapshot_hash("pending_receivables", "T", HDR, ROWS)
    d = pe.make_doc_id(7, "pending_receivables", snap)
    assert d == pe.make_doc_id(7, "pending_receivables", snap)
    assert re.fullmatch(r"EH-7-PENDINGREC-[0-9A-F]{8}", d), d


# ── PDF ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_pdf_is_real_multipage_and_carries_the_doc_id(monkeypatch):
    pypdf = pytest.importorskip("pypdf")
    monkeypatch.setattr(pe, "_fonts", lambda: ("Helvetica", "Helvetica-Bold", False))
    rows = [[f"A-{i}", f"{i * 100:,.2f}"] for i in range(1, 150)] + [["TOTAL", "9,99,999.00"]]
    snap = pe.snapshot_hash("pending_receivables", "T", HDR, rows)
    doc_id = pe.make_doc_id(7, "pending_receivables", snap)
    pdf = pe._render_pdf("Pending receivables", "Sunrise", "FY", HDR, rows, ["Treasurer", "Secretary"], ["meta ₹5"],
                         doc_id, snap)
    assert pdf.startswith(b"%PDF-")
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    pages = [p.extract_text() for p in reader.pages]
    assert len(pages) >= 3
    for i, text in enumerate(pages, start=1):                      # Doc ID, data hash and page x of y on EVERY page
        assert doc_id in text and snap[:16] in text and f"Page {i} of {len(pages)}" in text
    full = "\n".join(pages)
    assert "Rs.5" in full and "₹" not in full                        # Helvetica has no rupee glyph: printed as Rs.
    assert "Signature & date" in pages[-1] and "Treasurer" in pages[-1]
    assert "Flat no." in pages[1]                                    # header row repeats on later pages


def test_make_document_records_the_document(monkeypatch):
    seen = {}
    monkeypatch.setattr(ob, "record_document", lambda *a, **k: seen.update(args=a, kwargs=k) or {"id": 1})
    doc = pe.make_document(7, "pending_receivables", 3, "Pending receivables", "Sunrise", "FY", HDR, ROWS, ["Treasurer"], ["m"],
                           kind="k")
    assert doc["fmt"] == "pdf" and doc["data"].startswith(b"%PDF-")
    assert doc["filename"].endswith(f"{doc['doc_id']}.pdf")
    args = seen["args"]
    assert args[0] == 7 and args[1] == "pending_receivables" and args[2] == doc["doc_id"]
    assert args[3] == doc["snapshot_sha256"] and args[4] == doc["document_sha256"] and args[5] == "pdf"
    assert pe.hashlib.sha256(doc["data"]).hexdigest() == doc["document_sha256"]


def test_make_document_survives_a_recording_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(ob, "record_document", boom)
    doc = pe.make_document(7, "tds_rates", 3, "TDS Rates", "S", "", HDR, ROWS, ["CA"])
    assert doc["data"].startswith(b"%PDF-")


def test_unknown_signing_mode_is_refused(monkeypatch):
    with pytest.raises(ob.OnboardingError):
        pe.make_document(7, "tds_rates", 3, "T", "S", "", HDR, ROWS, ["CA"], signing_mode="esign")


# ── scan binding + stale detection ────────────────────────────────────────────────────────────────────────────
def test_scan_is_bound_to_the_generated_document(monkeypatch):
    got = {}
    gen = {"doc_id": "EH-7-X-AAAA", "document_sha256": "d" * 64, "snapshot_sha256": "s" * 64, "generated_at": "now"}
    monkeypatch.setattr(ob, "latest_document", lambda sid, purpose, kind=None, doc_id=None: got.update(kind=kind) or gen)
    monkeypatch.setattr(ob, "store_evidence_file",
                        lambda *a, **k: got.update(args=a, kw=k) or {"id": 5, "sha256": "x" * 64, "filename": a[3]})
    ev = pe.store_signed_scan(7, "pending_receivables", 3, "scan.pdf", _data_uri(PDF_BYTES), {"fy": 2026}, kind="k")
    assert got["kind"] == "k"
    assert got["kw"] == {"doc_id": "EH-7-X-AAAA", "document_sha256": "d" * 64, "snapshot_sha256": "s" * 64}
    assert got["args"][-1]["bound"] is True and ev["bound"] is True
    assert "linked to Doc ID EH-7-X-AAAA" in pe.stored_message({**ev, "doc_id": "EH-7-X-AAAA"})


def test_scan_without_a_generated_document_is_stored_unbound(monkeypatch):
    got = {}
    monkeypatch.setattr(ob, "latest_document", lambda *a, **k: None)
    monkeypatch.setattr(ob, "store_evidence_file",
                        lambda *a, **k: got.update(kw=k) or {"id": 5, "sha256": "x" * 64, "filename": a[3]})
    ev = pe.store_signed_scan(7, "tds_rates", 3, "scan.pdf", _data_uri(PDF_BYTES))
    assert got["kw"]["doc_id"] is None and ev["bound"] is False
    assert "not linked" in pe.stored_message(ev)


def test_scan_validation_still_applies():
    with pytest.raises(ob.OnboardingError):
        pe.store_signed_scan(7, "tds_rates", 3, "notes.txt", _data_uri(b"hello"))
    with pytest.raises(ob.OnboardingError):
        pe.store_signed_scan(7, "tds_rates", 3, "fake.pdf", _data_uri(b"not a pdf"))
    with pytest.raises(ob.OnboardingError):
        pe.store_signed_scan(7, "tds_rates", 3, "scan.pdf", None)


def _ev(snapshot, doc_id="EH-7-X-AAAA"):
    return [{"sha256": "a" * 64, "filename": "s.pdf", "uploaded_at": "t", "doc_id": doc_id,
             "snapshot_sha256": snapshot, "document_sha256": "d" * 64}]


def test_evidence_goes_stale_when_the_data_changes(monkeypatch):
    monkeypatch.setattr(ob, "get_evidence", lambda *a, **k: _ev("s1"))
    same = pe.evidence_status(7, "pending_receivables", current_snapshot="s1")
    changed = pe.evidence_status(7, "pending_receivables", current_snapshot="s2")
    assert same["evidenced"] and same["bound"] and not same["stale"]
    assert changed["stale"]
    assert pe.status_line(same)[0] == "success"
    colour, text = pe.status_line(changed)
    assert colour == "warning" and "print again" in text.lower()


def test_status_without_evidence_or_link(monkeypatch):
    monkeypatch.setattr(ob, "get_evidence", lambda *a, **k: [])
    assert pe.status_line(pe.evidence_status(7, "tds_rates"))[0] == "muted"
    monkeypatch.setattr(ob, "get_evidence", lambda *a, **k: _ev(None, doc_id=None))
    st = pe.evidence_status(7, "tds_rates", current_snapshot="s2")
    assert st["evidenced"] and not st["bound"] and not st["stale"]      # nothing to compare against
    assert pe.status_line(st)[0] == "info"


def test_apartment_charges_section_totals(monkeypatch):
    monkeypatch.setattr(ob, "_rows", lambda *a, **k: [
        {"flat_number": "A-10", "apartment_size": 1000, "undivided_interest_pct": "60.0"},
        {"flat_number": "A-2", "apartment_size": 500, "undivided_interest_pct": "40.0"}])
    sec = pe.apartment_charges_section(7, "10000")
    assert [r[0] for r in sec["rows"]] == ["A-2", "A-10", "TOTAL"]            # natural order
    assert sec["rows"][0][3] == "4,000.00" and sec["rows"][1][3] == "6,000.00"
    assert sec["rows"][-1][1:] == ["1500", "100.0000", "10,000.00"]
    assert pe.apartment_charges_section(7, None)["rows"][0][3] == ""


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


def test_adoption_document_lists_all_58_clauses(monkeypatch):
    from app.dash_apps.callbacks import paper_sign_callbacks as ps
    from app.services import regime_rules_admin as rra
    monkeypatch.setattr(ps, "current_choices", lambda sid: {"BL_08": {"choice": "adopted_as_is", "variation_text": "", "active": False}})
    hdr, rows, signers, meta = ps.document_parts(7)
    assert len(rows) == len(rra.MODEL_BYE_LAW_CLAUSES) == 58
    assert [r for r in rows if r[0] == "08"][0][2] == "Adopted as is"
    assert "1 of 58" in meta[1] and "Chair of the General Body meeting" in signers


# ── bulk-enrol register ───────────────────────────────────────────────────────────────────────────────────────
def test_bulk_register_never_includes_passwords_and_routes_purposes():
    from app.dash_apps.callbacks import bulk_enroll_callbacks as be
    assert "password" in be._REGISTER_HIDE
    assert be._bulk_purpose("apartments") == ("bulk_apartments", "bulk:apartments")
    assert be._bulk_purpose("staff")[0] == "bulk_staff"
    assert be._bulk_purpose("assets") == ("other_paper_evidence", "bulk:assets")
    assert all(p in ob.EVIDENCE_PURPOSES for p in set(be._BULK_EVIDENCE_PURPOSE.values()) | {"other_paper_evidence"})
