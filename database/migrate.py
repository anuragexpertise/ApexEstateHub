#!/usr/bin/env python3
# database/migrate.py
"""
EstateHub — Aiven PostgreSQL migration + seed script.

What it does
============
1. Connects to Aiven PostgreSQL (DATABASE_URL or PG* env vars).
2. Creates / updates the full schema (idempotent — uses IF NOT EXISTS).
3. Applies incremental alterations for existing installations
   (columns, constraints, tables that newer schema versions add).
4. On first run (no societies), asks whether to seed demo data:
     • 1 master admin
     • 1 society  (Sunrise Residency)
     • 50 Chart-of-Accounts entries
     • 1 admin, 13 apartment owners, 12 vendors, 12 security staff
     • 12 concerns, 12 events, 2 gate-log entries, 2 assets

All passwords stored with werkzeug generate_password_hash so
auth_service.check_password_hash() can verify them.

Usage
-----
    python3 database/migrate.py            # normal
    python3 database/migrate.py --force    # re-run DDL even if tables exist
    python3 database/migrate.py --seed     # skip prompt, always seed
    python3 database/migrate.py --no-seed  # skip prompt, never seed
"""

import os
import sys
import argparse
import json
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(override=False)

import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash

logging.basicConfig(level=logging.INFO, format="  %(message)s")
log = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# CONNECTION
# ═════════════════════════════════════════════════════════════════════════════

def _dsn() -> str:
    raw = os.getenv("DATABASE_URL", "").strip()
    if raw:
        return raw.replace("postgres://", "postgresql://", 1)
    host   = os.getenv("PGHOST",     "").strip()
    port   = os.getenv("PGPORT",     "5432").strip() or "5432"
    dbname = os.getenv("PGDATABASE", "").strip()
    user   = os.getenv("PGUSER",     "").strip()
    pw     = os.getenv("PGPASSWORD", "").strip()
    ssl    = os.getenv("PGSSLMODE",  "require").strip()
    if not all([host, dbname, user, pw]):
        print("❌  Set DATABASE_URL  or  PGHOST/PGDATABASE/PGUSER/PGPASSWORD")
        sys.exit(1)
    return f"postgresql://{user}:{pw}@{host}:{port}/{dbname}?sslmode={ssl}"


def get_conn():
    try:
        conn = psycopg2.connect(
            _dsn(),
            cursor_factory=psycopg2.extras.RealDictCursor,
            connect_timeout=20,
            # Without these, a blocked statement waits INDEFINITELY with
            # zero output — the exact "terminal just sits there" symptom.
            # Postgres default lock_timeout/statement_timeout is 0 (no
            # limit) unless set here or on the server/role. lock_timeout
            # fires fast and specifically on lock contention (most likely
            # cause: another session — e.g. the live app, or a previous
            # migrate.py/seed.py run that was Ctrl-C'd mid-transaction —
            # still holding a lock on a table this script needs).
            # statement_timeout is a broader backstop for any other kind
            # of runaway query. Both raise a normal psycopg2 exception
            # (55P03 / 57014) instead of hanging silently.
            options="-c lock_timeout=15000 -c statement_timeout=180000",
        )
        conn.autocommit = False
        return conn
    except Exception as exc:
        print(f"❌  Cannot connect: {exc}")
        sys.exit(1)


# ═════════════════════════════════════════════════════════════════════════════
# SCHEMA  (idempotent DDL)
# ═════════════════════════════════════════════════════════════════════════════

from pathlib import Path

def load_schema_sql():
    sql_file = Path(__file__).with_name("estatehub.sql")

    if not sql_file.exists():
        raise FileNotFoundError(
            f"Schema file not found: {sql_file}"
        )

    return sql_file.read_text(encoding="utf-8")

SCHEMA_SQL = load_schema_sql()

def run_schema(conn):
    import sqlparse
    stmts = sqlparse.split(SCHEMA_SQL)
    ok = 0
    err = 0
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
        for stmt in stmts:
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                cur.execute(stmt)
                conn.commit()
                ok += 1
            except Exception as exc:
                conn.rollback()
                snippet = stmt[:120].replace("\n", " ")
                print(f"\nFAILED:\n{snippet}")
                print(exc)
                err += 1
    return ok, err


# ═════════════════════════════════════════════════════════════════════════════
# INCREMENTAL ALTERATIONS — safe ALTER for existing installations
# (tables created by older schema versions that need column/constraint updates)
# ═════════════════════════════════════════════════════════════════════════════

def run_migrations(conn):
    """
    Apply all incremental schema changes needed by existing databases.
    Each ALTER is wrapped in its own savepoint so one failure doesn't block others.

    Note: Column additions are now defined inline in estatehub.sql CREATE TABLE
    statements. This function only handles:
    - Function replacements (fn_fy_closing_report)
    - Dead column cleanup (accounts.bf_amount)
    """
    alterations = [
        # fn_fy_closing_report: add depth + sort_path for Ledger Index tree
        "DROP FUNCTION IF EXISTS fn_fy_closing_report(integer, integer)",
        """CREATE OR REPLACE FUNCTION fn_fy_closing_report(
            p_society_id             INT,
            p_fy                     INT
        )
         RETURNS TABLE (
            account_id           INT,
            account_name         TEXT,
            tab_name             TEXT,
            parent_account_id    INT,
            drcr_account         TEXT,
            has_bf               BOOLEAN,
            own_bf               NUMERIC(15,2),
            own_movement         NUMERIC(15,2),
            depreciation_charge  NUMERIC(15,2),
            own_closing          NUMERIC(15,2),
            total_closing        NUMERIC(15,2),
            display_side         TEXT,
            display_amount       NUMERIC(15,2),
            depth                INT,
            sort_path            TEXT
        ) LANGUAGE plpgsql STABLE AS $$
        DECLARE
            v_fy_start DATE := MAKE_DATE(p_fy, 4, 1);
            v_fy_end   DATE := MAKE_DATE(p_fy + 1, 3, 31);
            v_total_depreciation NUMERIC(15,2);
            v_depreciation_acc_id INT;
        BEGIN
            v_depreciation_acc_id := fn_resolve_depreciation_account(p_society_id);

            SELECT COALESCE(SUM(fn_account_depreciation(p_society_id, a.id, p_fy)), 0)
            INTO v_total_depreciation
            FROM accounts a
            WHERE a.society_id = p_society_id;

            RETURN QUERY
            WITH RECURSIVE tree AS (
                SELECT a.id, a.parent_account_id, 0 AS depth,
                       LPAD(a.id::TEXT, 10, '0') AS sort_path
                FROM accounts a
                WHERE a.society_id = p_society_id AND a.parent_account_id IS NULL
                UNION ALL
                SELECT c.id, c.parent_account_id, t.depth + 1,
                       t.sort_path || '.' || LPAD(c.id::TEXT, 10, '0')
                FROM accounts c
                JOIN tree t ON c.parent_account_id = t.id
                WHERE c.society_id = p_society_id
            ),
            leaf_closing AS (
                SELECT
                    a.id,
                    a.name::TEXT,
                    a.tab_name::TEXT,
                    a.parent_account_id,
                    a.drcr_account::TEXT,
                    a.has_bf,
                    CASE WHEN a.has_bf THEN -fn_resolve_bf_amount_fy(p_society_id, a.id, p_fy) ELSE 0 END AS own_bf,
                    COALESCE((
                        SELECT SUM(CASE WHEN t.entry_side = 'Cr' THEN t.amount
                                         WHEN t.entry_side = 'Dr' THEN -t.amount
                                         ELSE 0 END)
                        FROM transactions t
                        WHERE t.acc_id = a.id AND t.society_id = p_society_id
                          AND t.status = 'paid'
                          AND t.trx_date BETWEEN v_fy_start AND v_fy_end
                    ), 0)
                    - CASE WHEN a.id = v_depreciation_acc_id THEN v_total_depreciation ELSE 0 END
                      AS own_movement_raw,
                    fn_account_depreciation(p_society_id, a.id, p_fy) AS depreciation_charge,
                    tree.depth,
                    tree.sort_path
                FROM accounts a
                JOIN tree ON tree.id = a.id
                WHERE a.society_id = p_society_id
            ),
            leaf_final AS (
                SELECT
                    lc.id, lc.name, lc.tab_name, lc.parent_account_id, lc.drcr_account, lc.has_bf,
                    lc.depth, lc.sort_path,
                    lc.own_bf, (lc.own_movement_raw + lc.depreciation_charge) AS own_movement,
                    lc.depreciation_charge,
                    (lc.own_bf + lc.own_movement_raw + lc.depreciation_charge) AS own_closing
                FROM leaf_closing lc
            ),
            ancestry AS (
                SELECT id AS acc_id, id AS ancestor_id
                FROM leaf_final
                UNION ALL
                SELECT anc.acc_id, lf.parent_account_id
                FROM ancestry anc
                JOIN leaf_final lf ON lf.id = anc.ancestor_id
                WHERE lf.parent_account_id IS NOT NULL
            ),
            rollup AS (
                SELECT anc.ancestor_id AS id, SUM(lf.own_closing) AS total_closing
                FROM ancestry anc
                JOIN leaf_final lf ON lf.id = anc.acc_id
                GROUP BY anc.ancestor_id
            )
            SELECT
                lf.id, lf.name, lf.tab_name, lf.parent_account_id, lf.drcr_account, lf.has_bf,
                lf.own_bf, lf.own_movement, lf.depreciation_charge, lf.own_closing,
                r.total_closing,
                CASE WHEN r.total_closing >= 0 THEN 'Cr' ELSE 'Dr' END,
                ABS(r.total_closing),
                lf.depth,
                lf.sort_path
            FROM leaf_final lf
            JOIN rollup r ON r.id = lf.id
            ORDER BY lf.sort_path;
        END;
        $$;""",

        $$;""",
    ]

    ok = 0
    skipped = 0
    with conn.cursor() as cur:
        for sql in alterations:
            try:
                cur.execute("SAVEPOINT migration_alter")
                cur.execute(sql)
                cur.execute("RELEASE SAVEPOINT migration_alter")
                conn.commit()
                ok += 1
            except Exception as exc:
                cur.execute("ROLLBACK TO SAVEPOINT migration_alter")
                conn.commit()
                skipped += 1
                snippet = sql[:80]
                print(f"  ↷ Skipped (already applied?): {snippet}… — {exc!s:.60}")

    print(f"  ✓ Migrations applied: {ok} ok, {skipped} skipped")

    # ── Data migration: users.push_subscription → push_subscriptions ────────
    _migrate_push_subscriptions(conn)


# ═════════════════════════════════════════════════════════════════════════════
# DEMO / SEED DATA — moved to database/seed.py (see --seed below).
# ACCOUNTS, SOCIETY, USERS, EVENTS, CONCERNS, ASSETS and all idempotent
# demo-data seeding now live in seed.run_seed(conn), using the same
# society_id=1 identity and the same hardcoded accounts/users migrate.py
# used to seed.
# ═════════════════════════════════════════════════════════════════════════════


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="EstateHub DB migration + seed")
    parser.add_argument("--force",   action="store_true",
                        help="Re-run DDL even if tables already exist")
    parser.add_argument("--seed",    action="store_true",
                        help="Always seed demo data without prompting")
    parser.add_argument("--no-seed", action="store_true",
                        help="Skip demo data seeding")
    args = parser.parse_args()

    print()
    print("═" * 62)
    print("  EstateHub — Database Migration")
    print("═" * 62)
    print(f"  Host : {os.getenv('PGHOST','(from DATABASE_URL)')}")
    print(f"  DB   : {os.getenv('PGDATABASE','')}")
    print()

    conn = get_conn()
    print("  ✓ Connected to Aiven PostgreSQL")

    # ── Schema ────────────────────────────────────────────────────────────
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_name='societies') AS ex"
        )
        tables_exist = cur.fetchone()["ex"]

    if tables_exist and not args.force:
        print("  ✓ Schema present — running safe ALTER/CREATE IF NOT EXISTS pass…")
    else:
        print("  ⟳ Creating schema…")

    ok, err = run_schema(conn)
    print(f"  ✓ DDL: {ok} ok, {err} skipped")

    # ── Incremental alterations for existing databases ────────────────────
    print("  ⟳ Running incremental migrations…")
    run_migrations(conn)

    # ── Seed decision ─────────────────────────────────────────────────────
    if args.no_seed:
        print("  Seed skipped (--no-seed).")
        conn.close()
        _summary()
        return

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM societies")
        has_societies = cur.fetchone()["c"] > 0

    if has_societies and not args.seed:
        print(f"  ✓ Societies exist — skipping demo seed.")
        print("    Use --seed to force-add demo data anyway.")
        conn.close()
        _summary()
        return

    if args.seed:
        do_seed = True
    else:
        print()
        print("  First run — no societies found.")
        print("  Seed demo data?  (1 society, 39 users, 50 accounts,")
        print("  12 events, 12 concerns, 2 gate logs, 2 assets)")
        print()
        try:
            ans = input("  Seed demo data? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = "y"
        do_seed = ans != "n"

    if do_seed:
        try:
            from seed import run_seed  # when run as `python3 database/migrate.py`
        except ImportError:
            from database.seed import run_seed  # when imported as a package
        try:
            run_seed(conn)
        except psycopg2.errors.LockNotAvailable:
            print()
            print("  ❌  Seeding stopped: timed out waiting for a database lock.")
            print("      Something else is holding a lock on a table this script")
            print("      needs — most likely another connection to the same DB")
            print("      (e.g. the live app, or a previous migrate.py/seed.py run")
            print("      that was interrupted mid-transaction and left idle).")
            print("      Run this in psql / Aiven console to find and end it:")
            print()
            print("        SELECT pid, state, query_start, state_change, query")
            print("        FROM pg_stat_activity")
            print("        WHERE datname = current_database() AND pid <> pg_backend_pid()")
            print("          AND state <> 'idle'")
            print("        ORDER BY query_start;")
            print()
            print("      Idle-in-transaction sessions are the usual culprit —")
            print("      SELECT pg_terminate_backend(<pid>) to clear one, then re-run.")
            conn.rollback()
            conn.close()
            sys.exit(1)
        except psycopg2.errors.QueryCanceled:
            print()
            print("  ❌  Seeding stopped: a statement exceeded the 3-minute timeout.")
            print("      This is a slower failure than a lock wait — check whether")
            print("      the DB itself is under load, or a single statement is")
            print("      doing far more work than expected.")
            conn.rollback()
            conn.close()
            sys.exit(1)
        conn = None  # run_seed() closes the connection itself
    else:
        print("  Seed skipped.  Log in as master admin to create a society.")

    if conn is not None:
        conn.close()
    _summary()


def _migrate_push_subscriptions(conn):
    """
    Migrate any existing users.push_subscription JSON blob into the new
    push_subscriptions table (one row per user, using the single legacy
    subscription as that user's desktop subscription).
    """
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, push_subscription
                  FROM users
                 WHERE push_subscription IS NOT NULL
            """)
            rows = cur.fetchall()
            if not rows:
                print("  ✓ Push subscriptions: nothing to migrate")
                return

            migrated = 0
            for row in rows:
                try:
                    sub = json.loads(row["push_subscription"]) if isinstance(row["push_subscription"], str) else row["push_subscription"]
                except Exception:
                    continue
                endpoint = sub.get("endpoint", "")
                p256dh = sub.get("keys", {}).get("p256dh", "")
                auth = sub.get("keys", {}).get("auth", "")
                if not endpoint:
                    continue
                try:
                    cur.execute("""
                        INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, user_agent)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, endpoint) DO NOTHING
                    """, (row["id"], endpoint, p256dh, auth, "legacy-migration"))
                    migrated += 1
                except Exception:
                    pass
            conn.commit()
            print(f"  ✓ Push subscriptions: migrated {migrated}/{len(rows)}")
    except Exception as exc:
        print(f"  ⚠ Push subscription migration failed: {exc}")
        conn.rollback()


def _summary():
    print()
    print("═" * 62)
    print("✅ Migration complete")
    print("═" * 62)
    print()


if __name__ == "__main__":
    main()