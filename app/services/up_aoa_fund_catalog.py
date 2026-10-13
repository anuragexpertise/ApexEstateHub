"""UP AOA fund catalogue: one source for the Setup Wizard's *Funds* step and its *Brought Forward* step.

Every fund an Uttar Pradesh Apartment Owners' Association (AOA) can hold is listed here with
  * status        - how binding it is (see STATUS_META)
  * verification  - whether the rate / rule was checked against the gazetted text (see VERIFY_META)
  * applicability, when it is levied, the rate, and what the money may be used for.

Status vocabulary (deliberately three levels, loosest last):
  statutory      Fixed by the Act, the Rules or a Regulation made under them; the society cannot change it.
  model_bye_law  Prescribed by the Model Bye-Laws of 16 Nov 2011 (Notification 3977/8-1-11-115 D.A./02 T.C.-I, made under
                 s.14(6)). Binding once the AOA adopts them; departing from them needs 2/3rd of owners AND the
                 competent authority's prior approval (bye-law 58).
  optional       Not in the Act, Rules or Model Bye-Laws. The society's own choice by General Body resolution; every
                 rate on it is PROVISIONAL until that resolution is on file.

Sources read for this catalogue (see docs/UP_AOA_FUNDS.md): UP Act 16 of 2010; Model Bye-Laws 2011 (full text);
UP RERA Reg. 47 amendment (Notification 7098/U.P. RERA/Regulation/2026-27 of 13.07.2026) through press and law-firm
reports only - the notification itself was not read, so its figures are marked provisional.

Keep this module free of Dash / database imports so it can be unit-tested on its own.
"""

STATUS_META = {
    "statutory": ("Statutory", "primary"),
    "model_bye_law": ("Model Bye-Law (prescribed)", "info"),
    "optional": ("Optional \u2014 Provisional", "warning"),
}

VERIFY_META = {
    "checked": ("Text checked", "success"),
    "provisional": ("Provisional \u2014 verify", "warning"),
}

# Legacy keys kept for existing callers: name, statutory, source, description, rate_applicable.
UP_AOA_FUNDS = {
    "ifms_corpus": {
        "name": "IFMS Corpus (Corpus Fund)",
        "statutory": True,
        "status": "statutory",
        "verification": "provisional",
        "verification_note": (
            "Act s.14(5) proviso read in the Act. The 2026 category rates come from press / law-firm reports of "
            "Notification 7098/U.P. RERA/Regulation/2026-27 (13.07.2026); the notification text was not read and "
            "reports disagree on the unit (per sq ft vs per sq m)."),
        "source": "UP Apartment Act 2010 s.14(5) proviso; UP RERA General Regulations 2019, Reg. 47 (as amended 13.07.2026)",
        "description": "Interest-Free Maintenance Security collected by the promoter; handed to the AOA at handover.",
        "rate_applicable": False,
        "bf_acc": 3230,
        "applicability": ("Promoter-collected security. The AOA does not levy it: it receives the corpus and a unit-wise "
                          "statement at handover and records it as an opening balance."),
        "levy_when": "One-time, by the promoter, at registration of the sale / lease deed.",
        "rate": ("Set by UP RERA by project type and unit category - group housing about \u20b920\u2013100, commercial "
                 "\u20b940 (non-central AC) / \u20b950 (central AC), as reported. Unit and exact slabs: verify in the notification."),
        "use": ("Operation, maintenance, repair and replacement of common areas and equipment only. Separate bank "
                "account, separate books, CA-audited, reported at the AGM. The app locks the principal (100%)."),
    },
    "major_repair": {
        "name": "Major Repair Fund",
        "statutory": True,
        "status": "model_bye_law",
        "verification": "checked",
        "verification_note": "Bye-law 39 (second proviso) and 3(1)(d) read in the gazetted Model Bye-Laws.",
        "source": "Model Bye-Laws 2011, bye-law 39 (and 3(1)(d), 37)",
        "description": "Transfer contribution, kept for future major repairs of the building.",
        "rate_applicable": False,
        "rate_pct": 0.5,
        "bf_acc": 3270,
        "applicability": "Every sale / transfer of an apartment in an AOA that has adopted the Model Bye-Laws.",
        "levy_when": "On each transfer, payable by the transferor (seller) to the AOA; not billed monthly.",
        "rate": "\u00bd% of the transfer value (bye-law 39). Common-area rent reserve and bye-law 37 levies add to it - see below.",
        "use": "Major repairs of the building (structural safety). Not for routine expenses.",
    },
    "reserve": {
        "name": "Reserve Fund",
        "statutory": True,
        "status": "model_bye_law",
        "verification": "provisional",
        "verification_note": ("Bye-law 46(c) says common profits form the nucleus of the reserve funds, but no percentage "
                              "is fixed anywhere. The 25% at FY close is this engine's default (co-operative convention)."),
        "source": "Model Bye-Laws 2011, bye-law 46(c); Act s.14(8)(a)",
        "description": "Nucleus built from common profits (net surplus) at financial-year close.",
        "rate_applicable": False,
        "bf_acc": 3220,
        "applicability": "Every AOA; the fund itself is prescribed, the amount set aside is not.",
        "levy_when": "Not levied on owners. Appropriated from net surplus at FY close under a General Body resolution.",
        "rate": "No percentage in UP law. App default 25% of net surplus - society policy, PROVISIONAL.",
        "use": "Long-term solvency and the association's general reserves.",
    },
    "sinking": {
        "name": "Sinking Fund",
        "statutory": False,
        "status": "optional",
        "verification": "provisional",
        "verification_note": "No UP provision found in the Act, Rules or Model Bye-Laws.",
        "source": "Not prescribed by the UP Apartment Act 2010 or Model Bye-Laws 2011; levied by General Body resolution",
        "description": "Voluntary fund for structural overhauls, lifts, DG sets. Rate and basis set by society policy.",
        "rate_applicable": True,
        "bf_acc": 3210,
        "applicability": "Only if the General Body resolves to levy it.",
        "levy_when": "From the date of the resolution, with each monthly bill (or from surplus at FY close).",
        "rate": ("None in UP law. Figures such as 0.25% of construction cost a year come from Maharashtra co-operative "
                 "practice and are not a UP rate."),
        "use": "Replacement / overhaul of big assets (lifts, pumps, DG sets, repainting, waterproofing).",
    },
    "repair": {
        "name": "Repair & Maintenance Fund",
        "statutory": False,
        "status": "optional",
        "verification": "provisional",
        "verification_note": ("Routine repairs are common expenses (Act s.18; bye-laws 25(a), 35). Only a separate "
                              "earmarked fund is optional."),
        "source": "UP Apartment Act 2010 s.18 (common expenses by undivided interest); Model Bye-Laws 2011 bye-laws 25, 35",
        "description": "Routine upkeep of common areas. Rate and basis set by society policy.",
        "rate_applicable": True,
        "bf_acc": 3220,
        "applicability": "Routine repairs are already covered by the monthly assessment; a separate fund is the society's choice.",
        "levy_when": "As part of the monthly assessment once the budget is approved (bye-law 11); a separate head only by resolution.",
        "rate": "None in UP law. Any 0.75%-of-cost style figure is a Maharashtra benchmark, not UP law.",
        "use": "Day-to-day repair of common areas and facilities.",
    },
    # --- information-only entries (no rate input on the Funds step, nothing to bill from there) ---
    "rental_reserve": {
        "name": "Common-area rent reserve",
        "statutory": False,
        "info_only": True,
        "status": "model_bye_law",
        "verification": "checked",
        "verification_note": "Bye-law 3(1)(d) read in the gazetted Model Bye-Laws.",
        "source": "Model Bye-Laws 2011, bye-law 3(1)(d)",
        "description": "Licence income from common areas let to outsiders, accumulated for major repairs.",
        "rate_applicable": False,
        "bf_acc": None,
        "applicability": ("Only where every member gives written consent and the competent authority permits the letting."),
        "levy_when": "As and when licence income is received; not an owner levy.",
        "rate": "Whatever the licence fetches - no rate prescribed.",
        "use": "Reserve for major repairs. This app books it with the Major Repair Fund (account 3270).",
    },
    "special_levy": {
        "name": "Major-repair special levy",
        "statutory": False,
        "info_only": True,
        "status": "model_bye_law",
        "verification": "checked",
        "verification_note": "Bye-law 37 read in the gazetted Model Bye-Laws.",
        "source": "Model Bye-Laws 2011, bye-law 37",
        "description": "One-off contribution when the building needs major repairs for structural safety.",
        "rate_applicable": False,
        "bf_acc": None,
        "applicability": "When major repairs are needed for structural safety or other sufficient reason.",
        "levy_when": "After the Board approves an engineer's detailed estimate; each member then pays a share.",
        "rate": "Each owner's share of the approved estimate - no fixed rate.",
        "use": "The approved major repair only.",
    },
    "share_capital": {
        "name": "Entrance fee and share capital",
        "statutory": False,
        "info_only": True,
        "status": "model_bye_law",
        "verification": "checked",
        "verification_note": "Bye-laws 4 and 6 read in the gazetted Model Bye-Laws.",
        "source": "Model Bye-Laws 2011, bye-laws 4 and 6",
        "description": "Membership money, carried in the Capital Account.",
        "rate_applicable": False,
        "bf_acc": 3100,
        "applicability": "Every owner, and every transferee on a transfer.",
        "levy_when": "One-time, on becoming a member (first purchase or transfer).",
        "rate": "\u20b91,000 entrance fee, and at least one share per owner (share value is set by the AOA).",
        "use": "Capital of the association.",
    },
}

# Brought Forward: account id -> fund keys whose rules govern that opening balance, and the row label.
BF_FUND_INFO = {
    3100: {"label": "Capital Account / Share Capital (entrance fee \u20b91,000 + share)", "funds": ["share_capital"]},
    3210: {"label": "Sinking Fund Reserve", "funds": ["sinking"]},
    3220: {"label": "Reserve Fund / Repair & Maintenance Fund Reserve", "funds": ["reserve", "repair"]},
    3230: {"label": "IFMS Corpus (Interest-Free Maintenance Security) \u2014 a.k.a. Corpus Fund", "funds": ["ifms_corpus"]},
    3270: {"label": "Major Repair Fund (\u00bd% transfer fee + common-area rent reserve)", "funds": ["major_repair", "rental_reserve"]},
}


def status_spec(fund):
    """(text, bootstrap colour) for the fund's status badge."""
    return STATUS_META[fund["status"]]


def verify_spec(fund):
    """(text, bootstrap colour) for the fund's verification badge."""
    return VERIFY_META[fund["verification"]]


def fund_facts(fund):
    """[(label, text)] shown under a fund on the Funds step and as a hint under its Brought Forward row."""
    return [("Applicability", fund["applicability"]), ("When levied", fund["levy_when"]),
            ("Rate", fund["rate"]), ("Use", fund["use"]), ("Source", fund["source"]),
            ("Verification", fund["verification_note"])]


def bf_info(acc_id):
    """Row label, badges and a one-line hint for a Brought Forward account; None for accounts that are not funds."""
    meta = BF_FUND_INFO.get(acc_id)
    if not meta:
        return None
    tags, hints = [], []
    for key in meta["funds"]:
        f = UP_AOA_FUNDS[key]
        text, colour = status_spec(f)
        tag = (f"{f['name']}: {text}", colour)
        if tag not in tags:
            tags.append(tag)
        vtext, vcolour = verify_spec(f)
        if f["verification"] != "checked" and (vtext, vcolour) not in tags:
            tags.append((vtext, vcolour))
        hints.append(f"{f['name']} \u2014 {f['levy_when']} Rate: {f['rate']}")
    return {"label": meta["label"], "tags": tags, "hint": " | ".join(hints)}
