-- ============================================================
-- ApexEstateHub  --  Database Schema  (Aiven PostgreSQL)
-- Run via:  python3 database/migrate.py
-- ============================================================

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

CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id),
    apartment_id INT REFERENCES apartments (id),
    amount NUMERIC(10, 2) NOT NULL,
    payment_type VARCHAR(50),
    payment_method VARCHAR(50),
    transaction_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    due_date DATE,
    paid_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
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

CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    name VARCHAR(20) NOT NULL,
    tab_name VARCHAR(10),
    header VARCHAR(50),
    parent_account_id INT NOT NULL REFERENCES accounts (id) DEFAULT 1,
    drcr_account VARCHAR(2) CHECK (drcr_account IN ('Dr', 'Cr')) NOT NULL,
    has_bf BOOLEAN DEFAULT FALSE,
    drcr_bf VARCHAR(2) CHECK (drcr_bf IN ('Dr', 'Cr')) NOT NULL,
    bf_amount DECIMAL(12, 2) DEFAULT 0.00,
    depreciation_percent DECIMAL(5, 2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_account_society_name UNIQUE (society_id, name),
    CONSTRAINT uq_account_society_id UNIQUE (society_id, id)
);
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    trx_date DATE NOT NULL,
    acc_id INT REFERENCES accounts (id),
    entity_id INTEGER,
    acc_particulars VARCHAR(100),
    amount DECIMAL(15, 2) NOT NULL,
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
    payment_gateway_ID VARCHAR(20), -- For online payments
    status VARCHAR(20) NOT NULL DEFAULT 'paid', -- 'pending', 'paid', 'cancelled'
    created_by INTEGER REFERENCES users (id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW() CHECK (amount > 0)
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

-- ── Indexes ───────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_vendor_passes_active ON vendor_passes (
    society_id,
    user_id,
    valid_until
)
WHERE
    status = 'active';

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

CREATE INDEX IF NOT EXISTS idx_users_society_role ON users (society_id, role);

CREATE INDEX IF NOT EXISTS idx_users_linked ON users (linked_id);

CREATE INDEX IF NOT EXISTS idx_apartments_society ON apartments (society_id);

CREATE INDEX IF NOT EXISTS idx_apartments_active ON apartments (society_id, active);

CREATE INDEX IF NOT EXISTS idx_vendors_society_active ON vendors (society_id, active);

CREATE INDEX IF NOT EXISTS idx_security_society_active ON security_staff (society_id, active);

CREATE INDEX IF NOT EXISTS idx_trx_society_date ON transactions (society_id, trx_date);

CREATE INDEX IF NOT EXISTS idx_trx_account ON transactions (acc_id);

CREATE INDEX IF NOT EXISTS idx_trx_entity ON transactions (entity_id);

CREATE INDEX IF NOT EXISTS idx_trx_status ON transactions (status);

CREATE INDEX IF NOT EXISTS idx_trx_society_status_date ON transactions (society_id, status, trx_date);

CREATE INDEX IF NOT EXISTS idx_trx_paid_only ON transactions (society_id, trx_date)
WHERE
    status = 'paid';

CREATE INDEX IF NOT EXISTS idx_gate_society_time ON gate_access (society_id, time_in);

CREATE INDEX IF NOT EXISTS idx_gate_entity ON gate_access (role, entity_id);

CREATE INDEX IF NOT EXISTS idx_gate_open_entries ON gate_access (role, entity_id, time_out);

CREATE INDEX IF NOT EXISTS idx_attendance_security ON attendance (security_id);

CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance (society_id, time_in);

CREATE INDEX IF NOT EXISTS idx_asset_society ON asset_register (society_id);

CREATE INDEX IF NOT EXISTS idx_asset_account ON asset_register (parent_account_id);

CREATE INDEX IF NOT EXISTS idx_payments_society_status ON payments (society_id, status);

CREATE INDEX IF NOT EXISTS idx_payments_user ON payments (user_id);

CREATE INDEX IF NOT EXISTS idx_payments_due_date ON payments (due_date);

CREATE INDEX IF NOT EXISTS idx_events_society_date ON events (society_id, event_date);

CREATE INDEX IF NOT EXISTS idx_concerns_society_status ON concerns (society_id, status);

-- ── Additive patches for existing installs ────────────────────────────────────
-- All statements below use IF NOT EXISTS / safe forms so they are safe to
-- re-run on any existing database without side-effects.

ALTER TABLE users
ADD COLUMN IF NOT EXISTS is_master_admin BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE users
ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER NOT NULL DEFAULT 0;

ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP;

ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token VARCHAR(64);

ALTER TABLE users
ADD COLUMN IF NOT EXISTS reset_token_expires TIMESTAMP;

ALTER TABLE users ADD COLUMN IF NOT EXISTS push_token TEXT;

ALTER TABLE users
ADD COLUMN IF NOT EXISTS push_enabled BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMP;

-- Indexes that depend on the columns added above (must come after ALTER TABLE).
CREATE INDEX IF NOT EXISTS idx_users_reset_token ON users (reset_token);

CREATE INDEX IF NOT EXISTS idx_users_reset_token_expires ON users (reset_token_expires);

CREATE INDEX IF NOT EXISTS idx_users_locked_until ON users (locked_until);

CREATE INDEX IF NOT EXISTS idx_users_login_method ON users (login_method);

CREATE INDEX IF NOT EXISTS idx_users_master_admin ON users (is_master_admin)
WHERE
    is_master_admin = TRUE;

-- Fix accounts UNIQUE constraint: old schema used a global UNIQUE on name;
-- correct is per-society. DROP IF EXISTS is safe on PostgreSQL 9.4+.
ALTER TABLE accounts DROP CONSTRAINT IF EXISTS accounts_name_key;
-- Mark the existing master admin user so login_callbacks can find it.
UPDATE users
SET
    is_master_admin = TRUE
WHERE
    email = 'master@estatehub.com'
    AND society_id IS NULL
    AND is_master_admin = FALSE;