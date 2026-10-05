# app/security/plan_guard.py
"""
Society plan-validity guard (audit finding A13).

`societies.plan_validity` was shown in dashboards and could be set to
yesterday by Master ("expire society"), but nothing ever checked it, so an
expired society kept working. This is the ONE definition of "plan expired",
mirroring how the society list already labels status:

    plan = 'Free'                       -> never expires (status "Free")
    plan_validity >= today              -> Active
    otherwise                           -> Expired

On top of that, PLAN_GRACE_DAYS (env, default 7) keeps an expired society
usable for a few days so a renewal that is a day late does not lock out gate
guards and residents at midnight. Set PLAN_GRACE_DAYS=0 for a hard cut-off.

Master has no society, so it is never affected (falsy society_id -> False).
"""
from __future__ import annotations

import os

DEFAULT_GRACE_DAYS = 7

PLAN_EXPIRED_MESSAGE = (
    "This society's EstateHub plan has expired. Please ask your society "
    "administrator to renew the plan."
)


def grace_days() -> int:
    try:
        return max(int(os.getenv("PLAN_GRACE_DAYS", DEFAULT_GRACE_DAYS)), 0)
    except (TypeError, ValueError):
        return DEFAULT_GRACE_DAYS


def society_plan_expired(society_id) -> bool:
    """True if this society's paid plan ran out (beyond the grace period)."""
    if not society_id:
        return False
    from database.db_manager import db
    row = db._execute(
        "SELECT (plan <> 'Free' AND plan_validity + :g < CURRENT_DATE) AS expired "
        "FROM societies WHERE id = :sid",
        {"sid": society_id, "g": grace_days()},
        fetch_one=True,
    )
    return bool((row or {}).get("expired"))
