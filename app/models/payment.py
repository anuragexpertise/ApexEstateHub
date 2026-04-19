from app import db
from datetime import datetime

class Payment(db.Model):
    __tablename__ = 'payments'
    
    id = db.Column(db.Integer, primary_key=True)
    society_id = db.Column(db.Integer, db.ForeignKey('societies.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    apartment_id = db.Column(db.Integer, db.ForeignKey('apartments.id'), nullable=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_type = db.Column(db.String(50), nullable=True)  # maintenance, late_fee, fine
    payment_method = db.Column(db.String(50), nullable=True)  # cash, online, card
    transaction_id = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='pending', index=True)  # pending, verified, failed
    due_date = db.Column(db.Date, nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    # Relationships
    user = db.relationship('User', backref='payments')
    apartment = db.relationship('Apartment', backref='payments')
    
    __table_args__ = (
        db.Index('idx_payments_society_status', 'society_id', 'status'),
        db.Index('idx_payments_user', 'user_id'),
        db.Index('idx_payments_due_date', 'due_date'),
    )
    
    def verify(self):
        """Mark payment as verified"""
        self.status = 'verified'
        self.paid_at = datetime.now()
        
        # Create corresponding transaction
        from app.models.transaction import Transaction
        transaction = Transaction(
            society_id=self.society_id,
            trx_date=self.paid_at.date(),
            acc_id=1,  # Cash/Bank account
            entity_id=self.user_id,
            acc_particulars=f'Payment received from {self.user.email if self.user else "Unknown"}',
            amount=self.amount,
            mode='online' if self.payment_method == 'online' else 'cash',
            status='paid'
        )
        db.session.add(transaction)
    
    def __repr__(self):
        return f'<Payment {self.id}: {self.amount}>'