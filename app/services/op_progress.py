"""
Progress tracking for database-intensive operations.

A heavy Dash callback keeps running synchronously and returns its normal outputs; while it runs it reports
steps into one ``op_progress`` row. A shell-level modal polls that row (see op_progress_callbacks.py) and shows
a progress bar. The row is keyed by a token the browser generated, and is only readable by the user who owns it.

Writes go through ``db._execute`` (their own connection per call), so progress is visible to the poller even
while the heavy callback's own work is still in flight, and across gunicorn workers.

Every function here is best-effort: a progress failure must never break the operation it is reporting on.
"""
from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Iterable, Iterator

from database.db_manager import db

log = logging.getLogger(__name__)

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_ensured = False

_DDL = """
CREATE TABLE IF NOT EXISTS op_progress (
    token UUID PRIMARY KEY,
    user_id INT,
    society_id INT,
    kind TEXT NOT NULL,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'done', 'failed')),
    step INT NOT NULL DEFAULT 0,
    steps_total INT NOT NULL DEFAULT 1,
    message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


def valid_token(token) -> bool:
    return isinstance(token, str) and bool(_UUID_RE.match(token))


def new_token() -> str:
    return str(uuid.uuid4())


def _ensure_table() -> None:
    """The table is also in estatehub.sql; creating it lazily means a deployed database works without a manual migration."""
    global _ensured  # noqa: PLW0603
    if _ensured:
        return
    db._execute(_DDL)
    _ensured = True


class Tracker:
    """Reports progress of one operation. ``Tracker(None, ...)`` (no valid token) is a silent no-op."""

    def __init__(self, token, kind: str, title: str, steps_total: int = 1,
                 user_id: int | None = None, society_id: int | None = None):
        self.token = token if valid_token(token) else None
        self.steps_total = max(int(steps_total or 1), 1)
        self._last_step = -1
        if not self.token:
            return
        try:
            _ensure_table()
            db._execute("DELETE FROM op_progress WHERE created_at < NOW() - INTERVAL '1 day'")
            db._execute(
                "INSERT INTO op_progress (token, user_id, society_id, kind, title, status, step, steps_total, message) "
                "VALUES (%s,%s,%s,%s,%s,'running',0,%s,%s) "
                "ON CONFLICT (token) DO UPDATE SET status='running', step=0, steps_total=EXCLUDED.steps_total, "
                "kind=EXCLUDED.kind, title=EXCLUDED.title, message=EXCLUDED.message, "
                "user_id=EXCLUDED.user_id, society_id=EXCLUDED.society_id, updated_at=NOW()",
                (self.token, user_id, society_id, kind, title, self.steps_total, "Starting"),
            )
        except Exception:  # noqa: BLE001
            log.exception("op_progress: could not start tracking %s", kind)
            self.token = None

    def step(self, step: int, message: str | None = None) -> None:
        if not self.token:
            return
        step = max(0, min(int(step), self.steps_total))
        if step == self._last_step and message is None:
            return
        self._last_step = step
        try:
            db._execute("UPDATE op_progress SET step=%s, message=COALESCE(%s, message), updated_at=NOW() "
                        "WHERE token=%s AND status='running'", (step, message, self.token))
        except Exception:  # noqa: BLE001, S110
            pass

    def done(self, message: str = "Done") -> None:
        self._finish("done", message)

    def fail(self, message: str = "Failed") -> None:
        self._finish("failed", message)

    def _finish(self, status: str, message: str) -> None:
        if not self.token:
            return
        try:
            db._execute("UPDATE op_progress SET status=%s, step=CASE WHEN %s='done' THEN steps_total ELSE step END, "
                        "message=%s, updated_at=NOW() WHERE token=%s", (status, status, message, self.token))
        except Exception:  # noqa: BLE001, S110
            pass

    def __enter__(self) -> Tracker:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        # Always close the row, so the browser's modal can never be left spinning.
        if exc_type is None:
            if self.token and self._status_is_running():
                self.done()
        else:
            self.fail("Failed")
        return False

    def _status_is_running(self) -> bool:
        try:
            row = db._execute("SELECT status FROM op_progress WHERE token=%s", (self.token,), fetch_one=True)
            return bool(row) and row["status"] == "running"
        except Exception:  # noqa: BLE001
            return True


class _TrackedList(list):
    """A list that reports progress while it is iterated, so a loop in code we do not want to touch
    (``for i, row in enumerate(rows)``) drives the bar by itself."""

    def __init__(self, items: Iterable, tracker: Tracker, label: str):
        super().__init__(items)
        self._tracker, self._label = tracker, label

    def __iter__(self) -> Iterator:
        total = len(self)
        # Report about 50 times however many rows there are, so a 5,000-row file is not 5,000 UPDATEs.
        every = max(total // 50, 1)
        for i, item in enumerate(super().__iter__()):
            if i % every == 0:
                self._tracker.step(int(i / total * self._tracker.steps_total) if total else 0,
                                   f"{self._label} {i + 1} of {total}")
            yield item


def tracked_rows(rows: Iterable, tracker: Tracker, label: str = "Row") -> list:
    """Wrap rows so that iterating them advances ``tracker`` (steps_total should be 100 for a percentage)."""
    return _TrackedList(rows, tracker, label)


def poll(token, user_id: int | None):
    """The row for this token, only if it belongs to ``user_id``. None when absent or not theirs."""
    if not valid_token(token) or user_id is None:
        return None
    try:
        return db._execute("SELECT token, kind, title, status, step, steps_total, message FROM op_progress "
                           "WHERE token=%s AND user_id=%s", (token, user_id), fetch_one=True)
    except Exception:  # noqa: BLE001
        return None


def percent(row) -> int:
    total = int(row.get("steps_total") or 1)
    if row.get("status") == "done":
        return 100
    return max(0, min(99, int(int(row.get("step") or 0) / total * 100)))


def begin(token_store, kind: str, title: str, steps_total: int = 1, society_id: int | None = None) -> Tracker:
    """Open a tracker for the signed-in user from the browser's ``op-token-store`` value ({"token": uuid}).
    Identity comes from the server session; with no usable token the tracker is a silent no-op."""
    from app.security.audit_context import get_current_society_id, get_current_user_id
    token = token_store.get("token") if isinstance(token_store, dict) else token_store
    return Tracker(token, kind, title, steps_total, user_id=get_current_user_id(),
                   society_id=society_id if society_id is not None else get_current_society_id())
