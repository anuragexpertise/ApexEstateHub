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
WIZARD_GROUPS = {
    "Organization Details": ["Society Details", "Administrator", "Instructions"],
    "Tax & Compliance": ["Society Compliance", "TAN & TDS Rates", "GSTIN & GST Rate"],
    "Billing & Accounts": ["Apartment Charges", "Vendor Charges", "Accounts", "Brought Forward"],
    "Finalization": ["Agreement"]
}
CATEGORIES = [step for group in WIZARD_GROUPS.values() for step in group]

CATEGORY_ICONS = {
    "Society Details": "fas fa-building",
    "Administrator": "fas fa-user-shield",
    "Instructions": "fas fa-info-circle",
    "Society Compliance": "fas fa-gavel",
    "TAN & TDS Rates": "fas fa-percent",
    "GSTIN & GST Rate": "fas fa-file-invoice-dollar",
    "Apartment Charges": "fas fa-home",
    "Vendor Charges": "fas fa-truck",
    "Accounts": "fas fa-book",
    "Brought Forward": "fas fa-arrow-right",
    "Agreement": "fas fa-handshake"
}

def _render_banner(title, text):
    return dbc.Card([
        dbc.CardBody([
            html.H6([html.I(className="fas fa-info-circle me-2"), title], className="text-primary mb-2"),
            html.P(text, className="small text-muted mb-0")
        ], className="p-3")
    ], className="mb-4 shadow-sm border-0 bg-light")

def render_category_content(category, society_id=None):
    elements = []
    
    # Render conversational header if available
    conv_info = next((item for item in CONVERSATION_DATA if item.get('Category') == category), None)
    if conv_info and conv_info.get('Information'):
        elements.append(
            dbc.Alert(
                [html.I(className="fas fa-lightbulb me-2"), conv_info['Information']],
                color="info",
                className="mb-3",
                style={"fontSize": "13px"}
            )
        )
        
    # Add Print Button for specific categories
    if category in ["Society Compliance", "TAN & TDS Rates", "Accounts"]:
        elements.append(
            html.Div([
                dbc.Button([html.I(className="fas fa-print me-2"), "Print / Open in New Window"], 
                           id={"type": "sw-print-btn", "cat": category}, 
                           color="outline-secondary", size="sm")
            ], style={"textAlign": "right", "marginBottom": "15px"})
        )

    if category == "Society Details":
        s_name, s_addr, s_pan, s_reg, s_phone, s_email = "", "", "", "", "", ""
        if society_id:
            row = db._execute("SELECT name, address, phone, email, PAN_number, registration_number FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
            if row:
                s_name = row.get("name", "") or ""
                s_addr = row.get("address", "") or ""
                s_phone = row.get("phone", "") or ""
                s_email = row.get("email", "") or ""
                s_pan = row.get("pan_number", row.get("PAN_number", "")) or ""
                s_reg = row.get("registration_number", "") or ""
        return elements + [
            _render_banner("Society Details", "Enter society details. Registration Number, Email, and Phone will be updated if provided. Logo and Background images are optional."),
            dbc.Label("Society Name"),
            dbc.Input(id="sw-society-name", type="text", required=True, className="mb-3", value=s_name, readonly=True, style={"opacity": "0.7", "backgroundColor": "#e9ecef"}),
            dbc.Label("Society Logo (Image)"),
            html.Div([
                html.Div([
                    dcc.Upload(
                        id={"type": "form-upload", "entity": "society", "field": "logo"},
                        children=html.Div([
                            html.I(className="fas fa-cloud-upload-alt me-1"),
                            "Upload / Drop",
                        ], style={"fontSize": "12px"}),
                        style={
                            "flex":         "1",
                            "height":       "42px",
                            "lineHeight":   "42px",
                            "borderWidth":  "2px",
                            "borderStyle":  "dashed",
                            "borderRadius": "10px",
                            "textAlign":    "center",
                            "borderColor":  "#667eea",
                            "background":   "rgba(102,126,234,0.04)",
                            "cursor":       "pointer",
                            "color":        "#667eea",
                            "minWidth":     "110px",
                        },
                        multiple=False, accept="image/*",
                    ),
                    html.Button([
                        html.I(className="fas fa-camera me-1"),
                        "Snap"
                    ], id={"type": "camera-snap-btn", "entity": "society", "field": "logo"},
                       style={
                        "display":       "inline-flex",
                        "alignItems":    "center",
                        "justifyContent":"center",
                        "cursor":        "pointer",
                        "userSelect":    "none",
                        "borderRadius":  "8px",
                        "fontSize":      "12px",
                        "fontWeight":    "600",
                        "padding":       "6px 14px",
                        "border":        "none",
                        "background":    "#17976e",
                        "color":         "white",
                        "height":        "42px",
                       })
                ], style={"display": "flex", "gap": "10px", "marginBottom": "5px"}),
                html.Div(id={"type": "image-preview", "entity": "society", "field": "logo"}, style={"marginTop": "5px", "marginBottom": "15px"}),
                dcc.Input(id={"type": "form-field-hidden", "entity": "society", "field": "logo"}, type="hidden"),
                dcc.Input(id={"type": "form-entity-pk", "entity": "society"}, type="hidden", value=""),
            ]),
            dbc.Label("Address"),
            dbc.Textarea(id="sw-society-address", required=True, className="mb-3", value=s_addr),
            dbc.Label("Email"),
            dbc.Input(id="sw-society-email", type="email", required=True, className="mb-3", value=s_email),
            dbc.Label("Phone Number"),
            dbc.Input(id="sw-society-phone", type="tel", required=True, className="mb-3", value=s_phone),
            dbc.Label("PAN Number"),
            dbc.Input(id="sw-society-pan", type="text", required=True, className="mb-3", value=s_pan, readonly=True, style={"opacity": "0.7", "backgroundColor": "#e9ecef"}),
            dbc.Label("Registration Number"),
            dbc.Input(id="sw-society-reg", type="text", required=True, className="mb-3", value=s_reg),
            dbc.Label("Login Background (Image)"),
            html.Div([
                html.Div([
                    dcc.Upload(
                        id={"type": "form-upload", "entity": "society", "field": "bg"},
                        children=html.Div([
                            html.I(className="fas fa-cloud-upload-alt me-1"),
                            "Upload / Drop",
                        ], style={"fontSize": "12px"}),
                        style={
                            "flex":         "1",
                            "height":       "42px",
                            "lineHeight":   "42px",
                            "borderWidth":  "2px",
                            "borderStyle":  "dashed",
                            "borderRadius": "10px",
                            "textAlign":    "center",
                            "borderColor":  "#667eea",
                            "background":   "rgba(102,126,234,0.04)",
                            "cursor":       "pointer",
                            "color":        "#667eea",
                            "minWidth":     "110px",
                        },
                        multiple=False, accept="image/*",
                    ),
                    html.Button([
                        html.I(className="fas fa-camera me-1"),
                        "Snap"
                    ], id={"type": "camera-snap-btn", "entity": "society", "field": "bg"},
                       style={
                        "display":       "inline-flex",
                        "alignItems":    "center",
                        "justifyContent":"center",
                        "cursor":        "pointer",
                        "userSelect":    "none",
                        "borderRadius":  "8px",
                        "fontSize":      "12px",
                        "fontWeight":    "600",
                        "padding":       "6px 14px",
                        "border":        "none",
                        "background":    "#17976e",
                        "color":         "white",
                        "height":        "42px",
                       })
                ], style={"display": "flex", "gap": "10px", "marginBottom": "5px"}),
                html.Div(id={"type": "image-preview", "entity": "society", "field": "bg"}, style={"marginTop": "5px", "marginBottom": "15px"}),
                dcc.Input(id={"type": "form-field-hidden", "entity": "society", "field": "bg"}, type="hidden"),
                dcc.Input(id={"type": "form-entity-pk", "entity": "society"}, type="hidden", value=""),
            ]),
        ]
    elif category == "TAN & TDS Rates":
        from database.seed import TDS_SECTION_RATE_SEED
        s_tan = ""
        if society_id:
            row = db._execute("SELECT tan_number FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
            if row:
                s_tan = row.get("tan_number") or ""
        inputs = [
            _render_banner("TAN & TDS Rates", "Configure TAN and TDS Section rates. Values are pre-filled with standards."),
            dbc.Label("TAN Number"),
            dbc.Input(id="sw-society-tan", type="text", placeholder="Enter TAN...", value=s_tan, className="mb-4"),
            html.Hr(),
            html.H6("TDS Rates", className="text-primary mb-3")
        ]
        
        header = dbc.Row([
            dbc.Col(html.B("Section", className="small text-uppercase"), width=1),
            dbc.Col(html.B("Nature of Income", className="small text-uppercase"), width=5),
            dbc.Col(html.B("Rate (%)", className="small text-uppercase"), width=1),
            dbc.Col(html.B("No Pan (%)", className="small text-uppercase"), width=1),
            dbc.Col(html.B("Single Bill (₹)", className="small text-uppercase"), width=2),
            dbc.Col(html.B("Aggregate (₹)", className="small text-uppercase"), width=2),
        ], className="mb-2 border-bottom pb-2")
        inputs.append(header)
        
        for idx, item in enumerate(TDS_SECTION_RATE_SEED):
            section, nature, rate, rate_no_pan, single_bill, agg_bill = item
            row = dbc.Row([
                dbc.Col(dbc.Input(id={"type": "tds-section", "index": idx}, value=section, readonly=True, size="sm"), width=1),
                dbc.Col(dbc.Input(id={"type": "tds-nature", "index": idx}, value=nature, size="sm"), width=5),
                dbc.Col(dbc.Input(id={"type": "tds-rate", "index": idx}, type="number", value=rate, step=0.1, size="sm"), width=1),
                dbc.Col(dbc.Input(id={"type": "tds-rate-no-pan", "index": idx}, type="number", value=rate_no_pan, step=0.1, size="sm"), width=1),
                dbc.Col(dbc.Input(id={"type": "tds-single-bill", "index": idx}, type="number", value=single_bill, size="sm"), width=2),
                dbc.Col(dbc.Input(id={"type": "tds-agg-bill", "index": idx}, type="number", value=agg_bill, size="sm"), width=2),
            ], className="mb-2")
            inputs.append(row)
            
        return elements + [html.Div(inputs, style={"maxHeight": "350px", "overflowY": "auto", "overflowX": "hidden", "paddingRight": "5px"})]
    elif category == "GSTIN & GST Rate":
        s_gstin = ""
        if society_id:
            row = db._execute("SELECT gstin FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
            if row:
                s_gstin = row.get("gstin") or ""
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
        return elements + [
            _render_banner("GSTIN & GST Rate", "Configure this society's GSTIN and GST rates. Turnover/exemption limits below are statutory constants maintained by Master, not editable per-society."),
            dbc.Label("GSTIN"),
            dbc.Input(id="sw-society-gstin", type="text", placeholder="Enter GSTIN...", value=s_gstin, className="mb-4"),
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
        from database.seed import STATE_COMPLIANCE_THRESHOLDS, KPI_RULE_LINKS
        c_sink_basis, c_repair_basis, c_gst_exempt, c_charges_int = "per_sq_ft", "per_sq_ft", True, True
        c_gst_cadence, c_gst_reg, c_tds_action, c_export_fmt = "monthly", False, "warn", "structured"
        if society_id:
            row = db._execute("SELECT * FROM society_compliance_settings WHERE society_id = :id", {"id": society_id}, fetch_one=True)
            if row:
                c_sink_basis = row.get("sinking_fund_rate_basis", c_sink_basis)
                c_repair_basis = row.get("repair_fund_rate_basis", c_repair_basis)
                c_gst_exempt = row.get("fund_gst_exempt", c_gst_exempt)
                c_charges_int = row.get("fund_charges_interest", c_charges_int)
                c_gst_cadence = row.get("gst_filing_cadence", c_gst_cadence)
                c_gst_reg = row.get("gst_registered", c_gst_reg)
                c_tds_action = row.get("tds_no_pan_action", c_tds_action)
                c_export_fmt = row.get("default_export_format", c_export_fmt)
        inputs = [_render_banner("Compliance Settings", "Configure compliance parameters specific to this society. Reference rule links and thresholds are shown below.")]
        inputs.append(html.H6("Society Compliance Settings", className="mt-2 mb-3 text-primary"))
        inputs.append(dbc.Row([
            dbc.Col([dbc.Label("Registered for GST?"), dbc.RadioItems(id="sw-gst-registered", options=[{"label": "Yes", "value": True}, {"label": "No", "value": False}], value=True, inline=True, className="mb-3")], width=6),
            dbc.Col([dbc.Label("Deducts TDS?"), dbc.RadioItems(id="sw-deducts-tds", options=[{"label": "Yes", "value": True}, {"label": "No", "value": False}], value=True, inline=True, className="mb-3")], width=6),
        ]))
        inputs.append(dbc.Row([
            dbc.Col([dbc.Label("Sinking Fund Basis"), dbc.Select(id="sw-comp-sink", options=[{"label": "Per Sq Ft", "value": "per_sq_ft"}, {"label": "Construction Cost", "value": "construction_cost"}], value=c_sink_basis, className="mb-3")], width=6),
            dbc.Col([dbc.Label("Repair Fund Basis"), dbc.Select(id="sw-comp-repair", options=[{"label": "Per Sq Ft", "value": "per_sq_ft"}, {"label": "Construction Cost", "value": "construction_cost"}], value=c_repair_basis, className="mb-3")], width=6)
        ]))
        inputs.append(dbc.Row([
            dbc.Col([dbc.Label("Fund GST Exempt"), dbc.Switch(id="sw-comp-gst-exempt", value=c_gst_exempt, className="mb-3")], width=6),
            dbc.Col([dbc.Label("Fund Charges Interest"), dbc.Switch(id="sw-comp-charges-int", value=c_charges_int, className="mb-3")], width=6)
        ]))
        inputs.append(dbc.Row([
            dbc.Col([dbc.Label("GST Filing Cadence"), dbc.Select(id="sw-comp-gst-cadence", options=[{"label": "Monthly", "value": "monthly"}, {"label": "QRMP", "value": "qrmp"}], value=c_gst_cadence, className="mb-3")], width=6),
            dbc.Col([dbc.Label("GST Registered"), dbc.Switch(id="sw-comp-gst-reg", value=c_gst_reg, className="mb-3")], width=6)
        ]))
        inputs.append(dbc.Row([
            dbc.Col([dbc.Label("TDS No PAN Action"), dbc.Select(id="sw-comp-tds-action", options=[{"label": "Warn", "value": "warn"}, {"label": "Block", "value": "block"}], value=c_tds_action, className="mb-3")], width=6),
            dbc.Col([dbc.Label("Export Format"), dbc.Select(id="sw-comp-export-fmt", options=[{"label": "Structured", "value": "structured"}, {"label": "GSTN Offline", "value": "gstn_offline"}, {"label": "TRACES 26Q", "value": "traces_26q"}], value=c_export_fmt, className="mb-3")], width=6)
        ]))
        inputs.append(html.Hr())
        inputs.append(html.H6("State Compliance Thresholds", className="mt-4 mb-2 text-primary"))
        for item in STATE_COMPLIANCE_THRESHOLDS:
            state, key, val, val_text, unit, eff_from, eff_to, notes = item
            inputs.append(dbc.Row([dbc.Col(html.B(state), width=1), dbc.Col(html.Span(key, className="small text-muted"), width=3), dbc.Col(html.Span(val if val is not None else "", className="small fw-bold"), width=2), dbc.Col(html.Span(unit, className="small text-muted"), width=1), dbc.Col(html.Span(notes, className="small text-muted"), width=5)], className="mb-2"))
        return elements + [html.Div(inputs, style={"maxHeight": "400px", "overflow": "auto", "paddingRight": "5px"})]
    elif category == "Apartment Charges":
        s_amt, s_rate, s_due, s_sink, s_repair, s_int = 0.0, 0.0, 1, 0.0, 0.0, 0.0
        if society_id:
            row = db._execute("SELECT apt_maintenance_amount, apt_maintenance_rate, apt_due_day, apt_sinking_fund_rate, apt_repair_fund_rate, apt_interest_pct FROM apt_charges_fines_basis WHERE society_id = :id AND apt_id IS NULL AND end_date IS NULL LIMIT 1", {"id": society_id}, fetch_one=True)
            if row:
                s_amt, s_rate, s_due = row.get("apt_maintenance_amount", 0.0) or 0.0, row.get("apt_maintenance_rate", 0.0) or 0.0, row.get("apt_due_day", 1) or 1
                s_sink, s_repair, s_int = row.get("apt_sinking_fund_rate", 0.0) or 0.0, row.get("apt_repair_fund_rate", 0.0) or 0.0, row.get("apt_interest_pct", 0.0) or 0.0
        return elements + [
            _render_banner("Apartment Charges", "Set default charges, billing cycle day, sinking fund, and repair fund rates for all apartments."),
            dbc.Row([dbc.Col([dbc.Label("Base Maintenance Amount"), dbc.Input(id="sw-apt-amt", type="number", value=s_amt, step=1, className="mb-3")], width=6), dbc.Col([dbc.Label("Maintenance Rate/SqFt"), dbc.Input(id="sw-apt-rate", type="number", value=s_rate, step=0.01, className="mb-3")], width=6)]),
            dbc.Row([dbc.Col([dbc.Label("Billing Due Day"), dbc.Input(id="sw-apt-due", type="number", value=s_due, min=1, max=31, step=1, className="mb-3")], width=4), dbc.Col([dbc.Label("Sinking Fund Rate"), dbc.Input(id="sw-apt-sink", type="number", value=s_sink, step=0.01, className="mb-3")], width=4), dbc.Col([dbc.Label("Repair Fund Rate"), dbc.Input(id="sw-apt-repair", type="number", value=s_repair, step=0.01, className="mb-3")], width=4)]),
            dbc.Row([dbc.Col([dbc.Label("Charges Interest Rate (%)"), dbc.Input(id="sw-apt-interest", type="number", value=s_int, step=0.01, className="mb-3")], width=4)])
        ]
    elif category == "Vendor Charges":
        s_v1, s_v7, s_v30 = 0.0, 0.0, 0.0
        if society_id:
            row = db._execute("SELECT vendor_1day, vendor_7day, vendor_1mth FROM ven_charges_fines_basis WHERE society_id = :id AND ven_id IS NULL AND end_date IS NULL LIMIT 1", {"id": society_id}, fetch_one=True)
            if row:
                s_v1, s_v7, s_v30 = row.get("vendor_1day", 0.0) or 0.0, row.get("vendor_7day", 0.0) or 0.0, row.get("vendor_1mth", 0.0) or 0.0
        return elements + [
            _render_banner("Vendor Charges", "Set default vendor pass charges (1-Day, 7-Day, 1-Month)."),
            dbc.Row([dbc.Col([dbc.Label("Vendor Pass (1 Day) ₹"), dbc.Input(id="sw-ven-1day", type="number", value=s_v1, step=1, className="mb-3")]), dbc.Col([dbc.Label("Vendor Pass (7 Days) ₹"), dbc.Input(id="sw-ven-7day", type="number", value=s_v7, step=1, className="mb-3")]), dbc.Col([dbc.Label("Vendor Pass (1 Month) ₹"), dbc.Input(id="sw-ven-1mth", type="number", value=s_v30, step=1, className="mb-3")])])
        ]
    elif category == "Accounts":
        s_calc = "2024-04-01"
        if society_id:
            row = db._execute("SELECT calc_start_date FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
            if row and row.get("calc_start_date"): s_calc = str(row["calc_start_date"])
        from database.seed import ACCOUNTS
        inputs = [
            _render_banner("Accounts Settings", "Configure accounting start date and Payment QR Code."),
            html.P("Note: The primary_bank_account is not set by default. The Society's payment QR code must correspond to this bank. You can set this later in the Admin portal under the 'Settings' tab, 'Account' KPI.", className="text-info small mb-3"),
            dbc.Label("Payment QR Code Image"),
            html.Div([
                html.Div([
                    dcc.Upload(
                        id={"type": "form-upload", "entity": "society", "field": "pay_qr"},
                        children=html.Div([
                            html.I(className="fas fa-cloud-upload-alt me-1"),
                            "Upload / Drop",
                        ], style={"fontSize": "12px"}),
                        style={
                            "flex":         "1",
                            "height":       "42px",
                            "lineHeight":   "42px",
                            "borderWidth":  "2px",
                            "borderStyle":  "dashed",
                            "borderRadius": "10px",
                            "textAlign":    "center",
                            "borderColor":  "#667eea",
                            "background":   "rgba(102,126,234,0.04)",
                            "cursor":       "pointer",
                            "color":        "#667eea",
                            "minWidth":     "110px",
                        },
                        multiple=False, accept="image/*",
                    ),
                    html.Button([
                        html.I(className="fas fa-camera me-1"),
                        "Snap"
                    ], id={"type": "camera-snap-btn", "entity": "society", "field": "pay_qr"},
                       style={
                        "display":       "inline-flex",
                        "alignItems":    "center",
                        "justifyContent":"center",
                        "cursor":        "pointer",
                        "userSelect":    "none",
                        "borderRadius":  "8px",
                        "fontSize":      "12px",
                        "fontWeight":    "600",
                        "padding":       "6px 14px",
                        "border":        "none",
                        "background":    "#17976e",
                        "color":         "white",
                        "height":        "42px",
                       })
                ], style={"display": "flex", "gap": "10px", "marginBottom": "5px"}),
                html.Div(id={"type": "image-preview", "entity": "society", "field": "pay_qr"}, style={"marginTop": "5px", "marginBottom": "15px"}),
                dcc.Input(id={"type": "form-field-hidden", "entity": "society", "field": "pay_qr"}, type="hidden"),
                dcc.Input(id={"type": "form-entity-pk", "entity": "society"}, type="hidden", value=""),
            ]),
            dbc.Label("Accounting/Calculation Start Date"),
            dcc.DatePickerSingle(id="sw-calc-start-date", date=s_calc, display_format='YYYY-MM-DD', className="mb-4 d-block"),
            html.Hr(),
            html.H6("All Accounts (Seeded)", className="text-primary mb-3"),
        ]
        header = dbc.Row([
            dbc.Col(html.B("ID", className="small text-uppercase"), width=1),
            dbc.Col(html.B("Tab", className="small text-uppercase"), width=2),
            dbc.Col(html.B("Name", className="small text-uppercase"), width=4),
            dbc.Col(html.B("Dr/Cr", className="small text-uppercase", title="drcr_account"), width=1),
            dbc.Col(html.B("BF?", className="small text-uppercase", title="has_bf"), width=1),
            dbc.Col(html.B("Depr?", className="small text-uppercase", title="is_depreciable"), width=1),
            dbc.Col(html.B("Depr %", className="small text-uppercase", title="depreciation_percent"), width=2),
        ], className="mb-2 border-bottom pb-1")
        inputs.append(header)

        # Group (sort) by parent_account_id (acc[4])
        sorted_accounts = sorted(ACCOUNTS, key=lambda x: (x[4] if x[4] is not None else -1, x[0]))

        for acc in sorted_accounts:
            # acc mapping: 0=id, 1=header, 2=tab, 3=name, 4=parent, 5=drcr, 6=has_bf, 7=drcr_bf, 8=depr_percent
            is_depreciable = acc[8] < 100 if acc[8] is not None else False
            
            row = dbc.Row([
                dbc.Col(html.Span(str(acc[0]), className="small text-muted"), width=1, className="d-flex align-items-center"),
                dbc.Col(html.Span(str(acc[2] or ""), className="small text-muted text-break"), width=2, className="d-flex align-items-center"),
                dbc.Col(html.Span(str(acc[3] or ""), className="small fw-bold"), width=4, className="d-flex align-items-center"),
                dbc.Col(html.Span(str(acc[5] or ""), className="small text-muted"), width=1, className="d-flex align-items-center"),
                dbc.Col(html.Span("Yes" if acc[6] else "No", className="small text-muted"), width=1, className="d-flex align-items-center"),
                dbc.Col(html.Span("Yes" if is_depreciable else "No", className="small text-muted"), width=1, className="d-flex align-items-center"),
                dbc.Col(html.Span(f"{acc[8]}%" if acc[8] is not None else "", className="small text-muted text-break"), width=2, className="d-flex align-items-center"),
            ], className="mb-2")
            inputs.append(row)
        return elements + [html.Div(inputs, style={"maxHeight": "450px", "overflow": "auto", "paddingRight": "5px"})]
    elif category == "Brought Forward":
        s_fy = 2024
        if society_id:
            row = db._execute("SELECT financial_year FROM brought_forward WHERE society_id = :id LIMIT 1", {"id": society_id}, fetch_one=True)
            if row: s_fy = row.get("financial_year", 2024)
        from database.seed import ACCOUNTS
        accounts = [{"id": acc[0], "tab_name": acc[2], "name": acc[3], "drcr_bf": acc[7]} for acc in ACCOUNTS if acc[6]]
        
        inputs = [
            _render_banner("Brought Forward", "Enter brought forward (opening balance) amounts for accounts. Values will be saved for the specified Financial Year."),
            dbc.Label("Financial Year (Start Year)"),
            dbc.Input(id="sw-bf-fy", type="number", value=s_fy, step=1, className="mb-3"),
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
            
        return elements + [html.Div(inputs, style={"maxHeight": "450px", "overflow": "auto", "paddingRight": "5px"})]
    elif category == "Administrator":
        s_name, s_phone, s_email = "", "", ""
        if society_id:
            row = db._execute("SELECT secretary_name, secretary_phone, secretary_email FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
            if row:
                s_name, s_phone, s_email = row.get("secretary_name", "") or "", row.get("secretary_phone", "") or "", row.get("secretary_email", "") or ""
        return elements + [
            _render_banner("Administrator Details", "Configure Secretary details, digital signature, and your secure QR SIGNING_SECRET. This secret is required to authenticate generated QR codes."),
            html.H6("Secretary Details", className="text-primary mb-3"),
            dbc.Label("Secretary Name"),
            dbc.Input(id="sw-sec-name", type="text", value=s_name, className="mb-3"),
            dbc.Label("Secretary Phone"),
            dbc.Input(id="sw-sec-phone", type="tel", value=s_phone, className="mb-3"),
            dbc.Label("Secretary Email"),
            dbc.Input(id="sw-sec-email", type="email", value=s_email, className="mb-3"),
            dbc.Label("Secretary Signature Image"),
            html.Div([
                html.Div([
                    dcc.Upload(
                        id={"type": "form-upload", "entity": "society", "field": "sec_sign"},
                        children=html.Div([
                            html.I(className="fas fa-cloud-upload-alt me-1"),
                            "Upload / Drop",
                        ], style={"fontSize": "12px"}),
                        style={
                            "flex":         "1",
                            "height":       "42px",
                            "lineHeight":   "42px",
                            "borderWidth":  "2px",
                            "borderStyle":  "dashed",
                            "borderRadius": "10px",
                            "textAlign":    "center",
                            "borderColor":  "#667eea",
                            "background":   "rgba(102,126,234,0.04)",
                            "cursor":       "pointer",
                            "color":        "#667eea",
                            "minWidth":     "110px",
                        },
                        multiple=False, accept="image/*",
                    ),
                    html.Button([
                        html.I(className="fas fa-camera me-1"),
                        "Snap"
                    ], id={"type": "camera-snap-btn", "entity": "society", "field": "sec_sign"},
                       style={
                        "display":       "inline-flex",
                        "alignItems":    "center",
                        "justifyContent":"center",
                        "cursor":        "pointer",
                        "userSelect":    "none",
                        "borderRadius":  "8px",
                        "fontSize":      "12px",
                        "fontWeight":    "600",
                        "padding":       "6px 14px",
                        "border":        "none",
                        "background":    "#17976e",
                        "color":         "white",
                        "height":        "42px",
                       })
                ], style={"display": "flex", "gap": "10px", "marginBottom": "5px"}),
                html.Div(id={"type": "image-preview", "entity": "society", "field": "sec_sign"}, style={"marginTop": "5px", "marginBottom": "15px"}),
                dcc.Input(id={"type": "form-field-hidden", "entity": "society", "field": "sec_sign"}, type="hidden"),
                dcc.Input(id={"type": "form-entity-pk", "entity": "society"}, type="hidden", value=""),
            ]),
            html.Hr(),
            html.P("Create this society's QR SIGNING_SECRET.", className="text-danger fw-bold mb-1"),
            html.P(
                "This is the real key used to sign every QR gate-pass code "
                "(apartments, vendors, security, admin) issued for THIS "
                "society — it is specific to this society and is never "
                "shared with any other society on the platform. Store it "
                "safely: changing it later invalidates every previously "
                "printed QR code for this society, requiring a full reissue.",
                className="text-muted small mb-3",
            ),
            dbc.Label("SIGNING_SECRET (Strong Password)"),
            dbc.Input(id="sw-qr-secret", type="password", required=True, className="mb-3"),
            dbc.Label("Confirm SIGNING_SECRET"),
            dbc.Input(id="sw-qr-secret-confirm", type="password", required=True, className="mb-3"),
        ]
    elif category == "Instructions":
        here = os.path.dirname(os.path.abspath(__file__))
        readme_path = os.path.abspath(os.path.join(here, "../../../README.md"))
        
        readme_txt = ""
        if os.path.exists(readme_path):
            with open(readme_path, 'r') as f:
                readme_txt = f.read()

        return elements + [
            html.Div([
                html.H5("EstateHub Instructions", className="text-primary mb-3", style={"display": "inline-block"}),
                html.A([html.I(className="fas fa-print me-1"), "Print / Open in New Window"], 
                       href="/print_doc/readme", target="_blank", 
                       className="btn btn-sm btn-outline-secondary float-end")
            ], className="mb-2"),
            html.Div(
                [dcc.Markdown(readme_txt)],
                style={"height": "350px", "overflowY": "auto", "backgroundColor": "#f8f9fa", "padding": "15px", "borderRadius": "5px", "border": "1px solid #ced4da", "marginBottom": "20px"}
            )
        ]
    elif category == "Review":
        return elements + [
            _render_banner("Review & Confirm", "Please review the key settings below before finalizing the setup."),
            html.Div(id="sw-review-content", style={"padding": "10px", "background": "#f8f9fa", "borderRadius": "8px"})
        ]
    elif category == "Agreement":
        here = os.path.dirname(os.path.abspath(__file__))
        agreement_path = os.path.abspath(os.path.join(here, "../../../database/AGREEMENT.md"))
        
        agreement_txt = ""
        if os.path.exists(agreement_path):
            with open(agreement_path, 'r') as f:
                agreement_txt = f.read()

        return elements + [
            html.Div([
                html.H5("EstateHub terms and agreements", className="text-primary mb-3", style={"display": "inline-block"}),
                html.A([html.I(className="fas fa-print me-1"), "Print Agreement Template"], 
                       href="/print_doc/agreement", target="_blank", 
                       className="btn btn-sm btn-outline-secondary float-end")
            ], className="mb-2"),
            html.Div(
                [dcc.Markdown(agreement_txt)],
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
                    dbc.Label("SIGNING_SECRET"),
                    dbc.Input(id="sw-qr-confirm-final", type="password", placeholder="Enter the SIGNING_SECRET created in the Administrator tab...", className="mb-3")
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
                dbc.Row(className="d-flex h-100", children=[
                    # Navigation (Left)
                    dbc.Col(
                        [
                            html.H3([html.I(className="fas fa-magic me-2"), "Setup Wizard"], style={"color": "#667eea", "fontWeight": "bold", "marginBottom": "30px", "fontSize": "1.5rem"}),
                            dbc.Nav(
                                [
                                    dbc.NavLink(
                                        [html.I(className=f"{CATEGORY_ICONS.get(cat, 'fas fa-circle')} me-2"), cat],
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
                        style={"flex": "0 0 250px", "borderRight": "1px solid #ddd", "paddingRight": "10px"}
                    ),
                    
                    # Content (Center)
                    dbc.Col(
                        className="d-flex flex-column",
                        children=[
                            html.H4(id="sw-category-title", children=CATEGORIES[0], style={"fontWeight": "bold", "marginBottom": "20px"}),
                            html.Div(id="sw-category-content", style={"flex": "1", "overflowY": "auto", "paddingRight": "10px"}, children=[
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
                                style={"marginTop": "30px", "textAlign": "right", "paddingTop": "15px", "borderTop": "1px solid #eee"}
                            )
                        ],
                        style={"flex": "1", "padding": "0 20px"}
                    ),

                    # Rules & Compliance Panel (Right)
                    dbc.Col(
                        className="d-flex flex-column",
                        children=[
                            html.Div(
                                [
                                    html.H5([html.I(className="fas fa-book me-2"), "Acts & Rules"], style={"fontWeight": "bold", "color": "#2c3e50"}),
                                    html.Hr(style={"margin": "10px 0"}),
                                    html.Div(id="sw-compliance-rules-panel", style={"flex": "1", "fontSize": "12.5px", "color": "#3a4a5c", "overflowY": "auto"})
                                ],
                                className="d-flex flex-column h-100",
                                style={"background": "rgba(255,255,255,0.85)", "padding": "15px", "borderRadius": "10px", "boxShadow": "0 2px 4px rgba(0,0,0,0.1)"}
                            )
                        ],
                        style={"flex": "0 0 300px", "paddingLeft": "10px"}
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
