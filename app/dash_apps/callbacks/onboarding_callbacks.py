# app/dash_apps/callbacks/onboarding_callbacks.py
"""
Callbacks for the Onboarding Hub (pages/onboarding_page.py).

This module is exempt from the setup gate (app/security/guards.py): the hub is the thing a society uses WHILE it is not
yet active. Because of that every callback decides for itself, from the SERVER session, who may do what:

  * seating, grievance officer, annex preparation and sealing: the society's administrator only;
  * signing the Agreement: only a login that holds the office (President / Secretary / Treasurer), with its own password;
  * the platform signature, and retrying a held activation: the master login only.
"""
import base64
import logging

import dash_bootstrap_components as dbc
from dash import ALL, MATCH, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from app.dash_apps.pages import onboarding_page as op
from app.security.audit_context import (
    get_current_society_id,
    get_current_user_id,
    get_current_user_role,
)
from app.security.guards import require_session
from app.services import document_signing as ds
from app.services import onboarding_service as ob
from app.utils.ux_toasts import celebration

log = logging.getLogger(__name__)

P = "onb"


def _session():
    sid, uid, role = get_current_society_id(), get_current_user_id(), get_current_user_role()
    if not uid:
        return None
    return (int(sid) if sid else None), int(uid), role


def _alert(msg, ok=True):
    return dbc.Alert(msg, color="success" if ok else "danger", className="py-2 mt-2", style={"fontSize": "12.5px"}, dismissable=True)


def _decode(contents):
    if not contents or "," not in contents:
        return None
    try:
        return base64.b64decode(contents.split(",", 1)[1])
    except Exception:                                                      # noqa: BLE001
        return None


def _paper_evidence(sid, uid, contents, filename):
    """Paper counterpart: the user uploads the scan, the SERVER computes the SHA-256 (nobody types a hash)."""
    raw = _decode(contents)
    if not raw:
        raise ds.SigningRefused("Upload the signed scan (PDF, PNG or JPG).")
    try:
        return ob.store_evidence_file(sid, "paper_signature", None, filename or "", raw, uid, {"kind": "agreement"})["sha256"]
    except ob.OnboardingError as exc:
        raise ds.SigningRefused(str(exc)) from exc


def _body(sid, uid, role, view=None):
    return op.hub_body(role, sid, uid, view=view), op.marker(sid)


_committee_view = op._committee_view          # defined in the page module (no page -> callbacks import cycle)


def register_onboarding_callbacks(app):
    # ── Apply Election Results.xlsx: seat every open office in one action ─────────────────────────────────────────────
    # Plain ids (not pattern-matching): the panel always renders all three offices, so every State below is in the layout.
    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-all-go", "n_clicks"),
        State(f"{P}-all-xlsx", "contents"), State(f"{P}-all-xlsx", "filename"),
        State(f"{P}-all-minutes", "contents"), State(f"{P}-all-minutes", "filename"),
        *[State(f"{P}-all-sig-{o}", "contents") for o in ob.CORE_OFFICES],
        *[State(f"{P}-all-sig-{o}", "filename") for o in ob.CORE_OFFICES],
        *[State(f"{P}-all-pw-{o}", "value") for o in ob.CORE_OFFICES],
        prevent_initial_call=True,
    )
    @require_session
    def onb_seat_all(n, xlsx_contents, xlsx_name, minutes_contents, minutes_name, *rest):
        s = _session()
        if not n or not s:
            return no_update, no_update, no_update
        sid, uid, role = s
        if role != "admin" or not sid:
            return no_update, _alert("Only the society's administrator can seat the committee.", False), no_update
        from app.services import xlsx_templates as xt
        # Use the freshly-uploaded workbook, falling back to rows already imported via
        # "Fill forms from Election Results.xlsx" (saved server-side in the draft, never in session).
        if xlsx_contents:
            raw = _decode(xlsx_contents)
            if not raw:
                return no_update, _alert("Choose the filled Election Results.xlsx first.", False), no_update
            res = xt.parse_upload(xlsx_contents, xlsx_name or "", "Election Results", ["office"], max_rows=10)
            if res.errors:
                return no_update, _alert(" ".join(res.errors), False), no_update
            rows = res.rows
            ob.save_election_rows(sid, uid, rows)
            workbook_sha = ob._sha(raw)
        else:
            rows = ob.get_election_rows(sid)
            if not rows:
                return no_update, _alert("Choose the filled Election Results.xlsx first (or use 'Fill forms from Election Results.xlsx').", False), no_update
            res = type("R", (), {"rows": rows, "errors": []})()
            workbook_sha = ""
        # Use the freshly-uploaded minutes, falling back to the scan already stored as evidence
        # (purpose election_results) via "Upload signed election minutes scan".
        if minutes_contents:
            minutes_name_used = minutes_name or ""
            minutes_bytes = _decode(minutes_contents)
        else:
            ev = ob.get_evidence(sid, "election_results") or []
            minutes_name_used = ""
            minutes_bytes = None
            if ev:
                latest = ev[0]
                minutes_name_used = latest.get("filename") or "election_minutes.pdf"
                try:
                    minutes_bytes = (ob.evidence_folder(sid) / latest["stored_name"]).read_bytes()
                except OSError:
                    minutes_bytes = None
        if not minutes_bytes:
            return no_update, _alert("Choose the signed minutes file first (or use 'Upload signed election minutes scan').", False), no_update
        k = len(ob.CORE_OFFICES)
        sig_files = {o: (rest[k + i], _decode(rest[i])) for i, o in enumerate(ob.CORE_OFFICES)}
        passwords = {o: rest[2 * k + i] or "" for i, o in enumerate(ob.CORE_OFFICES)}
        try:
            msg = ob.seat_founding_committee(uid, sid, rows, minutes_name_used, minutes_bytes, sig_files,
                                             passwords, workbook_sha256=workbook_sha)
        except ob.PartialSeating as exc:                  # some offices are now seated: show them, keep the message
            exc_out = exc
            msg = str(exc)
        except ob.OnboardingError as exc:                 # nothing changed: leave the chosen files in place
            return no_update, _alert(str(exc), False), no_update
        # File the election pair (workbook + minutes) unless there was no fresh workbook.
        filing_note = ""
        if xlsx_contents:
            try:
                from app.services import paired_intake as pi
                pi.file_election_pair(sid, uid, xlsx_name or "", raw, minutes_name_used, minutes_bytes)
            except Exception:
                log.exception("could not file the election pair for society %s", sid)
                filing_note = " No workbook was filed with the minutes."
        else:
            filing_note = " No workbook was uploaded, so no pair was filed."
        body, mk = _body(sid, uid, role, view=_committee_view(sid))
        return body, _alert(msg + filing_note, False if exc_out else True), mk

    @app.callback(
        Output(f"{P}-all-chosen", "children"),
        Input(f"{P}-all-xlsx", "filename"), Input(f"{P}-all-minutes", "filename"),
        *[Input(f"{P}-all-sig-{o}", "filename") for o in ob.CORE_OFFICES],
        prevent_initial_call=True,
    )
    @require_session
    def onb_seat_all_files(xlsx_name, minutes_name, *sig_names):
        picks = [("Workbook", xlsx_name), ("Minutes", minutes_name)] + \
                [(f"{ob.OFFICE_LABEL[o]} signature", nm) for o, nm in zip(ob.CORE_OFFICES, sig_names)]
        out = []
        for label, nm in picks:
            out.append(html.Span([f"{label}: ", html.Strong(nm) if nm else "not chosen"],
                                 style={"marginRight": "12px", "color": "#17976e" if nm else "#8895a5"}))
        return out

    # ── signature thumbnail preview while choosing a signature image ──────────
    @app.callback(
        Output({"type": f"{P}-f", "office": ALL, "field": "sig-preview"}, "children", allow_duplicate=True),
        Input({"type": f"{P}-f", "office": ALL, "field": "sig"}, "contents"),
        State({"type": f"{P}-f", "office": ALL, "field": "sig"}, "filename"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_sig_preview(contents_list, filename_list):
        trig = ctx.triggered_id
        outputs = ctx.outputs_list or []
        if not trig or not isinstance(trig, dict):
            return [no_update] * len(outputs)

        # Resolve the uploaded contents/filename for the triggered office.
        office = trig["office"]
        triggered_contents = ctx.triggered[0].get("value") if ctx.triggered else None
        fname = ""
        for item, name in zip(ctx.inputs_list[0] or [], filename_list or []):
            iid = item.get("id") if isinstance(item, dict) else item
            if isinstance(iid, dict) and iid.get("office") == office:
                fname = name or ""
                break

        if triggered_contents:
            preview = html.Div([
                html.Img(src=triggered_contents, style={"maxWidth": "140px", "maxHeight": "70px",
                                                      "border": "1px solid #c9d2dc", "borderRadius": "4px"}),
                html.Div(fname, style={"fontSize": "11px", "color": "#667", "marginTop": "2px"})])
        else:
            preview = html.Div("Signature image selected.", style={"fontSize": "11.5px", "color": "#17976e"})

        # Return exactly one value per matched output component, in order.
        out = []
        for item in outputs:
            iid = item.get("id") if isinstance(item, dict) else item
            if isinstance(iid, dict) and iid.get("office") == office:
                out.append(preview)
            else:
                out.append(no_update)
        return out

    # ── seated officer Edit details: mobile and/or signature replace ──────────
    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input({"type": f"{P}-f", "office": ALL, "field": "save"}, "n_clicks"),
        State({"type": f"{P}-f", "office": ALL, "field": "phone"}, "value"),
        State({"type": f"{P}-f", "office": ALL, "field": "sig"}, "contents"),
        State({"type": f"{P}-f", "office": ALL, "field": "sig"}, "filename"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_officer_update(_clicks, phones, sig_contents_list, sig_filename_list):
        trig = ctx.triggered_id
        if not trig or not isinstance(trig, dict):
            return no_update, no_update, no_update
        if not (ctx.triggered and ctx.triggered[0].get("value")):          # a re-rendered card, not a click
            return no_update, no_update, no_update
        s = _session()
        if not s or s[2] != "admin" or not s[0]:
            return no_update, _alert("Only the society's administrator can edit an officer.", False), no_update
        sid, uid, role = s
        office = trig["office"]
        phone = None
        for item in (ctx.states_list[0] or []):
            iid = item.get("id")
            if isinstance(iid, dict) and iid.get("office") == office and iid.get("field") == "phone":
                phone = item.get("value")
                break
        sig_contents = sig_filename = None
        for idx, item in enumerate(ctx.states_list[1] or []):
            iid = item.get("id")
            if isinstance(iid, dict) and iid.get("office") == office and iid.get("field") == "sig":
                sig_contents = item.get("value")
                sig_filename = (sig_filename_list or [None])[idx] if sig_filename_list else None
                break
        try:
            msg = ob.update_seated_officer(uid, sid, office, phone=phone,
                                           signature_name=sig_filename,
                                           signature_bytes=_decode(sig_contents))
        except ob.OnboardingError as exc:
            return no_update, _alert(str(exc), False), no_update
        body, mk = _body(sid, uid, role, view=_committee_view(sid))
        return body, _alert(msg), mk

    # ── "Complete missing details" (setup wizard, serving office-bearers list) → Stage 2 ──────────────────
    # The button lives in setup_wizard.py (render of the office-bearer list), so this callback is NOT dead.
    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output("onb-view", "data", allow_duplicate=True),
        Input("onb-back-to-committee", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_back_to_committee(n):
        s = _session()
        if not n or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update
        sid, uid, role = s
        return op.hub_body(role, sid, uid, view="committee"), "committee"

    # ── committee screen → wizard (only once the grievance officer is named) ──
    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output("onb-view", "data", allow_duplicate=True),
        Input(f"{P}-continue-setup", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_continue_setup(n):
        s = _session()
        if not n or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        st = ob.state_of(sid)
        if st == "setup draft":                  # already past the committee stage: just reopen the wizard
            return op.hub_body(role, sid, uid, view="setup"), no_update, "setup"
        if st != "committee seated":
            log.warning("continue-setup refused for society %s: onboarding_state=%r (expected 'committee seated')", sid, st)
            return no_update, _alert("The committee is not marked as seated yet. All three office-bearers (President, Secretary, "
                                     "Treasurer) need a login and signed election evidence. If they are all seated, refresh the "
                                     "page; if this persists, ask the platform operator to check the database timezone.", False), no_update
        if not op.grievance_named(sid):
            return no_update, _alert("Name the grievance officer first.", False), no_update
        return op.hub_body(role, sid, uid, view="setup"), no_update, "setup"

    # ── wizard step stores always follow whatever the body was just re-rendered to (F3) ──
    @app.callback(
        Output("onb-setup-step", "data", allow_duplicate=True),
        Output("onb-wizard-step", "data", allow_duplicate=True),
        Input(f"{P}-body", "children"),
        State("onb-view", "data"),
        State("onb-setup-step", "data"),
        State("onb-wizard-step", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_sync_step_stores(_children, view, setup_step, wizard_step):
        s = _session()
        if not s or not s[0] or s[2] != "admin":
            return no_update, no_update
        if ob.state_of(s[0]) not in ("committee seated", "setup draft"):
            return no_update, no_update
        n = op.step_from_view(view)
        if n is None:
            n = op.start_step(s[0])
        if setup_step == n and wizard_step == n:
            return no_update, no_update
        return n, n

    @app.callback(
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output("onb-view", "data", allow_duplicate=True),
        Input(f"{P}-g-save", "n_clicks"),
        State(f"{P}-g-name", "value"), State(f"{P}-g-email", "value"), State(f"{P}-g-phone", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_grievance(n, name, email, phone):
        s = _session()
        if not n or not s:
            return no_update, no_update, no_update
        sid, uid, role = s
        if role != "admin" or not sid:
            return _alert("Only the society's administrator can name the grievance officer.", False), no_update, no_update
        try:
            ob.set_grievance_officer(sid, name, email, phone)
        except ob.OnboardingError as exc:
            return _alert(str(exc), False), no_update, no_update
        view = _committee_view(sid)               # stay here so the "Continue to society setup" button is visible
        return _alert("Grievance officer saved."), op.hub_body(role, sid, uid, view=view), (view or no_update)

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Output("onb-view", "data", allow_duplicate=True),
        Input(f"{P}-prepare", "n_clicks"),
        State("op-token-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_prepare(n, op_token=None):
        s = _session()
        if not n or not s:
            return no_update, no_update, no_update, no_update
        sid, uid, role = s
        if role != "admin" or not sid:
            return no_update, _alert("Only the society's administrator can check the annexes.", False), no_update, no_update
        from app.services import op_progress
        with op_progress.begin(op_token, "annex_build", "Checking the annexes", steps_total=3, society_id=sid) as trk:
            try:
                trk.step(1, "Building Annexes A to E and testing each control")
                ob.build_annexes(sid, uid)
            except ob.OnboardingError as exc:
                trk.fail("Not ready")
                return no_update, _alert(str(exc), False), no_update, no_update
            trk.step(2, "Refreshing the checklist")
            body, mk = _body(sid, uid, role, view="current")
        return body, _alert("Annexes checked. Fix anything marked red using its link, then seal."), mk, "current"

    # ── "Fix in <step>" links on a failing annex control ─────────────────────
    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output("onb-view", "data", allow_duplicate=True),
        Input({"type": f"{P}-fix", "annex": ALL, "ctl": ALL, "key": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_fix(clicks):
        s = _session()
        trig = ctx.triggered_id
        if not s or not s[0] or s[2] != "admin" or not isinstance(trig, dict):
            return no_update, no_update
        if not (ctx.triggered and ctx.triggered[0].get("value")):          # a re-render, not a click
            return no_update, no_update
        sid, uid, role = s
        if ob.state_of(sid) not in ("committee seated", "setup draft"):
            return no_update, no_update
        key = trig.get("key")
        view = "committee" if key == "committee" else f"setup:{key}"
        return op.hub_body(role, sid, uid, view=view), view

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Output("celebrate-store", "data", allow_duplicate=True),
        Input(f"{P}-seal", "n_clicks"),
        State(f"{P}-agree", "value"), State(f"{P}-seal-pw", "value"),
        State("op-token-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_seal(n, agree, password, op_token=None):
        s = _session()
        if not n or not s:
            return no_update, no_update, no_update, no_update
        sid, uid, role = s
        if role != "admin" or not sid:
            return no_update, _alert("Only the society's administrator can seal the annexes.", False), no_update, no_update
        from app.services import op_progress
        trk = op_progress.begin(op_token, "annex_seal", "Sealing the annexes", steps_total=4, society_id=sid)
        try:
            trk.step(1, "Checking your confirmation and password")
            ob.seal_with_confirmation(sid, uid, agree, password)
            trk.step(3, "Annexes sealed. Preparing the Agreement for signing")
        except ob.OnboardingError as exc:
            trk.fail("Not sealed")
            return no_update, _alert(str(exc), False), no_update, no_update
        except Exception:
            trk.fail("Failed")
            raise
        body, mk = _body(sid, uid, role)
        trk.done("Agreement issued for signing")
        return (body, _alert("Annexes sealed and the Agreement issued for signing."), mk,
                celebration("sealed", "Agreement sealed",
                            "The annexes are sealed and the Agreement is issued for signing.",
                            ["Annexes sealed with their content hashes", "Agreement issued to the President, Secretary and Treasurer"]))

    @app.callback(
        Output(f"{P}-reissue-status", "children"),
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-reissue-agreement", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_reissue_agreement(n):
        s = _session()
        if not n or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        try:
            ob.reissue_agreement(sid, uid)
        except ob.OnboardingError as exc:
            return _alert(str(exc), False), no_update, no_update
        body, mk = _body(sid, uid, role)
        return _alert("Agreement reissued from the sealed annexes."), body, mk

    @app.callback(
        Output(f"{P}-op-status", "children"),
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-confirm-operator", "n_clicks"),
        State(f"{P}-op-name", "value"), State(f"{P}-op-addr", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_confirm_operator(n, name, address):
        s = _session()
        if not n or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        try:
            ob.confirm_operator(sid, uid, name or "", address or "")
        except ob.OnboardingError as exc:
            return _alert(str(exc), False), no_update, no_update
        body, mk = _body(sid, uid, role)
        return _alert("Operator confirmed."), body, mk

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Output("celebrate-store", "data", allow_duplicate=True),
        Input(f"{P}-sign", "n_clicks"),
        State(f"{P}-pw", "value"), State(f"{P}-method", "value"),
        State(f"{P}-paper", "contents"), State(f"{P}-paper", "filename"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_sign(n, password, method, paper, paper_name):
        s = _session()
        if not n or not s:
            return no_update, no_update, no_update, no_update
        sid, uid, role = s
        ag = ob.db._execute("SELECT id, body_text FROM society_agreements WHERE society_id=%s", (sid,), fetch_one=True) if sid else None
        if not ag or not (ag.get("body_text") or "").strip():
            return no_update, _alert("There is no Agreement to sign yet.", False), no_update, no_update
        try:
            from app.services import esign_adapter as es
            mode = ob.signing_mode(sid)
            if mode == "paper":
                st = ds.sign("agreement", ag["id"], uid, password or "", method="paper",
                             evidence_ref=_paper_evidence(sid, uid, paper, paper_name))
            elif es.is_required(sid):
                st = ds.sign("agreement", ag["id"], uid, password or "", method=method or "aadhaar_eSign")
            else:
                st = ds.sign("agreement", ag["id"], uid, password or "")
        except ds.SigningRefused as exc:
            return no_update, _alert(str(exc), False), no_update, no_update
        body, mk = _body(sid, uid, role)
        cel = (celebration("sealed", "Agreement sealed", "Every required signature is in. The Agreement is sealed.",
                           key=f"eh-agreement-sealed-{ag['id']}") if st.get("sealed") else no_update)
        return body, _alert("Signed." + (" The Agreement is sealed." if st.get("sealed") else "")), mk, cel

    @app.callback(
        Output(f"{P}-print-dl", "data"),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Input(f"{P}-print", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_print_agreement(n):
        s = _session()
        if not n or not s or not s[0]:
            return no_update, no_update
        # Direct PDF: the Agreement and annexes A to E drawn by reportlab, filed under app/assets/<society_id>/agreements/ with its
        # SHA-256 in issued_documents, and sent from that verified file. The browser-print HTML below stays as the fallback.
        try:
            from app.services import document_archive as da
            ag = ob.db._execute("SELECT id FROM society_agreements WHERE society_id=%s", (s[0],), fetch_one=True)
            if ag:
                row = da.archive_agreement(s[0], ag["id"], event="printed", created_by=s[1])
                _row, data = da.read_verified(s[0], row["id"])
                return dcc.send_bytes(data, row["filename"]), no_update
        except ob.OnboardingError as exc:
            return no_update, _alert(str(exc), False)
        except Exception:                                              # noqa: BLE001
            log.exception("Agreement PDF failed for society %s; sending the printable HTML instead", s[0])
        try:
            name, page = ob.agreement_print_html(s[0])
        except ob.OnboardingError as exc:
            return no_update, _alert(str(exc), False)
        return dcc.send_string(page, name, type="text/html"), no_update

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-esign-start", "n_clicks"), Input(f"{P}-esign-demo", "n_clicks"),
        State(f"{P}-method", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_esign_start(n_start, n_demo, method):
        s = _session()
        if not s or not (n_start or n_demo):
            return no_update, no_update, no_update
        sid, uid, role = s
        from app.services import esign_adapter as es
        ag = ob.db._execute("SELECT id FROM society_agreements WHERE society_id=%s", (sid,), fetch_one=True) if sid else None
        if not ag or not es.is_required(sid):
            return no_update, no_update, no_update
        try:
            _s_id, text = ds.item_text("agreement", ag["id"])
            u = ob.db._execute("SELECT name, email FROM users WHERE id=%s", (uid,), fetch_one=True) or {}
            if ctx.triggered_id == f"{P}-esign-demo":
                req = es.latest_for(sid, "agreement", ag["id"], uid)
                if not req:
                    return no_update, _alert("Start an eSign request first.", False), no_update
                es.simulate_completion(req["id"])
                msg = "The demo vendor completed your eSign."
            else:
                if method == "paper":
                    return no_update, _alert("A paper counterpart needs no request: upload the signed scan, then confirm with your password.", False), no_update
                es.create_request(sid, "agreement", ag["id"], u.get("name") or "Signer", u.get("email"), None,
                                  method or "aadhaar_eSign", ds.sha256(text), uid, signer_user_id=uid)
                msg = "eSign request started. Finish it with the vendor."
        except (es.EsignError, ds.SigningRefused) as exc:
            return no_update, _alert(str(exc), False), no_update
        body, mk = _body(sid, uid, role)
        return body, _alert(msg), mk

    @app.callback(
        Output("onb-tracker", "children"),
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-poll", "n_intervals"),
        State(f"{P}-marker", "data"),
        State("onb-view", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_poll(_n, last, view):
        s = _session()
        if not s or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        mk = op.marker(sid)
        if mk == last:
            return no_update, no_update, no_update
        st = ob.state_of(sid)
        # §2.3 poll safety: while the setup stage is mounted (view == "setup", or the
        # society is committee-seated / in a setup draft) the poll must not replace
        # onb-body — that wipes unsaved inputs and jumps the DOM (F3). Only refresh the
        # tracker; re-render the body only on real state transitions.
        v = view or ""
        setup_mounted = role == "admin" and (st == "committee seated" or (st == "setup draft" and (v.startswith("setup") or v == "committee")))
        if st == "active":
            return op.tracker(sid), op.hub_body(role, sid, uid), mk
        if setup_mounted:
            return op.tracker(sid), no_update, mk
        return op.tracker(sid), op.hub_body(role, sid, uid, view=view or "current"), mk

    # ── pause/resume the poller as the society moves between stages ───────────────────────────────────────────
    # The body is re-rendered on every stage transition, so it is the natural trigger. Keeps the poll off while the
    # admin is alone on the committee/setup screens and back on once others (signers) can change the state.
    @app.callback(
        Output(f"{P}-poll", "disabled"),
        Input(f"{P}-body", "children"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_poll_toggle(_children):
        s = _session()
        if not s or not s[0]:
            return no_update
        return op.poll_disabled(s[2], s[0])

    # ── Master queue ────────────────────────────────────────────────────────────────────────────────────────
    def _master_ok():
        s = _session()
        return s if s and s[2] == "master" else None

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-signmode", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_signmode(mode):
        s = _session()
        if not s or s[2] != "admin" or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        if mode == ob.signing_mode(sid):
            return no_update, no_update, no_update
        try:
            ob.set_signing_mode(sid, uid, mode)
        except Exception as exc:                                       # noqa: BLE001
            body, mk = _body(sid, uid, role)
            return body, _alert(f"The signing method could not be changed: {exc}", False), mk
        body, mk = _body(sid, uid, role)
        return body, _alert(f"Signing method is now {mode}."), mk

    # ── stage 7: adviser appointment / signing ──────────────────────────────
    ADV_FIELDS = ("kind", "name", "firm", "mno", "scope", "ts", "te", "res", "email", "pw")

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input({"type": f"{P}-adv", "field": "appoint"}, "n_clicks"),
        [State({"type": f"{P}-adv", "field": f}, "value") for f in ADV_FIELDS],
        prevent_initial_call=True,
    )
    @require_session
    def onb_adviser_appoint(n, kind, name, firm, mno, scope, ts, te, res, email, pw):
        s = _session()
        if not n or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        try:
            msg = ob.appoint_adviser(uid, sid, kind, name, firm, mno, scope, ts, te,
                                     int(res) if res not in (None, "") else None, email, pw)
        except ob.OnboardingError as exc:
            return no_update, _alert(str(exc), False), no_update
        body, mk = _body(sid, uid, role)
        return body, _alert(msg), mk

    @app.callback(
        Output({"type": f"{P}-mmsg", "sid": MATCH}, "children", allow_duplicate=True),
        Input({"type": f"{P}-mstart", "sid": MATCH}, "n_clicks"), Input({"type": f"{P}-mdemo", "sid": MATCH}, "n_clicks"),
        State({"type": f"{P}-mmethod", "sid": MATCH}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_master_esign(n_start, n_demo, method):
        s = _master_ok()
        if not s or not ctx.triggered_id or not (n_start or n_demo):
            return no_update
        sid = int(ctx.triggered_id["sid"])
        from app.services import esign_adapter as es
        ag = ob.db._execute("SELECT id FROM society_agreements WHERE society_id=%s", (sid,), fetch_one=True)
        if not ag or not es.is_required(sid):
            return no_update
        try:
            if ctx.triggered_id["type"] == f"{P}-mdemo":
                req = es.latest_for(sid, "agreement", ag["id"], s[1])
                if not req:
                    return _alert("Start an eSign request first.", False)
                es.simulate_completion(req["id"])
                return _alert("The demo vendor completed the platform's eSign. Now confirm with your password.")
            if method == "paper":
                return _alert("A paper counterpart needs no request: upload the signed scan and sign.", False)
            _x, text = ds.item_text("agreement", ag["id"])
            u = ob.db._execute("SELECT name, email FROM users WHERE id=%s", (s[1],), fetch_one=True) or {}
            es.create_request(sid, "agreement", ag["id"], u.get("name") or "Platform signatory", u.get("email"), None,
                              method or "dsc", ds.sha256(text), s[1], signer_user_id=s[1])
        except (es.EsignError, ds.SigningRefused) as exc:
            return _alert(str(exc), False)
        return _alert("eSign request started. Finish it with the vendor, then confirm with your password.")

    @app.callback(
        Output({"type": f"{P}-advmsg", "id": MATCH}, "children"),
        Input({"type": f"{P}-adv-sign", "id": MATCH}, "n_clicks"),
        State({"type": f"{P}-adv-pw", "id": MATCH}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_adviser_sign(n, password):
        s = _session()
        if not n or not s or not ctx.triggered_id:
            return no_update
        _sid, uid, _role = s
        appt_id = int(ctx.triggered_id["id"])
        try:
            st = ds.sign("adviser_appointment", appt_id, uid, password or "")
        except ds.SigningRefused as exc:
            return _alert(str(exc), False)
        return _alert("Adviser appointment signed." + (" Sealed." if st.get("sealed") else ""))

    # ── stage: legacy resolution import (V5.8) ──────────────────────────────
    LEG_FIELDS = ("held", "mtype", "dtype", "outcome", "mfile", "mhash", "body")

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input({"type": f"{P}-leg", "field": "import"}, "n_clicks"),
        [State({"type": f"{P}-leg", "field": f}, "value") for f in LEG_FIELDS],
        prevent_initial_call=True,
    )
    @require_session
    def onb_legacy_import(n, held, mtype, dtype, outcome, mfile, mhash, body):
        s = _session()
        if not n or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        try:
            msg = ob.import_legacy_resolution(sid, uid, held, mtype or "GBM", int(dtype) if dtype not in (None, "") else None,
                                              body, mfile, mhash, outcome or "unknown")
        except (ob.OnboardingError, ValueError, TypeError) as exc:
            return no_update, _alert(str(exc), False), no_update
        body_html, mk = _body(sid, uid, role)
        return body_html, _alert(msg), mk

    def _platform_sign_job(sid, uid, ag_id, password, method, evidence, progress=None):
        """Runs in a worker thread (a new DB connection per call). ds.sign reports steps 1-3 and activation 4-7."""
        st = ds.sign("agreement", ag_id, uid, password or "", method=method, evidence_ref=evidence, progress=progress)
        act = st.get("activation") or {}
        if st.get("sealed") and not act.get("ok"):
            raise RuntimeError("Signed and sealed, but activation is held: " + str(act.get("error")))
        return {"sealed": bool(st.get("sealed"))}

    @app.callback(
        Output({"type": f"{P}-mmsg", "sid": MATCH}, "children"),
        Input({"type": f"{P}-msign", "sid": MATCH}, "n_clicks"),
        State({"type": f"{P}-mpw", "sid": MATCH}, "value"),
        State({"type": f"{P}-mmethod", "sid": MATCH}, "value"),
        State({"type": f"{P}-mpaper", "sid": MATCH}, "contents"), State({"type": f"{P}-mpaper", "sid": MATCH}, "filename"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_master_sign(n, password, method, paper, paper_name):
        s = _master_ok()
        if not n or not s or not ctx.triggered_id:
            return no_update
        sid = int(ctx.triggered_id["sid"])
        ag = ob.db._execute("SELECT id FROM society_agreements WHERE society_id=%s", (sid,), fetch_one=True)
        if not ag:
            return _alert("That society has no Agreement.", False)
        from app.services import esign_adapter as es
        from app.services import onboarding_jobs as jobs
        try:
            mode = ob.signing_mode(sid)
            if mode == "paper":
                use_method, evidence = "paper", _paper_evidence(sid, s[1], paper, paper_name)
            elif es.is_required(sid):
                use_method, evidence = method or "dsc", None
            else:
                use_method, evidence = "password", None
        except ds.SigningRefused as exc:
            return _alert(str(exc), False)
        if jobs.latest_running(sid):
            return _alert("The platform signature is already being processed.", False)
        job_id = jobs.start("platform_sign", sid, s[1], _platform_sign_job, sid=sid, uid=s[1], ag_id=ag["id"],
                            password=password, method=use_method, evidence=evidence)
        return op.job_view(sid, job_id)

    @app.callback(
        Output({"type": f"{P}-jobbar", "sid": MATCH}, "children"),
        Output({"type": f"{P}-jobpoll", "sid": MATCH}, "disabled"),
        Input({"type": f"{P}-jobpoll", "sid": MATCH}, "n_intervals"),
        State({"type": f"{P}-jobid", "sid": MATCH}, "data"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_job_poll(_n, job_id):
        """Authorised on every poll: a master may watch any society's job; anyone else only their own society's."""
        s = _session()
        if not s or not job_id or not ctx.triggered_id:
            return no_update, no_update
        sid = int(ctx.triggered_id["sid"])
        if s[2] != "master" and s[0] != sid:
            return no_update, True
        from app.services import onboarding_jobs as jobs
        try:
            job = jobs.get(job_id, society_id=sid)
        except Exception:
            log.exception("job poll failed for job %s", job_id)
            return no_update, no_update
        if not job:
            return _alert("That job was not found.", False), True
        if job["status"] == "done":
            ev = ob.db._execute("SELECT id FROM onboarding_events WHERE society_id=%s AND event='agreement_signed' ORDER BY id DESC LIMIT 1",
                                (sid,), fetch_one=True)
            name = (ob.db._execute("SELECT name FROM societies WHERE id=%s", (sid,), fetch_one=True) or {}).get("name") or "The society"
            kids = [dbc.Progress(value=100, label="100%", color="success", style={"height": "20px"}),
                    html.Div("Society is live", style={"fontWeight": "700", "marginTop": "4px"})]
            if ev:
                kids.append(dcc.Store(id={"type": "onb-celebrate", "sid": sid}, data={"key": f"onb-celebrated-{sid}-{ev['id']}", "name": name}))
            return kids, True
        if job["status"] == "failed":
            return [dbc.Alert(str(job.get("error") or "The activation failed."), color="danger", className="py-2"),
                    dbc.Button("Retry activation", id={"type": f"{P}-retry", "sid": sid}, color="warning", size="sm", n_clicks=0)], True
        pct = op.JOB_PERCENT.get(int(job.get("step") or 0), 5)
        return dbc.Progress(value=pct, striped=True, animated=True, label=f"{pct}%", style={"height": "20px"}), False

    app.clientside_callback(
        """function(data){
            if (!data || !data.length || !window.dash_clientside || !window.dash_clientside.onboarding) {
                return window.dash_clientside.no_update;
            }
            window.dash_clientside.onboarding.celebrate(data[0]);
            return window.dash_clientside.no_update;
        }""",
        Output("onb-celebrate-sink", "children"),
        Input({"type": "onb-celebrate", "sid": ALL}, "data"),
        prevent_initial_call=False,
    )

    # ── items 14/15: Stage 5-7 buttons ───────────────────────────────────────
    # ── stage 5: the builder's Declaration of undivided interest ─────────────
    @app.callback(
        Output(f"{P}-decl-download", "data"),
        Input(f"{P}-decl-template", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_decl_template(n):
        s = _session()
        if not n or not s or s[2] != "admin" or not s[0]:
            return no_update
        from app.services import undivided_declaration as ud
        return dcc.send_bytes(ud.template_bytes(s[0]), ud.TEMPLATE_FILENAME)

    @app.callback(
        Output(f"{P}-decl-files", "children"),
        Input(f"{P}-decl-xlsx", "filename"), Input(f"{P}-decl-pdf", "filename"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_decl_files(xlsx_name, pdf_name):
        return f"Workbook: {xlsx_name or 'not chosen'}    Signed Declaration: {pdf_name or 'not chosen'}"

    # ── CA / advocate questionnaire (intake 3) ────────────────────────────────
    @app.callback(
        Output(f"{P}-ca-tpl-dl", "data"),
        Input(f"{P}-ca-tpl", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_ca_template(n):
        s = _session()
        if not n or not s or s[2] != "admin" or not s[0]:
            return no_update
        from app.services import xlsx_templates as xt
        return dcc.send_bytes(xt.build_ca_questionnaire_template(), "CA Questionnaire.xlsx")

    @app.callback(
        Output(f"{P}-ca-files", "children"),
        Input(f"{P}-ca-xlsx", "filename"), Input(f"{P}-ca-pdf", "filename"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_ca_files(xlsx_name, pdf_name):
        return f"Questionnaire: {xlsx_name or 'not chosen'}    Review letter: {pdf_name or 'not chosen'}"

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-ca-file", "n_clicks"),
        State(f"{P}-ca-xlsx", "contents"), State(f"{P}-ca-xlsx", "filename"),
        State(f"{P}-ca-pdf", "contents"), State(f"{P}-ca-pdf", "filename"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_ca_file(n, xlsx_c, xlsx_n, pdf_c, pdf_n):
        s = _session()
        if not n or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        xlsx, pdf = _decode(xlsx_c), _decode(pdf_c)
        if not xlsx or not pdf:
            return no_update, _alert("Choose both the filled questionnaire (.xlsx) and the signed review letter (.pdf).", False), no_update
        from app.services import paired_intake as pi
        try:
            msg = pi.apply_ca_review(sid, uid, xlsx_n or "", xlsx, pdf_n or "", pdf)
        except ob.OnboardingError as exc:
            return no_update, _alert(str(exc), False), no_update
        body, mk = _body(sid, uid, role)
        return body, _alert(msg), mk

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-decl-apply", "n_clicks"),
        State(f"{P}-decl-xlsx", "contents"), State(f"{P}-decl-xlsx", "filename"),
        State(f"{P}-decl-pdf", "contents"), State(f"{P}-decl-pdf", "filename"),
        State("op-token-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_decl_apply(n, xlsx_c, xlsx_n, pdf_c, pdf_n, op_token=None):
        s = _session()
        if not n or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        # Action-level authorization on top of the admin check, as for the bulk enrolment upload (tenant-scoped).
        from app.security.authorization import Cap
        from app.security.service_guard import blocks, check
        if blocks(check(Cap.ENROLLMENT_COMMIT, "enrollment_batch", target_society_id=sid)):
            return no_update, _alert("You don't have permission to do that.", False), no_update
        xlsx, pdf = _decode(xlsx_c), _decode(pdf_c)
        if not xlsx or not pdf:
            return no_update, _alert("Choose both the filled workbook (.xlsx) and the builder's signed Declaration (.pdf).", False), no_update
        from app.services import op_progress
        from app.services import undivided_declaration as ud
        try:
            with op_progress.begin(op_token, "declaration_apply", "Applying the Declaration", steps_total=3, society_id=sid) as trk:
                trk.step(1, "Checking every flat's share and filing the signed PDF")
                msg = ud.apply(sid, uid, xlsx_n or "", xlsx, pdf_n or "", pdf)
                trk.step(2, "Refreshing the page")
        except ob.OnboardingError as exc:
            return no_update, _alert(str(exc), False), no_update
        except Exception:
            log.exception("applying the Declaration failed for society %s", sid)
            return no_update, _alert("The Declaration could not be saved. Nothing was changed; try again.", False), no_update
        body, mk = _body(sid, uid, role)
        return body, _alert(msg), mk

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-enrol-done", "n_clicks"),
        State(f"{P}-enrol-later", "value"), State(f"{P}-enrol-later-reason", "value"),
        State(f"{P}-decl-waive", "value"), State(f"{P}-decl-waive-reason", "value"),
        State("op-token-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_enrol_done(n, later, reason, waive, waive_reason, op_token=None):
        s = _session()
        if not n or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        from app.services import op_progress
        with op_progress.begin(op_token, "enrollment_complete", "Completing enrollment", steps_total=3, society_id=sid) as trk:
            try:
                trk.step(1, "Opening the portals and catching up billing")
                msg = ob.mark_enrollment_complete(sid, uid, reason if later else None, waive_reason if waive else None)
            except ob.OnboardingError as exc:
                trk.fail("Not completed")
                return no_update, _alert(str(exc), False), no_update
            trk.step(2, "Refreshing the page")
        body, mk = _body(sid, uid, role)
        if ob.state_of(sid) != "active":
            # The Declaration is done; the admin must next open Apartment Charges to enter Intake 4.
            body = op.hub_body(role, sid, uid, view="setup:Apartment Charges")
            mk = op.marker(sid)
        return body, _alert(msg), mk

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-phase-next", "n_clicks"), Input(f"{P}-phase-later", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_phase_next(n_next, n_later):
        s = _session()
        if not (n_next or n_later) or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        nxt = {"adoption": "advisers", "advisers": "complete"}.get(ob.society_phase(sid))
        if not nxt:
            return no_update, no_update, no_update
        try:
            msg = ob.advance_phase(sid, uid, nxt)
        except ob.OnboardingError as exc:
            return no_update, _alert(str(exc), False), no_update
        body, mk = _body(sid, uid, role)
        return body, _alert(msg), mk

    @app.callback(
        Output({"type": f"{P}-retry", "sid": MATCH}, "children", allow_duplicate=True),
        Input({"type": f"{P}-retry", "sid": MATCH}, "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_master_retry(n):
        s = _master_ok()
        if not n or not s or not ctx.triggered_id:
            return no_update
        res = ob.try_activate(int(ctx.triggered_id["sid"]), s[1])
        return _alert("The society is active." if res["ok"] else "Still held: " + res["error"], res["ok"])



    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output("onb-view", "data", allow_duplicate=True),
        Input(f"{P}-back-to-setup", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_back_to_setup(n):
        s = _session()
        if not n or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update
        sid, uid, role = s
        if ob.annexes_sealed(sid):
            return no_update, _alert("The annexes are sealed: the wizard is locked. Use “Reissue Agreement” while nothing is signed.", False), no_update
        return op.hub_body(role, sid, uid, view="setup"), "setup"

    def _tds_wizard_names():
        from database.seed import tds_wizard_rows as _rows
        return [(r[0], r[1]) for r in _rows()]

    def _bf_accs(sid):
        return ob.db._execute("SELECT id AS acc_id FROM accounts WHERE society_id=%s AND has_bf=TRUE ORDER BY id", (sid,), fetch_all=True) or []


    # The seating forms (flat / name / email / mobile / resolution) and the grievance officer are only SAVED when "Seat" /
    # "Save grievance officer" is pressed. The print used to read the database alone, so an admin who had typed (or imported
    # from Election Results.xlsx) every entry but not yet seated them got a completely blank sheet. The print now also reads
    # the entries as they are on screen: a seated officer comes from the record, an office not yet seated from its form, and
    # the Status column says which, so the paper never claims more than the system holds.
    # ── Election Results.xlsx: template download + validated prefill of the seating forms ─────────────────────────
    @app.callback(Output(f"{P}-election-tpl-dl", "data"), Input(f"{P}-election-tpl", "n_clicks"), prevent_initial_call=True)
    @require_session
    def onb_election_template(n):
        s = _session()
        if not n or not s or not s[0] or s[2] != "admin":
            return no_update
        from app.services import xlsx_templates as xt
        data = xt.build_election_template()
        return dcc.send_bytes(data, "Election Results.xlsx")

    _EL_FIELDS = ("flat", "name", "size", "email", "phone", "ref")

    @app.callback(
        [Output({"type": f"{P}-f", "office": ALL, "field": f}, "value", allow_duplicate=True) for f in _EL_FIELDS],
        Output(f"{P}-g-name", "value", allow_duplicate=True),
        Output(f"{P}-g-email", "value", allow_duplicate=True),
        Output(f"{P}-g-phone", "value", allow_duplicate=True),
        Output(f"{P}-election-import-status", "children"),
        Input(f"{P}-election-xlsx", "contents"),
        State(f"{P}-election-xlsx", "filename"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_election_import(contents, filename):
        outs = ctx.outputs_list or []
        keep = [[no_update] * len(o) for o in outs[:len(_EL_FIELDS)]]
        s = _session()
        if not contents or not s or not s[0]:
            return (*keep, no_update, no_update, no_update, no_update)
        if s[2] != "admin":
            return (*keep, no_update, no_update, no_update, _alert("Only the society's administrator can import the Election Results.", False))
        from app.services import xlsx_templates as xt
        res = xt.parse_upload(contents, filename or "", "Election Results", ["office"], max_rows=10)
        if res.errors:
            return (*keep, no_update, no_update, no_update, _alert(" ".join(res.errors), False))
        data, errors = ob.validate_election_rows(res.rows)
        if errors:
            return (*keep, no_update, no_update, no_update, _alert("Fix the file and upload it again: " + " ".join(errors), False))
        ob.save_election_rows(s[0], s[1], res.rows)
        seated = ob.seated_officers(s[0])
        filled = []
        per_field = []
        for fname, group in zip(_EL_FIELDS, outs[:len(_EL_FIELDS)]):
            vals = []
            for o in group:
                office = o["id"].get("office")
                # Never overwrite a seated officer's card (its phone input is the only same-named field there).
                if office in ob.CORE_OFFICES and not seated.get(office):
                    v = data[office].get(fname)
                    vals.append(v if v not in (None, "") else no_update)
                else:
                    vals.append(no_update)
            per_field.append(vals)
        filled = [ob.OFFICE_LABEL[o] for o in ob.CORE_OFFICES if not seated.get(o)]
        g = data["grievance_officer"]
        note = (("Workbook checked for: " + ", ".join(filled) + ". ") if filled else "Every office is already seated. ") + \
               "Add each officer's temporary password and signature image under 'Seat all three', then press it. " \
               "Grievance officer fields are filled; press Save to keep them."
        return (*per_field, g["name"], g["email"], g["phone"], _alert(note))

    # ── Upload registration certificate: store as evidence and stamp the society row ──
    @app.callback(
        Output(f"{P}-reg-cert-status", "children", allow_duplicate=True),
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-reg-cert-upload", "contents"),
        State(f"{P}-reg-cert-upload", "filename"),
        State("onb-view", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_reg_cert(contents, filename, view):
        s = _session()
        if not contents or not s or not s[0]:
            return no_update, no_update, no_update
        if s[2] != "admin":
            return _alert("Only the society's administrator can upload the registration certificate.", False), no_update, no_update
        sid, uid, role = s
        raw = _decode(contents)
        if not raw:
            return _alert("Upload the registration certificate (PDF, PNG or JPG).", False), no_update, no_update
        try:
            ob._check_evidence_file(filename or "", raw)
        except ob.OnboardingError as exc:
            return _alert(f"Registration certificate: {exc}", False), no_update, no_update
        try:
            ev = ob.store_evidence_file(sid, "registration_certificate", None, filename or "", raw, uid,
                                        {"kind": "registration_certificate", "source": "committee_hub"})
            ob.db._execute("""UPDATE societies SET registration_certificate_file=%s, registration_certificate_hash=%s
                               WHERE id=%s""",
                           (filename or "registration_certificate.pdf", ev["sha256"], sid))
        except ob.OnboardingError as exc:
            return _alert(f"Registration certificate: {exc}", False), no_update, no_update
        body = op.hub_body(role, sid, uid, view=view or "committee")
        return (_alert(f"Registration certificate recorded: {filename} (SHA-256 {ev['sha256'][:16]}...).", True),
                body, op.marker(sid))

    # ── Upload optional document: store as evidence for Annex E (non-blocking) ──
    _OPT_LABEL = dict(ob.OPTIONAL_DOCS)

    # The per-row status output is ALL, not MATCH: Dash rejects a callback whose MATCH output sits beside plain
    # outputs (onb-body / onb-marker) with "Mismatched `MATCH` wildcards across `Output`s", and that one rejected
    # callback stops the whole front-end callback graph, so the login society dropdown never loaded.
    # ALL outputs may be mixed freely with plain ones; the callback returns one entry per row (no_update for the others).
    @app.callback(
        Output({"type": f"{P}-opt-doc-status", "code": ALL}, "children"),
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input({"type": f"{P}-opt-doc-upload", "code": ALL}, "contents"),
        State({"type": f"{P}-opt-doc-upload", "code": ALL}, "filename"),
        State("onb-view", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_opt_doc(contents_list, filename_list, view):
        trig = ctx.triggered_id
        if not isinstance(trig, dict) or not ctx.outputs_list:
            raise PreventUpdate
        code = trig.get("code")
        row_codes = [o["id"]["code"] for o in ctx.outputs_list[0]]       # layout order of the status divs
        in_codes = [i["id"]["code"] for i in ctx.inputs_list[0]]
        if code not in in_codes:
            raise PreventUpdate
        contents = contents_list[in_codes.index(code)]
        filename = filename_list[in_codes.index(code)]

        def row_msg(msg):
            """Show msg in the triggered row only; leave the other rows alone."""
            return [msg if c == code else no_update for c in row_codes]

        s = _session()
        if not contents or not s or not s[0]:
            raise PreventUpdate
        if s[2] != "admin":
            return (row_msg(_alert("Only the society's administrator can upload optional documents.", False)),
                    no_update, no_update)
        sid, uid, role = s
        label = _OPT_LABEL.get(code, code)
        raw = _decode(contents)
        if not raw:
            return row_msg(_alert(f"Upload the {label} (PDF, PNG or JPG).", False)), no_update, no_update
        try:
            ob._check_evidence_file(filename or "", raw)
        except ob.OnboardingError as exc:
            return row_msg(_alert(f"{label}: {exc}", False)), no_update, no_update
        try:
            ob.store_evidence_file(sid, code, None, filename or "", raw, uid,
                                   {"kind": "optional_document", "source": "committee_hub"})
        except ob.OnboardingError as exc:
            return row_msg(_alert(f"{label}: {exc}", False)), no_update, no_update
        # The hub body is rebuilt, which replaces every status div; the row now shows "On file: <name>" itself
        # (see onboarding_page._opt_doc_row), so the rows are left untouched here.
        body = op.hub_body(role, sid, uid, view=view or "committee")
        return [no_update for _ in row_codes], body, op.marker(sid)

    # ── Evidence register: re-hash stored scans against the SHA-256 recorded at upload (tamper check) ──
    # ALL outputs beside a plain one are valid; MATCH would not be (see onb_opt_doc above).
    @app.callback(
        Output({"type": f"{P}-ev-status", "id": ALL}, "children"),
        Output(f"{P}-ev-summary", "children"),
        Input({"type": f"{P}-ev-verify", "id": ALL}, "n_clicks"),
        Input(f"{P}-ev-verify-all", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_ev_verify(_clicks, _all_clicks):
        from app.services import evidence_service as ev
        trig = ctx.triggered_id
        if trig is None or not (ctx.triggered and ctx.triggered[0].get("value")):
            raise PreventUpdate                                            # a re-rendered card, not a click
        s = _session()
        if not s or not s[0] or s[2] != "admin":
            raise PreventUpdate
        sid, uid, _role = s
        row_ids = [o["id"]["id"] for o in ctx.outputs_list[0]]
        targets = row_ids if trig == f"{P}-ev-verify-all" else ([trig["id"]] if isinstance(trig, dict) else [])
        results = {}
        for eid in targets:
            try:
                results[eid] = ev.verify_row(sid, eid)
            except ev.EvidenceError:
                results[eid] = {"status": "missing"}
        shown = {"ok": ("✓ Verified", "#2e7d32"), "missing": ("✗ File missing", "#b26a00"), "altered": ("✗ ALTERED", "#c62828")}
        statuses = [html.Span(shown[results[i]["status"]][0], style={"color": shown[results[i]["status"]][1], "fontWeight": "600"})
                    if i in results else no_update for i in row_ids]
        failed = [r for r in results.values() if r["status"] != "ok"]
        if failed:
            try:
                ob._audit(sid, uid, "EVIDENCE_INTEGRITY_FAILED", "onboarding_evidence", None,
                          {"via": "verify", "failed": len(failed), "checked": len(results)})
            except Exception:
                log.exception("could not audit the integrity failure")
            summary = dbc.Alert(f"{len(failed)} of {len(results)} checked file(s) failed the integrity check. Re-upload the "
                                "original scan to restore it, and tell the platform operator.", color="danger", className="py-2 mb-0",
                                style={"fontSize": "12.5px"})
        else:
            summary = dbc.Alert(f"{len(results)} file(s) checked: every stored scan matches its recorded SHA-256.",
                                color="success", className="py-2 mb-0", style={"fontSize": "12.5px"})
        return statuses, summary

    # ── Evidence register: manual verification tick (admin confirms the scan matches the source document) ──
    # One click flips the row: "Mark verified" -> verified, "Revoke" -> not verified. Label and colour follow the new state.
    @app.callback(
        Output({"type": f"{P}-ev-manual-status", "id": ALL}, "children"),
        Output({"type": f"{P}-ev-manual", "id": ALL}, "children"),
        Output({"type": f"{P}-ev-manual", "id": ALL}, "color"),
        Input({"type": f"{P}-ev-manual", "id": ALL}, "n_clicks"),
        State({"type": f"{P}-ev-note", "id": ALL}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_ev_manual_verify(_clicks, note_values):
        from app.services import evidence_service as ev
        trig = ctx.triggered_id
        if trig is None or not (ctx.triggered and ctx.triggered[0].get("value")):
            raise PreventUpdate
        s = _session()
        if not s or not s[0] or s[2] != "admin":
            raise PreventUpdate
        sid, uid, _role = s
        row_ids = [o["id"]["id"] for o in ctx.outputs_list[0]]
        notes = dict(zip(row_ids, note_values or []))
        eid = trig["id"] if isinstance(trig, dict) else None
        n = len(row_ids)
        if eid is None:
            raise PreventUpdate
        try:
            cur = next((r for r in ev.list_register(sid) if int(r["id"]) == int(eid)), None)
            if cur is None:
                raise ob.OnboardingError("Evidence not found.")
            ob.verify_evidence(sid, int(eid), uid, not bool(cur.get("manually_verified")), notes.get(eid) or "")
        except ob.OnboardingError as exc:
            err = html.Span("Error: " + str(exc), style={"color": "#b02a37", "fontSize": "11px"})
            return [err if i == eid else no_update for i in row_ids], [no_update] * n, [no_update] * n
        verified = {int(r["id"]): r for r in ev.list_register(sid)}
        status, label, color = [], [], []
        for i in row_ids:
            r = verified.get(int(i)) or {}
            ok = bool(r.get("manually_verified"))
            status.append(html.Span("Verified" if ok else "Not verified",
                                    style={"color": "#2e7d32" if ok else "#b02a37", "fontWeight": "600" if ok else "400", "fontSize": "11px"}))
            label.append("Revoke" if ok else "Mark verified")
            color.append("danger" if ok else "success")
        return status, label, color

    # ── post go-live: Annexures F, G, H (build by the admin; sign by President / Secretary / Treasurer) ──────────
    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input({"type": f"{P}-supp-build", "code": ALL}, "n_clicks"),
        State("op-token-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_supp_build(clicks, op_token=None):
        s = _session()
        trig = ctx.triggered_id
        if not s or not s[0] or s[2] != "admin" or not trig or not any(clicks or []):
            return no_update, no_update, no_update
        sid, uid, role = s
        from app.services import op_progress
        with op_progress.begin(op_token, "supp_annex_build", f"Preparing Annexure {trig['code']}",
                               steps_total=3, society_id=sid) as trk:
            try:
                trk.step(1, f"Collecting the data for Annexure {trig['code']}")
                ob.build_supplementary_annex(sid, trig["code"], uid)
            except ob.OnboardingError as exc:
                trk.fail("Not ready")
                return no_update, _alert(str(exc), False), no_update
            trk.step(2, "Refreshing the page")
            body, mk = _body(sid, uid, role)
        return body, _alert(f"Annexure {trig['code']} is ready for signing."), mk

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Output("celebrate-store", "data", allow_duplicate=True),
        Input({"type": f"{P}-supp-sign", "code": ALL}, "n_clicks"),
        State({"type": f"{P}-supp-pw", "code": ALL}, "value"),
        State({"type": f"{P}-supp-pw", "code": ALL}, "id"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_supp_sign(clicks, pws, pw_ids):
        s = _session()
        trig = ctx.triggered_id
        if not s or not s[0] or not trig or not any(clicks or []):
            return no_update, no_update, no_update, no_update
        sid, uid, role = s
        code = trig["code"]
        password = next((v for v, i in zip(pws or [], pw_ids or []) if i.get("code") == code), "")
        try:
            st = ob.sign_supplementary_annex(sid, code, uid, password or "")
        except ob.OnboardingError as exc:
            return no_update, _alert(str(exc), False), no_update, no_update
        body, mk = _body(sid, uid, role)
        cel = (celebration("sealed", f"Annexure {code} sealed", "All three office-bearers have signed. It is now part of the Agreement.",
                           key=f"eh-annex-sealed-{sid}-{code}-{st.get('content_hash', '')}") if st.get("sealed") else no_update)
        return body, _alert("Signed." + (f" Annexure {code} is sealed." if st.get("sealed") else "")), mk, cel

    print("  ✓ Onboarding callbacks registered")
