#!/usr/bin/env python3
"""
Run one scheduled job and log it in job_runs (see app/services/job_runner.py).

    python scripts/run_job.py anchors        # daily:  anchor every society, then verify every signature
    python scripts/run_job.py patrol         # hourly
    python scripts/run_job.py ratification   # daily
    python scripts/run_job.py watchdog       # hourly: alerts when a job above has not run on time

The jobs refuse to run as the database owner or a superuser (set JOB_ALLOW_OWNER_LOGIN=1 only on a development machine).
See docs/SCHEDULER.md for the schedule, the login and how to read the run log.

Suggested schedule (hosts differ; check yours in task 0.6): anchors 0 21 * * * UTC (02:30 IST), patrol 0 * * * *,
ratification 30 21 * * * UTC. The scheduler's own environment needs the database login and SECRET_VAULT_KEY.
Exit status is 1 when the job failed.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.job_runner import JOBS, run_job  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in JOBS:
        print(f"usage: run_job.py {{{'|'.join(sorted(JOBS))}}}", file=sys.stderr)
        return 2
    if os.getenv("JOB_ALLOW_OWNER_LOGIN", "").strip().lower() not in ("1", "true", "yes"):
        from app.services.job_runner import alert_masters, check_restricted_login
        why = check_restricted_login()
        if why:
            msg = f"{sys.argv[1]} not run: {why}"
            print("refused", msg, file=sys.stderr)
            try:
                alert_masters(sys.argv[1], msg)
            except Exception:                                      # noqa: BLE001 - the exit status still flags it
                pass
            return 1
    out = run_job(sys.argv[1])
    print(out["status"], out.get("detail") or out.get("error"))
    return 0 if out["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
