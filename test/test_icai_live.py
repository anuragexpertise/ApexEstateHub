# test/test_icai_live.py
"""
Live ICAI correction checks against the scratch Postgres (Section 2 of the
correction plan).

Skipped unless ESTATEHUB_LIVE_TESTS=1 and PGHOST/PGPORT/PGUSER/PGPASSWORD/
PGDATABASE point at a LOCAL, throwaway instance. Never runs against Aiven.
See test/live_db_gate.py.
"""

import os

import psycopg2
import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

pytestmark = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)

_SQL_PATH = "test/live_icai_checks.sql"


def _connect():
    return psycopg2.connect(
        host=os.getenv("PGHOST"),
        port=os.getenv("PGPORT"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        dbname=os.getenv("PGDATABASE"),
        sslmode=os.getenv("PGSSLMODE", "disable"),
    )


def test_live_icai_checks_pass():
    """Run every DO-block check in test/live_icai_checks.sql; fail on the first exception."""
    with open(_SQL_PATH, encoding="utf-8") as fh:
        sql = fh.read()
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(sql)
    finally:
        conn.close()
