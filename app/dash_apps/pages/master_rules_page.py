# app/dash_apps/pages/master_rules_page.py
"""
Master Portal -> "AOA Rule Editor". Renders the editable view of the UP AOA rule tables.
All component ids are prefixed `mrl-`. The body sections are rebuilt by
render_rules_sections() so a save can refresh them without losing the toast.
Writes happen in callbacks/master_rules_callbacks.py -> services/regime_rules_admin.py.
"""
from __future__ import annotations

from datetime import date, timedelta

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.services import regime_rules_admin as rra

REGIME = rra.DEFAULT_REGIME
COLOR = "#c96a19"


def _table(headers, rows, empty):
    if not rows:
        return html.Div(empty, style={"fontSize": "12px", "color": "#888", "padding": "6px 0"})
    return html.Div(dbc.Table([
        html.Thead(html.Tr([html.Th(h, style={"fontSize": "11px"}) for h in headers])),
        html.Tbody([html.Tr([html.Td(c, style={"fontSize": "12px"}) for c in r]) for r in rows]),
    ], hover=True, size="sm", className="mb-0"), style={"overflowX": "auto"})


def _section(title, blurb, *children):
    return html.Div([
        html.H6(title, style={"fontWeight": "700", "color": COLOR, "marginBottom": "2px"}),
        html.P(blurb, style={"fontSize": "11px", "color": "#666", "marginBottom": "10px", "lineHeight": "1.5"}),
        *children,
    ], style={"padding": "16px", "background": "#fffdf8", "borderRadius": "10px", "marginTop": "16px",
              "border": "1px solid #f0e6d2"})


def _label(text):
    return html.Label(text, style={"fontSize": "11px", "fontWeight": "600", "marginBottom": "2px"})


def _val(r):
    v = r.get("value_text") if r.get("value_text") is not None else r.get("value")
    return f"{float(v):g}" if isinstance(v, (int, float)) or hasattr(v, "as_tuple") else str(v)


def _fmt_audit_change(a):
    old, new = a.get("old_value") or {}, a.get("new_value") or {}
    if a["target_table"] == "regime_rule_parameters":
        pick = lambda d: d.get("value_text") if d.get("value_text") is not None else d.get("value")
        return f"{pick(old)} -> {pick(new)} (from {new.get('effective_from')})"
    if a["target_table"] == "societies.cash_limit_mode":
        return f"{old.get('cash_limit_mode') or 'default'} -> {new.get('cash_limit_mode') or 'default'}"
    if a["target_table"] == "society_bye_laws":
        return f"{old.get('status')} -> {new.get('status')} (layer {new.get('layer')})"
    return f"status {old.get('status')} -> {new.get('status')}"


def _status_badge(status: str) -> html.Span:
    colors = {
        "adopted_as_is": "success",
        "adopted_with_variation": "warning",
        "not_adopted": "secondary",
        "provisional": "info",
    }
    return dbc.Badge(status.replace("_", " ").title(), color=colors.get(status, "secondary"), className="me-1", style={"fontSize": "10px"})


def _layer_badge(layer: int) -> html.Span:
    return dbc.Badge(f"Layer {layer}", color="dark", className="me-1", style={"fontSize": "10px"})


def render_bye_laws_sections(society_id: int | None = None) -> list:
    """Render the Society Bye-Laws tab sections."""
    if not society_id:
        return [_section("Society Bye-Laws", "Select a society to view and manage its bye-law adoption register.",
                         html.Div("No society selected.", style={"fontSize": "12px", "color": "#888", "padding": "6px 0"}))]
    
    try:
        clauses = rra.list_society_bye_laws(society_id)
    except Exception:
        clauses = []
    
    # Group by clause_id
    from collections import defaultdict
    by_clause = defaultdict(list)
    for c in clauses:
        by_clause[c["clause_id"]].append(c)
    
    clause_rows = []
    for clause_id, title in rra.MODEL_BYE_LAW_CLAUSES:
        versions = by_clause.get(clause_id, [])
        if not versions:
            # Show all layers as "not set"
            for layer in (1, 2, 3):
                clause_rows.append([
                    html.Div([html.Strong(clause_id, style={"fontSize": "11px"}), html.Br(),
                              html.Small(title, className="text-muted")]),
                    _layer_badge(layer),
                    html.Span("Not set", style={"fontSize": "11px", "color": "#888"}),
                    "", "", "—", "—"])
        else:
            for v in versions:
                clause_rows.append([
                    html.Div([html.Strong(clause_id, style={"fontSize": "11px"}), html.Br(),
                              html.Small(title, className="text-muted")]),
                    _layer_badge(v["layer"]),
                    html.Span([_status_badge(v["status"]), html.Small(("→ " + v["proposed_status"].replace("_", " ")) if v.get("proposed_status") else "", className="text-muted")]),
                    v.get("variation_text") or "—",
                    f"{v['effective_from']:%d %b %Y}" if v.get("effective_from") else "—",
                    "Provisional" if v["status"] == "provisional" else ("Active" if v.get("resolution_id") else "—"),
                    f"Res #{v['resolution_id']}" if v.get("resolution_id") else "—"])
    
    return [
        _section("Society Bye-Laws Register", "Layer 1 = Model Bye-Laws adoption (GBM). Layer 2 = Society Policy (GBM, tighten only). Layer 3 = Board Decision (MC). "
                          "Provisional choices require a passed resolution to become active.",
                  _table(["Clause", "Layer", "Status", "Variation", "Effective", "State", "Resolution"], clause_rows,
                         "No bye-laws configured for this society.")),
    ]


def render_bye_laws_form(society_id: int | None) -> html.Div:
    """Form to save a provisional bye-law choice."""
    if not society_id:
        return html.Div()
    
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    clause_opts = [{"label": f"{c[0]} — {c[1]}", "value": c[0]} for c in rra.MODEL_BYE_LAW_CLAUSES]
    layer_opts = [{"label": f"Layer {l} — {'Model Bye-Law Adoption' if l==1 else 'Society Policy (GBM)' if l==2 else 'Board Decision (MC)'}", "value": l} for l in (1, 2, 3)]
    status_opts = [{"label": {"adopted_as_is": "Adopt as-is", "adopted_with_variation": "Adopt with variation",
                              "not_adopted": "Not adopted (non-statutory clauses only)"}[s], "value": s}
                   for s in rra.ADOPTION_CHOICES]
    
    return _section(
        "Save Provisional Bye-Law Choice", "Creates a provisional entry; becomes active only when linked to a passed resolution. "
        "Layer 1: adopt/reject Model Bye-Law clause. Layer 2: tighten adopted clause (GBM). Layer 3: operational param (MC).",
        dbc.Row([
            dbc.Col([_label("Society"), dbc.Input(id="mrl-bye-soc", type="text", value=str(society_id), readonly=True, size="sm")], md=3),
            dbc.Col([_label("Clause"), dcc.Dropdown(id="mrl-bye-clause", options=clause_opts, clearable=False, style={"fontSize": "12px"})], md=5),
            dbc.Col([_label("Layer"), dcc.Dropdown(id="mrl-bye-layer", options=layer_opts, clearable=False, style={"fontSize": "12px"})], md=4),
        ], className="mb-2"),
        dbc.Row([
            dbc.Col([_label("Choice"), dbc.RadioItems(id="mrl-bye-status", options=status_opts, value="adopted_as_is", className="small")], md=4),
            dbc.Col([_label("Takes effect on"), dbc.Input(id="mrl-bye-eff", type="date", size="sm", value=tomorrow, min=tomorrow)], md=4),
            dbc.Col([_label("Passed resolution ID (blank = save as provisional)"), dbc.Input(id="mrl-bye-res", type="number", size="sm")], md=4),
        ], className="mb-2"),
        _label("Variation text (only for 'Adopt with variation')"),
        dbc.Textarea(id="mrl-bye-variation", rows=3, size="sm", className="mb-2", placeholder="Enter variation text..."),
        _label("Reason for the change"),
        dbc.Input(id="mrl-bye-reason", type="text", size="sm", className="mb-2", placeholder="Minimum 10 characters"),
        dbc.Button("Save provisional choice", id="mrl-bye-save", color="warning", size="sm"),
    )


def render_link_form(society_id: int | None) -> html.Div:
    """Form to link provisional choice to a passed resolution."""
    if not society_id:
        return html.Div()
    
    clause_opts = [{"label": f"{c[0]} — {c[1]}", "value": c[0]} for c in rra.MODEL_BYE_LAW_CLAUSES]
    layer_opts = [{"label": f"Layer {l}", "value": l} for l in (1, 2, 3)]
    
    return _section(
        "Link Provisional Choice to Passed Resolution", "When a GBM/MC passes a resolution on a bye-law, "
        "link the provisional choice here to make it active. The resolution must match the clause and layer.",
        dbc.Row([
            dbc.Col([_label("Society"), dbc.Input(id="mrl-link-soc", type="text", value=str(society_id), readonly=True, size="sm")], md=3),
            dbc.Col([_label("Clause"), dcc.Dropdown(id="mrl-link-clause", options=clause_opts, clearable=False, style={"fontSize": "12px"})], md=5),
            dbc.Col([_label("Layer"), dcc.Dropdown(id="mrl-link-layer", options=layer_opts, clearable=False, style={"fontSize": "12px"})], md=4),
        ], className="mb-2"),
        dbc.Row([
            dbc.Col([_label("Resolution ID"), dbc.Input(id="mrl-link-res", type="number", size="sm")], md=4),
            dbc.Col([_label("Reason"), dbc.Input(id="mrl-link-reason", type="text", size="sm")], md=8),
        ], className="mb-2"),
        dbc.Button("Link to Resolution", id="mrl-link-save", color="success", size="sm"),
    )


# ═════════════════════════════════════════════════════════════════════════════════
# Phase 5: Meetings & Resolutions UI
# ═════════════════════════════════════════════════════════════════════════════════

def render_meetings_sections(society_id: int | None = None) -> list:
    """Render the Meetings & Resolutions tab sections."""
    if not society_id:
        return [_section("Meetings & Resolutions", "Select a society to view and manage its governance records.",
                         html.Div("No society selected.", style={"fontSize": "12px", "color": "#888", "padding": "6px 0"}))]
    
    try:
        meetings = rra.list_meetings(society_id)
    except Exception:
        meetings = []
    
    meeting_rows = []
    for m in meetings:
        meeting_rows.append([
            html.Div([html.Strong(f"#{m['id']} — {m['type']}", style={"fontSize": "11px"}), html.Br(),
                      html.Small(f"Held: {m['held_on']}", className="text-muted")]),
            dbc.Badge("Quorum met" if m.get('quorum_met') else "No quorum", color="success" if m.get('quorum_met') else "warning", className="me-1", style={"fontSize": "10px"}),
            m.get('minutes_pdf') or "—",
            f"{m['created_at']:%d %b %Y %H:%M}" if m.get('created_at') else "—",
            f"User {m.get('created_by')}" if m.get('created_by') else "—"])
    
    # Get resolutions
    try:
        resolutions = rra.list_resolutions(society_id)
    except Exception:
        resolutions = []
    
    resolution_rows = []
    for r in resolutions:
        resolution_rows.append([
            html.Div([html.Strong(f"#{r['id']} — {r['decision_type_code']}", style={"fontSize": "11px"}), html.Br(),
                      html.Small(r.get('clause_id') or "General", className="text-muted")]),
            dbc.Badge("Passed" if r.get('passed') else "Pending", color="success" if r.get('passed') else "secondary", className="me-1", style={"fontSize": "10px"}),
            f"{r.get('passed_on')}" if r.get('passed_on') else "—",
            r.get('majority_required') or "—",
            f"Meeting #{r.get('meeting_id')}" if r.get('meeting_id') else "—",
            r.get('body')[:50] + "..." if r.get('body') and len(r['body']) > 50 else (r.get('body') or "—")])
    
    return [
        _section("Meetings (GBM / EGM / MC)", "Record General Body and Managing Committee meetings.",
                  _table(["Meeting", "Status", "Minutes", "Created", "By"], meeting_rows, "No meetings recorded.")),
        _section("Resolutions", "Decisions passed at meetings. Each resolution links to a decision type and optionally a bye-law clause.",
                  _table(["Resolution", "Status", "Passed On", "Majority %", "Meeting", "Body"], resolution_rows, "No resolutions recorded.")),
    ]


def render_meeting_form(society_id: int | None) -> html.Div:
    """Form to create a meeting."""
    if not society_id:
        return html.Div()
    
    tomorrow = date.today().isoformat()
    type_opts = [{"label": t, "value": t} for t in ("GBM", "EGM", "MC")]
    
    return _section(
        "Record Meeting", "Create a new GBM, EGM, or MC meeting record. Quorum can be marked after the meeting.",
        dbc.Row([
            dbc.Col([_label("Society"), dbc.Input(id="mrl-mtg-soc", type="text", value=str(society_id), readonly=True, size="sm")], md=3),
            dbc.Col([_label("Type"), dcc.Dropdown(id="mrl-mtg-type", options=type_opts, clearable=False, style={"fontSize": "12px"})], md=4),
            dbc.Col([_label("Held on"), dbc.Input(id="mrl-mtg-date", type="date", size="sm", value=tomorrow, max=date.today().isoformat())], md=3),
            dbc.Col([_label("Quorum met"), dbc.Checkbox(id="mrl-mtg-quorum", label="Yes", value=False)], md=2),
        ], className="mb-2"),
        dbc.Row([
            dbc.Col([_label("Minutes PDF path"), dbc.Input(id="mrl-mtg-minutes", type="text", size="sm", placeholder="/path/to/minutes.pdf")], md=8),
        ], className="mb-2"),
        _label("Reason / Notes"),
        dbc.Textarea(id="mrl-mtg-reason", rows=2, size="sm", className="mb-2"),
        dbc.Button("Save Meeting", id="mrl-mtg-save", color="warning", size="sm"),
    )


def render_resolution_form(society_id: int | None) -> html.Div:
    """Form to create a resolution."""
    if not society_id:
        return html.Div()
    
    try:
        meetings = rra.list_meetings(society_id)
    except Exception:
        meetings = []
    meeting_opts = [{"label": f"#{m['id']} — {m['type']} ({m['held_on']})", "value": m["id"]} for m in meetings]
    
    try:
        decision_types = rra.list_decision_types()
    except Exception:
        decision_types = []
    dt_opts = [{"label": f"{dt['code']} — {dt['label']}", "value": dt["id"]} for dt in decision_types]
    
    try:
        clauses = rra.MODEL_BYE_LAW_CLAUSES
    except Exception:
        clauses = []
    clause_opts = [{"label": f"{c[0]} — {c[1]}", "value": c[0]} for c in clauses]
    clause_opts.insert(0, {"label": "General (no clause)", "value": ""})
    
    return _section(
        "Record Resolution", "Create a resolution from a meeting. Decision type determines required body and majority. "
        "Link to a bye-law clause for Layer 1/2/3 enactments.",
        dbc.Row([
            dbc.Col([_label("Society"), dbc.Input(id="mrl-res-soc", type="text", value=str(society_id), readonly=True, size="sm")], md=3),
            dbc.Col([_label("Meeting"), dcc.Dropdown(id="mrl-res-mtg", options=meeting_opts, clearable=False, style={"fontSize": "12px"})], md=5),
            dbc.Col([_label("Decision Type"), dcc.Dropdown(id="mrl-res-dt", options=dt_opts, clearable=False, style={"fontSize": "12px"})], md=4),
        ], className="mb-2"),
        dbc.Row([
            dbc.Col([_label("Clause (optional)"), dcc.Dropdown(id="mrl-res-clause", options=clause_opts, style={"fontSize": "12px"})], md=6),
            dbc.Col([_label("Majority % (from decision type)"), dbc.Input(id="mrl-res-majority", type="number", step="0.01", size="sm", readonly=True)], md=3),
        ], className="mb-2"),
        _label("Resolution Body"),
        dbc.Textarea(id="mrl-res-body", rows=4, size="sm", className="mb-2", placeholder="Full text of the resolution..."),
        dbc.Row([
            dbc.Col([_label("Passed"), dbc.Checkbox(id="mrl-res-passed", label="Mark as passed", value=False)], md=4),
            dbc.Col([_label("Passed on"), dbc.Input(id="mrl-res-passed-on", type="date", size="sm", value=date.today().isoformat())], md=4),
        ], className="mb-2"),
        _label("Reason / Notes"),
        dbc.Textarea(id="mrl-res-reason", rows=2, size="sm", className="mb-2"),
        dbc.Button("Save Resolution", id="mrl-res-save", color="warning", size="sm"),
    )


def render_enactment_section(society_id: int | None) -> list:
    """Section to enact pending resolutions."""
    if not society_id:
        return []
    
    try:
        pending = rra.list_pending_enactments(society_id)
    except Exception:
        pending = []
    
    if not pending:
        return [_section("Resolution Enactment", "All resolutions have been enacted.", html.Div("No pending enactments.", style={"fontSize": "12px", "color": "#888", "padding": "6px 0"}))]
    
    enact_rows = []
    for e in pending:
        enact_rows.append([
            html.Div([html.Strong(f"Resolution #{e['resolution_id']}", style={"fontSize": "11px"}), html.Br(),
                      html.Small(f"{e.get('decision_type_code')} — {e.get('clause_id') or 'General'}", className="text-muted")]),
            e.get('handler_name') or "—",
            e.get('payload_json') or "—",
            e.get('status', 'pending'),
            html.Div([
                dbc.Button("Execute", id={"type": "mrl-enact", "index": e['id']}, color="success", size="sm", outline=True),
            ], style={"display": "flex", "gap": "4px"}),
        ])
    
    return [
        _section("Resolution Enactment", "Execute pending resolution effects (set_regime_param, set_society_policy, set_board_param). "
                          "Each effect is tracked with status and error handling.",
                  _table(["Resolution", "Handler", "Payload", "Status", "Action"], enact_rows, "No pending enactments.")),
    ]


def render_rules_sections() -> list:
    """The three live tables: rules in force, scheduled changes, recent audit."""
    rules = {r["rule_key"]: r for r in rra.effective_rules(REGIME)}
    rule_rows = []
    for key, spec in rra.RULE_SPECS.items():
        r = rules.get(key)
        if not r:
            continue
        rule_rows.append([html.Div([html.Strong(key, style={"fontSize": "12px"}), html.Br(),
                                    html.Small(spec.label, className="text-muted")]),
                          _val(r), r.get("unit") or "", f"{r['effective_from']:%d %b %Y}",
                          html.Small(r.get("source_reference") or "", className="text-muted"),
                          "statute" if spec.statutory else "policy"])
    sched = [[s["rule_key"], _val(s), f"{s['effective_from']:%d %b %Y}", html.Small(s["source_reference"], className="text-muted")]
             for s in rra.scheduled_rules(REGIME)]
    audit = [[f"{a['changed_at']:%d %b %Y %H:%M}", a["target_table"].replace("regime_rule_parameters", "rule")
              .replace("legal_instrument_catalog", "catalog").replace("societies.cash_limit_mode", "society"),
              a.get("rule_key") or "", _fmt_audit_change(a), a["reason"], f"user {a.get('changed_by')}"]
             for a in rra.recent_audit(25)]
    n = rra.societies_on_regime(REGIME)
    return [
        _section("Rules in force today", f"{n} society(ies) are on {REGIME}. A change here applies to all of them from its effective date.",
                 _table(["Rule", "Value", "Unit", "In force since", "Source", "Kind"], rule_rows,
                        "No rules found. Is estatehub.sql's UP AOA compliance layer loaded?")),
        _section("Scheduled changes", "Already queued; they take over automatically on their date.",
                 _table(["Rule", "New value", "Starts", "Source"], sched, "Nothing scheduled.")),
        _section("Audit log (last 25)", "Append-only: the database refuses edits and deletes of these rows.",
                 _table(["When", "Area", "Item", "Change", "Reason", "By"], audit, "No changes recorded yet.")),
    ]


def render_master_rules_page() -> html.Div:
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    rule_opts = [{"label": f"{k} — {s.label}", "value": k} for k, s in rra.RULE_SPECS.items()]
    try:
        instruments = rra.list_instruments(REGIME)
        societies = rra.list_societies_cash_mode(REGIME)
    except Exception:   # tables not integrated yet
        instruments, societies = [], []
    inst_opts = [{"label": f"[{i['instrument_type']}] {i['title']} ({i['enactment_year'] or 'n/a'})", "value": i["id"]}
                 for i in instruments]
    soc_opts = [{"label": f"{s['name']} — {s['cash_limit_mode'] or 'regime default'}", "value": s["id"]} for s in societies]
    
    default_society = societies[0]["id"] if societies else None

    rule_form = _section(
        "Change a rule", "Creates a NEW dated version; the current value is closed the day before. Back-dating is refused. "
        "Statutory figures need the amending instrument cited and an explicit confirmation.",
        dbc.Row([
            dbc.Col([_label("Rule"), dcc.Dropdown(id="mrl-key", options=rule_opts, clearable=False, style={"fontSize": "12px"})], md=6),
            dbc.Col([_label("New value"), dbc.Input(id="mrl-value", type="text", size="sm")], md=3),
            dbc.Col([_label("Takes effect on"), dbc.Input(id="mrl-eff", type="date", size="sm", value=tomorrow, min=tomorrow)], md=3),
        ], className="mb-2"),
        html.Div(id="mrl-hint", style={"fontSize": "11px", "color": "#666", "marginBottom": "8px"}),
        _label("Source — the amending Act / notification / bye-law"),
        dbc.Input(id="mrl-source", type="text", size="sm", className="mb-2"),
        _label("Reason for the change"),
        dbc.Input(id="mrl-reason", type="text", size="sm", className="mb-2"),
        dbc.Checkbox(id="mrl-confirm", label="I confirm this follows an official amendment (required for statutory figures).",
                     className="mb-2", style={"fontSize": "12px"}),
        dbc.Button("Save new version", id="mrl-save", color="warning", size="sm"),
    )
    cat_form = _section(
        "Edit a catalog entry", "Status, provisions, applicability, source and last-verified date. Entries are retired "
        "(status = superseded), never deleted.",
        _label("Instrument"), dcc.Dropdown(id="mrl-cat-id", options=inst_opts, style={"fontSize": "12px"}, className="mb-2"),
        dbc.Row([
            dbc.Col([_label("Status"), dcc.Dropdown(id="mrl-cat-status", clearable=False, style={"fontSize": "12px"},
                                                        options=[{"label": s, "value": s} for s in rra.CATALOG_STATUSES])], md=4),
            dbc.Col([_label("Last verified"), dbc.Input(id="mrl-cat-ver", type="date", size="sm", max=date.today().isoformat())], md=4),
        ], className="mb-2"),
        _label("Applicability"), dbc.Textarea(id="mrl-cat-app", rows=2, size="sm", className="mb-2"),
        _label("Key provisions"), dbc.Textarea(id="mrl-cat-prov", rows=4, size="sm", className="mb-2"),
        _label("Source reference"), dbc.Textarea(id="mrl-cat-src", rows=2, size="sm", className="mb-2"),
        _label("Reason for the change"), dbc.Input(id="mrl-cat-reason", type="text", size="sm", className="mb-2"),
        dbc.Button("Save catalog entry", id="mrl-cat-save", color="warning", size="sm"),
    )
    cash_form = _section(
        "Cash-limit enforcement per society", "warn = record a compliance flag; block = refuse the posting; "
        "blank = follow the regime default (cash_limit_default_mode above).",
        dbc.Row([
            dbc.Col([_label("Society"), dcc.Dropdown(id="mrl-cash-soc", options=soc_opts, style={"fontSize": "12px"})], md=5),
            dbc.Col([_label("Mode"), dcc.Dropdown(id="mrl-cash-mode", style={"fontSize": "12px"}, value="",
                                                  options=[{"label": "regime default", "value": ""},
                                                           {"label": "warn", "value": "warn"}, {"label": "block", "value": "block"}])], md=3),
            dbc.Col([_label("Reason"), dbc.Input(id="mrl-cash-reason", type="text", size="sm")], md=4),
        ], className="mb-2"),
        dbc.Button("Save mode", id="mrl-cash-save", color="warning", size="sm"),
    )
    
    bye_laws_sections = render_bye_laws_sections(default_society)
    bye_laws_form = render_bye_laws_form(default_society)
    link_form = render_link_form(default_society)
    
    meetings_sections = render_meetings_sections(default_society)
    meeting_form = render_meeting_form(default_society)
    resolution_form = render_resolution_form(default_society)
    enactment_section = render_enactment_section(default_society)
    
    return html.Div([
        html.H4([html.I(className="fas fa-sliders-h me-2", style={"color": COLOR}), "AOA Rule Editor"], style={"fontWeight": "700"}),
        html.P("Master-only. Every change is validated, dated and written to the audit log. Confirm any statutory change "
               "with an advocate before relying on it.", style={"fontSize": "12px", "color": "#666"}),
        html.Div(id="mrl-toast"),
        dcc.Tabs(id="mrl-tabs", value="tab-rules", children=[
            dcc.Tab(label="Rules", value="tab-rules", children=html.Div(render_rules_sections(), id="mrl-body")),
            dcc.Tab(label="Society Bye-Laws", value="tab-bye-laws", children=html.Div(bye_laws_sections, id="mrl-bye-body")),
            dcc.Tab(label="Meetings & Resolutions", value="tab-mtg", children=html.Div(meetings_sections + enactment_section, id="mrl-mtg-body")),
        ]),
        rule_form, cat_form, cash_form,
        bye_laws_form, link_form,
        meeting_form, resolution_form,
    ], className="portal-page")
