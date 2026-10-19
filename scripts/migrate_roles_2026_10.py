#!/usr/bin/env python3
"""
One-off, idempotent upgrade for a database installed BEFORE the Accountant / Supervisor / Staff / Auditor portals.

database/estatehub.sql already carries these changes for new installs; this applies them to an existing one:

  1. users.role CHECK now allows accountant, supervisor, staff, auditor (the constraint is looked up by its
     definition, not assumed to be called users_role_check).
  2. role_definitions gains 'society_president' and its role_permissions grants.

Safe to run twice. Runs in one transaction; any error rolls everything back.

    python3 scripts/migrate_roles_2026_10.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

NEW_ROLES = ("admin", "apartment", "vendor", "security", "accountant", "supervisor", "staff", "auditor")

SQL_ROLE_CHECK = """
DO $$
DECLARE c RECORD;
BEGIN
    FOR c IN
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'users'::regclass AND contype = 'c'
           AND pg_get_constraintdef(oid) ILIKE '%role%' AND pg_get_constraintdef(oid) ILIKE '%apartment%'
           AND pg_get_constraintdef(oid) NOT ILIKE '%user_type%'
    LOOP
        EXECUTE format('ALTER TABLE users DROP CONSTRAINT %I', c.conname);
    END LOOP;
    ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ({roles}));
END $$;
""".format(roles=", ".join(f"'{r}'" for r in NEW_ROLES))

SQL_PRESIDENT = """
INSERT INTO role_definitions (code, scope, name, description) VALUES
    ('society_president', 'society', 'Society President',
     'AOA president: chairs the committee; assigns concerns, declares poll results, approves (never prepares) payments.')
ON CONFLICT (code, scope) DO NOTHING;

INSERT INTO role_permissions (role_definition_id, permission_id, scope_society_id, min_amount, approval_threshold)
SELECT rd.id, p.id, NULL, NULL, NULL
  FROM role_definitions rd, permissions p
 WHERE rd.code = 'society_president'
   AND ((p.resource = 'concern' AND p.action IN ('assign', 'resolve'))
     OR (p.resource = 'poll'    AND p.action = 'declare_results')
     OR (p.resource = 'finance' AND p.action = 'payment.approve'))
ON CONFLICT (role_definition_id, permission_id) WHERE scope_society_id IS NULL DO NOTHING;
"""


def main() -> None:
    from database.db_manager import db
    with db._conn() as conn:
        cur = conn.cursor()
        cur.execute(SQL_ROLE_CHECK)
        cur.execute(SQL_PRESIDENT)
    print("users.role CHECK updated; society_president role installed.")


if __name__ == "__main__":
    main()
