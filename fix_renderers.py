import re

with open("app/dash_apps/drilldown/renderers.py", "r") as f:
    content = f.read()

# We'll just replace the entire `render_pay_dues_card` function
start_pattern = r'def render_pay_dues_card\('
end_pattern = r'# ════════════════════════════════════════════════════════════════════════════\n# VENDOR PASS CARD'

start_idx = re.search(start_pattern, content).start()
end_idx = re.search(end_pattern, content).start()

new_func = """def render_pay_dues_card(
    entity_id,
    flat_number: str,
    owner_name: str,
    pending_dues: float,
    overdue_dues: float,
    prefill_amount: float,
    prefill_mode: str = "cash",
    prefill_particulars: str = "",
    society_id=None,
    bill_groups=None,
) -> html.Div:
    if bill_groups is None: bill_groups = []
    color = "#17976e"
    overdue_color = "#de5c52" if overdue_dues > 0 else "#17976e"

    dues_summary = dbc.Row([
        dbc.Col(dbc.Card([
            html.Div("Pending Dues", style={"fontSize": "10px", "color": "#7d8ea3",
                                            "fontWeight": "600", "textTransform": "uppercase"}),
            html.Div(f"₹{pending_dues:,.2f}", style={"fontSize": "20px", "fontWeight": "800",
                                                      "color": "#15304f"}),
        ], body=True, style={"borderRadius": "10px", "border": "1px solid #e8edf5",
                              "textAlign": "center", "padding": "10px"}), width=6),
        dbc.Col(dbc.Card([
            html.Div("Overdue Dues", style={"fontSize": "10px", "color": "#7d8ea3",
                                            "fontWeight": "600", "textTransform": "uppercase"}),
            html.Div(f"₹{overdue_dues:,.2f}", style={"fontSize": "20px", "fontWeight": "800",
                                                       "color": overdue_color}),
        ], body=True, style={"borderRadius": "10px", "border": f"1px solid {overdue_color}33",
                              "textAlign": "center", "padding": "10px"}), width=6),
    ], className="mb-3")

    fifo_tab = dbc.Tab(label="FIFO Pay", tab_id="fifo", children=[
        html.Div([
            dues_summary,
            dbc.Alert([
                html.I(className="fas fa-info-circle me-2"),
                f"Payment applied FIFO — oldest dues first. "
                f"Excess beyond ₹{pending_dues:,.2f} credited as advance.",
            ], color="info", style={"fontSize": "12px", "padding": "8px 14px",
                                    "borderRadius": "10px", "marginBottom": "12px"}),
            # Hidden fields
            dcc.Input(id={"type": "form-field", "entity": "pay_due", "field": "entity_id"},
                      type="hidden", value=str(entity_id or "")),
            dcc.Input(id={"type": "form-field", "entity": "pay_due", "field": "role"},
                      type="hidden", value="apartment"),
            dcc.Input(id={"type": "form-entity-pk", "entity": "pay_due"},
                      type="hidden", value=str(entity_id or "")),
            # Amount
            dbc.Row([
                dbc.Col(dbc.Label("Amount (₹) *", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4, style={"paddingTop": "6px"}),
                dbc.Col(dbc.Input(
                    id={"type": "form-field", "entity": "pay_due", "field": "amount"},
                    type="number", value=str(prefill_amount) if prefill_amount else "",
                    min=1, step=0.01, style={"fontSize": "13px", "borderRadius": "10px"},
                ), width=8),
            ], className="mb-2"),
            # Mode
            dbc.Row([
                dbc.Col(dbc.Label("Payment Mode *", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4, style={"paddingTop": "6px"}),
                dbc.Col(dcc.Dropdown(
                    id={"type": "form-field", "entity": "pay_due", "field": "mode"},
                    options=[
                        {"label": "Cash",          "value": "cash"},
                        {"label": "Bank Transfer", "value": "bank_transfer"},
                        {"label": "UPI",           "value": "upi"},
                        {"label": "Cheque",        "value": "cheque"},
                        {"label": "Other",         "value": "other"},
                    ],
                    value=prefill_mode, clearable=False, style={"fontSize": "13px"},
                ), width=8),
            ], className="mb-2"),
            # Particulars
            dbc.Row([
                dbc.Col(dbc.Label("Particulars *", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4, style={"paddingTop": "6px"}),
                dbc.Col(dbc.Textarea(
                    id={"type": "form-field", "entity": "pay_due", "field": "particulars"},
                    value=prefill_particulars, rows=2, style={"fontSize": "13px", "borderRadius": "10px"},
                ), width=8),
            ], className="mb-2"),
            dbc.Button(
                [html.I(className="fas fa-check me-2"), "Apply Payment (FIFO)"],
                id={"type": "form-submit", "entity": "pay_due", "card_id": "form_pay_dues_new"},
                n_clicks=0, color="success", className="mt-3 w-100",
                style={"borderRadius": "12px", "fontWeight": "700"},
            ),
        ], style={"paddingTop": "15px"})
    ])

    bg_options = []
    for bg in bill_groups:
        lbl = f"{bg['period_month']} — {bg['desc']} (₹{bg['amount']:,.2f})"
        bg_options.append({"label": lbl, "value": bg['bill_group_id']})

    bill_group_tab = dbc.Tab(label="Bill Group Pay", tab_id="bill_group", children=[
        html.Div([
            dbc.Row([
                dbc.Col(dbc.Label("Select Bill", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4),
                dbc.Col(dcc.Dropdown(
                    id={"type": "form-field", "entity": "pay_due_bg", "field": "bill_group_id"},
                    options=bg_options, placeholder="Select a bill...", style={"fontSize": "13px"}
                ), width=8)
            ], className="mb-2"),
            dbc.Row([
                dbc.Col(dbc.Label("Amount (₹) *", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4),
                dbc.Col(dbc.Input(
                    id={"type": "form-field", "entity": "pay_due_bg", "field": "amount"},
                    type="number", min=1, step=0.01, style={"fontSize": "13px", "borderRadius": "10px"},
                ), width=8)
            ], className="mb-2"),
            dbc.Row([
                dbc.Col(dbc.Label("Mode *", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4),
                dbc.Col(dcc.Dropdown(
                    id={"type": "form-field", "entity": "pay_due_bg", "field": "mode"},
                    options=[
                        {"label": "Cash",          "value": "cash"},
                        {"label": "Bank Transfer", "value": "bank_transfer"},
                        {"label": "UPI",           "value": "upi"},
                        {"label": "Cheque",        "value": "cheque"},
                        {"label": "Other",         "value": "other"},
                    ], value=prefill_mode, clearable=False, style={"fontSize": "13px"},
                ), width=8),
            ], className="mb-2"),
            dbc.Row([
                dbc.Col(dbc.Label("Reference", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4),
                dbc.Col(dbc.Input(
                    id={"type": "form-field", "entity": "pay_due_bg", "field": "reference"},
                    type="text", style={"fontSize": "13px", "borderRadius": "10px"},
                ), width=8)
            ], className="mb-2"),
            
            dcc.Input(id={"type": "form-field", "entity": "pay_due_bg", "field": "role"}, type="hidden", value="apartment"),
            dcc.Input(id={"type": "form-field", "entity": "pay_due_bg", "field": "entity_id"}, type="hidden", value=str(entity_id or "")),
            
            dbc.Button(
                [html.I(className="fas fa-check me-2"), "Report Payment (Bill Group)"],
                id={"type": "form-submit", "entity": "pay_due_bg", "card_id": "form_pay_dues_new"},
                n_clicks=0, color="success", className="mt-3 w-100",
                style={"borderRadius": "12px", "fontWeight": "700"},
            ),
        ], style={"paddingTop": "15px"})
    ])

    return html.Div([
        html.Div(
            html.Div([
                html.Div(html.I(className="fas fa-rupee-sign", style={"color": "#fff", "fontSize": "16px"}),
                         style={"width": "38px", "height": "38px", "borderRadius": "10px",
                                "background": f"linear-gradient(135deg,{color},{color}aa)",
                                "display": "flex", "alignItems": "center",
                                "justifyContent": "center", "marginRight": "12px"}),
                html.Div([
                    html.Strong("Pay Dues", style={"fontSize": "14px"}),
                    html.Div(f"Flat {flat_number}" + (f" — {owner_name}" if owner_name else ""),
                             style={"fontSize": "11px", "color": "#999"}),
                ]),
            ], style={"display": "flex", "alignItems": "center"}),
            style={"padding": "12px 16px", "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"},
        ),
        html.Div([
            html.Div([
                dbc.Tabs([fifo_tab, bill_group_tab], active_tab="fifo", style={"borderBottom": f"2px solid {color}33"}),
            ], style={"flex": "1", "minWidth": "260px"}),
            render_payment_qr_widget(society_id),
        ], style={"padding": "16px", "display": "flex", "flexWrap": "wrap", "gap": "16px", "alignItems": "flex-start"}),
    ], style={"borderRadius": "16px", "border": f"1px solid {color}22", "boxShadow": f"0 10px 30px {color}18", "overflow": "hidden"})

\n\n"""

with open("app/dash_apps/drilldown/renderers.py", "w") as f:
    f.write(content[:start_idx] + new_func + content[end_idx:])

print("Fixed render_pay_dues_card")
