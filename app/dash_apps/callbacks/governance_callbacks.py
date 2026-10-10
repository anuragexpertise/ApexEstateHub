import json
from dash import Input, Output, State, callback, html, dcc, ALL, MATCH, no_update, callback_context
import dash_bootstrap_components as dbc

from app.dash_apps.pages.governance_settings import render_tab_content
from app.services.regime_rules_admin import RegimeRulesAdmin
from app.services.db import db

@callback(
    Output("gov-tab-content", "children"),
    Input("gov-tabs", "value"),
    State("session-sid", "data"),
    prevent_initial_call=False
)
def load_gov_tab(tab, sid):
    if not sid:
        return html.Div("No society selected")
    rra = RegimeRulesAdmin(db)
    return render_tab_content(tab, rra, sid)

@callback(
    Output("rules-table", "children"),
    Output("rules-scheduled", "children"),
    Output("rules-audit", "children"),
    Output("cash-limit-mode", "value"),
    Input("gov-tabs", "value"),
    State("session-sid", "data"),
    prevent_initial_call=False
)
def load_rules(tab, sid):
    if tab != "tab-rules" or not sid:
        return no_update, no_update, no_update, no_update
    rra = RegimeRulesAdmin(db)
    trows = []
    try:
        rows = rra.list_rule_params(sid) if hasattr(rra, 'list_rule_params') else []
    except Exception:
        rows = []
    for r in rows or []:
        is_stat = r.get('is_statute') or r.get('statute')
        action = html.Span("Statute (Master Managed)", className="badge bg-light text-dark") if is_stat else dbc.Button("Edit", id={"type": "rule-edit", "key": r.get('rule_key')}, size="sm", color="secondary", disabled=True)
        trows.append(html.Tr([
            html.Td(r.get('rule_key')),
            html.Td(r.get('current_value')),
            html.Td(r.get('unit') or '-'),
            html.Td(r.get('source_ref') or r.get('source_reference') or '-'),
            html.Td(r.get('type') or '-'),
            html.Td(action)
        ]))
    table = dbc.Table([html.Thead(html.Tr(["Rule Key","Current Value","Unit","Source Reference","Type","Action"])), html.Tbody(trows)], bordered=True, hover=True, size="sm", striped=True) if trows else html.Small("No rule params")

    srows = []
    try:
        sch = rra.scheduled_changes(sid) if hasattr(rra, 'scheduled_changes') else []
    except Exception:
        sch = []
    for s in sch or []:
        srows.append(html.Tr([html.Td(s.get('rule_key')), html.Td(s.get('effective_from')), html.Td(s.get('new_value')), html.Td(s.get('status') or '-')]))
    stable = dbc.Table([html.Thead(html.Tr(["Rule","Effective","New Value","Status"])), html.Tbody(srows)], bordered=True, hover=True, size="sm", striped=True) if srows else html.Small("No scheduled changes")

    arows = []
    try:
        aud = rra.audit_log_last25(sid)
    except Exception:
        aud = []
    for a in aud or []:
        arows.append(html.Tr([html.Td(a.get('created_at')), html.Td(a.get('rule_key')), html.Td(a.get('action')), html.Td(a.get('changed_by') or '-'), html.Td(a.get('note') or '-')]))
    atable = dbc.Table([html.Thead(html.Tr(["Date","Rule","Action","By","Note"])), html.Tbody(arows)], bordered=True, hover=True, size="sm", striped=True) if arows else html.Small("No audit entries")

    try:
        soc = db.fetchone("SELECT cash_limit_mode FROM societies WHERE id=%s", (sid,))
        mode = (soc or {}).get('cash_limit_mode') or 'regime default'
    except Exception:
        mode = 'regime default'
    return table, stable, atable, mode

@callback(
    Output("cash-limit-msg", "children"),
    Input("cash-limit-save", "n_clicks"),
    State("cash-limit-mode", "value"),
    State("session-sid", "data"),
    prevent_initial_call=True
)
def save_cash_limit(n, mode, sid):
    if not n or not sid: return no_update
    rra = RegimeRulesAdmin(db)
    ok, msg = rra.set_cash_limit_mode(sid, mode, 0)
    return dbc.Alert(msg, color="success" if ok else "danger", dismissable=True, duration=3000)

@callback(
    Output("bylaws-list", "children"),
    Input("gov-tabs", "value"),
    Input("pbc-save", "n_clicks"),
    State("session-sid", "data"),
    prevent_initial_call=False
)
def load_bylaws(tab, _n, sid):
    if tab != "tab-bye" or not sid: return no_update
    rra = RegimeRulesAdmin(db)
    trows = []
    try:
        rows = rra.list_bylaw_provisional(sid)
    except Exception:
        rows = []
    for r in rows or []:
        var = r.get('variation') or r.get('option') or '-'
        eff = r.get('effective_date') or '-'
        state = r.get('state') or '-'
        res = r.get('resolution_id') or '-'
        trows.append(html.Tr([
            html.Td(r.get('clause_no')),
            html.Td(r.get('clause_title') or '-'),
            html.Td(r.get('layer') or '-'),
            html.Td(var),
            html.Td(eff),
            html.Td(html.Span(state, className="badge bg-info" if state=='Draft' else "badge bg-success" if state in ('Approved','Enacted') else "badge bg-secondary")),
            html.Td(res),
            html.Td(dbc.Button("Profile (Society Bye-laws)", id={"type": "pbc-open", "cno": r.get('clause_no')}, size="sm", color="primary"))
        ]))
    return dbc.Table([html.Thead(html.Tr(["Clause No","Title","Layer","Variation","Effective Date","State","Resolution","Action"])), html.Tbody(trows)], bordered=True, hover=True, size="sm", striped=True) if trows else html.Small("No provisional by-law choices")

@callback(
    Output("pbc-modal", "is_open"),
    Output("pbc-clause-no", "value"),
    Output("pbc-title", "value"),
    Output("pbc-def", "value"),
    Output("pbc-link", "value"),
    Input({"type": "pbc-open", "cno": ALL}, "n_clicks"),
    State("session-sid", "data"),
    prevent_initial_call=True
)
def open_pbc(nlist, sid):
    ctx = callback_context
    if not ctx.triggered: return False, "", "", "", ""
    try:
        trig = ctx.triggered[0]['prop_id']
        cno = json.loads(trig.split('.')[0])['cno']
    except Exception:
        return False, "", "", "", ""
    rra = RegimeRulesAdmin(db)
    m = rra.get_clause_master(cno) or {}
    p = db.fetchone("SELECT * FROM society_bylaw_provisional WHERE society_id=%s AND clause_no=%s", (sid,cno)) or {}
    return True, cno, m.get('title') or p.get('clause_title') or "", m.get('definition') or p.get('clause_definition') or "", m.get('source_link') or p.get('source_link') or ""

@callback(
    Output("pbc-save-msg", "children"),
    Input("pbc-save", "n_clicks"),
    State("pbc-clause-no", "value"),
    State("pbc-title", "value"),
    State("pbc-def", "value"),
    State("pbc-link", "value"),
    State("pbc-layer", "value"),
    State("pbc-option", "value"),
    State("pbc-variation", "value"),
    State("pbc-eff", "date"),
    State("pbc-reason", "value"),
    State("session-sid", "data"),
    prevent_initial_call=True
)
def save_pbc(n, cno, title, defn, link, layer, option, var, eff, reason, sid):
    if not n or not sid or not cno: return no_update
    rra = RegimeRulesAdmin(db)
    payload = {
        "society_id": sid, "clause_no": cno, "clause_title": title,
        "clause_definition": defn, "source_link": link,
        "layer": layer or "Layer 2", "option": option or "Adopted as-is",
        "variation_text": var, "effective_date": eff, "reason": reason
    }
    ok, msg = rra.upsert_provisional_choice(payload, 0)
    return dbc.Alert(msg, color="success" if ok else "danger", dismissable=True, duration=3000)

@callback(
    Output("pol-msg", "children"),
    Input("pol-save", "n_clicks"),
    State("pol-key", "value"),
    State("pol-value", "value"),
    State("pol-reason", "value"),
    State("pol-eff", "date"),
    State("session-sid", "data"),
    prevent_initial_call=True
)
def save_policy(n, key, val, reason, eff, sid):
    if not n or not sid: return no_update
    rra = RegimeRulesAdmin(db)
    ok, msg = rra.record_policy_choice({"society_id": sid, "policy_key": key, "value_text": val, "reason": reason, "effective_date": eff}, 0)
    return dbc.Alert(msg, color="success" if ok else "danger", dismissable=True, duration=3000)

@callback(
    Output("mtgs-list", "children"),
    Input("gov-tabs", "value"),
    Input("mtg-save", "n_clicks"),
    State("session-sid", "data"),
    prevent_initial_call=False
)
def load_mtgs(tab, _n, sid):
    if tab != "tab-mtg" or not sid: return no_update
    rra = RegimeRulesAdmin(db)
    try:
        rows = rra.list_meetings(sid)
    except Exception:
        rows = []
    trows = []
    for r in rows or []:
        trows.append(html.Tr([
            html.Td(r.get('id')),
            html.Td(r.get('meeting_type')),
            html.Td(r.get('held_on') or '-'),
            html.Td("Yes" if r.get('quorum_met') else "No"),
            html.Td(r.get('minutes_pdf') or '-'),
            html.Td(r.get('created_by') or '-')
        ]))
    return dbc.Table([html.Thead(html.Tr(["ID","Type (GBM/EGM/MC)","Held On","Quorum Met","Minutes PDF","Created By"])), html.Tbody(trows)], bordered=True, hover=True, size="sm", striped=True) if trows else html.Small("No meetings")

@callback(
    Output("mtg-modal", "is_open"),
    Input("mtg-new", "n_clicks"),
    Input("mtg-close", "n_clicks"),
    State("mtg-modal", "is_open"),
    prevent_initial_call=True
)
def toggle_mtg(n1,n2,is_open):
    if n1 or n2: return not is_open
    return is_open

@callback(
    Output("mtg-save-msg", "children"),
    Input("mtg-save", "n_clicks"),
    State("mtg-type", "value"),
    State("mtg-no", "value"),
    State("mtg-held", "date"),
    State("mtg-venue", "value"),
    State("mtg-quorum", "value"),
    State("mtg-minutes", "value"),
    State("mtg-notes", "value"),
    State("session-sid", "data"),
    prevent_initial_call=True
)
def save_mtg(n, mtype, mno, held, venue, quorum, mins, notes, sid):
    if not n or not sid: return no_update
    rra = RegimeRulesAdmin(db)
    ok, msg = rra.create_meeting({
        "society_id": sid, "meeting_type": mtype, "meeting_no": mno,
        "held_on": held, "venue": venue, "quorum_met": quorum == 'yes',
        "minutes_pdf": mins, "notes": notes
    }, 0)
    return dbc.Alert(msg, color="success" if ok else "danger", dismissable=True, duration=3000)

@callback(
    Output("ress-list", "children"),
    Input("gov-tabs", "value"),
    Input("res-save", "n_clicks"),
    State("session-sid", "data"),
    prevent_initial_call=False
)
def load_res(tab, _n, sid):
    if tab != "tab-mtg" or not sid: return no_update
    rra = RegimeRulesAdmin(db)
    try:
        rows = rra.list_resolutions(sid)
    except Exception:
        rows = []
    trows = []
    for r in rows or []:
        trows.append(html.Tr([
            html.Td(r.get('id')),
            html.Td(r.get('meeting_id') or '-'),
            html.Td(r.get('clause_no') or '-'),
            html.Td(r.get('decision_type')),
            html.Td(r.get('majority_pct') or 0),
            html.Td("Yes" if r.get('passed') else "No"),
            html.Td(r.get('passed_date') or '-'),
        ]))
    return dbc.Table([html.Thead(html.Tr(["ID","Meeting","Clause","Decision Type","Majority %","Passed","Passed Date"])), html.Tbody(trows)], bordered=True, hover=True, size="sm", striped=True) if trows else html.Small("No resolutions")

@callback(
    Output("res-modal", "is_open"),
    Input("res-new", "n_clicks"),
    Input("res-close", "n_clicks"),
    State("res-modal", "is_open"),
    prevent_initial_call=True
)
def toggle_res(n1,n2,is_open):
    if n1 or n2: return not is_open
    return is_open

@callback(
    Output("res-save-msg", "children"),
    Input("res-save", "n_clicks"),
    State("res-meet", "value"),
    State("res-clause", "value"),
    State("res-subj", "value"),
    State("res-decision", "value"),
    State("res-text", "value"),
    State("res-major", "value"),
    State("res-passed", "value"),
    State("res-pdate", "date"),
    State("res-aff-bylaw", "value"),
    State("res-aff-pol", "value"),
    State("res-polkeys", "value"),
    State("session-sid", "data"),
    prevent_initial_call=True
)
def save_res(n, meet, clause, subj, dec, text, major, passed, pdate, affb, affp, polkeys, sid):
    if not n or not sid: return no_update
    rra = RegimeRulesAdmin(db)
    pk = [k.strip() for k in str(polkeys).split(',')] if polkeys else []
    rid, msg = rra.create_resolution({
        "society_id": sid, "meeting_id": meet, "clause_no": clause, "subject": subj,
        "decision_type": dec, "text": text, "majority_pct": major or 0,
        "passed": passed == 'yes', "passed_date": pdate,
        "affects_bylaw": affb == 'yes', "affects_policy": affp == 'yes',
        "policy_keys": pk
    }, 0)
    return dbc.Alert(msg, color="success" if rid else "danger", dismissable=True, duration=3000)

@callback(
    Output("enacted-list", "children"),
    Input("gov-tabs", "value"),
    Input({"type": "exec-eff", "id": ALL}, "n_clicks"),
    State("session-sid", "data"),
    prevent_initial_call=False
)
def load_enacted(tab, _n, sid):
    if tab != "tab-mtg" or not sid: return no_update
    rra = RegimeRulesAdmin(db)
    try:
        rows = rra.list_enacted_pending(sid)
    except Exception:
        rows = []
    trows = []
    for r in rows or []:
        trows.append(html.Tr([
            html.Td(r.get('id')),
            html.Td(r.get('resolution_id')),
            html.Td(r.get('effect_type')),
            html.Td(r.get('target_key')),
            html.Td(r.get('status')),
            html.Td(dbc.Button("Execute", id={"type": "exec-eff", "id": r.get('id')}, size="sm", color="success"))
        ]))
    return dbc.Table([html.Thead(html.Tr(["Effect ID","Resolution","Type","Target","Status","Action"])), html.Tbody(trows)], bordered=True, hover=True, size="sm", striped=True) if trows else html.Small("No pending enactments")

@callback(
    Output("exec-msg", "children"),
    Input({"type": "exec-eff", "id": ALL}, "n_clicks"),
    State("session-sid", "data"),
    prevent_initial_call=True
)
def exec_eff(nlist, sid):
    ctx = callback_context
    if not ctx.triggered: return no_update
    try:
        eid = json.loads(ctx.triggered[0]['prop_id'])['id']
    except Exception: return no_update
    rra = RegimeRulesAdmin(db)
    ok, msg = rra.execute_enactment(eid, 0)
    return dbc.Alert(msg, color="success" if ok else "danger", dismissable=True, duration=3000)

@callback(Output("pbc-modal","is_open", allow_duplicate=True), Input("pbc-close","n_clicks"), State("pbc-modal","is_open"), prevent_initial_call=True)
def close_pbc(n,is_open): return not is_open if n else is_open

@callback(Output("mtg-modal","is_open", allow_duplicate=True), Input("mtg-close","n_clicks"), State("mtg-modal","is_open"), prevent_initial_call=True)
def close_mtg(n,is_open): return not is_open if n else is_open

@callback(Output("res-modal","is_open", allow_duplicate=True), Input("res-close","n_clicks"), State("res-modal","is_open"), prevent_initial_call=True)
def close_res(n,is_open): return not is_open if n else is_open
