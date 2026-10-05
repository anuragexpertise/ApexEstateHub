# app/dash_apps/pages/governance_settings.py
"""
Settings -> governance tabs for the Admin and Owner portals.

    RWA Compliance (UP) | Rules | Society By-laws | Meetings & Resolutions

Everything here is scoped to the signed-in user's own society, resolved from the SERVER-side session
(never the browser's auth-store). Owners get a read-only view. Admins additionally get the forms that the
service layer (app.services.regime_rules_admin._require_writer) lets a society admin submit for their own
society: cash-limit mode, provisional bye-law choice, record meeting, record resolution.

Master-only and therefore never rendered here: Edit a catalog entry and Change a rule (a rule value is
regime-wide). Bye-law adoption, meetings and resolutions are edited by the society's ADMIN only (master has no
such tabs). A provisional bye-law choice is activated automatically when a matching passed resolution is
recorded, so there is no separate "link" step.

Component ids are prefixed `gov-` so Master's `mrl-` callbacks (platform-gated) never see them.
"""
from __future__ import annotations

from dash import dcc, html
import dash_bootstrap_components as dbc

from app.dash_apps.pages import master_rules_page as mrp
from app.security.audit_context import get_current_society_id
from app.services import regime_rules_admin as rra

P = "gov"


def _note(text: str):
    return html.Div(text, style={"fontSize": "12px", "color": "#666", "padding": "10px 12px", "marginTop": "16px",
                                 "background": "#f6f8fb", "border": "1px solid #e1e7ef", "borderRadius": "8px"})


def _no_society():
    return html.Div("No society is linked to your account.", className="text-muted p-3")


def rules_body(society_id) -> list:
    return mrp.render_rules_sections(society_id)


def bye_body(society_id) -> list:
    return mrp.render_bye_laws_sections(society_id)


def mtg_body(society_id, can_execute: bool = False) -> list:
    # Only the society's admin gets Execute buttons; owners see the pending list read-only.
    return (mrp.render_meetings_sections(society_id)
            + mrp.render_enactment_section(society_id, P, can_execute=can_execute))


def bye_choice_ui(society_id, clause_id, layer):
    """(options, value) for the guided bye-law form. Only choices the rules allow are enabled."""
    if not clause_id:
        return [{"label": "Select a clause first", "value": "", "disabled": True}], None
    info = rra.clause_rules(society_id, clause_id)
    layer = int(layer or 1)
    if layer != 1:
        return [{"label": "Adopt with variation  (a society policy / board decision is always a variation of an adopted clause)",
                 "value": "adopted_with_variation"}], "adopted_with_variation"
    opts = [
        {"label": "Adopt as-is  (the clause applies exactly as notified)", "value": "adopted_as_is"},
        {"label": "Adopt with variation  (you write the wording)", "value": "adopted_with_variation",
         "disabled": info["fixed"]},
        {"label": ("Not adopted  — not allowed: the Act/Rules enforce this clause" if info["locked"]
                   else "Not adopted  (non-statutory clauses only)"),
         "value": "not_adopted", "disabled": info["locked"]},
    ]
    if info["fixed"]:
        opts[1]["label"] = "Adopt with variation  — not allowed: this clause says the Act prevails"
    return opts, "adopted_as_is"


def bye_choice_panel(clause_id, layer, status):
    """(info children, show_variation_box) for the current selection."""
    if not clause_id or not status:
        return None, False
    title = rra.clause_title(clause_id)
    src = rra.model_bye_laws_source()
    link = (html.A("Read the notified Model Bye-Laws", href=src["url"], target="_blank", rel="noopener noreferrer")
            if src["url"] else html.Span("Refer to the notified Model Bye-Laws"))
    ref = html.Div([link, html.Span(f" — {src['reference']}", className="text-muted")], style={"fontSize": "11px"})
    head = html.Div([html.Strong(f"{clause_id} — {title}", style={"fontSize": "12px"})])
    if status == "adopted_as_is":
        body = html.Div("The society adopts this clause exactly as notified. Nothing to type.", style={"fontSize": "12px"})
    elif status == "adopted_with_variation":
        body = html.Div("Write your wording below. It must be a tightening; it cannot loosen the Model Bye-Law."
                        if int(layer or 1) != 1 else
                        "Write the wording the society adopts in place of the model clause (below).", style={"fontSize": "12px"})
    else:
        body = html.Div("The society does not adopt this clause. Needs a simple-majority GBM resolution.",
                        style={"fontSize": "12px"})
    box = html.Div([head, body, ref], style={"padding": "10px 12px", "background": "#f6f8fb",
                                              "border": "1px solid #e1e7ef", "borderRadius": "8px"})
    return box, status == "adopted_with_variation"


def render_governance_tabs(role: str, sid, color: str = "#1859b8"):
    """role: 'admin' (own-society forms) or 'apartment' (read-only). sid is only a fallback: the society
    comes from the server session."""
    from app.dash_apps.pages.portal_pages import _rwa_compliance_up_page

    is_admin = role == "admin"
    society_id = get_current_society_id() or sid
    try:
        society_id = int(society_id) if society_id else None
    except (TypeError, ValueError):
        society_id = None

    compliance = _rwa_compliance_up_page(color, role=role, embedded=True)
    if not society_id:
        scoped = [_no_society()]
        return _wrap(role, compliance, scoped, scoped, scoped)

    # ── Rules ───────────────────────────────────────────────────────────────
    try:
        cur_mode = rra.society_cash_mode(society_id)
    except Exception:
        cur_mode = None
    rules = [html.Div(rules_body(society_id), id=f"{P}-body")]
    if is_admin:
        rules.append(mrp.cash_limit_form(P, current_mode=cur_mode))
        rules.append(_note("Statute figures and platform policies apply to every society on the regime, so Master changes "
                           "them centrally. You will see a new value here once it takes effect."))
    else:
        rules.append(mrp._section("Cash-limit enforcement", "How cash payments above the limit are handled in your society.",
                                  html.Div(cur_mode or "regime default", style={"fontSize": "13px", "fontWeight": "600"})))

    # ── Society By-laws ─────────────────────────────────────────────────────
    bye = [html.Div(bye_body(society_id), id=f"{P}-bye-body")]
    if is_admin:
        bye.append(mrp.render_bye_laws_form(society_id, P))

    # ── Meetings & Resolutions ──────────────────────────────────────────────
    mtg = [html.Div(mtg_body(society_id, can_execute=is_admin), id=f"{P}-mtg-body")]
    if is_admin:
        mtg.append(mrp.render_meeting_form(society_id, P))
        mtg.append(mrp.render_resolution_form(society_id, P))
        mtg.append(_note("Step 2 of the bye-law process: when you record a PASSED resolution naming a clause, the "
                         "matching provisional choice is activated automatically (right decision type, quorum and "
                         "meeting body are checked). Record the meeting first, then the resolution."))

    return _wrap(role, compliance, rules, bye, mtg)


def _wrap(role, compliance, rules, bye, mtg):
    head = [html.H5("Society governance", style={"fontWeight": "700", "marginTop": "8px"})]
    if role != "admin":
        head.append(html.Small("Read-only view for your society.", className="text-muted"))
    return html.Div([
        *head,
        html.Div(id=f"{P}-toast"),
        dcc.Tabs(id=f"{P}-tabs", value="tab-rwa", children=[
            dcc.Tab(label="RWA Compliance (UP)", value="tab-rwa", children=html.Div(compliance)),
            dcc.Tab(label="Rules", value="tab-rules", children=html.Div(rules)),
            dcc.Tab(label="Society By-laws", value="tab-bye", children=html.Div(bye)),
            dcc.Tab(label="Meetings & Resolutions", value="tab-mtg", children=html.Div(mtg)),
        ]),
    ])
