from app import db

class Apartment(db.Model):
    __tablename__ = 'apartments'
    
    id = db.Column(db.Integer, primary_key=True)
    society_id = db.Column(db.Integer, db.ForeignKey('societies.id', ondelete='CASCADE'), nullable=False, index=True)
    flat_number = db.Column(db.String(20), nullable=False)
    owner_name = db.Column(db.String(100), nullable=True)
    mobile = db.Column(db.String(15), nullable=True)
    apartment_size = db.Column(db.Integer, nullable=False)  # in sq ft
    active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    # Index for faster lookups
    __table_args__ = (
        db.Index('idx_apartments_society_flat', 'society_id', 'flat_number'),
        db.UniqueConstraint('society_id', 'flat_number', name='uq_apartment_society_flat'),
    )
    
    @property
    def maintenance_rate(self):
        """Get current maintenance rate for this apartment"""
        from app.services.maintenance_service import get_current_maintenance_rate
        return get_current_maintenance_rate(self.society_id)
    
    @property
    def monthly_maintenance(self):
        """Calculate monthly maintenance amount"""
        return self.apartment_size * (self.maintenance_rate or 0)
    
    def __repr__(self):
        return f'<Apartment {self.flat_number}>'