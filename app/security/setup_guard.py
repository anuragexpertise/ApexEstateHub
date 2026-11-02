# app/security/setup_guard.py
"""
Society setup-completion guard.

V5: the single source of truth for "is a society ready to operate?" is
`societies.onboarding_state`. A society that is not `active` cannot post
receipts, expenses or journals, generate bills, or log in a resident.

`societies.stepup_password_hash` is kept as a legacy column (it still
confirms sensitive step-up actions such as QR re-issue and key rotation) but
it is no longer the "setup complete" flag.

- 'registered'      — society created; founding committee not yet seated
- 'committee seated'— President, Secretary, Treasurer seated (V5.3)
- 'setup draft'     — Setup Wizard two-phase draft saved, posts nothing (V5.4)
- 'active'          — Agreement sealed, opening journal posted, anchor taken (V5.7)
- 'suspended'       — administratively suspended; posting blocked

Anything that needs to know should call society_setup_incomplete(society_id)
instead of querying stepup_password_hash or onboarding_state directly.
"""

from __future__ import annotations


def society_setup_incomplete(society_id) -> bool:
    """
    True if `society_id` is set and that society isn't activated yet
    (societies.onboarding_state <> 'active'). False for a falsy society_id
    (e.g. master admin, who isn't scoped to one society) so callers don't
    need to special-case that themselves.
    """
    if not society_id:
        return False

    from database.db_manager import db
    row = db._execute(
        "SELECT onboarding_state FROM societies WHERE id = :sid",
        {"sid": society_id},
        fetch_one=True,
    )
    return bool(row) and row.get("onboarding_state") != "active"


# Item 15: after activation the apartment, vendor and security portals stay closed until the admin completes Enrollment.
ENROLLMENT_LOCKED_ROLES = ("apartment", "vendor", "security")


def society_portal_state(society_id, role) -> str:
    """'setup' (society not active: show the Hub) | 'enrollment_lock' (active, phase 'enrollment', resident-type role) | 'open'.

    Admin, master and advisers are never locked. Societies that were already active when the phase column was added
    were backfilled to 'complete' by migration 002, so nobody is locked out retroactively."""
    if not society_id or role == "master":
        return "open"
    from database.db_manager import db
    try:
        row = db._execute("SELECT onboarding_state, onboarding_phase FROM societies WHERE id = :sid",
                          {"sid": society_id}, fetch_one=True)
    except Exception as exc:                          # noqa: BLE001 - migrations/002 not applied yet: no phase lock
        if "onboarding_phase" not in str(exc):
            raise
        row = db._execute("SELECT onboarding_state FROM societies WHERE id = :sid", {"sid": society_id}, fetch_one=True)
    if not row:
        return "open"
    if row.get("onboarding_state") != "active":
        return "setup"
    if row.get("onboarding_phase") == "enrollment" and role in ENROLLMENT_LOCKED_ROLES:
        return "enrollment_lock"
    return "open"


def admin_in_onboarding(society_id, role) -> bool:
    """True while the admin's home route should show the Hub (Stages 5-7 not yet finished)."""
    if role != "admin" or not society_id:
        return False
    from database.db_manager import db
    try:
        row = db._execute("SELECT onboarding_state, onboarding_phase FROM societies WHERE id = :sid",
                          {"sid": society_id}, fetch_one=True)
    except Exception as exc:                          # noqa: BLE001
        if "onboarding_phase" not in str(exc):
            raise
        return False
    return bool(row) and row.get("onboarding_state") == "active" and row.get("onboarding_phase") in ("enrollment", "adoption", "advisers")
