# app/models/user.py
from flask_login import UserMixin
from database.db_manager import db


def _resolve_role(raw_role: str, society_id, is_master_admin_flag: bool) -> str:
    """
    Mirrors the role synthesis in app/services/auth_service.py::authenticate_user
    (raw "admin" + no society_id + is_master_admin=TRUE -> the virtual
    "master" role the rest of the app checks for). users.role never
    literally contains 'master' in the DB (CHECK constraint only allows
    admin/apartment/vendor/security) — "master" only ever existed as a
    value computed at login time and handed to the client. Without this,
    get_current_user_role() would return "admin" for master admins on
    every request after the first, since User.get()/find_by_email() just
    read the raw column — a real behavior change (master routed as an
    ordinary admin), not just a style difference, so it has to be kept in
    sync with auth_service.py's derivation rather than dropped.
    """
    if raw_role == "admin" and not society_id and is_master_admin_flag:
        return "master"
    return raw_role


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
                "SELECT id, email, role, society_id, linked_id, is_master_admin FROM users WHERE id = %s",
                (user_id,), fetch_one=True
            )
            if result:
                return User(
                    user_id=result['id'],
                    email=result['email'],
                    role=_resolve_role(result['role'], result.get('society_id'), result.get('is_master_admin')),
                    society_id=result.get('society_id'),
                    linked_id=result.get('linked_id'),
                )
        except Exception as e:
            print(f"Error loading user {user_id}: {e}")
        return None

    @staticmethod
    def find_by_email(email, society_id=None):
        try:
            query  = "SELECT id, email, role, society_id, linked_id, is_master_admin FROM users WHERE email = %s"
            params = [email]
            if society_id:
                query  += " AND society_id = %s"
                params.append(society_id)
            result = db._execute(query, tuple(params), fetch_one=True)
            if result:
                return User(
                    user_id=result['id'],
                    email=result['email'],
                    role=_resolve_role(result['role'], result.get('society_id'), result.get('is_master_admin')),
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