import os
import csv
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
    "Society Details", "Society Compliance", "TAN & TDS Rates", "GSTIN & GST Rate",
    "Apartment Charges", "Vendor Charges", "Accounts", "Brought Forward", "Administrator", "Agreement"
]

def render_category_content(category, society_id=None):
    if category == "Society Details":
        s_name, s_addr, s_pan, s_reg, s_phone = "", "", "", "", ""
        if society_id:
            row = db._execute("SELECT name, address, phone, PAN_number, registration_number FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
            if row:
                s_name = row.get("name", "") or ""
                s_addr = row.get("address", "") or ""
                s_phone = row.get("phone", "") or ""
                s_pan = row.get("pan_number", row.get("PAN_number", "")) or ""
                s_reg = row.get("registration_number", "") or ""
        return [
            html.P("Enter society details. Logo and Background images are optional.", className="text-muted small mb-3"),
            dbc.Label("Society Name"),
            dbc.Input(id="sw-society-name", type="text", required=True, className="mb-3", value=s_name, readonly=True, style={"opacity": "0.7", "backgroundColor": "#e9ecef"}),
            dbc.Label("Society Logo (Image)"),
            dcc.Upload(id="sw-logo-upload", children=html.Div(["Drag and Drop or ", html.A("Select Files")]), style={"border": "1px dashed #ced4da", "borderRadius": "5px", "textAlign": "center", "padding": "10px", "marginBottom": "15px"}, multiple=False),
            dbc.Label("Address"),
            dbc.Textarea(id="sw-society-address", required=True, className="mb-3", value=s_addr),
            dbc.Label("Phone Number"),
            dbc.Input(id="sw-society-phone", type="tel", required=True, className="mb-3", value=s_phone),
            dbc.Label("PAN Number"),
            dbc.Input(id="sw-society-pan", type="text", required=True, className="mb-3", value=s_pan, readonly=True, style={"opacity": "0.7", "backgroundColor": "#e9ecef"}),
            dbc.Label("Registration Number"),
            dbc.Input(id="sw-society-reg", type="text", required=True, className="mb-3", value=s_reg, readonly=True, style={"opacity": "0.7", "backgroundColor": "#e9ecef"}),
            dbc.Label("Login Background (Image)"),
            dcc.Upload(id="sw-bg-upload", children=html.Div(["Drag and Drop or ", html.A("Select Files")]), style={"border": "1px dashed #ced4da", "borderRadius": "5px", "textAlign": "center", "padding": "10px", "marginBottom": "15px"}, multiple=False),
        ]
    elif category == "TAN & TDS Rates":
        from database.seed import TDS_SECTION_RATE_SEED
        inputs = [
            html.P("Configure TAN and TDS Section rates. Values are pre-filled with standards.", className="text-muted mb-3"),
            dbc.Label("TAN Number"),
            dbc.Input(id="sw-society-tan", type="text", placeholder="Enter TAN...", className="mb-4"),
            html.Hr(),
            html.H6("TDS Rates", className="text-primary mb-3")
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
                dbc.Col(dbc.Input(id={"type": "sw-tds-rate", "index": idx}, type="number", value=rate, step=0.1, size="sm"), width=3),
            ], className="mb-2")
            inputs.append(row)
            
        return [html.Div(inputs, style={"maxHeight": "350px", "overflowY": "auto", "overflowX": "hidden", "paddingRight": "5px"})]
    elif category == "GSTIN & GST Rate":
        # Turnover/exemption limits are statutory constants (state_compliance_
        # thresholds), not per-society settings — same no-state-filter LIMIT 1
        # lookup fn_auto_generate_receivables already uses in production, so
        # this display matches what actually governs GST auto-generation.
        # Shown read-only: earlier this screen let each society's admin
        # "edit" these values in the form, but nothing ever wrote them
        # anywhere, and if it had, writing them here would have overwritten
        # the same statutory row for every OTHER society too.
        turnover_row = db._execute(
            "SELECT value FROM state_compliance_thresholds "
            "WHERE threshold_key = 'gst_turnover_lakh' AND is_active = TRUE LIMIT 1",
            fetch_one=True,
        )
        exempt_row = db._execute(
            "SELECT value FROM state_compliance_thresholds "
            "WHERE threshold_key = 'gst_per_member_monthly' AND is_active = TRUE LIMIT 1",
            fetch_one=True,
        )
        turnover_val = (turnover_row or {}).get("value", 20.0)
        exempt_val = (exempt_row or {}).get("value", 7500.0)
        readonly_style = {"opacity": "0.7", "backgroundColor": "#e9ecef"}
        return [
            html.P("Configure this society's GSTIN and GST rates. Turnover/exemption limits below are statutory constants maintained by Master, not editable per-society.", className="text-muted mb-3"),
            dbc.Label("GSTIN"),
            dbc.Input(id="sw-society-gstin", type="text", placeholder="Enter GSTIN...", className="mb-4"),
            html.Hr(),
            html.H6("GST Rates", className="text-primary mb-3"),
            dbc.Label("CGST Rate (%)"),
            dbc.Input(id="sw-cgst", type="number", value=9.0, className="mb-3", step=0.1),
            dbc.Label("SGST Rate (%)"),
            dbc.Input(id="sw-sgst", type="number", value=9.0, className="mb-3", step=0.1),
            dbc.Label("Annual Turnover Limit for GST (Lakhs)"),
            dbc.Input(type="number", value=turnover_val, className="mb-3", readonly=True, style=readonly_style),
            dbc.Label("Monthly Exemption Limit (₹ per member)"),
            dbc.Input(type="number", value=exempt_val, className="mb-3", readonly=True, style=readonly_style),
        ]
    elif category == "Society Compliance":
        # Read-only reference display. Both tables below are GLOBAL (shared
        # across every society in that state / nationwide) — they used to
        # render as editable dbc.Input fields, but nothing ever persisted
        # the edits, and had it been wired up it would have let one
        # society's admin silently rewrite statutory thresholds and rule
        # links for every other tenant in that state. Kept informational.
        from database.seed import KPI_RULE_LINKS, STATE_COMPLIANCE_THRESHOLDS
        inputs = [
            html.P("State Compliance Thresholds and Reference Rule Links (statutory reference values, maintained by Master — shown here for information only).", className="text-muted mb-3")
        ]
        
        # State Compliance Thresholds
        inputs.append(html.H6("State Compliance Thresholds", className="mt-4 mb-2 text-primary"))
        inputs.append(dbc.Row([
            dbc.Col(html.B("State", className="small text-uppercase"), width=1),
            dbc.Col(html.B("Compliance Key", className="small text-uppercase"), width=3),
            dbc.Col(html.B("Value", className="small text-uppercase"), width=2),
            dbc.Col(html.B("Unit", className="small text-uppercase"), width=1),
            dbc.Col(html.B("Notes", className="small text-uppercase"), width=5),
        ], className="mb-2 border-bottom pb-1"))
        
        for idx, item in enumerate(STATE_COMPLIANCE_THRESHOLDS):
            state, key, val, val_text, unit, eff_from, eff_to, notes = item
            display_val = val if val is not None else (val_text if val_text != "NULL_NO_FLOOR" else "")
            row = dbc.Row([
                dbc.Col(html.B(state), width=1, className="d-flex align-items-center"),
                dbc.Col(html.Span(key, className="small text-muted"), width=3, className="d-flex align-items-center text-break"),
                dbc.Col(html.Span(display_val, className="small fw-bold"), width=2, className="d-flex align-items-center"),
                dbc.Col(html.Span(unit, className="small text-muted"), width=1, className="d-flex align-items-center"),
                dbc.Col(html.Span(notes, className="small text-muted"), width=5, className="d-flex align-items-center"),
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
                dbc.Col(html.Span(label, className="small text-truncate d-block", title=label), width=4),
                dbc.Col(html.A(url, href=url, target="_blank", className="small text-truncate d-block", title=url), width=4),
            ], className="mb-2")
            inputs.append(row)
            
        return [html.Div(inputs, style={"maxHeight": "400px", "overflow": "auto", "paddingRight": "5px"})]
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
    elif category == "Accounts":
        from database.seed import ACCOUNTS
        inputs = [
            html.P("Configure general account parameters and view default accounts.", className="text-muted mb-3"),
            dbc.Label("Payment QR (Image)"),
            dcc.Upload(id="sw-payment-qr", children=html.Div(["Drag and Drop or ", html.A("Select Files")]), style={"border": "1px dashed #ced4da", "borderRadius": "5px", "textAlign": "center", "padding": "10px", "marginBottom": "15px"}, multiple=False),
            dbc.Label("Calculation Start Date"),
            dcc.DatePickerSingle(id="sw-calc-start-date", date="2024-04-01", display_format='YYYY-MM-DD', className="mb-4 d-block"),
            html.Hr(),
            html.H6("All Accounts (Seeded)", className="text-primary mb-3"),
        ]
        header = dbc.Row([
            dbc.Col(html.B("ID", className="small text-uppercase"), width=1),
            dbc.Col(html.B("Tab", className="small text-uppercase"), width=2),
            dbc.Col(html.B("Name", className="small text-uppercase"), width=4),
            dbc.Col(html.B("Dr/Cr BF", className="small text-uppercase"), width=1),
            dbc.Col(html.B("Dr/Cr Type", className="small text-uppercase"), width=2),
            dbc.Col(html.B("Group", className="small text-uppercase"), width=2),
        ], className="mb-2 border-bottom pb-1")
        inputs.append(header)

        for acc in ACCOUNTS:
            row = dbc.Row([
                dbc.Col(html.Span(str(acc[0]), className="small text-muted"), width=1, className="d-flex align-items-center"),
                dbc.Col(html.Span(acc[1], className="small text-muted text-break"), width=2, className="d-flex align-items-center"),
                dbc.Col(html.Span(acc[2], className="small fw-bold"), width=4, className="d-flex align-items-center"),
                dbc.Col(html.Span(str(acc[3]), className="small text-muted"), width=1, className="d-flex align-items-center"),
                dbc.Col(html.Span(str(acc[4]), className="small text-muted"), width=2, className="d-flex align-items-center"),
                dbc.Col(html.Span(str(acc[5]), className="small text-muted text-break"), width=2, className="d-flex align-items-center"),
            ], className="mb-2")
            inputs.append(row)
        return [html.Div(inputs, style={"maxHeight": "450px", "overflow": "auto", "paddingRight": "5px"})]
    elif category == "Brought Forward":
        accounts = []
        if society_id:
            accounts = db._execute(
                "SELECT id, tab_name, name, drcr_bf FROM accounts WHERE society_id = :sid AND has_bf = TRUE ORDER BY id",
                {"sid": society_id}, fetch_all=True
            ) or []
            
        inputs = [
            html.P("Configure Opening Balances (Brought Forward).", className="text-muted mb-3"),
            dbc.Label("Financial Year (Start Year)"),
            dbc.Input(id="sw-bf-fy", type="number", value=2026, step=1, className="mb-3"),
            html.H6("Brought Forward Accounts", className="mt-4 mb-2 text-primary"),
        ]
        
        header = dbc.Row([
            dbc.Col(html.B("ID", className="small text-uppercase"), width=1),
            dbc.Col(html.B("Tab", className="small text-uppercase"), width=2),
            dbc.Col(html.B("Name", className="small text-uppercase"), width=4),
            dbc.Col(html.B("Dr/Cr", className="small text-uppercase"), width=1),
            dbc.Col(html.B("Amount (₹)", className="small text-uppercase"), width=2),
            dbc.Col(html.B("Remarks", className="small text-uppercase"), width=2),
        ], className="mb-2 border-bottom pb-1")
        inputs.append(header)
        
        for acc in accounts:
            row = dbc.Row([
                dbc.Col(html.Span(str(acc["id"]), className="small text-muted"), width=1, className="d-flex align-items-center"),
                dbc.Col(html.Span(acc["tab_name"] or "", className="small text-muted text-break"), width=2, className="d-flex align-items-center"),
                dbc.Col(html.Span(acc["name"] or "", className="small fw-bold"), width=4, className="d-flex align-items-center"),
                dbc.Col(html.Span(acc["drcr_bf"] or "", className="small text-muted"), width=1, className="d-flex align-items-center"),
                dbc.Col(dbc.Input(id={"type": "sw-bf-amt", "acc_id": acc["id"]}, type="number", value=0.0, step=0.01, min=0, size="sm"), width=2),
                dbc.Col(dbc.Input(id={"type": "sw-bf-remarks", "acc_id": acc["id"]}, type="text", placeholder="Remarks...", size="sm"), width=2),
            ], className="mb-2")
            inputs.append(row)
            
        return [html.Div(inputs, style={"maxHeight": "450px", "overflow": "auto", "paddingRight": "5px"})]
    elif category == "Administrator":
        sec_name, sec_phone = "", ""
        if society_id:
            row = db._execute("SELECT secretary_name, secretary_phone FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
            if row:
                sec_name = row.get("secretary_name", "") or ""
                sec_phone = row.get("secretary_phone", "") or ""
        return [
            html.P("Configure Administrator (Secretary) details.", className="text-muted mb-3"),
            dbc.Label("Secretary Name"),
            dbc.Input(id="sw-sec-name", type="text", value=sec_name, className="mb-3"),
            dbc.Label("Secretary Phone"),
            dbc.Input(id="sw-sec-phone", type="tel", value=sec_phone, className="mb-3"),
            dbc.Label("Secretary Signature (Image)"),
            dcc.Upload(id="sw-sec-sign", children=html.Div(["Drag and Drop or ", html.A("Select Files")]), style={"border": "1px dashed #ced4da", "borderRadius": "5px", "textAlign": "center", "padding": "10px", "marginBottom": "15px"}, multiple=False),
            html.Hr(),
            html.P("Create a Setup Confirmation Password to secure this onboarding.", className="text-danger fw-bold mb-3"),
            dbc.Label("Setup Confirmation Password (Strong Password)"),
            dbc.Input(id="sw-qr-secret", type="password", required=True, className="mb-3"),
            dbc.Label("Confirm Password"),
            dbc.Input(id="sw-qr-secret-confirm", type="password", required=True, className="mb-3"),
            html.Small("This password is hashed and stored to mark setup as complete.", className="text-muted")
        ]
    elif category == "Agreement":
        here = os.path.dirname(os.path.abspath(__file__))
        readme_path = os.path.abspath(os.path.join(here, "../../../README.md"))
        agreement_path = os.path.abspath(os.path.join(here, "../../../database/AGREEMENT.md"))
        
        readme_txt = ""
        agreement_txt = ""
        if os.path.exists(readme_path):
            with open(readme_path, 'r') as f:
                readme_txt = f.read()
        if os.path.exists(agreement_path):
            with open(agreement_path, 'r') as f:
                agreement_txt = f.read()

        return [
            html.H5("EstateHub terms and agreements", className="text-primary mb-3"),
            html.Div(
                [
                    dcc.Markdown(readme_txt),
                    html.Hr(),
                    dcc.Markdown(agreement_txt)
                ],
                style={"height": "300px", "overflowY": "auto", "backgroundColor": "#f8f9fa", "padding": "15px", "borderRadius": "5px", "border": "1px solid #ced4da", "marginBottom": "20px"}
            ),
            dbc.Label("Type 'I AGREE' below to proceed"),
            dbc.Input(id="sw-i-agree", type="text", placeholder="I AGREE", className="mb-4"),
            html.Hr(),
            html.P("Authorization required to submit setup.", className="fw-bold"),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Admin Password"),
                    dbc.Input(id="sw-admin-password", type="password", placeholder="Your login password...", className="mb-3")
                ], width=6),
                dbc.Col([
                    dbc.Label("Setup Confirmation Password"),
                    dbc.Input(id="sw-qr-confirm-final", type="password", placeholder="Enter the password created in Administrator tab...", className="mb-3")
                ], width=6)
            ])
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
                    # Right: Rules (Above) and Content (Below)
                    dbc.Col(
                        [
                            # Rules (Above)
                            html.Div(
                                [
                                    html.H5([html.I(className="fas fa-info-circle me-2"), "Rules & Regulations"], style={"fontWeight": "bold", "color": "#2c3e50"}),
                                    html.Hr(style={"margin": "10px 0"}),
                                    html.P(id="sw-banner-text", style={"fontSize": "14px", "color": "#4a5568", "lineHeight": "1.6", "marginBottom": "10px"}),
                                    html.A("Learn More", id="sw-banner-link", href="#", target="_blank", className="btn btn-outline-info btn-sm")
                                ],
                                style={"background": "rgba(255,255,255,0.85)", "padding": "15px", "borderRadius": "10px", "boxShadow": "0 2px 4px rgba(0,0,0,0.1)", "marginBottom": "20px"}
                            ),
                            
                            # Content (Below)
                            html.H4(id="sw-category-title", children=CATEGORIES[0], style={"fontWeight": "bold", "marginBottom": "20px"}),
                            html.Div(id="sw-category-content", style={"overflow": "auto", "maxHeight": "500px", "paddingRight": "10px"}, children=[
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
                        width=9,
                        style={"padding": "0 20px"}
                    )
                ]),
                id="setup-wizard-modal-body",
                style={
                    "--login-bg": "url(/static/assets/EH_bk.jpg)",
                    "backgroundSize": "cover",
                    "backgroundPosition": "center",
                    "minHeight": "650px",
                    "padding": "30px"
                }
            ),
            dcc.Store(id="sw-current-step", data=0),
            dcc.Store(id="sw-society-id", data=society_id)
        ],
        id="setup-wizard-modal",
        is_open=True,
        size="xl",
        fullscreen=True,
        centered=True,
        backdrop="static",
        keyboard=False
    )
