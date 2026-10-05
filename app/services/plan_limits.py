# app/services/plan_limits.py
"""
Single source of truth for plan apartment caps (audit finding A3).

The cap used to live only in the single-add handler (drilldown_callbacks,
step 6c); Bulk Enroll never checked it. Both paths now call remaining_apartment_slots().
"""
from __future__ import annotations

import logging

from database.db_manager import db

log = logging.getLogger(__name__)

PLAN_APARTMENT_LIMITS = {"Free": 9, "9Apts": 9, "99Apts": 99, "999Apts": 999, "unlimited": 9999}
DEFAULT_APARTMENT_LIMIT = 9


def apartment_limit(plan: str | None) -> int:
    return PLAN_APARTMENT_LIMITS.get(plan or "Free", DEFAULT_APARTMENT_LIMIT)


def remaining_apartment_slots(society_id: int) -> tuple[int, str, int]:
    """Return (slots_left, plan_name, limit) for a society. slots_left is never negative."""
    row = db._execute("SELECT plan FROM societies WHERE id = %s", (society_id,), fetch_one=True)
    plan = (row or {}).get("plan") or "Free"
    count_row = db._execute(
        "SELECT COUNT(*) AS c FROM apartments WHERE society_id = %s", (society_id,), fetch_one=True
    )
    count = (count_row or {}).get("c", 0) or 0
    limit = apartment_limit(plan)
    return max(limit - count, 0), plan, limit
