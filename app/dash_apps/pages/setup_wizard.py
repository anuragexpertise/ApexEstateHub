import os
import csv
import hmac
import hashlib
from dash import html, dcc, Input, Output, State, ALL, callback, no_update
import dash_bootstrap_components as dbc
from database.db_manager import db
def load_conversation_data():
    data = []
    here = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.abspath(os.path.join(here, "../../../conversation.xlsx"))
    if os.path.exists(file_path):
        try:
            import pandas as pd
            df = pd.read_excel(file_path)
            # Replace NaNs with empty strings
            df = df.fillna('')
            data = df.to_dict('records')
        except Exception as e:
            print(f"Error loading conversation.xlsx: {e}")
    return data

CONVERSATION_DATA = load_conversation_data()
CATEGORIES = [
    "Society Details", "TDS Rates", "GST Rates", "Society Compliance",
    "Apartment Charges", "Vendor Charges", "Brought Forward", "QR Code"
]

def render_category_content(category, society_id=None):
    if category == "Society Details":
        s_name, s_addr, s_pan, s_reg = "", "", "", ""
        if society_id:
            row = db._execute("SELECT name, address, PAN_number, registration_number FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
            if row:
                s_name = row.get("name", "") or ""
                s_addr = row.get("address", "") or ""
                s_pan = row.get("pan_number", row.get("PAN_number", "")) or ""
                s_reg = row.get("registration_number", "") or ""
        return [
            html.P("Contact master administrator to update readonly fields", className="text-muted small mb-3"),
            dbc.Label("Society Name"),
            dbc.Input(id="sw-society-name", type="text", required=True, className="mb-3", value=s_name, readonly=True, style={"opacity": "0.7", "backgroundColor": "#e9ecef"}),
            dbc.Label("Address"),
            dbc.Textarea(id="sw-society-address", required=True, className="mb-3", value=s_addr, readonly=True, style={"opacity": "0.7", "backgroundColor": "#e9ecef"}),
            dbc.Label("PAN Number"),
            dbc.Input(id="sw-society-pan", type="text", required=True, className="mb-3", value=s_pan, readonly=True, style={"opacity": "0.7", "backgroundColor": "#e9ecef"}),
            dbc.Label("Registration Number"),
            dbc.Input(id="sw-society-reg", type="text", required=True, className="mb-3", value=s_reg, readonly=True, style={"opacity": "0.7", "backgroundColor": "#e9ecef"}),
        ]
    elif category == "TDS Rates":
        from database.seed import TDS_SECTION_RATE_SEED
        inputs = [
            html.P("Configure TDS Section rates. Values are pre-filled with standards.", className="text-muted mb-3")
        ]
        
        header = dbc.Row([
            dbc.Col(html.B("Section", className="small text-uppercase"), width=2),
            dbc.Col(html.B("Nature of Payment", className="small text-uppercase"), width=7),
            dbc.Col(html.B("Rate (%)", className="small text-uppercase"), width=3),
        ], className="mb-2 border-bottom pb-2")
        inputs.append(header)
        
        for idx, item in enumerate(TDS_SECTION_RATE_SEED):
            section, nature, rate = item[0], item[1], item[2]
            row = dbc.Row([
                dbc.Col(html.B(section), width=2, className="d-flex align-items-center text-primary"),
                dbc.Col(html.Span(nature, className="small text-muted"), width=7, className="d-flex align-items-center"),
                dbc.Col(dbc.Input(id={"type": "sw-tds-rate", "index": idx}, type="number", value=rate, step=0.1, bs_size="sm"), width=3),
            ], className="mb-2")
            inputs.append(row)
            
        return [html.Div(inputs, style={"maxHeight": "350px", "overflowY": "auto", "overflowX": "hidden", "paddingRight": "5px"})]
    elif category == "GST Rates":
        return [
            html.P("Configure GST Rates and Thresholds.", className="text-muted mb-3"),
            dbc.Label("CGST Rate (%)"),
            dbc.Input(id="sw-cgst", type="number", value=9.0, className="mb-3", step=0.1),
            dbc.Label("SGST Rate (%)"),
            dbc.Input(id="sw-sgst", type="number", value=9.0, className="mb-3", step=0.1),
            dbc.Label("Annual Turnover Limit for GST (Lakhs)"),
            dbc.Input(id="sw-gst-turnover", type="number", value=20.0, className="mb-3"),
            dbc.Label("Monthly Exemption Limit (₹ per member)"),
            dbc.Input(id="sw-gst-exempt", type="number", value=7500.0, className="mb-3"),
        ]
    elif category == "Society Compliance":
        from database.seed import KPI_RULE_LINKS, STATE_COMPLIANCE_THRESHOLDS
        inputs = [
            html.P("Configure State Compliance Thresholds and Reference Rule Links.", className="text-muted mb-3")
        ]
        
        # State Compliance Thresholds
        inputs.append(html.H6("State Compliance Thresholds", className="mt-4 mb-2 text-primary"))
        inputs.append(dbc.Row([
            dbc.Col(html.B("State", className="small text-uppercase"), width=1),
            dbc.Col(html.B("Compliance Key", className="small text-uppercase"), width=5),
            dbc.Col(html.B("Value", className="small text-uppercase"), width=2),
            dbc.Col(html.B("Unit", className="small text-uppercase"), width=1),
            dbc.Col(html.B("Notes", className="small text-uppercase"), width=3),
        ], className="mb-2 border-bottom pb-1"))
        
        for idx, item in enumerate(STATE_COMPLIANCE_THRESHOLDS):
            state, key, val, val_text, unit, eff_from, eff_to, notes = item
            display_val = val if val is not None else (val_text if val_text != "NULL_NO_FLOOR" else "")
            row = dbc.Row([
                dbc.Col(html.B(state), width=1, className="d-flex align-items-center"),
                dbc.Col(html.Span(key, className="small text-muted"), width=5, className="d-flex align-items-center text-break"),
                dbc.Col(dbc.Input(id={"type": "sw-compliance-val", "index": idx}, type="number" if val is not None else "text", value=display_val, bs_size="sm"), width=2),
                dbc.Col(html.Span(unit, className="small text-muted"), width=1, className="d-flex align-items-center"),
                dbc.Col(html.Span(notes[:30] + ("..." if len(notes) > 30 else ""), className="small text-muted", title=notes), width=3, className="d-flex align-items-center text-truncate"),
            ], className="mb-2")
            inputs.append(row)

        # KPI Rule Links
        inputs.append(html.H6("Reference KPI Rule Links", className="mt-4 mb-2 text-primary"))
        inputs.append(dbc.Row([
            dbc.Col(html.B("State", className="small text-uppercase"), width=1),
            dbc.Col(html.B("Category", className="small text-uppercase"), width=3),
            dbc.Col(html.B("Label", className="small text-uppercase"), width=4),
            dbc.Col(html.B("URL", className="small text-uppercase"), width=4),
        ], className="mb-2 border-bottom pb-1"))
        
        for idx, item in enumerate(KPI_RULE_LINKS):
            cat, state, label, url, desc, order = item
            row = dbc.Row([
                dbc.Col(html.B(state), width=1, className="d-flex align-items-center"),
                dbc.Col(html.Span(cat, className="small text-muted text-break"), width=3, className="d-flex align-items-center"),
                dbc.Col(dbc.Input(id={"type": "sw-kpi-label", "index": idx}, type="text", value=label, bs_size="sm", title=label), width=4),
                dbc.Col(dbc.Input(id={"type": "sw-kpi-url", "index": idx}, type="text", value=url, bs_size="sm", title=url), width=4),
            ], className="mb-2")
            inputs.append(row)
            
        return [html.Div(inputs, style={"maxHeight": "400px", "overflowY": "auto", "overflowX": "hidden", "paddingRight": "5px"})]
    elif category == "Apartment Charges":
        return [
            html.P("Configure default Apartment Charges & Fines Basis.", className="text-muted mb-3"),
            dbc.Label("Maintenance Flat Amount (₹)"),
            dbc.Input(id="sw-apt-maint-amt", type="number", value=1500.0, className="mb-3"),
            dbc.Label("Maintenance Rate (per sq.ft)"),
            dbc.Input(id="sw-apt-maint-rate", type="number", value=3.0, step=0.1, className="mb-3"),
            dbc.Label("Payment Due Day (1-31)"),
            dbc.Input(id="sw-apt-due-day", type="number", value=5, min=1, max=31, className="mb-3"),
            dbc.Label("Late Payment Interest (%) per month"),
            dbc.Input(id="sw-apt-interest", type="number", value=1.75, step=0.01, className="mb-3"),
            dbc.Label("Sinking Fund Rate"),
            dbc.Input(id="sw-apt-sinking", type="number", value=0.0, step=0.1, className="mb-3"),
            dbc.Label("Repair Fund Rate"),
            dbc.Input(id="sw-apt-repair", type="number", value=0.0, step=0.1, className="mb-3"),
        ]
    elif category == "Vendor Charges":
        return [
            html.P("Configure default Vendor Charges & Fines Basis.", className="text-muted mb-3"),
            dbc.Label("Vendor Pass (1 Day) ₹"),
            dbc.Input(id="sw-ven-1day", type="number", value=50.0, step=1, className="mb-3"),
            dbc.Label("Vendor Pass (7 Days) ₹"),
            dbc.Input(id="sw-ven-7day", type="number", value=200.0, step=1, className="mb-3"),
            dbc.Label("Vendor Pass (1 Month) ₹"),
            dbc.Input(id="sw-ven-1mth", type="number", value=500.0, step=1, className="mb-3"),
        ]
    elif category == "Brought Forward":
        return [
            html.P("Configure Opening Balances (Brought Forward).", className="text-muted mb-3"),
            dbc.Label("Financial Year (Start Year)"),
            dbc.Input(id="sw-bf-fy", type="number", value=2026, step=1, className="mb-3"),
            dbc.Label("Account ID"),
            dbc.Input(id="sw-bf-acc-id", type="number", value=1, step=1, className="mb-3"),
            dbc.Label("Type (Dr/Cr)"),
            dbc.Select(id="sw-bf-drcr", options=[
                {"label": "Debit (Dr)", "value": "Dr"},
                {"label": "Credit (Cr)", "value": "Cr"}
            ], value="Dr", className="mb-3"),
            dbc.Label("Amount (₹)"),
            dbc.Input(id="sw-bf-amount", type="number", value=0.0, step=0.01, min=0, className="mb-3"),
            dbc.Label("Remarks"),
            dbc.Input(id="sw-bf-remarks", type="text", placeholder="Opening balance...", className="mb-3"),
        ]
    elif category == "QR Code":
        return [
            html.P("Note: Administrator need to keep it secret, as it can revoke entire QR versioning.", className="text-danger fw-bold mb-3"),
            dbc.Label("QR_SIGNING_SECRET (Strong Password)"),
            dbc.Input(id="sw-qr-secret", type="password", required=True, className="mb-3"),
            dbc.Label("Confirm QR_SIGNING_SECRET"),
            dbc.Input(id="sw-qr-secret-confirm", type="password", required=True, className="mb-3"),
            html.Small("This secret will be hashed and stored in the database.", className="text-muted"),
        ]
    return []

def get_setup_wizard_layout(society_id=None):
    return dbc.Modal(
        [
            dbc.ModalHeader(
                [
                    dbc.ModalTitle("EstateHub First-Time Setup Wizard", style={"fontWeight": "bold", "color": "#fff"}),
                    html.Button(
                        html.I(className="fas fa-times"),
                        id="sw-close-btn",
                        style={"background": "none", "border": "none", "color": "#fff", "fontSize": "1.5rem", "cursor": "pointer"}
                    )
                ],
                close_button=False,
                style={"background": "linear-gradient(135deg,#667eea 0%,#764ba2 100%)", "borderBottom": "none", "display": "flex", "justifyContent": "space-between"}
            ),
            dbc.ModalBody(
                dbc.Row([
                    # Left: Categories
                    dbc.Col(
                        [
                            dbc.Nav(
                                [
                                    dbc.NavLink(
                                        cat,
                                        active=True if i == 0 else False,
                                        id={"type": "sw-nav-item", "index": i},
                                        href="#",
                                        style={"borderRadius": "8px", "marginBottom": "5px"}
                                    )
                                    for i, cat in enumerate(CATEGORIES)
                                ],
                                vertical=True,
                                pills=True,
                                id="sw-nav-menu"
                            )
                        ],
                        width=3,
                        style={"borderRight": "1px solid #e0e0e0"}
                    ),
                    # Middle: Form
                    dbc.Col(
                        [
                            html.H4(id="sw-category-title", children=CATEGORIES[0], style={"fontWeight": "bold", "marginBottom": "20px"}),
                            html.Div(id="sw-category-content", children=[
                                html.Div(
                                    render_category_content(cat, society_id),
                                    id={"type": "sw-step-container", "index": i},
                                    style={"display": "block" if i == 0 else "none"}
                                ) for i, cat in enumerate(CATEGORIES)
                            ]),
                            
                            html.Div(id="sw-error-msg", style={"color": "red", "marginTop": "15px"}),

                            html.Div(
                                [
                                    dbc.Button("Previous", id="sw-btn-prev", color="secondary", className="me-2", disabled=True),
                                    dbc.Button("Next", id="sw-btn-next", color="primary", className="me-2"),
                                    dbc.Button("Submit Setup", id="sw-btn-submit", color="success", style={"display": "none"})
                                ],
                                style={"marginTop": "30px", "textAlign": "right"}
                            )
                        ],
                        width=5,
                        style={"padding": "0 20px"}
                    ),
                    # Right: Banner Text
                    dbc.Col(
                        [
                            html.Div(
                                [
                                    html.H5([html.I(className="fas fa-info-circle me-2"), "Rules & Regulations"], style={"fontWeight": "bold", "color": "#2c3e50"}),
                                    html.Hr(),
                                    html.P(id="sw-banner-text", style={"fontSize": "14px", "color": "#4a5568", "lineHeight": "1.6"}),
                                    html.A("Learn More", id="sw-banner-link", href="#", target="_blank", className="btn btn-outline-info btn-sm mt-3")
                                ],
                                style={"background": "rgba(255,255,255,0.85)", "padding": "20px", "borderRadius": "10px", "boxShadow": "0 4px 6px rgba(0,0,0,0.1)", "height": "100%"}
                            )
                        ],
                        width=4
                    )
                ]),
                id="setup-wizard-modal-body",
                style={
                    "--login-bg": "url(/static/assets/EH_bk.jpg)",
                    "backgroundSize": "cover",
                    "backgroundPosition": "center",
                    "minHeight": "500px",
                    "padding": "30px"
                }
            ),
            dcc.Store(id="sw-current-step", data=0),
            dcc.Store(id="sw-society-id", data=society_id)
        ],
        id="setup-wizard-modal",
        is_open=True,
        size="xl",
        backdrop="static",
        keyboard=False
    )
