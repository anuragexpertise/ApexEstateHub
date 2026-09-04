import os
import csv
import hmac
import hashlib
from dash import html, dcc, Input, Output, State, ALL, callback, no_update
import dash_bootstrap_components as dbc
from utils.database import get_db_connection

def load_conversation_data():
    data = []
    file_path = os.path.join(os.path.dirname(__file__), "../../../conversation.csv")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)
    return data

CONVERSATION_DATA = load_conversation_data()
CATEGORIES = [
    "Society Details", "TDS Rates", "GST Rates", "Society Compliance",
    "Apartment Charges", "Vendor Charges", "Brought Forward", "QR Code"
]

def render_category_content(category):
    if category == "Society Details":
        return [
            dbc.Label("Society Name (Must)"),
            dbc.Input(id="sw-society-name", type="text", required=True, className="mb-3"),
            dbc.Label("Address (Must)"),
            dbc.Textarea(id="sw-society-address", required=True, className="mb-3"),
            dbc.Label("PAN Number (Must)"),
            dbc.Input(id="sw-society-pan", type="text", required=True, className="mb-3"),
            dbc.Label("Registration Number (Must)"),
            dbc.Input(id="sw-society-reg", type="text", required=True, className="mb-3"),
        ]
    elif category == "TDS Rates":
        return [
            html.P("Defaults will be filled based on seed.py (e.g. 194C, 194J).", className="text-muted"),
            dbc.Label("Default TDS Section 194C Rate (%)"),
            dbc.Input(id="sw-tds-194c", type="number", value=1.0, disabled=True, className="mb-3"),
            dbc.Label("Default TDS Section 194J Rate (%)"),
            dbc.Input(id="sw-tds-194j", type="number", value=10.0, disabled=True, className="mb-3"),
        ]
    elif category == "GST Rates":
        return [
            html.P("Defaults will be filled based on seed.py.", className="text-muted"),
            dbc.Label("CGST Rate (%)"),
            dbc.Input(id="sw-cgst", type="number", value=9.0, disabled=True, className="mb-3"),
            dbc.Label("SGST Rate (%)"),
            dbc.Input(id="sw-sgst", type="number", value=9.0, disabled=True, className="mb-3"),
        ]
    elif category == "Society Compliance":
        return [
            html.P("Defaults will be filled based on seed.py.", className="text-muted"),
            dbc.Label("Sinking Fund Rate Basis"),
            dbc.Input(value="per_sq_ft", disabled=True, className="mb-3"),
            dbc.Label("GST Filing Cadence"),
            dbc.Input(value="monthly", disabled=True, className="mb-3"),
        ]
    elif category == "Apartment Charges":
        return [
            html.P("Defaults will be filled.", className="text-muted"),
            dbc.Label("Base Maintenance Rate (per sq ft)"),
            dbc.Input(value=3.0, type="number", disabled=True, className="mb-3"),
            dbc.Label("Interest Pct"),
            dbc.Input(value=1.75, type="number", disabled=True, className="mb-3"),
        ]
    elif category == "Vendor Charges":
        return [
            html.P("Defaults will be filled.", className="text-muted"),
            dbc.Label("1-Day Pass Charge"),
            dbc.Input(value=0, type="number", disabled=True, className="mb-3"),
        ]
    elif category == "Brought Forward":
        return [
            html.P("Opening Balances must be 0.", className="text-muted"),
            dbc.Label("Dr Balance"),
            dbc.Input(value=0, type="number", disabled=True, className="mb-3"),
            dbc.Label("Cr Balance"),
            dbc.Input(value=0, type="number", disabled=True, className="mb-3"),
        ]
    elif category == "QR Code":
        return [
            dbc.Label("QR Signing Secret (Must)"),
            dbc.Input(id="sw-qr-secret", type="password", required=True, className="mb-3"),
            html.Small("This secret will be hashed and stored in the database.", className="text-muted"),
        ]
    return []

def get_setup_wizard_layout():
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("EstateHub First-Time Setup Wizard", style={"fontWeight": "bold", "color": "#fff"}),
                style={"background": "linear-gradient(135deg,#667eea 0%,#764ba2 100%)", "borderBottom": "none"}
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
                            html.Div(id="sw-category-content", children=render_category_content(CATEGORIES[0])),
                            
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
                                    html.H5(html.I(className="fas fa-info-circle me-2") + " Rules & Regulations", style={"fontWeight": "bold", "color": "#2c3e50"}),
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
                style={
                    "background": "url(/static/assets/EH_bk.jpg) center/cover no-repeat",
                    "minHeight": "500px",
                    "padding": "30px"
                }
            ),
            dcc.Store(id="sw-current-step", data=0)
        ],
        id="setup-wizard-modal",
        is_open=True,
        size="xl",
        backdrop="static",
        keyboard=False
    )
