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
            "bf_amount": Decimal,
            "depreciation_percent": Decimal
        }
    
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
        
        # Create account
        db._execute(
            """
            INSERT INTO accounts (
                id, society_id, name, tab_name, header, parent_account_id,
                drcr_account, has_bf, drcr_bf, bf_amount, depreciation_percent, is_depreciable
            ) VALUES (:id, :society_id, :name, :tab_name, :header, :parent_account_id,
                      :drcr_account, :has_bf, :drcr_bf, :bf_amount, :depreciation_percent, :is_depreciable)
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
                'bf_amount': data.get("bf_amount", 0),
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
            "bf_amount", "depreciation_percent", "is_depreciable"
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
        
        db._execute(
            f"UPDATE accounts SET {', '.join(updates)} WHERE id = :account_id AND society_id = :society_id",
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
                drcr_account, has_bf, drcr_bf, bf_amount, 
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

def record_receipt(society_id: int, data: dict, created_by: int = None) -> tuple[bool, str, int]:
    """
    Record a receipt (credit to society).
    
    Args:
        data: {
            "trx_date": date (default: today),
            "acc_id": int (required - must be Cr account),
            "entity_id": int (optional - link to apartment/vendor/user),
            "acc_particulars": str (required - description),
            "amount": Decimal (required),
            "mode": str (cash/cheque/upi/card/bank/crypto, default: cash),
            "payment_gateway_id": str (for online payables)
        }
    
    Returns:
        (success: bool, message: str, transaction_id: int)
    """
    try:
        # Validate required fields
        if not data.get("acc_id"):
            return False, "Account is required", 0
        
        if not data.get("acc_particulars"):
            return False, "Particulars are required", 0
        
        if not data.get("amount") or float(data["amount"]) <= 0:
            return False, "Valid amount is required", 0
        
        # Validate account is Cr type
        account = db._execute(
            "SELECT drcr_account, name FROM accounts WHERE id = :id AND society_id = :society_id",
            {'id': data["acc_id"], 'society_id': society_id},
            fetch_one=True
        )
        
        if not account:
            return False, "Account not found", 0
        
        if account["drcr_account"] != "Cr":
            return False, f"Invalid account selected ('{account['name']}' is a Debit account, not a Credit account)", 0
        
        # Validate mode
        valid_modes = ["cash", "cheque", "upi", "card", "bank", "crypto"]
        mode = data.get("mode", "cash").lower()
        if mode not in valid_modes:
            return False, f"Invalid payment mode. Must be one of: {', '.join(valid_modes)}", 0
        
        # Create transaction
        result = db._execute(
            """
            INSERT INTO transactions (
                society_id, trx_date, acc_id, entity_id, acc_particulars,
                amount, mode, payment_gateway_id, status, created_by
            ) VALUES (:society_id, :trx_date, :acc_id, :entity_id, :acc_particulars,
                      :amount, :mode, :payment_gateway_id, 'paid', :created_by)
            RETURNING id
            """,
            {
                'society_id': society_id,
                'trx_date': data.get("trx_date", date.today()),
                'acc_id': data["acc_id"],
                'entity_id': data.get("entity_id"),
                'acc_particulars': data["acc_particulars"],
                'amount': data["amount"],
                'mode': mode,
                'payment_gateway_id': data.get("payment_gateway_id"),
                'created_by': created_by
            },
            fetch_one=True
        )
        
        if not result:
            return False, "Failed to record receipt", 0
        
        transaction_id = result["id"]
        
        logger.info(f"Receipt recorded: ₹{float(data['amount']):,.2f} (ID: {transaction_id})")
        return True, f"Receipt of ₹{float(data['amount']):,.2f} recorded successfully", transaction_id
        
    except Exception as e:
        logger.error(f"Error recording receipt: {e}")
        return False, f"Error: {str(e)}", 0


def record_expense(society_id: int, data: dict, created_by: int = None) -> tuple[bool, str, int]:
    """
    Record an expense (debit from society).
    
    Args:
        data: {
            "trx_date": date (default: today),
            "acc_id": int (required - must be Dr account),
            "entity_id": int (optional - link to apartment/vendor/user),
            "acc_particulars": str (required - description),
            "amount": Decimal (required),
            "mode": str (cash/cheque/upi/card/bank/crypto, default: cash),
            "payment_gateway_id": str (for online payables)
        }
    
    Returns:
        (success: bool, message: str, transaction_id: int)
    """
    try:
        # Validate required fields
        if not data.get("acc_id"):
            return False, "Account is required", 0
        
        if not data.get("acc_particulars"):
            return False, "Particulars are required", 0
        
        if not data.get("amount") or float(data["amount"]) <= 0:
            return False, "Valid amount is required", 0
        
        # Validate account is Dr type
        account = db._execute(
            "SELECT drcr_account, name FROM accounts WHERE id = :id AND society_id = :society_id",
            {'id': data["acc_id"], 'society_id': society_id},
            fetch_one=True
        )
        
        if not account:
            return False, "Account not found", 0
        
        if account["drcr_account"] != "Dr":
            return False, f"Invalid account selected ('{account['name']}' is a Credit account, not a Debit account)", 0
        
        # Validate mode
        valid_modes = ["cash", "cheque", "upi", "card", "bank", "crypto"]
        mode = data.get("mode", "cash").lower()
        if mode not in valid_modes:
            return False, f"Invalid payment mode. Must be one of: {', '.join(valid_modes)}", 0
        
        # Create transaction
        result = db._execute(
            """
            INSERT INTO transactions (
                society_id, trx_date, acc_id, entity_id, acc_particulars,
                amount, mode, payment_gateway_id, status, created_by
            ) VALUES (:society_id, :trx_date, :acc_id, :entity_id, :acc_particulars,
                      :amount, :mode, :payment_gateway_id, 'paid', :created_by)
            RETURNING id
            """,
            {
                'society_id': society_id,
                'trx_date': data.get("trx_date", date.today()),
                'acc_id': data["acc_id"],
                'entity_id': data.get("entity_id"),
                'acc_particulars': data["acc_particulars"],
                'amount': data["amount"],
                'mode': mode,
                'payment_gateway_id': data.get("payment_gateway_id"),
                'created_by': created_by
            },
            fetch_one=True
        )
        
        if not result:
            return False, "Failed to record expense", 0
        
        transaction_id = result["id"]
        
        logger.info(f"Expense recorded: ₹{float(data['amount']):,.2f} (ID: {transaction_id})")
        return True, f"Expense of ₹{float(data['amount']):,.2f} recorded successfully", transaction_id
        
    except Exception as e:
        logger.error(f"Error recording expense: {e}")
        return False, f"Error: {str(e)}", 0


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
        
        db._execute(
            f"UPDATE transactions SET {', '.join(updates)} WHERE id = :transaction_id AND society_id = :society_id",
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


# ════════════════════════════════════════════════════════════════════════════
# CASHBOOK QUERIES
# ════════════════════════════════════════════════════════════════════════════

def get_cashbook(society_id: int, start_date: date = None, end_date: date = None, page: int = 1, page_size: int = 100) -> tuple[list, int, dict]:
    """
    Get cashbook with running balance.
    Shows receipts (Cr accounts) and payables (Dr accounts) in dual-column format.
    
    Args:
        society_id: Society ID
        start_date: Filter from date (optional)
        end_date: Filter to date (optional)
        page: Page number (1-indexed)
        page_size: Items per page
    
    Returns:
        (rows: list, total_count: int, summary: dict)
        
    Summary contains:
        - opening_balance: Balance at start_date
        - total_receipts: Sum of all receipts
        - total_payables: Sum of all payables
        - closing_balance: Final balance
    """
    try:
        offset = (page - 1) * page_size
        params = {'society_id': society_id, 'page_size': page_size, 'offset': offset}
        date_filter = ""
        
        if start_date:
            date_filter += " AND t.trx_date >= :start_date"
            params['start_date'] = start_date
        if end_date:
            date_filter += " AND t.trx_date <= :end_date"
            params['end_date'] = end_date
        
        # Get opening balance (before start_date)
        opening_balance = 0.0
        if start_date:
            opening = db._execute(
                """
                SELECT 
                    COALESCE(SUM(
                        CASE 
                            WHEN a.drcr_account = 'Cr' THEN t.amount
                            ELSE -t.amount
                        END
                    ), 0) as balance
                FROM transactions t
                JOIN accounts a ON t.acc_id = a.id
                WHERE t.society_id = :society_id 
                  AND t.status = 'paid'
                  AND t.trx_date < :start_date
                """,
                {'society_id': society_id, 'start_date': start_date},
                fetch_one=True
            )
            opening_balance = float(opening.get("balance", 0)) if opening else 0.0
        
        # Get total count
        count_query = f"""
            SELECT COUNT(*) as c
            FROM transactions t
            WHERE t.society_id = :society_id 
              AND t.status = 'paid'
              {date_filter}
        """
        count_params = {k: v for k, v in params.items() if k not in ['page_size', 'offset']}
        count_result = db._execute(count_query, count_params, fetch_one=True)
        total = count_result["c"] if count_result else 0
        
        # Get transactions with running balance
        query = f"""
            WITH cashbook AS (
                SELECT 
                    t.id,
                    t.trx_date,
                    a.name AS account_name,
                    a.tab_name,
                    a.drcr_account,
                    t.acc_particulars,
                    t.amount,
                    t.mode,
                    t.payment_gateway_id
                FROM transactions t
                JOIN accounts a ON t.acc_id = a.id
                WHERE t.society_id = :society_id
                  AND t.status = 'paid'
                  {date_filter}
                ORDER BY t.trx_date, t.id
                LIMIT :page_size OFFSET :offset
            )
            SELECT 
                id,
                trx_date,
                account_name,
                tab_name,
                drcr_account,
                acc_particulars,
                amount,
                mode,
                payment_gateway_id,
                CASE WHEN drcr_account = 'Cr' THEN account_name END AS receipt_account,
                CASE WHEN drcr_account = 'Cr' THEN acc_particulars END AS receipt_particulars,
                CASE WHEN drcr_account = 'Cr' AND mode = 'cash' THEN amount END AS receipt_cash,
                CASE WHEN drcr_account = 'Cr' AND mode IN ('cheque', 'bank') THEN amount END AS receipt_cheque,
                CASE WHEN drcr_account = 'Cr' THEN amount END AS receipt_total,
                
                CASE WHEN drcr_account = 'Dr' THEN account_name END AS payment_account,
                CASE WHEN drcr_account = 'Dr' THEN acc_particulars END AS payment_particulars,
                CASE WHEN drcr_account = 'Dr' AND mode = 'cash' THEN amount END AS payment_cash,
                CASE WHEN drcr_account = 'Dr' AND mode IN ('cheque', 'bank') THEN amount END AS payment_cheque,
                CASE WHEN drcr_account = 'Dr' THEN amount END AS payment_total
            FROM cashbook
        """
        
        rows = db._execute(query, params, fetch_all=True) or []
        
        # Calculate running balance
        balance = opening_balance
        for row in rows:
            if row.get("receipt_total"):
                balance += float(row["receipt_total"])
            if row.get("payment_total"):
                balance -= float(row["payment_total"])
            row["balance"] = round(balance, 2)
        
        # Calculate summary
        total_receipts = sum(float(r.get("receipt_total", 0)) for r in rows if r.get("receipt_total"))
        total_payables = sum(float(r.get("payment_total", 0)) for r in rows if r.get("payment_total"))
        
        summary = {
            "opening_balance": round(opening_balance, 2),
            "total_receipts": round(total_receipts, 2),
            "total_payables": round(total_payables, 2),
            "closing_balance": round(balance, 2)
        }
        
        return rows, total, summary
        
    except Exception as e:
        logger.error(f"Error getting cashbook: {e}")
        return [], 0, {}


def get_cashbook_summary(society_id: int, start_date: date = None, end_date: date = None) -> dict:
    """
    Get cashbook summary (totals only, no transactions).
    
    Returns:
        {
            "opening_balance": Decimal,
            "total_receipts": Decimal,
            "total_payables": Decimal,
            "closing_balance": Decimal
        }
    """
    try:
        params = {'society_id': society_id}
        date_filter = ""
        
        if start_date:
            date_filter += " AND t.trx_date >= :start_date"
            params['start_date'] = start_date
        if end_date:
            date_filter += " AND t.trx_date <= :end_date"
            params['end_date'] = end_date
        
        # Get opening balance
        opening_balance = 0.0
        if start_date:
            opening = db._execute(
                """
                SELECT 
                    COALESCE(SUM(
                        CASE 
                            WHEN a.drcr_account = 'Cr' THEN t.amount
                            ELSE -t.amount
                        END
                    ), 0) as balance
                FROM transactions t
                JOIN accounts a ON t.acc_id = a.id
                WHERE t.society_id = :society_id 
                  AND t.status = 'paid'
                  AND t.trx_date < :start_date
                """,
                {'society_id': society_id, 'start_date': start_date},
                fetch_one=True
            )
            opening_balance = float(opening.get("balance", 0)) if opening else 0.0
        
        # Get period totals
        totals = db._execute(
            f"""
            SELECT 
                COALESCE(SUM(CASE WHEN a.drcr_account = 'Cr' THEN t.amount END), 0) as total_receipts,
                COALESCE(SUM(CASE WHEN a.drcr_account = 'Dr' THEN t.amount END), 0) as total_payables
            FROM transactions t
            JOIN accounts a ON t.acc_id = a.id
            WHERE t.society_id = :society_id
              AND t.status = 'paid'
              {date_filter}
            """,
            params,
            fetch_one=True
        )
        
        total_receipts = float(totals.get("total_receipts", 0)) if totals else 0.0
        total_payables = float(totals.get("total_payables", 0)) if totals else 0.0
        closing_balance = opening_balance + total_receipts - total_payables
        
        return {
            "opening_balance": round(opening_balance, 2),
            "total_receipts": round(total_receipts, 2),
            "total_payables": round(total_payables, 2),
            "closing_balance": round(closing_balance, 2)
        }
        
    except Exception as e:
        logger.error(f"Error getting cashbook summary: {e}")
        return {
            "opening_balance": 0.0,
            "total_receipts": 0.0,
            "total_payables": 0.0,
            "closing_balance": 0.0
        }


# ════════════════════════════════════════════════════════════════════════════
# LEDGER QUERIES
# ════════════════════════════════════════════════════════════════════════════

def get_ledger(society_id: int, account_id: int, start_date: date = None, end_date: date = None, page: int = 1, page_size: int = 100) -> tuple[list, int, dict]:
    """
    Get ledger for a specific account with running balance.
    
    Args:
        society_id: Society ID
        account_id: Account ID
        start_date: Filter from date (optional)
        end_date: Filter to date (optional)
        page: Page number (1-indexed)
        page_size: Items per page
    
    Returns:
        (rows: list, total_count: int, account_info: dict)
        
    Account info contains:
        - id: Account ID
        - name: Account name
        - drcr_account: Dr or Cr
        - opening_balance: Balance at start_date (with Dr/Cr side)
        - closing_balance: Final balance (with Dr/Cr side)
    """
    try:
        # Get account info
        account = db._execute(
            """
            SELECT id, name, drcr_account, has_bf, drcr_bf, bf_amount
            FROM accounts 
            WHERE id = :id AND society_id = :society_id
            """,
            {'id': account_id, 'society_id': society_id},
            fetch_one=True
        )
        
        if not account:
            return [], 0, {}
        
        # Calculate opening balance
        opening_balance = 0.0
        opening_side = account["drcr_account"]
        
        # Start with B/F if account has it
        if account.get("has_bf") and account.get("bf_amount"):
            bf_amount = float(account["bf_amount"])
            if account["drcr_bf"] == account["drcr_account"]:
                opening_balance = bf_amount
            else:
                opening_balance = -bf_amount
        
        # Add transactions before start_date
        if start_date:
            before_start = db._execute(
                """
                SELECT 
                    COALESCE(SUM(
                        CASE 
                            WHEN :drcr_account = 'Cr' THEN t.amount
                            ELSE -t.amount
                        END
                    ), 0) as balance
                FROM transactions t
                WHERE t.acc_id = :acc_id
                  AND t.status = 'paid'
                  AND t.trx_date < :start_date
                """,
                {
                    'drcr_account': account["drcr_account"],
                    'acc_id': account_id,
                    'start_date': start_date
                },
                fetch_one=True
            )
            opening_balance += float(before_start.get("balance", 0)) if before_start else 0.0
        
        # Build query params
        offset = (page - 1) * page_size
        params = {'acc_id': account_id, 'page_size': page_size, 'offset': offset}
        date_filter = ""
        
        if start_date:
            date_filter += " AND t.trx_date >= :start_date"
            params['start_date'] = start_date
        if end_date:
            date_filter += " AND t.trx_date <= :end_date"
            params['end_date'] = end_date
        
        # Get total count
        count_query = f"""
            SELECT COUNT(*) as c
            FROM transactions t
            WHERE t.acc_id = :acc_id 
              AND t.status = 'paid'
              {date_filter}
        """
        count_params = {k: v for k, v in params.items() if k not in ['page_size', 'offset']}
        count_result = db._execute(count_query, count_params, fetch_one=True)
        total = count_result["c"] if count_result else 0
        
        # Get transactions
        query = f"""
            SELECT 
                t.id,
                t.trx_date AS date,
                t.acc_particulars AS description,
                t.amount,
                t.mode
            FROM transactions t
            WHERE t.acc_id = :acc_id
              AND t.status = 'paid'
              {date_filter}
            ORDER BY t.trx_date, t.id
            LIMIT :page_size OFFSET :offset
        """
        
        rows = db._execute(query, params, fetch_all=True) or []
        
        # Calculate running balance and format debit/credit columns
        balance = opening_balance
        for row in rows:
            amount = float(row["amount"])
            
            if account["drcr_account"] == "Dr":
                row["debit"] = amount
                row["credit"] = None
                balance += amount
            else:
                row["debit"] = None
                row["credit"] = amount
                balance += amount
            
            row["balance"] = round(balance, 2)
            # Determine balance side
            row["balance_side"] = account["drcr_account"] if balance >= 0 else ("Cr" if account["drcr_account"] == "Dr" else "Dr")
            row["balance_abs"] = abs(round(balance, 2))
        
        # Account info summary
        account_info = {
            "id": account["id"],
            "name": account["name"],
            "drcr_account": account["drcr_account"],
            "opening_balance": round(abs(opening_balance), 2),
            "opening_side": opening_side if opening_balance >= 0 else ("Cr" if opening_side == "Dr" else "Dr"),
            "closing_balance": round(abs(balance), 2),
            "closing_side": account["drcr_account"] if balance >= 0 else ("Cr" if account["drcr_account"] == "Dr" else "Dr")
        }
        
        return rows, total, account_info
        
    except Exception as e:
        logger.error(f"Error getting ledger: {e}")
        import traceback
        traceback.print_exc()
        return [], 0, {}


# ════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ════════════════════════════════════════════════════════════════════════════

def get_account_balance(account_id: int, as_of_date: date = None) -> dict:
    """
    Get current balance for an account.
    
    Returns:
        {
            "balance": Decimal,
            "side": str ('Dr' or 'Cr'),
            "balance_abs": Decimal (absolute value)
        }
    """
    try:
        account = db._execute(
            "SELECT drcr_account, has_bf, drcr_bf, bf_amount FROM accounts WHERE id = :id",
            {'id': account_id},
            fetch_one=True
        )
        
        if not account:
            return {"balance": 0.0, "side": "Dr", "balance_abs": 0.0}
        
        # Start with B/F
        balance = 0.0
        if account.get("has_bf") and account.get("bf_amount"):
            bf_amount = float(account["bf_amount"])
            if account["drcr_bf"] == account["drcr_account"]:
                balance = bf_amount
            else:
                balance = -bf_amount
        
        # Add all transactions
        date_filter = ""
        params = {'drcr_account': account["drcr_account"], 'acc_id': account_id}
        if as_of_date:
            date_filter = " AND t.trx_date <= :as_of_date"
            params['as_of_date'] = as_of_date
        
        transactions = db._execute(
            f"""
            SELECT 
                COALESCE(SUM(
                    CASE 
                        WHEN :drcr_account = 'Cr' THEN t.amount
                        ELSE -t.amount
                    END
                ), 0) as total
            FROM transactions t
            WHERE t.acc_id = :acc_id
              AND t.status = 'paid'
              {date_filter}
            """,
            params,
            fetch_one=True
        )
        
        balance += float(transactions.get("total", 0)) if transactions else 0.0
        
        side = account["drcr_account"] if balance >= 0 else ("Cr" if account["drcr_account"] == "Dr" else "Dr")
        
        return {
            "balance": round(balance, 2),
            "side": side,
            "balance_abs": round(abs(balance), 2)
        }
        
    except Exception as e:
        logger.error(f"Error getting account balance: {e}")
        return {"balance": 0.0, "side": "Dr", "balance_abs": 0.0}


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
