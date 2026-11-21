"""Chart id registry — constants mirror database.seed.ACCOUNTS; converted app files
use the constants, not raw account-id literals.

Pure: imports database.seed.ACCOUNTS and database.chart_ids only; no database, no Dash.
"""
import re

from database.seed import ACCOUNTS
import database.chart_ids as cid


def _by_id():
    by_id = {}
    for row in ACCOUNTS:
        aid = row[0]
        assert aid not in by_id, f"duplicate account id {aid}"
        by_id[aid] = row
    return by_id


# Name on the constant -> account id, cross-checked against ACCOUNTS row order.
_CONSTANT_TO_ID = {
    name: value
    for name, value in vars(cid).items()
    if name.isupper() and name != "ALL_IDS" and isinstance(value, int)
}


def test_chart_ids_match_accounts():
    by_id = _by_id()
    assert cid.ALL_IDS == set(by_id), (
        f"chart ids {sorted(cid.ALL_IDS ^ set(by_id))} do not match ACCOUNTS")
    for name, aid in _CONSTANT_TO_ID.items():
        assert aid in by_id, f"constant {name}={aid} is not an ACCOUNTS id"
        assert by_id[aid][0] == aid, f"constant {name}={aid} does not exist in ACCOUNTS"


def test_no_raw_account_id_literal_in_converted_files():
    """setup_wizard.py and drilldown_callbacks.py must reference chart_ids constants,
    not the raw literals they previously contained."""
    converted = {
        "app/dash_apps/pages/setup_wizard.py": {1510, 1520, 2240, 3100, 3240, 3250},
        "app/dash_apps/callbacks/drilldown_callbacks.py": {4230},
    }
    for path, banned in converted.items():
        text = open(path).read()
        for aid in banned:
            assert not re.search(rf"\b{aid}\b", text), (
                f"{path} still contains raw account-id literal {aid}")


def test_constants_are_positive_ints():
    for name, aid in _CONSTANT_TO_ID.items():
        assert isinstance(aid, int) and not isinstance(aid, bool), name
        assert aid > 0, f"{name}={aid} is not a positive account id"
