# app/services/chart_drift.py
"""
Chart-of-accounts drift detection.

Pure function: compare the live accounts table (``rows_from_db``) against the
seed chart (``ACCOUNTS``) per society and report differences in ``id``,
``name``, ``parent``, ``nature`` (``drcr_account``) and ``has_bf``.

No database access, no side effects — unit tested against in-memory rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable, Mapping

_SEED_SOCIETY = 1  # ACCOUNTS is society-scoped by id; the demo society is id 1.


@dataclass(frozen=True)
class Difference:
    society_id: int
    account_id: int
    field: str  # 'missing' | 'extra' | 'name' | 'parent' | 'nature' | 'has_bf'
    seed_value: object
    live_value: object


def _seed_by_id(accounts: Iterable[tuple]) -> dict[int, tuple]:
    out: dict[int, tuple] = {}
    for row in accounts:
        out[row[0]] = row
    return out


def chart_drift(rows_from_db: Iterable[Mapping], accounts: Iterable[tuple]) -> list[Difference]:
    """Return differences between the live accounts rows and the seed chart.

    ``rows_from_db``: iterable of mappings with keys ``society_id``, ``id``,
    ``name``, ``parent_account_id``, ``drcr_account``, ``has_bf``.

    ``accounts``: iterable of ACCOUNTS tuples
    ``(aid, name, tab, header, parent, drcr, has_bf, dep, mutuality, tds)``.

    Compares, per society, account presence plus ``name``, ``parent``,
    ``nature`` (``drcr_account``) and ``has_bf``.
    """
    seed_by_id = _seed_by_id(accounts)

    live_by_society: dict[int, dict[int, Mapping]] = {}
    for row in rows_from_db:
        sid = row["society_id"]
        live_by_society.setdefault(sid, {})[row["id"]] = row

    differences: list[Difference] = []
    for sid, live_accounts in live_by_society.items():
        for aid, seed_row in seed_by_id.items():
            live_row = live_accounts.get(aid)
            if live_row is None:
                differences.append(Difference(sid, aid, "missing", seed_row, None))
                continue
            comparisons = [
                ("name", seed_row[1], live_row.get("name")),
                ("parent", seed_row[4], live_row.get("parent_account_id")),
                ("nature", seed_row[5], live_row.get("drcr_account")),
                ("has_bf", seed_row[6], live_row.get("has_bf")),
            ]
            for field, seed_val, live_val in comparisons:
                if seed_val != live_val:
                    differences.append(Difference(sid, aid, field, seed_val, live_val))

        # Live accounts that the seed chart does not define at all.
        seed_ids = set(seed_by_id)
        for aid in sorted(live_accounts):
            if aid not in seed_ids:
                differences.append(Difference(sid, aid, "extra", None, live_accounts[aid]))

    return differences
