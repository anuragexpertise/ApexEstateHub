# app/utils/fiscal.py
"""Indian financial-year helpers (FY runs 1 April - 31 March). Audit finding A8."""
from __future__ import annotations

from datetime import date


def fy_start_year(today: date | None = None) -> int:
    """Calendar year in which the financial year containing `today` starts."""
    today = today or date.today()
    return today.year if today.month >= 4 else today.year - 1


def fy_start_date(today: date | None = None) -> date:
    """1 April of the current financial year."""
    return date(fy_start_year(today), 4, 1)
