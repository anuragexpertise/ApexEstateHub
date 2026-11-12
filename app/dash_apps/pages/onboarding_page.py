# app/dash_apps/pages/onboarding_page.py
"""
The Onboarding Hub (Gold-Standard Plan v5). One screen that takes a society from "registered" to "active":

  1 Register  ->  2 Founding committee  ->  3 Setup Wizard  ->  4 Agreement  ->  5 Enrollment  ->  6 Adoption  ->  7 Advisers

It replaces the old "Setup Not Complete" dead end. The admin sees the step they are on, with the form for it; the
President, Secretary and Treasurer (who are ordinary apartment logins) see the same tracker and the signing panel; the
Master sees a queue of societies waiting for the platform's signature (master_queue()).

Identity and society always come from the server session (callbacks re-check); nothing here trusts the browser.
"""
from __future__ import annotations

import json

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.dash_apps.callbacks.onboarding_callbacks import _committee_view
from app.dash_apps.pages.setup_wizard import (
    CATEGORIES,
    render_category_content,
    step_label,
)
from app.services import document_signing as ds
from app.services import onboarding_service as ob
from app.utils import today_ist

P = "onb"

P = "onb"
_MUTED = {"fontSize": "12px", "color": "#667"}
_CARD = {"padding": "14px 16px", "margin": "10px 0", "background": "#f6f8fb", "border": "1px solid #e1e7ef", "borderRadius": "10px"}
_ICON = {"done": ("fa-check-circle", "#2e9e5b"), "current": ("fa-dot-circle", "#1d74d8"), "todo": ("fa-circle", "#b8c2cf")}


def _field(label, comp, width="100%"):
    return html.Div([html.Div(label, style={"fontSize": "11.5px", "color": "#556", "marginBottom": "2px"}), comp],
                    style={"marginBottom": "8px", "width": width})


def tracker(society_id: int):
    items = []
    groups = [(1, 3, "Set up"), (4, 4, "Sign"), (5, 7, "Go-live checklist")]
    gi = 0
    for s in ob.stage_report(society_id):
        if gi < len(groups) and s["n"] == groups[gi][0]:
            items.append(html.Div(groups[gi][2], style={"fontSize": "10px", "fontWeight": "700",
                                                        "color": "#556", "marginTop": "6px", "marginBottom": "2px",
                                                        "textTransform": "uppercase", "letterSpacing": "0.5px",
                                                        "borderBottom": "1px solid #e1e7ef", "paddingBottom": "2px",
                                                        "flexBasis": "100%", "textAlign": "left"}))
            gi += 1
        icon, color = _ICON[s["status"]]
        items.append(html.Div([
            html.I(className=f"fas {icon}", style={"color": color, "fontSize": "20px"}),
            html.Div(f"{s['n']}. {s['label']}", style={"fontSize": "12px", "fontWeight": "700" if s["status"] == "current" else "500",
                                                       "color": "#223" if s["status"] != "todo" else "#8895a5", "marginTop": "4px"}),
        ], title=s["text"], style={"textAlign": "center", "flex": "1 1 90px", "minWidth": "84px", "padding": "6px 2px"}))
    return html.Div(items, style={"display": "flex", "flexWrap": "wrap", "gap": "2px", "borderBottom": "1px solid #e1e7ef", "paddingBottom": "8px"})


def marker(society_id: int) -> str:
    """Changes whenever anything the hub shows changes; the poller re-renders only then."""
    st = ob.state_of(society_id)
    ann = {k: (v["status"], v["blocking"]) for k, v in ob.annex_status(society_id).items()}
    seated = {k: bool(v) for k, v in ob.seated_officers(society_id).items()}
    ag = ob.db._execute("SELECT id FROM society_agreements WHERE society_id=%s", (society_id,), fetch_one=True)
    sigs = 0
    if ag:
        sigs = (ob.db._execute("SELECT COUNT(*) AS n FROM document_signatures WHERE subject_kind='agreement' AND subject_id=%s", (ag["id"],), fetch_one=True) or {}).get("n", 0)
    es = ob.db._execute("SELECT esign_required, (SELECT string_agg(id || status, ',' ORDER BY id) FROM esign_requests WHERE society_id=s.id) AS r "
                        "FROM societies s WHERE id=%s", (society_id,), fetch_one=True) or {}
    return json.dumps([st, ann, seated, sigs, es.get("esign_required"), es.get("r"), ob.society_phase(society_id), ob.signing_mode(society_id)], sort_keys=True, default=str)


# ── stage 2 ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _office_card(office: str, seated: dict | None, society_id: int | None = None):
    label = ob.OFFICE_LABEL[office]
    if not seated:
        return html.Div([
            html.Div([html.Strong(f"Seat the {label}"), html.Span("  not yet seated — use 'Seat all three' below", style=_MUTED)]),
        ], style=_CARD)

    sig = ob.signature_url(society_id, seated.get("signature_image")) if society_id else None
    sig_img = html.Div()
    if sig:
        sig_img = html.Img(src=sig, style={"maxWidth": "120px", "maxHeight": "60px", "marginTop": "6px",
                                           "border": "1px solid #c9d2dc", "borderRadius": "4px"})
    def fid(f):
        return {"type": f"{P}-f", "office": office, "field": f}
    return html.Div([html.I(className="fas fa-user-check me-2", style={"color": "#2e9e5b"}),
                     html.Strong(f"{label}: {seated['holder_name']}"), html.Span(f"  flat {seated['flat_number']}", style=_MUTED),
                     html.Div(f"Elected under {seated['resolution_ref']}; minutes SHA-256 {str(seated['evidence_hash'])[:16]}...", style=_MUTED),
                     html.Div([html.Strong("Signature: ", style={"fontSize": "11.5px", "color": "#556"}), sig_img], style={"marginTop": "6px"}),
                     html.Details([html.Summary("Edit details", style={"fontSize": "12px", "cursor": "pointer", "marginTop": "8px"}),
                                   dbc.Row([
                                       dbc.Col(_field("Mobile", dbc.Input(id=fid("phone"), size="sm", value=seated.get("phone") or "", maxLength=20)), md=4),
                                       dbc.Col(_field("Signature image", dcc.Upload(
                                           id=fid("sig"), accept=".png,.jpg,.jpeg,.webp", multiple=False,
                                           children=html.Span("Replace signature", style={"fontSize": "12px", "textDecoration": "underline", "cursor": "pointer"}),
                                           style={"padding": "5px 8px", "border": "1px dashed #b8c2cf", "borderRadius": "6px"})), md=4),
                                       dbc.Col(html.Div(id=fid("sig-preview"), style={"fontSize": "11.5px", "color": "#667", "marginTop": "6px"}), md=2),
                                       dbc.Col(dbc.Button("Save", id=fid("save"), color="primary", size="sm", n_clicks=0, style={"fontSize": "12px"}), md=1),
                                       dbc.Col(html.Div(id=fid("msg"), style={"fontSize": "12px"}), md=1),
                                   ], className="g-2")], style={"marginTop": "8px"})],
                  style=_CARD)


def _seat_all_panel(seated: dict):
    """Apply Election Results.xlsx: seat every office that is still open in one action. The workbook carries each person's
    flat, name, contact and resolution; the signed minutes (one file for all three), each signature image and each
    temporary password are given here. Always renders all three rows so the callback's ids are always present."""
    def upload(comp_id, text, accept, disabled=False):
        return dcc.Upload(id=comp_id, accept=accept, multiple=False, disabled=disabled,
                          children=html.Span(text, style={"fontSize": "12px", "textDecoration": "underline",
                                                          "cursor": "default" if disabled else "pointer"}),
                          style={"padding": "5px 8px", "border": "1px dashed #b8c2cf", "borderRadius": "6px",
                                 "opacity": 0.5 if disabled else 1})
    rows = []
    for o in ob.CORE_OFFICES:
        held = seated.get(o)
        rows.append(dbc.Row([
            dbc.Col(html.Div([html.Strong(ob.OFFICE_LABEL[o], style={"fontSize": "12.5px"}),
                              html.Div(f"{held['holder_name']} (already seated)" if held else "from the workbook", style=_MUTED)]), md=3),
            dbc.Col(upload(f"{P}-all-sig-{o}", "Signature image (PNG, JPG or WEBP)", ".png,.jpg,.jpeg,.webp", disabled=bool(held)), md=5),
            dbc.Col(dbc.Input(id=f"{P}-all-pw-{o}", size="sm", type="password", autoComplete="new-password",
                              placeholder="Temporary password", disabled=bool(held)), md=4),
        ], className="g-2 mb-1 align-items-center"))
    return dbc.Card(dbc.CardBody([
        html.Strong("Seat all three from Election Results.xlsx", className="d-block mb-1", style={"fontSize": "13px"}),
        html.Small("Choose the filled workbook and the one signed minutes file that covers all three, then each signature image and "
                   "temporary password. Offices already seated are left as they are. Nothing is seated unless every check passes.",
                   className="text-muted d-block mb-2"),
        dbc.Row([
            dbc.Col(_field("Election Results.xlsx", upload(f"{P}-all-xlsx", "Choose the filled workbook (.xlsx)", ".xlsx")), md=6),
            dbc.Col(_field("Signed minutes (PDF, PNG or JPG, up to 5 MB)", upload(f"{P}-all-minutes", "Choose the minutes file", ".pdf,.png,.jpg,.jpeg")), md=6),
        ], className="g-2"),
        *rows,
        html.Div(id=f"{P}-all-chosen", style={"fontSize": "11.5px", "color": "#667", "margin": "4px 0"}),
        dbc.Button([html.I(className="fas fa-users me-2"), "Seat all three"], id=f"{P}-all-go", color="primary", size="sm", n_clicks=0),
        html.Span("  Their flats and logins are created now; they must change the password at first sign-in.", style=_MUTED),
    ], className="py-2"), className="mb-2")


def _opt_doc_row(opt: tuple[str, str], society_id: int):
    """One optional-document upload row: label + upload button + status div (shows the file already on record)."""
    code, label = opt
    try:
        on_file = ob.get_evidence(society_id, code)
    except Exception:                                                      # noqa: BLE001  (a lookup failure must not break the stage)
        on_file = []
    status = ""
    if on_file:
        latest = on_file[0]                                                # newest first
        status = f"✓ On file: {latest['filename']}"
        if len(on_file) > 1:
            status += f" (+{len(on_file) - 1} earlier)"
    return dbc.Row([
        dbc.Col(html.Strong(label, style={"fontSize": "12px"}), md=4),
        dbc.Col(dcc.Upload(id={"type": f"{P}-opt-doc-upload", "code": code},
                           children=html.Span(f"Upload {label}", style={"fontSize": "11.5px", "textDecoration": "underline", "cursor": "pointer"}),
                           accept=".pdf,.png,.jpg,.jpeg", multiple=False,
                           style={"padding": "4px 8px", "border": "1px dashed #b8c2cf", "borderRadius": "6px", "fontSize": "11.5px"}), md=5),
        dbc.Col(html.Div(status, id={"type": f"{P}-opt-doc-status", "code": code},
                         style={"fontSize": "11px", "color": "#2e7d32" if on_file else "#8895a5"}), md=3),
    ], className="g-1 mb-1 align-items-center")


def _stage_committee(society_id: int):
    seated = ob.seated_officers(society_id)
    s = ob.db._execute("SELECT grievance_officer_name, grievance_officer_email, grievance_officer_phone, onboarding_state FROM societies WHERE id=%s",
                       (society_id,), fetch_one=True) or {}
    out = [html.H6("Stage 2: seat the founding committee"),
           dbc.Card(dbc.CardBody([
               html.Strong("Minutes evidence (mandatory)", className="d-block mb-1", style={"fontSize":"13px"}),
               html.Small("The signed minutes of the election are the real third-party document. Upload the scan here; "
                          "the server computes its SHA-256 and Annex B records it. No separate print/sign/scan loop is needed "
                          "for the Election Results data itself.", className="text-muted d-block mb-2"),
               dbc.Row([
                   dbc.Col(dcc.Upload(id=f"{P}-election-scan", children=dbc.Button([html.I(className="fas fa-file-upload me-2"), "Upload signed election minutes scan"], color="secondary", size="sm", outline=True, n_clicks=0), multiple=False, accept=".pdf,.png,.jpg,.jpeg"), md="auto"),
                   dbc.Col(dcc.Upload(id=f"{P}-reg-cert-upload", children=dbc.Button([html.I(className="fas fa-file-certificate me-2"), "Upload registration certificate"], color="secondary", size="sm", outline=True, n_clicks=0), multiple=False, accept=".pdf,.png,.jpg,.jpeg"), md="auto"),
                   dbc.Col(dbc.Button([html.I(className="fas fa-file-excel me-2"), "Election Results.xlsx template"], id=f"{P}-election-tpl", color="secondary", size="sm", outline=True, n_clicks=0), md="auto"),
                   dbc.Col(dcc.Upload(id=f"{P}-election-xlsx", children=dbc.Button([html.I(className="fas fa-table me-2"), "Fill forms from Election Results.xlsx"], color="secondary", size="sm", outline=True, n_clicks=0), multiple=False, accept=".xlsx"), md="auto"),
               ], className="g-2"), dcc.Download(id=f"{P}-election-tpl-dl"),
               html.Div(id=f"{P}-election-import-status", style={"fontSize":"12.5px","marginTop":"6px"}),
               html.Div(id=f"{P}-election-status", style={"fontSize":"12.5px","marginTop":"6px"}),
               html.Div(id=f"{P}-reg-cert-status", style={"fontSize":"12.5px","marginTop":"6px"}),
            ], className="py-2"), className="mb-2"),
           dbc.Card(dbc.CardBody([
               html.Strong("Optional documents (non-blocking)", className="d-block mb-1", style={"fontSize":"13px"}),
               html.Small("Listed in Annex E but do not block sealing. Upload any you have on file.", className="text-muted d-block mb-2"),
               *[_opt_doc_row(o, society_id) for o in ob.OPTIONAL_DOCS],
           ], className="py-2"), className="mb-2"),
            html.Div("The President, Secretary and Treasurer sign the Agreement, so they must hold office first. Each is seated with the "
                    "resolution that elected them and the signed minutes; the file's SHA-256 is kept as evidence. Use a different flat "
                    "for each person: the Agreement needs four different people to sign.", style=_MUTED)]
    if s.get("onboarding_state") in ("registered", "committee seated") and not all(seated[o] for o in ob.CORE_OFFICES):
        out.append(_seat_all_panel(seated))
    out += [_office_card(o, seated[o], society_id) for o in ob.CORE_OFFICES]
    out.append(html.Div([
        html.Strong("Grievance officer (DPDP)"), html.Div("Named on the login page and in every privacy notice.", style=_MUTED),
        dbc.Row([dbc.Col(_field("Name", dbc.Input(id=f"{P}-g-name", size="sm", value=s.get("grievance_officer_name") or "")), md=4),
                 dbc.Col(_field("Email", dbc.Input(id=f"{P}-g-email", size="sm", value=s.get("grievance_officer_email") or "")), md=5),
                 dbc.Col(_field("Mobile", dbc.Input(id=f"{P}-g-phone", size="sm", value=s.get("grievance_officer_phone") or "")), md=3)], className="g-2"),
        dbc.Button("Save grievance officer", id=f"{P}-g-save", color="secondary", size="sm", outline=True, n_clicks=0)], style=_CARD))
    state = s.get("onboarding_state")
    named = bool((s.get("grievance_officer_name") or "").strip())
    if state == "committee seated":
        # The founding committee is complete, but Stage 2 is not finished until the grievance officer is named:
        # the wizard must never swallow this card (it used to vanish the moment the Treasurer was seated).
        if named:
            out.append(html.Div([
                html.Div("All three office-bearers are seated and the grievance officer is named. Next: society setup. "
                         "Nothing posts until the Agreement is signed and the society is activated.", style=_MUTED),
                dbc.Button([html.I(className="fas fa-arrow-right me-2"), "Continue to society setup"],
                           id=f"{P}-continue-setup", color="primary", size="sm", n_clicks=0)], style={"marginTop": "8px"}))
        else:
            out.append(dbc.Alert("All three office-bearers are seated. Name the grievance officer above to continue to society setup.",
                                 color="info", className="py-2 mt-2", style={"fontSize": "12.5px"}))
    elif state == "setup draft":
        out.append(dbc.Button([html.I(className="fas fa-arrow-left me-2"), "Back to society setup"],
                              id=f"{P}-back-to-setup", color="secondary", size="sm", outline=True, n_clicks=0, style={"marginTop": "8px"}))
    return out


# ── stage 3 → 4 ───────────────────────────────────────────────────────────────────────────────────────────────────
def _fix_label(target: str) -> str:
    return "Fix in " + ("Founding committee" if target == "committee" else step_label(target))


def _controls(code: str, a: dict, society_id: int, sealed_ok: bool = False):
    ctl = a["controls_json"] if isinstance(a["controls_json"], dict) else json.loads(a["controls_json"] or "{}")
    rows = []
    for k, c in ctl.items():
        if c["passed"]:
            icon, color = "fa-check-circle", "#2e9e5b"
        else:
            icon, color = ("fa-times-circle", "#c0392b") if c["blocking"] else ("fa-exclamation-triangle", "#d68910")
        line = [html.I(className=f"fas {icon} me-2", style={"color": color}), c["reason"]]
        target = ob.CONTROL_FIX.get((code, k))
        if not c["passed"] and target and a["status"] != "sealed":
            line.append(dbc.Button(_fix_label(target), id={"type": f"{P}-fix", "annex": code, "ctl": k, "key": target},
                                   color="link", size="sm", n_clicks=0, style={"fontSize": "12px", "padding": "0 0 0 8px"}))
        rows.append(html.Li(line, style={"listStyle": "none", "fontSize": "12.5px", "margin": "2px 0"}))
    titles = {"A": "Annex A: legal regime and bye-laws", "B": "Annex B: review of the setup",
              "C": "Annex C: opening financial position", "D": "Annex D: data-protection and custody schedule",
              "E": "Annex E: source-documents index"}
    badge = dbc.Badge("Sealed", color="success") if a["status"] == "sealed" else (dbc.Badge("Blocked", color="danger") if a["blocking"] else dbc.Badge("Ready to seal", color="info"))
    ch = a.get("content_hash") or ""
    body = [html.Div([html.Strong(titles.get(code, f"Annex {code}")), html.Span("  "), badge, html.Span(f"  SHA-256 {ch[:16]}...", style=_MUTED)]),
            html.Ul(rows, style={"padding": "0", "margin": "6px 0 0"})]
    if code == "B":
        body.append(_annex_b_signatures(a, society_id))
    return html.Div(body, style=_CARD)


def _annex_b_signatures(a: dict, society_id: int):
    """Thumbnails of the office-bearers' signature images exactly as recorded in Annex B (read from the annex, not the live record)."""
    content = a.get("content") or {}
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            content = {}
    items = []
    for office in ob.CORE_OFFICES:
        o = (content.get("office_bearers") or {}).get(office)
        if not o:
            continue
        path = ob.signature_url(society_id, o.get("signature_image"))
        thumb = (html.Img(src=path, alt=f"Signature of {o.get('name')}",
                          style={"maxWidth": "120px", "maxHeight": "60px", "border": "1px solid #c9d2dc", "borderRadius": "4px", "background": "#fff"})
                 if path else html.Span("no signature image", style={"fontSize": "11.5px", "color": "#c0392b"}))
        items.append(html.Div([thumb, html.Div(f"{ob.OFFICE_LABEL[office]}: {o.get('name')}", style={"fontSize": "11.5px", "marginTop": "2px"}),
                               html.Div(f"SHA-256 {str(o.get('signature_sha256') or '')[:12]}", style=_MUTED)],
                              style={"marginRight": "16px", "marginTop": "6px"}))
    if not items:
        return html.Div()
    return html.Div([html.Strong("Signature images on record", style={"fontSize": "11.5px", "color": "#556"}),
                     html.Div(items, style={"display": "flex", "flexWrap": "wrap"})], style={"marginTop": "8px"})


def step_from_view(view: str | None) -> int | None:
    """'setup:<rail key>' deep-links the wizard to that step; anything else means 'no preference'."""
    if view and view.startswith("setup:") and view[6:] in CATEGORIES:
        return CATEGORIES.index(view[6:])
    return None


def _stage_annexes(society_id: int):
    drafts = {r["annex_code"]: r for r in ob.db._execute(
        "SELECT * FROM onboarding_annexes WHERE society_id=%s AND status IN ('draft','submitted','sealed') ORDER BY annex_code, "
        "CASE status WHEN 'sealed' THEN 0 ELSE 1 END", (society_id,), fetch_all=True) or []}
    codes = ob.ANNEX_CODES
    out = [html.H6("Stage 4: check, seal and sign"),
           html.Div("The Setup Wizard saved a draft and posted nothing. The four annexes below are generated from that draft and are what "
                    "the Agreement declares: the legal basis, the reviewed setup, the opening position and the data-protection schedule. "
                    "Each failing control blocks sealing and links to the step that fixes it.", style=_MUTED)]
    all_sealed = len(drafts) == len(codes) and all(v["status"] == "sealed" for v in drafts.values())
    if not all_sealed:
        out.append(dbc.Button([html.I(className="fas fa-sync me-2"), "Check annexes"], id=f"{P}-prepare", color="primary", size="sm", n_clicks=0,
                              style={"marginBottom": "10px"}))
    if not drafts:
        out.append(html.Div("Press Check annexes to generate Annexes A to D from your wizard draft.", style=_MUTED))
        return out
    for code in codes:
        if code in drafts:
            out.append(_controls(code, drafts[code], society_id))
    ready = len(drafts) == len(codes) and all(v["status"] != "sealed" and not v["blocking"] for v in drafts.values())
    if ready:
        out.append(html.Div([
            html.Strong("Seal the annexes and issue the Agreement"),
            html.Div("Sealing fixes these four annexes by their SHA-256 inside the Agreement text. Changing anything afterwards would void any "
                     "signature already given. Type I AGREE and confirm it is you.", style=_MUTED),
            dbc.Row([dbc.Col(dbc.Input(id=f"{P}-agree", size="sm", placeholder="Type I AGREE", autoComplete="off"), md=4),
                     dbc.Col(dbc.Input(id=f"{P}-seal-pw", size="sm", type="password", placeholder="Your login password", autoComplete="current-password"), md=4),
                     dbc.Col(dbc.Button([html.I(className="fas fa-stamp me-2"), "Seal annexes and issue the Agreement"], id=f"{P}-seal",
                                        color="success", size="sm", n_clicks=0), md=4)], className="g-2 mt-1"),
        ], style=_CARD))
    elif all_sealed:
        out.append(html.Div("Annexes sealed and the Agreement issued. The office-bearers sign below.", style=_MUTED))
    return out


# ── stage 3: society setup, rendered inline inside the Hub (non-modal) ────────────────────────────
def start_step(society_id: int) -> int:
    """Index into CATEGORIES where the wizard opens: step 0 for a fresh draft, otherwise the first step that is
    neither done nor skipped (the frontier). Used by BOTH the rendered DOM and the onb-setup-step store so
    they can never disagree (F3)."""
    from app.dash_apps.pages.wizard_registry import status_of as _status_of
    from app.services import onboarding_service as ob
    try:
        statuses = ob.step_statuses(society_id) or {}
    except Exception:                                                      # noqa: BLE001
        return 0
    keyed = [c for c in CATEGORIES if c != "Instructions"]
    if all(_status_of(statuses, c) == "todo" for c in keyed):
        return 0
    for i, cat in enumerate(CATEGORIES):
        if _status_of(statuses, cat) not in ("done", "skipped"):
            return i
    return len(CATEGORIES) - 1


def setup_stage(society_id: int, current_step: int | None = None) -> list:
    """Render the Setup Wizard categories as inline navigable stages inside the Onboarding Hub.

    Layout: left step-rail inside the page, main content area to the right (item 1).
    Step statuses come from the server draft (step_statuses), not browser state (item 2).
    Nothing is posted until the Agreement is signed and the society is activated."""
    from app.services import onboarding_service as ob
    statuses = ob.step_statuses(society_id) or {}
    if current_step is None:
        current_step = start_step(society_id)
    heading = "Stage 3: society setup"
    out = [html.H6(heading),
           html.Div("Declare the legal regime, rates, charges, accounts and opening balances. The wizard draft is saved as you move "
                    "between steps; nothing is posted until the Agreement is signed and the society is activated.", style=_MUTED)]

    # ── left rail (item 2) ──────────────────────────────────────────────────────
    rail_items = []
    last = len(CATEGORIES) - 1
    for i, cat in enumerate(CATEGORIES):
        from app.dash_apps.pages.wizard_registry import status_of as _status_of
        st = _status_of(statuses, cat)
        is_skipped = st == "skipped"
        base = {"type": "onb-rail", "key": cat}
        classes = ["onb-rail-item", st]
        if i == current_step:
            classes.append("current")
        if is_skipped:
            classes.append("skipped")
        dot = {"todo": "○", "current": "●", "done": "✔", "error": "✖", "needs_review": "◐", "skipped": "—"}.get(st, "○")
        dot_color = {"todo": "#b8c2cf", "current": "#1d74d8", "done": "#17976e", "error": "#c0392b",
                     "needs_review": "#e59620", "skipped": "#9aa3ad"}.get(st, "#b8c2cf")
        rail_items.append(html.Div([
            html.Span(dot, className="onb-rail-dot", style={"color": dot_color}),
            html.Span(step_label(cat), className="onb-rail-label", title=cat),
        ], id=base, n_clicks=0, className=" ".join(classes),
           style={"display": "flex", "alignItems": "center", "gap": "8px", "padding": "8px 10px",
                  "borderRadius": "8px", "border": "1px solid transparent", "fontSize": "12px",
                  "cursor": "default" if is_skipped else "pointer"}))
    rail = html.Div([
        html.Div("Setup steps", className="onb-rail-head", style={"fontWeight": "700", "fontSize": "13px", "color": "#223"}),
        html.Div(rail_items, className="onb-rail-body", style={"display": "flex", "flexDirection": "column", "gap": "4px", "padding": "6px 0"}),
        html.Div("Green = done · blue = current · amber = needs review · struck = skipped",
                 className="onb-rail-foot"),
    ], className="onb-rail")

    # ── main content ────────────────────────────────────────────────────────────
    containers = []
    for i, cat in enumerate(CATEGORIES):
        if cat == "Review":
            # Review is filled from the saved draft by a callback (§4.12), never from live State.
            # The wrapper carries the same pattern id as every other step, so the {"type": "onb-step", "key": ALL}
            # outputs of wizard_nav always resolve to len(CATEGORIES) components (was 11 vs 12 -> InvalidCallbackReturnValue).
            review_body = None
            if i == current_step:                      # opened straight on Review: the nav callback will not fire
                from app.dash_apps.pages.setup_wizard import render_review
                review_body = render_review(ob.load_draft(society_id), society_id)
            print_link = html.Div(html.A([html.I(className="fas fa-print me-2"), "Print / open review in a new window"],
                                         href="/print_wizard/review", target="_blank", rel="noopener",
                                         className="btn btn-outline-secondary btn-sm"),
                                  style={"textAlign": "right", "marginBottom": "8px"})
            containers.append(html.Div([print_link, html.Div(review_body, id="onb-review-container")], id={"type": "onb-step", "key": cat},
                                       style={"display": "block" if i == current_step else "none", "paddingTop": "6px"}))
        else:
            containers.append(html.Div(render_category_content(cat, society_id), id={"type": "onb-step", "key": cat},
                                       style={"display": "block" if i == current_step else "none", "paddingTop": "6px"}))
    main = html.Div([
        html.Div(containers, id="onb-step-containers"),
        html.Div([
            html.Div(id="onb-setup-error", className="onb-error"),
            dbc.Button("Previous", id="onb-btn-prev", color="secondary", size="sm", n_clicks=0,
                       disabled=(current_step == 0), style={"fontSize": "12px"}),
            dbc.Button("Next", id="onb-btn-next", color="primary", size="sm", n_clicks=0,
                       disabled=(current_step == last), style={"fontSize": "12px"}),
            dbc.Button("Save & continue to Agreement", id="onb-btn-finalize", color="success", size="sm", n_clicks=0,
                       style={"fontSize": "12px", "display": "none" if current_step != last else "inline-block"}),
            dbc.Button([html.I(className="fas fa-book me-2"), "Acts & Rules"], id="onb-btn-rules", color="secondary", outline=True,
                       size="sm", n_clicks=0, style={"fontSize": "12px", "marginLeft": "auto"}),
        ], style={"marginTop": "10px", "display": "flex", "gap": "6px", "flexWrap": "wrap", "alignItems": "center"}),
    ], className="onb-main")

    setup = html.Div([rail, main], className="onb-setup")

    # ── confirm modal (item 3): only the admin's login password ─────────────────
    modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Confirm it is you")),
        dbc.ModalBody([
            html.P("Enter your login password to save the draft and move to the Agreement stage.", className="small text-muted mb-3"),
            dbc.Input(id="onb-finalize-password", type="password", placeholder="Your login password",
                      autoComplete="current-password", className="mb-3"),
            html.Div(id="onb-finalize-error", style={"color": "#c0392b", "fontSize": "12px", "marginBottom": "8px"}),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="onb-finalize-cancel", color="secondary", size="sm", n_clicks=0),
            dbc.Button("Save & continue", id="onb-finalize-confirm", color="success", size="sm", n_clicks=0),
        ]),
    ], id="onb-finalize-modal", is_open=False, centered=True, backdrop="static")

    # ── Acts & Rules (item 1.4): a side panel, so it never takes layout width from the step ──────────────────
    rules = dbc.Offcanvas(
        html.Div(id="onb-rules-body", style={"fontSize": "12.5px", "color": "#3a4a5c"}),
        id="onb-rules-canvas", title="Acts & Rules", placement="end", is_open=False, scrollable=True,
        style={"width": "min(440px, 92vw)"})

    out.append(setup)
    out.append(modal)
    out.append(rules)
    return out


def esign_control(society_id: int, kind: str, subject_id: int, user_id: int, office: str, sign_id, pw_id):
    """The signer's own control. eSign off: password and Sign. eSign on: choose the method, start the request, finish it with the
    vendor (or upload the paper counterpart's hash), then confirm with the password. The method and paper fields are always in
    the layout (hidden when eSign is off) so the callback can read them either way."""
    from app.services import esign_adapter as es
    on = es.is_required(society_id)
    req = es.latest_for(society_id, kind, subject_id, user_id) if on else None
    hide = {} if on else {"display": "none"}
    status_line = ""
    if on:
        status_line = ("No eSign request yet. Pick a method and start one." if not req else
                       f"eSign request {req['status']} ({req['method'].replace('_', ' ')}). " +
                       ("It is complete: confirm with your password to record the signature." if req["status"] == "completed" else
                        "Finish it with the vendor; this page updates by itself."))
    mode = ob.signing_mode(society_id)
    if mode == "paper":
        method_opts = [{"label": "Signed paper counterpart", "value": "paper"}]
        method_val = "paper"
    else:
        method_opts = [{"label": "Aadhaar eSign", "value": "aadhaar_eSign"}, {"label": "Digital Signature Certificate", "value": "dsc"}]
        method_val = (req or {}).get("method") if (req or {}).get("method") in ("aadhaar_eSign", "dsc") else "aadhaar_eSign"
    paper_style = {"display": "inline-block", "marginRight": "8px"} if mode == "paper" else {"display": "none"}
    start_style = {} if mode == "esign" else {"display": "none"}
    box = [html.Div([
        dbc.Select(id=f"{P}-method", size="sm", value=method_val, style={"maxWidth": "230px", "display": "inline-block", "marginRight": "8px"},
                   options=method_opts),
        html.Div([dcc.Upload(id=f"{P}-paper", children=dbc.Button([html.I(className="fas fa-upload me-2"), "Upload signed scan"],
                                                                  color="secondary", outline=True, size="sm", n_clicks=0),
                             multiple=False, accept=".pdf,.png,.jpg,.jpeg"),
                  html.Small("PDF, PNG or JPG up to 5 MB. The server computes the SHA-256; nobody types a hash.", style=_MUTED)],
                 style=paper_style),
        dbc.Button("Start eSign", id=f"{P}-esign-start", color="primary", outline=True, size="sm", n_clicks=0, className="me-2", style=start_style),
        dbc.Button("Complete with demo vendor", id=f"{P}-esign-demo", color="secondary", outline=True, size="sm", n_clicks=0,
                   style={} if (es.SANDBOX() and mode == "esign") else {"display": "none"}),
        html.Div(status_line if mode == "esign" else
                 ("Print, sign, scan and upload the Agreement counterpart; then confirm with your password." if mode == "paper" else ""),
                 style=_MUTED)], style={"marginBottom": "6px", **hide})]
    return html.Div(box + [
        dbc.Input(id=pw_id, type="password", placeholder="Your login password", autoComplete="current-password", size="sm",
                  style={"maxWidth": "240px", "display": "inline-block", "marginRight": "8px"}),
        dbc.Button(f"Sign as {office.replace('_', ' ').title()}", id=sign_id, color="success", size="sm", n_clicks=0)])


def signing_panel(society_id: int, user_id: int | None, role: str | None = None):
    ag = ob.db._execute("SELECT id, body_text FROM society_agreements WHERE society_id=%s", (society_id,), fetch_one=True)
    sealed = ob.annex_status(society_id)
    if not ag or not ag["body_text"] or any(sealed.get(c, {}).get("status") != "sealed" for c in ob.ANNEX_CODES):
        return html.Div("The Agreement is issued for signing once the three annexes are sealed.", style=_MUTED)
    st = ds.status("agreement", ag["id"])
    have = {x["office_code"] for x in st["signed"]}
    rows = []
    for off, label in (("president", "President"), ("secretary", "Secretary"), ("treasurer", "Treasurer"), ("platform", "Platform (signs last)")):
        done = off in have
        rows.append(html.Li([html.I(className=f"fas {'fa-check-circle' if done else 'fa-hourglass-half'} me-2", style={"color": "#2e9e5b" if done else "#b8c2cf"}), label],
                            style={"listStyle": "none", "fontSize": "13px", "margin": "3px 0"}))
    mine = []
    if user_id:
        mine = [r[0] for r in ds._signer_roles(ob.db, society_id, "agreement", ag["id"], user_id) if r[0] in st["policy"]["eligible"] and r[0] not in have]
    control = html.Div()
    if st["sealed"]:
        control = dbc.Alert("The Agreement is sealed.", color="success", className="py-2 mb-0")
    elif mine:
        control = esign_control(society_id, "agreement", ag["id"], user_id, mine[0], f"{P}-sign", f"{P}-pw")
    # V5.6b: per-society eSign toggle (admin only). When on, the Agreement must be
    # signed through the eSign adapter instead of a password confirmation.
    esign_row = html.Div()
    if role == "admin":
        mode = ob.signing_mode(society_id)
        copy = {"password": "A password confirmation records who confirmed and when; it is not by itself a legal electronic signature.",
                "esign": "Each signer uses Aadhaar eSign or a Digital Signature Certificate through a licensed provider. The Society and the Operator never see or store the Aadhaar number.",
                "paper": "Each signer prints, signs and scans the Agreement, uploads the scan, and confirms with their login password."}
        esign_row = html.Div([
            html.Strong("Signing method", style={"fontSize": "12px", "color": "#556", "marginRight": "8px"}),
            dbc.RadioItems(id=f"{P}-signmode", value=mode, inline=True, className="btn-group", inputClassName="btn-check",
                           labelClassName="btn btn-outline-primary btn-sm", labelCheckedClassName="active",
                           options=[{"label": "Password", "value": "password"}, {"label": "eSign", "value": "esign"},
                                    {"label": "Paper", "value": "paper"}]),
            html.Div(copy[mode] + " Cannot be changed once signing starts.", style={"fontSize": "11.5px", "color": "#667", "flexBasis": "100%"})],
            style={"marginTop": "8px", "display": "flex", "alignItems": "center", "gap": "8px", "flexWrap": "wrap"})
    return html.Div([
        html.Strong("The Agreement"),
        html.Div("Each signature records who signed, when, and the SHA-256 of this exact text and its annex hashes.", style=_MUTED),
        html.Details([html.Summary("Read the Agreement text", style={"fontSize": "12.5px", "cursor": "pointer"}),
                      html.Pre(ag["body_text"], style={"whiteSpace": "pre-wrap", "fontSize": "11.5px", "maxHeight": "320px", "overflow": "auto",
                                                       "background": "#fff", "border": "1px solid #e1e7ef", "padding": "8px"})]),
        html.Ul(rows, style={"padding": "0", "margin": "8px 0"}),
        html.Div([dbc.Button([html.I(className="fas fa-print me-2"), "Print the Agreement with all its annexes"], id=f"{P}-print",
                             color="secondary", outline=True, size="sm", n_clicks=0),
                  html.Small(" For a paper copy each signer signs by hand and scans back (Paper method). Opens a print-ready page.", style=_MUTED),
                  dcc.Download(id=f"{P}-print-dl")], style={"margin": "6px 0"}),
        control, esign_row], style=_CARD)


# ── stage 7: advisers (V5.9) ────────────────────────────────────────────────
def _adviser_badge(active: bool) -> dbc.Badge:
    return dbc.Badge("Active" if active else "Revoked", color="success" if active else "danger", style={"fontSize": "11px"})


def advisers_section(society_id: int, role: str | None, user_id: int | None) -> list:
    """Adviser appointments (Auditor / CA / Advocate). Admin appoints; the three
    office-bearers sign the appointment; advisers hold read-only logins."""
    rows = ob.list_advisers(society_id)
    cards = []
    for a in rows:
        signed = {x["office_code"] for x in ds.status("adviser_appointment", int(a["id"])).get("signed", [])}
        mine = [r[0] for r in ds._signer_roles(ob.db, society_id, "adviser_appointment", int(a["id"]), user_id or 0)
                if r[0] in ("president", "secretary", "treasurer") and r[0] not in signed] if user_id else []
        ctrl = html.Div()
        if mine:
            ctrl = html.Div([
                dbc.Input(id={"type": f"{P}-adv-pw", "id": int(a["id"])}, type="password",
                          placeholder="Your login password", autoComplete="current-password", size="sm",
                          style={"maxWidth": "200px", "display": "inline-block", "marginRight": "6px"}),
                dbc.Button(f"Sign as {mine[0].title()}", id={"type": f"{P}-adv-sign", "id": int(a["id"])},
                           color="success", size="sm", n_clicks=0)])
        elif a["active"]:
            ctrl = html.Span("signed by " + (", ".join(sorted(signed)) or "none yet (awaiting President, Secretary and Treasurer)"),
                             style=_MUTED)
        cards.append(html.Div([
            html.Strong(f"{a['kind'].title()}: {a['name']}"),
            html.Div(f"firm={a['firm'] or '-'}  membership={a['membership_number'] or '-'}  "
                     f"term {a['term_start']:%d %b %Y} to {a['term_end']:%d %b %Y}  "
                     f"{_adviser_badge(bool(a['active']))}", style=_MUTED),
            html.Div(f"scope: {a['scope'] or '-'}   resolution #{a['resolution_id']}   "
                     f"login: {'yes' if a['login_user_id'] else 'no'}", style=_MUTED),
            html.Div(ctrl, style={"marginTop": "6px"}),
            html.Div(id={"type": f"{P}-advmsg", "id": int(a["id"])}),
        ], style=_CARD))
    out = [html.H6("Adviser appointments"), html.Div(cards or [html.Div("No advisers appointed yet.", style=_MUTED)])]
    if role == "admin":
        def fid(f):
            return {"type": f"{P}-adv", "field": f}
        out.append(html.Div([
            html.Strong("Appoint a new adviser"),
            html.Div("An appointment needs a PASSED General Body resolution (a legacy import does not count). Record the meeting and "
                     "its attendance and vote registers under Settings → Society governance → Meetings & Resolutions first; every "
                     "flat needs its undivided-interest percentage for the votes to be weighted. Enter that resolution's number below.",
                     style=_MUTED),
            dbc.Row([
                dbc.Col(_field("Role", dbc.Select(id=fid("kind"), size="sm", options=[{"label": a, "value": a} for a in ("auditor", "ca", "advocate")])), md=2),
                dbc.Col(_field("Name", dbc.Input(id=fid("name"), size="sm", maxLength=100)), md=3),
                dbc.Col(_field("Firm", dbc.Input(id=fid("firm"), size="sm", maxLength=100)), md=3),
                dbc.Col(_field("Membership no.", dbc.Input(id=fid("mno"), size="sm", maxLength=50)), md=2),
            ], className="g-2"),
            dbc.Row([
                dbc.Col(_field("Scope", dbc.Input(id=fid("scope"), size="sm", maxLength=300)), md=4),
                dbc.Col(_field("Term start", dbc.Input(id=fid("ts"), size="sm", type="date")), md=2),
                dbc.Col(_field("Term end", dbc.Input(id=fid("te"), size="sm", type="date")), md=2),
                dbc.Col(_field("Passed resolution #", dbc.Input(id=fid("res"), size="sm", type="number")), md=2),
            ], className="g-2"),
            dbc.Row([
                dbc.Col(_field("Adviser email (their login)", dbc.Input(id=fid("email"), size="sm", type="email", maxLength=100)), md=4),
                dbc.Col(_field("Temporary password", dbc.Input(id=fid("pw"), size="sm", type="password", autoComplete="new-password")), md=3),
                dbc.Col(dbc.Button("Appoint", id=fid("appoint"), color="success", size="sm", n_clicks=0), md=2),
            ], className="g-2"),
            html.Div(id=fid("msg")), html.Div(id=fid("marker"), style={"display": "none"}),
        ], style=_CARD))
    return out


def _celebrate_store(society_id: int):
    """Carries the agreement_signed event id; a clientside callback fires the confetti once per browser per event."""
    ev = ob.db._execute("SELECT id FROM onboarding_events WHERE society_id=%s AND event='agreement_signed' ORDER BY id DESC LIMIT 1",
                        (society_id,), fetch_one=True)
    if not ev or ob.society_phase(society_id) != "enrollment":
        return html.Div()
    name = (ob.db._execute("SELECT name FROM societies WHERE id=%s", (society_id,), fetch_one=True) or {}).get("name") or "Your society"
    return dcc.Store(id={"type": "onb-celebrate", "sid": society_id}, data={"key": f"onb-celebrated-{society_id}-{ev['id']}", "name": name})


def _enrollment_counts(society_id: int) -> dict:
    out = {}
    for label, role in (("Apartments", "apartment"), ("Vendors", "vendor"), ("Security", "security")):
        out[label] = (ob.db._execute("SELECT COUNT(*) AS n FROM users WHERE society_id=%s AND role=%s", (society_id, role), fetch_one=True) or {}).get("n", 0)
    return out


def declaration_panel(society_id: int, role: str | None):
    """Stage 5, step 1: the builder's Declaration of undivided interest. General Body votes are weighted by these shares,
    so Enrollment cannot be completed until they are complete, total 100% and the signed Declaration is on file."""
    from app.services import undivided_declaration as ud
    st = ud.status(society_id)
    ev = st["evidence"]
    ok = st["balanced"] and bool(ev)
    is_admin = role == "admin"
    badges = [dbc.Badge(f"Flats with a share: {st['flats'] - st['missing']} of {st['flats']}", color="light", text_color="dark", className="me-2"),
              dbc.Badge(f"Total: {st['total_pct'].normalize():f}%", color="success" if st["balanced"] else "danger", className="me-2"),
              dbc.Badge("Declaration PDF on file" if ev else "Declaration PDF not on file", color="success" if ev else "warning",
                        text_color=None if ev else "dark")]
    hold = []
    if ud.billing_waits(society_id):
        hold = [dbc.Alert([html.I(className="fas fa-pause-circle me-2"),
                           ("Billing is on hold. This society bills by undivided interest, so no bills are raised until the "
                           "Declaration is on file or Enrollment is completed with a recorded reason that the building has none. "
                           "Bills then catch up from the billing start month.")], color="warning", className="py-2 mb-2",
                          style={"fontSize": "12.5px"})]
    kids = hold + [html.Div([html.Strong("Builder's Declaration of undivided interest "),
                      dbc.Badge("done" if ok else "needed", color="success" if ok else "warning", text_color=None if ok else "dark")]),
            html.Div("Votes at a General Body meeting are weighted by each flat's undivided interest, so every flat needs its "
                     "share from the Declaration the builder filed, and the shares must total 100%. Download the workbook, fill in "
                     "Flat No, Area and Undivided-Interest for every flat (also flats not yet enrolled), then upload it with the "
                     "builder's signed Declaration as a PDF. Nothing is saved unless every row is valid.", style=_MUTED),
            html.Div(badges, className="my-2")]
    if ev:
        m = ev.get("meta") or {}
        kids.append(html.Div(f"{ev['filename']}  SHA-256 {str(ev['sha256'])[:16]}…  uploaded {ev['uploaded_at']:%d %b %Y}  "
                             f"({m.get('flats', '?')} flats, {m.get('created', 0)} created, {m.get('updated', 0)} updated)", style=_MUTED))
    if st["unenrolled"]:
        kids.append(html.Div(f"{st['unenrolled']} flat(s) have no owner login yet. On the Enrolled tab, Bulk Enroll → Apartments "
                             "gives a template pre-filled with them; upload it with email, password and the owners' details.", style=_MUTED))
    if is_admin:
        up_style = {"padding": "5px 8px", "border": "1px dashed #b8c2cf", "borderRadius": "6px", "display": "inline-block", "marginRight": "8px"}
        kids += [
            dbc.Row([
                dbc.Col(dbc.Button("Download the workbook", id=f"{P}-decl-template", color="secondary", outline=True, size="sm", n_clicks=0), md=3),
                dbc.Col(dcc.Upload(id=f"{P}-decl-xlsx", accept=".xlsx", multiple=False, style=up_style,
                                   children=html.Span("Choose the filled workbook (.xlsx)", style={"fontSize": "12px", "textDecoration": "underline", "cursor": "pointer"})), md=4),
                dbc.Col(dcc.Upload(id=f"{P}-decl-pdf", accept=".pdf", multiple=False, style=up_style,
                                   children=html.Span("Choose the signed Declaration (.pdf)", style={"fontSize": "12px", "textDecoration": "underline", "cursor": "pointer"})), md=3),
                dbc.Col(dbc.Button("Apply Declaration", id=f"{P}-decl-apply", color="primary", size="sm", n_clicks=0), md=2),
            ], className="g-2 mt-1 align-items-center"),
            html.Div(id=f"{P}-decl-files", style=_MUTED),
            dcc.Download(id=f"{P}-decl-download"),
            html.Div([dbc.Checkbox(id=f"{P}-decl-waive", label="This building has no builder's Declaration", value=False, className="mb-1"),
                      dbc.Input(id=f"{P}-decl-waive-reason", placeholder=f"Reason ({ud.WAIVER_MIN_CHARS} characters or more); shares then stay as derived from area",
                                size="sm", style={"maxWidth": "520px"})],
                     style={"marginTop": "8px", "display": "none" if ev else "block"}),
        ]
    return html.Div(kids, style=_CARD)


def _stage_enrollment(society_id: int, role: str | None):
    counts = _enrollment_counts(society_id)
    ob.relink_pending_for_existing_flats(society_id)
    pend = ob.db._execute("SELECT flat_number, amount FROM opening_receivables_pending WHERE society_id=%s AND status='pending_link' ORDER BY flat_number",
                          (society_id,), fetch_all=True) or []
    is_admin = role == "admin"
    kids = [html.H6("Stage 5: Enrollment"),
            html.Div("Enrol owners, vendors and guards from the Enrolled tab (bulk enrolment is there too). Their portals stay closed until you mark "
                     "enrollment complete. Each person accepts the privacy notice at first sign-in.", style=_MUTED),
            html.Div([dbc.Badge(f"{k}: {v}", color="light", text_color="dark", className="me-2") for k, v in counts.items()], className="my-2"),
            declaration_panel(society_id, role)]
    if pend:
        total = sum((r["amount"] for r in pend), 0)
        kids.append(dbc.Alert([html.Strong(f"Opening receivables awaiting enrolment: {len(pend)} flat(s), ₹{total}. "),
                               ", ".join(str(r["flat_number"]) for r in pend[:30]) + (" …" if len(pend) > 30 else "")],
                              color="warning", className="py-2", style={"fontSize": "12.5px"}))
    if is_admin:
        kids.append(dcc.Link(dbc.Button("Open the Enrolled tab", color="primary", size="sm", className="mb-2"), href="/dashboard/enrolled"))
        kids += [dbc.Checkbox(id=f"{P}-enrol-later", label="I will enrol the rest later", value=False, className="mb-1"),
                 dbc.Input(id=f"{P}-enrol-later-reason", placeholder="Reason (10 characters or more)", size="sm",
                           style={"maxWidth": "420px", "marginBottom": "8px"}),
                 dbc.Button("Mark enrollment complete", id=f"{P}-enrol-done", color="success", size="sm", n_clicks=0)]
    return html.Div(kids, style=_CARD)


# ── post go-live: supplementary annexures F, G, H (signed by President, Secretary, Treasurer only) ─────────
_SUPP_BADGE = {"sealed": ("Sealed", "success"), "draft": ("Draft: awaiting signatures", "warning"), "not built": ("Pending", "secondary")}


def supplementary_section(society_id: int, role: str | None, user_id: int | None):
    """Build, review and sign Annexures F, G and H. They attach to the signed Agreement as a hash chain (F -> G -> H) and need the
    three office-bearers only: the Operator never signs them (clause 7A of the Agreement). Sealing is non-blocking, so each row
    simply shows as pending until it is done."""
    rows = ob.supplementary_checklist(society_id, user_id)
    is_admin = role == "admin"
    items = []
    for r in rows:
        label, colour = _SUPP_BADGE.get(r["status"], (r["status"], "secondary"))
        have = set(r["signed"])
        who = " ".join(f"{'✓' if o in have else '○'} {o.title()}" for o in ("president", "secretary", "treasurer"))
        body = [html.Div([html.Strong(r["title"] + " "), dbc.Badge(label, color=colour, className="ms-1"),
                          dbc.Badge("not due yet", color="light", text_color="dark", className="ms-1") if not r["due"] else ""])]
        if r["status"] in ("draft", "sealed"):
            body.append(html.Div(who + (f"   ·   SHA-256 {r['content_hash'][:16]}…" if r.get("content_hash") else ""), style=_MUTED))
            content = ob.supplementary_annex_content(society_id, r["code"])
            body.append(html.Details([html.Summary("Read what is being signed", style={"fontSize": "12.5px", "cursor": "pointer"}),
                                      html.Pre(json.dumps(content, indent=2, default=str, ensure_ascii=False),
                                               style={"whiteSpace": "pre-wrap", "fontSize": "11.5px", "maxHeight": "260px", "overflow": "auto",
                                                      "background": "#fff", "border": "1px solid #e1e7ef", "padding": "8px"})]))
        if r["blocked_by"] and r["status"] == "not built":
            body.append(html.Div(f"Waiting for Annexure {r['blocked_by']} to be signed and sealed first.", style=_MUTED))
        controls = []
        if is_admin and r["status"] != "sealed" and not r["blocked_by"] and r["due"]:
            controls.append(dbc.Button("Refresh draft" if r["status"] == "draft" else "Prepare for signing",
                                       id={"type": f"{P}-supp-build", "code": r["code"]}, color="primary", outline=True, size="sm",
                                       n_clicks=0, className="me-2"))
        if r["status"] == "draft" and r["mine"] and r["due"]:
            controls += [dbc.Input(id={"type": f"{P}-supp-pw", "code": r["code"]}, type="password", placeholder="Your login password",
                                   autoComplete="current-password", size="sm", style={"maxWidth": "240px", "display": "inline-block", "marginRight": "8px"}),
                         dbc.Button(f"Sign as {r['mine'][0].title()}", id={"type": f"{P}-supp-sign", "code": r["code"]}, color="success", size="sm", n_clicks=0)]
        if controls:
            body.append(html.Div(controls, style={"marginTop": "6px"}))
        items.append(html.Div(body, style={"padding": "8px 0", "borderBottom": "1px solid #e1e7ef"}))
    return html.Div([html.H6("Supplementary annexures F, G and H"),
                     html.Div("Added to the Agreement after go-live. Signed by the President, Secretary and Treasurer with their own passwords; "
                              "the Operator is informed and does not sign. Changing the data after signing needs a new annexure; a sealed one is never edited. "
                              "No names, phones or emails appear in them.", style=_MUTED), *items], style=_CARD)


def _stage_active(society_id: int, role: str | None = None, user_id: int | None = None):
    phase = ob.society_phase(society_id) or "complete"
    is_admin = role == "admin"
    head = [dbc.Alert([html.I(className="fas fa-check-circle me-2"),
                       "Stages 1 to 4 are complete. The Agreement is sealed and the opening position is posted."],
                      color="success", className="py-2"), _celebrate_store(society_id)]
    if phase == "enrollment":
        return head + [_stage_enrollment(society_id, role)]
    out = list(head)
    if phase == "adoption":
        from app.dash_apps.pages.adoption_panel import render_adoption_panel
        out += [html.H6("Stage 6: Adoption"), render_adoption_panel(society_id)]
        if is_admin:
            out += [dbc.Button("Mark adoption done", id=f"{P}-phase-next", color="success", size="sm", n_clicks=0, className="me-2"),
                    dbc.Button("Do later", id=f"{P}-phase-later", color="secondary", outline=True, size="sm", n_clicks=0)]
        out += [html.Hr(), supplementary_section(society_id, role, user_id), html.Hr(), legacy_resolutions_section(society_id, role)]
    elif phase == "advisers":
        out += [html.H6("Stage 7: Adviser access"), advisers_section(society_id, role, user_id)]
        if is_admin:
            out += [dbc.Button("Finish onboarding", id=f"{P}-phase-next", color="success", size="sm", n_clicks=0, className="me-2"),
                    dbc.Button("Do later", id=f"{P}-phase-later", color="secondary", outline=True, size="sm", n_clicks=0)]
        out += [html.Hr(), supplementary_section(society_id, role, user_id)]
    else:
        out += [html.Div("Onboarding is complete.", style=_MUTED), html.Hr(), supplementary_section(society_id, role, user_id),
                html.Hr(), advisers_section(society_id, role, user_id), html.Hr(), legacy_resolutions_section(society_id, role)]
    return out


# ── stage: legacy resolutions (V5.8) ────────────────────────────────────────
def legacy_resolutions_section(society_id: int, role: str | None) -> list:
    rows = ob.list_legacy_resolutions(society_id)
    cards = [html.Div([
        html.Strong(f"{r['resolution_type'] or 'Resolution'} (#{r['id']})"),
        html.Div([f"{r['meeting_type']} meeting on {r['held_on']:%d %b %Y}. Old minutes say: {r['legacy_outcome'] or 'unknown'}. ",
                  dbc.Badge("evidence only", color="secondary")], style=_MUTED),
        html.Div((r['body'] or r['text'] or "")[:200] + ("…" if (r['body'] or r['text'] or "") and len(r['body'] or r['text'] or "") > 200 else ""),
                 style={"fontSize": "12px", "color": "#445", "marginTop": "4px"}),
        html.Div(f"minutes: {r['minutes_file'] or '-'}  hash: {r['minutes_hash'] or '-'}", style=_MUTED),
    ], style=_CARD) for r in rows]
    out = [html.H6("Legacy resolutions imported (V5.8 — evidence only, never a majority check)"),
           html.Div(cards or [html.Div("None imported yet.", style=_MUTED)])]
    if role == "admin":
        def fid(f):
            return {"type": f"{P}-leg", "field": f}
        out.append(html.Div([
            html.Strong("Import a legacy resolution"),
            dbc.Row([
                dbc.Col(_field("Date of the old meeting", dbc.Input(id=fid("held"), size="sm", type="date", max=str(today_ist()))), md=3),
                dbc.Col(_field("Meeting", dbc.Select(id=fid("mtype"), size="sm", value="GBM", options=[
                    {"label": "General Body", "value": "GBM"}, {"label": "Extraordinary General", "value": "EGM"},
                    {"label": "Managing Committee", "value": "MC"}])), md=3),
                dbc.Col(_field("Kind of decision", dbc.Select(id=fid("dtype"), size="sm",
                                                              options=[{"label": d["label"], "value": d["id"]} for d in ob.decision_type_options()])), md=3),
                dbc.Col(_field("Old minutes say", dbc.Select(id=fid("outcome"), size="sm", value="unknown", options=[
                    {"label": "Passed", "value": "passed"}, {"label": "Rejected", "value": "rejected"}, {"label": "Not clear", "value": "unknown"}])), md=3),
            ], className="g-2"),
            dbc.Row([
                dbc.Col(_field("Signed minutes: file name", dbc.Input(id=fid("mfile"), size="sm", maxLength=255)), md=5),
                dbc.Col(_field("Signed minutes: SHA-256 (64 characters)", dbc.Input(id=fid("mhash"), size="sm", maxLength=64)), md=7),
            ], className="g-2"),
            dbc.Row([
                dbc.Col(_field("Resolution body", dbc.Textarea(id=fid("body"), size="sm", rows=3)), md=8),
                dbc.Col(dbc.Button("Import", id=fid("import"), color="success", size="sm", n_clicks=0), md=2),
            ], className="g-2"),
            html.Div(id=fid("msg")), html.Div(id=fid("marker"), style={"display": "none"}),
        ], style=_CARD))
    return out


def grievance_named(society_id: int) -> bool:
    r = ob.db._execute("SELECT grievance_officer_name FROM societies WHERE id=%s", (society_id,), fetch_one=True) or {}
    return bool((r.get("grievance_officer_name") or "").strip())


def evidence_register(society_id: int):
    """Admin-only list of every stored scan: View / Download (served by app/routes/evidence_routes.py, hash-checked
    on every read) and a Verify button that re-hashes the stored file against the SHA-256 recorded at upload."""
    from app.services import evidence_service as ev
    try:
        rows = ev.list_register(society_id)
    except Exception:                                                      # noqa: BLE001  (never break the hub over this card)
        return html.Div()
    if not rows:
        return html.Div()
    link = {"fontSize": "11.5px", "marginRight": "10px"}
    body = []
    for r in rows:
        eid = r["id"]
        sha = str(r["sha256"]).lower()
        when = r["uploaded_at"].strftime("%d %b %Y %H:%M") if r.get("uploaded_at") else ""
        body.append(html.Tr([
            html.Td([html.Div(ev.purpose_label(r["purpose"]), style={"fontWeight": "600"}),
                     html.Div(r["filename"], style={"color": "#667"})]),
            html.Td([html.Div(when), html.Div(f"{(r.get('size_bytes') or 0) / 1024:.0f} KB", style={"color": "#667"})]),
            html.Td(html.Code(sha[:16] + "…", title=sha, style={"fontSize": "11px"})),
            html.Td([html.A("View", href=f"/evidence/{eid}", target="_blank", style=link),
                     html.A("Download", href=f"/evidence/{eid}?download=1", style=link),
                     html.A("As PDF", href=f"/evidence/{eid}?as=pdf", target="_blank", style=link)]),
            html.Td([dbc.Button("Verify", id={"type": f"{P}-ev-verify", "id": eid}, size="sm", outline=True,
                                color="secondary", n_clicks=0, style={"padding": "0 8px", "fontSize": "11.5px"}),
                     html.Span(id={"type": f"{P}-ev-status", "id": eid}, style={"fontSize": "11.5px", "marginLeft": "8px"})]),
        ], style={"fontSize": "12px", "verticalAlign": "top"}))
    return dbc.Card(dbc.CardBody([
        html.Div([html.Strong("Evidence register", style={"fontSize": "13px"}),
                  html.Span(f"  {len(rows)} stored scan(s)", style=_MUTED)]),
        html.Small("Every file is re-hashed (SHA-256) and compared with the fingerprint recorded at upload before it is shown. "
                   "A missing or altered file is refused.", className="text-muted d-block mb-2"),
        html.Div(dbc.Table([html.Thead(html.Tr([html.Th(h) for h in ("Document", "Uploaded", "SHA-256", "Open", "Integrity")])),
                            html.Tbody(body)], size="sm", borderless=True, className="mb-2"),
                 style={"overflowX": "auto"}),
        dbc.Button("Verify all", id=f"{P}-ev-verify-all", size="sm", color="secondary", outline=True, n_clicks=0, className="me-2"),
        html.A(dbc.Button("Download register (PDF)", size="sm", color="secondary", outline=True), href="/evidence/register.pdf",
               target="_blank"),
        html.Div(id=f"{P}-ev-summary", style={"marginTop": "8px"}),
    ], className="py-2"), className="mb-2 mt-3")


def hub_body(role: str, society_id: int, user_id: int | None, view: str | None = None) -> list:
    deep_step = step_from_view(view)
    if deep_step is not None:
        view = "setup"
    st = ob.state_of(society_id) or "registered"
    out = [html.Div(id="onb-tracker", children=tracker(society_id))]
    is_admin = role == "admin"
    if st == "registered":
        out += _stage_committee(society_id) if is_admin else [html.Div("The administrator is seating the founding committee.", style=_MUTED)]
    elif st == "committee seated":
        if is_admin:
            if view == "committee" or view is None or (view != "setup" and not grievance_named(society_id)):
                out += _stage_committee(society_id)
            else:
                out += setup_stage(society_id, current_step=deep_step)
        else:
            out.append(html.Div("The founding committee is seated; the administrator is completing society setup.", style=_MUTED))
    elif st == "setup draft":
        if view == "committee" and is_admin:
            out += _stage_committee(society_id)
        elif view == "setup" and is_admin:
            out.append(html.Div("Back to society setup to fix the blocked control.", style=_MUTED))
            out += setup_stage(society_id, current_step=deep_step)
        else:
            if is_admin:
                out += _stage_annexes(society_id)
            out.append(signing_panel(society_id, user_id, role))
        if not is_admin:
            out.append(html.Div("You sign here once the annexes are sealed. Until the Agreement is sealed the society cannot bill, receive or post.", style=_MUTED))
    elif st == "active":
        out += _stage_active(society_id, role, user_id)
    else:
        out.append(dbc.Alert("This society is suspended. Contact the platform operator.", color="warning"))
    if is_admin:
        out.append(evidence_register(society_id))
    return out


def _initial_step(society_id: int) -> int:
    try:
        return start_step(society_id) if ob.state_of(society_id) in ("committee seated", "setup draft") else 0
    except Exception:                                                      # noqa: BLE001
        return 0


POLL_MS = 20000                                    # was 6000: this is a human workflow, not a live feed


def poll_disabled(role: str | None, society_id: int | None) -> bool:
    """True while the admin is alone on the committee/setup screens. Nobody else can change the state there, and every
    admin action already refreshes the marker itself, so polling only burns ~8 DB queries per tick for nothing."""
    try:
        return role == "admin" and ob.state_of(society_id) in ("registered", "committee seated")
    except Exception:                                                      # noqa: BLE001
        return False


def render_pending(role: str, society_id: int | None, user_id: int | None):
    """What a not-yet-active society sees in place of its dashboard."""
    if not society_id:
        return html.Div("Society not resolved.", style=_MUTED)
    return html.Div([
        html.H4("Society onboarding", style={"fontWeight": "700", "marginTop": "8px"}),
        html.Div(id=f"{P}-toast"),
        dcc.Interval(id=f"{P}-poll", interval=POLL_MS, n_intervals=0, disabled=poll_disabled(role, society_id)),
        dcc.Store(id=f"{P}-marker", data=marker(society_id)),
        dcc.Store(id="onb-setup-step", data=_initial_step(society_id)),
        dcc.Store(id="onb-wizard-step", storage_type="session", data=_initial_step(society_id)),
        dcc.Store(id="onb-view", data=_committee_view(society_id) or "current"),
        html.Div(id="onb-celebrate-sink", style={"display": "none"}),
        html.Div(hub_body(role, society_id, user_id, view=_committee_view(society_id)), id=f"{P}-body"),
    ], className="portal-page onb-root")


# ── item 14: progress view for the platform signature job ───────────────────────────────────────────────────────
JOB_PERCENT = {0: 0, 1: 10, 2: 25, 3: 45, 4: 65, 5: 80, 6: 90, 7: 97}


def job_view(sid: int, job_id: str):
    """Store + Interval + bar. The Interval polls onboarding_jobs by id; a page refresh rebuilds this for a running job."""
    return html.Div([
        dcc.Store(id={"type": f"{P}-jobid", "sid": sid}, data=job_id),
        dcc.Interval(id={"type": f"{P}-jobpoll", "sid": sid}, interval=1500, n_intervals=0),
        html.Div(dbc.Progress(value=5, striped=True, animated=True, label="Starting", style={"height": "20px"}),
                 id={"type": f"{P}-jobbar", "sid": sid}),
    ])


# ── Master queue ──────────────────────────────────────────────────────────────────────────────────────────────────
def master_queue():
    rows = ob.awaiting_platform()
    if not rows:
        return html.Div([html.H5("Onboarding queue"), html.Div("No society is waiting for the platform's signature.", style=_MUTED)], style={"padding": "16px"})
    cards = []
    for r in rows:
        signed = set(r["signed"] or [])
        core = all(o in signed for o in ("president", "secretary", "treasurer"))
        head = html.Div([html.Strong(r["name"]), html.Span(f"  state: {r['onboarding_state']}", style=_MUTED),
                         html.Div("Signed: " + (", ".join(sorted(signed)) or "nobody yet"), style=_MUTED)])
        if r["sealed"]:
            body = html.Div([dbc.Alert("The Agreement is sealed but activation was held. Retry after the cause is fixed.", color="warning", className="py-2 mb-2"),
                             dbc.Button("Retry activation", id={"type": f"{P}-retry", "sid": r["id"]}, color="warning", size="sm", n_clicks=0)])
        elif core:
            from app.services import esign_adapter as es
            esign_on = es.is_required(r["id"])
            mmode = ob.signing_mode(r["id"])
            mopts = ([{"label": "Signed paper counterpart", "value": "paper"}] if mmode == "paper" else
                     [{"label": "Digital Signature Certificate", "value": "dsc"}, {"label": "Aadhaar eSign", "value": "aadhaar_eSign"}])
            esign_bits = [html.Div([
                dbc.Select(id={"type": f"{P}-mmethod", "sid": r["id"]}, size="sm", value=mopts[0]["value"], style={"maxWidth": "230px", "display": "inline-block", "marginRight": "8px"},
                           options=mopts),
                dcc.Upload(id={"type": f"{P}-mpaper", "sid": r["id"]}, multiple=False, accept=".pdf,.png,.jpg,.jpeg",
                           children=dbc.Button("Upload signed scan", color="secondary", outline=True, size="sm", n_clicks=0),
                           style={"display": "inline-block", "marginRight": "8px"} if mmode == "paper" else {"display": "none"}),
                dbc.Button("Start eSign", id={"type": f"{P}-mstart", "sid": r["id"]}, color="primary", outline=True, size="sm", n_clicks=0, className="me-2",
                           style={} if mmode == "esign" else {"display": "none"}),
                dbc.Button("Complete with demo vendor", id={"type": f"{P}-mdemo", "sid": r["id"]}, color="secondary", outline=True, size="sm", n_clicks=0,
                           style={} if (es.SANDBOX() and mmode == "esign") else {"display": "none"})],
                style={"marginBottom": "6px", **({} if esign_on else {"display": "none"})})]
            body = html.Div(esign_bits + [dbc.Input(id={"type": f"{P}-mpw", "sid": r["id"]}, type="password", placeholder="Your password", size="sm",
                                       autoComplete="current-password", style={"maxWidth": "230px", "display": "inline-block", "marginRight": "8px"}),
                             dbc.Button("Sign for the platform and activate", id={"type": f"{P}-msign", "sid": r["id"]}, color="success", size="sm", n_clicks=0)])
        else:
            body = html.Div("Waiting for the President, Secretary and Treasurer to sign first.", style=_MUTED)
        from app.services import onboarding_jobs as _jobs
        _running = _jobs.latest_running(r["id"])
        cards.append(html.Div([head, html.Div(job_view(r["id"], str(_running["id"])) if _running else None,
                                              id={"type": f"{P}-mmsg", "sid": r["id"]}), body], style=_CARD))
    return html.Div([html.H5("Onboarding queue"), html.Div("Societies whose Agreement waits for the platform.", style=_MUTED),
                     html.Div(id="onb-celebrate-sink", style={"display": "none"})] + cards, style={"padding": "16px"})
