"""UP AOA fund register: the funds a society holds, their parameters, and where each one is appropriated.

Scope is deliberately narrow. A fund is listed only if it is
  * PRESCRIBED  - statutory (Act / Regulation) or Model Bye-Law, so every UP AOA has it; or
  * OPT-IN      - not prescribed, held only if the society opts in by General Body resolution
                  (society policy levy_<fund>_fund = yes, or a collection mode other than 'none').
Anything that is only a *source* of money for one of these funds (common-area rent under bye-law 3(1)(d), the
bye-law 37 special levy) is recorded as a route of that fund, not as a fund of its own. Share capital and the
entrance fee are Capital Account items, not funds.

This module has NO imports from the app or the database, so database/seed.py (a standalone script) and the app
can both read it, and tests can check it against estatehub.sql and seed.py.

What was verified, and from what (13 Oct 2026):
  * Act, Model Bye-Laws 2011 (full gazetted text): checked.
  * Account routes: read in database/estatehub.sql (fn_auto_generate_receivables, fn_record_apartment_transfer,
    fn_fy_close_reserve_appropriation, fn_resolve_reserve_account, fn_appropriate_income_to_fund).
  * UP RERA IFMS notification 7098/U.P. RERA/Regulation/2026-27 (13.07.2026): press / law-firm reports only,
    so its figures are 'provisional'.
"""

STATUS_META = {
    "statutory": ("Statutory", "primary"),
    "model_bye_law": ("Model Bye-Law (prescribed)", "info"),
    "optional": ("Optional \u2014 opted by Society", "warning"),
}

VERIFY_META = {
    "checked": ("Text checked", "success"),
    "provisional": ("Provisional \u2014 verify", "warning"),
}

FUND_ORDER = ("ifms_corpus", "major_repair", "reserve", "sinking", "repair")

# Parameters that belong to every optional on-bill fund, and to billing generally.
SHARED_PARAMETERS = [
    {"key": "project_construction_cost", "label": "Construction cost of project", "unit": "INR",
     "store": "apt_charges_fines_basis.project_construction_cost",
     "note": "Only needed when a fund's basis is 'construction_cost'."},
    {"key": "fund_arrears_interest", "label": "Late-payment interest also applies to fund dues", "unit": "yes/no",
     "store": "society policy fund_arrears_interest", "note": "Applies to on-bill Sinking and Repair dues."},
]

FUNDS = {
    "ifms_corpus": {
        "name": "IFMS Corpus (Corpus Fund)",
        "status": "statutory",
        "verification": "provisional",
        "verification_note": (
            "Act s.14(5) proviso read in the Act. The 2026 category rates come from press / law-firm reports of "
            "Notification 7098/U.P. RERA/Regulation/2026-27 (13.07.2026); the notification text was not read and "
            "reports disagree on the unit (per sq ft vs per sq m)."),
        "source": "UP Apartment Act 2010 s.14(5) proviso; UP RERA General Regulations 2019, Reg. 47 (as amended 13.07.2026)",
        "description": "Interest-Free Maintenance Security collected by the promoter; handed to the AOA at handover.",
        "applicability": ("Promoter-collected security. The AOA does not levy it: it receives the corpus and a unit-wise "
                          "statement at handover and records it as an opening balance."),
        "levy_when": "One-time, by the promoter, at registration of the sale / lease deed.",
        "rate": ("Set by UP RERA by project type and unit category - group housing about \u20b920\u2013100, commercial "
                 "\u20b940 (non-central AC) / \u20b950 (central AC), as reported. Unit and exact slabs: verify in the notification."),
        "use": ("Operation, maintenance, repair and replacement of common areas and equipment only. Separate bank "
                "account, separate books, CA-audited, reported at the AGM. The app locks the principal (100%)."),
        "rate_applicable": False,
        "opt_in_policy": None,
        "account": {
            "id": 3230, "seed_name": "Corpus Fund", "head_code": "IFMS_CORPUS", "lock_pct": 100.0,
            "head_source": "Corpus Fund (builder handover) is the interest-free maintenance security under UP Apartment Act 2010 s.14(5)",
            "engine_lookup": "head IFMS_CORPUS; statutory_lock_pct 100 (fn_process_fund_utilization refuses principal draw-down)",
        },
        "parameters": [
            {"key": "ifms_rate", "label": "IFMS rate by project type / unit category", "unit": "INR (unit to verify)",
             "kind": "statutory", "store": "UP RERA notification 7098 of 13.07.2026 (not stored in the app)", "default": None},
            {"key": "statutory_lock_pct", "label": "Principal lock", "unit": "%", "kind": "statutory",
             "store": "accounts.statutory_lock_pct", "default": 100},
        ],
        "appropriations": [
            {"trigger": "Corpus handed over by the promoter", "function": "Brought Forward (opening balance)",
             "dr": "Bank / FD (society bank account)", "cr": 3230, "when": "once, at handover"},
            {"trigger": "Interest earned on the corpus", "function": "interest posting; optional move to a fund via fn_appropriate_income_to_fund",
             "dr": "Bank", "cr": "Interest Income (4110-4113), not locked", "when": "as earned"},
        ],
    },
    "major_repair": {
        "name": "Major Repair Fund",
        "status": "model_bye_law",
        "verification": "checked",
        "verification_note": "Bye-laws 39 (second proviso), 3(1)(d) and 37 read in the gazetted Model Bye-Laws.",
        "source": "Model Bye-Laws 2011, bye-law 39 (also 3(1)(d) and 37)",
        "description": "Transfer contribution, kept for future major repairs of the building.",
        "applicability": "Every sale / transfer of an apartment in an AOA that has adopted the Model Bye-Laws.",
        "levy_when": "On each transfer, payable by the transferor (seller) to the AOA; not billed monthly.",
        "rate": "\u00bd% of the transfer value (bye-law 39).",
        "use": "Major repairs of the building (structural safety). Not for routine expenses.",
        "rate_applicable": False,
        "rate_pct": 0.5,
        "opt_in_policy": None,
        "account": {
            "id": 3270, "seed_name": "Major Repair Fund (Transfer Fee)", "head_code": "MAJOR_REPAIR_FUND", "lock_pct": 0.0,
            "head_source": "Model Bye-Laws 2011, bye-law 39",
            "engine_lookup": "fixed id 3270 (fn_ensure_major_repair_fund creates it if missing)",
        },
        "parameters": [
            {"key": "transfer_fee_pct", "label": "Transfer fee", "unit": "% of transfer value", "kind": "model_bye_law",
             "store": "scheme pack UP_AOA_2010: transfer_fee_pct", "default": 0.5},
        ],
        "appropriations": [
            {"trigger": "Sale / transfer of an apartment", "function": "fn_record_apartment_transfer",
             "dr": "Sundry Debtors (transferor's receivable)", "cr": 3270, "when": "per transfer"},
            {"trigger": "Common-area rent (bye-law 3(1)(d))", "function": "fn_appropriate_income_to_fund (manual, General Body)",
             "dr": "Common-area / common-profits income account", "cr": 3270, "when": "as the General Body decides"},
            {"trigger": "Special levy for structural repairs (bye-law 37)", "function": "no automatic posting found in the app",
             "dr": "Sundry Debtors (one-off bill)", "cr": 3270, "when": "after the Board approves the engineer's estimate"},
        ],
    },
    "reserve": {
        "name": "Reserve Fund",
        "status": "model_bye_law",
        "verification": "provisional",
        "verification_note": ("Bye-law 46(c) says common profits form the nucleus of the reserve funds, but no percentage "
                              "is fixed anywhere. The 25% at FY close is this engine's default (co-operative convention)."),
        "source": "Model Bye-Laws 2011, bye-law 46(c); Act s.14(8)(a)",
        "description": "Nucleus built from common profits (net surplus) at financial-year close.",
        "applicability": "Every AOA; the fund itself is prescribed, the amount set aside is not.",
        "levy_when": "Not levied on owners. Appropriated from net surplus at FY close under a General Body resolution.",
        "rate": "No percentage in UP law. App default 25% of net surplus - society policy, PROVISIONAL.",
        "use": "Long-term solvency and the association's general reserves.",
        "rate_applicable": False,
        "opt_in_policy": None,
        "account": {
            "id": 3220, "seed_name": "Repair & Maintenance Fund Reserve", "head_code": "RESERVE_FUND", "lock_pct": 0.0,
            "head_source": "Repair & Maintenance Fund Reserve mapped to Reserve Fund per Model Bye-Laws 2011, bye-law 46",
            "engine_lookup": "head RESERVE_FUND (fn_resolve_reserve_account). SHARES account 3220 with the Repair & Maintenance Fund.",
        },
        "parameters": [
            {"key": "reserve_appropriation_pct", "label": "Share of net surplus moved to the Reserve Fund at FY close",
             "unit": "%", "kind": "policy", "store": "regime parameter reserve_appropriation_pct (General Body resolution)",
             "default": 25},
        ],
        "appropriations": [
            {"trigger": "Financial-year close", "function": "fn_fy_close_reserve_appropriation",
             "dr": "Income Expenditure A/c (5100)", "cr": 3220, "when": "yearly; one journal per FY"},
            {"trigger": "Optional / opted fund collected 'at year close'", "function": "same FY-close journal (one collective pool)",
             "dr": "Income Expenditure A/c (5100)", "cr": 3220, "when": "yearly"},
        ],
    },
    "sinking": {
        "name": "Sinking Fund",
        "status": "optional",
        "verification": "provisional",
        "verification_note": "No UP provision found in the Act, Rules or Model Bye-Laws.",
        "source": "Not prescribed by the UP Apartment Act 2010 or Model Bye-Laws 2011; levied by General Body resolution",
        "description": "Opt-in fund for structural overhauls, lifts, DG sets. Rate and basis set by society policy.",
        "applicability": "Only if the General Body resolves to levy it.",
        "levy_when": "From the date of the resolution, with each monthly bill (or from surplus at FY close).",
        "rate": ("None in UP law. Figures such as 0.25% of construction cost a year come from Maharashtra co-operative "
                 "practice and are not a UP rate."),
        "use": "Replacement / overhaul of big assets (lifts, pumps, DG sets, repainting, waterproofing).",
        "rate_applicable": True,
        "opt_in_policy": "levy_sinking_fund",
        "account": {
            "id": 3210, "seed_name": "Sinking Fund Reserve", "head_code": "SINKING_FUND", "lock_pct": 0.0,
            "head_source": "Sinking Fund: voluntary fund, no statutory rate in UP (Act 2010 / Model Bye-Laws 2011)",
            "engine_lookup": "account name ILIKE '%Sinking Fund Reserve%' (fn_auto_generate_receivables) - do not rename",
        },
        "parameters": [
            {"key": "levy_sinking_fund", "label": "Opt in (levy a Sinking Fund)", "unit": "yes/no", "kind": "policy",
             "store": "society policy levy_sinking_fund", "default": "no"},
            {"key": "sinking_fund_collection", "label": "When collected", "unit": "on_bill / fy_close / none", "kind": "policy",
             "store": "society policy sinking_fund_collection", "default": "regime_default"},
            {"key": "sinking_fund_basis", "label": "How shared between flats", "unit": "per_sq_ft / construction_cost / undivided_interest",
             "kind": "policy", "store": "society policy sinking_fund_basis", "default": "regime_default"},
            {"key": "apt_sinking_fund_rate", "label": "Rate", "unit": "per the basis", "kind": "policy",
             "store": "apt_charges_fines_basis.apt_sinking_fund_rate", "default": None},
        ],
        "appropriations": [
            {"trigger": "Monthly bill (collection = on_bill)", "function": "fn_auto_generate_receivables",
             "dr": "Sundry Debtors (flat's bill)", "cr": 3210, "when": "monthly, from the resolution date"},
            {"trigger": "Collection = fy_close", "function": "no separate posting: surplus goes to the Reserve Fund pool",
             "dr": "Income Expenditure A/c (5100)", "cr": 3220, "when": "yearly"},
        ],
    },
    "repair": {
        "name": "Repair & Maintenance Fund",
        "status": "optional",
        "verification": "provisional",
        "verification_note": ("Routine repairs are already common expenses (Act s.18; bye-laws 25(a), 35). Only a separate "
                              "earmarked fund is optional."),
        "source": "UP Apartment Act 2010 s.18 (common expenses by undivided interest); Model Bye-Laws 2011 bye-laws 25, 35",
        "description": "Opt-in earmarked fund for routine upkeep of common areas.",
        "applicability": "Routine repairs are already covered by the monthly assessment; a separate fund is the society's choice.",
        "levy_when": "As part of the monthly assessment once the budget is approved (bye-law 11); a separate head only by resolution.",
        "rate": "None in UP law. Any 0.75%-of-cost style figure is a Maharashtra benchmark, not UP law.",
        "use": "Day-to-day repair of common areas and facilities.",
        "rate_applicable": True,
        "opt_in_policy": "levy_repair_fund",
        "account": {
            "id": 3220, "seed_name": "Repair & Maintenance Fund Reserve", "head_code": "RESERVE_FUND", "lock_pct": 0.0,
            "head_source": "Repair & Maintenance Fund Reserve mapped to Reserve Fund per Model Bye-Laws 2011, bye-law 46",
            "engine_lookup": ("account name ILIKE '%Repair & Maintenance Fund Reserve%' (fn_auto_generate_receivables) - do not rename. "
                              "SHARES account 3220 with the Reserve Fund."),
        },
        "parameters": [
            {"key": "levy_repair_fund", "label": "Opt in (levy a Repair & Maintenance Fund)", "unit": "yes/no", "kind": "policy",
             "store": "society policy levy_repair_fund", "default": "no"},
            {"key": "repair_fund_collection", "label": "When collected", "unit": "on_bill / fy_close / none", "kind": "policy",
             "store": "society policy repair_fund_collection", "default": "regime_default"},
            {"key": "repair_fund_basis", "label": "How shared between flats", "unit": "per_sq_ft / construction_cost / undivided_interest",
             "kind": "policy", "store": "society policy repair_fund_basis", "default": "regime_default"},
            {"key": "apt_repair_fund_rate", "label": "Rate", "unit": "per the basis", "kind": "policy",
             "store": "apt_charges_fines_basis.apt_repair_fund_rate", "default": None},
        ],
        "appropriations": [
            {"trigger": "Monthly bill (collection = on_bill)", "function": "fn_auto_generate_receivables",
             "dr": "Sundry Debtors (flat's bill)", "cr": 3220, "when": "monthly, from the resolution date"},
            {"trigger": "Collection = fy_close", "function": "no separate posting: surplus goes to the Reserve Fund pool",
             "dr": "Income Expenditure A/c (5100)", "cr": 3220, "when": "yearly"},
        ],
    },
}


def is_prescribed(key):
    """True for statutory and Model Bye-Law funds, which every UP AOA holds."""
    return FUNDS[key]["status"] in ("statutory", "model_bye_law")


def active_keys(modes=None):
    """Funds the society holds: every prescribed fund, plus an optional fund only if it is opted.

    `modes` maps an optional fund key to its collection mode ('on_bill' | 'fy_close' | 'none'), as the Funds step
    works it out (fund_plan). A missing key or 'none' means not opted. modes=None means 'show everything'."""
    if modes is None:
        return set(FUND_ORDER)
    return {k for k in FUND_ORDER if is_prescribed(k) or (modes.get(k) or "none") != "none"}


def account_mappings():
    """[(account_id, head_code, source_reference)] for account_statutory_mappings, one row per account.

    3220 carries two funds (Reserve and Repair & Maintenance) under the one RESERVE_FUND head."""
    seen, out = set(), []
    for key in FUND_ORDER:
        a = FUNDS[key]["account"]
        if a["id"] in seen:
            continue
        seen.add(a["id"])
        out.append((a["id"], a["head_code"], a["head_source"]))
    return out


def principal_locks():
    """{account_id: lock_pct} for accounts whose principal the law protects."""
    return {FUNDS[k]["account"]["id"]: FUNDS[k]["account"]["lock_pct"]
            for k in FUND_ORDER if FUNDS[k]["account"]["lock_pct"] > 0}


def _acc_label(ref, names):
    if isinstance(ref, int):
        return f"{names.get(ref, 'Account')} ({ref})"
    return ref


def register_rows(modes=None, names=None, values=None):
    """Rows for the on-screen fund register: one per ACTIVE fund, with its live parameters and its account routes.

    modes  : {optional fund key: collection mode} (see active_keys)
    names  : {account id: account name} so routes show real account names
    values : {parameter key: current value} - anything unknown shows as 'not set'"""
    names, values = names or {}, values or {}
    rows = []
    for key in FUND_ORDER:
        if key not in active_keys(modes):
            continue
        f = FUNDS[key]
        params = []
        for p in f["parameters"]:
            v = values.get(p["key"], p["default"])
            params.append((p["label"], "not set" if v in (None, "") else f"{v:g} {p['unit']}" if isinstance(v, (int, float)) else f"{v} ({p['unit']})"))
        mode = (modes or {}).get(key)
        routes = []
        for r in f["appropriations"]:
            # an opted fund collected on the bill skips its fy_close route, and vice versa
            if key in ("sinking", "repair") and mode in ("on_bill", "fy_close"):
                if ("fy_close" in r["trigger"]) != (mode == "fy_close"):
                    continue
            routes.append({"trigger": r["trigger"], "function": r["function"],
                           "dr": _acc_label(r["dr"], names), "cr": _acc_label(r["cr"], names), "when": r["when"]})
        rows.append({"key": key, "name": f["name"], "status": f["status"], "verification": f["verification"],
                     "account": _acc_label(f["account"]["id"], names), "parameters": params, "routes": routes,
                     "shares_account": f["account"]["id"] == 3220})
    return rows


# ── How each kind of money reaches the books ────────────────────────────────────────────────────────────────────
# support: 'automatic' = the engine raises / posts it; 'partial' = part is automatic; 'manual' = the admin records a
# receipt or journal by hand (no schedule, bill or reminder); 'none' = deliberately nothing is billed.
# Each line was checked against database/estatehub.sql on 13-14 Oct 2026; 'engine' names the function that does it.
BILLING_CHANNELS = [
    {"no": 0, "channel": "No bill", "funds": ["ifms_corpus"], "support": "automatic",
     "engine": "Brought Forward at setup; interest posts to Interest Income",
     "how": "The promoter's corpus is received once at handover. Nothing is ever billed to owners."},
    {"no": 1, "channel": "Every maintenance bill", "funds": ["sinking", "repair"], "support": "automatic",
     "engine": "fn_auto_generate_receivables (receivable line per fund, credited to the fund account)",
     "how": "Billed monthly only if the society opted in (collection = on_bill). Basis: per sq ft, % of construction cost, or a monthly amount by undivided interest."},
    {"no": 2, "channel": "Entrance or transfer", "funds": ["major_repair"], "support": "automatic",
     "engine": "fn_record_apartment_transfer (1/2% transfer fee, charge_kind transfer_fee); member admission table (entrance fee and share)",
     "how": "On each sale: the transfer fee is a receivable on the transferor, credited to the Major Repair Fund. On admission: the 1,000 entrance fee and share go to Capital."},
    {"no": 3, "channel": "Monthly budget basis", "funds": ["sinking", "repair"], "support": "partial",
     "engine": "billing basis undivided_interest: monthly Common-Expense Budget (and a monthly fund amount) x each flat's undivided-interest %",
     "how": "The monthly budget and the monthly fund amounts are billed by each flat's share. The app keeps no annual-budget record and no approval step (bye-law 11), so the figures are typed in, not derived from an approved budget."},
    {"no": 4, "channel": "Special major repairs (bye-law 37)", "funds": ["major_repair"], "support": "manual",
     "engine": "receivables.charge_kind = 'other' exists; no function raises it from an engineer's estimate",
     "how": "The admin raises a one-off bill by hand after the Board approves the estimate. No estimate, approval or per-flat split is recorded."},
    {"no": 5, "channel": "Surplus at financial-year close", "funds": ["reserve"], "support": "automatic",
     "engine": "fn_fy_close_preview / fn_fy_close_reserve_appropriation (Dr Income Expenditure / Cr Reserve)",
     "how": "A percentage of net surplus moves to the Reserve Fund once per FY. A Sinking or Repair fund set to fy_close joins this one pool."},
    {"no": 6, "channel": "Events", "funds": [], "support": "automatic",
     "engine": "events, event_tickets, event_ticket_items; fn_sell_event_ticket",
     "how": "Ticket sales are income. Not a fund unless the General Body resolves to appropriate the surplus."},
    {"no": 7, "channel": "Common-area rent (bye-law 3(1)(d))", "funds": ["major_repair"], "support": "manual",
     "engine": "no lease or rent-schedule table; receipt to a common-profits income account",
     "how": "Recorded as a receipt by hand. Moving it to the Major Repair Fund is a manual appropriation (fn_appropriate_income_to_fund)."},
    {"no": 8, "channel": "Non-mutual income (advertising, hoarding)", "funds": [], "support": "manual",
     "engine": "accounts.mutuality_nature = 'non_mutual' on the income account",
     "how": "Recorded as a receipt by hand against an account flagged non-mutual; reports separate it from mutual income. No hoarding contract or rent register."},
]

SUPPORT_META = {
    "automatic": ("Automatic", "success"),
    "partial": ("Partly automatic", "warning"),
    "manual": ("Manual entry", "secondary"),
}
