"""document_archive: files land in app/assets/<society_id>/agreements|NOCs with a server-computed SHA-256 in the database."""
import hashlib
import sys
import types

import pytest

from app.services import document_archive as da


from test.archive_fixtures import FakeDB, png as _png_helper  # noqa: E402


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(da, "assets_root", lambda: tmp_path.resolve())
    db = FakeDB()
    db.nocs[5] = {"id": 5, "society_id": 7, "apartment_id": 3, "certificate_no": "NOC/7/2026/5", "issued_date": "2026-11-17",
                  "valid_until": "2026-11-30", "body_text": "NO OBJECTION CERTIFICATE\nFlat 3 has no dues.", "qr_payload": "7-NOC-5"}
    return tmp_path, db


def test_noc_goes_to_NOCs_folder_with_sha_in_db(env):
    root, db = env
    out = da.archive_noc(7, 5, None, society_name="Green Park", society_address="Agra", db=db)
    f = root / "7" / "NOCs" / out["filename"]
    assert f.is_file() and f.read_bytes().startswith(b"%PDF-")
    assert out["sha256"] == hashlib.sha256(f.read_bytes()).hexdigest() and out["version"] == 1 and out["created"]
    assert out["filename"].startswith("NOC-7-2026-5_")


def test_same_pdf_twice_is_one_row_and_edited_text_is_a_new_version(env):
    root, db = env
    a = da.archive_noc(7, 5, None, db=db); b = da.archive_noc(7, 5, None, db=db)
    assert b["created"] is False and b["id"] == a["id"] and len(db.docs) == 1
    c = da.archive_noc(7, 5, "NO OBJECTION CERTIFICATE\nEdited wording.", db=db)
    assert c["version"] == 2 and c["sha256"] != a["sha256"] and db.nocs[5]["body_text"].endswith("Edited wording.")
    assert (root / "7" / "NOCs" / a["filename"]).is_file()                 # version 1 is still on disk


def test_sealed_noc_ignores_edits(env):
    root, db = env
    db.sealed.add(5)
    out = da.archive_noc(7, 5, "NO OBJECTION CERTIFICATE\nSneaky edit.", db=db)
    assert out["text_reverted"] and "Sneaky" not in db.nocs[5]["body_text"]


def test_other_society_cannot_archive_or_read(env):
    root, db = env
    with pytest.raises(da.ArchiveError) as e:
        da.archive_noc(8, 5, None, db=db)
    assert e.value.status == "not_found"
    out = da.archive_noc(7, 5, None, db=db)
    with pytest.raises(da.ArchiveError):
        da.read_verified(8, out["id"], db=db)


def test_tamper_and_missing_are_detected_and_never_served(env):
    root, db = env
    out = da.archive_noc(7, 5, None, db=db)
    row, data = da.read_verified(7, out["id"], db=db)
    assert data.startswith(b"%PDF-")
    f = root / "7" / "NOCs" / out["filename"]
    f.write_bytes(f.read_bytes() + b"\n%tampered")
    assert da.verify_document(7, out["id"], db=db)["status"] == "altered"
    with pytest.raises(da.ArchiveError) as e:
        da.read_verified(7, out["id"], db=db)
    assert e.value.status == "altered"
    f.unlink()
    assert da.verify_document(7, out["id"], db=db)["status"] == "missing"


def _agreement_inputs():
    sig = _png()
    return dict(society_name="ग्रीन पार्क Apartments", agreement_no="AGR/7/2026/1",
                body_text="Agreement text\n  1. Fee Rs. 12,500 / ₹12,500\n  2. सचिव, श्री राजेश कुमार",
                annexes=[{"code": c, "title": f"Annex {c}", "hash": c.lower() * 64,
                          "content": {"note": "REG/आगरा/2019/44", "ok": True, "rows": [{"a": 1, "b": "x"}], "pic": "sig.png"}}
                         for c in "ABCDE"],
                officers=[{"label": "President", "name": "सुंदर लाल", "signature": sig},
                          {"label": "Secretary", "name": "S Verma", "signature": None},
                          {"label": "Treasurer", "name": "T Singh", "signature": sig}],
                image_loader=lambda p: sig if p == "sig.png" else None, evidence={})


_png = _png_helper


def _pages(pdf: bytes) -> int:
    import re
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf))


def test_agreement_full_pdf_has_all_annexes_footer_and_hindi_and_is_deterministic():
    from app.services import agreement_pdf as ap
    a = ap.render_agreement_full_pdf(**_agreement_inputs())
    b = ap.render_agreement_full_pdf(**_agreement_inputs())
    assert a == b and a.startswith(b"%PDF-")                                    # same input -> same bytes -> stable SHA-256
    assert _pages(a) == 7                                                      # agreement + 5 annexes + paper counterpart page
    assert b"NotoSansDevanagari" in a                                          # the Hindi font is embedded
    signed = ap.render_agreement_full_pdf(**_agreement_inputs(), signers=[{"office": "president", "at": "2026-11-17"}],
                                          sealed_at="2026-11-17", key_id="k1", paper_page=False)
    assert _pages(signed) == 7 and signed != a                                 # recorded signatures replace the paper page content


def test_hindi_shaping_dependency_is_present():
    from app.services import pdf_text as T
    assert T.fonts_ok(), "fonts/NotoSansDevanagari-*.ttf must be in the repo"
    assert T.shaping_available(), "pip install uharfbuzz (Hindi conjuncts and matras need shaping)"


def test_noc_with_hindi_text_embeds_the_devanagari_font(env):
    root, db = env
    db.nocs[5]["body_text"] = "NO OBJECTION CERTIFICATE\nफ्लैट 3 पर कोई बकाया नहीं है। ₹0 due."
    out = da.archive_noc(7, 5, None, society_name="ग्रीन पार्क", db=db)
    assert b"NotoSansDevanagari" in (root / "7" / "NOCs" / out["filename"]).read_bytes()


def test_archive_agreement_files_pdf_and_picks_sealed_variant(env, monkeypatch):
    from app.services import agreement_pdf as ap
    from app.services import document_signing as ds
    root, db = env
    db.ags = {1: {"id": 1, "agreement_no": "AGR/7/2026/1"}}
    orig = db._execute
    db._execute = lambda sql, params=(), **k: (db.ags[params[0]] if " ".join(sql.split()).startswith("SELECT id, agreement_no FROM society_agreements")
                                                else orig(sql, params, **k))
    monkeypatch.setattr(ap, "build_inputs", lambda sid: _agreement_inputs())
    monkeypatch.setattr(ds, "status", lambda kind, sid, d=None: {"signed": [], "sealed": False, "seal": None, "item_hash": "9" * 64}, raising=False)
    draft = da.archive_agreement(7, 1, event="printed", db=db)
    assert (root / "7" / "agreements" / draft["filename"]).is_file() and draft["event"] == "printed"
    assert da.archive_agreement(7, 1, event="printed", db=db)["created"] is False        # printing twice is not a new version
    sealed_st = {"signed": [{"office_code": "president", "signed_at": "2026-11-17"}], "sealed": True,
                 "seal": {"signed_at": "2026-11-17", "key_id": "k1"}, "item_hash": "9" * 64}
    sealed = da.archive_agreement(7, 1, st=sealed_st, event="sealed", db=db)
    assert sealed["version"] == 2 and sealed["sha256"] != draft["sha256"]


def test_signed_scan_is_filed_beside_the_agreement(env):
    root, db = env
    scan = da.store_signed_scan(7, "agreement", 1, "AGR/7/2026/1", "scan.pdf", b"%PDF-1.4 signed", 2, db=db)
    assert scan["origin"] == "signed_scan" and (root / "7" / "agreements" / scan["filename"]).is_file()
    with pytest.raises(da.ArchiveError):
        da.store_signed_scan(7, "agreement", 1, "x", "scan.png", b"\x89PNG", 2, db=db)


def test_rejects_non_pdf_and_unknown_kind(env):
    root, db = env
    with pytest.raises(da.ArchiveError):
        da.store_pdf(7, "noc", 5, "n", b"not a pdf", db=db)
    with pytest.raises(da.ArchiveError):
        da.store_pdf(7, "../../etc", 5, "n", b"%PDF-1", db=db)
    assert not (root / "7").exists() or not any((root / "7").rglob("*.pdf"))


def test_path_traversal_in_document_no_is_neutralised(env):
    root, db = env
    out = da.store_pdf(7, "noc", 5, "../../../evil", b"%PDF-1.4 x", db=db)
    assert "/" not in out["filename"] and not out["filename"].startswith(".")
    assert (root / "7" / "NOCs" / out["filename"]).is_file()
    assert all(root.resolve() in p.resolve().parents for p in root.rglob("*.pdf"))
