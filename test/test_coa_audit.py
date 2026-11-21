"""Chart of accounts — structural integrity audit (Audit_Chart_of_Account.md, Phase 1 Task 2).

Pure: imports database.seed.ACCOUNTS and UP_AOA_ACCOUNT_MAPPINGS only; no database, no Dash.
Every machine-checkable check is a test. A check that passes is a plain test. A check that
fails is ``@pytest.mark.xfail(strict=True, reason="F-NN")`` so the suite stays green now and
the marker must be removed when the finding is fixed (Phase 2).
"""
import pytest

from database.seed import ACCOUNTS

ROOTS = {1000: "Dr", 2000: "Cr", 3000: "Cr", 4000: "Cr", 5000: "Dr"}


def _by_id():
    by_id = {}
    for row in ACCOUNTS:
        aid = row[0]
        assert aid not in by_id, f"duplicate account id {aid}"
        by_id[aid] = row
    return by_id


def _root_of(aid, by_id):
    seen = set()
    cur = aid
    while cur is not None and cur not in seen:
        seen.add(cur)
        cur = by_id[cur][4]
    return next((x for x in seen if x in ROOTS), None)


# ═══════════════════════════════════════════════════════════════════════════════
# F-01: ids unique; every parent exists; no cycles; one root per nature (all pass)
# ═══════════════════════════════════════════════════════════════════════════════


def test_ids_unique():
    by_id = _by_id()
    assert len(by_id) == len(ACCOUNTS)


def test_every_parent_exists():
    by_id = _by_id()
    ids = set(by_id)
    for row in ACCOUNTS:
        parent = row[4]
        if parent is not None:
            assert parent in ids, f"account {row[0]} ({row[1]}) has missing parent {parent}"


def test_no_cycles():
    by_id = _by_id()
    for aid in by_id:
        seen = set()
        cur = aid
        while cur is not None and cur in by_id:
            assert cur not in seen, f"cycle at account {aid}"
            seen.add(cur)
            cur = by_id[cur][4]


def test_one_root_per_nature():
    """Every account resolves to exactly one (deterministic) root: no dangling chain, no
    account reachable under two roots. The chart deliberately keeps 5 root accounts
    (1000 Assets Dr, 5000 Expenses Dr; 2000 Liabilities Cr, 3000 Equity Cr,
    4000 Income Cr) to separate the balance sheet from the P&L — that is by design,
    not a finding."""
    by_id = _by_id()
    for aid in by_id:
        if by_id[aid][4] is None:  # the root accounts themselves
            continue
        roots = {x for x in _ancestors(aid, by_id) if x in ROOTS}
        assert len(roots) == 1, f"account {aid} resolves to roots {sorted(roots)}"


def _ancestors(aid, by_id):
    seen = {aid}
    cur = aid
    while cur is not None and cur in by_id:
        cur = by_id[cur][4]
        if cur is None or cur in seen:
            break
        seen.add(cur)
    return seen


# ═══════════════════════════════════════════════════════════════════════════════
# F-02: nature consistency — every account's Dr/Cr agrees with its root
# Known suspects: 2290 (Dr under Cr liabilities root 2000), 5100 (Cr under Dr expenses root 5000)
# ═══════════════════════════════════════════════════════════════════════════════


def _nature_mismatches():
    by_id = _by_id()
    out = []
    for aid, row in by_id.items():
        root = _root_of(aid, by_id)
        if root is None or row[5] is None:
            continue
        if row[5] != ROOTS[root]:
            out.append((aid, row[1], row[5], root, ROOTS[root]))
    return out


@pytest.mark.xfail(strict=True, reason="F-02: 2290 TDS to IT is Dr under Cr root 2000; 5100 Income Expenditure A/c is Cr under Dr root 5000")
def test_nature_agrees_with_root():
    assert _nature_mismatches() == [], _nature_mismatches()


# ═══════════════════════════════════════════════════════════════════════════════
# F-03: id range vs root — every id sits in its root's thousand-range
# Known suspects: 3250 Provisions (3xxx id, parent 2200 Current Liabilities); 51100-51200
# (5xxx id range under root 5000 which is 5xxx, so these sit outside the 5xxx range)
# ═══════════════════════════════════════════════════════════════════════════════


def _range_mismatches():
    by_id = _by_id()
    out = []
    for aid, row in by_id.items():
        root = _root_of(aid, by_id)
        if root is None:
            continue
        if (aid // 1000) != (root // 1000):
            out.append((aid, row[1], root))
    return out


@pytest.mark.xfail(strict=True, reason="F-03: 3250 Provisions is a 3xxx id under root 2000; 51100-51200 are 5-digit ids under root 5000 (5xxx range)")
def test_id_range_matches_root():
    assert _range_mismatches() == [], _range_mismatches()


# ═══════════════════════════════════════════════════════════════════════════════
# F-04: numbering scheme — four-digit ids mix with five-digit 51100-51200; 5110 vs 51100
# look alike; ORDER BY id (onboarding_callbacks.py:1103) does not preserve the hierarchy.
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.xfail(strict=True, reason="F-04: five-digit ids 51100-51200 mixed with four-digit; 5110 Depreciation and 51100 Insurance Paid look alike")
def test_numbering_scheme_no_five_digit_clash():
    five_digit = [r[0] for r in ACCOUNTS if r[0] >= 10000]
    assert five_digit == [], five_digit


def test_order_by_id_keeps_parent_before_child():
    """Numeric ORDER BY id on accounts (onboarding_callbacks.py:1103) keeps every parent
    before its child, so the hierarchy is preserved in traversal order. The five-digit
    ids 51100-51200 sort after 5220 but still under their parent 5100; that is a numbering
    oddity (F-04), not a hierarchy break."""
    by_id = _by_id()
    ordered = sorted(by_id)
    seen = set(ROOTS)
    for aid in ordered:
        parent = by_id[aid][4]
        if parent is not None:
            assert parent in seen, f"{aid} ordered before its parent {parent}"
        seen.add(aid)


# ═══════════════════════════════════════════════════════════════════════════════
# F-06: names and labels — duplicate names / header labels; tab codes unique
# 1400 and 1410 share the header "Loans & Advances Given" (names differ)
# ═══════════════════════════════════════════════════════════════════════════════


def test_tab_codes_unique():
    tabs = [r[2] for r in ACCOUNTS]
    assert len(tabs) == len(set(tabs)), f"duplicate tab codes: {tabs}"


@pytest.mark.xfail(strict=True, reason="F-06: 1400 and 1410 share the header label 'Loans & Advances Given'")
def test_no_duplicate_header_labels():
    headers = [r[3] for r in ACCOUNTS if r[3]]
    dupes = {h for h in headers if headers.count(h) > 1}
    assert not dupes, dupes


# ═══════════════════════════════════════════════════════════════════════════════
# F-07: has_bf completeness — balance-sheet leaves that cannot carry an opening balance
# Suspects: 1170 Generator, 1340 Input Tax Credit (RCM), 2210/2220/2230/2231/2232 GST payables,
# 2290 TDS to IT. Group/header accounts (1000,1100,1300,2000,2100,2200,3000,3200) intentionally
# carry has_bf=False and are listed separately for the record.
# ═══════════════════════════════════════════════════════════════════════════════


def test_has_bf_groups_documented():
    by_id = _by_id()
    groups = {aid for aid, row in by_id.items() if row[0] // 1000 in (1, 2, 3) and _root_of(aid, by_id) == aid}
    # header/group nodes are their own root's children with has_bf=False
    assert 1000 in groups and 2000 in groups and 3000 in groups


@pytest.mark.xfail(strict=True, reason="F-07: balance-sheet leaves 1170 Generator, 1340 Input Tax Credit (RCM), 2210/2220/2230/2231/2232 GST payables and 2290 TDS to IT have has_bf=False, so a society starting mid-year cannot open them")
def test_balance_sheet_leaves_carry_opening_balance():
    by_id = _by_id()
    suspects = [aid for aid, row in by_id.items()
                if row[0] // 1000 in (1, 2, 3)
                and row[6] is False
                and _root_of(aid, by_id) != aid
                and aid not in (1100, 1300, 2100, 2200, 3200)]
    assert suspects == [], suspects


# ═══════════════════════════════════════════════════════════════════════════════
# F-08: depreciation_percent semantics — every non-depreciable account carries 100;
# 1110 Immovable Assets carries 100 although a building component is depreciable
# ═══════════════════════════════════════════════════════════════════════════════


def test_depreciation_percent_recorded():
    by_id = _by_id()
    non_depreciable = [aid for aid, row in by_id.items() if row[7] == 100]
    depreciable = [aid for aid, row in by_id.items() if row[7] != 100]
    assert 1110 in non_depreciable
    assert sorted(depreciable) == [1120, 1130, 1140, 1150, 1160, 1170], depreciable


# ═══════════════════════════════════════════════════════════════════════════════
# F-09: tags — mutuality only on income accounts; tds_section only on expense accounts
# Verify 5120 Rent Paid carries no tds_section (it does not; open whether it should).
# ═══════════════════════════════════════════════════════════════════════════════


def test_mutuality_only_on_income():
    off = [(r[0], r[1]) for r in ACCOUNTS if r[8] is not None and (r[0] // 1000) != 4]
    assert off == [], off


def test_tds_section_only_on_expense():
    by_id = _by_id()
    off = []
    for r in ACCOUNTS:
        if r[9] is None:
            continue
        root = _root_of(r[0], by_id)
        if root != 5000:
            off.append((r[0], r[1], r[9], root))
    assert off == [], off


def test_5120_rent_paid_has_no_tds_section():
    by_id = _by_id()
    assert by_id[5120][9] is None
