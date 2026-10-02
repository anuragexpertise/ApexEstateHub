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
}

# Wizard step -> ordered STATUTORY_ROWS keys. Steps with no direct statute
# (Administrator, Instructions, Agreement) fall back to the full framework.
STEP_ROWS = {
    "Society Details":    ["it_mutuality", "it_return", "labour"],
    "Society Compliance": ["gst", "tds", "sinking", "repair", "reserve", "corpus"],
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
    "TAN & TDS Rates":    ["tds_no_pan", "income_tax_mutuality"],
    "GSTIN & GST Rate":   ["gst_registered", "fund_gst"],
    "Apartment Charges":  ["sinking_fund", "apartment_act", "cooperative_act"],
    "Vendor Charges":     ["tds_no_pan", "gst_registered"],
    "Accounts":           ["income_tax_mutuality"],
    "Brought Forward":    ["sinking_fund", "rera"],
    "Agreement":          ["apartment_act", "cooperative_act"],
}


def rows_for_step(step: str):
    """Framework rows for a wizard step; full framework if none map."""
    keys = STEP_ROWS.get(step) or list(STATUTORY_ROWS.keys())
    return [STATUTORY_ROWS[k] for k in keys]
