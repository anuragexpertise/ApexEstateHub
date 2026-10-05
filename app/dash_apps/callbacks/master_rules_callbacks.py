# app/dash_apps/callbacks/master_rules_callbacks.py
"""
Callbacks for Master Portal -> "AOA Rule Editor" and the catalog form on "RWA Compliance (UP)". Master only:
rule values, catalog entries and per-society cash-limit mode. Bye-law adoption, meetings and resolutions are
the society admin's (callbacks/governance_callbacks.py). Thin wrappers: the role comes from the
server-side Flask-Login session (never the browser's auth-store), the work is done by
app.services.regime_rules_admin, and the body is re-rendered only after a successful save.
"""
import dash_bootstrap_components as dbc
from dash import Input, Output, State, no_update

from app.dash_apps.pages.master_rules_page import REGIME, render_rules_sections
from app.security.audit_context import get_current_user_id, get_current_user_role
from app.services import regime_rules_admin as rra
from app.security.guards import require_session
from app.security.authorization import Cap
from app.security.service_guard import require_action

_TOAST = Output("mrl-toast", "children", allow_duplicate=True)
_BODY = Output("mrl-body", "children", allow_duplicate=True)


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
