"""
DB-backed onboarding jobs with progress (item 14).
"""
from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable

from database.db_manager import db


def start(kind: str, society_id: int, actor_id: int | None, fn: Callable, **kwargs) -> str:
    job_id = str(uuid.uuid4())
    db._execute(
        "INSERT INTO onboarding_jobs (id, society_id, kind, status, step, steps_total, created_by) VALUES (%s,%s,%s,'queued',0,7,%s)",
        (job_id, society_id, kind, actor_id),
    )
    def _run():
        try:
            db._execute("UPDATE onboarding_jobs SET status='running', started_at=NOW() WHERE id=%s", (job_id,))
            def progress(step: int, message: str):
                try:
                    db._execute("UPDATE onboarding_jobs SET step=%s, message=%s WHERE id=%s", (int(step), message, job_id))
                except Exception:  # noqa: BLE001, S110
                    pass
            res = fn(progress=progress, **kwargs)
            db._execute(
                "UPDATE onboarding_jobs SET status='done', step=steps_total, message=%s, result=%s::jsonb, finished_at=NOW() WHERE id=%s",
                ("Society is live", json.dumps(res or {"ok": True}, default=str), job_id),
            )
        except Exception as exc:  # noqa: BLE001
            try:
                db._execute(
                    "UPDATE onboarding_jobs SET status='failed', error=%s, finished_at=NOW() WHERE id=%s",
                    (str(exc), job_id),
                )
            except Exception:  # noqa: BLE001, S110
                pass
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return job_id


def get(job_id: str, society_id: int | None = None):
    """Fetch a job. When society_id is given the job must belong to it, so one society can never poll another's job."""
    if society_id is not None:
        return db._execute("SELECT * FROM onboarding_jobs WHERE id=%s AND society_id=%s", (job_id, society_id), fetch_one=True)
    return db._execute("SELECT * FROM onboarding_jobs WHERE id=%s", (job_id,), fetch_one=True)


def latest_running(society_id: int):
    """A page refresh resumes polling for any queued/running job of this society."""
    return db._execute("SELECT * FROM onboarding_jobs WHERE society_id=%s AND status IN ('queued','running') "
                       "ORDER BY created_at DESC LIMIT 1", (society_id,), fetch_one=True)
