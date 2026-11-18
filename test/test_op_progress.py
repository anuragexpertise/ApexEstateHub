"""Progress tracking for database-intensive operations (app/services/op_progress.py). No live database needed."""
import re

import pytest

from app.services import op_progress as op

TOKEN = "123e4567-e89b-42d3-a456-426614174000"


class FakeDB:
    """Just enough of db._execute for op_progress: one op_progress row keyed by token."""

    def __init__(self):
        self.rows, self.sql = {}, []

    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        self.sql.append(sql)
        s = " ".join(sql.split())
        if s.startswith("INSERT INTO op_progress"):
            t, user, soc, kind, title, total, msg = params
            self.rows[t] = dict(token=t, user_id=user, society_id=soc, kind=kind, title=title, status="running",
                                step=0, steps_total=total, message=msg)
        elif s.startswith("UPDATE op_progress SET step=%s, message=COALESCE"):
            step, msg, t = params
            r = self.rows[t]
            if r["status"] == "running":
                r["step"] = step
                r["message"] = msg if msg is not None else r["message"]
        elif s.startswith("UPDATE op_progress SET status="):
            status, _s2, msg, t = params
            r = self.rows[t]
            r["status"], r["message"] = status, msg
            if status == "done":
                r["step"] = r["steps_total"]
        elif s.startswith("SELECT status"):
            r = self.rows.get(params[0])
            return {"status": r["status"]} if r else None
        elif s.startswith("SELECT token, kind"):
            r = self.rows.get(params[0])
            return dict(r) if r and r["user_id"] == params[1] else None
        return None


@pytest.fixture
def fake(monkeypatch):
    f = FakeDB()
    monkeypatch.setattr(op, "db", f)
    monkeypatch.setattr(op, "_ensured", True)
    return f


def test_token_validation():
    assert op.valid_token(TOKEN)
    assert op.valid_token(op.new_token())
    for bad in (None, "", "abc", TOKEN + "x", "'; DROP TABLE x;--", 5):
        assert not op.valid_token(bad)


def test_invalid_token_is_a_silent_noop(fake):
    t = op.Tracker("not-a-token", "k", "T", 10, user_id=1)
    t.step(5, "x")
    t.done()
    assert fake.rows == {}


def test_steps_and_done(fake):
    with op.Tracker(TOKEN, "bulk", "Enrolling", 100, user_id=7, society_id=3) as t:
        t.step(40, "Row 40 of 100")
        assert op.percent(op.poll(TOKEN, 7)) == 40
    row = op.poll(TOKEN, 7)
    assert row["status"] == "done" and op.percent(row) == 100


def test_exception_marks_failed(fake):
    with pytest.raises(RuntimeError):
        with op.Tracker(TOKEN, "bulk", "Enrolling", 100, user_id=7):
            raise RuntimeError("boom")
    assert fake.rows[TOKEN]["status"] == "failed"


def test_running_percent_never_reaches_100_before_done(fake):
    t = op.Tracker(TOKEN, "k", "T", 4, user_id=1)
    t.step(4)
    assert op.percent(op.poll(TOKEN, 1)) == 99


def test_rows_of_another_user_are_not_visible(fake):
    op.Tracker(TOKEN, "k", "T", 4, user_id=1)
    assert op.poll(TOKEN, 2) is None
    assert op.poll(TOKEN, None) is None
    assert op.poll("garbage", 1) is None


def test_tracked_rows_reports_and_preserves_the_list(fake):
    t = op.Tracker(TOKEN, "k", "T", 100, user_id=1)
    rows = op.tracked_rows([{"a": i} for i in range(200)], t, "Row")
    assert len(rows) == 200
    seen = [r["a"] for _, r in enumerate(rows)]
    assert seen == list(range(200))
    updates = [s for s in fake.sql if "UPDATE op_progress SET step" in s]
    assert 40 <= len(updates) <= 60          # about 50 writes for 200 rows, not 200
    assert fake.rows[TOKEN]["step"] >= 95
    assert re.match(r"Row \d+ of 200", fake.rows[TOKEN]["message"])


def test_tracked_rows_empty(fake):
    t = op.Tracker(TOKEN, "k", "T", 100, user_id=1)
    assert list(op.tracked_rows([], t)) == []


def test_celebration_payload():
    from app.utils.ux_toasts import celebration, normalize_toast
    c = celebration("registered", "Acme is registered", "msg", ["a"], key="k1")
    assert c == {"kind": "registered", "title": "Acme is registered", "message": "msg", "details": ["a"], "key": "k1"}
    assert "key" not in celebration("sealed", "t")
    # a toast carrying a celebration keeps it through normalisation
    n = normalize_toast({"type": "success", "message": "ok", "celebrate": c})
    assert n["celebrate"] == c
