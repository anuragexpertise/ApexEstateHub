from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager
import json

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    society_id = db.Column(db.Integer, db.ForeignKey('societies.id', ondelete='CASCADE'), nullable=True)
    email = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    pin_hash = db.Column(db.String(255), nullable=True)
    pattern_hash = db.Column(db.String(255), nullable=True)
    role = db.Column(db.String(20), nullable=False, index=True)
    linked_id = db.Column(db.Integer, nullable=True)
    login_method = db.Column(db.String(20), default='password')
    push_subscription = db.Column(db.Text, nullable=True)  # JSON string for push subscription
    credential_id = db.Column(db.Text, nullable=True)  # For WebAuthn
    public_key = db.Column(db.Text, nullable=True)  # For WebAuthn
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='scrypt')
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def set_pin(self, pin):
        self.pin_hash = generate_password_hash(pin, method='scrypt')
    
    def check_pin(self, pin):
        return check_password_hash(self.pin_hash, pin) if self.pin_hash else False
    
    def set_pattern(self, pattern):
        self.pattern_hash = generate_password_hash(pattern, method='scrypt')
    
    def check_pattern(self, pattern):
        return check_password_hash(self.pattern_hash, pattern) if self.pattern_hash else False
    
    def is_master_admin(self):
        return self.role == 'admin' and self.society_id is None
    
    def set_push_subscription(self, subscription):
        self.push_subscription = json.dumps(subscription)
    
    def get_push_subscription(self):
        return json.loads(self.push_subscription) if self.push_subscription else None
    
    def get_id(self):
        return str(self.id)
    
    def __repr__(self):
        return f'<User {self.email}>'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))