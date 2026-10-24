# app/dash_apps/callbacks/tax_rate_callbacks.py
"""
Callbacks for the "TDS & GST Rates" tab: save GST rates, save TDS rates, confirm.

Who: the CA (accountant login), the Treasurer, or the Secretary while no Treasurer is seated. The capability
finance.taxrates.manage is asked of the policy engine in _gate(); the Secretary's conditional right and every write are
re-checked inside app/services/tax_rate_service.py. The society ALWAYS comes from the server session, never from a
browser value.
"""
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, no_update

from app.dash_apps.pages import tax_rates_page as tp
from app.security.audit_context import get_current_society_id
from app.security.authorization import Cap
from app.security.guards import require_session
from app.security.service_guard import check
from app.services import tax_rate_service as trs

P = tp.P
_TOAST = Output(f"{P}-toast", "children", allow_duplicate=True)
_BODY = Output(f"{P}-body", "children", allow_duplicate=True)


def _alert(msg, color):
    return dbc.Alert(msg, color=color, dismissable=True, style={"borderRadius": "8px", "fontSize": "13px"})


def _ctx():
    """(society_id, None) when the current user may edit tax rates in their OWN society, else (None, alert).
    The capability is asked of the policy engine here; the Secretary's right (no Treasurer seated) depends on
    committee_offices, so it is the one other way in. Both are re-checked inside the service on every write."""
    sid = get_current_society_id()
    if not sid:
        return None, _alert("Society not resolved.", "danger")
    sid = int(sid)
    allowed = check(Cap.FINANCE_TAX_RATES_MANAGE, "tax_rate_config", target_society_id=sid,
                    audit_denials=False).allowed or trs.secretary_fallback_allowed(sid)
    if not allowed:
        return None, _alert("Only the CA, the Treasurer (or the Secretary when no Treasurer is seated) can do that.", "danger")
    return sid, None


def _by_id(ids, values):
    return {i["id"]: v for i, v in zip(ids or [], values or [])}


def register_tax_rate_callbacks(app):

    @app.callback(_TOAST, _BODY, Input(f"{P}-gst-save", "n_clicks"),
                  State(f"{P}-cgst", "value"), State(f"{P}-sgst", "value"), prevent_initial_call=True)
    @require_session
    def tr_save_gst(n, cgst, sgst):
        if not n:
            return no_update, no_update
        sid, err = _ctx()
        if err:
            return err, no_update
        if cgst in (None, "") or sgst in (None, ""):
            return _alert("Enter both CGST and SGST.", "warning"), no_update
        try:
            trs.save_gst_rates(sid, cgst, sgst)
        except (ValueError, PermissionError) as exc:
            return _alert(str(exc), "danger"), no_update
        return _alert("GST rates saved. Pending confirmation.", "success"), tp.tax_rates_body(sid, True)

    @app.callback(_TOAST, _BODY, Input(f"{P}-tds-save", "n_clicks"),
                  State({"type": f"{P}-rate", "id": ALL}, "id"), State({"type": f"{P}-rate", "id": ALL}, "value"),
                  State({"type": f"{P}-rate-nopan", "id": ALL}, "id"), State({"type": f"{P}-rate-nopan", "id": ALL}, "value"),
                  State({"type": f"{P}-single", "id": ALL}, "id"), State({"type": f"{P}-single", "id": ALL}, "value"),
                  State({"type": f"{P}-annual", "id": ALL}, "id"), State({"type": f"{P}-annual", "id": ALL}, "value"),
                  prevent_initial_call=True)
    @require_session
    def tr_save_tds(n, rate_ids, rates, np_ids, nopan, s_ids, single, a_ids, annual):
        if not n:
            return no_update, no_update
        sid, err = _ctx()
        if err:
            return err, no_update
        rate, nopan_m, single_m, annual_m = (_by_id(rate_ids, rates), _by_id(np_ids, nopan),
                                             _by_id(s_ids, single), _by_id(a_ids, annual))
        changes = [{"id": rid, "rate": rate.get(rid), "rate_no_pan": nopan_m.get(rid),
                    "single_bill_threshold": single_m.get(rid), "annual_aggregate_threshold": annual_m.get(rid)}
                   for rid in rate]
        try:
            changed = trs.save_tds_rates(sid, changes)
        except (ValueError, PermissionError) as exc:
            return _alert(str(exc), "danger"), no_update
        msg = f"{changed} TDS row(s) saved. Pending confirmation." if changed else "Nothing changed."
        return _alert(msg, "success" if changed else "info"), tp.tax_rates_body(sid, True)

    @app.callback(_TOAST, _BODY, Input(f"{P}-confirm", "n_clicks"), prevent_initial_call=True)
    @require_session
    def tr_confirm(n):
        if not n:
            return no_update, no_update
        sid, err = _ctx()
        if err:
            return err, no_update
        try:
            trs.confirm_ca_rates(sid)
        except PermissionError as exc:
            return _alert(str(exc), "danger"), no_update
        return _alert("TDS and GST rates confirmed.", "success"), tp.tax_rates_body(sid, True)

    _NEW = ("section", "disc", "from", "act", "rate", "nopan", "single", "annual", "nature")

    @app.callback(_TOAST, _BODY, Input(f"{P}-tds-add", "n_clicks"),
                  *[State(f"{P}-new-{k}", "value") for k in _NEW], prevent_initial_call=True)
    @require_session
    def tr_add_tds(n, section, disc, eff_from, act, rate, nopan, single, annual, nature):
        if not n:
            return no_update, no_update
        sid, err = _ctx()
        if err:
            return err, no_update
        try:
            trs.add_tds_rate(sid, {
                "section": section, "discriminator": disc, "effective_from": eff_from, "act_version": act,
                "rate": rate, "rate_no_pan": nopan, "single_bill_threshold": single,
                "annual_aggregate_threshold": annual, "nature_of_income": nature})
        except (ValueError, PermissionError) as exc:
            return _alert(str(exc), "danger"), no_update
        return _alert("Rate added. Pending confirmation.", "success"), tp.tax_rates_body(sid, True)
