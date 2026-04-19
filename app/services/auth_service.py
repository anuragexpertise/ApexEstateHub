from database.db_manager import db
from werkzeug.security import check_password_hash

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
        
        # For master admin (society_id is None/Null)
        if user.get('society_id') is None:
            print(f"✓ Master admin login")
            return user
        
        # For regular users
        if society_id and user.get('society_id') != society_id:
            print(f"❌ Society mismatch")
            return None
        
        print(f"✓ Authentication successful")
        return user
        
    except Exception as e:
        print(f"❌ Authentication error: {e}")
        return None