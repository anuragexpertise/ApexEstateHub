"""Reusable paper-signing evidence workflow for onboarding/adoption datasets.

Flow: prepare rows/data -> server-side PDF with a signing footer (make_document) -> download/print ->
signed & scanned upload (PDF/PNG/JPG) -> server SHA-256 -> stored onboarding evidence.

Three hashes tie the paper to the data (see docs/PAPER_SIGNING.md):
  snapshot_sha256  - the exact rows/totals that were printed (survives re-rendering the PDF)
  document_sha256  - the generated, unsigned PDF
  sha256           - the signed scan the user uploads (stored on the evidence row, linked to the two above)
Every page of the PDF carries the Doc ID, so a scan can be matched to its document by eye as well as by record.
If the data changes after signing, evidence_status(..., current_snapshot=...) reports the scan as stale.

Only the "paper" signing mode exists today. "password" (document_signing.py) and "esign" (esign_adapter.py) are the
planned modes; SIGNING_MODES is the single place a new mode is registered.

This module is deliberately small/pure where possible; DB writes go through
onboarding_service.store_evidence_file/record_document/get_evidence.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import re
from datetime import date
from html import escape

log = logging.getLogger(__name__)

SIGNING_MODES = ("paper",)   # later: "password" (document_signing.py), "esign" (esign_adapter.py)

from app.services import onboarding_service as ob

ALLOWED_EXT = {".pdf": b"%PDF-", ".png": b"\x89PNG", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff"}
MAX_SCAN_BYTES = 5 * 1024 * 1024


def decode_upload(contents: str | None) -> bytes | None:
    if not contents or "," not in contents:
        return None
    try:
        return base64.b64decode(contents.split(",", 1)[1])
    except Exception:  # noqa: BLE001
        return None


def validate_scan(filename: str | None, raw: bytes | None) -> tuple[str, bytes]:
    from pathlib import Path
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ob.OnboardingError("Attach the signed scan as a PDF, PNG or JPG (max 5 MB).")
    if not raw or len(raw) > MAX_SCAN_BYTES:
        raise ob.OnboardingError("The signed scan must be between 1 byte and 5 MB.")
    if not raw.startswith(ALLOWED_EXT[ext]):
        raise ob.OnboardingError("The file does not look like a real %s." % ext.lstrip(".").upper())
    return ext, raw


def store_signed_scan(society_id: int, purpose: str, actor_id: int, filename: str | None,
                      contents: str | None, meta: dict | None = None, acc_id: int | None = None,
                      kind: str | None = None, doc_id: str | None = None) -> dict:
    """Validate and store a signed scan, bound to the document EstateHub generated for it.

    The scan is linked to `doc_id` if given, else to the newest generated document for this purpose (and `kind`, when a
    purpose is shared by several documents). With no generated document it is still stored, but marked unbound."""
    raw = decode_upload(contents)
    if not raw:
        raise ob.OnboardingError("Upload the signed & scanned file (PDF, PNG or JPG).")
    _, raw = validate_scan(filename, raw)
    doc = None
    try:
        doc = ob.latest_document(society_id, purpose, kind=kind, doc_id=doc_id)
    except Exception:  # noqa: BLE001  (best effort: an unbound scan is still evidence)
        log.exception("could not look up the generated document for %s", purpose)
    m = dict(meta or {})
    if kind:
        m.setdefault("kind", kind)
    m["bound"] = bool(doc)
    if doc:
        m["generated_at"] = str(doc.get("generated_at") or "")
    ev = ob.store_evidence_file(society_id, purpose, acc_id, filename or "signed_scan", raw, actor_id, m,
                                doc_id=(doc or {}).get("doc_id"),
                                document_sha256=(doc or {}).get("document_sha256"),
                                snapshot_sha256=(doc or {}).get("snapshot_sha256"))
    ev.setdefault("bound", bool(doc))
    return ev


def evidence_status(society_id: int, purpose: str, acc_id: int | None = None,
                    current_snapshot: str | None = None) -> dict:
    """Latest signed scan for a purpose. Pass current_snapshot (snapshot_hash of the data as it is NOW) to learn whether
    the entries changed after the scan was signed (stale)."""
    try:
        rows = ob.get_evidence(society_id, purpose, acc_id) if acc_id is not None else ob.get_evidence(society_id, purpose)
    except Exception:  # noqa: BLE001
        rows = []
    latest = rows[0] if rows else None
    snap = (latest or {}).get("snapshot_sha256")
    return {
        "evidenced": bool(latest),
        "sha256": (latest or {}).get("sha256"),
        "filename": (latest or {}).get("filename"),
        "uploaded_at": (latest or {}).get("uploaded_at"),
        "doc_id": (latest or {}).get("doc_id"),
        "snapshot_sha256": snap,
        "document_sha256": (latest or {}).get("document_sha256"),
        "bound": bool((latest or {}).get("doc_id")),
        "stale": bool(latest and current_snapshot and snap and snap != current_snapshot),
        "count": len(rows),
        "latest": latest,
    }


def stored_message(ev: dict) -> str:
    """One-line confirmation shown right after an upload."""
    msg = f"Signed scan stored. SHA-256: {ev.get('sha256')}"
    if ev.get("doc_id"):
        return msg + f" · linked to Doc ID {ev['doc_id']}"
    return msg + " · not linked to a document generated here (print the PDF from EstateHub first so the scan can be matched)"


def status_line(st: dict) -> tuple[str, str]:
    """(bootstrap colour, text) for an evidence_status dict."""
    if not st.get("evidenced"):
        return "muted", "No signed scan uploaded yet."
    short = str(st.get("sha256") or "")[:16]
    name = st.get("filename") or "scan"
    if st.get("stale"):
        return "warning", (f"Signed scan {name} (SHA-256 {short}…) was signed on earlier entries. The entries have "
                           "changed since: print again, sign and upload a new scan.")
    if st.get("bound"):
        return "success", f"Signed scan stored: {name} | SHA-256 {short}… | Doc ID {st.get('doc_id')}"
    return "info", (f"Signed scan stored: {name} | SHA-256 {short}… | not linked to a generated document "
                    "(print the PDF from EstateHub first so the scan can be matched).")


# ── snapshot + PDF ───────────────────────────────────────────────────────────────────────────────────────────
def _cell(c) -> str:
    return "" if c is None else str(c)


def snapshot_hash(purpose: str, title: str, headers: list[str], rows: list[list], meta_lines: list[str] | None = None,
                  sections: list[dict] | None = None) -> str:
    """SHA-256 of exactly what is printed (headers, rows, extra sections and the meta lines). It does not depend on the
    date, the Doc ID or the PDF renderer, so the same data always gives the same snapshot."""
    payload = {"purpose": purpose, "title": title, "headers": [_cell(h) for h in headers or []],
               "rows": [[_cell(c) for c in r] for r in rows or []], "meta": [_cell(m) for m in (meta_lines or [])],
               "sections": [{"heading": _cell(x.get("heading")), "headers": [_cell(h) for h in x.get("headers") or []],
                             "rows": [[_cell(c) for c in r] for r in x.get("rows") or []]} for x in (sections or [])]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def make_doc_id(society_id: int, purpose: str, snapshot: str) -> str:
    """Printed on every page. Deterministic: the same data in the same society gives the same Doc ID."""
    return f"EH-{int(society_id)}-{re.sub(r'[^A-Z0-9]', '', purpose.upper())[:10]}-{snapshot[:8].upper()}"


_FONT_CACHE: dict = {}


def _fonts() -> tuple[str, str, bool]:
    """(regular, bold, has_rupee_glyph). Uses DejaVu Sans when it can be found (has the rupee sign and Devanagari);
    otherwise Helvetica, where the rupee sign is printed as 'Rs.'."""
    if "f" in _FONT_CACHE:
        return _FONT_CACHE["f"]
    import os
    from pathlib import Path
    res = ("Helvetica", "Helvetica-Bold", False)
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        here = Path(__file__).resolve().parents[1] / "assets" / "fonts"
        pairs = [(os.environ.get("ESTATEHUB_PDF_FONT"), os.environ.get("ESTATEHUB_PDF_FONT_BOLD")),
                 (str(here / "DejaVuSans.ttf"), str(here / "DejaVuSans-Bold.ttf")),
                 ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")]
        for reg, bold in pairs:
            if not reg or not bold or not os.path.exists(reg) or not os.path.exists(bold):
                continue
            try:
                pdfmetrics.registerFont(TTFont("EH-Sans", reg))
                pdfmetrics.registerFont(TTFont("EH-Sans-Bold", bold))
                res = ("EH-Sans", "EH-Sans-Bold", True)
                break
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    _FONT_CACHE["f"] = res
    return res


def _render_pdf(title: str, society_name: str, subtitle: str, headers: list[str], rows: list[list], signers: list[str],
                meta_lines: list[str], doc_id: str, snapshot: str, sections: list[dict] | None = None,
                compress: bool = True) -> bytes:
    from xml.sax.saxutils import escape as xesc
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    reg, bold, has_rupee = _fonts()

    def T(v) -> str:
        t = _cell(v)
        return t if has_rupee else t.replace("\u20b9", "Rs.")

    def P(v, style) -> Paragraph:
        return Paragraph(xesc(T(v)).replace("\n", "<br/>"), style)

    h1 = ParagraphStyle("h1", fontName=bold, fontSize=15, leading=18, spaceAfter=2)
    h2 = ParagraphStyle("h2", fontName=reg, fontSize=10, leading=13, textColor=colors.HexColor("#444444"), spaceAfter=6)
    h3 = ParagraphStyle("h3", fontName=bold, fontSize=10.5, leading=13, spaceBefore=10, spaceAfter=4)
    muted = ParagraphStyle("muted", fontName=reg, fontSize=8.5, leading=11, textColor=colors.HexColor("#555555"))
    cellst = ParagraphStyle("cell", fontName=reg, fontSize=8, leading=10)
    cellb = ParagraphStyle("cellb", fontName=bold, fontSize=8, leading=10)
    headst = ParagraphStyle("head", fontName=bold, fontSize=8, leading=10)
    who = ParagraphStyle("who", fontName=bold, fontSize=8.5, leading=11, alignment=1)
    sub = ParagraphStyle("sub", fontName=reg, fontSize=7.5, leading=10, alignment=1, textColor=colors.HexColor("#555555"))

    margin = 12 * mm
    avail = A4[0] - 2 * margin

    def table(hdr, body):
        ncol = max(len(hdr), 1)
        weights = []
        for ci in range(ncol):
            longest = max([len(_cell(hdr[ci]))] + [len(_cell(r[ci])) for r in body if ci < len(r)] + [4])
            weights.append(min(max(longest, 6), 36))
        total = float(sum(weights))
        widths = [avail * w / total for w in weights]
        data = [[P(h, headst) for h in hdr]]
        bold_rows = []
        for ri, r in enumerate(body, start=1):
            cells = list(r) + [""] * (ncol - len(r))
            is_total = any(_cell(c).strip().upper() == "TOTAL" for c in cells)
            if is_total:
                bold_rows.append(ri)
            data.append([P(c, cellb if is_total else cellst) for c in cells[:ncol]])
        if not body:
            data.append([P("(no rows)", cellst)] + [""] * (ncol - 1))
        t = Table(data, colWidths=widths, repeatRows=1)
        style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#777777")),
                 ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f4f7")),
                 ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                 ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
        for ri in bold_rows:
            style.append(("BACKGROUND", (0, ri), (-1, ri), colors.HexColor("#fafafa")))
        t.setStyle(TableStyle(style))
        return t

    story = [P(title, h1), P(f"{society_name}" + (f" - {subtitle}" if subtitle else ""), h2),
             P(f"Generated {date.today().isoformat()} · Doc ID {doc_id}", muted)]
    for m in meta_lines or []:
        story.append(P(m, muted))
    story += [Spacer(1, 6), table(headers, rows)]
    for sec in sections or []:
        story += [P(sec.get("heading") or "", h3), table(sec.get("headers") or [], sec.get("rows") or [])]
    story += [Spacer(1, 8),
              P("After printing and obtaining signatures, scan every signed page and upload the scan in EstateHub. "
                f"The server computes the SHA-256 of the scan and links it to Doc ID {doc_id}.", muted),
              Spacer(1, 14)]
    sig_cells = [[P(x, who) for x in signers],
                 [P("Signature & date", sub) for _ in signers]]
    names = [[Spacer(1, 34) for _ in signers]] + sig_cells
    sig = Table(names, colWidths=[avail / max(len(signers), 1)] * max(len(signers), 1))
    sig.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
                             ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8)]))
    story.append(KeepTogether([sig]))

    footer_left = T(f"{society_name} - {title}")[:110]
    footer_mid = f"Doc ID {doc_id} · data SHA-256 {snapshot[:16]}"

    class _Numbered(rl_canvas.Canvas):
        def __init__(self, *a, **k):
            rl_canvas.Canvas.__init__(self, *a, **k)
            self._saved = []

        def showPage(self):
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            n = len(self._saved)
            for st in self._saved:
                self.__dict__.update(st)
                self.setFont(reg, 7)
                self.setFillGray(0.35)
                self.drawString(margin, 11 * mm, footer_left)
                self.drawString(margin, 7 * mm, footer_mid)
                self.drawRightString(A4[0] - margin, 7 * mm, f"Page {self._pageNumber} of {n}")
                rl_canvas.Canvas.showPage(self)
            rl_canvas.Canvas.save(self)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=margin,
                            bottomMargin=18 * mm, title=T(title), author="EstateHub", subject=doc_id,
                            pageCompression=1 if compress else 0)
    doc.build(story, canvasmaker=_Numbered)
    return buf.getvalue()


def make_document(society_id: int, purpose: str, actor_id: int | None, title: str, society_name: str, subtitle: str,
                  headers: list[str], rows: list[list], signers: list[str], meta_lines: list[str] | None = None,
                  sections: list[dict] | None = None, kind: str | None = None,
                  signing_mode: str = "paper") -> dict:
    """Build the unsigned document for signing and remember it (so the signed scan can be bound to it).

    Returns {filename, data (bytes), fmt ('pdf', or 'html' if reportlab is missing), doc_id, snapshot_sha256,
    document_sha256}. `kind` separates several documents that share one purpose (e.g. bulk uploads)."""
    if signing_mode not in SIGNING_MODES:
        raise ob.OnboardingError(f"Signing mode '{signing_mode}' is not available yet (paper only).")
    meta_lines = list(meta_lines or [])
    snap = snapshot_hash(purpose, title, headers, rows, meta_lines, sections)
    doc_id = make_doc_id(society_id, purpose, snap)
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_") or "document"
    try:
        data = _render_pdf(title, society_name, subtitle, headers, rows, signers, meta_lines, doc_id, snap, sections)
        fmt = "pdf"
    except ImportError:
        log.warning("reportlab is not installed; falling back to the printable HTML for %s", purpose)
        extra = [f"Doc ID {doc_id}"] + meta_lines
        _, page = printable_html(title, society_name, subtitle, headers, rows, signers, extra)
        data, fmt = page.encode("utf-8"), "html"
    digest = hashlib.sha256(data).hexdigest()
    try:
        m = {"title": title, "kind": kind} if kind else {"title": title}
        ob.record_document(society_id, purpose, doc_id, snap, digest, fmt,
                           len(rows or []) + sum(len(x.get("rows") or []) for x in (sections or [])), m, actor_id,
                           signing_mode)
    except Exception:  # noqa: BLE001  (the download still works; the scan will just be stored unbound)
        log.exception("could not record the generated document %s", doc_id)
    return {"filename": f"{safe}_{doc_id}.{fmt}", "data": data, "fmt": fmt, "doc_id": doc_id,
            "snapshot_sha256": snap, "document_sha256": digest}


def apartment_charges_section(society_id: int, monthly_budget=None) -> dict:
    """Part A of the Declaration of Undivided Interest: the apartment-wise table (flat, area, undivided interest %,
    and each flat's share of the monthly common-expense budget when a budget is given)."""
    from decimal import Decimal, InvalidOperation
    recs = ob._rows("""SELECT flat_number, apartment_size, undivided_interest_pct FROM apartments
                        WHERE society_id=%s AND active ORDER BY flat_number""", (society_id,)) or []

    def nat(r):
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(r.get("flat_number") or ""))]

    recs = sorted(recs, key=nat)
    try:
        budget = Decimal(str(monthly_budget)) if monthly_budget not in (None, "") else None
    except InvalidOperation:
        budget = None
    body, area, pct, share = [], 0, Decimal(0), Decimal(0)
    for r in recs:
        p = Decimal(str(r.get("undivided_interest_pct"))) if r.get("undivided_interest_pct") is not None else None
        sz = int(r.get("apartment_size") or 0)
        area += sz
        if p is not None:
            pct += p
        s_amt = (budget * p / Decimal(100)).quantize(Decimal("0.01")) if (budget is not None and p is not None) else None
        if s_amt is not None:
            share += s_amt
        body.append([r.get("flat_number") or "", str(sz) if sz else "", f"{p:.4f}" if p is not None else "",
                     f"{s_amt:,.2f}" if s_amt is not None else ""])
    body.append(["TOTAL", str(area) if area else "", f"{pct:.4f}" if recs else "", f"{share:,.2f}" if budget is not None else ""])
    return {"heading": "Part A - Apartment-wise charges (undivided interest)",
            "headers": ["Flat no.", "Area (sq ft)", "Undivided interest %", "Share of monthly budget (₹)"], "rows": body}


def _table(headers: list[str], rows: list[list[str]]) -> str:
    th = "".join(f"<th>{escape(str(h))}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{escape('' if c is None else str(c))}</td>" for c in r) + "</tr>" for r in rows) or "<tr><td colspan='%d'>(no rows)</td></tr>" % len(headers)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"


def printable_html(title: str, society_name: str, subtitle: str, headers: list[str], rows: list[list[str]],
                   signers: list[str], meta_lines: list[str] | None = None) -> tuple[str, str]:
    """Return (filename, self-contained printable HTML) with a signing footer."""
    meta = "".join(f"<div>{escape(m)}</div>" for m in (meta_lines or []))
    sig_cells = "".join(
        f"<td><div class='box'></div><div class='who'>{escape(s)}</div><div class='muted'>Signature & date</div></td>"
        for s in signers)
    css = (
        "@page{size:A4;margin:12mm}body{font:12pt/1.4 Georgia,serif;color:#111}h1{font-size:16pt;margin:0 0 4px}"
        "h2{font-size:11pt;margin:0 0 10px;font-weight:normal;color:#444}table{border-collapse:collapse;width:100%;margin:10px 0}"
        "th,td{border:1px solid #777;padding:5px 6px;vertical-align:top;font-size:10.5pt}th{background:#f2f4f7}"
        ".muted{color:#555;font-size:9.5pt}.sig{margin-top:18px;page-break-inside:avoid}.sig td{width:auto;text-align:center}"
        ".box{height:42px;border-bottom:1px solid #333;margin-bottom:4px}.who{font-weight:600;font-size:10pt}"
        "@media print{.noprint{display:none}}")
    doc = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{escape(title)}</title><style>{css}</style></head><body>"
        "<p class='noprint'>Use Print (Ctrl+P) / Save as PDF if the dialog does not open.</p>"
        f"<h1>{escape(title)}</h1><h2>{escape(society_name)}{(' — ' + escape(subtitle)) if subtitle else ''}</h2>"
        f"<div class='muted'>Generated {escape(date.today().isoformat())}</div>{meta}"
        + _table(headers, rows)
        + "<p class='muted'>After printing and obtaining signatures, scan the signed pages and upload the scan in EstateHub. "
          "The server computes and stores the SHA-256 of the scanned file as evidence.</p>"
        + f"<table class='sig'><tr>{sig_cells}</tr></table>"
        + "<script>window.addEventListener('load',function(){setTimeout(function(){window.print()},500)})</script></body></html>")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_") or "document"
    return f"{safe}.html", doc
