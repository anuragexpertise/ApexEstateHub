# app/services/pdf_text.py
"""
Fonts and text helpers for server-side PDFs (Latin, rupee sign and Hindi/Devanagari).

One font family does everything: Noto Sans Devanagari (SIL Open Font License 1.1) in <repo>/fonts. It carries the Latin letters,
digits and the rupee sign as well as Devanagari, so a line like "REG/आगरा/2019/44" is drawn in a single font. (Mixing two fonts
inside one word breaks reportlab's text shaping, so we do not.)

Devanagari letters join and reorder, so a plain glyph lookup prints them wrongly. reportlab 5 shapes them through HarfBuzz when
`uharfbuzz` is installed and the paragraph style has shaping=True; style() below sets that.

If the font files are missing the helpers fall back to Helvetica, print '?' for characters it lacks, and say so in the log.
"""
from __future__ import annotations

import logging
from pathlib import Path
from xml.sax.saxutils import escape

log = logging.getLogger(__name__)

FONT_DIR = Path(__file__).resolve().parents[2] / "fonts"
FAMILY, REGULAR, BOLD = "NotoDeva", "NotoSansDevanagari-Regular.ttf", "NotoSansDevanagari-Bold.ttf"
_state = {"done": False, "ok": False}


def register_fonts(font_dir: Path | None = None) -> bool:
    """Register the font family once. True when it is available."""
    if _state["done"] and font_dir is None:
        return _state["ok"]
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    base = Path(font_dir) if font_dir else FONT_DIR
    try:
        pdfmetrics.registerFont(TTFont(FAMILY, str(base / REGULAR)))
        pdfmetrics.registerFont(TTFont(FAMILY + "-Bold", str(base / BOLD)))
        pdfmetrics.registerFontFamily(FAMILY, normal=FAMILY, bold=FAMILY + "-Bold", italic=FAMILY, boldItalic=FAMILY + "-Bold")
        _state.update(done=True, ok=True)
    except Exception as exc:                                       # noqa: BLE001
        log.warning("PDF fonts not available in %s (%s); falling back to Helvetica without Hindi", base, exc)
        _state.update(done=True, ok=False)
    return _state["ok"]


def shaping_available() -> bool:
    try:
        import uharfbuzz  # noqa: F401
        return True
    except ImportError:
        log.warning("uharfbuzz is not installed: Hindi text will not be shaped correctly in PDFs")
        return False


def fonts_ok() -> bool:
    return register_fonts()


def base_font(bold: bool = False) -> str:
    if fonts_ok():
        return FAMILY + ("-Bold" if bold else "")
    return "Helvetica-Bold" if bold else "Helvetica"


def mono_font() -> str:
    return "Courier"                                               # hashes and certificate numbers are ASCII


def mark(text) -> str:
    """Text made safe for a reportlab Paragraph."""
    s = "" if text is None else str(text)
    if not fonts_ok():                                             # no fonts: keep the PDF valid and readable
        s = s.replace("\u20b9", "Rs. ").encode("latin-1", "replace").decode("latin-1")
    return escape(s)


def lines(text) -> list[str]:
    """A text block as Paragraph-ready lines: leading spaces kept as non-breaking spaces, empty lines kept."""
    res = []
    for ln in str(text or "").split("\n"):
        stripped = ln.lstrip(" ")
        res.append("&nbsp;" * (len(ln) - len(stripped)) + mark(stripped))
    return res


def style(name: str = "body", size: float = 10.5, leading: float | None = None, bold: bool = False, align: int = 0, **kw):
    from reportlab.lib.styles import ParagraphStyle
    return ParagraphStyle(name, fontName=base_font(bold), fontSize=size, leading=leading or size * 1.45, alignment=align,
                          shaping=shaping_available(), **kw)
