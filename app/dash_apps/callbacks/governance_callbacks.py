# app/dash_apps/callbacks/governance_callbacks.py
"""
Callbacks for Settings -> governance tabs (Admin portal). Admin only; the society is ALWAYS taken from the
server-side Flask-Login session, never from a browser value, and the service layer re-checks that the actor's
society matches (rra._require_writer). Owners have no write callbacks at all.

Wired here (admin, own society only): cash-limit mode, a provisional decision on a non-statute rule (Rules -> Edit), provisional bye-law choice (guided form), provisional policy choice, record meeting,
record resolution (which auto-activates a matching provisional choice) and executing society enactments.
Rule values and catalog entries stay in master_rules_callbacks.py (master only).
"""
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, ctx, no_update

from app.dash_apps.pages import governance_settings as gs
from app.dash_apps.pages import master_rules_page as mrp
from app.security.audit_context import get_current_society_id, get_current_user_id, get_current_user_role
from app.security.guards import require_session
from app.services import regime_rules_admin as rra
from app.services import rule_params

_TOAST = Output("gov-toast", "children", allow_duplicate=True)


def _alert(msg, color):
    return dbc.Alert(msg, color=color, dismissable=True, style={"borderRadius": "8px", "fontSize": "13px"})


def _ctx():
    """(society_id, user_id, role) for an authenticated admin, else (None, alert)."""
    if get_current_user_role() != "admin":
        return None, _alert("Admin role required.", "danger")
    sid = get_current_society_id()
    if not sid:
        return None, _alert("Society not resolved.", "danger")
    return (int(sid), get_current_user_id(), "admin"), None


def _run(fn, refresh, n_outputs):
    """fn(uid, role, sid) -> (ok, msg). Returns (toast, *refresh) — refresh only on success."""
    ctx, err = _ctx()
    if err:
        return (err,) + (no_update,) * n_outputs
    sid, uid, role = ctx
    try:
        ok, msg = fn(uid, role, sid)
    except PermissionError as exc:
        return (_alert(str(exc), "danger"),) + (no_update,) * n_outputs
    except Exception as exc:   # surface DB / constraint errors, never a blank page
        return (_alert(f"Could not save: {exc}", "danger"),) + (no_update,) * n_outputs
    toast = _alert(msg, "success" if ok else "warning")
    return (toast,) + (tuple(refresh(sid)) if ok else (no_update,) * n_outputs)


def _meeting_options(sid):
    try:
        return [{"label": f"#{m['id']} — {m['type']} ({m['held_on']})", "value": m["id"]} for m in rra.list_meetings(sid)]
    except Exception:
        return []


def register_governance_callbacks(app):

    @app.callback(_TOAST, Output("gov-body", "children", allow_duplicate=True), Input("gov-cash-save", "n_clicks"),
                  State("gov-cash-mode", "value"), State("gov-cash-reason", "value"), prevent_initial_call=True)
    @require_session
    def gov_save_cash_mode(n, mode, reason):
        if not n:
            return no_update, no_update
        return _run(lambda uid, role, sid: rra.set_cash_limit_mode(uid, role, sid, mode, reason, actor_society_id=sid),
                    lambda sid: (gs.rules_body(sid, can_edit=True),), 1)

    @app.callback(Output("gov-rule-key", "value"), Input({"type": "gov-rule-edit", "key": ALL}, "n_clicks"),
                  prevent_initial_call=True)
    @require_session
    def gov_rule_edit_prefill(clicks):
        """'Edit' on a row of the Rules list: select that rule in the decision form. Only a pre-fill; the write
        (gov_save_rule_decision) re-validates the rule and the actor server-side."""
        trig = ctx.triggered_id
        if not isinstance(trig, dict) or not any(clicks or []):
            return no_update
        key = trig.get("key")
        return key if key in {o["value"] for o in mrp.editable_rule_options()} else no_update

    @app.callback(_TOAST, Output("gov-body", "children", allow_duplicate=True), Input("gov-rule-save", "n_clicks"),
                  State("gov-rule-key", "value"), State("gov-rule-layer", "value"), State("gov-rule-choice", "value"),
                  State("gov-rule-value", "value"), State("gov-rule-eff", "value"), State("gov-rule-reason", "value"),
                  prevent_initial_call=True)
    @require_session
    def gov_save_rule_decision(n, key, layer, choice, value, eff, reason):
        if not n or not key or not layer or not choice:
            return no_update, no_update
        if key not in {o["value"] for o in mrp.editable_rule_options()}:
            return _alert("Only a non-statute (Policy) rule can be edited here.", "danger"), no_update
        # Always provisional (no resolution id here); a passed resolution naming the rule activates it.
        return _run(lambda uid, role, sid: rule_params.save_decision(
                        uid, role, sid, key, int(layer), choice,
                        (value or None) if choice == "adopted_with_variation" else None, eff, reason, None,
                        actor_society_id=sid),
                    lambda sid: (gs.rules_body(sid, can_edit=True),), 1)

    @app.callback(_TOAST, Output("gov-bye-body", "children", allow_duplicate=True), Input("gov-bye-save", "n_clicks"),
                  State("gov-bye-clause", "value"), State("gov-bye-layer", "value"), State("gov-bye-status", "value"),
                  State("gov-bye-variation", "value"), State("gov-bye-eff", "value"), State("gov-bye-reason", "value"),
                  prevent_initial_call=True)
    @require_session
    def gov_save_bye_law(n, clause, layer, status, variation, eff, reason):
        if not n or not clause or not layer or not status:
            return no_update, no_update
        # Always saved as provisional; the passed resolution activates it (see gov_save_resolution).
        return _run(lambda uid, role, sid: rra.save_bye_law_version(
                        uid, role, sid, clause, int(layer), status,
                        (variation or None) if status == "adopted_with_variation" else None, eff, reason, None,
                        actor_society_id=sid),
                    lambda sid: (gs.bye_body(sid),), 1)

    @app.callback(Output("gov-bye-status", "options"), Output("gov-bye-status", "value"),
                  Output("gov-bye-layer-help", "children"),
                  Input("gov-bye-clause", "value"), Input("gov-bye-layer", "value"), prevent_initial_call=True)
    @require_session
    def gov_bye_choices(clause, layer):
        ctx_, err = _ctx()
        if err:
            return no_update, no_update, no_update
        opts, value = gs.bye_choice_ui(ctx_[0], clause, layer)
        from app.dash_apps.pages.master_rules_page import LAYER_HELP
        return opts, value, LAYER_HELP.get(int(layer or 1), ("", ""))[1]

    @app.callback(Output("gov-bye-info", "children"), Output("gov-bye-var-wrap", "style"),
                  Input("gov-bye-clause", "value"), Input("gov-bye-layer", "value"), Input("gov-bye-status", "value"),
                  prevent_initial_call=True)
    @require_session
    def gov_bye_panel(clause, layer, status):
        if get_current_user_role() != "admin":
            return no_update, no_update
        info, show_var = gs.bye_choice_panel(clause, layer, status)
        return info, {"display": "block" if show_var else "none"}

    @app.callback(Output("gov-pol-value", "options"), Output("gov-pol-value", "value"), Output("gov-pol-info", "children"),
                  Input("gov-pol-key", "value"), prevent_initial_call=True)
    @require_session
    def gov_policy_choices(key):
        ctx_, err = _ctx()
        if err:
            return no_update, no_update, no_update
        return gs.policy_choice_ui(ctx_[0], key)

    @app.callback(_TOAST, Output("gov-bye-body", "children", allow_duplicate=True), Input("gov-pol-save", "n_clicks"),
                  State("gov-pol-key", "value"), State("gov-pol-value", "value"), prevent_initial_call=True)
    @require_session
    def gov_save_policy(n, key, value):
        if not n or not key or not value:
            return no_update, no_update
        return _run(lambda uid, role, sid: rra.record_wizard_policy(
                        uid, role, sid, sid, key, value, source="Settings (Society governance)"),
                    lambda sid: (gs.bye_body(sid),), 1)

    @app.callback(_TOAST, Output("gov-mtg-body", "children", allow_duplicate=True),
                  Output("gov-res-mtg", "options", allow_duplicate=True), Input("gov-mtg-save", "n_clicks"),
                  State("gov-mtg-type", "value"), State("gov-mtg-date", "value"), State("gov-mtg-quorum", "value"),
                  State("gov-mtg-minutes", "value"), State("gov-mtg-reason", "value"), prevent_initial_call=True)
    @require_session
    def gov_save_meeting(n, mtype, mdate, quorum, minutes, reason):
        if not n or not mtype or not mdate:
            return no_update, no_update, no_update
        return _run(lambda uid, role, sid: rra.create_meeting(
                        uid, role, sid, mtype, mdate, bool(quorum), minutes or None, reason, actor_society_id=sid),
                    lambda sid: (gs.mtg_body(sid, True), _meeting_options(sid)), 2)

    @app.callback(Output("gov-res-majority", "value"), Input("gov-res-dt", "value"), prevent_initial_call=True)
    @require_session
    def gov_prefill_majority(dt_id):
        if not dt_id or get_current_user_role() != "admin":
            return no_update
        dt = next((d for d in rra.list_decision_types() if d["id"] == int(dt_id)), None)
        return float(dt["majority_pct"]) if dt else no_update

    @app.callback(_TOAST, Output("gov-mtg-body", "children", allow_duplicate=True),
                  Output("gov-bye-body", "children", allow_duplicate=True), Input("gov-res-save", "n_clicks"),
                  State("gov-res-mtg", "value"), State("gov-res-dt", "value"), State("gov-res-clause", "value"),
                  State("gov-res-body", "value"), State("gov-res-majority", "value"), State("gov-res-passed", "value"),
                  State("gov-res-passed-on", "value"), State("gov-res-reason", "value"),
                  State("gov-res-present", "value"), State("gov-res-votes-for", "value"), State("gov-res-advocate", "value"),
                  State("gov-res-proxy", "value"), State("gov-res-for", "value"), State("gov-res-against", "value"),
                  State("gov-res-abstain", "value"),
                  prevent_initial_call=True)
    @require_session
    def gov_save_resolution(n, mtg_id, dt_id, clause, body, majority, passed, passed_on, reason,
                            present, votes_for, advocate, proxy, flats_for, flats_against, flats_abstain):
        if not n or not mtg_id or not dt_id or not body:
            return no_update, no_update, no_update
        return _run(lambda uid, role, sid: rra.create_resolution(
                        uid, role, sid, int(mtg_id), int(dt_id), clause or None, body,
                        float(majority) if majority else None, bool(passed), passed_on if passed else None, reason,
                        actor_society_id=sid, votes_for_pct=votes_for, advocate_opinion_ref=advocate,
                        present_flats=present, proxy_flats=proxy, for_flats=flats_for,
                        against_flats=flats_against, abstain_flats=flats_abstain),
                    lambda sid: (gs.mtg_body(sid, True), gs.bye_body(sid)), 2)

    @app.callback(_TOAST, Output("gov-mtg-body", "children", allow_duplicate=True),
                  Output("gov-bye-body", "children", allow_duplicate=True),
                  Input({"type": "gov-enact", "index": ALL}, "n_clicks"), prevent_initial_call=True)
    @require_session
    def gov_execute_enactment(n_clicks):
        trig = ctx.triggered_id
        if not trig or not any(n_clicks or []):
            return no_update, no_update, no_update
        effect_id = trig["index"]
        return _run(lambda uid, role, sid: rra.execute_enactment(uid, role, effect_id, actor_society_id=sid),
                    lambda sid: (gs.mtg_body(sid, True), gs.bye_body(sid)), 2)
