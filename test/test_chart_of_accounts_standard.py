"""Chart of accounts follows standard accounting practice (Plan Streamlining_Brought_Forward, section 4A.5).

Pure: imports database.seed.ACCOUNTS and UP_AOA_ACCOUNT_MAPPINGS only; no database, no Dash.
"""
from database.seed import ACCOUNTS, UP_AOA_ACCOUNT_MAPPINGS

ROOTS = {1000: "Dr", 2000: "Cr", 3000: "Cr", 4000: "Cr", 5000: "Dr"}
# I1 contra allow-list: contra (Cr) accounts that legitimately sit under a Dr
# root (accumulated depreciation, provision for doubtful debts). Exempt from
# the nature-agrees-with-root check; a second test asserts this set is exact.
CONTRA_ACCOUNTS = {1190, 1530}


def _root_of(aid, by_id):
    seen = set()
    cur = aid
    while cur is not None and cur not in seen:
        seen.add(cur)
        cur = by_id[cur][4]
    return next((x for x in seen if x in ROOTS), None)


def _by_id():
    by_id = {}
    for row in ACCOUNTS:
        aid = row[0]
        assert aid not in by_id, f"duplicate account id {aid}"
        by_id[aid] = row
    return by_id


def _mapping():
    return {aid: head for aid, head, _ in UP_AOA_ACCOUNT_MAPPINGS}


def _ancestors(aid, by_id):
    seen = {aid}
    cur = aid
    while cur is not None and cur in by_id:
        cur = by_id[cur][4]
        if cur is None or cur in seen:
            break
        seen.add(cur)
    return seen


def test_chart_of_accounts_standard():
    by_id = _by_id()

    # 3250 Provisions: liability under Current Liabilities (2200), Cr, has_bf
    row = by_id[2250]
    assert row[4] == 2200 and row[5] == "Cr" and row[6] is True, row

    # 3240 Earmarked Gifts Fund: under Reserves & Funds (3200), Cr, has_bf
    row = by_id[3240]
    assert row[4] == 3200 and row[5] == "Cr" and row[6] is True and row[1] == "Earmarked Gifts Fund", row

    # 3260 Gifts Given removed; 51200 expense under 5100, Dr, has_bf False, tab GiftGiven
    assert 3250 not in by_id, "3250 Provisions must be gone from the chart"
    row = by_id[5196]
    assert row[4] == 5100 and row[5] == "Dr" and row[6] is False and row[2] == "Gift", row

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
    assert 3240 in mapped and 4140 in mapped and 2250 in mapped and 3300 in mapped
    for aid, _, _ in UP_AOA_ACCOUNT_MAPPINGS:
        assert aid in by_id, f"mapping for unknown account {aid}"


# Section 6 invariants — I1/I2/I3 now run as module-level tests
# (test/test_chart_of_accounts_standard.py); I5/I6 are covered by the live
# SQL file (test/live_icai_checks.sql). I4/I7 are live checks too.


def test_I1_nature_agrees_with_root():
    """I1: every account's Dr/Cr nature agrees with its root, except the
    commented contra allow-list {1190, 1530}."""
    by_id = _by_id()
    for aid, row in by_id.items():
        root = _root_of(aid, by_id)
        if root is None or row[5] is None or aid in CONTRA_ACCOUNTS:
            continue
        assert row[5] == ROOTS[root], \
            f"account {aid} ({row[1]}) is {row[5]} under root {root} ({ROOTS[root]})"


def test_I1_contra_accounts_under_dr_root_exact():
    """I1 second test: the set of Cr accounts under the Dr root is exactly the
    contra allow-list {1190, 1530}."""
    by_id = _by_id()
    cr_under_dr = {
        aid for aid, row in by_id.items()
        if row[5] == "Cr" and _root_of(aid, by_id) == 1000
    }
    assert cr_under_dr == CONTRA_ACCOUNTS, \
        f"Cr accounts under Dr root: {sorted(cr_under_dr)}, expected {sorted(CONTRA_ACCOUNTS)}"


def test_I2_id_range_and_four_digits():
    """I2: every id sits in its root's thousand-range; all ids are four digits."""
    by_id = _by_id()
    for aid, row in by_id.items():
        root = _root_of(aid, by_id)
        if root is None:
            continue
        assert (aid // 1000) == (root // 1000), \
            f"account {aid} not in root {root}\'s thousand-range"
        assert 1000 <= aid <= 9999, f"account {aid} is not four digits"


def test_I3_no_group_account_mapped():
    """I3/F-18: no group account carries a statutory head."""
    mapping = _mapping()
    assert 1100 not in mapping, "group account 1100 (Fixed Assets) has a statutory head mapping"
    assert 1300 not in mapping, "group account 1300 (Current Assets) has a statutory head mapping"


def test_statutory_head_mappings_section_3_1():
    """T3: each mapping from plan section 3.1 table, and no group account mapped."""
    by_id = _by_id()
    mapping = {aid: head for aid, head, _ in UP_AOA_ACCOUNT_MAPPINGS}

    expected = {
        2290: "TAX_PAYABLE",      # F-14: TDS Payable
        2255: "TAX_PAYABLE",      # Provision for Income Tax
        5220: "INCOME_TAX_EXPENSE",  # F-13: Income Tax expense head
        3240: "EARMARKED_FUNDS",     # C2/F-17: Earmarked Gifts Fund → its own Equity head
        5170: "OTHER_EXPENSES",   # F-15: Electricity
        5180: "OTHER_EXPENSES",   # F-15: Water Tax
        5190: "OTHER_EXPENSES",   # F-15: House Tax
        5101: "ADMIN_EXPENSES",   # F-15: Insurance
        5195: "OTHER_EXPENSES",   # GST on Asset Disposal
        2250: "OTHER_LIABILITIES",  # Provisions
        2120: "OTHER_LIABILITIES",  # Long-term Provisions
    }
    for aid, head in expected.items():
        assert aid in mapping, f"account {aid} ({by_id[aid][1]}) missing statutory mapping"
        assert mapping[aid] == head, (
            f"account {aid} ({by_id[aid][1]}) maps to {mapping[aid]}, expected {head}")

    # F-18: group accounts carry no statutory head
    assert 1100 not in mapping, "group account 1100 must not be mapped"
    assert 1300 not in mapping, "group account 1300 must not be mapped"

    # every mapped id exists and is not a root
    for aid, head, _ in UP_AOA_ACCOUNT_MAPPINGS:
        assert aid in by_id, f"mapping for unknown account {aid}"
        assert by_id[aid][4] is not None, f"root account {aid} ({by_id[aid][1]}) has a mapping"


def test_no_account_has_duplicate_id():
    by_id = _by_id()
    assert len(by_id) == len(ACCOUNTS)
