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

from app.services import document_signing as ds
from app.services import onboarding_service as ob

P = "onb"
_MUTED = {"fontSize": "12px", "color": "#667"}
_CARD = {"padding": "14px 16px", "margin": "10px 0", "background": "#f6f8fb", "border": "1px solid #e1e7ef", "borderRadius": "10px"}
_ICON = {"done": ("fa-check-circle", "#2e9e5b"), "current": ("fa-dot-circle", "#1d74d8"), "todo": ("fa-circle", "#b8c2cf")}


def _field(label, comp, width="100%"):
    return html.Div([html.Div(label, style={"fontSize": "11.5px", "color": "#556", "marginBottom": "2px"}), comp],
                    style={"marginBottom": "8px", "width": width})


def tracker(society_id: int):
    items = []
    for s in ob.stage_report(society_id):
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
    return json.dumps([st, ann, seated, sigs], sort_keys=True, default=str)


# ── stage 2 ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _office_card(office: str, seated: dict | None):
    label = ob.OFFICE_LABEL[office]
    if seated:
        return html.Div([html.I(className="fas fa-user-check me-2", style={"color": "#2e9e5b"}),
                         html.Strong(f"{label}: {seated['holder_name']}"), html.Span(f"  flat {seated['flat_number']}", style=_MUTED),
                         html.Div(f"Elected under {seated['resolution_ref']}; minutes SHA-256 {str(seated['evidence_hash'])[:16]}...", style=_MUTED)],
                        style=_CARD)

    def fid(f):
        return {"type": f"{P}-f", "office": office, "field": f}
    return html.Div([
        html.Div([html.Strong(f"Seat the {label}"), html.Span("  not yet seated", style=_MUTED)]),
        dbc.Row([
            dbc.Col(_field("Flat number", dbc.Input(id=fid("flat"), size="sm", maxLength=20)), md=3),
            dbc.Col(_field("Full name", dbc.Input(id=fid("name"), size="sm", maxLength=100)), md=5),
            dbc.Col(_field("Flat area (sq ft)", dbc.Input(id=fid("size"), size="sm", type="number", min=0)), md=4),
        ], className="g-2 mt-1"),
        dbc.Row([
            dbc.Col(_field("Email (their login)", dbc.Input(id=fid("email"), size="sm", type="email", maxLength=100)), md=5),
            dbc.Col(_field("Mobile", dbc.Input(id=fid("phone"), size="sm", maxLength=20)), md=3),
            dbc.Col(_field("Temporary password", dbc.Input(id=fid("password"), size="sm", type="password", autoComplete="new-password")), md=4),
        ], className="g-2"),
        dbc.Row([
            dbc.Col(_field("Election resolution reference", dbc.Input(id=fid("ref"), size="sm", maxLength=200, placeholder="e.g. GBM 12-Oct-2026, Res. 3")), md=6),
            dbc.Col(_field("Signed minutes (PDF, PNG or JPG, up to 5 MB)", dcc.Upload(
                id=fid("file"), accept=".pdf,.png,.jpg,.jpeg", multiple=False,
                children=html.Span("Choose the minutes file", style={"fontSize": "12px", "textDecoration": "underline", "cursor": "pointer"}),
                style={"padding": "5px 8px", "border": "1px dashed #b8c2cf", "borderRadius": "6px"})), md=6),
        ], className="g-2"),
        html.Div([dbc.Button(f"Seat {label}", id={"type": f"{P}-seat", "office": office}, color="primary", size="sm", n_clicks=0),
                  html.Span("  Their flat and login are created now; they must change the password at first sign-in.", style=_MUTED)]),
    ], style=_CARD)


def _stage_committee(society_id: int):
    seated = ob.seated_officers(society_id)
    s = ob.db._execute("SELECT grievance_officer_name, grievance_officer_email, grievance_officer_phone, onboarding_state FROM societies WHERE id=%s",
                       (society_id,), fetch_one=True) or {}
    out = [html.H6("Stage 2: seat the founding committee"),
           html.Div("The President, Secretary and Treasurer sign the Agreement, so they must hold office first. Each is seated with the "
                    "resolution that elected them and the signed minutes; the file's SHA-256 is kept as evidence. Use a different flat "
                    "for each person: the Agreement needs four different people to sign.", style=_MUTED)]
    out += [_office_card(o, seated[o]) for o in ob.CORE_OFFICES]
    out.append(html.Div([
        html.Strong("Grievance officer (DPDP)"), html.Div("Named on the login page and in every privacy notice.", style=_MUTED),
        dbc.Row([dbc.Col(_field("Name", dbc.Input(id=f"{P}-g-name", size="sm", value=s.get("grievance_officer_name") or "")), md=4),
                 dbc.Col(_field("Email", dbc.Input(id=f"{P}-g-email", size="sm", value=s.get("grievance_officer_email") or "")), md=5),
                 dbc.Col(_field("Mobile", dbc.Input(id=f"{P}-g-phone", size="sm", value=s.get("grievance_officer_phone") or "")), md=3)], className="g-2"),
        dbc.Button("Save grievance officer", id=f"{P}-g-save", color="secondary", size="sm", outline=True, n_clicks=0)], style=_CARD))
    if s.get("onboarding_state") == "committee seated":
        out.append(dbc.Button([html.I(className="fas fa-arrow-right me-2"), "Continue to the Setup Wizard"], id=f"{P}-open-wizard",
                              color="success", n_clicks=0, className="mt-2"))
    return out


# ── stage 3 → 4 ───────────────────────────────────────────────────────────────────────────────────────────────────
def _controls(code: str, a: dict):
    ctl = a["controls_json"] if isinstance(a["controls_json"], dict) else json.loads(a["controls_json"] or "{}")
    rows = []
    for k, c in ctl.items():
        if c["passed"]:
            icon, color = "fa-check-circle", "#2e9e5b"
        else:
            icon, color = ("fa-times-circle", "#c0392b") if c["blocking"] else ("fa-exclamation-triangle", "#d68910")
        rows.append(html.Li([html.I(className=f"fas {icon} me-2", style={"color": color}), c["reason"]], style={"listStyle": "none", "fontSize": "12.5px", "margin": "2px 0"}))
    titles = {"A": "Annex A: legal regime and bye-laws", "B": "Annex B: review of the setup", "C": "Annex C: opening financial position"}
    badge = dbc.Badge("Sealed", color="success") if a["status"] == "sealed" else (dbc.Badge("Blocked", color="danger") if a["blocking"] else dbc.Badge("Ready to seal", color="info"))
    return html.Div([html.Div([html.Strong(titles[code]), html.Span("  "), badge, html.Span(f"  SHA-256 {a['content_hash'][:16]}...", style=_MUTED)]),
                     html.Ul(rows, style={"padding": "0", "margin": "6px 0 0"})], style=_CARD)


def _stage_annexes(society_id: int):
    drafts = {r["annex_code"]: r for r in ob.db._execute(
        "SELECT * FROM onboarding_annexes WHERE society_id=%s AND status IN ('draft','submitted','sealed') ORDER BY annex_code, "
        "CASE status WHEN 'sealed' THEN 0 ELSE 1 END", (society_id,), fetch_all=True) or []}
    decl = ob.declaration(society_id) or {}
    inp = decl.get("annex_c_inputs") or {}
    arrears = "\n".join(f"{x['flat_number']}, {x['amount']}, {x.get('overdue_days') or ''}".rstrip(", ") for x in inp.get("arrears_by_flat") or [])
    out = [html.H6("Stage 4: check, seal and sign"),
           html.Div("The Setup Wizard saved a draft and posted nothing. These three annexes are what the Agreement declares: the legal basis, "
                    "the reviewed setup and the opening position. Each failing control blocks signing.", style=_MUTED),
           html.Div([
               html.Strong("Opening-position details the wizard does not capture"),
               _field("Arrears by flat (one per line: flat, amount, days overdue)", dbc.Textarea(id=f"{P}-in-arrears", value=arrears, rows=3, style={"fontSize": "12px"})),
               dbc.Checkbox(id=f"{P}-in-bank", label="Bank and cash balances agree to the bank statement and cash count on the as-at date", value=bool(inp.get("bank_agrees")), className="mb-2"),
               dbc.Row([dbc.Col(_field("SHA-256 of last audited statements (optional)", dbc.Input(id=f"{P}-in-audit", size="sm", value=inp.get("audited_hash") or "")), md=6),
                        dbc.Col(_field("CA review reference, or leave blank for 'none obtained'", dbc.Input(id=f"{P}-in-ca", size="sm", value=inp.get("ca_review_ref") or "")), md=6)], className="g-2"),
               dbc.Button("Save and check the annexes", id=f"{P}-prepare", color="primary", size="sm", n_clicks=0)], style=_CARD)]
    for code in ("A", "B", "C"):
        if code in drafts:
            out.append(_controls(code, drafts[code]))
    ready = len(drafts) == 3 and all(v["status"] != "sealed" and not v["blocking"] for v in drafts.values())
    all_sealed = len(drafts) == 3 and all(v["status"] == "sealed" for v in drafts.values())
    if ready:
        out.append(dbc.Button([html.I(className="fas fa-stamp me-2"), "Seal the annexes and issue the Agreement"], id=f"{P}-seal", color="success", n_clicks=0))
    elif all_sealed:
        out.append(html.Div("Annexes sealed. Re-saving the details above would change them and void any signature already given.", style=_MUTED))
    return out


def signing_panel(society_id: int, user_id: int | None):
    ag = ob.db._execute("SELECT id, body_text FROM society_agreements WHERE society_id=%s", (society_id,), fetch_one=True)
    sealed = ob.annex_status(society_id)
    if not ag or not ag["body_text"] or any(sealed.get(c, {}).get("status") != "sealed" for c in "ABC"):
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
        control = html.Div([
            dbc.Input(id=f"{P}-pw", type="password", placeholder="Your login password", autoComplete="current-password", size="sm",
                      style={"maxWidth": "240px", "display": "inline-block", "marginRight": "8px"}),
            dbc.Button(f"Sign as {mine[0].title()}", id=f"{P}-sign", color="success", size="sm", n_clicks=0)])
    return html.Div([
        html.Strong("The Agreement"),
        html.Div("Each signature records who signed, when, and the SHA-256 of this exact text and its annex hashes.", style=_MUTED),
        html.Details([html.Summary("Read the Agreement text", style={"fontSize": "12.5px", "cursor": "pointer"}),
                      html.Pre(ag["body_text"], style={"whiteSpace": "pre-wrap", "fontSize": "11.5px", "maxHeight": "320px", "overflow": "auto",
                                                       "background": "#fff", "border": "1px solid #e1e7ef", "padding": "8px"})]),
        html.Ul(rows, style={"padding": "0", "margin": "8px 0"}), control], style=_CARD)


def _stage_active(society_id: int):
    return [dbc.Alert([html.I(className="fas fa-check-circle me-2"), "The society is active. The Agreement is sealed and the opening position is posted."],
                      color="success", className="py-2"),
            html.H6("What is next"),
            html.Ul([html.Li("Stage 5, Enrollment: enrol owners, vendors, guards and staff from the Enrolled tab. Each person accepts the privacy notice at first sign-in."),
                     html.Li("Stage 6, Adoption: adopt bye-laws and record resolutions under Settings, Society By-laws and Meetings & Resolutions."),
                     html.Li("Stage 7, Advisers: appoint the auditor, CA and advocate once a resolution is recorded.")], style={"fontSize": "13px"})]


def hub_body(role: str, society_id: int, user_id: int | None) -> list:
    st = ob.state_of(society_id) or "registered"
    out = [tracker(society_id)]
    is_admin = role == "admin"
    if st in ("registered", "committee seated"):
        out += _stage_committee(society_id) if is_admin else [html.Div("The administrator is seating the founding committee.", style=_MUTED)]
    elif st == "setup draft":
        if is_admin:
            out += _stage_annexes(society_id)
        out.append(signing_panel(society_id, user_id))
        if not is_admin:
            out.append(html.Div("You sign here once the annexes are sealed. Until the Agreement is sealed the society cannot bill, receive or post.", style=_MUTED))
    elif st == "active":
        out += _stage_active(society_id)
    else:
        out.append(dbc.Alert("This society is suspended. Contact the platform operator.", color="warning"))
    return out


def render_pending(role: str, society_id: int | None, user_id: int | None):
    """What a not-yet-active society sees in place of its dashboard."""
    if not society_id:
        return html.Div("Society not resolved.", style=_MUTED)
    return html.Div([
        html.H4("Society onboarding", style={"fontWeight": "700", "marginTop": "8px"}),
        html.Div(id=f"{P}-toast"),
        dcc.Interval(id=f"{P}-poll", interval=6000, n_intervals=0),
        dcc.Store(id=f"{P}-marker", data=marker(society_id)),
        html.Div(hub_body(role, society_id, user_id), id=f"{P}-body"),
    ], style={"maxWidth": "880px", "margin": "0 auto", "padding": "16px"})


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
            body = html.Div([dbc.Input(id={"type": f"{P}-mpw", "sid": r["id"]}, type="password", placeholder="Your password", size="sm",
                                       autoComplete="current-password", style={"maxWidth": "230px", "display": "inline-block", "marginRight": "8px"}),
                             dbc.Button("Sign for the platform and activate", id={"type": f"{P}-msign", "sid": r["id"]}, color="success", size="sm", n_clicks=0)])
        else:
            body = html.Div("Waiting for the President, Secretary and Treasurer to sign first.", style=_MUTED)
        cards.append(html.Div([head, html.Div(id={"type": f"{P}-mmsg", "sid": r["id"]}), body], style=_CARD))
    return html.Div([html.H5("Onboarding queue"), html.Div("Societies whose Agreement waits for the platform.", style=_MUTED)] + cards, style={"padding": "16px"})
