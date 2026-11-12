# app/dash_apps/pages/adoption_panel.py
"""
Stage 6 (Adoption) panel: Model Bye-Laws adoption + society resolution settings.

Moved here from the Setup Wizard's "Model Bye-Laws Adoption" step (item 8).
Choices remain provisional until a passed resolution is recorded under
Settings → Society governance → Meetings & Resolutions.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.services import regime_rules_admin as rra


def render_adoption_panel(society_id: int | None) -> html.Div:
    """Render the adoption panel for Stage 6 inside the Hub."""
    if not society_id:
        return html.Div("Select a society first.", className="text-muted")
    existing = {}
    try:
        for r in rra.list_society_bye_laws(society_id) or []:
            if r["layer"] == 1:
                existing[r["clause_id"]] = r
    except Exception:                                              # noqa: BLE001
        existing = {}
    labels = {"adopted_as_is": "Adopt as-is", "adopted_with_variation": "Adopt with variation",
              "not_adopted": "Not adopted"}
    rows = []
    for clause_id, title in rra.MODEL_BYE_LAW_CLAUSES:
        locked = rra.clause_is_locked(society_id, clause_id) or clause_id in rra.STATUTE_BACKED_CLAUSES
        cur = existing.get(clause_id) or {}
        current = cur.get("proposed_status") if cur.get("status") == "provisional" else cur.get("status")
        opts = [{"label": labels[c], "value": c} for c in rra.ADOPTION_CHOICES
                if not (locked and c == "not_adopted")]
        active = bool(cur.get("resolution_id")) and cur.get("status") != "provisional"
        rows.append(html.Tr([
            html.Td([html.Strong(clause_id, style={"fontSize": "11px"}), html.Br(),
                     html.Small(title + (" · enforced by the engine" if locked else ""), className="text-muted")],
                    style={"maxWidth": "260px"}),
            html.Td(dbc.RadioItems(id={"type": "sw-bl-choice", "clause": clause_id}, options=opts, value=current,
                                   inline=True, className="small", inputClassName="me-1", labelClassName="me-3",
                                   persistence=False)
                    if not active else dbc.Badge("Active (resolution on file)", color="success")),
            html.Td(dbc.Input(id={"type": "sw-bl-var", "clause": clause_id}, type="text", debounce=True, size="sm",
                              value=cur.get("variation_text") or "", placeholder="Variation text",
                              disabled=active, style={"fontSize": "11px"})),
            html.Td(html.Small(id={"type": "sw-bl-msg", "clause": clause_id}, className="text-muted")),
        ]))
    try:
        pol = rra.list_society_policies(society_id) or {}
    except Exception:                                              # noqa: BLE001
        pol = {}
    pol_rows, fund_pol_rows = [], []
    for key, (label, clause, choices) in rra.POLICY_SPECS.items():
        if key in rra.FUND_STEP_POLICY_KEYS:
            continue                      # asked on the Funds step
        st = pol.get(key) or {"value": choices[0][0], "active": False, "proposed": None}
        shown = st["proposed"] or st["value"]
        (fund_pol_rows if key in rra.FUND_POLICY_KEYS else pol_rows).append(html.Tr([
            html.Td([html.Strong(label, style={"fontSize": "12px"}), html.Br(),
                     html.Small(f"Resolution on {clause}", className="text-muted")], style={"maxWidth": "260px"}),
            html.Td(dbc.Select(id={"type": "sw-pol-choice", "key": key}, size="sm",
                               options=[{"label": lbl, "value": v} for v, lbl in choices], value=shown)),
            html.Td([dbc.Badge("Active (resolution on file)", color="success") if st["active"] and not st["proposed"]
                     else dbc.Badge("Provisional", color="warning", text_color="dark"),
                     html.Small(id={"type": "sw-pol-msg", "key": key}, className="text-muted ms-2")]),
        ]))
    policy_panel = html.Div([
        html.H6("Society resolution settings", className="mt-3 mb-1"),
        html.Small("Choices the engine used to hard-code. Provisional until you record the passed resolution "
                   "(Settings → Society governance → Meetings & Resolutions). "
                   "Clauses 7, 39, 49 and 55 are 'enforced by the engine' unless you allow them to be dropped; "
                   "which clauses are truly non-droppable is a legal call - confirm with an advocate.",
                   className="text-muted d-block mb-2"),
        dbc.Table([html.Thead(html.Tr([html.Th(h, style={"fontSize": "11px"}) for h in ("Setting", "Choice", "Status")])),
                   html.Tbody(pol_rows)], bordered=True, size="sm"),
        html.H6("Funds & assessments", className="mt-3 mb-1"),
        html.Small("Whether and how a Sinking or Repair fund is collected is asked on the Funds step.",
                   className="text-muted d-block mb-2"),
        dbc.Table([html.Thead(html.Tr([html.Th(h, style={"fontSize": "11px"}) for h in ("Setting", "Choice", "Status")])),
                   html.Tbody(fund_pol_rows)], bordered=True, size="sm") if fund_pol_rows else html.Div(),
    ])
    try:                                # status of the signed scan on file (stored / stale / none)
        from app.dash_apps.callbacks.paper_sign_callbacks import _status as _scan_status
        initial_scan_status = _scan_status(society_id)
    except Exception:                                              # noqa: BLE001
        initial_scan_status = None
    paper_card = dbc.Card(dbc.CardBody([
        html.H6([html.I(className="fas fa-file-signature me-2"), "Adoption of Bye-laws 1-58"], className="mb-1"),
        html.Small("Record which Model Bye-Laws 2011 clauses your Association adopts. Upload the signed General Body "
                   "minutes here as the real third-party document (Annex G); the clause choices are stored as data. "
                   "No separate print/sign/scan loop is needed for the bye-law list itself.", className="text-muted d-block mb-2"),
        dbc.Row([
            dbc.Col(dbc.Button([html.I(className="fas fa-download me-2"), "Society_bye_laws.xlsx"], id="adopt-bl-tpl",
                               size="sm", outline=True, color="secondary", n_clicks=0), width="auto"),
            dbc.Col(dcc.Upload(id="adopt-bl-xlsx", children=dbc.Button([html.I(className="fas fa-file-excel me-2"), "Upload filled xlsx"],
                                                                           size="sm", outline=True, color="secondary", n_clicks=0),
                               multiple=False, accept=".xlsx"), width="auto"),
            dbc.Col(dcc.Upload(id="adopt-bl-scan", children=dbc.Button([html.I(className="fas fa-file-upload me-2"), "Upload signed General Body minutes"],
                                                                           size="sm", outline=True, color="secondary", n_clicks=0),
                               multiple=False, accept=".pdf,.png,.jpg,.jpeg"), width="auto"),
        ], className="g-2"),
        dcc.Download(id="adopt-bl-tpl-dl"),
        html.Div(id="adopt-bl-import-status", className="mt-2", style={"fontSize": "12px"}),
        html.Div(initial_scan_status, id="adopt-bl-evidence-status", className="mt-2", style={"fontSize": "12px"}),
    ]), className="mb-3")
    return html.Div([
        paper_card,
        dbc.Alert([html.I(className="fas fa-scale-balanced me-2"),
                   "Record which Model Bye-Laws 2011 clauses your Association is adopting. These are ",
                   html.Strong("provisional"), (" — nothing changes in how EstateHub treats dues, voting, NOC or filings "
                   "until you record the General Body meeting and its passed resolution. Clauses you leave alone follow the "
                   "Model Bye-Laws and the Act as written.")], color="info", className="mb-3", style={"fontSize": "13px"}),
        html.Div([
            html.Div([html.Strong("Who can change what"), html.Br(),
                      html.Small("Act & Rules (locked) → Model Bye-Laws (this step; GBM resolution, 2/3) → Society Policy "
                                 "(GBM; may only tighten a clause) → Board Decision (MC; operational limits). "
                                 "A lower layer can never loosen a higher one.", className="text-muted")],
                     className="mb-2")]),
        html.Div(dbc.Table([html.Thead(html.Tr([html.Th(h, style={"fontSize": "11px"}) for h in
                            ("Clause", "Intended outcome", "Variation (if any)", "")])),
                            html.Tbody(rows)], bordered=True, size="sm", hover=True),
                 style={"maxHeight": "420px", "overflowY": "auto"}),
        policy_panel,
        dbc.Alert([html.I(className="fas fa-arrow-right me-2"), html.Strong("Next: "),
                   "after the General Body meets, record the meeting and then the passed resolution under ",
                   html.Strong("Settings → Society governance → Meetings & Resolutions"),
                   ". That activates the choices above automatically. ",
                   html.Strong("Order matters: save the choice first, then record the resolution. "
                               "An older resolution can't activate a newer choice.")],
                  color="warning", className="mt-3", style={"fontSize": "13px"}),
    ], className="onb-main")
