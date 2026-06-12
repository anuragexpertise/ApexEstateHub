-- ============================================================
-- ESTATEHUB - COMPLETE DATABASE SCHEMA & FUNCTIONS
-- Production: Aiven PostgreSQL
-- Deploy: psql -U user -d database < estatehub.sql
-- ============================================================
-- SAFE TO RE-RUN: Uses IF NOT EXISTS throughout
-- Last Updated: 2026-06-10 (explicit typecasts added)
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
    plan VARCHAR(20) NOT NULL DEFAULT 'Free' CHECK (
        plan IN ('Free','9Apts','99Apts','999Apts','unlimited')
    ),
    plan_validity DATE NOT NULL DEFAULT CURRENT_DATE,
    arrear_start_date DATE NOT NULL DEFAULT CURRENT_DATE,
    login_background VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies(id) ON DELETE CASCADE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    pin_hash TEXT,
    pattern_hash TEXT,
    name VARCHAR(100),
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
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
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
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
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
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    photo VARCHAR(255),
    id_proof VARCHAR(255),
    mobile VARCHAR(15),
    joining_date DATE DEFAULT CURRENT_DATE,
    shift VARCHAR(20),
    salary_per_shift NUMERIC(10,2),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id),
    entity_id INT,
    entity_type VARCHAR(20) CHECK (entity_type IN ('apartment','vendor','security','other')),
    amount NUMERIC(10,2) NOT NULL,
    payment_type VARCHAR(50),
    payment_method VARCHAR(50),
    transaction_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','confirmed','verified','failed','cancelled')),
    due_date DATE,
    paid_at TIMESTAMP,
    source_table VARCHAR(50),
    source_id INT,
    confirmed_by INT REFERENCES users(id),
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS attendance (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    security_id INT NOT NULL REFERENCES security_staff(id) ON DELETE CASCADE,
    time_in TIMESTAMP,
    time_out TIMESTAMP
);

CREATE TABLE IF NOT EXISTS apt_charges_fines (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    apt_id INT NOT NULL REFERENCES apartments(id) ON DELETE CASCADE,
    start_date DATE NOT NULL,
    end_date DATE,
    apt_maintenance_rate NUMERIC(10,4) NOT NULL DEFAULT 3.0,
    apt_due_day INTEGER DEFAULT 10,
    apt_delay_fine NUMERIC(10,2) DEFAULT 0,
    apt_fine NUMERIC(10,2) DEFAULT 0,
    apt_status BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ven_charges_fines (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    ven_id INT NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    start_date DATE NOT NULL,
    end_date DATE,
    vendor_1day NUMERIC(10,2) DEFAULT 0,
    vendor_7day NUMERIC(10,2) DEFAULT 0,
    vendor_1mth NUMERIC(10,2) DEFAULT 0,
    vendor_fine NUMERIC(10,2) DEFAULT 0,
    ven_status BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sec_charges_fines (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    sec_id INT NOT NULL REFERENCES security_staff(id) ON DELETE CASCADE,
    start_date DATE NOT NULL,
    end_date DATE,
    security_fine NUMERIC(10,2) DEFAULT 0,
    sec_status BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gate_access (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    role VARCHAR(1),
    entity_id INTEGER NOT NULL,
    time_in TIMESTAMP NOT NULL DEFAULT NOW(),
    time_out TIMESTAMP
);

CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    tab_name VARCHAR(20),
    header VARCHAR(50),
    parent_account_id INT,
    drcr_account VARCHAR(2) CHECK (drcr_account IN ('Dr','Cr',NULL)),
    has_bf BOOLEAN DEFAULT FALSE,
    drcr_bf VARCHAR(2) CHECK (drcr_bf IN ('Dr','Cr')) NOT NULL,
    bf_amount NUMERIC(12,2) DEFAULT 0.00,
    depreciation_percent NUMERIC(5,2) DEFAULT 100.00,
    is_depreciable BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_account_society_name UNIQUE (society_id, name),
    CONSTRAINT fk_account_parent FOREIGN KEY (parent_account_id) REFERENCES accounts(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    trx_date DATE NOT NULL,
    acc_id INT REFERENCES accounts(id),
    entity_id INTEGER,
    acc_particulars VARCHAR(100),
    amount NUMERIC(15,2) NOT NULL CHECK (amount > 0),
    mode VARCHAR(6) DEFAULT 'cash' CHECK (mode IN ('cash','cheque','upi','card','bank','crypto')),
    payment_gateway_ID VARCHAR(20),
    status VARCHAR(20) NOT NULL DEFAULT 'paid',
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS asset_register (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    asset_name VARCHAR(100),
    purchase_value NUMERIC(12,2),
    purchase_date DATE,
    parent_account_id INT REFERENCES accounts(id),
    depreciation_rate NUMERIC(5,2),
    last_depreciation_date DATE
);

CREATE TABLE IF NOT EXISTS receivables (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id),
    entity_id INT NOT NULL,
    entity_type VARCHAR(20) NOT NULL CHECK (entity_type IN ('apartment','vendor','security')),
    charge_type VARCHAR(50) NOT NULL,
    description TEXT,
    amount NUMERIC(10,2) NOT NULL CHECK (amount > 0),
    due_date DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','confirmed','cancelled')),
    source_table VARCHAR(50),
    source_id INT,
    confirmed_by INT REFERENCES users(id),
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS receipts (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id),
    entity_id INT,
    entity_type VARCHAR(20) CHECK (entity_type IN ('apartment','vendor','security','other')),
    receipt_date DATE NOT NULL,
    acc_id INT REFERENCES accounts(id),
    particulars TEXT NOT NULL,
    amount NUMERIC(10,2) NOT NULL CHECK (amount > 0),
    mode VARCHAR(20) DEFAULT 'cash' CHECK (mode IN ('cash','cheque','upi','card','bank','crypto')),
    cheque_no VARCHAR(50),
    transaction_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','confirmed','cancelled')),
    confirmed_by INT REFERENCES users(id),
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id),
    entity_id INT,
    entity_type VARCHAR(20) CHECK (entity_type IN ('vendor','security','other','assets')),
    expense_date DATE NOT NULL,
    acc_id INT REFERENCES accounts(id),
    particulars TEXT NOT NULL,
    amount NUMERIC(10,2) NOT NULL CHECK (amount > 0),
    mode VARCHAR(20) DEFAULT 'cash' CHECK (mode IN ('cash','cheque','upi','card','bank','crypto')),
    cheque_no VARCHAR(50),
    transaction_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','confirmed','cancelled')),
    confirmed_by INT REFERENCES users(id),
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
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
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
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
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    user_id INT NOT NULL REFERENCES users(id),
    pass_type VARCHAR(50) DEFAULT 'temporary',
    issued_date DATE DEFAULT CURRENT_DATE,
    valid_until DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (society_id, user_id, issued_date)
);

CREATE TABLE IF NOT EXISTS security_roster (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    security_id INT NOT NULL REFERENCES security_staff(id) ON DELETE CASCADE,
    roster_date DATE NOT NULL,
    shift_type VARCHAR(20) CHECK (shift_type IN ('morning','evening','night')),
    assigned_by INT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (society_id, security_id, roster_date)
);

CREATE TABLE IF NOT EXISTS role_permissions (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    card_id VARCHAR(100) NOT NULL,
    permission VARCHAR(20) NOT NULL CHECK (permission IN ('view','create','edit','delete')),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (society_id, role, card_id, permission)
);

-- ════════════════════════════════════════════════════════════════
-- SECTION 2: INDEXES
-- ════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_society_role ON users(society_id, role);
CREATE INDEX IF NOT EXISTS idx_apartments_society ON apartments(society_id);
CREATE INDEX IF NOT EXISTS idx_apartments_active ON apartments(society_id, active);
CREATE INDEX IF NOT EXISTS idx_vendors_society ON vendors(society_id);
CREATE INDEX IF NOT EXISTS idx_security_society ON security_staff(society_id);
CREATE INDEX IF NOT EXISTS idx_accounts_society ON accounts(society_id);
CREATE INDEX IF NOT EXISTS idx_transactions_society_date ON transactions(society_id, trx_date DESC);
CREATE INDEX IF NOT EXISTS idx_payments_society_status ON payments(society_id, status);
CREATE INDEX IF NOT EXISTS idx_receipts_society_status ON receipts(society_id, status);
CREATE INDEX IF NOT EXISTS idx_expenses_society_status ON expenses(society_id, status);
CREATE INDEX IF NOT EXISTS idx_receivables_society_status ON receivables(society_id, status);
CREATE INDEX IF NOT EXISTS idx_events_society_date ON events(society_id, event_date);
CREATE INDEX IF NOT EXISTS idx_concerns_society_status ON concerns(society_id, status);
CREATE INDEX IF NOT EXISTS idx_gate_society_time ON gate_access(society_id, time_in);
CREATE INDEX IF NOT EXISTS idx_security_roster_date ON security_roster(society_id, roster_date);

-- ════════════════════════════════════════════════════════════════
-- SECTION 3: BUSINESS LOGIC FUNCTIONS  (explicit typecasts)
-- ════════════════════════════════════════════════════════════════

-- ═══ APARTMENTS ═══

DROP FUNCTION IF EXISTS fn_apartments_list CASCADE;
DROP FUNCTION IF EXISTS fn_auto_generate_receivables CASCADE;
DROP FUNCTION IF EXISTS fn_auto_process_verified_payments CASCADE;

CREATE OR REPLACE FUNCTION fn_auto_generate_receivables(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO receivables (society_id, entity_id, entity_type, charge_type, description,
                             amount, due_date, status, source_table, source_id, created_at)
    SELECT
        acf.society_id::INT,
        acf.apt_id::INT,
        'apartment'::VARCHAR(20),
        'maintenance'::VARCHAR(50),
        ('Maintenance - ' || a.flat_number)::TEXT,
        (a.apartment_size * acf.apt_maintenance_rate)::NUMERIC(10,2),
        (DATE_TRUNC('month', CURRENT_DATE)
            + (INTERVAL '1 day' * (COALESCE(acf.apt_due_day, 10) - 1)))::DATE,
        'pending'::VARCHAR(20),
        'apt_charges_fines'::VARCHAR(50),
        acf.id::INT,
        NOW()::TIMESTAMP
    FROM apt_charges_fines acf
    JOIN apartments a ON a.id = acf.apt_id
    WHERE acf.society_id = p_society_id
      AND acf.apt_status = TRUE
      AND NOT EXISTS (
          SELECT 1 FROM receivables r
          WHERE r.source_table = 'apt_charges_fines'
            AND r.source_id = acf.id
      )
    ON CONFLICT DO NOTHING;
END;
$$;

CREATE OR REPLACE FUNCTION fn_auto_process_verified_payments(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    rec_payment    RECORD;
    remaining_amt  NUMERIC(15,2);
    rec_receivable RECORD;
BEGIN
    FOR rec_payment IN
        SELECT * FROM payments p
        WHERE p.society_id = p_society_id
          AND p.status = 'verified'
          AND NOT EXISTS (
              SELECT 1 FROM receipts r
              WHERE r.transaction_id = p.transaction_id
          )
    LOOP
        INSERT INTO receipts (society_id, user_id, entity_id, entity_type,
            receipt_date, acc_id, particulars, amount, mode,
            transaction_id, status, confirmed_by, confirmed_at, created_at)
        VALUES (
            rec_payment.society_id::INT,
            rec_payment.confirmed_by::INT,
            rec_payment.entity_id::INT,
            rec_payment.entity_type::VARCHAR(20),
            COALESCE(rec_payment.paid_at::DATE, CURRENT_DATE)::DATE,
            1::INT,
            'Payment Received'::TEXT,
            rec_payment.amount::NUMERIC(10,2),
            COALESCE(rec_payment.payment_method, 'cash')::VARCHAR(20),
            rec_payment.transaction_id::VARCHAR(255),
            'confirmed'::VARCHAR(20),
            rec_payment.confirmed_by::INT,
            rec_payment.confirmed_at::TIMESTAMP,
            NOW()::TIMESTAMP
        );

        remaining_amt := rec_payment.amount::NUMERIC(15,2);

        FOR rec_receivable IN
            SELECT * FROM receivables r
            WHERE r.society_id = p_society_id
              AND r.entity_id   = rec_payment.entity_id
              AND r.entity_type = rec_payment.entity_type
              AND r.status = 'pending'
            ORDER BY r.due_date ASC, r.id ASC
        LOOP
            IF remaining_amt <= 0 THEN EXIT; END IF;
            IF rec_receivable.amount <= remaining_amt THEN
                UPDATE receivables
                SET status       = 'confirmed'::VARCHAR(20),
                    confirmed_by = rec_payment.confirmed_by::INT,
                    confirmed_at = rec_payment.confirmed_at::TIMESTAMP
                WHERE id = rec_receivable.id;
                remaining_amt := remaining_amt - rec_receivable.amount;
            ELSE
                UPDATE receivables
                SET amount = (rec_receivable.amount - remaining_amt)::NUMERIC(10,2)
                WHERE id = rec_receivable.id;
                remaining_amt := 0;
            END IF;
        END LOOP;
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION fn_apartments_list(
    p_society_id  INT,
    p_search      TEXT    DEFAULT NULL,
    p_has_dues    BOOLEAN DEFAULT NULL
)
RETURNS TABLE (
    id                INT,
    flat_number       VARCHAR(20),
    owner_name        VARCHAR(100),
    mobile            VARCHAR(15),
    apartment_size    INT,
    active            BOOLEAN,
    society_id        INT,
    months_due        BIGINT,
    total_maintenance NUMERIC(15,2),
    paid_amount       NUMERIC(15,2),
    pending_dues      NUMERIC(15,2),
    late_fee          NUMERIC(15,2),
    grand_total       NUMERIC(15,2)
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM fn_auto_generate_receivables(p_society_id);
    PERFORM fn_auto_process_verified_payments(p_society_id);

    RETURN QUERY
    WITH apartment_base AS (
        SELECT
            a.id::INT,
            a.flat_number::VARCHAR(20),
            a.owner_name::VARCHAR(100),
            a.mobile::VARCHAR(15),
            a.apartment_size::INT,
            a.active::BOOLEAN,
            a.society_id::INT,
            COALESCE(acf.apt_maintenance_rate, 3.0)::NUMERIC(10,4) AS rate_per_sqft,
            acf.start_date::DATE
        FROM apartments a
        LEFT JOIN apt_charges_fines acf
               ON acf.apt_id = a.id AND acf.apt_status = TRUE
        WHERE a.society_id = p_society_id
          AND (p_search IS NULL
               OR a.flat_number ILIKE '%'||p_search||'%'
               OR a.owner_name  ILIKE '%'||p_search||'%')
    ),
    maintenance_calc AS (
        SELECT *,
               GREATEST(
                   EXTRACT(YEAR  FROM AGE(CURRENT_DATE, COALESCE(start_date, CURRENT_DATE))) * 12
                   + EXTRACT(MONTH FROM AGE(CURRENT_DATE, COALESCE(start_date, CURRENT_DATE))),
                   0
               )::BIGINT AS months_due
        FROM apartment_base
    ),
    payments_summary AS (
        SELECT
            p.entity_id::INT AS apartment_id,
            COALESCE(SUM(CASE WHEN p.status = 'verified'              THEN p.amount ELSE 0 END), 0)::NUMERIC(15,2) AS paid_amount,
            COALESCE(SUM(CASE WHEN p.status IN ('pending','confirmed') THEN p.amount ELSE 0 END), 0)::NUMERIC(15,2) AS pending_amount
        FROM payments p
        WHERE p.society_id = p_society_id AND p.entity_type = 'apartment'
        GROUP BY p.entity_id
    ),
    late_fee_calc AS (
        SELECT
            p.entity_id::INT AS apartment_id,
            COALESCE(SUM(
                CASE WHEN p.due_date < CURRENT_DATE
                     THEN p.amount * 0.02
                          * GREATEST(EXTRACT(DAY FROM AGE(CURRENT_DATE, p.due_date)), 0) / 30
                     ELSE 0 END
            ), 0)::NUMERIC(15,2) AS late_fee
        FROM payments p
        WHERE p.society_id = p_society_id
          AND p.entity_type = 'apartment'
          AND p.status IN ('pending','confirmed')
        GROUP BY p.entity_id
    )
    SELECT
        mc.id::INT,
        mc.flat_number::VARCHAR(20),
        mc.owner_name::VARCHAR(100),
        mc.mobile::VARCHAR(15),
        mc.apartment_size::INT,
        mc.active::BOOLEAN,
        mc.society_id::INT,
        mc.months_due::BIGINT,
        (mc.apartment_size * mc.rate_per_sqft * GREATEST(mc.months_due, 0))::NUMERIC(15,2),
        COALESCE(ps.paid_amount,    0)::NUMERIC(15,2),
        COALESCE(ps.pending_amount, 0)::NUMERIC(15,2),
        COALESCE(lf.late_fee,       0)::NUMERIC(15,2),
        (mc.apartment_size * mc.rate_per_sqft * GREATEST(mc.months_due, 0)
         - COALESCE(ps.paid_amount, 0)
         + COALESCE(lf.late_fee,    0))::NUMERIC(15,2)
    FROM maintenance_calc mc
    LEFT JOIN payments_summary ps ON ps.apartment_id = mc.id
    LEFT JOIN late_fee_calc    lf ON lf.apartment_id = mc.id
    WHERE (p_has_dues IS NULL
        OR (p_has_dues       AND (COALESCE(ps.pending_amount,0) + COALESCE(lf.late_fee,0)) > 0)
        OR (NOT p_has_dues   AND (COALESCE(ps.pending_amount,0) + COALESCE(lf.late_fee,0)) = 0))
    ORDER BY mc.flat_number;
END;
$$;

-- ═══ VENDORS ═══

DROP FUNCTION IF EXISTS fn_vendors_list CASCADE;
DROP FUNCTION IF EXISTS fn_auto_generate_vendor_receivables CASCADE;
DROP FUNCTION IF EXISTS fn_auto_process_vendor_payments CASCADE;

CREATE OR REPLACE FUNCTION fn_auto_generate_vendor_receivables(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO receivables (society_id, entity_id, entity_type, charge_type, description,
                             amount, due_date, status, source_table, source_id, created_at)
    SELECT
        vp.society_id::INT,
        vp.user_id::INT,
        'vendor'::VARCHAR(20),
        'vendor_pass'::VARCHAR(50),
        ('Vendor Pass - ' || v.name || ' (' || vp.pass_type || ')')::TEXT,
        500.00::NUMERIC(10,2),
        vp.valid_until::DATE,
        'pending'::VARCHAR(20),
        'vendor_passes'::VARCHAR(50),
        vp.id::INT,
        NOW()::TIMESTAMP
    FROM vendor_passes vp
    JOIN vendors v ON v.id = (SELECT linked_id FROM users WHERE id = vp.user_id)
    WHERE vp.society_id = p_society_id
      AND vp.status = 'active'
      AND vp.valid_until >= CURRENT_DATE
      AND NOT EXISTS (
          SELECT 1 FROM receivables r
          WHERE r.source_table = 'vendor_passes' AND r.source_id = vp.id
      )
    ON CONFLICT DO NOTHING;
END;
$$;

CREATE OR REPLACE FUNCTION fn_auto_process_vendor_payments(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    rec_payment    RECORD;
    remaining_amt  NUMERIC(15,2);
    rec_receivable RECORD;
BEGIN
    FOR rec_payment IN
        SELECT * FROM payments p
        WHERE p.society_id = p_society_id
          AND p.entity_type = 'vendor'
          AND p.status = 'verified'
          AND NOT EXISTS (SELECT 1 FROM receipts r WHERE r.transaction_id = p.transaction_id)
    LOOP
        INSERT INTO receipts (society_id, user_id, entity_id, entity_type,
            receipt_date, acc_id, particulars, amount, mode,
            transaction_id, status, confirmed_by, confirmed_at, created_at)
        VALUES (
            rec_payment.society_id::INT,
            rec_payment.confirmed_by::INT,
            rec_payment.entity_id::INT,
            rec_payment.entity_type::VARCHAR(20),
            COALESCE(rec_payment.paid_at::DATE, CURRENT_DATE)::DATE,
            1::INT,
            'Vendor Payment'::TEXT,
            rec_payment.amount::NUMERIC(10,2),
            COALESCE(rec_payment.payment_method, 'cash')::VARCHAR(20),
            rec_payment.transaction_id::VARCHAR(255),
            'confirmed'::VARCHAR(20),
            rec_payment.confirmed_by::INT,
            rec_payment.confirmed_at::TIMESTAMP,
            NOW()::TIMESTAMP
        );

        remaining_amt := rec_payment.amount::NUMERIC(15,2);

        FOR rec_receivable IN
            SELECT * FROM receivables r
            WHERE r.society_id = p_society_id
              AND r.entity_id   = rec_payment.entity_id
              AND r.entity_type = 'vendor'
              AND r.status = 'pending'
            ORDER BY r.due_date ASC, r.id ASC
        LOOP
            IF remaining_amt <= 0 THEN EXIT; END IF;
            IF rec_receivable.amount <= remaining_amt THEN
                UPDATE receivables
                SET status       = 'confirmed'::VARCHAR(20),
                    confirmed_by = rec_payment.confirmed_by::INT,
                    confirmed_at = rec_payment.confirmed_at::TIMESTAMP
                WHERE id = rec_receivable.id;
                remaining_amt := remaining_amt - rec_receivable.amount;
            ELSE
                UPDATE receivables
                SET amount = (rec_receivable.amount - remaining_amt)::NUMERIC(10,2)
                WHERE id = rec_receivable.id;
                remaining_amt := 0;
            END IF;
        END LOOP;
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION fn_vendors_list(
    p_society_id INT,
    p_search     TEXT DEFAULT NULL
)
RETURNS TABLE (
    id           INT,
    email        VARCHAR(100),
    society_id   INT,
    name         VARCHAR(100),
    service_type VARCHAR(100),
    mobile       VARCHAR(15),
    active       BOOLEAN,
    pending_dues NUMERIC(15,2),
    paid_amount  NUMERIC(15,2),
    active_passes INT
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM fn_auto_generate_vendor_receivables(p_society_id);
    PERFORM fn_auto_process_vendor_payments(p_society_id);

    RETURN QUERY
    WITH vendor_data AS (
        SELECT
            u.id::INT,
            u.email::VARCHAR(100),
            u.society_id::INT,
            COALESCE(v.name, u.email)::VARCHAR(100)       AS name,
            COALESCE(v.service_type, '—')::VARCHAR(100)   AS service_type,
            COALESCE(v.mobile, '—')::VARCHAR(15)          AS mobile,
            COALESCE(v.active, TRUE)::BOOLEAN              AS active,
            (SELECT COUNT(*)::INT
             FROM vendor_passes vp
             WHERE vp.society_id = u.society_id
               AND vp.user_id    = u.id
               AND vp.status     = 'active'
               AND vp.valid_until >= CURRENT_DATE)::INT    AS active_passes
        FROM users u
        LEFT JOIN vendors v ON v.id = u.linked_id
        WHERE u.society_id = p_society_id
          AND u.role = 'vendor'
          AND (p_search IS NULL
               OR v.name  ILIKE '%'||p_search||'%'
               OR u.email ILIKE '%'||p_search||'%')
    ),
    payment_summary AS (
        SELECT
            p.user_id::INT,
            COALESCE(SUM(CASE WHEN p.status = 'verified'              THEN p.amount ELSE 0 END), 0)::NUMERIC(15,2) AS paid_amount,
            COALESCE(SUM(CASE WHEN p.status IN ('pending','confirmed') THEN p.amount ELSE 0 END), 0)::NUMERIC(15,2) AS pending_dues
        FROM payments p
        WHERE p.society_id  = p_society_id
          AND p.entity_type = 'vendor'
        GROUP BY p.user_id
    )
    SELECT
        vd.id, vd.email, vd.society_id, vd.name, vd.service_type, vd.mobile, vd.active,
        COALESCE(ps.pending_dues, 0)::NUMERIC(15,2),
        COALESCE(ps.paid_amount,  0)::NUMERIC(15,2),
        vd.active_passes
    FROM vendor_data vd
    LEFT JOIN payment_summary ps ON ps.user_id = vd.id
    ORDER BY vd.name;
END;
$$;

-- ═══ SECURITY ═══

DROP FUNCTION IF EXISTS fn_security_list CASCADE;
DROP FUNCTION IF EXISTS fn_auto_generate_security_receivables CASCADE;
DROP FUNCTION IF EXISTS fn_auto_process_security_payments CASCADE;
DROP FUNCTION IF EXISTS fn_security_roster_assign CASCADE;
DROP FUNCTION IF EXISTS fn_security_roster_today CASCADE;
DROP FUNCTION IF EXISTS fn_security_roster_report CASCADE;

CREATE OR REPLACE FUNCTION fn_auto_generate_security_receivables(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO receivables (society_id, entity_id, entity_type, charge_type, description,
                             amount, due_date, status, source_table, source_id, created_at)
    SELECT
        scf.society_id::INT,
        u.id::INT,
        'security'::VARCHAR(20),
        'fine'::VARCHAR(50),
        ('Security Fine - ' || s.name)::TEXT,
        COALESCE(scf.security_fine, 0)::NUMERIC(10,2),
        CURRENT_DATE::DATE,
        'pending'::VARCHAR(20),
        'security_charges_fines'::VARCHAR(50),
        scf.id::INT,
        NOW()::TIMESTAMP
    FROM security_charges_fines scf
    JOIN security_staff s ON s.id = scf.sec_id
    JOIN users u ON u.linked_id = s.id AND u.role = 'security'
    WHERE scf.society_id = p_society_id
      AND scf.sec_status = TRUE
      AND COALESCE(scf.security_fine, 0) > 0
      AND NOT EXISTS (
          SELECT 1 FROM receivables r
          WHERE r.source_table = 'security_charges_fines' AND r.source_id = scf.id
      )
    ON CONFLICT DO NOTHING;
END;
$$;

CREATE OR REPLACE FUNCTION fn_auto_process_security_payments(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    rec_payment    RECORD;
    remaining_amt  NUMERIC(15,2);
    rec_receivable RECORD;
BEGIN
    FOR rec_payment IN
        SELECT * FROM payments p
        WHERE p.society_id  = p_society_id
          AND p.entity_type = 'security'
          AND p.status      = 'verified'
          AND NOT EXISTS (SELECT 1 FROM receipts r WHERE r.transaction_id = p.transaction_id)
    LOOP
        INSERT INTO receipts (society_id, user_id, entity_id, entity_type,
            receipt_date, acc_id, particulars, amount, mode,
            transaction_id, status, confirmed_by, confirmed_at, created_at)
        VALUES (
            rec_payment.society_id::INT,
            rec_payment.confirmed_by::INT,
            rec_payment.entity_id::INT,
            rec_payment.entity_type::VARCHAR(20),
            COALESCE(rec_payment.paid_at::DATE, CURRENT_DATE)::DATE,
            1::INT,
            'Security Payment'::TEXT,
            rec_payment.amount::NUMERIC(10,2),
            COALESCE(rec_payment.payment_method, 'cash')::VARCHAR(20),
            rec_payment.transaction_id::VARCHAR(255),
            'confirmed'::VARCHAR(20),
            rec_payment.confirmed_by::INT,
            rec_payment.confirmed_at::TIMESTAMP,
            NOW()::TIMESTAMP
        );

        remaining_amt := rec_payment.amount::NUMERIC(15,2);

        FOR rec_receivable IN
            SELECT * FROM receivables r
            WHERE r.society_id  = p_society_id
              AND r.entity_id   = rec_payment.entity_id
              AND r.entity_type = 'security'
              AND r.status = 'pending'
            ORDER BY r.due_date ASC, r.id ASC
        LOOP
            IF remaining_amt <= 0 THEN EXIT; END IF;
            IF rec_receivable.amount <= remaining_amt THEN
                UPDATE receivables
                SET status       = 'confirmed'::VARCHAR(20),
                    confirmed_by = rec_payment.confirmed_by::INT,
                    confirmed_at = rec_payment.confirmed_at::TIMESTAMP
                WHERE id = rec_receivable.id;
                remaining_amt := remaining_amt - rec_receivable.amount;
            ELSE
                UPDATE receivables
                SET amount = (rec_receivable.amount - remaining_amt)::NUMERIC(10,2)
                WHERE id = rec_receivable.id;
                remaining_amt := 0;
            END IF;
        END LOOP;
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION fn_security_list(
    p_society_id INT,
    p_search     TEXT DEFAULT NULL
)
RETURNS TABLE (
    id               INT,
    email            VARCHAR(100),
    society_id       INT,
    name             VARCHAR(100),
    shift            VARCHAR(20),
    mobile           VARCHAR(15),
    active           BOOLEAN,
    salary_per_shift NUMERIC(10,2),
    joining_date     DATE,
    days_worked      BIGINT,
    salary_due       NUMERIC(15,2),
    salary_paid      NUMERIC(15,2),
    salary_pending   NUMERIC(15,2),
    active_fines     NUMERIC(15,2),
    on_duty          VARCHAR(20),
    attendance       VARCHAR(20)
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM fn_auto_generate_security_receivables(p_society_id);
    PERFORM fn_auto_process_security_payments(p_society_id);

    RETURN QUERY
    WITH security_base AS (
        SELECT
            u.id::INT,
            u.email::VARCHAR(100),
            u.society_id::INT,
            COALESCE(s.name, u.email)::VARCHAR(100)  AS name,
            COALESCE(s.shift, '—')::VARCHAR(20)       AS shift,
            COALESCE(s.mobile, '—')::VARCHAR(15)      AS mobile,
            COALESCE(s.active, TRUE)::BOOLEAN          AS active,
            COALESCE(s.salary_per_shift, 0)::NUMERIC(10,2) AS salary_per_shift,
            s.joining_date::DATE,
            GREATEST(
                EXTRACT(DAY FROM AGE(CURRENT_DATE, COALESCE(s.joining_date, CURRENT_DATE))),
                0
            )::BIGINT AS days_worked
        FROM users u
        LEFT JOIN security_staff s ON s.id = u.linked_id
        WHERE u.society_id = p_society_id
          AND u.role = 'security'
          AND (p_search IS NULL OR s.name ILIKE '%'||p_search||'%')
    ),
    payment_summary AS (
        SELECT
            p.user_id::INT,
            COALESCE(SUM(CASE WHEN p.status = 'verified'              THEN p.amount ELSE 0 END), 0)::NUMERIC(15,2) AS salary_paid,
            COALESCE(SUM(CASE WHEN p.status IN ('pending','confirmed') THEN p.amount ELSE 0 END), 0)::NUMERIC(15,2) AS total_pending
        FROM payments p
        WHERE p.society_id  = p_society_id
          AND p.entity_type = 'security'
        GROUP BY p.user_id
    ),
    fine_summary AS (
        SELECT
            u.id::INT AS user_id,
            COALESCE(SUM(scf.security_fine), 0)::NUMERIC(15,2) AS active_fines
        FROM users u
        LEFT JOIN security_charges_fines scf ON scf.sec_id = u.linked_id
        WHERE u.society_id = p_society_id AND u.role = 'security'
        GROUP BY u.id
    )
    SELECT
        sb.id,
        sb.email,
        sb.society_id,
        sb.name,
        sb.shift,
        sb.mobile,
        sb.active,
        sb.salary_per_shift,
        sb.joining_date,
        sb.days_worked,
        (sb.salary_per_shift * sb.days_worked)::NUMERIC(15,2),
        COALESCE(ps.salary_paid, 0)::NUMERIC(15,2),
        GREATEST((sb.salary_per_shift * sb.days_worked) - COALESCE(ps.salary_paid, 0), 0)::NUMERIC(15,2),
        COALESCE(fs.active_fines, 0)::NUMERIC(15,2),
        'ACTIVE'::VARCHAR(20),
        'OFF'::VARCHAR(20)
    FROM security_base sb
    LEFT JOIN payment_summary ps ON ps.user_id = sb.id
    LEFT JOIN fine_summary     fs ON fs.user_id = sb.id
    ORDER BY sb.name;
END;
$$;

CREATE OR REPLACE FUNCTION fn_security_roster_assign(
    p_society_id  INT,
    p_security_id INT,
    p_roster_date DATE,
    p_shift_type  VARCHAR DEFAULT 'morning',
    p_assigned_by INT     DEFAULT NULL
)
RETURNS TEXT LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO security_roster (society_id, security_id, roster_date, shift_type, assigned_by)
    VALUES (p_society_id, p_security_id, p_roster_date,
            p_shift_type::VARCHAR(20), p_assigned_by)
    ON CONFLICT (society_id, security_id, roster_date)
    DO UPDATE SET shift_type = EXCLUDED.shift_type;
    RETURN 'Duty assigned'::TEXT;
END;
$$;

CREATE OR REPLACE FUNCTION fn_security_roster_today(p_society_id INT)
RETURNS TABLE (
    id         INT,
    name       VARCHAR(100),
    shift_type VARCHAR(20),
    mobile     VARCHAR(15),
    status     VARCHAR(20),
    time_in    TIMESTAMP,
    time_out   TIMESTAMP
)
LANGUAGE SQL STABLE AS $$
    SELECT
        s.id::INT,
        s.name::VARCHAR(100),
        r.shift_type::VARCHAR(20),
        s.mobile::VARCHAR(15),
        CASE
            WHEN g.time_out IS NULL AND g.time_in IS NOT NULL THEN 'ON DUTY'
            WHEN g.time_in IS NOT NULL                        THEN 'COMPLETED'
            ELSE                                                   'ABSENT'
        END::VARCHAR(20)        AS status,
        g.time_in::TIMESTAMP,
        g.time_out::TIMESTAMP
    FROM security_roster r
    JOIN security_staff s ON s.id = r.security_id
    LEFT JOIN gate_access g
           ON g.entity_id = (
               SELECT id FROM users
               WHERE linked_id = s.id AND role = 'security'
               LIMIT 1
           )
          AND g.role = 's'
          AND g.time_in::DATE = CURRENT_DATE
    WHERE r.society_id   = p_society_id
      AND r.roster_date  = CURRENT_DATE
    ORDER BY r.shift_type, s.name;
$$;

CREATE OR REPLACE FUNCTION fn_security_roster_report(
    p_society_id  INT,
    p_start_date  DATE DEFAULT (CURRENT_DATE - INTERVAL '30 days')::DATE,
    p_end_date    DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    security_id      INT,
    name             VARCHAR(100),
    total_assigned   INT,
    days_present     INT,
    attendance_rate  NUMERIC(5,2),
    total_fines      NUMERIC(15,2),
    total_salary_due NUMERIC(15,2)
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.id::INT,
        s.name::VARCHAR(100),
        COUNT(r.id)::INT,
        COUNT(DISTINCT g.time_in::DATE)::INT,
        ROUND(
            COUNT(DISTINCT g.time_in::DATE)::NUMERIC
            / NULLIF(COUNT(r.id), 0) * 100,
            2
        )::NUMERIC(5,2),
        COALESCE(SUM(scf.security_fine), 0)::NUMERIC(15,2),
        (COALESCE(s.salary_per_shift, 0) * COUNT(r.id))::NUMERIC(15,2)
    FROM security_staff s
    LEFT JOIN security_roster r
           ON r.security_id = s.id
          AND r.roster_date BETWEEN p_start_date AND p_end_date
    LEFT JOIN gate_access g
           ON g.entity_id = (
               SELECT id FROM users
               WHERE linked_id = s.id AND role = 'security'
               LIMIT 1
           )
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
DECLARE
    v_acc        RECORD;
    v_asset_name VARCHAR(100);
BEGIN
    SELECT name, depreciation_percent, is_depreciable
    INTO v_acc FROM accounts WHERE id = p_account_id;
    IF NOT FOUND THEN RETURN 'Error: Account not found'::TEXT; END IF;
    SELECT asset_name INTO v_asset_name FROM asset_register WHERE id = p_asset_id;
    UPDATE asset_register
    SET parent_account_id  = p_account_id,
        depreciation_rate  = v_acc.depreciation_percent
    WHERE id = p_asset_id;
    RETURN 'Asset linked to account'::TEXT;
END;
$$;

CREATE OR REPLACE FUNCTION fn_calculate_asset_depreciation(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    rec            RECORD;
    dep_rate       NUMERIC(5,2);
    expense_amount NUMERIC(15,2);
BEGIN
    FOR rec IN
        SELECT ar.*,
               COALESCE(acc.depreciation_percent, ar.depreciation_rate, 10)::NUMERIC(5,2) AS final_rate
        FROM asset_register ar
        LEFT JOIN accounts acc ON acc.id = ar.parent_account_id
        WHERE ar.society_id = p_society_id
          AND (ar.last_depreciation_date IS NULL
               OR ar.last_depreciation_date < CURRENT_DATE - INTERVAL '25 days')
    LOOP
        dep_rate := rec.final_rate;
        IF dep_rate = 100 THEN
            expense_amount := rec.purchase_value::NUMERIC(15,2);
        ELSE
            expense_amount := (rec.purchase_value * (dep_rate / 100))::NUMERIC(15,2);
        END IF;

        INSERT INTO expenses (society_id, user_id, entity_id, entity_type,
            expense_date, acc_id, particulars, amount, mode, status, created_at)
        VALUES (
            p_society_id::INT,
            1::INT,
            rec.id::INT,
            'assets'::VARCHAR(20),
            CURRENT_DATE::DATE,
            COALESCE(rec.parent_account_id, 5)::INT,
            ('Depreciation - ' || rec.asset_name)::TEXT,
            expense_amount,
            'cash'::VARCHAR(20),
            'pending'::VARCHAR(20),
            NOW()::TIMESTAMP
        );
        UPDATE asset_register
        SET last_depreciation_date = CURRENT_DATE
        WHERE id = rec.id;
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION fn_asset_list(
    p_society_id INT,
    p_search     TEXT DEFAULT NULL
)
RETURNS TABLE (
    id                  INT,
    asset_name          VARCHAR(100),
    purchase_value      NUMERIC(12,2),
    purchase_date       DATE,
    account_name        VARCHAR(100),
    depreciation_rate   NUMERIC(5,2),
    expense_portion     NUMERIC(15,2),
    asset_portion       NUMERIC(15,2),
    current_book_value  NUMERIC(15,2),
    status              VARCHAR(20)
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM fn_calculate_asset_depreciation(p_society_id);
    RETURN QUERY
    SELECT
        ar.id::INT,
        ar.asset_name::VARCHAR(100),
        ar.purchase_value::NUMERIC(12,2),
        ar.purchase_date::DATE,
        COALESCE(acc.name, '—')::VARCHAR(100),
        COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10.00)::NUMERIC(5,2),
        CASE
            WHEN COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) = 100
                THEN ar.purchase_value::NUMERIC(15,2)
            WHEN EXTRACT(MONTH FROM ar.purchase_date) >= 9
                THEN (ar.purchase_value * (COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) / 100) * 0.5)::NUMERIC(15,2)
            ELSE
                (ar.purchase_value * (COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) / 100))::NUMERIC(15,2)
        END,
        GREATEST(ar.purchase_value * (1 - COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) / 100), 0)::NUMERIC(15,2),
        GREATEST(ar.purchase_value * (1 - COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) / 100), 0)::NUMERIC(15,2),
        CASE
            WHEN COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) = 100
                THEN 'FULLY EXPENSED'::VARCHAR(20)
            ELSE 'ACTIVE'::VARCHAR(20)
        END
    FROM asset_register ar
    LEFT JOIN accounts acc ON acc.id = ar.parent_account_id
    WHERE ar.society_id = p_society_id
      AND (p_search IS NULL OR ar.asset_name ILIKE '%'||p_search||'%')
    ORDER BY ar.purchase_date DESC;
END;
$$;

-- ═══ EVENTS ═══

DROP FUNCTION IF EXISTS fn_events_list CASCADE;
DROP FUNCTION IF EXISTS fn_event_profile CASCADE;

CREATE OR REPLACE FUNCTION fn_events_list(
    p_society_id INT,
    p_search     TEXT    DEFAULT NULL,
    p_status     VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id              INT,
    title           VARCHAR(200),
    description     TEXT,
    event_date      DATE,
    event_time      VARCHAR(20),
    venue           VARCHAR(200),
    open_to         VARCHAR(20),
    attendees_count INT,
    created_at      TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        e.id::INT,
        e.title::VARCHAR(200),
        e.description::TEXT,
        e.event_date::DATE,
        e.event_time::VARCHAR(20),
        e.venue::VARCHAR(200),
        e.open_to::VARCHAR(20),
        0::INT,
        e.created_at::TIMESTAMP
    FROM events e
    WHERE e.society_id = p_society_id
      AND (p_search IS NULL OR e.title ILIKE '%'||p_search||'%')
      AND e.event_date >= CURRENT_DATE
    ORDER BY e.event_date ASC;
END;
$$;

CREATE OR REPLACE FUNCTION fn_event_profile(p_event_id INT)
RETURNS TABLE (
    id          INT,
    society_id  INT,
    title       VARCHAR(200),
    description TEXT,
    event_date  DATE,
    event_time  VARCHAR(20),
    venue       VARCHAR(200),
    open_to     VARCHAR(20),
    created_at  TIMESTAMP,
    subtitle    TEXT
)
LANGUAGE SQL STABLE AS $$
    SELECT
        id::INT,
        society_id::INT,
        title::VARCHAR(200),
        description::TEXT,
        event_date::DATE,
        event_time::VARCHAR(20),
        venue::VARCHAR(200),
        open_to::VARCHAR(20),
        created_at::TIMESTAMP,
        (event_date::TEXT || ' ' || COALESCE(event_time, ''))::TEXT AS subtitle
    FROM events
    WHERE id = p_event_id;
$$;

-- ═══ CONCERNS ═══

DROP FUNCTION IF EXISTS fn_concerns_list CASCADE;
DROP FUNCTION IF EXISTS fn_concern_profile CASCADE;

CREATE OR REPLACE FUNCTION fn_concerns_list(
    p_society_id INT,
    p_search     TEXT    DEFAULT NULL,
    p_status     VARCHAR DEFAULT 'open'
)
RETURNS TABLE (
    id          INT,
    flat_no     VARCHAR(20),
    concern_type VARCHAR(50),
    description TEXT,
    status      VARCHAR(20),
    assigned_to VARCHAR(100),
    priority    VARCHAR(10),
    created_at  TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id::INT,
        c.flat_no::VARCHAR(20),
        c.concern_type::VARCHAR(50),
        c.description::TEXT,
        c.status::VARCHAR(20),
        c.assigned_to::VARCHAR(100),
        CASE
            WHEN c.status = 'resolved'                                          THEN 'Low'
            WHEN EXTRACT(DAY FROM AGE(CURRENT_DATE, c.created_at)) > 7        THEN 'High'
            ELSE 'Medium'
        END::VARCHAR(10),
        c.created_at::TIMESTAMP
    FROM concerns c
    WHERE c.society_id = p_society_id
      AND (p_status IS NULL OR c.status = p_status)
      AND (p_search IS NULL OR c.flat_no ILIKE '%'||p_search||'%')
    ORDER BY
        CASE WHEN c.status = 'open' THEN 0 ELSE 1 END,
        c.created_at DESC;
END;
$$;

CREATE OR REPLACE FUNCTION fn_concern_profile(p_concern_id INT)
RETURNS TABLE (
    id            INT,
    society_id    INT,
    flat_no       VARCHAR(20),
    concern_type  VARCHAR(50),
    description   TEXT,
    status        VARCHAR(20),
    assigned_to   VARCHAR(100),
    preferred_time VARCHAR(20),
    days_open     BIGINT,
    created_at    TIMESTAMP,
    subtitle      TEXT
)
LANGUAGE SQL STABLE AS $$
    SELECT
        id::INT,
        society_id::INT,
        flat_no::VARCHAR(20),
        concern_type::VARCHAR(50),
        description::TEXT,
        status::VARCHAR(20),
        assigned_to::VARCHAR(100),
        preferred_time::VARCHAR(20),
        EXTRACT(DAY FROM AGE(CURRENT_DATE, created_at))::BIGINT,
        created_at::TIMESTAMP,
        ('Flat ' || flat_no || ' - ' || concern_type)::TEXT AS subtitle
    FROM concerns
    WHERE id = p_concern_id;
$$;

-- ═══ ACCOUNTS ═══

DROP FUNCTION IF EXISTS fn_accounts_list CASCADE;
DROP FUNCTION IF EXISTS fn_account_profile CASCADE;

CREATE OR REPLACE FUNCTION fn_accounts_list(
    p_society_id INT,
    p_search     TEXT    DEFAULT NULL,
    p_tab_name   VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id                  INT,
    name                VARCHAR(100),
    tab_name            VARCHAR(20),
    header              VARCHAR(50),
    drcr_account        VARCHAR(2),
    bf_amount           NUMERIC(12,2),
    current_balance     NUMERIC(15,2),
    transaction_count   INT,
    parent_account_name VARCHAR(100)
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        a.id::INT,
        a.name::VARCHAR(100),
        a.tab_name::VARCHAR(20),
        a.header::VARCHAR(50),
        a.drcr_account::VARCHAR(2),
        a.bf_amount::NUMERIC(12,2),
        (COALESCE(SUM(
            CASE WHEN a.drcr_account = 'Cr' THEN t.amount ELSE -t.amount END
        ), 0) + a.bf_amount)::NUMERIC(15,2),
        COUNT(t.id)::INT,
        COALESCE(p.name, '—')::VARCHAR(100)
    FROM accounts a
    LEFT JOIN accounts p ON p.id = a.parent_account_id
    LEFT JOIN transactions t
           ON t.acc_id = a.id AND t.status = 'paid'
    WHERE a.society_id = p_society_id
      AND (p_tab_name IS NULL OR a.tab_name = p_tab_name)
      AND (p_search   IS NULL OR a.name ILIKE '%'||p_search||'%')
    GROUP BY a.id, a.name, a.tab_name, a.header,
             a.drcr_account, a.bf_amount, p.name
    ORDER BY a.tab_name, a.name;
END;
$$;

CREATE OR REPLACE FUNCTION fn_account_profile(p_account_id INT)
RETURNS TABLE (
    id                  INT,
    society_id          INT,
    name                VARCHAR(100),
    tab_name            VARCHAR(20),
    header              VARCHAR(50),
    drcr_account        VARCHAR(2),
    bf_amount           NUMERIC(12,2),
    depreciation_percent NUMERIC(5,2),
    is_depreciable      BOOLEAN,
    parent_account_name VARCHAR(100),
    current_balance     NUMERIC(15,2),
    created_at          TIMESTAMP
)
LANGUAGE SQL STABLE AS $$
    SELECT
        a.id::INT,
        a.society_id::INT,
        a.name::VARCHAR(100),
        a.tab_name::VARCHAR(20),
        a.header::VARCHAR(50),
        a.drcr_account::VARCHAR(2),
        a.bf_amount::NUMERIC(12,2),
        a.depreciation_percent::NUMERIC(5,2),
        a.is_depreciable::BOOLEAN,
        COALESCE(p.name, '—')::VARCHAR(100),
        (COALESCE(SUM(
            CASE WHEN a.drcr_account = 'Cr' THEN t.amount ELSE -t.amount END
        ), 0) + a.bf_amount)::NUMERIC(15,2),
        a.created_at::TIMESTAMP
    FROM accounts a
    LEFT JOIN accounts p ON p.id = a.parent_account_id
    LEFT JOIN transactions t ON t.acc_id = a.id AND t.status = 'paid'
    WHERE a.id = p_account_id
    GROUP BY a.id, a.society_id, a.name, a.tab_name, a.header,
             a.drcr_account, a.bf_amount, a.depreciation_percent,
             a.is_depreciable, p.name, a.created_at;
$$;

-- ═══ SOCIETIES ═══

DROP FUNCTION IF EXISTS fn_societies_list CASCADE;
DROP FUNCTION IF EXISTS fn_society_profile CASCADE;

CREATE OR REPLACE FUNCTION fn_societies_list(
    p_search TEXT    DEFAULT NULL,
    p_plan   VARCHAR DEFAULT NULL,
    p_status VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id                INT,
    name              VARCHAR(100),
    email             VARCHAR(100),
    phone             VARCHAR(20),
    plan              VARCHAR(20),
    plan_status       VARCHAR(10),
    plan_validity     DATE,
    total_apartments  INT,
    total_users       INT,
    total_receivables NUMERIC(15,2),
    created_at        TIMESTAMP,
    secretary_phone   VARCHAR(20)
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.id::INT,
        s.name::VARCHAR(100),
        s.email::VARCHAR(100),
        s.phone::VARCHAR(20),
        s.plan::VARCHAR(20),
        CASE
            WHEN s.plan = 'Free'             THEN 'Free'
            WHEN s.plan_validity >= CURRENT_DATE THEN 'Active'
            ELSE 'Expired'
        END::VARCHAR(10),
        s.plan_validity::DATE,
        (SELECT COUNT(*)::INT FROM apartments WHERE society_id = s.id AND active = TRUE),
        (SELECT COUNT(*)::INT FROM users        WHERE society_id = s.id),
        (SELECT COALESCE(SUM(amount), 0)::NUMERIC(15,2)
         FROM receivables WHERE society_id = s.id AND status = 'pending'),
        s.created_at::TIMESTAMP,
        s.secretary_phone::VARCHAR(20)
    FROM societies s
    WHERE (p_search IS NULL OR s.name ILIKE '%'||p_search||'%')
      AND (p_plan   IS NULL OR s.plan = p_plan)
    ORDER BY s.name;
END;
$$;

CREATE OR REPLACE FUNCTION fn_society_profile(p_society_id INT)
RETURNS TABLE (
    id                 INT,
    name               VARCHAR(100),
    logo               VARCHAR(100),
    login_background   VARCHAR(100),
    email              VARCHAR(100),
    phone              VARCHAR(20),
    address            TEXT,
    plan               VARCHAR(20),
    plan_status        VARCHAR(10),
    plan_validity      DATE,
    arrear_start_date  DATE,
    secretary_name     VARCHAR(100),
    secretary_phone    VARCHAR(20),
    secretary_sign     VARCHAR(100),
    total_apartments   INT,
    total_vendors      INT,
    total_security     INT,
    total_users        INT,
    total_receivables  NUMERIC(15,2),
    created_at         TIMESTAMP,
    _image_society_id  INT
)
LANGUAGE SQL STABLE AS $$
    SELECT
        s.id::INT,
        s.name::VARCHAR(100),
        s.logo::VARCHAR(100),
        s.login_background::VARCHAR(100),
        s.email::VARCHAR(100),
        s.phone::VARCHAR(20),
        s.address::TEXT,
        s.plan::VARCHAR(20),
        CASE
            WHEN s.plan = 'Free'                 THEN 'Free'
            WHEN s.plan_validity >= CURRENT_DATE THEN 'Active'
            ELSE                                      'Expired'
        END::VARCHAR(10),
        s.plan_validity::DATE,
        s.arrear_start_date::DATE,
        s.secretary_name::VARCHAR(100),
        s.secretary_phone::VARCHAR(20),
        s.secretary_sign::VARCHAR(100),
        (SELECT COUNT(*)::INT FROM apartments    WHERE society_id = s.id),
        (SELECT COUNT(*)::INT FROM vendors       WHERE society_id = s.id),
        (SELECT COUNT(*)::INT FROM security_staff WHERE society_id = s.id),
        (SELECT COUNT(*)::INT FROM users         WHERE society_id = s.id),
        (SELECT COALESCE(SUM(amount), 0)::NUMERIC(15,2)
         FROM receivables WHERE society_id = s.id AND status = 'pending'),
        s.created_at::TIMESTAMP,
        s.id::INT
    FROM societies s
    WHERE s.id = p_society_id;
$$;

-- ═══ RECEIVABLES ═══

DROP FUNCTION IF EXISTS fn_receivables_list CASCADE;
DROP FUNCTION IF EXISTS fn_receivable_profile CASCADE;

CREATE OR REPLACE FUNCTION fn_receivables_list(
    p_society_id INT,
    p_search     TEXT    DEFAULT NULL,
    p_status     VARCHAR DEFAULT 'pending'
)
RETURNS TABLE (
    id           INT,
    entity_type  VARCHAR(20),
    entity_id    INT,
    entity_name  TEXT,
    charge_type  VARCHAR(50),
    description  TEXT,
    amount       NUMERIC(10,2),
    due_date     DATE,
    status       VARCHAR(20),
    days_overdue INT,
    created_at   TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        r.id::INT,
        r.entity_type::VARCHAR(20),
        r.entity_id::INT,
        CASE
            WHEN r.entity_type = 'apartment'
                THEN ('Flat ' || (SELECT flat_number FROM apartments WHERE id = r.entity_id))::TEXT
            WHEN r.entity_type = 'vendor'
                THEN (SELECT name::TEXT FROM vendors WHERE id = r.entity_id)
            WHEN r.entity_type = 'security'
                THEN (SELECT name::TEXT FROM security_staff WHERE id = r.entity_id)
            ELSE ('Entity #' || r.entity_id)::TEXT
        END AS entity_name,
        r.charge_type::VARCHAR(50),
        r.description::TEXT,
        r.amount::NUMERIC(10,2),
        r.due_date::DATE,
        r.status::VARCHAR(20),
        EXTRACT(DAY FROM AGE(CURRENT_DATE, r.due_date))::INT,
        r.created_at::TIMESTAMP
    FROM receivables r
    WHERE r.society_id = p_society_id
      AND (p_status IS NULL OR r.status = p_status)
      AND (p_search IS NULL OR r.description ILIKE '%'||p_search||'%')
    ORDER BY r.due_date ASC, r.created_at DESC;
END;
$$;

CREATE OR REPLACE FUNCTION fn_receivable_profile(p_receivable_id INT)
RETURNS TABLE (
    id           INT,
    society_id   INT,
    entity_type  VARCHAR(20),
    entity_id    INT,
    charge_type  VARCHAR(50),
    description  TEXT,
    amount       NUMERIC(10,2),
    due_date     DATE,
    status       VARCHAR(20),
    source_table VARCHAR(50),
    source_id    INT,
    confirmed_by INT,
    confirmed_at TIMESTAMP,
    created_at   TIMESTAMP,
    days_overdue INT
)
LANGUAGE SQL STABLE AS $$
    SELECT
        id::INT,
        society_id::INT,
        entity_type::VARCHAR(20),
        entity_id::INT,
        charge_type::VARCHAR(50),
        description::TEXT,
        amount::NUMERIC(10,2),
        due_date::DATE,
        status::VARCHAR(20),
        source_table::VARCHAR(50),
        source_id::INT,
        confirmed_by::INT,
        confirmed_at::TIMESTAMP,
        created_at::TIMESTAMP,
        EXTRACT(DAY FROM AGE(CURRENT_DATE, due_date))::INT
    FROM receivables
    WHERE id = p_receivable_id;
$$;

-- ═══ CASHBOOK ═══

DROP FUNCTION IF EXISTS fn_cashbook_list CASCADE;

CREATE OR REPLACE FUNCTION fn_cashbook_list(
    p_society_id INT,
    p_search     TEXT DEFAULT NULL,
    p_start_date DATE DEFAULT NULL,
    p_end_date   DATE DEFAULT NULL
)
RETURNS TABLE (
    id            INT,
    trx_date      DATE,
    account_name  VARCHAR(100),
    account_group VARCHAR(20),
    particulars   VARCHAR(100),
    debit         NUMERIC(15,2),
    credit        NUMERIC(15,2),
    balance       NUMERIC(15,2),
    mode          VARCHAR(6),
    created_at    TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_opening_balance NUMERIC(15,2);
BEGIN
    SELECT COALESCE(SUM(
        CASE WHEN drcr_bf = 'Cr' THEN bf_amount ELSE -bf_amount END
    ), 0)::NUMERIC(15,2)
    INTO v_opening_balance
    FROM accounts
    WHERE society_id = p_society_id;

    RETURN QUERY
    WITH ordered_transactions AS (
        SELECT
            t.id::INT,
            t.trx_date::DATE,
            a.name::VARCHAR(100)         AS account_name,
            a.tab_name::VARCHAR(20)      AS account_group,
            t.acc_particulars::VARCHAR(100),
            t.amount::NUMERIC(15,2),
            t.mode::VARCHAR(6),
            t.created_at::TIMESTAMP,
            CASE WHEN a.drcr_account = 'Dr' THEN t.amount ELSE NULL::NUMERIC END::NUMERIC(15,2) AS debit,
            CASE WHEN a.drcr_account = 'Cr' THEN t.amount ELSE NULL::NUMERIC END::NUMERIC(15,2) AS credit,
            ROW_NUMBER() OVER (ORDER BY t.trx_date ASC, t.id ASC) AS row_num
        FROM transactions t
        JOIN accounts a ON a.id = t.acc_id
        WHERE t.society_id = p_society_id
          AND t.status = 'paid'
          AND (p_start_date IS NULL OR t.trx_date >= p_start_date)
          AND (p_end_date   IS NULL OR t.trx_date <= p_end_date)
          AND (p_search     IS NULL OR a.name ILIKE '%'||p_search||'%')
    )
    SELECT
        ot.id,
        ot.trx_date,
        ot.account_name,
        ot.account_group,
        ot.acc_particulars,
        ot.debit,
        ot.credit,
        (v_opening_balance
         + SUM(COALESCE(ot.credit, 0) - COALESCE(ot.debit, 0))
           OVER (ORDER BY ot.row_num))::NUMERIC(15,2),
        ot.mode,
        ot.created_at
    FROM ordered_transactions ot
    ORDER BY ot.trx_date ASC, ot.id ASC;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- UTILITY FUNCTIONS
-- ════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION get_function_sql(p_function_name TEXT)
RETURNS TEXT AS $$
DECLARE v_sql TEXT;
BEGIN
    SELECT pg_get_functiondef(p.oid)
    INTO v_sql FROM pg_proc p
    WHERE p.proname = p_function_name LIMIT 1;
    RETURN COALESCE(v_sql, ('Function not found: ' || p_function_name)::TEXT);
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_kpi_functions()
RETURNS TABLE (
    function_name   TEXT,
    function_schema TEXT,
    parameters      TEXT,
    source_code     TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        p.proname::TEXT,
        n.nspname::TEXT,
        pg_get_function_arguments(p.oid)::TEXT,
        pg_get_functiondef(p.oid)::TEXT
    FROM pg_proc p
    JOIN pg_namespace n ON p.pronamespace = n.oid
    WHERE p.proname LIKE 'fn_%'
      AND n.nspname = 'public'
    ORDER BY p.proname;
END;
$$ LANGUAGE plpgsql;

-- ════════════════════════════════════════════════════════════════════════════
-- Get KPIs by portal with their function mappings
-- ════════════════════════════════════════════════════════════════════════════
-- CREATE OR REPLACE FUNCTION get_portal_kpis(p_portal TEXT DEFAULT NULL)
-- RETURNS TABLE (
--     kpi_id TEXT,
--     kpi_label TEXT,
--     kpi_icon TEXT,
--     portal TEXT,
--     tab_name TEXT,
--     function_name TEXT
-- ) AS $$
-- BEGIN
--     RETURN QUERY
--     SELECT 
--         'kpi_apartments_total'::TEXT,
--         'Total Apartments'::TEXT,
--         'fa-building'::TEXT,
--         'admin'::TEXT,
--         'overview'::TEXT,
--         'fn_apartments_list'::TEXT
--     UNION ALL
--     SELECT 'kpi_apartments_dues', 'Apartments with Dues', 'fa-exclamation-circle', 'admin', 'overview', 'fn_apartments_list'
--     UNION ALL
--     SELECT 'kpi_vendors_total', 'All Vendors', 'fa-handshake', 'admin', 'overview', 'fn_vendors_list'
--     UNION ALL
--     SELECT 'kpi_security_total', 'Security Staff', 'fa-shield', 'admin', 'overview', 'fn_security_list'
--     UNION ALL
--     SELECT 'kpi_security_on_duty', 'On Duty Now', 'fa-user-shield', 'admin', 'overview', 'fn_security_list'
--     UNION ALL
--     SELECT 'kpi_events_total', 'Upcoming Events', 'fa-calendar', 'admin', 'events', 'fn_events_list'
--     UNION ALL
--     SELECT 'kpi_concerns_open', 'Open Concerns', 'fa-exclamation-circle', 'admin', 'concerns', 'fn_concerns_list'
--     UNION ALL
--     SELECT 'kpi_gate_logs', 'Gate Logs Today', 'fa-receipt', 'admin', 'overview', 'fn_gate_logs'
--     UNION ALL
--     SELECT 'kpi_receipts_month', 'Receipts (Month)', 'fa-receipt', 'admin', 'cashbook', 'fn_cashbook_list'
--     UNION ALL
--     SELECT 'kpi_expenses_month', 'Expenses (Month)', 'fa-wallet', 'admin', 'cashbook', 'fn_cashbook_list'
--     UNION ALL
--     SELECT 'kpi_cash_in_hand', 'Cash in Hand', 'fa-money-bill', 'admin', 'cashbook', 'fn_cashbook_list'
--     UNION ALL
--     SELECT 'kpi_bank_balance', 'Current Balance', 'fa-wallet', 'admin', 'cashbook', 'fn_cashbook_list'
--     UNION ALL
--     SELECT 'kpi_receivables_total', 'Total Receivables', 'fa-hand-holding-usd', 'admin', 'cashbook', 'fn_receivables_list'
--     UNION ALL
--     SELECT 'kpi_payables_total', 'Total Payables', 'fa-wallet', 'admin', 'cashbook', 'fn_expenses_list'
--     UNION ALL
--     SELECT 'kpi_maintenance_due', 'Maintenance Due', 'fa-home', 'admin', 'cashbook', 'fn_apartments_list'
--     UNION ALL
--     SELECT 'kpi_late_fees_due', 'Late Fees Due', 'fa-clock', 'admin', 'cashbook', 'fn_payments_list'
--     UNION ALL
--     SELECT 'kpi_security_salaries_due', 'Security Salaries Due', 'fa-user-shield', 'admin', 'cashbook', 'fn_payments_list'
--     UNION ALL
--     SELECT 'kpi_vendor_payables_due', 'Vendor Payments', 'fa-truck', 'admin', 'cashbook', 'fn_payments_list'
--     UNION ALL
--     SELECT 'kpi_amc_due', 'AMC Due', 'fa-building', 'admin', 'expenses', 'fn_expenses_list'
--     UNION ALL
--     SELECT 'kpi_accounts_count', 'Chart of Accounts', 'fa-book-open', 'admin', 'settings', 'fn_accounts_list'
--     UNION ALL
--     SELECT 'kpi_apt_charges', 'Apartment Charges', 'fa-home', 'admin', 'settings', 'fn_apt_charges_fines'
--     UNION ALL
--     SELECT 'kpi_ven_charges', 'Vendor Charges', 'fa-briefcase', 'admin', 'settings', 'fn_ven_charges_fines'
--     UNION ALL
--     SELECT 'kpi_sec_charges', 'Security Charges', 'fa-lock', 'admin', 'settings', 'fn_sec_charges_fines'
--     UNION ALL
--     SELECT 'kpi_attendance', 'Attendance (30d)', 'fa-clock', 'admin', 'settings', 'fn_attendance_list'
--     UNION ALL
--     SELECT 'kpi_plan_validity', 'Plan Validity', 'fa-calendar-times', 'admin', 'settings', 'fn_societies_list'
--     UNION ALL
--     SELECT 'kpi_societies_total', 'Total Societies', 'fa-building', 'master', 'dashboard', 'fn_societies_list'
--     UNION ALL
--     SELECT 'kpi_societies_free', 'Free Plans', 'fa-circle', 'master', 'dashboard', 'fn_societies_list'
--     UNION ALL
--     SELECT 'kpi_societies_9Apts', '9Apts Plans', 'fa-star', 'master', 'dashboard', 'fn_societies_list'
--     UNION ALL
--     SELECT 'kpi_societies_99Apts', '99Apts Plans', 'fa-star', 'master', 'dashboard', 'fn_societies_list'
--     UNION ALL
--     SELECT 'kpi_societies_999Apts', '999Apts Plans', 'fa-star', 'master', 'dashboard', 'fn_societies_list'
--     UNION ALL
--     SELECT 'kpi_societies_unlimited', 'unlimited Plans', 'fa-star', 'master', 'dashboard', 'fn_societies_list'
--     UNION ALL
--     SELECT 'kpi_master_apartments_total', 'All Apartments', 'fa-home', 'master', 'dashboard', 'fn_apartments_list'
--     UNION ALL
--     SELECT 'kpi_master_vendors_total', 'All Vendors', 'fa-truck', 'master', 'dashboard', 'fn_vendors_list'
--     UNION ALL
--     SELECT 'kpi_master_security_total', 'All Security', 'fa-user-shield', 'master', 'dashboard', 'fn_security_list'
--     UNION ALL
--     SELECT 'kpi_apartments_dues', 'Pending Dues', 'fa-rupee-sign', 'apartment', 'dashboard', 'fn_apartments_list'
--     UNION ALL
--     SELECT 'kpi_concerns_open', 'Open Concerns', 'fa-hand-point-up', 'apartment', 'dashboard', 'fn_concerns_list'
--     UNION ALL
--     SELECT 'kpi_events_total', 'Upcoming Events', 'fa-calendar-check', 'apartment', 'dashboard', 'fn_events_list'
--     UNION ALL
--     SELECT 'kpi_gate_logs', 'Gate Logs', 'fa-receipt', 'apartment', 'dashboard', 'fn_gate_logs'
--     UNION ALL
--     SELECT 'kpi_receipts_month', 'Paid (Month)', 'fa-receipt', 'apartment', 'cashbook', 'fn_cashbook_list'
--     UNION ALL
--     SELECT 'kpi_bank_balance', 'Balance', 'fa-wallet', 'apartment', 'cashbook', 'fn_cashbook_list'
--     UNION ALL
--     SELECT 'kpi_receivables_total', 'To Pay', 'fa-wallet', 'apartment', 'dashboard', 'fn_payments_list'
--     UNION ALL
--     SELECT 'kpi_vendors_dues', 'Pending Dues', 'fa-rupee-sign', 'vendor', 'dashboard', 'fn_vendors_list'
--     UNION ALL
--     SELECT 'kpi_receipts_month', 'Receipts (Month)', 'fa-receipt', 'vendor', 'cashbook', 'fn_cashbook_list'
--     UNION ALL
--     SELECT 'kpi_bank_balance', 'Balance', 'fa-wallet', 'vendor', 'cashbook', 'fn_cashbook_list'
--     UNION ALL
--     SELECT 'kpi_concerns_open', 'Jobs / Concerns', 'fa-hand-point-up', 'vendor', 'dashboard', 'fn_concerns_list'
--     UNION ALL
--     SELECT 'kpi_events_total', 'Events', 'fa-calendar-check', 'vendor', 'events', 'fn_events_list'
--     UNION ALL
--     SELECT 'kpi_receivables_total', 'Payable Due', 'fa-receipt', 'vendor', 'dashboard', 'fn_payments_list'
--     UNION ALL
--     SELECT 'kpi_gate_logs', 'Gate Logs', 'fa-receipt', 'vendor', 'dashboard', 'fn_gate_logs'
--     UNION ALL
--     SELECT 'kpi_vendor_fines', 'Vendor Fines', 'fa-exclamation-triangle', 'vendor', 'charges', 'fn_payments_list'
--     UNION ALL
--     SELECT 'kpi_vendor_other_charges', 'Other Charges', 'fa-plus', 'vendor', 'charges', 'fn_payments_list'
--     UNION ALL
--     SELECT 'kpi_vendor_date', 'Managed Since', 'fa-calendar-alt', 'vendor', 'settings', 'fn_vendors_list'
--     UNION ALL
--     SELECT 'kpi_apartments_total', 'Apartments', 'fa-home', 'security', 'dashboard', 'fn_apartments_list'
--     UNION ALL
--     SELECT 'kpi_vendors_total', 'Vendors', 'fa-truck', 'security', 'dashboard', 'fn_vendors_list'
--     UNION ALL
--     SELECT 'kpi_security_total', 'Security', 'fa-user-shield', 'security', 'dashboard', 'fn_security_list'
--     UNION ALL
--     SELECT 'kpi_security_shift_count', 'Shift Count', 'fa-hand-point-up', 'security', 'dashboard', 'fn_security_list'
--     UNION ALL
--     SELECT 'kpi_receivables_total', 'Receipts Due', 'fa-receipt', 'security', 'dashboard', 'fn_payments_list'
--     UNION ALL
--     SELECT 'kpi_payables_total', 'Expenses Due', 'fa-wallet', 'security', 'cashbook', 'fn_expenses_list'
--     UNION ALL
--     SELECT 'kpi_receipts_month', 'Receipts (Month)', 'fa-receipt', 'security', 'cashbook', 'fn_cashbook_list'
--     UNION ALL
--     SELECT 'kpi_expenses_month', 'Expenses (Month)', 'fa-wallet', 'security', 'cashbook', 'fn_cashbook_list'
--     UNION ALL
--     SELECT 'kpi_gate_logs', 'Gate Logs', 'fa-receipt', 'security', 'dashboard', 'fn_gate_logs'
--     UNION ALL
--     SELECT 'kpi_security_fines', 'Security Fines', 'fa-exclamation-triangle', 'security', 'charges', 'fn_payments_list'
--     UNION ALL
--     SELECT 'kpi_security_other_charges', 'Other Charges', 'fa-plus', 'security', 'charges', 'fn_payments_list'
--     UNION ALL
--     SELECT 'kpi_receipts_in_hand_total', 'Receipts-in-hand', 'fa-money-bill-wave', 'security', 'charges', 'fn_cashbook_list'
--     UNION ALL
--     SELECT 'kpi_security_salary_due', 'Salary Due', 'fa-rupee-sign', 'security', 'payments', 'fn_payments_list'
--     UNION ALL
--     SELECT 'kpi_security_bonus_due', 'Bonus Due', 'fa-gift', 'security', 'payments', 'fn_payments_list'
--     UNION ALL
--     SELECT 'kpi_events_total', 'Events', 'fa-calendar-check', 'security', 'events', 'fn_events_list'
--     UNION ALL
--     SELECT 'kpi_receipts_month', 'Receipts (Month)', 'fa-receipt', 'security', 'receipt', 'fn_cashbook_list'
--     UNION ALL
--     SELECT 'kpi_security_date', 'Managed Since', 'fa-calendar-alt', 'security', 'settings', 'fn_security_list'
--     UNION ALL
--     SELECT 'kpi_security_salary_per_shift', 'Salary per Shift', 'fa-rupee-sign', 'security', 'settings', 'fn_security_list'
--     UNION ALL
--     SELECT 'kpi_security_shift', 'Completed Shifts', 'fa-clock', 'security', 'settings', 'fn_gate_logs'
--     WHERE (p_portal IS NULL OR portal = p_portal)
--     ORDER BY portal, tab_name, kpi_label;
-- END;
-- $$ LANGUAGE plpgsql;

-- -- ════════════════════════════════════════════════════════════════════════════
-- -- Helper: Get profile card actions for an entity
-- -- ════════════════════════════════════════════════════════════════════════════
-- CREATE OR REPLACE FUNCTION get_entity_actions(p_entity TEXT)
-- RETURNS TABLE (
--     action_id TEXT,
--     action_label TEXT,
--     target_card TEXT,
--     icon TEXT
-- ) AS $$
-- BEGIN
--     RETURN QUERY
--     SELECT 
--         'view'::TEXT,
--         'View'::TEXT,
--         'profile_' || p_entity::TEXT,
--         'fa-eye'::TEXT
--     UNION ALL
--     SELECT 'edit', 'Edit', 'form_' || p_entity || '_edit', 'fa-edit'
--     UNION ALL
--     SELECT 'delete', 'Delete', 'form_' || p_entity || '_edit', 'fa-trash';
-- END;
-- $$ LANGUAGE plpgsql;

-- ════════════════════════════════════════════════════════════════════════════
-- Missing functions for KPI compatibility
-- ════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_gate_logs(p_society_id INT)
RETURNS TABLE (
    id        INT,
    time_in   TIMESTAMP,
    time_out  TIMESTAMP,
    role      VARCHAR(1),
    entity_id INT
)
LANGUAGE SQL STABLE AS $$
    SELECT
        id::INT,
        time_in::TIMESTAMP,
        time_out::TIMESTAMP,
        role::VARCHAR(1),
        entity_id::INT
    FROM gate_access
    WHERE society_id = p_society_id
      AND time_in >= CURRENT_DATE
    ORDER BY time_in DESC;
$$;

CREATE OR REPLACE FUNCTION fn_payments_list(
    p_society_id  INT,
    p_entity_type VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id           INT,
    entity_id    INT,
    entity_type  VARCHAR(20),
    amount       NUMERIC(10,2),
    status       VARCHAR(20),
    payment_type VARCHAR(50),
    created_at   TIMESTAMP
)
LANGUAGE SQL STABLE AS $$
    SELECT
        id::INT,
        entity_id::INT,
        entity_type::VARCHAR(20),
        amount::NUMERIC(10,2),
        status::VARCHAR(20),
        payment_type::VARCHAR(50),
        created_at::TIMESTAMP
    FROM payments
    WHERE society_id  = p_society_id
      AND (p_entity_type IS NULL OR entity_type = p_entity_type)
    ORDER BY created_at DESC;
$$;

CREATE OR REPLACE FUNCTION fn_expenses_list(p_society_id INT)
RETURNS TABLE (
    id          INT,
    acc_id      INT,
    particulars TEXT,
    amount      NUMERIC(10,2),
    mode        VARCHAR(20),
    status      VARCHAR(20),
    created_at  TIMESTAMP
)
LANGUAGE SQL STABLE AS $$
    SELECT
        id::INT,
        acc_id::INT,
        particulars::TEXT,
        amount::NUMERIC(10,2),
        mode::VARCHAR(20),
        status::VARCHAR(20),
        created_at::TIMESTAMP
    FROM expenses
    WHERE society_id = p_society_id
    ORDER BY created_at DESC;
$$;

CREATE OR REPLACE FUNCTION fn_attendance_list(p_society_id INT)
RETURNS TABLE (
    id          INT,
    security_id INT,
    time_in     TIMESTAMP,
    time_out    TIMESTAMP,
    status      VARCHAR(20)
)
LANGUAGE SQL STABLE AS $$
    SELECT
        a.id::INT,
        a.security_id::INT,
        a.time_in::TIMESTAMP,
        a.time_out::TIMESTAMP,
        CASE
            WHEN a.time_out IS NULL AND a.time_in IS NOT NULL THEN 'ON_DUTY'
            WHEN a.time_in  IS NOT NULL                       THEN 'COMPLETED'
            ELSE                                                   'ABSENT'
        END::VARCHAR(20) AS status
    FROM attendance a
    WHERE a.society_id = p_society_id
      AND a.time_in >= CURRENT_DATE - INTERVAL '30 days'
    ORDER BY a.time_in DESC;
$$;
