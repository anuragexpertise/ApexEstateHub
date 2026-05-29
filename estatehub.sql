-- ============================================================
-- ESTATEHUB - COMPLETE DATABASE SCHEMA & FUNCTIONS
-- Production: Aiven PostgreSQL
-- Deploy: psql -U user -d database < estatehub.sql
-- ============================================================
-- SAFE TO RE-RUN: Uses IF NOT EXISTS throughout
-- Last Updated: 2026-05-28
-- ============================================================

-- ════════════════════════════════════════════════════════════════
-- SECTION 1: CORE SCHEMA
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
    plan VARCHAR(20) NOT NULL DEFAULT 'Free' 
        CHECK (plan IN ('Free', '9Apts','99Apts','999Apts','unlimited')),
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
    role VARCHAR(20) NOT NULL 
        CHECK (role IN ('admin','apartment','vendor','security')),
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
    entity_type VARCHAR(20) 
        CHECK (entity_type IN ('apartment', 'vendor', 'security', 'other')),
    amount NUMERIC(10, 2) NOT NULL,
    payment_type VARCHAR(50),
    payment_method VARCHAR(50),
    transaction_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending', 'confirmed', 'verified', 'failed', 'cancelled')),
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
    CONSTRAINT fk_account_parent FOREIGN KEY (parent_account_id) 
        REFERENCES accounts(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    trx_date DATE NOT NULL,
    acc_id INT REFERENCES accounts (id),
    entity_id INTEGER,
    acc_particulars VARCHAR(100),
    amount NUMERIC(15, 2) NOT NULL CHECK (amount > 0),
    mode VARCHAR(6) DEFAULT 'cash' 
        CHECK (mode IN ('cash','cheque','upi','card','bank','crypto')),
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
    entity_type VARCHAR(20) NOT NULL 
        CHECK (entity_type IN ('apartment', 'vendor', 'security')),
    charge_type VARCHAR(50) NOT NULL,
    description TEXT,
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    due_date DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending', 'confirmed', 'cancelled')),
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
    entity_type VARCHAR(20) 
        CHECK (entity_type IN ('apartment', 'vendor', 'security', 'other')),
    receipt_date DATE NOT NULL,
    acc_id INT REFERENCES accounts (id),
    particulars TEXT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    mode VARCHAR(20) DEFAULT 'cash' 
        CHECK (mode IN ('cash','cheque','upi','card','bank','crypto')),
    cheque_no VARCHAR(50),
    transaction_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending', 'confirmed', 'cancelled')),
    confirmed_by INT REFERENCES users (id),
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id),
    entity_id INT,
    entity_type VARCHAR(20) 
        CHECK (entity_type IN ('vendor', 'security', 'other')),
    expense_date DATE NOT NULL,
    acc_id INT REFERENCES accounts (id),
    particulars TEXT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    mode VARCHAR(20) DEFAULT 'cash' 
        CHECK (mode IN ('cash','cheque','upi','card','bank','crypto')),
    cheque_no VARCHAR(50),
    transaction_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending', 'confirmed', 'cancelled')),
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
    UNIQUE (society_id, user_id, issued_date)
);

CREATE TABLE IF NOT EXISTS security_roster (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    security_id INT NOT NULL REFERENCES security_staff (id) ON DELETE CASCADE,
    roster_date DATE NOT NULL,
    shift_type VARCHAR(20) CHECK (shift_type IN ('morning', 'evening', 'night')),
    assigned_by INT REFERENCES users (id),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(society_id, security_id, roster_date)
);

CREATE TABLE IF NOT EXISTS role_permissions (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    card_id VARCHAR(100) NOT NULL,
    permission VARCHAR(20) NOT NULL CHECK (permission IN ('view', 'create', 'edit', 'delete')),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (COALESCE(society_id, 0), role, card_id, permission)
);

-- ════════════════════════════════════════════════════════════════
-- SECTION 2: INDEXES
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
-- SECTION 3: BUSINESS LOGIC FUNCTIONS
-- ════════════════════════════════════════════════════════════════

-- ═══ APARTMENTS ═══

DROP FUNCTION IF EXISTS fn_apartments_list CASCADE;
DROP FUNCTION IF EXISTS fn_auto_generate_receivables CASCADE;
DROP FUNCTION IF EXISTS fn_auto_process_verified_payments CASCADE;

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
        SELECT *, GREATEST(EXTRACT(YEAR FROM AGE(CURRENT_DATE, COALESCE(start_date, CURRENT_DATE)))*12 +
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
        (mc.apartment_size * mc.rate_per_sqft * GREATEST(mc.months_due, 0)) AS total_maintenance,
        COALESCE(ps.paid_amount, 0), COALESCE(ps.pending_amount, 0),
        COALESCE(lf.late_fee, 0),
        (mc.apartment_size * mc.rate_per_sqft * GREATEST(mc.months_due, 0) - COALESCE(ps.paid_amount, 0) + COALESCE(lf.late_fee, 0)) AS grand_total
    FROM maintenance_calc mc
    LEFT JOIN payments_summary ps ON ps.apartment_id = mc.id
    LEFT JOIN late_fee_calc lf ON lf.apartment_id = mc.id
    WHERE (p_has_dues IS NULL OR 
          (p_has_dues AND (COALESCE(ps.pending_amount,0) + COALESCE(lf.late_fee,0)) > 0) OR
          (NOT p_has_dues AND (COALESCE(ps.pending_amount,0) + COALESCE(lf.late_fee,0)) = 0))
    ORDER BY mc.flat_number;
END;
$$;

CREATE OR REPLACE FUNCTION fn_auto_generate_receivables(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO receivables (society_id, entity_id, entity_type, charge_type, description, 
                             amount, due_date, status, source_table, source_id, created_at)
    SELECT 
        acf.society_id, acf.apt_id, 'apartment', 'maintenance',
        'Maintenance - ' || a.flat_number,
        (a.apartment_size * acf.apt_maintenance_rate)::NUMERIC,
        (DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 day' * (COALESCE(acf.apt_due_day, 10)-1))::DATE,
        'pending', 'apt_charges_fines', acf.id, NOW()
    FROM apt_charges_fines acf
    JOIN apartments a ON a.id = acf.apt_id
    WHERE acf.society_id = p_society_id AND acf.apt_status = TRUE
      AND NOT EXISTS (SELECT 1 FROM receivables r 
                      WHERE r.source_table = 'apt_charges_fines' AND r.source_id = acf.id)
    ON CONFLICT DO NOTHING;
END;
$$;

CREATE OR REPLACE FUNCTION fn_auto_process_verified_payments(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
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
                --  OR ((r.entity_id = p.entity_id) AND (r.entity_type = p.entity_type) 
                --      AND r.amount = p.amount AND r.receipt_date = COALESCE(p.paid_at::DATE, CURRENT_DATE))
          )
    LOOP
        INSERT INTO receipts (society_id, user_id, entity_id, entity_type, receipt_date, acc_id,
            particulars, amount, mode, transaction_id, status, confirmed_by, confirmed_at, created_at)
        VALUES (rec_payment.society_id, rec_payment.confirmed_by, rec_payment.entity_id,
            rec_payment.entity_type, COALESCE(rec_payment.paid_at::DATE, CURRENT_DATE), 1,
            'Payment Received', rec_payment.amount, COALESCE(rec_payment.payment_method, 'cash'),
            rec_payment.transaction_id, 'confirmed', rec_payment.confirmed_by, rec_payment.confirmed_at, NOW());

        remaining_amount := rec_payment.amount;
        FOR rec_receivable IN 
            SELECT * FROM receivables r
            WHERE r.society_id = p_society_id AND r.entity_id = rec_payment.entity_id
              AND r.entity_type = rec_payment.entity_type AND r.status = 'pending'
            ORDER BY r.due_date ASC, r.id ASC
        LOOP
            IF remaining_amount <= 0 THEN EXIT; END IF;
            IF rec_receivable.amount <= remaining_amount THEN
                UPDATE receivables 
                SET status = 'confirmed', confirmed_by = rec_payment.confirmed_by, confirmed_at = rec_payment.confirmed_at
                WHERE id = rec_receivable.id;
                remaining_amount := remaining_amount - rec_receivable.amount;
            ELSE
                UPDATE receivables SET amount = rec_receivable.amount - remaining_amount WHERE id = rec_receivable.id;
                remaining_amount := 0;
            END IF;
        END LOOP;
    END LOOP;
END;
$$;

-- ═══ VENDORS ═══

DROP FUNCTION IF EXISTS fn_vendors_list CASCADE;
DROP FUNCTION IF EXISTS fn_auto_generate_vendor_receivables CASCADE;
DROP FUNCTION IF EXISTS fn_auto_process_vendor_payments CASCADE;

CREATE OR REPLACE FUNCTION fn_vendors_list(p_society_id INT, p_search TEXT DEFAULT NULL)
RETURNS TABLE (id INT, email VARCHAR, society_id INT, business_name TEXT, service_type VARCHAR,
    mobile VARCHAR, active BOOLEAN, pending_dues NUMERIC, paid_amount NUMERIC, active_passes INT)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM fn_auto_generate_vendor_receivables(p_society_id);
    PERFORM fn_auto_process_vendor_payments(p_society_id);
    RETURN QUERY
    WITH vendor_data AS (
        SELECT u.id, u.email, u.society_id, COALESCE(v.name, u.email) AS business_name,
               COALESCE(v.service_type, '—') AS service_type, COALESCE(v.mobile, '—') AS mobile,
               COALESCE(v.active, TRUE) AS active,
               (SELECT COUNT(*) FROM vendor_passes vp WHERE vp.society_id = u.society_id
                  AND vp.user_id = u.id AND vp.status = 'active' AND vp.valid_until >= CURRENT_DATE) AS active_passes
        FROM users u LEFT JOIN vendors v ON v.id = u.linked_id
        WHERE u.society_id = p_society_id AND u.role = 'vendor'
          AND (p_search IS NULL OR v.name ILIKE '%'||p_search||'%' OR u.email ILIKE '%'||p_search||'%')
    ),
    payment_summary AS (
        SELECT p.user_id,
               COALESCE(SUM(CASE WHEN p.status = 'verified' THEN p.amount ELSE 0 END), 0) AS paid_amount,
               COALESCE(SUM(CASE WHEN p.status IN ('pending','confirmed') THEN p.amount ELSE 0 END), 0) AS pending_dues
        FROM payments p WHERE p.society_id = p_society_id AND p.entity_type = 'vendor' GROUP BY p.user_id
    )
    SELECT vd.id, vd.email, vd.society_id, vd.business_name, vd.service_type, vd.mobile, vd.active,
           COALESCE(ps.pending_dues, 0), COALESCE(ps.paid_amount, 0), vd.active_passes
    FROM vendor_data vd LEFT JOIN payment_summary ps ON ps.user_id = vd.id ORDER BY vd.business_name;
END;
$$;

CREATE OR REPLACE FUNCTION fn_auto_generate_vendor_receivables(p_society_id INT) RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO receivables (society_id, entity_id, entity_type, charge_type, description, amount, due_date, status, source_table, source_id, created_at)
    SELECT vp.society_id, vp.user_id, 'vendor', 'vendor_pass',
           'Vendor Pass - ' || v.name || ' (' || vp.pass_type || ')', 500.00, vp.valid_until, 'pending',
           'vendor_passes', vp.id, NOW()
    FROM vendor_passes vp JOIN vendors v ON v.id = (SELECT linked_id FROM users WHERE id = vp.user_id)
    WHERE vp.society_id = p_society_id AND vp.status = 'active' AND vp.valid_until >= CURRENT_DATE
      AND NOT EXISTS (SELECT 1 FROM receivables r WHERE r.source_table = 'vendor_passes' AND r.source_id = vp.id)
    ON CONFLICT DO NOTHING;
END;
$$;

CREATE OR REPLACE FUNCTION fn_auto_process_vendor_payments(p_society_id INT) RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    rec_payment RECORD;
    remaining_amount NUMERIC;
    rec_receivable RECORD;
BEGIN
    FOR rec_payment IN SELECT * FROM payments p WHERE p.society_id = p_society_id AND p.entity_type = 'vendor'
        AND p.status = 'verified' AND NOT EXISTS (SELECT 1 FROM receipts r WHERE r.transaction_id = p.transaction_id)
    LOOP
        INSERT INTO receipts (society_id, user_id, entity_id, entity_type, receipt_date, acc_id, particulars, amount,
            mode, transaction_id, status, confirmed_by, confirmed_at, created_at)
        VALUES (rec_payment.society_id, rec_payment.confirmed_by, rec_payment.entity_id, rec_payment.entity_type,
            COALESCE(rec_payment.paid_at::DATE, CURRENT_DATE), 1, 'Vendor Payment', rec_payment.amount,
            COALESCE(rec_payment.payment_method, 'cash'), rec_payment.transaction_id, 'confirmed',
            rec_payment.confirmed_by, rec_payment.confirmed_at, NOW());
        remaining_amount := rec_payment.amount;
        FOR rec_receivable IN SELECT * FROM receivables r WHERE r.society_id = p_society_id
            AND r.entity_id = rec_payment.entity_id AND r.entity_type = 'vendor' AND r.status = 'pending'
            ORDER BY r.due_date ASC, r.id ASC
        LOOP
            IF remaining_amount <= 0 THEN EXIT; END IF;
            IF rec_receivable.amount <= remaining_amount THEN
                UPDATE receivables SET status = 'confirmed', confirmed_by = rec_payment.confirmed_by,
                    confirmed_at = rec_payment.confirmed_at WHERE id = rec_receivable.id;
                remaining_amount := remaining_amount - rec_receivable.amount;
            ELSE
                UPDATE receivables SET amount = rec_receivable.amount - remaining_amount WHERE id = rec_receivable.id;
                remaining_amount := 0;
            END IF;
        END LOOP;
    END LOOP;
END;
$$;

-- ═══ SECURITY ═══

DROP FUNCTION IF EXISTS fn_security_list CASCADE;
DROP FUNCTION IF EXISTS fn_auto_generate_security_receivables CASCADE;
DROP FUNCTION IF EXISTS fn_auto_process_security_payments CASCADE;
DROP FUNCTION IF EXISTS fn_security_roster_assign CASCADE;
DROP FUNCTION IF EXISTS fn_security_roster_today CASCADE;
DROP FUNCTION IF EXISTS fn_security_roster_report CASCADE;

CREATE OR REPLACE FUNCTION fn_security_list(p_society_id INT, p_search TEXT DEFAULT NULL)
RETURNS TABLE (id INT, email VARCHAR, society_id INT, name TEXT, shift VARCHAR, mobile VARCHAR, active BOOLEAN,
    salary_per_shift NUMERIC, joining_date DATE, days_worked BIGINT, salary_due NUMERIC, salary_paid NUMERIC,
    salary_pending NUMERIC, active_fines NUMERIC, current_status TEXT, today_duty TEXT)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM fn_auto_generate_security_receivables(p_society_id);
    PERFORM fn_auto_process_security_payments(p_society_id);
    RETURN QUERY
    WITH security_base AS (
        SELECT u.id, u.email, u.society_id, COALESCE(s.name, u.email) AS name, COALESCE(s.shift, '—') AS shift,
               COALESCE(s.mobile, '—') AS mobile, COALESCE(s.active, TRUE) AS active, s.salary_per_shift, s.joining_date,
               EXTRACT(DAY FROM AGE(CURRENT_DATE, COALESCE(s.joining_date, CURRENT_DATE)))::BIGINT AS days_worked
        FROM users u LEFT JOIN security_staff s ON s.id = u.linked_id
        WHERE u.society_id = p_society_id AND u.role = 'security'
          AND (p_search IS NULL OR s.name ILIKE '%'||p_search||'%')
    ),
    payment_summary AS (
        SELECT p.user_id, COALESCE(SUM(CASE WHEN p.status = 'verified' THEN p.amount ELSE 0 END), 0) AS salary_paid,
               COALESCE(SUM(CASE WHEN p.status IN ('pending','confirmed') THEN p.amount ELSE 0 END), 0) AS total_pending
        FROM payments p WHERE p.society_id = p_society_id AND p.entity_type = 'security' GROUP BY p.user_id
    ),
    fine_summary AS (
        SELECT u.id AS user_id, COALESCE(SUM(scf.security_fine), 0) AS active_fines
        FROM users u LEFT JOIN security_charges_fines scf ON scf.sec_id = u.linked_id
        WHERE u.society_id = p_society_id AND u.role = 'security' GROUP BY u.id
    )
    SELECT sb.id, sb.email, sb.society_id, sb.name, sb.shift, sb.mobile, sb.active, sb.salary_per_shift,
           sb.joining_date, sb.days_worked, sb.salary_per_shift * sb.days_worked,
           COALESCE(ps.salary_paid, 0),
           GREATEST((sb.salary_per_shift * sb.days_worked) - COALESCE(ps.salary_paid, 0), 0),
           COALESCE(fs.active_fines, 0), 'ACTIVE', 'OFF'
    FROM security_base sb LEFT JOIN payment_summary ps ON ps.user_id = sb.id
         LEFT JOIN fine_summary fs ON fs.user_id = sb.id ORDER BY sb.name;
END;
$$;

CREATE OR REPLACE FUNCTION fn_auto_generate_security_receivables(p_society_id INT) RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO receivables (society_id, entity_id, entity_type, charge_type, description, amount, due_date, status, source_table, source_id, created_at)
    SELECT scf.society_id, u.id, 'security', 'fine', 'Security Fine - ' || s.name, COALESCE(scf.security_fine, 0),
           CURRENT_DATE, 'pending', 'security_charges_fines', scf.id, NOW()
    FROM security_charges_fines scf JOIN security_staff s ON s.id = scf.sec_id
         JOIN users u ON u.linked_id = s.id AND u.role = 'security'
    WHERE scf.society_id = p_society_id AND scf.sec_status = TRUE AND COALESCE(scf.security_fine, 0) > 0
      AND NOT EXISTS (SELECT 1 FROM receivables r WHERE r.source_table = 'security_charges_fines' AND r.source_id = scf.id)
    ON CONFLICT DO NOTHING;
END;
$$;

CREATE OR REPLACE FUNCTION fn_auto_process_security_payments(p_society_id INT) RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    rec_payment RECORD;
    remaining_amount NUMERIC;
    rec_receivable RECORD;
BEGIN
    FOR rec_payment IN SELECT * FROM payments p WHERE p.society_id = p_society_id AND p.entity_type = 'security'
        AND p.status = 'verified' AND NOT EXISTS (SELECT 1 FROM receipts r WHERE r.transaction_id = p.transaction_id)
    LOOP
        INSERT INTO receipts (society_id, user_id, entity_id, entity_type, receipt_date, acc_id, particulars, amount,
            mode, transaction_id, status, confirmed_by, confirmed_at, created_at)
        VALUES (rec_payment.society_id, rec_payment.confirmed_by, rec_payment.entity_id, rec_payment.entity_type,
            COALESCE(rec_payment.paid_at::DATE, CURRENT_DATE), 1, 'Security Payment', rec_payment.amount,
            COALESCE(rec_payment.payment_method, 'cash'), rec_payment.transaction_id, 'confirmed',
            rec_payment.confirmed_by, rec_payment.confirmed_at, NOW());
        remaining_amount := rec_payment.amount;
        FOR rec_receivable IN SELECT * FROM receivables r WHERE r.society_id = p_society_id
            AND r.entity_id = rec_payment.entity_id AND r.entity_type = 'security' AND r.status = 'pending'
            ORDER BY r.due_date ASC, r.id ASC
        LOOP
            IF remaining_amount <= 0 THEN EXIT; END IF;
            IF rec_receivable.amount <= remaining_amount THEN
                UPDATE receivables SET status = 'confirmed', confirmed_by = rec_payment.confirmed_by,
                    confirmed_at = rec_payment.confirmed_at WHERE id = rec_receivable.id;
                remaining_amount := remaining_amount - rec_receivable.amount;
            ELSE
                UPDATE receivables SET amount = rec_receivable.amount - remaining_amount WHERE id = rec_receivable.id;
                remaining_amount := 0;
            END IF;
        END LOOP;
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION fn_security_roster_assign(p_society_id INT, p_security_id INT, p_roster_date DATE,
    p_shift_type VARCHAR DEFAULT 'morning', p_assigned_by INT DEFAULT NULL)
RETURNS TEXT LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO security_roster (society_id, security_id, roster_date, shift_type, assigned_by)
    VALUES (p_society_id, p_security_id, p_roster_date, p_shift_type, p_assigned_by)
    ON CONFLICT (society_id, security_id, roster_date) DO UPDATE SET shift_type = EXCLUDED.shift_type;
    RETURN 'Duty assigned';
END;
$$;

CREATE OR REPLACE FUNCTION fn_security_roster_today(p_society_id INT)
RETURNS TABLE (id INT, name TEXT, shift_type VARCHAR, mobile VARCHAR, status TEXT, time_in TIMESTAMP, time_out TIMESTAMP)
LANGUAGE SQL STABLE AS $$
    SELECT s.id, s.name, r.shift_type, s.mobile,
           CASE WHEN g.time_out IS NULL AND g.time_in IS NOT NULL THEN 'ON DUTY'
                WHEN g.time_in IS NOT NULL THEN 'COMPLETED' ELSE 'ABSENT' END AS status,
           g.time_in, g.time_out
    FROM security_roster r JOIN security_staff s ON s.id = r.security_id
    LEFT JOIN gate_access g ON g.entity_id = (SELECT id FROM users WHERE linked_id = s.id AND role = 'security')
        AND g.role = 's' AND g.time_in::DATE = CURRENT_DATE
    WHERE r.society_id = p_society_id AND r.roster_date = CURRENT_DATE
    ORDER BY r.shift_type, s.name;
$$;

CREATE OR REPLACE FUNCTION fn_security_roster_report(p_society_id INT, p_start_date DATE DEFAULT CURRENT_DATE - INTERVAL '30 days',
    p_end_date DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (security_id INT, name TEXT, total_assigned INT, days_present INT, attendance_rate NUMERIC,
    total_fines NUMERIC, total_salary_due NUMERIC)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT s.id, s.name, COUNT(r.id)::INT, COUNT(DISTINCT g.time_in::DATE)::INT,
           ROUND(COUNT(DISTINCT g.time_in::DATE)::NUMERIC / NULLIF(COUNT(r.id), 0) * 100, 2),
           COALESCE(SUM(scf.security_fine), 0), SUM(s.salary_per_shift) * COUNT(r.id)
    FROM security_staff s
    LEFT JOIN security_roster r ON r.security_id = s.id AND r.roster_date BETWEEN p_start_date AND p_end_date
    LEFT JOIN gate_access g ON g.entity_id = (SELECT id FROM users WHERE linked_id = s.id AND role='security')
        AND g.time_in::DATE = r.roster_date
    LEFT JOIN security_charges_fines scf ON scf.sec_id = s.id
    WHERE s.society_id = p_society_id
    GROUP BY s.id, s.name, s.salary_per_shift
    ORDER BY attendance_rate DESC;
END;
$$;

-- ═══ ASSETS ═══

DROP FUNCTION IF EXISTS fn_asset_set_from_account CASCADE;
DROP FUNCTION IF EXISTS fn_asset_list CASCADE;
DROP FUNCTION IF EXISTS fn_calculate_asset_depreciation CASCADE;

CREATE OR REPLACE FUNCTION fn_asset_set_from_account(p_asset_id INT, p_account_id INT)
RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE v_acc RECORD; v_asset_name VARCHAR;
BEGIN
    SELECT name, depreciation_percent, is_depreciable INTO v_acc FROM accounts WHERE id = p_account_id;
    IF NOT FOUND THEN RETURN 'Error: Account not found'; END IF;
    SELECT asset_name INTO v_asset_name FROM asset_register WHERE id = p_asset_id;
    UPDATE asset_register SET parent_account_id = p_account_id, depreciation_rate = v_acc.depreciation_percent
        WHERE id = p_asset_id;
    RETURN 'Asset linked to account';
END;
$$;

CREATE OR REPLACE FUNCTION fn_asset_list(p_society_id INT, p_search TEXT DEFAULT NULL)
RETURNS TABLE (id INT, asset_name VARCHAR, purchase_value NUMERIC, purchase_date DATE, account_name VARCHAR,
    depreciation_rate DECIMAL, expense_portion NUMERIC, asset_portion NUMERIC, current_book_value NUMERIC, status TEXT)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM fn_calculate_asset_depreciation(p_society_id);
    RETURN QUERY
    SELECT ar.id, ar.asset_name, ar.purchase_value, ar.purchase_date, COALESCE(acc.name, '—'),
           COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10.00),
           CASE WHEN COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) = 100 THEN ar.purchase_value
                WHEN EXTRACT(MONTH FROM ar.purchase_date) >= 9 THEN ar.purchase_value * (COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) / 100) * 0.5
                ELSE ar.purchase_value * (COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) / 100) END,
           GREATEST(ar.purchase_value * (1 - COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) / 100), 0),
           GREATEST(ar.purchase_value * (1 - COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) / 100), 0),
           CASE WHEN COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) = 100 THEN 'FULLY EXPENSED' ELSE 'ACTIVE' END
    FROM asset_register ar LEFT JOIN accounts acc ON acc.id = ar.parent_account_id
    WHERE ar.society_id = p_society_id AND (p_search IS NULL OR ar.asset_name ILIKE '%'||p_search||'%')
    ORDER BY ar.purchase_date DESC;
END;
$$;

CREATE OR REPLACE FUNCTION fn_calculate_asset_depreciation(p_society_id INT) RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE rec RECORD; dep_rate DECIMAL; expense_amount NUMERIC;
BEGIN
    FOR rec IN SELECT ar.*, COALESCE(acc.depreciation_percent, ar.depreciation_rate, 10) AS final_rate
        FROM asset_register ar LEFT JOIN accounts acc ON acc.id = ar.parent_account_id
        WHERE ar.society_id = p_society_id AND (ar.last_depreciation_date IS NULL OR ar.last_depreciation_date < CURRENT_DATE - INTERVAL '25 days')
    LOOP
        dep_rate := rec.final_rate;
        IF dep_rate = 100 THEN expense_amount := rec.purchase_value;
        ELSE expense_amount := rec.purchase_value * (dep_rate / 100);
        END IF;
        INSERT INTO expenses (society_id, user_id, entity_id, entity_type, expense_date, acc_id, particulars, amount, mode, status, created_at)
        VALUES (p_society_id, 1, rec.id, 'asset', CURRENT_DATE, COALESCE(rec.parent_account_id, 5),
                'Depreciation - ' || rec.asset_name, expense_amount, 'cash', 'pending', NOW());
        UPDATE asset_register SET last_depreciation_date = CURRENT_DATE WHERE id = rec.id;
    END LOOP;
END;
$$;

-- ═══ EVENTS, CONCERNS, ACCOUNTS, SOCIETIES, RECEIVABLES, CASHBOOK ═══

DROP FUNCTION IF EXISTS fn_events_list CASCADE;
DROP FUNCTION IF EXISTS fn_event_profile CASCADE;
DROP FUNCTION IF EXISTS fn_concerns_list CASCADE;
DROP FUNCTION IF EXISTS fn_concern_profile CASCADE;
DROP FUNCTION IF EXISTS fn_accounts_list CASCADE;
DROP FUNCTION IF EXISTS fn_account_profile CASCADE;
DROP FUNCTION IF EXISTS fn_societies_list CASCADE;
DROP FUNCTION IF EXISTS fn_society_profile CASCADE;
DROP FUNCTION IF EXISTS fn_receivables_list CASCADE;
DROP FUNCTION IF EXISTS fn_receivable_profile CASCADE;
DROP FUNCTION IF EXISTS fn_cashbook_list CASCADE;

CREATE OR REPLACE FUNCTION fn_events_list(p_society_id INT, p_search TEXT DEFAULT NULL, p_status VARCHAR DEFAULT NULL)
RETURNS TABLE (id INT, title VARCHAR, description TEXT, event_date DATE, event_time VARCHAR, venue VARCHAR,
    open_to VARCHAR, attendees_count INT, created_at TIMESTAMP)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT e.id, e.title, e.description, e.event_date, e.event_time, e.venue, e.open_to, 0::INT, e.created_at
    FROM events e
    WHERE e.society_id = p_society_id AND (p_search IS NULL OR e.title ILIKE '%'||p_search||'%')
      AND e.event_date >= CURRENT_DATE
    ORDER BY e.event_date ASC;
END;
$$;

CREATE OR REPLACE FUNCTION fn_event_profile(p_event_id INT)
RETURNS TABLE (id INT, society_id INT, title VARCHAR, description TEXT, event_date DATE, event_time VARCHAR,
    venue VARCHAR, open_to VARCHAR, created_at TIMESTAMP, subtitle VARCHAR)
LANGUAGE SQL STABLE AS $$
    SELECT id, society_id, title, description, event_date, event_time, venue, open_to, created_at,
           (event_date || ' ' || COALESCE(event_time, '')) AS subtitle
    FROM events WHERE id = p_event_id;
$$;

CREATE OR REPLACE FUNCTION fn_concerns_list(p_society_id INT, p_search TEXT DEFAULT NULL, p_status VARCHAR DEFAULT 'open')
RETURNS TABLE (id INT, flat_no VARCHAR, concern_type VARCHAR, description TEXT, status VARCHAR, assigned_to VARCHAR,
    priority VARCHAR, created_at TIMESTAMP)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT c.id, c.flat_no, c.concern_type, c.description, c.status, c.assigned_to,
           CASE WHEN c.status = 'resolved' THEN 'Low'
                WHEN EXTRACT(DAY FROM AGE(CURRENT_DATE, c.created_at)) > 7 THEN 'High'
                ELSE 'Medium' END, c.created_at
    FROM concerns c
    WHERE c.society_id = p_society_id AND (p_status IS NULL OR c.status = p_status)
      AND (p_search IS NULL OR c.flat_no ILIKE '%'||p_search||'%')
    ORDER BY CASE WHEN c.status = 'open' THEN 0 ELSE 1 END, c.created_at DESC;
END;
$$;

CREATE OR REPLACE FUNCTION fn_concern_profile(p_concern_id INT)
RETURNS TABLE (id INT, society_id INT, flat_no VARCHAR, concern_type VARCHAR, description TEXT, status VARCHAR,
    assigned_to VARCHAR, preferred_time VARCHAR, days_open BIGINT, created_at TIMESTAMP, subtitle VARCHAR)
LANGUAGE SQL STABLE AS $$
    SELECT id, society_id, flat_no, concern_type, description, status, assigned_to, preferred_time,
           EXTRACT(DAY FROM AGE(CURRENT_DATE, created_at))::BIGINT, created_at,
           'Flat ' || flat_no || ' - ' || concern_type
    FROM concerns WHERE id = p_concern_id;
$$;

CREATE OR REPLACE FUNCTION fn_accounts_list(p_society_id INT, p_search TEXT DEFAULT NULL, p_tab_name VARCHAR DEFAULT NULL)
RETURNS TABLE (id INT, name VARCHAR, tab_name VARCHAR, header VARCHAR, drcr_account VARCHAR, bf_amount NUMERIC,
    current_balance NUMERIC, transaction_count INT, parent_account_name VARCHAR)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    WITH account_balance AS (
        SELECT a.id, a.name, a.tab_name, a.header, a.drcr_account, a.bf_amount,
               COALESCE(SUM(CASE WHEN a.drcr_account = 'Cr' THEN t.amount ELSE -t.amount END), 0) + a.bf_amount,
               COUNT(t.id), COALESCE(p.name, '—')
        FROM accounts a LEFT JOIN accounts p ON p.id = a.parent_account_id
        LEFT JOIN transactions t ON t.acc_id = a.id AND t.status = 'paid'
        WHERE a.society_id = p_society_id AND (p_tab_name IS NULL OR a.tab_name = p_tab_name)
          AND (p_search IS NULL OR a.name ILIKE '%'||p_search||'%')
        GROUP BY a.id, a.name, a.tab_name, a.header, a.drcr_account, a.bf_amount, p.name
    )
    SELECT * FROM account_balance ORDER BY tab_name, name;
END;
$$;

CREATE OR REPLACE FUNCTION fn_account_profile(p_account_id INT)
RETURNS TABLE (id INT, society_id INT, name VARCHAR, tab_name VARCHAR, header VARCHAR, drcr_account VARCHAR,
    bf_amount NUMERIC, depreciation_percent NUMERIC, is_depreciable BOOLEAN, parent_account_name VARCHAR,
    current_balance NUMERIC, created_at TIMESTAMP)
LANGUAGE SQL STABLE AS $$
    SELECT a.id, a.society_id, a.name, a.tab_name, a.header, a.drcr_account, a.bf_amount,
           a.depreciation_percent, a.is_depreciable, COALESCE(p.name, '—'),
           COALESCE(SUM(CASE WHEN a.drcr_account = 'Cr' THEN t.amount ELSE -t.amount END), 0) + a.bf_amount,
           a.created_at
    FROM accounts a LEFT JOIN accounts p ON p.id = a.parent_account_id
    LEFT JOIN transactions t ON t.acc_id = a.id AND t.status = 'paid'
    WHERE a.id = p_account_id
    GROUP BY a.id, a.society_id, a.name, a.tab_name, a.header, a.drcr_account, a.bf_amount,
             a.depreciation_percent, a.is_depreciable, p.name, a.created_at;
$$;

CREATE OR REPLACE FUNCTION fn_societies_list(p_search TEXT DEFAULT NULL, p_plan VARCHAR DEFAULT NULL, p_status VARCHAR DEFAULT NULL)
RETURNS TABLE (id INT, name VARCHAR, email VARCHAR, phone VARCHAR, plan VARCHAR, plan_status VARCHAR, plan_validity DATE,
    total_apartments INT, total_users INT, total_receivables NUMERIC, created_at TIMESTAMP)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT s.id, s.name, s.email, s.phone, s.plan,
           CASE WHEN s.plan = 'Free' THEN 'Free' WHEN s.plan_validity >= CURRENT_DATE THEN 'Active' ELSE 'Expired' END,
           s.plan_validity,
           (SELECT COUNT(*) FROM apartments WHERE society_id = s.id AND active = TRUE),
           (SELECT COUNT(*) FROM users WHERE society_id = s.id),
           (SELECT COALESCE(SUM(amount), 0) FROM receivables WHERE society_id = s.id AND status = 'pending'),
           s.created_at
    FROM societies s
    WHERE (p_search IS NULL OR s.name ILIKE '%'||p_search||'%')
      AND (p_plan IS NULL OR s.plan = p_plan)
    ORDER BY s.name;
END;
$$;

CREATE OR REPLACE FUNCTION fn_society_profile(p_society_id INT)
RETURNS TABLE (id INT, name VARCHAR, logo VARCHAR, login_background VARCHAR, email VARCHAR, phone VARCHAR,
    address TEXT, plan VARCHAR, plan_status VARCHAR, plan_validity DATE, arrear_start_date DATE,
    secretary_name VARCHAR, secretary_phone VARCHAR, secretary_sign VARCHAR, total_apartments INT,
    total_vendors INT, total_security INT, total_users INT, total_receivables NUMERIC, created_at TIMESTAMP,
    _image_society_id INT)
LANGUAGE SQL STABLE AS $$
    SELECT s.id, s.name, s.logo, s.login_background, s.email, s.phone, s.address, s.plan,
           CASE WHEN s.plan = 'Free' THEN 'Free' WHEN s.plan_validity >= CURRENT_DATE THEN 'Active' ELSE 'Expired' END,
           s.plan_validity, s.arrear_start_date, s.secretary_name, s.secretary_phone, s.secretary_sign,
           (SELECT COUNT(*) FROM apartments WHERE society_id = s.id),
           (SELECT COUNT(*) FROM vendors WHERE society_id = s.id),
           (SELECT COUNT(*) FROM security_staff WHERE society_id = s.id),
           (SELECT COUNT(*) FROM users WHERE society_id = s.id),
           (SELECT COALESCE(SUM(amount), 0) FROM receivables WHERE society_id = s.id AND status = 'pending'),
           s.created_at, s.id
    FROM societies s WHERE s.id = p_society_id;
$$;

CREATE OR REPLACE FUNCTION fn_receivables_list(p_society_id INT, p_search TEXT DEFAULT NULL, p_status VARCHAR DEFAULT 'pending')
RETURNS TABLE (id INT, entity_type VARCHAR, entity_id INT, entity_name VARCHAR, charge_type VARCHAR, description TEXT,
    amount NUMERIC, due_date DATE, status VARCHAR, days_overdue INT, created_at TIMESTAMP)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    WITH entity_names AS (
        SELECT r.id, CASE WHEN r.entity_type = 'apartment' THEN 'Flat ' || (SELECT flat_number FROM apartments WHERE id = r.entity_id)
                         WHEN r.entity_type = 'vendor' THEN (SELECT name FROM vendors WHERE id = r.entity_id)
                         WHEN r.entity_type = 'security' THEN (SELECT name FROM security_staff WHERE id = r.entity_id)
                         ELSE 'Entity #' || r.entity_id END AS entity_name,
               r.entity_type, r.entity_id, r.charge_type, r.description, r.amount, r.due_date, r.status,
               EXTRACT(DAY FROM AGE(CURRENT_DATE, r.due_date))::INT AS days_overdue, r.created_at
        FROM receivables r WHERE r.society_id = p_society_id
          AND (p_status IS NULL OR r.status = p_status)
          AND (p_search IS NULL OR r.description ILIKE '%'||p_search||'%')
    )
    SELECT * FROM entity_names ORDER BY due_date ASC, created_at DESC;
END;
$$;

CREATE OR REPLACE FUNCTION fn_receivable_profile(p_receivable_id INT)
RETURNS TABLE (id INT, society_id INT, entity_type VARCHAR, entity_id INT, charge_type VARCHAR, description TEXT,
    amount NUMERIC, due_date DATE, status VARCHAR, source_table VARCHAR, source_id INT, confirmed_by INT,
    confirmed_at TIMESTAMP, created_at TIMESTAMP, days_overdue INT)
LANGUAGE SQL STABLE AS $$
    SELECT id, society_id, entity_type, entity_id, charge_type, description, amount, due_date, status,
           source_table, source_id, confirmed_by, confirmed_at, created_at,
           EXTRACT(DAY FROM AGE(CURRENT_DATE, due_date))::INT
    FROM receivables WHERE id = p_receivable_id;
$$;

CREATE OR REPLACE FUNCTION fn_cashbook_list(p_society_id INT, p_search TEXT DEFAULT NULL, p_start_date DATE DEFAULT NULL,
    p_end_date DATE DEFAULT NULL)
RETURNS TABLE (id INT, trx_date DATE, account_name VARCHAR, account_group VARCHAR, particulars VARCHAR,
    debit NUMERIC, credit NUMERIC, balance NUMERIC, mode VARCHAR, created_at TIMESTAMP)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_opening_balance NUMERIC;
BEGIN
    SELECT COALESCE(SUM(CASE WHEN drcr_bf = 'Cr' THEN bf_amount ELSE -bf_amount END), 0)
    INTO v_opening_balance FROM accounts WHERE society_id = p_society_id;
    RETURN QUERY
    WITH ordered_transactions AS (
        SELECT t.id, t.trx_date, a.name AS account_name, a.tab_name, t.acc_particulars, t.amount, t.mode, t.created_at,
               CASE WHEN a.drcr_account = 'Dr' THEN t.amount ELSE NULL::NUMERIC END AS debit,
               CASE WHEN a.drcr_account = 'Cr' THEN t.amount ELSE NULL::NUMERIC END AS credit,
               ROW_NUMBER() OVER (ORDER BY t.trx_date ASC, t.id ASC) AS row_num
        FROM transactions t JOIN accounts a ON a.id = t.acc_id
        WHERE t.society_id = p_society_id AND t.status = 'paid'
          AND (p_start_date IS NULL OR t.trx_date >= p_start_date)
          AND (p_end_date IS NULL OR t.trx_date <= p_end_date)
          AND (p_search IS NULL OR a.name ILIKE '%'||p_search||'%')
    )
    SELECT ot.id, ot.trx_date, ot.account_name, ot.tab_name, ot.acc_particulars, ot.debit, ot.credit,
           v_opening_balance + (SUM(COALESCE(ot.credit, 0) - COALESCE(ot.debit, 0)) OVER (ORDER BY ot.row_num)),
           ot.mode, ot.created_at
    FROM ordered_transactions ot ORDER BY ot.trx_date ASC, ot.id ASC;
END;
$$;
