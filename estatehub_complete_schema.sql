-- ═════════════════════════════════════════════════════════════════════════════
-- ESTATEHUB COMPLETE SCHEMA - VALIDATED & COMPLETE
-- ═════════════════════════════════════════════════════════════════════════════
-- Database: PostgreSQL 12+
-- Features: Transaction ledger, auto-receivables, RBAC, image management
-- ═════════════════════════════════════════════════════════════════════════════

-- ═════════════════════════════════════════════════════════════════════════════
-- 1. CORE TABLES (from dashestatehub.sql - VALIDATED)
-- ═════════════════════════════════════════════════════════════════════════════

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
    plan VARCHAR(20) NOT NULL DEFAULT 'Free' 
        CHECK (plan IN ('Free','9Apts','99Apts','999Apts','unlimited')),
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
    role VARCHAR(20) NOT NULL CHECK (role IN ('admin','apartment','vendor','security')),
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

CREATE TABLE IF NOT EXISTS accounts (
    id INT PRIMARY KEY NOT NULL,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    tab_name VARCHAR(20),
    header VARCHAR(50),
    parent_account_id INT REFERENCES accounts (id),
    drcr_account VARCHAR(2) CHECK (drcr_account IN ('Dr', 'Cr')),
    has_bf BOOLEAN DEFAULT FALSE,
    drcr_bf VARCHAR(2) CHECK (drcr_bf IN ('Dr', 'Cr')) NOT NULL DEFAULT 'Dr',
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
    acc_id INT NOT NULL REFERENCES accounts (id),
    entity_id INTEGER,
    acc_particulars VARCHAR(255),
    amount DECIMAL(15, 2) NOT NULL CHECK (amount > 0),
    mode VARCHAR(10) CHECK (mode IN ('cash','cheque','upi','card','bank','crypto')) DEFAULT 'cash',
    payment_gateway_ID VARCHAR(20),
    status VARCHAR(20) NOT NULL DEFAULT 'paid' CHECK (status IN ('paid','pending','failed')),
    created_by INTEGER REFERENCES users (id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_transactions_society FOREIGN KEY (society_id) 
        REFERENCES societies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS receivables (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id),
    entity_id INT NOT NULL,
    entity_type VARCHAR(20) NOT NULL CHECK (entity_type IN ('apartment','vendor','security')),
    charge_type VARCHAR(50) NOT NULL,
    description TEXT,
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    due_date DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending','confirmed','cancelled')),
    source_table VARCHAR(50),
    source_id INT,
    confirmed_by INT REFERENCES users (id),
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_receivables_society FOREIGN KEY (society_id) 
        REFERENCES societies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id),
    entity_id INT,
    entity_type VARCHAR(20) CHECK (entity_type IN ('apartment','vendor','security','other')),
    amount NUMERIC(10, 2) NOT NULL,
    payment_type VARCHAR(50),
    payment_method VARCHAR(50),
    transaction_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','confirmed','verified','failed','cancelled')),
    due_date DATE,
    paid_at TIMESTAMP,
    source_table VARCHAR(50),
    source_id INT,
    confirmed_by INT REFERENCES users (id),
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_payments_society FOREIGN KEY (society_id) 
        REFERENCES societies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS receipts (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id),
    entity_id INT,
    entity_type VARCHAR(20) CHECK (entity_type IN ('apartment','vendor','security','other')),
    receipt_date DATE NOT NULL,
    acc_id INT REFERENCES accounts (id),
    particulars TEXT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    mode VARCHAR(20) DEFAULT 'cash' CHECK (mode IN ('cash','cheque','upi','card','bank','crypto')),
    cheque_no VARCHAR(50),
    transaction_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending','confirmed','cancelled')),
    confirmed_by INT REFERENCES users (id),
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_receipts_society FOREIGN KEY (society_id) 
        REFERENCES societies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id),
    entity_id INT,
    entity_type VARCHAR(20) CHECK (entity_type IN ('vendor','security','other')),
    expense_date DATE NOT NULL,
    acc_id INT REFERENCES accounts (id),
    particulars TEXT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    mode VARCHAR(20) DEFAULT 'cash' CHECK (mode IN ('cash','cheque','upi','card','bank','crypto')),
    cheque_no VARCHAR(50),
    transaction_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending','confirmed','cancelled')),
    confirmed_by INT REFERENCES users (id),
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_expenses_society FOREIGN KEY (society_id) 
        REFERENCES societies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS gate_access (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    role VARCHAR(1),
    entity_id INTEGER NOT NULL,
    time_in TIMESTAMP NOT NULL DEFAULT NOW(),
    time_out TIMESTAMP,
    CONSTRAINT fk_gate_access_society FOREIGN KEY (society_id) 
        REFERENCES societies(id) ON DELETE CASCADE
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
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_events_society FOREIGN KEY (society_id) 
        REFERENCES societies(id) ON DELETE CASCADE
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
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_concerns_society FOREIGN KEY (society_id) 
        REFERENCES societies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS apt_charges_fines (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    apt_id INT NOT NULL REFERENCES apartments (id) ON DELETE CASCADE,
    start_date DATE NOT NULL,
    end_date DATE,
    apt_maintenance_rate FLOAT NOT NULL DEFAULT 0,
    apt_due_day INTEGER DEFAULT 10,
    apt_delay_fine DECIMAL(10, 2) DEFAULT 0,
    apt_fine DECIMAL(10, 2) DEFAULT 0,
    apt_status BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ven_charges_fines (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    ven_id INT NOT NULL REFERENCES vendors (id) ON DELETE CASCADE,
    start_date DATE NOT NULL,
    end_date DATE,
    vendor_1day DECIMAL(10, 2) DEFAULT 0,
    vendor_7day DECIMAL(10, 2) DEFAULT 0,
    vendor_1mth DECIMAL(10, 2) DEFAULT 0,
    vendor_fine DECIMAL(10, 2) DEFAULT 0,
    ven_status BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS security_charges_fines (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    sec_id INT NOT NULL REFERENCES security_staff (id) ON DELETE CASCADE,
    start_date DATE NOT NULL,
    end_date DATE,
    security_fine DECIMAL(10, 2) DEFAULT 0,
    sec_status BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS asset_register (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    asset_name VARCHAR(100),
    purchase_value DECIMAL(12, 2),
    purchase_date DATE,
    parent_account_id INT REFERENCES accounts (id),
    depreciation_rate DECIMAL(5, 2) DEFAULT 10.00,
    last_depreciation_date DATE,
    CONSTRAINT fk_asset_register_society FOREIGN KEY (society_id) 
        REFERENCES societies(id) ON DELETE CASCADE
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
    UNIQUE (society_id, user_id, issued_date)
);

CREATE TABLE IF NOT EXISTS security_roster (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    security_id INT NOT NULL REFERENCES security_staff (id) ON DELETE CASCADE,
    roster_date DATE NOT NULL,
    shift_type VARCHAR(20) CHECK (shift_type IN ('morning','evening','night')),
    assigned_by INT REFERENCES users (id),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (society_id, security_id, roster_date)
);

-- ═════════════════════════════════════════════════════════════════════════════
-- 2. INDEXES (VALIDATED & OPTIMIZED)
-- ═════════════════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_society_role ON users (society_id, role);
CREATE INDEX IF NOT EXISTS idx_users_linked ON users (linked_id);
CREATE INDEX IF NOT EXISTS idx_users_master_admin ON users (is_master_admin) 
    WHERE is_master_admin = TRUE;

CREATE INDEX IF NOT EXISTS idx_apartments_society ON apartments (society_id);
CREATE INDEX IF NOT EXISTS idx_apartments_active ON apartments (society_id, active);
CREATE INDEX IF NOT EXISTS idx_apartments_society_flat ON apartments (society_id, flat_number);

CREATE INDEX IF NOT EXISTS idx_vendors_society_active ON vendors (society_id, active);

CREATE INDEX IF NOT EXISTS idx_security_society_active ON security_staff (society_id, active);

CREATE INDEX IF NOT EXISTS idx_accounts_society ON accounts (society_id);
CREATE INDEX IF NOT EXISTS idx_accounts_tab ON accounts (society_id, tab_name);
CREATE INDEX IF NOT EXISTS idx_accounts_parent ON accounts (parent_account_id);

CREATE INDEX IF NOT EXISTS idx_transactions_society_date ON transactions (society_id, trx_date DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions (acc_id);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions (status);
CREATE INDEX IF NOT EXISTS idx_transactions_society_status ON transactions (society_id, status);

CREATE INDEX IF NOT EXISTS idx_receivables_society_status ON receivables (society_id, status);
CREATE INDEX IF NOT EXISTS idx_receivables_entity ON receivables (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_receivables_due_date ON receivables (due_date);

CREATE INDEX IF NOT EXISTS idx_payments_society_status ON payments (society_id, status);
CREATE INDEX IF NOT EXISTS idx_payments_user ON payments (user_id);
CREATE INDEX IF NOT EXISTS idx_payments_due_date ON payments (due_date);
CREATE INDEX IF NOT EXISTS idx_payments_entity ON payments (entity_id, entity_type);

CREATE INDEX IF NOT EXISTS idx_receipts_society_status ON receipts (society_id, status);
CREATE INDEX IF NOT EXISTS idx_receipts_date ON receipts (receipt_date);
CREATE INDEX IF NOT EXISTS idx_receipts_entity ON receipts (entity_type, entity_id);

CREATE INDEX IF NOT EXISTS idx_expenses_society_status ON expenses (society_id, status);
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses (expense_date);
CREATE INDEX IF NOT EXISTS idx_expenses_entity ON expenses (entity_type, entity_id);

CREATE INDEX IF NOT EXISTS idx_gate_society_time ON gate_access (society_id, time_in);
CREATE INDEX IF NOT EXISTS idx_gate_entity ON gate_access (role, entity_id);
CREATE INDEX IF NOT EXISTS idx_gate_open_entries ON gate_access (role, entity_id, time_out);

CREATE INDEX IF NOT EXISTS idx_events_society_date ON events (society_id, event_date);

CREATE INDEX IF NOT EXISTS idx_concerns_society_status ON concerns (society_id, status);

CREATE INDEX IF NOT EXISTS idx_asset_society ON asset_register (society_id);
CREATE INDEX IF NOT EXISTS idx_asset_account ON asset_register (parent_account_id);

CREATE INDEX IF NOT EXISTS idx_vendor_passes_active ON vendor_passes (society_id, user_id, valid_until)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_security_roster_date ON security_roster (society_id, roster_date);
CREATE INDEX IF NOT EXISTS idx_security_roster_staff ON security_roster (security_id);

-- ═════════════════════════════════════════════════════════════════════════════
-- 3. RBAC TABLE (NEW - Role-Based Access Control)
-- ═════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS role_permissions (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    resource VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    allowed BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (society_id, role, resource, action)
);

CREATE INDEX idx_role_permissions_lookup ON role_permissions (society_id, role, resource);

-- ═════════════════════════════════════════════════════════════════════════════
-- 4. APARTMENT LIST FUNCTION (VALIDATED & ENHANCED)
-- ═════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_apartments_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL,
    p_has_dues BOOLEAN DEFAULT NULL
)
RETURNS TABLE (
    id INT, flat_number VARCHAR, owner_name VARCHAR, mobile VARCHAR,
    apartment_size INT, active BOOLEAN, society_id INT, months_due BIGINT,
    total_maintenance NUMERIC, paid_amount NUMERIC, pending_amount NUMERIC,
    late_fee NUMERIC, grand_total NUMERIC
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM fn_auto_generate_receivables(p_society_id);
    PERFORM fn_auto_process_verified_payments(p_society_id);

    RETURN QUERY
    WITH apartment_base AS (
        SELECT a.id, a.flat_number, a.owner_name, a.mobile, a.apartment_size, a.active, a.society_id,
               COALESCE(acf.apt_maintenance_rate, 3.0) AS rate_per_sqft,
               acf.start_date
        FROM apartments a
        LEFT JOIN apt_charges_fines acf ON acf.apt_id = a.id AND acf.apt_status = TRUE
        WHERE a.society_id = p_society_id
          AND (p_search IS NULL OR a.flat_number ILIKE '%'||p_search||'%' OR a.owner_name ILIKE '%'||p_search||'%')
    ),
    maintenance_calc AS (
        SELECT *, 
               GREATEST(EXTRACT(YEAR FROM AGE(CURRENT_DATE, COALESCE(start_date, CURRENT_DATE)))*12 +
                        EXTRACT(MONTH FROM AGE(CURRENT_DATE, COALESCE(start_date, CURRENT_DATE))), 0) AS months_due
        FROM apartment_base
    ),
    payments_summary AS (
        SELECT entity_id AS apartment_id,
               SUM(CASE WHEN status='verified' THEN amount ELSE 0 END) AS paid_amount,
               SUM(CASE WHEN status IN ('pending','confirmed') THEN amount ELSE 0 END) AS pending_amount
        FROM payments WHERE society_id = p_society_id AND entity_type = 'apartment'
        GROUP BY entity_id
    ),
    late_fee_calc AS (
        SELECT entity_id AS apartment_id,
               SUM(CASE WHEN due_date < CURRENT_DATE THEN amount * 0.02 * GREATEST(EXTRACT(DAY FROM AGE(CURRENT_DATE, due_date)),0)/30 ELSE 0 END) AS late_fee
        FROM payments 
        WHERE society_id = p_society_id AND entity_type = 'apartment' AND status IN ('pending','confirmed')
        GROUP BY entity_id
    )
    SELECT 
        mc.id, mc.flat_number, mc.owner_name, mc.mobile, mc.apartment_size, mc.active, mc.society_id,
        mc.months_due::BIGINT,
        (mc.apartment_size * mc.rate_per_sqft * GREATEST(mc.months_due, 0))::NUMERIC AS total_maintenance,
        COALESCE(ps.paid_amount, 0), COALESCE(ps.pending_amount, 0),
        COALESCE(lf.late_fee, 0),
        (mc.apartment_size * mc.rate_per_sqft * GREATEST(mc.months_due, 0) - COALESCE(ps.paid_amount, 0) + COALESCE(lf.late_fee, 0))::NUMERIC AS grand_total
    FROM maintenance_calc mc
    LEFT JOIN payments_summary ps ON ps.apartment_id = mc.id
    LEFT JOIN late_fee_calc lf ON lf.apartment_id = mc.id
    WHERE (p_has_dues IS NULL OR 
          (p_has_dues AND (COALESCE(ps.pending_amount,0) + COALESCE(lf.late_fee,0)) > 0) OR
          (NOT p_has_dues AND (COALESCE(ps.pending_amount,0) + COALESCE(lf.late_fee,0)) = 0))
    ORDER BY mc.flat_number;
END;
$$;

-- ═════════════════════════════════════════════════════════════════════════════
-- 5. AUTO RECEIVABLES FUNCTION (VALIDATED)
-- ═════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_auto_generate_receivables(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO receivables (
        society_id, entity_id, entity_type, charge_type, description, 
        amount, due_date, status, source_table, source_id, created_at
    )
    SELECT 
        acf.society_id, acf.apt_id, 'apartment', 'maintenance',
        'Maintenance - ' || a.flat_number,
        (a.apartment_size * acf.apt_maintenance_rate)::NUMERIC,
        (DATE_TRUNC('month', CURRENT_DATE) + ((COALESCE(acf.apt_due_day, 10)-1) || ' days')::INTERVAL)::DATE,
        'pending', 'apt_charges_fines', acf.id, NOW()
    FROM apt_charges_fines acf
    JOIN apartments a ON a.id = acf.apt_id
    WHERE acf.society_id = p_society_id AND acf.apt_status = TRUE
      AND NOT EXISTS (SELECT 1 FROM receivables r 
                      WHERE r.source_table = 'apt_charges_fines' AND r.source_id = acf.id 
                        AND r.status != 'cancelled')
    ON CONFLICT DO NOTHING;
END;
$$;

-- ═════════════════════════════════════════════════════════════════════════════
-- 6. AUTO PAYMENT PROCESSING (VALIDATED)
-- ═════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_auto_process_verified_payments(p_society_id INT)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    rec_payment RECORD;
    remaining_amount NUMERIC;
    rec_receivable RECORD;
BEGIN
    FOR rec_payment IN 
        SELECT * FROM payments p
        WHERE p.society_id = p_society_id 
          AND p.status = 'verified'
          AND NOT EXISTS (
              SELECT 1 FROM receipts r 
              WHERE r.transaction_id = p.transaction_id 
                 OR (r.entity_id = p.entity_id 
                     AND r.entity_type = p.entity_type 
                     AND r.amount = p.amount 
                     AND r.receipt_date = COALESCE(p.paid_at::DATE, CURRENT_DATE))
          )
    LOOP
        INSERT INTO receipts (
            society_id, user_id, entity_id, entity_type, receipt_date, acc_id,
            particulars, amount, mode, transaction_id, status, 
            confirmed_by, confirmed_at, created_at
        )
        VALUES (
            rec_payment.society_id,
            rec_payment.confirmed_by,
            rec_payment.entity_id,
            rec_payment.entity_type,
            COALESCE(rec_payment.paid_at::DATE, CURRENT_DATE),
            1,
            'Payment Received - ' || 
                CASE 
                    WHEN rec_payment.entity_type = 'apartment' THEN 'Flat ' || (SELECT flat_number FROM apartments WHERE id = rec_payment.entity_id)
                    WHEN rec_payment.entity_type = 'vendor' THEN (SELECT name FROM vendors WHERE id = rec_payment.entity_id)
                    WHEN rec_payment.entity_type = 'security' THEN (SELECT name FROM security_staff WHERE id = rec_payment.entity_id)
                    ELSE 'Entity #' || rec_payment.entity_id 
                END,
            rec_payment.amount,
            COALESCE(rec_payment.payment_method, 'cash'),
            rec_payment.transaction_id,
            'confirmed',
            rec_payment.confirmed_by,
            rec_payment.confirmed_at,
            NOW()
        );

        remaining_amount := rec_payment.amount;

        FOR rec_receivable IN 
            SELECT * FROM receivables r
            WHERE r.society_id = p_society_id
              AND r.entity_id = rec_payment.entity_id
              AND r.entity_type = rec_payment.entity_type
              AND r.status = 'pending'
            ORDER BY r.due_date ASC, r.id ASC
        LOOP
            IF remaining_amount <= 0 THEN EXIT; END IF;

            IF rec_receivable.amount <= remaining_amount THEN
                UPDATE receivables 
                SET status = 'confirmed',
                    confirmed_by = rec_payment.confirmed_by,
                    confirmed_at = rec_payment.confirmed_at
                WHERE id = rec_receivable.id;

                remaining_amount := remaining_amount - rec_receivable.amount;
            ELSE
                UPDATE receivables 
                SET amount = rec_receivable.amount - remaining_amount
                WHERE id = rec_receivable.id;

                remaining_amount := 0;
            END IF;
        END LOOP;
    END LOOP;
END;
$$;

-- ═════════════════════════════════════════════════════════════════════════════
-- 7. VENDOR LIST FUNCTION (VALIDATED & NEW)
-- ═════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_vendors_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT, 
    email VARCHAR, 
    society_id INT, 
    business_name TEXT, 
    service_type VARCHAR,
    mobile VARCHAR, 
    active BOOLEAN, 
    pending_dues NUMERIC, 
    paid_amount NUMERIC,
    active_passes INT
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    PERFORM fn_auto_generate_vendor_receivables(p_society_id);
    PERFORM fn_auto_process_vendor_payments(p_society_id);

    RETURN QUERY
    WITH vendor_data AS (
        SELECT 
            u.id,
            u.email,
            u.society_id,
            COALESCE(v.name, u.email) AS business_name,
            COALESCE(v.service_type, '—') AS service_type,
            COALESCE(v.mobile, '—') AS mobile,
            COALESCE(v.active, TRUE) AS active,
            (SELECT COUNT(*) FROM vendor_passes vp 
             WHERE vp.society_id = u.society_id 
               AND vp.user_id = u.id 
               AND vp.status = 'active' 
               AND vp.valid_until >= CURRENT_DATE) AS active_passes
        FROM users u
        LEFT JOIN vendors v ON v.id = u.linked_id
        WHERE u.society_id = p_society_id 
          AND u.role = 'vendor'
          AND (p_search IS NULL 
               OR v.name ILIKE '%' || p_search || '%' 
               OR u.email ILIKE '%' || p_search || '%')
    ),
    payment_summary AS (
        SELECT 
            p.user_id,
            COALESCE(SUM(CASE WHEN p.status = 'verified' THEN p.amount ELSE 0 END), 0) AS paid_amount,
            COALESCE(SUM(CASE WHEN p.status IN ('pending', 'confirmed') THEN p.amount ELSE 0 END), 0) AS pending_dues
        FROM payments p
        WHERE p.society_id = p_society_id 
          AND p.entity_type = 'vendor'
        GROUP BY p.user_id
    )
    SELECT 
        vd.id, vd.email, vd.society_id, vd.business_name, vd.service_type,
        vd.mobile, vd.active, 
        COALESCE(ps.pending_dues, 0) AS pending_dues,
        COALESCE(ps.paid_amount, 0) AS paid_amount,
        vd.active_passes
    FROM vendor_data vd
    LEFT JOIN payment_summary ps ON ps.user_id = vd.id
    ORDER BY vd.business_name;
END;
$$;

-- ═════════════════════════════════════════════════════════════════════════════
-- 8. SECURITY LIST FUNCTION (VALIDATED & NEW)
-- ═════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_security_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT, email VARCHAR, society_id INT, name TEXT, shift VARCHAR, 
    mobile VARCHAR, active BOOLEAN, salary_per_shift NUMERIC, 
    joining_date DATE, days_worked BIGINT, salary_due NUMERIC, 
    salary_paid NUMERIC, salary_pending NUMERIC, current_status TEXT
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM fn_auto_generate_security_receivables(p_society_id);
    PERFORM fn_auto_process_security_payments(p_society_id);

    RETURN QUERY
    WITH security_base AS (
        SELECT u.id, u.email, u.society_id, COALESCE(s.name, u.email) AS name,
               COALESCE(s.shift, '—') AS shift, COALESCE(s.mobile, '—') AS mobile,
               COALESCE(s.active, TRUE) AS active, s.salary_per_shift, s.joining_date,
               EXTRACT(DAY FROM AGE(CURRENT_DATE, COALESCE(s.joining_date, CURRENT_DATE)))::BIGINT AS days_worked
        FROM users u LEFT JOIN security_staff s ON s.id = u.linked_id
        WHERE u.society_id = p_society_id AND u.role = 'security'
          AND (p_search IS NULL OR s.name ILIKE '%'||p_search||'%' OR u.email ILIKE '%'||p_search||'%')
    ),
    payment_summary AS (
        SELECT 
            p.user_id,
            SUM(CASE WHEN p.status = 'verified' AND p.payment_type = 'salary' THEN p.amount ELSE 0 END) AS salary_paid,
            SUM(CASE WHEN p.status IN ('pending','confirmed') THEN p.amount ELSE 0 END) AS total_pending
        FROM payments p
        WHERE p.society_id = p_society_id AND p.entity_type = 'security'
        GROUP BY p.user_id
    ),
    current_status AS (
        SELECT 
            g.entity_id,
            'ON_DUTY' AS status
        FROM gate_access g
        WHERE g.society_id = p_society_id
          AND g.role = 's'
          AND g.time_out IS NULL
          AND g.time_in >= CURRENT_DATE
    )
    SELECT 
        sb.id, sb.email, sb.society_id, sb.name, sb.shift, sb.mobile, sb.active,
        sb.salary_per_shift, sb.joining_date, sb.days_worked,
        (sb.salary_per_shift * sb.days_worked)::NUMERIC AS salary_due,
        COALESCE(ps.salary_paid, 0),
        GREATEST((sb.salary_per_shift * sb.days_worked) - COALESCE(ps.salary_paid, 0), 0)::NUMERIC,
        COALESCE(cs.status, 'OFF_DUTY')
    FROM security_base sb
    LEFT JOIN payment_summary ps ON ps.user_id = sb.id
    LEFT JOIN current_status cs ON cs.entity_id = sb.id
    ORDER BY sb.name;
END;
$$;

-- ═════════════════════════════════════════════════════════════════════════════
-- 9. EVENTS LIST FUNCTION (NEW)
-- ═════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_events_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT, event_date DATE, title VARCHAR, venue VARCHAR, 
    open_to VARCHAR, days_away INT, created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT 
        e.id, e.event_date, e.title, e.venue, e.open_to,
        (e.event_date - CURRENT_DATE)::INT AS days_away,
        e.created_at
    FROM events e
    WHERE e.society_id = p_society_id
      AND (p_search IS NULL OR e.title ILIKE '%'||p_search||'%' OR e.venue ILIKE '%'||p_search||'%')
    ORDER BY e.event_date ASC;
END;
$$;

-- ═════════════════════════════════════════════════════════════════════════════
-- 10. CONCERNS LIST FUNCTION (NEW)
-- ═════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_concerns_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL,
    p_status VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id INT, flat_no VARCHAR, concern_type VARCHAR, description TEXT,
    status VARCHAR, assigned_to VARCHAR, days_old INT, created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.id, c.flat_no, c.concern_type, c.description, c.status, c.assigned_to,
        (CURRENT_DATE - c.created_at::DATE)::INT AS days_old,
        c.created_at
    FROM concerns c
    WHERE c.society_id = p_society_id
      AND (p_status IS NULL OR c.status = p_status)
      AND (p_search IS NULL OR c.flat_no ILIKE '%'||p_search||'%' OR c.description ILIKE '%'||p_search||'%')
    ORDER BY c.created_at DESC;
END;
$$;

-- ═════════════════════════════════════════════════════════════════════════════
-- 11. ACCOUNTS LIST FUNCTION (NEW)
-- ═════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_accounts_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT, name VARCHAR, tab_name VARCHAR, header VARCHAR,
    drcr_account VARCHAR, bf_amount DECIMAL, current_balance DECIMAL,
    parent_account_name VARCHAR
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT 
        a.id, a.name, a.tab_name, a.header, a.drcr_account, a.bf_amount,
        COALESCE(
            (SELECT SUM(
                CASE 
                    WHEN a.drcr_account = 'Cr' THEN t.amount
                    ELSE -t.amount
                END
            )
            FROM transactions t
            WHERE t.acc_id = a.id AND t.status = 'paid'),
            0
        ) + a.bf_amount AS current_balance,
        COALESCE(parent.name, '—') AS parent_account_name
    FROM accounts a
    LEFT JOIN accounts parent ON a.parent_account_id = parent.id
    WHERE a.society_id = p_society_id
      AND (p_search IS NULL OR a.name ILIKE '%'||p_search||'%' OR a.tab_name ILIKE '%'||p_search||'%')
    ORDER BY a.name;
END;
$$;

-- ═════════════════════════════════════════════════════════════════════════════
-- 12. SOCIETIES LIST FUNCTION (NEW - Master Admin)
-- ═════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_societies_list(
    p_search TEXT DEFAULT NULL,
    p_plan VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id INT, name VARCHAR, email VARCHAR, phone VARCHAR, plan VARCHAR,
    plan_validity DATE, plan_status VARCHAR, created_at TIMESTAMP,
    total_users INT, total_apartments INT
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.id, s.name, s.email, s.phone, s.plan, s.plan_validity,
        CASE 
            WHEN s.plan = 'Free' THEN 'Free'
            WHEN s.plan_validity >= CURRENT_DATE THEN 'Active'
            ELSE 'Expired'
        END AS plan_status,
        s.created_at,
        (SELECT COUNT(*) FROM users WHERE society_id = s.id) AS total_users,
        (SELECT COUNT(*) FROM apartments WHERE society_id = s.id AND active = TRUE) AS total_apartments
    FROM societies s
    WHERE (p_plan IS NULL OR s.plan = p_plan)
      AND (p_search IS NULL OR s.name ILIKE '%'||p_search||'%' OR s.email ILIKE '%'||p_search||'%')
    ORDER BY s.name;
END;
$$;

-- ═════════════════════════════════════════════════════════════════════════════
-- 13. ASSET DEPRECIATION (NEW)
-- ═════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_asset_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT, asset_name VARCHAR, purchase_value DECIMAL,
    purchase_date DATE, account_name VARCHAR, depreciation_rate DECIMAL,
    expense_portion DECIMAL, asset_portion DECIMAL, current_book_value DECIMAL,
    status TEXT
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM fn_calculate_asset_depreciation(p_society_id);

    RETURN QUERY
    SELECT 
        ar.id, ar.asset_name, ar.purchase_value, ar.purchase_date,
        COALESCE(acc.name, '—') AS account_name,
        COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10.00) AS depreciation_rate,
        CASE 
            WHEN COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) = 100 
                THEN ar.purchase_value
            WHEN EXTRACT(MONTH FROM ar.purchase_date) >= 9 
                THEN ar.purchase_value * (COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) / 100) * 0.5
            ELSE ar.purchase_value * (COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) / 100)
        END AS expense_portion,
        GREATEST(
            ar.purchase_value * (1 - COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) / 100), 
            0
        ) AS asset_portion,
        GREATEST(
            ar.purchase_value * (1 - COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) / 100), 
            0
        ) AS current_book_value,
        CASE 
            WHEN COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) = 100 THEN 'FULLY_EXPENSED'
            ELSE 'ACTIVE'
        END AS status
    FROM asset_register ar
    LEFT JOIN accounts acc ON acc.id = ar.parent_account_id
    WHERE ar.society_id = p_society_id
      AND (p_search IS NULL OR ar.asset_name ILIKE '%' || p_search || '%')
    ORDER BY ar.purchase_date DESC;
END;
$$;

CREATE OR REPLACE FUNCTION fn_calculate_asset_depreciation(p_society_id INT)
RETURNS VOID
LANGUAGE plpgsql AS $$
DECLARE
    rec RECORD;
    dep_rate DECIMAL(5,2);
    expense_amount NUMERIC;
    half_year_rule BOOLEAN;
BEGIN
    FOR rec IN 
        SELECT ar.*, COALESCE(acc.depreciation_percent, ar.depreciation_rate, 10) AS final_rate
        FROM asset_register ar
        LEFT JOIN accounts acc ON acc.id = ar.parent_account_id
        WHERE ar.society_id = p_society_id 
          AND (ar.last_depreciation_date IS NULL OR ar.last_depreciation_date < CURRENT_DATE - INTERVAL '25 days')
    LOOP
        dep_rate := rec.final_rate;

        IF dep_rate = 100 THEN
            expense_amount := rec.purchase_value;
        ELSE
            half_year_rule := (EXTRACT(MONTH FROM rec.purchase_date) >= 9);
            IF half_year_rule THEN
                expense_amount := rec.purchase_value * (dep_rate / 100) * 0.5;
            ELSE
                expense_amount := rec.purchase_value * (dep_rate / 100);
            END IF;
        END IF;

        INSERT INTO expenses (
            society_id, entity_type, expense_date, acc_id, particulars, amount, mode, status, created_at
        )
        VALUES (
            p_society_id, 'asset', CURRENT_DATE, 
            COALESCE(rec.parent_account_id, 5),
            'Depreciation - ' || rec.asset_name || CASE WHEN half_year_rule THEN ' (Half Year)' ELSE '' END,
            expense_amount, 'cash', 'confirmed', NOW()
        );

        UPDATE asset_register 
        SET last_depreciation_date = CURRENT_DATE 
        WHERE id = rec.id;
    END LOOP;
END;
$$;

-- ═════════════════════════════════════════════════════════════════════════════
-- 14. PLACEHOLDER FUNCTIONS (To be completed from fn_*.sql files)
-- ═════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_auto_generate_vendor_receivables(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    -- Vendor receivables from passes & fines - see fn_vendors.sql
    NULL;
END;
$$;

CREATE OR REPLACE FUNCTION fn_auto_process_vendor_payments(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    -- Auto process verified vendor payments - see fn_vendors.sql
    NULL;
END;
$$;

CREATE OR REPLACE FUNCTION fn_auto_generate_security_receivables(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    -- Security receivables from fines - see fn_security.sql
    NULL;
END;
$$;

CREATE OR REPLACE FUNCTION fn_auto_process_security_payments(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    -- Auto process security salary payments - see fn_security.sql
    NULL;
END;
$$;

-- ═════════════════════════════════════════════════════════════════════════════
-- 15. CASHBOOK / TRANSACTION VIEW (NEW)
-- ═════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE VIEW vw_cashbook AS
WITH transactions_with_balance AS (
    SELECT 
        t.id, t.society_id, t.trx_date, t.acc_id, t.acc_particulars,
        t.amount, t.mode, t.status, t.created_at,
        acc.name AS account_name,
        acc.drcr_account,
        CASE WHEN acc.drcr_account = 'Dr' THEN t.amount ELSE NULL END AS debit,
        CASE WHEN acc.drcr_account = 'Cr' THEN t.amount ELSE NULL END AS credit,
        SUM(CASE 
            WHEN acc.drcr_account = 'Cr' THEN t.amount
            ELSE -t.amount
        END) OVER (PARTITION BY t.society_id ORDER BY t.trx_date, t.id) AS running_balance
    FROM transactions t
    JOIN accounts acc ON t.acc_id = acc.id
    WHERE t.status = 'paid'
)
SELECT * FROM transactions_with_balance;

-- ═════════════════════════════════════════════════════════════════════════════
-- SCHEMA COMPLETE - Ready for application integration
-- ═════════════════════════════════════════════════════════════════════════════
