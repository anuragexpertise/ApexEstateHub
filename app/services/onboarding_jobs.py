"""
DB-backed onboarding jobs with progress (item 14).
"""
from __future__ import annotations

import json
import threading
import uuid
from typing import Callable

from app.services import db


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
                except Exception:
                    pass
            res = fn(progress=progress, **kwargs)
            db._execute(
                "UPDATE onboarding_jobs SET status='done', step=steps_total, message=%s, result=%s::jsonb, finished_at=NOW() WHERE id=%s",
                ("Society is live", json.dumps(res or {"ok": True}), job_id),
            )
            try:
                db._execute("INSERT INTO onboarding_events (society_id, event, payload) VALUES (%s,'agreement_signed','{}'::jsonb)",
                            (society_id,))
            except Exception:
                pass
        except Exception as exc:
            try:
                db._execute(
                    "UPDATE onboarding_jobs SET status='failed', error=%s, finished_at=NOW() WHERE id=%s",
                    (str(exc), job_id),
                )
            except Exception:
                pass
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return job_id


def get(job_id: str):
    return db._execute("SELECT * FROM onboarding_jobs WHERE id=%s", (job_id,), fetch_one=True)
