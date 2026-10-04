# database/db_config.py
"""
Single source of truth for "which database are we talking to".

Every entry point (migrate.py, seed.py, reset_database.py) resolves its target
here, so they cannot disagree. That disagreement was a real hazard: migrate.py
and seed.py preferred DATABASE_URL and fell back to the PG* variables, while
reset_database.py read the PG* variables only. With a DATABASE_URL in .env, a
`reset_database.py --yes --after seed` run dropped the schema from the PG*
database and then seeded the DATABASE_URL one instead — and a standalone
`migrate.py --seed` silently applied the schema to the DATABASE_URL database
rather than the local test database.

Precedence is therefore PG* first, DATABASE_URL only as a fallback:

  * If PGHOST/PGDATABASE/PGUSER/PGPASSWORD are all set, that is the target.
    This matches what reset_database.py has always done and is what a local
    dev/test workflow expects.
  * DATABASE_URL is used only when the PG* set is incomplete.

`describe_target()` is printed by the callers so the resolved host and database
are always visible before anything is written.
"""

import os
import sys


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def pg_vars() -> dict:
    """The PG* variables, normalised. Empty strings where unset/blank."""
    return {
        "host": _env("PGHOST"),
        "port": _env("PGPORT") or "5432",
        "dbname": _env("PGDATABASE"),
        "user": _env("PGUSER"),
        "password": os.getenv("PGPASSWORD", ""),
        "sslmode": _env("PGSSLMODE") or "require",
        "sslrootcert": _env("PGSSLROOTCERT"),
    }


def pg_vars_complete() -> bool:
    """True when the PG* set identifies a database.

    PGPASSWORD is deliberately excluded: passwordless local/peer auth (a
    socket or trust connection) is a normal dev setup, and requiring a
    non-empty password here would silently fall through to DATABASE_URL —
    i.e. to the remote database instead of the local one.
    """
    v = pg_vars()
    return all(v[k] for k in ("host", "dbname", "user"))


def connection_params() -> dict:
    """psycopg2.connect(**params) kwargs for the resolved target."""
    if pg_vars_complete():
        v = pg_vars()
        params = {
            "host": v["host"],
            "port": int(v["port"]),
            "dbname": v["dbname"],
            "user": v["user"],
            "password": v["password"],
            "sslmode": v["sslmode"],
        }
        if v["sslrootcert"] and v["sslmode"] != "disable":
            params["sslrootcert"] = v["sslrootcert"]
        return params

    raw = _env("DATABASE_URL")
    if not raw:
        print("❌  Set PGHOST/PGDATABASE/PGUSER  or  DATABASE_URL")
        sys.exit(1)
    return {"dsn": raw.replace("postgres://", "postgresql://", 1)}


def dsn() -> str:
    """libpq-style keyword/value DSN, for callers that pass a single string."""
    p = connection_params()
    if "dsn" in p:
        return p["dsn"]
    return (
        f"postgresql://{p['user']}:{p['password']}@{p['host']}:{p['port']}"
        f"/{p['dbname']}?sslmode={p['sslmode']}"
    )


def describe_target() -> str:
    """One-line 'host:port/db' for the resolved target, for logging."""
    p = connection_params()
    if "dsn" in p:
        tail = p["dsn"].split("@", 1)[-1]
        return tail.split("?")[0]
    return f"{p['host']}:{p['port']}/{p['dbname']}"