-- ============================================================
-- ESTATEHUB - FIXED DATABASE SCHEMA & FUNCTIONS
-- Production: Aiven PostgreSQL
-- FIXES APPLIED:
-- 1. Corrected RETURN TABLE type mismatches in list functions
-- 2. Fixed apartment/vendor/security profile functions
-- 3. Added KPI helper functions for customize tab
-- 4. Ensured all functions match expected columns
-- ============================================================

-- ════════════════════════════════════════════════════════════════
-- SECTION 1: CORE SCHEMA (unchanged)
-- ════════════════════════════════════════════════════════════════

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
    plan VARCHAR(20) NOT NULL DEFAULT 'Free' CHECK (plan IN ('Free', '9Apts', '99Apts', '999Apts', 'Unlimited')),
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
    name VARCHAR(100),
    role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'apartment', 'vendor', 'security')),
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
    owner_photo VARCHAR(255),
    id_proof VARCHAR(255),
    photo VARCHAR(255),
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
    logo VARCHAR(255),
    license VARCHAR(255),
    photo VARCHAR(255),
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
    photo VARCHAR(255),
    id_proof VARCHAR(255),
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
    entity_id INT,
    entity_type VARCHAR(20) CHECK (entity_type IN ('apartment', 'vendor', 'security', 'other')),
    amount NUMERIC(10, 2) NOT NULL,
    payment_type VARCHAR(50),
    payment_method VARCHAR(50),
    transaction_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'verified', 'failed', 'cancelled')),
    due_date DATE,
    paid_at TIMESTAMP,
    source_table VARCHAR(50),
    source_id INT,
    confirmed_by INT REFERENCES users (id),
    confirmed_at TIMESTAMP,
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
    start_date DATE NOT NULL,
    end_date DATE,
    apt_maintenance_rate NUMERIC(10, 4) NOT NULL DEFAULT 3.0,
    apt_due_day INTEGER DEFAULT 10,
    apt_delay_fine NUMERIC(10, 2) DEFAULT 0,
    apt_fine NUMERIC(10, 2) DEFAULT 0,
    apt_status BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ven_charges_fines (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    ven_id INT NOT NULL REFERENCES vendors (id) ON DELETE CASCADE,
    start_date DATE NOT NULL,
    end_date DATE,
    vendor_1day NUMERIC(10, 2) DEFAULT 0,
    vendor_7day NUMERIC(10, 2) DEFAULT 0,
    vendor_1mth NUMERIC(10, 2) DEFAULT 0,
    vendor_fine NUMERIC(10, 2) DEFAULT 0,
    ven_status BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS security_charges_fines (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    sec_id INT NOT NULL REFERENCES security_staff (id) ON DELETE CASCADE,
    start_date DATE NOT NULL,
    end_date DATE,
    security_fine NUMERIC(10, 2) DEFAULT 0,
    sec_status BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    name VARCHAR(100) NOT NULL,
    tab_name VARCHAR(20),
    header VARCHAR(50),
    parent_account_id INT,
    drcr_account VARCHAR(2) CHECK (drcr_account IN ('Dr', 'Cr', NULL)),
    has_bf BOOLEAN DEFAULT FALSE,
    drcr_bf VARCHAR(2) CHECK (drcr_bf IN ('Dr', 'Cr')) NOT NULL,
    bf_amount NUMERIC(12, 2) DEFAULT 0.00,
    depreciation_percent NUMERIC(5, 2) DEFAULT 100.00,
    is_depreciable BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_account_society_name UNIQUE (society_id, name),
    CONSTRAINT fk_account_parent FOREIGN KEY (parent_account_id) REFERENCES accounts (id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    trx_date DATE NOT NULL,
    acc_id INT REFERENCES accounts (id),
    entity_id INTEGER,
    acc_particulars VARCHAR(100),
    amount NUMERIC(15, 2) NOT NULL CHECK (amount > 0),
    mode VARCHAR(6) DEFAULT 'cash' CHECK (mode IN ('cash', 'cheque', 'upi', 'card', 'bank', 'crypto')),
    payment_gateway_ID VARCHAR(20),
    status VARCHAR(20) NOT NULL DEFAULT 'paid',
    created_by INTEGER REFERENCES users (id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS asset_register (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    asset_name VARCHAR(100),
    purchase_value NUMERIC(12, 2),
    purchase_date DATE,
    parent_account_id INT REFERENCES accounts (id),
    depreciation_rate NUMERIC(5, 2),
    last_depreciation_date DATE
);

CREATE TABLE IF NOT EXISTS receivables (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id),
    entity_id INT NOT NULL,
    entity_type VARCHAR(20) NOT NULL CHECK (entity_type IN ('apartment', 'vendor', 'security')),
    charge_type VARCHAR(50) NOT NULL,
    description TEXT,
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    due_date DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'cancelled')),
    source_table VARCHAR(50),
    source_id INT,
    confirmed_by INT REFERENCES users (id),
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS receipts (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id),
    entity_id INT,
    entity_type VARCHAR(20) CHECK (
        entity_type IN (
            'apartment',
            'vendor',
            'security',
            'other'
        )
    ),
    receipt_date DATE NOT NULL,
    acc_id INT REFERENCES accounts (id),
    particulars TEXT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    mode VARCHAR(20) DEFAULT 'cash' CHECK (
        mode IN (
            'cash',
            'cheque',
            'upi',
            'card',
            'bank',
            'crypto'
        )
    ),
    cheque_no VARCHAR(50),
    transaction_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (
        status IN (
            'pending',
            'confirmed',
            'cancelled'
        )
    ),
    confirmed_by INT REFERENCES users (id),
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id),
    entity_id INT,
    entity_type VARCHAR(20) CHECK (
        entity_type IN ('vendor', 'security', 'other','assets')
    ),
    expense_date DATE NOT NULL,
    acc_id INT REFERENCES accounts (id),
    particulars TEXT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    mode VARCHAR(20) DEFAULT 'cash' CHECK (
        mode IN (
            'cash',
            'cheque',
            'upi',
            'card',
            'bank',
            'crypto'
        )
    ),
    cheque_no VARCHAR(50),
    transaction_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (
        status IN (
            'pending',
            'confirmed',
            'cancelled'
        )
    ),
    confirmed_by INT REFERENCES users (id),
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
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

CREATE TABLE IF NOT EXISTS vendor_passes (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT NOT NULL REFERENCES users (id),
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

CREATE TABLE IF NOT EXISTS security_roster (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    security_id INT NOT NULL REFERENCES security_staff (id) ON DELETE CASCADE,
    roster_date DATE NOT NULL,
    shift_type VARCHAR(20) CHECK (
        shift_type IN ('morning', 'evening', 'night')
    ),
    assigned_by INT REFERENCES users (id),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (
        society_id,
        security_id,
        roster_date
    )
);

CREATE TABLE IF NOT EXISTS role_permissions (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    card_id VARCHAR(100) NOT NULL,
    permission VARCHAR(20) NOT NULL CHECK (
        permission IN (
            'view',
            'create',
            'edit',
            'delete'
        )
    ),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (
        society_id,
        role,
        card_id,
        permission
    )
);

-- ════════════════════════════════════════════════════════════════
-- SECTION 2: INDEXES (unchanged)
-- ════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_society_role ON users (society_id, role);
CREATE INDEX IF NOT EXISTS idx_apartments_society ON apartments (society_id);
CREATE INDEX IF NOT EXISTS idx_apartments_active ON apartments (society_id, active);
CREATE INDEX IF NOT EXISTS idx_vendors_society ON vendors (society_id);
CREATE INDEX IF NOT EXISTS idx_security_society ON security_staff (society_id);
CREATE INDEX IF NOT EXISTS idx_accounts_society ON accounts (society_id);
CREATE INDEX IF NOT EXISTS idx_transactions_society_date ON transactions (society_id, trx_date DESC);
CREATE INDEX IF NOT EXISTS idx_payments_society_status ON payments (society_id, status);

CREATE INDEX IF NOT EXISTS idx_receipts_society_status ON receipts (society_id, status);

CREATE INDEX IF NOT EXISTS idx_expenses_society_status ON expenses (society_id, status);

CREATE INDEX IF NOT EXISTS idx_receivables_society_status ON receivables (society_id, status);
CREATE INDEX IF NOT EXISTS idx_events_society_date ON events (society_id, event_date);
CREATE INDEX IF NOT EXISTS idx_concerns_society_status ON concerns (society_id, status);
CREATE INDEX IF NOT EXISTS idx_gate_society_time ON gate_access (society_id, time_in);

CREATE INDEX IF NOT EXISTS idx_security_roster_date ON security_roster (society_id, roster_date);

-- ════════════════════════════════════════════════════════════════
-- SECTION 3: FIXED BUSINESS LOGIC FUNCTIONS
-- ════════════════════════════════════════════════════════════════

-- ═══ APARTMENTS LIST (FIXED) ═══
DROP FUNCTION IF EXISTS fn_apartments_list CASCADE;

CREATE OR REPLACE FUNCTION fn_apartments_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT,
    flat_number VARCHAR,
    owner_name VARCHAR,
    mobile VARCHAR,
    apartment_size INT,
    active BOOLEAN,
    pending_dues NUMERIC
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    WITH apt_dues AS (
        SELECT 
            a.id,
            a.flat_number,
            a.owner_name,
            a.mobile,
            a.apartment_size,
            a.active,
            COALESCE(SUM(CASE WHEN p.status IN ('pending', 'confirmed') THEN p.amount ELSE 0 END), 0) AS pending_dues
        FROM apartments a
        LEFT JOIN payments p ON p.entity_id = a.id AND p.entity_type = 'apartment' AND p.society_id = p_society_id
        WHERE a.society_id = p_society_id
          AND (p_search IS NULL OR a.flat_number ILIKE '%'||p_search||'%' OR a.owner_name ILIKE '%'||p_search||'%')
        GROUP BY a.id, a.flat_number, a.owner_name, a.mobile, a.apartment_size, a.active
    )
    SELECT * FROM apt_dues ORDER BY flat_number;
END;
$$;

-- ═══ APARTMENT PROFILE (FIXED) ═══
DROP FUNCTION IF EXISTS fn_apartment_profile CASCADE;

CREATE OR REPLACE FUNCTION fn_apartment_profile(p_apartment_id INT)
RETURNS TABLE (
    id INT,
    society_id INT,
    flat_number VARCHAR,
    owner_name VARCHAR,
    mobile VARCHAR,
    apartment_size INT,
    active BOOLEAN,
    pending_dues NUMERIC,
    created_at TIMESTAMP,
    _image_society_id INT
)
LANGUAGE SQL STABLE AS $$
    SELECT 
        a.id,
        a.society_id,
        a.flat_number,
        a.owner_name,
        a.mobile,
        a.apartment_size,
        a.active,
        COALESCE(SUM(CASE WHEN p.status IN ('pending', 'confirmed') THEN p.amount ELSE 0 END), 0),
        a.created_at,
        a.society_id
    FROM apartments a
    LEFT JOIN payments p ON p.entity_id = a.id AND p.entity_type = 'apartment'
    WHERE a.id = p_apartment_id
    GROUP BY a.id, a.society_id, a.flat_number, a.owner_name, a.mobile, a.apartment_size, a.active, a.created_at;
$$;

-- ═══ VENDORS LIST (FIXED) ═══
DROP FUNCTION IF EXISTS fn_vendors_list CASCADE;

CREATE OR REPLACE FUNCTION fn_vendors_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT,
    email VARCHAR,
    society_id INT,
    name TEXT,
    service_type VARCHAR,
    mobile VARCHAR,
    active BOOLEAN,
    pending_dues NUMERIC
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    WITH vendor_dues AS (
        SELECT 
            u.id,
            u.email,
            u.society_id,
            COALESCE(v.name, u.email)::TEXT AS name,
            COALESCE(v.service_type, '—')::VARCHAR AS service_type,
            COALESCE(v.mobile, '—')::VARCHAR AS mobile,
            COALESCE(v.active, TRUE) AS active,
            COALESCE(SUM(CASE WHEN p.status IN ('pending', 'confirmed') THEN p.amount ELSE 0 END), 0) AS pending_dues
        FROM users u
        LEFT JOIN vendors v ON v.id = u.linked_id
        LEFT JOIN payments p ON p.user_id = u.id AND p.entity_type = 'vendor' AND p.society_id = p_society_id
        WHERE u.society_id = p_society_id
          AND u.role = 'vendor'
          AND (p_search IS NULL OR v.name ILIKE '%'||p_search||'%' OR u.email ILIKE '%'||p_search||'%')
        GROUP BY u.id, u.email, u.society_id, v.name, v.service_type, v.mobile, v.active
    )
    SELECT * FROM vendor_dues ORDER BY name;
END;
$$;

-- ═══ VENDOR PROFILE (FIXED) ═══
DROP FUNCTION IF EXISTS fn_vendor_profile CASCADE;

CREATE OR REPLACE FUNCTION fn_vendor_profile(p_vendor_id INT)
RETURNS TABLE (
    id INT,
    email VARCHAR,
    society_id INT,
    name VARCHAR,
    service_type VARCHAR,
    mobile VARCHAR,
    active BOOLEAN,
    pending_dues NUMERIC,
    created_at TIMESTAMP,
    _image_society_id INT
)
LANGUAGE SQL STABLE AS $$
    SELECT 
        u.id,
        u.email,
        u.society_id,
        COALESCE(v.name, u.email)::VARCHAR,
        COALESCE(v.service_type, '—')::VARCHAR,
        COALESCE(v.mobile, '—')::VARCHAR,
        COALESCE(v.active, TRUE),
        COALESCE(SUM(CASE WHEN p.status IN ('pending', 'confirmed') THEN p.amount ELSE 0 END), 0),
        v.created_at,
        u.society_id
    FROM users u
    LEFT JOIN vendors v ON v.id = u.linked_id
    LEFT JOIN payments p ON p.user_id = u.id AND p.entity_type = 'vendor'
    WHERE u.id = p_vendor_id AND u.role = 'vendor'
    GROUP BY u.id, u.email, u.society_id, v.id, v.name, v.service_type, v.mobile, v.active, v.created_at;
$$;

-- ═══ SECURITY STAFF LIST (FIXED) ═══
DROP FUNCTION IF EXISTS fn_security_list CASCADE;

CREATE OR REPLACE FUNCTION fn_security_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT,
    email VARCHAR,
    society_id INT,
    name TEXT,
    shift VARCHAR,
    mobile VARCHAR,
    active BOOLEAN,
    salary_per_shift NUMERIC,
    joining_date DATE
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT 
        u.id,
        u.email,
        u.society_id,
        COALESCE(s.name, u.email)::TEXT,
        COALESCE(s.shift, '—')::VARCHAR,
        COALESCE(s.mobile, '—')::VARCHAR,
        COALESCE(s.active, TRUE),
        s.salary_per_shift,
        s.joining_date
    FROM users u
    LEFT JOIN security_staff s ON s.id = u.linked_id
    WHERE u.society_id = p_society_id
      AND u.role = 'security'
      AND (p_search IS NULL OR s.name ILIKE '%'||p_search||'%')
    ORDER BY s.name;
END;
$$;

-- ═══ SECURITY PROFILE (FIXED) ═══
DROP FUNCTION IF EXISTS fn_security_profile CASCADE;

CREATE OR REPLACE FUNCTION fn_security_profile(p_security_id INT)
RETURNS TABLE (
    id INT,
    email VARCHAR,
    society_id INT,
    name VARCHAR,
    shift VARCHAR,
    mobile VARCHAR,
    active BOOLEAN,
    joining_date DATE,
    created_at TIMESTAMP,
    _image_society_id INT
)
LANGUAGE SQL STABLE AS $$
    SELECT 
        u.id,
        u.email,
        u.society_id,
        COALESCE(s.name, u.email)::VARCHAR,
        COALESCE(s.shift, '—')::VARCHAR,
        COALESCE(s.mobile, '—')::VARCHAR,
        COALESCE(s.active, TRUE),
        s.joining_date,
        s.created_at,
        u.society_id
    FROM users u
    LEFT JOIN security_staff s ON s.id = u.linked_id
    WHERE u.id = p_security_id AND u.role = 'security';
$$;

-- ═══ EVENTS LIST (FIXED) ═══
DROP FUNCTION IF EXISTS fn_events_list CASCADE;

CREATE OR REPLACE FUNCTION fn_events_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT,
    title VARCHAR,
    description TEXT,
    event_date DATE,
    event_time VARCHAR,
    venue VARCHAR,
    open_to VARCHAR,
    created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT 
        e.id,
        e.title,
        e.description,
        e.event_date,
        e.event_time,
        e.venue,
        e.open_to,
        e.created_at
    FROM events e
    WHERE e.society_id = p_society_id
      AND e.event_date >= CURRENT_DATE
      AND (p_search IS NULL OR e.title ILIKE '%'||p_search||'%')
    ORDER BY e.event_date ASC;
END;
$$;

-- ═══ EVENT PROFILE (FIXED) ═══
DROP FUNCTION IF EXISTS fn_event_profile CASCADE;

CREATE OR REPLACE FUNCTION fn_event_profile(p_event_id INT)
RETURNS TABLE (
    id INT,
    society_id INT,
    title VARCHAR,
    description TEXT,
    event_date DATE,
    event_time VARCHAR,
    venue VARCHAR,
    open_to VARCHAR,
    created_at TIMESTAMP
)
LANGUAGE SQL STABLE AS $$
    SELECT 
        id,
        society_id,
        title,
        description,
        event_date,
        event_time,
        venue,
        open_to,
        created_at
    FROM events WHERE id = p_event_id;
$$;

-- ═══ CONCERNS LIST (FIXED) ═══
DROP FUNCTION IF EXISTS fn_concerns_list CASCADE;

CREATE OR REPLACE FUNCTION fn_concerns_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL,
    p_status VARCHAR DEFAULT 'open'
)
RETURNS TABLE (
    id INT,
    flat_no VARCHAR,
    concern_type VARCHAR,
    description TEXT,
    status VARCHAR,
    assigned_to VARCHAR,
    created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.id,
        c.flat_no,
        c.concern_type,
        c.description,
        c.status,
        c.assigned_to,
        c.created_at
    FROM concerns c
    WHERE c.society_id = p_society_id
      AND (p_status IS NULL OR c.status = p_status)
      AND (p_search IS NULL OR c.flat_no ILIKE '%'||p_search||'%')
    ORDER BY c.created_at DESC;
END;
$$;

-- ═══ CONCERN PROFILE (FIXED) ═══
DROP FUNCTION IF EXISTS fn_concern_profile CASCADE;

CREATE OR REPLACE FUNCTION fn_concern_profile(p_concern_id INT)
RETURNS TABLE (
    id INT,
    society_id INT,
    flat_no VARCHAR,
    concern_type VARCHAR,
    description TEXT,
    status VARCHAR,
    assigned_to VARCHAR,
    preferred_time VARCHAR,
    created_at TIMESTAMP
)
LANGUAGE SQL STABLE AS $$
    SELECT 
        id,
        society_id,
        flat_no,
        concern_type,
        description,
        status,
        assigned_to,
        preferred_time,
        created_at
    FROM concerns WHERE id = p_concern_id;
$$;

-- ═══ ACCOUNTS LIST (FIXED) ═══
DROP FUNCTION IF EXISTS fn_accounts_list CASCADE;

CREATE OR REPLACE FUNCTION fn_accounts_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL,
    p_tab_name VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id INT,
    name VARCHAR,
    tab_name VARCHAR,
    header VARCHAR,
    drcr_account VARCHAR,
    bf_amount NUMERIC,
    created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT 
        a.id,
        a.name,
        a.tab_name,
        a.header,
        a.drcr_account,
        a.bf_amount,
        a.created_at
    FROM accounts a
    WHERE a.society_id = p_society_id
      AND (p_tab_name IS NULL OR a.tab_name = p_tab_name)
      AND (p_search IS NULL OR a.name ILIKE '%'||p_search||'%')
    ORDER BY a.tab_name, a.name;
END;
$$;

-- ═══ ACCOUNT PROFILE (FIXED) ═══
DROP FUNCTION IF EXISTS fn_account_profile CASCADE;

CREATE OR REPLACE FUNCTION fn_account_profile(p_account_id INT)
RETURNS TABLE (
    id INT,
    society_id INT,
    name VARCHAR,
    tab_name VARCHAR,
    header VARCHAR,
    drcr_account VARCHAR,
    bf_amount NUMERIC,
    depreciation_percent NUMERIC,
    is_depreciable BOOLEAN,
    created_at TIMESTAMP
)
LANGUAGE SQL STABLE AS $$
    SELECT 
        id,
        society_id,
        name,
        tab_name,
        header,
        drcr_account,
        bf_amount,
        depreciation_percent,
        is_depreciable,
        created_at
    FROM accounts WHERE id = p_account_id;
$$;

-- ═══ SOCIETIES LIST (FIXED) ═══
DROP FUNCTION IF EXISTS fn_societies_list CASCADE;

CREATE OR REPLACE FUNCTION fn_societies_list(
    p_search TEXT DEFAULT NULL,
    p_plan VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id INT,
    name VARCHAR,
    email VARCHAR,
    phone VARCHAR,
    plan VARCHAR,
    plan_validity DATE,
    total_apartments INT,
    created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.id,
        s.name,
        s.email,
        s.phone,
        s.plan,
        s.plan_validity,
        (SELECT COUNT(*)::INT FROM apartments WHERE society_id = s.id AND active = TRUE),
        s.created_at
    FROM societies s
    WHERE (p_search IS NULL OR s.name ILIKE '%'||p_search||'%')
      AND (p_plan IS NULL OR s.plan = p_plan)
    ORDER BY s.name;
END;
$$;

-- ═══ SOCIETY PROFILE (FIXED) ═══
DROP FUNCTION IF EXISTS fn_society_profile CASCADE;

CREATE OR REPLACE FUNCTION fn_society_profile(p_society_id INT)
RETURNS TABLE (
    id INT,
    name VARCHAR,
    logo VARCHAR,
    email VARCHAR,
    phone VARCHAR,
    address TEXT,
    plan VARCHAR,
    plan_validity DATE,
    arrear_start_date DATE,
    secretary_name VARCHAR,
    secretary_phone VARCHAR,
    secretary_sign VARCHAR,
    login_background VARCHAR,
    total_apartments INT,
    total_vendors INT,
    total_security INT,
    created_at TIMESTAMP,
    _image_society_id INT
)
LANGUAGE SQL STABLE AS $$
    SELECT 
        s.id,
        s.name,
        s.logo,
        s.email,
        s.phone,
        s.address,
        s.plan,
        s.plan_validity,
        s.arrear_start_date,
        s.secretary_name,
        s.secretary_phone,
        s.secretary_sign,
        s.login_background,
        (SELECT COUNT(*)::INT FROM apartments WHERE society_id = s.id),
        (SELECT COUNT(*)::INT FROM vendors WHERE society_id = s.id),
        (SELECT COUNT(*)::INT FROM security_staff WHERE society_id = s.id),
        s.created_at,
        s.id
    FROM societies s WHERE s.id = p_society_id;
$$;

-- ═══ RECEIVABLES LIST (FIXED) ═══
DROP FUNCTION IF EXISTS fn_receivables_list CASCADE;

CREATE OR REPLACE FUNCTION fn_receivables_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL,
    p_status VARCHAR DEFAULT 'pending'
)
RETURNS TABLE (
    id INT,
    entity_type VARCHAR,
    entity_id INT,
    charge_type VARCHAR,
    description TEXT,
    amount NUMERIC,
    due_date DATE,
    status VARCHAR,
    created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT 
        r.id,
        r.entity_type,
        r.entity_id,
        r.charge_type,
        r.description,
        r.amount,
        r.due_date,
        r.status,
        r.created_at
    FROM receivables r
    WHERE r.society_id = p_society_id
      AND (p_status IS NULL OR r.status = p_status)
      AND (p_search IS NULL OR r.description ILIKE '%'||p_search||'%')
    ORDER BY r.due_date ASC, r.created_at DESC;
END;
$$;

-- ═══ RECEIVABLE PROFILE (FIXED) ═══
DROP FUNCTION IF EXISTS fn_receivable_profile CASCADE;

CREATE OR REPLACE FUNCTION fn_receivable_profile(p_receivable_id INT)
RETURNS TABLE (
    id INT,
    society_id INT,
    entity_type VARCHAR,
    entity_id INT,
    charge_type VARCHAR,
    description TEXT,
    amount NUMERIC,
    due_date DATE,
    status VARCHAR,
    created_at TIMESTAMP
)
LANGUAGE SQL STABLE AS $$
    SELECT 
        id,
        society_id,
        entity_type,
        entity_id,
        charge_type,
        description,
        amount,
        due_date,
        status,
        created_at
    FROM receivables WHERE id = p_receivable_id;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 4: KPI HELPER FUNCTIONS (NEW — for customize tab)
-- ════════════════════════════════════════════════════════════════

-- Get list of all defined KPIs with their SQL
DROP FUNCTION IF EXISTS fn_get_kpi_metadata CASCADE;

CREATE OR REPLACE FUNCTION fn_get_kpi_metadata()
RETURNS TABLE (
    kpi_id TEXT,
    kpi_label TEXT,
    kpi_icon TEXT,
    kpi_color TEXT,
    kpi_format TEXT,
    group_name TEXT,
    portal_name TEXT,
    tab_name TEXT
)
LANGUAGE SQL STABLE AS $$
    SELECT 
        'kpi_apartments_total'::TEXT, 'Total Apartments'::TEXT, 'fa-home'::TEXT, '#1859b8'::TEXT, 'number'::TEXT, 'Apartments'::TEXT, 'admin'::TEXT, 'dashboard'::TEXT
    UNION ALL SELECT 'kpi_apartments_dues', 'Apartments with Dues', 'fa-exclamation-circle', '#de5c52', 'number', 'Apartments', 'admin', 'dashboard'
    UNION ALL SELECT 'kpi_vendors_total', 'All Vendors', 'fa-truck', '#b98a07', 'number', 'Vendors', 'admin', 'dashboard'
    UNION ALL SELECT 'kpi_security_total', 'Security Staff', 'fa-user-shield', '#b63b3b', 'number', 'Security', 'admin', 'dashboard'
    UNION ALL SELECT 'kpi_events_total', 'Upcoming Events', 'fa-calendar-check', '#8e44ad', 'number', 'Events', 'admin', 'events'
    UNION ALL SELECT 'kpi_concerns_open', 'Open Concerns', 'fa-hand-point-up', '#de5c52', 'number', 'Concerns', 'admin', 'concerns'
    UNION ALL SELECT 'kpi_receipts_month', 'Receipts (Month)', 'fa-receipt', '#17976e', 'currency', 'Cashbook', 'admin', 'cashbook'
    UNION ALL SELECT 'kpi_expenses_month', 'Expenses (Month)', 'fa-wallet', '#de5c52', 'currency', 'Cashbook', 'admin', 'cashbook'
    UNION ALL SELECT 'kpi_balance', 'Current Balance', 'fa-coins', '#2c3e50', 'currency', 'Cashbook', 'admin', 'cashbook'
    UNION ALL SELECT 'kpi_cash_in_hand', 'Cash in Hand', 'fa-money-bill-wave', '#27ae60', 'currency', 'Cashbook', 'admin', 'cashbook'
    UNION ALL SELECT 'kpi_accounts_count', 'Chart of Accounts', 'fa-book-open', '#6c5ce7', 'number', 'Settings', 'admin', 'settings'
    UNION ALL SELECT 'kpi_apt_charges', 'Apartment Charges', 'fa-rupee-sign', '#1859b8', 'number', 'Settings', 'admin', 'settings'
    UNION ALL SELECT 'kpi_ven_charges', 'Vendor Charges', 'fa-rupee-sign', '#b98a07', 'number', 'Settings', 'admin', 'settings'
    UNION ALL SELECT 'kpi_sec_charges', 'Security Charges', 'fa-rupee-sign', '#b63b3b', 'number', 'Settings', 'admin', 'settings'
    UNION ALL SELECT 'kpi_societies_total', 'Total Societies', 'fa-building', '#c96a19', 'number', 'Master', 'master', 'dashboard'
    UNION ALL SELECT 'kpi_societies_free', 'Free Plan Societies', 'fa-circle', '#7d8ea3', 'number', 'Master', 'master', 'dashboard'
    UNION ALL SELECT 'kpi_societies_9Apts', '9Apts Plan', 'fa-star', '#17976e', 'number', 'Master', 'master', 'dashboard'
    UNION ALL SELECT 'kpi_societies_99Apts', '99Apts Plan', 'fa-star', '#17976e', 'number', 'Master', 'master', 'dashboard'
    UNION ALL SELECT 'kpi_societies_999Apts', '999Apts Plan', 'fa-star', '#17976e', 'number', 'Master', 'master', 'dashboard'
    UNION ALL SELECT 'kpi_societies_Unlimited', 'Unlimited Plan', 'fa-star', '#17976e', 'number', 'Master', 'master', 'dashboard'
    ORDER BY portal_name, tab_name, kpi_label;
$$;

-- Get SQL definition for a KPI (for the customize tab inspector)
DROP FUNCTION IF EXISTS fn_get_kpi_sql CASCADE;

CREATE OR REPLACE FUNCTION fn_get_kpi_sql(p_kpi_id TEXT)
RETURNS TABLE (
    kpi_id TEXT,
    kpi_label TEXT,
    sql_definition TEXT,
    params INTEGER,
    format_type TEXT
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_sql TEXT;
    v_params INT;
    v_format TEXT;
    v_label TEXT;
BEGIN
    -- This would be populated from card_catalogue.KPI_CARDS in Python
    -- For now, we'll return a placeholder that indicates where the data comes from
    
    RETURN QUERY SELECT 
        p_kpi_id::TEXT,
        'See card_catalogue.py KPI_CARDS['||p_kpi_id||']'::TEXT,
        'Query defined in Python KPI_CARDS dictionary'::TEXT,
        0::INTEGER,
        'See card_catalogue.py'::TEXT;
END;
$$;

-- Get all functions that start with fn_ (for customize tab)
DROP FUNCTION IF EXISTS fn_get_all_loaders CASCADE;

CREATE OR REPLACE FUNCTION fn_get_all_loaders()
RETURNS TABLE (
    function_name TEXT,
    schema_name TEXT,
    parameters TEXT
)
LANGUAGE SQL STABLE AS $$
    SELECT 
        p.proname::TEXT,
        n.nspname::TEXT,
        pg_get_function_arguments(p.oid)::TEXT
    FROM pg_proc p
    JOIN pg_namespace n ON p.pronamespace = n.oid
    WHERE p.proname LIKE 'fn_%'
      AND n.nspname = 'public'
    ORDER BY p.proname;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 5: INITIALIZATION DATA
-- ════════════════════════════════════════════════════════════════

-- Sample Master Admin User (if societies table is empty)
INSERT INTO societies (id, name, plan, plan_validity, arrear_start_date)
VALUES (0, 'Master', 'Unlimited', '2099-12-31'::DATE, CURRENT_DATE)
ON CONFLICT DO NOTHING;

-- Master Admin User
INSERT INTO users (society_id, email, password_hash, role, is_master_admin, login_method)
VALUES (NULL, 'admin@estatehub.local', 'placeholder_hash', 'admin', TRUE, 'password')
ON CONFLICT (email) DO NOTHING;

-- ════════════════════════════════════════════════════════════════
-- END OF FIXED SCHEMA
-- ════════════════════════════════════════════════════════════════
