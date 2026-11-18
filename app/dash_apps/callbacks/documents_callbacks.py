# app/dash_apps/callbacks/documents_callbacks.py
"""
Callbacks for the Settings -> Documents tab: the kind filter, and Verify / Verify all (re-hash the stored PDF against the
SHA-256 recorded when it was issued, and say whether it still matches the record it was made from).

Admin of the signed-in society only. The society and the role come from the server session (Flask-Login), never from the browser.
A failed check is written to the audit log, one entry per file.
"""
import logging

from dash import ALL, Input, Output, ctx, no_update
from dash.exceptions import PreventUpdate

from app.dash_apps.pages import documents_page as dp
from app.security.audit_context import (
    get_current_society_id,
    get_current_user_id,
    get_current_user_role,
)
from app.security.guards import require_session
from app.services import document_archive as da

log = logging.getLogger(__name__)
P = dp.P


def _admin_scope():
    """(society_id, user_id) of the signed-in administrator, else (None, None)."""
    sid, uid = get_current_society_id(), get_current_user_id()
    if not sid or uid is None or get_current_user_role() != "admin":
        return None, None
    return int(sid), int(uid)


def _audit_failure(sid: int, uid: int, doc_id: int, result: dict) -> None:
    try:
        from app.services import onboarding_service as ob
        ob._audit(sid, uid, "DOCUMENT_INTEGRITY_FAILED", "issued_documents", doc_id, {"status": result["status"], "via": "verify"})
    except Exception:                                              # noqa: BLE001
        log.exception("could not audit the integrity failure of document %s", doc_id)


def register_documents_callbacks(app):

    @app.callback(
        Output({"type": f"{P}-status", "id": ALL}, "children"),
        Output(f"{P}-summary", "children"),
        Input({"type": f"{P}-verify", "id": ALL}, "n_clicks"),
        Input(f"{P}-verify-all", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def idoc_verify(_clicks, _all_clicks):
        trig = ctx.triggered_id
        if trig is None or not (ctx.triggered and ctx.triggered[0].get("value")):
            raise PreventUpdate                                    # a re-rendered table, not a click
        sid, uid = _admin_scope()
        if not sid:
            raise PreventUpdate
        row_ids = [o["id"]["id"] for o in ctx.outputs_list[0]]
        targets = row_ids if trig == f"{P}-verify-all" else ([trig["id"]] if isinstance(trig, dict) else [])
        results = {}
        for doc_id in targets:
            try:
                results[doc_id] = da.verify_document(sid, doc_id)
            except da.ArchiveError:
                results[doc_id] = {"status": "not_found"}
        for doc_id, res in results.items():
            if res["status"] in ("missing", "altered"):
                _audit_failure(sid, uid, doc_id, res)
        statuses, summary = dp.verify_outcome(results, row_ids)
        return [no_update if s is None else s for s in statuses], summary

    @app.callback(
        Output(f"{P}-table", "children"),
        Output(f"{P}-summary", "children", allow_duplicate=True),
        Input(f"{P}-kind", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def idoc_filter(kind):
        sid, _uid = _admin_scope()
        if not sid:
            raise PreventUpdate
        return dp.register_body(sid, kind or "all"), None
