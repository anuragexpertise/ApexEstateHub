"""
Scheduled jobs (Gold-Standard Plan v3, task 1.4). Host-neutral: any scheduler (ApexWeave, Render cron, cron) runs

    python scripts/run_job.py <job>

Each run writes a `job_runs` row (started, finished, ok/failed, detail, error). A failure raises an alert to every
platform master and the process exits non-zero so the scheduler also flags it. Jobs should use the restricted
application login (database/app_role.py), not the owner.

    anchors      daily   anchor every society's ledger chain and verify every anchor signature
    patrol       hourly  mark missed patrols and assign new ones
    ratification daily   expire overdue ratifications (fn_expire_overdue_ratifications)
    watchdog     hourly  alert the masters when any of the above has not run lately (a scheduler that never fires
                         leaves no failed row, so only a check on the log can notice it)

Plan v4, C.8. The schedule itself lives on the host: see docs/SCHEDULER.md.
"""
from __future__ import annotations

import json
import logging
import traceback

log = logging.getLogger(__name__)


def _db(db=None):
    if db is not None:
        return db
    from database.db_manager import db as _default
    return _default


def job_anchors(db=None) -> dict:
    from app.security import ledger_anchor
    results = ledger_anchor.anchor_all(None, "scheduled", db=_db(db))
    failed = [r for r in results if not r["ok"]]
    bad_sigs = ledger_anchor.verify_signatures(None, db=_db(db))
    detail = {"anchored": len(results) - len(failed), "failed": [{"society_id": r["society_id"], "error": r["error"]} for r in failed],
              "signature_problems": bad_sigs}
    if failed or bad_sigs:
        raise JobFailed(f"{len(failed)} society anchors failed, {len(bad_sigs)} signature problems", detail)
    return detail


def job_patrol(db=None) -> dict:
    import scripts.patrol_cron as pc  # noqa: WPS433
    pc.init_db()
    pc.check_missed_tasks()
    pc.assign_random_patrols()
    return {"ran": True}


def job_ratification(db=None) -> dict:
    d = _db(db)
    items = d._execute("SELECT fn_expire_ratification_items() AS n", fetch_one=True)
    row = d._execute("SELECT fn_expire_overdue_ratifications() AS n", fetch_one=True)
    row = {"n": int(row["n"] or 0) + int((items or {}).get("n") or 0)}
    return {"expired": int(row["n"])}


# How long each job may go without a finished, successful run before the watchdog complains. Daily jobs get a little over a
# day (a late scheduler start is not an outage); hourly jobs get a little over two hours.
MAX_AGE_HOURS = {"anchors": 26, "patrol": 2.5, "ratification": 26}


def job_watchdog(db=None) -> dict:
    d = _db(db)
    stale = []
    for name, hours in MAX_AGE_HOURS.items():
        row = d._execute("SELECT MAX(finished_at) AS last_ok FROM job_runs WHERE job_name=%s AND status='ok'", (name,), fetch_one=True)
        age = d._execute("SELECT EXTRACT(EPOCH FROM (NOW() - %s::timestamp)) / 3600.0 AS h", ((row or {}).get("last_ok"),), fetch_one=True) \
            if (row or {}).get("last_ok") else None
        if age is None or float(age["h"]) > hours:
            stale.append({"job": name, "last_ok": str((row or {}).get("last_ok")), "max_age_hours": hours})
    if stale:
        raise JobFailed("not run on time: " + ", ".join(x["job"] for x in stale), {"stale": stale})
    return {"checked": sorted(MAX_AGE_HOURS)}


def check_restricted_login(db=None) -> str | None:
    """None when the connection is the restricted application login; otherwise why it is not. The scheduler must not run
    as the owner or a superuser, because that is the login the append-only protections are meant to hold against."""
    row = _db(db)._execute(
        "SELECT r.rolsuper AS su, current_user AS who, "
        "       EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'estatehub_app') AS role_exists, "
        "       CASE WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'estatehub_app') "
        "            THEN pg_has_role(current_user, 'estatehub_app', 'member') ELSE FALSE END AS app_member "
        "FROM pg_roles r WHERE r.rolname = current_user", fetch_one=True)
    if not row:
        return "could not read the database login"
    if row["su"]:
        return f"connected as superuser {row['who']!r}; use the restricted login (database/app_role.py)"
    if not row["role_exists"]:
        return "the estatehub_app role does not exist; run database/app_role.py --apply"
    if not row["app_member"]:
        return f"login {row['who']!r} is not a member of estatehub_app (database/app_role.py)"
    return None


JOBS = {"anchors": job_anchors, "patrol": job_patrol, "ratification": job_ratification, "watchdog": job_watchdog}


class JobFailed(RuntimeError):
    def __init__(self, msg, detail=None):
        super().__init__(msg)
        self.detail = detail


def alert_masters(job: str, error: str, db=None) -> int:
    """Best effort: push a notification to every platform master. Returns how many were attempted."""
    d = _db(db)
    masters = d._execute("SELECT id FROM users WHERE role = 'master'", fetch_all=True) or []
    try:
        from app.services.push_service import send_push_notification
    except Exception:                                              # noqa: BLE001
        return 0
    n = 0
    for m in masters:
        try:
            send_push_notification(user_id=m["id"], title=f"Scheduled job failed: {job}", body=error[:200])
            n += 1
        except Exception:                                          # noqa: BLE001
            log.exception("could not alert master %s", m["id"])
    return n


def run_job(name: str, db=None, alert=alert_masters) -> dict:
    """Run one job and record it. Returns {'status', 'detail'|'error'}. Never raises for a job failure."""
    if name not in JOBS:
        raise ValueError(f"Unknown job {name!r}; choose from {sorted(JOBS)}")
    d = _db(db)
    run = d._execute("INSERT INTO job_runs (job_name) VALUES (%s) RETURNING id", (name,), fetch_one=True)
    try:
        detail = JOBS[name](d)
        d._execute("UPDATE job_runs SET status='ok', finished_at=NOW(), detail=%s::jsonb WHERE id=%s",
                   (json.dumps(detail, default=str), run["id"]))
        return {"status": "ok", "detail": detail, "run_id": run["id"]}
    except Exception as exc:                                       # noqa: BLE001 - recorded and alerted, not hidden
        detail = getattr(exc, "detail", None)
        msg = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
        d._execute("UPDATE job_runs SET status='failed', finished_at=NOW(), detail=%s::jsonb, error=%s WHERE id=%s",
                   (json.dumps(detail, default=str) if detail is not None else None, msg + "\n" + traceback.format_exc()[-1500:], run["id"]))
        try:
            alert(name, msg, d)
        except Exception:                                          # noqa: BLE001
            log.exception("alerting masters failed")
        return {"status": "failed", "error": msg, "run_id": run["id"]}
