# app/models/user.py
from flask_login import UserMixin
from database.db_manager import db

class User(UserMixin):
    def __init__(self, user_id, email, role, society_id=None, linked_id=None):
        self.id = user_id
        self.email = email
        self.role = role
        self.society_id = society_id
        # apartments.id / vendors.id / security_staff.id for role in
        # ('apartment','vendor','security') — NULL for admin/master.
        # Added alongside get_current_linked_id() in audit_context.py:
        # role/society_id alone can't answer "is this the caller's own
        # record" (their own apartment, their own vendor profile, their
        # own duty shift), which is what most ownership checks actually
        # need — those were still reading auth-store's client-editable
        # apartment_id/vendor_id/security_id for that, same trust gap as
        # role, just missing from the server session until now.
        self.linked_id = linked_id
        self.name = email.split('@')[0].title() # Default name from email
    
    @staticmethod
    def get(user_id):
        try:
            result = db._execute(
                "SELECT id, email, role, society_id, linked_id FROM users WHERE id = %s",
                (user_id,), fetch_one=True
            )
            if result:
                return User(
                    user_id=result['id'],
                    email=result['email'],
                    role=result['role'],
                    society_id=result.get('society_id'),
                    linked_id=result.get('linked_id'),
                )
        except Exception as e:
            print(f"Error loading user {user_id}: {e}")
        return None

    @staticmethod
    def find_by_email(email, society_id=None):
        try:
            query  = "SELECT id, email, role, society_id, linked_id FROM users WHERE email = %s"
            params = [email]
            if society_id:
                query  += " AND society_id = %s"
                params.append(society_id)
            result = db._execute(query, tuple(params), fetch_one=True)
            if result:
                return User(
                    user_id=result['id'],
                    email=result['email'],
                    role=result['role'],
                    society_id=result.get('society_id'),
                    linked_id=result.get('linked_id'),
                )
        except Exception as e:
            print(f"Error finding user: {e}")
        return None


    @staticmethod
    def create(email, password_hash, role, society_id=None, name=None, phone=None, created_by=None):
        """Create a new user"""
        try:
            result = db._execute(
                """INSERT INTO users (email, password_hash, role, society_id, name, login_method, created_by)
                   VALUES (%s, %s, %s, %s, %s, 'password', %s)
                   RETURNING id""",
                (email, password_hash, role, society_id, name, created_by), fetch_one=True
            )
            if result:
                return User.get(result['id'])
        except Exception as e:
            print(f"Error creating user: {e}")
        return None
    
    def get_id(self):
        return str(self.id)
    
    def is_master_admin(self):
        return self.role == 'master' or (self.role == 'admin' and self.society_id is None)
    
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
            'linked_id': self.linked_id,
            'name': self.name,
            'is_master_admin': self.is_master_admin()
        }