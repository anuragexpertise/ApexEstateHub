#!/usr/bin/env python3
# database/verify.py
"""
Verify database schema is correct after migration.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(override=False)

from database.db_manager import db


def verify_column_exists(table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    result = db._execute(
        """
        SELECT EXISTS (
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_name = :table AND column_name = :column
        ) as exists
        """,
        {'table': table, 'column': column},
        fetch_one=True
    )
    return result and result.get('exists', False)


def verify_foreign_key_exists(table: str, constraint_name: str) -> bool:
    """Check if a foreign key constraint exists."""
    result = db._execute(
        """
        SELECT EXISTS (
            SELECT 1 
            FROM information_schema.table_constraints 
            WHERE table_name = :table AND constraint_name = :constraint
        ) as exists
        """,
        {'table': table, 'constraint': constraint_name},
        fetch_one=True
    )
    return result and result.get('exists', False)


def verify_index_exists(index_name: str) -> bool:
    """Check if an index exists."""
    result = db._execute(
        """
        SELECT EXISTS (
            SELECT 1 
            FROM pg_indexes 
            WHERE indexname = :index
        ) as exists
        """,
        {'index': index_name},
        fetch_one=True
    )
    return result and result.get('exists', False)


def main():
    print("=" * 70)
    print("  Database Schema Verification")
    print("=" * 70)
    print()
    
    checks = []
    
    # Critical columns for account_service.py
    print("📋 Checking Accounts Table...")
    checks.append(("drcr_bf column", verify_column_exists('accounts', 'drcr_bf')))
    checks.append(("drcr_account column", verify_column_exists('accounts', 'drcr_account')))
    checks.append(("bf_amount column", verify_column_exists('accounts', 'bf_amount')))
    checks.append(("has_bf column", verify_column_exists('accounts', 'has_bf')))
    checks.append(("parent_account_id column", verify_column_exists('accounts', 'parent_account_id')))
    
    # Auth columns
    print("📋 Checking Users Table...")
    checks.append(("is_master_admin column", verify_column_exists('users', 'is_master_admin')))
    checks.append(("failed_login_attempts column", verify_column_exists('users', 'failed_login_attempts')))
    checks.append(("locked_until column", verify_column_exists('users', 'locked_until')))
    checks.append(("reset_token column", verify_column_exists('users', 'reset_token')))
    checks.append(("reset_token_expires column", verify_column_exists('users', 'reset_token_expires')))
    checks.append(("push_token column", verify_column_exists('users', 'push_token')))
    checks.append(("push_enabled column", verify_column_exists('users', 'push_enabled')))
    checks.append(("last_login column", verify_column_exists('users', 'last_login')))
    
    # Foreign keys
    print("📋 Checking Foreign Key Constraints...")
    checks.append(("accounts parent_account_id FK", verify_foreign_key_exists('accounts', 'accounts_parent_account_id_fkey')))
    
    # Indexes
    print("📋 Checking Indexes...")
    checks.append(("idx_accounts_parent_account_id", verify_index_exists('idx_accounts_parent_account_id')))
    checks.append(("idx_users_reset_token", verify_index_exists('idx_users_reset_token')))
    checks.append(("idx_users_locked_until", verify_index_exists('idx_users_locked_until')))
    
    # Print results
    print()
    print("=" * 70)
    print("  Results")
    print("=" * 70)
    
    passed = 0
    failed = 0
    
    for check_name, result in checks:
        status = "✅" if result else "❌"
        print(f"  {status}  {check_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print()
    print("=" * 70)
    print(f"  {passed} passed, {failed} failed")
    print("=" * 70)
    
    # Get some basic stats
    print()
    print("📊 Database Statistics:")
    
    tables = [
        'societies', 'users', 'apartments', 'vendors', 'security_staff',
        'accounts', 'transactions', 'payments', 'events', 'concerns'
    ]
    
    for table in tables:
        result = db._execute(
            f"SELECT COUNT(*) as c FROM {table}",
            {},
            fetch_one=True
        )
        count = result['c'] if result else 0
        print(f"  - {table:20} : {count:4} rows")
    
    print()
    print("=" * 70)
    
    return failed == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
