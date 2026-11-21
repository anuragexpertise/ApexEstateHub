"""Chart-of-accounts → ICAI statement mapping (pure, no database, no Dash).

Maps every account to the ICAI statement section it rolls up into, based on
its root (1000 Assets, 2000 Liabilities, 3000 Equity/Funds, 4000 Income,
5000 Expenditure). Used by app/services/icai_statements.py to classify
fn_trial_balance_fy / fn_balance_sheet_fy rows into the statutory
statements (Balance Sheet, Income & Expenditure, Receipts & Payments).
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
