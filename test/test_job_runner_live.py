"""Task 1.4: scheduled jobs write a run log and alert masters on failure (real Postgres, rolled back)."""
import os

import pytest

import psycopg2.extras  # noqa: F401
from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

psycopg2 = pytest.importorskip("psycopg2")
pytestmark = [pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON), pytest.mark.postgres_integration]

from app.services import job_runner as jr  # noqa: E402
from test.test_signing_vault_live import Tx  # noqa: E402


class SavepointTx(Tx):
    """Each statement in a savepoint, so one failing statement does not poison the test's transaction
    (in production every statement is its own transaction)."""
    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        cur = self.conn.cursor()
        cur.execute("SAVEPOINT stmt")
        try:
            out = super()._execute(sql, params, fetch_one, fetch_all)
            cur.execute("RELEASE SAVEPOINT stmt")
            return out
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT stmt")
            raise


@pytest.fixture()
def db():
    c = psycopg2.connect(host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"), dbname=os.getenv("PGDATABASE"),
                         user=os.getenv("PGUSER"), password=os.getenv("PGPASSWORD"))
    yield SavepointTx(c)
    c.rollback()
    c.close()


def test_a_successful_run_is_logged(db):
    out = jr.run_job("ratification", db=db)
    assert out["status"] == "ok"
    row = db._execute("SELECT status, finished_at, detail FROM job_runs WHERE id=%s", (out["run_id"],), fetch_one=True)
    assert row["status"] == "ok" and row["finished_at"] and "expired" in row["detail"]


def test_a_forced_failure_is_logged_and_raises_an_alert(db, monkeypatch):
    def boom(_d):
        raise RuntimeError("forced failure")
    monkeypatch.setitem(jr.JOBS, "ratification", boom)
    alerts = []
    out = jr.run_job("ratification", db=db, alert=lambda name, err, d: alerts.append((name, err)))
    assert out["status"] == "failed" and alerts == [("ratification", "forced failure")]
    row = db._execute("SELECT status, error FROM job_runs WHERE id=%s", (out["run_id"],), fetch_one=True)
    assert row["status"] == "failed" and "forced failure" in row["error"]


def test_anchor_job_fails_loudly_when_a_chain_does_not_verify(db):
    cur = db.conn.cursor()
    cur.execute("ALTER TABLE transactions DISABLE TRIGGER USER")
    cur.execute("UPDATE transactions SET amount = amount + 1 WHERE society_id=1 AND ledger_seq = 1")
    cur.execute("ALTER TABLE transactions ENABLE TRIGGER USER")
    out = jr.run_job("anchors", db=db, alert=lambda *a: None)
    assert out["status"] == "failed"


def test_anchor_job_passes_on_an_intact_ledger(db):
    if not os.getenv("SECRET_VAULT_KEY"):
        pytest.skip("needs the seed's SECRET_VAULT_KEY")
    assert jr.run_job("anchors", db=db, alert=lambda *a: None)["status"] == "ok"


def test_unknown_job_is_refused(db):
    with pytest.raises(ValueError):
        jr.run_job("nope", db=db)
