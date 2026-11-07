from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                PageBreak, KeepTogether, Flowable, HRFlowable)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from pathlib import Path
import textwrap, re

out = Path(__file__).resolve().parent / "EstateHub_Marketing_Brochure_Print_Ready.pdf"
W, H = A4
NAVY  = HexColor("#0F2B46")
BLUE  = HexColor("#1D70F7")
TEAL  = HexColor("#00A6A6")
GREEN = HexColor("#2EAF62")
GOLD  = HexColor("#F4B942")
CORAL = HexColor("#F26457")
PURPLE= HexColor("#6A1B9A")
INDIGO= HexColor("#3949AB")
INK   = HexColor("#203040")
MUTED = HexColor("#64748B")
LIGHT = HexColor("#F4F8FC")
PALE  = HexColor("#EAF2FF")
CARDL = HexColor("#D8E3EE")
WHITE = colors.white

USABLE = 178 * mm  # 210mm - 2*16mm margins

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="CoverT", fontName="Helvetica-Bold", fontSize=34, leading=38,
                          textColor=NAVY, spaceAfter=6))
styles.add(ParagraphStyle(name="CoverSub", fontName="Helvetica", fontSize=15, leading=20,
                          textColor=BLUE, spaceAfter=10))
styles.add(ParagraphStyle(name="CoverTag", fontName="Helvetica-Oblique", fontSize=13, leading=18,
                          textColor=INK, alignment=TA_CENTER, spaceAfter=4))
styles.add(ParagraphStyle(name="H1x", fontName="Helvetica-Bold", fontSize=20, leading=24,
                          textColor=NAVY, spaceBefore=2, spaceAfter=6))
styles.add(ParagraphStyle(name="H2x", fontName="Helvetica-Bold", fontSize=12.5, leading=16,
                          textColor=BLUE, spaceBefore=6, spaceAfter=4))
styles.add(ParagraphStyle(name="B", fontName="Helvetica", fontSize=9, leading=12.5,
                          textColor=INK, spaceAfter=4, alignment=TA_LEFT))
styles.add(ParagraphStyle(name="BC", fontName="Helvetica", fontSize=9, leading=12.5,
                          textColor=INK, spaceAfter=4, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="S", fontName="Helvetica", fontSize=7, leading=9.5,
                          textColor=MUTED, spaceAfter=3))
styles.add(ParagraphStyle(name="Q", fontName="Helvetica-Oblique", fontSize=13.5, leading=18,
                          textColor=NAVY, alignment=TA_CENTER, spaceAfter=4))
styles.add(ParagraphStyle(name="TH", fontName="Helvetica-Bold", fontSize=7.6, leading=9.5,
                          textColor=WHITE))
styles.add(ParagraphStyle(name="TB", fontName="Helvetica", fontSize=7.6, leading=9.8,
                          textColor=INK))
styles.add(ParagraphStyle(name="Cap", fontName="Helvetica-Bold", fontSize=7.4, leading=9,
                          textColor=WHITE, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="StatN", fontName="Helvetica-Bold", fontSize=20, leading=22,
                          textColor=NAVY, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="StatL", fontName="Helvetica", fontSize=6.6, leading=8.5,
                          textColor=MUTED, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="CardT", fontName="Helvetica-Bold", fontSize=8.6, leading=10.5,
                          textColor=NAVY))
styles.add(ParagraphStyle(name="CardB", fontName="Helvetica", fontSize=7.2, leading=9.4,
                          textColor=INK))

def P(s, st="B"): return Paragraph(s, styles[st])

def sect(num, title, sub=None):
    """Section header with colored accent bar."""
    rows = [[P(f"<b>{num}  |  {title}</b>", "H1x")]]
    if sub:
        rows.append([P(sub, "S")])
    t = Table(rows, colWidths=[USABLE])
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, -1), (-1, -1), 2.2, BLUE),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return [t, Spacer(1, 3 * mm)]

def stat_item(num, label, sub, accent):
    inner = [
        [P(num, "StatN")],
        [P(label, "StatL")],
        [P(sub, "StatL")],
    ]
    t = Table(inner, colWidths=[42 * mm], rowHeights=[7.5 * mm, 5.5 * mm, 5 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("LINEBELOW", (0, 0), (-1, 0), 1.6, accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t

class Card(Flowable):
    """Rounded card: accent bar top, bold title, body text."""
    def __init__(self, title, body, accent=BLUE, w=84 * mm, h=40 * mm, body_st="CardB"):
        self.title, self.body, self.accent, self.width, self.height, self.body_st = \
            title, body, accent, w, h, body_st
    def wrap(self, aw, ah): return self.width, self.height
    def draw(self):
        c = self.canv
        c.setFillColor(WHITE); c.setStrokeColor(CARDL)
        c.roundRect(0, 0, self.width, self.height, 3.5 * mm, fill=1, stroke=1)
        c.setFillColor(self.accent)
        c.roundRect(0, self.height - 3.4 * mm, self.width, 3.4 * mm, 2 * mm, fill=1, stroke=0)
        c.setFillColor(WHITE); c.setFont("Helvetica-Bold", 7.6)
        c.drawString(5.5 * mm, self.height - 2.4 * mm, self.title)
        c.setFillColor(INK); c.setFont("Helvetica", 7.2, 9.3)
        y = self.height - 10.5 * mm
        for line in textwrap.wrap(re.sub("<[^>]+>", "", self.body), 46)[:5]:
            c.drawString(5.5 * mm, y, line); y -= 8.6

def row_of_cards(items, gap=6 * mm, w=84 * mm, h=40 * mm):
    cells = []
    for title, body, accent in items:
        cells.append(Card(title, body, accent, w, h))
    if len(cells) == 1:
        cells.append(Spacer(1, 1))
    n = len(cells)
    colw = (USABLE - gap * (n - 1)) / n
    # rescale cards to fit
    for cell in cells:
        cell.width = colw
    t = Table([cells], colWidths=[colw] * n)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), gap),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t

class Hero(Flowable):
    def __init__(self):
        self.width = USABLE; self.height = 58 * mm
    def wrap(self, aw, ah): return self.width, self.height
    def draw(self):
        c = self.canv
        c.setFillColor(PALE); c.roundRect(0, 0, self.width, self.height, 6 * mm, fill=1, stroke=0)
        c.setFillColor(NAVY); c.roundRect(0, self.height - 9 * mm, self.width, 9 * mm, 6 * mm, fill=1, stroke=0)
        c.setFillColor(WHITE); c.setFont("Helvetica-Bold", 9.5)
        c.drawString(10 * mm, self.height - 5.5 * mm, "MULTI-TENANT   •   ROLE-AWARE   •   REAL-TIME   •   ZERO-RELOAD")
        c.setFont("Helvetica", 7.2); c.setFillColor(HexColor("#9FB3C8"))
        c.drawString(10 * mm, self.height - 8.2 * mm, "Python 3.12  •  Dash 2.14 + Flask 2.2  •  PostgreSQL 16  •  gunicorn")
        # stat chips
        chips = [("10", "Role-Scoped Portals", TEAL), ("160", "Database Tables", BLUE),
                 ("353", "SQL Functions", GREEN), ("87", "Database Triggers", GOLD)]
        x = 10 * mm; y = self.height - 22 * mm
        for num, lab, col in chips:
            c.setFillColor(LIGHT); c.roundRect(x, y, 40 * mm, 14 * mm, 3 * mm, fill=1, stroke=0)
            c.setFillColor(col); c.circle(x + 6 * mm, y + 7 * mm, 2.6 * mm, fill=1, stroke=0)
            c.setFillColor(INK); c.setFont("Helvetica-Bold", 11)
            c.drawString(x + 11 * mm, y + 8.5 * mm, num)
            c.setFont("Helvetica", 6.4); c.setFillColor(MUTED)
            c.drawString(x + 11 * mm, y + 3.5 * mm, lab)
            x += 42 * mm
        # role badges
        roles = [("MASTER", PURPLE), ("ADMIN", BLUE), ("OWNER", TEAL), ("VENDOR", GOLD),
                 ("SECURITY", CORAL), ("ACCOUNTANT", INDIGO), ("SUPERVISOR", GREEN),
                 ("STAFF", TEAL), ("AUDITOR", BLUE), ("ADVISER", PURPLE)]
        bx = 10 * mm; by = 6 * mm
        c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 7.5)
        c.drawString(10 * mm, by + 22 * mm, "ONE LOGIN  •  TEN ROLE-SCOPED PORTALS  •  ONE SOURCE OF TRUTH")
        c.setStrokeColor(NAVY)
        for i, (lab, col) in enumerate(roles):
            rx = bx + (i % 5) * 33 * mm; ry = by + (i // 5) * 11 * mm
            c.setStrokeColor(col); c.line(10 * mm, by + 20 * mm, rx, ry + 4 * mm)
            c.setFillColor(col); c.circle(rx, ry + 4 * mm, 4.5 * mm, fill=1, stroke=0)
            c.setFillColor(WHITE); c.setFont("Helvetica-Bold", 4.6)
            c.drawCentredString(rx, ry + 2.6 * mm, lab)

class QRBox(Flowable):
    def __init__(self):
        self.width = self.height = 36 * mm
    def wrap(self, aw, ah): return self.width, self.height
    def draw(self):
        c = self.canv
        c.setFillColor(WHITE); c.setStrokeColor(NAVY); c.rect(0, 0, self.width, self.height, fill=1, stroke=1)
        c.setFillColor(NAVY); n = 9; cell = self.width / n
        for i in range(81):
            if (i * 17 + i // 3) % 7 in (0, 2, 4):
                c.rect((i % n) * cell, self.height - ((i // n) + 1) * cell, cell, cell, fill=1, stroke=0)
        c.setFillColor(CORAL); c.setFont("Helvetica-Bold", 5.2)
        c.drawCentredString(self.width / 2, 3 * mm, "SCAN FOR A LIVE DEMO")

def footer(c, doc):
    c.saveState()
    c.setFillColor(BLUE); c.rect(0, H - 2.6 * mm, W, 2.6 * mm, fill=1, stroke=0)
    c.setFillColor(MUTED); c.setFont("Helvetica", 6.4)
    c.drawString(16 * mm, 7.5 * mm, "EstateHub  •  The Complete Society Management Platform  •  Marketing Brochure v1.0")
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 6.6)
    c.drawRightString(W - 16 * mm, 7.5 * mm, str(doc.page))
    c.restoreState()

doc = SimpleDocTemplate(str(out), pagesize=A4,
                        leftMargin=16 * mm, rightMargin=16 * mm,
                        topMargin=14 * mm, bottomMargin=16 * mm,
                        title="EstateHub — Marketing Brochure", author="EstateHub")
S = []

# ============================ COVER ============================
S += [Spacer(1, 6 * mm),
      P("EstateHub", "CoverT"),
      P("The Complete Society Management Platform", "CoverSub"),
      Spacer(1, 2 * mm),
      Hero(),
      Spacer(1, 5 * mm),
      P("PROFESSIONAL MARKETING BROCHURE", "H2x"),
      P("For Society Administrators, Secretaries & Managing Committee Members", "S"),
      Spacer(1, 4 * mm),
      P("“Stop managing your society. Start leading it.”", "Q"),
      Spacer(1, 6 * mm),
      Table([[Table([[P("Sunrise Residency  •  Uttar Pradesh  •  Demo society", "S")]],
                  colWidths=[USABLE], style=[("ALIGN", (0, 0), (-1, -1), "CENTER")]),
               QRBox()]],
            colWidths=[USABLE - 42 * mm, 42 * mm],
            style=[("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]),
      Spacer(1, 4 * mm),
      P("Contact: ____________________   Email: ______________________", "S"),
      P("Phone: ______________________   Website: ______________________", "S"),
      PageBreak()]

# ============================ 1. EXECUTIVE SUMMARY ============================
S += sect("1", "Executive Summary",
          "Society administration should not depend on manual registers, scattered WhatsApp messages, "
          "Excel workbooks and the memory of one or two committee members.")
S += [P("EstateHub brings the operational back office into one browser-based platform. It combines "
        "automated receivables, double-entry cashbook, bank reconciliation, secure signed QR gate access, "
        "complaints, events, polls, NOCs, assets, reports and resident self-service — all without page reloads."),
      Spacer(1, 3 * mm),
      P("<b>Built for Uttar Pradesh Apartment Owners' Associations</b> (UP Apartment Act, 2010; UP Apartment "
        "Rules, 2011; Model Bye-Laws, 2011), with Central tax laws layered on top. Every statutory threshold is "
        "dated data, not hard-coded, so a change in law is a data row — never a redeploy."),
      Spacer(1, 4 * mm),
      row_of_cards([
        ("50+", "Workflows covered", BLUE),
        ("10", "Role-scoped portals", TEAL),
        ("30 days", "Adoption roadmap", GREEN),
        ("₹2,00,000", "Cash-receipt ceiling enforced", GOLD),
      ], w=42 * mm, h=40 * mm),
      Spacer(1, 5 * mm),
      P("From fragmented work to a controlled workflow", "H2x")]

S += [Table([[P("BEFORE", "TH"), P("WITH APEXESTATEHUB", "TH")],
             [P("WhatsApp reminders and manual follow-up", "TB"),
              P("Dues visible to owners; channels broadcast reminders", "TB")],
             [P("Excel-based bank reconciliation", "TB"),
              P("Exact match → fuzzy match → row-by-row reconciliation", "TB")],
             [P("Paper receipts and cashbook", "TB"),
              P("Receipts, vouchers and month-wise double-entry ledger", "TB")],
             [P("Handwritten gate passes", "TB"),
              P("HMAC-signed, versioned QR passes; camera + NFC scanning", "TB")],
             [P("Complaints buried in chat", "TB"),
              P("Raise → assign → vendor bid → resolve with audit trail", "TB")]],
            colWidths=[76 * mm, 102 * mm],
            style=[("BACKGROUND", (0, 0), (-1, 0), NAVY),
                   ("GRID", (0, 0), (-1, -1), 0.4, CARDL),
                   ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
                   ("VALIGN", (0, 0), (-1, -1), "TOP"),
                   ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                   ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5)])]
S += [Spacer(1, 5 * mm), P("“Stop managing your society. Start leading it.”", "Q"), PageBreak()]

# ============================ 2. THE PAIN LANDSCAPE ============================
S += sect("2", "The Pain Landscape", "A day in the life of Rajesh, Society Secretary, Sunrise Residency (120 flats).")
S += [P("Rajesh is a retired bank manager who volunteered as Secretary. He knows accounts and people — "
        "and still every Monday begins with a fresh pile of unfinished work."), Spacer(1, 3 * mm)]
pain = [("08:30", "Dues chase", "Three owners ask for maintenance balances on WhatsApp. Rajesh checks an old Excel sheet and replies one by one.", TEAL),
        ("10:15", "Bank reconciliation", "A bank statement arrives. He compares rows manually against another workbook, marking possible matches.", BLUE),
        ("12:00", "Gate pass", "A contractor needs access. Rajesh prepares a pass, sends a photo to security and hopes the latest version reaches the gate.", GOLD),
        ("14:30", "Complaints", "Fifteen messages arrive: seepage, lift noise, plumbing, parking. No single queue, owner, deadline or audit trail.", CORAL),
        ("17:00", "Cashbook", "He starts the monthly cashbook. One figure does not agree. He searches paper vouchers and old messages.", GREEN),
        ("19:30", "NOC search", "An owner needs a copy of an NOC issued six months ago. He searches folders, email and WhatsApp.", PURPLE)]
for t, h, b, col in pain:
    S += [Table([[P("<b>" + t + "</b>", "TB"), P("<b>" + h + "</b><br/>" + b, "TB")]],
                colWidths=[22 * mm, 156 * mm],
                style=[("BACKGROUND", (0, 0), (0, 0), PALE),
                       ("BOX", (0, 0), (-1, -1), 0.4, CARDL),
                       ("VALIGN", (0, 0), (-1, -1), "TOP"),
                       ("LEFTPADDING", (0, 0), (-1, -1), 6),
                       ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5)]),
              Spacer(1, 1.6 * mm)]
S += [Spacer(1, 2 * mm), P("He is doing the work. The problem is that the work is scattered.", "Q"),
      Spacer(1, 3 * mm), P("“There has to be a better way.”", "Q"), PageBreak()]

# ============================ 3. ESTATEHUB AT A GLANCE (10 PORTALS) ============================
S += sect("3", "EstateHub at a Glance",
          "Ten role-scoped portals. One operating model. Each login sees only the rows its role is scoped to.")
portals = [
    ("MASTER ADMIN", "Platform operator", "Platform oversight • societies • plans • statutory rule data", PURPLE),
    ("SOCIETY ADMIN", "Secretary / Treasurer / MC", "Dashboard • finance • operations • compliance", BLUE),
    ("APARTMENT OWNER", "Owner / family / tenant", "Dues • concerns • events • gate pass • bills paid", TEAL),
    ("VENDOR", "Service contractor", "Pass status • charges • gate QR • bid on concerns", GOLD),
    ("SECURITY GUARD", "Gate staff", "QR scanner • attendance • gate log • walk-ins", CORAL),
    ("ACCOUNTANT", "Finance preparer", "Receipts • expenses • dues • cashbook • TDS & GST", INDIGO),
    ("SUPERVISOR", "Gate & field oversight", "Gate & security • users • concerns • events", GREEN),
    ("STAFF", "General society staff", "Concerns • events • alert channels", TEAL),
    ("AUDITOR", "Statutory / internal auditor", "Verify checks • books • receipts • financials (read-only)", BLUE),
    ("ADVISER", "CA / Advocate / Auditor", "Appointment-bound masked ledger export", PURPLE),
]
for i in range(0, 10, 2):
    pair = portals[i:i + 2]
    cells = []
    for name, role, desc, col in pair:
        cells.append(Card(name, role + "\\n\\n" + desc, col, 86 * mm, 46 * mm))
    if len(cells) == 1:
        cells.append(Spacer(1, 1))
    colw = (USABLE - 6 * mm) / 2
    for cell in cells:
        cell.width = colw
    S += [Table([cells], colWidths=[colw, colw],
                style=[("VALIGN", (0, 0), (-1, -1), "TOP"),
                       ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6 * mm),
                       ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]),
          Spacer(1, 4 * mm)]
S += [P("Design principle: role-scoped by default. The Admin gets the control plane; residents get self-service; "
        "vendors and guards get focused workflows; the Master Admin gets platform-level management — with no "
        "society-data capability.", "B"), PageBreak()]

# ============================ 4. THE ADMIN PORTAL ============================
S += sect("4", "The Admin Portal", "The committee's operational control room — scoped to one society.")
tabs = [
    ("Dashboard", "Dues, receipts, gate logs and open concerns in KPI cards.", BLUE),
    ("Financials", "Receipts, expenses, receivables, payables, cashbook, ledger.", TEAL),
    ("Bank Reconcile", "CSV/Excel upload; exact + fuzzy matching; row-by-row reconcile.", GREEN),
    ("Enrolled", "Apartments, vendors, security; bulk CSV upload.", GOLD),
    ("Concerns", "Raise → assign → vendor bid → resolve with audit trail.", CORAL),
    ("Events", "Create events, sell tickets, scan QR entry.", TEAL),
    ("Polls", "Create polls, collect owner votes, view results.", GREEN),
    ("Gate Pass", "QR validity, revoke/re-issue, browser NFC writing.", BLUE),
    ("NOC", "Eligibility gate → rich-text editor → print/PDF/email.", TEAL),
    ("Customize", "Drag-and-drop KPI layout + KPI SQL Inspector.", GOLD),
    ("Settings", "Setup Wizard, team logins, QR re-issue, password controls.", CORAL),
    ("UP AOA Compliance", "Bye-law 49 filings, undivided interest, s.22, bye-law 7, owner loans.", GREEN),
]
for i in range(0, len(tabs), 2):
    pair = tabs[i:i + 2]
    cells = [Card(t, b, col, 86 * mm, 36 * mm) for t, b, col in pair]
    if len(cells) == 1:
        cells.append(Spacer(1, 1))
    colw = (USABLE - 6 * mm) / 2
    for cell in cells:
        cell.width = colw
    S += [Table([cells], colWidths=[colw, colw],
                style=[("VALIGN", (0, 0), (-1, -1), "TOP"),
                       ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6 * mm),
                       ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]),
          Spacer(1, 3 * mm)]
S += [PageBreak()]

# ============================ 5. FIVE WORKFLOW BLUEPRINTS ============================
S += sect("5", "Five Workflow Blueprints",
          "System actions are automated where specified; people remain accountable for approvals and governance.")
workflows = [
    ("01  Monthly Dues Collection", "Auto-generates receivables on the 1st → Owner sees dues → Admin sends reminder → Owner pays/disputes → FIFO allocation → SHA-256 receipt → cashbook updated → bank reconciled.", BLUE),
    ("02  Vendor Gate Pass", "Admin creates vendor and validity → Signed QR generated → Vendor downloads pass → Security scans → Entry IN logged → expiry/loss → revoke and re-issue → old QR invalid.", TEAL),
    ("03  Maintenance Complaint", "Owner raises concern → System timestamps → Admin assigns vendor → Vendor submits bid → Admin approves → Work completed → Owner confirms → audit trail closed.", GREEN),
    ("04  NOC Issuance", "Owner requests NOC → System checks zero dues → Admin edits rich-text NOC → Branded document generated → Print/PDF/email delivered. If ineligible, outstanding amount is shown.", GOLD),
    ("05  New Society Onboarding", "First login → Setup Wizard → Society Details → Tax & Compliance → Billing & Accounts → Brought-forward balances → Agreement e-sign → Society goes live.", CORAL),
]
for title, body, col in workflows:
    S += [Card(title, body, col, USABLE, 34 * mm), Spacer(1, 3 * mm)]
S += [P("Demonstrated end-to-end: dues cycle, gate QR scan, concern resolution and NOC issuance follow the "
        "society's real operating workflow.", "S"), PageBreak()]

# ============================ 6. THE FINANCIAL PROMISE ============================
S += sect("6", "The Financial Promise", "Why administrators can trust the workflow behind the numbers.")
fin = [
    ("Double-entry accounting", "Every receipt and expense posts paired Dr/Cr legs; a deferred balance trigger refuses an unbalanced journal at commit.", BLUE),
    ("FIFO allocation", "Oldest dues first; interest cleared before principal; selective Pay Dues settles mixed funds per row.", TEAL),
    ("SHA-256 receipt hashing", "Receipt numbers form a cryptographic hash chain; altering a historical receipt breaks every later link.", GREEN),
    ("Bank reconciliation", "Exact match first, fuzzy match next, then manual row-by-row reconciliation per bank account.", GOLD),
    ("GST / TDS defaults", "GST billed only above the ₹7,500/member and ₹20 lakh turnover gate; effective-dated TDS sections and rates.", CORAL),
    ("One-click reports", "Cashbook, ledger, receivables, receipts, expenses and six financial statements export to CSV/Excel.", BLUE),
]
for i in range(0, 6, 2):
    pair = fin[i:i + 2]
    cells = [Card(a, b, col, 86 * mm, 40 * mm) for a, b, col in pair]
    colw = (USABLE - 6 * mm) / 2
    for cell in cells:
        cell.width = colw
    S += [Table([cells], colWidths=[colw, colw],
                style=[("VALIGN", (0, 0), (-1, -1), "TOP"),
                       ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6 * mm),
                       ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]),
          Spacer(1, 4 * mm)]
S += [Spacer(1, 3 * mm),
      P("“At the AGM, Rajesh projected the cashbook on the hall screen. For the first time in 11 years, "
        "every rupee was accounted for, to the paisa.”", "Q"),
      P("Illustrative testimonial — replace with verified customer evidence before public release.", "S"),
      PageBreak()]

# ============================ 7. STATUTORY COMPLIANCE ============================
S += sect("7", "Statutory Compliance — Built for UP AOAs",
          "Six things the software will not let anyone do — enforced inside the database, so a screen, a bug "
          "or a hurried user cannot get round them.")
compliance = [
    ("Quietly change the books", "Posted ledger lines are immutable; mistakes are corrected only by a visible reversal. A SHA-256 hash chain plus signed anchor certificates filed with the CA make any rewrite show.", TEAL),
    ("Post an unbalanced voucher", "A deferred balance trigger refuses any journal that does not balance. Cash vouchers are provenance- and amount-checked against their source document.", BLUE),
    ("Reopen a locked year", "After year-end close, the Treasurer alone can lock it irreversibly; nothing can be posted into that or any earlier year, and a signed ledger anchor is taken first.", GREEN),
    ("Apply a rule without showing its authority", "53 UP rules carry source text and status (38 checked, 13 provisional, 2 disputed). Rule changes are dated, non-retroactive and audited.", GOLD),
    ("Pass a resolution on a typed number", "Quorum (30% floor) and majority are derived from attendance and vote registers, each flat weighted by undivided interest, measured against all owners — not votes cast.", CORAL),
    ("Hide a tax assumption", "Cash receipts of ₹2,00,000+ from one payer in a day are refused. GST is charged only when turnover clearly exceeds ₹20 lakh and a member's charge exceeds ₹7,500; contested heads are held for the CA.", PURPLE),
]
for i in range(0, 6, 2):
    pair = compliance[i:i + 2]
    cells = [Card(t, b, col, 86 * mm, 46 * mm) for t, b, col in pair]
    colw = (USABLE - 6 * mm) / 2
    for cell in cells:
        cell.width = colw
    S += [Table([cells], colWidths=[colw, colw],
                style=[("VALIGN", (0, 0), (-1, -1), "TOP"),
                       ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6 * mm),
                       ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]),
          Spacer(1, 4 * mm)]
S += [Spacer(1, 2 * mm),
      P("What we do not claim: no return filing, no TRACES/GST e-filing, no Section 80P/80AC computation, no "
        "DPDP certification (parameters marked [Verify]), no e-invoicing, and no automated breach notification. "
        "EstateHub prepares and protects the books — it does not replace the society's CA and advocate.", "S"),
      PageBreak()]

# ============================ 8. SECURITY, PRIVACY & RELIABILITY ============================
S += sect("8", "Security, Privacy & Reliability", "Trust built into every layer — never sourced from the browser.")
sec = [
    ("Signed QR passes", "HMAC-SHA256 signed, versioned passes keyed per society under SECRET_VAULT_KEY; revoke and re-issue invalidates old codes.", BLUE),
    ("Two-actor visitor approval", "Owner confirmation required before visitor admission; the guard cannot approve its own alert.", TEAL),
    ("Anti-spoofing patrol", "GPS geo-fence (50 m) plus travel-speed check (>25 km/h rejected); 60-second expiring epoch QR for attendance.", GREEN),
    ("Role-scoped access", "Explicit capability sets, no wildcards; tenant isolation is a hard deny; platform operators have no society-data capability.", GOLD),
    ("DPDP Act machinery", "Versioned notice gate, purpose-bound consent, rights register (access/correction/erasure/nominee/grievance), breach register, profile-only erasure.", CORAL),
    ("Immutable audit trail", "Actor, role, society, action, before/after values, reason, correlation id and IP — append-only, trigger-guarded, credentials stripped.", PURPLE),
]
for i in range(0, 6, 2):
    pair = sec[i:i + 2]
    cells = [Card(t, b, col, 86 * mm, 42 * mm) for t, b, col in pair]
    colw = (USABLE - 6 * mm) / 2
    for cell in cells:
        cell.width = colw
    S += [Table([cells], colWidths=[colw, colw],
                style=[("VALIGN", (0, 0), (-1, -1), "TOP"),
                       ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6 * mm),
                       ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]),
          Spacer(1, 4 * mm)]
S += [PageBreak()]

# ============================ 9. RESIDENT EXPERIENCE ============================
S += sect("9", "Resident Experience", "Routine queries become self-service — from a phone.")
res = [
    ("Know your dues", "See pending dues, payment history and your own ledger passbook.", TEAL),
    ("Raise a concern", "Submit and track complaints in real time; invite vendors or be assigned directly.", CORAL),
    ("Join events", "Buy tickets and use QR-based venue entry; tickets marked used on scan to prevent double-scan.", GOLD),
    ("Vote in polls", "One vote per apartment, secret ballot, weighted by undivided interest; quorum 30%, majority 51%.", BLUE),
    ("Carry your pass", "Download your personal gate-pass QR; visitor pre-registration and gate alerts.", GREEN),
    ("Control alerts", "Subscribe or unsubscribe from school bus, taxi and visitor broadcast channels.", TEAL),
]
for i in range(0, 6, 2):
    pair = res[i:i + 2]
    cells = [Card(t, b, col, 86 * mm, 40 * mm) for t, b, col in pair]
    colw = (USABLE - 6 * mm) / 2
    for cell in cells:
        cell.width = colw
    S += [Table([cells], colWidths=[colw, colw],
                style=[("VALIGN", (0, 0), (-1, -1), "TOP"),
                       ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6 * mm),
                       ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]),
          Spacer(1, 4 * mm)]
S += [Spacer(1, 4 * mm),
      P("“Earlier I had to call the secretary to find out my maintenance balance. Now I open the app and it's "
        "there — to the paisa, with every payment history.”", "Q"),
      P("— Priya Sharma, Flat A-203, Sunrise Residency (illustrative)", "S"), PageBreak()]

# ============================ 10. ADOPTION ROADMAP ============================
S += sect("10", "Adoption Roadmap", "From paper to platform in 30 days.")
S += [Table([[P("WEEK", "TH"), P("ACTION", "TH"), P("TOOLS", "TH")],
             [P("1", "TB"), P("Society details, logo and signing setup", "TB"), P("Setup Wizard • Image upload", "TB")],
             [P("2", "TB"), P("Bulk enrol apartments, vendors and security (XLSX)", "TB"), P("Bulk CSV enrol", "TB")],
             [P("3", "TB"), P("Issue QR passes; onboard security; invite owners", "TB"), P("QR modal • Security portal", "TB")],
             [P("4", "TB"), P("Generate receivables; verify cashbook; issue NOC", "TB"), P("Financial engine • NOC", "TB")],
             [P("ONGOING", "TB"), P("Reconcile statements; export AGM reports", "TB"), P("Bank reconcile • Reports", "TB")]],
            colWidths=[24 * mm, 100 * mm, 54 * mm],
            style=[("BACKGROUND", (0, 0), (-1, 0), NAVY),
                   ("GRID", (0, 0), (-1, -1), 0.4, CARDL),
                   ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
                   ("VALIGN", (0, 0), (-1, -1), "TOP"),
                   ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                   ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5)])]
S += [Spacer(1, 7 * mm), P("“From Day 30 onwards, EstateHub runs the back-office. The Secretary runs the society.”", "Q"),
      PageBreak()]

# ============================ 11. PLANS & CALL TO ACTION ============================
S += sect("11", "Plans & Call to Action", "Simple, society-sized pricing. Every plan includes role-scoped portals, "
                                          "signed QR gate access and the full statutory engine.")
S += [Table([[P("STARTER", "TH"), P("PROFESSIONAL", "TH"), P("ENTERPRISE", "TH")],
             [P("<b>₹ TBD</b><br/>Smaller communities<br/><br/>Core administration<br/>Resident self-service", "TB"),
              P("<b>₹ TBD</b><br/>Growing societies<br/><br/>Financial workflows<br/>Gate + concerns + reports", "TB"),
              P("<b>₹ TBD</b><br/>Portfolios / operators<br/><br/>Multi-society management<br/>Advanced controls", "TB")]],
            colWidths=[58 * mm] * 3,
            style=[("BACKGROUND", (0, 0), (-1, 0), NAVY),
                   ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#CDD9E5")),
                   ("VALIGN", (0, 0), (-1, -1), "TOP"),
                   ("LEFTPADDING", (0, 0), (-1, -1), 7),
                   ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)])]
S += [Spacer(1, 7 * mm), P("Request a live demonstration", "H2x"),
      P("See the Admin dashboard, run a sample dues cycle, scan a gate QR, raise a concern and issue an NOC. "
        "The demonstration can follow your society's real operating workflow."),
      Spacer(1, 6 * mm),
      Table([[QRBox(), P("<b>Scan to request a live demo</b><br/><br/>Contact: ____________________<br/>Email: ______________________<br/>Phone: ______________________<br/>Website: ______________________", "B")]],
            colWidths=[46 * mm, 132 * mm],
            style=[("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)])]
S += [Spacer(1, 6 * mm), P("“Stop managing your society. Start leading it.”", "Q"), PageBreak()]

# ============================ 12. FAQ ============================
S += sect("12", "Frequently Asked Questions", "Straight answers for committees evaluating the platform.")
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
for q, a in faqs:
    S += [P(q, "H2x"), P(a, "B")]
S += [Spacer(1, 3 * mm),
      P("Marketing claims, pricing, metrics and testimonials marked as placeholders should be verified before "
        "commercial publication.", "S")]

doc.build(S, onFirstPage=footer, onLaterPages=footer)
print(f"Created: {out}")
print(f"File size: {out.stat().st_size/1024:.1f} KB")
