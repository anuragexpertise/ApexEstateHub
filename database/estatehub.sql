-- ============================================================
-- ESTATEHUB - COMPLETE DATABASE SCHEMA & FUNCTIONS (v3 - CORRECTED)
-- Accounts-as-categorisation: acc_id replaces charge_type/payment_type/category
-- Interest split: single receivable row, two transaction lines on verify
-- Double-entry bookkeeping: every financial event posts paired Dr + Cr lines
--   linked by transactions.journal_id.
-- ============================================================
-- SAFE TO RE-RUN: CREATE OR REPLACE / IF NOT EXISTS / ON CONFLICT DO NOTHING
-- Intended for a FRESH database reset followed by migrate.py seeding.
-- ============================================================

-- ════════════════════════════════════════════════════════════════
-- SECTION 1: CORE SCHEMA
-- ════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS societies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    PAN_number VARCHAR(10),
    logo VARCHAR(100),
    address TEXT,
    email VARCHAR(100),
    phone VARCHAR(20),
    secretary_name VARCHAR(100),
    secretary_phone VARCHAR(20),
    secretary_sign VARCHAR(100),
    payment_qr VARCHAR(255),
    plan VARCHAR(20) NOT NULL DEFAULT 'Free' CHECK (
        plan IN (
            'Free',
            '9Apts',
            '99Apts',
            '999Apts',
            'unlimited'
        )
    ),
    plan_validity DATE NOT NULL DEFAULT CURRENT_DATE,
    calc_start_date DATE NOT NULL DEFAULT CURRENT_DATE,
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

-- ── accounts ──────────────────────────────────────────────────
-- `tab_name` is reserved for future per-tab Excel/ledger export (AccEstate sheet
-- grouping). It is NOT used as a category or filter key anywhere in the engine.
-- Categorisation is entirely determined by acc_id + drcr_account at the point
-- of use — there is no `category` column on this table.
CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    tab_name VARCHAR(20), -- Excel ledger tab grouping only
    header VARCHAR(50),
    parent_account_id INT,
    drcr_account VARCHAR(2) CHECK (
        drcr_account IN ('Dr', 'Cr')
        OR drcr_account IS NULL
    ),
    has_bf BOOLEAN DEFAULT FALSE,
    drcr_bf VARCHAR(2) NOT NULL CHECK (drcr_bf IN ('Dr', 'Cr')),
    bf_amount NUMERIC(12, 2) DEFAULT 0.00,
    depreciation_percent NUMERIC(5, 2) DEFAULT 100.00,
    is_depreciable BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_account_society_name UNIQUE (society_id, name),
    CONSTRAINT fk_account_parent FOREIGN KEY (parent_account_id) REFERENCES accounts (id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED
);

-- is_cash_or_bank: explicit flag so cashbook logic doesn't have to guess
-- account identity from name/header text matching. Set TRUE on Cash-in-Hand
-- and every bank account (ICICI, SBI, etc). ALTER, not inline on CREATE
-- TABLE, so it still applies on databases where accounts already exists
-- (CREATE TABLE IF NOT EXISTS is a no-op there).
ALTER TABLE accounts
ADD COLUMN IF NOT EXISTS is_cash_or_bank BOOLEAN NOT NULL DEFAULT FALSE;

-- One-time backfill guess for existing rows (review after running — this
-- is a convenience seed, not a guarantee). Uses the same name patterns
-- fn_resolve_cash_account already relies on.
UPDATE accounts
SET
    is_cash_or_bank = TRUE
WHERE
    is_cash_or_bank = FALSE
    AND drcr_account = 'Dr'
    AND (
        name ILIKE '%cash-in-hand%'
        OR name ILIKE '%cash in hand%'
        OR name ILIKE '%bank%'
        OR name ILIKE '%SBI%'
        OR name ILIKE '%ICICI%'
    );

-- ════════════════════════════════════════════════════════════════
-- accounts.bf_amount / accounts.drcr_bf(*) retirement
--
-- *** RUN THIS ONLY AFTER CONFIRMING brought_forward IS SEEDED ***
-- fn_seed_brought_forward_from_accounts() (the one-time copy helper)
-- has already been removed from this script on the assumption its job
-- is done. If you have NOT yet run it against this database, DO NOT
-- run the DROP COLUMN below — you will permanently lose any BF values
-- still sitting only in accounts.bf_amount. Instead, run this first:
--
--   INSERT INTO brought_forward
--       (society_id, financial_year, acc_id, drcr_bf, bf_amount,
--        is_auto_calculated, remarks, created_at)
--   SELECT society_id, <your_financial_year>, id, drcr_bf,
--          COALESCE(bf_amount, 0), FALSE, 'Manual pre-drop seed', NOW()
--   FROM accounts WHERE has_bf = TRUE
--   ON CONFLICT (society_id, financial_year, acc_id) DO NOTHING;
--
-- Once you've confirmed brought_forward has the rows you expect,
-- uncomment the line below (or run it separately) to drop the column.
-- Left commented rather than active, since this script may be re-run
-- against a database that hasn't been checked yet.
--
-- ALTER TABLE accounts DROP COLUMN IF EXISTS bf_amount;
-- ════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS apartments (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    flat_number VARCHAR(20) NOT NULL,
    owner_name VARCHAR(100),
    owner_photo VARCHAR(255),
    id_proof VARCHAR(255),
    mobile VARCHAR(15),
    alt_mobile VARCHAR(15),
    alt_address TEXT,
    apartment_size INT NOT NULL DEFAULT 0,
    apt_calc_start_date DATE DEFAULT CURRENT_DATE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    created_by INT REFERENCES users (id),
    updated_by INT REFERENCES users (id),
    CONSTRAINT uq_apartment_society_flat UNIQUE (society_id, flat_number)
);

CREATE TABLE IF NOT EXISTS vendors (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    business_name VARCHAR(100) NOT NULL,
    logo VARCHAR(255),
    license VARCHAR(255),
    name VARCHAR(100),
    photo VARCHAR(255),
    service_type VARCHAR(100),
    mobile VARCHAR(15),
    service_description TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    created_by INT REFERENCES users (id),
    updated_by INT REFERENCES users (id)
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
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    created_by INT REFERENCES users (id),
    updated_by INT REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS assets (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    company_name VARCHAR(100),
    asset_name VARCHAR(100) NOT NULL,
    asset_SNo VARCHAR(50),
    purchase_date DATE,
    purchase_value NUMERIC(12, 2),
    acc_id INT REFERENCES accounts (id), -- asset class account (e.g. Furniture 61)
    depreciation_rate NUMERIC(5, 2),
    last_depreciation_date DATE,
    disposed BOOLEAN NOT NULL DEFAULT FALSE,
    disposed_at DATE,
    sale_value NUMERIC(12, 2),
    sale_acc_id INT REFERENCES accounts (id), -- Selling Asset income account (e.g. 212)
    disposed_by INT REFERENCES users (id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INT REFERENCES users (id),
    updated_at TIMESTAMP,
    updated_by INT REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    event_date DATE NOT NULL,
    event_time TIME,
    venue VARCHAR(200),
    open_to VARCHAR(20) DEFAULT 'all',
    parent_account_id INT REFERENCES accounts (id), -- e.g. event income or event expense account
    ticket_name VARCHAR(20) DEFAULT 'Adult',
    ticket_price NUMERIC(10, 2) DEFAULT 0, -- per-ticket price when parent_account_id is a ticket (Cr) account
    ticket_name2 VARCHAR(20) DEFAULT 'Child',
    ticket_price2 NUMERIC(10, 2) DEFAULT 0,
    image TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by INT REFERENCES users (id),
    updated_at TIMESTAMP,
    updated_by INT REFERENCES users (id)
);
-- Migrate existing events table to support dual ticket pricing
ALTER TABLE events ADD COLUMN IF NOT EXISTS ticket_name VARCHAR(20) DEFAULT 'Adult';
ALTER TABLE events ADD COLUMN IF NOT EXISTS ticket_price2 NUMERIC(10,2) DEFAULT 0;
ALTER TABLE events ADD COLUMN IF NOT EXISTS ticket_name2 VARCHAR(20) DEFAULT 'Child';

CREATE TABLE IF NOT EXISTS concerns (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    flat_no VARCHAR(20),
    concern_type VARCHAR(50),
    description TEXT,
    preferred_time VARCHAR(20),
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    assigned_to VARCHAR(100),
    image TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by INT REFERENCES users (id),
    updated_at TIMESTAMP,
    updated_by INT REFERENCES users (id)
);

-- ── security_roster & attendance (needed before payables FK) ──
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

-- ════════════════════════════════════════════════════════════════
-- RECEIVABLES  — auto-credits, one row per entity per billing period.
--
-- KEY DESIGN:
--   acc_id       → the income account this receivable maps to when posted
--                  (e.g. 2311 = Society Maintenance Charge for maintenance rows).
--                  Set by the generator function; flows directly into transactions
--                  when fn_verify_receivable / fn_pay_apartment_dues_fifo run.
--   interest_acc_id → separate income account for the interest component
--                  (e.g. 2113 = Due Interest). If NULL, interest is posted
--                  to the same acc_id as the base amount.
--   description  → acc_particulars that lands in transactions.transactions.
--                  DEFAULT pattern: 'Maintenance Apr-2025' / 'Salary Apr-2025'.
--   NO charge_type column — the account row itself is the category.
--
--   ADVANCE CREDIT rows (status='credit'):
--   Created when fn_pay_apartment_dues_fifo() collects more than the entity
--   currently owes. Reuses the same row shape as an ordinary due, but
--   inverted in meaning — it's money the SOCIETY owes back to the entity,
--   held as a balance to auto-offset future dues:
--     amount       → the credit originally granted (unallocated overpayment)
--     paid_amount  → how much of that credit has since been drawn down
--                    against later dues (0 = fully available)
--     residual (amount - paid_amount, same formula fn_receivables_named
--                    already exposes) → remaining unused credit balance
--   fn_apply_advance_credit() draws these down FIFO against the entity's
--   oldest pending/partial rows; a credit row flips to 'paid' once fully
--   consumed (paid_amount = amount), same terminal state as a settled due.
-- ════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS receivables (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    entity_id INT NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (
        role IN (
            'apartment',
            'vendor',
            'security'
        )
    ),
    acc_id INT REFERENCES accounts (id), -- income account for base amount
    interest_acc_id INT REFERENCES accounts (id), -- income account for interest (NULL = same as acc_id)
    description TEXT NOT NULL DEFAULT 'Receivable', -- becomes acc_particulars in transactions
    period_month DATE, -- first-of-month; NULL for non-periodic rows
    base_amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    interest_amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    interest_months_applied INT NOT NULL DEFAULT 0,
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0), -- base + interest, kept in sync
    paid_amount NUMERIC(10, 2) NOT NULL DEFAULT 0 CHECK (paid_amount >= 0),
    -- paid_principal = portion of paid_amount applied to the BASE (principal)
    -- component only. paid_amount - paid_principal = interest portion paid.
    -- Tracked separately so Simple Interest next month is charged strictly on
    -- the UNPAID principal residual (never on interest) — required by Indian
    -- housing-society bye-laws. See fn_pay_apartment_dues_fifo / fn_verify_receivable.
    paid_principal NUMERIC(10, 2) NOT NULL DEFAULT 0 CHECK (paid_principal >= 0),
    due_date DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (
        status IN (
            'pending',
            'partial',
            'unverified',
            'paid',
            'cancelled',
            'credit'
        )
    ),
    confirmed_by INT REFERENCES users (id),
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_receivable_entity_month ON receivables (entity_id, role, period_month)
WHERE
    period_month IS NOT NULL;

-- ── RECEIPTS — manual credits, deemed paid on creation ────────
CREATE TABLE IF NOT EXISTS receipts (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id),
    entity_id INT,
    role VARCHAR(20) CHECK (
        role IN (
            'apartment',
            'vendor',
            'security',
            'other'
        )
    ),
    receipt_date DATE NOT NULL,
    acc_id INT REFERENCES accounts (id), -- income account (Cr) — IS the category
    particulars TEXT NOT NULL, -- human-readable label; suggested from Python PARTICULARS_TEMPLATES
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
    last_printed_at TIMESTAMP,
    last_emailed_at TIMESTAMP,
    receipt_number VARCHAR(64) UNIQUE,
    previous_hash VARCHAR(64),
    source_reference VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ── EXPENSES — manual debits, deemed paid on creation ─────────
CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id),
    entity_id INT,
    role VARCHAR(20) CHECK (
        role IN (
            'vendor',
            'security',
            'other',
            'assets'
        )
    ),
    expense_date DATE NOT NULL,
    acc_id INT REFERENCES accounts (id), -- expense account (Dr) — IS the category
    particulars TEXT NOT NULL, -- human-readable label; suggested from Python PARTICULARS_TEMPLATES
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
    last_printed_at TIMESTAMP,
    last_emailed_at TIMESTAMP,
    previous_hash VARCHAR(64),
    source_reference VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ════════════════════════════════════════════════════════════════
-- payables  — auto-debits (security payroll from roster).
--
-- KEY DESIGN:
--   acc_id       → expense account for this payment
--                  (e.g. 235 = Salary). Set by fn_auto_generate_payables;
--                  flows directly into transactions on fn_verify_payment.
--   description  → acc_particulars in transactions.
--                  DEFAULT pattern: 'Salary Apr-2025'.
--   NO payment_type column — acc_id IS the type.
--   roster_id    → UNIQUE, prevents double-billing one shift.
-- ════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS payables (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    entity_id INT, -- security_staff.id
    role VARCHAR(20) CHECK (
        role IN (
            'apartment',
            'vendor',
            'security',
            'other'
        )
    ),
    acc_id INT REFERENCES accounts (id), -- expense account (Dr) — IS the category
    description TEXT NOT NULL DEFAULT 'Payment', -- becomes acc_particulars in transactions
    roster_id INT REFERENCES security_roster (id),
    shift_date DATE,
    amount NUMERIC(10, 2) NOT NULL,
    mode VARCHAR(20),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (
        status IN (
            'pending',
            'verified',
            'failed',
            'cancelled'
        )
    ),
    due_date DATE,
    paid_at TIMESTAMP,
    confirmed_by INT REFERENCES users (id),
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_payment_roster UNIQUE (roster_id)
);

-- ── TRANSACTIONS — single ledger source of truth ───────────────
-- source_table / source_id trace every row back to its origin
-- (receipts / expenses / receivables / payables).
-- journal_id links the paired Dr + Cr lines of one financial event
-- for double-entry bookkeeping.
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    trx_date DATE NOT NULL,
    acc_id INT REFERENCES accounts (id),
    entity_id INTEGER,
    acc_particulars VARCHAR(200),
    amount NUMERIC(15, 2) NOT NULL CHECK (amount > 0),
    mode VARCHAR(10) DEFAULT 'cash' CHECK (
        mode IN (
            'cash',
            'cheque',
            'upi',
            'card',
            'bank',
            'crypto'
        )
    ),
    payment_gateway_id VARCHAR(50),
    status VARCHAR(20) NOT NULL DEFAULT 'paid',
    source_table VARCHAR(50),
    source_id INT,
    created_by INTEGER REFERENCES users (id),
    journal_id INT,
    transaction_number VARCHAR(64) UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transactions_journal ON transactions (journal_id);

-- ── Vendor passes ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vendor_passes (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT NOT NULL REFERENCES users (id),
    pass_type VARCHAR(20) NOT NULL DEFAULT '1day' CHECK (
        pass_type IN (
            '1day',
            '7day',
            '1mth',
            'free_1mth'
        )
    ),
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

-- ── Event tickets ──────────────────────────────────────────────
-- Tracks who bought tickets for which event; the money itself is
-- recorded via the usual receipts/transactions pair (acc_id = the
-- event's parent_account_id, e.g. "Holi" = 23191 under "Event
-- Ticket" = 2319), same pattern as vendor_passes -> receipts.
CREATE TABLE IF NOT EXISTS event_tickets (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    event_id INT NOT NULL REFERENCES events (id) ON DELETE CASCADE,
    user_id INT NOT NULL REFERENCES users (id),
    quantity_adult INT NOT NULL DEFAULT 0 CHECK (quantity_adult >= 0),
    quantity_child INT NOT NULL DEFAULT 0 CHECK (quantity_child >= 0),
    amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    receipt_id INT REFERENCES receipts (id),
    issued_date DATE DEFAULT CURRENT_DATE,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_event_tickets_event ON event_tickets (event_id);

CREATE INDEX IF NOT EXISTS idx_event_tickets_user ON event_tickets (user_id);

-- ── Apartment charges / fines basis ───────────────────────────
CREATE TABLE IF NOT EXISTS apt_charges_fines_basis (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    apt_id INT REFERENCES apartments (id),
    start_date DATE NOT NULL,
    end_date DATE,
    apt_maintenance_amount NUMERIC(10, 2) NOT NULL DEFAULT 1500, -- amount overide rate
    apt_maintenance_rate NUMERIC(10, 2) NOT NULL DEFAULT 3.0,
    apt_due_day INTEGER DEFAULT 5,
    apt_interest_pct NUMERIC(5, 2) DEFAULT 1.75,
    apt_status BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    updated_by INT REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS idx_apt_charges_society ON apt_charges_fines_basis (society_id, apt_id);

-- ── Vendor charges ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ven_charges_fines_basis (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    ven_id INT REFERENCES vendors (id),
    start_date DATE NOT NULL,
    end_date DATE,
    vendor_1day NUMERIC(10, 2) DEFAULT 0,
    vendor_7day NUMERIC(10, 2) DEFAULT 0,
    vendor_1mth NUMERIC(10, 2) DEFAULT 0,
    ven_status BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    updated_by INT REFERENCES users (id)
);

-- ── Gate access & other tables ─────────────────────────────────
CREATE TABLE IF NOT EXISTS gate_access (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    entity_id INTEGER NOT NULL,
    role VARCHAR(20),
    time_in TIMESTAMP NOT NULL DEFAULT NOW(),
    time_out TIMESTAMP
);

-- brought_forward: opening balance per account per financial year.
-- Replaces accounts.bf_amount/drcr_bf as the source of truth once
-- seeded (see fn_seed_brought_forward_from_accounts below).
CREATE TABLE IF NOT EXISTS brought_forward (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    financial_year SMALLINT NOT NULL, -- START year of FY, e.g. 2025 = FY 1-Apr-2025..31-Mar-2026
    acc_id INT NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
    drcr_bf VARCHAR(2) NOT NULL CHECK (drcr_bf IN ('Dr', 'Cr')),
    bf_amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00 CHECK (bf_amount >= 0),
    is_auto_calculated BOOLEAN NOT NULL DEFAULT FALSE, -- TRUE if written by fn_close_financial_year
    remarks VARCHAR(200),
    created_by INT REFERENCES users (id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP,
    updated_by INT REFERENCES users (id),
    CONSTRAINT uq_bf_society_fy_acc UNIQUE (
        society_id,
        financial_year,
        acc_id
    )
);

CREATE INDEX IF NOT EXISTS idx_bf_society_fy ON brought_forward (society_id, financial_year);

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

CREATE TABLE IF NOT EXISTS Dashboard_settings (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    key VARCHAR(100) NOT NULL,
    value TEXT,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (society_id, key)
);

CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    body TEXT NOT NULL,
    url VARCHAR(500),
    notification_type VARCHAR(50) NOT NULL DEFAULT 'push',
    read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ════════════════════════════════════════════════════════════════
-- SECTION 2: INDEXES
-- ════════════════════════════════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications (
    user_id,
    read,
    created_at DESC
);

CREATE INDEX IF NOT EXISTS idx_gate_entity_role_time ON gate_access (entity_id, role, time_in);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

CREATE INDEX IF NOT EXISTS idx_users_society_role ON users (society_id, role);

CREATE INDEX IF NOT EXISTS idx_apartments_society ON apartments (society_id);

CREATE INDEX IF NOT EXISTS idx_apartments_active ON apartments (society_id, active);

CREATE INDEX IF NOT EXISTS idx_vendors_society ON vendors (society_id);

CREATE INDEX IF NOT EXISTS idx_security_society ON security_staff (society_id);

CREATE INDEX IF NOT EXISTS idx_accounts_society ON accounts (society_id);

CREATE INDEX IF NOT EXISTS idx_accounts_drcr ON accounts (society_id, drcr_account);

CREATE INDEX IF NOT EXISTS idx_transactions_society_date ON transactions (society_id, trx_date DESC);

CREATE INDEX IF NOT EXISTS idx_transactions_source ON transactions (source_table, source_id);

CREATE INDEX IF NOT EXISTS idx_transactions_acc_date ON transactions (acc_id, trx_date);

CREATE INDEX IF NOT EXISTS idx_transactions_entity_date ON transactions (entity_id, trx_date);

CREATE INDEX IF NOT EXISTS idx_payables_society_status ON payables (society_id, status);

CREATE INDEX IF NOT EXISTS idx_payables_roster ON payables (roster_id);

CREATE INDEX IF NOT EXISTS idx_receipts_society_status ON receipts (society_id, status);

CREATE INDEX IF NOT EXISTS idx_receipts_entity_role ON receipts (entity_id, role);

CREATE INDEX IF NOT EXISTS idx_expenses_society_status ON expenses (society_id, status);

CREATE INDEX IF NOT EXISTS idx_expenses_entity_role ON expenses (entity_id, role);

CREATE INDEX IF NOT EXISTS idx_payables_entity_role ON payables (entity_id, role);

CREATE INDEX IF NOT EXISTS idx_receivables_society_status ON receivables (society_id, status);

CREATE INDEX IF NOT EXISTS idx_receivables_entity ON receivables (entity_id, role);

CREATE INDEX IF NOT EXISTS idx_receivables_due_date ON receivables (due_date);

CREATE INDEX IF NOT EXISTS idx_receivables_entity_status_date ON receivables (
    entity_id,
    role,
    status,
    due_date
);

CREATE INDEX IF NOT EXISTS idx_events_society_date ON events (society_id, event_date);

CREATE INDEX IF NOT EXISTS idx_concerns_society_status ON concerns (society_id, status);

CREATE INDEX IF NOT EXISTS idx_gate_society_time ON gate_access (society_id, time_in);

CREATE INDEX IF NOT EXISTS idx_security_roster_date ON security_roster (society_id, roster_date);

CREATE INDEX IF NOT EXISTS idx_ven_charges_society ON ven_charges_fines_basis (society_id, ven_id);

CREATE INDEX IF NOT EXISTS idx_ven_charges_status ON ven_charges_fines_basis (society_id, ven_status);

CREATE INDEX IF NOT EXISTS idx_vendor_passes_user ON vendor_passes (user_id, valid_until);

CREATE INDEX IF NOT EXISTS idx_assets_society ON assets (society_id, disposed);

CREATE INDEX IF NOT EXISTS idx_dashboard_settings_lookup ON Dashboard_settings (society_id, key);

-- ════════════════════════════════════════════════════════════════
-- SECTION 2B: NUMBERING SEQUENCES & TRIGGERS
-- Auto-generate human-friendly receipt_number / transaction_number.
-- ════════════════════════════════════════════════════════════════
CREATE SEQUENCE IF NOT EXISTS seq_receipt_number;

CREATE SEQUENCE IF NOT EXISTS seq_transaction_number;

-- ── Chain hash helpers ─────────────────────────────────────────
DROP FUNCTION IF EXISTS fn_compute_receipt_hash(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT) CASCADE;

CREATE OR REPLACE FUNCTION fn_compute_receipt_hash(
    p_society_id       TEXT,
    p_acc_id           TEXT,
    p_amount           TEXT,
    p_confirmed_at     TEXT,
    p_entity_id        TEXT,
    p_role             TEXT,
    p_particulars      TEXT,
    p_mode             TEXT,
    p_receipt_date     TEXT,
    p_entity_name      TEXT,
    p_previous_hash    TEXT,
    p_source_reference TEXT
) RETURNS VARCHAR(64) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_input TEXT;
BEGIN
    v_input :=
        COALESCE(p_society_id,       '') || '|' ||
        COALESCE(p_acc_id,           '') || '|' ||
        LPAD(COALESCE(p_amount,      '0'), 20, ' ') || '|' ||
        COALESCE(p_confirmed_at,     '') || '|' ||
        COALESCE(p_entity_id,        '') || '|' ||
        COALESCE(p_role,             '') || '|' ||
        COALESCE(p_particulars,      '') || '|' ||
        COALESCE(p_mode,             '') || '|' ||
        COALESCE(p_receipt_date,     '') || '|' ||
        COALESCE(p_entity_name,      '') || '|' ||
        COALESCE(p_previous_hash,    '') || '|' ||
        COALESCE(p_source_reference, '') || '|' ||
        'APEX_RECEIPT_V1';

    RETURN ENCODE(DIGEST(v_input, 'sha256'), 'hex');
END;
$$;

-- Get the previous receipt hash in the same (society_id, acc_id) chain.
DROP FUNCTION IF EXISTS fn_get_chain_previous_hash (INT, INT, TIMESTAMP) CASCADE;

CREATE OR REPLACE FUNCTION fn_get_chain_previous_hash(
    p_society_id   INT,
    p_acc_id       INT,
    p_confirmed_at TIMESTAMP
) RETURNS VARCHAR(64) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_hash  VARCHAR(64);
    v_seed  VARCHAR(64);
BEGIN
    -- Chain genesis for this (society, acc_id)
    v_seed := ENCODE(DIGEST(
        p_society_id::TEXT || '|' || COALESCE(p_acc_id::TEXT,'0') || '|' || 'APEX_RECEIPT_V1',
        'sha256'), 'hex');

    SELECT receipt_number INTO v_hash
      FROM receipts
     WHERE society_id = p_society_id
       AND acc_id = p_acc_id
       AND status = 'confirmed'
       AND receipt_number IS NOT NULL
       AND confirmed_at < p_confirmed_at
     ORDER BY confirmed_at DESC, id DESC
     LIMIT 1;

    RETURN COALESCE(v_hash, v_seed);
END;
$$;

-- Issue the immutable SHA256 receipt_number for a confirmed receipt.
DROP FUNCTION IF EXISTS fn_issue_receipt_hash_for_receipt (INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_issue_receipt_hash_for_receipt(p_receipt_id INT)
RETURNS VARCHAR(64) LANGUAGE plpgsql AS $$
DECLARE
    v_rec         receipts%ROWTYPE;
    v_entity_name TEXT;
    v_prev_hash   VARCHAR(64);
    v_number      VARCHAR(64);
BEGIN
    SELECT * INTO v_rec FROM receipts WHERE id = p_receipt_id FOR UPDATE;
    IF NOT FOUND THEN RETURN NULL; END IF;
    IF v_rec.status <> 'confirmed' THEN RETURN NULL; END IF;
    IF v_rec.confirmed_at IS NULL THEN
        v_rec.confirmed_at := NOW();
    END IF;

    -- Resolve entity_name for hash determinism
    IF v_rec.role = 'apartment' THEN
        SELECT COALESCE(flat_number || ' - ' || COALESCE(owner_name,''), '') INTO v_entity_name
          FROM apartments WHERE id = v_rec.entity_id;
    ELSIF v_rec.role = 'vendor' THEN
        SELECT COALESCE(name,'') INTO v_entity_name FROM vendors WHERE id = v_rec.entity_id;
    ELSIF v_rec.role = 'security' THEN
        SELECT COALESCE(name,'') INTO v_entity_name FROM security_staff WHERE id = v_rec.entity_id;
    ELSE
        v_entity_name := COALESCE(v_rec.entity_id::TEXT, '');
    END IF;

    v_prev_hash := fn_get_chain_previous_hash(v_rec.society_id, v_rec.acc_id, v_rec.confirmed_at);

    v_number := fn_compute_receipt_hash(
        v_rec.society_id::TEXT,
        COALESCE(v_rec.acc_id::TEXT,      '0'),
        COALESCE(v_rec.amount::TEXT,      '0'),
        COALESCE(TO_CHAR(v_rec.confirmed_at,'YYYY-MM-DD HH24:MI:SS.US'), ''),
        COALESCE(v_rec.entity_id::TEXT,   ''),
        COALESCE(v_rec.role,              ''),
        COALESCE(v_rec.particulars,       ''),
        COALESCE(v_rec.mode,              ''),
        COALESCE(v_rec.receipt_date::TEXT,''),
        COALESCE(v_entity_name,           ''),
        v_prev_hash,
        COALESCE(v_rec.source_reference,  '')
    );

    UPDATE receipts
       SET receipt_number = v_number,
           previous_hash  = v_prev_hash,
           confirmed_at   = v_rec.confirmed_at
     WHERE id = p_receipt_id;

    RETURN v_number;
END;
$$;

-- BEFORE INSERT/UPDATE trigger: auto-issue receipt_number when status flips to 'confirmed'.
DROP FUNCTION IF EXISTS fn_trg_receipt_hash_issue () CASCADE;

CREATE OR REPLACE FUNCTION fn_trg_receipt_hash_issue()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_number       VARCHAR(64);
    v_entity_name  TEXT;
    v_prev_hash    VARCHAR(64);
    v_chain_seed   VARCHAR(64);
BEGIN
    IF NEW.status = 'confirmed' AND (OLD.status IS DISTINCT FROM NEW.status OR OLD.status IS NULL) THEN
        IF NEW.confirmed_at IS NULL THEN
            NEW.confirmed_at := NOW();
        END IF;
        IF NEW.receipt_number IS NULL OR TRIM(NEW.receipt_number) = '' THEN
            IF NEW.role = 'apartment' THEN
                SELECT COALESCE(flat_number || ' - ' || COALESCE(owner_name,''), '') INTO v_entity_name
                  FROM apartments WHERE id = NEW.entity_id;
            ELSIF NEW.role = 'vendor' THEN
                SELECT COALESCE(name,'') INTO v_entity_name FROM vendors WHERE id = NEW.entity_id;
            ELSIF NEW.role = 'security' THEN
                SELECT COALESCE(name,'') INTO v_entity_name FROM security_staff WHERE id = NEW.entity_id;
            ELSE
                v_entity_name := COALESCE(NEW.entity_id::TEXT, '');
            END IF;

            v_chain_seed := ENCODE(DIGEST(
                NEW.society_id::TEXT || '|' || COALESCE(NEW.acc_id::TEXT,'0') || '|' || 'APEX_RECEIPT_V1',
                'sha256'), 'hex');

            SELECT receipt_number INTO v_prev_hash
              FROM receipts
             WHERE society_id = NEW.society_id
               AND acc_id = NEW.acc_id
               AND status = 'confirmed'
               AND receipt_number IS NOT NULL
               AND id <> NEW.id
               AND confirmed_at < NEW.confirmed_at
             ORDER BY confirmed_at DESC, id DESC
             LIMIT 1;

            v_prev_hash := COALESCE(v_prev_hash, v_chain_seed);

            v_number := fn_compute_receipt_hash(
                NEW.society_id::TEXT,
                COALESCE(NEW.acc_id::TEXT,      '0'),
                COALESCE(NEW.amount::TEXT,      '0'),
                COALESCE(TO_CHAR(NEW.confirmed_at,'YYYY-MM-DD HH24:MI:SS.US'), ''),
                COALESCE(NEW.entity_id::TEXT,   ''),
                COALESCE(NEW.role,              ''),
                COALESCE(NEW.particulars,       ''),
                COALESCE(NEW.mode,              ''),
                COALESCE(NEW.receipt_date::TEXT, ''),
                COALESCE(v_entity_name,         ''),
                v_prev_hash,
                COALESCE(NEW.source_reference,  '')
            );

            NEW.receipt_number := v_number;
            NEW.previous_hash  := v_prev_hash;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_receipt_hash_issue ON receipts;

CREATE TRIGGER trg_receipt_hash_issue
    BEFORE UPDATE OF status ON receipts
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_receipt_hash_issue();

-- Fallback BEFORE INSERT trigger: if a receipt is inserted already confirmed, issue number immediately.
DROP FUNCTION IF EXISTS fn_trg_receipt_hash_insert () CASCADE;

CREATE OR REPLACE FUNCTION fn_trg_receipt_hash_insert()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_number       VARCHAR(64);
    v_entity_name  TEXT;
    v_prev_hash    VARCHAR(64);
    v_chain_seed   VARCHAR(64);
BEGIN
    IF NEW.status = 'confirmed' THEN
        IF NEW.confirmed_at IS NULL THEN
            NEW.confirmed_at := NOW();
        END IF;
        IF NEW.receipt_number IS NULL OR TRIM(NEW.receipt_number) = '' THEN
            IF NEW.role = 'apartment' THEN
                SELECT COALESCE(flat_number || ' - ' || COALESCE(owner_name,''), '') INTO v_entity_name
                  FROM apartments WHERE id = NEW.entity_id;
            ELSIF NEW.role = 'vendor' THEN
                SELECT COALESCE(name,'') INTO v_entity_name FROM vendors WHERE id = NEW.entity_id;
            ELSIF NEW.role = 'security' THEN
                SELECT COALESCE(name,'') INTO v_entity_name FROM security_staff WHERE id = NEW.entity_id;
            ELSE
                v_entity_name := COALESCE(NEW.entity_id::TEXT, '');
            END IF;

            v_chain_seed := ENCODE(DIGEST(
                NEW.society_id::TEXT || '|' || COALESCE(NEW.acc_id::TEXT,'0') || '|' || 'APEX_RECEIPT_V1',
                'sha256'), 'hex');

            SELECT receipt_number INTO v_prev_hash
              FROM receipts
             WHERE society_id = NEW.society_id
               AND acc_id = NEW.acc_id
               AND status = 'confirmed'
               AND receipt_number IS NOT NULL
               AND confirmed_at < NEW.confirmed_at
             ORDER BY confirmed_at DESC, id DESC
             LIMIT 1;

            v_prev_hash := COALESCE(v_prev_hash, v_chain_seed);

            v_number := fn_compute_receipt_hash(
                NEW.society_id::TEXT,
                COALESCE(NEW.acc_id::TEXT,      '0'),
                COALESCE(NEW.amount::TEXT,      '0'),
                COALESCE(TO_CHAR(NEW.confirmed_at,'YYYY-MM-DD HH24:MI:SS.US'), ''),
                COALESCE(NEW.entity_id::TEXT,   ''),
                COALESCE(NEW.role,              ''),
                COALESCE(NEW.particulars,       ''),
                COALESCE(NEW.mode,              ''),
                COALESCE(NEW.receipt_date::TEXT, ''),
                COALESCE(v_entity_name,         ''),
                v_prev_hash,
                COALESCE(NEW.source_reference,  '')
            );

            NEW.receipt_number := v_number;
            NEW.previous_hash  := v_prev_hash;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_receipt_hash_insert ON receipts;

CREATE TRIGGER trg_receipt_hash_insert
    BEFORE INSERT ON receipts
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_receipt_hash_insert();

-- Same for expenses: placeholder no-op triggers (expense hash feature not yet fully implemented).
DROP FUNCTION IF EXISTS fn_trg_expense_hash_issue () CASCADE;
CREATE OR REPLACE FUNCTION fn_trg_expense_hash_issue()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_expense_hash_issue ON expenses;
CREATE TRIGGER trg_expense_hash_issue
    BEFORE UPDATE OF status ON expenses
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_expense_hash_issue();

DROP FUNCTION IF EXISTS fn_trg_expense_hash_insert () CASCADE;
CREATE OR REPLACE FUNCTION fn_trg_expense_hash_insert()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_expense_hash_insert ON expenses;
CREATE TRIGGER trg_expense_hash_insert
    BEFORE INSERT ON expenses
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_expense_hash_insert();

DROP FUNCTION IF EXISTS fn_trg_transaction_number () CASCADE;

CREATE OR REPLACE FUNCTION fn_trg_transaction_number()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.transaction_number IS NULL OR TRIM(NEW.transaction_number) = '' THEN
        NEW.transaction_number := 'TXN-' || TO_CHAR(CURRENT_DATE, 'YYYYMM') || '-' ||
            LPAD(NEXTVAL('seq_transaction_number')::TEXT, 6, '0');
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_transaction_number ON transactions;

CREATE TRIGGER trg_transaction_number
    BEFORE INSERT ON transactions
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_transaction_number();

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
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_apartment_active_guard ON apartments;

CREATE TRIGGER trg_apartment_active_guard
    BEFORE UPDATE ON apartments
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_apartment_active_guard();

-- Generic updated_at stamping trigger factory
DROP FUNCTION IF EXISTS fn_trg_set_updated_at () CASCADE;

CREATE OR REPLACE FUNCTION fn_trg_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_vendors_updated ON vendors;

CREATE TRIGGER trg_vendors_updated
    BEFORE UPDATE ON vendors
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_set_updated_at();

DROP TRIGGER IF EXISTS trg_security_updated ON security_staff;

CREATE TRIGGER trg_security_updated
    BEFORE UPDATE ON security_staff
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_set_updated_at();

DROP TRIGGER IF EXISTS trg_assets_updated ON assets;

CREATE TRIGGER trg_assets_updated
    BEFORE UPDATE ON assets
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_set_updated_at();

DROP TRIGGER IF EXISTS trg_events_updated ON events;

CREATE TRIGGER trg_events_updated
    BEFORE UPDATE ON events
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_set_updated_at();

DROP TRIGGER IF EXISTS trg_concerns_updated ON concerns;

CREATE TRIGGER trg_concerns_updated
    BEFORE UPDATE ON concerns
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_set_updated_at();

DROP TRIGGER IF EXISTS trg_apt_charges_updated ON apt_charges_fines_basis;

CREATE TRIGGER trg_apt_charges_updated
    BEFORE UPDATE ON apt_charges_fines_basis
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_set_updated_at();

DROP TRIGGER IF EXISTS trg_ven_charges_updated ON ven_charges_fines_basis;

CREATE TRIGGER trg_ven_charges_updated
    BEFORE UPDATE ON ven_charges_fines_basis
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_set_updated_at();

-- ════════════════════════════════════════════════════════════════
-- SECTION 3B: GATE-PASS EVALUATION
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

DROP FUNCTION IF EXISTS fn_apply_advance_credit CASCADE;

CREATE OR REPLACE FUNCTION fn_apply_advance_credit(
    p_entity_id INT,
    p_role      VARCHAR
)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    credit_rec  RECORD;
    due_rec     RECORD;
    v_credit_left NUMERIC(15,2);
    v_take        NUMERIC(15,2);
    v_row_residual NUMERIC(15,2);
    v_row_int      NUMERIC(15,2);
    v_row_prin     NUMERIC(15,2);
    v_pay_int      NUMERIC(15,2);
    v_pay_prin     NUMERIC(15,2);
BEGIN
    FOR credit_rec IN
        SELECT id, amount, paid_amount
        FROM receivables
        WHERE entity_id = p_entity_id AND role = p_role AND status = 'credit'
          AND amount > paid_amount
        ORDER BY created_at ASC, id ASC
        FOR UPDATE
    LOOP
        v_credit_left := credit_rec.amount - credit_rec.paid_amount;
        EXIT WHEN v_credit_left <= 0;

        FOR due_rec IN
            SELECT id, amount, paid_amount, paid_principal, base_amount,
                   interest_amount
            FROM receivables
            WHERE entity_id = p_entity_id AND role = p_role
              AND status IN ('pending','partial')
            ORDER BY due_date ASC NULLS LAST, id ASC
            FOR UPDATE
        LOOP
            EXIT WHEN v_credit_left <= 0;
            v_row_residual := due_rec.amount - due_rec.paid_amount;
            v_row_int      := LEAST(
                due_rec.interest_amount - GREATEST(due_rec.paid_amount - due_rec.paid_principal, 0),
                v_row_residual);
            v_row_int      := GREATEST(v_row_int, 0);
            v_row_prin     := v_row_residual - v_row_int;

            -- Apply advance credit interest-first (bye-law allocation order).
            v_pay_int  := LEAST(v_credit_left, v_row_int);
            v_pay_prin := LEAST(v_credit_left - v_pay_int, v_row_prin);
            v_take     := v_pay_int + v_pay_prin;
            IF v_take <= 0 THEN CONTINUE; END IF;

            UPDATE receivables
                 SET paid_amount   = due_rec.paid_amount + v_take,
                     paid_principal = due_rec.paid_principal + v_pay_prin,
                     status        = CASE WHEN due_rec.paid_amount + v_take >= due_rec.amount
                                          THEN 'paid' ELSE 'partial' END
                 WHERE id = due_rec.id;

            v_credit_left := v_credit_left - v_take;
        END LOOP;

        UPDATE receivables
             SET paid_amount = credit_rec.amount - v_credit_left,
                 status      = CASE WHEN v_credit_left <= 0 THEN 'paid' ELSE 'credit' END
             WHERE id = credit_rec.id;
    END LOOP;
END;
$$;

-- Generates one receivable row per apartment per calendar month.
CREATE OR REPLACE FUNCTION fn_auto_generate_receivables(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    v_society_calc_start DATE;
    v_calc_start         DATE;
    v_month              DATE;
    v_month_start        DATE;
    v_month_end          DATE;
    v_days_in_month      INT;
    v_overlap_start      DATE;
    v_overlap_end        DATE;
    v_overlap_days       INT;
    apt           RECORD;
    charge        RECORD;
    v_base        NUMERIC(10,2);
    v_due_date    DATE;
    v_desc        TEXT;
    -- fallback account IDs resolved once per society call
    v_fallback_maint_acc  INT;
    v_fallback_int_acc    INT;
BEGIN
    SELECT calc_start_date INTO v_society_calc_start FROM societies WHERE id = p_society_id;
    IF v_society_calc_start IS NULL THEN RETURN; END IF;

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
        SELECT id, apartment_size, apt_calc_start_date FROM apartments
        WHERE society_id = p_society_id AND active = TRUE
    LOOP
        v_calc_start := COALESCE(apt.apt_calc_start_date, v_society_calc_start);

        -- Patch existing NULL rows for this apartment while we are here
        UPDATE receivables
        SET acc_id          = COALESCE(acc_id, v_fallback_maint_acc),
            interest_acc_id = COALESCE(interest_acc_id, v_fallback_int_acc)
        WHERE society_id = p_society_id
          AND entity_id  = apt.id
          AND role       = 'apartment'
          AND (acc_id IS NULL OR interest_acc_id IS NULL);

        v_month := DATE_TRUNC('month', v_calc_start)::DATE;
        WHILE v_month <= DATE_TRUNC('month', CURRENT_DATE)::DATE LOOP
            v_month_start   := v_month;
            v_month_end     := (v_month + INTERVAL '1 month - 1 day')::DATE;
            v_days_in_month := (v_month_end - v_month_start + 1);

            SELECT apt_maintenance_amount, apt_maintenance_rate, apt_due_day,
                   apt_interest_pct, start_date, end_date
            INTO charge
            FROM apt_charges_fines_basis
            WHERE society_id = p_society_id AND apt_status = TRUE
              AND (apt_id = apt.id OR apt_id IS NULL)
              AND start_date <= v_month_end
              AND (end_date IS NULL OR end_date >= v_month_start)
            ORDER BY apt_id NULLS LAST, start_date DESC
            LIMIT 1;

            IF charge.apt_maintenance_rate IS NULL THEN
                charge.apt_maintenance_amount := NULL;
                charge.apt_maintenance_rate   := 3.0;
                charge.apt_due_day            := 5;
                charge.apt_interest_pct       := 1.75;
                charge.start_date             := v_month_start;
                charge.end_date               := v_month_end;
            END IF;

            v_overlap_start := GREATEST(v_month_start, charge.start_date, v_calc_start);
            v_overlap_end   := LEAST(v_month_end, COALESCE(charge.end_date, v_month_end));
            v_overlap_days  := GREATEST((v_overlap_end - v_overlap_start + 1)::INT, 0);

            IF v_overlap_days = 0 THEN
                v_month := (v_month + INTERVAL '1 month')::DATE;
                CONTINUE;
            END IF;

            IF charge.apt_maintenance_amount IS NOT NULL AND charge.apt_maintenance_amount > 0 THEN
                v_base := ROUND(charge.apt_maintenance_amount * v_overlap_days::NUMERIC / v_days_in_month, 2);
            ELSE
                v_base := ROUND(apt.apartment_size * charge.apt_maintenance_rate * v_overlap_days::NUMERIC / v_days_in_month, 2);
            END IF;

            v_due_date := (v_month + ((COALESCE(charge.apt_due_day,5) - 1) * INTERVAL '1 day'))::DATE;
            v_desc     := 'Maintenance ' || TO_CHAR(v_month, 'Mon-YYYY');

            INSERT INTO receivables (
                society_id, entity_id, role,
                acc_id, interest_acc_id,
                description, period_month,
                base_amount, amount, paid_principal, due_date, status, created_at
            ) VALUES (
                p_society_id, apt.id, 'apartment',
                v_fallback_maint_acc, v_fallback_int_acc,
                v_desc, v_month,
                v_base, v_base, 0, v_due_date, 'pending', NOW()
            )
            ON CONFLICT DO NOTHING;

            v_month := (v_month + INTERVAL '1 month')::DATE;
        END LOOP;

        PERFORM fn_apply_advance_credit(apt.id, 'apartment');
    END LOOP;
END;
$$;

-- Applies SIMPLE INTEREST monthly on overdue residual.
DROP FUNCTION IF EXISTS fn_apply_receivable_interest (INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_apply_receivable_interest(p_society_id INT)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    rec               RECORD;
    v_rate            NUMERIC(5,2);
    v_months_elapsed  INT;
    v_months_new      INT;
    v_residual        NUMERIC(15,2);
    v_total_increment NUMERIC(15,2);
    v_int_acc_id      INT;
BEGIN
    SELECT id
      INTO v_int_acc_id
    FROM accounts
    WHERE society_id = p_society_id
      AND name ILIKE '%Due Interest%'
      AND drcr_account = 'Cr'
    LIMIT 1;

    FOR rec IN
        SELECT
            r.id,
            r.entity_id,
            r.due_date,
            r.base_amount,
            r.amount,
            COALESCE(r.paid_amount,0)               AS paid_amount,
            COALESCE(r.paid_principal,0)            AS paid_principal,
            COALESCE(r.interest_amount,0)           AS interest_amount,
            COALESCE(r.interest_months_applied,0)   AS interest_months_applied,
            r.description,
            r.interest_acc_id
        FROM receivables r
        WHERE r.society_id = p_society_id
          AND r.role = 'apartment'
          AND r.status IN ('pending','partial')
          AND r.due_date < CURRENT_DATE
        FOR UPDATE
    LOOP
        SELECT apt_interest_pct
          INTO v_rate
        FROM apt_charges_fines_basis
        WHERE society_id = p_society_id
          AND apt_status = TRUE
          AND (apt_id = rec.entity_id OR apt_id IS NULL)
        ORDER BY apt_id NULLS LAST,
                 start_date DESC
        LIMIT 1;

        IF COALESCE(v_rate,0) <= 0 THEN
            CONTINUE;
        END IF;

        v_months_elapsed :=
            GREATEST(
                (
                    EXTRACT(YEAR FROM AGE(CURRENT_DATE, rec.due_date))*12
                  + EXTRACT(MONTH FROM AGE(CURRENT_DATE, rec.due_date))
                )::INT,
                0
            );

        v_months_new :=
            v_months_elapsed - rec.interest_months_applied;

        IF v_months_new <= 0 THEN
            CONTINUE;
        END IF;

        v_residual :=
            GREATEST(
                COALESCE(rec.base_amount,0)
              - COALESCE(rec.paid_principal,0),
                0
            );

        IF v_residual = 0 THEN
            CONTINUE;
        END IF;

        v_total_increment :=
            ROUND(
                v_residual
                * v_rate
                * v_months_new
                / 100.0,
                2
            );

        IF v_total_increment <= 0 THEN
            CONTINUE;
        END IF;

        UPDATE receivables
           SET interest_amount =
                    COALESCE(interest_amount,0) + v_total_increment,
               amount =
                    COALESCE(amount,0) + v_total_increment,
               interest_months_applied =
                    COALESCE(interest_months_applied,0) + v_months_new,
               interest_acc_id =
                    COALESCE(interest_acc_id, v_int_acc_id),
               description =
                    CASE
                        WHEN description IS NULL
                            THEN 'Interest'
                        WHEN description LIKE '% + Interest'
                            THEN description
                        ELSE description || ' + Interest'
                    END
         WHERE id = rec.id;

    END LOOP;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 4B: DOUBLE-ENTRY CASH ACCOUNT RESOLVER
-- Returns the Dr (cash/bank) account to pair against an income/expense
-- account for a given society + payment mode.
--   mode='bank' → SBI A/c - Society (6311) if present, else first Dr account
--   otherwise   → Cash-in-hand (633) if present, else first Dr account
-- ════════════════════════════════════════════════════════════════
DROP FUNCTION IF EXISTS fn_resolve_cash_account (INT, VARCHAR) CASCADE;

CREATE OR REPLACE FUNCTION fn_resolve_cash_account(p_society_id INT, p_mode VARCHAR)
RETURNS INT LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_acc_id INT;
BEGIN
    IF p_mode = 'bank' THEN
        SELECT id INTO v_acc_id FROM accounts
        WHERE society_id = p_society_id AND drcr_account = 'Dr'
          AND name ILIKE '%SBI A/c - Society%'
        LIMIT 1;
    ELSE
        SELECT id INTO v_acc_id FROM accounts
        WHERE society_id = p_society_id AND drcr_account = 'Dr'
          AND name ILIKE '%Cash-in-hand%'
        LIMIT 1;
    END IF;

    IF v_acc_id IS NULL THEN
        SELECT id INTO v_acc_id FROM accounts
        WHERE society_id = p_society_id AND drcr_account = 'Dr'
        ORDER BY id ASC LIMIT 1;
    END IF;

    RETURN v_acc_id;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 4C: UNIFIED RECEIPT SAVE + VERIFY (double-entry)
-- fn_save_receipt determines status from creator role:
--   admin/master -> 'confirmed' + transactions posted immediately
--   anyone else  -> 'pending', no transactions yet
-- fn_save_receipt_pending is removed; its logic is subsumed.
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_verify_receipt CASCADE;

CREATE OR REPLACE FUNCTION fn_verify_receipt(
    p_receipt_id   INT,
    p_confirmed_by INT,
    p_mode         VARCHAR DEFAULT NULL
)
RETURNS TABLE(receipt_id INT, receipt_number VARCHAR(64), msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_rec    receipts%ROWTYPE;
    v_trx_id INT;
    v_journal_id INT;
    v_cash_acc INT;
    v_mode VARCHAR(20);
    v_number VARCHAR(64);
BEGIN
    SELECT * INTO v_rec FROM receipts WHERE id = p_receipt_id FOR UPDATE;
    IF NOT FOUND    THEN receipt_id := p_receipt_id; receipt_number := NULL; msg := 'Error: Receipt not found'; RETURN NEXT; RETURN; END IF;
    IF v_rec.status = 'confirmed'  THEN receipt_id := p_receipt_id; receipt_number := v_rec.receipt_number; msg := 'Already confirmed'; RETURN NEXT; RETURN; END IF;
    IF v_rec.status = 'cancelled'  THEN receipt_id := p_receipt_id; receipt_number := v_rec.receipt_number; msg := 'Error: Receipt is cancelled'; RETURN NEXT; RETURN; END IF;
    IF v_rec.acc_id IS NULL        THEN receipt_id := p_receipt_id; receipt_number := v_rec.receipt_number; msg := 'Error: No income account on this receipt'; RETURN NEXT; RETURN; END IF;

    v_mode := COALESCE(p_mode, v_rec.mode);
    v_cash_acc := fn_resolve_cash_account(v_rec.society_id, v_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    -- Cr: income account (the receipt's acc_id)
    INSERT INTO transactions(
        society_id, trx_date, acc_id, entity_id, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id, journal_id
    ) VALUES (
        v_rec.society_id, v_rec.receipt_date, v_rec.acc_id, v_rec.entity_id,
        v_rec.particulars,
        v_rec.amount, v_mode, 'paid',
        p_confirmed_by, NOW(), 'receipts', v_rec.id, v_journal_id
    ) RETURNING id INTO v_trx_id;

    -- Dr: cash / bank paired side (double-entry)
    IF v_cash_acc IS NOT NULL AND v_cash_acc <> v_rec.acc_id THEN
        INSERT INTO transactions(
            society_id, trx_date, acc_id, entity_id, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_rec.society_id, v_rec.receipt_date, v_cash_acc, v_rec.entity_id,
            'Cash received - ' || v_rec.particulars,
            v_rec.amount, v_mode, 'paid',
            p_confirmed_by, NOW(), 'receipts', v_rec.id, v_journal_id
        );
    END IF;

    UPDATE receipts
    SET status       = 'confirmed',
        confirmed_by = p_confirmed_by,
        confirmed_at = NOW()
    WHERE id = p_receipt_id;

    v_number := fn_issue_receipt_hash_for_receipt(p_receipt_id);

    receipt_id := p_receipt_id;
    receipt_number := v_number;
    msg := 'Verified: transaction #' || v_trx_id::TEXT || ' receipt_number=' || COALESCE(v_number, 'N/A');
    RETURN NEXT;
END;
$$;

-- Verify a pending expense: posts Dr expense + Cr cash/bank, then issues hash.
DROP FUNCTION IF EXISTS fn_verify_expense CASCADE;

CREATE OR REPLACE FUNCTION fn_verify_expense(
    p_expense_id   INT,
    p_confirmed_by INT,
    p_mode         VARCHAR DEFAULT NULL
)
RETURNS TABLE(expense_id INT, receipt_number VARCHAR(64), msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_rec    expenses%ROWTYPE;
    v_trx_id INT;
    v_journal_id INT;
    v_cash_acc INT;
    v_mode VARCHAR(20);
    v_number VARCHAR(64);
BEGIN
    SELECT * INTO v_rec FROM expenses WHERE id = p_expense_id FOR UPDATE;
    IF NOT FOUND    THEN expense_id := p_expense_id; receipt_number := NULL; msg := 'Error: Expense not found'; RETURN NEXT; RETURN; END IF;
    IF v_rec.status = 'confirmed'  THEN expense_id := p_expense_id; receipt_number := v_rec.receipt_number; msg := 'Already confirmed'; RETURN NEXT; RETURN; END IF;
    IF v_rec.status = 'cancelled'  THEN expense_id := p_expense_id; receipt_number := v_rec.receipt_number; msg := 'Error: Expense is cancelled'; RETURN NEXT; RETURN; END IF;
    IF v_rec.acc_id IS NULL        THEN expense_id := p_expense_id; receipt_number := v_rec.receipt_number; msg := 'Error: No expense account on this row'; RETURN NEXT; RETURN; END IF;

    v_mode := COALESCE(p_mode, v_rec.mode);
    v_cash_acc := fn_resolve_cash_account(v_rec.society_id, v_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    -- Dr: expense account
    INSERT INTO transactions(
        society_id, trx_date, acc_id, entity_id, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id, journal_id
    ) VALUES (
        v_rec.society_id, v_rec.expense_date, v_rec.acc_id, v_rec.entity_id,
        v_rec.particulars,
        v_rec.amount, v_mode, 'paid',
        p_confirmed_by, NOW(), 'expenses', v_rec.id, v_journal_id
    ) RETURNING id INTO v_trx_id;

    -- Cr: cash / bank paired side
    IF v_cash_acc IS NOT NULL AND v_cash_acc <> v_rec.acc_id THEN
        INSERT INTO transactions(
            society_id, trx_date, acc_id, entity_id, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_rec.society_id, v_rec.expense_date, v_cash_acc, v_rec.entity_id,
            'Cash paid - ' || v_rec.particulars,
            v_rec.amount, v_mode, 'paid',
            p_confirmed_by, NOW(), 'expenses', v_rec.id, v_journal_id
        );
    END IF;

    UPDATE expenses
    SET status       = 'confirmed',
        confirmed_by = p_confirmed_by,
        confirmed_at = NOW()
    WHERE id = p_expense_id;

    v_number := fn_issue_receipt_hash_for_receipt(p_expense_id);

    expense_id := p_expense_id;
    receipt_number := v_number;
    msg := 'Verified: transaction #' || v_trx_id::TEXT || ' receipt_number=' || COALESCE(v_number, 'N/A');
    RETURN NEXT;
END;
$$;

-- Single-row verify. Writes the income side(s), then the cash/bank Dr side.
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
    v_journal_id  INT;
    v_cash_acc    INT;
BEGIN
    SELECT * INTO v_rec FROM receivables WHERE id = p_receivable_id FOR UPDATE;
    IF NOT FOUND THEN RETURN 'Error: Receivable not found'; END IF;
    IF v_rec.status = 'paid' THEN RETURN 'Already fully paid'; END IF;
    IF v_rec.acc_id IS NULL THEN RETURN 'Error: No income account set on this receivable — check apt_charges_fines_basis'; END IF;

    v_residual := v_rec.amount - v_rec.paid_amount;
    IF v_residual <= 0 THEN RETURN 'Nothing outstanding on this row'; END IF;

    v_int_acc  := v_rec.interest_acc_id;
    v_int_post := LEAST(v_rec.interest_amount - GREATEST(v_rec.paid_amount - v_rec.base_amount, 0), v_residual);
    v_int_post := GREATEST(COALESCE(v_int_post, 0), 0);
    v_base_post := v_residual - v_int_post;

    v_cash_acc := fn_resolve_cash_account(v_rec.society_id, p_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    IF v_int_acc IS NOT NULL AND v_int_post > 0 THEN
        -- Line 1: base maintenance income
        INSERT INTO transactions(
            society_id, trx_date, acc_id, entity_id, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_rec.society_id, CURRENT_DATE, v_rec.acc_id, v_rec.entity_id,
            REPLACE(v_rec.description, ' + Interest', ''),
            v_base_post, p_mode, 'paid', p_confirmed_by, NOW(), 'receivables', v_rec.id, v_journal_id
        ) RETURNING id INTO v_trx_id;

        -- Line 2: interest income to separate account
        INSERT INTO transactions(
            society_id, trx_date, acc_id, entity_id, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_rec.society_id, CURRENT_DATE, v_int_acc, v_rec.entity_id,
            'Interest on ' || REPLACE(v_rec.description, ' + Interest', ''),
            v_int_post, p_mode, 'paid', p_confirmed_by, NOW(), 'receivables', v_rec.id, v_journal_id
        );
    ELSE
        -- Single line: full residual goes to maintenance income account
        INSERT INTO transactions(
            society_id, trx_date, acc_id, entity_id, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_rec.society_id, CURRENT_DATE, v_rec.acc_id, v_rec.entity_id,
            v_rec.description,
            v_residual, p_mode, 'paid', p_confirmed_by, NOW(), 'receivables', v_rec.id, v_journal_id
        ) RETURNING id INTO v_trx_id;
    END IF;

    -- Dr: cash / bank paired side (total residual)
    IF v_cash_acc IS NOT NULL AND v_cash_acc <> v_rec.acc_id THEN
        INSERT INTO transactions(
            society_id, trx_date, acc_id, entity_id, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_rec.society_id, CURRENT_DATE, v_cash_acc, v_rec.entity_id,
            'Cash received - ' || REPLACE(v_rec.description, ' + Interest', ''),
            v_residual, p_mode, 'paid', p_confirmed_by, NOW(), 'receivables', v_rec.id, v_journal_id
        );
    END IF;

    UPDATE receivables
         SET paid_amount  = v_rec.amount,
             paid_principal = v_rec.base_amount,
             status       = 'paid',
             confirmed_by = p_confirmed_by,
             confirmed_at = NOW()
         WHERE id = p_receivable_id;

    RETURN 'Verified: transaction #' || v_trx_id::TEXT;
END;
$$;

-- Bulk FIFO payment across monthly rows (Pay Dues button).
-- Posts ONE journal (income side + cash Dr side) for the whole payment.
DROP FUNCTION IF EXISTS fn_pay_apartment_dues_fifo CASCADE;

CREATE OR REPLACE FUNCTION fn_pay_apartment_dues_fifo(
    p_apartment_id INT,
    p_amount       NUMERIC,
    p_mode         VARCHAR DEFAULT 'cash',
    p_confirmed_by INT     DEFAULT NULL,
    p_particulars  TEXT    DEFAULT NULL
)
RETURNS TABLE(transaction_id INT, allocated NUMERIC, unallocated NUMERIC, journal_id INT)
LANGUAGE plpgsql AS $$
DECLARE
    v_society_id INT;
    v_acc_id     INT;
    v_desc       TEXT;
    v_remaining  NUMERIC(15,2) := p_amount;
    v_trx_id     INT;
    v_journal_id INT;
    v_cash_acc   INT;
    rec          RECORD;
    v_take        NUMERIC(15,2);
    v_row_residual NUMERIC(15,2);
    v_row_int      NUMERIC(15,2);
    v_row_prin     NUMERIC(15,2);
    v_pay_int      NUMERIC(15,2);
    v_pay_prin     NUMERIC(15,2);
    v_fallback_int_acc INT;
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN
        RAISE EXCEPTION 'Amount must be > 0';
    END IF;

    SELECT society_id INTO v_society_id FROM apartments WHERE id = p_apartment_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Apartment not found'; END IF;

    SELECT id INTO v_fallback_int_acc FROM accounts
    WHERE society_id = v_society_id
      AND name ILIKE '%Due Interest%' AND drcr_account = 'Cr'
    LIMIT 1;

    SELECT acc_id, description INTO v_acc_id, v_desc
    FROM receivables
    WHERE entity_id = p_apartment_id AND role = 'apartment'
      AND status IN ('pending','partial')
    ORDER BY due_date ASC NULLS LAST LIMIT 1;

    IF v_acc_id IS NULL THEN
        SELECT id INTO v_acc_id FROM accounts
        WHERE society_id = v_society_id
          AND name ILIKE '%Society Maintenance Charge%'
          AND drcr_account = 'Cr'
        LIMIT 1;
    END IF;

    v_cash_acc := fn_resolve_cash_account(v_society_id, p_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    -- Cr: income side (one journal line for the whole payment)
    INSERT INTO transactions(
        society_id, trx_date, acc_id, entity_id, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, journal_id
    ) VALUES (
        v_society_id, CURRENT_DATE, v_acc_id, p_apartment_id,
        COALESCE(p_particulars, 'Maintenance Payment'),
        p_amount, p_mode, 'paid', p_confirmed_by, NOW(), 'receivables', v_journal_id
    ) RETURNING id INTO v_trx_id;

    -- Dr: cash / bank paired side
    IF v_cash_acc IS NOT NULL AND v_cash_acc <> v_acc_id THEN
        INSERT INTO transactions(
            society_id, trx_date, acc_id, entity_id, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_society_id, CURRENT_DATE, v_cash_acc, p_apartment_id,
            'Cash received - Maintenance Payment',
            p_amount, p_mode, 'paid', p_confirmed_by, NOW(), 'receivables', v_trx_id, v_journal_id
        );
    END IF;

    FOR rec IN
        SELECT id, amount, paid_amount, paid_principal, base_amount,
               interest_amount, confirmed_by FROM receivables
        WHERE entity_id = p_apartment_id AND role = 'apartment'
          AND status IN ('pending','partial')
        ORDER BY due_date ASC NULLS LAST, id ASC
        FOR UPDATE
    LOOP
        EXIT WHEN v_remaining <= 0;

        v_row_residual := rec.amount - rec.paid_amount;
        v_row_int      := LEAST(
            rec.interest_amount - GREATEST(rec.paid_amount - rec.paid_principal, 0),
            v_row_residual);
        v_row_int      := GREATEST(v_row_int, 0);
        v_row_prin     := v_row_residual - v_row_int;

        v_pay_int  := LEAST(v_remaining, v_row_int);
        v_pay_prin := LEAST(v_remaining - v_pay_int, v_row_prin);
        v_take     := v_pay_int + v_pay_prin;
        IF v_take <= 0 THEN CONTINUE; END IF;

        UPDATE receivables
             SET paid_amount    = rec.paid_amount + v_take,
                 paid_principal = rec.paid_principal + v_pay_prin,
                 status         = CASE WHEN rec.paid_amount + v_take >= rec.amount
                                        THEN 'paid' ELSE 'partial' END,
                 confirmed_by   = COALESCE(p_confirmed_by, rec.confirmed_by),
                 confirmed_at   = NOW()
             WHERE id = rec.id;

        v_remaining := v_remaining - v_take;
    END LOOP;

    -- Excess beyond every currently-open due is banked as an advance-credit
    -- row (status='credit') rather than discarded.
    IF v_remaining > 0 THEN
        INSERT INTO receivables (
            society_id, entity_id, role, acc_id, interest_acc_id,
            description, base_amount, amount, paid_amount, paid_principal,
            status, confirmed_by, confirmed_at, created_at
        ) VALUES (
            v_society_id, p_apartment_id, 'apartment', v_acc_id,
            COALESCE(v_fallback_int_acc, v_acc_id),
            'Advance Credit', v_remaining, v_remaining, 0, 0,
            'credit', p_confirmed_by, NOW(), NOW()
        );
    END IF;

    RETURN QUERY SELECT v_trx_id,
        (p_amount - v_remaining)::NUMERIC(15,2),
        v_remaining::NUMERIC(15,2),
        v_journal_id;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 5: payables ENGINE (security payroll, roster-driven)
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_auto_generate_payables CASCADE;

CREATE OR REPLACE FUNCTION fn_auto_generate_payables(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    rec          RECORD;
    v_acc_id     INT;
    v_desc       TEXT;
BEGIN
    SELECT id INTO v_acc_id FROM accounts
    WHERE society_id = p_society_id AND name ILIKE '%Salary%' AND drcr_account = 'Dr'
    LIMIT 1;

    FOR rec IN
        SELECT sr.id AS roster_id, sr.security_id, sr.roster_date, ss.salary_per_shift
        FROM security_roster sr
        JOIN security_staff ss ON ss.id = sr.security_id
        JOIN users u2 ON u2.linked_id = sr.security_id AND u2.role = 'security'
        JOIN gate_access ga
             ON ga.entity_id = u2.id
            AND ga.role = 's'
            AND ga.time_in::DATE = sr.roster_date
            AND ga.time_out IS NOT NULL
        WHERE sr.society_id = p_society_id
          AND sr.roster_date <= CURRENT_DATE
          AND NOT EXISTS (SELECT 1 FROM payables p WHERE p.roster_id = sr.id)
    LOOP
        v_desc := 'Salary ' || TO_CHAR(rec.roster_date, 'DD-Mon-YYYY');

        INSERT INTO payables(
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

-- Single-row verify. Posts Dr expense side + Cr cash/bank side.
DROP FUNCTION IF EXISTS fn_verify_payment CASCADE;

CREATE OR REPLACE FUNCTION fn_verify_payment(
    p_payment_id   INT,
    p_confirmed_by INT,
    p_mode         VARCHAR DEFAULT 'cash'
)
RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
    v_pay    payables%ROWTYPE;
    v_trx_id INT;
    v_journal_id INT;
    v_cash_acc INT;
BEGIN
    SELECT * INTO v_pay FROM payables WHERE id = p_payment_id FOR UPDATE;
    IF NOT FOUND THEN RETURN 'Error: Payment not found'; END IF;
    IF v_pay.status = 'verified' THEN RETURN 'Already verified'; END IF;
    IF v_pay.acc_id IS NULL THEN RETURN 'Error: No expense account set on this payment row'; END IF;

    v_cash_acc := fn_resolve_cash_account(v_pay.society_id, p_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    -- Dr: expense account (salary etc.)
    INSERT INTO transactions(
        society_id, trx_date, acc_id, entity_id, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id, journal_id
    ) VALUES (
        v_pay.society_id, CURRENT_DATE, v_pay.acc_id, v_pay.entity_id,
        v_pay.description,
        v_pay.amount, p_mode, 'paid', p_confirmed_by, NOW(), 'payables', v_pay.id, v_journal_id
    ) RETURNING id INTO v_trx_id;

    -- Cr: cash / bank paired side
    IF v_cash_acc IS NOT NULL AND v_cash_acc <> v_pay.acc_id THEN
        INSERT INTO transactions(
            society_id, trx_date, acc_id, entity_id, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_pay.society_id, CURRENT_DATE, v_cash_acc, v_pay.entity_id,
            'Cash paid - ' || v_pay.description,
            v_pay.amount, p_mode, 'paid', p_confirmed_by, NOW(), 'payables', v_pay.id, v_journal_id
        );
    END IF;

    UPDATE payables
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
RETURNS TABLE(receipt_id INT, pass_id INT, valid_until DATE, journal_id INT, status VARCHAR(20))
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
    v_cash_acc    INT;
    v_journal_id  INT;
    v_is_admin    BOOLEAN;
    v_status      VARCHAR(20);
BEGIN
    IF p_pass_type NOT IN ('1day','7day','1mth','free_1mth') THEN
        RAISE EXCEPTION 'Invalid pass_type %. Use 1day / 7day / 1mth / free_1mth', p_pass_type;
    END IF;

    SELECT society_id, linked_id INTO v_society_id, v_vendor_id
    FROM users WHERE id = p_user_id AND role = 'vendor';
    IF NOT FOUND THEN RAISE EXCEPTION 'Vendor user not found'; END IF;

    SELECT v.name INTO v_vendor_name FROM vendors v WHERE v.id = v_vendor_id;

    IF p_pass_type = 'free_1mth' THEN
        v_rate := 0;
    ELSE
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
    END IF;

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
        WHEN 'free_1mth' THEN p_issued_date + INTERVAL '1 month'
    END::DATE;

    v_desc := COALESCE(p_particulars,
        'Vendor Pass (' || p_pass_type || ') - ' || COALESCE(v_vendor_name,''));

    v_cash_acc := fn_resolve_cash_account(v_society_id, p_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    SELECT (role = 'admin' OR is_master_admin) INTO v_is_admin
      FROM users WHERE id = p_created_by;

    IF v_is_admin OR p_pass_type = 'free_1mth' THEN
        v_status := 'confirmed';
    ELSE
        v_status := 'pending';
    END IF;

    IF p_pass_type != 'free_1mth' THEN
        INSERT INTO receipts(
            society_id, user_id, entity_id, role,
            receipt_date, acc_id, particulars, amount, mode,
            status, confirmed_by, confirmed_at, source_reference, created_at
        ) VALUES (
            v_society_id, p_user_id, v_vendor_id, 'vendor',
            p_issued_date, v_acc_id, v_desc, v_rate, p_mode,
            v_status,
            CASE WHEN v_status = 'confirmed' THEN p_created_by ELSE NULL END,
            CASE WHEN v_status = 'confirmed' THEN NOW() ELSE NULL END,
            NULL, NOW()
        ) RETURNING id INTO v_receipt_id;

        IF v_status = 'confirmed' THEN
            -- Cr: income account
            INSERT INTO transactions(
                society_id, trx_date, acc_id, entity_id, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id, journal_id
            ) VALUES (
                v_society_id, p_issued_date, v_acc_id, v_vendor_id, v_desc,
                v_rate, p_mode, 'paid', p_created_by, NOW(), 'receipts', v_receipt_id, v_journal_id
            );

            -- Dr: cash / bank paired side
            IF v_cash_acc IS NOT NULL AND v_cash_acc <> v_acc_id THEN
                INSERT INTO transactions(
                    society_id, trx_date, acc_id, entity_id, acc_particulars,
                    amount, mode, status, created_by, created_at, source_table, source_id, journal_id
                ) VALUES (
                    v_society_id, p_issued_date, v_cash_acc, v_vendor_id,
                    'Cash received - ' || v_desc,
                    v_rate, p_mode, 'paid', p_created_by, NOW(), 'receipts', v_receipt_id, v_journal_id
                );
            END IF;
        END IF;
    ELSE
        v_receipt_id := NULL;
    END IF;

    INSERT INTO vendor_passes(
        society_id, user_id, pass_type, issued_date, valid_until, status, created_at
    ) VALUES (
        v_society_id, p_user_id, p_pass_type, p_issued_date, v_valid_until, 'active', NOW()
    ) RETURNING id INTO v_pass_id;

    receipt_id := v_receipt_id;
    pass_id := v_pass_id;
    valid_until := v_valid_until;
    journal_id := v_journal_id;
    status := v_status;
    RETURN NEXT;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 6b: EVENT TICKET SALE
--
-- fn_sell_event_ticket: Cr the event's own ticket sub-account
-- (events.parent_account_id, e.g. "Holi" = 23191 under the
-- "Event Ticket" = 2319 header) + Dr cash/bank paired side —
-- same double-entry shape as fn_sell_vendor_pass, but the
-- income account and per-unit price both come from the event
-- row itself instead of a rate table.
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_sell_event_ticket CASCADE;

CREATE OR REPLACE FUNCTION fn_sell_event_ticket(
    p_user_id      INT,
    p_event_id     INT,
    p_quantity_adult  INT DEFAULT 0,
    p_quantity_child  INT DEFAULT 0,
    p_mode         VARCHAR DEFAULT 'cash',
    p_created_by   INT DEFAULT NULL,
    p_issued_date  DATE DEFAULT CURRENT_DATE,
    p_particulars  TEXT DEFAULT NULL
)
RETURNS TABLE(receipt_id INT, ticket_id INT, amount NUMERIC, journal_id INT, status VARCHAR(20))
LANGUAGE plpgsql AS $$
DECLARE
    v_society_id   INT;
    v_apt_id       INT;
    v_flat_number  VARCHAR;
    v_event        RECORD;
    v_acc_id       INT;
    v_is_ticket_ac BOOLEAN;
    v_amount       NUMERIC(10,2);
    v_cash_acc     INT;
    v_receipt_id   INT;
    v_ticket_id    INT;
    v_desc         TEXT;
    v_journal_id   INT;
    v_is_admin     BOOLEAN;
    v_status       VARCHAR(20);
    v_total_qty    INT;
BEGIN
    IF (COALESCE(p_quantity_adult, 0) + COALESCE(p_quantity_child, 0)) < 1 THEN
        RAISE EXCEPTION 'Total ticket quantity must be at least 1';
    END IF;

    SELECT society_id, linked_id INTO v_society_id, v_apt_id
    FROM users WHERE id = p_user_id AND role = 'apartment';
    IF NOT FOUND THEN RAISE EXCEPTION 'Apartment user not found'; END IF;

    SELECT flat_number INTO v_flat_number FROM apartments WHERE id = v_apt_id;

    SELECT e.* INTO v_event FROM events e
    WHERE e.id = p_event_id AND e.society_id = v_society_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Event not found'; END IF;

    v_acc_id := v_event.parent_account_id;
    IF v_acc_id IS NULL THEN
        RAISE EXCEPTION 'This event has no ticket account set — tickets cannot be sold for it';
    END IF;

    SELECT (a.id = 2319 OR a.parent_account_id = 2319) INTO v_is_ticket_ac
    FROM accounts a WHERE a.id = v_acc_id AND a.society_id = v_society_id;
    IF v_is_ticket_ac IS NOT TRUE THEN
        RAISE EXCEPTION 'Event''s account is not an Event Ticket (2319) account — tickets cannot be sold for it';
    END IF;

    v_amount := COALESCE(v_event.ticket_price, 0) * COALESCE(p_quantity_adult, 0)
             + COALESCE(v_event.ticket_price2, 0) * COALESCE(p_quantity_child, 0);
    v_total_qty := COALESCE(p_quantity_adult, 0) + COALESCE(p_quantity_child, 0);
    v_desc := COALESCE(p_particulars,
        'Event Ticket x' || v_total_qty || ' - ' || COALESCE(v_event.title,'') ||
        ' - ' || COALESCE(v_flat_number,''));

    v_cash_acc   := fn_resolve_cash_account(v_society_id, p_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    SELECT (role = 'admin' OR is_master_admin) INTO v_is_admin
      FROM users WHERE id = p_created_by;

    IF v_is_admin THEN
        v_status := 'confirmed';
    ELSE
        v_status := 'pending';
    END IF;

    IF v_amount > 0 THEN
        INSERT INTO receipts(
            society_id, user_id, entity_id, role,
            receipt_date, acc_id, particulars, amount, mode,
            status, confirmed_by, confirmed_at, source_reference, created_at
        ) VALUES (
            v_society_id, p_user_id, v_apt_id, 'apartment',
            p_issued_date, v_acc_id, v_desc, v_amount, p_mode,
            v_status,
            CASE WHEN v_status = 'confirmed' THEN p_created_by ELSE NULL END,
            CASE WHEN v_status = 'confirmed' THEN NOW() ELSE NULL END,
            NULL, NOW()
        ) RETURNING id INTO v_receipt_id;

        IF v_status = 'confirmed' THEN
            INSERT INTO transactions(
                society_id, trx_date, acc_id, entity_id, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id, journal_id
            ) VALUES (
                v_society_id, p_issued_date, v_acc_id, v_apt_id, v_desc,
                v_amount, p_mode, 'paid', p_created_by, NOW(), 'receipts', v_receipt_id, v_journal_id
            );

            IF v_cash_acc IS NOT NULL AND v_cash_acc <> v_acc_id THEN
                INSERT INTO transactions(
                    society_id, trx_date, acc_id, entity_id, acc_particulars,
                    amount, mode, status, created_by, created_at, source_table, source_id, journal_id
                ) VALUES (
                    v_society_id, p_issued_date, v_cash_acc, v_apt_id,
                    'Cash received - ' || v_desc,
                    v_amount, p_mode, 'paid', p_created_by, NOW(), 'receipts', v_receipt_id, v_journal_id
                );
            END IF;
        END IF;
    ELSE
        v_receipt_id := NULL;
    END IF;

    INSERT INTO event_tickets(
        society_id, event_id, user_id, quantity_adult, quantity_child, amount, receipt_id, issued_date, status, created_at
    ) VALUES (
        v_society_id, p_event_id, p_user_id, COALESCE(p_quantity_adult, 0), COALESCE(p_quantity_child, 0), v_amount, v_receipt_id, p_issued_date, 'active', NOW()
    ) RETURNING id INTO v_ticket_id;

    receipt_id := v_receipt_id;
    ticket_id := v_ticket_id;
    amount := v_amount;
    journal_id := v_journal_id;
    status := v_status;
    RETURN NEXT;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 7: ASSET PURCHASE / DISPOSAL  (double-entry)
--
-- fn_buy_asset:     Dr Asset account  +  Cr Cash/Bank (NO expense row).
-- fn_dispose_asset: Dr Cash/Bank  +  Cr Asset (book value)  +  gain/loss.
-- Signatures are matched EXACTLY to the Python callers:
--   fn_buy_asset(sid, name, sno, value, acc_id, date, mode, by, particulars)
--   fn_dispose_asset(id, value, mode, by, date, particulars, acc_id)
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_buy_asset CASCADE;

CREATE OR REPLACE FUNCTION fn_buy_asset(
    p_society_id        INT,
    p_asset_name        VARCHAR,
    p_asset_sno         VARCHAR,
    p_purchase_value    NUMERIC,
    p_acc_id            INT,
    p_purchase_date     DATE    DEFAULT CURRENT_DATE,
    p_mode              VARCHAR DEFAULT 'cash',
    p_created_by        INT     DEFAULT NULL,
    p_particulars       TEXT    DEFAULT NULL
)
RETURNS TABLE(asset_id INT, transaction_id INT, journal_id INT)
LANGUAGE plpgsql AS $$
DECLARE
    v_asset_id   INT;
    v_trx_id     INT;
    v_journal_id INT;
    v_cash_acc   INT;
    v_dep_rate   NUMERIC(5,2);
    v_desc       TEXT;
BEGIN
    IF p_acc_id IS NULL THEN
        RAISE EXCEPTION 'acc_id (asset class account) is required';
    END IF;
    IF p_purchase_value IS NULL OR p_purchase_value <= 0 THEN
        RAISE EXCEPTION 'purchase_value must be > 0';
    END IF;

    SELECT depreciation_percent INTO v_dep_rate FROM accounts WHERE id = p_acc_id;

    INSERT INTO assets(
        society_id, asset_name, asset_SNo, purchase_date, purchase_value,
        acc_id, depreciation_rate, created_at, created_by
    ) VALUES (
        p_society_id, p_asset_name, p_asset_sno, p_purchase_date, p_purchase_value,
        p_acc_id, v_dep_rate, NOW(), p_created_by
    ) RETURNING id INTO v_asset_id;

    v_desc := COALESCE(p_particulars, 'Asset Purchase - ' || p_asset_name);
    v_cash_acc := fn_resolve_cash_account(p_society_id, p_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    -- Dr: asset class account
    INSERT INTO transactions(
        society_id, trx_date, acc_id, entity_id, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id, journal_id
    ) VALUES (
        p_society_id, p_purchase_date, p_acc_id, v_asset_id, v_desc,
        p_purchase_value, p_mode, 'paid', p_created_by, NOW(), 'assets', v_asset_id, v_journal_id
    ) RETURNING id INTO v_trx_id;

    -- Cr: cash / bank paired side
    IF v_cash_acc IS NOT NULL AND v_cash_acc <> p_acc_id THEN
        INSERT INTO transactions(
            society_id, trx_date, acc_id, entity_id, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            p_society_id, p_purchase_date, v_cash_acc, v_asset_id,
            'Cash paid - ' || v_desc,
            p_purchase_value, p_mode, 'paid', p_created_by, NOW(), 'assets', v_asset_id, v_journal_id
        );
    END IF;

    RETURN QUERY SELECT v_asset_id, v_trx_id, v_journal_id;
END;
$$;

DROP FUNCTION IF EXISTS fn_dispose_asset CASCADE;

CREATE OR REPLACE FUNCTION fn_dispose_asset(
    p_asset_id    INT,
    p_sale_value  NUMERIC,
    p_mode        VARCHAR DEFAULT 'cash',
    p_created_by  INT     DEFAULT NULL,
    p_sale_date   DATE    DEFAULT CURRENT_DATE,
    p_particulars TEXT    DEFAULT NULL,
    p_acc_id      INT     DEFAULT NULL
)
RETURNS TABLE(receipt_id INT, transaction_id INT, journal_id INT)
LANGUAGE plpgsql AS $$
DECLARE
    v_asset      assets%ROWTYPE;
    v_acc_id     INT;
    v_cash_acc   INT;
    v_receipt_id INT;
    v_trx_id     INT;
    v_journal_id INT;
    v_book_value NUMERIC(15,2);
    v_gain_loss  NUMERIC(15,2);
    v_desc       TEXT;
BEGIN
    SELECT * INTO v_asset FROM assets WHERE id = p_asset_id FOR UPDATE;
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

    -- Book value = purchase_value less straight-line depreciation
    v_book_value := GREATEST(
        v_asset.purchase_value * (1 - COALESCE(v_asset.depreciation_rate,
                                              COALESCE((SELECT depreciation_percent FROM accounts WHERE id = v_asset.acc_id), 100)) / 100),
        0);
    v_gain_loss := p_sale_value - v_book_value;

    v_desc := COALESCE(p_particulars, 'Asset Sale - ' || v_asset.asset_name);
    v_cash_acc := fn_resolve_cash_account(v_asset.society_id, p_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    -- Dr: cash / bank (sale proceeds)
    INSERT INTO transactions(
        society_id, trx_date, acc_id, entity_id, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id, journal_id
    ) VALUES (
        v_asset.society_id, p_sale_date, v_cash_acc, p_asset_id,
        'Cash received - ' || v_desc,
        p_sale_value, p_mode, 'paid', p_created_by, NOW(), 'assets', p_asset_id, v_journal_id
    ) RETURNING id INTO v_trx_id;

    -- Cr: asset class account (book value removal)
    INSERT INTO transactions(
        society_id, trx_date, acc_id, entity_id, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id, journal_id
    ) VALUES (
        v_asset.society_id, p_sale_date, v_asset.acc_id, p_asset_id,
        'Asset written off - ' || v_asset.asset_name,
        v_book_value, p_mode, 'paid', p_created_by, NOW(), 'assets', p_asset_id, v_journal_id
    );

    -- Cr (balancing): gain, or Dr (balancing): loss via the sale income account
    IF v_gain_loss <> 0 THEN
        IF v_gain_loss > 0 THEN
            -- Gain: Cr income account
            INSERT INTO transactions(
                society_id, trx_date, acc_id, entity_id, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id, journal_id
            ) VALUES (
                v_asset.society_id, p_sale_date, v_acc_id, p_asset_id,
                'Gain on sale - ' || v_asset.asset_name,
                v_gain_loss, p_mode, 'paid', p_created_by, NOW(), 'assets', p_asset_id, v_journal_id
            );
        ELSE
            -- Loss: Dr loss account (the same income account, debited)
            INSERT INTO transactions(
                society_id, trx_date, acc_id, entity_id, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id, journal_id
            ) VALUES (
                v_asset.society_id, p_sale_date, v_acc_id, p_asset_id,
                'Loss on sale - ' || v_asset.asset_name,
                -v_gain_loss, p_mode, 'paid', p_created_by, NOW(), 'assets', p_asset_id, v_journal_id
            );
        END IF;
    END IF;

    UPDATE assets
    SET disposed    = TRUE,
        disposed_at = p_sale_date,
        sale_value  = p_sale_value,
        sale_acc_id = v_acc_id,
        disposed_by = p_created_by
    WHERE id = p_asset_id;

    RETURN QUERY SELECT v_receipt_id, v_trx_id, v_journal_id;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 8: MANUAL RECEIPT / EXPENSE SAVE HELPER (double-entry)
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_save_receipt CASCADE;

CREATE OR REPLACE FUNCTION fn_save_receipt(
    p_society_id       INT,
    p_acc_id           INT,
    p_particulars      TEXT,
    p_amount           NUMERIC,

    p_entity_id        INT     DEFAULT NULL,
    p_role             VARCHAR DEFAULT 'other',
    p_mode             VARCHAR DEFAULT 'cash',
    p_receipt_date     DATE    DEFAULT CURRENT_DATE,
    p_created_by       INT     DEFAULT NULL,
    p_cheque_no        VARCHAR DEFAULT NULL,
    p_trx_id           VARCHAR DEFAULT NULL,
    p_source_reference VARCHAR DEFAULT NULL
)
RETURNS TABLE(receipt_id INT, transaction_id INT, journal_id INT, status VARCHAR(20))
LANGUAGE plpgsql AS $$
DECLARE
    v_receipt_id INT;
    v_trx_id     INT;
    v_journal_id INT;
    v_cash_acc   INT;
    v_drcr       VARCHAR(2);
    v_is_admin   BOOLEAN;
    v_status     VARCHAR(20);
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN RAISE EXCEPTION 'Amount must be > 0'; END IF;
    IF p_acc_id IS NULL THEN RAISE EXCEPTION 'acc_id is required'; END IF;
    IF p_particulars IS NULL OR TRIM(p_particulars) = '' THEN RAISE EXCEPTION 'particulars is required'; END IF;

    SELECT drcr_account INTO v_drcr FROM accounts WHERE id = p_acc_id AND society_id = p_society_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Account % not found for this society', p_acc_id; END IF;
    IF v_drcr = 'Dr' THEN
        RAISE EXCEPTION 'Account % is a Dr (expense) account — use fn_save_expense for expenses', p_acc_id;
    END IF;

    SELECT (role = 'admin' OR is_master_admin) INTO v_is_admin
      FROM users WHERE id = p_created_by;

    IF v_is_admin THEN
        v_status := 'confirmed';
    ELSE
        v_status := 'pending';
    END IF;

    INSERT INTO receipts(
        society_id, user_id, entity_id, role, receipt_date, acc_id, particulars,
        amount, mode, cheque_no, transaction_id, status, confirmed_by, confirmed_at,
        source_reference, created_at
    ) VALUES (
        p_society_id, p_created_by, p_entity_id, p_role, p_receipt_date, p_acc_id, p_particulars,
        p_amount, p_mode, p_cheque_no, p_trx_id, v_status,
        CASE WHEN v_status = 'confirmed' THEN p_created_by ELSE NULL END,
        CASE WHEN v_status = 'confirmed' THEN NOW() ELSE NULL END,
        p_source_reference, NOW()
    ) RETURNING id INTO v_receipt_id;

    IF v_status = 'confirmed' THEN
        v_cash_acc := fn_resolve_cash_account(p_society_id, p_mode);
        v_journal_id := NEXTVAL('seq_transaction_number');

        INSERT INTO transactions(
            society_id, trx_date, acc_id, entity_id, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            p_society_id, p_receipt_date, p_acc_id, p_entity_id, p_particulars,
            p_amount, p_mode, 'paid', p_created_by, NOW(), 'receipts', v_receipt_id, v_journal_id
        ) RETURNING id INTO v_trx_id;

        IF v_cash_acc IS NOT NULL AND v_cash_acc <> p_acc_id THEN
            INSERT INTO transactions(
                society_id, trx_date, acc_id, entity_id, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id, journal_id
            ) VALUES (
                p_society_id, p_receipt_date, v_cash_acc, p_entity_id,
                'Cash received - ' || p_particulars,
                p_amount, p_mode, 'paid', p_created_by, NOW(), 'receipts', v_receipt_id, v_journal_id
            );
        END IF;
    ELSE
        v_trx_id := NULL;
        v_journal_id := NULL;
    END IF;

    status := v_status;
    receipt_id := v_receipt_id;
    transaction_id := v_trx_id;
    journal_id := v_journal_id;

    RETURN NEXT;
END;
$$;

DROP FUNCTION IF EXISTS fn_save_expense CASCADE;

CREATE OR REPLACE FUNCTION fn_save_expense(
    p_society_id       INT,
    p_acc_id           INT,
    p_particulars      TEXT,
    p_amount           NUMERIC,

    p_entity_id        INT     DEFAULT NULL,
    p_role             VARCHAR DEFAULT 'other',
    p_mode             VARCHAR DEFAULT 'cash',
    p_expense_date     DATE    DEFAULT CURRENT_DATE,
    p_created_by       INT     DEFAULT NULL,
    p_cheque_no        VARCHAR DEFAULT NULL,
    p_trx_id           VARCHAR DEFAULT NULL,
    p_source_reference VARCHAR DEFAULT NULL
)
RETURNS TABLE(expense_id INT, transaction_id INT, journal_id INT, status VARCHAR(20))
LANGUAGE plpgsql AS $$
DECLARE
    v_expense_id INT;
    v_trx_id     INT;
    v_journal_id INT;
    v_cash_acc   INT;
    v_drcr       VARCHAR(2);
    v_is_admin   BOOLEAN;
    v_status     VARCHAR(20);
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN RAISE EXCEPTION 'Amount must be > 0'; END IF;
    IF p_acc_id IS NULL THEN RAISE EXCEPTION 'acc_id is required'; END IF;
    IF p_particulars IS NULL OR TRIM(p_particulars) = '' THEN RAISE EXCEPTION 'particulars is required'; END IF;

    SELECT drcr_account INTO v_drcr FROM accounts WHERE id = p_acc_id AND society_id = p_society_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Account % not found for this society', p_acc_id; END IF;
    IF v_drcr = 'Cr' THEN
        RAISE EXCEPTION 'Account % is a Cr (income) account — use fn_save_receipt for receipts', p_acc_id;
    END IF;

    SELECT (role = 'admin' OR is_master_admin) INTO v_is_admin
      FROM users WHERE id = p_created_by;

    IF v_is_admin THEN
        v_status := 'confirmed';
    ELSE
        v_status := 'pending';
    END IF;

    INSERT INTO expenses(
        society_id, user_id, entity_id, role, expense_date, acc_id, particulars,
        amount, mode, cheque_no, transaction_id, status, confirmed_by, confirmed_at,
        source_reference, created_at
    ) VALUES (
        p_society_id, p_created_by, p_entity_id, p_role, p_expense_date, p_acc_id, p_particulars,
        p_amount, p_mode, p_cheque_no, p_trx_id, v_status,
        CASE WHEN v_status = 'confirmed' THEN p_created_by ELSE NULL END,
        CASE WHEN v_status = 'confirmed' THEN NOW() ELSE NULL END,
        p_source_reference, NOW()
    ) RETURNING id INTO v_expense_id;

    IF v_status = 'confirmed' THEN
        v_cash_acc := fn_resolve_cash_account(p_society_id, p_mode);
        v_journal_id := NEXTVAL('seq_transaction_number');

        INSERT INTO transactions(
            society_id, trx_date, acc_id, entity_id, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            p_society_id, p_expense_date, p_acc_id, p_entity_id, p_particulars,
            p_amount, p_mode, 'paid', p_created_by, NOW(), 'expenses', v_expense_id, v_journal_id
        ) RETURNING id INTO v_trx_id;

        IF v_cash_acc IS NOT NULL AND v_cash_acc <> p_acc_id THEN
            INSERT INTO transactions(
                society_id, trx_date, acc_id, entity_id, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id, journal_id
            ) VALUES (
                p_society_id, p_expense_date, v_cash_acc, p_entity_id,
                'Cash paid - ' || p_particulars,
                p_amount, p_mode, 'paid', p_created_by, NOW(), 'expenses', v_expense_id, v_journal_id
            );
        END IF;
    ELSE
        v_trx_id := NULL;
        v_journal_id := NULL;
    END IF;

    status := v_status;
    expense_id := v_expense_id;
    transaction_id := v_trx_id;
    journal_id := v_journal_id;

    RETURN NEXT;
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
    alt_mobile VARCHAR(15), alt_address TEXT, apt_calc_start_date DATE,
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
           a.alt_mobile::VARCHAR(15), a.alt_address::TEXT, a.apt_calc_start_date::DATE,
           a.apartment_size::INT, a.active::BOOLEAN, a.society_id::INT,
           COALESCE(d.pending_dues, 0)::NUMERIC(15,2), COALESCE(d.overdue_dues, 0)::NUMERIC(15,2),
           (COALESCE(d.overdue_dues, 0) <= 0)::BOOLEAN,
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

-- Optimised vendor list: replaces repeated correlated subqueries with a
-- single LEFT JOIN LATERAL to vendor_passes.
DROP FUNCTION IF EXISTS fn_vendors_list CASCADE;

CREATE OR REPLACE FUNCTION fn_vendors_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL,
    p_has_passes BOOLEAN DEFAULT NULL
)
RETURNS TABLE (
    id INT, email VARCHAR(100), society_id INT, name VARCHAR(100),
    business_name VARCHAR(100), service_type VARCHAR(100), mobile VARCHAR(15), active BOOLEAN,
    pass_expiry DATE, gate_pass BOOLEAN, active_passes INT
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        u.id::INT, u.email::VARCHAR(100), u.society_id::INT,
        COALESCE(v.name, u.email)::VARCHAR(100),
        v.business_name::VARCHAR(100),
        COALESCE(v.service_type,'—')::VARCHAR(100),
        COALESCE(v.mobile,'—')::VARCHAR(15),
        COALESCE(v.active,TRUE)::BOOLEAN,
        COALESCE(pass.pass_expiry, p_pass_max.expiry)::DATE,
        COALESCE(pass.pass_expiry >= CURRENT_DATE, FALSE),
        (COALESCE(pass.active_passes, 0))::INT
    FROM users u
    LEFT JOIN vendors v ON v.id = u.linked_id
    LEFT JOIN LATERAL (
        SELECT MAX(valid_until) AS pass_expiry,
               COUNT(*)::INT   AS active_passes
        FROM vendor_passes vp
        WHERE vp.user_id = u.id
          AND vp.status = 'active'
          AND vp.valid_until >= CURRENT_DATE
    ) pass ON TRUE
    LEFT JOIN LATERAL (
        SELECT MAX(valid_until) AS expiry
        FROM vendor_passes vp2
        WHERE vp2.user_id = u.id AND vp2.status = 'active'
    ) p_pass_max ON TRUE
    WHERE u.society_id = p_society_id AND u.role = 'vendor'
      AND (p_search IS NULL OR v.name ILIKE '%'||p_search||'%' OR u.email ILIKE '%'||p_search||'%')
      AND (p_has_passes IS NULL
           OR (p_has_passes AND COALESCE(pass.active_passes, 0) > 0)
           OR (NOT p_has_passes AND COALESCE(pass.active_passes, 0) <= 0))
    ORDER BY v.name;
END;
$$;

DROP FUNCTION IF EXISTS fn_security_list CASCADE;

CREATE OR REPLACE FUNCTION fn_security_list(p_society_id INT, p_search TEXT DEFAULT NULL)
RETURNS TABLE (
    id INT, email VARCHAR(100), society_id INT, name VARCHAR(100),
    shift VARCHAR(20), mobile VARCHAR(15), active BOOLEAN, salary_per_shift NUMERIC(10,2),
    joining_date DATE, shift_count BIGINT, salary_due NUMERIC(15,2), salary_paid NUMERIC(15,2), gate_pass BOOLEAN
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM fn_auto_generate_payables(p_society_id);
    RETURN QUERY
    WITH pay_sum AS (
        SELECT entity_id AS staff_id,
            COUNT(*)::BIGINT AS shifts_completed,
            COALESCE(SUM(amount) FILTER (WHERE status='pending'), 0)::NUMERIC(15,2) AS salary_due,
            COALESCE(SUM(amount) FILTER (WHERE status='verified'), 0)::NUMERIC(15,2) AS salary_paid
        FROM payables p WHERE p.society_id = p_society_id AND p.role = 'security' GROUP BY entity_id
    )
    SELECT
        u.id::INT, u.email::VARCHAR(100), u.society_id::INT,
        COALESCE(s.name, u.email)::VARCHAR(100), COALESCE(s.shift,'—')::VARCHAR(20),
        COALESCE(s.mobile,'—')::VARCHAR(15), COALESCE(s.active,TRUE)::BOOLEAN,
        COALESCE(s.salary_per_shift,0)::NUMERIC(10,2), s.joining_date::DATE,
        COALESCE(ps.shifts_completed, 0)::BIGINT AS shift_count,
        COALESCE(ps.salary_due, 0)::NUMERIC(15,2), COALESCE(ps.salary_paid, 0)::NUMERIC(15,2),
        EXISTS(SELECT 1 FROM gate_access ga WHERE ga.entity_id=u.id AND ga.role='s' AND ga.time_out IS NULL)::BOOLEAN AS gate_pass
    FROM users u
    LEFT JOIN security_staff s ON s.id = u.linked_id
    LEFT JOIN pay_sum ps ON ps.staff_id = s.id
    WHERE u.society_id = p_society_id AND u.role = 'security'
      AND (p_search IS NULL OR s.name ILIKE '%'||p_search||'%')
    ORDER BY s.name;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 10: NAMED RECEIVABLES / payables
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
      AND (p_status IS NULL OR
           (p_status = 'overdue' AND r.status IN ('pending','partial') AND r.due_date < CURRENT_DATE) OR
           (p_status <> 'overdue' AND r.status = p_status))
      AND (p_entity_id   IS NULL OR r.entity_id = p_entity_id)
      AND (p_entity_role IS NULL OR r.role = p_entity_role)
      AND (p_search IS NULL OR r.description ILIKE '%'||p_search||'%' OR a.name ILIKE '%'||p_search||'%')
    ORDER BY r.due_date ASC, r.created_at DESC;
END;
$$;

DROP FUNCTION IF EXISTS fn_payables_named CASCADE;

CREATE OR REPLACE FUNCTION fn_payables_named(
    p_society_id  INT, p_search TEXT DEFAULT NULL,
    p_status      TEXT DEFAULT NULL, p_entity_role TEXT DEFAULT NULL,
    p_entity_id   INT  DEFAULT NULL
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
    FROM payables p
    LEFT JOIN accounts a       ON a.id = p.acc_id
    LEFT JOIN security_staff s ON s.id = p.entity_id AND p.role='security'
    WHERE p.society_id = p_society_id
      AND (p_status      IS NULL OR p.status = p_status)
      AND (p_entity_role IS NULL OR p.role = p_entity_role)
      AND (p_entity_id   IS NULL OR p.entity_id = p_entity_id)
      AND (p_search IS NULL OR p.description ILIKE '%'||p_search||'%' OR a.name ILIKE '%'||p_search||'%')
    ORDER BY p.due_date ASC, p.created_at DESC;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 11: RECEIPTS / EXPENSES LIST FUNCTIONS
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
                (SELECT asset_name FROM assets WHERE assets.id = e.entity_id),
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

DROP FUNCTION IF EXISTS fn_resolve_bf_amount_fy (INT, INT, SMALLINT) CASCADE;

CREATE OR REPLACE FUNCTION fn_resolve_bf_amount_fy(
    p_society_id     INT,
    p_account_id     INT,
    p_financial_year SMALLINT
)
RETURNS NUMERIC(15,2) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_bf        NUMERIC(15,2);
    v_drcr_bf   VARCHAR(2);
    v_fy_start  DATE := MAKE_DATE(p_financial_year, 4, 1);
BEGIN
    SELECT bf_amount, drcr_bf INTO v_bf, v_drcr_bf
    FROM brought_forward
    WHERE society_id = p_society_id AND acc_id = p_account_id
      AND financial_year = p_financial_year;
 
    IF FOUND THEN
        RETURN CASE WHEN v_drcr_bf = 'Dr' THEN v_bf ELSE -v_bf END;
    END IF;
 
    -- No explicit row: sum child accounts' pre-FY closing position
    -- (mirrors the original fn_resolve_bf_amount hierarchy fallback).
    SELECT COALESCE(SUM(
        CASE WHEN a.drcr_account = 'Cr'
             THEN COALESCE(t.cr_sum, 0) - COALESCE(t.dr_sum, 0)
             ELSE COALESCE(t.dr_sum, 0) - COALESCE(t.cr_sum, 0)
        END
    ), 0) INTO v_bf
    FROM accounts a
    LEFT JOIN (
        SELECT t.acc_id, a3.drcr_account,
               SUM(t.amount) FILTER (WHERE a3.drcr_account = 'Cr') AS cr_sum,
               SUM(t.amount) FILTER (WHERE a3.drcr_account = 'Dr') AS dr_sum
        FROM transactions t
        JOIN accounts a3 ON a3.id = t.acc_id
        WHERE t.status = 'paid' AND t.trx_date < v_fy_start
        GROUP BY t.acc_id, a3.drcr_account
    ) t ON t.acc_id = a.id
    WHERE a.parent_account_id = p_account_id AND a.society_id = p_society_id;
 
    RETURN COALESCE(v_bf, 0);
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 4: DEPRECIATION CALCULATION
-- Full-year depreciation on brought-forward WDV; half-year depreciation
-- on assets purchased on/after 1-Sep of the financial year (per spec:
-- "Half depreciation if asset date > 1 Sep of the year").
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_account_depreciation (INT, INT, SMALLINT) CASCADE;

CREATE OR REPLACE FUNCTION fn_account_depreciation(
    p_society_id     INT,
    p_account_id     INT,
    p_financial_year SMALLINT
)
RETURNS NUMERIC(15,2) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_dep_pct      NUMERIC(5,2);
    v_is_dep       BOOLEAN;
    v_opening_wdv  NUMERIC(15,2);
    v_dep_opening  NUMERIC(15,2) := 0;
    v_dep_additions NUMERIC(15,2) := 0;
    v_half_cutoff  DATE := MAKE_DATE(p_financial_year, 9, 1);
    v_fy_start     DATE := MAKE_DATE(p_financial_year, 4, 1);
    v_fy_end       DATE := MAKE_DATE(p_financial_year + 1, 3, 31);
BEGIN
    SELECT depreciation_percent, is_depreciable
      INTO v_dep_pct, v_is_dep
      FROM accounts WHERE id = p_account_id AND society_id = p_society_id;
 
    IF NOT FOUND OR NOT COALESCE(v_is_dep, FALSE) OR COALESCE(v_dep_pct, 100) >= 100 THEN
        RETURN 0;
    END IF;
 
    -- Depreciation on the opening WDV (assets already owned before this FY)
    v_opening_wdv := fn_resolve_bf_amount_fy(p_society_id, p_account_id, p_financial_year);
    v_dep_opening := GREATEST(v_opening_wdv, 0) * v_dep_pct / 100.0;
 
    -- Depreciation on assets purchased DURING this FY (half-year rule)
    SELECT COALESCE(SUM(
        purchase_value * v_dep_pct / 100.0 *
        CASE WHEN purchase_date >= v_half_cutoff THEN 0.5 ELSE 1.0 END
    ), 0)
    INTO v_dep_additions
    FROM assets
    WHERE society_id = p_society_id
      AND acc_id = p_account_id
      AND purchase_date BETWEEN v_fy_start AND v_fy_end
      AND disposed = FALSE;
 
    RETURN ROUND(v_dep_opening + v_dep_additions, 2);
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 5: LEDGER v2 — FY-aware BF + depreciation-aware closing
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_account_ledger_fy (INT, INT, SMALLINT) CASCADE;

CREATE OR REPLACE FUNCTION fn_account_ledger_fy(
    p_society_id     INT,
    p_account_id     INT,
    p_financial_year SMALLINT
)
RETURNS TABLE (
    row_date      DATE,
    particulars   TEXT,
    debit         NUMERIC(15,2),
    credit        NUMERIC(15,2),
    balance       NUMERIC(15,2),
    row_type      TEXT,       -- 'bf' | 'txn' | 'depreciation' | 'closing'
    parent_name   TEXT
) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_acc          RECORD;
    v_fy_start     DATE := MAKE_DATE(p_financial_year, 4, 1);
    v_fy_end       DATE := MAKE_DATE(p_financial_year + 1, 3, 31);
    v_bf           NUMERIC(15,2);
    v_bf_drcr      VARCHAR(2);
    v_balance      NUMERIC(15,2);
    v_dep_acc_id   INT;
    v_dep_amount   NUMERIC(15,2) := 0;
    v_final_balance NUMERIC(15,2);
    v_transfer_amt  NUMERIC(15,2);
BEGIN
    SELECT a.drcr_account, a.is_depreciable, a.depreciation_percent, a.parent_account_id,
           COALESCE(p.name, '--') AS parent_name
      INTO v_acc
      FROM accounts a
      LEFT JOIN accounts p ON p.id = a.parent_account_id
     WHERE a.id = p_account_id AND a.society_id = p_society_id;
 
    IF NOT FOUND THEN RETURN; END IF;
 
    -- Resolve BF (signed: +ve = natural Dr, -ve = natural Cr, per fn_resolve_bf_amount_fy)
    v_bf := fn_resolve_bf_amount_fy(p_society_id, p_account_id, p_financial_year);
    v_bf_drcr := CASE WHEN v_bf >= 0 THEN 'Dr' ELSE 'Cr' END;
    v_bf := ABS(v_bf);
 
    v_balance := v_bf;
 
    IF v_bf <> 0 THEN
        RETURN QUERY SELECT
            v_fy_start - INTERVAL '1 day', 'Balance B/F'::TEXT,
            CASE WHEN v_bf_drcr = 'Dr' THEN v_bf ELSE 0 END,
            CASE WHEN v_bf_drcr = 'Cr' THEN v_bf ELSE 0 END,
            v_balance, 'bf'::TEXT, v_acc.parent_name;
    END IF;
 
    -- Transaction rows, running balance
    RETURN QUERY
    WITH txns AS (
        SELECT t.trx_date,
               t.acc_particulars::TEXT,
               COALESCE(SUM(t.amount) FILTER (WHERE a.drcr_account = 'Dr'), 0) AS debit,
               COALESCE(SUM(t.amount) FILTER (WHERE a.drcr_account = 'Cr'), 0) AS credit
        FROM transactions t
        JOIN accounts a ON a.id = t.acc_id
        WHERE t.acc_id = p_account_id AND t.society_id = p_society_id AND t.status = 'paid'
          AND t.trx_date BETWEEN v_fy_start AND v_fy_end
        GROUP BY t.trx_date, t.acc_particulars
        ORDER BY t.trx_date ASC
    )
    SELECT
        tx.trx_date, tx.acc_particulars, tx.debit, tx.credit,
        CASE v_acc.drcr_account
            WHEN 'Cr' THEN v_balance + tx.credit - tx.debit
            ELSE v_balance - tx.credit + tx.debit
        END,
        'txn'::TEXT, v_acc.parent_name
    FROM txns tx;
 
    -- Final balance before depreciation/closing
    SELECT v_bf + COALESCE(
        CASE v_acc.drcr_account
            WHEN 'Cr' THEN SUM(CASE WHEN a.drcr_account='Cr' THEN t.amount ELSE -t.amount END)
            ELSE SUM(CASE WHEN a.drcr_account='Dr' THEN t.amount ELSE -t.amount END)
        END, 0)
    INTO v_final_balance
    FROM transactions t JOIN accounts a ON a.id = t.acc_id
    WHERE t.acc_id = p_account_id AND t.society_id = p_society_id AND t.status = 'paid'
      AND t.trx_date BETWEEN v_fy_start AND v_fy_end;
 
    v_transfer_amt := v_final_balance;
 
    -- Depreciation split (only for is_depreciable accounts with % < 100)
    IF COALESCE(v_acc.is_depreciable, FALSE) AND COALESCE(v_acc.depreciation_percent, 100) < 100 THEN
        v_dep_amount := fn_account_depreciation(p_society_id, p_account_id, p_financial_year);
        IF v_dep_amount > 0 THEN
            SELECT id INTO v_dep_acc_id FROM accounts
            WHERE society_id = p_society_id AND name = 'Dep' LIMIT 1;
 
            RETURN QUERY SELECT
                v_fy_end, ('Depreciation @ ' || v_acc.depreciation_percent || '% -> Dep A/c')::TEXT,
                CASE WHEN v_acc.drcr_account = 'Cr' THEN v_dep_amount ELSE 0::NUMERIC(15,2) END,
                CASE WHEN v_acc.drcr_account = 'Dr' THEN v_dep_amount ELSE 0::NUMERIC(15,2) END,
                (v_final_balance - v_dep_amount), 'depreciation'::TEXT,
                COALESCE((SELECT name FROM accounts WHERE id = v_dep_acc_id), 'Dep');
 
            v_transfer_amt := v_final_balance - v_dep_amount;
        END IF;
    END IF;
 
    -- Closing row: transfer remainder to parent, balance -> 0
    IF v_transfer_amt <> 0 THEN
        RETURN QUERY SELECT
            v_fy_end,
            ('Balance C/F -> ' || COALESCE(v_acc.parent_name, 'Parent'))::TEXT,
            CASE WHEN v_acc.drcr_account = 'Dr' THEN v_transfer_amt ELSE 0::NUMERIC(15,2) END,
            CASE WHEN v_acc.drcr_account = 'Cr' THEN v_transfer_amt ELSE 0::NUMERIC(15,2) END,
            0::NUMERIC(15,2), 'closing'::TEXT, v_acc.parent_name;
    END IF;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- Current financial year (1-Apr..31-Mar cycle) as a plain SMALLINT
-- start-year, e.g. a date of 15-Jan-2027 -> 2026 (FY 2026-27).
-- Used everywhere a view/function needs "today's" BF without the
-- caller having to pass one in explicitly.
-- ════════════════════════════════════════════════════════════════
DROP FUNCTION IF EXISTS fn_current_financial_year () CASCADE;

CREATE OR REPLACE FUNCTION fn_current_financial_year()
RETURNS SMALLINT LANGUAGE SQL STABLE AS $$
    SELECT (EXTRACT(YEAR FROM CURRENT_DATE)::SMALLINT
            - CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) < 4 THEN 1 ELSE 0 END);
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 12: CASHBOOK (paired Cr/Dr over transactions table)
-- fn_cashbook_paired (v1) has been retired — loaders.py and
-- cashbook_export.py now both call fn_cashbook_paired_v2 (Cash/Chq
-- split, fixed multi-leg pairing, FY-scoped BF via brought_forward).
-- ════════════════════════════════════════════════════════════════

-- fn_cashbook_paired_v2 — fixes the multi-leg journal duplication bug in
-- the old v1 (a journal with 1 Cr + 2 Dr legs repeated the Cr amount on
-- every row instead of once-then-blank), splits amounts into Cash vs Chq
-- columns by transaction mode, and includes rc_acc_id/pc_acc_id (ledger
-- folio) columns. Now the only cashbook function — loaders.py and
-- cashbook_export.py both call this.
DROP FUNCTION IF EXISTS fn_cashbook_paired_v2 (
    INT,
    INT,
    TEXT,
    TEXT,
    DATE,
    DATE
) CASCADE;

CREATE OR REPLACE FUNCTION fn_cashbook_paired_v2(
    p_society_id  INT,
    p_entity_id   INT  DEFAULT NULL,
    p_entity_role TEXT DEFAULT NULL,
    p_search      TEXT DEFAULT NULL,
    p_start_date  DATE DEFAULT NULL,
    p_end_date    DATE DEFAULT NULL
)
RETURNS TABLE (
    row_date         DATE,
    rc_acc_id INT, rc_account_name  TEXT, rc_entity_name TEXT, rc_particulars TEXT,
    rc_cash NUMERIC(15,2), rc_chq NUMERIC(15,2),
    pc_acc_id INT, pc_account_name  TEXT, pc_entity_name TEXT, pc_particulars TEXT,
    pc_cash NUMERIC(15,2), pc_chq NUMERIC(15,2),
    running_balance  NUMERIC(15,2)
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_opening_balance NUMERIC(15,2);
    v_fy SMALLINT;
BEGIN
    v_fy := CASE WHEN p_start_date IS NULL THEN fn_current_financial_year()
                 ELSE EXTRACT(YEAR FROM p_start_date)::SMALLINT
                      - CASE WHEN EXTRACT(MONTH FROM p_start_date) < 4 THEN 1 ELSE 0 END
            END;

    -- is_cash_or_bank accounts are always Dr-natured; Dr BF adds, Cr BF subtracts.
    SELECT COALESCE(SUM(
        CASE WHEN bf.drcr_bf = 'Dr' THEN bf.bf_amount ELSE -bf.bf_amount END
    ), 0)
    INTO v_opening_balance
    FROM accounts a
    JOIN brought_forward bf ON bf.acc_id = a.id AND bf.society_id = a.society_id
    WHERE a.society_id = p_society_id AND a.is_cash_or_bank = TRUE
      AND bf.financial_year = v_fy;

    RETURN QUERY
    WITH cr_rows AS (
        SELECT t.id, t.journal_id, t.trx_date,
               a.id AS acc_id, a.name::TEXT AS account_name,
               COALESCE(ap.flat_number, v.name, s.name, '')::TEXT AS entity_name,
               COALESCE(t.acc_particulars,'')::TEXT AS particulars,
               CASE WHEN t.mode = 'cash' THEN t.amount ELSE 0 END AS cash_amt,
               CASE WHEN t.mode <> 'cash' THEN t.amount ELSE 0 END AS chq_amt,
               ROW_NUMBER() OVER (PARTITION BY COALESCE(t.journal_id, -t.id) ORDER BY t.id) AS rn
        FROM transactions t
        JOIN accounts a ON a.id = t.acc_id AND a.drcr_account = 'Cr'
        LEFT JOIN apartments ap ON ap.id = t.entity_id AND ap.society_id = p_society_id
        LEFT JOIN vendors v ON v.id = t.entity_id AND v.society_id = p_society_id
        LEFT JOIN security_staff s ON s.id = t.entity_id AND s.society_id = p_society_id
        WHERE t.society_id = p_society_id AND t.status = 'paid'
          AND (p_start_date IS NULL OR t.trx_date >= p_start_date)
          AND (p_end_date IS NULL OR t.trx_date <= p_end_date)
          AND (p_entity_id IS NULL OR t.entity_id = p_entity_id)
          AND (p_entity_role IS NULL OR
               (p_entity_role = 'apartment' AND ap.id IS NOT NULL) OR
               (p_entity_role = 'vendor' AND v.id IS NOT NULL) OR
               (p_entity_role = 'security' AND s.id IS NOT NULL))
          AND (p_search IS NULL OR a.name ILIKE '%'||p_search||'%' OR t.acc_particulars ILIKE '%'||p_search||'%')
    ),
    dr_rows AS (
        SELECT t.id, t.journal_id, t.trx_date,
               a.id AS acc_id, a.name::TEXT AS account_name,
               COALESCE(ap.flat_number, v.name, s.name, '')::TEXT AS entity_name,
               COALESCE(t.acc_particulars,'')::TEXT AS particulars,
               CASE WHEN t.mode = 'cash' THEN t.amount ELSE 0 END AS cash_amt,
               CASE WHEN t.mode <> 'cash' THEN t.amount ELSE 0 END AS chq_amt,
               ROW_NUMBER() OVER (PARTITION BY COALESCE(t.journal_id, -t.id) ORDER BY t.id) AS rn
        FROM transactions t
        JOIN accounts a ON a.id = t.acc_id AND a.drcr_account = 'Dr'
        LEFT JOIN apartments ap ON ap.id = t.entity_id AND ap.society_id = p_society_id
        LEFT JOIN vendors v ON v.id = t.entity_id AND v.society_id = p_society_id
        LEFT JOIN security_staff s ON s.id = t.entity_id AND s.society_id = p_society_id
        WHERE t.society_id = p_society_id AND t.status = 'paid'
          AND (p_start_date IS NULL OR t.trx_date >= p_start_date)
          AND (p_end_date IS NULL OR t.trx_date <= p_end_date)
          AND (p_entity_id IS NULL OR t.entity_id = p_entity_id)
          AND (p_entity_role IS NULL OR
               (p_entity_role = 'apartment' AND ap.id IS NOT NULL) OR
               (p_entity_role = 'vendor' AND v.id IS NOT NULL) OR
               (p_entity_role = 'security' AND s.id IS NOT NULL))
          AND (p_search IS NULL OR a.name ILIKE '%'||p_search||'%' OR t.acc_particulars ILIKE '%'||p_search||'%')
    ),
    journals AS (
        SELECT COALESCE(journal_id, -id) AS jid, trx_date FROM transactions
        WHERE society_id = p_society_id AND status = 'paid'
        GROUP BY COALESCE(journal_id, -id), trx_date
    ),
    slot_counts AS (
        SELECT j.jid, j.trx_date,
               GREATEST(COALESCE(MAX(cr.rn), 0), COALESCE(MAX(dr.rn), 0)) AS max_rn
        FROM journals j
        LEFT JOIN cr_rows cr ON cr.journal_id = j.jid OR (cr.journal_id IS NULL AND -cr.id = j.jid)
        LEFT JOIN dr_rows dr ON dr.journal_id = j.jid OR (dr.journal_id IS NULL AND -dr.id = j.jid)
        GROUP BY j.jid, j.trx_date
        HAVING GREATEST(COALESCE(MAX(cr.rn), 0), COALESCE(MAX(dr.rn), 0)) > 0
    ),
    slots AS (
        SELECT jid, trx_date, gs AS rn
        FROM slot_counts, LATERAL generate_series(1, max_rn) AS gs
    ),
    paired AS (
        SELECT
            sl.trx_date AS row_date,
            cr.acc_id AS rc_acc_id,
            cr.account_name AS rc_account_name, cr.entity_name AS rc_entity_name,
            cr.particulars AS rc_particulars, cr.cash_amt AS rc_cash, cr.chq_amt AS rc_chq,
            dr.acc_id AS pc_acc_id,
            dr.account_name AS pc_account_name, dr.entity_name AS pc_entity_name,
            dr.particulars AS pc_particulars, dr.cash_amt AS pc_cash, dr.chq_amt AS pc_chq
        FROM slots sl
        LEFT JOIN cr_rows cr ON (cr.journal_id = sl.jid OR (cr.journal_id IS NULL AND -cr.id = sl.jid)) AND cr.rn = sl.rn
        LEFT JOIN dr_rows dr ON (dr.journal_id = sl.jid OR (dr.journal_id IS NULL AND -dr.id = sl.jid)) AND dr.rn = sl.rn
    ),
    day_totals AS (
        SELECT row_date,
               SUM(COALESCE(rc_cash,0) + COALESCE(rc_chq,0)) AS day_rc,
               SUM(COALESCE(pc_cash,0) + COALESCE(pc_chq,0)) AS day_pc
        FROM paired GROUP BY row_date
    ),
    running AS (
        SELECT row_date,
               v_opening_balance + SUM(day_rc - day_pc) OVER (ORDER BY row_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS bal
        FROM day_totals
    )
    SELECT
        p.row_date,
        p.rc_acc_id, COALESCE(p.rc_account_name,'')::TEXT, COALESCE(p.rc_entity_name,'')::TEXT, COALESCE(p.rc_particulars,'')::TEXT,
        COALESCE(p.rc_cash,0)::NUMERIC(15,2), COALESCE(p.rc_chq,0)::NUMERIC(15,2),
        p.pc_acc_id, COALESCE(p.pc_account_name,'')::TEXT, COALESCE(p.pc_entity_name,'')::TEXT, COALESCE(p.pc_particulars,'')::TEXT,
        COALESCE(p.pc_cash,0)::NUMERIC(15,2), COALESCE(p.pc_chq,0)::NUMERIC(15,2),
        r.bal::NUMERIC(15,2)
    FROM paired p
    JOIN running r ON r.row_date = p.row_date
    ORDER BY p.row_date;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 13: GATE LOGS
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
            WHEN g.role = 's' THEN COALESCE(ss.name||COALESCE(' ('||ss.shift||')',''), 'Security #'||g.entity_id::TEXT)
            ELSE 'Unknown #'||g.entity_id::TEXT
        END::TEXT,
        g.time_in::TIMESTAMP, g.time_out::TIMESTAMP,
        CASE WHEN g.time_out IS NOT NULL
             THEN EXTRACT(EPOCH FROM (g.time_out - g.time_in))::INT / 60
             ELSE NULL END::INT
    FROM gate_access g
    LEFT JOIN apartments   ap ON ap.id = g.entity_id AND g.role = 'a'
    LEFT JOIN vendors       v ON  v.id = g.entity_id AND g.role = 'v'
    LEFT JOIN users         su ON su.id = g.entity_id AND g.role = 's'
    LEFT JOIN security_staff ss ON ss.id = su.linked_id
    WHERE g.society_id = p_society_id
      AND (p_date   IS NULL OR g.time_in::DATE = p_date)
      AND (p_search IS NULL OR CASE
           WHEN g.role='a' THEN ap.flat_number||' '||COALESCE(ap.owner_name,'')
           WHEN g.role='v' THEN v.name
           WHEN g.role='s' THEN ss.name
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
        a.drcr_account::VARCHAR(2),
        COALESCE(MAX(bf.bf_amount), 0)::NUMERIC(12,2) AS bf_amount,
        (COALESCE(SUM(
            CASE WHEN a.drcr_account = 'Cr' THEN t.amount ELSE -t.amount END
        ), 0) + COALESCE(MAX(bf.bf_amount), 0))::NUMERIC(15,2),
        COUNT(t.id)::INT,
        COALESCE(p.name,'—')::VARCHAR(100)
    FROM accounts a
    LEFT JOIN accounts p ON p.id = a.parent_account_id
    LEFT JOIN transactions t ON t.acc_id = a.id AND t.status = 'paid'
    LEFT JOIN brought_forward bf ON bf.acc_id = a.id AND bf.society_id = a.society_id
                                 AND bf.financial_year = fn_current_financial_year()
    WHERE a.society_id = p_society_id
      AND (p_tab_name IS NULL OR a.tab_name = p_tab_name)
      AND (p_search   IS NULL OR a.name ILIKE '%'||p_search||'%')
    GROUP BY a.id, a.name, a.tab_name, a.header, a.drcr_account, p.name
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
        a.drcr_account::VARCHAR(2),
        COALESCE(MAX(bf.bf_amount), 0)::NUMERIC(12,2),
        a.depreciation_percent::NUMERIC(5,2), a.is_depreciable::BOOLEAN,
        COALESCE(p.name,'—')::VARCHAR(100),
        (COALESCE(SUM(CASE WHEN a.drcr_account='Cr' THEN t.amount ELSE -t.amount END),0)
         + COALESCE(MAX(bf.bf_amount), 0))::NUMERIC(15,2),
        a.created_at::TIMESTAMP
    FROM accounts a
    LEFT JOIN accounts p ON p.id = a.parent_account_id
    LEFT JOIN transactions t ON t.acc_id = a.id AND t.status = 'paid'
    LEFT JOIN brought_forward bf ON bf.acc_id = a.id AND bf.society_id = a.society_id
                                 AND bf.financial_year = fn_current_financial_year()
    WHERE a.id = p_account_id
    GROUP BY a.id, a.society_id, a.name, a.tab_name, a.header, a.drcr_account,
             a.depreciation_percent, a.is_depreciable, p.name, a.created_at;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 15: SOCIETIES LIST / PROFILE
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_societies_list CASCADE;

CREATE OR REPLACE FUNCTION fn_societies_list(
    p_search TEXT    DEFAULT NULL,
    p_plan   VARCHAR DEFAULT NULL,
    p_status VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id INT, name VARCHAR(100), email VARCHAR(100), phone VARCHAR(20),
    pan_number VARCHAR(10), secretary_name VARCHAR(100),
    plan VARCHAR(20), plan_status VARCHAR(10), plan_validity DATE,
    calc_start_date DATE,
    total_apartments INT, total_users INT, total_receivables NUMERIC(15,2),
    created_at TIMESTAMP, secretary_phone VARCHAR(20)
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.id::INT, s.name::VARCHAR(100), s.email::VARCHAR(100), s.phone::VARCHAR(20),
        s.PAN_number::VARCHAR(10), s.secretary_name::VARCHAR(100),
        s.plan::VARCHAR(20),
        CASE WHEN s.plan='Free' THEN 'Free'
             WHEN s.plan_validity >= CURRENT_DATE THEN 'Active'
             ELSE 'Expired' END::VARCHAR(10),
        s.plan_validity::DATE,
        s.calc_start_date::DATE,
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
    PAN_number VARCHAR(10), payment_qr VARCHAR(255),
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
        s.PAN_number::VARCHAR(10), s.payment_qr::VARCHAR(255),
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
-- SECTION 16: EVENTS / CONCERNS
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_events_list CASCADE;

CREATE OR REPLACE FUNCTION fn_events_list(
    p_society_id INT, p_search TEXT DEFAULT NULL, p_status VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id INT, title VARCHAR(200), description TEXT, event_date DATE, event_time VARCHAR(20),
    venue VARCHAR(200), open_to VARCHAR(20), parent_account_id INT,
    ticket_name VARCHAR(20), ticket_price NUMERIC(10,2),
    ticket_name2 VARCHAR(20), ticket_price2 NUMERIC(10,2),
    created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        e.id::INT, e.title::VARCHAR(200), e.description::TEXT, e.event_date::DATE,
        e.event_time::VARCHAR(20), e.venue::VARCHAR(200), e.open_to::VARCHAR(20),
        e.parent_account_id::INT,
        e.ticket_name::VARCHAR(20), e.ticket_price::NUMERIC(10,2),
        e.ticket_name2::VARCHAR(20), e.ticket_price2::NUMERIC(10,2),
        e.created_at::TIMESTAMP
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
    parent_account_id INT,
    ticket_name VARCHAR(20), ticket_price NUMERIC(10,2),
    ticket_name2 VARCHAR(20), ticket_price2 NUMERIC(10,2),
    created_at TIMESTAMP, image TEXT, subtitle TEXT
)
LANGUAGE SQL STABLE AS $$
    SELECT id::INT, society_id::INT, title::VARCHAR(200), description::TEXT,
           event_date::DATE, event_time::VARCHAR(20), venue::VARCHAR(200),
           open_to::VARCHAR(20), parent_account_id::INT,
           ticket_name::VARCHAR(20), ticket_price::NUMERIC(10,2),
           ticket_name2::VARCHAR(20), ticket_price2::NUMERIC(10,2),
           created_at::TIMESTAMP, image::TEXT,
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
    id INT, company_name VARCHAR(100), asset_name VARCHAR(100), asset_sno VARCHAR(50),
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
        ar.company_name::VARCHAR(100),
        ar.asset_name::VARCHAR(100),
        ar.asset_sno::VARCHAR(50),
        ar.purchase_date::DATE,
        ar.purchase_value::NUMERIC(12,2),
        COALESCE(a.name,'—')::VARCHAR(100),
        COALESCE(ar.depreciation_rate, a.depreciation_percent, 100)::NUMERIC(5,2),
        GREATEST(
            ar.purchase_value * (1 - COALESCE(ar.depreciation_rate, a.depreciation_percent, 100) / 100),
            0
        )::NUMERIC(15,2),
        ar.disposed::BOOLEAN,
        ar.disposed_at::DATE,
        ar.sale_value::NUMERIC(12,2),
        ar.created_at::TIMESTAMP
    FROM assets ar
    LEFT JOIN accounts a ON a.id = ar.acc_id
    WHERE ar.society_id = p_society_id
      AND ar.disposed = COALESCE(p_disposed, FALSE)
      AND (p_search IS NULL OR ar.asset_name ILIKE '%'||p_search||'%')
    ORDER BY ar.purchase_date DESC;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 18: VIEWS
-- ════════════════════════════════════════════════════════════════

CREATE OR REPLACE VIEW v_apartment_dues AS
SELECT
    a.id AS apartment_id,
    a.society_id,
    COALESCE(
        SUM(r.amount - r.paid_amount) FILTER (
            WHERE
                r.status IN ('pending', 'partial')
        ),
        0
    ) AS pending_dues,
    COALESCE(
        SUM(r.amount - r.paid_amount) FILTER (
            WHERE
                r.status IN ('pending', 'partial')
                AND r.due_date < CURRENT_DATE
        ),
        0
    ) AS overdue_dues,
    COALESCE(
        SUM(r.amount - r.paid_amount) FILTER (
            WHERE
                r.status IN ('pending', 'partial')
                AND r.due_date < CURRENT_DATE
        ),
        0
    ) <= 0 AS gate_pass,
    COALESCE(
        SUM(r.amount - r.paid_amount) FILTER (
            WHERE
                r.status IN ('pending', 'partial')
        ),
        0
    ) <= 0 AS noc_eligible
FROM
    apartments a
    LEFT JOIN receivables r ON r.entity_id = a.id
    AND r.role = 'apartment'
GROUP BY
    a.id,
    a.society_id;

CREATE OR REPLACE VIEW v_vendor_pass_status AS
SELECT
    u.id AS user_id,
    u.society_id,
    v.id AS vendor_id,
    MAX(vp.valid_until) AS pass_expiry,
    COALESCE(
        MAX(vp.valid_until) >= CURRENT_DATE,
        FALSE
    ) AS gate_pass
FROM
    users u
    LEFT JOIN vendors v ON v.id = u.linked_id
    LEFT JOIN vendor_passes vp ON vp.user_id = u.id
    AND vp.status = 'active'
WHERE
    u.role = 'vendor'
GROUP BY
    u.id,
    u.society_id,
    v.id;

CREATE OR REPLACE VIEW v_security_status AS
SELECT
    u.id AS user_id,
    u.society_id,
    s.id AS security_id,
    COUNT(ga.id) FILTER (
        WHERE
            ga.role = 's'
            AND ga.time_out IS NOT NULL
    ) AS shift_count,
    EXISTS (
        SELECT 1
        FROM gate_access ga2
        WHERE
            ga2.entity_id = u.id
            AND ga2.role = 's'
            AND ga2.time_out IS NULL
    ) AS gate_pass
FROM
    users u
    JOIN security_staff s ON s.id = u.linked_id
    LEFT JOIN gate_access ga ON ga.entity_id = u.id
    AND ga.role = 's'
WHERE
    u.role = 'security'
GROUP BY
    u.id,
    u.society_id,
    s.id;

-- ── v_apartment_data: enriched apartment info ──
CREATE OR REPLACE VIEW v_apartment_data AS
SELECT
    a.id AS apartment_id,
    a.society_id,
    a.flat_number,
    a.owner_name,
    a.mobile,
    a.apartment_size,
    a.active,
    COALESCE(
        SUM(r.amount - r.paid_amount) FILTER (
            WHERE
                r.status IN ('pending', 'partial')
        ),
        0
    ) AS pending_dues,
    COALESCE(
        SUM(r.amount - r.paid_amount) FILTER (
            WHERE
                r.status IN ('pending', 'partial')
                AND r.due_date < CURRENT_DATE
        ),
        0
    ) AS overdue_dues,
    COALESCE(apd.gate_pass, TRUE) AS gate_pass,
    COALESCE(apd.noc_eligible, TRUE) AS noc_eligible,
    (
        SELECT MAX(vp.valid_until)
        FROM
            vendor_passes vp
            JOIN users vu ON vu.id = vp.user_id
            AND vu.role = 'vendor'
        WHERE
            vu.linked_id = a.id
            AND vp.status = 'active'
    ) AS gate_pass_valid_until,
    (
        SELECT COALESCE(
                SUM(r2.amount - r2.paid_amount), 0
            )
        FROM receivables r2
        WHERE
            r2.entity_id = a.id
            AND r2.role = 'apartment'
            AND r2.status = 'credit'
    ) AS advance_credit
FROM
    apartments a
    LEFT JOIN receivables r ON r.entity_id = a.id
    AND r.role = 'apartment'
    LEFT JOIN v_apartment_dues apd ON apd.apartment_id = a.id
GROUP BY
    a.id,
    a.society_id,
    a.flat_number,
    a.owner_name,
    a.mobile,
    a.apartment_size,
    a.active,
    apd.gate_pass,
    apd.noc_eligible;

-- ── v_financial_trial_balance: every account with Dr/Cr split ──
CREATE OR REPLACE VIEW v_financial_trial_balance AS
SELECT
    a.society_id,
    a.id AS account_id,
    a.name AS account_name,
    a.drcr_account,
    a.parent_account_id,
    COALESCE(SUM(t.amount) FILTER (WHERE t.acc_id = a.id AND t.amount > 0 AND a.drcr_account = 'Dr'), 0)::NUMERIC(15,2)
        + COALESCE(MAX(bf.bf_amount), 0) AS dr_total,
    COALESCE(SUM(t.amount) FILTER (WHERE t.acc_id = a.id AND t.amount > 0 AND a.drcr_account = 'Cr'), 0)::NUMERIC(15,2)
        + COALESCE(MAX(bf.bf_amount), 0) AS cr_total,
    (COALESCE(SUM(CASE WHEN a.drcr_account = 'Cr' THEN t.amount ELSE -t.amount END), 0)
        + COALESCE(MAX(bf.bf_amount), 0))::NUMERIC(15,2) AS balance
FROM accounts a
LEFT JOIN transactions t ON t.acc_id = a.id AND t.status = 'paid'
LEFT JOIN brought_forward bf ON bf.acc_id = a.id AND bf.society_id = a.society_id
                             AND bf.financial_year = fn_current_financial_year()
GROUP BY a.society_id, a.id, a.name, a.drcr_account, a.parent_account_id
ORDER BY a.society_id, a.id;

-- ── v_financial_income_expenditure: income & expense accounts ──
CREATE OR REPLACE VIEW v_financial_income_expenditure AS
SELECT
    a.society_id,
    a.id AS account_id,
    a.name AS account_name,
    a.drcr_account,
    COALESCE(SUM(t.amount), 0)::NUMERIC(15,2) AS gross_movement,
    (COALESCE(SUM(CASE WHEN a.drcr_account = 'Cr' THEN t.amount ELSE -t.amount END), 0)
        + COALESCE(MAX(bf.bf_amount), 0))::NUMERIC(15,2) AS net_balance
FROM accounts a
LEFT JOIN transactions t ON t.acc_id = a.id AND t.status = 'paid'
LEFT JOIN brought_forward bf ON bf.acc_id = a.id AND bf.society_id = a.society_id
                             AND bf.financial_year = fn_current_financial_year()
WHERE a.drcr_account IN ('Dr','Cr')
  AND (a.name ILIKE '%Income%' OR a.name ILIKE '%Receipt%'
       OR a.name ILIKE '%Expense%' OR a.name ILIKE '%Salary%'
       OR a.header ILIKE '%Income%' OR a.header ILIKE '%Expense%')
GROUP BY a.society_id, a.id, a.name, a.drcr_account
ORDER BY a.society_id, a.drcr_account, a.name;

-- ── v_financial_balance_sheet: assets, liabilities, capital ──
CREATE OR REPLACE VIEW v_financial_balance_sheet AS
SELECT
    a.society_id,
    a.id AS account_id,
    a.name AS account_name,
    CASE
        WHEN a.name ILIKE '%Asset%' OR a.header ILIKE '%Asset%' THEN 'Assets'
        WHEN a.drcr_account = 'Cr' THEN 'Liabilities & Capital'
        ELSE 'Expenses'
    END AS category,
    (COALESCE(SUM(CASE WHEN a.drcr_account = 'Cr' THEN t.amount ELSE -t.amount END), 0)
        + COALESCE(MAX(bf.bf_amount), 0))::NUMERIC(15,2) AS balance
FROM accounts a
LEFT JOIN transactions t ON t.acc_id = a.id AND t.status = 'paid'
LEFT JOIN brought_forward bf ON bf.acc_id = a.id AND bf.society_id = a.society_id
                             AND bf.financial_year = fn_current_financial_year()
GROUP BY a.society_id, a.id, a.name, a.drcr_account, a.header
HAVING (COALESCE(SUM(CASE WHEN a.drcr_account = 'Cr' THEN t.amount ELSE -t.amount END), 0)
        + COALESCE(MAX(bf.bf_amount), 0)) <> 0
ORDER BY a.society_id, category, a.name;

-- ── v_dashboard_stats: key metrics ──
CREATE OR REPLACE VIEW v_dashboard_stats AS
SELECT
    s.id AS society_id,
    s.name AS society_name,
    (SELECT COALESCE(SUM(r.amount - r.paid_amount), 0)::NUMERIC(15,2)
     FROM receivables r WHERE r.society_id = s.id AND r.status IN ('pending','partial')) AS total_receivables,
    (SELECT COALESCE(SUM(r.amount - r.paid_amount) FILTER (WHERE r.due_date < CURRENT_DATE), 0)::NUMERIC(15,2)
     FROM receivables r WHERE r.society_id = s.id AND r.status IN ('pending','partial')) AS overdue_dues,
    (SELECT COALESCE(SUM(p.amount), 0)::NUMERIC(15,2)
     FROM payables p WHERE p.society_id = s.id AND p.status = 'pending') AS total_payables,
    (SELECT COALESCE(SUM(CASE WHEN a.drcr_account = 'Cr' THEN t.amount ELSE -t.amount END), 0)::NUMERIC(15,2)
     FROM transactions t
     JOIN accounts a ON a.id = t.acc_id
     WHERE t.society_id = s.id AND t.status = 'paid'
       AND (a.name ILIKE '%Cash%' OR a.name ILIKE '%Bank%' OR a.name ILIKE '%SBI%')
     AND a.drcr_account = 'Dr') AS cash_balance,
    (SELECT COUNT(*) FROM apartments ap WHERE ap.society_id = s.id AND ap.active = TRUE) AS total_apartments,
    (SELECT COUNT(*) FROM vendors vd WHERE vd.society_id = s.id) AS total_vendors,
    (SELECT COUNT(*) FROM security_staff ss WHERE ss.society_id = s.id) AS total_security
FROM societies s
ORDER BY s.id;

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
             WHERE accounts.society_id = acf.society_id
               AND name ILIKE '%Society Maintenance Charge%'
             LIMIT 1),
            '—'
        )::TEXT,
        COALESCE(
            (SELECT name FROM accounts
             WHERE accounts.society_id = acf.society_id
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
             WHERE accounts.society_id = vcf.society_id
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

CREATE OR REPLACE FUNCTION get_function_sql(p_function_name TEXT)
RETURNS TEXT AS $$
DECLARE v_sql TEXT;
BEGIN
    SELECT pg_get_functiondef(p.oid) INTO v_sql
    FROM pg_proc p WHERE p.proname = p_function_name LIMIT 1;
    RETURN COALESCE(v_sql, 'Function not found: '||p_function_name);
END;
$$ LANGUAGE plpgsql;

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

-- ════════════════════════════════════════════════════════════════
-- SECTION 21: REPORTING FUNCTIONS
-- ════════════════════════════════════════════════════════════════

-- Trial balance: all accounts with current Dr/Cr balances.
DROP FUNCTION IF EXISTS fn_trial_balance (INT, TEXT) CASCADE;

CREATE OR REPLACE FUNCTION fn_trial_balance(p_society_id INT, p_search TEXT DEFAULT NULL)
RETURNS TABLE (
    account_id INT, account_name VARCHAR(100), drcr_account VARCHAR(2),
    dr_balance NUMERIC(15,2), cr_balance NUMERIC(15,2), net_balance NUMERIC(15,2)
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        a.id::INT,
        a.name::VARCHAR(100),
        a.drcr_account::VARCHAR(2),
        CASE WHEN a.drcr_account = 'Dr'
             THEN (COALESCE(SUM(t.amount),0) + COALESCE(MAX(bf.bf_amount),0))::NUMERIC(15,2)
             ELSE 0::NUMERIC(15,2) END AS dr_balance,
        CASE WHEN a.drcr_account = 'Cr'
             THEN (COALESCE(SUM(t.amount),0) + COALESCE(MAX(bf.bf_amount),0))::NUMERIC(15,2)
             ELSE 0::NUMERIC(15,2) END AS cr_balance,
        (COALESCE(SUM(CASE WHEN a.drcr_account='Cr' THEN t.amount ELSE -t.amount END),0)
            + COALESCE(MAX(bf.bf_amount),0))::NUMERIC(15,2) AS net_balance
    FROM accounts a
    LEFT JOIN transactions t ON t.acc_id = a.id AND t.status = 'paid'
    LEFT JOIN brought_forward bf ON bf.acc_id = a.id AND bf.society_id = a.society_id
                                 AND bf.financial_year = fn_current_financial_year()
    WHERE a.society_id = p_society_id
      AND (p_search IS NULL OR a.name ILIKE '%'||p_search||'%')
    GROUP BY a.id, a.name, a.drcr_account
    ORDER BY a.drcr_account, a.name;
END;
$$;

-- Income & expenditure over a date range.
DROP FUNCTION IF EXISTS fn_income_expenditure (INT, DATE, DATE) CASCADE;

CREATE OR REPLACE FUNCTION fn_income_expenditure(
    p_society_id INT,
    p_start_date DATE DEFAULT NULL,
    p_end_date   DATE DEFAULT NULL
)
RETURNS TABLE (
    account_id INT, account_name VARCHAR(100), drcr_account VARCHAR(2),
    total NUMERIC(15,2)
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        a.id::INT,
        a.name::VARCHAR(100),
        a.drcr_account::VARCHAR(2),
        COALESCE(SUM(t.amount),0)::NUMERIC(15,2) AS total
    FROM accounts a
    LEFT JOIN transactions t ON t.acc_id = a.id AND t.status = 'paid'
        AND (p_start_date IS NULL OR t.trx_date >= p_start_date)
        AND (p_end_date   IS NULL OR t.trx_date <= p_end_date)
    WHERE a.society_id = p_society_id
      AND a.drcr_account IN ('Dr','Cr')
    GROUP BY a.id, a.name, a.drcr_account
    ORDER BY a.drcr_account DESC, a.name;
END;
$$;

-- Balance sheet as of a date.
DROP FUNCTION IF EXISTS fn_balance_sheet (INT, DATE) CASCADE;

CREATE OR REPLACE FUNCTION fn_balance_sheet(
    p_society_id INT,
    p_as_of      DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    account_id INT, account_name VARCHAR(100), category VARCHAR(30),
    balance NUMERIC(15,2)
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        a.id::INT,
        a.name::VARCHAR(100),
        CASE
            WHEN a.name ILIKE '%Asset%' OR a.header ILIKE '%Asset%' THEN 'Assets'
            WHEN a.drcr_account = 'Cr' THEN 'Liabilities & Capital'
            ELSE 'Expenses'
        END::VARCHAR(30),
        (COALESCE(SUM(CASE WHEN a.drcr_account='Cr' THEN t.amount ELSE -t.amount END),0)
            + COALESCE(MAX(bf.bf_amount),0))::NUMERIC(15,2)
    FROM accounts a
    LEFT JOIN transactions t ON t.acc_id = a.id AND t.status = 'paid'
        AND t.trx_date <= p_as_of
    LEFT JOIN brought_forward bf ON bf.acc_id = a.id AND bf.society_id = a.society_id
                                 AND bf.financial_year = (EXTRACT(YEAR FROM p_as_of)::SMALLINT
                                     - CASE WHEN EXTRACT(MONTH FROM p_as_of) < 4 THEN 1 ELSE 0 END)
    WHERE a.society_id = p_society_id
    GROUP BY a.id, a.name, a.drcr_account, a.header
    ORDER BY category, a.name;
END;
$$;

-- Dashboard stats for a society.
DROP FUNCTION IF EXISTS fn_dashboard_stats (INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_dashboard_stats(p_society_id INT)
RETURNS TABLE (
    total_receivables NUMERIC(15,2),
    overdue_dues NUMERIC(15,2),
    total_payables NUMERIC(15,2),
    cash_balance NUMERIC(15,2),
    total_apartments INT,
    total_vendors INT,
    total_security INT,
    total_transactions BIGINT
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_cash_acc_ids INT[];
BEGIN
    SELECT ARRAY_AGG(id) INTO v_cash_acc_ids
    FROM accounts
    WHERE society_id = p_society_id
      AND drcr_account = 'Dr'
      AND (name ILIKE '%Cash%' OR name ILIKE '%Bank%' OR name ILIKE '%SBI%');

    RETURN QUERY
    SELECT
        (SELECT COALESCE(SUM(r.amount - r.paid_amount), 0)::NUMERIC(15,2)
         FROM receivables r WHERE r.society_id = p_society_id AND r.status IN ('pending','partial'))
            AS total_receivables,
        (SELECT COALESCE(SUM(r.amount - r.paid_amount) FILTER (WHERE r.due_date < CURRENT_DATE), 0)::NUMERIC(15,2)
         FROM receivables r WHERE r.society_id = p_society_id AND r.status IN ('pending','partial'))
            AS overdue_dues,
        (SELECT COALESCE(SUM(p.amount), 0)::NUMERIC(15,2)
         FROM payables p WHERE p.society_id = p_society_id AND p.status = 'pending')
            AS total_payables,
        (SELECT COALESCE(SUM(CASE WHEN a.drcr_account='Cr' THEN t.amount ELSE -t.amount END), 0)::NUMERIC(15,2)
         FROM transactions t JOIN accounts a ON a.id = t.acc_id
         WHERE t.society_id = p_society_id AND t.status = 'paid'
           AND a.id = ANY(v_cash_acc_ids))
            AS cash_balance,
        (SELECT COUNT(*)::INT FROM apartments ap WHERE ap.society_id = p_society_id AND ap.active = TRUE)
            AS total_apartments,
        (SELECT COUNT(*)::INT FROM vendors vd WHERE vd.society_id = p_society_id)
            AS total_vendors,
        (SELECT COUNT(*)::INT FROM security_staff ss WHERE ss.society_id = p_society_id)
            AS total_security,
        (SELECT COUNT(*)::BIGINT FROM transactions t WHERE t.society_id = p_society_id AND t.status = 'paid')
            AS total_transactions;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 22: VENDOR LEDGER
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_vendor_ledger (INT, INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_vendor_ledger(p_society_id INT, p_vendor_id INT)
RETURNS TABLE (
    ledger_type VARCHAR(20),
    ref_id INT,
    trx_date DATE,
    particulars TEXT,
    debit NUMERIC(15,2),
    credit NUMERIC(15,2),
    balance NUMERIC(15,2)
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_running NUMERIC(15,2) := 0;
    rec RECORD;
BEGIN
    FOR rec IN
        -- Bills (payables) = vendor is owed → debit
        SELECT 'bill'::VARCHAR(20) AS ledger_type, p.id AS ref_id, p.shift_date AS trx_date,
               p.description AS particulars, p.amount AS debit, 0::NUMERIC(15,2) AS credit
        FROM payables p
        WHERE p.society_id = p_society_id AND p.entity_id = p_vendor_id AND p.role = 'vendor'
          AND p.status IN ('pending','verified')
        UNION ALL
        -- Payments made to vendor (expenses) = vendor paid → credit
        SELECT 'payment'::VARCHAR(20), e.id, e.expense_date, e.particulars,
               0::NUMERIC(15,2) AS debit, e.amount AS credit
        FROM expenses e
        WHERE e.society_id = p_society_id AND e.entity_id = p_vendor_id AND e.role = 'vendor'
          AND e.status = 'confirmed'
        UNION ALL
        -- Pass-sale receipts tied to the vendor (credit to society, but tracked here as vendor activity)
        SELECT 'receipt'::VARCHAR(20), r.id, r.receipt_date, r.particulars,
               0::NUMERIC(15,2) AS debit, r.amount AS credit
        FROM receipts r
        WHERE r.society_id = p_society_id AND r.entity_id = p_vendor_id AND r.role = 'vendor'
          AND r.status = 'confirmed'
        ORDER BY trx_date ASC, ref_id ASC
    LOOP
        v_running := v_running + rec.debit - rec.credit;
        ledger_type := rec.ledger_type;
        ref_id := rec.ref_id;
        trx_date := rec.trx_date;
        particulars := rec.particulars;
        debit := rec.debit;
        credit := rec.credit;
        balance := v_running;
        RETURN NEXT;
    END LOOP;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 23: DATA INTEGRITY VALIDATION FUNCTIONS
-- Each returns zero or more problem rows describing the anomaly.
-- ════════════════════════════════════════════════════════════════

-- Apartments with no owning user row (orphan apartments).
DROP FUNCTION IF EXISTS fn_check_orphan_apartments (INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_check_orphan_apartments(p_society_id INT)
RETURNS TABLE (apartment_id INT, flat_number VARCHAR(20), issue TEXT) LANGUAGE SQL STABLE AS $$
    SELECT a.id, a.flat_number, 'No linked apartment user account'::TEXT
    FROM apartments a
    WHERE a.society_id = p_society_id
      AND NOT EXISTS (
        SELECT 1 FROM users u
        WHERE u.linked_id = a.id AND u.society_id = p_society_id AND u.role = 'apartment'
      );
$$;

-- Ledger entries (transactions) referencing accounts/users that no longer exist.
DROP FUNCTION IF EXISTS fn_check_orphan_ledger_entries (INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_check_orphan_ledger_entries(p_society_id INT)
RETURNS TABLE (transaction_id INT, issue TEXT) LANGUAGE SQL STABLE AS $$
    SELECT t.id, 'Transaction references missing account'::TEXT
    FROM transactions t
    WHERE t.society_id = p_society_id
      AND t.acc_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM accounts a WHERE a.id = t.acc_id)
    UNION ALL
    SELECT t.id, 'Transaction references missing created_by user'::TEXT
    FROM transactions t
    WHERE t.society_id = p_society_id
      AND t.created_by IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id = t.created_by);
$$;

-- Receipts whose acc_id (income account) no longer exists.
DROP FUNCTION IF EXISTS fn_check_orphan_receipts (INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_check_orphan_receipts(p_society_id INT)
RETURNS TABLE (receipt_id INT, issue TEXT) LANGUAGE SQL STABLE AS $$
    SELECT r.id, 'Receipt references missing income account'::TEXT
    FROM receipts r
    WHERE r.society_id = p_society_id
      AND r.acc_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM accounts a WHERE a.id = r.acc_id);
$$;

-- Vendors with no linked user account.
DROP FUNCTION IF EXISTS fn_check_orphan_vendors (INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_check_orphan_vendors(p_society_id INT)
RETURNS TABLE (vendor_id INT, business_name VARCHAR(100), issue TEXT) LANGUAGE SQL STABLE AS $$
    SELECT v.id, v.business_name, 'No linked vendor user account'::TEXT
    FROM vendors v
    WHERE v.society_id = p_society_id
      AND NOT EXISTS (
        SELECT 1 FROM users u
        WHERE u.linked_id = v.id AND u.society_id = p_society_id AND u.role = 'vendor'
      );
$$;

-- Receivables pointing at a missing apartment/vendor/security entity.
DROP FUNCTION IF EXISTS fn_check_orphan_receivables (INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_check_orphan_receivables(p_society_id INT)
RETURNS TABLE (receivable_id INT, role VARCHAR(20), entity_id INT, issue TEXT) LANGUAGE SQL STABLE AS $$
    SELECT r.id, r.role, r.entity_id, 'Receivable references missing entity'::TEXT
    FROM receivables r
    WHERE r.society_id = p_society_id
      AND r.role = 'apartment'
      AND NOT EXISTS (SELECT 1 FROM apartments a WHERE a.id = r.entity_id)
    UNION ALL
    SELECT r.id, r.role, r.entity_id, 'Receivable references missing vendor'::TEXT
    FROM receivables r
    WHERE r.society_id = p_society_id
      AND r.role = 'vendor'
      AND NOT EXISTS (SELECT 1 FROM vendors v WHERE v.id = r.entity_id)
    UNION ALL
    SELECT r.id, r.role, r.entity_id, 'Receivable references missing security staff'::TEXT
    FROM receivables r
    WHERE r.society_id = p_society_id
      AND r.role = 'security'
      AND NOT EXISTS (SELECT 1 FROM security_staff s WHERE s.id = r.entity_id);
$$;

-- Duplicate receivable rows for the same entity/role/period_month.
DROP FUNCTION IF EXISTS fn_check_duplicate_receivables (INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_check_duplicate_receivables(p_society_id INT)
RETURNS TABLE (entity_id INT, role VARCHAR(20), period_month DATE, dup_count BIGINT, issue TEXT) LANGUAGE SQL STABLE AS $$
    SELECT r.entity_id, r.role, r.period_month, COUNT(*) AS dup_count,
           'Multiple receivables for same entity/role/period'::TEXT
    FROM receivables r
    WHERE r.society_id = p_society_id AND r.period_month IS NOT NULL
    GROUP BY r.entity_id, r.role, r.period_month
    HAVING COUNT(*) > 1;
$$;

-- Journal ids that do not have exactly one Dr and one Cr line (unbalanced).
DROP FUNCTION IF EXISTS fn_check_duplicate_journals (INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_check_duplicate_journals(p_society_id INT)
RETURNS TABLE (journal_id INT, dr_count BIGINT, cr_count BIGINT, dr_sum NUMERIC(15,2), cr_sum NUMERIC(15,2), issue TEXT) LANGUAGE SQL STABLE AS $$
    SELECT t.journal_id,
           COUNT(*) FILTER (WHERE a.drcr_account = 'Dr') AS dr_count,
           COUNT(*) FILTER (WHERE a.drcr_account = 'Cr') AS cr_count,
           COALESCE(SUM(t.amount) FILTER (WHERE a.drcr_account = 'Dr'),0)::NUMERIC(15,2) AS dr_sum,
           COALESCE(SUM(t.amount) FILTER (WHERE a.drcr_account = 'Cr'),0)::NUMERIC(15,2) AS cr_sum,
           'Unbalanced journal (Dr != Cr)'::TEXT
    FROM transactions t
    JOIN accounts a ON a.id = t.acc_id
    WHERE t.society_id = p_society_id AND t.journal_id IS NOT NULL AND t.status = 'paid'
    GROUP BY t.journal_id
    HAVING COUNT(*) FILTER (WHERE a.drcr_account = 'Dr') <> 1
        OR COUNT(*) FILTER (WHERE a.drcr_account = 'Cr') <> 1
        OR COALESCE(SUM(t.amount) FILTER (WHERE a.drcr_account = 'Dr'),0)
           <> COALESCE(SUM(t.amount) FILTER (WHERE a.drcr_account = 'Cr'),0);
$$;

-- Broken foreign keys across the major tables.
DROP FUNCTION IF EXISTS fn_check_broken_fks (INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_check_broken_fks(p_society_id INT)
RETURNS TABLE (table_name TEXT, row_id INT, column_name TEXT, issue TEXT) LANGUAGE SQL STABLE AS $$
    SELECT 'receivables'::TEXT, r.id, 'acc_id'::TEXT, 'Missing account FK'::TEXT
    FROM receivables r
    WHERE r.society_id = p_society_id AND r.acc_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM accounts a WHERE a.id = r.acc_id)
    UNION ALL
    SELECT 'expenses'::TEXT, e.id, 'acc_id'::TEXT, 'Missing account FK'::TEXT
    FROM expenses e
    WHERE e.society_id = p_society_id AND e.acc_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM accounts a WHERE a.id = e.acc_id)
    UNION ALL
    SELECT 'payables'::TEXT, p.id, 'acc_id'::TEXT, 'Missing account FK'::TEXT
    FROM payables p
    WHERE p.society_id = p_society_id AND p.acc_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM accounts a WHERE a.id = p.acc_id)
    UNION ALL
    SELECT 'assets'::TEXT, ar.id, 'acc_id'::TEXT, 'Missing asset-class account FK'::TEXT
    FROM assets ar
    WHERE ar.society_id = p_society_id AND ar.acc_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM accounts a WHERE a.id = ar.acc_id)
    UNION ALL
    SELECT 'security_roster'::TEXT, sr.id, 'security_id'::TEXT, 'Missing security staff FK'::TEXT
    FROM security_roster sr
    WHERE sr.society_id = p_society_id
      AND NOT EXISTS (SELECT 1 FROM security_staff ss WHERE ss.id = sr.security_id)
    UNION ALL
    SELECT 'gate_access'::TEXT, g.id, 'entity_id'::TEXT, 'Missing user FK for gate_access'::TEXT
    FROM gate_access g
    WHERE g.society_id = p_society_id AND g.role = 's'
      AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id = g.entity_id);
$$;

-- ============================================================
-- SECTION 21: LEDGER FUNCTIONS
-- ============================================================

-- Year-end close: compute each has_bf account's closing balance as of
-- 31-Mar of p_financial_year, and write it as the OPENING balance for
-- p_financial_year + 1. p_overwrite=FALSE (default) never touches a row
-- that already exists — protects manual admin overrides. Pass TRUE to
-- force a recompute.
DROP FUNCTION IF EXISTS fn_close_financial_year (INT, SMALLINT, BOOLEAN) CASCADE;

CREATE OR REPLACE FUNCTION fn_close_financial_year(
    p_society_id     INT,
    p_financial_year SMALLINT,
    p_overwrite      BOOLEAN DEFAULT FALSE
)
RETURNS INT LANGUAGE plpgsql AS $$
DECLARE
    v_fy_end   DATE := MAKE_DATE(p_financial_year + 1, 3, 31);
    v_count    INT := 0;
    rec        RECORD;
    v_closing  NUMERIC(15,2);
    v_drcr     VARCHAR(2);
BEGIN
    FOR rec IN
        SELECT a.id AS acc_id, a.drcr_account
        FROM accounts a
        WHERE a.society_id = p_society_id AND a.has_bf = TRUE
    LOOP
        -- Closing balance = opening BF for THIS fy + net movement during it
        SELECT
            fn_resolve_bf_amount_fy(p_society_id, rec.acc_id, p_financial_year)
            + COALESCE(SUM(CASE WHEN rec.drcr_account = 'Cr' THEN
                              CASE WHEN a2.drcr_account = 'Cr' THEN t.amount ELSE -t.amount END
                          ELSE
                              CASE WHEN a2.drcr_account = 'Dr' THEN t.amount ELSE -t.amount END
                          END), 0)
        INTO v_closing
        FROM transactions t
        JOIN accounts a2 ON a2.id = t.acc_id
        WHERE t.acc_id = rec.acc_id
          AND t.society_id = p_society_id
          AND t.status = 'paid'
          AND t.trx_date BETWEEN MAKE_DATE(p_financial_year, 4, 1) AND v_fy_end;
 
        v_drcr := CASE WHEN v_closing < 0 THEN
                        CASE WHEN rec.drcr_account = 'Dr' THEN 'Cr' ELSE 'Dr' END
                   ELSE rec.drcr_account END;
 
        INSERT INTO brought_forward (
            society_id, financial_year, acc_id, drcr_bf, bf_amount,
            is_auto_calculated, remarks, created_at
        ) VALUES (
            p_society_id, p_financial_year + 1, rec.acc_id, v_drcr, ABS(v_closing),
            TRUE, 'Auto-calculated at year-end close of FY' || p_financial_year, NOW()
        )
        ON CONFLICT (society_id, financial_year, acc_id) DO UPDATE
            SET drcr_bf = EXCLUDED.drcr_bf,
                bf_amount = EXCLUDED.bf_amount,
                is_auto_calculated = TRUE,
                updated_at = NOW()
            WHERE p_overwrite = TRUE AND brought_forward.is_auto_calculated = TRUE;
            -- Never overwrites a row an admin hand-edited (is_auto_calculated=FALSE),
            -- even with p_overwrite=TRUE.
 
        v_count := v_count + 1;
    END LOOP;
 
    RETURN v_count;
END;
$$;

-- ═══════════════════════════════════════════════════════════════════════════════
-- DOCUMENTATION: clarify receipts.user_id's dual role
-- ═══════════════════════════════════════════════════════════════════════════════
-- receipts.user_id is semantically "created_by" / "recorded_by" — the user
-- who entered the receipt (an admin entering it directly, or security/an
-- apartment owner submitting one that lands as status='pending'). It is
-- NOT who verified/approved it — that's confirmed_by, set separately by
-- fn_verify_receipt when an admin confirms a pending receipt. Left as
-- `user_id` rather than renamed to `created_by`, since dozens of existing
-- call sites (fn_save_receipt, fn_verify_receipt,
-- every receipts list/report query) already depend on this exact name;
-- renaming has no functional upside and meaningful regression risk.
COMMENT ON COLUMN receipts.user_id IS 'User who recorded/submitted this receipt (creator), NOT who verified it — see confirmed_by.';

-- ═══════════════════════════════════════════════════════════════════════════════
-- MIGRATION: add created_by columns missing from initial schema
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER TABLE societies
ADD COLUMN IF NOT EXISTS created_by INT REFERENCES users (id);

ALTER TABLE users
ADD COLUMN IF NOT EXISTS created_by INT REFERENCES users (id);

ALTER TABLE accounts
ADD COLUMN IF NOT EXISTS created_by INT REFERENCES users (id);

ALTER TABLE security_roster
ADD COLUMN IF NOT EXISTS created_by INT REFERENCES users (id);

ALTER TABLE receivables
ADD COLUMN IF NOT EXISTS created_by INT REFERENCES users (id);

ALTER TABLE receipts
ADD COLUMN IF NOT EXISTS created_by INT REFERENCES users (id);

ALTER TABLE expenses
ADD COLUMN IF NOT EXISTS created_by INT REFERENCES users (id);

ALTER TABLE payables
ADD COLUMN IF NOT EXISTS created_by INT REFERENCES users (id);

ALTER TABLE vendor_passes
ADD COLUMN IF NOT EXISTS created_by INT REFERENCES users (id);

ALTER TABLE apt_charges_fines_basis
ADD COLUMN IF NOT EXISTS created_by INT REFERENCES users (id);

ALTER TABLE ven_charges_fines_basis
ADD COLUMN IF NOT EXISTS created_by INT REFERENCES users (id);

-- MIGRATION: split event_tickets.quantity into quantity_adult + quantity_child
ALTER TABLE event_tickets DROP COLUMN IF EXISTS quantity;
ALTER TABLE event_tickets ADD COLUMN IF NOT EXISTS quantity_adult INT NOT NULL DEFAULT 0 CHECK (quantity_adult >= 0);
ALTER TABLE event_tickets ADD COLUMN IF NOT EXISTS quantity_child INT NOT NULL DEFAULT 0 CHECK (quantity_child >= 0);

-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 2E: AUDITOR VERIFICATION — Parallel (society_id, acc_id) SHA256 chains
-- ═══════════════════════════════════════════════════════════════════════════════

-- Verify a single confirmed receipt's hash and chain link.
DROP FUNCTION IF EXISTS fn_verify_receipt_chain (INT, INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_verify_receipt_chain(
    p_society_id INT,
    p_acc_id     INT
) RETURNS TABLE(
    chain_position  INT,
    receipt_id      INT,
    receipt_number  VARCHAR(64),
    is_valid        BOOLEAN,
    break_reason    TEXT
) LANGUAGE plpgsql AS $$
DECLARE
    r           RECORD;
    v_prev_hash  VARCHAR(64);
    v_chain_seed VARCHAR(64);
    v_expected   VARCHAR(64);
    v_pos        INT := 0;
    v_entity_name TEXT;
BEGIN
    v_chain_seed := ENCODE(DIGEST(
        p_society_id::TEXT || '|' || COALESCE(p_acc_id::TEXT,'0') || '|' || 'APEX_RECEIPT_V1',
        'sha256'), 'hex');
    v_prev_hash := v_chain_seed;

    FOR r IN
        SELECT id, receipt_number, previous_hash,
               society_id, acc_id, amount, confirmed_at,
               entity_id, role, particulars, mode, receipt_date,
               source_reference
          FROM receipts
         WHERE society_id = p_society_id
           AND acc_id = p_acc_id
           AND status = 'confirmed'
           AND receipt_number IS NOT NULL
         ORDER BY confirmed_at ASC, id ASC
    LOOP
        v_pos := v_pos + 1;

        -- Verify chain pointer
        IF r.previous_hash IS DISTINCT FROM v_prev_hash THEN
            is_valid := FALSE;
            break_reason := FORMAT('Broken chain link at receipt %s (id=%s): expected previous_hash=%s, stored=%s',
                                   r.receipt_number, r.id, v_prev_hash, r.previous_hash);
            chain_position := v_pos;
            receipt_id := r.id;
            receipt_number := r.receipt_number;
            RETURN NEXT;
            RETURN;
        END IF;

        -- Resolve entity_name for deterministic hash
        IF r.role = 'apartment' THEN
            SELECT COALESCE(flat_number || ' - ' || COALESCE(owner_name,''), '') INTO v_entity_name
              FROM apartments WHERE id = r.entity_id;
        ELSIF r.role = 'vendor' THEN
            SELECT COALESCE(name,'') INTO v_entity_name FROM vendors WHERE id = r.entity_id;
        ELSIF r.role = 'security' THEN
            SELECT COALESCE(name,'') INTO v_entity_name FROM security_staff WHERE id = r.entity_id;
        ELSE
            v_entity_name := COALESCE(r.entity_id::TEXT, '');
        END IF;

        -- Recompute expected hash
        v_expected := fn_compute_receipt_hash(
            r.society_id::TEXT,
            COALESCE(r.acc_id::TEXT,      '0'),
            COALESCE(r.amount::TEXT,      '0'),
            COALESCE(TO_CHAR(r.confirmed_at,'YYYY-MM-DD HH24:MI:SS.US'), ''),
            COALESCE(r.entity_id::TEXT,   ''),
            COALESCE(r.role,              ''),
            COALESCE(r.particulars,       ''),
            COALESCE(r.mode,              ''),
            COALESCE(r.receipt_date::TEXT,''),
            COALESCE(v_entity_name,       ''),
            r.previous_hash,
            COALESCE(r.source_reference,  '')
        );

        IF v_expected IS DISTINCT FROM r.receipt_number THEN
            is_valid := FALSE;
            break_reason := FORMAT('Tampered receipt %s (id=%s): stored=%s, computed=%s',
                                   r.receipt_number, r.id, r.receipt_number, v_expected);
            chain_position := v_pos;
            receipt_id := r.id;
            receipt_number := r.receipt_number;
            RETURN NEXT;
            RETURN;
        END IF;

        v_prev_hash := r.receipt_number;
        is_valid := TRUE;
        break_reason := NULL;
        chain_position := v_pos;
        receipt_id := r.id;
        receipt_number := r.receipt_number;
        RETURN NEXT;
    END LOOP;
END;
$$;

-- Verify ALL parallel chains for a society.
DROP FUNCTION IF EXISTS fn_verify_all_receipt_chains (INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_verify_all_receipt_chains(p_society_id INT)
RETURNS TABLE(
    account_id    INT,
    account_name  TEXT,
    receipt_count INT,
    is_valid      BOOLEAN,
    break_point   TEXT
) LANGUAGE plpgsql AS $$
DECLARE
    r           RECORD;
    v           RECORD;
    v_break     TEXT;
BEGIN
    FOR r IN
        SELECT DISTINCT acc_id FROM receipts
         WHERE society_id = p_society_id AND status = 'confirmed' AND receipt_number IS NOT NULL
    LOOP
        SELECT COUNT(*) INTO receipt_count FROM receipts
         WHERE society_id = p_society_id AND acc_id = r.acc_id
           AND status = 'confirmed' AND receipt_number IS NOT NULL;

        SELECT a.name INTO account_name FROM accounts a WHERE a.id = r.acc_id;
        account_id := r.acc_id;

        is_valid := TRUE;
        break_point := NULL;

        FOR v IN SELECT * FROM fn_verify_receipt_chain(p_society_id, r.acc_id) LOOP
            IF NOT v.is_valid THEN
                is_valid := FALSE;
                break_point := v.break_reason;
                EXIT;
            END IF;
        END LOOP;

        RETURN NEXT;
    END LOOP;
END;
$$;

-- Reconcile receipts in a chain (society, acc_id) against their transaction lines.
DROP FUNCTION IF EXISTS fn_reconcile_receipt_chain (INT, INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_reconcile_receipt_chain(
    p_society_id INT,
    p_acc_id     INT
) RETURNS TABLE(
    receipt_id        INT,
    receipt_number    VARCHAR(64),
    receipt_amount    NUMERIC(15,2),
    receipt_status    VARCHAR(20),
    transaction_count INT,
    transaction_total NUMERIC(15,2),
    match             BOOLEAN,
    discrepancy       NUMERIC(15,2)
) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        r.id::INT,
        r.receipt_number::VARCHAR(64),
        r.amount::NUMERIC(15,2),
        r.status::VARCHAR(20),
        COUNT(t.id)::INT,
        COALESCE(SUM(t.amount), 0)::NUMERIC(15,2),
        (r.status = 'confirmed' AND COUNT(t.id) >= 2
         AND COALESCE(SUM(t.amount), 0) = r.amount * 2)::BOOLEAN,
        (COALESCE(SUM(t.amount), 0) - r.amount * 2)::NUMERIC(15,2)
    FROM receipts r
    LEFT JOIN transactions t ON t.source_table = 'receipts' AND t.source_id = r.id
    WHERE r.society_id = p_society_id
      AND r.acc_id = p_acc_id
    GROUP BY r.id, r.receipt_number, r.amount, r.status
    ORDER BY r.confirmed_at ASC, r.id ASC;
END;
$$;

-- Auditor helper: full integrity report for one (society, acc_id) chain.
DROP FUNCTION IF EXISTS fn_audit_receipt_chain (INT, INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_audit_receipt_chain(
    p_society_id INT,
    p_acc_id     INT
) RETURNS TABLE(
    check_name   TEXT,
    passed       BOOLEAN,
    details      TEXT
) LANGUAGE plpgsql AS $$
DECLARE
    v           RECORD;
    v_count     INT;
    v_break     TEXT;
BEGIN
    -- 1. Chain hash integrity
    FOR v IN SELECT * FROM fn_verify_receipt_chain(p_society_id, p_acc_id) LOOP
        IF NOT v.is_valid THEN
            check_name := 'chain_integrity';
            passed := FALSE;
            details := FORMAT('FAIL at %s: %s', v.receipt_number, v.break_reason);
            RETURN NEXT;
            RETURN;
        END IF;
    END LOOP;

    SELECT COUNT(*) INTO v_count FROM receipts
     WHERE society_id = p_society_id AND acc_id = p_acc_id AND status = 'confirmed';
    check_name := 'chain_integrity';
    passed := TRUE;
    details := FORMAT('OK: %d confirmed receipts verified', v_count);
    RETURN NEXT;

    -- 2. Double-entry reconciliation
    FOR v IN SELECT * FROM fn_reconcile_receipt_chain(p_society_id, p_acc_id)
             WHERE NOT match LOOP
        check_name := 'double_entry';
        passed := FALSE;
        details := FORMAT('Mismatch receipt %s: expected txn total=%s, actual=%s',
                          v.receipt_number, v.receipt_amount * 2, v.transaction_total);
        RETURN NEXT;
        RETURN;
    END LOOP;

    check_name := 'double_entry';
    passed := TRUE;
    details := 'OK: all confirmed receipts have matching double-entry transactions';
    RETURN NEXT;

    -- 3. Sequential confirmed_at check (no back-dated confirms after newer ones)
    SELECT COUNT(*) INTO v_count FROM receipts r1
     WHERE r1.society_id = p_society_id AND r1.acc_id = p_acc_id AND r1.status = 'confirmed'
       AND EXISTS (
           SELECT 1 FROM receipts r2
           WHERE r2.society_id = r1.society_id AND r2.acc_id = r1.acc_id
             AND r2.status = 'confirmed'
             AND r2.confirmed_at > r1.confirmed_at
             AND r2.id < r1.id
       );

    IF v_count > 0 THEN
        check_name := 'temporal_order';
        passed := FALSE;
        details := FORMAT('FAIL: %d receipts confirmed out of chronological order', v_count);
    ELSE
        check_name := 'temporal_order';
        passed := TRUE;
        details := 'OK: all receipts confirmed in chronological order';
    END IF;
    RETURN NEXT;
END;
$$;