"""A failure while COMMITting must never re-run the statement.

If the connection drops during COMMIT the server may already have committed;
re-executing a non-idempotent statement (ledger posting, receipt, insert)
would apply it twice. Failures before COMMIT are safe to retry (the server
rolls the open transaction back when the connection dies).
"""
import threading

import psycopg2
import pytest

from database.db_manager import DatabaseManager


class _Cur:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        self.conn.executes += 1
        if self.conn.fail_on == "execute" and self.conn.executes == 1:
            raise psycopg2.OperationalError("SSL SYSCALL error: EOF detected")

    def fetchone(self):
        return {"id": 1}


class _Conn:
    closed = 0

    def __init__(self, fail_on):
        self.fail_on = fail_on
        self.executes = 0
        self.commits = 0

    def cursor(self):
        return _Cur(self)

    def commit(self):
        self.commits += 1
        if self.fail_on == "commit":
            raise psycopg2.OperationalError("SSL SYSCALL error: EOF detected")

    def rollback(self):
        pass


class _Pool:
    def __init__(self, fail_on):
        self.fail_on = fail_on
        self.made = []

    def getconn(self):
        c = _Conn(self.fail_on if not self.made else None)  # only the first conn is faulty
        self.made.append(c)
        return c

    def putconn(self, conn, close=False):
        pass


def _mgr(fail_on):
    m = DatabaseManager.__new__(DatabaseManager)
    m._pool = _Pool(fail_on)
    m._slots = threading.BoundedSemaphore(2)
    m._slot_wait = 1.0
    m._last_error = ""
    return m


def test_commit_failure_is_not_retried(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    m = _mgr("commit")
    with pytest.raises(psycopg2.OperationalError):
        m.execute("SELECT fn_post_receipt(%s)", (1,), fetch_one=True)
    total = sum(c.executes for c in m._pool.made)
    assert total == 1, f"statement executed {total} times; a COMMIT failure must not re-run it"


def test_failure_before_commit_is_still_retried(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    m = _mgr("execute")
    row = m.execute("SELECT 1", fetch_one=True)
    assert row == {"id": 1}
    assert len(m._pool.made) == 2          # first connection died, second succeeded
