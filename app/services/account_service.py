# app/services/account_service.py
"""
Account Management Service - Complete Chart of Accounts & Cashbook System
Handles: Accounts Master, Receipts, Expenses, Cashbook, Ledger
Updated: Uses account.id instead of account.ac_no
"""

from datetime import date, datetime
from decimal import Decimal
from database.db_manager import db
import logging

from app.security.audit_context import get_current_user_id

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# ACCOUNT MASTER MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════

def create_account(society_id: int, account_id: int, data: dict) -> tuple[bool, str, int]:
    """
    Create new account in chart of accounts.
    
    Args:
        society_id: Society ID
        account_id: Account ID (user-specified, e.g. 1001, 2001, etc.)
        data: {
            "name": str (required),
            "tab_name": str,
            "header": str,
            "parent_account_id": int (parent account id, default=1),
            "drcr_account": str ('Dr' or 'Cr', required),
            "has_bf": bool (default=False),
            "drcr_bf": str ('Dr' or 'Cr'),
            "depreciation_percent": Decimal
        }
        Note: opening balances are no longer set here — use
        set_brought_forward()-style logic against the brought_forward
        table (FY-scoped) instead of an account-level "bf_amount".
    
    Returns:
        (success: bool, message: str, account_id: int)
    """
    try:
        # Validate required fields
        if not account_id or account_id <= 0:
            return False, "Valid account ID is required", 0
        
        if not data.get("name"):
            return False, "Account name is required", 0
        
        if not data.get("drcr_account"):
            return False, "Dr/Cr designation is required", 0
        
        if data["drcr_account"] not in ("Dr", "Cr"):
            return False, "drcr_account must be 'Dr' or 'Cr'", 0
        
        # Check for duplicate id
        existing = db._execute(
            "SELECT id FROM accounts WHERE society_id = :society_id AND id = :id",
            {'society_id': society_id, 'id': account_id},
            fetch_one=True
        )
        if existing:
            return False, f"Account ID {account_id} already exists", 0
        
        # Check for duplicate name
        existing = db._execute(
            "SELECT id FROM accounts WHERE society_id = :society_id AND name = :name",
            {'society_id': society_id, 'name': data["name"]},
            fetch_one=True
        )
        if existing:
            return False, f"Account name '{data['name']}' already exists", 0
        
        # Set defaults
        drcr_bf = data.get("drcr_bf", data["drcr_account"])
        if drcr_bf not in ("Dr", "Cr"):
            drcr_bf = data["drcr_account"]
        depreciation_percent = data.get("depreciation_percent", 100)
        is_depreciable = depreciation_percent < 100
        
        # Create account (bf_amount removed — use brought_forward table)
        db._execute(
            """
            INSERT INTO accounts (
                id, society_id, name, tab_name, header, parent_account_id,
                drcr_account, has_bf, drcr_bf, depreciation_percent, is_depreciable
            ) VALUES (:id, :society_id, :name, :tab_name, :header, :parent_account_id,
                      :drcr_account, :has_bf, :drcr_bf, :depreciation_percent, :is_depreciable)
            """,
            {
                'id': account_id,
                'society_id': society_id,
                'name': data["name"],
                'tab_name': data.get("tab_name"),
                'header': data.get("header"),
                'parent_account_id': data.get("parent_account_id", 1),
                'drcr_account': data["drcr_account"],
                'has_bf': data.get("has_bf", False),
                'drcr_bf': drcr_bf,
                'depreciation_percent': depreciation_percent,
                'is_depreciable': is_depreciable
            }
        )
        
        logger.info(f"Account created: {data['name']} (ID: {account_id})")
        return True, f"Account '{data['name']}' created successfully", account_id
        
    except Exception as e:
        logger.error(f"Error creating account: {e}")
        return False, f"Error: {str(e)}", 0


def update_account(account_id: int, society_id: int, data: dict) -> tuple[bool, str]:
    """
    Update account details.
    
    Args:
        data: Fields to update (same as create_account except id)
    
    Returns:
        (success: bool, message: str)
    """
    try:
        allowed_fields = [
            "name", "tab_name", "header", "parent_account_id",
            "drcr_account", "has_bf", "drcr_bf",
            "depreciation_percent", "is_depreciable"
        ]
        
        updates = []
        params = {}
        
        for field in allowed_fields:
            if field in data:
                updates.append(f"{field} = :{field}")
                params[field] = data[field]
        
        if not updates:
            return False, "No fields to update"
        
        # Validate Dr/Cr values
        if "drcr_account" in data and data["drcr_account"] not in ("Dr", "Cr"):
            return False, "drcr_account must be 'Dr' or 'Cr'"
        
        if "drcr_bf" in data and data["drcr_bf"] not in ("Dr", "Cr"):
            return False, "drcr_bf must be 'Dr' or 'Cr'"

        if "depreciation_percent" in data:
            params["is_depreciable"] = data["depreciation_percent"] < 100
            if "is_depreciable" not in updates:
                updates.append("is_depreciable = :is_depreciable")
        
        params['account_id'] = account_id
        params['society_id'] = society_id
        params['updated_by'] = get_current_user_id()

        db._execute(
            f"UPDATE accounts SET {', '.join(updates)}, updated_by = :updated_by "
            "WHERE id = :account_id AND society_id = :society_id",
            params
        )
        
        logger.info(f"Account {account_id} updated")
        return True, "Account updated successfully"
        
    except Exception as e:
        logger.error(f"Error updating account: {e}")
        return False, f"Error: {str(e)}"


def get_account(account_id: int, society_id: int) -> dict:
    """Get account details."""
    try:
        return db._execute(
            "SELECT * FROM accounts WHERE id = :id AND society_id = :society_id",
            {'id': account_id, 'society_id': society_id},
            fetch_one=True
        ) or {}
    except Exception as e:
        logger.error(f"Error getting account: {e}")
        return {}


def list_accounts(society_id: int, filters: dict = None, page: int = 1, page_size: int = 100) -> tuple[list, int]:
    """
    List accounts with filtering.
    
    Args:
        filters: {
            "tab_name": str,
            "drcr_account": str ('Dr' or 'Cr'),
            "has_bf": bool,
            "search": str
        }
    
    Returns:
        (rows: list, total_count: int)
    """
    try:
        offset = (page - 1) * page_size
        where_clauses = ["society_id = :society_id"]
        params = {'society_id': society_id, 'page_size': page_size, 'offset': offset}
        
        if filters:
            if filters.get("tab_name"):
                where_clauses.append("tab_name = :tab_name")
                params['tab_name'] = filters["tab_name"]
            
            if filters.get("drcr_account"):
                where_clauses.append("drcr_account = :drcr_account")
                params['drcr_account'] = filters["drcr_account"]
            
            if filters.get("has_bf") is not None:
                where_clauses.append("has_bf = :has_bf")
                params['has_bf'] = filters["has_bf"]
            
            if filters.get("search"):
                where_clauses.append("(name ILIKE :search OR header ILIKE :search)")
                params['search'] = f"%{filters['search']}%"
        
        where_sql = f"WHERE {' AND '.join(where_clauses)}"
        
        # Get total count
        count_result = db._execute(
            f"SELECT COUNT(*) as c FROM accounts {where_sql}",
            {k: v for k, v in params.items() if k not in ['page_size', 'offset']},
            fetch_one=True
        )
        total = count_result["c"] if count_result else 0
        
        # Get paginated results
        rows = db._execute(
            f"""
            SELECT 
                id, name, tab_name, header, parent_account_id,
                drcr_account, has_bf, drcr_bf,
                depreciation_percent, created_at
            FROM accounts {where_sql}
            ORDER BY id
            LIMIT :page_size OFFSET :offset
            """,
            params,
            fetch_all=True
        ) or []
        
        return rows, total
        
    except Exception as e:
        logger.error(f"Error listing accounts: {e}")
        return [], 0


def get_accounts_for_receipt(society_id: int) -> list:
    """
    Get all Cr accounts (income/receipt accounts).
    Used for receipt entry dropdown.
    """
    try:
        return db._execute(
            """
            SELECT id, name, tab_name, header
            FROM accounts
            WHERE society_id = :society_id AND drcr_account = 'Cr'
            ORDER BY name
            """,
            {'society_id': society_id},
            fetch_all=True
        ) or []
    except Exception as e:
        logger.error(f"Error getting receipt accounts: {e}")
        return []


def get_accounts_for_expense(society_id: int) -> list:
    """
    Get all Dr accounts (expense/payment accounts).
    Used for expense entry dropdown.
    """
    try:
        return db._execute(
            """
            SELECT id, name, tab_name, header
            FROM accounts
            WHERE society_id = :society_id AND drcr_account = 'Dr'
            ORDER BY name
            """,
            {'society_id': society_id},
            fetch_all=True
        ) or []
    except Exception as e:
        logger.error(f"Error getting expense accounts: {e}")
        return []


def delete_account(account_id: int, society_id: int) -> tuple[bool, str]:
    """
    Delete an account (soft delete by checking for transactions).
    
    Returns:
        (success: bool, message: str)
    """
    try:
        # Check if account has transactions
        has_transactions = db._execute(
            "SELECT COUNT(*) as c FROM transactions WHERE acc_id = :acc_id",
            {'acc_id': account_id},
            fetch_one=True
        )
        
        if has_transactions and has_transactions["c"] > 0:
            return False, "Cannot delete account with existing transactions"
        
        db._execute(
            "DELETE FROM accounts WHERE id = :id AND society_id = :society_id",
            {'id': account_id, 'society_id': society_id}
        )
        
        logger.info(f"Account {account_id} deleted")
        return True, "Account deleted successfully"
        
    except Exception as e:
        logger.error(f"Error deleting account: {e}")
        return False, f"Error: {str(e)}"


def get_next_account_id(society_id: int, range_start: int = 1000) -> int:
    """
    Get next available account ID for a society.
    
    Args:
        society_id: Society ID
        range_start: Starting range for account IDs (default 1000)
        
    Returns:
        Next available account ID
    """
    try:
        result = db._execute(
            """
            SELECT COALESCE(MAX(id), :range_start) + 1 as next_id 
            FROM accounts 
            WHERE society_id = :society_id AND id >= :range_start
            """,
            {'society_id': society_id, 'range_start': range_start},
            fetch_one=True
        )
        return result["next_id"] if result else range_start
    except Exception:
        return range_start


# ════════════════════════════════════════════════════════════════════════════
# RECEIPT & EXPENSE RECORDING
# ════════════════════════════════════════════════════════════════════════════
# NOTE: record_receipt() and record_expense() were removed here — both dead
# code with zero callers anywhere in the app. Each inserted directly into
# `transactions` with status='paid' unconditionally, bypassing the
# confirmed/pending gate that the real receipt/expense paths (fn_save_receipt
# / fn_save_expense via _save_receipt_v3 / _save_expense_v3 in
# drilldown_callbacks.py) enforce based on who's recording it. Leaving them
# in place risked someone wiring one up later and silently skipping admin
# verification for non-admin-recorded entries.

def update_transaction(transaction_id: int, society_id: int, data: dict) -> tuple[bool, str]:
    """
    Update transaction details.
    
    Args:
        data: Fields to update
    
    Returns:
        (success: bool, message: str)
    """
    try:
        allowed_fields = [
            "trx_date", "acc_particulars", "amount", "mode", "payment_gateway_id"
        ]
        
        updates = []
        params = {}
        
        for field in allowed_fields:
            if field in data:
                updates.append(f"{field} = :{field}")
                params[field] = data[field]
        
        if not updates:
            return False, "No fields to update"
        
        params['transaction_id'] = transaction_id
        params['society_id'] = society_id
        params['updated_by'] = get_current_user_id()
        
        db._execute(
            f"UPDATE transactions SET {', '.join(updates)}, updated_by = :updated_by "
            "WHERE id = :transaction_id AND society_id = :society_id",
            params
        )
        
        logger.info(f"Transaction {transaction_id} updated")
        return True, "Transaction updated successfully"
        
    except Exception as e:
        logger.error(f"Error updating transaction: {e}")
        return False, f"Error: {str(e)}"


def delete_transaction(transaction_id: int, society_id: int) -> tuple[bool, str]:
    """
    Delete a transaction (mark as cancelled).
    
    Returns:
        (success: bool, message: str)
    """
    try:
        db._execute(
            "UPDATE transactions SET status = 'cancelled' WHERE id = :id AND society_id = :society_id",
            {'id': transaction_id, 'society_id': society_id}
        )
        
        logger.info(f"Transaction {transaction_id} cancelled")
        return True, "Transaction cancelled successfully"
        
    except Exception as e:
        logger.error(f"Error deleting transaction: {e}")
        return False, f"Error: {str(e)}"


def get_account_tabs(society_id: int) -> list:
    """Get list of unique tab names for a society."""
    try:
        rows = db._execute(
            """
            SELECT DISTINCT tab_name 
            FROM accounts 
            WHERE society_id = :society_id AND tab_name IS NOT NULL
            ORDER BY tab_name
            """,
            {'society_id': society_id},
            fetch_all=True
        ) or []
        
        return [r["tab_name"] for r in rows]
    except Exception:
        return []
