import json
import re
import traceback
from functools import wraps
from dash.exceptions import PreventUpdate
from dash import Input, Output, State, ALL, MATCH, callback, no_update, html, ctx, clientside_callback
import dash_bootstrap_components as dbc
from database.db_manager import db
from database.money import D, money, rupee  # noqa: F401  (Plan v4 C.9: rupee amounts are Decimal)
from database.seed import tds_wizard_rows, it2025_twin
from app.dash_apps.pages.setup_wizard import (
    get_setup_wizard_layout, CATEGORIES, step_label, CONVERSATION_DATA, render_category_content, CATEGORY_ICONS,
    build_rules_panel, rules_subtitle, apt_charges_error, basis_hint, render_review,
    fund_plan, funds_error, fund_rate_label, fund_hint, FUND_BASIS_LABELS,
    fund_flags, fund_note, regime_badge, state_thresholds_rows, legal_regime_live, fund_status_children,
)
from app.utils.ux_toasts import error_toast
from app.security.guards import require_session
from app.security.password_policy import validate_signing_secret
from app.utils.fiscal import fy_start_date
from app.security.audit_context import get_current_society_id, get_current_user_id, get_current_user_role

# Index of the statutes step in CATEGORIES — the only step whose body depends
# on the State picked in Society Details. Step containers are keyed by that
# index, so the refresh callback has to target a concrete one.
STATE_ACT_STEP = CATEGORIES.index("State Act & Rules") if "State Act & Rules" in CATEGORIES else None
MODEL_BYE_LAWS_STEP = CATEGORIES.index("Model Bye-Laws Adoption") if "Model Bye-Laws Adoption" in CATEGORIES else None
APARTMENT_CHARGES_STEP = CATEGORIES.index("Apartment Charges") if "Apartment Charges" in CATEGORIES else None
FUNDS_STEP = CATEGORIES.index("Funds") if "Funds" in CATEGORIES else None


def _setup_validation_result(value, label, base_class="mb-3", kind="text"):
    value = str(value or "").strip()
    if not value:
        return f"is-invalid {base_class}".strip(), f"{label} is required."
    if kind == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        return f"is-invalid {base_class}".strip(), "Enter a valid email address."
    if kind == "phone" and not re.fullmatch(r"[0-9+()\-\s]{7,20}", value):
        return f"is-invalid {base_class}".strip(), "Enter a valid phone number."
    if kind == "secret":
        _err = validate_signing_secret(value)
        if _err:
            return f"is-invalid {base_class}".strip(), _err
    return base_class, ""


def _society_details_error(address, email, phone, registration):
    """A6: server-side required checks for the Society Details step.

    Registration number is NOT checked: Master owns it and it is read-only in the wizard (the argument is
    kept so existing callers still work).

    Returns an error message, or None. Previously these fields only got red
    styling; Next and Submit never checked them, and a blank address was sent
    on as "" which COALESCE() treats as a real value, wiping the address the
    Master had entered.
    """
    for value, label, kind in (
        (address, "Address", "text"),
        (email, "Email", "email"),
        (phone, "Phone number", "phone"),
    ):
        cls, msg = _setup_validation_result(value, label, "", kind)
        if msg:
            return msg if label in msg else f"{label}: {msg}"
    return None


def register_setup_wizard_callbacks(app):

    @app.callback(
        Output("sw-society-address", "className"),
        Output("sw-society-address-feedback", "children"),
        Output("sw-society-email", "className"),
        Output("sw-society-email-feedback", "children"),
        Output("sw-society-phone", "className"),
        Output("sw-society-phone-feedback", "children"),
        Output("sw-society-reg", "className"),
        Output("sw-society-reg-feedback", "children"),
        Output("sw-qr-secret", "className"),
        Output("sw-qr-secret-feedback", "children"),
        Output("sw-qr-secret-confirm", "className"),
        Output("sw-qr-secret-confirm-feedback", "children"),
        Output("sw-i-agree", "className"),
        Output("sw-i-agree-feedback", "children"),
        Output("sw-admin-password", "className"),
        Output("sw-admin-password-feedback", "children"),
        Output("sw-qr-confirm-final", "className"),
        Output("sw-qr-confirm-final-feedback", "children"),
        Input("sw-society-address", "value"),
        Input("sw-society-email", "value"),
        Input("sw-society-phone", "value"),
        Input("sw-society-reg", "value"),
        Input("sw-qr-secret", "value"),
        Input("sw-qr-secret-confirm", "value"),
        Input("sw-i-agree", "value"),
        Input("sw-admin-password", "value"),
        Input("sw-qr-confirm-final", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def validate_setup_fields(address, email, phone, registration, secret, secret_confirm, agreement, password, secret_final):
        address_result = _setup_validation_result(address, "Address", "mb-3")
        email_result = _setup_validation_result(email, "Email", "mb-3", "email")
        phone_result = _setup_validation_result(phone, "Phone number", "mb-3", "phone")
        registration_result = ("mb-3", "")   # read-only, entered by Master: never flagged invalid here
        secret_result = _setup_validation_result(secret, "Signing secret", "mb-3", "secret")
        secret_confirm_result = _setup_validation_result(secret_confirm, "Signing secret confirmation", "mb-3", "secret")
        final_result = _setup_validation_result(secret_final, "Signing secret confirmation", "mb-3", "secret")
        if secret and secret != secret_confirm:
            secret_confirm_result = ("is-invalid mb-3", "Signing secrets must match.")
        if secret and secret != secret_final:
            final_result = ("is-invalid mb-3", "Signing secret must match the original value.")
        agreement_result = (
            ("is-invalid mb-4", "Type I AGREE to proceed.")
            if str(agreement or "").strip() != "I AGREE"
            else ("mb-4", "")
        )
        password_result = _setup_validation_result(password, "Admin password", "mb-3")
        return (
            *address_result, *email_result, *phone_result, *registration_result,
            *secret_result, *secret_confirm_result, *agreement_result,
            *password_result, *final_result,
        )


    @app.callback(
        Output("setup-wizard-container", "children"),
        Input("auth-store", "data"),
        Input("pwd-gate-store", "data"),
    )
    @require_session
    def trigger_setup_wizard(auth, pwd_gate):
        # `auth` (the browser's auth-store) only re-triggers this callback on
        # login; role and society come from the server session. Reading them
        # from the client-editable store let a forged society_id open another
        # society's setup wizard.
        if get_current_user_role() != "admin":
            return no_update
        society_id = get_current_society_id()
        if not society_id:
            return no_update

        # The compulsory first-login password change comes first: while the
        # account still has a temporary password, don't open the wizard.
        # pwd-gate-store fires this callback again once the change succeeds.
        from app.services.auth_service import must_change_password
        if must_change_password(get_current_user_id()):
            return no_update

        # Setup-completion check now lives in one place — see
        # app/security/setup_guard.py — instead of this callback carrying
        # its own copy of the stepup_password_hash query.
        from app.security.setup_guard import society_setup_incomplete
        if society_setup_incomplete(society_id):
            from app.services import onboarding_service as _ob
            if _ob.state_of(society_id) == "registered":
                return html.Div()        # stage 2 first: the Onboarding Hub seats the committee, then opens the wizard
            if _ob.state_of(society_id) == "setup draft":
                return html.Div()        # the draft is saved; the hub now handles the annexes and signatures
            # Trigger Wizard
            return get_setup_wizard_layout(society_id)

        return html.Div() # Clear wizard



    @app.callback(
        Output("sw-current-step", "data"),
        Output("sw-category-title", "children"),
        Output({"type": "sw-step-container", "index": ALL}, "style"),
        Output("sw-compliance-rules-panel", "children"),
        Output("sw-rules-subtitle", "children"),
        Output({"type": "sw-nav-item", "index": ALL}, "active"),
        Output({"type": "sw-nav-item", "index": ALL}, "children"),
        Output("sw-btn-prev", "disabled"),
        Output("sw-btn-next", "style"),
        Output("sw-btn-submit", "style"),
        Output("sw-submit-spinner", "spinner_style"),
        Output("sw-error-msg", "children"),
        Input("sw-btn-prev", "n_clicks"),
        Input("sw-btn-next", "n_clicks"),
        Input({"type": "sw-nav-item", "index": ALL}, "n_clicks"),
        State("sw-current-step", "data"),
        State("sw-society-id", "data"),
        State("sw-central-it-tan", "value"),
        State("sw-central-tds", "value"),
        State("sw-central-gst", "value"),
        State("sw-central-rera", "value"),
        State("sw-qr-secret", "value"),
        State("sw-qr-secret-confirm", "value"),
        State("sw-society-address", "value"),
        State("sw-society-email", "value"),
        State("sw-society-phone", "value"),
        State("sw-society-reg", "value"),
        State("sw-society-state", "value"),
        State("sw-society-constitution", "value"),
        State("sw-apt-billing-basis", "value"),
        State("sw-apt-budget", "value"),
        State("sw-apt-rate", "value"),
        State("sw-apt-amt", "value"),
        State("sw-apt-sinking", "value"),
        State("sw-apt-repair", "value"),
        State("sw-apt-cost", "value"),
        State({"type": "sw-pol-choice", "key": ALL}, "value"),
        State({"type": "sw-pol-choice", "key": ALL}, "id"),
        prevent_initial_call=True
    )
    @require_session
    def handle_wizard_navigation(n_prev, n_next, nav_clicks, current_step, society_id, central_it_tan, central_tds, central_gst, central_rera, qr_secret, qr_confirm,
                                 s_address, s_email_v, s_phone_v, s_reg_v, s_state_v, s_constit_v,
                                 apt_basis_v, apt_budget_v, apt_rate_v, apt_amt_v,
                                 apt_sinking_v, apt_repair_v, apt_cost_v, pol_values, pol_ids):
        triggered_id = ctx.triggered_id
        
        error_msg = ""
        new_step = current_step

        # Apartment Charges: block moving forward while the field the chosen billing basis needs is 0 / empty.
        _forward = (triggered_id == "sw-btn-next" and n_next) or (
            isinstance(triggered_id, dict) and triggered_id.get("type") == "sw-nav-item"
            and any(nav_clicks or []) and triggered_id["index"] > current_step)
        gate_err = None
        if _forward and CATEGORIES[current_step] == "Apartment Charges":
            gate_err = apt_charges_error(apt_basis_v, apt_budget_v, apt_rate_v, apt_amt_v)
        elif _forward and CATEGORIES[current_step] == "Funds":
            # the live drop-down values, not the saved ones: the admin may not have left the field yet
            _chosen = {i["key"]: v for i, v in zip(pol_ids or [], pol_values or [])}
            gate_err = funds_error(fund_plan(get_current_society_id(), s_state_v, _chosen, constitution=s_constit_v)["plan"], apt_sinking_v, apt_repair_v, apt_cost_v)
        
        def get_next_valid_step(step, direction):
            while 0 <= step < len(CATEGORIES):
                cat = CATEGORIES[step]
                # Skip GSTIN & GST Rate if not GST registered (from Legal Regime Selection)
                if cat == "GSTIN & GST Rate" and not central_gst:
                    step += direction
                # Skip TAN & TDS Rates if not deducting TDS (from Legal Regime Selection)
                elif cat == "TAN & TDS Rates" and not central_tds:
                    step += direction
                else:
                    break
            return max(0, min(step, len(CATEGORIES) - 1))
            
        if triggered_id == "sw-btn-next" and n_next:
            if gate_err:
                error_msg = gate_err
            elif CATEGORIES[current_step] == "Society Details" and _society_details_error(s_address, s_email_v, s_phone_v, s_reg_v):
                error_msg = _society_details_error(s_address, s_email_v, s_phone_v, s_reg_v)
            elif CATEGORIES[current_step] == "Administrator":
                if not qr_secret or not qr_confirm:
                    error_msg = "Please enter and confirm your SIGNING_SECRET."
                elif qr_secret != qr_confirm:
                    error_msg = "SIGNING_SECRET fields do not match."
                elif validate_signing_secret(qr_secret):
                    error_msg = validate_signing_secret(qr_secret)
                else:
                    new_step = get_next_valid_step(current_step + 1, 1)
            elif current_step < len(CATEGORIES) - 1:
                new_step = get_next_valid_step(current_step + 1, 1)
        elif triggered_id == "sw-btn-prev" and n_prev:
            if current_step > 0:
                new_step = get_next_valid_step(current_step - 1, -1)
        elif isinstance(triggered_id, dict) and triggered_id["type"] == "sw-nav-item" and any(nav_clicks):
            clicked_step = triggered_id["index"]
            if CATEGORIES[current_step] == "Administrator" and clicked_step > current_step:
                if not qr_secret or not qr_confirm:
                    error_msg = "Please enter and confirm your SIGNING_SECRET."
                elif qr_secret != qr_confirm:
                    error_msg = "SIGNING_SECRET fields do not match."
                elif validate_signing_secret(qr_secret):
                    error_msg = validate_signing_secret(qr_secret)
                else:
                    new_step = get_next_valid_step(clicked_step, 1)
            elif gate_err:
                error_msg = gate_err
            else:
                new_step = get_next_valid_step(clicked_step, 1)

        cat_name = CATEGORIES[new_step]
        step_styles = [{"display": "block"} if i == new_step else {"display": "none"} for i in range(len(CATEGORIES))]
        
        # Acts & Rules: framework rows + official links for THIS step (see build_rules_panel)
        rules_html = build_rules_panel(cat_name, society_id, s_state_v)
        rules_sub = rules_subtitle(cat_name, society_id, s_state_v)

        nav_active = [i == new_step for i in range(len(CATEGORIES))]
        nav_children = []
        for i, cat in enumerate(CATEGORIES):
            cat_icon_cls = CATEGORY_ICONS.get(cat, 'fas fa-circle')
            cat_icon = html.I(className=f"{cat_icon_cls} me-2")
            if (cat == "GSTIN & GST Rate" and not central_gst) or (cat == "TAN & TDS Rates" and not central_tds):
                nav_children.append(html.Span([cat_icon, step_label(cat)], style={"textDecoration": "line-through", "opacity": "0.5"}))
            elif i < new_step:
                nav_children.append(html.Span([cat_icon, step_label(cat), html.I(className="fas fa-check-circle text-success float-end", style={"marginTop": "4px"})]))
            else:
                nav_children.append(html.Span([cat_icon, step_label(cat)]))
                
        prev_disabled = (new_step == 0)
        
        next_style = {"display": "inline-block"} if new_step < len(CATEGORIES) - 1 else {"display": "none"}
        submit_style = {"display": "inline-block"} if new_step == len(CATEGORIES) - 1 else {"display": "none"}
        spinner_style = {"display": "inline-block"} if new_step == len(CATEGORIES) - 1 else {"display": "none"}

        return new_step, step_label(cat_name), step_styles, rules_html, rules_sub, nav_active, nav_children, prev_disabled, next_style, submit_style, spinner_style, error_msg


    # Apartment Charges: tell the admin which Part A field the chosen billing basis needs.
    @app.callback(
        Output("sw-apt-basis-hint", "children"),
        Input("sw-apt-billing-basis", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def update_basis_hint(basis):
        return basis_hint(basis)

    # Review: built from the LIVE form values when the step opens. Nothing is saved before Submit, so the old
    # database-backed Review could only ever show defaults.
    REVIEW_STEP = CATEGORIES.index("Review") if "Review" in CATEGORIES else None
    if REVIEW_STEP is not None:
        @app.callback(
            Output({"type": "sw-step-container", "index": REVIEW_STEP}, "children"),
            Input("sw-current-step", "data"),
            State("sw-society-state", "value"),
            State("sw-society-constitution", "value"),
            State("sw-society-address", "value"),
            State("sw-society-email", "value"),
            State("sw-society-phone", "value"),
            State("sw-society-tan", "value"),
            State("sw-tds-effective-date", "date"),
            State("sw-society-gstin", "value"),
            State("sw-cgst", "value"),
            State("sw-sgst", "value"),
            State("sw-central-it-tan", "value"),
            State("sw-central-tds", "value"),
            State("sw-central-gst", "value"),
            State("sw-central-rera", "value"),
            State({"type": "tds-rate", "index": ALL}, "value"),
            State("sw-apt-cost", "value"),
            State("sw-apt-budget", "value"),
            State("sw-apt-rate", "value"),
            State("sw-apt-amt", "value"),
            State("sw-apt-billing-basis", "value"),
            State("sw-apt-due", "value"),
            State("sw-apt-sinking", "value"),
            State("sw-apt-repair", "value"),
            State("sw-apt-interest", "value"),
            State("sw-ven-1day", "value"),
            State("sw-ven-7day", "value"),
            State("sw-ven-1mth", "value"),
            State("sw-gate-logic", "value"),
            State("sw-duty-hrs", "value"),
            State("sw-sec-name", "value"),
            State("sw-sec-phone", "value"),
            State("sw-sec-email", "value"),
            State("sw-calc-start-date", "date"),
            State("sw-bf-fy", "value"),
            State({"type": "sw-bf-amt", "acc_id": ALL}, "id"),
            State({"type": "sw-bf-amt", "acc_id": ALL}, "value"),
            State({"type": "sw-pol-choice", "key": ALL}, "value"),
            State({"type": "sw-pol-choice", "key": ALL}, "id"),
            prevent_initial_call=True,
        )
        @require_session
        def refresh_review(step, state, constitution, address, email, phone, tan, tds_date, gstin, cgst, sgst,
                           central_it_tan, central_tds, central_gst, central_rera, tds_rates,
                           apt_cost, apt_budget, apt_rate, apt_amt, apt_basis, apt_due, apt_sinking, apt_repair, apt_interest,
                           ven1, ven7, ven30, gate, duty, sec_name, sec_phone, sec_email, calc_start,
                           bf_fy, bf_ids, bf_amts, pol_values, pol_ids):
            if step != REVIEW_STEP:
                return no_update
            values = {
                "state": state, "constitution": constitution, "address": address, "email": email, "phone": phone,
                "tan": tan, "tds_date": tds_date, "gstin": gstin, "cgst": cgst, "sgst": sgst,
                "central_it_tan": central_it_tan, "central_tds": central_tds, "central_gst": central_gst,
                "central_rera": central_rera, "tds_rates": tds_rates,
                "apt_cost": apt_cost, "apt_budget": apt_budget, "apt_rate": apt_rate, "apt_amt": apt_amt,
                "apt_basis": apt_basis, "apt_due": apt_due, "apt_sink": apt_sinking, "apt_repair": apt_repair,
                "apt_interest": apt_interest, "ven1": ven1, "ven7": ven7, "ven30": ven30,
                "gate": gate, "duty": duty, "sec_name": sec_name, "sec_phone": sec_phone, "sec_email": sec_email,
                "calc_start": calc_start, "bf_fy": bf_fy,
                "bf_ids": [d.get("acc_id") for d in (bf_ids or [])], "bf_amts": bf_amts or [],
                "pol": {i["key"]: v for i, v in zip(pol_ids or [], pol_values or [])},
            }
            return render_review(values, get_current_society_id())

    # Bye-Laws Adoption step: each radio / variation edit is saved straight away as a PROVISIONAL Layer-1 row
    # (record_wizard_adoption — admin of this society or master; never active without a passed resolution).
    @app.callback(
        Output({"type": "sw-bl-msg", "clause": MATCH}, "children"),
        Input({"type": "sw-bl-choice", "clause": MATCH}, "value"),
        Input({"type": "sw-bl-var", "clause": MATCH}, "value"),
        State({"type": "sw-bl-choice", "clause": MATCH}, "id"),
        State("sw-society-id", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def save_wizard_bye_law_choice(choice, variation, comp_id, society_id):
        if not choice or not society_id:
            return no_update
        from app.security.audit_context import get_current_user_id, get_current_user_role, get_current_society_id
        from app.services import regime_rules_admin as rra
        try:
            ok, msg = rra.record_wizard_adoption(
                get_current_user_id(), get_current_user_role(), get_current_society_id(),
                int(society_id), comp_id["clause"], choice, variation or None)
        except PermissionError as exc:
            return f"✗ {exc}"
        except Exception as exc:
            return f"✗ not saved ({exc.__class__.__name__})"
        return ("✓ " if ok else "✗ ") + msg

    # Society-resolution drop-downs (Bye-Laws Adoption step): saved straight away as PROVISIONAL policy rows.
    @app.callback(
        Output({"type": "sw-pol-msg", "key": MATCH}, "children"),
        Input({"type": "sw-pol-choice", "key": MATCH}, "value"),
        State({"type": "sw-pol-choice", "key": MATCH}, "id"),
        State("sw-society-id", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def save_wizard_policy_choice(value, comp_id, society_id):
        if not value or not society_id:
            return no_update
        from app.security.audit_context import get_current_user_id, get_current_user_role, get_current_society_id
        from app.services import regime_rules_admin as rra
        try:
            ok, msg = rra.record_wizard_policy(
                get_current_user_id(), get_current_user_role(), get_current_society_id(),
                int(society_id), comp_id["key"], value)
        except PermissionError as exc:
            return f"✗ {exc}"
        except Exception as exc:
            return f"✗ not saved ({exc.__class__.__name__})"
        return ("✓ " if ok else "✗ ") + msg

    # Legal Regime Selection: State/Constitution are only persisted on submit, so this block is driven by the
    # live dropdowns. It also listens to the current step so it is rebuilt on arrival at the step, not only
    # when a dropdown changes.
    @app.callback(
        Output("sw-legal-regime-live", "children"),
        Input("sw-society-state", "value"),
        Input("sw-society-constitution", "value"),
        Input("sw-current-step", "data"),
        State("sw-society-id", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def refresh_legal_regime_step(picked_state, picked_constitution, _current_step, _client_society_id):
        return legal_regime_live(get_current_society_id(), picked_state, picked_constitution)


    # NOTE: Dash skips a multi-output callback entirely if ANY of its outputs is not in the layout, so every Output
    # below must be a component the wizard actually renders (a removed panel used to silently disable this callback).
    # Every step body is rendered once, when the modal is built — so the
    # statutes step kept showing whatever societies.state held at that moment
    # (empty for a society being onboarded, and a full name like
    # 'Uttar Pradesh' rather than the 'UP' code the dropdown writes) no
    # matter what the admin had just selected. Re-render it, and the Acts &
    # Rules column, off the dropdown instead. Both rules-panel outputs are
    # allow_duplicate because handle_wizard_navigation also writes them.
    if STATE_ACT_STEP is not None and MODEL_BYE_LAWS_STEP is not None and FUNDS_STEP is not None:
        @app.callback(
            Output({"type": "sw-step-container", "index": STATE_ACT_STEP}, "children"),
            Output({"type": "sw-step-container", "index": MODEL_BYE_LAWS_STEP}, "children"),
            Output({"type": "sw-step-container", "index": FUNDS_STEP}, "children"),
            Output("sw-compliance-rules-panel", "children", allow_duplicate=True),
            Output("sw-rules-subtitle", "children", allow_duplicate=True),
            Output("sw-regime-badge", "children"),
            Input("sw-society-state", "value"),
            Input("sw-society-constitution", "value"),
            State("sw-society-id", "data"),
            State("sw-current-step", "data"),
            prevent_initial_call=True,
        )
        @require_session
        def refresh_state_dependent_steps(picked_state, picked_constitution, _client_society_id, current_step):
            # The society comes from the server session; the browser-side sw-society-id store is never trusted
            # for what data to render.
            society_id = get_current_society_id()
            # Statutes and Bye-Laws (fund opt-ins per regime) both depend on the State dropdown, which is only
            # persisted on submit. The Acts & Rules column is rewritten for the step the admin is ON; it used
            # to be overwritten with the UP AOA statutes whichever step was open.
            here = CATEGORIES[current_step] if isinstance(current_step, int) and 0 <= current_step < len(CATEGORIES) else CATEGORIES[0]
            return (
                render_category_content("State Act & Rules", society_id, picked_state),
                render_category_content("Model Bye-Laws Adoption", society_id, picked_state),
                render_category_content("Funds", society_id, picked_state, constitution=picked_constitution),
                build_rules_panel(here, society_id, picked_state),
                rules_subtitle(here, society_id, picked_state),
                regime_badge(picked_state, picked_constitution),
            )

        # The Funds step follows the admin's clicks: which questions are shown, what the rate field means, and the
        # sentence under it. fund_plan() applies the same rules as the SQL function fn_fund_rule.
        from app.services.up_aoa_fund_catalog import FUNDS as _UP_FUNDS
        _FUND_OUTS = []
        for _f in ("sinking", "repair"):
            _FUND_OUTS += [Output(f"sw-fund-{_f}-collect-wrap", "style"), Output(f"sw-fund-{_f}-basis-wrap", "style"),
                           Output(f"sw-fund-{_f}-rate-wrap", "style"), Output(f"sw-fund-{_f}-rate-label", "children"),
                           Output(f"sw-fund-{_f}-hint", "children"), Output(f"sw-fund-{_f}-status", "children")]

        @app.callback(
            *_FUND_OUTS,
            Input({"type": "sw-pol-choice", "key": ALL}, "value"),
            Input("sw-society-state", "value"),
            Input("sw-society-constitution", "value"),
            State({"type": "sw-pol-choice", "key": ALL}, "id"),
            State("sw-society-id", "data"),
            prevent_initial_call=True,
        )
        @require_session
        def toggle_fund_fields(values, picked_state, picked_constitution, ids, _client_society_id):
            society_id = get_current_society_id()  # server session, not the browser-side store
            chosen = {i["key"]: v for i, v in zip(ids or [], values or [])}
            fp = fund_plan(society_id, picked_state, chosen, constitution=picked_constitution)
            show = lambda on: {} if on else {"display": "none"}
            out = []
            for fund in ("sinking", "repair"):
                f = fp["plan"][fund]
                out += [show(not f["statutory"] and (f["levy"] == "yes" or f["mode"] != "none")),   # collection question
                        show(not f["statutory"] and f["mode"] == "on_bill"),                          # basis question
                        show(f["mode"] == "on_bill"),                                                 # rate field
                        dbc.Label(fund_rate_label(f["basis"]), className="fw-semibold small"),
                        fund_hint(f, fp["regime"]),
                        no_update if f["statutory"] else fund_status_children(_UP_FUNDS[fund], opted=(f["levy"] == "yes"))]
            return tuple(out)

        # Answering "No" to "collect this fund?" also records "Not collected"; "Yes" lifts that back to the regime default.
        for _f in ("sinking", "repair"):
            @app.callback(
                Output({"type": "sw-pol-choice", "key": f"{_f}_fund_collection"}, "value"),
                Input({"type": "sw-pol-choice", "key": f"levy_{_f}_fund"}, "value"),
                State({"type": "sw-pol-choice", "key": f"{_f}_fund_collection"}, "value"),
                prevent_initial_call=True,
            )
            @require_session
            def sync_collection_with_levy(levy, current):
                if levy == "no":
                    return "none" if current != "none" else no_update
                if levy == "yes" and current == "none":
                    return "regime_default"
                return no_update



    # Defined BEFORE the decorator below: its running= list reads it while the callback is being registered
    # (it used to be defined inside the function body, so registration raised NameError).
    _hidden_spinner = {"display": "none", "marginLeft": "8px"}

    def _surface_errors(fn):
        """Submit Setup: an unexpected exception used to return a bare 500 and the wizard just sat there. Log it and
        show the admin a message in the red error line instead (PreventUpdate still passes through)."""
        @wraps(fn)
        def wrapped(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except PreventUpdate:
                raise
            except Exception as exc:
                traceback.print_exc()
                msg = error_toast(exc, "Setup could not be submitted. Please check the entries on each step and try again.")["message"]
                return True, no_update, no_update, no_update, no_update, msg, _hidden_spinner, no_update, no_update
        return wrapped

    @app.callback(
        Output("setup-wizard-modal", "is_open"),
        Output("auth-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Output("login-modal", "is_open", allow_duplicate=True),
        Output("sw-error-msg", "children", allow_duplicate=True),
        Output("sw-submit-spinner", "spinner_style", allow_duplicate=True),
        Output("agreement-modal", "is_open", allow_duplicate=True),
        Output("agreement-modal-body", "children", allow_duplicate=True),
        Input("sw-btn-submit", "n_clicks"),
        Input("sw-close-btn", "n_clicks"),
        State({"type": "form-field-hidden", "entity": "society", "field": "logo"}, "value"),
        State("sw-society-address", "value"),
        State("sw-society-state", "value"),
        State("sw-society-constitution", "value"),
        State("sw-society-email", "value"),
        State("sw-society-phone", "value"),
        State({"type": "form-field-hidden", "entity": "society", "field": "bg"}, "value"),
        State("sw-society-tan", "value"),
        State("sw-society-gstin", "value"),
        State("sw-society-reg", "value"),
        State("sw-gate-logic", "value"),
        State("sw-duty-hrs", "value"),
        State({"type": "form-field-hidden", "entity": "society", "field": "pay_qr"}, "value"),
        State("sw-calc-start-date", "date"),
        State("sw-sec-name", "value"),
        State("sw-sec-phone", "value"),
        State("sw-sec-email", "value"),
        State({"type": "form-field-hidden", "entity": "society", "field": "sec_sign"}, "value"),
        State("sw-qr-secret", "value"),
        State("sw-qr-secret-confirm", "value"),
        State("sw-i-agree", "value"),
        State("sw-admin-password", "value"),
        State("sw-qr-confirm-final", "value"),
        State({"type": "tds-nature", "index": ALL}, "value"),
        State({"type": "tds-rate", "index": ALL}, "value"),
        State({"type": "tds-rate-no-pan", "index": ALL}, "value"),
        State({"type": "tds-single-bill", "index": ALL}, "value"),
        State({"type": "tds-agg-bill", "index": ALL}, "value"),
        State("sw-cgst", "value"),
        State("sw-sgst", "value"),
        State("sw-apt-amt", "value"),
        State("sw-apt-rate", "value"),
        State("sw-apt-billing-basis", "value"),
        State("sw-apt-due", "value"),
        State("sw-apt-sinking", "value"),
        State("sw-apt-repair", "value"),
        State("sw-apt-interest", "value"),
        State("sw-apt-cost", "value"),
        State("sw-apt-budget", "value"),
        State("sw-ven-1day", "value"),
        State("sw-ven-7day", "value"),
        State("sw-ven-1mth", "value"),
        State("sw-bf-fy", "value"),
        State({"type": "sw-bf-amt", "acc_id": ALL}, "id"),
        State({"type": "sw-bf-amt", "acc_id": ALL}, "value"),
        State({"type": "sw-bf-remarks", "acc_id": ALL}, "value"),
        State("sw-tds-effective-date", "date"),
        State("sw-central-it-tan", "value"),
        State("sw-central-tds", "value"),
        State("sw-central-gst", "value"),
        State("sw-central-rera", "value"),
        State("auth-store", "data"),
        running=[
            (Output("sw-btn-submit", "disabled"), True, False),
            (Output("sw-submit-spinner", "spinner_style"), {"display": "inline-block"}, _hidden_spinner),
        ],
        prevent_initial_call=True
    )
    @require_session
    @_surface_errors
    def submit_setup_wizard(n_submit, n_close, 
                            logo_data, address, s_state, s_constitution, s_email, phone, bg_data, 
                            tan, gstin, reg_num, gate_logic, duty_hrs, pay_qr_data, calc_start, 
                            sec_name, sec_phone, sec_email, sec_sign_data, 
                            qr_secret, qr_confirm, i_agree, admin_pass, qr_confirm_final,
                            tds_natures, tds_rates, tds_rates_no_pan, tds_single_bills, tds_agg_bills,
                            cgst, sgst,
                            apt_amt, apt_rate, apt_billing_basis, apt_due_day, apt_sinking, apt_repair, apt_interest,
                            apt_cost, apt_budget,
                            ven_1day, ven_7day, ven_1mth,
                            bf_fy, bf_ids, bf_amts, bf_remarks, tds_effective_date,
                            central_it_tan, central_tds, central_gst, central_rera, auth):
        triggered = ctx.triggered_id
        _noop = (no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update)
        
        # Default compliance settings (no longer in wizard, set defaults)
        c_gst_exempt = False
        c_gst_cad = "monthly"
        c_tds_act = "warn"
        c_exp_fmt = "structured"

        if triggered == "sw-close-btn":
            if not n_close:
                return _noop
            try:
                from flask_login import logout_user
                logout_user()
            except Exception:
                pass
            return False, None, "/dashboard/", {"type": "info", "message": "Setup cancelled. You have been logged out."}, True, "", _hidden_spinner, no_update, no_update

        if triggered == "sw-btn-submit":
            if not n_submit:
                return _noop

            # auth-store must never be overwritten with anything but a real
            # auth dict or None (logout) — every other callback in the app
            # does auth.get(...) on it. Validation failures below only ever
            # touch is_open / sw-error-msg.
            # Identity is server-resolved. Previously society_id/user_id came from
            # the client-editable auth-store and NO role check existed, so any
            # logged-in user (an apartment owner included) could overwrite a
            # society's QR signing secret and setup. Setup is admin-only.
            society_id = get_current_society_id()
            _sw_uid = get_current_user_id()
            if not society_id or not _sw_uid:
                return True, no_update, no_update, no_update, no_update, "Session error — please log in again.", _hidden_spinner, no_update, no_update
            if get_current_user_role() != "admin":
                return True, no_update, no_update, no_update, no_update, "Only the society admin can complete setup.", _hidden_spinner, no_update, no_update

            # Plan v5 stage 2 comes first: the three office-bearers sign the Agreement, so they must be seated before a draft is saved.
            from app.services import onboarding_service as _ob
            if _ob.state_of(society_id) not in ("committee seated", "setup draft"):
                return True, no_update, no_update, no_update, no_update, "Seat the President, Secretary and Treasurer first (Society onboarding page).", _hidden_spinner, no_update, no_update

            # A11: the 5-second throttle used to be an in-memory dict, so with 2
            # gunicorn workers it was per-worker and reset on restart. One atomic
            # UPDATE on the database makes it shared: only the request that moves
            # setup_submit_at forward gets a row back.
            uid = _sw_uid
            _slot = db._execute(
                "UPDATE users SET setup_submit_at = NOW() "
                "WHERE id = :uid AND (setup_submit_at IS NULL "
                "OR setup_submit_at < NOW() - INTERVAL '5 seconds') RETURNING id",
                {"uid": uid}, fetch_one=True,
            )
            if not _slot:
                return True, no_update, no_update, no_update, no_update, "Please wait before submitting again.", _hidden_spinner, no_update, no_update

            _details_err = _society_details_error(address, s_email, phone, reg_num)
            if _details_err:
                return True, no_update, no_update, no_update, no_update, _details_err, _hidden_spinner, no_update, no_update

            from app.dash_apps.pages.setup_wizard import fund_flags as _ff_submit
            _apt_err = (apt_charges_error(apt_billing_basis, apt_budget, apt_rate, apt_amt)
                        or funds_error(_ff_submit(society_id, s_state, constitution=s_constitution)["plan"], apt_sinking, apt_repair, apt_cost))
            if _apt_err:
                return True, no_update, no_update, no_update, no_update, _apt_err, _hidden_spinner, no_update, no_update

            if i_agree != 'I AGREE':
                return True, no_update, no_update, no_update, no_update, "You must type 'I AGREE' to proceed.", _hidden_spinner, no_update, no_update

            if not admin_pass:
                return True, no_update, no_update, no_update, no_update, "Admin Password is required.", _hidden_spinner, no_update, no_update

            # Validate the secret fields first so a typo there never counts
            # as a wrong-password attempt.
            if not qr_secret:
                return True, no_update, no_update, no_update, no_update, "SIGNING_SECRET is required.", _hidden_spinner, no_update, no_update

            if qr_secret != qr_confirm or qr_secret != qr_confirm_final:
                return True, no_update, no_update, no_update, no_update, "SIGNING_SECRETs do not match.", _hidden_spinner, no_update, no_update

            _secret_err = validate_signing_secret(qr_secret)
            if _secret_err:
                return True, no_update, no_update, no_update, no_update, _secret_err, _hidden_spinner, no_update, no_update

            # A11: wrong admin passwords here now feed the shared login lockout.
            from app.services.auth_service import verify_password_with_lockout
            _pw_ok, _pw_msg = verify_password_with_lockout(_sw_uid, admin_pass)
            if not _pw_ok:
                return True, no_update, no_update, no_update, no_update, _pw_msg, _hidden_spinner, no_update, no_update

            # society_id was resolved from the server session above.

            # The typed secret is now only a STEP-UP PASSWORD (stored as a one-way hash; it signs nothing). The
            # four signing keys are random, made by the server and wrapped under SECRET_VAULT_KEY. They are
            # created BEFORE setup is marked complete, so a vault misconfiguration fails here, loudly, and
            # never leaves a "complete" society without keys.
            try:
                from app.services.signing_service import ensure_society_keys, set_stepup_password_hash
                ensure_society_keys(society_id, _sw_uid)
                secret_enc = set_stepup_password_hash(qr_secret)
            except Exception as e:
                return True, no_update, no_update, no_update, no_update, error_toast(e, "Unable to create the society's signing keys. Check the server configuration (SECRET_VAULT_KEY) and try again.")["message"], _hidden_spinner, no_update, no_update

            try:   # Plan v3 2.8: derive flats' undivided-interest shares from area unless the Declaration's own were typed
                from app.services.up_aoa_actions import fill_after_enrolment
                fill_after_enrolment(society_id)
            except Exception as e:
                print(f"undivided-interest fill skipped: {e}")

            # Zip the typed rates back onto the wizard's rows: ONE per (section, discriminator), see
            # database.seed.tds_wizard_rows(). Earlier dated rates are added later on the TDS & GST Rates tab.
            def _num_or_none(lst, i):
                v = lst[i] if i < len(lst) else None
                return None if v in (None, "") else float(v)

            tds_pairs = []
            for idx, item in enumerate(tds_wizard_rows()):
                rate = _num_or_none(tds_rates, idx)
                if rate is None:
                    continue        # not entered: save nothing for this row; the CA fills it in later
                pair = {
                    "section": item[0],
                    "discriminator": item[1],
                    "nature_of_income": tds_natures[idx] if idx < len(tds_natures) else None,
                    "rate": rate,
                    "rate_no_pan": _num_or_none(tds_rates_no_pan, idx),
                    "single_bill_threshold": _num_or_none(tds_single_bills, idx),
                    "annual_aggregate_threshold": _num_or_none(tds_agg_bills, idx),
                }
                # The rows above are IT1961 rows. From 1-Apr-2026 the TDS engine reads only IT2025 rows, so the
                # setup function also writes a 2025 twin (same rate, s.393 thresholds) where the 2025 table has one.
                twin = it2025_twin(item[0], item[1])
                if twin is not None:
                    pair["it2025"] = twin
                tds_pairs.append(pair)

            bf_json = []
            if bf_ids and bf_amts:
                for idx, acc_dict in enumerate(bf_ids):
                    amt = bf_amts[idx]
                    if amt is not None and D(amt) > 0:
                        bf_json.append({
                            "acc_id": acc_dict["acc_id"],
                            "bf_amount": str(money(amt)),     # a string in the JSON, so no binary float on the way to NUMERIC
                            "remarks": bf_remarks[idx] if idx < len(bf_remarks) else ""
                        })

            logo_path = logo_data
            bg_path = bg_data
            qr_path = pay_qr_data
            sign_path = sec_sign_data

            from app.dash_apps.callbacks.drilldown_callbacks import _move_temp_images
            form_data = {}
            if logo_path: form_data["logo"] = logo_path
            if bg_path: form_data["bg"] = bg_path
            if qr_path: form_data["pay_qr"] = qr_path
            if sign_path: form_data["sec_sign"] = sign_path

            if form_data:
                _move_temp_images("society", society_id, society_id, form_data)

            s_email = str(s_email)[:100] if s_email else None
            tan = str(tan)[:10] if tan else None
            gstin = str(gstin)[:15] if gstin else None
            # Registration number is Master-owned and read-only in the wizard: never trust the posted value.
            _reg_row = db._execute("SELECT registration_number FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True) or {}
            reg_num = _reg_row.get("registration_number")
            phone = str(phone)[:20] if phone else None
            sec_phone = str(sec_phone)[:20] if sec_phone else None
            sec_name = str(sec_name)[:100] if sec_name else None
            sec_email = str(sec_email)[:100] if sec_email else None
            
            # A14: chart-of-accounts seeding and the setup write now share ONE
            # transaction. If the setup function rejects the input (e.g. an
            # unbalanced Brought Forward) or errors, the seeding is rolled back
            # too, so a failed submit no longer leaves a half-initialised society.
            from database.seed import seed_accounts
            from database.db_manager import _to_pyformat
            from app.services import regime_rules_admin as _rra
            from app.dash_apps.pages.setup_wizard import fund_flags as _fund_flags

            # Fund settings come from the Bye-Laws Adoption step, not from separate Compliance inputs.
            # A fund the state does not prescribe and the society did not opt into is stored as 0 (not levied),
            # so monthly billing (fn_generate_monthly_charges bills a fund only when its rate > 0) skips it.
            _flags = _fund_flags(society_id, s_state, constitution=s_constitution)
            apt_sinking = (apt_sinking or 0) if _flags["sinking"] else 0
            apt_repair = (apt_repair or 0) if _flags["repair"] else 0
            # society_compliance_settings keeps the allocation basis of a fund billed on the bill (the CHECK allows
            # only the three concrete bases); a fund not billed on the bill stores the neutral per_sq_ft.
            c_sink = _flags["plan"]["sinking"]["basis"] if _flags["plan"]["sinking"]["mode"] == "on_bill" else "per_sq_ft"
            c_repair = _flags["plan"]["repair"]["basis"] if _flags["plan"]["repair"]["mode"] == "on_bill" else "per_sq_ft"
            c_charges_int = _rra.policy_intent(society_id, "fund_arrears_interest") == "yes"

            class _SetupRejected(Exception):
                pass

            _setup_sql = """SELECT fn_complete_society_setup(
                        :sid, :secret_enc, :logo, :addr, :phone, :bg, :tan, :gstin, :pay_qr, :calc_start, :sec_name, :sec_phone, :sec_email, :sec_sign,
                        CAST(:tds_json AS jsonb), :cgst, :sgst,
                        :apt_amt, :apt_rate, :apt_billing_basis, :apt_due, :apt_sink, :apt_repair,
                        :ven_1, :ven_7, :ven_30,
                        :bf_fy, CAST(:bf_json AS jsonb), :created_by,
                        :s_email, :reg_num, :apt_interest,
                        :c_sink, :c_repair, :c_gst_exempt, :c_charges_int, :c_gst_cad, :c_gst_reg, :c_tds_act, :c_exp_fmt, :gate_logic, :duty_hrs, :tds_effective_date, :s_state, :s_constitution,
                        :apt_cost, :apt_budget, :draft
                    ) AS result"""
            _setup_params = {
                        "sid": society_id,
                        "secret_enc": secret_enc,
                        "logo": logo_path,
                        "addr": address,
                        "phone": phone,
                        "bg": bg_path,
                        "tan": tan,
                        "gstin": gstin,
                        "pay_qr": qr_path,
                        "calc_start": calc_start or str(fy_start_date()),
                        "sec_name": sec_name,
                        "gate_logic": gate_logic,
                        "duty_hrs": duty_hrs,
                        "sec_phone": sec_phone,
                        "sec_email": sec_email,
                        "sec_sign": sign_path,
                        "tds_json": json.dumps(tds_pairs),
                        "cgst": None if cgst in (None, "") else float(cgst),
                        "sgst": None if sgst in (None, "") else float(sgst),
                        "apt_amt": apt_amt, "apt_rate": apt_rate, "apt_billing_basis": apt_billing_basis, "apt_due": apt_due_day,
                        "apt_sink": apt_sinking, "apt_repair": apt_repair,
                        "ven_1": ven_1day, "ven_7": ven_7day, "ven_30": ven_1mth,
                        "bf_fy": bf_fy, "bf_json": json.dumps(bf_json),
                        "created_by": _sw_uid,
                        "s_email": s_email,
                        "reg_num": reg_num,
                        # No cap here: the rate is what the General Body resolved (UP Model Bye-Laws 2011, bye-law 46(a)).
                        "apt_interest": max(float(apt_interest or 0), 0.0),
                        "apt_cost": apt_cost, "apt_budget": apt_budget,
                        "c_sink": c_sink,
                        "c_repair": c_repair,
                        "c_gst_exempt": c_gst_exempt,
                        "c_charges_int": c_charges_int,
                        "c_gst_cad": c_gst_cad,
                        "c_gst_reg": central_gst,
                        "c_tds_act": c_tds_act,
                        "c_exp_fmt": c_exp_fmt,
                        "tds_effective_date": tds_effective_date or str(fy_start_date()),
                        "s_state": (s_state or "").strip()[:50] or None,
                        "s_constitution": (s_constitution or "AOA").strip()[:20] or "AOA",
                        # V5.4: wizard submit is a draft — posts nothing to the ledger.
                        "draft": True,
                    }
            _sql, _prm = _to_pyformat(_setup_sql, _setup_params)
            try:
                with db._conn() as conn:
                    cur = conn.cursor()
                    seed_accounts(cur, conn, society_id, commit=False)
                    # V5.4: persist the two-phase draft so it can be re-opened for
                    # editing and later posted from the sealed Annex C (V5.7).
                    _declaration = {
                        "tds": tds_pairs,
                        "cgst": cgst, "sgst": sgst,
                        "apt": {"amt": apt_amt, "rate": apt_rate, "billing_basis": apt_billing_basis,
                                "due_day": apt_due_day, "sinking": apt_sinking, "repair": apt_repair,
                                "interest": apt_interest, "cost": apt_cost, "budget": apt_budget},
                        "ven": {"1day": ven_1day, "7day": ven_7day, "1mth": ven_1mth},
                        "bf": {"fy": bf_fy, "rows": bf_json},
                        "compliance": {"gst_exempt": c_gst_exempt, "charges_int": c_charges_int,
                                       "cadence": c_gst_cad, "registered": central_gst,
                                       "tds_no_pan": c_tds_act, "export_fmt": c_exp_fmt},
                        "society": {"state": s_state, "constitution": s_constitution,
                                    "email": s_email, "reg_num": reg_num},
                    }
                    cur.execute(
                        """INSERT INTO onboarding_declarations (society_id, declaration_json, status, created_by, submitted_at)
                           VALUES (%s, %s::jsonb, 'submitted', %s, NOW())
                           ON CONFLICT (society_id) DO UPDATE SET
                               declaration_json = EXCLUDED.declaration_json,
                               status = 'submitted', updated_at = NOW(), submitted_at = NOW()""",
                        (society_id, json.dumps(_declaration), _sw_uid))
                    cur.execute(_sql, _prm)
                    _row = cur.fetchone()
                    result = dict(_row) if _row else None
                    _res = (result or {}).get("result") or ""
                    if _res != "OK":
                        raise _SetupRejected(_res or "Setup could not be saved — please try again.")
            except _SetupRejected as rej:
                return True, no_update, no_update, no_update, no_update, str(rej), _hidden_spinner, no_update, no_update
            except Exception as e:
                print("⚠️  Setup submission failed:", e)
                return True, no_update, no_update, no_update, no_update, error_toast(e, "Unable to save the society setup. Please try again.")["message"], _hidden_spinner, no_update, no_update

            outcome = (result or {}).get("result") or ""
            if outcome != "OK":
                return True, no_update, no_update, no_update, no_update, outcome or "Setup could not be saved — please try again.", _hidden_spinner, no_update, no_update

            # State is now written inside fn_complete_society_setup (same
            # statement, same transaction), so a failure here can no longer be
            # swallowed and leave the society without a legal regime (A10).

            # Plan v5: the wizard only SAVED A DRAFT. The binding Agreement is issued after the annexes are sealed, so no
            # Agreement preview opens here (the old preview showed text that was not what gets signed).
            agreement_body = no_update
            agreement_open = no_update

            return (
                False, no_update, "/dashboard/admin-portal",
                {"type": "success", "message": "Setup draft saved. Next: check and seal the annexes, then sign the Agreement."},
                no_update, "",
                _hidden_spinner,
                agreement_open, agreement_body,
            )  # Close wizard modal, redirect to admin dashboard, open Agreement modal

        return _noop

    clientside_callback(
        """
        function(n_clicks, state, constitution, btn_id) {
            if (n_clicks && btn_id) {
                // Open the clean server-rendered view (/print_wizard) instead of
                // window.print() on the SPA, which also prints the wizard modal.
                var q = [];
                if (state) q.push('state=' + encodeURIComponent(state));
                if (constitution) q.push('constitution=' + encodeURIComponent(constitution));
                window.open('/print_wizard/' + encodeURIComponent(btn_id.cat) +
                            (q.length ? '?' + q.join('&') : ''), '_blank');
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output({"type": "sw-print-btn", "cat": MATCH}, "id"),
        Input({"type": "sw-print-btn", "cat": MATCH}, "n_clicks"),
        State("sw-society-state", "value"),
        State("sw-society-constitution", "value"),
        State({"type": "sw-print-btn", "cat": MATCH}, "id"),
        prevent_initial_call=True
    )
