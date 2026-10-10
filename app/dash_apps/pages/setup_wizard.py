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

# Legal hierarchy labels for the regime selection step
LEGAL_HIERARCHY = [
    ("Central Act", "Income Tax Act, 1961; GST Act, 2017; RERA Act, 2016", "locked"),
    ("State Act", "UP Apartment Act, 2010 (or applicable state act)", "locked"),
    ("AOA Rules", "UP Apartment Rules, 2011 (or applicable state rules)", "locked"),
    ("Model Bye-laws", "UP Model Bye-Laws, 2011 (notified 16 Nov 2011)", "provisional"),
    ("Society Adopted Bye-laws", "Clauses adopted / varied by General Body resolution", "provisional"),
    ("Resolutions (Passed/Enacted)", "General Body / EGM resolutions activating choices", "provisional"),
    ("Board Meetings", "Management Committee operational decisions", "provisional"),
]

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
    "Legal Regime": ["Legal Regime Selection"],
    "Central Acts": ["Central Acts Compliance", "TAN & TDS Rates", "GSTIN & GST Rate"],
    "State Act & Rules": ["State Act & Rules", "Model Bye-Laws Adoption"],
    "Society Policy": ["Apartment Charges", "Vendor Charges", "Society Operations"],
    "Accounts": ["Accounts Heads", "Brought Forward"],
    "Finalization": ["Review", "Agreement"]
}
CATEGORIES = [
    'Instructions',
    'Society Details',
    'Administrator',
    'Legal Regime Selection',
    'Central Acts Compliance',
    'TAN & TDS Rates',
    'GSTIN & GST Rate',
    'State Act & Rules',
    'Model Bye-Laws Adoption',
    'Apartment Charges',
    'Vendor Charges',
    'Society Operations',
    'Accounts Heads',
    'Brought Forward',
    'Review',
    'Agreement'
]

CATEGORY_ICONS = {
    "Society Details": "fas fa-building",
    "Administrator": "fas fa-user-shield",
    "Instructions": "fas fa-info-circle",
    "Legal Regime Selection": "fas fa-sitemap",
    "Central Acts Compliance": "fas fa-landmark",
    "State Act & Rules": "fas fa-university",
    "Model Bye-Laws Adoption": "fas fa-scale-balanced",
    "TAN & TDS Rates": "fas fa-percent",
    "GSTIN & GST Rate": "fas fa-file-invoice-dollar",
    "Apartment Charges": "fas fa-home",
    "Vendor Charges": "fas fa-truck",
    "Society Operations": "fas fa-cogs",
    "Accounts Heads": "fas fa-book",
    "Brought Forward": "fas fa-arrow-right",
    "Review": "fas fa-clipboard-check",
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


def _render_tds_rates_table():
    """Render the TDS rates table for Central Acts Compliance and TAN & TDS Rates steps."""
    from database.seed import TDS_SECTION_RATE_SEED
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
    return html.Div([header] + rows, className="sw-hscroll")


def _society_state(society_id):
    if not society_id:
        return None
    try:
        row = db._execute("SELECT state FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
        return (row or {}).get("state") or None
    except Exception:
        return None


def fund_flags(society_id=None, state=None):
    """Which fund inputs the wizard should ask for.

    A fund is asked for only if the state PRESCRIBES it (statutory) or the
    admin opted in on the Bye-Laws Adoption step (levy_*_fund = 'yes'). Under
    UP_AOA_2010 neither Sinking nor Repair has a statutory rate, so by default
    neither is asked for. The Corpus Fund is never a setup input.
    """
    from app.services.statutory_rules import fund_rules_for_state
    from app.services import regime_rules_admin as rra
    rules = fund_rules_for_state(state if state else _society_state(society_id))

    def levied(fund):
        if rules[fund]["mode"] == "statutory":
            return True
        return bool(society_id) and rra.policy_intent(society_id, f"levy_{fund}_fund") == "yes"

    return {"rules": rules, "sinking": levied("sinking"), "repair": levied("repair")}


def fund_note(flags, regime):
    """One-line explanation shown above the fund fields."""
    r = flags["rules"]
    if r["sinking"]["mode"] == "statutory" or r["repair"]["mode"] == "statutory":
        return (f"{regime} prescribes minimum Sinking / Repair fund rates "
                f"(sinking {r['sinking']['min_pct']}% , repair {r['repair']['min_pct']}% of construction cost per year).")
    if flags["sinking"] or flags["repair"]:
        return f"{regime} sets no statutory rate; these funds are levied by your General Body resolution (Bye-Laws Adoption step)."
    return (f"{regime} does not prescribe a Sinking or Repair fund. None is being levied. To levy one, opt in on the "
            "Bye-Laws Adoption step (Funds & assessments).")


def regime_badge(state_code):
    """Society Details: which legal regime the picked State puts the society under."""
    from app.services.statutory_rules import (regime_for_society, state_has_own_regime, regime_profile)
    if not state_code:
        return html.Small("Select a State to see the governing legal regime.", className="text-muted")
    regime = regime_for_society(None, state_code)
    name, status = regime_profile(regime)
    own = state_has_own_regime(state_code)
    parts = [dbc.Badge(regime, color="primary" if own else "secondary", className="me-2"), html.Span(name, className="small")]
    if status == "draft":
        parts.append(dbc.Badge("draft", color="warning", text_color="dark", className="ms-2"))
    if not own:
        parts.append(html.Div("No dedicated regime is seeded for this state yet. UP_AOA_2010 is shown as a reference only; "
                              "confirm applicable law with an advocate.", className="small text-warning mt-1"))
    return html.Div(parts)


def state_thresholds_rows(state_code):
    """Society Compliance: thresholds for ALL-India plus only the picked state (was: every state's)."""
    from database.seed import STATE_COMPLIANCE_THRESHOLDS
    from app.services.statutory_rules import normalize_state
    st = normalize_state(state_code)
    rows = []
    for (state, key, val, val_text, unit, eff_from, eff_to, notes) in STATE_COMPLIANCE_THRESHOLDS:
        if state not in ("ALL", st) or eff_to is not None:
            continue
        rows.append(dbc.Row([dbc.Col(html.B(state), width=1), dbc.Col(html.Span(key, className="small text-muted"), width=3),
                             dbc.Col(html.Span(val if val is not None else (val_text or "no floor"), className="small fw-bold"), width=2),
                             dbc.Col(html.Span(unit or "", className="small text-muted"), width=1),
                             dbc.Col(html.Span(notes or "", className="small text-muted"), width=5)], className="mb-2"))
    return rows


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
    if category in ["Central Acts Compliance", "State Act & Rules", "Model Bye-Laws Adoption", "TAN & TDS Rates", "Accounts Heads"]:
        elements.append(
            html.Div([
                dbc.Button([html.I(className="fas fa-print me-2"), "Print / Open in New Window"], 
                           id={"type": "sw-print-btn", "cat": category}, 
                           color="outline-secondary", size="sm")
            ], style={"textAlign": "right", "marginBottom": "15px"})
        )

    if category == "Society Details":
        s_name, s_addr, s_pan, s_reg, s_phone, s_email, s_gate_logic, s_duty_hrs, s_state, s_constitution = "", "", "", "", "", "", "both", "8", "", "AOA"
        if society_id:
            row = db._execute("SELECT name, address, phone, email, PAN_number, registration_number, gate_logic, duty_hrs, state, constitution FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
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
                s_constitution = row.get("constitution", "AOA") or "AOA"
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
        constitution_options = [
            {"label": "Apartment Owners' Association (AOA)", "value": "AOA"},
            {"label": "Registered Society (REG_SOCIETY)", "value": "REG_SOCIETY"},
            {"label": "Co-operative Housing Society (COOP)", "value": "COOP"},
            {"label": "Generic / Other", "value": "GENERIC"},
        ]
        return elements + [
            _render_banner("Society Details", "Enter society identity details. State + Constitution together select the legal regime. Registration Number, Email, and Phone will be updated if provided. Logo and Background images are optional."),
            _label("Society Name"),
            dbc.Input(id="sw-society-name", type="text", required=True, className="mb-3", value=s_name, readonly=True, style={"opacity": "0.7", "backgroundColor": "#e9ecef"}),
            _label("Society Logo (Image)"),
            _render_image_capture_control("society", "logo", _imgs.get("logo"), society_id),
            _label("Address"),
            dbc.Textarea(id="sw-society-address", required=True, className="mb-3", value=s_addr),
            _field_feedback("sw-society-address-feedback"),
            _label("State", html_for="sw-society-state"),
            dbc.Select(id="sw-society-state", options=state_options, value=s_state, className="mb-1"),
            _label("Constitution", html_for="sw-society-constitution"),
            dbc.Select(id="sw-society-constitution", options=constitution_options, value=s_constitution, className="mb-3"),
            html.Div(id="sw-regime-badge", children=regime_badge(s_state), className="mb-2"),
            html.P(
                "State + Constitution together select the legal regime (Central Act → State Act → Rules → Model Bye-laws). "
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
            _label("Login Background (Image)"),
            _render_image_capture_control("society", "bg", _imgs.get("bg"), society_id),
        ]
    elif category == "Legal Regime Selection":
        from app.services.statutory_rules import regime_for_society, regime_profile, state_has_own_regime, normalize_state
        picked_state = state or _society_state(society_id)
        picked_constitution = ""
        if society_id:
            row = db._execute("SELECT constitution FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
            if row:
                picked_constitution = row.get("constitution", "AOA") or "AOA"
        regime = regime_for_society(society_id, picked_state)
        name, status = regime_profile(regime)
        own = state_has_own_regime(picked_state)
        
        hierarchy_rows = []
        for label, desc, badge_type in LEGAL_HIERARCHY:
            if badge_type == "locked":
                badge = dbc.Badge(label, color="primary", className="me-2", pill=True, style={"fontSize": "10px"})
            else:
                badge = dbc.Badge(label, color="warning", className="me-2", pill=True, style={"fontSize": "10px"})
            hierarchy_rows.append(html.Tr([
                html.Td(badge),
                html.Td(desc, style={"fontSize": "12px"}),
                html.Td(dbc.Badge(badge_type.capitalize(), color="secondary" if badge_type == "locked" else "info", pill=True, style={"fontSize": "9px"})),
            ]))
        
        return elements + [
            _render_banner("Legal Regime Selection", "Your State and Constitution together determine the legal regime. The hierarchy below shows how rules flow — a lower layer can never loosen a higher one."),
            html.Div([
                html.H6([html.I(className="fas fa-sitemap me-2"), f"Active Regime: {regime}"], className="text-primary mb-3"),
                html.Div([
                    dbc.Badge(regime, color="primary" if own else "secondary", className="me-2"),
                    html.Span(name, className="small"),
                ], className="mb-2"),
                html.Small(f"This regime is {'active' if own else 'a fallback (UP reference)'} — confirm applicable law with an advocate if not a dedicated regime." if not own else "", className="text-muted d-block mb-3"),
                html.H6("Legal Hierarchy (Precedence Order)", className="text-primary mt-3 mb-2"),
                dbc.Table([
                    html.Thead(html.Tr([
                        html.Th("Layer", style={"fontSize": "11px", "width": "150px"}),
                        html.Th("Instrument", style={"fontSize": "11px"}),
                        html.Th("Status", style={"fontSize": "11px", "width": "120px"}),
                    ])),
                    html.Tbody(hierarchy_rows),
                ], bordered=True, hover=True, size="sm", style={"fontSize": "12px"}),
            ]),
            html.Hr(),
            html.H6("Central Act Settings", className="text-primary mt-3 mb-2"),
            html.P("The following Central Acts apply to all societies. Configure the rates and applicability for your society:", className="text-muted small mb-3"),
            dbc.Row([
                dbc.Col([
                    _label("Income Tax — TAN Required?"),
                    dbc.RadioItems(id="sw-central-it-tan", options=[{"label": "Yes", "value": True}, {"label": "No", "value": False}], value=True, inline=True, className="mb-3"),
                ], width=6),
                dbc.Col([
                    _label("TDS Applicable?"),
                    dbc.RadioItems(id="sw-central-tds", options=[{"label": "Yes", "value": True}, {"label": "No", "value": False}], value=True, inline=True, className="mb-3"),
                ], width=6),
            ]),
            dbc.Row([
                dbc.Col([
                    _label("GST Applicable?"),
                    dbc.RadioItems(id="sw-central-gst", options=[{"label": "Yes", "value": True}, {"label": "No", "value": False}], value=False, inline=True, className="mb-3"),
                ], width=6),
                dbc.Col([
                    _label("RERA Applicable?"),
                    dbc.RadioItems(id="sw-central-rera", options=[{"label": "Yes", "value": True}, {"label": "No", "value": False}], value=False, inline=True, className="mb-3"),
                ], width=6),
            ]),
        ]
    elif category == "Central Acts Compliance":
        from app.services.statutory_rules import regime_for_society
        regime = regime_for_society(society_id, state)
        
        s_tan = ""
        if society_id:
            row = db._execute("SELECT tan_number FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
            if row:
                s_tan = row.get("tan_number") or ""
        
        return elements + [
            _render_banner("Central Acts Compliance", f"Configure Income Tax, GST, and RERA settings for {regime}. These Central Acts apply uniformly across India."),
            html.H6("Income Tax Act, 1961 — TAN & TDS", className="text-primary mb-3"),
            _label("TAN Number"),
            dbc.Input(id="sw-society-tan", type="text", placeholder="Enter TAN (e.g. ABCD12345E)...", value=s_tan, className="mb-4"),
            _label("TDS Effective Date"),
            html.Div(dcc.DatePickerSingle(
                id="sw-tds-effective-date",
                date=str(fy_start_date()),
                display_format="YYYY-MM-DD"
            ), className="mb-4"),
            html.Hr(),
            html.H6("TDS Section Rates", className="text-primary mb-3"),
            html.P("Standard rates are pre-filled. Modify only if your CA advises.", className="text-muted small mb-3"),
            _render_tds_rates_table(),
        ]
    elif category == "State Act & Rules":
        from app.services.statutory_rules import regime_for_society, instruments_for_society, grouped_instruments, INSTRUMENT_BADGE_COLOR, fund_rules_for_state
        from app.services import regime_rules_admin as rra
        regime, instruments = instruments_for_society(society_id, state)
        _ff = fund_flags(society_id, state)
        fund_rules = fund_rules_for_state(state)
        
        # Show the State Act instruments
        instrument_rows = []
        for itype, items in grouped_instruments(instruments).items():
            instrument_rows.append(html.Tr([
                html.Td(dbc.Badge(itype, color=INSTRUMENT_BADGE_COLOR.get(itype, "light"), pill=True, style={"fontSize": "10px"})),
                html.Td(items[0]["title"] + (f" ({items[0]['enactment_year']})" if items[0].get("enactment_year") else ""), style={"fontSize": "11px", "fontWeight": "600"}),
            ]))
            for r in items[1:]:
                instrument_rows.append(html.Tr([
                    html.Td(""),
                    html.Td(html.Small("· " + r["title"] + (f" ({r['enactment_year']})" if r.get("enactment_year") else ""), className="text-muted", style={"fontSize": "10px"})),
                ]))
        
        # Fund prescriptions
        fund_rows = []
        for fund_key in ["sinking", "repair"]:
            rule = fund_rules[fund_key]
            if rule["mode"] == "statutory":
                fund_rows.append(html.Tr([
                    html.Td(f"{fund_key.capitalize()} Fund", style={"fontWeight": "600"}),
                    html.Td(f"Statutory minimum: {rule['min_pct']}% of construction cost per year"),
                    html.Td(dbc.Badge("Mandatory", color="danger", pill=True, style={"fontSize": "9px"})),
                ]))
            elif _ff[fund_key]:
                fund_rows.append(html.Tr([
                    html.Td(f"{fund_key.capitalize()} Fund", style={"fontWeight": "600"}),
                    html.Td("Opted in via Bye-Laws Adoption step"),
                    html.Td(dbc.Badge("Optional (levied)", color="warning", pill=True, style={"fontSize": "9px"})),
                ]))
            else:
                fund_rows.append(html.Tr([
                    html.Td(f"{fund_key.capitalize()} Fund", style={"fontWeight": "600"}),
                    html.Td("Not prescribed by state; not opted in"),
                    html.Td(dbc.Badge("Not levied", color="secondary", pill=True, style={"fontSize": "9px"})),
                ]))
        
        return elements + [
            _render_banner("State Act & Rules", f"Review the State Act and Rules governing this society ({regime}). These are read-only — maintained by Master. The statutory fund rates prescribed by your state are shown below."),
            html.H6("State Instruments", className="text-primary mt-3 mb-2"),
            dbc.Table([
                html.Thead(html.Tr([html.Th("Type", style={"fontSize": "11px"}), html.Th("Instrument", style={"fontSize": "11px"})])),
                html.Tbody(instrument_rows),
            ], bordered=True, hover=True, size="sm", style={"fontSize": "12px"}),
            html.H6("Fund Prescriptions", className="text-primary mt-3 mb-2"),
            html.Small(fund_note(_ff, regime), className="text-muted d-block mb-2"),
            dbc.Table([
                html.Thead(html.Tr([html.Th("Fund", style={"fontSize": "11px"}), html.Th("Rule", style={"fontSize": "11px"}), html.Th("Status", style={"fontSize": "11px"})])),
                html.Tbody(fund_rows),
            ], bordered=True, hover=True, size="sm", style={"fontSize": "12px"}),
        ]
    elif category == "Model Bye-Laws Adoption":
        from app.services import regime_rules_admin as rra
        from app.services.statutory_rules import regime_for_society
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
        pol_rows, fund_pol_rows = [], []
        _ff = fund_flags(society_id, state)
        for key, (label, clause, choices) in rra.POLICY_SPECS.items():
            if key in rra.FUND_POLICY_KEYS:
                fund = "sinking" if "sinking" in key else "repair" if "repair" in key else None
                if fund and _ff["rules"][fund]["mode"] == "statutory":
                    continue
            st = pol.get(key) or {"value": choices[0][0], "active": False, "proposed": None}
            shown = st["proposed"] or st["value"]
            (fund_pol_rows if key in rra.FUND_POLICY_KEYS else pol_rows).append(html.Tr([
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
            html.H6("Funds & assessments", className="mt-3 mb-1"),
            html.Small(fund_note(_ff, regime_for_society(society_id, state)),
                       className="text-muted d-block mb-2", id="sw-fund-note"),
            dbc.Table([html.Thead(html.Tr([html.Th(h, style={"fontSize": "11px"}) for h in ("Setting", "Choice", "Status")])),
                       html.Tbody(fund_pol_rows)], bordered=True, size="sm") if fund_pol_rows else html.Div(),
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
    elif category == "Model Bye-Laws Adoption":
        # The society's bye-law register: for each Model Bye-Law 2011 clause the admin notes the intended outcome
        # (adopt as-is / adopt with variation / not adopted). Every choice is PROVISIONAL: it is stored with
        # proposed_status and changes nothing in the engine until the passed GBM resolution is recorded
        # (Admin → Settings → Society governance → Meetings & Resolutions), which activates it automatically.
        # A clause nobody touches is governed by the Model
        # Bye-Laws / Act as-is. Persistence is immediate, by callback (sw-bl-*), not on wizard submit.
        from app.services import regime_rules_admin as rra
        from app.services.statutory_rules import regime_for_society
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
        pol_rows, fund_pol_rows = [], []
        _ff = fund_flags(society_id, state)
        for key, (label, clause, choices) in rra.POLICY_SPECS.items():
            if key in rra.FUND_POLICY_KEYS:
                fund = "sinking" if "sinking" in key else "repair" if "repair" in key else None
                # a prescribed fund is not a choice: no opt-in row, and its basis is fixed by the state rule
                if fund and _ff["rules"][fund]["mode"] == "statutory":
                    continue
            st = pol.get(key) or {"value": choices[0][0], "active": False, "proposed": None}
            shown = st["proposed"] or st["value"]
            (fund_pol_rows if key in rra.FUND_POLICY_KEYS else pol_rows).append(html.Tr([
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
            html.H6("Funds & assessments", className="mt-3 mb-1"),
            html.Small(fund_note(_ff, regime_for_society(society_id, state)),
                       className="text-muted d-block mb-2", id="sw-fund-note"),
            dbc.Table([html.Thead(html.Tr([html.Th(h, style={"fontSize": "11px"}) for h in ("Setting", "Choice", "Status")])),
                       html.Tbody(fund_pol_rows)], bordered=True, size="sm") if fund_pol_rows else html.Div(),
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
    elif category == "Apartment Charges":
        s_amt, s_rate, s_due = 0.0, 0.0, 1
        s_billing_basis = "per_sqft"
        _ff = fund_flags(society_id, state)
        # The 0.25 / 0.75 defaults are Maharashtra's statutory minimum percentages, so they are only a
        # sensible pre-fill where the state prescribes the fund; elsewhere the fund starts at 0 (not levied).
        s_sink = DEFAULT_SINKING_FUND_RATE if _ff["rules"]["sinking"]["mode"] == "statutory" else 0.0
        s_repair = DEFAULT_REPAIR_FUND_RATE if _ff["rules"]["repair"]["mode"] == "statutory" else 0.0
        s_int = MAX_INTEREST_RATE_PCT
        if society_id:
            row = db._execute("SELECT apt_maintenance_amount, apt_maintenance_rate, apt_due_day, apt_sinking_fund_rate, apt_repair_fund_rate, apt_interest_pct, billing_basis FROM apt_charges_fines_basis WHERE society_id = :id AND apt_id IS NULL AND end_date IS NULL LIMIT 1", {"id": society_id}, fetch_one=True)
            if row:
                s_amt, s_rate, s_due = row.get("apt_maintenance_amount", 0.0) or 0.0, row.get("apt_maintenance_rate", 0.0) or 0.0, row.get("apt_due_day", 1) or 1
                s_billing_basis = row.get("billing_basis", "per_sqft") or "per_sqft"
                # a stored 0 means "never set" on first-time setup, so fall back to the defaults
                s_sink = row.get("apt_sinking_fund_rate") or s_sink
                s_repair = row.get("apt_repair_fund_rate") or s_repair
                s_int = min(row.get("apt_interest_pct") or MAX_INTEREST_RATE_PCT, MAX_INTEREST_RATE_PCT)
        return elements + [
            _render_banner("Apartment Charges", "Set default charges, billing cycle day and late-payment interest (capped at " + str(MAX_INTEREST_RATE_PCT) + "%). "
                           "Sinking / Repair fund rates appear only where your state prescribes them or you opted in on the Bye-Laws Adoption step."),
            dbc.Row([
                dbc.Col([_label("Base Maintenance Amount"), dbc.Input(id="sw-apt-amt", type="number", value=s_amt, step=1, className="mb-3")], width=4),
                dbc.Col([_label("Maintenance Rate/SqFt"), dbc.Input(id="sw-apt-rate", type="number", value=s_rate, step=0.01, className="mb-3")], width=4),
                dbc.Col([_label("Maintenance Billing Basis"), dbc.Select(id="sw-apt-billing-basis", options=[
                    {"label": "Per Sq Ft", "value": "per_sqft"},
                    {"label": "Undivided Interest (Construction Cost)", "value": "undivided_interest"},
                    {"label": "Fixed Amount per Apartment", "value": "fixed"},
                ], value=s_billing_basis, className="mb-3")], width=4),
            ]),
            dbc.Row([
                dbc.Col([_label("Billing Due Day"), dbc.Input(id="sw-apt-due", type="number", value=s_due, min=1, max=31, step=1, className="mb-3")], width=4),
                dbc.Col([_label("Sinking Fund Rate"), dbc.Input(id="sw-apt-sink", type="number", value=s_sink, step=0.01, className="mb-3")], id="sw-apt-sink-col", width=4, style={} if _ff["sinking"] else {"display": "none"}),
                dbc.Col([_label("Repair Fund Rate"), dbc.Input(id="sw-apt-repair", type="number", value=s_repair, step=0.01, className="mb-3")], id="sw-apt-repair-col", width=4, style={} if _ff["repair"] else {"display": "none"}),
            ]),
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
    elif category == "Society Operations":
        s_gate_logic, s_duty_hrs = "both", "8"
        if society_id:
            row = db._execute("SELECT gate_logic, duty_hrs FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
            if row:
                s_gate_logic = row.get("gate_logic", "both") or "both"
                s_duty_hrs = row.get("duty_hrs", "8") or "8"
        return elements + [
            _render_banner("Society Operations", "Configure gate pass enforcement, security duty hours, and vendor pass charges."),
            html.H6("Gate Pass & Security", className="text-primary mb-3"),
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
            html.Hr(),
            html.H6("Vendor Pass Charges", className="text-primary mb-3"),
            dbc.Row([
                dbc.Col([_label("Vendor Pass (1 Day) ₹"), dbc.Input(id="sw-ven-1day", type="number", value=DEFAULT_VENDOR_1DAY, step=1, className="mb-3")], width=4),
                dbc.Col([_label("Vendor Pass (7 Days) ₹"), dbc.Input(id="sw-ven-7day", type="number", value=DEFAULT_VENDOR_7DAY, step=1, className="mb-3")], width=4),
                dbc.Col([_label("Vendor Pass (1 Month) ₹"), dbc.Input(id="sw-ven-1mth", type="number", value=DEFAULT_VENDOR_1MTH, step=1, className="mb-3")], width=4),
            ]),
        ]
    elif category == "Accounts Heads":
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
        # Fetch existing data from DB for review
        society_data = {}
        compliance_data = {}
        apt_charges = {}
        vendor_charges = {}
        bf_data = {}
        if society_id:
            society_data = db._execute("SELECT * FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True) or {}
            compliance_data = db._execute("SELECT * FROM society_compliance_settings WHERE society_id = :id", {"id": society_id}, fetch_one=True) or {}
            apt_charges = db._execute("SELECT * FROM apt_charges_fines_basis WHERE society_id = :id AND apt_id IS NULL AND end_date IS NULL LIMIT 1", {"id": society_id}, fetch_one=True) or {}
            vendor_charges = db._execute("SELECT * FROM ven_charges_fines_basis WHERE society_id = :id AND ven_id IS NULL AND end_date IS NULL LIMIT 1", {"id": society_id}, fetch_one=True) or {}
            bf_data = db._execute("SELECT * FROM brought_forward WHERE society_id = :id", {"id": society_id}, fetch_all=True) or []
        
        # Get bye-law adoption status
        bye_law_status = []
        policy_status = []
        if society_id:
            from app.services import regime_rules_admin as rra
            try:
                for r in rra.list_society_bye_laws(society_id):
                    if r["layer"] == 1 and r["status"] == "provisional":
                        bye_law_status.append(f"{r['clause_id']}: {r['proposed_status'].replace('_', ' ').title()}")
                for k, v in rra.list_society_policies(society_id).items():
                    if v["proposed"]:
                        policy_status.append(f"{k}: {v['proposed']} (awaiting resolution)")
            except Exception:
                pass
        
        review_sections = [
            ("Society Identity", [
                ("Society Name", society_data.get("name", "—")),
                ("State", society_data.get("state", "—")),
                ("Constitution", society_data.get("constitution", "—")),
                ("PAN", society_data.get("pan_number", "—")),
                ("Registration No.", society_data.get("registration_number", "—")),
                ("Email", society_data.get("email", "—")),
                ("Phone", society_data.get("phone", "—")),
            ]),
            ("Central Acts Configuration", [
                ("Income Tax - TAN Required", "Yes" if society_data.get("tan_number") else "No"),
                ("TDS Applicable", "Yes" if compliance_data.get("gst_registered") else "No"),  # placeholder
                ("GST Registered", "Yes" if compliance_data.get("gst_registered") else "No"),
                ("RERA Applicable", "No"),  # placeholder
            ]),
            ("State Act & Funds", [
                ("Sinking Fund", "Levied" if apt_charges.get("apt_sinking_fund_rate") else "Not levied"),
                ("Repair Fund", "Levied" if apt_charges.get("apt_repair_fund_rate") else "Not levied"),
                ("Maintenance Billing Basis", apt_charges.get("billing_basis", "per_sqft")),
            ]),
            ("Apartment Charges", [
                ("Base Maintenance Amount", f"₹{apt_charges.get('apt_maintenance_amount', 0):,.2f}"),
                ("Maintenance Rate/SqFt", f"₹{apt_charges.get('apt_maintenance_rate', 0):,.2f}"),
                ("Billing Due Day", apt_charges.get("apt_due_day", 1)),
                ("Interest Rate", f"{apt_charges.get('apt_interest_pct', 1.75)}%"),
            ]),
            ("Vendor Charges", [
                ("1 Day Pass", f"₹{vendor_charges.get('vendor_1day', 100):,.0f}"),
                ("7 Day Pass", f"₹{vendor_charges.get('vendor_7day', 500):,.0f}"),
                ("1 Month Pass", f"₹{vendor_charges.get('vendor_1mth', 2000):,.0f}"),
            ]),
            ("Society Operations", [
                ("Gate Pass Enforcement", society_data.get("gate_logic", "both").title()),
                ("Security Duty Hours", f"{society_data.get('duty_hrs', '8')} hours"),
            ]),
            ("Administrator", [
                ("Secretary Name", society_data.get("secretary_name", "—")),
                ("Secretary Email", society_data.get("secretary_email", "—")),
                ("Secretary Phone", society_data.get("secretary_phone", "—")),
            ]),
        ]
        
        def _section_card(title, items):
            rows = []
            for label, value in items:
                rows.append(html.Tr([
                    html.Td(html.Strong(label), style={"width": "30%", "fontSize": "12px"}),
                    html.Td(str(value), style={"fontSize": "12px"}),
                ]))
            return dbc.Card([
                dbc.CardHeader(html.H6(title, className="mb-0", style={"fontSize": "13px"})),
                dbc.CardBody([
                    dbc.Table([
                        html.Tbody(rows)
                    ], bordered=False, size="sm", style={"fontSize": "12px", "marginBottom": "0"}),
                ], className="py-2"),
            ], className="mb-3 shadow-sm")
        
        # Pending ratification checklist
        ratification_items = []
        if bye_law_status:
            ratification_items.append(html.Li([html.Strong("Bye-Law Adoptions: "), html.Br(), html.Ul([html.Li(item, style={"fontSize": "11px"}) for item in bye_law_status])]))
        if policy_status:
            ratification_items.append(html.Li([html.Strong("Society Policies: "), html.Br(), html.Ul([html.Li(item, style={"fontSize": "11px"}) for item in policy_status])]))
        if not ratification_items:
            ratification_items = [html.Li("No pending ratifications — all choices are either not set or already backed by resolutions.", className="text-muted", style={"fontSize": "12px"})]
        
        return elements + [
            _render_banner("Review & Confirm", "Review all settings below. Items marked 'awaiting resolution' require a General Body meeting and passed resolution to take effect in the engine."),
            html.Div([_section_card(title, items) for title, items in review_sections]),
            html.H6("Pending Ratification Checklist", className="text-primary mt-3 mb-2"),
            html.P("The following provisional choices need a General Body resolution to become active:", className="text-muted small mb-2"),
            html.Ul(ratification_items, style={"fontSize": "12px"}),
            html.Hr(),
            dbc.Alert([
                html.I(className="fas fa-info-circle me-2"),
                "After reviewing, proceed to the Agreement step to accept the terms and submit the setup."
            ], color="info", className="mt-3"),
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
