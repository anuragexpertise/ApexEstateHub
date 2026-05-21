-- ============================================================
-- EsateHub  --  Unified Database Schema (Aiven PostgreSQL)
-- Run via:  python3 database/migrate.py
-- ============================================================
-- All CREATE TABLE, ALTER TABLE, and INDEX statements merged
-- Safe to re-run on existing databases (uses IF NOT EXISTS)
-- ============================================================

-- ════════════════════════════════════════════════════════════════════════════
-- CORE TABLES
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS societies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    logo VARCHAR(100),
    address TEXT,
    email VARCHAR(100),
    phone VARCHAR(20),
    secretary_name VARCHAR(100),
    secretary_phone VARCHAR(20),
    secretary_sign VARCHAR(100),
    plan VARCHAR(4) NOT NULL DEFAULT 'Free' CHECK (plan IN ('Free', 'Paid')),
    plan_validity DATE NOT NULL DEFAULT CURRENT_DATE,
    arrear_start_date DATE NOT NULL DEFAULT CURRENT_DATE,
    login_background VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    pin_hash TEXT,
    pattern_hash TEXT,
    role VARCHAR(20) NOT NULL CHECK (
        role IN (
            'admin',
            'apartment',
            'vendor',
            'security'
        )
    ),
    linked_id INT,
    login_method VARCHAR(20) DEFAULT 'password',
    push_subscription TEXT,
    is_master_admin BOOLEAN NOT NULL DEFAULT FALSE,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMP,
    reset_token VARCHAR(64),
    reset_token_expires TIMESTAMP,
    push_token TEXT,
    push_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    last_login TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS apartments (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    flat_number VARCHAR(20) NOT NULL,
    owner_name VARCHAR(100),
    mobile VARCHAR(15),
    apartment_size INT NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_apartment_society_flat UNIQUE (society_id, flat_number)
);

CREATE TABLE IF NOT EXISTS vendors (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    service_type VARCHAR(100),
    mobile VARCHAR(15),
    service_description TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS security_staff (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    mobile VARCHAR(15),
    joining_date DATE DEFAULT CURRENT_DATE,
    shift VARCHAR(20),
    salary_per_shift NUMERIC(10, 2),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- ════════════════════════════════════════════════════════════════════════════
-- PAYMENTS TABLE UPDATE - Auto-calculated Debits (pending payables)
-- ════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id),
    entity_id INT,
    entity_type VARCHAR(20) CHECK (entity_type IN ('apartment', 'vendor', 'security', 'other')),
    amount NUMERIC(10, 2) NOT NULL,
    payment_type VARCHAR(50),
    payment_method VARCHAR(50),
    transaction_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    due_date DATE,
    paid_at TIMESTAMP,
    source_table VARCHAR(50),
    source_id INT,
    confirmed_by INT REFERENCES users (id),
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT payments_status_check 
        CHECK (status IN ('pending', 'confirmed', 'verified', 'failed', 'cancelled')),
);

CREATE TABLE IF NOT EXISTS attendance (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    security_id INT NOT NULL REFERENCES security_staff (id) ON DELETE CASCADE,
    time_in TIMESTAMP,
    time_out TIMESTAMP
);

CREATE TABLE IF NOT EXISTS apt_charges_fines (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    apt_id INT NOT NULL REFERENCES apartments (id) ON DELETE CASCADE,
    start_date DATE,
    end_date DATE,
    apt_maintenance_rate FLOAT,
    apt_due_day INTEGER DEFAULT 0,
    apt_delay_fine DECIMAL(10, 2) DEFAULT 0,
    apt_fine DECIMAL(10, 2) DEFAULT 0,
    apt_status BOOLEAN
);

CREATE TABLE IF NOT EXISTS ven_charges_fines (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    ven_id INT NOT NULL REFERENCES vendors (id) ON DELETE CASCADE,
    start_date DATE,
    end_date DATE,
    vendor_1day DECIMAL(10, 2) DEFAULT 0,
    vendor_7day DECIMAL(10, 2) DEFAULT 0,
    vendor_1mth DECIMAL(10, 2) DEFAULT 0,
    vendor_fine DECIMAL(10, 2) DEFAULT 0,
    ven_status BOOLEAN
);

CREATE TABLE IF NOT EXISTS security_charges_fines (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    sec_id INT NOT NULL REFERENCES security_staff (id) ON DELETE CASCADE,
    start_date DATE,
    end_date DATE,
    security_fine DECIMAL(10, 2) DEFAULT 0,
    sec_status BOOLEAN
);

CREATE TABLE IF NOT EXISTS gate_access (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    role VARCHAR(1),
    entity_id INTEGER NOT NULL,
    time_in TIMESTAMP NOT NULL DEFAULT NOW(),
    time_out TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- ACCOUNTING TABLES
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS accounts (
    id INT PRIMARY KEY NOT NULL,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    tab_name VARCHAR(20),
    header VARCHAR(50),
    parent_account_id INT NOT NULL REFERENCES accounts (id) DEFAULT 1,
    drcr_account VARCHAR(2) CHECK (drcr_account IN ('Dr', 'Cr')),
    has_bf BOOLEAN DEFAULT FALSE,
    drcr_bf VARCHAR(2) CHECK (drcr_bf IN ('Dr', 'Cr')) NOT NULL,
    bf_amount DECIMAL(12, 2) DEFAULT 0.00,
    depreciation_percent DECIMAL(5, 2) DEFAULT 100.00,
    is_depreciable BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_account_society_name UNIQUE (society_id, name)
);

CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    trx_date DATE NOT NULL,
    acc_id INT REFERENCES accounts (id),
    entity_id INTEGER,
    acc_particulars VARCHAR(100),
    amount DECIMAL(15, 2) NOT NULL CHECK (amount > 0),
    mode VARCHAR(6) CHECK (
        mode IN (
            'cash',
            'cheque',
            'upi',
            'card',
            'bank',
            'crypto'
        )
    ) DEFAULT 'cash',
    payment_gateway_ID VARCHAR(20),
    status VARCHAR(20) NOT NULL DEFAULT 'paid',
    created_by INTEGER REFERENCES users (id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS asset_register (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    asset_name VARCHAR(20),
    purchase_value DECIMAL(12, 2),
    purchase_date DATE,
    parent_account_id INT REFERENCES accounts (id),
    last_depreciation_date DATE
);

CREATE TABLE IF NOT EXISTS receivables (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id),  -- Admin who confirmed
    entity_id INT NOT NULL,  -- apartment_id or vendor_id or security_id
    entity_type VARCHAR(20) NOT NULL CHECK (entity_type IN ('apartment', 'vendor', 'security')),
    
    -- Charge details
    charge_type VARCHAR(50) NOT NULL,  -- 'maintenance', 'fine', 'late_fee', etc.
    description TEXT,
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    
    -- Due date tracking
    due_date DATE,
    
    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'cancelled')),
    
    -- Reference to charge source
    source_table VARCHAR(50),  -- 'apt_charges_fines', 'ven_charges_fines', etc.
    source_id INT,  -- ID in source table
    
    -- Audit
    confirmed_by INT REFERENCES users (id),
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    CONSTRAINT fk_receivables_society FOREIGN KEY (society_id) REFERENCES societies(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_receivables_society_status ON receivables (society_id, status);
CREATE INDEX IF NOT EXISTS idx_receivables_entity ON receivables (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_receivables_due_date ON receivables (due_date);

-- ════════════════════════════════════════════════════════════════════════════
-- RECEIPTS TABLE - Manually added Credits (manually recorded income)
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS receipts (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id),  -- Who created the receipt
    entity_id INT,  -- Optional: apartment_id or vendor_id or security_id
    entity_type VARCHAR(20) CHECK (entity_type IN ('apartment', 'vendor', 'security', 'other')),
    
    -- Receipt details
    receipt_date DATE NOT NULL,
    acc_id INT REFERENCES accounts (id),  -- Link to chart of accounts
    particulars TEXT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    
    -- Payment mode
    mode VARCHAR(20) DEFAULT 'cash' CHECK (mode IN ('cash', 'cheque', 'upi', 'card', 'bank', 'crypto')),
    cheque_no VARCHAR(50),
    transaction_id VARCHAR(255),
    
    -- Status (needs admin confirmation)
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'cancelled')),
    
    -- Audit
    confirmed_by INT REFERENCES users (id),  -- Must be admin
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    CONSTRAINT fk_receipts_society FOREIGN KEY (society_id) REFERENCES societies(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_receipts_society_status ON receipts (society_id, status);
CREATE INDEX IF NOT EXISTS idx_receipts_date ON receipts (receipt_date);
CREATE INDEX IF NOT EXISTS idx_receipts_entity ON receipts (entity_type, entity_id);



-- ════════════════════════════════════════════════════════════════════════════
-- EXPENSES TABLE - Manually added Debits (manually recorded expenses)
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id),  -- Who created the expense
    entity_id INT,  -- Optional: vendor_id or security_id (payee)
    entity_type VARCHAR(20) CHECK (entity_type IN ('vendor', 'security', 'other')),
    
    -- Expense details
    expense_date DATE NOT NULL,
    acc_id INT REFERENCES accounts (id),  -- Link to chart of accounts
    particulars TEXT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    
    -- Payment mode
    mode VARCHAR(20) DEFAULT 'cash' CHECK (mode IN ('cash', 'cheque', 'upi', 'card', 'bank', 'crypto')),
    cheque_no VARCHAR(50),
    transaction_id VARCHAR(255),
    
    -- Status (needs admin confirmation)
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'cancelled')),
    
    -- Audit
    confirmed_by INT REFERENCES users (id),  -- Must be admin
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    CONSTRAINT fk_expenses_society FOREIGN KEY (society_id) REFERENCES societies(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_expenses_society_status ON expenses (society_id, status);
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses (expense_date);
CREATE INDEX IF NOT EXISTS idx_expenses_entity ON expenses (entity_type, entity_id);
-- ════════════════════════════════════════════════════════════════════════════
-- FEATURE TABLES
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS society_settings (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    key VARCHAR(60) NOT NULL,
    value TEXT,
    UNIQUE (society_id, key)
);

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    event_date DATE NOT NULL,
    event_time VARCHAR(20),
    venue VARCHAR(200),
    open_to VARCHAR(20) DEFAULT 'all',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS concerns (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    flat_no VARCHAR(20),
    concern_type VARCHAR(50),
    description TEXT,
    preferred_time VARCHAR(20),
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    assigned_to VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS charges (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    charge_type VARCHAR(30),
    amount NUMERIC(10, 2),
    applies_to VARCHAR(20) DEFAULT 'all',
    frequency VARCHAR(20) DEFAULT 'monthly',
    due_day INTEGER DEFAULT 15,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS vendor_passes (
    id SERIAL PRIMARY KEY,
    society_id INTEGER NOT NULL REFERENCES societies (id),
    user_id INTEGER NOT NULL REFERENCES users (id),
    pass_type VARCHAR(50) DEFAULT 'temporary',
    issued_date DATE DEFAULT CURRENT_DATE,
    valid_until DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (
        society_id,
        user_id,
        issued_date
    )
);

-- ════════════════════════════════════════════════════════════════════════════
-- INDEXES
-- ════════════════════════════════════════════════════════════════════════════

-- Users indexes
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

CREATE INDEX IF NOT EXISTS idx_users_society_role ON users (society_id, role);

CREATE INDEX IF NOT EXISTS idx_users_linked ON users (linked_id);

CREATE INDEX IF NOT EXISTS idx_users_reset_token ON users (reset_token);

CREATE INDEX IF NOT EXISTS idx_users_reset_token_expires ON users (reset_token_expires);

CREATE INDEX IF NOT EXISTS idx_users_locked_until ON users (locked_until);

CREATE INDEX IF NOT EXISTS idx_users_login_method ON users (login_method);

CREATE INDEX IF NOT EXISTS idx_users_master_admin ON users (is_master_admin)
WHERE
    is_master_admin = TRUE;

-- Apartments indexes
CREATE INDEX IF NOT EXISTS idx_apartments_society ON apartments (society_id);

CREATE INDEX IF NOT EXISTS idx_apartments_active ON apartments (society_id, active);

-- Vendors indexes
CREATE INDEX IF NOT EXISTS idx_vendors_society_active ON vendors (society_id, active);

-- Security indexes
CREATE INDEX IF NOT EXISTS idx_security_society_active ON security_staff (society_id, active);

-- Accounting indexes
CREATE INDEX IF NOT EXISTS idx_accounts_society ON accounts (society_id);

CREATE INDEX IF NOT EXISTS idx_accounts_tab ON accounts (society_id, tab_name);

CREATE INDEX IF NOT EXISTS idx_accounts_parent_account_id ON accounts (society_id, parent_account_id);

-- Transaction indexes
CREATE INDEX IF NOT EXISTS idx_transactions_society_date ON transactions (society_id, trx_date DESC);

CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions (acc_id);

CREATE INDEX IF NOT EXISTS idx_transactions_entity ON transactions (entity_id);

CREATE INDEX IF NOT EXISTS idx_trx_society_date ON transactions (society_id, trx_date);

CREATE INDEX IF NOT EXISTS idx_trx_account ON transactions (acc_id);

CREATE INDEX IF NOT EXISTS idx_trx_entity ON transactions (entity_id);

CREATE INDEX IF NOT EXISTS idx_trx_status ON transactions (status);

CREATE INDEX IF NOT EXISTS idx_trx_society_status_date ON transactions (society_id, status, trx_date);

CREATE INDEX IF NOT EXISTS idx_trx_paid_only ON transactions (society_id, trx_date)
WHERE
    status = 'paid';

-- Gate access indexes
CREATE INDEX IF NOT EXISTS idx_gate_society_time ON gate_access (society_id, time_in);

CREATE INDEX IF NOT EXISTS idx_gate_entity ON gate_access (role, entity_id);

CREATE INDEX IF NOT EXISTS idx_gate_open_entries ON gate_access (role, entity_id, time_out);

-- Attendance indexes
CREATE INDEX IF NOT EXISTS idx_attendance_security ON attendance (security_id);

CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance (society_id, time_in);

-- Asset register indexes
CREATE INDEX IF NOT EXISTS idx_asset_society ON asset_register (society_id);

CREATE INDEX IF NOT EXISTS idx_asset_account ON asset_register (parent_account_id);

-- Payment indexes
CREATE INDEX IF NOT EXISTS idx_payments_society_status ON payments (society_id, status);

CREATE INDEX IF NOT EXISTS idx_payments_user ON payments (user_id);

CREATE INDEX IF NOT EXISTS idx_payments_due_date ON payments (due_date);

-- Event indexes
CREATE INDEX IF NOT EXISTS idx_events_society_date ON events (society_id, event_date);

-- Concern indexes
CREATE INDEX IF NOT EXISTS idx_concerns_society_status ON concerns (society_id, status);

-- Vendor pass indexes
CREATE INDEX IF NOT EXISTS idx_vendor_passes_active ON vendor_passes (
    society_id,
    user_id,
    valid_until
)
WHERE
    status = 'active';

-- ════════════════════════════════════════════════════════════════════════════
-- DATA PATCHES (Safe to re-run)
-- ════════════════════════════════════════════════════════════════════════════

-- Mark existing master admin user
DO $$ BEGIN IF EXISTS (
    SELECT 1
    FROM users
    WHERE
        email = 'master@estatehub.com'
        AND society_id IS NULL
) THEN
UPDATE users
SET
    is_master_admin = TRUE
WHERE
    email = 'master@estatehub.com'
    AND society_id IS NULL
    AND is_master_admin = FALSE;

END IF;

END $$;
