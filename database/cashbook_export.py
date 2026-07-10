# database/cashbook_export.py
"""
Cashbook Excel Generator — EstateHub
======================================
Produces the traditional paired Indian society cashbook (month-wise).

Column layout (A–O):
  A  Date (receipt side)
  B  Receipt A/c name       (accounts.tab_name)
  C  Receipt Particulars    (acc_particulars + payment_gateway_id)
  D  Receipt L.F. No.       (ledger folio = accounts.id)
  E  Receipt Cash           (mode='cash' → Cr amount)
  F  Receipt Chq/UPI        (mode≠'cash' → Cr amount, informational only)
  G  Receipt Running Total  (running sum of col E — cash receipts only)
  H  Date (payment side)
  I  Payment A/c name       (accounts.tab_name)
  J  Payment Particulars    (acc_particulars + payment_gateway_id)
  K  Payment L.F. No.       (accounts.id)
  L  Payment Cash           (mode='cash' → Dr amount)
  M  Payment Chq            (mode≠'cash' → Dr amount, informational)
  N  Payment Running Total  (running sum of col L — cash payables only)
  O  Balance                (= G − N, physical cash in hand)

Row structure:
  Row 1: blank
  Row 2: A2=filename, C2=society_name, E2='Society', F2='CASHBOOK', G2='PAN:', H2=PAN,
          J2='Asst.Yr.', K2=year_range, L2='Month', M2=month_abbrev
  Row 3: blank
  Row 4: Column headers
  Row 5: B/F balance row (Balance B/F from accounts.bf_amount sum)
  Row 6+: Data rows (receipt side / payment side, odd side left blank)
  Last:  C/F row (Balance C/F, closing cash → payment side)

Balance formulas (in O column):
  O5  =E5-L5                       ← first data row
  O6  =O5+E6-L6                    ← subsequent rows

G formula:
  G5  =E5
  G6  =G5+E6                       ← running cash receipt total

N formula:
  N5  =L5
  N6  =N5+L6                       ← running cash payment total

The C/F row's L value = O_{last_data_row} (cash carried forward), making N_cf = N_prev + O_prev
so that G_total = N_cf (both sides foot).
"""

from __future__ import annotations
import io
from datetime import date, datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, numbers
)
from openpyxl.utils import get_column_letter


# ── Style constants ──────────────────────────────────────────────────────
_FONT_BODY   = Font(name="Arial", size=9)
_FONT_HEADER = Font(name="Arial", size=9, bold=True)
_FONT_TITLE  = Font(name="Arial", size=10, bold=True)
_FONT_BF_CF  = Font(name="Arial", size=9, bold=True, italic=True)

_FILL_HEADER  = PatternFill("solid", fgColor="D9E1F2")   # light blue
_FILL_BF      = PatternFill("solid", fgColor="E2EFDA")   # light green
_FILL_CF      = PatternFill("solid", fgColor="FCE4D6")   # light orange
_FILL_ALT     = PatternFill("solid", fgColor="F7F7F7")   # alternating row

_ALIGN_C  = Alignment(horizontal="center", vertical="center")
_ALIGN_L  = Alignment(horizontal="left",   vertical="center")
_ALIGN_R  = Alignment(horizontal="right",  vertical="center")

_THIN = Side(style="thin")
_THICK = Side(style="medium")
_BORDER_ALL   = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_BORDER_THICK = Border(left=_THICK, right=_THICK, top=_THICK, bottom=_THICK)

_FMT_DATE  = "DD-MMM-YY"
_FMT_AMT   = '#,##0.00;[Red](#,##0.00);"-"'
_FMT_AMT0  = '#,##0;[Red](#,##0);"-"'

# Column widths (A=1 … O=15)
_COL_WIDTHS = {
    "A": 10, "B": 10, "C": 28, "D":  6,
    "E":  9, "F":  9, "G": 10,
    "H": 10, "I": 10, "J": 28, "K":  6,
    "L":  9, "M":  9, "N": 10, "O": 10,
}

# Separator column between receipt and payment halves (thin right border on G)
_DIVIDER_COL = 7   # column G (1-indexed)


def _style_cell(cell, font=None, fill=None, align=None, border=None, fmt=None):
    if font:   cell.font      = font
    if fill:   cell.fill      = fill
    if align:  cell.alignment = align
    if border: cell.border    = border
    if fmt:    cell.number_format = fmt


def _write_row(ws, row_idx: int, values: dict[int, Any], style: dict = None):
    """Write a dict of {col_idx: value} into a row, applying optional shared style."""
    style = style or {}
    for col, val in values.items():
        cell = ws.cell(row=row_idx, column=col, value=val)
        _style_cell(cell,
                    font=style.get("font"),
                    fill=style.get("fill"),
                    align=style.get("align"),
                    fmt=style.get("fmt"))
        cell.border = style.get("border", _BORDER_ALL)


def generate_cashbook_excel(
    db,
    society_id: int,
    month: int,       # 1–12
    year: int,
    filename_prefix: str = "Cashbook",
) -> bytes:
    """
    Query fn_cashbook_paired for the given month/year and produce
    an .xlsx cashbook in the traditional paired format.

    Returns raw bytes (ready to stream with dcc.send_bytes).
    """
    from database.db_manager import db as _db
    if db is None:
        db = _db

    # ── 1. Load society meta ──────────────────────────────────────────────
    soc = db._execute(
        "SELECT name, pan_number, calc_start_date FROM societies WHERE id=%s",
        (society_id,), fetch_one=True,
    ) or {}
    society_name = soc.get("name", "Society")
    pan          = soc.get("pan_number", "")
    calc_start   = soc.get("calc_start_date", date(year, 4, 1))
    asst_year    = f"{year}-{year+1}"

    # ── 2. Opening balance = sum of all Cr BF − all Dr BF ────────────────
    bf_row = db._execute(
        "SELECT COALESCE(SUM(CASE WHEN drcr_bf='Cr' THEN bf_amount ELSE -bf_amount END),0) AS bf "
        "FROM accounts WHERE society_id=%s AND has_bf=TRUE",
        (society_id,), fetch_one=True,
    ) or {}
    opening_balance = float(bf_row.get("bf", 0))

    # ── 3. Pull cashbook data for the month ───────────────────────────────
    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year + 1, 1, 1)
    else:
        month_end = date(year, month + 1, 1)

    # fn_cashbook_paired returns paired rows sorted by date
    rows = db._execute(
        "SELECT * FROM fn_cashbook_paired(%s, NULL, NULL, NULL, %s, %s)",
        (society_id, month_start, month_end),
        fetch_all=True,
    ) or []

    # ── 4. Build the workbook ─────────────────────────────────────────────
    wb = Workbook()
    ws = wb.active
    ws.title = date(year, month, 1).strftime("%b")

    # Set column widths
    for col_letter, width in _COL_WIDTHS.items():
        ws.column_dimensions[col_letter].width = width

    # ── Row 1: blank ─────────────────────────────────────────────────────
    ws.row_dimensions[1].height = 6

    # ── Row 2: Title header ───────────────────────────────────────────────
    filename = f"{filename_prefix}_{year}-{year+1}.xlsx"
    month_abbrev = date(year, month, 1).strftime("%b")

    title_data = {
        1: filename,            # A2
        3: society_name,        # C2
        5: "Society",           # E2
        6: "CASHBOOK",          # F2
        7: "PAN:",              # G2
        8: pan,                 # H2
        10: "Asst.Yr.",         # J2
        11: asst_year,          # K2
        12: "Month",            # L2
        13: month_abbrev,       # M2
    }
    for col, val in title_data.items():
        cell = ws.cell(row=2, column=col, value=val)
        cell.font      = _FONT_TITLE
        cell.alignment = _ALIGN_C

    # ── Row 3: blank ─────────────────────────────────────────────────────
    ws.row_dimensions[3].height = 6

    # ── Row 4: Column headers ─────────────────────────────────────────────
    headers = {
        1: "Date",        2: "Receipt A/c",      3: "Receipt Particulars",
        4: "L.F.",        5: "Cash",              6: "Chq./UPI",
        7: "Total",
        8: "Date",        9: "Payment A/c",       10: "Payment Particulars",
        11: "L.F.",       12: "Cash",             13: "Chq.",
        14: "Total",      15: "Balance",
    }
    for col, hdr in headers.items():
        cell = ws.cell(row=4, column=col, value=hdr)
        _style_cell(cell, font=_FONT_HEADER, fill=_FILL_HEADER,
                    align=_ALIGN_C, border=_BORDER_ALL)

    # ── Row 5: Balance B/F ───────────────────────────────────────────────
    bf_date = month_start
    bf_values = {
        1: bf_date,        # A5
        2: "Balance",      # B5
        3: "B/F",          # C5
        5: opening_balance if opening_balance >= 0 else None,   # E5 cash receipt
        12: abs(opening_balance) if opening_balance < 0 else None,  # L5 cash payment
    }
    for col, val in bf_values.items():
        cell = ws.cell(row=5, column=col, value=val)
        _style_cell(cell, font=_FONT_BF_CF, fill=_FILL_BF,
                    align=_ALIGN_R if col in (5,6,7,12,13,14,15) else _ALIGN_L,
                    border=_BORDER_ALL,
                    fmt=_FMT_DATE if col in (1,8) else (_FMT_AMT if col in (5,6,7,12,13,14,15) else None))

    # G5 = E5 (running receipt total initialised from B/F)
    ws.cell(row=5, column=7).value  = f"=E5"
    ws.cell(row=5, column=7).number_format = _FMT_AMT
    ws.cell(row=5, column=7).font   = _FONT_BF_CF
    ws.cell(row=5, column=7).fill   = _FILL_BF
    ws.cell(row=5, column=7).border = _BORDER_ALL
    ws.cell(row=5, column=7).alignment = _ALIGN_R
    # N5 = L5 (running payment total initialised from B/F payment side, usually 0)
    ws.cell(row=5, column=14).value = f"=L5"
    ws.cell(row=5, column=14).number_format = _FMT_AMT
    ws.cell(row=5, column=14).font   = _FONT_BF_CF
    ws.cell(row=5, column=14).fill   = _FILL_BF
    ws.cell(row=5, column=14).border = _BORDER_ALL
    ws.cell(row=5, column=14).alignment = _ALIGN_R
    # O5 = G5 - N5
    ws.cell(row=5, column=15).value = f"=G5-N5"
    ws.cell(row=5, column=15).number_format = _FMT_AMT
    ws.cell(row=5, column=15).font   = _FONT_BF_CF
    ws.cell(row=5, column=15).fill   = _FILL_BF
    ws.cell(row=5, column=15).border = _BORDER_ALL
    ws.cell(row=5, column=15).alignment = _ALIGN_R

    # ── Rows 6+: Data rows ───────────────────────────────────────────────
    current_row = 6

    def _particulars(row_dict: dict, prefix: str = "") -> str:
        """Concatenate particulars + payment gateway id if present."""
        p   = (row_dict.get(f"{prefix}particulars") or "").strip()
        gw  = (row_dict.get(f"{prefix}cheque_no") or "").strip()  # payment_gateway_id stored here
        return f"{p} [{gw}]" if gw else p

    for i, r in enumerate(rows):
        fill = _FILL_ALT if i % 2 == 0 else None

        # ── Receipt side (Cr) ─────────────────────────────────────────────
        rc_date  = r.get("rc_trx_date")
        rc_acc   = r.get("rc_account_name") or ""
        rc_part  = _particulars(r, "rc_")
        rc_lf    = r.get("rc_id")             # cashbook row → ledger folio
        rc_amt   = float(r.get("rc_amount") or 0)
        rc_mode  = (r.get("rc_mode") or "cash").lower()
        rc_cash  = rc_amt if rc_mode == "cash" else None
        rc_chq   = rc_amt if rc_mode != "cash" else None

        # ── Payment side (Dr) ─────────────────────────────────────────────
        pc_date  = r.get("pc_trx_date")
        pc_acc   = r.get("pc_account_name") or ""
        pc_part  = _particulars(r, "pc_")
        pc_lf    = r.get("pc_id")
        pc_amt   = float(r.get("pc_amount") or 0)
        pc_mode  = (r.get("pc_mode") or "cash").lower()
        pc_cash  = pc_amt if pc_mode == "cash" else None
        pc_chq   = pc_amt if pc_mode != "cash" else None

        row_data = {
            1:  rc_date or None,
            2:  rc_acc  or None,
            3:  rc_part or None,
            4:  rc_lf   or None,
            5:  rc_cash,
            6:  rc_chq,
            8:  pc_date or None,
            9:  pc_acc  or None,
            10: pc_part or None,
            11: pc_lf   or None,
            12: pc_cash,
            13: pc_chq,
        }

        for col, val in row_data.items():
            cell = ws.cell(row=current_row, column=col, value=val)
            cell.font   = _FONT_BODY
            cell.fill   = fill or PatternFill()
            cell.border = _BORDER_ALL
            align = _ALIGN_R if col in (5, 6, 12, 13) else _ALIGN_L
            cell.alignment = align
            if col in (1, 8) and val:
                cell.number_format = _FMT_DATE
            elif col in (5, 6, 12, 13):
                cell.number_format = _FMT_AMT

        # Running totals as Excel formulas (G, N, O)
        prev = current_row - 1
        for col, formula in [
            (7,  f"=G{prev}+IF(E{current_row}<>\"\",E{current_row},0)"),
            (14, f"=N{prev}+IF(L{current_row}<>\"\",L{current_row},0)"),
            (15, f"=G{current_row}-N{current_row}"),
        ]:
            cell = ws.cell(row=current_row, column=col, value=formula)
            cell.font   = _FONT_BODY
            cell.fill   = fill or PatternFill()
            cell.border = _BORDER_ALL
            cell.alignment = _ALIGN_R
            cell.number_format = _FMT_AMT

        current_row += 1

    # ── C/F row ───────────────────────────────────────────────────────────
    cf_row = current_row
    prev   = cf_row - 1

    ws.cell(row=cf_row, column=8,  value=month_start.replace(day=28))   # H - end of month date approx
    ws.cell(row=cf_row, column=9,  value="Balance")                      # I
    ws.cell(row=cf_row, column=10, value="C/F")                          # J
    # L = closing cash balance = O{prev}
    ws.cell(row=cf_row, column=12, value=f"=O{prev}")                    # L
    # G stays the same (no more receipts)
    ws.cell(row=cf_row, column=7,  value=f"=G{prev}")                    # G
    # N = N_prev + C/F cash (so both sides total equal)
    ws.cell(row=cf_row, column=14, value=f"=N{prev}+L{cf_row}")          # N
    # O = G - N = 0 (balanced)
    ws.cell(row=cf_row, column=15, value=f"=G{cf_row}-N{cf_row}")        # O

    for col in [7, 8, 9, 10, 12, 14, 15]:
        cell = ws.cell(row=cf_row, column=col)
        cell.font   = _FONT_BF_CF
        cell.fill   = _FILL_CF
        cell.border = _BORDER_ALL
        cell.alignment = _ALIGN_R if col not in (9, 10) else _ALIGN_L
        if col in (7, 12, 14, 15):
            cell.number_format = _FMT_AMT

    # Also stamp blank cells on receipt side of C/F row with fills
    for col in [1, 2, 3, 4, 5, 6]:
        cell = ws.cell(row=cf_row, column=col)
        if not cell.value:
            cell.value = None
        cell.font   = _FONT_BODY
        cell.fill   = _FILL_CF
        cell.border = _BORDER_ALL

    # ── Freeze panes below header row ─────────────────────────────────────
    ws.freeze_panes = "A5"

    # ── Output ────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
