from app import db
from app.models.user import User

def authenticate_user(email, password, society_id=None):
    """Authenticate user with email and password"""
    query = User.query.filter_by(email=email)
    
    if society_id:
        query = query.filter_by(society_id=society_id)
    else:
        query = query.filter(User.society_id.is_(None))
    
    user = query.first()
    
    if user and user.check_password(password):
        return user
    return None

def authenticate_pin(email, pin, society_id=None):
    """Authenticate user with email and PIN"""
    query = User.query.filter_by(email=email)
    
    if society_id:
        query = query.filter_by(society_id=society_id)
    
    user = query.first()
    
    if user and user.check_pin(pin):
        return user
    return None

def authenticate_pattern(email, pattern, society_id=None):
    """Authenticate user with pattern"""
    query = User.query.filter_by(email=email)
    
    if society_id:
        query = query.filter_by(society_id=society_id)
    
    user = query.first()
    
    if user and user.check_pattern(pattern):
        return user
    return None