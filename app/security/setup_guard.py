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
