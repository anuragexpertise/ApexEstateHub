# app/dash_apps/callbacks/admin_callbacks.py
"""
Admin-portal callbacks.

PRUNED from the original file: update_society_count, update_recent_societies,
and enroll_member were removed. All three targeted component IDs
(total-societies, recent-societies-list, enroll-name/email/phone/role/flat/
area/password/confirm/enroll-submit-btn) that don't exist anywhere in the
current portal_pages.py layout — the master portal already surfaces society
counts through the generic KPI system (kpi_societies_total), and the admin
Enroll tab now uses the schema-driven "New" button flow
(drilldown_callbacks.py's _save_user_entity / _save_apartment) instead of a
dedicated enroll form. Keeping them registered would just be inert dead code
duplicating logic that already exists elsewhere.

validate_qr_code_admin has been RETIRED (2026-07) — replaced by
qr_callbacks.py's validate_manual_qr_scoped, which is the same manual
paste-and-validate QR feature but modularized (render_manual_qr_card +
a single scope-pattern-matched callback) so it can render on more than one
page. The old version only ever showed a generic "Access Granted" card and
never actually opened anything for concern/receipt/expense/asset QR types;
the new one opens the real concern profile inline. It used ids
manual-qr-input / validate-qr-btn / qr-validation-result — those are now
{"type": "manual-qr-input"/"manual-qr-validate-btn"/"manual-qr-result",
"scope": <page>}, scoped per page (e.g. "pass_evaluation",
"vendor_concern_lookup") so multiple instances can coexist without
colliding.

handle_create_society and its "CLEAR CREATE-SOCIETY FORM" clientside
callback were REMOVED (2026-09) — dead code left over from an earlier,
static-id create-society form (master-create-society-btn, new-society-name,
etc.) that no longer exists anywhere in portal_pages.py/renderers.py. The
live "New Society" form is form_master_society_new (renderers.py's
render_form_master_society_new), submitted through the generic
form-field/form-submit pattern and handled by the "Master Society Creation
Intercept" in drilldown_callbacks.py's handle_form_submit. Besides being
unreachable, handle_create_society also called `raise PreventUpdate`
without importing PreventUpdate — a NameError had it ever fired.
"""

from dash import Input, Output, State, html, no_update
from datetime import datetime

from app.security.guards import require_session


def register_admin_callbacks(app):
    # Fully pruned — see module docstring. Kept as a no-op registration
    # slot for future admin-specific callbacks.
    print("  ✓ Admin callbacks registered (no-op — see admin_callbacks.py module docstring)")
