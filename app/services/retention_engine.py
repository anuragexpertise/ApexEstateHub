"""Retention sweep: report-only.

For each society's ``retention_rules`` row the sweep counts the rows of that
record class that are older than ``default_retention_years``. A rule with
``hold_for_disputes`` or ``hold_for_audits`` set makes nothing eligible: the
rows are still counted as too old, but ``total_eligible`` stays 0.

The sweep never deletes. Purging records is a legal decision (see
docs/PHASE0_TRACKER.md, task 0.4); until the CA signs off, a person must act on
the report.

A record class is swept only when it names a real table in the ``public``
schema that has a ``created_at`` column; any other class is reported with
``swept=False``.
"""
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_MAX_IDS = 1000


@dataclass
class SweepResult:
    too_old: list = field(default_factory=list)
    total_eligible: int = 0
    swept: bool = True
    held: bool = False
    years: int = 0


def _sweepable(db, table: str) -> bool:
    row = db._execute(
        "SELECT 1 AS x FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s AND column_name = 'created_at'",
        (table,), fetch_one=True)
    return bool(row)


def sweep_society(db, society_id: int) -> dict:
    results = {}
    rules = db._execute("SELECT * FROM retention_rules WHERE society_id = %s",
                        (society_id,), fetch_all=True) or []
    for r in rules:
        cls = r.get("record_class")
        years = int(r.get("default_retention_years") or 0)
        res = SweepResult(years=years)
        results[(society_id, cls)] = res
        held = bool(r.get("hold_for_disputes") or r.get("hold_for_audits"))
        res.held = held
        if not cls or not _sweepable(db, cls):
            res.swept = False
            continue
        # cls is an existing table name from information_schema, not user input;
        # it is still quoted defensively.
        tbl = '"' + cls.replace('"', '""') + '"'
        cols = {c["column_name"] for c in (db._execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s", (cls,), fetch_all=True) or [])}
        scope = "society_id = %s AND " if "society_id" in cols else ""
        params = ((society_id,) if scope else ()) + (years,)
        rows = db._execute(
            f"SELECT id FROM {tbl} WHERE {scope}created_at < NOW() - make_interval(years => %s) "
            f"ORDER BY id LIMIT {_MAX_IDS}", params, fetch_all=True) if "id" in cols else []
        res.too_old = [x["id"] for x in (rows or [])]
        res.total_eligible = 0 if held else len(res.too_old)
    return results


def sweep_all_societies():
    from database.db_manager import db
    results = {}
    try:
        societies = db._execute("SELECT id FROM societies", fetch_all=True) or []
    except Exception:  # noqa: BLE001
        logger.exception("retention sweep could not list societies")
        return results
    for s in societies:
        try:
            results.update(sweep_society(db, s["id"]))
        except Exception:  # noqa: BLE001
            logger.exception("retention sweep failed for society %s", s["id"])
    return results
