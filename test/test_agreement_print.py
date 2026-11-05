"""The printable Agreement carries the agreement text and all four sealed annexes in full, embeds every image they refer to,
repeats the four parties' signature footer on every page, and refuses before the annexes are sealed."""
import base64
import json
import pytest
from app.services import onboarding_service as ob

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
SCAN_SHA = "e" * 64


def _stub(monkeypatch, tmp_path, sealed_codes=("A", "B", "C", "D")):
    sigdir = tmp_path / "7" / "signatures"; sigdir.mkdir(parents=True)
    evdir = tmp_path / "7" / "evidence"; evdir.mkdir(parents=True)
    (sigdir / "pres.png").write_bytes(PNG); (sigdir / "sec.png").write_bytes(PNG)      # treasurer has none on record
    (evdir / (SCAN_SHA + ".png")).write_bytes(PNG)
    monkeypatch.setattr(ob, "_assets_root", lambda: tmp_path.resolve())
    contents = {"A": {"regime_code": "UP_AOA"},
                "B": {"office_bearers": {"president": {"name": "P <Sundar>", "signature_image": "pres.png"},
                                          "secretary": {"name": "S", "signature_image": "7/signatures/sec.png"}}},
                "C": {"total_debits": "1600000.00", "opening_balances": [{"name": "SBI <A/c>", "amount": "100000"}],
                      "bank_reconciliation": {"1311": {"evidence_sha256": SCAN_SHA}}},
                "D": {"k": "D"}}
    annex = [{"annex_code": c, "content": contents[c] if c == "C" else json.dumps(contents[c]), "content_hash": c * 64} for c in sealed_codes]
    ag = {"agreement_no": "AG/2026/7", "body_text": "AGREEMENT <TEXT> & more"}

    def _row(sql, params=None):
        return ag if "society_agreements" in sql else {"name": "Test Society"}

    def _rows(sql, params=None):
        return [{"sha256": SCAN_SHA, "stored_name": SCAN_SHA + ".png", "filename": "stmt.png"}] if "onboarding_evidence" in sql else annex
    monkeypatch.setattr(ob, "_row", _row); monkeypatch.setattr(ob, "_rows", _rows)
    monkeypatch.setattr(ob, "seated_officers", lambda sid: {
        "president": {"holder_name": "P Sundar", "signature_image": "pres.png"},
        "secretary": {"holder_name": "SC Verma", "signature_image": "sec.png"},
        "treasurer": {"holder_name": "TR Vashisht", "signature_image": None}})


def test_print_contains_agreement_and_every_annex(monkeypatch, tmp_path):
    _stub(monkeypatch, tmp_path)
    name, page = ob.agreement_print_html(7)
    assert name == "Agreement_AG_2026_7_with_annexes.html"
    assert "AGREEMENT &lt;TEXT&gt; &amp; more" in page and "SBI &lt;A/c&gt;" in page and "window.print" in page
    for t in ("Annex A", "Annex B", "Annex C", "Annex D"):
        assert t in page


def test_all_images_are_embedded(monkeypatch, tmp_path):
    _stub(monkeypatch, tmp_path)
    _, page = ob.agreement_print_html(7)
    assert "src='/assets" not in page and "http" not in page.replace("<!doctype html>", "")
    # Annex B signature images (bare file name and full relative path) and Annex C's attached scan are inline data URIs
    assert page.count("class='embed'") == 2 and page.count("class='embed scan'") == 1
    assert page.count("data:image/png;base64,") >= 3


def test_footer_with_all_four_parties_on_every_section(monkeypatch, tmp_path):
    _stub(monkeypatch, tmp_path)
    _, page = ob.agreement_print_html(7)
    assert page.count("<tfoot>") == 6                                   # agreement + 4 annexes + signature page
    for who in ("P Sundar", "SC Verma", "TR Vashisht", "For the Operator"):
        assert page.count(who) >= 6
    assert "table-footer-group" in page


def test_missing_image_is_reported_not_fatal(monkeypatch, tmp_path):
    _stub(monkeypatch, tmp_path)
    (tmp_path / "7" / "signatures" / "pres.png").unlink()
    _, page = ob.agreement_print_html(7)
    assert "image file not found" in page


def test_image_path_cannot_escape_assets(monkeypatch, tmp_path):
    _stub(monkeypatch, tmp_path)
    assert ob._image_data_uri("../../etc/passwd.png") is None


def test_print_refused_until_all_annexes_sealed(monkeypatch, tmp_path):
    _stub(monkeypatch, tmp_path, sealed_codes=("A", "B", "C"))
    with pytest.raises(ob.OnboardingError):
        ob.agreement_print_html(7)
