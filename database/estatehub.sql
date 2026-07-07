-- ============================================================
-- ESTATEHUB - COMPLETE DATABASE SCHEMA & FUNCTIONS (v3)
-- Accounts-as-categorisation: acc_id replaces charge_type/payment_type/category
-- Interest split: single receivable row, two transaction lines on verify
-- ============================================================
-- SAFE TO RE-RUN: CREATE OR REPLACE / IF NOT EXISTS / ON CONFLICT DO NOTHING
-- Intended for a FRESH database reset followed by migrate.py seeding.
-- ============================================================

-- ════════════════════════════════════════════════════════════════
-- SECTION 1: CORE SCHEMA
-- ════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS societies (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(100) NOT NULL UNIQUE,
    PAN_number       VARCHAR(10),
    logo             VARCHAR(100),
    address          TEXT,
    email            VARCHAR(100),
    phone            VARCHAR(20),
    secretary_name   VARCHAR(100),
    secretary_phone  VARCHAR(20),
    secretary_sign   VARCHAR(100),
    payment_qr       VARCHAR(255),
    plan             VARCHAR(20) NOT NULL DEFAULT 'Free'
        CHECK (plan IN ('Free','9Apts','99Apts','999Apts','unlimited')),
    plan_validity    DATE NOT NULL DEFAULT CURRENT_DATE,
    calc_start_date  DATE NOT NULL DEFAULT CURRENT_DATE,
    login_background VARCHAR(100),
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id                    SERIAL PRIMARY KEY,
    society_id            INT REFERENCES societies(id) ON DELETE CASCADE,
    email                 VARCHAR(100) NOT NULL UNIQUE,
    password_hash         TEXT NOT NULL,
    pin_hash              TEXT,
    pattern_hash          TEXT,
    name                  VARCHAR(100),
    role                  VARCHAR(20) NOT NULL
        CHECK (role IN ('admin','apartment','vendor','security')),
    linked_id             INT,
    login_method          VARCHAR(20) DEFAULT 'password',
    push_subscription     TEXT,
    is_master_admin       BOOLEAN NOT NULL DEFAULT FALSE,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until          TIMESTAMP,
    reset_token           VARCHAR(64),
    reset_token_expires   TIMESTAMP,
    push_token            TEXT,
    push_enabled          BOOLEAN NOT NULL DEFAULT FALSE,
    last_login            TIMESTAMP,
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ── accounts ──────────────────────────────────────────────────
-- `tab_name` is reserved for future per-tab Excel/ledger export (AccEstate sheet
-- grouping). It is NOT used as a category or filter key anywhere in the engine.
-- Categorisation is entirely determined by acc_id + drcr_account at the point
-- of use — there is no `category` column on this table.
CREATE TABLE IF NOT EXISTS accounts (
    id                   SERIAL PRIMARY KEY,
    society_id           INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    name                 VARCHAR(100) NOT NULL,
    tab_name             VARCHAR(20),                    -- Excel ledger tab grouping only
    header               VARCHAR(50),
    parent_account_id    INT,
    drcr_account         VARCHAR(2) CHECK (drcr_account IN ('Dr','Cr') OR drcr_account IS NULL),
    has_bf               BOOLEAN DEFAULT FALSE,
    drcr_bf              VARCHAR(2) NOT NULL CHECK (drcr_bf IN ('Dr','Cr')),
    bf_amount            NUMERIC(12,2) DEFAULT 0.00,
    depreciation_percent NUMERIC(5,2)  DEFAULT 100.00,
    is_depreciable       BOOLEAN DEFAULT FALSE,
    created_at           TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_account_society_name UNIQUE (society_id, name),
    CONSTRAINT fk_account_parent FOREIGN KEY (parent_account_id)
        REFERENCES accounts(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS apartments (
    id              SERIAL PRIMARY KEY,
    society_id      INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    flat_number     VARCHAR(20) NOT NULL,
    owner_name      VARCHAR(100),
    owner_photo     VARCHAR(255),
    id_proof        VARCHAR(255),
    mobile          VARCHAR(15),
    apartment_size  INT NOT NULL DEFAULT 0,
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_apartment_society_flat UNIQUE (society_id, flat_number)
);

CREATE TABLE IF NOT EXISTS vendors (
    id                  SERIAL PRIMARY KEY,
    society_id          INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    business_name       VARCHAR(100) NOT NULL,
    logo                VARCHAR(255),
    license             VARCHAR(255),
    name                VARCHAR(100),
    photo               VARCHAR(255),
    service_type        VARCHAR(100),
    mobile              VARCHAR(15),
    service_description TEXT,
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS security_staff (
    id               SERIAL PRIMARY KEY,
    society_id       INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    name             VARCHAR(100) NOT NULL,
    photo            VARCHAR(255),
    id_proof         VARCHAR(255),
    mobile           VARCHAR(15),
    joining_date     DATE DEFAULT CURRENT_DATE,
    shift            VARCHAR(20),
    salary_per_shift NUMERIC(10,2),
    active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS asset_register (
    id                   SERIAL PRIMARY KEY,
    society_id           INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    company_name         VARCHAR(100),
    asset_name           VARCHAR(100) NOT NULL,
    asset_SNo            VARCHAR(50),
    purchase_date        DATE,
    purchase_value       NUMERIC(12,2),
    parent_account_id    INT REFERENCES accounts(id),  -- asset class account (e.g. Furniture 61)
    depreciation_rate    NUMERIC(5,2),
    last_depreciation_date DATE,
    disposed             BOOLEAN NOT NULL DEFAULT FALSE,
    disposed_at          DATE,
    sale_value           NUMERIC(12,2),
    sale_acc_id          INT REFERENCES accounts(id),  -- Selling Asset income account (e.g. 212)
    disposed_by          INT REFERENCES users(id),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id                SERIAL PRIMARY KEY,
    society_id        INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    title             VARCHAR(200) NOT NULL,
    description       TEXT,
    event_date        DATE NOT NULL,
    event_time        TIME,
    venue             VARCHAR(200),
    open_to           VARCHAR(20) DEFAULT 'all',
    parent_account_id INT REFERENCES accounts(id),  -- e.g. event income or event expense account
    image             TEXT,
    created_at        TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS concerns (
    id             SERIAL PRIMARY KEY,
    society_id     INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    flat_no        VARCHAR(20),
    concern_type   VARCHAR(50),
    description    TEXT,
    preferred_time VARCHAR(20),
    status         VARCHAR(20) NOT NULL DEFAULT 'open',
    assigned_to    VARCHAR(100),
    image          TEXT,
    created_at     TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ── security_roster & attendance (needed before payments FK) ──
CREATE TABLE IF NOT EXISTS security_roster (
    id           SERIAL PRIMARY KEY,
    society_id   INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    security_id  INT NOT NULL REFERENCES security_staff(id) ON DELETE CASCADE,
    roster_date  DATE NOT NULL,
    shift_type   VARCHAR(20) CHECK (shift_type IN ('morning','evening','night')),
    assigned_by  INT REFERENCES users(id),
    created_at   TIMESTAMP DEFAULT NOW(),
    UNIQUE (society_id, security_id, roster_date)
);

CREATE TABLE IF NOT EXISTS attendance (
    id          SERIAL PRIMARY KEY,
    society_id  INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    security_id INT NOT NULL REFERENCES security_staff(id) ON DELETE CASCADE,
    time_in     TIMESTAMP,
    time_out    TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════
-- RECEIVABLES  — auto-credits, one row per entity per billing period.
--
-- KEY DESIGN:
--   acc_id       → the income account this receivable maps to when posted
--                  (e.g. 2311 = Society Maintenance Charge for maintenance rows).
--                  Set by the generator function; flows directly into transactions
--                  when fn_verify_receivable / fn_pay_apartment_dues_fifo run.
--   interest_acc_id → separate income account for the interest component
--                  (e.g. 211 = Interest Income). If NULL, interest is posted
--                  to the same acc_id as the base amount.
--   description  → acc_particulars that lands in transactions.transactions.
--                  DEFAULT pattern: 'Maintenance Apr-2025' / 'Salary Apr-2025'.
--   NO charge_type column — the account row itself is the category.
-- ════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS receivables (
    id                      SERIAL PRIMARY KEY,
    society_id              INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    entity_id               INT NOT NULL,
    role                    VARCHAR(20) NOT NULL CHECK (role IN ('apartment','vendor','security')),
    acc_id                  INT REFERENCES accounts(id),     -- income account for base amount
    interest_acc_id         INT REFERENCES accounts(id),     -- income account for interest (NULL = same as acc_id)
    description             TEXT NOT NULL DEFAULT 'Receivable',  -- becomes acc_particulars in transactions
    period_month            DATE,                            -- first-of-month; NULL for non-periodic rows
    base_amount             NUMERIC(10,2) NOT NULL DEFAULT 0,
    interest_amount         NUMERIC(10,2) NOT NULL DEFAULT 0,
    interest_months_applied INT NOT NULL DEFAULT 0,
    amount                  NUMERIC(10,2) NOT NULL CHECK (amount > 0),  -- base + interest, kept in sync
    paid_amount             NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (paid_amount >= 0),
    due_date                DATE,
    status                  VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','partial','unverified','paid','cancelled')),
    confirmed_by            INT REFERENCES users(id),
    confirmed_at            TIMESTAMP,
    created_at              TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_receivable_entity_month
    ON receivables(entity_id, role, period_month)
    WHERE period_month IS NOT NULL;

-- ── RECEIPTS — manual credits, deemed paid on creation ────────
CREATE TABLE IF NOT EXISTS receipts (
    id              SERIAL PRIMARY KEY,
    society_id      INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    user_id         INT REFERENCES users(id),
    entity_id       INT,
    role            VARCHAR(20) CHECK (role IN ('apartment','vendor','security','other')),
    receipt_date    DATE NOT NULL,
    acc_id          INT REFERENCES accounts(id),   -- income account (Cr) — IS the category
    particulars     TEXT NOT NULL,                 -- human-readable label; suggested from Python PARTICULARS_TEMPLATES
    amount          NUMERIC(10,2) NOT NULL CHECK (amount > 0),
    mode            VARCHAR(20) DEFAULT 'cash'
        CHECK (mode IN ('cash','cheque','upi','card','bank','crypto')),
    cheque_no       VARCHAR(50),
    transaction_id  VARCHAR(255),
    status          VARCHAR(20) NOT NULL DEFAULT 'confirmed'
        CHECK (status IN ('pending','confirmed','cancelled')),
    confirmed_by    INT REFERENCES users(id),
    confirmed_at    TIMESTAMP DEFAULT NOW(),
    last_printed_at TIMESTAMP,
    last_emailed_at TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ── EXPENSES — manual debits, deemed paid on creation ─────────
CREATE TABLE IF NOT EXISTS expenses (
    id              SERIAL PRIMARY KEY,
    society_id      INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    user_id         INT REFERENCES users(id),
    entity_id       INT,
    role            VARCHAR(20) CHECK (role IN ('vendor','security','other','assets')),
    expense_date    DATE NOT NULL,
    acc_id          INT REFERENCES accounts(id),   -- expense account (Dr) — IS the category
    particulars     TEXT NOT NULL,                 -- human-readable label; suggested from Python PARTICULARS_TEMPLATES
    amount          NUMERIC(10,2) NOT NULL CHECK (amount > 0),
    mode            VARCHAR(20) DEFAULT 'cash'
        CHECK (mode IN ('cash','cheque','upi','card','bank','crypto')),
    cheque_no       VARCHAR(50),
    transaction_id  VARCHAR(255),
    status          VARCHAR(20) NOT NULL DEFAULT 'confirmed'
        CHECK (status IN ('pending','confirmed','cancelled')),
    confirmed_by    INT REFERENCES users(id),
    confirmed_at    TIMESTAMP DEFAULT NOW(),
    last_printed_at TIMESTAMP,
    last_emailed_at TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ════════════════════════════════════════════════════════════════
-- PAYMENTS  — auto-debits (security payroll from roster).
--
-- KEY DESIGN:
--   acc_id       → expense account for this payment
--                  (e.g. 235 = Salary). Set by fn_auto_generate_payments;
--                  flows directly into transactions on fn_verify_payment.
--   description  → acc_particulars in transactions.
--                  DEFAULT pattern: 'Salary Apr-2025'.
--   NO payment_type column — acc_id IS the type.
--   roster_id    → UNIQUE, prevents double-billing one shift.
-- ════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS payments (
    id           SERIAL PRIMARY KEY,
    society_id   INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    entity_id    INT,                               -- security_staff.id
    role         VARCHAR(20) CHECK (role IN ('apartment','vendor','security','other')),
    acc_id       INT REFERENCES accounts(id),       -- expense account (Dr) — IS the category
    description  TEXT NOT NULL DEFAULT 'Payment',   -- becomes acc_particulars in transactions
    roster_id    INT REFERENCES security_roster(id),
    shift_date   DATE,
    amount       NUMERIC(10,2) NOT NULL,
    mode         VARCHAR(20),
    status       VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','verified','failed','cancelled')),
    due_date     DATE,
    paid_at      TIMESTAMP,
    confirmed_by INT REFERENCES users(id),
    confirmed_at TIMESTAMP,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_payment_roster UNIQUE (roster_id)
);

-- ── TRANSACTIONS — single ledger source of truth ───────────────
-- source_table / source_id trace every row back to its origin
-- (receipts / expenses / receivables / payments).
CREATE TABLE IF NOT EXISTS transactions (
    id                 SERIAL PRIMARY KEY,
    society_id         INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    trx_date           DATE NOT NULL,
    acc_id             INT REFERENCES accounts(id),
    entity_id          INTEGER,
    acc_particulars    VARCHAR(200),
    amount             NUMERIC(15,2) NOT NULL CHECK (amount > 0),
    mode               VARCHAR(10) DEFAULT 'cash'
        CHECK (mode IN ('cash','cheque','upi','card','bank','crypto')),
    payment_gateway_id VARCHAR(50),
    status             VARCHAR(20) NOT NULL DEFAULT 'paid',
    source_table       VARCHAR(50),
    source_id          INT,
    created_by         INTEGER REFERENCES users(id),
    created_at         TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ── Vendor passes ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vendor_passes (
    id          SERIAL PRIMARY KEY,
    society_id  INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    user_id     INT NOT NULL REFERENCES users(id),
    pass_type   VARCHAR(20) NOT NULL DEFAULT '1day'
        CHECK (pass_type IN ('1day','7day','1mth')),
    issued_date DATE DEFAULT CURRENT_DATE,
    valid_until DATE NOT NULL,
    status      VARCHAR(20) DEFAULT 'active',
    created_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (society_id, user_id, issued_date)
);

-- ── Apartment charges / fines basis ───────────────────────────
-- apt_id NULL = society-wide default rate; apt_id = override for one apartment.
-- apt_interest_pct = flat % compounded monthly on the overdue residual of each
-- monthly receivable row (was apt_delay_fine in old schema).
-- apt_maintenance_acc_id = which income account (e.g. 2311) to put on generated receivable rows.
-- apt_interest_acc_id    = which income account for interest portion (e.g. 211). NULL = same as maintenance.
CREATE TABLE IF NOT EXISTS apt_charges_fines_basis
 (
    id                     SERIAL PRIMARY KEY,
    society_id             INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    apt_id                 INT REFERENCES apartments(id),
    start_date             DATE NOT NULL,
    end_date               DATE,
    apt_maintenance_rate   NUMERIC(10,4) NOT NULL DEFAULT 3.0,
    apt_due_day            INTEGER DEFAULT 5,
    apt_interest_pct       NUMERIC(5,2) DEFAULT 2.0,
    apt_status             BOOLEAN DEFAULT TRUE,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- apt_charges index on society + apt for the per-apartment rule lookup
CREATE INDEX IF NOT EXISTS idx_apt_charges_society ON apt_charges_fines_basis(society_id, apt_id);

-- ── Vendor charges ─────────────────────────────────────────────
-- vendor_fine removed — ad-hoc fines are manual receipts.
-- ven_maintenance_acc_id = income account for pass-sale receipts generated
-- by fn_sell_vendor_pass (e.g. 2318 = Society Charge / pass fees income).
CREATE TABLE IF NOT EXISTS ven_charges_fines_basis (
    id                    SERIAL PRIMARY KEY,
    society_id            INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    ven_id                INT REFERENCES vendors(id),
    start_date            DATE NOT NULL,
    end_date              DATE,
    vendor_1day           NUMERIC(10,2) DEFAULT 0,
    vendor_7day           NUMERIC(10,2) DEFAULT 0,
    vendor_1mth           NUMERIC(10,2) DEFAULT 0,
    ven_status            BOOLEAN DEFAULT TRUE,
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ── sec_charges_fines_basis removed — security no longer generates
--    receivables. Security payroll flows entirely through payments
--    (roster-driven), with a salary expense account (235) set on each row.

-- ── Gate access & other tables ─────────────────────────────────
CREATE TABLE IF NOT EXISTS gate_access (
    id         SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    entity_id  INTEGER NOT NULL,
    role       VARCHAR(20),
    time_in    TIMESTAMP NOT NULL DEFAULT NOW(),
    time_out   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS role_permissions (
    id         SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies(id) ON DELETE CASCADE,
    role       VARCHAR(20) NOT NULL,
    card_id    VARCHAR(100) NOT NULL,
    permission VARCHAR(20) NOT NULL CHECK (permission IN ('view','create','edit','delete')),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (society_id, role, card_id, permission)
);

CREATE TABLE IF NOT EXISTS society_settings (
    id          SERIAL PRIMARY KEY,
    society_id  INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    key         VARCHAR(100) NOT NULL,
    value       TEXT,
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (society_id, key)   -- required: matches _upsert_layout's
                               -- ON CONFLICT (society_id, key) target exactly
);
 

-- ════════════════════════════════════════════════════════════════
-- SECTION 2: INDEXES
-- ════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_users_email              ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_society_role       ON users(society_id, role);
CREATE INDEX IF NOT EXISTS idx_apartments_society       ON apartments(society_id);
CREATE INDEX IF NOT EXISTS idx_apartments_active        ON apartments(society_id, active);
CREATE INDEX IF NOT EXISTS idx_vendors_society          ON vendors(society_id);
CREATE INDEX IF NOT EXISTS idx_security_society         ON security_staff(society_id);
CREATE INDEX IF NOT EXISTS idx_accounts_society         ON accounts(society_id);
CREATE INDEX IF NOT EXISTS idx_accounts_drcr            ON accounts(society_id, drcr_account);
CREATE INDEX IF NOT EXISTS idx_transactions_society_date ON transactions(society_id, trx_date DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_source      ON transactions(source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_payments_society_status  ON payments(society_id, status);
CREATE INDEX IF NOT EXISTS idx_payments_roster          ON payments(roster_id);
CREATE INDEX IF NOT EXISTS idx_receipts_society_status  ON receipts(society_id, status);
CREATE INDEX IF NOT EXISTS idx_expenses_society_status  ON expenses(society_id, status);
CREATE INDEX IF NOT EXISTS idx_receivables_society_status ON receivables(society_id, status);
CREATE INDEX IF NOT EXISTS idx_receivables_entity       ON receivables(entity_id, role);
CREATE INDEX IF NOT EXISTS idx_receivables_due_date     ON receivables(due_date);
CREATE INDEX IF NOT EXISTS idx_events_society_date      ON events(society_id, event_date);
CREATE INDEX IF NOT EXISTS idx_concerns_society_status  ON concerns(society_id, status);
CREATE INDEX IF NOT EXISTS idx_gate_society_time        ON gate_access(society_id, time_in);
CREATE INDEX IF NOT EXISTS idx_security_roster_date     ON security_roster(society_id, roster_date);
CREATE INDEX IF NOT EXISTS idx_attendance_security_date ON attendance(security_id, time_in);
CREATE INDEX IF NOT EXISTS idx_ven_charges_society      ON ven_charges_fines_basis(society_id, ven_id);
CREATE INDEX IF NOT EXISTS idx_ven_charges_status       ON ven_charges_fines_basis(society_id, ven_status);
CREATE INDEX IF NOT EXISTS idx_vendor_passes_user       ON vendor_passes(user_id, valid_until);
CREATE INDEX IF NOT EXISTS idx_asset_register_society   ON asset_register(society_id, disposed);
CREATE INDEX IF NOT EXISTS idx_society_settings_lookup  ON society_settings(society_id, key);

-- ════════════════════════════════════════════════════════════════
-- SECTION 3: APARTMENT HELPER FUNCTIONS (used by trigger + gate pass + NOC)
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_apartment_outstanding CASCADE;
CREATE OR REPLACE FUNCTION fn_apartment_outstanding(p_apartment_id INT)
RETURNS NUMERIC(15,2) LANGUAGE SQL STABLE AS $$
    SELECT COALESCE(SUM(amount - paid_amount), 0)::NUMERIC(15,2)
    FROM receivables r
    WHERE r.entity_id = p_apartment_id AND r.role = 'apartment'
      AND r.status IN ('pending','partial');
$$;

DROP FUNCTION IF EXISTS fn_apartment_overdue_outstanding CASCADE;
CREATE OR REPLACE FUNCTION fn_apartment_overdue_outstanding(p_apartment_id INT)
RETURNS NUMERIC(15,2) LANGUAGE SQL STABLE AS $$
    SELECT COALESCE(SUM(amount - paid_amount), 0)::NUMERIC(15,2)
    FROM receivables r
    WHERE r.entity_id = p_apartment_id AND r.role = 'apartment'
      AND r.status IN ('pending','partial')
      AND r.due_date < CURRENT_DATE;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 3A: APARTMENT ACTIVE-STATE TRIGGER
-- Blocks toggling apartments.active in EITHER direction while ANY
-- outstanding balance exists (all dues, not just overdue ones).
-- ════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_trg_apartment_active_guard()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_outstanding NUMERIC(15,2);
BEGIN
    IF NEW.active IS DISTINCT FROM OLD.active THEN
        v_outstanding := fn_apartment_outstanding(OLD.id);
        IF v_outstanding > 0 THEN
            RAISE EXCEPTION
                'Cannot change active status for flat %: outstanding dues of Rs.%',
                OLD.flat_number, v_outstanding
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_apartment_active_guard ON apartments;
CREATE TRIGGER trg_apartment_active_guard
    BEFORE UPDATE ON apartments
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_apartment_active_guard();

-- ════════════════════════════════════════════════════════════════
-- SECTION 3B: GATE-PASS EVALUATION
-- Single callable for the QR scanner. Returns (passed, reason, amount_due).
-- Apartment: FAILS only on OVERDUE residual (not future billing).
-- Vendor:    FAILS when no vendor_passes row has valid_until >= today.
-- Security:  FAILS when not clocked in (no open gate_access row with role='s').
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_evaluate_gate_pass CASCADE;
CREATE OR REPLACE FUNCTION fn_evaluate_gate_pass(p_role VARCHAR, p_entity_id INT)
RETURNS TABLE(passed BOOLEAN, reason TEXT, amount_due NUMERIC(15,2))
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_overdue     NUMERIC(15,2);
    v_pass_expiry DATE;
    v_on_duty     BOOLEAN;
BEGIN
    IF p_role = 'apartment' THEN
        v_overdue := fn_apartment_overdue_outstanding(p_entity_id);
        IF v_overdue > 0 THEN
            RETURN QUERY SELECT FALSE,
                ('Overdue maintenance dues Rs.' || v_overdue::TEXT)::TEXT, v_overdue;
        ELSE
            RETURN QUERY SELECT TRUE, 'Dues clear'::TEXT, 0::NUMERIC(15,2);
        END IF;

    ELSIF p_role = 'vendor' THEN
        SELECT MAX(valid_until) INTO v_pass_expiry
        FROM vendor_passes WHERE user_id = p_entity_id AND status = 'active';
        IF v_pass_expiry IS NULL OR v_pass_expiry < CURRENT_DATE THEN
            RETURN QUERY SELECT FALSE, 'No active vendor pass'::TEXT, 0::NUMERIC(15,2);
        ELSE
            RETURN QUERY SELECT TRUE,
                ('Pass valid until ' || v_pass_expiry::TEXT)::TEXT, 0::NUMERIC(15,2);
        END IF;

    ELSIF p_role = 'security' THEN
        SELECT EXISTS(
            SELECT 1 FROM gate_access
            WHERE entity_id = p_entity_id AND role = 's' AND time_out IS NULL
        ) INTO v_on_duty;
        IF NOT v_on_duty THEN
            RETURN QUERY SELECT FALSE, 'Not currently on duty'::TEXT, 0::NUMERIC(15,2);
        ELSE
            RETURN QUERY SELECT TRUE, 'On duty'::TEXT, 0::NUMERIC(15,2);
        END IF;

    ELSE
        RETURN QUERY SELECT FALSE,
            ('Unknown role: ' || COALESCE(p_role,'NULL'))::TEXT, 0::NUMERIC(15,2);
    END IF;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 3C: NOC ELIGIBILITY
-- ALL outstanding dues (not just overdue) must be zero.
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_check_noc_eligibility CASCADE;
CREATE OR REPLACE FUNCTION fn_check_noc_eligibility(p_apartment_id INT)
RETURNS TABLE(eligible BOOLEAN, reason TEXT, outstanding NUMERIC(15,2))
LANGUAGE plpgsql STABLE AS $$
DECLARE v_total NUMERIC(15,2);
BEGIN
    v_total := fn_apartment_outstanding(p_apartment_id);
    IF v_total > 0 THEN
        RETURN QUERY SELECT FALSE,
            ('Outstanding dues Rs.' || v_total::TEXT || ' — clear before NOC')::TEXT, v_total;
    ELSE
        RETURN QUERY SELECT TRUE, 'No outstanding dues — eligible for NOC'::TEXT, 0::NUMERIC(15,2);
    END IF;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 4: RECEIVABLES ENGINE (apartment maintenance, monthly)
-- ════════════════════════════════════════════════════════════════

-- Generates one receivable row per apartment per calendar month from
-- society.calc_start_date through the current month. Idempotent via the
-- partial unique index. The acc_id and interest_acc_id come from the
-- apt_charges_fines_basis row for that apartment/society.
CREATE OR REPLACE FUNCTION fn_auto_generate_receivables(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    v_calc_start  DATE;
    v_month       DATE;
    apt           RECORD;
    charge        RECORD;
    v_base        NUMERIC(10,2);
    v_due_date    DATE;
    v_desc        TEXT;
    -- fallback account IDs resolved once per society call
    v_fallback_maint_acc  INT;
    v_fallback_int_acc    INT;
BEGIN
    SELECT calc_start_date INTO v_calc_start FROM societies WHERE id = p_society_id;
    IF v_calc_start IS NULL THEN RETURN; END IF;
 
    -- Resolve fallback accounts ONCE (same logic as fn_pay_apartment_dues_fifo)
    SELECT id INTO v_fallback_maint_acc FROM accounts
    WHERE society_id = p_society_id
      AND name ILIKE '%Society Maintenance Charge%'
      AND drcr_account = 'Cr'
    LIMIT 1;
 
    SELECT id INTO v_fallback_int_acc FROM accounts
    WHERE society_id = p_society_id
      AND name ILIKE '%Due Interest%'
      AND drcr_account = 'Cr'
    LIMIT 1;
 
    FOR apt IN
        SELECT id, apartment_size FROM apartments
        WHERE society_id = p_society_id AND active = TRUE
    LOOP
        SELECT apt_maintenance_rate, apt_due_day, apt_interest_pct
        INTO charge
        FROM apt_charges_fines_basis
        WHERE society_id = p_society_id AND apt_status = TRUE
          AND (apt_id = apt.id OR apt_id IS NULL)
          AND start_date <= CURRENT_DATE
          AND (end_date IS NULL OR end_date >= CURRENT_DATE)
        ORDER BY apt_id NULLS LAST, start_date DESC
        LIMIT 1;
 
        IF charge.apt_maintenance_rate IS NULL THEN
            charge.apt_maintenance_rate := 3.0;
            charge.apt_due_day          := 5;
            charge.apt_interest_pct     := 2.0;
        END IF;
 
        -- Also patch existing NULL rows for this apartment while we are here
        UPDATE receivables
        SET acc_id          = COALESCE(acc_id, v_fallback_maint_acc),
            interest_acc_id = COALESCE(interest_acc_id, v_fallback_int_acc)
        WHERE society_id = p_society_id
          AND entity_id  = apt.id
          AND role       = 'apartment'
          AND (acc_id IS NULL OR interest_acc_id IS NULL);
 
        v_month := DATE_TRUNC('month', v_calc_start)::DATE;
        WHILE v_month <= DATE_TRUNC('month', CURRENT_DATE)::DATE LOOP
            v_base     := (apt.apartment_size * charge.apt_maintenance_rate)::NUMERIC(10,2);
            v_due_date := (v_month + ((COALESCE(charge.apt_due_day,5) - 1) * INTERVAL '1 day'))::DATE;
            v_desc     := 'Maintenance ' || TO_CHAR(v_month, 'Mon-YYYY');
 
            INSERT INTO receivables (
                society_id, entity_id, role,
                acc_id, interest_acc_id,
                description, period_month,
                base_amount, amount, due_date, status, created_at
            ) VALUES (
                p_society_id, apt.id, 'apartment',
                v_fallback_maint_acc, v_fallback_int_acc,
                v_desc, v_month,
                v_base, v_base, v_due_date, 'pending', NOW()
            )
            ON CONFLICT (entity_id, role, period_month)
            WHERE period_month IS NOT NULL
            DO NOTHING;
 
            v_month := (v_month + INTERVAL '1 month')::DATE;
        END LOOP;
    END LOOP;
END;
$$;
 
-- Compounds apt_interest_pct monthly on the OVERDUE RESIDUAL of each row.
-- interest_months_applied prevents double-application across multiple calls.
-- On each application the `description` gains ' + Interest' so the verifying
-- admin can see at a glance that this row carries an interest component.
CREATE OR REPLACE FUNCTION fn_save_receipt_pending(
    p_society_id   INT,
    p_acc_id       INT,
    p_particulars  TEXT,
    p_amount       NUMERIC,
    p_entity_id    INT     DEFAULT NULL,
    p_role         VARCHAR DEFAULT 'other',
    p_mode         VARCHAR DEFAULT 'cash',
    p_receipt_date DATE    DEFAULT CURRENT_DATE,
    p_created_by   INT     DEFAULT NULL,
    p_cheque_no    VARCHAR DEFAULT NULL,
    p_trx_id       VARCHAR DEFAULT NULL
)
RETURNS TABLE(receipt_id INT)  -- NO transaction_id: transaction posted only on admin verify
LANGUAGE plpgsql AS $$
DECLARE v_receipt_id INT; v_drcr VARCHAR(2);
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN RAISE EXCEPTION 'Amount must be > 0'; END IF;
    IF p_acc_id IS NULL THEN RAISE EXCEPTION 'acc_id is required'; END IF;
    IF p_particulars IS NULL OR TRIM(p_particulars) = '' THEN RAISE EXCEPTION 'particulars is required'; END IF;

    SELECT drcr_account INTO v_drcr FROM accounts
    WHERE id = p_acc_id AND society_id = p_society_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Account % not found', p_acc_id; END IF;
    IF v_drcr = 'Dr' THEN
        RAISE EXCEPTION 'Account % is a Dr account — use fn_save_expense', p_acc_id;
    END IF;

    INSERT INTO receipts(
        society_id, user_id, entity_id, role, receipt_date, acc_id, particulars,
        amount, mode, cheque_no, transaction_id, status, created_at
        -- confirmed_by / confirmed_at intentionally NULL until admin verifies
    ) VALUES (
        p_society_id, p_created_by, p_entity_id, p_role, p_receipt_date, p_acc_id, p_particulars,
        p_amount, p_mode, p_cheque_no, p_trx_id, 'pending', NOW()
    ) RETURNING id INTO v_receipt_id;

    RETURN QUERY SELECT v_receipt_id;
END;
$$;

-- Admin verify: post pending receipt to transactions and mark confirmed
CREATE OR REPLACE FUNCTION fn_verify_receipt(
    p_receipt_id   INT,
    p_confirmed_by INT,
    p_mode         VARCHAR DEFAULT NULL   -- NULL = use receipt's own mode
)
RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
    v_rec    receipts%ROWTYPE;
    v_trx_id INT;
BEGIN
    SELECT * INTO v_rec FROM receipts WHERE id = p_receipt_id FOR UPDATE;
    IF NOT FOUND    THEN RETURN 'Error: Receipt not found'; END IF;
    IF v_rec.status = 'confirmed'  THEN RETURN 'Already confirmed'; END IF;
    IF v_rec.status = 'cancelled'  THEN RETURN 'Error: Receipt is cancelled'; END IF;
    IF v_rec.acc_id IS NULL        THEN RETURN 'Error: No income account on this receipt'; END IF;

    INSERT INTO transactions(
        society_id, trx_date, acc_id, entity_id, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id
    ) VALUES (
        v_rec.society_id, v_rec.receipt_date, v_rec.acc_id, v_rec.entity_id,
        v_rec.particulars,
        v_rec.amount, COALESCE(p_mode, v_rec.mode), 'paid',
        p_confirmed_by, NOW(), 'receipts', v_rec.id
    ) RETURNING id INTO v_trx_id;

    UPDATE receipts
    SET status       = 'confirmed',
        confirmed_by = p_confirmed_by,
        confirmed_at = NOW()
    WHERE id = p_receipt_id;

    RETURN 'Verified: transaction #' || v_trx_id::TEXT;
END;
$$;

DROP FUNCTION IF EXISTS fn_apply_receivable_interest CASCADE;
CREATE OR REPLACE FUNCTION fn_apply_receivable_interest(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    rec               RECORD;
    v_rate            NUMERIC(5,2);
    v_months_elapsed  INT;
    v_months_new      INT;
    v_residual        NUMERIC(15,2);
    v_increment       NUMERIC(15,2);
    v_total_increment NUMERIC(15,2);
    i                 INT;
    v_int_acc_id      INT;
BEGIN
    -- Resolve once per society call — apt_interest_acc_id column removed,
    -- interest income account is now name-resolved (same pattern used
    -- elsewhere: fn_auto_generate_receivables, fn_create_default_charges).
    SELECT id INTO v_int_acc_id FROM accounts
    WHERE society_id = p_society_id
      AND name ILIKE '%Due Interest%'
      AND drcr_account = 'Cr'
    LIMIT 1;
 
    FOR rec IN
        SELECT r.id, r.entity_id, r.due_date, r.amount, r.paid_amount,
               r.interest_amount, r.interest_months_applied,
               r.description, r.interest_acc_id
        FROM receivables r
        WHERE r.society_id = p_society_id AND r.role = 'apartment'
          AND r.status IN ('pending','partial')
          AND r.due_date < CURRENT_DATE
        FOR UPDATE
    LOOP
        -- Look up interest RATE only — acc_id column removed from
        -- apt_charges_fines_basis; v_int_acc_id (resolved above) is
        -- used as the fallback instead.
        SELECT apt_interest_pct
        INTO v_rate
        FROM apt_charges_fines_basis
        WHERE society_id = p_society_id AND apt_status = TRUE
          AND (apt_id = rec.entity_id OR apt_id IS NULL)
        ORDER BY apt_id NULLS LAST, start_date DESC
        LIMIT 1;
 
        IF v_rate IS NULL OR v_rate = 0 THEN CONTINUE; END IF;
 
        v_months_elapsed := GREATEST(
            (EXTRACT(YEAR  FROM AGE(CURRENT_DATE, rec.due_date)) * 12
           + EXTRACT(MONTH FROM AGE(CURRENT_DATE, rec.due_date)))::INT, 0);
        v_months_new := v_months_elapsed - rec.interest_months_applied;
        IF v_months_new <= 0 THEN CONTINUE; END IF;
 
        v_residual        := rec.amount - rec.paid_amount;
        v_total_increment := 0;
        FOR i IN 1..v_months_new LOOP
            v_increment := (v_residual * v_rate / 100)::NUMERIC(15,2);
            v_residual  := v_residual + v_increment;
            v_total_increment := v_total_increment + v_increment;
        END LOOP;
 
        UPDATE receivables
             SET interest_amount         = rec.interest_amount + v_total_increment,
                 amount                  = rec.amount + v_total_increment,
                 interest_months_applied = rec.interest_months_applied + v_months_new,
                 interest_acc_id         = COALESCE(rec.interest_acc_id, v_int_acc_id),
                 -- Append ' + Interest' to description once, so the verifying
                 -- admin can see at a glance that this row carries an interest component.
                 description = CASE
                     WHEN rec.description NOT LIKE '% + Interest' THEN rec.description || ' + Interest'
                     ELSE rec.description
                 END
             WHERE id = rec.id;
    END LOOP;
END;
$$;

-- Single-row verify (the Verify button on a specific receivable row).
-- Writes TWO transaction lines when the row has an interest component:
--   Line 1: base_amount → acc_id           (maintenance income, e.g. 2311)
--   Line 2: interest_amount → interest_acc_id (interest income, e.g. 211)
-- If interest_acc_id IS NULL, interest folds into Line 1.
DROP FUNCTION IF EXISTS fn_verify_receivable CASCADE;
CREATE OR REPLACE FUNCTION fn_verify_receivable(
    p_receivable_id INT,
    p_confirmed_by  INT,
    p_mode          VARCHAR DEFAULT 'cash'
)
RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
    v_rec         receivables%ROWTYPE;
    v_residual    NUMERIC(15,2);
    v_base_post   NUMERIC(15,2);
    v_int_post    NUMERIC(15,2);
    v_int_acc     INT;
    v_trx_id      INT;
BEGIN
    SELECT * INTO v_rec FROM receivables WHERE id = p_receivable_id FOR UPDATE;
    IF NOT FOUND THEN RETURN 'Error: Receivable not found'; END IF;
    IF v_rec.status = 'paid' THEN RETURN 'Already fully paid'; END IF;
    IF v_rec.acc_id IS NULL THEN RETURN 'Error: No income account set on this receivable — check apt_charges_fines_basis'; END IF;

    v_residual := v_rec.amount - v_rec.paid_amount;
    IF v_residual <= 0 THEN RETURN 'Nothing outstanding on this row'; END IF;

    v_int_acc  := v_rec.interest_acc_id;           -- may be NULL
    v_int_post := LEAST(v_rec.interest_amount - GREATEST(v_rec.paid_amount - v_rec.base_amount, 0), v_residual);
    v_int_post := GREATEST(COALESCE(v_int_post, 0), 0);
    v_base_post := v_residual - v_int_post;

    -- Line 1: base maintenance income (or full amount if no interest split)
    IF v_int_acc IS NOT NULL AND v_int_post > 0 THEN
        INSERT INTO transactions(
            society_id, trx_date, acc_id, entity_id, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id
        ) VALUES (
            v_rec.society_id, CURRENT_DATE, v_rec.acc_id, v_rec.entity_id,
            REPLACE(v_rec.description, ' + Interest', ''),
            v_base_post, p_mode, 'paid', p_confirmed_by, NOW(), 'receivables', v_rec.id
        ) RETURNING id INTO v_trx_id;

        -- Line 2: interest income to separate account
        INSERT INTO transactions(
            society_id, trx_date, acc_id, entity_id, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id
        ) VALUES (
            v_rec.society_id, CURRENT_DATE, v_int_acc, v_rec.entity_id,
            'Interest on ' || REPLACE(v_rec.description, ' + Interest', ''),
            v_int_post, p_mode, 'paid', p_confirmed_by, NOW(), 'receivables', v_rec.id
        );
    ELSE
        -- Single line: full residual goes to maintenance income account
        INSERT INTO transactions(
            society_id, trx_date, acc_id, entity_id, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id
        ) VALUES (
            v_rec.society_id, CURRENT_DATE, v_rec.acc_id, v_rec.entity_id,
            v_rec.description,
            v_residual, p_mode, 'paid', p_confirmed_by, NOW(), 'receivables', v_rec.id
        ) RETURNING id INTO v_trx_id;
    END IF;

    UPDATE receivables
         SET paid_amount  = v_rec.amount,
             status       = 'paid',
             confirmed_by = p_confirmed_by,
             confirmed_at = NOW()
         WHERE id = p_receivable_id;

    RETURN 'Verified: transaction #' || v_trx_id::TEXT;
END;
$$;

-- Bulk FIFO payment across monthly rows (the "Pay Dues" button amount entry).
-- ONE transaction per call using the acc_id of the earliest unpaid row.
-- Interest split on bulk payment: interest folds into the single transaction
-- (does not split to interest_acc_id) to keep bulk-pay accounting simple.
-- For precise interest-split accounting use the per-row Verify button.
DROP FUNCTION IF EXISTS fn_pay_apartment_dues_fifo CASCADE;
CREATE OR REPLACE FUNCTION fn_pay_apartment_dues_fifo(
    p_apartment_id INT,
    p_amount       NUMERIC,
    p_mode         VARCHAR DEFAULT 'cash',
    p_confirmed_by INT     DEFAULT NULL,
    p_particulars  TEXT    DEFAULT NULL
)
RETURNS TABLE(transaction_id INT, allocated NUMERIC, unallocated NUMERIC)
LANGUAGE plpgsql AS $$
DECLARE
    v_society_id INT;
    v_acc_id     INT;
    v_desc       TEXT;
    v_remaining  NUMERIC(15,2) := p_amount;
    v_trx_id     INT;
    rec          RECORD;
    v_take       NUMERIC(15,2);
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN
        RAISE EXCEPTION 'Amount must be > 0';
    END IF;

    SELECT society_id INTO v_society_id FROM apartments WHERE id = p_apartment_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Apartment not found'; END IF;

    -- Use acc_id + description from the oldest unpaid row as the transaction label
    SELECT acc_id, description INTO v_acc_id, v_desc
    FROM receivables
    WHERE entity_id = p_apartment_id AND role = 'apartment'
      AND status IN ('pending','partial')
    ORDER BY due_date ASC NULLS LAST LIMIT 1;

    -- Fallback: find maintenance income account by well-known name
    IF v_acc_id IS NULL THEN
        SELECT id INTO v_acc_id FROM accounts
        WHERE society_id = v_society_id
          AND name ILIKE '%Society Maintenance Charge%'
          AND drcr_account = 'Cr'
        LIMIT 1;
    END IF;

    INSERT INTO transactions(
        society_id, trx_date, acc_id, entity_id, acc_particulars,
        amount, mode, status, created_by, created_at, source_table
    ) VALUES (
        v_society_id, CURRENT_DATE, v_acc_id, p_apartment_id,
        COALESCE(p_particulars, 'Maintenance Payment'),
        p_amount, p_mode, 'paid', p_confirmed_by, NOW(), 'receivables'
    ) RETURNING id INTO v_trx_id;

    FOR rec IN
        SELECT id, amount, paid_amount, confirmed_by FROM receivables
        WHERE entity_id = p_apartment_id AND role = 'apartment'
          AND status IN ('pending','partial')
        ORDER BY due_date ASC NULLS LAST, id ASC
        FOR UPDATE
    LOOP
        EXIT WHEN v_remaining <= 0;
        v_take := LEAST(v_remaining, rec.amount - rec.paid_amount);

        UPDATE receivables
             SET paid_amount   = rec.paid_amount + v_take,
                 status        = CASE WHEN rec.paid_amount + v_take >= rec.amount THEN 'paid' ELSE 'partial' END,
                 confirmed_by  = COALESCE(p_confirmed_by, rec.confirmed_by),
                 confirmed_at  = NOW()
             WHERE id = rec.id;

        v_remaining := v_remaining - v_take;
    END LOOP;

    -- Note: if v_remaining > 0 after all rows cleared, the excess is NOT
    -- applied anywhere (no advance-credit concept). The transaction row
    -- stands for the full p_amount paid; the diff is the unallocated return value.

    RETURN QUERY SELECT v_trx_id,
        (p_amount - v_remaining)::NUMERIC(15,2),
        v_remaining::NUMERIC(15,2);
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 5: PAYMENTS ENGINE (security payroll, roster-driven)
-- acc_id IS the category (235 = Salary); description IS the particulars.
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_auto_generate_payments CASCADE;
CREATE OR REPLACE FUNCTION fn_auto_generate_payments(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    rec          RECORD;
    v_user_id    INT;
    v_acc_id     INT;
    v_desc       TEXT;
BEGIN
    -- Find the salary expense account by well-known name
    SELECT id INTO v_acc_id FROM accounts
    WHERE society_id = p_society_id AND name ILIKE '%Salary%' AND drcr_account = 'Dr'
    LIMIT 1;

    FOR rec IN
        SELECT sr.id AS roster_id, sr.security_id, sr.roster_date, ss.salary_per_shift
        FROM security_roster sr
        JOIN security_staff ss ON ss.id = sr.security_id
        -- Only create payment when a matching attendance record shows time_out (shift completed)
        JOIN attendance att
             ON att.security_id = sr.security_id
            AND att.time_in::DATE = sr.roster_date
            AND att.time_out IS NOT NULL
        WHERE sr.society_id = p_society_id
          AND sr.roster_date <= CURRENT_DATE
          AND NOT EXISTS (SELECT 1 FROM payments p WHERE p.roster_id = sr.id)
    LOOP
        SELECT id INTO v_user_id FROM users
        WHERE linked_id = rec.security_id AND role = 'security' LIMIT 1;

        v_desc := 'Salary ' || TO_CHAR(rec.roster_date, 'DD-Mon-YYYY');

        INSERT INTO payments(
            society_id, entity_id, role, acc_id, description,
            roster_id, shift_date, amount, status, due_date, created_at
        ) VALUES (
            p_society_id, rec.security_id, 'security', v_acc_id, v_desc,
            rec.roster_id, rec.roster_date, COALESCE(rec.salary_per_shift, 0),
            'pending', rec.roster_date, NOW()
        );
    END LOOP;
END;
$$;

-- Single-row verify (admin Verify button on Payments tab).
-- acc_id and description come directly from the payments row.
DROP FUNCTION IF EXISTS fn_verify_payment CASCADE;
CREATE OR REPLACE FUNCTION fn_verify_payment(
    p_payment_id   INT,
    p_confirmed_by INT,
    p_mode         VARCHAR DEFAULT 'cash'
)
RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
    v_pay    payments%ROWTYPE;
    v_trx_id INT;
BEGIN
    SELECT * INTO v_pay FROM payments WHERE id = p_payment_id FOR UPDATE;
    IF NOT FOUND THEN RETURN 'Error: Payment not found'; END IF;
    IF v_pay.status = 'verified' THEN RETURN 'Already verified'; END IF;
    IF v_pay.acc_id IS NULL THEN RETURN 'Error: No expense account set on this payment row'; END IF;

    INSERT INTO transactions(
        society_id, trx_date, acc_id, entity_id, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id
    ) VALUES (
        v_pay.society_id, CURRENT_DATE, v_pay.acc_id, v_pay.entity_id,
        v_pay.description,
        v_pay.amount, p_mode, 'paid', p_confirmed_by, NOW(), 'payments', v_pay.id
    ) RETURNING id INTO v_trx_id;

    UPDATE payments
    SET status       = 'verified',
        confirmed_by = p_confirmed_by,
        confirmed_at = NOW(),
        paid_at      = NOW()
    WHERE id = p_payment_id;

    RETURN 'Verified: transaction #' || v_trx_id::TEXT;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 6: VENDOR PASS SALE
-- ════════════════════════════════════════════════════════════════
DROP FUNCTION IF EXISTS fn_sell_vendor_pass CASCADE;
CREATE OR REPLACE FUNCTION fn_sell_vendor_pass(
    p_user_id     INT,
    p_pass_type   VARCHAR,
    p_acc_id      INT     DEFAULT NULL,
    p_mode        VARCHAR DEFAULT 'cash',
    p_created_by  INT     DEFAULT NULL,
    p_issued_date DATE    DEFAULT CURRENT_DATE,
    p_particulars TEXT    DEFAULT NULL
)
RETURNS TABLE(receipt_id INT, pass_id INT, valid_until DATE)
LANGUAGE plpgsql AS $$
DECLARE
    v_society_id  INT;
    v_vendor_id   INT;
    v_vendor_name TEXT;
    v_rate        NUMERIC(10,2);
    v_valid_until DATE;
    v_acc_id      INT;
    v_receipt_id  INT;
    v_pass_id     INT;
    v_desc        TEXT;
BEGIN
    IF p_pass_type NOT IN ('1day','7day','1mth') THEN
        RAISE EXCEPTION 'Invalid pass_type %. Use 1day / 7day / 1mth', p_pass_type;
    END IF;
 
    SELECT society_id, linked_id INTO v_society_id, v_vendor_id
    FROM users WHERE id = p_user_id AND role = 'vendor';
    IF NOT FOUND THEN RAISE EXCEPTION 'Vendor user not found'; END IF;
 
    SELECT v.name INTO v_vendor_name FROM vendors v WHERE v.id = v_vendor_id;
 
    -- ven_pass_acc_id column removed — rate only
    SELECT CASE p_pass_type
        WHEN '1day' THEN vendor_1day
        WHEN '7day' THEN vendor_7day
        WHEN '1mth' THEN vendor_1mth
    END
    INTO v_rate
    FROM ven_charges_fines_basis
    WHERE society_id = v_society_id AND ven_status = TRUE
      AND (ven_id = v_vendor_id OR ven_id IS NULL)
    ORDER BY ven_id NULLS LAST, start_date DESC
    LIMIT 1;
 
    IF v_rate IS NULL THEN
        RAISE EXCEPTION 'No pass pricing configured for type % in ven_charges_fines_basis', p_pass_type;
    END IF;
 
    -- Caller-supplied acc_id wins; else resolve by name
    v_acc_id := p_acc_id;
    IF v_acc_id IS NULL THEN
        SELECT id INTO v_acc_id FROM accounts
        WHERE society_id = v_society_id AND name ILIKE '%Society Charge%' AND drcr_account = 'Cr'
        LIMIT 1;
    END IF;
 
    v_valid_until := CASE p_pass_type
        WHEN '1day' THEN p_issued_date + INTERVAL '1 day'
        WHEN '7day' THEN p_issued_date + INTERVAL '7 days'
        WHEN '1mth' THEN p_issued_date + INTERVAL '1 month'
    END::DATE;
 
    v_desc := COALESCE(p_particulars,
        'Vendor Pass (' || p_pass_type || ') - ' || COALESCE(v_vendor_name,''));
 
    -- Receipt: deemed paid immediately on creation
    INSERT INTO receipts(
        society_id, user_id, entity_id, role,
        receipt_date, acc_id, particulars, amount, mode,
        status, confirmed_by, confirmed_at, created_at
    ) VALUES (
        v_society_id, p_user_id, v_vendor_id, 'vendor',
        p_issued_date, v_acc_id, v_desc, v_rate, p_mode,
        'confirmed', p_created_by, NOW(), NOW()
    ) RETURNING id INTO v_receipt_id;
 
    -- Transaction (acc_id directly from receipt, description as particulars)
    INSERT INTO transactions(
        society_id, trx_date, acc_id, entity_id, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id
    ) VALUES (
        v_society_id, p_issued_date, v_acc_id, v_vendor_id, v_desc,
        v_rate, p_mode, 'paid', p_created_by, NOW(), 'receipts', v_receipt_id
    );
 
    -- Vendor pass
    INSERT INTO vendor_passes(
        society_id, user_id, pass_type, issued_date, valid_until, status, created_at
    ) VALUES (
        v_society_id, p_user_id, p_pass_type, p_issued_date, v_valid_until, 'active', NOW()
    ) RETURNING id INTO v_pass_id;
 
    RETURN QUERY SELECT v_receipt_id, v_pass_id, v_valid_until;
END;
$$;
-- ════════════════════════════════════════════════════════════════
-- SECTION 7: ASSET PURCHASE / DISPOSAL
-- fn_buy_asset:     creates asset_register row + expense row + transaction.
-- fn_dispose_asset: creates receipt row + transaction; marks asset disposed.
-- Both require parent_account_id on the asset row (the asset class account,
-- e.g. Furniture=61). acc_id on the expense/receipt is the flow account
-- (e.g. 234=Depreciation, 212=Selling Asset, 233=Miscellaneous).
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_buy_asset CASCADE;
CREATE OR REPLACE FUNCTION fn_buy_asset(
    p_society_id        INT,
    p_asset_name        VARCHAR,
    p_purchase_value    NUMERIC,
    p_parent_account_id INT,

    p_asset_type        VARCHAR DEFAULT NULL,
    p_purchase_date     DATE DEFAULT CURRENT_DATE,
    p_expense_acc_id    INT DEFAULT NULL,
    p_mode              VARCHAR DEFAULT 'cash',
    p_created_by        INT DEFAULT NULL,
    p_particulars       TEXT DEFAULT NULL
)
RETURNS TABLE(asset_id INT, expense_id INT)
LANGUAGE plpgsql AS $$
DECLARE
    v_asset_id   INT;
    v_expense_id INT;
    v_acc_id     INT;
    v_dep_rate   NUMERIC(5,2);
    v_desc       TEXT;
BEGIN
    IF p_parent_account_id IS NULL THEN
        RAISE EXCEPTION 'parent_account_id (asset class account) is required';
    END IF;
    IF p_purchase_value IS NULL OR p_purchase_value <= 0 THEN
        RAISE EXCEPTION 'purchase_value must be > 0';
    END IF;

    SELECT depreciation_percent INTO v_dep_rate FROM accounts WHERE id = p_parent_account_id;

    INSERT INTO asset_register(
        society_id, asset_name, asset_type, purchase_date, purchase_value,
        parent_account_id, depreciation_rate, created_at
    ) VALUES (
        p_society_id, p_asset_name, p_asset_type, p_purchase_date, p_purchase_value,
        p_parent_account_id, v_dep_rate, NOW()
    ) RETURNING id INTO v_asset_id;

    -- Resolve expense (Dr) account
    v_acc_id := p_expense_acc_id;
    IF v_acc_id IS NULL THEN
        SELECT id INTO v_acc_id FROM accounts
        WHERE society_id = p_society_id AND drcr_account = 'Dr' AND name ILIKE '%Miscellaneous%'
        LIMIT 1;
    END IF;

    v_desc := COALESCE(p_particulars, 'Asset Purchase - ' || p_asset_name);

    INSERT INTO expenses(
        society_id, user_id, entity_id, role, expense_date, acc_id,
        particulars, amount, mode, status, confirmed_by, confirmed_at, created_at
    ) VALUES (
        p_society_id, p_created_by, v_asset_id, 'assets', p_purchase_date, v_acc_id,
        v_desc, p_purchase_value, p_mode, 'confirmed', p_created_by, NOW(), NOW()
    ) RETURNING id INTO v_expense_id;

    INSERT INTO transactions(
        society_id, trx_date, acc_id, entity_id, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id
    ) VALUES (
        p_society_id, p_purchase_date, v_acc_id, v_asset_id, v_desc,
        p_purchase_value, p_mode, 'paid', p_created_by, NOW(), 'expenses', v_expense_id
    );

    RETURN QUERY SELECT v_asset_id, v_expense_id;
END;
$$;

DROP FUNCTION IF EXISTS fn_dispose_asset CASCADE;
CREATE OR REPLACE FUNCTION fn_dispose_asset(
    p_asset_id    INT,
    p_sale_value  NUMERIC,
    p_acc_id      INT     DEFAULT NULL,   -- Cr account for the sale income (e.g. 212)
    p_mode        VARCHAR DEFAULT 'cash',
    p_created_by  INT     DEFAULT NULL,
    p_sale_date   DATE    DEFAULT CURRENT_DATE,
    p_particulars TEXT    DEFAULT NULL
)
RETURNS TABLE(receipt_id INT)
LANGUAGE plpgsql AS $$
DECLARE
    v_asset      asset_register%ROWTYPE;
    v_acc_id     INT;
    v_receipt_id INT;
    v_desc       TEXT;
BEGIN
    SELECT * INTO v_asset FROM asset_register WHERE id = p_asset_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Asset not found'; END IF;
    IF v_asset.disposed THEN RAISE EXCEPTION 'Asset already disposed'; END IF;
    IF p_sale_value IS NULL OR p_sale_value <= 0 THEN
        RAISE EXCEPTION 'sale_value must be > 0';
    END IF;

    v_acc_id := COALESCE(p_acc_id, v_asset.sale_acc_id);
    IF v_acc_id IS NULL THEN
        SELECT id INTO v_acc_id FROM accounts
        WHERE society_id = v_asset.society_id AND name ILIKE '%Selling Asset%' AND drcr_account = 'Cr'
        LIMIT 1;
    END IF;

    v_desc := COALESCE(p_particulars, 'Asset Sale - ' || v_asset.asset_name);

    INSERT INTO receipts(
        society_id, user_id, entity_id, role, receipt_date, acc_id,
        particulars, amount, mode, status, confirmed_by, confirmed_at, created_at
    ) VALUES (
        v_asset.society_id, p_created_by, p_asset_id, 'other', p_sale_date, v_acc_id,
        v_desc, p_sale_value, p_mode, 'confirmed', p_created_by, NOW(), NOW()
    ) RETURNING id INTO v_receipt_id;

    INSERT INTO transactions(
        society_id, trx_date, acc_id, entity_id, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id
    ) VALUES (
        v_asset.society_id, p_sale_date, v_acc_id, p_asset_id, v_desc,
        p_sale_value, p_mode, 'paid', p_created_by, NOW(), 'receipts', v_receipt_id
    );

    UPDATE asset_register
    SET disposed    = TRUE,
        disposed_at = p_sale_date,
        sale_value  = p_sale_value,
        sale_acc_id = v_acc_id,
        disposed_by = p_created_by
    WHERE id = p_asset_id;

    RETURN QUERY SELECT v_receipt_id;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 8: MANUAL RECEIPT / EXPENSE SAVE HELPER
-- Called by the Python layer when admin creates a receipt or expense
-- manually (fines, donations, salary bonus, vendor service payments, etc.).
-- The acc_id selects the appropriate income/expense account from the chart.
-- The particulars string is supplied by the caller (from Python's
-- PARTICULARS_TEMPLATES hard-coded dict).
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_save_receipt CASCADE;
CREATE OR REPLACE FUNCTION fn_save_receipt(
    p_society_id   INT,
    p_acc_id       INT,
    p_particulars  TEXT,
    p_amount       NUMERIC,

    p_entity_id    INT DEFAULT NULL,
    p_role         VARCHAR DEFAULT 'other',
    p_mode         VARCHAR DEFAULT 'cash',
    p_receipt_date DATE DEFAULT CURRENT_DATE,
    p_created_by   INT DEFAULT NULL,
    p_cheque_no    VARCHAR DEFAULT NULL,
    p_trx_id       VARCHAR DEFAULT NULL
)
RETURNS TABLE(receipt_id INT, transaction_id INT)
LANGUAGE plpgsql AS $$
DECLARE
    v_receipt_id INT;
    v_trx_id     INT;
    v_drcr       VARCHAR(2);
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN RAISE EXCEPTION 'Amount must be > 0'; END IF;
    IF p_acc_id IS NULL THEN RAISE EXCEPTION 'acc_id is required'; END IF;
    IF p_particulars IS NULL OR TRIM(p_particulars) = '' THEN RAISE EXCEPTION 'particulars is required'; END IF;

    SELECT drcr_account INTO v_drcr FROM accounts WHERE id = p_acc_id AND society_id = p_society_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Account % not found for this society', p_acc_id; END IF;
    IF v_drcr = 'Dr' THEN
        RAISE EXCEPTION 'Account % is a Dr (expense) account — use fn_save_expense for expenses', p_acc_id;
    END IF;

    INSERT INTO receipts(
        society_id, user_id, entity_id, role, receipt_date, acc_id, particulars,
        amount, mode, cheque_no, transaction_id, status, confirmed_by, confirmed_at, created_at
    ) VALUES (
        p_society_id, p_created_by, p_entity_id, p_role, p_receipt_date, p_acc_id, p_particulars,
        p_amount, p_mode, p_cheque_no, p_trx_id, 'confirmed', p_created_by, NOW(), NOW()
    ) RETURNING id INTO v_receipt_id;

    INSERT INTO transactions(
        society_id, trx_date, acc_id, entity_id, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id
    ) VALUES (
        p_society_id, p_receipt_date, p_acc_id, p_entity_id, p_particulars,
        p_amount, p_mode, 'paid', p_created_by, NOW(), 'receipts', v_receipt_id
    ) RETURNING id INTO v_trx_id;

    RETURN QUERY SELECT v_receipt_id, v_trx_id;
END;
$$;

DROP FUNCTION IF EXISTS fn_save_expense CASCADE;
CREATE OR REPLACE FUNCTION fn_save_expense(
    p_society_id   INT,
    p_acc_id       INT,
    p_particulars  TEXT,
    p_amount       NUMERIC,

    p_entity_id    INT DEFAULT NULL,
    p_role         VARCHAR DEFAULT 'other',
    p_mode         VARCHAR DEFAULT 'cash',
    p_expense_date DATE DEFAULT CURRENT_DATE,
    p_created_by   INT DEFAULT NULL,
    p_cheque_no    VARCHAR DEFAULT NULL,
    p_trx_id       VARCHAR DEFAULT NULL
)
RETURNS TABLE(expense_id INT, transaction_id INT)
LANGUAGE plpgsql AS $$
DECLARE
    v_expense_id INT;
    v_trx_id     INT;
    v_drcr       VARCHAR(2);
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN RAISE EXCEPTION 'Amount must be > 0'; END IF;
    IF p_acc_id IS NULL THEN RAISE EXCEPTION 'acc_id is required'; END IF;
    IF p_particulars IS NULL OR TRIM(p_particulars) = '' THEN RAISE EXCEPTION 'particulars is required'; END IF;

    SELECT drcr_account INTO v_drcr FROM accounts WHERE id = p_acc_id AND society_id = p_society_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Account % not found for this society', p_acc_id; END IF;
    IF v_drcr = 'Cr' THEN
        RAISE EXCEPTION 'Account % is a Cr (income) account — use fn_save_receipt for receipts', p_acc_id;
    END IF;

    INSERT INTO expenses(
        society_id, user_id, entity_id, role, expense_date, acc_id, particulars,
        amount, mode, cheque_no, transaction_id, status, confirmed_by, confirmed_at, created_at
    ) VALUES (
        p_society_id, p_created_by, p_entity_id, p_role, p_expense_date, p_acc_id, p_particulars,
        p_amount, p_mode, p_cheque_no, p_trx_id, 'confirmed', p_created_by, NOW(), NOW()
    ) RETURNING id INTO v_expense_id;

    INSERT INTO transactions(
        society_id, trx_date, acc_id, entity_id, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id
    ) VALUES (
        p_society_id, p_expense_date, p_acc_id, p_entity_id, p_particulars,
        p_amount, p_mode, 'paid', p_created_by, NOW(), 'expenses', v_expense_id
    ) RETURNING id INTO v_trx_id;

    RETURN QUERY SELECT v_expense_id, v_trx_id;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 9: LIST FUNCTIONS (apartments, vendors, security)
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_apartments_list CASCADE;
CREATE OR REPLACE FUNCTION fn_apartments_list(
    p_society_id INT,
    p_search     TEXT    DEFAULT NULL,
    p_has_dues   BOOLEAN DEFAULT NULL
)
RETURNS TABLE (
    id INT, flat_number VARCHAR(20), owner_name VARCHAR(100), mobile VARCHAR(15),
    apartment_size INT, active BOOLEAN, society_id INT,
    pending_dues NUMERIC(15,2), overdue_dues NUMERIC(15,2),
    gate_pass BOOLEAN, noc_eligible BOOLEAN
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM fn_auto_generate_receivables(p_society_id);
    PERFORM fn_apply_receivable_interest(p_society_id);
    RETURN QUERY
    WITH dues AS (
        SELECT entity_id AS apt_id,
            COALESCE(SUM(amount - paid_amount) FILTER (WHERE status IN ('pending','partial')), 0)::NUMERIC(15,2) AS pending_dues,
            COALESCE(SUM(amount - paid_amount) FILTER (WHERE status IN ('pending','partial') AND due_date < CURRENT_DATE), 0)::NUMERIC(15,2) AS overdue_dues
        FROM receivables r WHERE r.society_id = p_society_id AND r.role = 'apartment'
        GROUP BY entity_id
    )
    SELECT a.id::INT, a.flat_number::VARCHAR(20), a.owner_name::VARCHAR(100), a.mobile::VARCHAR(15),
           a.apartment_size::INT, a.active::BOOLEAN, a.society_id::INT,
           COALESCE(d.pending_dues, 0)::NUMERIC(15,2), COALESCE(d.overdue_dues, 0)::NUMERIC(15,2),
           -- gate_pass fails only on OVERDUE dues (mirrors v_apartment_dues)
           (COALESCE(d.overdue_dues, 0) <= 0)::BOOLEAN,
           -- noc_eligible requires ALL dues cleared (mirrors v_apartment_dues)
           (COALESCE(d.pending_dues, 0) <= 0)::BOOLEAN
    FROM apartments a LEFT JOIN dues d ON d.apt_id = a.id
    WHERE a.society_id = p_society_id
      AND (p_search IS NULL OR a.flat_number ILIKE '%'||p_search||'%' OR a.owner_name ILIKE '%'||p_search||'%')
      AND (p_has_dues IS NULL
           OR (p_has_dues AND COALESCE(d.pending_dues,0) > 0)
           OR (NOT p_has_dues AND COALESCE(d.pending_dues,0) <= 0))
    ORDER BY a.flat_number;
END;
$$;
DROP FUNCTION IF EXISTS fn_vendors_list CASCADE;
CREATE OR REPLACE FUNCTION fn_vendors_list(p_society_id INT, p_search TEXT DEFAULT NULL)
RETURNS TABLE (
    id INT, email VARCHAR(100), society_id INT, name VARCHAR(100),
    service_type VARCHAR(100), mobile VARCHAR(15), active BOOLEAN,
    pass_expiry DATE, gate_pass BOOLEAN, active_passes INT
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        u.id::INT, u.email::VARCHAR(100), u.society_id::INT,
        COALESCE(v.name, u.email)::VARCHAR(100),
        COALESCE(v.service_type,'—')::VARCHAR(100),
        COALESCE(v.mobile,'—')::VARCHAR(15),
        COALESCE(v.active,TRUE)::BOOLEAN,
        (SELECT MAX(valid_until) FROM vendor_passes WHERE user_id=u.id AND status='active')::DATE,
        COALESCE((SELECT MAX(valid_until) FROM vendor_passes WHERE user_id=u.id AND status='active') >= CURRENT_DATE, FALSE),
        (SELECT COUNT(*)::INT FROM vendor_passes WHERE user_id=u.id AND status='active' AND valid_until >= CURRENT_DATE)
    FROM users u
    LEFT JOIN vendors v ON v.id = u.linked_id
    WHERE u.society_id = p_society_id AND u.role = 'vendor'
      AND (p_search IS NULL OR v.name ILIKE '%'||p_search||'%' OR u.email ILIKE '%'||p_search||'%')
    ORDER BY v.name;
END;
$$;

DROP FUNCTION IF EXISTS fn_security_list CASCADE;
CREATE OR REPLACE FUNCTION fn_security_list(p_society_id INT, p_search TEXT DEFAULT NULL)
RETURNS TABLE (
    id INT, email VARCHAR(100), society_id INT, name VARCHAR(100),
    shift VARCHAR(20), mobile VARCHAR(15), active BOOLEAN, salary_per_shift NUMERIC(10,2),
    joining_date DATE, shifts_completed BIGINT, salary_due NUMERIC(15,2), salary_paid NUMERIC(15,2), on_duty BOOLEAN
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM fn_auto_generate_payments(p_society_id);
    RETURN QUERY
    WITH pay_sum AS (
        SELECT entity_id AS staff_id,
            COUNT(*)::BIGINT AS shifts_completed,
            COALESCE(SUM(amount) FILTER (WHERE status='pending'), 0)::NUMERIC(15,2) AS salary_due,
            COALESCE(SUM(amount) FILTER (WHERE status='verified'), 0)::NUMERIC(15,2) AS salary_paid
        FROM payments p WHERE p.society_id = p_society_id AND p.role = 'security' GROUP BY entity_id
    )
    SELECT
        u.id::INT, u.email::VARCHAR(100), u.society_id::INT,
        COALESCE(s.name, u.email)::VARCHAR(100), COALESCE(s.shift,'—')::VARCHAR(20),
        COALESCE(s.mobile,'—')::VARCHAR(15), COALESCE(s.active,TRUE)::BOOLEAN,
        COALESCE(s.salary_per_shift,0)::NUMERIC(10,2), s.joining_date::DATE,
        COALESCE(ps.shifts_completed, 0)::BIGINT,
        COALESCE(ps.salary_due, 0)::NUMERIC(15,2), COALESCE(ps.salary_paid, 0)::NUMERIC(15,2),
        EXISTS(SELECT 1 FROM gate_access ga WHERE ga.entity_id=u.id AND ga.role='s' AND ga.time_out IS NULL)::BOOLEAN
    FROM users u
    LEFT JOIN security_staff s ON s.id = u.linked_id
    LEFT JOIN pay_sum ps ON ps.staff_id = s.id
    WHERE u.society_id = p_society_id AND u.role = 'security'
      AND (p_search IS NULL OR s.name ILIKE '%'||p_search||'%')
    ORDER BY s.name;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 10: NAMED RECEIVABLES / PAYMENTS (read-only tab listing)
-- Exposes acc_id + account name so the UI can show "Maintenance Income" etc.
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_receivables_named CASCADE;
CREATE OR REPLACE FUNCTION fn_receivables_named(
    p_society_id  INT, p_search TEXT DEFAULT NULL, p_status TEXT DEFAULT NULL,
    p_entity_id   INT DEFAULT NULL, p_entity_role TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT, society_id INT, entity_id INT, role VARCHAR(20), entity_name TEXT,
    acc_id INT, account_name TEXT, interest_acc_id INT, interest_account_name TEXT,
    description TEXT, period_month DATE,
    base_amount NUMERIC(10,2), interest_amount NUMERIC(10,2),
    amount NUMERIC(10,2), paid_amount NUMERIC(10,2), residual NUMERIC(10,2),
    due_date DATE, status VARCHAR(20), days_overdue INT,
    confirmed_by INT, confirmed_at TIMESTAMP, created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        r.id::INT, r.society_id::INT, r.entity_id::INT, r.role::VARCHAR(20),
        CASE WHEN r.role='apartment' THEN COALESCE(ap.flat_number||' — '||COALESCE(ap.owner_name,''),'')
             WHEN r.role='vendor'    THEN COALESCE(v.name,'')
             WHEN r.role='security'  THEN COALESCE(s.name,'')
             ELSE 'Entity #'||r.entity_id::TEXT END::TEXT,
        r.acc_id::INT,
        COALESCE(a.name,'—')::TEXT,
        r.interest_acc_id::INT,
        COALESCE(ia.name,'—')::TEXT,
        r.description::TEXT, r.period_month::DATE,
        r.base_amount::NUMERIC(10,2), r.interest_amount::NUMERIC(10,2),
        r.amount::NUMERIC(10,2), r.paid_amount::NUMERIC(10,2),
        (r.amount - r.paid_amount)::NUMERIC(10,2),
        r.due_date::DATE, r.status::VARCHAR(20),
        GREATEST(EXTRACT(DAY FROM AGE(CURRENT_DATE, r.due_date)),0)::INT,
        r.confirmed_by::INT, r.confirmed_at::TIMESTAMP, r.created_at::TIMESTAMP
    FROM receivables r
    LEFT JOIN accounts a    ON a.id  = r.acc_id
    LEFT JOIN accounts ia   ON ia.id = r.interest_acc_id
    LEFT JOIN apartments ap ON ap.id = r.entity_id AND r.role='apartment'
    LEFT JOIN vendors v     ON  v.id = r.entity_id AND r.role='vendor'
    LEFT JOIN security_staff s ON s.id = r.entity_id AND r.role='security'
    WHERE r.society_id = p_society_id
      AND (p_status      IS NULL OR r.status = p_status)
      AND (p_entity_id   IS NULL OR r.entity_id = p_entity_id)
      AND (p_entity_role IS NULL OR r.role = p_entity_role)
      AND (p_search IS NULL OR r.description ILIKE '%'||p_search||'%' OR a.name ILIKE '%'||p_search||'%')
    ORDER BY r.due_date ASC, r.created_at DESC;
END;
$$;

DROP FUNCTION IF EXISTS fn_payments_named CASCADE;
CREATE OR REPLACE FUNCTION fn_payments_named(
    p_society_id  INT, p_search TEXT DEFAULT NULL,
    p_status      TEXT DEFAULT NULL, p_entity_role TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT, society_id INT, entity_id INT, role VARCHAR(20), entity_name TEXT,
    acc_id INT, account_name TEXT,
    description TEXT, roster_id INT, shift_date DATE,
    amount NUMERIC(10,2), status VARCHAR(20), due_date DATE, days_overdue INT,
    paid_at TIMESTAMP, confirmed_by INT, confirmed_at TIMESTAMP, created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        p.id::INT, p.society_id::INT, p.entity_id::INT, p.role::VARCHAR(20),
        CASE WHEN p.role='security' THEN COALESCE(s.name,'') ELSE 'Entity #'||COALESCE(p.entity_id::TEXT,'—') END::TEXT,
        p.acc_id::INT,
        COALESCE(a.name,'—')::TEXT,
        p.description::TEXT, p.roster_id::INT, p.shift_date::DATE,
        p.amount::NUMERIC(10,2), p.status::VARCHAR(20), p.due_date::DATE,
        GREATEST(EXTRACT(DAY FROM AGE(CURRENT_DATE, p.due_date)),0)::INT,
        p.paid_at::TIMESTAMP, p.confirmed_by::INT, p.confirmed_at::TIMESTAMP, p.created_at::TIMESTAMP
    FROM payments p
    LEFT JOIN accounts a       ON a.id = p.acc_id
    LEFT JOIN security_staff s ON s.id = p.entity_id AND p.role='security'
    WHERE p.society_id = p_society_id
      AND (p_status      IS NULL OR p.status = p_status)
      AND (p_entity_role IS NULL OR p.role = p_entity_role)
      AND (p_search IS NULL OR p.description ILIKE '%'||p_search||'%' OR a.name ILIKE '%'||p_search||'%')
    ORDER BY p.due_date ASC, p.created_at DESC;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 11: RECEIPTS / EXPENSES LIST FUNCTIONS
-- account_name is derived from acc_id — no category field needed.
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_receipts_list CASCADE;
CREATE OR REPLACE FUNCTION fn_receipts_list(
    p_society_id  INT,
    p_search      TEXT DEFAULT NULL,
    p_entity_id   INT  DEFAULT NULL,
    p_entity_role TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT, society_id INT, entity_id INT, role VARCHAR(20), entity_name TEXT,
    receipt_date DATE, acc_id INT, account_name TEXT,
    particulars TEXT, amount NUMERIC(10,2), mode VARCHAR(20),
    cheque_no VARCHAR(50), transaction_id VARCHAR(255), status VARCHAR(20),
    confirmed_by INT, confirmed_at TIMESTAMP,
    last_printed_at TIMESTAMP, last_emailed_at TIMESTAMP, created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        r.id::INT, r.society_id::INT, r.entity_id::INT, r.role::VARCHAR(20),
        CASE
            WHEN r.role = 'apartment' THEN COALESCE(ap.flat_number||' — '||COALESCE(ap.owner_name,''), '')
            WHEN r.role = 'vendor'    THEN COALESCE(v.name||COALESCE(' ('||v.service_type||')',''), '')
            WHEN r.role = 'security'  THEN COALESCE(s.name, '')
            ELSE COALESCE('Other #'||r.entity_id::TEXT, '')
        END::TEXT,
        r.receipt_date::DATE,
        r.acc_id::INT,
        COALESCE(a.name, '—')::TEXT,
        r.particulars::TEXT,
        r.amount::NUMERIC(10,2), r.mode::VARCHAR(20),
        COALESCE(r.cheque_no,'')::VARCHAR(50),
        COALESCE(r.transaction_id,'')::VARCHAR(255),
        r.status::VARCHAR(20),
        r.confirmed_by::INT, r.confirmed_at::TIMESTAMP,
        r.last_printed_at::TIMESTAMP, r.last_emailed_at::TIMESTAMP,
        r.created_at::TIMESTAMP
    FROM receipts r
    LEFT JOIN accounts      a  ON a.id  = r.acc_id
    LEFT JOIN apartments   ap  ON ap.id = r.entity_id AND r.role = 'apartment'
    LEFT JOIN vendors       v  ON  v.id = r.entity_id AND r.role = 'vendor'
    LEFT JOIN security_staff s ON  s.id = r.entity_id AND r.role = 'security'
    WHERE r.society_id = p_society_id
      AND (p_entity_id   IS NULL OR r.entity_id = p_entity_id)
      AND (p_entity_role IS NULL OR r.role = p_entity_role)
      AND (p_search IS NULL
           OR r.particulars ILIKE '%'||p_search||'%'
           OR a.name        ILIKE '%'||p_search||'%')
    ORDER BY r.receipt_date DESC, r.id DESC;
END;
$$;

DROP FUNCTION IF EXISTS fn_expenses_list CASCADE;
CREATE OR REPLACE FUNCTION fn_expenses_list(
    p_society_id  INT,
    p_search      TEXT DEFAULT NULL,
    p_entity_id   INT  DEFAULT NULL,
    p_entity_role TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT, society_id INT, entity_id INT, role VARCHAR(20), entity_name TEXT,
    expense_date DATE, acc_id INT, account_name TEXT,
    particulars TEXT, amount NUMERIC(10,2), mode VARCHAR(20),
    cheque_no VARCHAR(50), transaction_id VARCHAR(255), status VARCHAR(20),
    confirmed_by INT, confirmed_at TIMESTAMP,
    last_printed_at TIMESTAMP, last_emailed_at TIMESTAMP, created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        e.id::INT, e.society_id::INT, e.entity_id::INT, e.role::VARCHAR(20),
        CASE
            WHEN e.role = 'vendor'   THEN COALESCE(v.name||COALESCE(' ('||v.service_type||')',''), '')
            WHEN e.role = 'security' THEN COALESCE(s.name||COALESCE(' ('||s.shift||')',''), '')
            WHEN e.role = 'assets'   THEN COALESCE(
                (SELECT asset_name FROM asset_register WHERE asset_register.id = e.entity_id),
                'Asset #'||e.entity_id::TEXT)
            ELSE 'Other'
        END::TEXT,
        e.expense_date::DATE,
        e.acc_id::INT,
        COALESCE(a.name, '—')::TEXT,
        e.particulars::TEXT,
        e.amount::NUMERIC(10,2), e.mode::VARCHAR(20),
        COALESCE(e.cheque_no,'')::VARCHAR(50),
        COALESCE(e.transaction_id,'')::VARCHAR(255),
        e.status::VARCHAR(20),
        e.confirmed_by::INT, e.confirmed_at::TIMESTAMP,
        e.last_printed_at::TIMESTAMP, e.last_emailed_at::TIMESTAMP,
        e.created_at::TIMESTAMP
    FROM expenses e
    LEFT JOIN accounts       a ON a.id = e.acc_id
    LEFT JOIN vendors        v ON v.id = e.entity_id AND e.role = 'vendor'
    LEFT JOIN security_staff s ON s.id = e.entity_id AND e.role = 'security'
    WHERE e.society_id = p_society_id
      AND (p_entity_id   IS NULL OR e.entity_id = p_entity_id)
      AND (p_entity_role IS NULL OR e.role = p_entity_role)
      AND (p_search IS NULL
           OR e.particulars ILIKE '%'||p_search||'%'
           OR a.name        ILIKE '%'||p_search||'%')
    ORDER BY e.expense_date DESC, e.id DESC;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 12: CASHBOOK (paired Cr/Dr over transactions table)
-- Unchanged logic; transactions.acc_particulars already carries the
-- description text set by the engine functions above.
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_cashbook_paired CASCADE;
CREATE OR REPLACE FUNCTION fn_cashbook_paired(
    p_society_id INT,
    p_entity_id  INT  DEFAULT NULL,
    p_entity_role TEXT DEFAULT NULL,
    p_search     TEXT DEFAULT NULL,
    p_start_date DATE DEFAULT NULL,
    p_end_date   DATE DEFAULT NULL
)
RETURNS TABLE (
    row_date         DATE,
    rc_id            INT,    rc_trx_date DATE,
    rc_account_name  TEXT,   rc_entity_name TEXT,
    rc_particulars   TEXT,   rc_mode TEXT,   rc_amount NUMERIC(15,2),
    pc_id            INT,    pc_trx_date DATE,
    pc_account_name  TEXT,   pc_entity_name TEXT,
    pc_particulars   TEXT,   pc_mode TEXT,   pc_amount NUMERIC(15,2),
    day_rc_total     NUMERIC(15,2),
    day_pc_total     NUMERIC(15,2),
    running_balance  NUMERIC(15,2)
)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_opening_balance NUMERIC(15,2);
BEGIN
    SELECT COALESCE(SUM(CASE WHEN drcr_bf='Cr' THEN bf_amount ELSE -bf_amount END),0)
    INTO v_opening_balance FROM accounts WHERE society_id = p_society_id;

    RETURN QUERY
    WITH
    cr_rows AS (
        SELECT t.id::INT AS rc_id, t.trx_date::DATE AS rc_date,
               a.name::TEXT AS rc_account_name,
               COALESCE(ap.flat_number||COALESCE(' ('||ap.owner_name||')',''), v.name, s.name, '')::TEXT AS rc_entity_name,
               COALESCE(t.acc_particulars,'')::TEXT AS rc_particulars,
               COALESCE(t.mode,'')::TEXT AS rc_mode,
               t.amount::NUMERIC(15,2) AS rc_amount,
               ROW_NUMBER() OVER (PARTITION BY t.trx_date ORDER BY t.id) AS rn
        FROM transactions t
        JOIN accounts a ON a.id = t.acc_id AND a.drcr_account = 'Cr'
        LEFT JOIN apartments   ap ON ap.id = t.entity_id AND ap.society_id = p_society_id
        LEFT JOIN vendors       v ON  v.id = t.entity_id AND  v.society_id = p_society_id
        LEFT JOIN security_staff s ON s.id = t.entity_id AND  s.society_id = p_society_id
        WHERE t.society_id = p_society_id AND t.status = 'paid'
          AND (p_start_date  IS NULL OR t.trx_date >= p_start_date)
          AND (p_end_date    IS NULL OR t.trx_date <= p_end_date)
          AND (p_entity_id   IS NULL OR t.entity_id = p_entity_id)
          AND (p_search IS NULL
               OR a.name ILIKE '%'||p_search||'%'
               OR t.acc_particulars ILIKE '%'||p_search||'%')
    ),
    dr_rows AS (
        SELECT t.id::INT AS pc_id, t.trx_date::DATE AS pc_date,
               a.name::TEXT AS pc_account_name,
               COALESCE(v.name, s.name, ap.flat_number, '')::TEXT AS pc_entity_name,
               COALESCE(t.acc_particulars,'')::TEXT AS pc_particulars,
               COALESCE(t.mode,'')::TEXT AS pc_mode,
               t.amount::NUMERIC(15,2) AS pc_amount,
               ROW_NUMBER() OVER (PARTITION BY t.trx_date ORDER BY t.id) AS rn
        FROM transactions t
        JOIN accounts a ON a.id = t.acc_id AND a.drcr_account = 'Dr'
        LEFT JOIN vendors       v ON  v.id = t.entity_id AND  v.society_id = p_society_id
        LEFT JOIN security_staff s ON s.id = t.entity_id AND  s.society_id = p_society_id
        LEFT JOIN apartments   ap ON ap.id = t.entity_id AND ap.society_id = p_society_id
        WHERE t.society_id = p_society_id AND t.status = 'paid'
          AND (p_start_date  IS NULL OR t.trx_date >= p_start_date)
          AND (p_end_date    IS NULL OR t.trx_date <= p_end_date)
          AND (p_entity_id   IS NULL OR t.entity_id = p_entity_id)
          AND (p_search IS NULL
               OR a.name ILIKE '%'||p_search||'%'
               OR t.acc_particulars ILIKE '%'||p_search||'%')
    ),
    date_totals AS (
        SELECT d::DATE AS dt,
            COALESCE(SUM(cr.rc_amount),0)::NUMERIC(15,2) AS day_rc_total,
            COALESCE(SUM(dr.pc_amount),0)::NUMERIC(15,2) AS day_pc_total
        FROM (SELECT DISTINCT rc_date AS d FROM cr_rows
              UNION SELECT DISTINCT pc_date FROM dr_rows) dates
        LEFT JOIN cr_rows cr ON cr.rc_date = d::DATE
        LEFT JOIN dr_rows dr ON dr.pc_date = d::DATE
        GROUP BY d
    ),
    all_dates AS (
        SELECT
            dts.dt,
            dts.day_rc_total,
            dts.day_pc_total,
            SUM(dts.day_rc_total - dts.day_pc_total)
                OVER (
                    ORDER BY dts.dt
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                )
                + v_opening_balance AS running_balance
        FROM date_totals dts
    ),
    max_rn AS (
        SELECT COALESCE(cr.rc_date, dr.pc_date) AS dt,
               GREATEST(MAX(cr.rn), MAX(dr.rn)) AS max_rows
        FROM cr_rows cr
        FULL OUTER JOIN dr_rows dr ON dr.pc_date = cr.rc_date AND dr.rn = cr.rn
        GROUP BY COALESCE(cr.rc_date, dr.pc_date)
    ),
    row_slots AS (
        SELECT m.dt, gs.rn
        FROM max_rn m CROSS JOIN LATERAL generate_series(1, m.max_rows) AS gs(rn)
    )
    SELECT
        rs.dt::DATE,
        cr.rc_id::INT, cr.rc_date::DATE,
        COALESCE(cr.rc_account_name,'')::TEXT, COALESCE(cr.rc_entity_name,'')::TEXT,
        COALESCE(cr.rc_particulars,'')::TEXT,  COALESCE(cr.rc_mode,'')::TEXT,
        COALESCE(cr.rc_amount, 0)::NUMERIC(15,2),
        dr.pc_id::INT, dr.pc_date::DATE,
        COALESCE(dr.pc_account_name,'')::TEXT, COALESCE(dr.pc_entity_name,'')::TEXT,
        COALESCE(dr.pc_particulars,'')::TEXT,  COALESCE(dr.pc_mode,'')::TEXT,
        COALESCE(dr.pc_amount, 0)::NUMERIC(15,2),
        ad.day_rc_total::NUMERIC(15,2),
        ad.day_pc_total::NUMERIC(15,2),
        ad.running_balance::NUMERIC(15,2)
    FROM row_slots rs
    JOIN all_dates ad ON ad.dt = rs.dt
    LEFT JOIN cr_rows cr ON cr.rc_date = rs.dt AND cr.rn = rs.rn
    LEFT JOIN dr_rows dr ON dr.pc_date = rs.dt AND dr.rn = rs.rn
    ORDER BY rs.dt, rs.rn;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 13: GATE LOGS  (unchanged)
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_gate_logs_named CASCADE;
CREATE OR REPLACE FUNCTION fn_gate_logs_named(
    p_society_id INT,
    p_search     TEXT DEFAULT NULL,
    p_date       DATE DEFAULT NULL
)
RETURNS TABLE (
    id INT, society_id INT, role VARCHAR(1), entity_id INT,
    entity_name TEXT, time_in TIMESTAMP, time_out TIMESTAMP, duration_min INT
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        g.id::INT, g.society_id::INT, g.role::VARCHAR(1), g.entity_id::INT,
        CASE
            WHEN g.role = 'a' THEN COALESCE(ap.flat_number||' — '||COALESCE(ap.owner_name,''), 'Apt #'||g.entity_id::TEXT)
            WHEN g.role = 'v' THEN COALESCE(v.name||COALESCE(' ('||v.service_type||')',''), 'Vendor #'||g.entity_id::TEXT)
            WHEN g.role = 's' THEN COALESCE(s.name||COALESCE(' ('||s.shift||')',''), 'Security #'||g.entity_id::TEXT)
            ELSE 'Unknown #'||g.entity_id::TEXT
        END::TEXT,
        g.time_in::TIMESTAMP, g.time_out::TIMESTAMP,
        CASE WHEN g.time_out IS NOT NULL
             THEN EXTRACT(EPOCH FROM (g.time_out - g.time_in))::INT / 60
             ELSE NULL END::INT
    FROM gate_access g
    LEFT JOIN apartments   ap ON ap.id = g.entity_id AND g.role = 'a'
    LEFT JOIN vendors       v ON  v.id = g.entity_id AND g.role = 'v'
    LEFT JOIN security_staff s ON s.id = g.entity_id AND g.role = 's'
    WHERE g.society_id = p_society_id
      AND (p_date   IS NULL OR g.time_in::DATE = p_date)
      AND (p_search IS NULL OR CASE
           WHEN g.role='a' THEN ap.flat_number||' '||COALESCE(ap.owner_name,'')
           WHEN g.role='v' THEN v.name
           WHEN g.role='s' THEN s.name
           ELSE '' END ILIKE '%'||p_search||'%')
    ORDER BY g.time_in DESC;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 14: ACCOUNTS LIST / PROFILE
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_accounts_list CASCADE;
CREATE OR REPLACE FUNCTION fn_accounts_list(
    p_society_id INT,
    p_search     TEXT    DEFAULT NULL,
    p_tab_name   VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id INT, name VARCHAR(100), tab_name VARCHAR(20), header VARCHAR(50),
    drcr_account VARCHAR(2), bf_amount NUMERIC(12,2),
    current_balance NUMERIC(15,2), transaction_count INT,
    parent_account_name VARCHAR(100)
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        a.id::INT, a.name::VARCHAR(100), a.tab_name::VARCHAR(20), a.header::VARCHAR(50),
        a.drcr_account::VARCHAR(2), a.bf_amount::NUMERIC(12,2),
        (COALESCE(SUM(
            CASE WHEN a.drcr_account = 'Cr' THEN t.amount ELSE -t.amount END
        ), 0) + a.bf_amount)::NUMERIC(15,2),
        COUNT(t.id)::INT,
        COALESCE(p.name,'—')::VARCHAR(100)
    FROM accounts a
    LEFT JOIN accounts p ON p.id = a.parent_account_id
    LEFT JOIN transactions t ON t.acc_id = a.id AND t.status = 'paid'
    WHERE a.society_id = p_society_id
      AND (p_tab_name IS NULL OR a.tab_name = p_tab_name)
      AND (p_search   IS NULL OR a.name ILIKE '%'||p_search||'%')
    GROUP BY a.id, a.name, a.tab_name, a.header, a.drcr_account, a.bf_amount, p.name
    ORDER BY a.tab_name NULLS LAST, a.id;
END;
$$;

DROP FUNCTION IF EXISTS fn_account_profile CASCADE;
CREATE OR REPLACE FUNCTION fn_account_profile(p_account_id INT)
RETURNS TABLE (
    id INT, society_id INT, name VARCHAR(100), tab_name VARCHAR(20), header VARCHAR(50),
    drcr_account VARCHAR(2), bf_amount NUMERIC(12,2), depreciation_percent NUMERIC(5,2),
    is_depreciable BOOLEAN, parent_account_name VARCHAR(100),
    current_balance NUMERIC(15,2), created_at TIMESTAMP
)
LANGUAGE SQL STABLE AS $$
    SELECT
        a.id::INT, a.society_id::INT, a.name::VARCHAR(100), a.tab_name::VARCHAR(20), a.header::VARCHAR(50),
        a.drcr_account::VARCHAR(2), a.bf_amount::NUMERIC(12,2),
        a.depreciation_percent::NUMERIC(5,2), a.is_depreciable::BOOLEAN,
        COALESCE(p.name,'—')::VARCHAR(100),
        (COALESCE(SUM(CASE WHEN a.drcr_account='Cr' THEN t.amount ELSE -t.amount END),0)
         + a.bf_amount)::NUMERIC(15,2),
        a.created_at::TIMESTAMP
    FROM accounts a
    LEFT JOIN accounts p ON p.id = a.parent_account_id
    LEFT JOIN transactions t ON t.acc_id = a.id AND t.status = 'paid'
    WHERE a.id = p_account_id
    GROUP BY a.id, a.society_id, a.name, a.tab_name, a.header, a.drcr_account,
             a.bf_amount, a.depreciation_percent, a.is_depreciable, p.name, a.created_at;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 15: SOCIETIES LIST / PROFILE  (unchanged logic)
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_societies_list CASCADE;
CREATE OR REPLACE FUNCTION fn_societies_list(
    p_search TEXT    DEFAULT NULL,
    p_plan   VARCHAR DEFAULT NULL,
    p_status VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id INT, name VARCHAR(100), email VARCHAR(100), phone VARCHAR(20),
    plan VARCHAR(20), plan_status VARCHAR(10), plan_validity DATE,
    total_apartments INT, total_users INT, total_receivables NUMERIC(15,2),
    created_at TIMESTAMP, secretary_phone VARCHAR(20)
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.id::INT, s.name::VARCHAR(100), s.email::VARCHAR(100), s.phone::VARCHAR(20),
        s.plan::VARCHAR(20),
        CASE WHEN s.plan='Free' THEN 'Free'
             WHEN s.plan_validity >= CURRENT_DATE THEN 'Active'
             ELSE 'Expired' END::VARCHAR(10),
        s.plan_validity::DATE,
        (SELECT COUNT(*)::INT FROM apartments WHERE society_id=s.id AND active=TRUE),
        (SELECT COUNT(*)::INT FROM users        WHERE society_id=s.id),
        (SELECT COALESCE(SUM(amount-paid_amount),0)::NUMERIC(15,2)
         FROM receivables WHERE society_id=s.id AND status IN ('pending','partial')),
        s.created_at::TIMESTAMP, s.secretary_phone::VARCHAR(20)
    FROM societies s
    WHERE (p_search IS NULL OR s.name ILIKE '%'||p_search||'%')
      AND (p_plan   IS NULL OR s.plan = p_plan)
    ORDER BY s.name;
END;
$$;

DROP FUNCTION IF EXISTS fn_society_profile CASCADE;
CREATE OR REPLACE FUNCTION fn_society_profile(p_society_id INT)
RETURNS TABLE (
    id INT, name VARCHAR(100), logo VARCHAR(100), login_background VARCHAR(100),
    email VARCHAR(100), phone VARCHAR(20), address TEXT, plan VARCHAR(20),
    plan_status VARCHAR(10), plan_validity DATE, calc_start_date DATE,
    secretary_name VARCHAR(100), secretary_phone VARCHAR(20), secretary_sign VARCHAR(100),
    total_apartments INT, total_vendors INT, total_security INT, total_users INT,
    total_receivables NUMERIC(15,2), created_at TIMESTAMP, _image_society_id INT
)
LANGUAGE SQL STABLE AS $$
    SELECT
        s.id::INT, s.name::VARCHAR(100), s.logo::VARCHAR(100), s.login_background::VARCHAR(100),
        s.email::VARCHAR(100), s.phone::VARCHAR(20), s.address::TEXT, s.plan::VARCHAR(20),
        CASE WHEN s.plan='Free' THEN 'Free'
             WHEN s.plan_validity >= CURRENT_DATE THEN 'Active'
             ELSE 'Expired' END::VARCHAR(10),
        s.plan_validity::DATE, s.calc_start_date::DATE,
        s.secretary_name::VARCHAR(100), s.secretary_phone::VARCHAR(20), s.secretary_sign::VARCHAR(100),
        (SELECT COUNT(*)::INT FROM apartments    WHERE society_id=s.id),
        (SELECT COUNT(*)::INT FROM vendors       WHERE society_id=s.id),
        (SELECT COUNT(*)::INT FROM security_staff WHERE society_id=s.id),
        (SELECT COUNT(*)::INT FROM users         WHERE society_id=s.id),
        (SELECT COALESCE(SUM(amount-paid_amount),0)::NUMERIC(15,2)
         FROM receivables WHERE society_id=s.id AND status IN ('pending','partial')),
        s.created_at::TIMESTAMP, s.id::INT
    FROM societies s WHERE s.id = p_society_id;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 16: EVENTS / CONCERNS  (unchanged)
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_events_list CASCADE;
CREATE OR REPLACE FUNCTION fn_events_list(
    p_society_id INT, p_search TEXT DEFAULT NULL, p_status VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id INT, title VARCHAR(200), description TEXT, event_date DATE, event_time VARCHAR(20),
    venue VARCHAR(200), open_to VARCHAR(20), parent_account_id INT, created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        e.id::INT, e.title::VARCHAR(200), e.description::TEXT, e.event_date::DATE,
        e.event_time::VARCHAR(20), e.venue::VARCHAR(200), e.open_to::VARCHAR(20),
        e.parent_account_id::INT, e.created_at::TIMESTAMP
    FROM events e
    WHERE e.society_id = p_society_id
      AND (p_search IS NULL OR e.title ILIKE '%'||p_search||'%')
      AND e.event_date >= CURRENT_DATE
    ORDER BY e.event_date ASC;
END;
$$;

DROP FUNCTION IF EXISTS fn_event_profile CASCADE;
CREATE OR REPLACE FUNCTION fn_event_profile(p_event_id INT)
RETURNS TABLE (
    id INT, society_id INT, title VARCHAR(200), description TEXT, event_date DATE,
    event_time VARCHAR(20), venue VARCHAR(200), open_to VARCHAR(20),
    parent_account_id INT, created_at TIMESTAMP, image TEXT, subtitle TEXT
)
LANGUAGE SQL STABLE AS $$
    SELECT id::INT, society_id::INT, title::VARCHAR(200), description::TEXT,
           event_date::DATE, event_time::VARCHAR(20), venue::VARCHAR(200),
           open_to::VARCHAR(20), parent_account_id::INT, created_at::TIMESTAMP, image::TEXT,
           (event_date::TEXT||' '||COALESCE(event_time::TEXT,''))::TEXT
    FROM events WHERE id = p_event_id;
$$;

DROP FUNCTION IF EXISTS fn_concern_profile CASCADE;
CREATE OR REPLACE FUNCTION fn_concern_profile(p_concern_id INT)
RETURNS TABLE (
    id INT, society_id INT, flat_no VARCHAR(20), concern_type VARCHAR(50),
    description TEXT, status VARCHAR(20), assigned_to VARCHAR(100),
    preferred_time VARCHAR(20), days_open BIGINT, created_at TIMESTAMP, image TEXT, subtitle TEXT
)
LANGUAGE SQL STABLE AS $$
    SELECT id::INT, society_id::INT, flat_no::VARCHAR(20), concern_type::VARCHAR(50),
           description::TEXT, status::VARCHAR(20), assigned_to::VARCHAR(100),
           preferred_time::VARCHAR(20),
           EXTRACT(DAY FROM AGE(CURRENT_DATE, created_at))::BIGINT,
           created_at::TIMESTAMP, image::TEXT,
           ('Flat '||flat_no||' - '||concern_type)::TEXT
    FROM concerns WHERE id = p_concern_id;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 17: ASSET REGISTER LIST / PROFILE
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_asset_list CASCADE;
CREATE OR REPLACE FUNCTION fn_asset_list(
    p_society_id INT,
    p_search     TEXT    DEFAULT NULL,
    p_disposed   BOOLEAN DEFAULT FALSE
)
RETURNS TABLE (
    id INT, asset_name VARCHAR(100), asset_type VARCHAR(50),
    purchase_date DATE, purchase_value NUMERIC(12,2),
    parent_account_name VARCHAR(100), depreciation_rate NUMERIC(5,2),
    book_value NUMERIC(15,2), disposed BOOLEAN,
    disposed_at DATE, sale_value NUMERIC(12,2), created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        ar.id::INT,
        ar.asset_name::VARCHAR(100),
        ar.asset_type::VARCHAR(50),
        ar.purchase_date::DATE,
        ar.purchase_value::NUMERIC(12,2),
        COALESCE(a.name,'—')::VARCHAR(100),
        COALESCE(ar.depreciation_rate, a.depreciation_percent, 100)::NUMERIC(5,2),
        -- Approximate straight-line book value; proper per-annum calculation
        -- happens in Python / a future fn_calculate_asset_depreciation call.
        GREATEST(
            ar.purchase_value * (1 - COALESCE(ar.depreciation_rate, a.depreciation_percent, 100) / 100),
            0
        )::NUMERIC(15,2),
        ar.disposed::BOOLEAN,
        ar.disposed_at::DATE,
        ar.sale_value::NUMERIC(12,2),
        ar.created_at::TIMESTAMP
    FROM asset_register ar
    LEFT JOIN accounts a ON a.id = ar.parent_account_id
    WHERE ar.society_id = p_society_id
      AND ar.disposed = COALESCE(p_disposed, FALSE)
      AND (p_search IS NULL OR ar.asset_name ILIKE '%'||p_search||'%')
    ORDER BY ar.purchase_date DESC;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 18: VIEWS  (apartment dues, vendor pass status, security duty)
-- Used by load_profile() in loaders.py.
-- ════════════════════════════════════════════════════════════════

CREATE OR REPLACE VIEW v_apartment_dues AS
SELECT
    a.id          AS apartment_id,
    a.society_id,
    COALESCE(SUM(r.amount - r.paid_amount) FILTER (WHERE r.status IN ('pending','partial')), 0)
        AS pending_dues,
    COALESCE(SUM(r.amount - r.paid_amount) FILTER (WHERE r.status IN ('pending','partial') AND r.due_date < CURRENT_DATE), 0)
        AS overdue_dues,
    -- gate_pass fails only on OVERDUE dues
    COALESCE(SUM(r.amount - r.paid_amount) FILTER (WHERE r.status IN ('pending','partial') AND r.due_date < CURRENT_DATE), 0) <= 0
        AS gate_pass,
    -- noc_eligible requires ALL dues cleared
    COALESCE(SUM(r.amount - r.paid_amount) FILTER (WHERE r.status IN ('pending','partial')), 0) <= 0
        AS noc_eligible
FROM apartments a
LEFT JOIN receivables r ON r.entity_id = a.id AND r.role = 'apartment'
GROUP BY a.id, a.society_id;

CREATE OR REPLACE VIEW v_vendor_pass_status AS
SELECT
    u.id          AS user_id,
    u.society_id,
    v.id          AS vendor_id,
    MAX(vp.valid_until)                           AS pass_expiry,
    COALESCE(MAX(vp.valid_until) >= CURRENT_DATE, FALSE) AS gate_pass
FROM users u
LEFT JOIN vendors v ON v.id = u.linked_id
LEFT JOIN vendor_passes vp ON vp.user_id = u.id AND vp.status = 'active'
WHERE u.role = 'vendor'
GROUP BY u.id, u.society_id, v.id;

CREATE OR REPLACE VIEW v_security_status AS
SELECT
    u.id          AS user_id,
    u.society_id,
    s.id          AS security_id,
    COUNT(att.id) FILTER (WHERE att.time_out IS NOT NULL)  AS shift_count,
    EXISTS(
        SELECT 1 FROM gate_access ga
        WHERE ga.entity_id = u.id AND ga.role = 's' AND ga.time_out IS NULL
    ) AS gate_pass
FROM users u
JOIN security_staff s ON s.id = u.linked_id
LEFT JOIN attendance att ON att.security_id = s.id
WHERE u.role = 'security'
GROUP BY u.id, u.society_id, s.id;

-- ════════════════════════════════════════════════════════════════
-- SECTION 19: APT CHARGES LIST / VEN CHARGES LIST
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_apt_charges_list CASCADE;
CREATE OR REPLACE FUNCTION fn_apt_charges_list(
    p_society_id INT,
    p_apt_id     INT DEFAULT NULL
)
RETURNS TABLE (
    id INT, society_id INT, apt_id INT, flat_number VARCHAR(20),
    start_date DATE, end_date DATE, apt_maintenance_rate NUMERIC(10,4),
    apt_due_day INT, apt_interest_pct NUMERIC(5,2),
    maintenance_account_name TEXT, interest_account_name TEXT,
    apt_status BOOLEAN, created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        acf.id::INT, acf.society_id::INT, acf.apt_id::INT,
        COALESCE(a.flat_number,'ALL')::VARCHAR(20),
        acf.start_date::DATE, acf.end_date::DATE,
        acf.apt_maintenance_rate::NUMERIC(10,4),
        acf.apt_due_day::INT, acf.apt_interest_pct::NUMERIC(5,2),
        COALESCE(
            (SELECT name FROM accounts
             WHERE society_id = acf.society_id
               AND name ILIKE '%Society Maintenance Charge%'
             LIMIT 1),
            '—'
        )::TEXT,
        COALESCE(
            (SELECT name FROM accounts
             WHERE society_id = acf.society_id
               AND name ILIKE '%Due Interest%'
             LIMIT 1),
            '—'
        )::TEXT,
        acf.apt_status::BOOLEAN, acf.created_at::TIMESTAMP
    FROM apt_charges_fines_basis acf
    LEFT JOIN apartments a ON a.id = acf.apt_id
    WHERE acf.society_id = p_society_id
      AND (p_apt_id IS NULL OR acf.apt_id = p_apt_id OR acf.apt_id IS NULL)
    ORDER BY acf.apt_id NULLS FIRST, acf.start_date DESC;
END;
$$;
DROP FUNCTION IF EXISTS fn_ven_charges_list CASCADE;
CREATE OR REPLACE FUNCTION fn_ven_charges_list(
    p_society_id INT,
    p_ven_id     INT DEFAULT NULL
)
RETURNS TABLE (
    id INT, society_id INT, ven_id INT, vendor_name VARCHAR(100),
    start_date DATE, end_date DATE,
    vendor_1day NUMERIC(10,2), vendor_7day NUMERIC(10,2), vendor_1mth NUMERIC(10,2),
    pass_account_name TEXT, ven_status BOOLEAN, created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        vcf.id::INT, vcf.society_id::INT, vcf.ven_id::INT,
        COALESCE(v.name,'ALL')::VARCHAR(100),
        vcf.start_date::DATE, vcf.end_date::DATE,
        vcf.vendor_1day::NUMERIC(10,2), vcf.vendor_7day::NUMERIC(10,2), vcf.vendor_1mth::NUMERIC(10,2),
        COALESCE(
            (SELECT name FROM accounts
             WHERE society_id = vcf.society_id
               AND name ILIKE '%Society Charge%'
             LIMIT 1),
            '—'
        )::TEXT,
        vcf.ven_status::BOOLEAN, vcf.created_at::TIMESTAMP
    FROM ven_charges_fines_basis vcf
    LEFT JOIN vendors v ON v.id = vcf.ven_id
    WHERE vcf.society_id = p_society_id
      AND (p_ven_id IS NULL OR vcf.ven_id = p_ven_id OR vcf.ven_id IS NULL)
    ORDER BY vcf.ven_id NULLS FIRST, vcf.start_date DESC;
END;
$$;
-- ════════════════════════════════════════════════════════════════
-- SECTION 20: UTILITY FUNCTIONS
-- ════════════════════════════════════════════════════════════════

-- Introspect a stored function's definition (used by KPI Inspector tab)
CREATE OR REPLACE FUNCTION get_function_sql(p_function_name TEXT)
RETURNS TEXT AS $$
DECLARE v_sql TEXT;
BEGIN
    SELECT pg_get_functiondef(p.oid) INTO v_sql
    FROM pg_proc p WHERE p.proname = p_function_name LIMIT 1;
    RETURN COALESCE(v_sql, 'Function not found: '||p_function_name);
END;
$$ LANGUAGE plpgsql;

-- List all fn_* functions (used by KPI Inspector)
CREATE OR REPLACE FUNCTION get_kpi_functions()
RETURNS TABLE(function_name TEXT, function_schema TEXT, parameters TEXT, source_code TEXT) AS $$
BEGIN
    RETURN QUERY
    SELECT p.proname::TEXT, n.nspname::TEXT,
           pg_get_function_arguments(p.oid)::TEXT,
           pg_get_functiondef(p.oid)::TEXT
    FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid
    WHERE p.proname LIKE 'fn_%' AND n.nspname = 'public'
    ORDER BY p.proname;
END;
$$ LANGUAGE plpgsql;

-- Create default charge rules for a new society after accounts are seeded.
-- Resolves account names to IDs at call time so it's robust against
-- different insertion orders.
CREATE OR REPLACE FUNCTION fn_create_default_charges(p_society_id INT)
RETURNS VOID AS $$
DECLARE
    v_calc_date DATE;
BEGIN
    SELECT calc_start_date INTO v_calc_date FROM societies WHERE id = p_society_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Society % not found', p_society_id; END IF;
 
    INSERT INTO apt_charges_fines_basis(
        society_id, apt_id, start_date, apt_maintenance_rate, apt_due_day, apt_interest_pct,
        apt_status
    ) VALUES (
        p_society_id, NULL, v_calc_date, 3.0, 5, 2.0, TRUE
    ) ON CONFLICT DO NOTHING;
 
    INSERT INTO ven_charges_fines_basis(
        society_id, ven_id, start_date, vendor_1day, vendor_7day, vendor_1mth,
        ven_status
    ) VALUES (
        p_society_id, NULL, v_calc_date, 100.0, 500.0, 1500.0, TRUE
    ) ON CONFLICT DO NOTHING;
END;
$$ LANGUAGE plpgsql;
 



