from app import db
from datetime import datetime

class Society(db.Model):
    __tablename__ = 'societies'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True, index=True)
    logo = db.Column(db.String(100), nullable=True)
    address = db.Column(db.Text, nullable=True)
    email = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    secretary_name = db.Column(db.String(100), nullable=True)
    secretary_phone = db.Column(db.String(20), nullable=True)
    secretary_sign = db.Column(db.String(100), nullable=True)
    plan = db.Column(db.String(4), default='Free')
    plan_validity = db.Column(db.Date, nullable=False)
    arrear_start_date = db.Column(db.Date, default=datetime.now().date)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    login_background = db.Column(db.String(100), nullable=True)
    
    # Relationships
    apartments = db.relationship('Apartment', backref='society', lazy='dynamic', cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='society', lazy='dynamic')
    transactions = db.relationship('Transaction', backref='society', lazy='dynamic')
    gate_access = db.relationship('GateAccess', backref='society', lazy='dynamic')
    
    def __repr__(self):
        return f'<Society {self.name}>'