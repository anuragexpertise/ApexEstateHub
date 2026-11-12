# app/services/evidence_service.py
"""
Evidence register: list a society's stored scans, re-check each against the SHA-256 recorded when it was uploaded,
and hand out only bytes that passed that check.

Same idea as society_service.verify_registration_certificate: trust neither the file name nor the browser. Re-read the
stored file, re-hash it, and compare with the hash in onboarding_evidence. A file that is missing or no longer matches is
reported ("missing" / "altered") and is never served.

Every lookup is scoped by society_id taken from the server session by the caller, never from a URL or the client.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
from datetime import datetime

from app.services import onboarding_service as ob
from app.utils import now_ist

log = logging.getLogger(__name__)

STATUS_OK, STATUS_MISSING, STATUS_ALTERED = "ok", "missing", "altered"

PURPOSE_LABEL = {
    "election_results": "Signed election minutes", "registration_certificate": "Registration certificate",
    "cash_count": "Cash-count certificate", "audited_report": "Audited statements", "review_letter": "CA review letter",
    "ca_rates_letter": "CA letter on TDS / GST rates", "bank_statement": "Bank statement",
    "account_statement": "Account statement", "pending_receivables": "Pending receivables",
    "tds_rates": "TDS rates", "declaration_undivided_interest": "Declaration of undivided interest",
    "brought_forward": "Brought-forward balances", "apartment_charges": "Apartment charges",
    "paper_signature": "Paper signature", "adoption_resolution": "Adoption resolution",
    "adoption_minutes": "Adoption minutes", "adviser_appointment_letter": "Adviser appointment letter",
    "other_paper_evidence": "Other paper evidence",
}

MIME = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


class EvidenceError(Exception):
    """Evidence could not be handed out. .status is not_found / missing / altered; the message is safe to show."""

    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


def purpose_label(purpose: str) -> str:
    return PURPOSE_LABEL.get(purpose, (purpose or "").replace("_", " ").capitalize())


def list_register(society_id: int) -> list[dict]:
    """Every stored scan for the society, newest first. Reads the database only (no hashing)."""
    return ob._rows("""SELECT e.id, e.purpose, e.filename, e.stored_name, e.sha256, e.size_bytes, e.uploaded_at,
                              u.name AS uploaded_by_name
                         FROM onboarding_evidence e
                         LEFT JOIN users u ON u.id = e.uploaded_by
                        WHERE e.society_id = %s
                        ORDER BY e.uploaded_at DESC, e.id DESC""", (int(society_id),))


def _get_row(society_id: int, evidence_id: int) -> dict:
    row = ob._row("""SELECT id, purpose, filename, stored_name, sha256, size_bytes, uploaded_at
                       FROM onboarding_evidence WHERE id = %s AND society_id = %s""",
                  (int(evidence_id), int(society_id)))
    if not row:
        raise EvidenceError("not_found", "That evidence record was not found.")
    return row


def _check(society_id: int, row: dict) -> tuple[str, str | None, bytes | None]:
    """Re-read the stored file and re-hash it. Returns (status, actual_sha256, bytes-if-ok)."""
    name = os.path.basename((row.get("stored_name") or "").strip())      # never let a stored value escape the folder
    expected = str(row.get("sha256") or "").strip().lower()
    if not name or not expected:
        return STATUS_MISSING, None, None
    path = ob.evidence_folder(society_id) / name
    if not path.is_file():
        return STATUS_MISSING, None, None
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    size = row.get("size_bytes")
    if actual != expected or (size is not None and int(size) != len(data)):
        return STATUS_ALTERED, actual, None
    return STATUS_OK, actual, data


def verify_row(society_id: int, evidence_id: int) -> dict:
    """The tamper check for one record: {id, status, expected, actual, filename, purpose}."""
    row = _get_row(society_id, evidence_id)
    status, actual, _ = _check(society_id, row)
    if status != STATUS_OK:
        log.warning("evidence %s (society %s) failed integrity check: %s", row["id"], society_id, status)
    return {"id": row["id"], "status": status, "expected": str(row["sha256"]).lower(), "actual": actual,
            "filename": row["filename"], "purpose": row["purpose"]}


def read_verified(society_id: int, evidence_id: int) -> tuple[dict, bytes]:
    """The row and its bytes, only if the file still matches its recorded hash. Raises EvidenceError otherwise."""
    row = _get_row(society_id, evidence_id)
    status, _, data = _check(society_id, row)
    if status == STATUS_MISSING:
        raise EvidenceError(STATUS_MISSING, "The stored file could not be found. It may have been removed.")
    if status == STATUS_ALTERED:
        raise EvidenceError(STATUS_ALTERED, "The stored file no longer matches the fingerprint (SHA-256) recorded when "
                                            "it was uploaded, so it is not being shown. It may have been altered or damaged.")
    return row, data


def _fmt_dt(v) -> str:
    return v.strftime("%d %b %Y %H:%M") if isinstance(v, datetime) else str(v or "")


def as_pdf(row: dict, data: bytes) -> bytes:
    """A PDF scan is returned as is. A PNG/JPG scan is wrapped on one A4 page with its file name and SHA-256 underneath."""
    ext = os.path.splitext(row.get("stored_name") or "")[1].lower()
    if ext == ".pdf":
        return data
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    w, h = A4
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(row.get("filename") or "Evidence")
    img = ImageReader(io.BytesIO(data))
    iw, ih = img.getSize()
    margin, foot = 28, 48
    scale = min((w - 2 * margin) / iw, (h - margin - foot - margin) / ih)
    dw, dh = iw * scale, ih * scale
    c.drawImage(img, (w - dw) / 2, foot + (h - margin - foot - dh) / 2, dw, dh, mask="auto")
    c.setFont("Helvetica", 8)
    c.drawString(margin, foot - 14, f"{row.get('filename') or ''}  |  {purpose_label(row.get('purpose'))}  |  "
                                    f"uploaded {_fmt_dt(row.get('uploaded_at'))}")
    c.setFont("Courier", 7)
    c.drawString(margin, foot - 26, "SHA-256 of the original file: " + str(row.get("sha256") or ""))
    c.showPage()
    c.save()
    return buf.getvalue()


def register_pdf(society_id: int, society_name: str) -> bytes:
    """One-page-per-screenful register of all evidence with its recorded SHA-256 and a fresh integrity result."""
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    ss = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=ss["BodyText"], fontSize=7.5, leading=9)
    mono = ParagraphStyle("mono", parent=cell, fontName="Courier", fontSize=6.5, leading=8)
    head = ParagraphStyle("head", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)
    rows = list_register(society_id)
    labels = {STATUS_OK: "Verified", STATUS_MISSING: "File missing", STATUS_ALTERED: "ALTERED"}
    data = [[Paragraph(t, head) for t in ("#", "Document", "File name", "Uploaded", "Size", "SHA-256 recorded at upload", "Integrity now")]]
    bad = 0
    for i, r in enumerate(rows, 1):
        status, _, _ = _check(society_id, r)
        bad += status != STATUS_OK
        kb = f"{(r.get('size_bytes') or 0) / 1024:.0f} KB"
        data.append([Paragraph(str(i), cell), Paragraph(escape(purpose_label(r["purpose"])), cell),
                     Paragraph(escape(r["filename"] or ""), cell),
                     Paragraph(escape(_fmt_dt(r["uploaded_at"]) + ((" by " + r["uploaded_by_name"]) if r.get("uploaded_by_name") else "")), cell),
                     Paragraph(kb, cell), Paragraph(escape(str(r["sha256"]).lower()), mono),
                     Paragraph((f"<b>{labels[status]}</b>") if status != STATUS_OK else labels[status], cell)])
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=28, bottomMargin=28,
                            title="Evidence register")
    story = [Paragraph("Evidence register", ss["Title"]),
             Paragraph(escape(society_name or "") + " | generated " + _fmt_dt(now_ist()) +
                       f" | {len(rows)} document(s)" + (f" | <b>{bad} FAILED the integrity check</b>" if bad else " | all verified"), ss["BodyText"]),
             Spacer(1, 8)]
    if rows:
        t = Table(data, repeatRows=1, colWidths=[20, 105, 135, 105, 38, 290, 62])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#34495e")),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b8c2cf")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")])]))
        story.append(t)
    else:
        story.append(Paragraph("No evidence has been uploaded yet.", ss["BodyText"]))
    story += [Spacer(1, 8), Paragraph("Each SHA-256 is computed by the server from the file as uploaded. 'Integrity now' re-reads "
                                      "the stored file and compares it with that value.", cell)]
    doc.build(story)
    return buf.getvalue()
