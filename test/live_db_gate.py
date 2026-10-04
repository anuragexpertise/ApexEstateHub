# test/live_db_gate.py
"""
Guard for the tests that talk to a real PostgreSQL.

Those tests are skipped unless a database is configured, and the obvious way to
configure one — `load_dotenv()` picking up `PGHOST`/`DATABASE_URL` from .env —
is exactly the wrong trigger. .env in this repo points at a real remote Aiven
database, and these tests write through application handlers, so a plain
`pytest test/` would silently execute against it. That is not hypothetical: a
full-suite run did exactly this and wrote to the remote database.

So the live tests require an explicit opt-in as well as a reachable database:

    ESTATEHUB_LIVE_TESTS=1 PGHOST=... PGDATABASE=... PGUSER=... pytest test/

Use the local, throwaway instance — not a shared or remote database.
"""

import os

# Set this to run the tests marked as needing a real database.
OPT_IN_ENV = "ESTATEHUB_LIVE_TESTS"

LIVE_DB_REASON = (
    f"needs a real Postgres and explicit opt-in: {OPT_IN_ENV}=1 "
    "(see test/live_db_gate.py) — and point PGHOST at a local throwaway "
    "instance, never a shared or remote database"
)


def live_db_enabled() -> bool:
    """True only when the live tests may run.

    Note pytest.mark.skipif() evaluates its first argument as Python source,
    so this must be a plain bool expression — passing the reason text there is a
    SyntaxError at collection time.
    """
    if os.getenv(OPT_IN_ENV, "").strip().lower() not in ("1", "true", "yes"):
        return False
    return bool(os.getenv("PGHOST"))


# Back-compat alias for callers that want a reason string.
def live_db_skip_reason() -> str | None:
    return None if live_db_enabled() else LIVE_DB_REASON