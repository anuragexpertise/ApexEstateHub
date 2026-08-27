# ============================================================
# app/dash_apps/callbacks/__init__.py
# ============================================================
# Changes vs previous version:
#   - Added registration of noc_callbacks (NOC Print/PDF/Email)
#     as step 10, before debug callbacks.
#   - admin_callbacks (step 11) fully pruned — validate_qr_code_admin
#     moved to qr_callbacks.py's validate_manual_qr_scoped; remaining
#     callbacks (update_society_count, update_recent_societies,
#     enroll_member) had no matching layout IDs and were removed.
# ============================================================

def register_callbacks(app):
    if getattr(app, "_callbacks_registered", False):
        print("📋 Callbacks already registered — skipping")
        return
    app._callbacks_registered = True

    print("📋 Registering callbacks...")

    # 1. Shell FIRST (owns society-dropdown, guard_modal, route_page)
    from .shell_callbacks import register_shell_callbacks
    register_shell_callbacks(app)

    # 2. Login (writes auth-store with allow_duplicate=True)
    from .login_callbacks import register_login_callbacks
    register_login_callbacks(app)

    # 3. Drilldown — needs profile-action-trigger Store in app_shell
    try:
        from .drilldown_callbacks import register_drilldown_callbacks
        register_drilldown_callbacks(app)
    except Exception as e:
        print(f"⚠️ drilldown_callbacks failed: {e}")
        import traceback; traceback.print_exc()

    # 4. Card catalogue (KPI refresh + list loaders)
    try:
        from .card_catalogue_callbacks import register_card_catalogue_callbacks
        register_card_catalogue_callbacks(app)
    except Exception as e:
        print(f"⚠️ card_catalogue_callbacks failed: {e}")

    # 5. Customize (DnD layout editor)
    try:
        from .customize_callbacks import register_customize_callbacks
        register_customize_callbacks(app)
    except Exception as e:
        print(f"⚠️ customize_callbacks failed: {e}")

    # 6. QR gate pass callbacks
    try:
        from .qr_callbacks import register_qr_callbacks
        register_qr_callbacks(app)
    except Exception as e:
        print(f"⚠️ qr_callbacks failed: {e}")

    # 6b. Security gate-alert callbacks (School Bus / Taxi trigger + escalate,
    #     presumed-visitor notify/call, walk-in visitor, QR scan validate,
    #     attendance clock-in/out). portal_pages.py already imports
    #     render_gate_alerts_section from this module to render the buttons
    #     on the security portal's Gate Pass Evaluation page, but
    #     register_security_callbacks(app) itself was never called anywhere
    #     in this registry — every one of those buttons has been rendered
    #     with no callback listening on it, i.e. non-functional, since
    #     whenever this file was added. Discovered while migrating this
    #     file's auth-store usage to the server-verified session.
    try:
        from .security_callbacks import register_security_callbacks
        register_security_callbacks(app)
    except Exception as e:
        print(f"⚠️ security_callbacks failed: {e}")

    # 7. Camera capture (clientside JS injection)
    try:
        from .camera_callbacks import register_camera_callbacks
        register_camera_callbacks(app)
    except Exception as e:
        print(f"⚠️ camera_callbacks failed: {e}")

    # 8. KPI Inspector callbacks (Customize → KPI Inspector tab)
    try:
        from .customize_kpi_callbacks import register_customize_kpi_callbacks
        register_customize_kpi_callbacks(app)
    except Exception as e:
        print(f"⚠️ customize_kpi_callbacks failed: {e}")

    # 8b. List Inspector callbacks (Customize → List Inspector tab)
    try:
        from .list_inspector_callbacks import register_list_inspector_callbacks
        register_list_inspector_callbacks(app)
    except Exception as e:
        print(f"⚠️ list_inspector_callbacks failed: {e}")

    # 9. Debug LAST (writes customize-kpi-metadata, kpi-audit-table)
    try:
        from .debug_callbacks import register_debug_callbacks
        register_debug_callbacks(app)
    except Exception as e:
        print(f"⚠️ debug_callbacks failed: {e}")

    # 10. NOC card buttons (Print / PDF / Email — clientside JS)
    #     Requires dcc.Store(id='noc-action-store') in app_shell.py layout.
    try:
        from .noc_callbacks import register_noc_callbacks
        register_noc_callbacks(app)
    except Exception as e:
        print(f"⚠️ noc_callbacks failed: {e}")

    # 11. Admin callbacks — fully pruned. update_society_count,
    #     update_recent_societies, enroll_member, and
    #     validate_qr_code_admin were all removed from admin_callbacks.py:
    #     their target component IDs don't exist anywhere in portal_pages.py.
    #     Society counts come from the generic KPI system, enrollment goes
    #     through the schema-driven "New" button flow, and the manual QR
    #     paste-and-validate feature was moved to qr_callbacks.py's
    #     validate_manual_qr_scoped (modular, scoped, opens concern profiles
    #     inline). register_admin_callbacks is a no-op now — kept so the
    #     registration slot remains documented for future admin-specific
    #     callbacks. See admin_callbacks.py's module docstring for the full
    #     rationale.
    try:
        from .admin_callbacks import register_admin_callbacks
        register_admin_callbacks(app)
    except Exception as e:
        print(f"⚠️ admin_callbacks failed: {e}")

    # 12. Form autofill — particulars auto-suggestion for Receipts/Expenses
    #     forms (implements the previously-unwired PARTICULARS_TEMPLATES
    #     intent noted in estatehub.sql's schema comments).
    try:
        from .form_autofill_callbacks import register_form_autofill_callbacks
        register_form_autofill_callbacks(app)
    except Exception as e:
        print(f"⚠️ form_autofill_callbacks failed: {e}")

    # 13. Receipt Print / Save / Email buttons (receipt-action-store dummy
    #     Output — requires that store added to app_shell.py).
    try:
        from .receipt_callbacks import register_receipt_callbacks
        register_receipt_callbacks(app)
    except Exception as e:
        print(f"⚠️ receipt_callbacks failed: {e}")

    # 13b. Event Ticket Print / Save / Email buttons (event-ticket-action-store
    #      dummy Output — requires those stores added to app_shell.py). New
    #      2026-08 — event tickets previously had no print/download flow.
    try:
        from .event_ticket_callbacks import register_event_ticket_callbacks
        register_event_ticket_callbacks(app)
    except Exception as e:
        print(f"⚠️ event_ticket_callbacks failed: {e}")

    # 13c. Vendor Pass Print / Save / Email buttons (vendor-pass-action-store
    #      dummy Output — requires those stores added to app_shell.py). New
    #      2026-08 — vendor passes previously had no print/download flow.
    try:
        from .vendor_pass_callbacks import register_vendor_pass_callbacks
        register_vendor_pass_callbacks(app)
    except Exception as e:
        print(f"⚠️ vendor_pass_callbacks failed: {e}")

    # 14. Bulk Enroll (CSV upload for apartments/vendors/security on the
    #     Admin/Enroll tab). Requires "bulk-enroll-modal" +
    #     "bulk-enroll-entity-store" in app_shell.py, and a "Bulk Enroll"
    #     button rendered next to "New" in renderers.py::render_list_card.
    try:
        from .bulk_enroll_callbacks import register_bulk_enroll_callbacks
        register_bulk_enroll_callbacks(app)
    except Exception as e:
        print(f"⚠️ bulk_enroll_callbacks failed: {e}")

    # 14b. Assign-To modal (concern assignment to admins/vendors/security)
    #     Requires "assign-to-modal" + "assign-to-store" in app_shell.py.
    try:
        from .assign_to_callbacks import register_assign_to_callbacks
        register_assign_to_callbacks(app)
    except Exception as e:
        print(f"⚠️ assign_to_callbacks failed: {e}")

    # 14c. Concern Bid modal (vendor "Save Bid" action on a concern)
    #     Requires "concern-bid-modal" + "concern-bid-store" in app_shell.py.
    try:
        from .concern_bid_callbacks import register_concern_bid_callbacks
        register_concern_bid_callbacks(app)
    except Exception as e:
        print(f"⚠️ concern_bid_callbacks failed: {e}")

    # 14d. Invite-To modal (admin/owner invites vendors/security to bid)
    #     Requires "invite-to-modal" + "invite-to-store" in app_shell.py.
    try:
        from .invite_to_callbacks import register_invite_to_callbacks
        register_invite_to_callbacks(app)
    except Exception as e:
        print(f"⚠️ invite_to_callbacks failed: {e}")

    # 14e. Drill-In entity picker modal (New Receipt/Expense/Concern/… entity_id
    #     and FK fields opted into drillin.py's DRILLIN_CONFIG).
    #     Requires "drillin-modal" + "drillin-store" in app_shell.py.
    try:
        from .drillin_callbacks import register_drillin_callbacks
        register_drillin_callbacks(app)
    except Exception as e:
        print(f"⚠️ drillin_callbacks failed: {e}")

    # 15. Channel callbacks (Create Channel & Subscribe/Unsubscribe & View Subscribers)
    try:
        from .channel_callbacks import register_channel_callbacks
        register_channel_callbacks(app)
    except Exception as e:
        print(f"⚠️ channel_callbacks failed: {e}")

    # 16. Poll callbacks (owner voting, admin CRUD, server-side user.id auth)
    try:
        from .poll_callbacks import register_poll_callbacks
        register_poll_callbacks(app)
    except Exception as e:
        print(f"⚠️ poll_callbacks failed: {e}")

    # 17. Account Settings — self-service Change Password (all roles).
    #     Requires "account-settings-modal" + "account-settings-btn" in
    #     app_shell.py.
    try:
        from .account_callbacks import register_account_callbacks
        register_account_callbacks(app)
    except Exception as e:
        print(f"⚠️ account_callbacks failed: {e}")

    print("✅ All callbacks registered")
