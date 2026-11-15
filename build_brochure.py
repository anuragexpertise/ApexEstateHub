"""Build the EstateHub marketing brochure PDF.

Usage:
    pip install reportlab
    python build_brochure.py

Writes EstateHub_Marketing_Brochure_Print_Ready.pdf next to this script.

Design notes
  * No overlapping text: every card, tile, banner and flow step measures its own text
    with ReportLab Paragraphs and sizes itself to fit, so nothing is clipped or drawn
    over anything else. Cards in the same row are stretched to equal height.
  * Icons come from Font Awesome Free (solid). The font file fa-solid-900.ttf is looked
    up in ./fonts, ./static/fonts, ./static/webfonts; if it is not found it is downloaded
    once from the Font Awesome GitHub repository into ./fonts. Without it the brochure
    still builds, just without icons. (Font Awesome Free: fonts under SIL OFL 1.1,
    icons under CC BY 4.0 - https://fontawesome.com/license/free)
  * The cover's database counts (tables, SQL functions, triggers) are read from the
    "Schema source of truth" line near the top of README.md.
  * Set ESTATEHUB_DEMO_URL to print a real, scannable QR code for the demo link;
    otherwise a labelled placeholder box is drawn.
  * All other brochure text lives in this file and is edited by hand.
"""
import os
import re
import sys
import urllib.request
from pathlib import Path

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Flowable, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parent
out = ROOT / "EstateHub_Marketing_Brochure_Print_Ready.pdf"
README = ROOT / "README.md"
DEMO_URL = os.environ.get("ESTATEHUB_DEMO_URL", "").strip()

# ----------------------------------------------------------------------------------
# Database counts from README.md
# ----------------------------------------------------------------------------------
# Used only if README.md is missing or its "Schema source of truth" line cannot be parsed.
FALLBACK_STATS = {"tables": 158, "views": 9, "functions": 313, "triggers": 89}


def load_stats():
    """Read table / view / fn_* function / trigger counts from README.md."""
    stats = dict(FALLBACK_STATS)
    try:
        text = README.read_text(encoding="utf-8")
    except OSError:
        print(f"WARNING: {README.name} not found; using fallback counts {stats}", file=sys.stderr)
        return stats
    m = re.search(r"Schema source of truth[^\n]*?(\d+)\s+tables(?:\s*\(\+\s*(\d+)\s+views\))?"
                  r",\s*(\d+)\s+`?fn_\*`?\s+functions,\s*(\d+)\s+triggers", text)
    if not m:
        print(f"WARNING: could not parse the schema counts in {README.name}; "
              f"using fallback counts {stats}", file=sys.stderr)
        return stats
    stats["tables"] = int(m.group(1))
    stats["views"] = int(m.group(2)) if m.group(2) else stats["views"]
    stats["functions"] = int(m.group(3))
    stats["triggers"] = int(m.group(4))
    return stats


STATS = load_stats()

# ----------------------------------------------------------------------------------
# Font Awesome (solid) - registered as the "FA" font
# ----------------------------------------------------------------------------------
FA_VERSION = "6.5.2"
FA_URL = (f"https://raw.githubusercontent.com/FortAwesome/Font-Awesome/{FA_VERSION}"
          "/webfonts/fa-solid-900.ttf")
FA_CANDIDATES = [ROOT / "fonts" / "fa-solid-900.ttf",
                 ROOT / "static" / "fonts" / "fa-solid-900.ttf",
                 ROOT / "static" / "webfonts" / "fa-solid-900.ttf",
                 ROOT / "static" / "fontawesome" / "webfonts" / "fa-solid-900.ttf"]

# Codepoints checked against Font Awesome Free 6.5.2 (css/all.css and the font's cmap).
ICONS = {
    "crown": 0xf521, "user-shield": 0xf505, "house": 0xf015, "screwdriver-wrench": 0xf7d9,
    "shield-halved": 0xf3ed, "calculator": 0xf1ec, "clipboard-check": 0xf46c, "users": 0xf0c0,
    "magnifying-glass": 0xf002, "scale-balanced": 0xf24e, "database": 0xf1c0, "gears": 0xf085,
    "bolt": 0xf0e7, "building": 0xf1ad, "indian-rupee-sign": 0xe1bc, "check": 0xf00c,
    "xmark": 0xf00d, "arrow-right": 0xf061, "ban": 0xf05e, "lock": 0xf023,
    "key": 0xf084, "link": 0xf0c1, "qrcode": 0xf029, "ticket": 0xf145,
    "check-to-slot": 0xf772, "file-signature": 0xf573, "file-lines": 0xf15c, "comments": 0xf086,
    "bullhorn": 0xf0a1, "receipt": 0xf543, "bell": 0xf0f3, "chart-line": 0xf201,
    "chart-pie": 0xf200, "table-columns": 0xf0db, "calendar-check": 0xf274, "rocket": 0xf135,
    "seedling": 0xf4d8, "building-columns": 0xf19c, "handshake": 0xf2b5, "circle-question": 0xf059,
    "mobile-screen": 0xf3cf, "camera": 0xf030, "location-dot": 0xf3c5, "person-walking": 0xf554,
    "user-check": 0xf4fc, "gavel": 0xf0e3, "book": 0xf02d, "landmark": 0xf66f,
    "id-card": 0xf2c2, "envelope": 0xf0e0, "sliders": 0xf1de, "eye": 0xf06e,
    "wallet": 0xf555, "coins": 0xf51e, "stamp": 0xf5bf, "fingerprint": 0xf577,
    "clock": 0xf017, "list-check": 0xf0ae, "circle-check": 0xf058, "hand-holding-dollar": 0xf4c0,
    "wand-magic-sparkles": 0xe2ca, "user-tie": 0xf508, "arrows-rotate": 0xf021, "clipboard-list": 0xf46d,
    "thumbs-up": 0xf164, "print": 0xf02f, "wrench": 0xf0ad, "file-invoice": 0xf570,
    "layer-group": 0xf5fd, "bars-progress": 0xf828, "cash-register": 0xf788, "arrow-down": 0xf063,
}


def _register_fa():
    paths = [p for p in FA_CANDIDATES if p.is_file()]
    if not paths:
        target = FA_CANDIDATES[0]
        try:
            print(f"Downloading Font Awesome {FA_VERSION} icon font to {target} ...")
            target.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(FA_URL, timeout=30) as r:
                data = r.read()
            if len(data) < 50_000:
                raise OSError("downloaded file is too small to be the font")
            target.write_bytes(data)
            paths = [target]
        except Exception as exc:  # network blocked, offline, etc.
            print(f"WARNING: could not get the Font Awesome font ({exc}). Building without icons.\n"
                  f"         Put fa-solid-900.ttf in {target.parent} to enable them.", file=sys.stderr)
            return False
    try:
        pdfmetrics.registerFont(TTFont("FA", str(paths[0])))
        return True
    except Exception as exc:
        print(f"WARNING: Font Awesome font could not be loaded ({exc}). Building without icons.",
              file=sys.stderr)
        return False


HAVE_FA = _register_fa()


def ic(name, color=None, size=None):
    """Inline icon markup for use inside Paragraph text."""
    if not HAVE_FA:
        return ""
    attrs = f' color="{color.hexval().replace("0x", "#")}"' if color is not None else ""
    if size:
        attrs += f' size="{size}"'
    return f'<font name="FA"{attrs}>{chr(ICONS[name])}</font>'


def fx(text):
    """Swap characters the standard PDF fonts cannot draw (rupee sign, arrow)."""
    if HAVE_FA:
        text = text.replace("₹", ic("indian-rupee-sign")).replace("→", ic("arrow-right"))
    else:
        text = text.replace("₹", "Rs.").replace("→", "->")
    return text


def draw_icon(c, name, cx, cy, size, color):
    if not HAVE_FA:
        return
    c.setFillColor(color)
    c.setFont("FA", size)
    c.drawCentredString(cx, cy - size * 0.375, chr(ICONS[name]))


def draw_badge(c, cx, cy, d, icon, fill, glyph=None):
    c.setFillColor(fill)
    c.circle(cx, cy, d / 2, fill=1, stroke=0)
    if icon:
        draw_icon(c, icon, cx, cy, d * 0.47, glyph or colors.white)


def draw_arrow(c, cx, cy, color, size=8):
    """Right-pointing arrow centred on (cx, cy)."""
    if HAVE_FA:
        draw_icon(c, "arrow-right", cx, cy, size, color)
    else:
        c.setFillColor(color)
        p = c.beginPath()
        p.moveTo(cx - size * 0.3, cy + size * 0.35)
        p.lineTo(cx + size * 0.4, cy)
        p.lineTo(cx - size * 0.3, cy - size * 0.35)
        p.close()
        c.drawPath(p, fill=1, stroke=0)


def fit_font(text, font, size, max_w, min_size=5.5):
    while size > min_size and stringWidth(text, font, size) > max_w:
        size -= 0.25
    return size


# ----------------------------------------------------------------------------------
# Palette, page geometry, styles
# ----------------------------------------------------------------------------------
W, H = A4
NAVY   = HexColor("#0F2B46")
BLUE   = HexColor("#1D70F7")
TEAL   = HexColor("#00A6A6")
GREEN  = HexColor("#2EAF62")
GOLD   = HexColor("#F4B942")
CORAL  = HexColor("#F26457")
PURPLE = HexColor("#6A1B9A")
INDIGO = HexColor("#3949AB")
INK    = HexColor("#203040")
MUTED  = HexColor("#64748B")
LIGHT  = HexColor("#F4F8FC")
PALE   = HexColor("#EAF2FF")
CARDL  = HexColor("#D8E3EE")
WHITE  = colors.white
GOLD_TXT = HexColor("#A86A00")  # darker gold, used where gold is text on a light background

USABLE = 178 * mm  # 210 mm page - 2 x 16 mm margins


def tint(color, f):
    """Blend a colour towards white; f=0 keeps it, f=1 gives white."""
    return colors.Color(color.red + (1 - color.red) * f,
                        color.green + (1 - color.green) * f,
                        color.blue + (1 - color.blue) * f)


def mkst(name, font="Helvetica", size=8, leading=None, color=INK, align=TA_LEFT, **kw):
    return ParagraphStyle(name=name, fontName=font, fontSize=size,
                          leading=leading or round(size * 1.3, 1), textColor=color,
                          alignment=align, **kw)


ST = {
    "CoverT":   mkst("CoverT", "Helvetica-Bold", 34, 38, NAVY, spaceAfter=6),
    "CoverSub": mkst("CoverSub", "Helvetica", 15, 20, BLUE, spaceAfter=10),
    "H1x":      mkst("H1x", "Helvetica-Bold", 18, 22, NAVY),
    "H2x":      mkst("H2x", "Helvetica-Bold", 12, 15, BLUE, spaceBefore=4, spaceAfter=3),
    "B":        mkst("B", "Helvetica", 9, 12.8, INK, spaceAfter=4),
    "S":        mkst("S", "Helvetica", 7.4, 10, MUTED, spaceAfter=2),
    "Q":        mkst("Q", "Helvetica-Oblique", 12.5, 17, NAVY, TA_CENTER),
    "TH":       mkst("TH", "Helvetica-Bold", 7.8, 10, WHITE),
    "TB":       mkst("TB", "Helvetica", 8, 10.6, INK),
    "TBC":      mkst("TBC", "Helvetica", 8, 10.6, INK, TA_CENTER),
    "CardT":    mkst("CardT", "Helvetica-Bold", 8.6, 10.8, NAVY),
    "CardB":    mkst("CardB", "Helvetica", 7.7, 10.3, INK),
    "TileL":    mkst("TileL", "Helvetica", 7, 9, MUTED, TA_CENTER),
    "BannerT":  mkst("BannerT", "Helvetica-Bold", 10.5, 13, WHITE),
    "BannerS":  mkst("BannerS", "Helvetica", 7.2, 9.4, WHITE),
    "StepT":    mkst("StepT", "Helvetica", 7.4, 9.6, INK),
    "StepS":    mkst("StepS", "Helvetica-Oblique", 6.6, 8.6, MUTED),
    "TlB":      mkst("TlB", "Helvetica", 7.8, 10.4, INK),
    "SegV":     mkst("SegV", "Helvetica-Bold", 7.6, 9.4, WHITE, TA_CENTER),
    "SegN":     mkst("SegN", "Helvetica", 6.8, 8.6, INK, TA_CENTER),
}


def P(s, st="B"):
    return Paragraph(fx(s), ST[st])


TS_ZERO = TableStyle([
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
])

# ----------------------------------------------------------------------------------
# Self-sizing building blocks
# ----------------------------------------------------------------------------------


class Box(Flowable):
    """Base for flowables that measure themselves; `forced_h` stretches a row to equal height."""
    def __init__(self, w=None):
        Flowable.__init__(self)
        self.w = w
        self.forced_h = None

    def natural(self, w):  # returns natural height for width w (subclasses build layout here)
        raise NotImplementedError

    def wrap(self, aw, ah):
        w = self.w or aw
        nat = self.natural(w)
        self.width = w
        self.height = max(nat, self.forced_h or 0)
        return self.width, self.height


class Card(Box):
    """Icon + title + body, sized to its text."""
    BAR = 2.0 * mm
    PAD = 3.4 * mm
    D = 8.4 * mm

    def __init__(self, title, body, accent=BLUE, icon=None, w=None):
        Box.__init__(self, w)
        self.title, self.body, self.accent, self.icon = fx(title), fx(body), accent, icon

    def natural(self, w):
        pad = self.PAD
        d = self.D if (self.icon and HAVE_FA) else 0
        self.tx = pad + (d + 2.4 * mm if d else 0)
        self.d = d
        self.tp = Paragraph(self.title, ST["CardT"])
        _, self.th = self.tp.wrap(w - self.tx - pad, 10 ** 4)
        self.bp = Paragraph(self.body, ST["CardB"])
        _, self.bh = self.bp.wrap(w - 2 * pad, 10 ** 4)
        self.hh = max(d, self.th)
        return self.BAR + pad + self.hh + 2.2 * mm + self.bh + pad

    def draw(self):
        c, w, h, pad = self.canv, self.width, self.height, self.PAD
        c.saveState()
        path = c.beginPath()
        path.roundRect(0, 0, w, h, 3 * mm)
        c.clipPath(path, stroke=0, fill=0)
        c.setFillColor(WHITE)
        c.rect(0, 0, w, h, fill=1, stroke=0)
        c.setFillColor(self.accent)
        c.rect(0, h - self.BAR, w, self.BAR, fill=1, stroke=0)
        c.restoreState()
        c.setStrokeColor(CARDL)
        c.setLineWidth(0.6)
        c.roundRect(0, 0, w, h, 3 * mm, fill=0, stroke=1)
        top = h - self.BAR - pad
        if self.d:
            draw_badge(c, pad + self.d / 2, top - self.hh / 2, self.d, self.icon, self.accent)
        self.tp.drawOn(c, self.tx, top - self.hh / 2 - self.th / 2)
        self.bp.drawOn(c, pad, top - self.hh - 2.2 * mm - self.bh)


class Tile(Box):
    """Big number with an icon above and a label below."""
    PAD = 3 * mm
    D = 9 * mm

    def __init__(self, num, label, accent, icon, w=None):
        Box.__init__(self, w)
        self.num, self.label, self.accent, self.icon = fx(num), fx(label), accent, icon

    def natural(self, w):
        pad = self.PAD
        self.d = self.D if HAVE_FA else 0
        avail = w - 2 * pad
        for fs in (18, 16, 14, 12.5, 11, 10, 9):
            st = mkst("tile%s" % fs, "Helvetica-Bold", fs, fs * 1.15, NAVY, TA_CENTER)
            self.np = Paragraph(self.num, st)
            _, self.nh = self.np.wrap(avail, 10 ** 4)
            if self.nh <= fs * 1.2:
                break
        self.lp = Paragraph(self.label, ST["TileL"])
        _, self.lh = self.lp.wrap(avail, 10 ** 4)
        return pad + (self.d + 2 * mm if self.d else 0) + self.nh + 1.2 * mm + self.lh + pad

    def draw(self):
        c, w, h, pad = self.canv, self.width, self.height, self.PAD
        c.setFillColor(PALE)
        c.roundRect(0, 0, w, h, 3 * mm, fill=1, stroke=0)
        c.setFillColor(self.accent)
        c.rect(w * 0.18, 0, w * 0.64, 1.1 * mm, fill=1, stroke=0)
        y = h - pad
        if self.d:
            draw_badge(c, w / 2, y - self.d / 2, self.d, self.icon, self.accent)
            y -= self.d + 2 * mm
        self.np.drawOn(c, pad, y - self.nh)
        y -= self.nh + 1.2 * mm
        self.lp.drawOn(c, pad, y - self.lh)


def grid(items, cols, cls=Card, gap=4 * mm, row_gap=3.6 * mm):
    """Rows of equal-height cards. items: (title, body, accent, icon) or (num, label, accent, icon)."""
    colw = (USABLE - gap * (cols - 1)) / cols
    flow = []
    for i in range(0, len(items), cols):
        cards = [cls(*it, w=colw) for it in items[i:i + cols]]
        hmax = max(cd.natural(colw) for cd in cards)
        for cd in cards:
            cd.forced_h = hmax
        cells, widths = [], []
        for j in range(cols):
            if j:
                cells.append("")
                widths.append(gap)
            cells.append(cards[j] if j < len(cards) else "")
            widths.append(colw)
        flow += [Table([cells], colWidths=widths, style=TS_ZERO), Spacer(1, row_gap)]
    return flow


class Badge(Flowable):
    def __init__(self, d, icon, color):
        Flowable.__init__(self)
        self.d, self.icon, self.color = d, icon, color

    def wrap(self, aw, ah):
        return self.d, self.d

    def draw(self):
        draw_badge(self.canv, self.d / 2, self.d / 2, self.d, self.icon, self.color)


def sect(num, title, sub=None, icon="circle-check", accent=BLUE):
    """Section header: icon badge, numbered title, optional subtitle, accent rule."""
    bd = 11 * mm
    rows = [[Badge(bd, icon, accent) if HAVE_FA else "", P(f"{num}  |  {title}", "H1x")]]
    style = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
             ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
             ("LINEBELOW", (0, -1), (-1, -1), 2.2, accent)]
    colw = [bd + 3 * mm, USABLE - bd - 3 * mm] if HAVE_FA else [0.01, USABLE - 0.01]
    if sub:
        rows.append(["", P(sub, "S")])
        style += [("TOPPADDING", (0, 1), (-1, 1), 1), ("BOTTOMPADDING", (0, 1), (-1, 1), 3),
                  ("BOTTOMPADDING", (0, 0), (-1, 0), 0)]
    return [Table(rows, colWidths=colw, style=TableStyle(style)), Spacer(1, 4 * mm)]


def quote(text, who=None, accent=BLUE):
    cell = [Paragraph(fx(text), ST["Q"])]
    if who:
        cell.append(Paragraph(fx(who), ST["S"]))
    return Table([[cell]], colWidths=[USABLE], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("LINEBEFORE", (0, 0), (0, -1), 3, accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))


class Banner(Box):
    """Full-width coloured title bar with an icon, used above each flow diagram."""
    PAD = 2.6 * mm
    D = 8 * mm

    def __init__(self, title, sub, accent, icon, w=USABLE):
        Box.__init__(self, w)
        self.title, self.sub, self.accent, self.icon = fx(title), fx(sub or ""), accent, icon

    def natural(self, w):
        self.d = self.D if HAVE_FA else 0
        self.tx = self.PAD + (self.d + 3 * mm if self.d else 0)
        self.tp = Paragraph(self.title, ST["BannerT"])
        _, self.th = self.tp.wrap(w - self.tx - self.PAD, 10 ** 4)
        self.sp = Paragraph(self.sub, ST["BannerS"]) if self.sub else None
        self.sh = self.sp.wrap(w - self.tx - self.PAD, 10 ** 4)[1] if self.sp else 0
        return max(self.d, self.th + self.sh) + 2 * self.PAD

    def draw(self):
        c, w, h = self.canv, self.width, self.height
        c.setFillColor(self.accent)
        c.roundRect(0, 0, w, h, 2.6 * mm, fill=1, stroke=0)
        if self.d:
            c.setFillColor(WHITE)
            c.circle(self.PAD + self.d / 2, h / 2, self.d / 2, fill=1, stroke=0)
            draw_icon(c, self.icon, self.PAD + self.d / 2, h / 2, self.d * 0.47, self.accent)
        block = self.th + self.sh
        y = h / 2 + block / 2
        self.tp.drawOn(c, self.tx, y - self.th)
        if self.sp:
            self.sp.drawOn(c, self.tx, y - block)


class StepFlow(Box):
    """Numbered process boxes joined by arrows; wraps onto extra rows with an elbow connector.

    steps: (icon, tag, text, sub_text_or_None)
    """
    PAD = 2.8 * mm
    D = 7 * mm

    def __init__(self, steps, accent, per_row=4, gap=8 * mm, row_gap=6 * mm, w=USABLE):
        Box.__init__(self, w)
        self.steps, self.accent, self.per_row = steps, accent, per_row
        self.gap, self.row_gap = gap, row_gap

    def natural(self, w):
        pr, gap, pad = self.per_row, self.gap, self.PAD
        self.bw = (w - (pr - 1) * gap) / pr
        inner = self.bw - 2 * pad
        self.d = self.D if HAVE_FA else 0
        self.items = []
        bh = 0
        for icon, tag, text, sub in self.steps:
            tp = Paragraph(fx(text), ST["StepT"])
            th = tp.wrap(inner, 10 ** 4)[1]
            sp = Paragraph(fx(sub), ST["StepS"]) if sub else None
            sh = sp.wrap(inner, 10 ** 4)[1] if sp else 0
            self.items.append((icon, tag, tp, th, sp, sh))
            bh = max(bh, max(self.d, 4 * mm) + 2 * mm + th + (1.2 * mm + sh if sp else 0))
        self.bh = bh + 2 * pad
        self.nrows = -(-len(self.steps) // pr)
        return self.nrows * self.bh + (self.nrows - 1) * self.row_gap

    def draw(self):
        c, pad, bw, bh = self.canv, self.PAD, self.bw, self.bh
        n, pr = len(self.items), self.per_row
        c.setLineWidth(1.1)
        for i, (icon, tag, tp, th, sp, sh) in enumerate(self.items):
            row, col = divmod(i, pr)
            x = col * (bw + self.gap)
            ytop = self.height - row * (bh + self.row_gap)
            ybot = ytop - bh
            c.setFillColor(WHITE)
            c.setStrokeColor(tint(self.accent, 0.35))
            c.roundRect(x, ybot, bw, bh, 2.4 * mm, fill=1, stroke=1)
            hdr_cy = ytop - pad - max(self.d, 4 * mm) / 2
            if self.d:
                draw_badge(c, x + pad + self.d / 2, hdr_cy, self.d, icon, self.accent)
            tag_x = x + pad + (self.d + 1.8 * mm if self.d else 0)
            c.setFillColor(GOLD_TXT if self.accent == GOLD else self.accent)
            c.setFont("Helvetica-Bold", fit_font(tag, "Helvetica-Bold", 6.6, x + bw - pad - tag_x))
            c.drawString(tag_x, hdr_cy - 2.2, tag)
            y = ytop - pad - max(self.d, 4 * mm) - 2 * mm
            tp.drawOn(c, x + pad, y - th)
            if sp:
                sp.drawOn(c, x + pad, y - th - 1.2 * mm - sh)
            # arrow to the next box on the same row
            if col < pr - 1 and i < n - 1:
                draw_arrow(c, x + bw + self.gap / 2, ybot + bh / 2, self.accent, 8)
            # elbow connector to the first box of the next row
            if col == pr - 1 and i < n - 1:
                c.setStrokeColor(tint(self.accent, 0.25))
                ymid = ybot - self.row_gap / 2
                xs, xe = x + bw / 2, bw / 2
                p = c.beginPath()
                p.moveTo(xs, ybot)
                p.lineTo(xs, ymid)
                p.lineTo(xe, ymid)
                p.lineTo(xe, ybot - self.row_gap + 0.8 * mm)
                c.drawPath(p, fill=0, stroke=1)
                c.setFillColor(tint(self.accent, 0.25))
                a = c.beginPath()
                yb = ybot - self.row_gap
                a.moveTo(xe - 1.3 * mm, yb + 1.8 * mm)
                a.lineTo(xe + 1.3 * mm, yb + 1.8 * mm)
                a.lineTo(xe, yb + 0.2 * mm)
                a.close()
                c.drawPath(a, fill=1, stroke=0)


class TimelineRow(Box):
    """One row of a vertical timeline: time chip, icon on a continuous line, text panel."""
    CHIP_W = 16 * mm
    D = 8 * mm
    PADX = 3 * mm
    GAP = 2.4 * mm

    def __init__(self, tag, icon, title, body, accent, first=False, last=False, w=USABLE):
        Box.__init__(self, w)
        self.tag, self.icon, self.accent = tag, icon, accent
        self.text = f"<b>{title}</b><br/>{body}"
        self.first, self.last = first, last

    def natural(self, w):
        self.cx = self.CHIP_W + 7 * mm
        self.tx0 = self.cx + self.D / 2 + 3 * mm
        self.tp = Paragraph(fx(self.text), ST["TlB"])
        _, self.th = self.tp.wrap(w - self.tx0 - 2 * self.PADX - 1.2 * mm, 10 ** 4)
        self.panel_h = max(self.th + 2 * 2.8 * mm, 14 * mm)
        return self.panel_h + self.GAP

    def draw(self):
        c, w, h = self.canv, self.width, self.height
        cy = h - 7 * mm
        c.setStrokeColor(tint(self.accent, 0.45))
        c.setLineWidth(1.8)
        y0 = cy if self.first else h
        y1 = cy if self.last else 0
        c.line(self.cx, y0, self.cx, y1)
        c.setFillColor(LIGHT)
        c.setStrokeColor(CARDL)
        c.setLineWidth(0.5)
        c.roundRect(self.tx0, self.GAP, w - self.tx0, self.panel_h, 2.4 * mm, fill=1, stroke=1)
        c.setFillColor(self.accent)
        c.rect(self.tx0, self.GAP + 2 * mm, 1.2 * mm, self.panel_h - 4 * mm, fill=1, stroke=0)
        draw_badge(c, self.cx, cy, self.D, self.icon, self.accent)
        c.setFillColor(PALE)
        c.roundRect(0, cy - 3 * mm, self.CHIP_W, 6 * mm, 1.8 * mm, fill=1, stroke=0)
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 7.6)
        c.drawCentredString(self.CHIP_W / 2, cy - 1, self.tag)
        self.tp.drawOn(c, self.tx0 + self.PADX + 1.2 * mm, self.GAP + (self.panel_h - self.th) / 2)


def timeline(rows, accents):
    n = len(rows)
    return [TimelineRow(t, ico, h, b, accents[i % len(accents)], first=(i == 0), last=(i == n - 1))
            for i, (t, ico, h, b) in enumerate(rows)]


# ----------------------------------------------------------------------------------
# Infographics
# ----------------------------------------------------------------------------------
class Hero(Flowable):
    """Cover graphic: headline band, four database/portal stat chips, hub-and-spoke of the 10 roles."""
    def __init__(self):
        Flowable.__init__(self)
        self.width, self.height = USABLE, 104 * mm

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c, w, h = self.canv, self.width, self.height
        c.setFillColor(PALE)
        c.roundRect(0, 0, w, h, 5 * mm, fill=1, stroke=0)
        # headline band (rounded top corners only)
        bh = 15 * mm
        c.setFillColor(NAVY)
        c.roundRect(0, h - bh, w, bh, 5 * mm, fill=1, stroke=0)
        c.rect(0, h - bh, w, bh / 2, fill=1, stroke=0)
        t1 = "MULTI-TENANT   •   ROLE-AWARE   •   REAL-TIME   •   ZERO-RELOAD"
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", fit_font(t1, "Helvetica-Bold", 9, w - 12 * mm))
        c.drawCentredString(w / 2, h - 6.2 * mm, t1)
        t2 = "Python 3.12   •   Dash 2.14 + Flask 2.2   •   PostgreSQL 16   •   gunicorn"
        c.setFillColor(HexColor("#9FB3C8"))
        c.setFont("Helvetica", fit_font(t2, "Helvetica", 7.2, w - 12 * mm))
        c.drawCentredString(w / 2, h - 11.4 * mm, t2)

        # stat chips
        chips = [("10", "Role-Scoped Portals", TEAL, "users"),
                 (str(STATS["tables"]), "Database Tables", BLUE, "database"),
                 (str(STATS["functions"]), "SQL Functions", GREEN, "gears"),
                 (str(STATS["triggers"]), "Database Triggers", GOLD, "bolt")]
        m, gap, ch = 6 * mm, 3 * mm, 15 * mm
        cw = (w - 2 * m - 3 * gap) / 4
        y = h - bh - 4 * mm - ch
        for i, (num, lab, col, icon) in enumerate(chips):
            x = m + i * (cw + gap)
            c.setFillColor(WHITE)
            c.roundRect(x, y, cw, ch, 3 * mm, fill=1, stroke=0)
            draw_badge(c, x + 3 * mm + 4.5 * mm, y + ch / 2, 9 * mm, icon, col)
            tx = x + 3 * mm + 9 * mm + 2.5 * mm
            avail = x + cw - 2 * mm - tx
            c.setFillColor(NAVY)
            c.setFont("Helvetica-Bold", fit_font(num, "Helvetica-Bold", 14, avail))
            c.drawString(tx, y + 8.4 * mm, num)
            c.setFillColor(MUTED)
            c.setFont("Helvetica", fit_font(lab, "Helvetica", 6.6, avail))
            c.drawString(tx, y + 3.6 * mm, lab)

        # hub and spokes
        roles = [("MASTER", PURPLE, "crown"), ("ADMIN", BLUE, "user-shield"), ("OWNER", TEAL, "house"),
                 ("VENDOR", GOLD, "screwdriver-wrench"), ("SECURITY", CORAL, "shield-halved"),
                 ("ACCOUNTANT", INDIGO, "calculator"), ("SUPERVISOR", GREEN, "clipboard-check"),
                 ("STAFF", TEAL, "users"), ("AUDITOR", BLUE, "magnifying-glass"),
                 ("ADVISER", PURPLE, "scale-balanced")]
        region_top = y - 4 * mm
        label_y1 = region_top - 3.2 * mm
        cy1 = label_y1 - 2 * mm - 5 * mm
        label_y2 = 3.4 * mm
        cy2 = label_y2 + 3 * mm + 2 * mm + 5 * mm
        hub_cy = (cy1 + cy2) / 2
        colw = w / 5
        pos = []
        for i, (lab, col, icon) in enumerate(roles):
            row, cidx = divmod(i, 5)
            pos.append(((cidx + 0.5) * colw, cy1 if row == 0 else cy2, lab, col, icon, row))
        c.setLineWidth(1.2)
        for cx, cy, lab, col, icon, row in pos:
            c.setStrokeColor(tint(col, 0.2))
            c.line(w / 2, hub_cy, cx, cy)
        hw, hh_ = 58 * mm, 13 * mm
        c.setFillColor(NAVY)
        c.roundRect(w / 2 - hw / 2, hub_cy - hh_ / 2, hw, hh_, 3.5 * mm, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 9.5)
        c.drawCentredString(w / 2, hub_cy + 1.0 * mm, "ESTATEHUB")
        sub = "ONE LOGIN  •  ONE SOURCE OF TRUTH"
        c.setFillColor(HexColor("#9FB3C8"))
        c.setFont("Helvetica-Bold", fit_font(sub, "Helvetica-Bold", 5.8, hw - 6 * mm))
        c.drawCentredString(w / 2, hub_cy - 4.3 * mm, sub)
        for cx, cy, lab, col, icon, row in pos:
            c.setFillColor(WHITE)
            c.circle(cx, cy, 5.6 * mm, fill=1, stroke=0)
            draw_badge(c, cx, cy, 10 * mm, icon, col)
            c.setFillColor(NAVY)
            c.setFont("Helvetica-Bold", fit_font(lab, "Helvetica-Bold", 7, colw - 4 * mm))
            ly = label_y1 if row == 0 else label_y2
            c.drawCentredString(cx, ly, lab)


class DbBars(Flowable):
    """Horizontal bar chart of the database objects, values taken from README.md."""
    ROW, GAP = 8 * mm, 2.6 * mm

    def __init__(self, bars):
        Flowable.__init__(self)
        self.bars = bars
        self.width = USABLE
        self.height = len(bars) * self.ROW + (len(bars) - 1) * self.GAP

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c, w = self.canv, self.width
        label_w, val_w = 38 * mm, 14 * mm
        track = w - label_w - val_w
        vmax = max(v for _, v, _, _ in self.bars)
        for i, (label, val, col, icon) in enumerate(self.bars):
            yb = self.height - (i + 1) * self.ROW - i * self.GAP
            cy = yb + self.ROW / 2
            draw_badge(c, 3.5 * mm, cy, 6.6 * mm, icon, col)
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 8)
            c.drawString(8.5 * mm, cy - 2.6, label)
            c.setFillColor(PALE)
            c.roundRect(label_w, yb + 1.2 * mm, track, self.ROW - 2.4 * mm, 1.8 * mm, fill=1, stroke=0)
            bl = max(track * val / vmax, 3 * mm)
            c.setFillColor(col)
            c.roundRect(label_w, yb + 1.2 * mm, bl, self.ROW - 2.4 * mm, 1.8 * mm, fill=1, stroke=0)
            c.setFillColor(NAVY)
            c.setFont("Helvetica-Bold", 9.5)
            c.drawString(label_w + track + 2.5 * mm, cy - 3.2, str(val))


class LayerStack(Flowable):
    """Nested 'defence in depth' bars, widest (outer) layer first."""
    BAR_H, GAP, STEP = 9 * mm, 1.8 * mm, 14 * mm

    def __init__(self, layers):
        Flowable.__init__(self)
        self.layers = layers
        self.width = USABLE
        self.height = len(layers) * self.BAR_H + (len(layers) - 1) * self.GAP

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c, w = self.canv, self.width
        for i, (icon, text, col) in enumerate(self.layers):
            bw = w - i * self.STEP
            x0 = (w - bw) / 2
            yb = self.height - (i + 1) * self.BAR_H - i * self.GAP
            c.setFillColor(col)
            c.roundRect(x0, yb, bw, self.BAR_H, 2.6 * mm, fill=1, stroke=0)
            cy = yb + self.BAR_H / 2
            if HAVE_FA:
                c.setFillColor(WHITE)
                c.circle(x0 + 5.2 * mm, cy, 3.4 * mm, fill=1, stroke=0)
                draw_icon(c, icon, x0 + 5.2 * mm, cy, 3.4 * mm * 0.95, col)
            area_l = x0 + (10.5 * mm if HAVE_FA else 4 * mm)
            area_w = bw - (10.5 * mm if HAVE_FA else 4 * mm) - 4 * mm
            fs = fit_font(text, "Helvetica-Bold", 8.4, area_w)
            c.setFillColor(WHITE)
            c.setFont("Helvetica-Bold", fs)
            c.drawCentredString(area_l + area_w / 2, cy - fs * 0.35, text)


class HashChain(Flowable):
    """Three linked receipt blocks - each block's 'prev' equals the block before's 'hash'."""
    BLOCK_H = 25 * mm
    GAP = 14 * mm

    def __init__(self):
        Flowable.__init__(self)
        self.width, self.height = USABLE, self.BLOCK_H

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c, w, h = self.canv, self.width, self.height
        bw = (w - 2 * self.GAP) / 3
        data = [("Receipt #1001", "0000...0000", "9f3a...c71", BLUE),
                ("Receipt #1002", "9f3a...c71", "e4b2...51d", TEAL),
                ("Receipt #1003", "e4b2...51d", "27cd...b08", GREEN)]
        for i, (title, prev, hsh, col) in enumerate(data):
            x = i * (bw + self.GAP)
            c.setFillColor(WHITE)
            c.setStrokeColor(tint(col, 0.3))
            c.setLineWidth(1)
            c.roundRect(x, 0, bw, h, 2.6 * mm, fill=1, stroke=1)
            c.saveState()
            path = c.beginPath()
            path.roundRect(x, 0, bw, h, 2.6 * mm)
            c.clipPath(path, stroke=0, fill=0)
            c.setFillColor(col)
            c.rect(x, h - 7.5 * mm, bw, 7.5 * mm, fill=1, stroke=0)
            c.restoreState()
            if HAVE_FA:
                draw_icon(c, "receipt", x + 4.5 * mm, h - 3.75 * mm, 8, WHITE)
            c.setFillColor(WHITE)
            c.setFont("Helvetica-Bold", 8)
            c.drawString(x + (8.5 * mm if HAVE_FA else 3 * mm), h - 5.2 * mm, title)
            for k, (lab, val, vcol) in enumerate([("prev", prev, MUTED), ("hash", hsh, col)]):
                yy = h - 12.8 * mm - k * 6 * mm
                c.setFillColor(MUTED)
                c.setFont("Helvetica", 6.8)
                c.drawString(x + 3.5 * mm, yy, lab)
                c.setFillColor(vcol if k else (col if i else MUTED))
                c.setFont("Courier-Bold", 8)
                c.drawString(x + 12 * mm, yy, val)
            if i < 2:
                gx = x + bw + self.GAP / 2
                if HAVE_FA:
                    draw_icon(c, "link", gx, h / 2, 11, col)
                else:
                    draw_arrow(c, gx, h / 2, col, 10)


class FifoBar(Flowable):
    """One payment split across dues, oldest first (illustrative amounts)."""
    def __init__(self):
        Flowable.__init__(self)
        self.width, self.height = USABLE, 29 * mm

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c, w, h = self.canv, self.width, self.height
        segs = [("Interest", 1000, CORAL), ("Oldest due", 4000, BLUE), ("Next due", 5000, TEAL)]
        total = sum(v for _, v, _ in segs)
        head = Paragraph(fx("<b>Payment received: ₹10,000</b>  (illustrative) — allocated oldest first, "
                            "interest before principal"), ST["TB"])
        hw, hh = head.wrap(w, 100)
        head.drawOn(c, 0, h - hh)
        bar_y, bar_h = 7 * mm, 9 * mm
        c.saveState()
        path = c.beginPath()
        path.roundRect(0, bar_y, w, bar_h, 2.4 * mm)
        c.clipPath(path, stroke=0, fill=0)
        x = 0
        spans = []
        for name, v, col in segs:
            sw = w * v / total
            c.setFillColor(col)
            c.rect(x, bar_y, sw, bar_h, fill=1, stroke=0)
            spans.append((x, sw))
            x += sw
        c.restoreState()
        for i, ((name, v, col), (sx, sw)) in enumerate(zip(segs, spans)):
            val = Paragraph(fx(f"₹{v:,}"), ST["SegV"])
            vw, vh = val.wrap(sw, 50)
            val.drawOn(c, sx, bar_y + (bar_h - vh) / 2)
            nm = Paragraph(name, ST["SegN"])
            nw, nh = nm.wrap(sw, 50)
            nm.drawOn(c, sx, bar_y - 1.5 * mm - nh)
            cy = bar_y + bar_h + 3.4 * mm
            c.setFillColor(NAVY)
            c.circle(sx + sw / 2, cy, 2.5 * mm, fill=1, stroke=0)
            c.setFillColor(WHITE)
            c.setFont("Helvetica-Bold", 7)
            c.drawCentredString(sx + sw / 2, cy - 2.4, str(i + 1))


class QRBox(Flowable):
    """Real QR code when ESTATEHUB_DEMO_URL is set, otherwise a clearly labelled placeholder."""
    def __init__(self, size=36 * mm):
        Flowable.__init__(self)
        self.width = self.height = size

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c, s = self.canv, self.width
        if DEMO_URL:
            widget = qr.QrCodeWidget(DEMO_URL)
            b = widget.getBounds()
            bw, bh = b[2] - b[0], b[3] - b[1]
            d = Drawing(s, s, transform=[s / bw, 0, 0, s / bh, 0, 0])
            d.add(widget)
            renderPDF.draw(d, c, 0, 0)
            return
        c.setStrokeColor(NAVY)
        c.setDash(3, 2)
        c.setLineWidth(1)
        c.roundRect(0, 0, s, s, 3 * mm, fill=0, stroke=1)
        c.setDash()
        draw_icon(c, "qrcode", s / 2, s / 2 + 4 * mm, s * 0.42, tint(NAVY, 0.55))
        c.setFillColor(CORAL)
        c.setFont("Helvetica-Bold", 6.2)
        c.drawCentredString(s / 2, 7 * mm, "DEMO QR GOES HERE")
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 5.2)
        c.drawCentredString(s / 2, 3.6 * mm, "set ESTATEHUB_DEMO_URL")


def footer(c, doc):
    c.saveState()
    c.setFillColor(BLUE)
    c.rect(0, H - 2.6 * mm, W, 2.6 * mm, fill=1, stroke=0)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 6.4)
    c.drawString(16 * mm, 7.5 * mm,
                 "EstateHub  •  The Complete Society Management Platform  •  Marketing Brochure v1.0")
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 6.6)
    c.drawRightString(W - 16 * mm, 7.5 * mm, str(doc.page))
    c.restoreState()


def table_style(header=True):
    st = [("GRID", (0, 0), (-1, -1), 0.4, CARDL),
          ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [WHITE, LIGHT]),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
          ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
    if header:
        st.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    return TableStyle(st)


doc = SimpleDocTemplate(str(out), pagesize=A4,
                        leftMargin=16 * mm, rightMargin=16 * mm,
                        topMargin=14 * mm, bottomMargin=16 * mm,
                        title="EstateHub — Marketing Brochure", author="EstateHub")
S = []

# ============================ COVER ============================
S += [Spacer(1, 4 * mm),
      P("EstateHub", "CoverT"),
      P("The Complete Society Management Platform", "CoverSub"),
      Spacer(1, 1 * mm),
      Hero(),
      Spacer(1, 6 * mm),
      P("PROFESSIONAL MARKETING BROCHURE", "H2x"),
      P("For Society Administrators, Secretaries &amp; Managing Committee Members", "S"),
      Spacer(1, 5 * mm),
      quote("“Stop managing your society. Start leading it.”"),
      Spacer(1, 7 * mm),
      Table([[[P("<b>Sunrise Residency</b>  •  Uttar Pradesh  •  Demo society", "TB"),
               Spacer(1, 4 * mm),
               P("Contact: ____________________   Email: ______________________", "S"),
               Spacer(1, 2 * mm),
               P("Phone: ______________________   Website: ______________________", "S")],
              QRBox()]],
            colWidths=[USABLE - 42 * mm, 42 * mm],
            style=[("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]),
      PageBreak()]

# ============================ 1. EXECUTIVE SUMMARY ============================
S += sect("1", "Executive Summary",
          "Society administration should not depend on manual registers, scattered WhatsApp messages, "
          "Excel workbooks and the memory of one or two committee members.", "chart-line", BLUE)
S += [P("EstateHub brings the operational back office into one browser-based platform. It combines "
        "automated receivables, double-entry cashbook, bank reconciliation, secure signed QR gate access, "
        "complaints, events, polls, NOCs, assets, reports and resident self-service — all without page reloads."),
      Spacer(1, 2 * mm),
      P("<b>Built for Uttar Pradesh Apartment Owners' Associations</b> (UP Apartment Act, 2010; UP Apartment "
        "Rules, 2011; Model Bye-Laws, 2011), with Central tax laws layered on top. Every statutory threshold is "
        "dated data, not hard-coded, so a change in law is a data row — never a redeploy."),
      Spacer(1, 4 * mm)]
S += grid([("50+", "Workflows covered", BLUE, "list-check"),
           ("10", "Role-scoped portals", TEAL, "users"),
           ("30 days", "Adoption roadmap", GREEN, "calendar-check"),
           ("₹2,00,000", "Cash-receipt ceiling enforced", GOLD, "ban")], 4, cls=Tile, gap=4 * mm, row_gap=3 * mm)
S += [P("From fragmented work to a controlled workflow", "H2x")]
ba = [("comments", "WhatsApp reminders and manual follow-up", "Dues visible to owners; channels broadcast reminders"),
      ("arrows-rotate", "Excel-based bank reconciliation", "Exact match → fuzzy match → row-by-row reconciliation"),
      ("receipt", "Paper receipts and cashbook", "Receipts, vouchers and month-wise double-entry ledger"),
      ("qrcode", "Handwritten gate passes", "HMAC-signed, versioned QR passes; camera + NFC scanning"),
      ("clipboard-list", "Complaints buried in chat", "Raise → assign → vendor bid → resolve with audit trail")]
rows = [["", P(ic("xmark", CORAL) + "  BEFORE", "TH"), P(ic("check", GREEN) + "  WITH APEXESTATEHUB", "TH")]]
for icon, before, after in ba:
    rows.append([P(ic(icon, BLUE, 11), "TBC"), P(before, "TB"), P(ic("check", GREEN) + "  " + after, "TB")])
S += [Table(rows, colWidths=[12 * mm, 74 * mm, 92 * mm], style=table_style()),
      Spacer(1, 5 * mm),
      P("Under the hood", "H2x"),
      P("Counts are read from the schema line in README.md, so they stay in step with the database.", "S"),
      Spacer(1, 1 * mm),
      DbBars([("Tables", STATS["tables"], BLUE, "database"),
              ("SQL functions", STATS["functions"], GREEN, "gears"),
              ("Triggers", STATS["triggers"], GOLD, "bolt"),
              ("Views", STATS["views"], TEAL, "table-columns")]),
      Spacer(1, 6 * mm),
      quote("“Stop managing your society. Start leading it.”"),
      PageBreak()]

# ============================ 2. THE PAIN LANDSCAPE ============================
S += sect("2", "The Pain Landscape", "A day in the life of Rajesh, Society Secretary, Sunrise Residency (120 flats).",
          "clock", CORAL)
S += [P("Rajesh is a retired bank manager who volunteered as Secretary. He knows accounts and people — "
        "and still every Monday begins with a fresh pile of unfinished work."), Spacer(1, 3 * mm)]
pain = [("08:30", "comments", "Dues chase", "Three owners ask for maintenance balances on WhatsApp. Rajesh checks an old Excel sheet and replies one by one."),
        ("10:15", "arrows-rotate", "Bank reconciliation", "A bank statement arrives. He compares rows manually against another workbook, marking possible matches."),
        ("12:00", "qrcode", "Gate pass", "A contractor needs access. Rajesh prepares a pass, sends a photo to security and hopes the latest version reaches the gate."),
        ("14:30", "bullhorn", "Complaints", "Fifteen messages arrive: seepage, lift noise, plumbing, parking. No single queue, owner, deadline or audit trail."),
        ("17:00", "book", "Cashbook", "He starts the monthly cashbook. One figure does not agree. He searches paper vouchers and old messages."),
        ("19:30", "file-signature", "NOC search", "An owner needs a copy of an NOC issued six months ago. He searches folders, email and WhatsApp.")]
S += timeline(pain, [TEAL, BLUE, GOLD, CORAL, GREEN, PURPLE])
S += [Spacer(1, 6 * mm),
      quote("He is doing the work. The problem is that the work is scattered."),
      Spacer(1, 3 * mm),
      quote("“There has to be a better way.”", accent=CORAL),
      PageBreak()]

# ============================ 3. ESTATEHUB AT A GLANCE (10 PORTALS) ============================
S += sect("3", "EstateHub at a Glance",
          "Ten role-scoped portals. One operating model. Each login sees only the rows its role is scoped to.",
          "users", TEAL)
portals = [
    ("MASTER ADMIN", "Platform operator", "Platform oversight • societies • plans • statutory rule data", PURPLE, "crown"),
    ("SOCIETY ADMIN", "Secretary / Treasurer / MC", "Dashboard • finance • operations • compliance", BLUE, "user-shield"),
    ("APARTMENT OWNER", "Owner / family / tenant", "Dues • concerns • events • gate pass • bills paid", TEAL, "house"),
    ("VENDOR", "Service contractor", "Pass status • charges • gate QR • bid on concerns", GOLD, "screwdriver-wrench"),
    ("SECURITY GUARD", "Gate staff", "QR scanner • attendance • gate log • walk-ins", CORAL, "shield-halved"),
    ("ACCOUNTANT", "Finance preparer", "Receipts • expenses • dues • cashbook • TDS &amp; GST", INDIGO, "calculator"),
    ("SUPERVISOR", "Gate &amp; field oversight", "Gate &amp; security • users • concerns • events", GREEN, "clipboard-check"),
    ("STAFF", "General society staff", "Concerns • events • alert channels", TEAL, "users"),
    ("AUDITOR", "Statutory / internal auditor", "Verify checks • books • receipts • financials (read-only)", BLUE, "magnifying-glass"),
    ("ADVISER", "CA / Advocate / Auditor", "Appointment-bound masked ledger export", PURPLE, "scale-balanced"),
]
S += grid([(n, f"<b>{role}</b><br/>{desc}", col, icon) for n, role, desc, col, icon in portals], 2)
S += [Spacer(1, 1 * mm),
      P("Design principle: role-scoped by default. The Admin gets the control plane; residents get self-service; "
        "vendors and guards get focused workflows; the Master Admin gets platform-level management — with no "
        "society-data capability.", "B"),
      PageBreak()]

# ============================ 4. THE ADMIN PORTAL ============================
S += sect("4", "The Admin Portal", "The committee's operational control room — scoped to one society.",
          "user-shield", BLUE)
tabs = [
    ("Dashboard", "Dues, receipts, gate logs and open concerns in KPI cards.", BLUE, "chart-pie"),
    ("Financials", "Receipts, expenses, receivables, payables, cashbook, ledger.", TEAL, "wallet"),
    ("Bank Reconcile", "CSV/Excel upload; exact + fuzzy matching; row-by-row reconcile.", GREEN, "arrows-rotate"),
    ("Enrolled", "Apartments, vendors, security; bulk CSV upload.", GOLD, "id-card"),
    ("Concerns", "Raise → assign → vendor bid → resolve with audit trail.", CORAL, "comments"),
    ("Events", "Create events, sell tickets, scan QR entry.", TEAL, "ticket"),
    ("Polls", "Create polls, collect owner votes, view results.", GREEN, "check-to-slot"),
    ("Gate Pass", "QR validity, revoke/re-issue, browser NFC writing.", BLUE, "qrcode"),
    ("NOC", "Eligibility gate → rich-text editor → print/PDF/email.", TEAL, "file-signature"),
    ("Customize", "Drag-and-drop KPI layout + KPI SQL Inspector.", GOLD, "sliders"),
    ("Settings", "Setup Wizard, team logins, QR re-issue, password controls.", CORAL, "gears"),
    ("UP AOA Compliance", "Bye-law 49 filings, undivided interest, s.22, bye-law 7, owner loans.", GREEN, "landmark"),
]
S += grid(tabs, 3)
S += [PageBreak()]

# ============================ 5. FIVE WORKFLOW BLUEPRINTS ============================
S += sect("5", "Five Workflow Blueprints",
          "System actions are automated where specified; people remain accountable for approvals and governance.",
          "list-check", GREEN)


def workflow(title, icon, accent, steps, note=None, per_row=4):
    flow = [Banner(title, None, accent, icon), Spacer(1, 3 * mm),
            StepFlow([(ico, f"STEP {i + 1}", txt, None) for i, (ico, txt) in enumerate(steps)],
                     accent, per_row=per_row)]
    if note:
        flow += [Spacer(1, 2 * mm), P(note, "S")]
    return [KeepTogether(flow), Spacer(1, 6 * mm)]


S += workflow("01  Monthly Dues Collection", "receipt", BLUE, [
    ("calendar-check", "Auto-generates receivables on the 1st"), ("eye", "Owner sees dues"),
    ("bell", "Admin sends reminder"), ("wallet", "Owner pays or disputes"),
    ("list-check", "FIFO allocation"), ("link", "SHA-256 receipt"),
    ("book", "Cashbook updated"), ("arrows-rotate", "Bank reconciled")])
S += workflow("02  Vendor Gate Pass", "qrcode", TEAL, [
    ("id-card", "Admin creates vendor and validity"), ("qrcode", "Signed QR generated"),
    ("mobile-screen", "Vendor downloads pass"), ("camera", "Security scans"),
    ("person-walking", "Entry IN logged"), ("clock", "Expiry or loss"),
    ("arrows-rotate", "Revoke and re-issue"), ("ban", "Old QR invalid")])
S += workflow("03  Maintenance Complaint", "wrench", GREEN, [
    ("comments", "Owner raises concern"), ("clock", "System timestamps"),
    ("user-tie", "Admin assigns vendor"), ("hand-holding-dollar", "Vendor submits bid"),
    ("circle-check", "Admin approves"), ("wrench", "Work completed"),
    ("thumbs-up", "Owner confirms"), ("file-lines", "Audit trail closed")])
S += workflow("04  NOC Issuance", "file-signature", GOLD, [
    ("envelope", "Owner requests NOC"), ("circle-check", "System checks zero dues"),
    ("file-signature", "Admin edits rich-text NOC"), ("stamp", "Branded document generated"),
    ("print", "Print, PDF or email delivered")],
    note="If the owner is ineligible, the outstanding amount is shown instead.")
S += workflow("05  New Society Onboarding", "rocket", CORAL, [
    ("key", "First login"), ("wand-magic-sparkles", "Setup Wizard"),
    ("building", "Society details"), ("landmark", "Tax &amp; compliance"),
    ("wallet", "Billing &amp; accounts"), ("book", "Brought-forward balances"),
    ("file-signature", "Agreement e-sign"), ("rocket", "Society goes live")])
S += [P("Demonstrated end-to-end: dues cycle, gate QR scan, concern resolution and NOC issuance follow the "
        "society's real operating workflow.", "S"),
      PageBreak()]

# ============================ 6. THE FINANCIAL PROMISE ============================
S += sect("6", "The Financial Promise", "Why administrators can trust the workflow behind the numbers.",
          "scale-balanced", BLUE)
fin = [
    ("Double-entry accounting", "Every receipt and expense posts paired Dr/Cr legs; a deferred balance trigger refuses an unbalanced journal at commit.", BLUE, "scale-balanced"),
    ("FIFO allocation", "Oldest dues first; interest cleared before principal; selective Pay Dues settles mixed funds per row.", TEAL, "bars-progress"),
    ("SHA-256 receipt hashing", "Receipt numbers form a cryptographic hash chain; altering a historical receipt breaks every later link.", GREEN, "link"),
    ("Bank reconciliation", "Exact match first, fuzzy match next, then manual row-by-row reconciliation per bank account.", GOLD, "arrows-rotate"),
    ("GST / TDS defaults", "GST billed only above the ₹7,500/member and ₹20 lakh turnover gate; effective-dated TDS sections and rates.", CORAL, "receipt"),
    ("One-click reports", "Cashbook, ledger, receivables, receipts, expenses and six financial statements export to CSV/Excel.", BLUE, "chart-line"),
]
S += grid(fin, 2)
S += [KeepTogether([P("How receipt numbers chain together", "H2x"), Spacer(1, 1 * mm), HashChain(), Spacer(1, 2 * mm),
                    P("Illustrative values. Each receipt's number is a SHA-256 hash that includes the previous receipt's hash, "
                      "so changing any historical receipt breaks every later link and the tampering shows.", "S")]),
      Spacer(1, 3 * mm),
      KeepTogether([P("How a payment is allocated", "H2x"), Spacer(1, 1 * mm), FifoBar()]),
      Spacer(1, 6 * mm),
      quote("“At the AGM, Rajesh projected the cashbook on the hall screen. For the first time in 11 years, "
            "every rupee was accounted for, to the paisa.”",
            "Illustrative testimonial — replace with verified customer evidence before public release."),
      PageBreak()]

# ============================ 7. STATUTORY COMPLIANCE ============================
S += sect("7", "Statutory Compliance — Built for UP AOAs",
          "Six things the software will not let anyone do — enforced inside the database, so a screen, a bug "
          "or a hurried user cannot get round them.", "landmark", TEAL)
compliance = [
    ("Quietly change the books", "Posted ledger lines are immutable; mistakes are corrected only by a visible reversal. A SHA-256 hash chain plus signed anchor certificates filed with the CA make any rewrite show.", TEAL, "lock"),
    ("Post an unbalanced voucher", "A deferred balance trigger refuses any journal that does not balance. Cash vouchers are provenance- and amount-checked against their source document.", BLUE, "scale-balanced"),
    ("Reopen a locked year", "After year-end close, the Treasurer alone can lock it irreversibly; nothing can be posted into that or any earlier year, and a signed ledger anchor is taken first.", GREEN, "key"),
    ("Apply a rule without showing its authority", "53 UP rules carry source text and status (38 checked, 13 provisional, 2 disputed). Rule changes are dated, non-retroactive and audited.", GOLD, "gavel"),
    ("Pass a resolution on a typed number", "Quorum (30% floor) and majority are derived from attendance and vote registers, each flat weighted by undivided interest, measured against all owners — not votes cast.", CORAL, "check-to-slot"),
    ("Hide a tax assumption", "Cash receipts of ₹2,00,000+ from one payer in a day are refused. GST is charged only when turnover clearly exceeds ₹20 lakh and a member's charge exceeds ₹7,500; contested heads are held for the CA.", PURPLE, "receipt"),
]
S += grid(compliance, 2)
S += [KeepTogether([P("Defence in depth: how the ledger is protected", "H2x"),
                    P("Each layer is there for what the layer above it cannot catch on its own.", "S"),
                    Spacer(1, 1 * mm),
                    LayerStack([("users", "Application: role-scoped access and tenant isolation", BLUE),
                                ("bolt", "Database triggers: immutable lines, balanced journals", TEAL),
                                ("link", "SHA-256 ledger hash chain", GREEN),
                                ("stamp", "Signed anchors filed with the CA", INDIGO),
                                ("shield-halved", "Restricted database role: no truncate, update or delete", PURPLE),
                                ("book", "The society's books", NAVY)])]),
      Spacer(1, 4 * mm),
      P("What we do not claim: no return filing, no TRACES/GST e-filing, no Section 80P/80AC computation, no "
        "DPDP certification (parameters marked [Verify]), no e-invoicing, and no automated breach notification. "
        "EstateHub prepares and protects the books — it does not replace the society's CA and advocate.", "S"),
      PageBreak()]

# ============================ 8. SECURITY, PRIVACY & RELIABILITY ============================
S += sect("8", "Security, Privacy &amp; Reliability", "Trust built into every layer — never sourced from the browser.",
          "shield-halved", PURPLE)
sec = [
    ("Signed QR passes", "HMAC-SHA256 signed, versioned passes keyed per society under SECRET_VAULT_KEY; revoke and re-issue invalidates old codes.", BLUE, "qrcode"),
    ("Two-actor visitor approval", "Owner confirmation required before visitor admission; the guard cannot approve its own alert.", TEAL, "user-check"),
    ("Anti-spoofing patrol", "GPS geo-fence (50 m) plus travel-speed check (&gt;25 km/h rejected); 60-second expiring epoch QR for attendance.", GREEN, "location-dot"),
    ("Role-scoped access", "Explicit capability sets, no wildcards; tenant isolation is a hard deny; platform operators have no society-data capability.", GOLD, "shield-halved"),
    ("DPDP Act machinery", "Versioned notice gate, purpose-bound consent, rights register (access/correction/erasure/nominee/grievance), breach register, profile-only erasure.", CORAL, "fingerprint"),
    ("Immutable audit trail", "Actor, role, society, action, before/after values, reason, correlation id and IP — append-only, trigger-guarded, credentials stripped.", PURPLE, "clipboard-list"),
]
S += grid(sec, 2)
S += [KeepTogether([P("Visitor admission: two people must agree", "H2x"), Spacer(1, 1 * mm),
                    StepFlow([("person-walking", "STEP 1", "Visitor arrives at the gate and the guard scans the pass", None),
                              ("bell", "STEP 2", "A pending pass raises an alert to the owner in the app", None),
                              ("user-check", "STEP 3", "The guard admits the visitor only after the owner approves", None)],
                             PURPLE, per_row=3, gap=10 * mm)]),
      PageBreak()]

# ============================ 9. RESIDENT EXPERIENCE ============================
S += sect("9", "Resident Experience", "Routine queries become self-service — from a phone.", "mobile-screen", TEAL)
res = [
    ("Know your dues", "See pending dues, payment history and your own ledger passbook.", TEAL, "wallet"),
    ("Raise a concern", "Submit and track complaints in real time; invite vendors or be assigned directly.", CORAL, "comments"),
    ("Join events", "Buy tickets and use QR-based venue entry; tickets marked used on scan to prevent double-scan.", GOLD, "ticket"),
    ("Vote in polls", "One vote per apartment, secret ballot, weighted by undivided interest; quorum 30%, majority 51%.", BLUE, "check-to-slot"),
    ("Carry your pass", "Download your personal gate-pass QR; visitor pre-registration and gate alerts.", GREEN, "qrcode"),
    ("Control alerts", "Subscribe or unsubscribe from school bus, taxi and visitor broadcast channels.", TEAL, "bell"),
]
S += grid(res, 3)
S += [Spacer(1, 6 * mm),
      quote("“Earlier I had to call the secretary to find out my maintenance balance. Now I open the app and it's "
            "there — to the paisa, with every payment history.”",
            "— Priya Sharma, Flat A-203, Sunrise Residency (illustrative)"),
      Spacer(1, 10 * mm)]

# ============================ 10. ADOPTION ROADMAP ============================
S += sect("10", "Adoption Roadmap", "From paper to platform in 30 days.", "rocket", GREEN)
S += [StepFlow([("building", "WEEK 1", "Society details, logo and signing setup", "Setup Wizard • Image upload"),
                ("id-card", "WEEK 2", "Bulk enrol apartments, vendors and security (XLSX)", "Bulk CSV enrol"),
                ("qrcode", "WEEK 3", "Issue QR passes; onboard security; invite owners", "QR modal • Security portal"),
                ("calculator", "WEEK 4", "Generate receivables; verify cashbook; issue NOC", "Financial engine • NOC"),
                ("arrows-rotate", "ONGOING", "Reconcile statements; export AGM reports", "Bank reconcile • Reports")],
               GREEN, per_row=5, gap=7 * mm),
      Spacer(1, 8 * mm),
      quote("“From Day 30 onwards, EstateHub runs the back-office. The Secretary runs the society.”", accent=GREEN),
      PageBreak()]

# ============================ 11. PLANS & CALL TO ACTION ============================
S += sect("11", "Plans &amp; Call to Action", "Simple, society-sized pricing. Every plan includes role-scoped portals, "
                                          "signed QR gate access and the full statutory engine.", "handshake", GOLD)
S += grid([("STARTER", "<b>₹ TBD</b><br/>Smaller communities<br/><br/>Core administration<br/>Resident self-service", TEAL, "seedling"),
           ("PROFESSIONAL", "<b>₹ TBD</b><br/>Growing societies<br/><br/>Financial workflows<br/>Gate + concerns + reports", BLUE, "building"),
           ("ENTERPRISE", "<b>₹ TBD</b><br/>Portfolios / operators<br/><br/>Multi-society management<br/>Advanced controls", PURPLE, "building-columns")], 3)
S += [Spacer(1, 5 * mm), P("Request a live demonstration", "H2x"),
      P("See the Admin dashboard, run a sample dues cycle, scan a gate QR, raise a concern and issue an NOC. "
        "The demonstration can follow your society's real operating workflow."),
      Spacer(1, 5 * mm),
      Table([[QRBox(), [P("<b>Scan to request a live demo</b>", "B"), Spacer(1, 3 * mm),
                        P(ic("user-tie", BLUE, 9) + "  Contact: ____________________", "TB"), Spacer(1, 2 * mm),
                        P(ic("envelope", BLUE, 9) + "  Email: ______________________", "TB"), Spacer(1, 2 * mm),
                        P(ic("mobile-screen", BLUE, 9) + "  Phone: ______________________", "TB"), Spacer(1, 2 * mm),
                        P(ic("rocket", BLUE, 9) + "  Website: ______________________", "TB")]]],
            colWidths=[46 * mm, 132 * mm],
            style=[("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]),
      Spacer(1, 8 * mm),
      quote("“Stop managing your society. Start leading it.”", accent=GOLD),
      PageBreak()]

# ============================ 12. FAQ ============================
S += sect("12", "Frequently Asked Questions", "Straight answers for committees evaluating the platform.",
          "circle-question", INDIGO)
faqs = [
    ("Our committee is not tech-savvy.", "Role-based screens and a guided Setup Wizard; adoption begins with controlled, 30-day onboarding."),
    ("What if the internet goes down?", "Live cloud functions depend on connectivity; the final deployment should define the society's outage contingency procedure."),
    ("We have 30 years of paper records—how do we migrate?", "Bulk-enrolment templates for current apartments, vendors and staff; historical financials follow agreed opening balances and retention rules."),
    ("Is our financial data safe on the cloud?", "Tenant isolation, authentication, managed PostgreSQL and backups; final hosting and access controls reviewed before approval."),
    ("Can we customise dashboard KPIs?", "Yes — a drag-and-drop KPI layout editor and KPI SQL Inspector per portal and tab."),
    ("What happens if we cancel?", "Cancellation/export policy should be stated in the subscription terms; data exports are available on demand."),
    ("Our vendors don't have smartphones?", "Vendor workflows are defined; the exact non-smartphone fallback documented in the deployment SOP."),
    ("We already have a WhatsApp group—why do we need this?", "WhatsApp stays useful for conversation. EstateHub provides structured records for finance, complaints, gate access and governance."),
    ("Can bank reconciliation handle our co-operative bank's format?", "CSV/Excel upload with exact and fuzzy matching; the bank's actual format tested during onboarding."),
    ("Will receipts be legally valid for income-tax purposes?", "Receipt records and SHA-256 hashing are provided; legal/tax validity depends on applicable law and the society's processes."),
    ("Can multiple committee members log in simultaneously?", "Role-based architecture is designed for multiple authorised users, subject to the account and authentication policy."),
    ("How are partial payments handled?", "FIFO allocation applies payments to the oldest dues first, with interest cleared before principal."),
]
accents = [BLUE, TEAL, GREEN, GOLD, CORAL, PURPLE]
S += grid([(q, a, accents[i % len(accents)], "circle-question") for i, (q, a) in enumerate(faqs)], 2)
S += [Spacer(1, 1 * mm),
      P("Marketing claims, pricing, metrics and testimonials marked as placeholders should be verified before "
        "commercial publication.", "S")]

doc.build(S, onFirstPage=footer, onLaterPages=footer)
print(f"Counts used (from {README.name}): {STATS['tables']} tables, "
      f"{STATS['functions']} functions, {STATS['triggers']} triggers")
print(f"Icons: {'Font Awesome ' + FA_VERSION if HAVE_FA else 'OFF (font not available)'}"
      f"   QR: {'real code for ' + DEMO_URL if DEMO_URL else 'placeholder'}")
print(f"Created: {out}")
print(f"File size: {out.stat().st_size/1024:.1f} KB")
