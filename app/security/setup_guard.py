# app/security/setup_guard.py
"""
Society setup-completion guard.

societies.signing_secret_enc is NULL until a society's admin completes the
Setup Wizard (TDS/GST rate defaults, apartment/vendor charge defaults,
brought-forward balances, QR signing secret, etc — see
setup_wizard_callbacks.py / fn_complete_society_setup).

2026-09 audit finding: three different places in the app had each grown
their own independent copy of "is setup done?" (login_callbacks.py's
_redirect, setup_wizard_callbacks.py's trigger_setup_wizard, and nothing at
all in the main page router) — and only one of those copies (the
admin-only wizard modal) actually stopped anyone from doing anything. The
page router itself rendered the full dashboard for every role regardless
of setup status, so non-admin roles (who never saw the wizard modal) hit
their normal dashboard with no gate whatsoever.

Fix: exactly one definition of "setup complete" lives here. Anything that
needs to know should call society_setup_incomplete(society_id) instead of
querying signing_secret_enc directly.
"""

from __future__ import annotations


def society_setup_incomplete(society_id) -> bool:
    """
    True if `society_id` is set and that society hasn't finished the Setup
    Wizard yet (societies.signing_secret_enc IS NULL). False for a falsy
    society_id (e.g. master admin, who isn't scoped to one society) so
    callers don't need to special-case that themselves.
    """
    if not society_id:
        return False

    from database.db_manager import db
    row = db._execute(
        "SELECT signing_secret_enc FROM societies WHERE id = :sid",
        {"sid": society_id},
        fetch_one=True,
    )
    return bool(row) and not row.get("signing_secret_enc")
