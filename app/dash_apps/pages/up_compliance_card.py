# app/dash_apps/pages/up_compliance_card.py
"""
"UP AOA Compliance" admin card: UP Apartment Act 2010 / Model Bye-Laws 2011.

Pure rendering: render_up_compliance_card(data) takes the dict from
app.services.up_aoa_actions.load_card_data and returns a Dash component, so it can
be tested without a browser. Every figure and verdict comes from the SQL rule
functions; nothing is decided here.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.services.up_aoa_actions import NODUES_ACTIONS, PAY_MODES, S22_STEPS

COLOR = "#7a4f01"
_STATUS_COLOR = {"done": "#17976e", "overdue": "#c0392b", "due_soon": "#d68910", "upcoming": "#566573",
                 "deemed_granted": "#17976e", "issued": "#17976e", "refused": "#c0392b", "pending": "#d68910",
                 "not_requested": "#566573"}


def _fmt(v):
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, (int,)):
        return str(v)
    if isinstance(v, (Decimal, float)):
        return f"{float(v):,.2f}"
    if isinstance(v, date):
        return v.strftime("%d %b %Y")
    return str(v)


def _badge(text):
    c = _STATUS_COLOR.get(str(text), "#566573")
    return html.Span(str(text).replace("_", " "), style={"background": c, "color": "#fff", "borderRadius": "10px",
                                                           "padding": "2px 9px", "fontSize": "11px", "fontWeight": "700"})


def _table(headers, rows, empty="Nothing recorded yet."):
    if not rows:
        return html.Div(empty, style={"fontSize": "12px", "color": "#888", "padding": "6px 0"})
    return html.Div(dbc.Table([
        html.Thead(html.Tr([html.Th(h, style={"fontSize": "11px"}) for h in headers])),
        html.Tbody([html.Tr([html.Td(c, style={"fontSize": "12px"}) for c in r]) for r in rows]),
    ], bordered=False, hover=True, size="sm", className="mb-0"), style={"overflowX": "auto"})


def _section(title, blurb, *children):
    return html.Div([
        html.H6(title, style={"fontWeight": "700", "color": COLOR, "marginBottom": "2px"}),
        html.P(blurb, style={"fontSize": "11px", "color": "#666", "marginBottom": "10px", "lineHeight": "1.5"}) if blurb else None,
        *children,
    ], style={"padding": "16px", "background": "#fffdf8", "borderRadius": "10px", "marginTop": "16px", "border": "1px solid #f0e6d2"})


def _field(label, comp, width=3):
    return dbc.Col([dbc.Label(label, style={"fontSize": "12px"}), comp], width=width)


def _date(id_):
    return dcc.DatePickerSingle(id=id_, display_format="YYYY-MM-DD", style={"width": "100%", "fontSize": "13px"})


def _btn(label, id_, icon="fa-save"):
    return dbc.Button([html.I(className=f"fas {icon} me-2"), label], id=id_, n_clicks=0, color="primary",
                      style={"borderRadius": "8px", "fontWeight": "600", "fontSize": "12px", "marginTop": "8px"})


def _flat_opts(apts):
    return [{"label": f"{a['flat_number']}  {a.get('owner_name') or ''}".strip(), "value": a["id"]} for a in apts]


def _mode_dd(id_):
    return dcc.Dropdown(id=id_, options=[{"label": m.capitalize(), "value": m} for m in PAY_MODES], value="bank",
                        clearable=False, style={"fontSize": "13px"})


def render_up_compliance_card(data: dict) -> html.Div:
    name = (data.get("society") or {}).get("name", "Society")
    header = html.Div([
        html.H5([html.I(className="fas fa-gavel me-2"), "UP AOA Compliance"], style={"fontWeight": "800", "color": COLOR, "marginBottom": "2px"}),
        html.Div(f"{name} \u00b7 UP Apartment Act 2010 and Model Bye-Laws 2011", style={"fontSize": "12px", "color": "#666"}),
        html.Div("These tools record and check; the Board and the competent authority act. Confirm bye-law numbers with an advocate "
                 "before relying on them in a filing.", style={"fontSize": "11px", "color": "#8a6d3b", "marginTop": "4px"}),
    ], style={"marginBottom": "6px"})
    toast = html.Div(id="upc-toast", style={"marginTop": "10px"})

    if not data.get("rules_on"):
        return html.Div([header, dbc.Alert(
            "UP Apartment Act rules are not active for this society. They switch on when the society's legal regime is "
            "Uttar Pradesh (AOA 2010); set the State in Society Details.", color="secondary")], style={"padding": "12px"})

    apts = data.get("apartments") or []
    flat_opts = _flat_opts(apts)
    secs = []

    # ── 1. Bye-law 49 calendar ───────────────────────────────────────────────
    cal = data.get("calendar") or []
    fy_opts = sorted({int(r["fy_label"][:4]) for r in cal}, reverse=True)
    secs.append(_section(
        "Statement filings (bye-law 49)",
        "Audited statement published by 31 July, copy to the competent authority by 15 August, summary to every owner within 15 days "
        "of publication, with owner and loanee lists attached.",
        _table(["Year", "Step", "Due", "Done on", "Status"],
               [[r["fy_label"], r["step"], _fmt(r["due_date"]), _fmt(r["done_on"]), _badge(r["status"])] for r in cal]),
        html.Hr(),
        dbc.Row([
            _field("Financial year", dcc.Dropdown(id="upc-fil-fy", options=[{"label": f"{y}-{str(y + 1)[-2:]}", "value": y} for y in fy_opts],
                                                   value=fy_opts[0] if fy_opts else None, clearable=False, style={"fontSize": "13px"}), 2),
            _field("Statements published", _date("upc-fil-pub"), 2),
            _field("Copy to authority", _date("upc-fil-auth"), 2),
            _field("Summaries sent to owners", _date("upc-fil-sum"), 2),
            _field("Auditor", dbc.Input(id="upc-fil-auditor", type="text", placeholder="Name of auditor", style={"fontSize": "13px"}), 4),
        ], className="g-2"),
        dbc.Row([dbc.Col(dbc.Checklist(id="upc-fil-attach", options=[
            {"label": "Owner list attached", "value": "owners"}, {"label": "Loanee list attached", "value": "loanees"}],
            value=[], inline=True, style={"fontSize": "12px"}), width=8)], className="mt-2"),
        html.Div([_btn("Save filing record", "upc-fil-save"),
                  dbc.Button([html.I(className="fas fa-file-excel me-2"), "Download owner and loanee lists"], id="upc-export-btn", n_clicks=0,
                             color="secondary", outline=True, style={"borderRadius": "8px", "fontWeight": "600", "fontSize": "12px",
                                                                      "marginTop": "8px", "marginLeft": "8px"}),
                  dcc.Download(id="upc-export-dl")]),
    ))

    # ── 2. Undivided interest and billing basis ──────────────────────────────
    s = data.get("ui_summary") or {}
    basis = data.get("basis") or {}
    ok = bool(s.get("balanced"))
    secs.append(_section(
        "Undivided interest and billing basis (Act s.5(2), s.18(1))",
        "Each flat's share is its area divided by the total area of all flats, as stated in the Declaration. Common expenses are then "
        "split by that percentage. Enter the Declaration's own figures if it weights by anything other than area.",
        html.Div([_badge("done" if ok else "overdue"),
                  html.Span(f"  {_fmt(s.get('total_declared_pct'))}% declared across {s.get('apartments_total', 0)} flats; "
                            f"{s.get('apartments_missing', 0)} missing", style={"fontSize": "12px", "marginLeft": "6px"})]),
        _table(["Flat", "Area", "Declared %", "Area-based %", "Status"],
               [[r["flat_number"], _fmt(r["apartment_size"]), _fmt(r["declared_pct"]), _fmt(r["area_based_pct"]),
                 _badge({"matches_area": "done", "missing": "overdue"}.get(r["status"], "due_soon"))] for r in (data.get("ui_rows") or [])]),
        _btn("Fill missing from area share", "upc-ui-fill", "fa-calculator"),
        html.Hr(),
        dbc.Row([
            _field("Maintenance billed", dcc.Dropdown(id="upc-basis", clearable=False, style={"fontSize": "13px"},
                   options=[{"label": "Per sq ft (rate x area)", "value": "per_sqft"},
                            {"label": "By undivided interest % (budget x %)", "value": "undivided_interest"}],
                   value=basis.get("billing_basis") or "per_sqft"), 4),
            _field("Monthly common-expense budget", dbc.Input(id="upc-budget", type="number", min=0, step="0.01", placeholder="\u20b9 per month",
                   value=float(basis["common_expense_budget_monthly"]) if basis.get("common_expense_budget_monthly") else None,
                   style={"fontSize": "13px"}), 3),
        ], className="g-2"),
        _btn("Save billing basis", "upc-basis-save"),
    ))

    # ── 3. Transfers ─────────────────────────────────────────────────────────
    tr = data.get("transfers") or []
    secs.append(_section(
        "Transfers: Major Repair Fund and No Dues (bye-law 39)",
        "On a sale, \u00bd% of the transfer value goes to the Major Repair Fund (account 3270), not the Reserve Fund. It is added to the flat's "
        "dues. A No Dues Certificate is treated as granted if not refused within 15 days of the request.",
        _table(["Flat", "Date", "Buyer", "Value", "Fee", "No Dues"],
               [[r["flat_number"], _fmt(r["transfer_date"]), r.get("transferee_name") or "-", _fmt(r["transfer_value"]), _fmt(r["fee_amount"]),
                 html.Span([_badge(r["nodues_status"]), html.Span(f"  deemed {_fmt(r['deemed_on'])}" if r.get("deemed_on") and r["nodues_status"] == "pending" else "",
                                                                   style={"fontSize": "11px"})])] for r in tr]),
        html.Hr(),
        dbc.Row([
            _field("Flat", dcc.Dropdown(id="upc-tr-flat", options=flat_opts, placeholder="Select flat", style={"fontSize": "13px"}), 3),
            _field("Transfer date", _date("upc-tr-date"), 2),
            _field("Transfer value (\u20b9)", dbc.Input(id="upc-tr-value", type="number", min=0, step="0.01", style={"fontSize": "13px"}), 2),
            _field("Seller", dbc.Input(id="upc-tr-from", type="text", style={"fontSize": "13px"}), 2),
            _field("Buyer", dbc.Input(id="upc-tr-to", type="text", style={"fontSize": "13px"}), 3),
        ], className="g-2"),
        _btn("Record transfer and levy fee", "upc-tr-save", "fa-exchange-alt"),
        html.Hr(),
        dbc.Row([
            _field("Transfer", dcc.Dropdown(id="upc-nd-transfer", options=[{"label": f"{r['flat_number']} on {_fmt(r['transfer_date'])}", "value": r["id"]} for r in tr],
                                             placeholder="Select transfer", style={"fontSize": "13px"}), 4),
            _field("No Dues certificate", dcc.Dropdown(id="upc-nd-action", options=[{"label": v, "value": k} for k, v in NODUES_ACTIONS.items()],
                                                       placeholder="What happened", style={"fontSize": "13px"}), 4),
            _field("Date", _date("upc-nd-date"), 2),
        ], className="g-2"),
        _btn("Update No Dues record", "upc-nd-save", "fa-stamp"),
    ))

    # ── 4. Bye-law 7 ─────────────────────────────────────────────────────────
    secs.append(_section(
        "Who can vote or stand (bye-law 7)",
        "Owners with arrears of more than 60 days cannot vote or stand for the Board. Run this when the election notice goes out: "
        "it uses the balance outstanding today. Advocates differ on whether 'the year before' means the financial or the calendar year.",
        dbc.Row([
            _field("Election date", _date("upc-b7-date"), 3),
            _field("Year basis", dcc.Dropdown(id="upc-b7-basis", clearable=False, value="financial_year", style={"fontSize": "13px"},
                   options=[{"label": "Financial year (default)", "value": "financial_year"}, {"label": "Calendar year", "value": "calendar_year"}]), 3),
        ], className="g-2"),
        _btn("Check eligibility", "upc-b7-run", "fa-vote-yea"),
        html.Div(id="upc-b7-result", style={"marginTop": "10px"}),
    ))

    # ── 5. Section 22 ────────────────────────────────────────────────────────
    s22 = data.get("s22") or []
    secs.append(_section(
        "Cutting an essential service (section 22)",
        "Allowed only after more than 6 months' default, 7 days' notice, a general-body resolution, certified copies sent to the competent "
        "authority and the owner, a one-month wait, a displayed notice and the owner's 15-day appeal window. This tracks the steps and reports "
        "what still blocks a cut-off. It never cuts anything.",
        _table(["Flat", "Service", "Default since", "Status", "Can cut off?", "Earliest", "Still blocking"],
               [[r["flat_number"], r["service_type"], _fmt(r["default_since"]), _badge(r["status"]) if r["status"] != "in_progress" else "in progress",
                 _badge("done" if r.get("can_cut_off") else "overdue") if r["status"] == "in_progress" else "-",
                 _fmt(r.get("earliest_cutoff_date")), html.Ul([html.Li(b, style={"fontSize": "11px"}) for b in (r.get("blockers") or [])], className="mb-0")]
                for r in s22], empty="No proceedings opened."),
        html.Hr(),
        dbc.Row([
            _field("Flat", dcc.Dropdown(id="upc-s22-flat", options=flat_opts, placeholder="Select flat", style={"fontSize": "13px"}), 3),
            _field("Service", dbc.Input(id="upc-s22-service", type="text", placeholder="e.g. water supply", style={"fontSize": "13px"}), 3),
            _field("Default began", _date("upc-s22-since"), 2),
            _field("Notes", dbc.Input(id="upc-s22-notes", type="text", style={"fontSize": "13px"}), 4),
        ], className="g-2"),
        _btn("Open proceeding", "upc-s22-start", "fa-folder-open"),
        html.Hr(),
        dbc.Row([
            _field("Proceeding", dcc.Dropdown(id="upc-s22-proc", options=[{"label": f"{r['flat_number']}: {r['service_type']} (#{r['id']})", "value": r["id"]}
                                                                          for r in s22 if r["status"] == "in_progress"], placeholder="Select", style={"fontSize": "13px"}), 4),
            _field("Step", dcc.Dropdown(id="upc-s22-step", options=[{"label": v, "value": k} for k, v in S22_STEPS.items()], placeholder="Select", style={"fontSize": "13px"}), 4),
            _field("Date", _date("upc-s22-date"), 2),
        ], className="g-2"),
        _btn("Record step", "upc-s22-record", "fa-check"),
    ))

    # ── 6. Owner loans ───────────────────────────────────────────────────────
    loans = data.get("loans") or []
    secs.append(_section(
        "Loans to owners (bye-law 3(1)(f))",
        "Posted to the ledger: a loan debits Loans to Owners and credits cash or bank; a repayment credits Loans to Owners for principal and "
        "Interest on Owner Loans for interest. A resolution reference is required. Interest shown is a simple-interest estimate only.",
        _table(["Flat", "Date", "Principal", "Repaid", "Outstanding", "Rate %", "Interest est.", "Resolution", "Ledger"],
               [[r["flat_number"], _fmt(r["loan_date"]), _fmt(r["principal"]), _fmt(r["repaid_amount"]), _fmt(r["outstanding"]),
                 _fmt(r["interest_rate_pct"]), _fmt(r["interest_estimate"]), r.get("resolution_ref") or "-",
                 "posted" if r["ledger_posted"] else "register only"] for r in loans], empty="No loans recorded."),
        html.Hr(),
        dbc.Row([
            _field("Flat", dcc.Dropdown(id="upc-ln-flat", options=flat_opts, placeholder="Select flat", style={"fontSize": "13px"}), 3),
            _field("Date", _date("upc-ln-date"), 2),
            _field("Principal (\u20b9)", dbc.Input(id="upc-ln-principal", type="number", min=0, step="0.01", style={"fontSize": "13px"}), 2),
            _field("Interest % p.a.", dbc.Input(id="upc-ln-rate", type="number", min=0, step="0.01", value=0, style={"fontSize": "13px"}), 2),
            _field("Paid out by", _mode_dd("upc-ln-mode"), 3),
        ], className="g-2"),
        dbc.Row([
            _field("Resolution reference *", dbc.Input(id="upc-ln-ref", type="text", placeholder="Board / GB resolution #", style={"fontSize": "13px"}), 4),
            _field("Purpose", dbc.Input(id="upc-ln-purpose", type="text", style={"fontSize": "13px"}), 8),
        ], className="g-2 mt-1"),
        _btn("Record loan", "upc-ln-save", "fa-hand-holding-usd"),
        html.Hr(),
        dbc.Row([
            _field("Loan", dcc.Dropdown(id="upc-rp-loan", options=[{"label": f"{r['flat_number']}: \u20b9{_fmt(r['outstanding'])} outstanding (#{r['id']})", "value": r["id"]}
                                                                   for r in loans if r["ledger_posted"] and r["outstanding"] > 0], placeholder="Select loan", style={"fontSize": "13px"}), 4),
            _field("Date", _date("upc-rp-date"), 2),
            _field("Principal (\u20b9)", dbc.Input(id="upc-rp-principal", type="number", min=0, step="0.01", style={"fontSize": "13px"}), 2),
            _field("Interest (\u20b9)", dbc.Input(id="upc-rp-interest", type="number", min=0, step="0.01", value=0, style={"fontSize": "13px"}), 2),
            _field("Received by", _mode_dd("upc-rp-mode"), 2),
        ], className="g-2"),
        _btn("Record repayment", "upc-rp-save", "fa-undo"),
    ))

    # ── 7. Cash limits and flags ─────────────────────────────────────────────
    petty = data.get("petty") or {}
    flags = data.get("flags") or []
    secs.append(_section(
        "Cash and cheque limits",
        "Payments above \u20b92,500 should be by cheque or bank transfer, and petty cash should stay within \u20b920,000. Cash payments over the limit are "
        f"currently set to: {data.get('cash_mode') or 'warn'}. (Change per society with societies.cash_limit_mode = 'warn' or 'block'.)",
        html.Div([_badge("overdue" if petty.get("breach") else "done"),
                  html.Span(f"  Cash in hand {_fmt(petty.get('cash_in_hand'))} against a limit of {_fmt(petty.get('limit_amount'))}",
                            style={"fontSize": "12px", "marginLeft": "6px"})]) if petty else None,
        _table(["When", "Rule", "Detail"], [[_fmt(r["flagged_at"].date() if hasattr(r["flagged_at"], "date") else r["flagged_at"]), r["rule_code"], r["detail"]] for r in flags],
               empty="No compliance flags raised."),
    ))

    return html.Div([header, toast, html.Div(secs, id="upc-body")], style={"padding": "12px"})


def render_up_compliance_body(data: dict):
    """The sections only (what the action callbacks swap in after a successful save)."""
    card = render_up_compliance_card(data)
    return card.children[2].children if data.get("rules_on") else card.children
