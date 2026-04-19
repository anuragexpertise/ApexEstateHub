from werkzeug.security import check_password_hash
from database.db_manager import db

def authenticate_user(email, password, society_id=None):
    """Authenticate user with email and password"""
    try:
        print(f"\n=== AUTHENTICATION DEBUG ===")
        print(f"Email: {email}")
        
        # Query for user
        query = """
            SELECT id as user_id, email, role, society_id, password_hash
            FROM users 
            WHERE email = %s
        """
        params = [email]
        
        user = db.execute_query(query, params, fetch_one=True)
        
        if not user:
            print(f"❌ User not found: {email}")
            return None
        
        print(f"✓ User found: {user.get('email')}")
        print(f"  User society_id: {user.get('society_id')}")
        print(f"  User role: {user.get('role')}")
        
        if not user.get('password_hash'):
            print(f"❌ No password hash for user")
            return None
        
        if not check_password_hash(user['password_hash'], password):
            print(f"❌ Password verification failed")
            return None
        
        print(f"✓ Password verified")
        return user
        
    except Exception as e:
        print(f"❌ Authentication error: {e}")
        return None


def authenticate_pin(email, pin, society_id=None):
    """Authenticate user with email and PIN"""
    try:
        print(f"\n=== PIN AUTHENTICATION DEBUG ===")
        print(f"Email: {email}")
        
        # Query for user
        query = """
            SELECT id as user_id, email, role, society_id, pin_hash
            FROM users 
            WHERE email = %s
        """
        params = [email]
        
        user = db.execute_query(query, params, fetch_one=True)
        
        if not user:
            print(f"❌ User not found: {email}")
            return None
        
        if not user.get('pin_hash'):
            print(f"❌ No PIN hash for user")
            return None
        
        if not check_password_hash(user['pin_hash'], pin):
            print(f"❌ PIN verification failed")
            return None
        
        print(f"✓ PIN verified")
        return user
        
    except Exception as e:
        print(f"❌ PIN authentication error: {e}")
        return None


def authenticate_pattern(email, pattern, society_id=None):
    """Authenticate user with email and pattern"""
    try:
        print(f"\n=== PATTERN AUTHENTICATION DEBUG ===")
        print(f"Email: {email}")
        
        # Query for user
        query = """
            SELECT id as user_id, email, role, society_id, pattern_hash
            FROM users 
            WHERE email = %s
        """
        params = [email]
        
        user = db.execute_query(query, params, fetch_one=True)
        
        if not user:
            print(f"❌ User not found: {email}")
            return None
        
        if not user.get('pattern_hash'):
            print(f"❌ No pattern hash for user")
            return None
        
        if not check_password_hash(user['pattern_hash'], pattern):
            print(f"❌ Pattern verification failed")
            return None
        
        print(f"✓ Pattern verified")
        return user
        
    except Exception as e:
        print(f"❌ Pattern authentication error: {e}")
        return None