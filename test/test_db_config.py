# test/test_db_config.py
"""
The three database entry points must resolve to ONE target.

regression guard for a real incident: migrate.py and seed.py preferred
DATABASE_URL and only fell back to the PG* variables, while reset_database.py
read the PG* variables only. With a DATABASE_URL in .env, a
`reset_database.py --yes --after seed` run dropped the schema from the PG*
database and then seeded the DATABASE_URL one, and a standalone
`migrate.py --seed` applied the schema to the remote database instead of the
local one. All three now go through database/db_config.py.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "database"))

PG_KEYS = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGSSLMODE")

LOCAL = {
    "PGHOST": "/tmp/pgsock",
    "PGPORT": "5432",
    "PGDATABASE": "local_test_db",
    "PGUSER": "postgres",
    "PGPASSWORD": "",
    "PGSSLMODE": "disable",
}
REMOTE_URL = "postgresql://someone@remote.example.com:21207/prod_db?sslmode=require"


@pytest.fixture()
def clean_env(monkeypatch):
    """DATABASE_URL set (as .env does) and every PG* controlled explicitly."""
    for k in PG_KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DATABASE_URL", REMOTE_URL)
    import db_config
    return importlib.reload(db_config)


def test_pg_vars_win_over_database_url(clean_env, monkeypatch):
    """The whole point: PG* identifies the local DB, so that is the target —
    DATABASE_URL must not silently redirect writes to the remote DB."""
    for k, v in LOCAL.items():
        monkeypatch.setenv(k, v)
    assert clean_env.pg_vars_complete() is True
    assert clean_env.describe_target() == "/tmp/pgsock:5432/local_test_db"
    assert "remote.example.com" not in clean_env.dsn()


def test_passwordless_local_auth_is_not_treated_as_unset(clean_env, monkeypatch):
    """An empty PGPASSWORD is normal for socket/peer auth. Requiring a
    non-empty password here used to fall through to DATABASE_URL and aim the
    whole toolchain at the remote database."""
    for k, v in LOCAL.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PGPASSWORD", "")
    assert clean_env.pg_vars_complete() is True
    assert "remote.example.com" not in clean_env.describe_target()


def test_falls_back_to_database_url_when_pg_incomplete(clean_env, monkeypatch):
    """DATABASE_URL is still honoured when PG* doesn't identify a database."""
    monkeypatch.setenv("PGDATABASE", "local_test_db")
    monkeypatch.setenv("PGUSER", "postgres")
    assert clean_env.pg_vars_complete() is False
    assert "remote.example.com" in clean_env.describe_target()


def test_all_three_entry_points_agree(clean_env, monkeypatch):
    """migrate.py, seed.py and reset_database.py must agree — they used to
    each resolve their own target independently."""
    for k, v in LOCAL.items():
        monkeypatch.setenv(k, v)
    targets = set()
    for mod in ("db_config", "migrate", "seed", "reset_database"):
        m = importlib.reload(importlib.import_module(mod))
        targets.add(m.describe_target())
    assert targets == {"/tmp/pgsock:5432/local_test_db"}, targets