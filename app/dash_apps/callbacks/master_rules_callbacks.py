# app/dash_apps/callbacks/master_rules_callbacks.py
"""
Callbacks for Master Portal -> "AOA Rule Editor". Thin wrappers: the role comes from the
server-side Flask-Login session (never the browser's auth-store), the work is done by
app.services.regime_rules_admin, and the body is re-rendered only after a successful save.
"""
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, no_update

from app.dash_apps.pages.master_rules_page import REGIME, render_rules_sections, render_bye_laws_sections, render_meetings_sections
from app.security.audit_context import get_current_user_id, get_current_user_role
from app.services import regime_rules_admin as rra
from app.security.guards import require_session
from app.security.authorization import Cap
from app.security.service_guard import require_action

_TOAST = Output("mrl-toast", "children", allow_duplicate=True)
_BODY = Output("mrl-body", "children", allow_duplicate=True)
_BYE_BODY = Output("mrl-bye-body", "children", allow_duplicate=True)
_MTG_BODY = Output("mrl-mtg-body", "children", allow_duplicate=True)


def _alert(msg, color):
    return dbc.Alert(msg, color=color, dismissable=True, style={"borderRadius": "8px", "fontSize": "13px"})


def _denied(_decision=None):
    """on_deny for the mutating callbacks: same shape as _run()'s own refusal."""
    return _alert("Master role required.", "danger"), no_update


def _run(fn):
    """fn(user_id) -> (ok, msg). Master only; refresh the tables on success."""
    if get_current_user_role() != "master":
        return _alert("Master role required.", "danger"), no_update
    try:
        ok, msg = fn(get_current_user_id())
    except PermissionError as exc:
        return _alert(str(exc), "danger"), no_update
    except Exception as exc:   # surface DB / constraint errors, never a blank page
        return _alert(f"Could not save: {exc}", "danger"), no_update
    return _alert(msg, "success" if ok else "warning"), (render_rules_sections() if ok else no_update)


def _run_bye(fn):
    """fn(user_id) -> (ok, msg). Master only; refresh the bye-laws table on success."""
    if get_current_user_role() != "master":
        return _alert("Master role required.", "danger"), no_update
    try:
        ok, msg = fn(get_current_user_id())
    except PermissionError as exc:
        return _alert(str(exc), "danger"), no_update
    except Exception as exc:
        return _alert(f"Could not save: {exc}", "danger"), no_update
    return _alert(msg, "success" if ok else "warning"), (render_bye_laws_sections() if ok else no_update)


def _run_mtg(fn):
    """fn(user_id) -> (ok, msg). Master only; refresh the meetings table on success."""
    if get_current_user_role() != "master":
        return _alert("Master role required.", "danger"), no_update
    try:
        ok, msg = fn(get_current_user_id())
    except PermissionError as exc:
        return _alert(str(exc), "danger"), no_update
    except Exception as exc:
        return _alert(f"Could not save: {exc}", "danger"), no_update
    return _alert(msg, "success" if ok else "warning"), (render_meetings_sections() if ok else no_update)


def register_master_rules_callbacks(app):

    @app.callback(Output("mrl-hint", "children"), Input("mrl-key", "value"), prevent_initial_call=True)
    @require_session
    @require_action(Cap.PLATFORM_RULES_MANAGE, "platform_rule")
    def show_hint(key):
        spec = rra.RULE_SPECS.get(key)
        if not spec:
            return ""
        cur = next((r for r in rra.effective_rules(REGIME) if r["rule_key"] == key), None)
        now = (cur.get("value_text") or f"{float(cur['value']):g}") if cur else "n/a"
        allowed = (f"one of {', '.join(spec.choices)}" if spec.kind == "text"
                   else f"{'whole number' if spec.kind == 'int' else 'number'} {spec.lo:g} to {spec.hi:g}")
        kind = "statutory figure" if spec.statutory else "engine policy"
        return f"In force now: {now} {cur.get('unit') or ''}. Allowed: {allowed}. This is a {kind}."

    @app.callback(_TOAST, _BODY, Input("mrl-save", "n_clicks"),
                  State("mrl-key", "value"), State("mrl-value", "value"), State("mrl-eff", "value"),
                  State("mrl-source", "value"), State("mrl-reason", "value"), State("mrl-confirm", "value"),
                  prevent_initial_call=True)
    @require_session
    @require_action(Cap.PLATFORM_RULES_MANAGE, "platform_rule", on_deny=_denied)
    def save_rule(n, key, value, eff, source, reason, confirm):
        if not n:
            return no_update, no_update
        role = get_current_user_role()
        return _run(lambda uid: rra.save_rule_version(uid, role, REGIME, key, value, eff, source, reason, bool(confirm)))

    @app.callback(Output("mrl-cat-status", "value"), Output("mrl-cat-ver", "value"), Output("mrl-cat-app", "value"),
                  Output("mrl-cat-prov", "value"), Output("mrl-cat-src", "value"),
                  Input("mrl-cat-id", "value"), prevent_initial_call=True)
    @require_session
    @require_action(Cap.PLATFORM_RULES_MANAGE, "platform_rule")
    def prefill_catalog(iid):
        row = next((i for i in rra.list_instruments(REGIME) if i["id"] == iid), None)
        if not row:
            return None, None, "", "", ""
        ver = row.get("last_verified_on")
        return row["status"], ver.isoformat() if ver else None, row.get("applicability") or "", \
            row["key_provisions"], row.get("source_reference") or ""

    @app.callback(_TOAST, _BODY, Input("mrl-cat-save", "n_clicks"),
                  State("mrl-cat-id", "value"), State("mrl-cat-status", "value"), State("mrl-cat-app", "value"),
                  State("mrl-cat-prov", "value"), State("mrl-cat-src", "value"), State("mrl-cat-ver", "value"),
                  State("mrl-cat-reason", "value"), prevent_initial_call=True)
    @require_session
    @require_action(Cap.PLATFORM_RULES_MANAGE, "platform_rule", on_deny=_denied)
    def save_catalog(n, iid, status, app_txt, prov, src, ver, reason):
        if not n:
            return no_update, no_update
        role = get_current_user_role()
        return _run(lambda uid: rra.update_instrument(uid, role, iid, status, app_txt, prov, src, ver, reason))

    @app.callback(_TOAST, _BODY, Input("mrl-cash-save", "n_clicks"),
                  State("mrl-cash-soc", "value"), State("mrl-cash-mode", "value"), State("mrl-cash-reason", "value"),
                  prevent_initial_call=True)
    @require_session
    @require_action(Cap.PLATFORM_RULES_MANAGE, "platform_rule", on_deny=_denied)
    def save_cash_mode(n, soc, mode, reason):
        if not n:
            return no_update, no_update
        role = get_current_user_role()
        return _run(lambda uid: rra.set_cash_limit_mode(uid, role, soc, mode, reason))

    # ── Society Bye-Laws callbacks ──────────────────────────────────────────────
    @app.callback(_TOAST, _BYE_BODY, Input("mrl-bye-save", "n_clicks"),
                  State("mrl-bye-soc", "value"), State("mrl-bye-clause", "value"), State("mrl-bye-layer", "value"),
                  State("mrl-bye-status", "value"), State("mrl-bye-variation", "value"), State("mrl-bye-eff", "value"),
                  State("mrl-bye-reason", "value"), State("mrl-bye-res", "value"),
                  prevent_initial_call=True)
    @require_session
    @require_action(Cap.PLATFORM_RULES_MANAGE, "platform_rule", on_deny=_denied)
    def save_bye_law(n, soc, clause, layer, status, variation, eff, reason, res_id):
        if not n or not soc or not clause or not layer or not status:
            return no_update, no_update
        role = get_current_user_role()
        return _run_bye(lambda uid: rra.save_bye_law_version(
            uid, role, int(soc), clause, int(layer), status,
            variation or None, eff, reason, int(res_id) if res_id else None))

    @app.callback(_TOAST, _BYE_BODY, Input("mrl-link-save", "n_clicks"),
                  State("mrl-link-soc", "value"), State("mrl-link-clause", "value"), State("mrl-link-layer", "value"),
                  State("mrl-link-res", "value"), State("mrl-link-reason", "value"),
                  prevent_initial_call=True)
    @require_session
    @require_action(Cap.PLATFORM_RULES_MANAGE, "platform_rule", on_deny=_denied)
    def link_bye_law(n, soc, clause, layer, res_id, reason):
        if not n or not soc or not clause or not layer or not res_id:
            return no_update, no_update
        role = get_current_user_role()
        return _run_bye(lambda uid: rra.link_provisional_to_resolution(
            uid, role, int(soc), clause, int(layer), int(res_id), reason))

    # ── Meetings & Resolutions callbacks ────────────────────────────────────────
    @app.callback(_TOAST, _MTG_BODY, Input("mrl-mtg-save", "n_clicks"),
                  State("mrl-mtg-soc", "value"), State("mrl-mtg-type", "value"), State("mrl-mtg-date", "value"),
                  State("mrl-mtg-quorum", "value"), State("mrl-mtg-minutes", "value"), State("mrl-mtg-reason", "value"),
                  prevent_initial_call=True)
    @require_session
    @require_action(Cap.PLATFORM_RULES_MANAGE, "platform_rule", on_deny=_denied)
    def save_meeting(n, soc, mtype, mdate, quorum, minutes, reason):
        if not n or not soc or not mtype or not mdate:
            return no_update, no_update
        role = get_current_user_role()
        return _run_mtg(lambda uid: rra.create_meeting(
            uid, role, int(soc), mtype, mdate, bool(quorum), minutes or None, reason))

    @app.callback(Output("mrl-res-majority", "value"), Input("mrl-res-dt", "value"), prevent_initial_call=True)
    @require_session
    @require_action(Cap.PLATFORM_RULES_MANAGE, "platform_rule")
    def prefill_resolution_majority(dt_id):
        if not dt_id:
            return no_update
        dt = next((dt for dt in rra.list_decision_types() if dt["id"] == int(dt_id)), None)
        return float(dt["majority_pct"]) if dt else no_update

    @app.callback(_TOAST, _MTG_BODY, Input("mrl-res-save", "n_clicks"),
                  State("mrl-res-soc", "value"), State("mrl-res-mtg", "value"), State("mrl-res-dt", "value"),
                  State("mrl-res-clause", "value"), State("mrl-res-body", "value"), State("mrl-res-majority", "value"),
                  State("mrl-res-passed", "value"), State("mrl-res-passed-on", "value"), State("mrl-res-reason", "value"),
                  prevent_initial_call=True)
    @require_session
    @require_action(Cap.PLATFORM_RULES_MANAGE, "platform_rule", on_deny=_denied)
    def save_resolution(n, soc, mtg_id, dt_id, clause, body, majority, passed, passed_on, reason):
        if not n or not soc or not mtg_id or not dt_id or not body:
            return no_update, no_update
        role = get_current_user_role()
        return _run_mtg(lambda uid: rra.create_resolution(
            uid, role, int(soc), int(mtg_id), int(dt_id),
            clause or None, body, float(majority) if majority else None,
            bool(passed), passed_on if passed else None, reason))

    # Enactment execution
    @app.callback(_TOAST, _MTG_BODY, Input({"type": "mrl-enact", "index": ALL}, "n_clicks"),
                  State({"type": "mrl-enact", "index": ALL}, "id"),
                  prevent_initial_call=True)
    @require_session
    @require_action(Cap.PLATFORM_RULES_MANAGE, "platform_rule", on_deny=_denied)
    def execute_enactment(n_clicks, ids):
        if not n_clicks or not any(n_clicks):
            return no_update, no_update
        # Find which button was clicked
        triggered = [i for i, n in zip(ids, n_clicks) if n]
        if not triggered:
            return no_update, no_update
        effect_id = triggered[0]["index"]
        role = get_current_user_role()
        return _run_mtg(lambda uid: rra.execute_enactment(uid, role, effect_id))
