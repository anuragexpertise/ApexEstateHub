from app import db

class Transaction(db.Model):
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    society_id = db.Column(db.Integer, db.ForeignKey('societies.id', ondelete='CASCADE'), nullable=False, index=True)
    trx_date = db.Column(db.Date, nullable=False, index=True)
    acc_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True, index=True)
    acc_particulars = db.Column(db.String(100), nullable=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    mode = db.Column(db.String(6), nullable=True)  # cash, online, other
    status = db.Column(db.String(20), default='paid', index=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    __table_args__ = (
        db.Index('idx_trx_society_date', 'society_id', 'trx_date'),
        db.Index('idx_trx_society_status_date', 'society_id', 'status', 'trx_date'),
    )
    
    def __repr__(self):
        return f'<Transaction {self.id}>'

class Account(db.Model):
    __tablename__ = 'accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    society_id = db.Column(db.Integer, db.ForeignKey('societies.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(10), nullable=False, unique=True)
    tab_name = db.Column(db.String(100), nullable=True)
    header = db.Column(db.String(255), nullable=True)
    parent_account_id = db.Column(db.String(10), nullable=True, index=True)
    drcr_account = db.Column(db.String(2), nullable=True)  # Dr, Cr
    has_bf = db.Column(db.Boolean, default=False)
    bf_type = db.Column(db.String(2), nullable=True)  # Dr, Cr
    bf_amount = db.Column(db.Numeric(12, 2), nullable=True)
    depreciation_percent = db.Column(db.Float, default=0)
    is_depreciable = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    __table_args__ = (
        db.Index('idx_accounts_society_tab', 'society_id', 'tab_name'),
        db.Index('idx_accounts_parent', 'parent_account_id'),
    )