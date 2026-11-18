# app/services/agreement_pdf.py
"""
The Agreement with every sealed annex (A to E) drawn straight to PDF with reportlab: no HTML and no browser or HTML engine.

Same content as onboarding_service.agreement_print_html: the Agreement text, each annex in full (dicts as two-column tables,
lists of dicts as grids, stored images and image scans embedded), the four parties' signature block repeated at the foot of
every page, and either the paper counterpart signing page (before signing) or the recorded signatures and seal (after).

The renderer is pure: everything it needs comes in as arguments (build_inputs() fetches them), so it can be tested without a
database and gives identical bytes for identical input (invariant=1), which is what lets the stored SHA-256 mean something.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from app.services import pdf_text as T

PAGE_MARGIN_MM, FOOTER_MM = 15, 34
_IMG_EXT = {".webp", ".png", ".jpg", ".jpeg"}
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def _image_flow(data: bytes, max_w: float, max_h: float):
    """A picture scaled to fit, or None if the bytes are not a readable image."""
    from reportlab.platypus import Image
    try:
        from PIL import Image as PILImage
        im = PILImage.open(io.BytesIO(data))
        im.load()
        im = im.convert("RGBA") if im.mode in ("RGBA", "LA", "P") else im.convert("RGB")
        w, h = im.size
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        buf.seek(0)
        k = min(max_w / w, max_h / h, 1.0)
        return Image(buf, w * k, h * k)
    except Exception:                                              # noqa: BLE001
        return None


class _Ctx:
    def __init__(self, image_loader, evidence):
        self.load = image_loader or (lambda p: None)
        self.evidence = {str(k).lower(): v for k, v in (evidence or {}).items()}
        from reportlab.lib import colors
        self.colors = colors
        self.cell = T.style("cell", 9, 12.5)
        self.small = T.style("cellsm", 7.5, 10)
        self.key = T.style("key", 9, 12.5, bold=True)
        self.hash = T.style("hash", 7.5, 10, )
        self.hash.fontName = T.mono_font()
        self.hash.shaping = False


def _value(v, width: float, cx: _Ctx, small: bool = False) -> list:
    """Any JSON annex value as reportlab flowables that fit `width` points."""
    from reportlab.platypus import Paragraph, Table, TableStyle
    st = cx.small if small else cx.cell
    if v is None or v == "":
        return [Paragraph("&mdash;", st)]
    if isinstance(v, bool):
        return [Paragraph("Yes" if v else "No", st)]
    if isinstance(v, dict):
        if not v:
            return [Paragraph("&mdash;", st)]
        kw = width * 0.28
        rows = [[Paragraph(T.mark(str(k).replace("_", " ").capitalize()), cx.key), _value(x, width - kw - 12, cx, small)]
                for k, x in v.items()]
        t = Table(rows, colWidths=[kw, width - kw], splitInRow=1)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, cx.colors.HexColor("#666666")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("BACKGROUND", (0, 0), (0, -1), cx.colors.HexColor("#eeeeee"))]))
        return [t]
    if isinstance(v, list):
        if not v:
            return [Paragraph("&mdash;", st)]
        if all(isinstance(x, dict) for x in v):
            cols = list(dict.fromkeys(k for x in v for k in x))
            tiny = len(cols) > 6
            cw = width / max(len(cols), 1)
            hs = T.style("gh", 7.5 if tiny else 9, 10 if tiny else 12.5, bold=True)
            rows = [[Paragraph(T.mark(str(c).replace("_", " ").capitalize()), hs) for c in cols]]
            rows += [[_value(x.get(c), cw - 12, cx, small=tiny) for c in cols] for x in v]
            t = Table(rows, colWidths=[cw] * len(cols), repeatRows=1, splitInRow=1)
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, cx.colors.HexColor("#666666")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("BACKGROUND", (0, 0), (-1, 0), cx.colors.HexColor("#eeeeee")),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
            return [t]
        out = []
        for x in v:
            inner = _value(x, width - 12, cx, small)
            if len(inner) == 1 and isinstance(inner[0], Paragraph):
                out.append(Paragraph("&bull;&nbsp;" + inner[0].text, inner[0].style))
            else:
                out.extend(inner)
        return out
    txt = str(v)
    if Path(txt).suffix.lower() in _IMG_EXT:                       # a stored image path (e.g. a signature image)
        flow = None
        data = cx.load(txt)
        if data:
            flow = _image_flow(data, min(width, 160), 80)
        return [flow] if flow else [Paragraph(T.mark(txt) + " <i>(image file not found)</i>", st)]
    ev = cx.evidence.get(txt.lower()) if _HEX64.match(txt) else None
    if ev:                                                         # the SHA-256 of an attached scan
        out = [Paragraph(txt, cx.hash)]
        flow = _image_flow(ev["image"], min(width, 420), 330) if ev.get("image") else None
        if flow:
            out.append(flow)
        else:
            out.append(Paragraph(T.mark(ev.get("filename") or "scan") + " <i>(a PDF or unreadable scan: kept on file, "
                                 "identified by this SHA-256)</i>", st))
        return out
    if _HEX64.match(txt):
        return [Paragraph(txt, cx.hash)]
    return [Paragraph(T.mark(txt), st)]


def _footer_table(officers: list[dict], width: float, cx: _Ctx):
    from reportlab.platypus import Paragraph, Table, TableStyle
    lab = T.style("who", 7.5, 9.5, align=1)
    cells = []
    for o in officers:
        box = _image_flow(o["signature"], width / 4 - 14, 30) if o.get("signature") else None
        cells.append([box or Paragraph("&nbsp;", lab), Paragraph(T.mark(o["label"]) + "<br/>" + T.mark(o.get("name") or ""), lab)])
    cells.append([Paragraph("&nbsp;", lab), Paragraph("For the Operator<br/>authorised signatory", lab)])
    t = Table([[c[0] for c in cells], [c[1] for c in cells]], colWidths=[width / len(cells)] * len(cells), rowHeights=[34, None])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, cx.colors.HexColor("#666666")),
                           ("INNERGRID", (0, 0), (-1, -1), 0.5, cx.colors.HexColor("#666666")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    return t


def render_agreement_full_pdf(*, society_name: str, agreement_no: str, body_text: str, annexes: list[dict], officers: list[dict],
                              text_hash: str | None = None, signers: list[dict] | None = None, sealed_at=None,
                              key_id: str | None = None, image_loader=None, evidence: dict | None = None,
                              paper_page: bool = True) -> bytes:
    """annexes: [{code, title, hash, content}]; officers: [{label, name, signature(bytes|None)}];
    evidence: {sha256: {filename, image(bytes|None)}}; image_loader(path) -> bytes|None for stored image paths."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle

    T.register_fonts()
    cx = _Ctx(image_loader, evidence)
    W, H = A4
    m = PAGE_MARGIN_MM * mm
    inner_w = W - 2 * m
    foot = _footer_table(officers, inner_w, cx)
    h1, body = T.style("h1", 15, 19, bold=True), T.style("body", 10.5, 15.5)
    mono = T.style("mono", 7.5, 10)
    mono.fontName, mono.shaping = T.mono_font(), False
    tag = f"Agreement {agreement_no}"

    def on_page(canvas, doc):
        canvas.saveState()
        _w, fh = foot.wrapOn(canvas, inner_w, H)
        foot.drawOn(canvas, m, 8 * mm)
        canvas.setFont(T.mono_font(), 7)
        canvas.drawString(m, 8 * mm + fh + 3, tag + (f"  |  text SHA-256 {text_hash[:16]}..." if text_hash else ""))
        canvas.drawRightString(W - m, 8 * mm + fh + 3, f"Page {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=m, rightMargin=m, topMargin=m, bottomMargin=FOOTER_MM * mm + 6 * mm,
                          title=f"{tag} - {society_name}", author=society_name or "", invariant=1)
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(m, FOOTER_MM * mm + 6 * mm, inner_w, H - m - FOOTER_MM * mm - 6 * mm - 4,
                                                             leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)],
                                       onPage=on_page)])
    story = [Paragraph("Agreement", h1), Spacer(1, 4)]
    story += [Paragraph(ln or "&nbsp;", body) for ln in T.lines(body_text)]
    for a in annexes:
        story += [PageBreak(), Paragraph(T.mark(a["title"]), h1), Paragraph("SHA-256 " + str(a["hash"]), mono), Spacer(1, 4)]
        story += _value(a["content"], inner_w, cx)
    story.append(PageBreak())
    if signers:
        story += [Paragraph("Signatures recorded in EstateHub", h1), Spacer(1, 6)]
        rows = [[Paragraph("<b>Office</b>", body), Paragraph("<b>Signed at</b>", body)]] + \
               [[Paragraph(T.mark(str(s.get("office", "")).replace("_", " ").title()), body), Paragraph(T.mark(s.get("at", "")), body)]
                for s in signers]
        t = Table(rows, colWidths=[inner_w * 0.4, inner_w * 0.6])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, cx.colors.grey), ("BACKGROUND", (0, 0), (-1, 0), cx.colors.HexColor("#eeeeee"))]))
        story += [t, Spacer(1, 8)]
        if text_hash:
            story.append(Paragraph("Text SHA-256 " + text_hash, mono))
        if sealed_at:
            story.append(Paragraph(f"Sealed {sealed_at}" + (f" | key {key_id}" if key_id else ""), mono))
    if paper_page:
        story += [Paragraph("Paper counterpart: signatures", h1), Spacer(1, 4),
                  Paragraph("Each signer signs and dates this page by hand. Scan it and upload the scan in EstateHub, then confirm "
                            "with your login password.", body), Spacer(1, 8)]
        rows = [[Paragraph("<b>Signer</b>", body), Paragraph("<b>Signature</b>", body), Paragraph("<b>Date</b>", body)]]
        rows += [[Paragraph(T.mark(o["label"]) + "<br/>" + T.mark(o.get("name") or ""), body), "", ""] for o in officers]
        rows.append([Paragraph("For the Operator<br/>authorised signatory", body), "", ""])
        t = Table(rows, colWidths=[inner_w * 0.34, inner_w * 0.46, inner_w * 0.2], rowHeights=[None] + [44] * (len(rows) - 1))
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, cx.colors.HexColor("#666666")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(t)
    doc.build(story)
    return buf.getvalue()


# ── fetching the inputs from the database (the only part that needs the app) ───────────────────────────────────
ANNEX_TITLES = {"A": "Annex A: legal regime and bye-laws", "B": "Annex B: review of the setup",
                "C": "Annex C: opening financial position", "D": "Annex D: data-protection and custody schedule",
                "E": "Annex E: source-documents index"}


def build_inputs(society_id: int) -> dict:
    """Everything the renderer needs for this society, using onboarding_service's own readers so the PDF and the printable HTML
    show the same facts. Raises onboarding_service.OnboardingError until the Agreement is issued and annexes A to E are sealed."""
    import base64
    import json

    from app.services import onboarding_service as ob

    ag = ob._row("SELECT agreement_no, body_text FROM society_agreements WHERE society_id=%s", (society_id,))
    sealed = {r["annex_code"]: r for r in ob._rows(
        "SELECT annex_code, content, content_hash FROM onboarding_annexes WHERE society_id=%s AND status='sealed'", (society_id,))}
    if not ag or not ag.get("body_text") or set(sealed) != set(ob.ANNEX_CODES):
        raise ob.OnboardingError("The Agreement is issued once annexes A, B, C, D and E are sealed.")
    soc = ob._row("SELECT name FROM societies WHERE id=%s", (society_id,)) or {}

    def load(rel: str | None) -> bytes | None:                    # same folder guard as the printable HTML
        uri = ob._image_data_uri(ob.signature_path(society_id, rel) if rel and "/" not in rel else rel)
        return base64.b64decode(uri.split(",", 1)[1]) if uri else None

    officers_db = ob.seated_officers(society_id)
    officers = [{"label": ob.OFFICE_LABEL[o], "name": (officers_db.get(o) or {}).get("holder_name") or "",
                 "signature": load((officers_db.get(o) or {}).get("signature_image"))} for o in ob.CORE_OFFICES]
    try:
        ev_rows = ob._rows("SELECT sha256, stored_name, filename FROM onboarding_evidence WHERE society_id=%s", (society_id,)) or []
    except Exception:                                              # noqa: BLE001 - scans are an extra
        ev_rows = []
    evidence = {}
    for r in ev_rows:
        is_img = Path(r["stored_name"]).suffix.lower() in _IMG_EXT
        img = None
        if is_img:
            uri = ob._image_data_uri(f"{society_id}/evidence/{r['stored_name']}")
            img = base64.b64decode(uri.split(",", 1)[1]) if uri else None
        evidence[str(r["sha256"]).lower()] = {"filename": r["filename"], "image": img}
    annexes = [{"code": c, "title": ANNEX_TITLES[c], "hash": sealed[c]["content_hash"],
                "content": sealed[c]["content"] if isinstance(sealed[c]["content"], (dict, list)) else json.loads(sealed[c]["content"])}
               for c in ob.ANNEX_CODES]
    return {"society_name": soc.get("name") or "", "agreement_no": ag.get("agreement_no") or "", "body_text": ag["body_text"],
            "annexes": annexes, "officers": officers, "image_loader": load, "evidence": evidence}
