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
    return f"status {old.get('status')} -> {new.get('status')}"


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
    return html.Div([
        html.H4([html.I(className="fas fa-sliders-h me-2", style={"color": COLOR}), "AOA Rule Editor"], style={"fontWeight": "700"}),
        html.P("Master-only. Every change is validated, dated and written to the audit log. Confirm any statutory change "
               "with an advocate before relying on it.", style={"fontSize": "12px", "color": "#666"}),
        html.Div(id="mrl-toast"),
        html.Div(render_rules_sections(), id="mrl-body"),
        rule_form, cat_form, cash_form,
    ], className="portal-page")
