"""Chart of accounts follows standard accounting practice (Plan Streamlining_Brought_Forward, section 4A.5).

Pure: imports database.seed.ACCOUNTS and UP_AOA_ACCOUNT_MAPPINGS only; no database, no Dash.
"""
from database.seed import ACCOUNTS, UP_AOA_ACCOUNT_MAPPINGS


def _by_id():
    by_id = {}
    for row in ACCOUNTS:
        aid = row[0]
        assert aid not in by_id, f"duplicate account id {aid}"
        by_id[aid] = row
    return by_id


def test_chart_of_accounts_standard():
    by_id = _by_id()

    # 3250 Provisions: liability under Current Liabilities (2200), Cr, has_bf
    row = by_id[3250]
    assert row[4] == 2200 and row[5] == "Cr" and row[6] is True, row

    # 3240 Earmarked Gifts Fund: under Reserves & Funds (3200), Cr, has_bf
    row = by_id[3240]
    assert row[4] == 3200 and row[5] == "Cr" and row[6] is True and row[1] == "Earmarked Gifts Fund", row

    # 3260 Gifts Given removed; 51200 expense under 5100, Dr, has_bf False, tab GiftGiven
    assert 3260 not in by_id, "3260 Gifts Given must be gone from the chart"
    row = by_id[51200]
    assert row[4] == 5100 and row[5] == "Dr" and row[6] is False and row[2] == "GiftGiven", row

    # 4140 general income: under 4100, Cr, has_bf False, mutuality non_mutual
    row = by_id[4140]
    assert row[4] == 4100 and row[5] == "Cr" and row[6] is False and row[8] == "non_mutual", row

    # 1200 Non-Current Investments: Dr, has_bf
    row = by_id[1200]
    assert row[3] == "Non-Current Investments" and row[5] == "Dr" and row[6] is True, row

    # every parent_id exists
    ids = set(by_id)
    for row in ACCOUNTS:
        parent = row[4]
        if parent is not None:
            assert parent in ids, f"account {row[0]} ({row[1]}) has missing parent {parent}"

    # no has_bf=True account has an ancestor 4000 (Income) or 5000 (Expense)
    def ancestors(aid):
        seen = set()
        cur = aid
        while cur is not None and cur in by_id:
            cur = by_id[cur][4]
            if cur in seen:
                break
            seen.add(cur)
        return seen

    for aid, row in by_id.items():
        if row[6] is True:
            anc = ancestors(aid)
            assert 4000 not in anc, f"has_bf account {aid} ({row[1]}) under Income root"
            assert 5000 not in anc, f"has_bf account {aid} ({row[1]}) under Expense root"

    # UP_AOA_ACCOUNT_MAPPINGS contains 3240 and 4140; every mapped id exists
    mapped = {a for a, _, _ in UP_AOA_ACCOUNT_MAPPINGS}
    assert 3240 in mapped and 4140 in mapped
    for aid, _, _ in UP_AOA_ACCOUNT_MAPPINGS:
        assert aid in by_id, f"mapping for unknown account {aid}"


def test_no_account_has_duplicate_id():
    by_id = _by_id()
    assert len(by_id) == len(ACCOUNTS)
