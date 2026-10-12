import os

from dash import html, dcc, Input, Output, State, ALL, callback, no_update
from app.utils.fiscal import fy_start_date, fy_start_year
import dash_bootstrap_components as dbc
from database.db_manager import db


# ── Defaults requested for first-time setup ────────────────────────────────
DEFAULT_SINKING_FUND_RATE = 0.25    # ₹ per sq ft / month
DEFAULT_REPAIR_FUND_RATE  = 0.75    # ₹ per sq ft / month
DEFAULT_INTEREST_RATE_PCT = 1.75    # pre-filled, EDITABLE late-payment interest (% per month, simple interest)
# There is no hard cap in the wizard: the rate is whatever the General Body resolved.
INTEREST_RATE_NOTE = ("Simple interest, % per month, on overdue dues after the Billing Due Day. "
                      "UP Model Bye-Laws 2011, bye-law 46(a): the rate is set by General Body resolution.")
# Case name + citation to print under the interest field. Left None until a verified citation is supplied.
INTEREST_CASE_CITATION = None
DEFAULT_VENDOR_1DAY, DEFAULT_VENDOR_7DAY, DEFAULT_VENDOR_1MTH = 100, 500, 2000

# Legal hierarchy rows are built from the society's regime: see legal_hierarchy_rows()

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
    "Charges Interest Rate (% per month)": "Simple interest per month on overdue dues. The rate is the one your General Body resolved (UP Model Bye-Laws 2011, bye-law 46(a)).",
    "Construction Cost of Project (₹)": "Total construction cost of the project. Recorded for fund percentages and the Declaration; it is not billed as maintenance.",
    "Monthly Common-Expense Budget (₹)": "Society's monthly common-expense budget. Under Undivided Interest billing each flat pays this x its undivided-interest %.",
    "Default Rate per sq ft (₹)": "Monthly maintenance per sq ft of apartment area. Needed when the billing basis is Per Sq Ft.",
    "Default Fixed Amount (₹)": "Flat monthly maintenance per apartment. Needed when the billing basis is Fixed Amount.",
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
            "'State Act & Rules' step.",
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
# conversation.xlsx is a binary file; corrected wording lives here so the fix is reviewable as text.
CONVERSATION_TEXT_OVERRIDES = {
    "Vendor Charges": ("Set the price of Vendor Passes (1-day, 7-day, 1-month) that vendors pay to work in the society. "
                       "These are pass prices, not penalties or fines. Match them to your vendor policy."),
}
REVIEW_STEP_NAME = "Review"
WIZARD_GROUPS = {
    "Organization Details": ["Instructions", "Society Details", "Administrator"],
    "Legal Regime": ["Legal Regime Selection"],
    # Central Acts are not a choice: they apply to every society, so they are a read-only banner on
    # "Legal Regime Selection". Only the two steps that need figures (TAN/TDS, GSTIN/GST) remain here.
    "Central Acts": ["TAN & TDS Rates", "GSTIN & GST Rate"],
    "State Act & Rules": ["State Act & Rules", "Model Bye-Laws Adoption"],
    "Society Policy": ["Apartment Charges", "Funds", "Vendor Charges", "Society Operations"],
    "Accounts": ["Accounts Heads", "Brought Forward"],
    "Finalization": ["Review", "Agreement"]
}
CATEGORIES = [
    'Instructions',
    'Society Details',
    'Administrator',
    'Legal Regime Selection',
    'TAN & TDS Rates',
    'GSTIN & GST Rate',
    'State Act & Rules',
    'Model Bye-Laws Adoption',
    'Apartment Charges',
    'Funds',
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
    "State Act & Rules": "fas fa-university",
    "Model Bye-Laws Adoption": "fas fa-scale-balanced",
    "TAN & TDS Rates": "fas fa-percent",
    "GSTIN & GST Rate": "fas fa-file-invoice-dollar",
    "Apartment Charges": "fas fa-home",
    "Funds": "fas fa-piggy-bank",
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


def _central_acts_banner():
    """Read-only table of the Central Acts (Layer 0). Nothing here is entered or chosen: figures go on the
    'TAN & TDS Rates' and 'GSTIN & GST Rate' steps. Wording is deliberately conservative: the Income-tax Act, 2025
    replaced the 1961 Act from 1 April 2026, and this app's section references still follow the 1961 Act."""
    return dbc.Table([
        html.Thead(html.Tr([html.Th("Central Act"), html.Th("What it means for your society"), html.Th("Where you enter it")])),
        html.Tbody([
            html.Tr([html.Td("Income-tax Act, 2025 (in force 1 April 2026; replaced the Income-tax Act, 1961)"),
                     html.Td(["TAN, TDS on payments to vendors and contractors, and the mutuality position. ",
                              html.Strong("Section references in this app still follow the 1961 Act"),
                              " - your CA must re-map them for FY 2026-27 onward."]),
                     html.Td("TAN & TDS Rates step (skipped if you answered TDS = No)")]),
            html.Tr([html.Td("Central GST Act, 2017, and the UP GST Act, 2017 (state law mirroring it)"),
                     html.Td("GST on maintenance above the per-member threshold, and reverse charge (RCM)."),
                     html.Td("GSTIN & GST Rate step (skipped if you answered GST = No)")]),
            html.Tr([html.Td("Real Estate (Regulation and Development) Act, 2016"),
                     html.Td("Applies to registered projects and to the promoter's duties up to handover (maintenance until the "
                             "association takes over, handover of common areas). It is not a compliance category for the "
                             "association's own accounts."),
                     html.Td("Nothing to enter")]),
        ]),
    ], bordered=True, size="sm", style={"fontSize": "12.5px"})


def _render_tds_rates_table():
    """Render the TDS rates table for the TAN & TDS Rates step."""
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


FUND_NAMES = {
    "sinking": "Sinking Fund",
    "repair": "Repair & Maintenance Fund",
    "reserve": "Reserve Fund",
    "major_repair": "Major Repair Fund",
    "ifms_corpus": "IFMS Corpus",
}
FUND_MODE_LABELS = {"on_bill": "On every maintenance bill", "fy_close": "At year close, from surplus", "none": "Not collected"}
FUND_BASIS_LABELS = {"per_sq_ft": "Per sq ft of apartment area", "construction_cost": "% of construction cost per year, shared by undivided interest",
                     "undivided_interest": "Society's monthly fund amount, shared by undivided interest"}
FUND_BASES = ("per_sq_ft", "construction_cost", "undivided_interest")


# UP AOA Fund definitions with statutory basis
UP_AOA_FUNDS = {
    "ifms_corpus": {
        "name": "IFMS Corpus",
        "statutory": True,
        "source": "UP Apartment Act 2010, Sec 14(5)",
        "description": "Interest-Free Maintenance Security Corpus — builder handover corpus; one-time receipt, not a recurring rate.",
        "rate_applicable": False,
    },
    "major_repair": {
        "name": "Major Repair Fund",
        "statutory": True,
        "source": "Model Bye-Laws 2011, bye-law 39",
        "description": "½% of transfer value on sale, payable by seller. Not a recurring rate — levied per transfer.",
        "rate_applicable": False,
    },
    "reserve": {
        "name": "Reserve Fund",
        "statutory": True,
        "source": "Model Bye-Laws 2011, bye-laws 3(1)(d) and 46; Act Sec 14(8)(a)",
        "description": "Common profits nucleus — appropriated from net surplus at FY close (default 25%, configurable).",
        "rate_applicable": False,
    },
    "sinking": {
        "name": "Sinking Fund",
        "statutory": False,
        "source": "Not prescribed by UP Apartment Act 2010 or Model Bye-Laws 2011; levied by General Body resolution",
        "description": "Voluntary fund for structural overhauls, lifts, DG sets. Rate and basis set by society policy.",
        "rate_applicable": True,
    },
    "repair": {
        "name": "Repair & Maintenance Fund",
        "statutory": False,
        "source": "UP Apartment Act 2010 s.18 (common expenses by undivided interest); Model Bye-Laws 2011 bye-law 35/36",
        "description": "Routine upkeep of common areas. Rate and basis set by society policy.",
        "rate_applicable": True,
    },
}


def fund_effective(statutory, regime_mode, regime_basis, levy, collection, basis_pick):
    """(mode, basis) a fund ends up with. Mirrors the SQL function fn_fund_rule, so what the wizard asks for is what
    the billing engine will do once the General Body resolution is recorded.

      statutory   : the state prescribes the fund -> on every bill, shared by construction cost, no resolution needed
      collection / basis_pick : the society's choice, or 'regime_default' to keep the regime's default
      levy        : 'yes' = the society opts in; 'no' leaves the fund uncollected unless the regime itself bills on the bill
    """
    if statutory:
        return "on_bill", "construction_cost"
    mode, basis = regime_mode or "none", regime_basis or "none"
    if collection in ("on_bill", "fy_close", "none"):
        mode = collection
    elif levy == "yes":
        if mode == "none":
            mode = "on_bill"
    elif mode != "on_bill":
        mode = "none"
    if basis_pick in FUND_BASES:
        basis = basis_pick
    if mode == "on_bill" and basis not in FUND_BASES:
        basis = "per_sq_ft"
    return mode, basis


def fund_rate_label(basis):
    return {"per_sq_ft": "Rate (₹ per sq ft per month)",
            "construction_cost": "Rate (% of project construction cost per year)",
            "undivided_interest": "Monthly fund amount for the whole society (₹)"}.get(basis, "Rate")


def fund_plan(society_id=None, state=None, chosen=None):
    """Per fund: is it prescribed or optional, and the mode / basis it ends up with.

    `chosen` ({policy_key: value}) overrides what is stored: the Funds step passes the live drop-down values so the
    screen follows the admin's clicks; everything else reads the saved (provisional or active) choice."""
    from app.services.statutory_rules import fund_rules_for_state, fund_collection_for_regime, scheme_for
    from app.services import regime_rules_admin as rra
    picked_state = state if state else _society_state(society_id)
    rules = fund_rules_for_state(picked_state)
    constitution = None
    if society_id:
        _row = db._execute("SELECT constitution FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
        constitution = (_row or {}).get("constitution")
    regime = scheme_for(picked_state, constitution)      # the scheme the billing engine will use
    reg_mode, reg_basis = fund_collection_for_regime(regime)
    chosen = chosen or {}

    def pick(key):
        if key in chosen and chosen[key]:
            return chosen[key]
        return rra.policy_intent(society_id, key) if society_id else rra.policy_default(key)

    plan = {}
    for fund in ("sinking", "repair"):
        statutory = rules[fund]["mode"] == "statutory"
        mode, basis = fund_effective(statutory, reg_mode, reg_basis, pick(f"levy_{fund}_fund"),
                                     pick(f"{fund}_fund_collection"), pick(f"{fund}_fund_basis"))
        plan[fund] = {"statutory": statutory, "min_pct": rules[fund]["min_pct"], "mode": mode, "basis": basis,
                      "levy": pick(f"levy_{fund}_fund"), "regime_mode": reg_mode, "regime_basis": reg_basis}
    return {"rules": rules, "regime": regime, "plan": plan,
            "sinking": plan["sinking"]["mode"] == "on_bill", "repair": plan["repair"]["mode"] == "on_bill"}


def fund_flags(society_id=None, state=None):
    """Which fund RATE inputs the wizard should ask for: a fund needs a rate only if it is collected on the bill.
    (Kept for existing callers; the full answer, with mode and basis, is fund_plan().)"""
    p = fund_plan(society_id, state)
    return {"rules": p["rules"], "sinking": p["sinking"], "repair": p["repair"], "plan": p["plan"], "regime": p["regime"]}


def funds_error(plan, sink_rate, repair_rate, project_cost):
    """First problem in the fund answers, or None. A fund collected on every bill needs a rate above 0 (and at least the
    statutory minimum where the state prescribes one); a construction-cost basis needs the project's construction cost."""
    for fund, rate in (("sinking", sink_rate), ("repair", repair_rate)):
        f = plan[fund]
        if f["mode"] != "on_bill":
            continue
        try:
            r = float(rate or 0)
        except (TypeError, ValueError):
            r = 0.0
        name = FUND_NAMES[fund]
        if r <= 0:
            return f"Funds: the {name} is collected on every bill, so its rate is required (above 0)."
        if f["statutory"] and f["min_pct"] is not None and r < float(f["min_pct"]):
            return f"Funds: the {name} rate is below the statutory minimum of {f['min_pct']}% of construction cost per year."
        if f["basis"] == "construction_cost":
            try:
                ok = float(project_cost or 0) > 0
            except (TypeError, ValueError):
                ok = False
            if not ok:
                return f"Funds: the {name} is shared by construction cost, so enter the Construction Cost of Project on Apartment Charges."
    return None


def fund_hint(f, regime):
    """Sentence under a fund's rate field, for the fund's current mode / basis."""
    from app.services.statutory_rules import regime_reserve_pct
    if f["mode"] == "none":
        return "Not collected."
    if f["mode"] == "fy_close":
        return (f"Nothing is added to the monthly bill. The reserve is built at financial-year close: {regime_reserve_pct(regime):g}% of net surplus "
                "goes to the Reserve Fund as one collective pool (a General Body resolution can change the share).")
    return {"per_sq_ft": "Billed with every maintenance bill: area x this rate.",
            "construction_cost": "Billed with every maintenance bill: project construction cost x this rate ÷ 12, shared by each flat's undivided-interest %.",
            "undivided_interest": "Billed with every maintenance bill: this amount shared by each flat's undivided-interest %."}[f["basis"]]


def fund_note(flags, regime):
    """One-line explanation shown above the fund fields."""
    r = flags["rules"]
    if r["sinking"]["mode"] == "statutory" or r["repair"]["mode"] == "statutory":
        return (f"{regime} prescribes minimum Sinking / Repair fund rates "
                f"(sinking {r['sinking']['min_pct']}% , repair {r['repair']['min_pct']}% of construction cost per year).")
    from app.services.statutory_rules import fund_collection_for_regime
    mode, basis = fund_collection_for_regime(regime)   # regime default, before the society's own choice on the Funds step
    if mode == "fy_close":
        return (f"{regime}: no fixed Sinking / Repair fund rate was found, so by default nothing is added to the monthly bill. "
                "Reserves are built from the year's surplus at financial-year close. To levy a fund on every bill instead, opt in on the "
                "Model Bye-Laws Adoption step (Funds & assessments); a rate entered here is billed only once that General Body resolution is recorded.")
    if mode == "none":
        return f"{regime} collects no Sinking or Repair fund. None is being levied."
    if flags["sinking"] or flags["repair"]:
        return (f"{regime} sets no statutory rate; these funds are added to each monthly bill at the rate you enter, "
                f"shared by default {basis.replace('_', ' ')}. Choose the basis on the Model Bye-Laws Adoption step.")
    return (f"{regime} does not prescribe a Sinking or Repair fund. None is being levied. To levy one, opt in on the "
            "Model Bye-Laws Adoption step (Funds & assessments).")


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


# ── Apartment Charges: society-default billing basis ───────────────────────
BILLING_BASIS_OPTIONS = [
    {"label": "Undivided Interest (monthly budget x flat's % of undivided interest)", "value": "undivided_interest"},
    {"label": "Per Sq Ft (rate x apartment area)", "value": "per_sqft"},
    {"label": "Fixed Amount per Apartment", "value": "fixed"},
]
BASIS_NEEDS = {   # basis -> (field label, key)
    "undivided_interest": ("Monthly Common-Expense Budget (₹)", "budget"),
    "per_sqft": ("Default Rate per sq ft (₹)", "rate"),
    "fixed": ("Default Fixed Amount (₹)", "amt"),
}


def apt_charges_error(basis, budget, rate, amt):
    """Message if the field the chosen billing basis needs is missing or 0, else None."""
    need = BASIS_NEEDS.get(basis or "undivided_interest")
    if not need:
        return "Apartment Charges: choose a Maintenance Billing Basis."
    label, key = need
    try:
        ok = float({"budget": budget, "rate": rate, "amt": amt}[key] or 0) > 0
    except (TypeError, ValueError):
        ok = False
    if not ok:
        return f"Apartment Charges: '{label}' is required (above 0) for the selected billing basis."
    return None


def basis_hint(basis):
    label, _ = BASIS_NEEDS.get(basis or "undivided_interest", BASIS_NEEDS["undivided_interest"])
    extra = (" Each flat also needs its undivided-interest % (area share is used until the Declaration figures are entered after enrolment)."
             if (basis or "undivided_interest") == "undivided_interest" else "")
    return dbc.Alert([html.I(className="fas fa-hand-point-up me-2"), html.Strong("Required for this basis: "), label + "." + extra],
                     color="warning", className="py-2 mb-3", style={"fontSize": "12.5px"})


# ── Legal Hierarchy: instruments as links ─────────────────────────────────
_UNVERIFIED_URLS = {"https://indiankanoon.org/doc/1987654321/"}   # placeholder-looking seed ID, never surface


def _usable_url(url):
    u = (url or "").strip()
    return u if u.lower().startswith(("http://", "https://")) and u not in _UNVERIFIED_URLS else None


def _instrument_link(title, url, year=None):
    text = title + (f" ({year})" if year else "")
    u = _usable_url(url)
    if not u:
        return html.Span(text)
    return html.A([text, html.I(className="fas fa-external-link-alt ms-1", style={"fontSize": "9px"})],
                  href=u, target="_blank", rel="noopener noreferrer")


def legal_hierarchy_rows(society_id=None, state=None):
    """Body rows of the Legal Hierarchy table, driven by the society's regime (no hard-coded state)."""
    from app.services.statutory_rules import instruments_for_society, grouped_instruments, normalize_state
    st = normalize_state(state or _society_state(society_id))
    regime, instruments = instruments_for_society(society_id, st)
    groups = grouped_instruments(instruments)
    try:
        from app.services.kpi_rule_links_service import get_links_for_categories
        central_links = get_links_for_categories(["central_acts"], state=st).get("central_acts", [])
    except Exception:
        central_links = []

    def items(types):
        out = []
        for t in types:
            for r in groups.get(t, []):
                out.append(html.Div(_instrument_link(r["title"], r.get("source_url"), r.get("enactment_year")), className="mb-1"))
        return out

    central = items(("Central Act", "Central Rules"))
    if not central:   # catalog has no Central Act rows: use the official-portal links
        central = [html.Div(_instrument_link(l.label.split(" — ")[0], l.url), className="mb-1") for l in central_links]
    pending = html.Small("link pending verification", className="text-muted")
    state_act = items(("Act",)) or [html.Span(f"No {regime} Act in the catalog yet.", className="text-muted")]
    rules = items(("Rules", "Notification")) or [html.Span(f"No {regime} Rules in the catalog yet.", className="text-muted")]
    model_bl = items(("Bye-laws",)) or [html.Span(f"No {regime} Model Bye-laws in the catalog yet.", className="text-muted")]
    try:
        from app.services import regime_rules_admin as _rra
        _dts = {d["code"]: d for d in _rra.list_decision_types()}
    except Exception:
        _dts = {}

    def _maj(code):
        """'66.67% of all votes (provisional)' for a decision type, read from decision_types (single source)."""
        d = _dts.get(code)
        if not d:
            return "see Settings > Society governance"
        tag = "" if d.get("verification") == "verified" else " (provisional - confirm with your advocate)"
        if d["required_body"] == "GBM":
            return f"{float(d['majority_pct']):g}% of all votes, by undivided interest{tag}"
        return f"simple majority of the committee{tag}"

    def _note(text):
        return html.Div(html.Small(text, className="text-muted"))

    rows = [
        ("L0 - Central Acts", central + [_note("Income-tax, GST, RERA. Apply to every society; not a choice.")], "locked"),
        ("L0 - State Act", state_act, "locked"),
        ("L0 - Rules", rules, "locked"),
        ("L0 - Model Bye-laws (notified)", model_bl + [_note("Made by the Governor under the Act; a society makes its bye-laws in accordance with them.")], "locked"),
        ("L1 - Society Bye-laws", [html.Span("The Model Bye-laws as adopted or varied by the General Body on the "),
                                  html.Strong("Model Bye-Laws Adoption"), html.Span(" step. Adopting or varying: "),
                                  html.Span(_maj("ADOPT_BYE_LAW")), html.Span(". A clause may be recorded as not adopted only on "
                                  "a written advocate's opinion, and never if the Act or Rules back it.")], "provisional"),
        ("L2 - Society Policy / GBM Resolutions", [html.Span("Policy: "), html.Span(_maj("SET_SOCIETY_POLICY")),
                                                  html.Span(". Ordinary General Body resolution: "), html.Span(_maj("GENERAL_RESOLUTION")),
                                                  html.Span(", with quorum. Recorded under "), html.Strong("Settings > Society governance > Meetings & Resolutions"),
                                                  html.Span(". A policy may tighten, never loosen, the layer above it.")], "provisional"),
        ("L3 - Board / Working Committee", [html.Span("Operational limits decided by the committee: "), html.Span(_maj("SET_BOARD_PARAM")),
                                           html.Span(", then placed before the General Body for ratification. Recorded under "),
                                           html.Strong("Settings > Society governance"), html.Span(".")], "provisional"),
    ]
    out = []
    for label, body, badge_type in rows:
        out.append(html.Tr([
            html.Td(dbc.Badge(label, color="primary" if badge_type == "locked" else "warning", className="me-2", pill=True, style={"fontSize": "10px"})),
            html.Td(body, style={"fontSize": "12px"}),
            html.Td(dbc.Badge(badge_type.capitalize(), color="secondary" if badge_type == "locked" else "info", pill=True, style={"fontSize": "9px"})),
        ]))
    return out


def _yn(v):
    return "Yes" if v else "No"


def render_review(v, society_id=None):
    """Review step body built from the LIVE form values `v` (dict), not from the database.

    Nothing is saved until Submit, so reading the database here could only ever show defaults or blanks.
    Name / PAN / Registration are Master-owned, so they come from the database."""
    v = v or {}
    db_s = {}
    if society_id:
        db_s = db._execute("SELECT name, pan_number, registration_number FROM societies WHERE id = :id",
                           {"id": society_id}, fetch_one=True) or {}

    def num(x, d=0.0):
        try:
            return float(x if x not in (None, "") else d)
        except (TypeError, ValueError):
            return d

    def rs(x):
        return f"₹{num(x):,.2f}"

    basis = v.get("apt_basis") or "undivided_interest"
    basis_label = {o["value"]: o["label"] for o in BILLING_BASIS_OPTIONS}.get(basis, basis)
    problems = []
    for label, val in (("Address", v.get("address")), ("Email", v.get("email")), ("Phone", v.get("phone"))):
        if not str(val or "").strip():
            problems.append(f"{label} is empty (Society Details).")
    if not v.get("state"):
        problems.append("State is not selected (Society Details): the legal regime cannot be assigned.")
    err = apt_charges_error(basis, v.get("apt_budget"), v.get("apt_rate"), v.get("apt_amt"))
    if err:
        problems.append(err)
    if v.get("central_tds") and not str(v.get("tan") or "").strip():
        problems.append("TDS applies but no TAN is entered (TAN & TDS Rates).")
    if v.get("central_gst") and not str(v.get("gstin") or "").strip():
        problems.append("GST applies but no GSTIN is entered (GSTIN & GST Rate).")
    if not str(v.get("sec_name") or "").strip():
        problems.append("Secretary name is empty (Administrator).")

    # Brought Forward totals
    bf_dr = bf_cr = 0.0
    bf_n = 0
    try:
        from database.seed import ACCOUNTS
        drcr = {a[0]: a[5] for a in ACCOUNTS}
        for acc_id, amt in zip(v.get("bf_ids") or [], v.get("bf_amts") or []):
            a = num(amt)
            if a:
                bf_n += 1
                if drcr.get(acc_id) == "Dr":
                    bf_dr += a
                else:
                    bf_cr += a
    except Exception:
        pass
    if bf_n and abs(bf_dr - bf_cr) > 0.005:
        problems.append(f"Brought Forward does not balance: Dr ₹{bf_dr:,.2f} vs Cr ₹{bf_cr:,.2f}. Submit will reject it.")

    from database.seed import TDS_SECTION_RATE_SEED
    rates = v.get("tds_rates") or []
    tds_edited = sum(1 for i, item in enumerate(TDS_SECTION_RATE_SEED)
                     if i < len(rates) and rates[i] is not None and abs(num(rates[i]) - num(item[3])) > 1e-9)

    fund_rows = []
    try:
        fp = fund_plan(society_id, v.get("state"), v.get("pol") or {})
        for fund, rate in (("sinking", v.get("apt_sink")), ("repair", v.get("apt_repair"))):
            f = fp["plan"][fund]
            status = "Prescribed by the state" if f["statutory"] else ("Opted in" if f["mode"] != "none" else "Not collected")
            fund_rows.append((FUND_NAMES[fund], f"{status}; {FUND_MODE_LABELS[f['mode']].lower()}"))
            if f["mode"] == "on_bill":
                fund_rows.append((f"  {FUND_NAMES[fund]} basis and rate", f"{FUND_BASIS_LABELS[f['basis']]}: {num(rate):g}"))
        _fe = funds_error(fp["plan"], v.get("apt_sink"), v.get("apt_repair"), v.get("apt_cost"))
        if _fe:
            problems.append(_fe)
    except Exception:
        fund_rows = [("Funds", "-")]

    sections = [
        ("Society Identity", [
            ("Society Name (Master)", db_s.get("name") or "—"),
            ("PAN (Master)", db_s.get("pan_number") or "—"),
            ("Registration No. (Master)", db_s.get("registration_number") or "— (ask Master to enter it)"),
            ("State", v.get("state") or "—"),
            ("Constitution", v.get("constitution") or "—"),
            ("Address", v.get("address") or "—"),
            ("Email", v.get("email") or "—"),
            ("Phone", v.get("phone") or "—"),
        ]),
        ("Central Acts", [
            ("Income Tax - TAN required", _yn(v.get("central_it_tan"))),
            ("TDS applicable", _yn(v.get("central_tds"))),
            ("GST applicable", _yn(v.get("central_gst"))),
            ("RERA applicable", _yn(v.get("central_rera"))),
        ]),
        ("TAN & TDS", [
            ("TAN", v.get("tan") or "—"),
            ("TDS effective date", v.get("tds_date") or "—"),
            ("TDS rate rows changed from standard", tds_edited),
        ]),
        ("GST", [
            ("GSTIN", v.get("gstin") or "—"),
            ("CGST / SGST", f"{num(v.get('cgst')):g}% / {num(v.get('sgst')):g}%"),
        ]),
        ("Apartment Charges (society default)", [
            ("Maintenance Billing Basis", basis_label),
            ("Construction Cost of Project", rs(v.get("apt_cost"))),
            ("Monthly Common-Expense Budget", rs(v.get("apt_budget"))),
            ("Default Rate per sq ft", rs(v.get("apt_rate"))),
            ("Default Fixed Amount", rs(v.get("apt_amt"))),
            ("Billing Due Day", v.get("apt_due") or "—"),
            ("Sinking Fund Rate", num(v.get("apt_sink"))),
            ("Repair Fund Rate", num(v.get("apt_repair"))),
            ("Interest (% per month, simple)", f"{num(v.get('apt_interest')):g}%"),
        ]),
        ("Funds (Sinking / Repair)", fund_rows),
        ("Vendor Pass Charges", [
            ("1 Day Pass", f"₹{num(v.get('ven1')):,.0f}"),
            ("7 Day Pass", f"₹{num(v.get('ven7')):,.0f}"),
            ("1 Month Pass", f"₹{num(v.get('ven30')):,.0f}"),
        ]),
        ("Society Operations", [
            ("Gate Pass Enforcement", str(v.get("gate") or "—").title()),
            ("Security Duty Hours", f"{v.get('duty') or '—'} hours"),
        ]),
        ("Administrator", [
            ("Secretary Name", v.get("sec_name") or "—"),
            ("Secretary Email", v.get("sec_email") or "—"),
            ("Secretary Phone", v.get("sec_phone") or "—"),
        ]),
        ("Accounts & Brought Forward", [
            ("Accounting start date", v.get("calc_start") or "—"),
            ("Brought Forward financial year", v.get("bf_fy") or "—"),
            ("Accounts with an opening balance", bf_n),
            ("Total Dr / Total Cr", f"₹{bf_dr:,.2f} / ₹{bf_cr:,.2f}"),
        ]),
    ]

    def card(title, items):
        rows = [html.Tr([html.Td(html.Strong(k), style={"width": "34%", "fontSize": "12px"}),
                         html.Td(str(val), style={"fontSize": "12px"})]) for k, val in items]
        return dbc.Card([dbc.CardHeader(html.H6(title, className="mb-0", style={"fontSize": "13px"})),
                         dbc.CardBody(dbc.Table([html.Tbody(rows)], bordered=False, size="sm", style={"marginBottom": "0"}), className="py-2")],
                        className="mb-3 shadow-sm")

    # Bye-law / policy choices ARE saved instantly (provisional), so the database is the right source for these.
    bye_law_status, policy_status = [], []
    if society_id:
        try:
            from app.services import regime_rules_admin as rra
            for r in rra.list_society_bye_laws(society_id):
                if r["layer"] == 1 and r["status"] == "provisional":
                    bye_law_status.append(f"{r['clause_id']}: {r['proposed_status'].replace('_', ' ').title()}")
            for k, pv in rra.list_society_policies(society_id).items():
                if pv["proposed"]:
                    policy_status.append(f"{k}: {pv['proposed']} (awaiting resolution)")
        except Exception:
            pass
    ratification = []
    if bye_law_status:
        ratification.append(html.Li([html.Strong("Bye-Law Adoptions: "), html.Ul([html.Li(i, style={"fontSize": "11px"}) for i in bye_law_status])]))
    if policy_status:
        ratification.append(html.Li([html.Strong("Society Policies: "), html.Ul([html.Li(i, style={"fontSize": "11px"}) for i in policy_status])]))
    if not ratification:
        ratification = [html.Li("No pending ratifications.", className="text-muted", style={"fontSize": "12px"})]

    attention = (dbc.Alert([html.Strong("Fix before you submit:"), html.Ul([html.Li(x) for x in problems], className="mb-0")], color="danger", className="py-2")
                 if problems else dbc.Alert("Nothing missing in the steps checked above.", color="success", className="py-2"))
    return [
        _render_banner("Review & Confirm", "These are the values currently on screen. Nothing is saved until you Submit on the Agreement step."),
        attention,
        html.Div([card(t, i) for t, i in sections]),
        html.H6("Pending Ratification Checklist", className="text-primary mt-3 mb-2"),
        html.P("These provisional choices need a General Body resolution to become active:", className="text-muted small mb-2"),
        html.Ul(ratification, style={"fontSize": "12px"}),
    ]


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
        _conv_text = CONVERSATION_TEXT_OVERRIDES.get(category) or conv_info.get('Recommendation from Master to Admin')
        if _conv_text:
            elements.append(
                dbc.Alert(
                    [html.I(className="fas fa-lightbulb me-2"), _conv_text],
                    color="info",
                    className="mb-3",
                    style={"fontSize": "13px"}
                )
            )
        
    # Add Print Button for specific categories
    if category in ["State Act & Rules", "Model Bye-Laws Adoption", "TAN & TDS Rates", "Accounts Heads"]:
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
            {"label": "Apartment Owners' Association (AOA) - UP Apartment Act, 2010", "value": "AOA"},
            {"label": "Registered Society - Societies Registration Act, 1860 (as amended in UP)", "value": "REG_SOCIETY"},
            {"label": "Co-operative Housing Society - UP Co-operative Societies Act", "value": "COOP"},
            {"label": "Generic / Other (central laws only)", "value": "GENERIC"},
        ]
        return elements + [
            _render_banner("Society Details", "Enter society identity details. State + Constitution together select the legal regime. Name, PAN and Registration Number are set by Master and cannot be edited here. Logo and Background images are optional."),
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
                "State + Constitution together select the legal regime (Central Acts → State Act → Rules → Model Bye-laws → "
                "Society Bye-laws → Policy / Resolutions → Board). In UP an AOA is itself registered as a society; "
                "the Apartment Act applies on top. "
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
            dbc.Input(id="sw-society-reg", type="text", className="mb-1", value=s_reg, readonly=True, style={"opacity": "0.7", "backgroundColor": "#e9ecef"}),
            html.Small("Entered by Master. Contact Master to change it." if s_reg else "Not entered yet. Ask Master to add your registration number.", className="text-muted d-block mb-3"),
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
        
        hierarchy_rows = legal_hierarchy_rows(society_id, picked_state)
        
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
            html.H6([html.I(className="fas fa-landmark me-2"), "Central Acts (Layer 0 - apply to every society, not a choice)"], className="text-primary mt-3 mb-2"),
            _central_acts_banner(),
            html.H6("Central Act Settings", className="text-primary mt-3 mb-2"),
            html.P("The Acts above apply to every society whatever you answer. What depends on your society's facts is whether a duty "
                   "under them has been triggered (a GST registration threshold, TDS on payments you make). All answers default to Yes; "
                   "answer No only on your CA's advice. TDS = No hides the TAN & TDS Rates step and GST = No hides the GSTIN & GST Rate step:", className="text-muted small mb-3"),
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
                    dbc.RadioItems(id="sw-central-gst", options=[{"label": "Yes", "value": True}, {"label": "No", "value": False}], value=True, inline=True, className="mb-3"),
                ], width=6),
                dbc.Col([
                    _label("RERA - is the project RERA-registered? (handover rules only)"),
                    dbc.RadioItems(id="sw-central-rera", options=[{"label": "Yes", "value": True}, {"label": "No", "value": False}], value=True, inline=True, className="mb-3"),
                ], width=6),
            ]),
        ]
    elif category == "State Act & Rules":
        from app.services.statutory_rules import regime_for_society, instruments_for_society, grouped_instruments, INSTRUMENT_BADGE_COLOR, fund_rules_for_state
        from app.services import regime_rules_admin as rra
        from app.dash_apps.pages.setup_wizard import fund_flags
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
                    html.Td("Opted in via Model Bye-Laws Adoption step"),
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
        from app.dash_apps.pages.setup_wizard import fund_flags
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
            if key in rra.FUND_STEP_POLICY_KEYS:
                continue                      # asked on the Funds step
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
            html.Small("Whether and how a Sinking or Repair fund is collected is asked on the Funds step.",
                       className="text-muted d-block mb-2"),
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
    elif category == "Apartment Charges":
        s_amt, s_rate, s_due, s_cost, s_budget = 0.0, 0.0, 1, 0.0, 0.0
        s_billing_basis = "undivided_interest"        # society default; apartments can override at enrolment
        s_int = DEFAULT_INTEREST_RATE_PCT
        if society_id:
            row = db._execute("SELECT apt_maintenance_amount, apt_maintenance_rate, apt_due_day, apt_sinking_fund_rate, apt_repair_fund_rate, apt_interest_pct, billing_basis, project_construction_cost, common_expense_budget_monthly FROM apt_charges_fines_basis WHERE society_id = :id AND apt_id IS NULL AND end_date IS NULL LIMIT 1", {"id": society_id}, fetch_one=True)
            if row:
                s_amt, s_rate, s_due = row.get("apt_maintenance_amount", 0.0) or 0.0, row.get("apt_maintenance_rate", 0.0) or 0.0, row.get("apt_due_day", 1) or 1
                s_billing_basis = row.get("billing_basis") or "undivided_interest"
                s_cost = row.get("project_construction_cost") or 0.0
                s_budget = row.get("common_expense_budget_monthly") or 0.0
                s_int = row.get("apt_interest_pct") if row.get("apt_interest_pct") is not None else s_int
        citation = [html.Small(INTEREST_CASE_CITATION, className="text-muted d-block mb-3")] if INTEREST_CASE_CITATION else []
        return elements + [
            _render_banner("Apartment Charges", "Set the SOCIETY DEFAULT charges, billing day and late-payment interest. "
                           "Sinking and Repair funds are set on the next step (Funds)."),
            dbc.Alert([html.I(className="fas fa-info-circle me-2"),
                       "These are the society defaults. Apartments can differ: an individual apartment can be given its own billing basis and amounts when you enrol it."],
                      color="info", className="py-2 mb-3", style={"fontSize": "12.5px"}),
            html.H6("Part A: Society defaults (all optional, fill what you know)", className="text-primary mb-2"),
            dbc.Row([
                dbc.Col([_label("Construction Cost of Project (₹)"), dbc.Input(id="sw-apt-cost", type="number", value=s_cost, min=0, step=1, className="mb-3")], width=3),
                dbc.Col([_label("Monthly Common-Expense Budget (₹)"), dbc.Input(id="sw-apt-budget", type="number", value=s_budget, min=0, step=1, className="mb-3")], width=3),
                dbc.Col([_label("Default Rate per sq ft (₹)"), dbc.Input(id="sw-apt-rate", type="number", value=s_rate, min=0, step=0.01, className="mb-3")], width=3),
                dbc.Col([_label("Default Fixed Amount (₹)"), dbc.Input(id="sw-apt-amt", type="number", value=s_amt, min=0, step=1, className="mb-3")], width=3),
            ]),
            html.H6("Part B: Maintenance Billing Basis (society default)", className="text-primary mb-2"),
            dbc.Row([dbc.Col([_label("Maintenance Billing Basis"), dbc.Select(id="sw-apt-billing-basis", options=BILLING_BASIS_OPTIONS, value=s_billing_basis, className="mb-2")], width=8)]),
            html.Div(id="sw-apt-basis-hint", children=basis_hint(s_billing_basis)),
            html.Hr(),
            dbc.Row([
                dbc.Col([_label("Billing Due Day"), dbc.Input(id="sw-apt-due", type="number", value=s_due, min=1, max=31, step=1, className="mb-3")], width=4),
            ]),
            dbc.Row([dbc.Col([_label("Charges Interest Rate (% per month)"),
                              dbc.Input(id="sw-apt-interest", type="number", value=s_int, min=0, step=0.01, className="mb-1"),
                              html.Small(INTEREST_RATE_NOTE, className="text-muted d-block mb-1")] + citation, width=8)]),
            html.P("After enrolment, each flat needs its undivided-interest %. Area share is used until you enter the Declaration figures.", className="text-muted small"),
        ]
    elif category == "Funds":
        from app.services import regime_rules_admin as rra
        from app.dash_apps.pages.setup_wizard import fund_plan, fund_flags
        from app.services.statutory_rules import fund_rules_for_state
        s_sink, s_repair = 0.0, 0.0
        if society_id:
            row = db._execute("SELECT apt_sinking_fund_rate, apt_repair_fund_rate FROM apt_charges_fines_basis WHERE society_id = :id AND apt_id IS NULL AND end_date IS NULL LIMIT 1", {"id": society_id}, fetch_one=True)
            if row:
                s_sink, s_repair = row.get("apt_sinking_fund_rate") or 0.0, row.get("apt_repair_fund_rate") or 0.0
        fp = fund_plan(society_id, state)
        ff = fund_flags(society_id, state)
        fund_rules = fund_rules_for_state(state)
        try:
            pol = rra.list_society_policies(society_id) if society_id else {}
        except Exception:
            pol = {}
        cards = []

        def policy_select(key, lock_regime_label=None):
            label, clause, choices = rra.POLICY_SPECS[key]
            st = pol.get(key) or {"value": choices[0][0], "active": False, "proposed": None}
            shown = st["proposed"] or st["value"]
            opts = []
            for v, lbl in choices:
                if v == "regime_default":
                    lbl = f"Regime default: {FUND_MODE_LABELS.get(f['regime_mode'], f['regime_mode']) if key.endswith('collection') else FUND_BASIS_LABELS.get(f['regime_basis'], 'per sq ft of apartment area')}"
                opts.append({"label": lbl, "value": v})
            return html.Div([
                _label(label),
                dbc.Select(id={"type": "sw-pol-choice", "key": key}, size="sm", options=opts, value=shown, className="mb-1"),
                html.Small([dbc.Badge("Active (resolution on file)", color="success") if st["active"] and not st["proposed"]
                            else dbc.Badge("Provisional", color="warning", text_color="dark"),
                            html.Span(id={"type": "sw-pol-msg", "key": key}, className="text-muted ms-2")], className="d-block mb-2"),
            ])

        for fund_key, fund_info in UP_AOA_FUNDS.items():
            name = fund_info["name"]
            rate_applicable = fund_info["rate_applicable"]

            # Check if sinking/repair is statutory for this state
            is_statutory = fund_info["statutory"]
            if fund_key in ("sinking", "repair"):
                is_statutory = fund_rules[fund_key]["mode"] == "statutory"

            # Get stored rate and plan for voluntary funds
            if fund_key == "sinking":
                stored_rate = s_sink
                f = fp["plan"]["sinking"]
            elif fund_key == "repair":
                stored_rate = s_repair
                f = fp["plan"]["repair"]
            else:
                stored_rate = 0.0
                f = {"statutory": is_statutory, "mode": "none", "basis": "per_sq_ft", "min_pct": None, "regime_mode": "none", "regime_basis": "per_sq_ft"}

            rate_value = stored_rate or 0.0

            if is_statutory:
                # Statutory funds - show locked info
                badge_color = "primary" if rate_applicable else "secondary"
                body = [
                    dbc.Badge(f"Statutory — {fund_info['source']}", color=badge_color, className="mb-2", pill=True),
                    html.Small(fund_info["description"], className="text-muted d-block mb-2"),
                ]
                if not rate_applicable:
                    body.append(html.Small("No recurring rate — this fund is not billed monthly.", className="text-info d-block"))
                # For statutory funds with rate (like MH sinking/repair), show rate info
                if rate_applicable and fund_key in ("sinking", "repair"):
                    min_pct = fund_rules[fund_key].get("min_pct")
                    if min_pct:
                        body.append(html.Small(f"Statutory minimum: {min_pct}% of construction cost per year", className="text-warning d-block mb-2"))
                    body.append(html.Div([
                        html.Div(_label(fund_rate_label(f.get("basis", "per_sq_ft"))), id=f"sw-fund-{fund_key}-rate-label"),
                        dbc.Input(id=f"sw-apt-{fund_key}", type="number", value=rate_value, min=0, step=0.01, className="mb-1", disabled=True),
                    ], id=f"sw-fund-{fund_key}-rate-wrap", style={"display": "block"}))
                    body.append(html.Small("Rate fixed by state statute — cannot be changed.", className="text-muted d-block"))
            else:
                # Voluntary funds - show policy choices
                levy_key, cm_key, bp_key = f"levy_{fund_key}_fund", f"{fund_key}_fund_collection", f"{fund_key}_fund_basis"
                show_collect = {} if (f.get("levy") == "yes" or f.get("mode") != "none") else {"display": "none"}
                body = [
                    dbc.Badge("Voluntary — Society Policy", color="warning", className="mb-2", pill=True, text_color="dark"),
                    html.Small(fund_info["description"], className="text-muted d-block mb-2"),
                    html.Small(f"Not prescribed by {fp['regime']}. Optional: the society decides, by General Body resolution.", className="text-muted d-block mb-2"),
                    policy_select(levy_key),
                    html.Div(policy_select(cm_key), id=f"sw-fund-{fund_key}-collect-wrap", style=show_collect),
                    html.Div(policy_select(bp_key), id=f"sw-fund-{fund_key}-basis-wrap", style={} if f.get("mode") == "on_bill" else {"display": "none"}),
                ]

            if rate_applicable and not is_statutory:
                body.append(html.Div([
                    html.Div(_label(fund_rate_label(f.get("basis", "per_sq_ft"))), id=f"sw-fund-{fund_key}-rate-label"),
                    dbc.Input(id=f"sw-apt-{fund_key}", type="number", value=rate_value, min=0, step=0.01, className="mb-1"),
                ], id=f"sw-fund-{fund_key}-rate-wrap", style={} if f.get("mode") == "on_bill" else {"display": "none"}))
                body.append(html.Small(fund_hint(f, fp["regime"]), id=f"sw-fund-{fund_key}-hint", className="text-muted d-block"))

            cards.append(dbc.Card([
                dbc.CardHeader(html.Strong(name)),
                dbc.CardBody(body),
            ], className="mb-3 shadow-sm"))

        return elements + [
            _render_banner("Funds", "All UP AOA funds: statutory funds (IFMS Corpus, Major Repair Fund, Reserve Fund) and voluntary funds (Sinking Fund, Repair & Maintenance Fund)."),
            dbc.Alert([html.I(className="fas fa-info-circle me-2"),
                       "Statutory funds are fixed by law and cannot be changed. Voluntary funds require a General Body resolution to levy; choices are provisional until the resolution is recorded (Settings > Society governance)."],
                      color="info", className="py-2 mb-3", style={"fontSize": "12.5px"}),
            *cards,
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
            _render_banner("Society Operations", "Configure gate pass enforcement and security duty hours. (Vendor pass prices are set on the Vendor Charges step.)"),
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

        # UP AOA Fund account labels per statutory heads
        UP_AOA_FUND_LABELS = {
            3100: "Capital Account / Share Capital",
            3210: "Sinking Fund Reserve",
            3220: "Repair & Maintenance Fund Reserve",
            3230: "IFMS Corpus (Interest-Free Maintenance Security Corpus)",
            3240: "Gifts Received",
            3250: "Provisions",
            3260: "Gifts Given",
            3270: "Major Repair Fund (Transfer Fee ½%)",
        }

        # Same shape as the Balance Sheet: Assets (Dr) on the left,
        # Liabilities + Equity/Reserves (Cr) on the right, each as a parent -> child tree.
        children = {}
        for acc in ACCOUNTS:
            children.setdefault(acc[4], []).append(acc)
        for kids in children.values():
            kids.sort(key=lambda a: a[0])

        def _has_bf(acc):
            return bool(acc[6]) or any(_has_bf(c) for c in children.get(acc[0], []))

        def _get_aoa_label(acc_id, default_name):
            """Get UP AOA label for fund accounts, fallback to default name."""
            return UP_AOA_FUND_LABELS.get(acc_id, default_name)

        def _render_node(acc, depth):
            out = []
            indent = {"paddingLeft": f"{12 + depth * 14}px"}
            if acc[6]:   # postable account -> amount + remarks inputs (ids unchanged)
                aoa_label = _get_aoa_label(acc[0], acc[3] or "")
                out.append(html.Div([
                    html.Div([aoa_label, html.Small(f"{acc[2] or ''} · {acc[5] or ''}")], className="sw-bf-name"),
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
        # Filled by a callback (setup_wizard_callbacks.refresh_review) from the live form values when the
        # admin opens this step. Reading the database here showed defaults, because nothing is saved before Submit.
        return elements + [_render_banner("Review & Confirm", "Open this step after filling the earlier ones: it shows what you entered.")]
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
                                    dbc.Button("Previous", id="sw-btn-prev", color="secondary", className="me-2", disabled=True, style={"display": "inline-block"}),
                                    dbc.Button("Next", id="sw-btn-next", color="primary", className="me-2", style={"display": "inline-block"}),
                                    dbc.Button("Submit Setup", id="sw-btn-submit", color="success", style={"display": "none"}),
                                    # dbc.Spinner accepts no `style` (any dbc version), which crashed the whole wizard
                                    # layout; the id and style live on a wrapper the submit callback toggles.
                                    html.Span(
                                        dbc.Spinner(type="border", size="sm", color="success"),
                                        id="sw-submit-spinner",
                                        style={"display": "none", "marginLeft": "8px"},
                                    ),
                                ],
                                style={"textAlign": "right", "display": "flex", "justifyContent": "flex-end", "alignItems": "center"}
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
