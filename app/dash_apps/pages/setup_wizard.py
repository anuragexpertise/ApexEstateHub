import os

from dash import html, dcc, Input, Output, State, ALL, callback, no_update
from app.utils.fiscal import fy_start_date, fy_start_year
import dash_bootstrap_components as dbc
from database.db_manager import db


# ── Defaults requested for first-time setup ────────────────────────────────
DEFAULT_SINKING_FUND_RATE = 0.25    # ₹ per sq ft / month
DEFAULT_REPAIR_FUND_RATE  = 0.75    # ₹ per sq ft / month
MAX_INTEREST_RATE_PCT     = 1.75    # hard cap on the late-payment interest rate
DEFAULT_VENDOR_1DAY, DEFAULT_VENDOR_7DAY, DEFAULT_VENDOR_1MTH = 100, 500, 2000

_Label = dbc.Label

FIELD_TIPS = {
    # Society Details
    "Society Name": "Registered name of the society. Fixed at onboarding — contact Master to change it.",
    "Society Logo (Image)": "Shown on receipts, letterheads and the portal header. Images are compressed to WebP under 50 KB.",
    "Address": "Full postal address. Printed on receipts, bills and the Agreement.",
    "State": "Decides inter-state (IGST) vs intra-state (CGST+SGST) on RCM, and which state's statutory rules and fund-rate defaults apply.",
    "Email": "Society contact email used on bills and notices.",
    "Phone Number": "Society contact number printed on receipts and notices.",
    "PAN Number": "Society PAN. Fixed at onboarding — contact Master to change it.",
    "Registration Number": "Registration number under the Societies Registration Act / UP Apartment Act as printed on your registration certificate.",
    "Gate Pass Enforcement": "Which gate movement is denied when a vendor's or resident's pass is invalid or unpaid: entry, exit, or both.",
    "Security Duty Hours": "Shift pattern for the security roster: 8-hour (three shifts) or 12-hour (day and night).",
    "Login Background (Image)": "Optional picture shown behind your society's login screen.",
    # Administrator
    "Secretary Name": "Name of the Secretary / authorised signatory, printed on receipts and the Agreement.",
    "Secretary Phone": "Secretary's contact number.",
    "Secretary Email": "Secretary's contact email.",
    "Secretary Signature Image": "Scanned signature printed on receipts and official letters.",
    "SIGNING_SECRET (Strong Password)": "Key that signs every QR gate-pass for this society. Minimum 8 characters with upper case, lower case and a special character. Changing it later invalidates all printed QR codes.",
    "Confirm SIGNING_SECRET": "Re-enter the SIGNING_SECRET exactly to avoid a typo locking you out of QR issuing.",
    # Society Compliance
    "Registered for GST?": "Yes shows the GSTIN & GST Rate step. Societies are usually registered only when turnover crosses the GST threshold.",
    "Deducts TDS?": "Yes shows the TAN & TDS Rates step. Needed when you pay vendors above the TDS thresholds.",
    "Sinking Fund Basis": "How the Sinking Fund contribution is calculated: per sq ft of apartment area, or as a share of construction cost.",
    "Repair Fund Basis": "How the Repair & Maintenance Fund contribution is calculated: per sq ft, or as a share of construction cost.",
    "Fund GST Exempt": "On = sinking / repair fund collections are treated as GST-exempt (see CBIC Circular 109/28/2019-GST).",
    "Fund Charges Interest": "On = late-payment interest also applies to overdue Sinking / Repair fund dues.",
    "GST Filing Cadence": "Monthly = a return every month. QRMP = quarterly returns with monthly tax payment.",
    "TDS No PAN Action": "What happens when a payee has no PAN (Sec. 206AA higher rate): Warn = allow with a warning, Block = stop the payment.",
    "Export Format": "Default layout for compliance exports: Structured (generic), GSTN Offline (GST portal) or TRACES 26Q (TDS return).",
    # TAN / TDS
    "TAN Number": "Tax Deduction Account Number (10 characters, e.g. ABCD12345E). Required to deposit TDS and file 26Q.",
    "TDS Effective Date": "Date from which the TDS rates below apply. The default is the start of the financial year.",
    # GST
    "GSTIN": "15-character GST identification number issued on registration.",
    "CGST Rate (%)": "Central GST rate. Default 9% (CGST 9% + SGST 9% = 18%).",
    "SGST Rate (%)": "State GST rate. Default 9% (CGST 9% + SGST 9% = 18%).",
    "Annual Turnover Limit for GST (Lakhs)": "Statutory turnover above which registration is mandatory. Maintained by Master — read-only.",
    "Monthly Exemption Limit (₹ per member)": "Maintenance up to this amount per member per month is GST-exempt. Maintained by Master — read-only.",
    # Apartment charges
    "Base Maintenance Amount": "Flat monthly maintenance charged per apartment. Leave 0 if you charge only by rate per sq ft.",
    "Maintenance Rate/SqFt": "Monthly maintenance per sq ft of apartment area.",
    "Billing Due Day": "Day of the month by which bills must be paid (1–31). Interest starts after this day.",
    "Sinking Fund Rate": f"Monthly Sinking Fund contribution (₹ per sq ft). Default {DEFAULT_SINKING_FUND_RATE}.",
    "Repair Fund Rate": f"Monthly Repair & Maintenance Fund contribution (₹ per sq ft). Default {DEFAULT_REPAIR_FUND_RATE}.",
    "Charges Interest Rate (%)": f"Interest charged on overdue dues. Capped at {MAX_INTEREST_RATE_PCT}%.",
    # Vendor charges
    "Vendor Pass (1 Day) ₹": f"Default fee for a one-day vendor pass. Default ₹{DEFAULT_VENDOR_1DAY}.",
    "Vendor Pass (7 Days) ₹": f"Default fee for a seven-day vendor pass. Default ₹{DEFAULT_VENDOR_7DAY}.",
    "Vendor Pass (1 Month) ₹": f"Default fee for a one-month vendor pass. Default ₹{DEFAULT_VENDOR_1MTH}.",
    # Accounts / BF
    "Payment QR Code Image": "Your society's payment QR (UPI). It must belong to the primary bank account (the seeded 'SBI A/c - Society' unless you change it).",
    "Accounting/Calculation Start Date": "Date from which EstateHub calculates bills, interest and books. Usually the start of a financial year.",
    "Financial Year (Start Year)": "Year in which the financial year of these opening balances starts (e.g. 2024 for FY 2024-25).",
    # Agreement
    "Type 'I AGREE' below to proceed": "Type I AGREE in capitals to accept the EstateHub terms and agreement.",
    "Admin Password": "Your own login password. Confirms it is really you finalising the setup.",
    "SIGNING_SECRET": "The SIGNING_SECRET you created on the Administrator step.",
}


def _tip_icon(tip):
    """CSS-only tooltip (see setup_wizard.css .sw-tip) — no ids, works on hover and keyboard focus."""
    return html.Span(
        html.I(className="fas fa-info-circle"),
        className="sw-tip", tabIndex=0,
        **{"data-tip": tip, "aria-label": tip},
    )


def _label(text, *args, tip=None, **kwargs):
    """dbc.Label with an info-icon tooltip looked up from FIELD_TIPS (or passed as tip=)."""
    tip = tip or (FIELD_TIPS.get(text) if isinstance(text, str) else None)
    children = [text, _tip_icon(tip)] if tip else text
    return _Label(children, *args, **kwargs)


def _th(text, tip=None):
    """Table header cell with optional tooltip."""
    return html.Div([text, _tip_icon(tip)] if tip else text)


def _existing_society_images(society_id):
    """Already-saved image filenames for this society (so re-opening the wizard shows them)."""
    if not society_id:
        return {}
    try:
        row = db._execute(
            "SELECT logo, login_background, payment_qr, secretary_sign FROM societies WHERE id = :id",
            {"id": society_id}, fetch_one=True,
        ) or {}
    except Exception:
        return {}
    return {
        "logo": row.get("logo"), "bg": row.get("login_background"),
        "pay_qr": row.get("payment_qr"), "sec_sign": row.get("secretary_sign"),
    }


def build_rules_panel(step, society_id=None, state=None):
    """
    Body of the "Acts & Rules" column for one wizard step.

    1) Framework rows from README "Statutory Framework Coverage" (app/services/statutory_rules.py)
    2) For the steps listed in STEP_INSTRUMENTS, the tabulated Act / Rules /
       Bye-laws governing this society's regime (legal_instrument_catalog)
    3) Official "read the Act" links from kpi_rule_links, looked up through
       STEP_LINK_CATEGORIES — the old code queried the wizard step *name*
       ("Society Details") against kpi_rule_links.category ('sinking_fund',
       'fund_gst', ...) and always got nothing — for the society's own state
       (was hard-coded "ALL", which also hid every UP-specific link).

    `state` is the value of the Society Details State dropdown, when it has
    been picked but not yet saved (societies.state is only written on
    submit) — without it the panel showed the old/blank DB state while the
    admin was looking at a freshly-chosen one.
    """
    from app.services.statutory_rules import (
        rows_for_step, STEP_LINK_CATEGORIES, STEP_INSTRUMENTS,
        instruments_for_society, grouped_instruments, INSTRUMENT_BADGE_COLOR,
        normalize_state,
    )

    if state:
        state = normalize_state(state)
    else:
        state = "UP"
        if society_id:
            try:
                row = db._execute("SELECT state FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
                state = normalize_state((row or {}).get("state"))
            except Exception:
                pass

    cards = []
    for area, sections, requirement, covered, note in rows_for_step(step):
        cards.append(html.Div([
            html.Div(area, className="sw-rule-area"),
            html.Div(sections, className="sw-rule-sec"),
            html.Div(requirement, className="sw-rule-req"),
            html.Div(
                [html.I(className=f"fas {'fa-check-circle' if covered else 'fa-exclamation-circle'} me-1"),
                 ("In EstateHub: " if covered else "Not yet covered: ") + note],
                className="sw-rule-cov " + ("ok" if covered else "partial"),
            ),
        ], className="sw-rule"))

    instruments_html = []
    if step in STEP_INSTRUMENTS:
        regime, instruments = instruments_for_society(society_id, state)
        instruments_html.append(html.H6(
            [html.I(className="fas fa-gavel me-2"), "Act / Rules / Bye-laws"],
            style={"fontWeight": "700", "color": "#2c3e50", "marginTop": "18px", "marginBottom": "6px"},
        ))
        instruments_html.append(html.Small(
            f"{regime} · {len(instruments)} instrument{'s' if len(instruments) != 1 else ''} — full table on the "
            "'UP AOA Compliance' step.",
            className="text-muted", style={"display": "block", "marginBottom": "6px"},
        ))
        for itype, items in grouped_instruments(instruments).items():
            instruments_html.append(html.Div(
                [dbc.Badge(itype, color=INSTRUMENT_BADGE_COLOR.get(itype, "light"), className="me-2",
                           pill=True, style={"fontSize": "10px"}),
                 html.Small(items[0]["title"] + (f" ({items[0]['enactment_year']})" if items[0].get("enactment_year") else ""),
                            style={"fontSize": "11.5px", "fontWeight": "600", "color": "#1f3b57"})],
                style={"marginBottom": "3px"},
            ))
            for r in items[1:]:
                instruments_html.append(html.Small(
                    "· " + r["title"] + (f" ({r['enactment_year']})" if r.get("enactment_year") else ""),
                    className="text-muted", style={"display": "block", "marginLeft": "8px", "fontSize": "11px"},
                ))

    links = []
    cats = STEP_LINK_CATEGORIES.get(step, [])
    if cats:
        try:
            from app.services.kpi_rule_links_service import get_links_for_categories
            by_cat = get_links_for_categories(cats, state=state)
        except Exception:
            by_cat = {}
        seen = set()
        for cat in cats:
            for lk in by_cat.get(cat, []):
                if lk.url in seen:
                    continue
                seen.add(lk.url)
                links.append(html.Div([
                    html.A([html.I(className="fas fa-external-link-alt me-1"), lk.label],
                           href=lk.url, target="_blank", rel="noopener noreferrer",
                           style={"fontWeight": "500", "color": "#0d6efd", "textDecoration": "none", "display": "block", "marginBottom": "3px"}),
                    html.P(lk.description, style={"fontSize": "11.5px", "color": "#6c757d", "marginBottom": "8px", "lineHeight": "1.4"}),
                ], style={"borderBottom": "1px solid #eee", "marginBottom": "8px"}))

    out = cards + instruments_html
    if links:
        out = out + [html.H6("Official sources", className="text-primary mt-3 mb-2")] + links
    return out


def rules_subtitle(step, society_id=None, state=None):
    """`<step> · <regime>` for the Acts & Rules column header."""
    from app.services.statutory_rules import regime_for_society
    regime = regime_for_society(society_id, state)
    return f"{step} · {regime}"


def _field_feedback(field_id):
    return html.Small(
        id=field_id,
        className="invalid-feedback d-block",
        style={"fontSize": "11px", "marginTop": "4px"},
    )
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
    "Organization Details": ["Instructions", "Society Details", "Administrator"],
    "Central Acts": ["TAN & TDS Rates", "GSTIN & GST Rates"],
    "UP_AOA Acts": ["Compliance (UP_AOA)"],
    "UPAOA Rules": ["Compliance (UP_AOA)"],
    "UP By-Laws": ["By-Laws Adoption"],
    "Society Policy": ["Apartment Charges", "Vendor Charges", "Accounts", "Brought Forward"],
    "Finalization": ["Agreement"]
}
CATEGORIES = [
    'Instructions',
    'Society Details',
    'Administrator',
    'TAN & TDS Rates',
    'GSTIN & GST Rates',
    'Compliance (UP_AOA)',
    'By-Laws Adoption',
    'Apartment Charges',
    'Vendor Charges',
    'Accounts',
    'Brought Forward',
    'Agreement'
]

CATEGORY_ICONS = {
    "Society Details": "fas fa-building",
    "Administrator": "fas fa-user-shield",
    "Instructions": "fas fa-info-circle",
    "Society Compliance": "fas fa-gavel",
    "UP AOA Compliance": "fas fa-book-open",
    "Bye-Laws Adoption": "fas fa-scale-balanced",
    "TAN & TDS Rates": "fas fa-percent",
    "GSTIN & GST Rate": "fas fa-file-invoice-dollar",
    "Apartment Charges": "fas fa-home",
    "Vendor Charges": "fas fa-truck",
    "Accounts": "fas fa-book",
    "Brought Forward": "fas fa-arrow-right",
    "Agreement": "fas fa-handshake"
}

def _render_image_capture_control(entity, field, existing=None, society_id=None):
    """
    Upload-or-camera control for a single image field, reusing the exact
    working id/data-attribute pattern from renderers.py's "image_upload"
    field type (cam-btn-/cam-snap-/cam-stop- id substrings, plus the
    <video>/<canvas> elements camera_callbacks.py's clientside delegation
    listens for).

    The wizard previously built its own "Snap" buttons with
    id={"type": "camera-snap-btn", ...} — a Dash pattern-matching dict id
    that never matches the app's camera click-delegation listener (which
    matches on id substrings like "cam-snap-"), and with no <video>/
    <canvas> elements anywhere on the page for a capture to target. Those
    buttons were inert: clicking "Snap" did nothing at all. Rebuilding the
    control with the shared helper fixes that and keeps the wizard in
    sync with the one working camera implementation instead of a second,
    broken one.
    """
    cam_vid_id  = f"cam-vid-{entity}-{field}"
    cam_cvs_id  = f"cam-cvs-{entity}-{field}"
    cam_snap_id = f"cam-snap-{entity}-{field}"
    cam_stop_id = f"cam-stop-{entity}-{field}"
    cam_btn_id  = f"cam-btn-{entity}-{field}"
    prev_img_id = f"cam-prev-{entity}-{field}"
    hidden_marker = f'"entity": "{entity}", "field": "{field}"'

    _btn_base = {
        "display": "inline-flex", "alignItems": "center", "justifyContent": "center",
        "cursor": "pointer", "userSelect": "none", "borderRadius": "8px",
        "fontSize": "12px", "fontWeight": "600", "padding": "6px 14px", "border": "none",
    }

    return html.Div([
        html.Div([
            dcc.Upload(
                id={"type": "form-upload", "entity": entity, "field": field},
                children=html.Div([
                    html.I(className="fas fa-cloud-upload-alt me-1"),
                    "Upload / Drop",
                ], style={"fontSize": "12px"}),
                style={
                    "flex": "1", "height": "42px", "lineHeight": "42px",
                    "borderWidth": "2px", "borderStyle": "dashed", "borderRadius": "10px",
                    "textAlign": "center", "borderColor": "#667eea",
                    "background": "rgba(102,126,234,0.04)", "cursor": "pointer",
                    "color": "#667eea", "minWidth": "110px",
                },
                multiple=False, accept="image/*",
            ),
            html.Div(
                [html.I(className="fas fa-camera me-1"), "Camera"],
                id=cam_btn_id,
                **{
                    "data-cam-video": cam_vid_id,
                    "data-cam-canvas": cam_cvs_id,
                    "data-cam-snap": cam_snap_id,
                    "data-cam-stop": cam_stop_id,
                },
                style={
                    **_btn_base, "flex": "0 0 auto", "height": "42px",
                    "border": "2px dashed #17976e", "background": "rgba(23,151,110,0.06)",
                    "color": "#17976e", "padding": "0 14px",
                },
            ),
        ], style={"display": "flex", "gap": "10px", "marginBottom": "5px"}),

        html.Video(
            id=cam_vid_id, autoPlay=True, muted=True,
            style={
                "width": "100%", "maxHeight": "200px", "borderRadius": "10px",
                "display": "none", "objectFit": "cover", "background": "#111",
                "marginBottom": "6px",
            },
        ),
        html.Canvas(id=cam_cvs_id, style={"display": "none"}),

        html.Div([
            html.Div(
                [html.I(className="fas fa-circle me-1"), "Snap"],
                id=cam_snap_id,
                **{
                    "data-cam-video":     cam_vid_id,
                    "data-cam-canvas":    cam_cvs_id,
                    "data-cam-btn":       cam_btn_id,   # ← lets snapCamCapture reset the Camera button label
                    "data-cam-stop":      cam_stop_id,
                    "data-preview-id":    prev_img_id,
                    "data-hidden-marker": hidden_marker,
                },
                style={**_btn_base, "background": "#de5c52", "color": "#fff", "display": "none"},
            ),
            html.Div(
                [html.I(className="fas fa-stop me-1"), "Stop"],
                id=cam_stop_id,
                **{"data-cam-video": cam_vid_id, "data-cam-btn": cam_btn_id, "data-cam-snap": cam_snap_id},
                style={**_btn_base, "background": "#7d8ea3", "color": "#fff", "display": "none"},
            ),
        ], style={"display": "flex", "gap": "6px", "justifyContent": "center", "marginBottom": "6px"}),

        html.Div(
            id={"type": "image-preview", "entity": entity, "field": field},
            style={"marginTop": "5px", "marginBottom": "15px"},
            # Show what is already saved; a new upload/snap overwrites this div.
            children=(
                html.Img(
                    src=f"/assets/{society_id}/{existing}" if (existing and society_id and "/" not in str(existing)) else existing,
                    style={"maxWidth": "200px", "maxHeight": "150px", "borderRadius": "8px", "border": "1px solid #ddd"},
                ) if existing else None
            ),
        ),
        html.Img(id=prev_img_id, style={
            "display": "none", "maxWidth": "100%", "maxHeight": "160px",
            "borderRadius": "8px", "marginTop": "6px", "border": "1px solid #ddd",
        }),
        # value=existing keeps an already-saved image when nothing new is uploaded
        # (fn_complete_society_setup COALESCEs, so re-sending the same name is a no-op).
        # NOTE: the old duplicate {"type": "form-entity-pk", "entity": entity} hidden input
        # that used to be emitted here (once per image field => 4 identical ids for
        # entity "society") was the likely cause of the upload callback never firing;
        # it was an unused State, and has been removed from handle_image_upload as well.
        dcc.Input(id={"type": "form-field-hidden", "entity": entity, "field": field}, type="hidden", value=existing or ""),
    ])


def _render_banner(title, text):
    return dbc.Card([
        dbc.CardBody([
            html.H6([html.I(className="fas fa-info-circle me-2"), title], className="text-primary mb-2"),
            html.P(text, className="small text-muted mb-0")
        ], className="p-3")
    ], className="mb-4 shadow-sm border-0 bg-light")

def render_category_content(category, society_id=None, state=None):
    """
    Step body for one wizard category.

    `state` is the Society Details State dropdown value; it is only persisted
    on submit, so any step whose content depends on the state (the "UP AOA
    Compliance" statutes) has to be re-rendered when the admin picks it — see
    refresh_up_aoa_step_content in setup_wizard_callbacks.py.
    """
    elements = []
    _imgs = _existing_society_images(society_id) if category in ("Society Details", "Administrator", "Accounts") else {}
    
    # Render conversational header(s) if available. A category can have more
    # than one guidance row in conversation.xlsx (e.g. "Society Details" has
    # both a Duty Hours tip and a State/Jurisdiction tip) — this used to
    # take only the first match via next(...), so any row after the first
    # for the same category was seeded correctly but never actually
    # rendered. In particular the jurisdiction-aware State guidance row
    # (added in an earlier audit) silently never appeared on screen because
    # it wasn't the first "Society Details" row in the sheet. Now every
    # matching row for the category renders as its own banner.
    conv_infos = [item for item in CONVERSATION_DATA if item.get('Setup Wizard Category') == category]
    for conv_info in conv_infos:
        if conv_info.get('Recommendation from Master to Admin'):
            elements.append(
                dbc.Alert(
                    [html.I(className="fas fa-lightbulb me-2"), conv_info['Recommendation from Master to Admin']],
                    color="info",
                    className="mb-3",
                    style={"fontSize": "13px"}
                )
            )
        
    # Add Print Button for specific categories
    if category in ["Society Compliance", "UP AOA Compliance", "Bye-Laws Adoption", "TAN & TDS Rates", "Accounts"]:
        elements.append(
            html.Div([
                dbc.Button([html.I(className="fas fa-print me-2"), "Print / Open in New Window"], 
                           id={"type": "sw-print-btn", "cat": category}, 
                           color="outline-secondary", size="sm")
            ], style={"textAlign": "right", "marginBottom": "15px"})
        )

    if category == "Society Details":
        s_name, s_addr, s_pan, s_reg, s_phone, s_email, s_gate_logic, s_duty_hrs, s_state = "", "", "", "", "", "", "both", "8", ""
        if society_id:
            row = db._execute("SELECT name, address, phone, email, PAN_number, registration_number, gate_logic, duty_hrs, state FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
            if row:
                s_name = row.get("name", "") or ""
                s_addr = row.get("address", "") or ""
                s_phone = row.get("phone", "") or ""
                s_email = row.get("email", "") or ""
                s_pan = row.get("pan_number", row.get("PAN_number", "")) or ""
                s_reg = row.get("registration_number", "") or ""
                s_gate_logic = row.get("gate_logic", "both") or "both"
                s_duty_hrs = row.get("duty_hrs", "8") or "8"
                s_state = row.get("state", "") or ""
        from app.services.kpi_rule_links_service import get_states
        # Jurisdiction-aware statutory rules (fn_balance_sheet_fy statutory
        # head mapping, state_compliance_thresholds sinking/repair-fund
        # rates) are fully seeded for UP only today; other states show
        # generic/Union-law figures until their own regime is seeded — see
        # legal_regime_profiles.status ('active' vs 'draft'). This dropdown
        # is also the society's ONLY write path for `societies.state`,
        # which GST RCM interstate/intrastate determination
        # (fn_compute_rcm / vendor.state comparison) depends on entirely —
        # previously state had no UI at all and every RCM check silently
        # fell back to guessing the state from the free-text address.
        _state_choices = get_states()
        state_options = [{"label": "— Select State —", "value": ""}] + [
            {"label": f"{name}{' (jurisdiction-aware rules active)' if code == 'UP' else ''}", "value": code}
            for code, name in _state_choices.items() if code != "ALL"
        ]
        return elements + [
            _render_banner("Society Details", "Enter society details. Registration Number, Email, and Phone will be updated if provided. Logo and Background images are optional."),
            _label("Society Name"),
            dbc.Input(id="sw-society-name", type="text", required=True, className="mb-3", value=s_name, readonly=True, style={"opacity": "0.7", "backgroundColor": "#e9ecef"}),
            _label("Society Logo (Image)"),
            _render_image_capture_control("society", "logo", _imgs.get("logo"), society_id),
            _label("Address"),
            dbc.Textarea(id="sw-society-address", required=True, className="mb-3", value=s_addr),
            _field_feedback("sw-society-address-feedback"),
            _label("State", html_for="sw-society-state"),
            dbc.Select(id="sw-society-state", options=state_options, value=s_state, className="mb-1"),
            html.P(
                "Drives GST inter-state (IGST) vs intra-state (CGST+SGST) determination on RCM, and which "
                "state's statutory Balance Sheet head-mapping / fund-rate defaults apply.",
                className="text-muted small mb-3",
            ),
            _label("Email"),
            dbc.Input(id="sw-society-email", type="email", required=True, className="mb-3", value=s_email),
            _field_feedback("sw-society-email-feedback"),
            _label("Phone Number"),
            dbc.Input(id="sw-society-phone", type="tel", required=True, className="mb-3", value=s_phone),
            _field_feedback("sw-society-phone-feedback"),
            _label("PAN Number"),
            dbc.Input(id="sw-society-pan", type="text", required=True, className="mb-3", value=s_pan, readonly=True, style={"opacity": "0.7", "backgroundColor": "#e9ecef"}),
            _label("Registration Number"),
            dbc.Input(id="sw-society-reg", type="text", required=True, className="mb-3", value=s_reg),
            _field_feedback("sw-society-reg-feedback"),
            _label("Gate Pass Enforcement"),
            dbc.Select(
                id="sw-gate-logic",
                options=[
                    {"label": "Deny Both Entry and Exit", "value": "both"},
                    {"label": "Deny Entry Only", "value": "entry"},
                    {"label": "Deny Exit Only", "value": "exit"},
                ],
                value=s_gate_logic,
                className="mb-3"
            ),
            _label("Security Duty Hours"),
            dbc.Select(
                id="sw-duty-hrs",
                options=[
                    {"label": "8 Hours (morning, evening, night)", "value": "8"},
                    {"label": "12 Hours (day, night)", "value": "12"},
                ],
                value=s_duty_hrs,
                className="mb-3"
            ),
            _label("Login Background (Image)"),
            _render_image_capture_control("society", "bg", _imgs.get("bg"), society_id),
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
            _label("TAN Number"),
            dbc.Input(id="sw-society-tan", type="text", placeholder="Enter TAN...", value=s_tan, className="mb-4"),
            _label("TDS Effective Date"),
            html.Div(dcc.DatePickerSingle(
                id="sw-tds-effective-date",
                date=str(fy_start_date()),
                display_format="YYYY-MM-DD"
            ), className="mb-4"),
            html.Hr(),
            html.H6("TDS Rates", className="text-primary mb-3")
        ]
        
        header = html.Div([
            _th("Section", "Income Tax Act section the TDS is deducted under (e.g. 194C contractors, 194J professionals)."),
            _th("Discriminator", "Sub-category inside a section (for example payee type). Fixed by the seed data."),
            _th("Nature of Income", "Description of the payment this row covers. Editable."),
            _th("Rate (%)", "TDS rate when the payee has a PAN."),
            _th("No Pan (%)", "Higher rate when the payee has no PAN (Sec. 206AA, typically 20%)."),
            _th("Single Bill (₹)", "A single bill above this amount attracts TDS."),
            _th("Aggregate (₹)", "TDS applies once total payments to a payee in the financial year exceed this."),
        ], className="sw-grid-row sw-tds-grid sw-grid-head")

        rows = []
        for idx, item in enumerate(TDS_SECTION_RATE_SEED):
            section, discriminator, nature, rate, rate_no_pan, single_bill, agg_bill = item
            rows.append(html.Div([
                html.Div(dbc.Input(id={"type": "tds-section", "index": idx}, value=section, readonly=True, size="sm")),
                html.Div(dbc.Input(id={"type": "tds-discriminator", "index": idx}, value=discriminator or "", readonly=True, size="sm")),
                html.Div(dbc.Input(id={"type": "tds-nature", "index": idx}, value=nature, size="sm")),
                html.Div(dbc.Input(id={"type": "tds-rate", "index": idx}, type="number", value=rate, step=0.1, size="sm")),
                html.Div(dbc.Input(id={"type": "tds-rate-no-pan", "index": idx}, type="number", value=rate_no_pan, step=0.1, size="sm")),
                html.Div(dbc.Input(id={"type": "tds-single-bill", "index": idx}, type="number", value=single_bill, size="sm")),
                html.Div(dbc.Input(id={"type": "tds-agg-bill", "index": idx}, type="number", value=agg_bill, size="sm")),
            ], className="sw-grid-row sw-tds-grid"))
        inputs.append(html.Div([header] + rows, className="sw-hscroll"))

        return elements + [html.Div(inputs, style={"paddingRight": "5px"})]
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
            _label("GSTIN"),
            dbc.Input(id="sw-society-gstin", type="text", placeholder="Enter GSTIN...", value=s_gstin, className="mb-4"),
            html.Hr(),
            html.H6("GST Rates", className="text-primary mb-2"),
            html.P(
                [html.I(className="fas fa-info-circle me-1"),
                 "These GST rates are the defaults for the selected UP AOA scheme "
                 "(UP Apartment Act, 2010 — Apartment Owners' Association): CGST 9% + SGST 9% = 18%. "
                 "Change them only if your CA advises."],
                className="small text-muted mb-3",
            ),
            _label("CGST Rate (%)"),
            dbc.Input(id="sw-cgst", type="number", value=9.0, className="mb-3", step=0.1),
            _label("SGST Rate (%)"),
            dbc.Input(id="sw-sgst", type="number", value=9.0, className="mb-3", step=0.1),
            _label("Annual Turnover Limit for GST (Lakhs)"),
            dbc.Input(type="number", value=turnover_val, className="mb-3", readonly=True, style=readonly_style),
            _label("Monthly Exemption Limit (₹ per member)"),
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
        # NOTE: "Registered for GST?" is the single source of truth for
        # whether this society is GST-registered — it both decides
        # whether the "GSTIN & GST Rate" step is shown at all (see
        # get_next_valid_step in setup_wizard_callbacks.py) and is what
        # gets saved to society_compliance_settings.gst_registered.
        # There used to be a *second*, unrelated "GST Registered" switch
        # further down this same page that also claimed to represent this
        # setting but was never linked to this one or to the step-skip
        # logic — an admin could answer "Yes" here (showing the GSTIN
        # step) while that switch still silently said "No" (or vice
        # versa), and whichever one was touched last is what actually got
        # written to the database. That duplicate switch has been
        # removed; this radio now both drives navigation and is the value
        # persisted on submit.
        inputs.append(dbc.Row([
            dbc.Col([_label("Registered for GST?"), dbc.RadioItems(id="sw-gst-registered", options=[{"label": "Yes", "value": True}, {"label": "No", "value": False}], value=c_gst_reg, inline=True, className="mb-3")], width=6),
            dbc.Col([_label("Deducts TDS?"), dbc.RadioItems(id="sw-deducts-tds", options=[{"label": "Yes", "value": True}, {"label": "No", "value": False}], value=True, inline=True, className="mb-3")], width=6),
        ]))
        inputs.append(dbc.Row([
            dbc.Col([_label("Sinking Fund Basis"), dbc.Select(id="sw-comp-sink", options=[{"label": "Per Sq Ft", "value": "per_sq_ft"}, {"label": "Construction Cost", "value": "construction_cost"}], value=c_sink_basis, className="mb-3")], width=6),
            dbc.Col([_label("Repair Fund Basis"), dbc.Select(id="sw-comp-repair", options=[{"label": "Per Sq Ft", "value": "per_sq_ft"}, {"label": "Construction Cost", "value": "construction_cost"}], value=c_repair_basis, className="mb-3")], width=6)
        ]))
        inputs.append(dbc.Row([
            dbc.Col([_label("Fund GST Exempt"), dbc.Switch(id="sw-comp-gst-exempt", value=c_gst_exempt, className="mb-3")], width=6),
            dbc.Col([_label("Fund Charges Interest"), dbc.Switch(id="sw-comp-charges-int", value=c_charges_int, className="mb-3")], width=6)
        ]))
        inputs.append(dbc.Row([
            dbc.Col([_label("GST Filing Cadence"), dbc.Select(id="sw-comp-gst-cadence", options=[{"label": "Monthly", "value": "monthly"}, {"label": "QRMP", "value": "qrmp"}], value=c_gst_cadence, className="mb-3")], width=6),
            dbc.Col([_label("TDS No PAN Action"), dbc.Select(id="sw-comp-tds-action", options=[{"label": "Warn", "value": "warn"}, {"label": "Block", "value": "block"}], value=c_tds_action, className="mb-3")], width=6),
        ]))
        inputs.append(dbc.Row([
            dbc.Col([_label("Export Format"), dbc.Select(id="sw-comp-export-fmt", options=[{"label": "Structured", "value": "structured"}, {"label": "GSTN Offline", "value": "gstn_offline"}, {"label": "TRACES 26Q", "value": "traces_26q"}], value=c_export_fmt, className="mb-3")], width=6)
        ]))
        inputs.append(html.Hr())
        inputs.append(html.H6("State Compliance Thresholds", className="mt-4 mb-2 text-primary"))
        for item in STATE_COMPLIANCE_THRESHOLDS:
            state, key, val, val_text, unit, eff_from, eff_to, notes = item
            inputs.append(dbc.Row([dbc.Col(html.B(state), width=1), dbc.Col(html.Span(key, className="small text-muted"), width=3), dbc.Col(html.Span(val if val is not None else "", className="small fw-bold"), width=2), dbc.Col(html.Span(unit, className="small text-muted"), width=1), dbc.Col(html.Span(notes, className="small text-muted"), width=5)], className="mb-2"))
        return elements + [html.Div(inputs, style={"paddingRight": "5px"})]
    elif category == "Bye-Laws Adoption":
        # The society's bye-law register: for each Model Bye-Law 2011 clause the admin notes the intended outcome
        # (adopt as-is / adopt with variation / not adopted). Every choice is PROVISIONAL: it is stored with
        # proposed_status and changes nothing in the engine until the passed GBM resolution is recorded
        # (Admin → Settings → Society governance → Meetings & Resolutions), which activates it automatically.
        # A clause nobody touches is governed by the Model
        # Bye-Laws / Act as-is. Persistence is immediate, by callback (sw-bl-*), not on wizard submit.
        from app.services import regime_rules_admin as rra
        existing = {}
        try:
            for r in rra.list_society_bye_laws(society_id) if society_id else []:
                if r["layer"] == 1:
                    existing[r["clause_id"]] = r
        except Exception:
            existing = {}
        labels = {"adopted_as_is": "Adopt as-is", "adopted_with_variation": "Adopt with variation", "not_adopted": "Not adopted"}
        rows = []
        for clause_id, title in rra.MODEL_BYE_LAW_CLAUSES:
            locked = rra.clause_is_locked(society_id, clause_id) if society_id else clause_id in rra.STATUTE_BACKED_CLAUSES
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
            pol = rra.list_society_policies(society_id) if society_id else {}
        except Exception:
            pol = {}
        pol_rows = []
        for key, (label, clause, choices) in rra.POLICY_SPECS.items():
            st = pol.get(key) or {"value": choices[0][0], "active": False, "proposed": None}
            shown = st["proposed"] or st["value"]
            pol_rows.append(html.Tr([
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
                       "which clauses are truly non-droppable is a legal call - confirm with an advocate.", className="text-muted d-block mb-2"),
            dbc.Table([html.Thead(html.Tr([html.Th(h, style={"fontSize": "11px"}) for h in ("Setting", "Choice", "Status")])),
                       html.Tbody(pol_rows)], bordered=True, size="sm"),
        ]) if society_id else html.Div()
        return elements + [
            dbc.Alert([html.I(className="fas fa-scale-balanced me-2"),
                       "Record which Model Bye-Laws 2011 clauses your Association is adopting. These are ",
                       html.Strong("provisional"), " — nothing changes in how EstateHub treats dues, voting, NOC or filings "
                       "until you record the General Body meeting and its passed resolution. Clauses you leave alone follow the "
                       "Model Bye-Laws and the Act as written."], color="info", className="mb-3", style={"fontSize": "13px"}),
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
        ]
    elif category == "UP AOA Compliance":
        # Read-only reference step: the tabulated Acts, Rules, Bye-laws and
        # Notifications governing this society's regime, from
        # legal_instrument_catalog — the same rows the Master Portal's
        # "RWA Compliance (UP)" tab renders (portal_pages.py), so the admin
        # can read the provisions behind the fund rates / bases they set on
        # the Society Compliance and Apartment Charges steps. Maintained by
        # Master (LEGAL_INSTRUMENTS_UP_AOA in database/seed.py); nothing on
        # this step is editable, so it takes no State in submit_setup_wizard.
        from app.services.statutory_rules import (
            instruments_for_society, grouped_instruments, INSTRUMENT_BADGE_COLOR,
            normalize_state,
        )
        regime, instruments = instruments_for_society(society_id, state)

        profile = {}
        try:
            profile = db._execute(
                """SELECT name, primary_law, rules_version, model_bye_laws_version,
                          effective_from, status
                   FROM legal_regime_profiles WHERE code = :code""",
                {"code": regime}, fetch_one=True,
            ) or {}
        except Exception:
            profile = {}

        picked = normalize_state(state) if state else None
        out = [
            _render_banner(
                "UP AOA Compliance — Act / Rules / Bye-laws",
                f"The statutes governing this Apartment Owners' Association ({regime}"
                + (f", the State selected under Society Details" if picked else "")
                + "). This reference is maintained by Master and cannot be edited here — review it "
                "before submitting, and raise anything out of date through Master Portal → "
                "RWA Compliance (UP).",
            ),
        ]

        if profile:
            out.append(dbc.Card([
                dbc.CardBody([
                    html.H6([html.I(className="fas fa-scale-balanced me-2"),
                             profile.get("name") or regime],
                            className="text-primary mb-2", style={"fontWeight": "700", "fontSize": "13px"}),
                    html.Div([
                        html.Div([html.Small("Primary law", className="text-muted d-block"),
                                  html.Small(profile.get("primary_law") or "—")], className="sw-rule-sec"),
                        html.Div([html.Small("Rules", className="text-muted d-block"),
                                  html.Small(profile.get("rules_version") or "—")], className="sw-rule-sec"),
                        html.Div([html.Small("Model bye-laws", className="text-muted d-block"),
                                  html.Small(profile.get("model_bye_laws_version") or "—")], className="sw-rule-sec"),
                        html.Div([html.Small("Effective from", className="text-muted d-block"),
                                  html.Small(str(profile.get("effective_from") or "—"))], className="sw-rule-sec"),
                        html.Div([html.Small("Regime", className="text-muted d-block"),
                                  html.Small(regime),
                                  dbc.Badge(profile.get("status") or "active",
                                            color="success" if (profile.get("status") or "active") == "active" else "secondary",
                                            pill=True, style={"fontSize": "10px"})], className="sw-rule-sec"),
                    ], style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(190px, 1fr))", "gap": "10px"}),
                ])
            ], className="mb-3 shadow-sm border-0"))

        if not instruments:
            fallback = ("" if regime == "UP_AOA_2010" else
                        " Until Master seeds them, this society falls back to the generic "
                        "(Union-law) framework shown in the Acts & Rules column.")
            out.append(dbc.Alert(
                [html.H6([html.I(className="fas fa-database me-2"), f"No statutes on file for {regime}"],
                         className="alert-heading", style={"fontWeight": "700"}),
                 html.P(f"The {regime} regime has no Act / Rules / Bye-laws rows in "
                        f"legal_instrument_catalog yet.{fallback} Master can integrate them from "
                        "Master Portal → Settings → KPI Inspector → \"Integrate to DB\" — the SQL "
                        "is on Master Portal → RWA Compliance (UP).",
                        style={"fontSize": "13px", "marginBottom": "0"})],
                color="warning", className="mb-3 shadow-sm",
            ))
            return elements + out

        out.append(html.H6(
            f"{len(instruments)} statutory instrument{'s' if len(instruments) != 1 else ''} — {regime}",
            style={"fontWeight": "700", "color": "#15304f", "marginTop": "14px", "marginBottom": "8px", "fontSize": "13px"},
        ))

        for itype, items in grouped_instruments(instruments).items():
            out.append(html.H6(
                [dbc.Badge(itype, color=INSTRUMENT_BADGE_COLOR.get(itype, "light"), className="me-2"),
                 f"{len(items)} instrument{'s' if len(items) != 1 else ''}"],
                style={"marginTop": "14px", "marginBottom": "6px", "fontWeight": "700",
                       "color": "#15304f", "fontSize": "12.5px"},
            ))
            body_rows = []
            for r in items:
                year = f" ({r['enactment_year']})" if r.get("enactment_year") else ""
                body_rows.append(html.Tr([
                    html.Td([html.Strong(r["title"] + year, style={"fontSize": "11.5px"}),
                             html.Br(),
                             html.Small(r.get("issuing_authority") or "", className="text-muted")],
                            style={"maxWidth": "240px"}),
                    html.Td(html.Small(r.get("applicability") or "—"), style={"fontSize": "11px", "maxWidth": "200px"}),
                    html.Td(html.Small(r.get("key_provisions") or "—"), style={"fontSize": "11px", "maxWidth": "340px"}),
                    html.Td(dbc.Badge(r.get("status") or "active",
                                      color="success" if (r.get("status") or "active") == "active" else "secondary",
                                      pill=True), style={"fontSize": "10px"}),
                    html.Td(html.Small(r.get("source_reference") or "—", className="text-muted"),
                            style={"fontSize": "10px", "maxWidth": "200px"}),
                ]))
            out.append(dbc.Table([
                html.Thead(html.Tr([
                    html.Th("Instrument", style={"fontSize": "11px"}),
                    html.Th("Applicability", style={"fontSize": "11px"}),
                    html.Th("Key Provisions", style={"fontSize": "11px"}),
                    html.Th("Status", style={"fontSize": "11px"}),
                    html.Th("Source", style={"fontSize": "11px"}),
                ])),
                html.Tbody(body_rows),
            ], bordered=True, hover=True, responsive=True, size="sm", style={"fontSize": "12px"}))

        out.append(html.Small(
            "Superseded instruments are retained as history — check the Status column before relying on "
            "a provision. Last verified: "
            + str(max((r.get("last_verified_on") for r in instruments if r.get("last_verified_on")), default="not recorded")) + ".",
            className="text-muted d-block mt-2",
        ))
        return elements + out
    elif category == "Apartment Charges":
        s_amt, s_rate, s_due = 0.0, 0.0, 1
        s_sink, s_repair, s_int = DEFAULT_SINKING_FUND_RATE, DEFAULT_REPAIR_FUND_RATE, MAX_INTEREST_RATE_PCT
        if society_id:
            row = db._execute("SELECT apt_maintenance_amount, apt_maintenance_rate, apt_due_day, apt_sinking_fund_rate, apt_repair_fund_rate, apt_interest_pct FROM apt_charges_fines_basis WHERE society_id = :id AND apt_id IS NULL AND end_date IS NULL LIMIT 1", {"id": society_id}, fetch_one=True)
            if row:
                s_amt, s_rate, s_due = row.get("apt_maintenance_amount", 0.0) or 0.0, row.get("apt_maintenance_rate", 0.0) or 0.0, row.get("apt_due_day", 1) or 1
                # a stored 0 means "never set" on first-time setup, so fall back to the defaults
                s_sink = row.get("apt_sinking_fund_rate") or DEFAULT_SINKING_FUND_RATE
                s_repair = row.get("apt_repair_fund_rate") or DEFAULT_REPAIR_FUND_RATE
                s_int = min(row.get("apt_interest_pct") or MAX_INTEREST_RATE_PCT, MAX_INTEREST_RATE_PCT)
        return elements + [
            _render_banner("Apartment Charges", f"Set default charges, billing cycle day, sinking fund, and repair fund rates for all apartments. Defaults are pre-filled: Sinking Fund {DEFAULT_SINKING_FUND_RATE}, Repair Fund {DEFAULT_REPAIR_FUND_RATE}, interest capped at {MAX_INTEREST_RATE_PCT}%."),
            dbc.Row([dbc.Col([_label("Base Maintenance Amount"), dbc.Input(id="sw-apt-amt", type="number", value=s_amt, step=1, className="mb-3")], width=6), dbc.Col([_label("Maintenance Rate/SqFt"), dbc.Input(id="sw-apt-rate", type="number", value=s_rate, step=0.01, className="mb-3")], width=6)]),
            dbc.Row([dbc.Col([_label("Billing Due Day"), dbc.Input(id="sw-apt-due", type="number", value=s_due, min=1, max=31, step=1, className="mb-3")], width=4), dbc.Col([_label("Sinking Fund Rate"), dbc.Input(id="sw-apt-sink", type="number", value=s_sink, step=0.01, className="mb-3")], width=4), dbc.Col([_label("Repair Fund Rate"), dbc.Input(id="sw-apt-repair", type="number", value=s_repair, step=0.01, className="mb-3")], width=4)]),
            dbc.Row([dbc.Col([_label("Charges Interest Rate (%)"), dbc.Input(id="sw-apt-interest", type="number", value=s_int, min=0, max=MAX_INTEREST_RATE_PCT, step=0.01, className="mb-1"), html.Small(f"Maximum {MAX_INTEREST_RATE_PCT}%", className="text-muted d-block mb-3")], width=4)])
        ]
    elif category == "Vendor Charges":
        s_v1, s_v7, s_v30 = DEFAULT_VENDOR_1DAY, DEFAULT_VENDOR_7DAY, DEFAULT_VENDOR_1MTH
        if society_id:
            row = db._execute("SELECT vendor_1day, vendor_7day, vendor_1mth FROM ven_charges_fines_basis WHERE society_id = :id AND ven_id IS NULL AND end_date IS NULL LIMIT 1", {"id": society_id}, fetch_one=True)
            if row:
                s_v1 = row.get("vendor_1day") or DEFAULT_VENDOR_1DAY
                s_v7 = row.get("vendor_7day") or DEFAULT_VENDOR_7DAY
                s_v30 = row.get("vendor_1mth") or DEFAULT_VENDOR_1MTH
        return elements + [
            _render_banner("Vendor Charges", f"Set default vendor pass charges. Pre-filled: 1 Day ₹{DEFAULT_VENDOR_1DAY}, 7 Days ₹{DEFAULT_VENDOR_7DAY}, 1 Month ₹{DEFAULT_VENDOR_1MTH}."),
            dbc.Row([dbc.Col([_label("Vendor Pass (1 Day) ₹"), dbc.Input(id="sw-ven-1day", type="number", value=s_v1, step=1, className="mb-3")]), dbc.Col([_label("Vendor Pass (7 Days) ₹"), dbc.Input(id="sw-ven-7day", type="number", value=s_v7, step=1, className="mb-3")]), dbc.Col([_label("Vendor Pass (1 Month) ₹"), dbc.Input(id="sw-ven-1mth", type="number", value=s_v30, step=1, className="mb-3")])])
        ]
    elif category == "Accounts":
        s_calc = str(fy_start_date())
        if society_id:
            row = db._execute("SELECT calc_start_date FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
            if row and row.get("calc_start_date"): s_calc = str(row["calc_start_date"])
        from database.seed import ACCOUNTS
        inputs = [
            _render_banner("Accounts Settings", "Configure accounting start date and Payment QR Code."),
            html.P([html.B("Note: "), "The seeded account 'SBI A/c - Society' is set as your society's primary bank account. Every non-cash receipt and payment is booked to it, so the Society's payment QR code must belong to this bank. If your society banks elsewhere, change the primary bank account after setup (Admin portal, 'Settings' tab, 'Account' KPI)."], className="sw-note-red mb-3"),
            _label("Payment QR Code Image"),
            _render_image_capture_control("society", "pay_qr", _imgs.get("pay_qr"), society_id),
            _label("Accounting/Calculation Start Date"),
            dcc.DatePickerSingle(id="sw-calc-start-date", date=s_calc, display_format='YYYY-MM-DD', className="mb-4 d-block"),
            html.Hr(),
            html.H6("All Accounts (Seeded)", className="text-primary mb-3"),
        ]
        header = html.Div([
            _th("ID"), _th("Tab"), _th("Name"),
            _th("Dr/Cr", "drcr_account — whether the account normally carries a debit or credit balance."),
            _th("BF?", "has_bf — whether this account can carry a brought-forward opening balance."),
            _th("Depr?", "is_depreciable — whether depreciation is charged on this account."),
            _th("Depr %", "depreciation_percent — annual depreciation rate (100 = not depreciated)."),
        ], className="sw-grid-row sw-acc-grid sw-grid-head")

        # Group (sort) by parent_account_id (acc[4])
        sorted_accounts = sorted(ACCOUNTS, key=lambda x: (x[4] if x[4] is not None else -1, x[0]))
        rows = []
        for acc in sorted_accounts:
            # acc mapping: 0=id, 1=header, 2=tab, 3=name, 4=parent, 5=drcr, 6=has_bf, 7=depr_percent
            is_depreciable = acc[7] < 100 if acc[7] is not None else False
            rows.append(html.Div([
                html.Div(str(acc[0]), className="small text-muted"),
                html.Div(str(acc[2] or ""), className="small text-muted"),
                html.Div(str(acc[3] or ""), className="small fw-bold"),
                html.Div(str(acc[5] or ""), className="small text-muted"),
                html.Div("Yes" if acc[6] else "No", className="small text-muted"),
                html.Div("Yes" if is_depreciable else "No", className="small text-muted"),
                html.Div(f"{acc[7]}%" if acc[7] is not None else "", className="small text-muted"),
            ], className="sw-grid-row sw-acc-grid"))
        inputs.append(html.Div([header] + rows, className="sw-hscroll"))
        return elements + [html.Div(inputs, style={"paddingRight": "5px"})]
    elif category == "Brought Forward":
        s_fy = fy_start_year()
        if society_id:
            row = db._execute("SELECT financial_year FROM brought_forward WHERE society_id = :id LIMIT 1", {"id": society_id}, fetch_one=True)
            if row: s_fy = row.get("financial_year") or s_fy
        from database.seed import ACCOUNTS

        # Same shape as the Balance Sheet: Assets (Dr) on the left,
        # Liabilities + Equity/Reserves (Cr) on the right, each as a parent -> child tree.
        children = {}
        for acc in ACCOUNTS:
            children.setdefault(acc[4], []).append(acc)
        for kids in children.values():
            kids.sort(key=lambda a: a[0])

        def _has_bf(acc):
            return bool(acc[6]) or any(_has_bf(c) for c in children.get(acc[0], []))

        def _render_node(acc, depth):
            out = []
            indent = {"paddingLeft": f"{12 + depth * 14}px"}
            if acc[6]:   # postable account -> amount + remarks inputs (ids unchanged)
                out.append(html.Div([
                    html.Div([acc[3] or "", html.Small(f"{acc[2] or ''} · {acc[5] or ''}")], className="sw-bf-name"),
                    dbc.Input(id={"type": "sw-bf-amt", "acc_id": acc[0]}, type="number", value=0.0, step=0.01, min=0, size="sm"),
                    dbc.Input(id={"type": "sw-bf-remarks", "acc_id": acc[0]}, type="text", placeholder="Remarks...", size="sm", className="sw-bf-remarks"),
                ], className="sw-bf-row", style={**indent, "paddingRight": "12px"}))
            else:        # group heading
                out.append(html.Div(acc[3] or "", className="sw-bf-group", style=indent))
            for child in children.get(acc[0], []):
                if _has_bf(child):
                    out.extend(_render_node(child, depth + 1))
            return out

        def _side(title, subtitle, root_ids):
            body = []
            for rid in root_ids:
                root = next((a for a in ACCOUNTS if a[0] == rid), None)
                if root and _has_bf(root):
                    body.extend(_render_node(root, 0))
            return html.Div([
                html.Div([html.Span(title), html.Span(subtitle)], className="sw-bf-side-head"),
                *body,
            ], className="sw-bf-side")

        inputs = [
            _render_banner("Brought Forward", "Enter brought forward (opening balance) amounts for accounts. Values will be saved for the specified Financial Year."),
            _label("Financial Year (Start Year)"),
            dbc.Input(id="sw-bf-fy", type="number", value=s_fy, step=1, className="mb-3"),
            html.H6("Brought Forward Accounts", className="mt-4 mb-2 text-primary"),
            html.Div([
                _side("Assets", "Dr", [1000]),
                _side("Liabilities & Equity", "Cr", [2000, 3000]),
            ], className="sw-bf-grid"),
        ]
        return elements + [html.Div(inputs, style={"paddingRight": "5px"})]
    elif category == "Administrator":
        s_name, s_phone, s_email = "", "", ""
        if society_id:
            row = db._execute("SELECT secretary_name, secretary_phone, secretary_email FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
            if row:
                s_name, s_phone, s_email = row.get("secretary_name", "") or "", row.get("secretary_phone", "") or "", row.get("secretary_email", "") or ""
        return elements + [
            _render_banner("Administrator Details", "Configure Secretary details, digital signature, and your secure QR SIGNING_SECRET. This secret is required to authenticate generated QR codes."),
            html.H6("Secretary Details", className="text-primary mb-3"),
            _label("Secretary Name"),
            dbc.Input(id="sw-sec-name", type="text", value=s_name, className="mb-3"),
            _label("Secretary Phone"),
            dbc.Input(id="sw-sec-phone", type="tel", value=s_phone, className="mb-3"),
            _label("Secretary Email"),
            dbc.Input(id="sw-sec-email", type="email", value=s_email, className="mb-3"),
            _label("Secretary Signature Image"),
            _render_image_capture_control("society", "sec_sign", _imgs.get("sec_sign"), society_id),
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
            _label("SIGNING_SECRET (Strong Password)"),
            dbc.Input(id="sw-qr-secret", type="password", required=True, className="mb-3"),
            _field_feedback("sw-qr-secret-feedback"),
            _label("Confirm SIGNING_SECRET"),
            dbc.Input(id="sw-qr-secret-confirm", type="password", required=True, className="mb-3"),
            _field_feedback("sw-qr-secret-confirm-feedback"),
        ]
    elif category == "Instructions":
        here = os.path.dirname(os.path.abspath(__file__))
        # A12: show the short admin-facing quick start, not the 170 KB
        # developer README.
        readme_path = os.path.abspath(os.path.join(here, "../../../docs/ADMIN_QUICKSTART.md"))
        
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
                style={"backgroundColor": "#f8f9fa", "padding": "15px", "borderRadius": "5px", "border": "1px solid #ced4da", "marginBottom": "20px"}
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
                style={"backgroundColor": "#f8f9fa", "padding": "15px", "borderRadius": "5px", "border": "1px solid #ced4da", "marginBottom": "20px"}
            ),
            _label("Type 'I AGREE' below to proceed"),
            dbc.Input(id="sw-i-agree", type="text", placeholder="I AGREE", className="mb-4"),
            _field_feedback("sw-i-agree-feedback"),
            html.Hr(),
            html.P("Authorization required to submit setup.", className="fw-bold"),
            dbc.Row([
                dbc.Col([
                    _label("Admin Password"),
                    dbc.Input(id="sw-admin-password", type="password", placeholder="Your login password...", className="mb-3"),
                    _field_feedback("sw-admin-password-feedback")
                ], width=6),
                dbc.Col([
                    _label("SIGNING_SECRET"),
                    dbc.Input(id="sw-qr-confirm-final", type="password", placeholder="Enter the SIGNING_SECRET created in the Administrator tab...", className="mb-3"),
                    _field_feedback("sw-qr-confirm-final-feedback")
                ], width=6)
            ])
        ]
    return []

def get_setup_wizard_layout(society_id=None):
    return dbc.Modal(
        [
            dbc.ModalHeader(
                [
                    html.Div([
                        dbc.ModalTitle("EstateHub First-Time Setup Wizard", style={"fontWeight": "bold", "color": "#fff", "marginBottom": "2px"}),
                        html.Div(
                            "Jurisdiction-aware for Indian RWAs/CHS/AOAs — state-specific statutory rules apply automatically once your State is set (see Society Details)",
                            style={"color": "#ffffffcc", "fontSize": "11px"}
                        ),
                    ]),
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
                # One shell for every step: [sidebar] [content] [Acts & Rules].
                # Each column = pinned header | scrolling body (| pinned footer),
                # so nothing shifts between categories (see assets/setup_wizard.css).
                html.Div(className="sw-shell", children=[

                    # ── Column 1: sidebar ──────────────────────────────────
                    html.Div(className="sw-col sw-col-nav", children=[
                        html.Div(className="sw-col-head", children=[
                            html.H3([html.I(className="fas fa-magic me-2"), "Setup Wizard"],
                                    style={"color": "#667eea", "fontWeight": "bold", "fontSize": "1.5rem"}),
                        ]),
                        html.Div(className="sw-col-body", children=[
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
                            ),
                        ]),
                    ]),

                    # ── Column 2: step content ─────────────────────────────
                    html.Div(className="sw-col sw-col-content", children=[
                        html.Div(className="sw-col-head", children=[
                            html.H4(id="sw-category-title", children=CATEGORIES[0], style={"fontWeight": "bold"}),
                        ]),
                        html.Div(id="sw-category-content", className="sw-col-body", children=[
                            html.Div(
                                render_category_content(cat, society_id),
                                id={"type": "sw-step-container", "index": i},
                                style={"display": "block" if i == 0 else "none"}
                            ) for i, cat in enumerate(CATEGORIES)
                        ]),
                        html.Div(className="sw-col-foot", children=[
                            html.Div(id="sw-error-msg", style={"color": "red", "marginBottom": "8px"}),
                            html.Div(
                                [
                                    dbc.Button("Previous", id="sw-btn-prev", color="secondary", className="me-2", disabled=True),
                                    dbc.Button("Next", id="sw-btn-next", color="primary", className="me-2"),
                                    dbc.Button("Submit Setup", id="sw-btn-submit", color="success", style={"display": "none"})
                                ],
                                style={"textAlign": "right"}
                            ),
                        ]),
                    ]),

                    # ── Column 3: Acts & Rules ─────────────────────────────
                    html.Div(className="sw-col sw-col-rules", children=[
                        html.Div(className="sw-col-head", children=[
                            html.H5([html.I(className="fas fa-book me-2"), "Acts & Rules"], style={"fontWeight": "bold", "color": "#2c3e50"}),
                            html.Small(id="sw-rules-subtitle", children=rules_subtitle(CATEGORIES[0], society_id), className="text-muted"),
                        ]),
                        html.Div(id="sw-compliance-rules-panel", className="sw-col-body",
                                 children=build_rules_panel(CATEGORIES[0], society_id),
                                 style={"fontSize": "12.5px", "color": "#3a4a5c"}),
                    ]),
                ]),
                id="setup-wizard-modal-body",
                style={
                    "--login-bg": "url(/static/assets/EH_bk.jpg)",
                    "backgroundSize": "cover",
                    "backgroundPosition": "center",
                    "minHeight": "650px",
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
