"""Chart-of-accounts → ICAI statement mapping (pure, no database, no Dash).

Maps every account to the ICAI statement section it rolls up into, based on
its root (1000 Assets, 2000 Liabilities, 3000 Equity/Funds, 4000 Income,
5000 Expenditure). Used by app/services/icai_statements.py to classify
fn_trial_balance_fy / fn_balance_sheet_fy rows into the statutory
statements (Balance Sheet, Income & Expenditure, Receipts & Payments).

`R1_LINE` maps **every** account id in ``database.seed.ACCOUNTS`` to exactly
one balance-sheet or income-and-expenditure statement line. Contra lines
(accumulated depreciation, provision for doubtful debts) present as "less"
lines inside their asset group, never as a separate asset.
"""

from __future__ import annotations

from typing import Dict

# root id → ICAI statement section
ROOT_STATEMENT_SECTION = {
    1000: "Assets",
    2000: "Liabilities",
    3000: "Equity",
    4000: "Income",
    5000: "Expenditure",
}

# Contra / memo accounts that present on the opposite side of their section.
CONTRA_ACCOUNTS = {1190, 1530}

# Fixed-asset (gross) accounts netted against accumulated depreciation (1190)
# inside "Property, plant and equipment".
PPE_GROSS_ACCOUNTS = {1110, 1120, 1130, 1140, 1150, 1160, 1170}
ACCUM_DEPRECIATION = 1190

# Trade receivables (gross) netted against provision for doubtful debts (1530).
TRADE_RECEIVABLES_GROSS = {1500, 1510, 1520}
PROVISION_DOUBTFUL_DEBTS = 1530


def section_for_account(account_id: int) -> str:
    """Return the ICAI statement section for an account id by its root.

    ``account_id`` may itself be a root. Unknown accounts → "Unknown".
    """
    root = account_id // 1000 * 1000
    return ROOT_STATEMENT_SECTION.get(root, "Unknown")


def is_contra(account_id: int) -> bool:
    return account_id in CONTRA_ACCOUNTS


def statement_sections() -> Dict[int, str]:
    """Full account-id → statement-section mapping for the seeded chart.

    Populated from database.seed.ACCOUNTS so it stays in sync with the chart.
    Each account rolls up to the statement section of its top-level root.
    """
    from database.seed import ACCOUNTS  # noqa: WPS433 (import inside function)

    by_id = {row[0]: row for row in ACCOUNTS}

    def root_of(aid: int) -> int:
        cur = aid
        seen = {aid}
        while cur is not None and cur in by_id:
            parent = by_id[cur][4]
            if parent is None or parent in seen:
                return cur
            seen.add(parent)
            cur = parent
        return cur

    mapping: Dict[int, str] = {}
    for row in ACCOUNTS:
        aid = row[0]
        root = root_of(aid)
        mapping[aid] = ROOT_STATEMENT_SECTION.get(root, "Unknown")
    return mapping


# ────────────────────────────────────────────────────────────────────────────
# R1_LINE: every account id → exactly one statement line
# ────────────────────────────────────────────────────────────────────────────

# account id → statement line. Every id in database.seed.ACCOUNTS appears as a
# key exactly once; several ids may share the same line (e.g. the fixed-asset
# leaves all roll up to "Property, plant and equipment").
R1_LINE: Dict[int, str] = {
    # ── Roots / headers ──
    1: "Balance Sheet",
    1000: "Assets",
    1100: "Property, plant and equipment",
    1300: "Current assets",
    1400: "Loans and advances given",
    1500: "Trade receivables",
    2000: "Liabilities",
    2100: "Non-current liabilities",
    2200: "Current liabilities",
    3000: "Equity",
    3100: "Capital account",
    3200: "Reserves and funds",
    4000: "Income",
    4100: "Income from other sources",
    4200: "Member contributions",
    5000: "Expenses",
    5100: "Expenditure account",
    # ── Fixed assets (Property, plant and equipment) ──
    1110: "Property, plant and equipment",
    1120: "Furniture and fixtures",
    1130: "Instruments and tools",
    1140: "Machinery",
    1150: "Vehicles",
    1160: "Computers",
    1170: "Generator",
    1190: "Less: accumulated depreciation",
    1200: "Non-current investments",
    # ── Current assets ──
    1310: "Bank accounts",
    1311: "Bank: SBI",
    1312: "Bank: ICICI",
    1320: "Deposits",
    1330: "Cash-in-hand",
    1340: "Input tax credit (RCM)",
    1350: "TDS and advance tax receivable",
    1360: "Interest accrued on deposits",
    1370: "Prepaid expenses",
    1410: "Loans to owners",
    1510: "Sundry debtors (digital)",
    1520: "Sundry debtors (cash)",
    1530: "Less: provision for doubtful debts",
    # ── Liabilities ──
    2110: "Loans and advances taken",
    2120: "Long-term provisions",
    2210: "CGST payable",
    2220: "SGST payable",
    2230: "CGST payable (RCM)",
    2231: "SGST payable (RCM)",
    2232: "IGST payable (RCM)",
    2240: "Sundry creditors",
    2250: "Provisions",
    2255: "Provision for income tax",
    2260: "Outstanding expenses",
    2270: "Advance maintenance from members",
    2280: "Deposits received",
    2290: "TDS payable",
    2295: "Statutory dues payable",
    # ── Equity / reserves & funds ──
    3210: "Sinking fund reserve",
    3220: "Repair and maintenance fund reserve",
    3230: "Corpus fund",
    3240: "Earmarked gifts fund",
    3270: "Major repair fund (transfer fee)",
    3280: "Depreciation fund",
    3300: "Accumulated surplus / (deficit)",
    # ── Income ──
    4110: "Interest income",
    4111: "Bank interest",
    4112: "Saving interest",
    4113: "FD interest",
    4114: "Exempt income",
    4115: "Maintenance due interest",
    4116: "Interest on owner loans",
    4120: "Profit on sale of assets",
    4130: "Property income",
    4140: "Donations and gifts received",
    4210: "Society maintenance charge",
    4220: "Society fine",
    4230: "Society charge",
    4240: "Event ticket",
    4241: "Holi ticket",
    4242: "Diwali ticket",
    # ── Expenditure ──
    5110: "Depreciation",
    5111: "Staff PF/ESI and welfare",
    5120: "Rent paid",
    5130: "Miscellaneous",
    5140: "Vehicle expenditure",
    5150: "Salary",
    5160: "Phone charges",
    5170: "Electricity",
    5180: "Water tax",
    5190: "House tax",
    5101: "Insurance paid",
    5102: "Repair and maintenance",
    5103: "Stationery",
    5104: "Generator charges",
    5105: "Accountant fee",
    5106: "Audit fee",
    5107: "Lift AMC",
    5108: "Intercom AMC",
    5109: "CCTV AMC",
    5115: "Interest on borrowings",
    5116: "Bank charges",
    5117: "Legal and professional",
    5118: "Security services",
    5119: "Housekeeping and gardening",
    5121: "Event expenses",
    5122: "Bad debts",
    5123: "Loss on sale of assets",
    5124: "Penalties and late fees",
    5195: "GST on asset disposal",
    5196: "Gifts given",
    5200: "Duties paid",
    5210: "Taxes paid",
    5220: "Income tax",
}

# statement line → ICAI statement section. Every line in R1_LINE must appear
# here with a known section.
LINE_SECTION: Dict[str, str] = {
    "Balance Sheet": "Assets",
    "Assets": "Assets",
    "Property, plant and equipment": "Assets",
    "Furniture and fixtures": "Assets",
    "Instruments and tools": "Assets",
    "Machinery": "Assets",
    "Vehicles": "Assets",
    "Computers": "Assets",
    "Generator": "Assets",
    "Less: accumulated depreciation": "Assets",
    "Non-current investments": "Assets",
    "Current assets": "Assets",
    "Bank accounts": "Assets",
    "Bank: SBI": "Assets",
    "Bank: ICICI": "Assets",
    "Deposits": "Assets",
    "Cash-in-hand": "Assets",
    "Input tax credit (RCM)": "Assets",
    "TDS and advance tax receivable": "Assets",
    "Interest accrued on deposits": "Assets",
    "Prepaid expenses": "Assets",
    "Loans and advances given": "Assets",
    "Loans to owners": "Assets",
    "Trade receivables": "Assets",
    "Sundry debtors (digital)": "Assets",
    "Sundry debtors (cash)": "Assets",
    "Less: provision for doubtful debts": "Assets",
    "Liabilities": "Liabilities",
    "Non-current liabilities": "Liabilities",
    "Current liabilities": "Liabilities",
    "Loans and advances taken": "Liabilities",
    "Long-term provisions": "Liabilities",
    "CGST payable": "Liabilities",
    "SGST payable": "Liabilities",
    "CGST payable (RCM)": "Liabilities",
    "SGST payable (RCM)": "Liabilities",
    "IGST payable (RCM)": "Liabilities",
    "Sundry creditors": "Liabilities",
    "Provisions": "Liabilities",
    "Provision for income tax": "Liabilities",
    "Outstanding expenses": "Liabilities",
    "Advance maintenance from members": "Liabilities",
    "Deposits received": "Liabilities",
    "TDS payable": "Liabilities",
    "Statutory dues payable": "Liabilities",
    "Equity": "Equity",
    "Capital account": "Equity",
    "Reserves and funds": "Equity",
    "Sinking fund reserve": "Equity",
    "Repair and maintenance fund reserve": "Equity",
    "Corpus fund": "Equity",
    "Earmarked gifts fund": "Equity",
    "Major repair fund (transfer fee)": "Equity",
    "Depreciation fund": "Equity",
    "Accumulated surplus / (deficit)": "Equity",
    "Income": "Income",
    "Income from other sources": "Income",
    "Interest income": "Income",
    "Bank interest": "Income",
    "Saving interest": "Income",
    "FD interest": "Income",
    "Exempt income": "Income",
    "Maintenance due interest": "Income",
    "Interest on owner loans": "Income",
    "Profit on sale of assets": "Income",
    "Property income": "Income",
    "Donations and gifts received": "Income",
    "Member contributions": "Income",
    "Society maintenance charge": "Income",
    "Society fine": "Income",
    "Society charge": "Income",
    "Event ticket": "Income",
    "Holi ticket": "Income",
    "Diwali ticket": "Income",
    "Expenses": "Expenditure",
    "Expenditure account": "Expenditure",
    "Depreciation": "Expenditure",
    "Staff PF/ESI and welfare": "Expenditure",
    "Rent paid": "Expenditure",
    "Miscellaneous": "Expenditure",
    "Vehicle expenditure": "Expenditure",
    "Salary": "Expenditure",
    "Phone charges": "Expenditure",
    "Electricity": "Expenditure",
    "Water tax": "Expenditure",
    "House tax": "Expenditure",
    "Insurance paid": "Expenditure",
    "Repair and maintenance": "Expenditure",
    "Stationery": "Expenditure",
    "Generator charges": "Expenditure",
    "Accountant fee": "Expenditure",
    "Audit fee": "Expenditure",
    "Lift AMC": "Expenditure",
    "Intercom AMC": "Expenditure",
    "CCTV AMC": "Expenditure",
    "Interest on borrowings": "Expenditure",
    "Bank charges": "Expenditure",
    "Legal and professional": "Expenditure",
    "Security services": "Expenditure",
    "Housekeeping and gardening": "Expenditure",
    "Event expenses": "Expenditure",
    "Bad debts": "Expenditure",
    "Loss on sale of assets": "Expenditure",
    "Penalties and late fees": "Expenditure",
    "GST on asset disposal": "Expenditure",
    "Gifts given": "Expenditure",
    "Duties paid": "Expenditure",
    "Taxes paid": "Expenditure",
    "Income tax": "Expenditure",
}

KNOWN_SECTIONS = {"Assets", "Liabilities", "Equity", "Income", "Expenditure"}


def line_for_account(account_id: int) -> str | None:
    """Return the R1_LINE statement line for an account id, or None."""
    return R1_LINE.get(account_id)


def section_for_line(line: str) -> str:
    """Return the statement section for an R1_LINE statement line."""
    return LINE_SECTION.get(line, "Unknown")
