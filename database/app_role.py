#!/usr/bin/env python3
"""
database/app_role.py -- a restricted database role for the running application.

(estatehub.sql is the repository's only .sql file, so the role's SQL lives here as APP_ROLE_SQL.)

Why: the append-only and immutability TRIGGERS protect the ledger and audit records from the application, but
they are only as strong as the database account the application uses. If it connects as the table OWNER (or a
superuser), anyone who can run SQL through it, for example via a bug, can DISABLE the triggers, TRUNCATE, or
call fn_rebuild_ledger_chain to re-sign an altered ledger. This role cannot do any of that.

How to use: run this ONCE as the owner / a superuser, after estatehub.sql, then create the application's login
as a member of the role and point DATABASE_URL / PG* at that login instead of the owner:

    CREATE USER estatehub_login PASSWORD '<long random>' IN ROLE estatehub_app;

Keep the owner's credentials OFF the application host; use them only to migrate. Run this script again after
each migration that adds tables (it is idempotent). Keep the ledger-anchor signing key
(LEDGER_ANCHOR_SECRET) off the database host as well: that is what lets a CA detect a rewrite by the owner.

Honest limit: nothing here constrains the database owner or a superuser. Against them the controls are the
signed ledger anchors, off-site backups and the filed certificates (app/security/ledger_anchor.py).

Usage:
    python database/app_role.py            # print the SQL
    python database/app_role.py --apply    # run it, as the owner / a superuser, using the usual PG* settings
"""
import os
import sys

APP_ROLE = "estatehub_app"

APP_ROLE_SQL = r'''
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'estatehub_app') THEN
        CREATE ROLE estatehub_app NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO estatehub_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO estatehub_app;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO estatehub_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO estatehub_app;

-- Never: truncating, creating triggers (a trigger is how a guard would be sidestepped), or foreign keys.
REVOKE TRUNCATE, TRIGGER, REFERENCES ON ALL TABLES IN SCHEMA public FROM estatehub_app;

-- Ledger lines: insert-only. The two bank-reconciliation flags are the only columns that may ever change.
REVOKE UPDATE, DELETE ON transactions FROM estatehub_app;
GRANT UPDATE (bank_reconciled, bank_line_id) ON transactions TO estatehub_app;

-- Append-only records: read and add, never change or remove.
REVOKE UPDATE, DELETE ON audit_events, regime_rule_audit, fy_locks FROM estatehub_app;

-- Ledger anchors: the signature and the filing reference are the only things filled in afterwards.
REVOKE UPDATE, DELETE ON ledger_chain_anchors FROM estatehub_app;
GRANT UPDATE (signature, external_ref) ON ledger_chain_anchors TO estatehub_app;

-- Re-signing a ledger is not an application operation. (Revoked from PUBLIC as well, so it is the owner's alone.)
REVOKE EXECUTE ON FUNCTION fn_rebuild_ledger_chain(INT, BOOLEAN) FROM PUBLIC, estatehub_app;
'''


def apply(conn) -> None:
    """Run APP_ROLE_SQL on an open psycopg2 connection (the owner's) and commit."""
    with conn.cursor() as cur:
        cur.execute(APP_ROLE_SQL)
    conn.commit()


def main() -> int:
    if "--apply" not in sys.argv[1:]:
        print(APP_ROLE_SQL)
        return 0
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    import psycopg2
    from database.db_config import connection_params
    conn = psycopg2.connect(**connection_params())
    try:
        apply(conn)
    finally:
        conn.close()
    print(f"Role {APP_ROLE} is set up. Create the application's login with:\n"
          f"  CREATE USER estatehub_login PASSWORD '<long random>' IN ROLE {APP_ROLE};")
    return 0


if __name__ == "__main__":
    sys.exit(main())
