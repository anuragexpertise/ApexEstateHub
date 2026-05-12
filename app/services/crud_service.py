# app/services/crud_service.py
"""
CRUD Service - Unified handlers for all entities
Handles: Societies, Entities (Apartments/Vendors/Security), Events, Concerns, Receipts, Payments, Attendance
"""

from datetime import datetime, date
from werkzeug.security import generate_password_hash
from database.db_manager import db
import logging

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# SOCIETY MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════

def create_society(data: dict) -> tuple[bool, str, int]:
    """
    Create a new society with admin user.
    
    Args:
        data: {
            "name": str (required),
            "email": str,
            "phone": str,
            "address": str,
            "plan": str ("Free" or "Paid"),
            "admin_email": str (required),
            "admin_password": str (required),
            "logo": str (file path),
            "secretary_name": str,
            "secretary_phone": str
        }
    
    Returns:
        (success: bool, message: str, society_id: int)
    """
    try:
        # Validate required fields
        if not data.get("name"):
            return False, "Society name is required", 0
        
        if not data.get("admin_email") or not data.get("admin_password"):
            return False, "Admin email and password are required", 0
        
        # Check if society name already exists
        existing = db._execute(
            "SELECT id FROM societies WHERE name = %s",
            (data["name"],),
            fetch_one=True
        )
        if existing:
            return False, f"Society '{data['name']}' already exists", 0
        
        # Create society
        society = db._execute(
            """
            INSERT INTO societies (
                name, email, phone, address, logo,
                secretary_name, secretary_phone,
                plan, plan_validity, arrear_start_date
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                data["name"],
                data.get("email"),
                data.get("phone"),
                data.get("address"),
                data.get("logo"),
                data.get("secretary_name"),
                data.get("secretary_phone"),
                data.get("plan", "Free"),
                date.today(),
                date.today()
            ),
            fetch_one=True
        )
        
        if not society:
            return False, "Failed to create society", 0
        
        society_id = society["id"]
        
        # Create admin user
        admin_hash = generate_password_hash(data["admin_password"])
        admin = db._execute(
            """
            INSERT INTO users (society_id, email, password_hash, role, login_method)
            VALUES (%s, %s, %s, 'admin', 'password')
            RETURNING id
            """,
            (society_id, data["admin_email"], admin_hash),
            fetch_one=True
        )
        
        if not admin:
            # Rollback society creation
            db._execute("DELETE FROM societies WHERE id = %s", (society_id,))
            return False, "Failed to create admin user", 0
        
        logger.info(f"Society created: {data['name']} (ID: {society_id})")
        return True, f"Society '{data['name']}' created successfully", society_id
        
    except Exception as e:
        logger.error(f"Error creating society: {e}")
        return False, f"Error: {str(e)}", 0


def update_society(society_id: int, data: dict) -> tuple[bool, str]:
    """
    Update society information.
    
    Args:
        society_id: Society ID
        data: Fields to update
    
    Returns:
        (success: bool, message: str)
    """
    try:
        allowed_fields = [
            "name", "email", "phone", "address", "logo",
            "secretary_name", "secretary_phone", "secretary_sign",
            "plan", "plan_validity"
        ]
        
        updates = []
        params = []
        
        for field in allowed_fields:
            if field in data:
                updates.append(f"{field} = %s")
                params.append(data[field])
        
        if not updates:
            return False, "No fields to update"
        
        params.append(society_id)
        
        db._execute(
            f"UPDATE societies SET {', '.join(updates)} WHERE id = %s",
            tuple(params)
        )
        
        logger.info(f"Society {society_id} updated")
        return True, "Society updated successfully"
        
    except Exception as e:
        logger.error(f"Error updating society: {e}")
        return False, f"Error: {str(e)}"


def get_society(society_id: int) -> dict:
    """Get society details."""
    return db._execute(
        "SELECT * FROM societies WHERE id = %s",
        (society_id,),
        fetch_one=True
    ) or {}


def list_societies(filters: dict = None, page: int = 1, page_size: int = 50) -> tuple[list, int]:
    """
    List societies with filtering and pagination.
    
    Args:
        filters: {"plan": str, "search": str}
        page: Page number (1-indexed)
        page_size: Items per page
    
    Returns:
        (rows: list, total_count: int)
    """
    offset = (page - 1) * page_size
    where_clauses = []
    params = []
    
    if filters:
        if filters.get("plan"):
            where_clauses.append("plan = %s")
            params.append(filters["plan"])
        
        if filters.get("search"):
            where_clauses.append("(name ILIKE %s OR email ILIKE %s)")
            search_term = f"%{filters['search']}%"
            params.extend([search_term, search_term])
    
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    
    # Get total count
    count_result = db._execute(
        f"SELECT COUNT(*) as c FROM societies {where_sql}",
        tuple(params),
        fetch_one=True
    )
    total = count_result["c"] if count_result else 0
    
    # Get paginated results
    rows = db._execute(
        f"""
        SELECT id, name, email, phone, plan, created_at 
        FROM societies {where_sql}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [page_size, offset]),
        fetch_all=True
    ) or []
    
    return rows, total


# ════════════════════════════════════════════════════════════════════════════
# ENTITY MANAGEMENT (Apartments, Vendors, Security)
# ════════════════════════════════════════════════════════════════════════════

def create_apartment(society_id: int, data: dict) -> tuple[bool, str, int]:
    """
    Create apartment with optional user account.
    
    Args:
        data: {
            "flat_number": str (required),
            "owner_name": str,
            "mobile": str,
            "apartment_size": int,
            "email": str (optional - creates user),
            "password": str (required if email provided)
        }
    
    Returns:
        (success: bool, message: str, apartment_id: int)
    """
    try:
        if not data.get("flat_number"):
            return False, "Flat number is required", 0
        
        # Check for duplicate flat number
        existing = db._execute(
            "SELECT id FROM apartments WHERE society_id = %s AND flat_number = %s",
            (society_id, data["flat_number"]),
            fetch_one=True
        )
        if existing:
            return False, f"Flat {data['flat_number']} already exists", 0
        
        # Create apartment
        apartment = db._execute(
            """
            INSERT INTO apartments (
                society_id, flat_number, owner_name, mobile, apartment_size, active
            ) VALUES (%s, %s, %s, %s, %s, TRUE)
            RETURNING id
            """,
            (
                society_id,
                data["flat_number"],
                data.get("owner_name"),
                data.get("mobile"),
                data.get("apartment_size", 0)
            ),
            fetch_one=True
        )
        
        if not apartment:
            return False, "Failed to create apartment", 0
        
        apartment_id = apartment["id"]
        
        # Create user account if email provided
        if data.get("email") and data.get("password"):
            user_hash = generate_password_hash(data["password"])
            user = db._execute(
                """
                INSERT INTO users (society_id, email, password_hash, role, linked_id, login_method)
                VALUES (%s, %s, %s, 'apartment', %s, 'password')
                RETURNING id
                """,
                (society_id, data["email"], user_hash, apartment_id),
                fetch_one=True
            )
            
            if not user:
                logger.warning(f"Apartment created but user creation failed for {data['email']}")
        
        logger.info(f"Apartment created: {data['flat_number']} (ID: {apartment_id})")
        return True, f"Apartment {data['flat_number']} created successfully", apartment_id
        
    except Exception as e:
        logger.error(f"Error creating apartment: {e}")
        return False, f"Error: {str(e)}", 0


def create_vendor(society_id: int, data: dict) -> tuple[bool, str, int]:
    """
    Create vendor with user account.
    
    Args:
        data: {
            "email": str (required),
            "password": str (required),
            "name": str (required),
            "service_type": str,
            "mobile": str,
            "service_description": str
        }
    
    Returns:
        (success: bool, message: str, vendor_id: int)
    """
    try:
        if not data.get("email") or not data.get("password"):
            return False, "Email and password are required", 0
        
        if not data.get("name"):
            return False, "Vendor name is required", 0
        
        # Check if email exists
        existing = db._execute(
            "SELECT id FROM users WHERE society_id = %s AND email = %s",
            (society_id, data["email"]),
            fetch_one=True
        )
        if existing:
            return False, f"Email {data['email']} already registered", 0
        
        # Create vendor record
        vendor = db._execute(
            """
            INSERT INTO vendors (
                society_id, name, service_type, mobile, service_description, active
            ) VALUES (%s, %s, %s, %s, %s, TRUE)
            RETURNING id
            """,
            (
                society_id,
                data["name"],
                data.get("service_type"),
                data.get("mobile"),
                data.get("service_description")
            ),
            fetch_one=True
        )
        
        if not vendor:
            return False, "Failed to create vendor", 0
        
        vendor_id = vendor["id"]
        
        # Create user account
        user_hash = generate_password_hash(data["password"])
        user = db._execute(
            """
            INSERT INTO users (society_id, email, password_hash, role, linked_id, login_method)
            VALUES (%s, %s, %s, 'vendor', %s, 'password')
            RETURNING id
            """,
            (society_id, data["email"], user_hash, vendor_id),
            fetch_one=True
        )
        
        if not user:
            # Rollback vendor creation
            db._execute("DELETE FROM vendors WHERE id = %s", (vendor_id,))
            return False, "Failed to create user account", 0
        
        logger.info(f"Vendor created: {data['name']} (ID: {vendor_id})")
        return True, f"Vendor {data['name']} created successfully", vendor_id
        
    except Exception as e:
        logger.error(f"Error creating vendor: {e}")
        return False, f"Error: {str(e)}", 0


def create_security_staff(society_id: int, data: dict) -> tuple[bool, str, int]:
    """
    Create security staff with user account.
    
    Args:
        data: {
            "email": str (required),
            "password": str (required),
            "name": str (required),
            "mobile": str,
            "shift": str,
            "joining_date": date,
            "salary_per_shift": float
        }
    
    Returns:
        (success: bool, message: str, security_id: int)
    """
    try:
        if not data.get("email") or not data.get("password"):
            return False, "Email and password are required", 0
        
        if not data.get("name"):
            return False, "Security staff name is required", 0
        
        # Check if email exists
        existing = db._execute(
            "SELECT id FROM users WHERE society_id = %s AND email = %s",
            (society_id, data["email"]),
            fetch_one=True
        )
        if existing:
            return False, f"Email {data['email']} already registered", 0
        
        # Create security record
        security = db._execute(
            """
            INSERT INTO security_staff (
                society_id, name, mobile, shift, joining_date, salary_per_shift, active
            ) VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            RETURNING id
            """,
            (
                society_id,
                data["name"],
                data.get("mobile"),
                data.get("shift"),
                data.get("joining_date", date.today()),
                data.get("salary_per_shift", 0)
            ),
            fetch_one=True
        )
        
        if not security:
            return False, "Failed to create security staff", 0
        
        security_id = security["id"]
        
        # Create user account
        user_hash = generate_password_hash(data["password"])
        user = db._execute(
            """
            INSERT INTO users (society_id, email, password_hash, role, linked_id, login_method)
            VALUES (%s, %s, %s, 'security', %s, 'password')
            RETURNING id
            """,
            (society_id, data["email"], user_hash, security_id),
            fetch_one=True
        )
        
        if not user:
            # Rollback security creation
            db._execute("DELETE FROM security_staff WHERE id = %s", (security_id,))
            return False, "Failed to create user account", 0
        
        logger.info(f"Security staff created: {data['name']} (ID: {security_id})")
        return True, f"Security staff {data['name']} created successfully", security_id
        
    except Exception as e:
        logger.error(f"Error creating security staff: {e}")
        return False, f"Error: {str(e)}", 0


# ════════════════════════════════════════════════════════════════════════════
# EVENT MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════

def create_event(society_id: int, data: dict) -> tuple[bool, str, int]:
    """
    Create a society event.
    
    Args:
        data: {
            "title": str (required),
            "description": str,
            "event_date": date (required),
            "event_time": str,
            "venue": str,
            "open_to": str ("all", "apartment", "vendor", "security")
        }
    
    Returns:
        (success: bool, message: str, event_id: int)
    """
    try:
        if not data.get("title"):
            return False, "Event title is required", 0
        
        if not data.get("event_date"):
            return False, "Event date is required", 0
        
        event = db._execute(
            """
            INSERT INTO events (
                society_id, title, description, event_date, event_time, venue, open_to
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                society_id,
                data["title"],
                data.get("description"),
                data["event_date"],
                data.get("event_time"),
                data.get("venue"),
                data.get("open_to", "all")
            ),
            fetch_one=True
        )
        
        if not event:
            return False, "Failed to create event", 0
        
        event_id = event["id"]
        
        logger.info(f"Event created: {data['title']} (ID: {event_id})")
        return True, f"Event '{data['title']}' created successfully", event_id
        
    except Exception as e:
        logger.error(f"Error creating event: {e}")
        return False, f"Error: {str(e)}", 0


def update_event(event_id: int, society_id: int, data: dict) -> tuple[bool, str]:
    """Update event details."""
    try:
        allowed_fields = ["title", "description", "event_date", "event_time", "venue", "open_to"]
        
        updates = []
        params = []
        
        for field in allowed_fields:
            if field in data:
                updates.append(f"{field} = %s")
                params.append(data[field])
        
        if not updates:
            return False, "No fields to update"
        
        params.extend([event_id, society_id])
        
        db._execute(
            f"UPDATE events SET {', '.join(updates)} WHERE id = %s AND society_id = %s",
            tuple(params)
        )
        
        logger.info(f"Event {event_id} updated")
        return True, "Event updated successfully"
        
    except Exception as e:
        logger.error(f"Error updating event: {e}")
        return False, f"Error: {str(e)}"


def list_events(society_id: int, filters: dict = None, page: int = 1, page_size: int = 20) -> tuple[list, int]:
    """
    List events with filtering.
    
    Args:
        filters: {"upcoming": bool, "search": str}
    
    Returns:
        (rows: list, total_count: int)
    """
    offset = (page - 1) * page_size
    where_clauses = ["society_id = %s"]
    params = [society_id]
    
    if filters:
        if filters.get("upcoming"):
            where_clauses.append("event_date >= CURRENT_DATE")
        
        if filters.get("search"):
            where_clauses.append("(title ILIKE %s OR description ILIKE %s)")
            search_term = f"%{filters['search']}%"
            params.extend([search_term, search_term])
    
    where_sql = f"WHERE {' AND '.join(where_clauses)}"
    
    count_result = db._execute(
        f"SELECT COUNT(*) as c FROM events {where_sql}",
        tuple(params),
        fetch_one=True
    )
    total = count_result["c"] if count_result else 0
    
    rows = db._execute(
        f"""
        SELECT id, title, description, event_date, event_time, venue, open_to, created_at
        FROM events {where_sql}
        ORDER BY event_date DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [page_size, offset]),
        fetch_all=True
    ) or []
    
    return rows, total


# ════════════════════════════════════════════════════════════════════════════
# CONCERN MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════

def create_concern(society_id: int, data: dict, user_id: int = None) -> tuple[bool, str, int]:
    """
    Create a maintenance concern/complaint.
    
    Args:
        data: {
            "flat_no": str,
            "concern_type": str (required),
            "description": str (required),
            "preferred_time": str
        }
        user_id: User who raised the concern (optional)
    
    Returns:
        (success: bool, message: str, concern_id: int)
    """
    try:
        if not data.get("concern_type"):
            return False, "Concern type is required", 0
        
        if not data.get("description"):
            return False, "Description is required", 0
        
        concern = db._execute(
            """
            INSERT INTO concerns (
                society_id, flat_no, concern_type, description, preferred_time, status
            ) VALUES (%s, %s, %s, %s, %s, 'open')
            RETURNING id
            """,
            (
                society_id,
                data.get("flat_no"),
                data["concern_type"],
                data["description"],
                data.get("preferred_time", "anytime")
            ),
            fetch_one=True
        )
        
        if not concern:
            return False, "Failed to create concern", 0
        
        concern_id = concern["id"]
        
        logger.info(f"Concern created: {data['concern_type']} (ID: {concern_id})")
        return True, "Concern registered successfully", concern_id
        
    except Exception as e:
        logger.error(f"Error creating concern: {e}")
        return False, f"Error: {str(e)}", 0


def update_concern(concern_id: int, society_id: int, data: dict) -> tuple[bool, str]:
    """
    Update concern status/assignment.
    
    Args:
        data: {"status": str, "assigned_to": str}
    """
    try:
        allowed_fields = ["status", "assigned_to"]
        
        updates = []
        params = []
        
        for field in allowed_fields:
            if field in data:
                updates.append(f"{field} = %s")
                params.append(data[field])
        
        if not updates:
            return False, "No fields to update"
        
        params.extend([concern_id, society_id])
        
        db._execute(
            f"UPDATE concerns SET {', '.join(updates)} WHERE id = %s AND society_id = %s",
            tuple(params)
        )
        
        logger.info(f"Concern {concern_id} updated")
        return True, "Concern updated successfully"
        
    except Exception as e:
        logger.error(f"Error updating concern: {e}")
        return False, f"Error: {str(e)}"


def list_concerns(society_id: int, filters: dict = None, page: int = 1, page_size: int = 20) -> tuple[list, int]:
    """
    List concerns with filtering.
    
    Args:
        filters: {"status": str, "flat_no": str, "search": str}
    
    Returns:
        (rows: list, total_count: int)
    """
    offset = (page - 1) * page_size
    where_clauses = ["society_id = %s"]
    params = [society_id]
    
    if filters:
        if filters.get("status"):
            where_clauses.append("status = %s")
            params.append(filters["status"])
        
        if filters.get("flat_no"):
            where_clauses.append("flat_no = %s")
            params.append(filters["flat_no"])
        
        if filters.get("search"):
            where_clauses.append("(description ILIKE %s OR concern_type ILIKE %s)")
            search_term = f"%{filters['search']}%"
            params.extend([search_term, search_term])
    
    where_sql = f"WHERE {' AND '.join(where_clauses)}"
    
    count_result = db._execute(
        f"SELECT COUNT(*) as c FROM concerns {where_sql}",
        tuple(params),
        fetch_one=True
    )
    total = count_result["c"] if count_result else 0
    
    rows = db._execute(
        f"""
        SELECT id, flat_no, concern_type, description, status, assigned_to, 
               preferred_time, created_at
        FROM concerns {where_sql}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [page_size, offset]),
        fetch_all=True
    ) or []
    
    return rows, total


# ════════════════════════════════════════════════════════════════════════════
# PAYMENT & RECEIPT MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════

def create_payment(society_id: int, data: dict) -> tuple[bool, str, int]:
    """
    Create a payment record (pending payment/bill).
    
    Args:
        data: {
            "apartment_id": int,
            "user_id": int (optional - for vendors/security),
            "amount": float (required),
            "payment_type": str,
            "due_date": date,
            "status": str ("pending", "verified", "failed")
        }
    
    Returns:
        (success: bool, message: str, payment_id: int)
    """
    try:
        if not data.get("amount"):
            return False, "Amount is required", 0
        
        payment = db._execute(
            """
            INSERT INTO payments (
                society_id, user_id, apartment_id, amount, 
                payment_type, payment_method, status, due_date
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                society_id,
                data.get("user_id"),
                data.get("apartment_id"),
                data["amount"],
                data.get("payment_type"),
                data.get("payment_method"),
                data.get("status", "pending"),
                data.get("due_date")
            ),
            fetch_one=True
        )
        
        if not payment:
            return False, "Failed to create payment", 0
        
        payment_id = payment["id"]
        
        logger.info(f"Payment created: ₹{data['amount']} (ID: {payment_id})")
        return True, f"Payment of ₹{data['amount']} created", payment_id
        
    except Exception as e:
        logger.error(f"Error creating payment: {e}")
        return False, f"Error: {str(e)}", 0


def create_receipt(society_id: int, data: dict) -> tuple[bool, str, int]:
    """
    Create a receipt/transaction (money received).
    
    Args:
        data: {
            "trx_date": date,
            "acc_id": int (optional),
            "entity_id": int (optional),
            "acc_particulars": str (required),
            "amount": float (required),
            "mode": str ("cash", "online", "other"),
            "status": str ("paid", "pending")
        }
    
    Returns:
        (success: bool, message: str, transaction_id: int)
    """
    try:
        if not data.get("amount"):
            return False, "Amount is required", 0
        
        if not data.get("acc_particulars"):
            return False, "Particulars are required", 0
        
        transaction = db._execute(
            """
            INSERT INTO transactions (
                society_id, trx_date, acc_id, entity_id, 
                acc_particulars, amount, mode, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                society_id,
                data.get("trx_date", date.today()),
                data.get("acc_id"),
                data.get("entity_id"),
                data["acc_particulars"],
                data["amount"],
                data.get("mode", "cash"),
                data.get("status", "paid")
            ),
            fetch_one=True
        )
        
        if not transaction:
            return False, "Failed to create receipt", 0
        
        transaction_id = transaction["id"]
        
        logger.info(f"Receipt created: ₹{data['amount']} (ID: {transaction_id})")
        return True, f"Receipt of ₹{data['amount']} created", transaction_id
        
    except Exception as e:
        logger.error(f"Error creating receipt: {e}")
        return False, f"Error: {str(e)}", 0


def verify_payment(payment_id: int, society_id: int, transaction_data: dict) -> tuple[bool, str]:
    """
    Mark payment as verified and create corresponding transaction.
    
    Args:
        transaction_data: {
            "transaction_id": str,
            "payment_method": str,
            "amount": float
        }
    
    Returns:
        (success: bool, message: str)
    """
    try:
        # Update payment status
        db._execute(
            """
            UPDATE payments 
            SET status = 'verified', 
                paid_at = NOW(),
                transaction_id = %s,
                payment_method = %s
            WHERE id = %s AND society_id = %s
            """,
            (
                transaction_data.get("transaction_id"),
                transaction_data.get("payment_method"),
                payment_id,
                society_id
            )
        )
        
        # Get payment details
        payment = db._execute(
            "SELECT * FROM payments WHERE id = %s",
            (payment_id,),
            fetch_one=True
        )
        
        if not payment:
            return False, "Payment not found"
        
        # Create transaction record
        db._execute(
            """
            INSERT INTO transactions (
                society_id, trx_date, entity_id, 
                acc_particulars, amount, mode, status
            ) VALUES (%s, %s, %s, %s, %s, %s, 'paid')
            """,
            (
                society_id,
                date.today(),
                payment.get("apartment_id") or payment.get("user_id"),
                f"Payment #{payment_id} - {payment.get('payment_type', 'Payment')}",
                payment["amount"],
                transaction_data.get("payment_method", "online")
            )
        )
        
        logger.info(f"Payment {payment_id} verified")
        return True, "Payment verified and recorded"
        
    except Exception as e:
        logger.error(f"Error verifying payment: {e}")
        return False, f"Error: {str(e)}"


# ════════════════════════════════════════════════════════════════════════════
# ATTENDANCE MANAGEMENT (Security Staff)
# ════════════════════════════════════════════════════════════════════════════

def clock_in(society_id: int, security_id: int) -> tuple[bool, str, int]:
    """
    Clock in security staff.
    
    Returns:
        (success: bool, message: str, attendance_id: int)
    """
    try:
        # Check if already clocked in
        existing = db._execute(
            """
            SELECT id FROM attendance 
            WHERE society_id = %s AND security_id = %s AND time_out IS NULL
            """,
            (society_id, security_id),
            fetch_one=True
        )
        
        if existing:
            return False, "Already clocked in", 0
        
        # Create attendance record
        attendance = db._execute(
            """
            INSERT INTO attendance (society_id, security_id, time_in)
            VALUES (%s, %s, NOW())
            RETURNING id
            """,
            (society_id, security_id),
            fetch_one=True
        )
        
        if not attendance:
            return False, "Failed to clock in", 0
        
        attendance_id = attendance["id"]
        
        logger.info(f"Security {security_id} clocked in (Attendance ID: {attendance_id})")
        return True, "Clocked in successfully", attendance_id
        
    except Exception as e:
        logger.error(f"Error clocking in: {e}")
        return False, f"Error: {str(e)}", 0


def clock_out(society_id: int, security_id: int) -> tuple[bool, str]:
    """
    Clock out security staff.
    
    Returns:
        (success: bool, message: str)
    """
    try:
        # Find active attendance record
        attendance = db._execute(
            """
            SELECT id, time_in FROM attendance 
            WHERE society_id = %s AND security_id = %s AND time_out IS NULL
            ORDER BY time_in DESC
            LIMIT 1
            """,
            (society_id, security_id),
            fetch_one=True
        )
        
        if not attendance:
            return False, "No active clock-in found"
        
        # Update with clock-out time
        db._execute(
            "UPDATE attendance SET time_out = NOW() WHERE id = %s",
            (attendance["id"],)
        )
        
        logger.info(f"Security {security_id} clocked out (Attendance ID: {attendance['id']})")
        return True, "Clocked out successfully"
        
    except Exception as e:
        logger.error(f"Error clocking out: {e}")
        return False, f"Error: {str(e)}"


def get_attendance_status(society_id: int, security_id: int) -> dict:
    """
    Get current attendance status for security staff.
    
    Returns:
        {
            "is_on_duty": bool,
            "time_in": datetime,
            "duration_hours": float
        }
    """
    try:
        attendance = db._execute(
            """
            SELECT id, time_in, time_out,
                   EXTRACT(EPOCH FROM (COALESCE(time_out, NOW()) - time_in))/3600 as duration_hours
            FROM attendance 
            WHERE society_id = %s AND security_id = %s AND time_out IS NULL
            ORDER BY time_in DESC
            LIMIT 1
            """,
            (society_id, security_id),
            fetch_one=True
        )
        
        if attendance:
            return {
                "is_on_duty": True,
                "time_in": attendance["time_in"],
                "duration_hours": float(attendance["duration_hours"])
            }
        
        return {"is_on_duty": False, "time_in": None, "duration_hours": 0}
        
    except Exception as e:
        logger.error(f"Error getting attendance status: {e}")
        return {"is_on_duty": False, "time_in": None, "duration_hours": 0}


def list_attendance(society_id: int, filters: dict = None, page: int = 1, page_size: int = 50) -> tuple[list, int]:
    """
    List attendance records.
    
    Args:
        filters: {
            "security_id": int,
            "date_from": date,
            "date_to": date,
            "on_duty": bool (only currently on duty)
        }
    
    Returns:
        (rows: list, total_count: int)
    """
    offset = (page - 1) * page_size
    where_clauses = ["a.society_id = %s"]
    params = [society_id]
    
    if filters:
        if filters.get("security_id"):
            where_clauses.append("a.security_id = %s")
            params.append(filters["security_id"])
        
        if filters.get("date_from"):
            where_clauses.append("DATE(a.time_in) >= %s")
            params.append(filters["date_from"])
        
        if filters.get("date_to"):
            where_clauses.append("DATE(a.time_in) <= %s")
            params.append(filters["date_to"])
        
        if filters.get("on_duty"):
            where_clauses.append("a.time_out IS NULL")
    
    where_sql = f"WHERE {' AND '.join(where_clauses)}"
    
    count_result = db._execute(
        f"SELECT COUNT(*) as c FROM attendance a {where_sql}",
        tuple(params),
        fetch_one=True
    )
    total = count_result["c"] if count_result else 0
    
    rows = db._execute(
        f"""
        SELECT a.id, a.security_id, s.name as security_name, a.time_in, a.time_out,
               EXTRACT(EPOCH FROM (COALESCE(a.time_out, NOW()) - a.time_in))/3600 as duration_hours
        FROM attendance a
        JOIN security_staff s ON a.security_id = s.id
        {where_sql}
        ORDER BY a.time_in DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [page_size, offset]),
        fetch_all=True
    ) or []
    
    return rows, total


def calculate_monthly_hours(society_id: int, security_id: int, month: int, year: int) -> dict:
    """
    Calculate total hours worked for a security staff in a month.
    
    Returns:
        {
            "total_hours": float,
            "total_shifts": int,
            "average_shift_hours": float
        }
    """
    try:
        result = db._execute(
            """
            SELECT 
                COUNT(*) as total_shifts,
                SUM(EXTRACT(EPOCH FROM (time_out - time_in))/3600) as total_hours
            FROM attendance
            WHERE society_id = %s 
              AND security_id = %s
              AND EXTRACT(MONTH FROM time_in) = %s
              AND EXTRACT(YEAR FROM time_in) = %s
              AND time_out IS NOT NULL
            """,
            (society_id, security_id, month, year),
            fetch_one=True
        )
        
        if result:
            total_hours = float(result.get("total_hours") or 0)
            total_shifts = int(result.get("total_shifts") or 0)
            avg_hours = total_hours / total_shifts if total_shifts > 0 else 0
            
            return {
                "total_hours": round(total_hours, 2),
                "total_shifts": total_shifts,
                "average_shift_hours": round(avg_hours, 2)
            }
        
        return {"total_hours": 0, "total_shifts": 0, "average_shift_hours": 0}
        
    except Exception as e:
        logger.error(f"Error calculating monthly hours: {e}")
        return {"total_hours": 0, "total_shifts": 0, "average_shift_hours": 0}
