"""database/estatehub.sql is the schema of record and every install is fresh, so the incremental files in
database/migrations/ (kept only to upgrade an old database) must change nothing on a fresh install: whatever they
add is already declared inline. Each file is applied here inside a transaction that is rolled back, and the schema
fingerprint (columns, indexes, constraints, triggers, function bodies) must be identical before and after."""
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("ESTATEHUB_LIVE_TESTS") != "1", reason="live database tests are opt-in")

MIGRATIONS = sorted((Path(__file__).resolve().parent.parent / "database" / "migrations").glob("*.sql"))

FINGERPRINT = """
SELECT md5(string_agg(x, '|' ORDER BY x)) AS h, count(*) AS n FROM (
  SELECT 'col:' || table_name || '.' || column_name || ':' || data_type || ':' || is_nullable || ':' || coalesce(column_default, '')
    FROM information_schema.columns WHERE table_schema = 'public'
  UNION ALL SELECT 'idx:' || indexdef FROM pg_indexes WHERE schemaname = 'public'
  UNION ALL SELECT 'con:' || conrelid::regclass || ':' || conname || ':' || pg_get_constraintdef(oid)
    FROM pg_constraint WHERE connamespace = 'public'::regnamespace
  UNION ALL SELECT 'trg:' || tgrelid::regclass || ':' || tgname || ':' || pg_get_triggerdef(oid)
    FROM pg_trigger WHERE NOT tgisinternal
  UNION ALL SELECT 'fn:' || p.proname || ':' || pg_get_function_identity_arguments(p.oid) || ':' || md5(p.prosrc)
    FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace
) s(x)
"""


def test_there_are_migrations_to_check():
    assert MIGRATIONS, "database/migrations/ is empty: delete this test together with the directory"


@pytest.mark.parametrize("path", MIGRATIONS, ids=lambda p: p.name)
def test_a_migration_changes_nothing_on_a_fresh_install(path):
    from database.db_manager import db
    with db._conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(FINGERPRINT)
            before = dict(cur.fetchone())
            cur.execute(path.read_text(encoding="utf-8"))
            cur.execute(FINGERPRINT)
            after = dict(cur.fetchone())
        finally:
            conn.rollback()
    assert after == before, f"{path.name} still changes the schema: fold it into database/estatehub.sql"
