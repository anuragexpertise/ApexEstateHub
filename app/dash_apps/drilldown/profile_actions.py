# app/dash_apps/drilldown/profile_actions.py
"""
Profile action buttons — application WORKFLOW layer.
These cannot be derived from schema introspection; they encode which
button on a profile card triggers which navigation or server-side action.

v3 changes:
  - apartments: added 'issue_noc', kept 'pay_dues' (now routes to FIFO form)
  - vendors:    added 'sell_vendor_pass'
  - receivables: added 'verify_receivable' (admin-only; enforced in renderers.py)
  - payables:    added 'verify_payment'    (admin-only)
  - assets:      added 'dispose_asset'     (admin-only)
  - Removed:     sec_charges (table dropped in v3)
"""

PROFILE_ACTIONS: dict[str, list[dict]] = {

    # ── APARTMENTS ──────────────────────────────────────────────────────────
    "apartments": [
        {
            "label": "Pay Dues",
            "action_id": "pay_dues",
            "target_card": "form_pay_dues_new",
            "icon": "fa-rupee-sign",
            "color": "success",
            "roles": ["admin"],          # only admin can apply a payment
        },
        {
            "label": "Show Cashbook",
            "action_id": "show_cashbook",
            "target_card": "list_cashbook",
            "icon": "fa-book",
            "color": "info",
        },
        {
            "label": "Gate Pass",
            "action_id": "show_qr",
            "target_card": "modal_qr",
            "icon": "fa-qrcode",
            "color": "primary",
        },
        {
            "label": "Raise Concern",
            "action_id": "new_concern",
            "target_card": "form_concern_new",
            "icon": "fa-comment-alt",
            "color": "warning",
        },
        {
            "label": "Issue NOC",
            "action_id": "issue_noc",
            "target_card": "form_noc_print",
            "icon": "fa-certificate",
            "color": "dark",
            "roles": ["admin"],          # admin only; eligibility checked server-side
        },
    ],

    # ── VENDORS ─────────────────────────────────────────────────────────────
    "vendors": [
        {
            "label": "Sell Pass", # admin sells
            "action_id": "sell_vendor_pass",
            "target_card": "form_vendor_pass_new",
            "icon": "fa-id-card",
            "color": "success",
            "roles": ["admin"],  #admin portal 
        },
        {
            "label": "Buy Pass",         # NEW — vendor buys their own pass
            "action_id": "buy_vendor_pass",
            "target_card": "form_vendor_pass_new",
            "icon": "fa-id-card",
            "color": "primary",
            "roles": ["vendor"],         # vendor portal only
        },
        {
            "label": "Show Cashbook",
            "action_id": "show_cashbook",
            "target_card": "list_cashbook",
            "icon": "fa-book",
            "color": "info",
        },
        {
            "label": "Gate Pass",
            "action_id": "show_qr",
            "target_card": "modal_qr",
            "icon": "fa-qrcode",
            "color": "primary",
        },
    ],

    # ── SECURITY ─────────────────────────────────────────────────────────────
    "security": [
        {
            "label": "Show Cashbook",
            "action_id": "show_cashbook",
            "target_card": "list_cashbook",
            "icon": "fa-book",
            "color": "info",
        },
        {
            "label": "Gate Pass",
            "action_id": "show_qr",
            "target_card": "modal_qr",
            "icon": "fa-qrcode",
            "color": "primary",
        },
        {
            # Manual on/off-duty clock toggle. Clocking IN opens a
            # gate_access row (role='SEC', time_out NULL), which is exactly
            # what fn_evaluate_gate_pass() checks to treat the guard as on
            # duty for gate scans. Clocking OUT stamps time_out=NOW() on
            # that row. Shift/payroll counting itself (fn_security_list's
            # shift_count) is driven separately by the security_roster +
            # payables system — this toggle only controls live on/off-duty
            # status for gate scans. See loaders.toggle_security_duty().
            #
            # Admin-only: a guard could otherwise open ANY other guard's
            # profile_security card (portal perm on ("security","security")
            # is view+edit, not self-scoped) and flip their on/off-duty
            # status. Restricting this action to admin closes that gap;
            # a guard's own duty status is set via the portal's own
            # Clock In/Out control or the timed attendance QR, not here.
            "label": "Toggle Duty",
            "action_id": "toggle_duty",
            "target_card": None,          # server-side only — no navigation
            "icon": "fa-toggle-on",
            "color": "warning",
            "roles": ["admin"],
        },
    ],


    # ── CONCERNS ─────────────────────────────────────────────────────────────
    "concerns": [
        {
        "label": "Invite",
        "action_id": "invite",
        "target_card": "modal_invite",  # opens the invite-to modal — no navigation;
                                         # this value is never looked up for routing
                                         # (action=="invite" is intercepted directly
                                         # in drilldown_callbacks.py's route_drilldown,
                                         # same as "show_qr"->"modal_qr" below), it's
                                         # just descriptive id metadata instead of ""
        "icon": "fa-envelope",
        "color": "info",
        "roles": ["admin", "apartment"],   # Admin portal + Owner portal
        },
        {
            "label": "Assign",
            "action_id": "assign",
            "target_card": "form_concern_edit",
            "icon": "fa-user-check",
            "color": "warning",
            "roles": ["admin", "apartment"],   # Admin portal + Owner portal
        },
        {
            "label": "Bid",
            "action_id": "save_bid",
            "target_card": None,          # opens the bid-entry modal — no navigation
            "icon": "fa-hand-holding-usd",
            "color": "primary",
            # Vendor portal only, per the Concerns workflow spec
            # (workflow_vendor_kpi_list_profile). Shown only while the
            # caller's own row is 'invited' (renderers.py).
            "roles": ["vendor"],
        },
        {
            "label": "Decline",
            "action_id": "decline_concern",
            "target_card": None,          # server-side only — no navigation
            "icon": "fa-times",
            "color": "secondary",
            # Vendor portal only, per spec — companion to "Bid". Only
            # shown while the caller's own concerns_assigns row is
            # 'invited' (same gate as "Bid"); sets status='declined',
            # notifies admin, and drops the caller from the Assign modal's
            # candidate pool for this concern until re-invited.
            "roles": ["vendor"],
        },
        {
            "label": "Resolved",
            "action_id": "vendor_resolve",
            "target_card": None,          # server-side only — no navigation
            "icon": "fa-check",
            "color": "success",
            # Vendor portal: shown while the caller's own row is
            # 'assigned' (renderers.py). Security portal: also uses this
            # action id, but per spec its gate checks whether an ADMIN's
            # row on the same concern is 'accepted' — not the security
            # caller's own status (see renderers.py / loaders.is_any_admin_accepted).
            "roles": ["vendor", "security"],
        },
        {
            "label": "Accept",
            "action_id": "accept_concern",
            "target_card": None,          # server-side only — no navigation
            "icon": "fa-thumbs-up",
            "color": "success",
            # Admin portal only, per workflow_admin_kpi_list_profile.
            # Shown while the caller's own ADM row is 'assigned'
            # (renderers.py); moves it to 'accepted'.
            "roles": ["admin"],
        },
        {
            "label": "Decline",
            "action_id": "decline_concern_admin",
            "target_card": None,          # server-side only — no navigation
            "icon": "fa-times",
            "color": "secondary",
            # Admin portal only, per workflow_admin_kpi_list_profile — an
            # assigned admin declining the assignment (distinct from the
            # vendor's pre-bid "decline_concern" above). Shown while the
            # caller's own ADM row is 'assigned' (renderers.py).
            "roles": ["admin"],
        },
        {
            "label": "Resolved",
            "action_id": "admin_resolve",
            "target_card": None,          # server-side only — no navigation
            "icon": "fa-check",
            "color": "success",
            # Admin portal only, per workflow_admin_kpi_list_profile.
            # Shown while the caller's own ADM row is 'accepted'
            # (renderers.py); moves it to 'resolved'.
            "roles": ["admin"],
        },
        {
            "label": "Close",
            "action_id": "close_concern",
            "target_card": None,          # server-side only — no navigation
            "icon": "fa-lock",
            "color": "dark",
            "roles": ["admin", "apartment"],   # Admin portal + Owner portal
        },
    ],

    # ── RECEIVABLES  (read-only tab — Verify is the only action) ────────────
    "receivables": [
        {
            "label": "Verify",
            "action_id": "verify_receivable",
            "target_card": "form_verify_receivable",
            "icon": "fa-check-double",
            "color": "success",
            "roles": ["admin"],          # admin-only; enforced in renderers.py
        },
        {
            "label": "Pay Due",
            "action_id": "pay_due_receivable",
            "target_card": "form_pay_dues_new",
            "icon": "fa-rupee-sign",
            "color": "primary",
            "roles": ["admin"],
        },
    ],

    # ── payables  (read-only tab — Verify is the only action) ───────────────
    "payables": [
        {
            "label": "Verify",
            "action_id": "verify_payment",
            "target_card": None,         # server-side only — no navigation
            "icon": "fa-check-double",
            "color": "success",
            "roles": ["admin"],
        },
    ],
    # ── RECEIPTS ─────────────────────────────────────────────────────────────
    "receipts": [
        {
            "label": "Verify & Post",
            "action_id": "verify_receipt",
            "target_card": None,        # server-side only
            "icon": "fa-check-double",
            "color": "success",
            "roles": ["admin"],
        },
        {
            "label": "Print Receipt",
            "action_id": "print_receipt",
            "target_card": "form_receipt_print",
            "icon": "fa-print",
            "color": "secondary",
            # no "roles" restriction — anyone who can view a receipt at all
            # (admin always; apartment/vendor/security for their own rows,
            # per the view-only _PORTAL_PERMS entries) can print/save/email it.
        },
    ],
    # ── EXPENSES ────────────────────────────────────────────────────────────
    "expenses": [
        {
            "label": "Verify & Post",
            "action_id": "verify_expense",
            "target_card": None,        # server-side only
            "icon": "fa-check-double",
            "color": "success",
            "roles": ["admin"],
        },
    ],
    # ── ASSETS ───────────────────────────────────────────────────────────────
    "assets": [
        {
            "label": "Sell / Dispose",
            "action_id": "dispose_asset",
            "target_card": "form_asset_dispose_new",
            "icon": "fa-sign-out-alt",
            "color": "danger",
            "roles": ["admin"],
        },
    ],

    # ── POLLS ──────────────────────────────────────────────────────────
    "polls": [
        {
            "label": "Declare Results",
            "action_id": "declare_results",
            "target_card": None,
            "icon": "fa-check-circle",
            "color": "success",
            "roles": ["admin"],
        },
        {
            "label": "Close Poll",
            "action_id": "close_poll",
            "target_card": None,
            "icon": "fa-lock",
            "color": "dark",
            "roles": ["admin"],
        },
    ],

    # ── APT CHARGES ──────────────────────────────────────────────────────────
    "apt_charges": [
        {
            "label": "Show Transactions",
            "action_id": "show_transactions",
            "target_card": "list_cashbook",
            "icon": "fa-book",
            "color": "info",
        },
    ],

    # ── VEN CHARGES ──────────────────────────────────────────────────────────
    "ven_charges": [
        {
            "label": "Show Transactions",
            "action_id": "show_transactions",
            "target_card": "list_cashbook",
            "icon": "fa-book",
            "color": "info",
        },
    ],

    # ── EVENTS ──────────────────────────────────────────────────────────────
    "events": [
        {
            "label": "Sell Tickets",       # admin sells to a chosen apartment
            "action_id": "sell_event_ticket",
            "target_card": "form_event_ticket_new",
            "icon": "fa-ticket-alt",
            "color": "success",
            "roles": ["admin"],
        },
        {
            "label": "Buy Tickets",        # apartment buys their own
            "action_id": "buy_event_ticket",
            "target_card": "form_event_ticket_new",
            "icon": "fa-ticket-alt",
            "color": "primary",
            "roles": ["apartment"],
        },
    ],

    # ── CHANNELS ─────────────────────────────────────────────────────────────
    "channels": [
        {
            "label": "Subscribe",
            "action_id": "subscribe_channel",
            "target_card": None,          # server-side only — no navigation
            "icon": "fa-bell",
            "color": "primary",
            "roles": ["apartment"],
        },
        {
            "label": "Trigger Alert",
            "action_id": "trigger_alert",
            "target_card": None,          # server-side only — no navigation
            "icon": "fa-bullhorn",
            "color": "warning",
            "roles": ["admin", "security"],
        },
        {
            "label": "Create Channel",
            "action_id": "create_channel",
            "target_card": "form_channel_new",
            "icon": "fa-plus",
            "color": "success",
            "roles": ["admin"],
        },
        {
            "label": "View Subscribers",
            "action_id": "view_subscribers",
            "target_card": "modal_subscribers",
            "icon": "fa-users",
            "color": "info",
            "roles": ["admin", "apartment", "security"],
        },
    ],
}


# ── Per-field RBAC ───────────────────────────────────────────────────────────
# Only fields that are MORE restrictive than the rest of their entity's row
# need an entry here. Everything else inherits from the portal permission matrix.
FIELD_VISIBILITY: dict[str, dict[str, set[str]]] = {
    "security": {
        "salary_per_shift": {"admin", "master"},
        "salary_due":       {"admin", "master"},
        "salary_paid":      {"admin", "master"},
    },
    "vendors": {
        "mobile":  {"admin", "master", "vendor"},
    },
    "apartments": {
        "mobile":  {"admin", "master", "apartment"},
    },
    "receivables": {
        # All portals can VIEW their own receivables;
        # 'confirmed_by' and 'confirmed_at' are admin-only columns
        "confirmed_by": {"admin", "master"},
        "confirmed_at": {"admin", "master"},
    },
    "payables": {
        "confirmed_by": {"admin", "master"},
        "confirmed_at": {"admin", "master"},
    },
    "events": {
        # Internal accounting linkage (which Event Ticket account this event
        # posts to) — not meaningful to apartment/vendor/security portals,
        # so treat it like the other admin-only internal fields above.
        "account_id": {"admin", "master"},
    },
}
