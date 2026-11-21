"""Brought Forward group layout (Plan Streamlining_Brought_Forward, section 5).

Pure Python: no Dash, no database. The only place that knows the grouping of the
Brought Forward grid. Groups are never derived from `database.seed.ACCOUNTS`
parents (the seed parents differ from this grouping).

A node is a dict with optional ``acc`` (account id with its own amount input)
and optional ``children`` (list of nodes), plus ``key`` and ``label`` for
headers. Leaves are plain ints.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TypedDict

from app.services import bf_controls as _bc

LAYOUT = {
    "Cr": [   # LEFT column, titled "Liabilities & Equity (Cr)"
        {"key": "eq", "label": "Equity", "children": [3100]},
        {"key": "res", "label": "Reserves & Funds", "children": [3230, 3270, 3220, 3210, 3280, 3240]},
        {"key": "ncl", "label": "Non-Current Liabilities", "children": [2110]},
        {"key": "cl", "label": "Current Liabilities", "children": [2240, 3250]},
    ],
    "Dr": [   # RIGHT column, titled "Assets (Dr)"
        {"key": "nca", "label": "Non-Current Assets", "children": [
            {"key": "fa", "label": "Fixed Assets", "children": [1110, 1140, 1130, 1120, 1160, 1150]},
            1200]},                                   # Non-Current Investments
        {"key": "ca", "label": "Current Assets", "children": [
            {"key": "bank", "label": "Bank A/c", "children": [1311, 1312]},
            1320, 1330]},
        {"key": "lag", "label": "Loans & Advances Given", "acc": 1400, "children": [1410]},
        {"key": "sdr", "label": "Sundry Debtors", "children": [1510, 1520]},
    ],
}

_SIDES = ("Cr", "Dr")


class RollUpResult(TypedDict, total=False):
    """Shape returned by :func:`roll_up`.

    Group totals keyed by node ``key`` (nested headers included), the side grand total under
    ``"_total"``, and the Annex C control inputs for that side: ``dr``, ``cr``, ``n`` (postable
    accounts the user gave a value for), ``fund_cr``, ``bank_dr``, ``debtors_dr``.
    """
    _total: Decimal
    dr: Decimal
    cr: Decimal
    n: int
    fund_cr: Decimal
    bank_dr: Decimal
    debtors_dr: Decimal


def _seed_meta():
    """id -> {tab, drcr} for every ``has_bf`` account, from the seed chart."""
    from database.seed import ACCOUNTS as _accts
    return {r[0]: {"tab": r[2], "drcr": r[5]} for r in _accts if r[6]}


def _filter_node(node, is_hidden):
    """Return a filtered copy of ``node`` with hidden accounts/empty groups removed, or None."""
    if isinstance(node, int):
        return None if is_hidden(node) else node
    acc = node.get("acc")
    kids = node.get("children") or []
    filtered_kids = []
    for k in kids:
        fk = _filter_node(k, is_hidden)
        if fk is not None:
            filtered_kids.append(fk)
    if acc is not None and is_hidden(acc):
        return None
    if acc is None and not filtered_kids:
        return None  # empty group
    return {"key": node["key"], "label": node["label"], "acc": acc, "children": filtered_kids}


def side_nodes(side, is_hidden) -> list:
    """Visible nodes for ``side`` ("Cr" or "Dr"), hidden accounts and empty groups removed.

    ``is_hidden`` is a callable ``is_hidden(acc_id) -> bool``.
    """
    if side not in _SIDES:
        raise ValueError(f"unknown side {side!r}")
    return [n for n in (_filter_node(n, is_hidden) for n in LAYOUT.get(side, [])) if n is not None]


def _collect(node, out):
    if isinstance(node, int):
        out.append(node)
        return
    if node.get("acc") is not None:
        out.append(node["acc"])
    for k in node.get("children") or []:
        _collect(k, out)


def ordered_account_ids(is_hidden) -> list:
    """Cr side first, then Dr; every visible account id once (used by the template)."""
    out = []
    for side in _SIDES:
        for node in side_nodes(side, is_hidden):
            _collect(node, out)
    return out


def _node_total(node, amounts):
    if isinstance(node, int):
        return _amount(amounts.get(node))
    own = _amount(amounts.get(node.get("acc"))) if node.get("acc") is not None else Decimal(0)
    return own + sum((_node_total(c, amounts) for c in node.get("children") or []), Decimal(0))


def _amount(v):
    try:
        return Decimal(v or 0)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0)


def roll_up(side_nodes_list, amounts: dict, side: str | None = None) -> dict:
    """Roll up one side of the BF grid.

    Returns a :class:`RollUpResult`: totals keyed by node ``key`` (nested headers included),
    the side grand total under ``"_total"``, and the Annex C control inputs for that side
    (``dr``, ``cr``, ``n``, ``fund_cr``, ``bank_dr``, ``debtors_dr``).

    ``amounts`` maps acc_id -> Decimal (blank means 0 / absent). Each postable account's amount
    counts exactly once toward ``_total`` (its own amount if it is an ``acc`` node, otherwise its
    leaf amount).
    """
    meta = _seed_meta()
    totals: dict = {}
    amount_ids = []
    dr = cr = fund_cr = bank_dr = debtors_dr = Decimal(0)
    n = 0

    def _account(acc_id):
        nonlocal dr, cr, fund_cr, bank_dr, debtors_dr, n
        if acc_id not in amounts:
            return
        n += 1
        amt = _amount(amounts.get(acc_id))
        m = meta.get(acc_id) or {}
        drcr = m.get("drcr") or (side or "Dr")
        if drcr == "Dr":
            dr += amt
            if m.get("tab") in _bc.BANK_TABS:
                bank_dr += amt
            if m.get("tab") in _bc.RECEIVABLE_TABS:
                debtors_dr += amt
        else:
            cr += amt
            if m.get("tab") in _bc.FUND_TABS:
                fund_cr += amt

    def _walk(nodes):
        for node in nodes:
            if isinstance(node, int):
                amount_ids.append(node)
                _account(node)
                continue
            acc = node.get("acc")
            if acc is not None:
                amount_ids.append(acc)
                _account(acc)
            totals[node["key"]] = _node_total(node, amounts)
            _walk(node.get("children") or [])

    _walk(side_nodes_list)
    totals["_total"] = sum((_amount(amounts.get(i)) for i in amount_ids), Decimal(0))
    totals["dr"] = dr
    totals["cr"] = cr
    totals["n"] = n
    totals["fund_cr"] = fund_cr
    totals["bank_dr"] = bank_dr
    totals["debtors_dr"] = debtors_dr
    return totals


def _validate():
    from database.seed import ACCOUNTS as _accts
    acc_info = {r[0]: r for r in _accts}
    seen = set()
    for side in _SIDES:
        _validate_side(LAYOUT.get(side, []), side, acc_info, seen)
    bf_accounts = {r[0] for r in _accts if r[6]}
    missing = bf_accounts - seen
    extra = seen - bf_accounts
    if missing:
        raise ImportError(f"bf_layout: has_bf accounts missing from layout: {sorted(missing)}")
    if extra:
        raise ImportError(f"bf_layout: layout ids not has_bf accounts: {sorted(extra)}")


def _validate_side(nodes, side, acc_info, seen):
    for node in nodes:
        if isinstance(node, int):
            _check_leaf(node, side, acc_info, seen)
            continue
        acc = node.get("acc")
        if acc is not None:
            _check_leaf(acc, side, acc_info, seen)
        _validate_side(node.get("children") or [], side, acc_info, seen)


def _check_leaf(acc_id, side, acc_info, seen):
    if acc_id not in acc_info:
        raise ImportError(f"bf_layout: layout id {acc_id} is not in ACCOUNTS")
    r = acc_info[acc_id]
    if not r[6]:
        raise ImportError(f"bf_layout: layout id {acc_id} ({r[1]}) has has_bf=False")
    if r[5] != side:
        raise ImportError(f"bf_layout: layout id {acc_id} ({r[1]}) is {r[5]} but placed under {side}")
    if acc_id in seen:
        raise ImportError(f"bf_layout: duplicate layout id {acc_id}")
    seen.add(acc_id)


_validate()
