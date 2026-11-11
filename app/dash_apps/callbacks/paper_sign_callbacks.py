# app/dash_apps/callbacks/paper_sign_callbacks.py
"""
Adoption of the Model Bye-Laws 1-58 (Society_bye_laws.xlsx): template download, validated xlsx import that fills the choice
buttons, and ONE plain upload of the signed General Body minutes (purpose adoption_minutes). The clause choices are data; no
generated print / sign / scan loop remains. After go-live the choices and the minutes SHA-256 are sealed in Annex G.

Listed in _SETUP_EXEMPT_MODULES: the Adoption panel lives in the Onboarding Hub, which a not-yet-active society uses. Every
callback checks the session and the admin role itself.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update

from app.security.audit_context import get_current_society_id, get_current_user_id, get_current_user_role
from app.security.guards import require_session
from app.services import onboarding_service as ob
from app.services import regime_rules_admin as rra
from app.services import xlsx_templates as xt

PURPOSE = "adoption_minutes"
_CHOICE_LABEL = {"adopted_as_is": "Adopted as is", "adopted_with_variation": "Adopted with variation",
                 "not_adopted": "Not adopted"}


def _session():
    uid = get_current_user_id()
    if not uid:
        return None
    sid = get_current_society_id()
    return (int(sid) if sid else None), int(uid), get_current_user_role()


def _admin():
    s = _session()
    return s if (s and s[0] and s[2] == "admin") else None


def current_choices(society_id: int) -> dict:
    """clause_id -> {choice, variation_text, active} as recorded for this society (layer 1)."""
    out = {}
    for r in rra.list_society_bye_laws(society_id) or []:
        if r.get("layer") != 1:
            continue
        prov = r.get("status") == "provisional"
        out[r["clause_id"]] = {"choice": (r.get("proposed_status") if prov else r.get("status")),
                               "variation_text": r.get("variation_text") or "",
                               "active": bool(r.get("resolution_id")) and not prov}
    return out


def _status(society_id: int):
    """Status of the signed General Body minutes on file."""
    ev = ob.get_evidence(society_id, PURPOSE)
    if not ev:
        return html.Div("No signed General Body minutes on file yet.", className="text-muted")
    e = ev[0]
    return dbc.Alert([html.I(className="fas fa-check-circle me-2"),
                      f"Minutes on file: {e['filename']} (SHA-256 {e['sha256'][:16]}...). It is bound into Annex G."],
                     color="success", className="py-1 mb-0", style={"fontSize": "12px"})


def register_paper_sign_callbacks(app):

    @app.callback(Output("adopt-bl-tpl-dl", "data"), Input("adopt-bl-tpl", "n_clicks"), prevent_initial_call=True)
    @require_session
    def adopt_template(n):
        s = _admin()
        if not n or not s:
            return no_update
        sid = s[0]
        cur = current_choices(sid)
        locked = [cid for cid, _ in rra.MODEL_BYE_LAW_CLAUSES
                  if rra.clause_is_locked(sid, cid) or cid in rra.STATUTE_BACKED_CLAUSES]
        data = xt.build_bye_laws_template(rra.MODEL_BYE_LAW_CLAUSES, cur, locked)
        return dcc.send_bytes(data, "Society_bye_laws.xlsx")

    @app.callback(
        Output({"type": "sw-bl-choice", "clause": ALL}, "value", allow_duplicate=True),
        Output({"type": "sw-bl-var", "clause": ALL}, "value", allow_duplicate=True),
        Output("adopt-bl-import-status", "children"),
        Input("adopt-bl-xlsx", "contents"),
        State("adopt-bl-xlsx", "filename"),
        prevent_initial_call=True,
    )
    @require_session
    def adopt_import(contents, filename):
        """Validate Society_bye_laws.xlsx and fill the choice buttons. The existing live-save then records each one as a
        provisional choice, so nothing is applied until the resolution is recorded."""
        def fail(msg):
            n_c = len(ctx.outputs_list[0] or []); n_v = len(ctx.outputs_list[1] or [])
            return [no_update] * n_c, [no_update] * n_v, dbc.Alert(msg, color="danger", className="py-1 mb-0",
                                                                  style={"fontSize": "12px"})
        s = _admin()
        if not s or not contents:
            return fail("Only the admin can import the bye-law choices.")
        sid = s[0]
        res = xt.parse_upload(contents, filename or "", "Bye-laws", ["clause_id", "choice"], max_rows=80)
        if res.errors:
            return fail(" ".join(res.errors))
        locked = [cid for cid, _ in rra.MODEL_BYE_LAW_CLAUSES
                  if rra.clause_is_locked(sid, cid) or cid in rra.STATUTE_BACKED_CLAUSES]
        ok = xt.validate_bye_law_rows(res.rows, [c for c, _ in rra.MODEL_BYE_LAW_CLAUSES], locked)
        if ok.errors:
            shown = ok.errors[:6] + ([f"...and {len(ok.errors) - 6} more."] if len(ok.errors) > 6 else [])
            return fail("Nothing imported. Fix the file: " + " ".join(shown))
        by = {r["clause_id"]: r for r in ok.rows}
        active = {cid for cid, v in current_choices(sid).items() if v.get("active")}
        applied, skipped = 0, []
        choice_out, var_out = [], []
        for item in ctx.outputs_list[0] or []:
            cid = (item.get("id") or {}).get("clause")
            if cid in by and cid not in active:
                choice_out.append(by[cid]["choice"]); applied += 1
            else:
                choice_out.append(no_update)
        for item in ctx.outputs_list[1] or []:
            cid = (item.get("id") or {}).get("clause")
            var_out.append(by[cid]["variation_text"] if cid in by and cid not in active else no_update)
        skipped = sorted(cid for cid in by if cid in active)
        msg = f"Imported {applied} clause choice(s) from {filename}. They are saved as provisional choices."
        if skipped:
            msg += " Already active (resolution on file), left unchanged: " + ", ".join(skipped) + "."
        return choice_out, var_out, dbc.Alert(msg, color="success", className="py-1 mb-0", style={"fontSize": "12px"})

    @app.callback(Output("adopt-bl-evidence-status", "children"), Input("adopt-bl-scan", "contents"),
                  State("adopt-bl-scan", "filename"), prevent_initial_call=True)
    @require_session
    def adopt_scan(contents, filename):
        s = _admin()
        if not s or not contents or "," not in contents:
            return no_update
        sid, uid, _role = s
        import base64
        try:
            raw = base64.b64decode(contents.split(",", 1)[1])
            ob.store_evidence_file(sid, PURPOSE, None, filename or "", raw, uid, {"kind": "adoption_minutes"})
        except Exception as exc:                               # noqa: BLE001
            return dbc.Alert(str(exc), color="danger", className="py-1 mb-0", style={"fontSize": "12px"})
        return _status(sid)
