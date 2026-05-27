# app/models/base.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

db = SQLAlchemy()

class BaseModel(DeclarativeBase):
    __abstract__ = True

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, nullable=True)
    updated_by = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, default=True)

    def save(self, session=None):
        if session is None:
            session = db.session
        session.add(self)
        session.commit()
        return self

    def soft_delete(self, session=None):
        self.is_active = False
        return self.save(session)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}