# app/services/document_archive.py
"""
Issued Agreements and NOCs kept as PDF evidence.

    app/assets/<society_id>/agreements/<agreement_no>_<sha12>.pdf
    app/assets/<society_id>/NOCs/<certificate_no>_<sha12>.pdf

Each stored PDF has a row in issued_documents with the SHA-256 the SERVER computed from the exact bytes it wrote. Same idea
as evidence_service: the stored file is re-read and re-hashed before it is ever handed out, and a file that is missing or no
longer matches is reported ("missing" / "altered") and never served.

A PDF that changes (edited NOC text, the sealed copy of an Agreement) is a NEW version with its own file and hash. Nothing is
overwritten, and the database refuses to edit or delete these rows.

Every lookup takes society_id from the server session, never from a URL or the browser.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

FOLDER = {"agreement": "agreements", "noc": "NOCs"}
MAX_PDF_BYTES = 20 * 1024 * 1024
STATUS_OK, STATUS_MISSING, STATUS_ALTERED = "ok", "missing", "altered"
EVENTS = ("issued", "printed", "emailed", "sealed", "uploaded")


class ArchiveError(Exception):
    """A document could not be stored or handed out. .status is not_found / missing / altered / invalid."""

    def __init__(self, status: str, message: str, expected: str | None = None, actual: str | None = None):
        super().__init__(message)
        self.status = status
        self.expected = expected          # the SHA-256 recorded when the file was issued
        self.actual = actual              # the SHA-256 of what is on disk now (None when the file is missing)


def _db(db=None):
    if db is not None:
        return db
    from database.db_manager import db as _default
    return _default


def sha256_hex(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def assets_root() -> Path:
    try:
        from app.dash_apps.callbacks.drilldown_callbacks import ASSETS_ROOT
        return Path(ASSETS_ROOT).resolve()
    except Exception:                                              # noqa: BLE001
        return (Path(__file__).resolve().parent.parent / "assets").resolve()


def archive_folder(society_id: int, kind: str) -> Path:
    """<assets>/<society_id>/agreements or <assets>/<society_id>/NOCs. The kind is looked up, never joined from input."""
    if kind not in FOLDER:
        raise ArchiveError("invalid", "Unknown document kind.")
    return assets_root() / str(int(society_id)) / FOLDER[kind]


def _safe(name: str) -> str:
    """A file-name stem from a document number such as NOC/7/2026/12 -> NOC-7-2026-12."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", (name or "").strip()).strip("-._")
    return s[:80] or "document"


def _write_verified(path: Path, data: bytes, digest: str) -> None:
    """Write via a temp file and rename, then read back and re-hash. Never leaves a half-written file under the final name."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and sha256_hex(path.read_bytes()) == digest:
        return
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".part")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    if sha256_hex(path.read_bytes()) != digest:
        raise OSError("read-back hash mismatch")


def store_pdf(society_id: int, kind: str, subject_id: int, document_no: str | None, pdf: bytes, *,
              text_hash: str | None = None, origin: str = "generated", event: str = "issued",
              created_by: int | None = None, db=None) -> dict:
    """Save a PDF under the society's folder and record its SHA-256. The same bytes stored twice give the same row
    (created=False); different bytes for the same record become the next version."""
    if kind not in FOLDER:
        raise ArchiveError("invalid", "Unknown document kind.")
    if event not in EVENTS or origin not in ("generated", "signed_scan"):
        raise ArchiveError("invalid", "Unknown event or origin.")
    if not pdf or len(pdf) > MAX_PDF_BYTES or not pdf.startswith(b"%PDF-"):
        raise ArchiveError("invalid", "That is not a PDF of a usable size (1 byte to 20 MB).")
    d = _db(db)
    digest = sha256_hex(pdf)
    name = f"{_safe(document_no or f'{kind}-{subject_id}')}_{digest[:12]}.pdf"
    try:
        _write_verified(archive_folder(society_id, kind) / name, pdf, digest)
    except Exception:                                              # noqa: BLE001
        log.exception("could not keep %s %s for society %s", kind, subject_id, society_id)
        raise ArchiveError("invalid", "The PDF could not be stored safely.")
    key = (int(society_id), kind, int(subject_id), digest)
    found = d._execute("SELECT * FROM issued_documents WHERE society_id=%s AND subject_kind=%s AND subject_id=%s AND sha256=%s",
                       key, fetch_one=True)
    if found:
        return {**dict(found), "created": False}
    row = d._execute(
        """INSERT INTO issued_documents (society_id, subject_kind, subject_id, version, document_no, filename, sha256,
                                         size_bytes, text_hash, origin, event, created_by)
           VALUES (%s,%s,%s,(SELECT COALESCE(MAX(version),0)+1 FROM issued_documents
                              WHERE society_id=%s AND subject_kind=%s AND subject_id=%s),%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (society_id, subject_kind, subject_id, sha256) DO NOTHING RETURNING *""",
        (int(society_id), kind, int(subject_id), int(society_id), kind, int(subject_id), document_no, name, digest,
         len(pdf), text_hash, origin, event, created_by), fetch_one=True)
    if row is None:                                                # lost a race with an identical store: that row is the answer
        row = d._execute("SELECT * FROM issued_documents WHERE society_id=%s AND subject_kind=%s AND subject_id=%s AND sha256=%s",
                         key, fetch_one=True)
        return {**dict(row), "created": False}
    return {**dict(row), "created": True}


# ── reading back, with the tamper check ───────────────────────────────────────────────────────────────────────
def list_documents(society_id: int, kind: str | None = None, subject_id: int | None = None, db=None) -> list[dict]:
    sql, params = "SELECT * FROM issued_documents WHERE society_id=%s", [int(society_id)]
    if kind:
        sql += " AND subject_kind=%s"
        params.append(kind)
    if subject_id is not None:
        sql += " AND subject_id=%s"
        params.append(int(subject_id))
    return _db(db)._execute(sql + " ORDER BY subject_kind, subject_id, version DESC", tuple(params), fetch_all=True) or []


def list_register(society_id: int, limit: int = 500, db=None) -> list[dict]:
    """Newest first, for the Documents screen: each row has `label` (NOC: the flat; Agreement: blank) and `is_latest`."""
    d = _db(db)
    rows = d._execute(
        """SELECT dd.*, CASE WHEN dd.subject_kind = 'noc' AND a.flat_number IS NOT NULL THEN 'Flat ' || a.flat_number ELSE '' END AS label
             FROM issued_documents dd
             LEFT JOIN nocs n ON dd.subject_kind = 'noc' AND n.id = dd.subject_id AND n.society_id = dd.society_id
             LEFT JOIN apartments a ON a.id = n.apartment_id AND a.society_id = dd.society_id
            WHERE dd.society_id = %s
            ORDER BY dd.created_at DESC, dd.id DESC LIMIT %s""", (int(society_id), int(limit)), fetch_all=True) or []
    newest = {(r["subject_kind"], r["subject_id"]): r["v"] for r in (d._execute(
        "SELECT subject_kind, subject_id, MAX(version) AS v FROM issued_documents WHERE society_id=%s GROUP BY 1, 2",
        (int(society_id),), fetch_all=True) or [])}
    return [{**dict(r), "is_latest": int(r["version"]) == int(newest.get((r["subject_kind"], r["subject_id"]), r["version"]))}
            for r in rows]


def _row(d, society_id: int, doc_id: int) -> dict:
    row = d._execute("SELECT * FROM issued_documents WHERE id=%s AND society_id=%s", (int(doc_id), int(society_id)), fetch_one=True)
    if not row:
        raise ArchiveError("not_found", "That document was not found.")
    return dict(row)


def _check(row: dict) -> tuple[str, str | None, bytes | None]:
    name = os.path.basename((row.get("filename") or "").strip())      # a stored value can never leave the folder
    expected = str(row.get("sha256") or "").strip().lower()
    path = archive_folder(row["society_id"], row["subject_kind"]) / name
    if not name or not expected or not path.is_file():
        return STATUS_MISSING, None, None
    data = path.read_bytes()
    actual = sha256_hex(data)
    if actual != expected or int(row.get("size_bytes") or len(data)) != len(data):
        return STATUS_ALTERED, actual, None
    return STATUS_OK, actual, data


RECORD_CURRENT, RECORD_CHANGED, RECORD_EARLIER, RECORD_UNKNOWN = "current", "changed", "earlier", "n/a"


def record_status(row: dict, d) -> str:
    """Does this PDF still show the record's current text?
    current: the record's text hashes to the text_hash this PDF was made from. changed: the record was edited after this PDF
    (the newest PDF no longer shows it). earlier: a newer version of this document exists, so this one is history.
    n/a: a scanned paper copy, or the record could not be read."""
    if row.get("origin") != "generated" or not row.get("text_hash"):
        return RECORD_UNKNOWN
    newest = d._execute("SELECT MAX(version) AS v FROM issued_documents WHERE society_id=%s AND subject_kind=%s AND subject_id=%s",
                        (row["society_id"], row["subject_kind"], row["subject_id"]), fetch_one=True) or {}
    if int(newest.get("v") or 0) > int(row["version"]):
        return RECORD_EARLIER
    try:
        from app.services import document_signing as ds
        _sid, canonical = ds.item_text(row["subject_kind"], int(row["subject_id"]), d)
        return RECORD_CURRENT if ds.sha256(canonical) == str(row["text_hash"]).strip().lower() else RECORD_CHANGED
    except Exception:                                              # noqa: BLE001 - the record may be gone; say so, do not guess
        return RECORD_UNKNOWN


def verify_document(society_id: int, doc_id: int, db=None) -> dict:
    d = _db(db)
    row = _row(d, society_id, doc_id)
    status, actual, _ = _check(row)
    if status != STATUS_OK:
        log.warning("issued document %s (society %s) failed its integrity check: %s", row["id"], society_id, status)
    return {"id": row["id"], "status": status, "expected": str(row["sha256"]).lower(), "actual": actual,
            "filename": row["filename"], "kind": row["subject_kind"], "version": row["version"],
            "record": record_status(row, d)}


def read_verified(society_id: int, doc_id: int, db=None) -> tuple[dict, bytes]:
    """The row and its bytes, only while the file still matches its recorded SHA-256."""
    row = _row(_db(db), society_id, doc_id)
    status, actual, data = _check(row)
    expected = str(row.get("sha256") or "").strip().lower()
    if status == STATUS_MISSING:
        raise ArchiveError(STATUS_MISSING, "The stored file could not be found. It may have been removed.", expected, None)
    if status == STATUS_ALTERED:
        raise ArchiveError(STATUS_ALTERED, "The stored file no longer matches the SHA-256 recorded when it was issued, "
                                           "so it is not being shown.", expected, actual)
    return row, data


# ── PDF rendering (reportlab only, drawn directly: no HTML engine) ────────────────────────────────────────────
def _qr_image(payload: str | None):
    if not payload:
        return None
    try:
        import qrcode
        buf = io.BytesIO()
        qrcode.make(payload).save(buf, format="PNG")
        buf.seek(0)
        return buf
    except Exception:                                              # noqa: BLE001 - a QR is an extra; never block the PDF
        return None


def render_noc_pdf(*, society_name: str, society_address: str, certificate_no: str, text: str,
                   valid_until=None, qr_payload: str | None = None, text_hash: str | None = None) -> bytes:
    """The NOC as a letter: society name and address, the text (English and/or Hindi), then certificate number, validity,
    the text's SHA-256 and a QR code. Fonts and Hindi shaping come from pdf_text."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table

    from app.services import pdf_text as T
    T.register_fonts()
    body = T.style("body", 12, 19)
    head = T.style("head", 15, 19, bold=True, align=1)
    title = T.style("title", 22, 28, bold=True, align=1, spaceAfter=10)
    small = T.style("small", 7, 9)
    small.fontName, small.shaping = T.mono_font(), False
    story = [Paragraph(T.mark(society_name), head)]
    if society_address:
        story.append(Paragraph(T.mark(society_address), T.style("addr", 9, 12, align=1)))
    story.append(Spacer(1, 10))
    for i, line in enumerate(T.lines(text)):
        first = (text or "").split("\n")[0].strip().upper() if i == 0 else ""
        story.append(Paragraph(line or "&nbsp;", title if first == "NO OBJECTION CERTIFICATE" else body))
    story.append(Spacer(1, 14))
    qr = _qr_image(qr_payload)
    foot = [Paragraph(T.mark(f"Certificate {certificate_no}" + (f" | valid until {valid_until}" if valid_until else "")), small),
            Paragraph("Text SHA-256: " + (text_hash or sha256_hex(text or "")), small)]
    story.append(Table([[foot, Image(qr, 26 * mm, 26 * mm)]], colWidths=[140 * mm, 30 * mm]) if qr else foot[0])
    if not qr:
        story.append(foot[1])
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm, topMargin=20 * mm, bottomMargin=18 * mm,
                      title=f"NOC {certificate_no}", author=society_name or "",
                      invariant=1).build(story)          # invariant: same text -> same bytes -> same SHA-256, not a new version per click
    return buf.getvalue()


# ── the two hooks the app calls ─────────────────────────────────────────────────────────────────────────────
def archive_noc(society_id: int, noc_id: int, text: str | None, *, event: str = "issued", created_by: int | None = None,
                society_name: str = "", society_address: str = "", db=None) -> dict:
    """Render the NOC as shown to the person and store it. `text` is what is in the editor; it becomes the NOC's stored
    wording unless the NOC is already sealed, in which case the sealed wording is used and the edit is ignored."""
    d = _db(db)
    noc = d._execute("SELECT * FROM nocs WHERE id=%s AND society_id=%s", (int(noc_id), int(society_id)), fetch_one=True)
    if not noc:
        raise ArchiveError("not_found", "NOC not found.")
    noc = dict(noc)
    sealed = bool(d._execute("SELECT 1 AS x FROM signed_records WHERE subject_kind='noc' AND subject_id=%s AND status='valid'",
                             (int(noc_id),), fetch_one=True))
    wording = (text or "").strip() or noc.get("body_text") or ""
    reverted = False
    if sealed and wording != (noc.get("body_text") or ""):
        wording, reverted = noc.get("body_text") or "", True
    elif wording != (noc.get("body_text") or ""):
        d._execute("UPDATE nocs SET body_text=%s WHERE id=%s AND society_id=%s", (wording, int(noc_id), int(society_id)))
    if not wording:
        raise ArchiveError("invalid", "The NOC has no text to store.")
    from app.services import document_signing as ds
    _sid, canonical = ds.item_text("noc", int(noc_id), d)
    pdf = render_noc_pdf(society_name=society_name, society_address=society_address, certificate_no=noc.get("certificate_no") or "",
                         text=wording, valid_until=noc.get("valid_until"), qr_payload=noc.get("qr_payload"),
                         text_hash=ds.sha256(canonical))
    out = store_pdf(society_id, "noc", noc_id, noc.get("certificate_no"), pdf, text_hash=ds.sha256(canonical),
                    event="sealed" if sealed and event == "sealed" else event, created_by=created_by, db=d)
    out["text_reverted"] = reverted
    return out


def archive_agreement(society_id: int, agreement_id: int, *, st: dict | None = None, event: str = "issued",
                      created_by: int | None = None, db=None) -> dict:
    """Store the Agreement with all sealed annexes as PDF. Not yet sealed: it shows any signatures recorded so far and ends with
    the paper counterpart page. Sealed: recorded signatures and the seal, no paper page. `st` is document_signing.status(); it is
    looked up when not given."""
    from app.services import agreement_pdf as ap
    d = _db(db)
    ag = d._execute("SELECT id, agreement_no FROM society_agreements WHERE id=%s AND society_id=%s",
                    (int(agreement_id), int(society_id)), fetch_one=True)
    if not ag:
        raise ArchiveError("not_found", "Agreement not found.")
    from app.services import document_signing as ds
    inp = ap.build_inputs(int(society_id))
    st = st if st is not None else ds.status("agreement", int(agreement_id), d)
    seal = st.get("seal") or {}
    text_hash = st.get("item_hash") or sha256_hex(inp["body_text"])
    signers = [{"office": x.get("office_code"), "at": str(x.get("signed_at"))} for x in st.get("signed", [])] or None
    pdf = ap.render_agreement_full_pdf(**inp, text_hash=text_hash, signers=signers, sealed_at=seal.get("signed_at"),
                                       key_id=seal.get("key_id"), paper_page=not st.get("sealed"))
    return store_pdf(society_id, "agreement", agreement_id, ag["agreement_no"], pdf, text_hash=text_hash, event=event,
                     created_by=created_by, db=d)


def store_signed_scan(society_id: int, kind: str, subject_id: int, document_no: str | None, filename: str, data: bytes,
                      created_by: int | None, db=None) -> dict:
    """A signed paper copy (scanned to PDF) filed beside the generated one."""
    if os.path.splitext(filename or "")[1].lower() != ".pdf":
        raise ArchiveError("invalid", "Attach the signed copy as a PDF.")
    return store_pdf(society_id, kind, subject_id, f"{document_no or kind}-signed", data, origin="signed_scan",
                     event="uploaded", created_by=created_by, db=db)
