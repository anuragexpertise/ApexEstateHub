# app/services/statutory_rules.py
"""
Acts & Rules content for the Setup Wizard's right-hand panel.

Source of truth: README.md → "EstateHub Compliance — Statutory Framework
Coverage" table (UP AOA 2010 first). Rows here are short, wizard-sized
summaries of that table; edit the README table and this list together.

Why this exists
---------------
The wizard used to call get_links_for_categories([<wizard step name>]) but
kpi_rule_links.category holds keys like 'sinking_fund' / 'fund_gst' /
'tds_no_pan' — never "Society Details", "Vendor Charges", etc. — so the
panel was empty for every step. STEP_LINK_CATEGORIES bridges the two, and
STATUTORY_ROWS supplies the framework rows that have no external link.
"""

# key -> (area, governing provisions, requirement, coverage_ok, coverage_note)
STATUTORY_ROWS = {
    "it_mutuality": (
        "Income Tax — Taxability & Mutuality",
        "Sec. 2(31), Sec. 4, Doctrine of Mutuality",
        "Member maintenance is exempt under Mutuality; non-mutual income "
        "(bank interest, rentals, cell towers) is taxable at AOP rates.",
        True,
        "Income accounts are tagged mutual / non-mutual; Mutuality Summary export.",
    ),
    "it_80p": (
        "Income Tax — Deductions",
        "Sec. 80P(2)(c) / 80P(2)(d)",
        "Deduction on interest from cooperative banks, claimed via annual return.",
        False,
        "Not yet tracked.",
    ),
    "it_return": (
        "Income Tax — Return of Income",
        "Sec. 139(1), Sec. 44AB",
        "Annual ITR-5 filing; tax audit if commercial turnover exceeds the threshold.",
        False,
        "Out of e-filing scope; no Sec. 44AB flag yet.",
    ),
    "tds": (
        "TDS (Income Tax Act, 1961)",
        "Sec. 194A, 194C, 194H, 194-I, 194-IA/IB/IC, 194J",
        "Deduct TDS on vendor payouts (contracts, professional fees, rent, "
        "brokerage), remit it, and file 26Q.",
        True,
        "Section / rate / PAN-vs-no-PAN engine, single-bill & annual thresholds, "
        "structured 26Q-shaped export.",
    ),
    "labour": (
        "Labour & Safety Compliances",
        "EPF & MP Act 1952, ESI Act 1948, Contract Labour Act 1970",
        "Minimum-wage / EPF / ESIC compliance for direct employees; manpower "
        "agencies (security, housekeeping) must furnish monthly PF/ESIC challans.",
        False,
        "Not tracked — no challan capture or invoice-hold gate yet.",
    ),
    "gst": (
        "GST (CGST Act, 2017)",
        "Sec. 22(1), Notification 12/2017-CT(R) Entry 77",
        "Up to ₹7,500/month/member is exempt; above that, 18% on the entire "
        "amount if society turnover exceeds ₹20L (₹10L in special-category "
        "states). RCM applies on unregistered vendors.",
        True,
        "gst_rates table, registration-threshold gate, RCM accounts, "
        "inter-state IGST via societies.state, GSTR-1/3B-shaped export.",
    ),
    "reserve": (
        "Reserve Fund",
        "Societies Registration Act / State Cooperative Societies Acts",
        "Statutory reserve from net surplus, for long-term solvency (25% of "
        "net surplus under the UP AOA regime). The UP transfer fee (1/2%) goes to "
        "the Major Repair Fund under bye-law 39, not here.",
        True,
        "Mapped to the RESERVE_FUND head; FY close appropriates the surplus.",
    ),
    "sinking": (
        "Sinking Fund",
        "Model Bye-laws 13(c)/14(c), State Apartment Ownership Acts",
        "Dedicated fund for structural overhauls, lifts and DG sets; about "
        "0.25–0.33%/yr of construction cost.",
        True,
        "Dedicated ledger account, per-society rate basis, auto-billed monthly.",
    ),
    "repair": (
        "Repair & Maintenance Fund",
        "Model Bye-laws 13(a)/14(b)",
        "Routine upkeep of common areas, plumbing and electricals; typically "
        "at least 0.75%/yr of construction cost.",
        True,
        "Dedicated ledger account, same rate config and billing as Sinking Fund.",
    ),
    "corpus": (
        "Corpus Fund",
        "RERA Act 2016 Sec. 11(4)(g), 17; State Apartment Ownership Acts",
        "One-time builder-handover capital receipt; principal is inviolable, "
        "only the interest is deployable.",
        True,
        "Dedicated ledger account; principal locked via statutory_lock_pct.",
    ),
    "up_aoa_act": (
        "Governing Statute — UP Apartment Act, 2010",
        "Sec. 3 (common areas), 12 (promoter's Declaration), 14 (AOA & "
        "bye-laws), 18/20 (common expenses / common profits)",
        "Every building with 4+ apartments must form an Association of "
        "Apartment Owners with bye-laws adopted at a General Body; common "
        "expenses and common profits are accounted for separately.",
        True,
        "UP_AOA_2010 regime drives the statutory head mapping on the Balance "
        "Sheet, the fund ledgers and the AOA compliance card.",
    ),
    "up_aoa_rules": (
        "UP Apartment Rules, 2011 & Model Bye-Laws",
        "Rules notified 16-11-2011; Model Bye-laws 13(a)/13(c), 14(b)/14(c), "
        "39 (transfer fee ½%), 46 (reserve & share capital), 49 (audit), "
        "54 (Act prevails), 58 (adoption by 2/3rd majority)",
        "Procedural code under the Act — competent authority, Declaration and "
        "Deed of Apartment forms; bye-laws fix the financial framework "
        "(sinking, repair, reserve, corpus) this wizard is setting rates for.",
        True,
        "Fund bases and rates configured on the Society Compliance / "
        "Apartment Charges steps; statutory_calendar tracks the filings.",
    ),
    "legal_instruments": (
        "Act / Rules / Bye-laws catalog",
        "legal_instrument_catalog (regime UP_AOA_2010)",
        "The full tabulated list of Acts, Rules, Bye-laws and Notifications "
        "governing this AOA, with applicability, key provisions and sources.",
        True,
        "Full table on the Setup Wizard's 'UP AOA Compliance' step; Master "
        "maintains it on Master Portal → RWA Compliance (UP).",
    ),
}

# Wizard step -> ordered STATUTORY_ROWS keys. Steps with no direct statute
# (Administrator, Instructions, Agreement) fall back to the full framework.
STEP_ROWS = {
    "Society Details":    ["it_mutuality", "it_return", "labour"],
    "Society Compliance": ["gst", "tds", "sinking", "repair", "reserve", "corpus"],
    "UP AOA Compliance":  ["up_aoa_act", "up_aoa_rules", "legal_instruments",
                           "reserve", "corpus", "sinking", "repair"],
    "TAN & TDS Rates":    ["tds"],
    "GSTIN & GST Rate":   ["gst"],
    "Apartment Charges":  ["sinking", "repair", "reserve", "corpus", "gst"],
    "Vendor Charges":     ["tds", "gst", "labour"],
    "Accounts":           ["it_mutuality", "it_80p", "reserve", "corpus"],
    "Brought Forward":    ["corpus", "reserve", "sinking", "repair"],
}

# Wizard step -> kpi_rule_links.category keys (external "read the Act" links).
STEP_LINK_CATEGORIES = {
    "Society Details":    ["apartment_act", "cooperative_act", "rera"],
    "Administrator":      ["apartment_act"],
    "Society Compliance": ["sinking_fund", "fund_gst", "gst_registered", "tds_no_pan"],
    "UP AOA Compliance":  ["apartment_act", "cooperative_act", "rera",
                           "sinking_fund", "income_tax_mutuality"],
    "TAN & TDS Rates":    ["tds_no_pan", "income_tax_mutuality"],
    "GSTIN & GST Rate":   ["gst_registered", "fund_gst"],
    "Apartment Charges":  ["sinking_fund", "apartment_act", "cooperative_act"],
    "Vendor Charges":     ["tds_no_pan", "gst_registered"],
    "Accounts":           ["income_tax_mutuality"],
    "Brought Forward":    ["sinking_fund", "rera"],
    "Agreement":          ["apartment_act", "cooperative_act"],
}

# Steps whose "Acts & Rules" column also lists the tabulated Act / Rules /
# Bye-laws for the society's regime (legal_instrument_catalog). Steps without
# an entry render the framework rows and official links only.
STEP_INSTRUMENTS = {"Society Details", "Society Compliance", "UP AOA Compliance",
                    "Apartment Charges", "Accounts", "Agreement"}


# ── Act / Rules / Bye-laws catalog (legal_instrument_catalog) ───────────────
# The wizard's "UP AOA Compliance" step shows the same tabulated Acts, Rules,
# Bye-laws and Notifications that the Master Portal's "RWA Compliance (UP)" tab
# renders (app/dash_apps/pages/portal_pages.py::_rwa_compliance_up_page), from
# the same table — so an admin reads the governing provisions while setting
# the fund rates / bases those provisions require. Rows are seeded from
# database/seed.py::LEGAL_INSTRUMENTS_UP_AOA.

DEFAULT_REGIME = "UP_AOA_2010"

# societies.state -> legal_regime_profiles.code (same state codes as
# app/services/kpi_rule_links_service.get_states). UP is the only fully
# seeded regime; the rest fall back to UP until their own rows exist.
STATE_REGIME = {
    "UP": "UP_AOA_2010",
    "MH": "MH_COOP_1965",
}

# Table order for the grouped render (anything else keeps display_order).
INSTRUMENT_TYPE_ORDER = ["Act", "Central Act", "Rules", "Central Rules",
                         "Bye-laws", "Notification"]

INSTRUMENT_BADGE_COLOR = {
    "Act": "primary", "Central Act": "info", "Rules": "secondary",
    "Central Rules": "info", "Bye-laws": "warning", "Notification": "dark",
}


def regime_for_society(society_id=None):
    """
    Legal regime governing this society.

    society_legal_regime (written by seed_society_legal_regime for UP
    addresses) wins; otherwise societies.state is mapped through
    STATE_REGIME. societies.state is only persisted on Setup Wizard submit
    (see setup_wizard_callbacks.submit_setup_wizard), so a society part-way
    through the wizard still resolves to the UP default.
    """
    if not society_id:
        return DEFAULT_REGIME
    try:
        from database.db_manager import db
        row = db._execute(
            "SELECT regime_code FROM society_legal_regime WHERE society_id=%s",
            (society_id,), fetch_one=True,
        )
        if row and row.get("regime_code"):
            return row["regime_code"]
        row = db._execute("SELECT state FROM societies WHERE id=%s", (society_id,), fetch_one=True)
        return STATE_REGIME.get(((row or {}).get("state") or "").strip(), DEFAULT_REGIME)
    except Exception:
        return DEFAULT_REGIME


def _seed_fallback_instruments(regime_code):
    """LEGAL_INSTRUMENTS_UP_AOA rows as plain dicts, for a database where
    legal_instrument_catalog hasn't been integrated yet."""
    try:
        from database.seed import LEGAL_INSTRUMENTS_UP_AOA
    except Exception:
        return []
    out = []
    for (rc, itype, title, year, authority, applicability, provisions,
         source, order, status) in LEGAL_INSTRUMENTS_UP_AOA:
        if rc != regime_code:
            continue
        out.append({
            "instrument_type": itype, "title": title, "enactment_year": year,
            "issuing_authority": authority, "applicability": applicability,
            "key_provisions": provisions, "source_reference": source,
            "display_order": order, "status": status, "last_verified_on": None,
        })
    return out


def instruments_for_regime(regime_code=DEFAULT_REGIME):
    """
    Act / Rules / Bye-laws rows for one regime, from legal_instrument_catalog.

    Falls back to the seed list in database/seed.py when the table is missing
    on this database (the same "not integrated yet" situation the Master tab
    renders setup instructions for) so the wizard step never comes up blank.
    """
    try:
        from database.db_manager import db
        rows = db._execute(
            """SELECT instrument_type, title, enactment_year, issuing_authority,
                      applicability, key_provisions, source_reference,
                      display_order, status, last_verified_on
               FROM legal_instrument_catalog
               WHERE regime_code=%s
               ORDER BY display_order""",
            (regime_code,), fetch_all=True,
        ) or []
    except Exception:
        rows = []
    if not rows:
        rows = _seed_fallback_instruments(regime_code)
    return sorted(
        rows,
        key=lambda r: (
            INSTRUMENT_TYPE_ORDER.index(r["instrument_type"])
            if r.get("instrument_type") in INSTRUMENT_TYPE_ORDER else len(INSTRUMENT_TYPE_ORDER),
            r.get("display_order") or 0,
        ),
    )


def instruments_for_society(society_id=None):
    """(regime_code, instrument rows) for one society."""
    regime = regime_for_society(society_id)
    return regime, instruments_for_regime(regime)


def grouped_instruments(rows):
    """{instrument_type: [rows]} in INSTRUMENT_TYPE_ORDER."""
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(r.get("instrument_type") or "Other", []).append(r)
    return groups


def rows_for_step(step: str):
    """Framework rows for a wizard step; full framework if none map."""
    keys = STEP_ROWS.get(step) or list(STATUTORY_ROWS.keys())
    return [STATUTORY_ROWS[k] for k in keys]
