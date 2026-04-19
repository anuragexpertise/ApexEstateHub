from app import db
from datetime import datetime

class GateAccess(db.Model):
    __tablename__ = 'gate_access'
    
    id = db.Column(db.Integer, primary_key=True)
    society_id = db.Column(db.Integer, db.ForeignKey('societies.id', ondelete='CASCADE'), nullable=False, index=True)
    role = db.Column(db.String(1), nullable=True)
    entity_id = db.Column(db.Integer, nullable=False, index=True)
    time_in = db.Column(db.DateTime, server_default=db.func.now(), index=True)
    time_out = db.Column(db.DateTime, nullable=True)
    
    __table_args__ = (
        db.Index('idx_gate_entity', 'role', 'entity_id'),
        db.Index('idx_gate_open_entries', 'role', 'entity_id', 'time_out'),
    )
    
    def check_out(self):
        self.time_out = datetime.now()
    
    @property
    def duration(self):
        if self.time_out:
            return (self.time_out - self.time_in).total_seconds() / 3600
        return None