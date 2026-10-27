#!/usr/bin/env python3
"""
Run one scheduled job and log it in job_runs (see app/services/job_runner.py).

    python scripts/run_job.py anchors        # daily:  anchor every society, then verify every signature
    python scripts/run_job.py patrol         # hourly
    python scripts/run_job.py ratification   # daily

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
    out = run_job(sys.argv[1])
    print(out["status"], out.get("detail") or out.get("error"))
    return 0 if out["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
