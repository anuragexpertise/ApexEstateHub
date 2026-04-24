# app/models/user.py
from flask_login import UserMixin
from database.db_manager import db

class User(UserMixin):
    def __init__(self, user_id, email, role, society_id=None, name=None, phone=None):
        self.id = user_id
        self.email = email
        self.role = role
        self.society_id = society_id
        self.name = name or email.split('@')[0].title()
        self.phone = phone
    
    @staticmethod
    def get(user_id):
        """Get user by ID from database"""
        try:
            result = db.execute_query(
                """SELECT u.id, u.email, u.role, u.society_id, u.name, u.phone 
                   FROM users u WHERE u.id = %s""",
                (user_id,), fetch_one=True
            )
            if result:
                return User(
                    user_id=result['id'],
                    email=result['email'],
                    role=result['role'],
                    society_id=result.get('society_id'),
                    name=result.get('name'),
                    phone=result.get('phone')
                )
        except Exception as e:
            print(f"Error loading user {user_id}: {e}")
        return None
    
    @staticmethod
    def find_by_email(email, society_id=None):
        """Find user by email and optional society"""
        try:
            query = """SELECT u.id, u.email, u.role, u.society_id, u.name, u.phone 
                       FROM users u WHERE u.email = %s"""
            params = [email]
            
            if society_id:
                query += " AND u.society_id = %s"
                params.append(society_id)
            
            result = db.execute_query(query, tuple(params), fetch_one=True)
            if result:
                return User(
                    user_id=result['id'],
                    email=result['email'],
                    role=result['role'],
                    society_id=result.get('society_id'),
                    name=result.get('name'),
                    phone=result.get('phone')
                )
        except Exception as e:
            print(f"Error finding user: {e}")
        return None
    
    @staticmethod
    def create(email, password_hash, role, society_id=None, name=None, phone=None):
        """Create a new user"""
        try:
            result = db.execute_query(
                """INSERT INTO users (email, password_hash, role, society_id, name, phone, login_method)
                   VALUES (%s, %s, %s, %s, %s, %s, 'password')
                   RETURNING id""",
                (email, password_hash, role, society_id, name, phone), fetch_one=True
            )
            if result:
                return User.get(result['id'])
        except Exception as e:
            print(f"Error creating user: {e}")
        return None
    
    def get_id(self):
        return str(self.id)
    
    def is_master_admin(self):
        return self.role == 'admin' and self.society_id is None
    
    def is_admin(self):
        return self.role == 'admin' and self.society_id is not None
    
    def is_apartment_owner(self):
        return self.role == 'apartment'
    
    def is_vendor(self):
        return self.role == 'vendor'
    
    def is_security(self):
        return self.role == 'security'
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'role': self.role,
            'society_id': self.society_id,
            'name': self.name,
            'phone': self.phone,
            'is_master_admin': self.is_master_admin()
        }