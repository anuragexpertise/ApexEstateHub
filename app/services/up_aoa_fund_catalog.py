"""UP AOA fund catalogue for the Setup Wizard: a thin, Dash-free layer over schemes/fund_register.py.

The register holds the data (status, parameters, account routes, billing channels). This module adds what the
screens need: the legacy UP_AOA_FUNDS shape, badge specs, and the Brought Forward row labels that show only the
funds a society holds - every prescribed fund, plus an optional fund only once the society opts in.
"""
from schemes.fund_register import (BILLING_CHANNELS, FUND_ORDER, FUNDS, IFMS_NOTES, IFMS_PROJECT_TYPES,  # noqa: F401
                                   IFMS_SLABS, SHARED_PARAMETERS, STATUS_META, SUPPORT_META, VERIFY_META,
                                   account_mappings, active_keys, ifms_amount_range, ifms_rate_range, is_prescribed,
                                   principal_locks, register_rows)

# Legacy shape kept for existing callers: name, statutory (= prescribed, so the card is locked), source,
# description, rate_applicable - plus everything the register adds.
UP_AOA_FUNDS = {k: {**FUNDS[k], "statutory": is_prescribed(k), "bf_acc": FUNDS[k]["account"]["id"]} for k in FUND_ORDER}

# Brought Forward: which fund(s) an account carries. 3220 carries two (Reserve + Repair & Maintenance reserve).
_BF_ACCOUNT_FUNDS = {}
for _k in FUND_ORDER:
    _BF_ACCOUNT_FUNDS.setdefault(FUNDS[_k]["account"]["id"], []).append(_k)
BF_FUND_ACCOUNTS = dict(_BF_ACCOUNT_FUNDS)

_BF_LABEL = {
    3210: "Sinking Fund Reserve (UP AOA)",
    3220: {"reserve": "Reserve Fund", "both": "Reserve Fund / Repair & Maintenance Fund Reserve"},
    3230: "Corpus Fund (IFMS) (UP AOA)",
    3270: "Major Repair Fund (UP AOA)",
    3280: "Depreciation Fund (Society Policy / as applicable)",
}


def status_spec(fund):
    """(text, bootstrap colour) for the fund's status badge."""
    return STATUS_META[fund["status"]]


def verify_spec(fund):
    """(text, bootstrap colour) for the fund's verification badge."""
    return VERIFY_META[fund["verification"]]


def fund_facts(fund):
    """[(label, text)] shown under a fund on the Funds step."""
    return [("Applicability", fund["applicability"]), ("When levied", fund["levy_when"]),
            ("Rate", fund["rate"]), ("Use", fund["use"]), ("Source", fund["source"]),
            ("Verification", fund["verification_note"])]


def bf_info(acc_id, active=None, up=True):
    """Brought Forward row for a fund account, or None for an ordinary account.

    active : set of fund keys the society holds (active_keys); None = every fund (no hiding)
    up     : True under the UP AOA regime. Under any other regime the UP labels and badges are not applied; only an
             optional fund the society has not opted into is still hidden.
    Returns {'hidden', 'label', 'tags', 'hint'}; label is None when the caller should keep the account's own name."""
    keys = BF_FUND_ACCOUNTS.get(acc_id)
    if not keys:
        return None
    held = [k for k in keys if active is None or k in active]
    if not held:
        return {"hidden": True, "label": None, "tags": [], "hint": ""}
    if not up:
        return {"hidden": False, "label": None, "tags": [], "hint": ""}
    label = _BF_LABEL[acc_id]
    if isinstance(label, dict):
        label = label["both"] if len(held) > 1 else label["reserve"]
    tags, hints = [], []
    for k in held:
        f = FUNDS[k]
        text, colour = status_spec(f)
        tags.append((f"{f['name']}: {text}", colour))
        vtext, vcolour = verify_spec(f)
        if f["verification"] != "checked" and (vtext, vcolour) not in tags:
            tags.append((vtext, vcolour))
        hints.append(f"{f['name']} \u2014 {f['levy_when']} Rate: {f['rate']}")
    return {"hidden": False, "label": label, "tags": tags, "hint": " | ".join(hints)}
