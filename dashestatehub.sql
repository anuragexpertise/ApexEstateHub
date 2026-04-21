CREATE TABLE societies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    logo VARCHAR(100),
    address TEXT,
    email VARCHAR(100),
    phone VARCHAR(20),
    secretary_name VARCHAR(100),
    secretary_phone VARCHAR(20),
    secretary_sign VARCHAR(100),
    plan VARCHAR(4) CHECK (plan IN ('Free', 'Paid')) DEFAULT 'Free' NOT NULL,
    plan_validity DATE NOT NULL,
    arrear_start_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    login_background VARCHAR(100)
);

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    pin_hash TEXT,
    pattern_hash TEXT,
    role VARCHAR(20) CHECK (
        role IN (
            'admin',
            'apartment',
            'vendor',
            'security'
        )
    ) NOT NULL,
    linked_id INT, -- apartment_id / vendor_id / etc
    login_method VARCHAR(20) DEFAULT 'pin',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE apartments (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    flat_number VARCHAR(20) NOT NULL,
    owner_name VARCHAR(100),
    mobile VARCHAR(15),
    apartment_size INT NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE vendors (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    service_type VARCHAR(100),
    mobile VARCHAR(15),
    service_description TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE security_staff (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    mobile VARCHAR(15),
    joining_date TIMESTAMP DEFAULT CURRENT_DATE,
    shift VARCHAR(20),
    salary_per_shift NUMERIC(10, 2),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE attendance (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    security_id INT REFERENCES security_staff (id) ON DELETE CASCADE,
    time_in TIMESTAMP,
    time_out TIMESTAMP
);

CREATE TABLE apt_charges_fines (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    apt_id INT REFERENCES apartments (id) ON DELETE CASCADE,
    start_date DATE,
    end_date DATE,
    apt_maintenance_rate FLOAT, -- Rs per sqft
    apt_due_day INTEGER DEFAULT 0,
    apt_delay_fine DECIMAL(10, 2) DEFAULT 0, -- Rs/day
    apt_fine DECIMAL(10, 2) DEFAULT 0,
    apt_status BOOLEAN
);

CREATE TABLE ven_charges_fines (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    ven_id INT REFERENCES vendors (id) ON DELETE CASCADE,
    start_date DATE,
    end_date DATE,
    vendor_1day DECIMAL(10, 2) DEFAULT 0,
    vendor_7day DECIMAL(10, 2) DEFAULT 0,
    vendor_1mth DECIMAL(10, 2) DEFAULT 0,
    vendor_fine DECIMAL(10, 2) DEFAULT 0,
    ven_status BOOLEAN
);

CREATE TABLE security_charges_fines (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    sec_id INT REFERENCES security_staff (id) ON DELETE CASCADE,
    start_date DATE,
    end_date DATE,
    security_fine DECIMAL(10, 2) DEFAULT 0,
    sec_status BOOLEAN
);

CREATE TABLE gate_access (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    role VARCHAR(1),
    entity_id INTEGER,
    time_in TIMESTAMP DEFAULT NOW(),
    time_out TIMESTAMP NULL
);

CREATE TABLE accounts (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    name VARCHAR(10) NOT NULL UNIQUE,
    tab_name VARCHAR(100),
    header VARCHAR(255),
    parent_account_id VARCHAR(10),
    drcr_account VARCHAR(2) CHECK (drcr_account IN ('Dr', 'Cr')),
    has_bf BOOLEAN DEFAULT FALSE,
    bf_type VARCHAR(2) CHECK (bf_type IN ('Dr', 'Cr')),
    bf_amount DECIMAL(12, 2),
    depreciation_percent FLOAT DEFAULT 0,
    is_depreciable BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    trx_date DATE,
    acc_id INT REFERENCES accounts (id),
    entity_id INTEGER,
    acc_Particulars VARCHAR(100),
    amount NUMERIC(10, 2) NOT NULL,
    mode VARCHAR(6) CHECK (
        mode IN ('cash', 'online', 'other')
    ),
    status VARCHAR(20) DEFAULT 'paid',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE asset_register (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    asset_name VARCHAR(20),
    purchase_value DECIMAL(12, 2),
    purchase_date DATE,
    parent_account_id INT REFERENCES accounts (id),
    last_depreciation_date DATE
);

CREATE TABLE IF NOT EXISTS society_settings (
    id         SERIAL PRIMARY KEY,
    society_id INTEGER NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    key        VARCHAR(60) NOT NULL,
    value      TEXT,
    UNIQUE(society_id, key)
);

CREATE INDEX idx_users_email ON users (email);

CREATE INDEX idx_users_society_role ON users (society_id, role);

CREATE INDEX idx_users_linked ON users (linked_id);

CREATE INDEX idx_apartments_society ON apartments (society_id);

CREATE INDEX idx_apartments_active ON apartments (society_id, active);

CREATE INDEX idx_apartments_flat ON apartments (society_id, flat_number);

CREATE INDEX idx_vendors_society_active ON vendors (society_id, active);

CREATE INDEX idx_vendors_service ON vendors (service_type);

CREATE INDEX idx_security_society_active ON security_staff (society_id, active);

CREATE INDEX idx_trx_society_date ON transactions (society_id, trx_date);

CREATE INDEX idx_trx_account ON transactions (acc_id);

CREATE INDEX idx_trx_entity ON transactions (entity_id);

CREATE INDEX idx_trx_status ON transactions (status);

CREATE INDEX idx_trx_society_status_date ON transactions (society_id, status, trx_date);

CREATE INDEX idx_gate_society_time ON gate_access (society_id, time_in);

CREATE INDEX idx_gate_entity ON gate_access (role, entity_id);

CREATE INDEX idx_gate_open_entries ON gate_access (role, entity_id, time_out);

CREATE INDEX idx_attendance_security ON attendance (security_id);

CREATE INDEX idx_attendance_date ON attendance (society_id, time_in);

CREATE INDEX idx_apt_charges_society ON apt_charges_fines (society_id, apt_id);

CREATE INDEX idx_apt_charges_date ON apt_charges_fines (start_date, end_date);

CREATE INDEX idx_ven_charges_society ON ven_charges_fines (society_id, ven_id);

CREATE INDEX idx_ven_charges_date ON ven_charges_fines (start_date, end_date);

CREATE INDEX idx_sec_charges_society ON security_charges_fines (society_id, sec_id);

CREATE INDEX idx_accounts_society ON accounts (society_id);

CREATE INDEX idx_accounts_parent ON accounts (parent_account_id);

CREATE INDEX idx_accounts_tab ON accounts (tab_name);

CREATE INDEX idx_asset_society ON asset_register (society_id);

CREATE INDEX idx_asset_account ON asset_register (parent_account_id);

CREATE INDEX idx_trx_paid_only ON transactions (society_id, trx_date)
WHERE
    status = 'paid';
