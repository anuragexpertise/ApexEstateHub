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


def _kind_badge(statutory: bool):
    return (dbc.Badge("Statute", color="danger", className="me-1", style={"fontSize": "10px"}) if statutory else
            dbc.Badge("Policy", color="secondary", className="me-1", style={"fontSize": "10px"}))


KIND_LEGEND = html.Div([
    html.Div([_kind_badge(True), html.Span("A figure laid down by the Act, Rules or Bye-laws. Mandatory for every society; "
                                           "it changes only when the law is amended.", style={"fontSize": "11px"})],
             style={"marginBottom": "4px"}),
    html.Div([_kind_badge(False), html.Span("A setting chosen by the platform (not a statute figure). Applies to every society "
                                            "on the regime unless noted.", style={"fontSize": "11px"})]),
], style={"padding": "10px 12px", "background": "#f6f8fb", "border": "1px solid #e1e7ef", "borderRadius": "8px"})


def _status_badge(status: str) -> html.Span:
    colors = {
        "adopted_as_is": "success",
        "adopted_with_variation": "warning",
        "not_adopted": "secondary",
        "provisional": "info",
    }
    label = {"adopted_as_is": "Adopted as-is", "adopted_with_variation": "Adopted with variation",
             "not_adopted": "Not adopted", "provisional": "Provisional"}.get(status, status.replace("_", " ").title())
    return dbc.Badge(label, color=colors.get(status, "secondary"), className="me-1", style={"fontSize": "10px"})


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
                          "A provisional choice becomes active automatically when you record a matching passed resolution (Meetings & Resolutions tab).",
                  _table(["Clause", "Layer", "Status", "Variation", "Effective", "State", "Resolution"], clause_rows,
                         "No bye-laws configured for this society.")),
    ]


LAYER_HELP = {
    1: ("Model Bye-Law adoption", "Decided by the General Body (GBM). Adopt a clause of the 2011 Model Bye-Laws as-is, "
                                  "adopt it with a variation, or - for non-statutory clauses only - not adopt it."),
    2: ("Society policy", "Decided by the General Body (GBM). Tightens an adopted clause for your society; "
                          "it can never loosen the Model Bye-Law."),
    3: ("Board decision", "Decided by the Managing Committee (MC). An operating setting within the limits of the "
                          "adopted clause and society policy."),
}
CHOICE_LABELS = {"adopted_as_is": "Adopt as-is", "adopted_with_variation": "Adopt with variation",
                 "not_adopted": "Not adopted"}


def render_bye_laws_form(society_id: int | None, p: str = "gov") -> html.Div:
    """Guided form: pick clause -> pick who decides (layer) -> only the choices that are allowed are offered, the
    clause title and notification link are shown for 'as-is', and a text box appears only for 'with variation'."""
    if not society_id:
        return html.Div()

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    clause_opts = [{"label": f"{c[0]} — {c[1]}", "value": c[0]} for c in rra.MODEL_BYE_LAW_CLAUSES]
    layer_opts = [{"label": f"Layer {l} — {LAYER_HELP[l][0]}", "value": l} for l in (1, 2, 3)]

    return _section(
        "Save Provisional Bye-Law Choice",
        "Step 1 of 2. Record what the society intends. It stays provisional until you record the matching passed "
        "resolution under Meetings & Resolutions (step 2), which activates it automatically. "
        "Order matters: save the choice first, then record the resolution.",
        dbc.Row([
            dbc.Col([_label("Clause"), dcc.Dropdown(id=f"{p}-bye-clause", options=clause_opts, clearable=False,
                                                    style={"fontSize": "12px"})], md=7),
            dbc.Col([_label("Who decides (layer)"), dcc.Dropdown(id=f"{p}-bye-layer", options=layer_opts, value=1,
                                                                 clearable=False, style={"fontSize": "12px"})], md=5),
        ], className="mb-2"),
        html.Div(id=f"{p}-bye-layer-help", children=LAYER_HELP[1][1],
                 style={"fontSize": "11px", "color": "#666", "marginBottom": "8px"}),
        _label("Your choice"),
        dbc.RadioItems(id=f"{p}-bye-status", options=[{"label": "Select a clause first", "value": "", "disabled": True}],
                       className="small mb-2"),
        html.Div(id=f"{p}-bye-info", className="mb-2"),
        html.Div([
            _label("Your variation — the exact wording the society adopts"),
            dbc.Textarea(id=f"{p}-bye-variation", rows=3, size="sm", placeholder="Enter variation text..."),
        ], id=f"{p}-bye-var-wrap", style={"display": "none"}, className="mb-2"),
        dbc.Row([
            dbc.Col([_label("Takes effect on"), dbc.Input(id=f"{p}-bye-eff", type="date", size="sm", value=tomorrow, min=tomorrow)], md=4),
            dbc.Col([_label("Reason for the change (min. 10 characters)"), dbc.Input(id=f"{p}-bye-reason", type="text", size="sm")], md=8),
        ], className="mb-2"),
        dbc.Button("Save provisional choice", id=f"{p}-bye-save", color="warning", size="sm"),
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


def render_meeting_form(society_id: int | None, p: str = "mrl") -> html.Div:
    """Form to create a meeting."""
    if not society_id:
        return html.Div()
    
    tomorrow = date.today().isoformat()
    type_opts = [{"label": t, "value": t} for t in ("GBM", "EGM", "MC")]
    
    return _section(
        "Record Meeting", "Create a new GBM, EGM, or MC meeting record. Quorum can be marked after the meeting.",
        dbc.Row([
            dbc.Col([_label("Society"), dbc.Input(id=f"{p}-mtg-soc", type="text", value=str(society_id), readonly=True, size="sm")], md=3),
            dbc.Col([_label("Type"), dcc.Dropdown(id=f"{p}-mtg-type", options=type_opts, clearable=False, style={"fontSize": "12px"})], md=4),
            dbc.Col([_label("Held on"), dbc.Input(id=f"{p}-mtg-date", type="date", size="sm", value=tomorrow, max=date.today().isoformat())], md=3),
            dbc.Col([_label("Quorum met"), dbc.Checkbox(id=f"{p}-mtg-quorum", label="Yes", value=False)], md=2),
        ], className="mb-2"),
        dbc.Row([
            dbc.Col([_label("Minutes PDF path"), dbc.Input(id=f"{p}-mtg-minutes", type="text", size="sm", placeholder="/path/to/minutes.pdf")], md=8),
        ], className="mb-2"),
        _label("Reason / Notes"),
        dbc.Textarea(id=f"{p}-mtg-reason", rows=2, size="sm", className="mb-2"),
        dbc.Button("Save Meeting", id=f"{p}-mtg-save", color="warning", size="sm"),
    )


def render_resolution_form(society_id: int | None, p: str = "mrl") -> html.Div:
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
            dbc.Col([_label("Society"), dbc.Input(id=f"{p}-res-soc", type="text", value=str(society_id), readonly=True, size="sm")], md=3),
            dbc.Col([_label("Meeting"), dcc.Dropdown(id=f"{p}-res-mtg", options=meeting_opts, clearable=False, style={"fontSize": "12px"})], md=5),
            dbc.Col([_label("Decision Type"), dcc.Dropdown(id=f"{p}-res-dt", options=dt_opts, clearable=False, style={"fontSize": "12px"})], md=4),
        ], className="mb-2"),
        dbc.Row([
            dbc.Col([_label("Clause (optional)"), dcc.Dropdown(id=f"{p}-res-clause", options=clause_opts, style={"fontSize": "12px"})], md=6),
            dbc.Col([_label("Majority % (from decision type)"), dbc.Input(id=f"{p}-res-majority", type="number", step="0.01", size="sm", readonly=True)], md=3),
        ], className="mb-2"),
        _label("Resolution Body"),
        dbc.Textarea(id=f"{p}-res-body", rows=4, size="sm", className="mb-2", placeholder="Full text of the resolution..."),
        dbc.Row([
            dbc.Col([_label("Passed"), dbc.Checkbox(id=f"{p}-res-passed", label="Mark as passed", value=False)], md=4),
            dbc.Col([_label("Passed on"), dbc.Input(id=f"{p}-res-passed-on", type="date", size="sm", value=date.today().isoformat())], md=4),
        ], className="mb-2"),
        _label("Reason / Notes"),
        dbc.Textarea(id=f"{p}-res-reason", rows=2, size="sm", className="mb-2"),
        dbc.Button("Save Resolution", id=f"{p}-res-save", color="warning", size="sm"),
    )


def render_enactment_section(society_id: int | None, p: str = "mrl", can_execute: bool = True) -> list:
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
                dbc.Button("Execute", id={"type": f"{p}-enact", "index": e['id']}, color="success", size="sm", outline=True),
            ], style={"display": "flex", "gap": "4px"}) if (can_execute and e.get("handler_name") != "set_regime_param") else html.Small(
                "Regime-wide: Master changes it via Change a rule" if e.get("handler_name") == "set_regime_param"
                else "Admin executes", className="text-muted"),
        ])
    
    return [
        _section("Resolution Enactment", "Execute pending resolution effects (set_regime_param, set_society_policy, set_board_param). "
                          "Each effect is tracked with status and error handling.",
                  _table(["Resolution", "Handler", "Payload", "Status", "Action"], enact_rows, "No pending enactments.")),
    ]


def render_rules_sections(society_id: int | None = None) -> list:
    """The three live tables: rules in force, scheduled changes, recent audit.
    With society_id, the regime is the society's own and the audit log is that society's (plus regime-wide
    rule changes that apply to it)."""
    regime = (rra.society_regime(society_id) if society_id else None) or REGIME
    rules = {r["rule_key"]: r for r in rra.effective_rules(regime)}
    rule_rows = []
    for key, spec in rra.RULE_SPECS.items():
        r = rules.get(key)
        if not r:
            continue
        rule_rows.append([html.Div([html.Strong(key, style={"fontSize": "12px"}), html.Br(),
                                    html.Small(spec.label, className="text-muted")]),
                          _val(r), r.get("unit") or "", f"{r['effective_from']:%d %b %Y}",
                          html.Small(r.get("source_reference") or "", className="text-muted"),
                          _kind_badge(spec.statutory)])
    sched = [[s["rule_key"], _val(s), f"{s['effective_from']:%d %b %Y}", html.Small(s["source_reference"], className="text-muted")]
             for s in rra.scheduled_rules(regime)]
    audit = [[f"{a['changed_at']:%d %b %Y %H:%M}", a["target_table"].replace("regime_rule_parameters", "rule")
              .replace("legal_instrument_catalog", "catalog").replace("societies.cash_limit_mode", "society"),
              a.get("rule_key") or "", _fmt_audit_change(a), a["reason"], f"user {a.get('changed_by')}"]
             for a in rra.recent_audit(25, society_id)]
    n = rra.societies_on_regime(regime)
    blurb = (f"Your society is on {regime}. These are the rules in force for it today." if society_id else
             f"{n} society(ies) are on {regime}. A change here applies to all of them from its effective date.")
    return [
        _section("Rules in force today", blurb, KIND_LEGEND,
                 _table(["Rule", "Value", "Unit", "In force since", "Source", "Kind"], rule_rows,
                        "No rules found. Is estatehub.sql's UP AOA compliance layer loaded?")),
        _section("Scheduled changes", "Already queued; they take over automatically on their date.",
                 _table(["Rule", "New value", "Starts", "Source"], sched, "Nothing scheduled.")),
        _section("Audit log (last 25)", "Append-only: the database refuses edits and deletes of these rows.",
                 _table(["When", "Area", "Item", "Change", "Reason", "By"], audit, "No changes recorded yet.")),
    ]


def cash_limit_form(p: str, current_mode=None) -> html.Div:
    """Cash-limit enforcement for ONE society (the signed-in admin's; re-checked server-side). It is a
    society-specific setting, so master has no form for it."""
    mode_opts = [{"label": "regime default", "value": ""}, {"label": "warn", "value": "warn"}, {"label": "block", "value": "block"}]
    return _section(
        "Cash-limit enforcement (your society)",
        "warn = record a compliance flag; block = refuse the posting; blank = follow the regime default.",
        dbc.Row([
            dbc.Col([_label("Mode"), dcc.Dropdown(id=f"{p}-cash-mode", style={"fontSize": "12px"}, value=current_mode or "",
                                                  options=mode_opts, clearable=False)], md=4),
            dbc.Col([_label("Reason (min. 10 characters)"), dbc.Input(id=f"{p}-cash-reason", type="text", size="sm")], md=8),
        ], className="mb-2"),
        dbc.Button("Save mode", id=f"{p}-cash-save", color="warning", size="sm"),
    )


def catalog_edit_form() -> html.Div:
    """Master-only: edit a legal_instrument_catalog entry. Ids stay mrl-cat-* (master callbacks)."""
    try:
        instruments = rra.list_instruments(REGIME)
    except Exception:
        instruments = []
    inst_opts = [{"label": f"[{i['instrument_type']}] {i['title']} ({i['enactment_year'] or 'n/a'})", "value": i["id"]}
                 for i in instruments]
    return _section(
        "Edit a catalog entry", "Status, provisions, applicability, source and last-verified date. Entries are retired "
        "(status = superseded), never deleted.",
        _label("Instrument"), dcc.Dropdown(id="mrl-cat-id", options=inst_opts, style={"fontSize": "12px"}, className="mb-2"),
        dbc.Row([
            dbc.Col([_label("Status"), dcc.Dropdown(id="mrl-cat-status", clearable=False, style={"fontSize": "12px"},
                                                    options=[{"label": x, "value": x} for x in rra.CATALOG_STATUSES])], md=4),
            dbc.Col([_label("Last verified"), dbc.Input(id="mrl-cat-ver", type="date", size="sm", max=date.today().isoformat())], md=4),
        ], className="mb-2"),
        _label("Applicability"), dbc.Textarea(id="mrl-cat-app", rows=2, size="sm", className="mb-2"),
        _label("Key provisions"), dbc.Textarea(id="mrl-cat-prov", rows=4, size="sm", className="mb-2"),
        _label("Source reference"), dbc.Textarea(id="mrl-cat-src", rows=2, size="sm", className="mb-1"),
        html.Div("Include the full https:// link to the instrument. For the Bye-laws entry, the first link here is the "
                 "'Read the notified Model Bye-Laws' link every society sees when adopting a clause as-is.",
                 style={"fontSize": "11px", "color": "#666"}, className="mb-2"),
        _label("Reason for the change"), dbc.Input(id="mrl-cat-reason", type="text", size="sm", className="mb-2"),
        dbc.Button("Save catalog entry", id="mrl-cat-save", color="warning", size="sm"),
    )


def render_master_rules_page() -> html.Div:
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    rule_opts = [{"label": f"{k} — {s.label}", "value": k} for k, s in rra.RULE_SPECS.items()]
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
    # Master manages the law: Statute / Policy rule values (and catalog entries, on RWA Compliance (UP)).
    # Bye-law adoption, meetings and resolutions are each society's own governance and are edited by that
    # society's admin (Admin -> Settings), as is the society-specific cash-limit mode, so none are offered here.
    # 'Edit a catalog entry' lives on RWA Compliance (UP).
    return html.Div([
        html.H4([html.I(className="fas fa-sliders-h me-2", style={"color": COLOR}), "AOA Rule Editor"], style={"fontWeight": "700"}),
        html.P("Master-only. Statute figures change only when the law is amended; every change is validated, dated and "
               "written to the audit log. Confirm any statutory change with an advocate before relying on it.",
               style={"fontSize": "12px", "color": "#666"}),
        html.Div(id="mrl-toast"),
        html.Div(render_rules_sections(), id="mrl-body"),
        rule_form,
    ], className="portal-page")
