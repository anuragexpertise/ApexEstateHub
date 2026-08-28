-- ============================================================
-- ESTATEHUB - COMPLETE DATABASE SCHEMA & FUNCTIONS (v3 - CORRECTED)
-- Reorganized: TYPE -> TABLES -> INDEXES -> FUNCTIONS -> VIEWS -> TRIGGERS
-- ============================================================

-- ════════════════════════════════════════════════════════════════
-- SECTION 0: TYPES
-- ════════════════════════════════════════════════════════════════

-- (No custom ENUM/DOMAIN types in this schema)

-- ════════════════════════════════════════════════════════════════
-- SECTION 1: TABLES
-- ════════════════════════════════════════════════════════════════

-- ════════════════════════════════════════════════════════════════
-- SECTION 1: CORE SCHEMA
-- ════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS societies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    PAN_number VARCHAR(10),
    logo VARCHAR(100),
    address TEXT,
    email VARCHAR(30),
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
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INT,
    gstin VARCHAR(15)
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    email VARCHAR(30) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    pin_hash TEXT,
    pattern_hash TEXT,
    name VARCHAR(100),
    role VARCHAR(10) NOT NULL CHECK (
        role IN (
            'admin',
            'apartment',
            'vendor',
            'security'
        )
    ),
    linked_id INT,
    -- Fallback qr_version for admin logins with no apartments row to key
    -- off (linked_id IS NULL — the seeded first-admin case). A promoted
    -- apartment owner (linked_id = apartments.id) uses apartments.qr_version
    -- instead; this column is only ever consulted when linked_id is NULL.
    -- See app/services/qr_service.py _current_qr_version's ADM branch.
    qr_version INT NOT NULL DEFAULT 1,
    login_method VARCHAR(20) DEFAULT 'password',
    -- push_subscription is DEPRECATED; use push_subscriptions table instead.
    -- Kept here for migration compatibility only.
    push_subscription TEXT,
    is_master_admin BOOLEAN NOT NULL DEFAULT FALSE,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMP,
    reset_token VARCHAR(64),
    reset_token_expires TIMESTAMP,
    push_token TEXT,
    push_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    last_login TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INT REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    endpoint TEXT NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    user_agent TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id, endpoint)
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
    depreciation_percent NUMERIC(5, 2) DEFAULT 100.00,
    is_depreciable BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    created_by INT REFERENCES users (id),
    updated_at TIMESTAMP,
    updated_by INT REFERENCES users (id),
    CONSTRAINT uq_account_society_name UNIQUE (society_id, name),
    CONSTRAINT fk_account_parent FOREIGN KEY (parent_account_id) REFERENCES accounts (id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED
,
    mutuality_nature VARCHAR(10) CHECK (mutuality_nature IN ('mutual','non_mutual')) DEFAULT 'mutual',
    tds_section VARCHAR(10)
);

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
    qr_version INT NOT NULL DEFAULT 1,
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
    service_type VARCHAR(30),
    mobile VARCHAR(15),
    service_description TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    qr_version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    created_by INT REFERENCES users (id),
    updated_by INT REFERENCES users (id),
    pan_number VARCHAR(10),
    gstin VARCHAR(15)
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
    qr_version INT NOT NULL DEFAULT 1,
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
    updated_by INT REFERENCES users (id),
    qr_payload VARCHAR(255)
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
    ticket_price NUMERIC(10, 2) DEFAULT 0,
    ticket_name2 VARCHAR(20) DEFAULT 'Child',
    ticket_price2 NUMERIC(10, 2) DEFAULT 0,
    image TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by INT REFERENCES users (id),
    updated_at TIMESTAMP,
    updated_by INT REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS concerns (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    apartment_id INT REFERENCES apartments (id) ON DELETE SET NULL,
    concern_type VARCHAR(50),
    description TEXT,
    preferred_time VARCHAR(20),
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    image TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by INT REFERENCES users (id),
    updated_at TIMESTAMP,
    updated_by INT REFERENCES users (id),
    qr_payload VARCHAR(255)
);

-- ════════════════════════════════════════════════════════════════════════
-- CONCERNS_ASSIGNS — unified per-assignee lifecycle (2026-07 overhaul)
--
-- One row per (concern, role, entity). Carries the FULL delegation
-- lifecycle for that assignee, replacing what used to be split across
-- two tables (concerns_assigns + concerns_invite):
--
--     invited -> bid_submitted -> assigned -> resolved -> closed
--
-- ADM rows (society admins, who are auto-assigned rather than invited to
-- bid) skip straight to 'assigned', then follow their own sub-lifecycle:
--
--     assigned -> accepted -> resolved -> closed
--     assigned -> declined
--
-- ('accepted' added 2026-08 to support the Admin portal's Accept/Decline/
-- Resolved actions on an assigned concern — see
-- migration_concerns_assigns_accepted_status.sql.) VND/SEC rows normally
-- start at 'invited' and progress through 'bid_submitted' before an admin
-- formally 'assigned's them — though a direct "Assign" is still allowed at
-- any point as a shortcut (e.g. price already agreed offline), which simply
-- promotes whatever row exists straight to 'assigned'.
--
-- concerns.status is KEPT (existing code, KPIs, and the
-- idx_concerns_society_status index all depend on it), but it is a
-- read-only aggregate cache synced by ONE trigger (fn_sync_concern_status,
-- below) from these rows — application code should stop writing
-- concerns.status directly for anything except the initial INSERT ('open').
--
-- Aggregate rule:
--   no concerns_assigns rows for this concern_id            -> concerns.status='open'
--   all rows status='closed'                                -> 'closed'
--   all rows status IN ('resolved','closed')                 -> 'resolved'
--   any row status IN ('assigned','accepted','resolved','closed') -> 'assigned'
--   otherwise (only 'invited'/'bid_submitted' rows exist)     -> 'open'
-- ════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS concerns_assigns (
    id SERIAL PRIMARY KEY,
    concern_id INT NOT NULL REFERENCES concerns (id) ON DELETE CASCADE,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    role VARCHAR(10) NOT NULL CHECK (role IN ('ADM', 'VND', 'SEC')),
    entity_id INT NOT NULL,
    invited_by INT REFERENCES users (id),
    assigned_by INT REFERENCES users (id),
    resolved_by INT REFERENCES users (id),
    closed_by INT REFERENCES users (id),
    status VARCHAR(20) NOT NULL DEFAULT 'invited' CHECK (
        status IN (
            'invited',
            'bid_submitted',
            'declined',
            'assigned',
            'accepted',
            'resolved',
            'closed'
        )
    ),
    bid_amount NUMERIC(10, 2),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP,
    UNIQUE (concern_id, role, entity_id)
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
    created_by INT REFERENCES users (id),
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
    role VARCHAR(10) NOT NULL CHECK (
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
            'credit',
            'rejected'
        )
    ),
    confirmed_by INT REFERENCES users (id),
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by INT REFERENCES users (id)
,
    bill_group_id UUID DEFAULT gen_random_uuid(),
    reported_amount NUMERIC(10, 2),
    reported_mode VARCHAR(20),
    reported_reference VARCHAR(255),
    reported_at TIMESTAMP,
    reported_by INT REFERENCES users (id)
);

-- ── RECEIPTS — manual credits, deemed paid on creation ────────
CREATE TABLE IF NOT EXISTS receipts (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id),
    entity_id INT,
    role VARCHAR(10) CHECK (
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
            'cancelled',
            'rejected'
        )
    ),
    confirmed_by INT REFERENCES users (id),
    confirmed_at TIMESTAMP,
    last_printed_at TIMESTAMP,
    last_emailed_at TIMESTAMP,
    receipt_number VARCHAR(64) UNIQUE,
    previous_hash VARCHAR(64),
    source_reference VARCHAR(255),
    qr_payload VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by INT REFERENCES users (id)
);

COMMENT ON COLUMN receipts.user_id IS 'User who recorded/submitted this receipt (creator), NOT who verified it — see confirmed_by.';

-- ── NOCS — persisted No-Objection Certificates, one row per issuance ──
-- Previously NOCs were generated on the fly with no DB record at all, so
-- there was nothing for a verification QR to point at. This gives every
-- issued NOC a real id/certificate number, an audit trail (who issued it,
-- when, for which apartment), and a status a security guard's scan can
-- check (valid / expired / revoked) — mirrors the receipts/expenses
-- pattern (qr_payload, last_printed_at, last_emailed_at) already in use.
CREATE TABLE IF NOT EXISTS nocs (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    apartment_id INT NOT NULL REFERENCES apartments (id) ON DELETE CASCADE,
    certificate_no VARCHAR(64) UNIQUE,
    body_text TEXT NOT NULL, -- the exact text issued, so a later edit to the template doesn't change what a printed/verified NOC says
    status VARCHAR(20) NOT NULL DEFAULT 'valid' CHECK (
        status IN (
            'valid',
            'expired',
            'revoked'
        )
    ),
    issued_date DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_until DATE NOT NULL, -- issued_date + 30 days, matches the "valid for 30 days" language already in the NOC template text
    revoked_at TIMESTAMP,
    revoked_by INT REFERENCES users (id),
    qr_payload VARCHAR(255),
    last_printed_at TIMESTAMP,
    last_emailed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by INT REFERENCES users (id)
);

COMMENT ON COLUMN nocs.status IS 'valid/expired are derived by validate_noc_qr() comparing valid_until to today; revoked is the only status ever written directly (via an explicit revoke action).';

-- ── EXPENSES — manual debits, deemed paid on creation ─────────
CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id),
    entity_id INT,
    role VARCHAR(10) CHECK (
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
    tds_pct NUMERIC(5, 2) DEFAULT 10,
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
    qr_payload VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by INT REFERENCES users (id)
,
    tds_section VARCHAR(10)
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
    role VARCHAR(10) CHECK (
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
    created_by INT REFERENCES users (id),
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
    entry_side VARCHAR(2),
    trx_date DATE NOT NULL,
    acc_id INT REFERENCES accounts (id),
    entity_id INTEGER,
    -- Discriminator for entity_id, mirroring receipts/expenses/payables.role.
    -- Without this, joining apartments/vendors/security_staff on entity_id
    -- alone risks a false match if IDs collide across those tables. 'assets'
    -- covers asset purchase/sale/writeoff legs, where entity_id references
    -- assets.id (a distinct ID space, not apartment/vendor/security).
    role VARCHAR(10) CHECK (
        role IN (
            'apartment',
            'vendor',
            'security',
            'other',
            'assets'
        )
    ),
    acc_particulars VARCHAR(200),
    amount NUMERIC(15, 2) NOT NULL CHECK (amount > 0),
    -- 'journal': a pure book entry with no cash or bank movement at all
    -- (e.g. Dr Depreciation/Cr Asset). Distinct from 'cash', which means
    -- physical rupees moved — see fn_resolve_bank_leg and
    -- fn_cashbook_paired_v3's header comment for why the two must not be
    -- conflated.
    mode VARCHAR(10) DEFAULT 'cash' CHECK (
        mode IN (
            'cash',
            'cheque',
            'upi',
            'card',
            'bank',
            'crypto',
            'journal'
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
    created_by INT REFERENCES users (id),
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
    booking_reference VARCHAR(50),
    issued_date DATE DEFAULT CURRENT_DATE,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW()
);

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
    created_by INT REFERENCES users (id),
    updated_at TIMESTAMP,
    updated_by INT REFERENCES users (id),
    apt_sinking_fund_rate NUMERIC(10,2) DEFAULT 0,
    apt_repair_fund_rate NUMERIC(10,2) DEFAULT 0,
    charges_interest BOOLEAN DEFAULT TRUE
);

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
    created_by INT REFERENCES users (id),
    updated_at TIMESTAMP,
    updated_by INT REFERENCES users (id)
);

-- ── Gate access & other tables ─────────────────────────────────
CREATE TABLE IF NOT EXISTS gate_access (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    entity_id INTEGER NOT NULL,
    role VARCHAR(10),
    time_in TIMESTAMP NOT NULL DEFAULT NOW(),
    time_out TIMESTAMP,
    created_by INT REFERENCES users (id),
    updated_by INT
);

CREATE TABLE IF NOT EXISTS brought_forward (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    financial_year SMALLINT NOT NULL, -- START year of FY, e.g. 2025 = FY 1-Apr-2025..31-Mar-2026
    acc_id INT NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
    drcr_bf VARCHAR(2) NOT NULL CHECK (drcr_bf IN ('Dr', 'Cr')),
    bf_amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00 CHECK (bf_amount >= 0),
    is_auto_calculated BOOLEAN NOT NULL DEFAULT FALSE, -- FALSE once a human hand-edits this row (see drilldown_callbacks.py); no automatic writer exists as of 2026-08 (fn_close_financial_year removed)
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

CREATE TABLE IF NOT EXISTS role_permissions (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    role VARCHAR(10) NOT NULL,
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

CREATE TABLE IF NOT EXISTS society_compliance_settings (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    sinking_fund_rate_basis VARCHAR(20) DEFAULT 'per_sq_ft' CHECK (sinking_fund_rate_basis IN ('per_sq_ft', 'construction_cost')),
    repair_fund_rate_basis VARCHAR(20) DEFAULT 'per_sq_ft' CHECK (repair_fund_rate_basis IN ('per_sq_ft', 'construction_cost')),
    fund_gst_exempt BOOLEAN DEFAULT TRUE,
    fund_charges_interest BOOLEAN DEFAULT TRUE,
    gst_filing_cadence VARCHAR(20) DEFAULT 'monthly' CHECK (gst_filing_cadence IN ('monthly', 'qrmp')),
    gst_registered BOOLEAN DEFAULT FALSE,
    gstin VARCHAR(15),
    tds_no_pan_action VARCHAR(10) DEFAULT 'warn' CHECK (tds_no_pan_action IN ('warn', 'block')),
    default_export_format VARCHAR(20) DEFAULT 'structured' CHECK (default_export_format IN ('structured', 'gstn_offline', 'traces_26q')),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_society_compliance_settings UNIQUE (society_id)
);

-- ════════════════════════════════════════════════════════════════════════════
-- GST RATES — Society-specific GST rates with effective dates
-- ════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS gst_rates (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    cgst_rate_pct NUMERIC(5, 2) NOT NULL,
    sgst_rate_pct NUMERIC(5, 2) NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ════════════════════════════════════════════════════════════════════════════
-- KPI RULE LINKS — external "Rules & Regulations" links surfaced in the
-- compliance-settings banner (and any future KPI context). Stored in the DB
-- rather than hardcoded so admins can add/retire links without a code deploy,
-- and so state-specific statutes (UP Apartment Act, Maharashtra Bye-Laws,
-- etc.) can coexist with Union-law links (CBIC, Income Tax) that apply
-- nationwide. The banner renderer joins these by category + state at render
-- time.
-- ════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS kpi_rule_links (
    id SERIAL PRIMARY KEY,
    category VARCHAR(50) NOT NULL CHECK (category IN (
        'sinking_fund', 'repair_fund', 'fund_gst', 'fund_interest',
        'gst_registered', 'tds_no_pan', 'rera', 'apartment_act',
        'cooperative_act', 'income_tax_mutuality', 'other'
    )),
    state VARCHAR(10) NOT NULL DEFAULT 'ALL'
        CHECK (state IN ('ALL','UP','MH','KA','TN','DL','RJ','MP','WB','GJ','TS','AP','BR','HR','PB','KL')),
    label VARCHAR(200) NOT NULL,
    url TEXT NOT NULL,
    description TEXT,
    sort_order INT NOT NULL DEFAULT 100,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    effective_from DATE,
    effective_to DATE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ════════════════════════════════════════════════════════════════════════════
-- STATE COMPLIANCE THRESHOLDS — statutory rates and thresholds that vary by
-- state (sinking/repair fund percentages, GST limits, TDS thresholds, etc.).
-- Unlike kpi_rule_links (which stores external URLs), this stores the actual
-- numeric values the system can validate against and surface as defaults
-- when onboarding a society. NULL means "no statutory floor / not applicable"
-- (e.g., UP sinking fund has no fixed percentage — it's whatever the AOA
-- bye-laws specify).
-- ════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS state_compliance_thresholds (
    id SERIAL PRIMARY KEY,
    state VARCHAR(10) NOT NULL
        CHECK (state IN ('ALL','UP','MH','KA','TN','DL','RJ','MP','WB','GJ','TS','AP','BR','HR','PB','KL')),
    threshold_key VARCHAR(60) NOT NULL CHECK (threshold_key IN (
        'sinking_fund_pct_construction_cost',
        'repair_fund_pct_construction_cost',
        'sinking_fund_pct_sqft',
        'repair_fund_pct_sqft',
        'gst_turnover_lakh',
        'gst_per_member_monthly',
        'gst_rwa_collective_monthly',
        'tds_194c_single_bill',
        'tds_194c_annual_aggregate',
        'tds_194j_annual_aggregate',
        'tds_no_pan_rate',
        'income_tax_basic_exemption_new_regime',
        'income_tax_basic_exemption_old_regime',
        'income_tax_surcharge_limit',
        'rera_carpet_area_sqft',
        'rera_project_units',
        'rera_project_area_sqft',
        'apartment_act_min_units',
        'apartment_act_quorum_pct',
        'apartment_act_competent_authority'
    )),
    value NUMERIC(12,4),
    value_text TEXT,
    unit VARCHAR(20),
    effective_from DATE,
    effective_to DATE,
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_state_threshold UNIQUE (state, threshold_key, effective_from)
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

CREATE TABLE IF NOT EXISTS event_ticket_items (
    id SERIAL PRIMARY KEY,
    event_ticket_id INT NOT NULL REFERENCES event_tickets (id) ON DELETE CASCADE,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    ticket_type VARCHAR(20) NOT NULL CHECK (
        ticket_type IN ('ADULT', 'CHILD')
    ),
    qr_payload VARCHAR(255) UNIQUE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'used', 'cancelled')
    ),
    scanned_at TIMESTAMP,
    scanned_by INT REFERENCES users (id),
    last_printed_at TIMESTAMP,
    last_emailed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS visitors (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    apartment_id INT REFERENCES apartments (id) ON DELETE SET NULL,
    host_apartment_id INT REFERENCES apartments (id),
    name VARCHAR(100) NOT NULL,
    mobile VARCHAR(15),
    purpose VARCHAR(200),
    vehicle_number VARCHAR(20),
    visit_date DATE NOT NULL DEFAULT CURRENT_DATE,
    visit_time_from TIME,
    visit_time_to TIME,
    qr_payload VARCHAR(255) UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (
        status IN (
            'pending',
            'approved',
            'denied',
            'entered',
            'exited'
        )
    ),
    approved_by INT REFERENCES users (id),
    security_user_id INT REFERENCES users (id),
    entered_at TIMESTAMP,
    exited_at TIMESTAMP,
    source VARCHAR(20) NOT NULL DEFAULT 'security' CHECK (
        source IN ('owner', 'security')
    ),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alert_channels (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    channel_type VARCHAR(30) NOT NULL CHECK (
        channel_type IN (
            'school_bus',
            'taxi',
            'visitor'
        )
    ),
    name VARCHAR(100) NOT NULL,
    identifier VARCHAR(50),
    apartment_id INT REFERENCES apartments (id),
    is_recurring BOOLEAN NOT NULL DEFAULT TRUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alert_subscriptions (
    id SERIAL PRIMARY KEY,
    channel_id INT NOT NULL REFERENCES alert_channels (id) ON DELETE CASCADE,
    apartment_id INT NOT NULL REFERENCES apartments (id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (channel_id, apartment_id)
);

CREATE TABLE IF NOT EXISTS alert_events (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    channel_id INT REFERENCES alert_channels (id) ON DELETE CASCADE,
    visitor_id INT REFERENCES visitors (id) ON DELETE CASCADE,
    state VARCHAR(30) NOT NULL CHECK (
        state IN (
            'idle',
            'pending',
            'arrived',
            'calling',
            'resolved',
            'denied'
        )
    ),
    triggered_by INT REFERENCES users (id),
    triggered_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS patrol_locations (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    location_name VARCHAR(100) NOT NULL,
    description TEXT,
    qr_payload VARCHAR(255) UNIQUE NOT NULL,
    schedule_start TIME,
    schedule_end TIME,
    scan_interval INT DEFAULT 120,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS patrol_scans (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    location_id INT NOT NULL REFERENCES patrol_locations (id) ON DELETE CASCADE,
    security_user_id INT NOT NULL REFERENCES users (id),
    scanned_at TIMESTAMP DEFAULT NOW(),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS polls (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    created_by INT REFERENCES users (id),
    title VARCHAR(200) NOT NULL,
    description TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (
        status IN (
            'active',
            'closed',
            'results_declared'
        )
    ),
    choice_count SMALLINT NOT NULL CHECK (choice_count BETWEEN 2 AND 5),
    choice_1 VARCHAR(100) NOT NULL,
    choice_2 VARCHAR(100) NOT NULL,
    choice_3 VARCHAR(100),
    choice_4 VARCHAR(100),
    choice_5 VARCHAR(100),
    results_announced_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP,
    ends_at TIMESTAMP,
    reminder_sent_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS poll_votes (
    id SERIAL PRIMARY KEY,
    poll_id INT NOT NULL REFERENCES polls (id) ON DELETE CASCADE,
    user_id INT NOT NULL REFERENCES users (id),
    choice SMALLINT NOT NULL CHECK (choice BETWEEN 1 AND 5),
    cast_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (poll_id, user_id)
);

-- SECTION 15: INDIAN CHS/RWA COMPLIANCE — TDS (Phase 4)
-- ════════════════════════════════════════════════════════════════
-- CBDT TDS section → rate + thresholds. Rate is per-section; the
-- single-bill and annual-aggregate thresholds drive the "does TDS
-- apply to this bill" decision in fn_compute_tds_pct below.
--
-- [-WFLAG — PROFESSIONAL REVIEW- Rates here are a best-guess seed
-- (194C: 1% individual/HUF, 2% others, F30K single / F1L annual;
-- 194J: 10%, no threshold). Confirm against the applicable Finance
-- Act before relying on these for an actual filing.]
--
-- effective_from / effective_to give each rate row a validity window
-- (so a mid-year Finance-Act change can be added as a new row without
-- invalidating historical FY reports). A NULL effective_to means
-- "currently active". The lookup functions below resolve the row
-- effective as of a given date.
CREATE TABLE IF NOT EXISTS tds_section_rates (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    section VARCHAR(10) NOT NULL,
    rate NUMERIC(5, 2) NOT NULL,
    rate_no_pan NUMERIC(5, 2),
    single_bill_threshold NUMERIC(12, 2) NOT NULL DEFAULT 30000,
    annual_aggregate_threshold NUMERIC(12, 2) NOT NULL DEFAULT 0,
    effective_from DATE NOT NULL DEFAULT '2024-04-01',
    effective_to DATE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tds_section_rate UNIQUE (society_id, section, effective_from)
);

-- Circular-reference FKs (societies <-> users)

ALTER TABLE societies
ADD CONSTRAINT societies_created_by_fkey FOREIGN KEY (created_by) REFERENCES users (id);

ALTER TABLE societies
DROP CONSTRAINT IF EXISTS societies_created_by_fkey;

-- societies.primary_bank_account_id (2026-08)
-- ==============================================
-- Single default bank account used for every non-cash transaction leg
-- (cheque/upi/card/bank/crypto alike) society-wide. See
-- fn_resolve_bank_leg below for how writer functions consume this.
-- Added here (after `accounts`, which it forward-references) rather than
-- inline on the societies CREATE TABLE above, same late-ALTER-TABLE
-- pattern already used for societies_created_by_fkey just above.
--
-- The FK alone can't express "must be a child of THIS society's own Bank
-- Accounts header" — a trigger (defense-in-depth alongside the FK)
-- enforces both (a) the referenced account belongs to this same society,
-- and (b) its parent_account_id is that society's 'BkAc' (Bank Accounts)
-- header account. Per-mode bank routing (UPI -> ICICI, Cheque -> SBI,
-- etc.) may replace this single column later; for now every non-cash
-- mode routes through it uniformly.
ALTER TABLE societies
ADD COLUMN IF NOT EXISTS primary_bank_account_id INT REFERENCES accounts (id);

-- SECTION 2B: NUMBERING SEQUENCES & TRIGGERS
-- Auto-generate human-friendly receipt_number / transaction_number.
-- ════════════════════════════════════════════════════════════════
CREATE SEQUENCE IF NOT EXISTS seq_receipt_number;

CREATE SEQUENCE IF NOT EXISTS seq_transaction_number;

-- SECTION 2: INDEXES
-- ════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user ON push_subscriptions (user_id);

CREATE INDEX IF NOT EXISTS idx_push_subscriptions_endpoint ON push_subscriptions (endpoint);

CREATE INDEX IF NOT EXISTS idx_society_compliance_settings_society ON society_compliance_settings (society_id);

CREATE INDEX IF NOT EXISTS idx_kpi_rule_links_category ON kpi_rule_links (category);

CREATE INDEX IF NOT EXISTS idx_kpi_rule_links_state ON kpi_rule_links (state);

CREATE INDEX IF NOT EXISTS idx_kpi_rule_links_active ON kpi_rule_links (is_active);

CREATE INDEX IF NOT EXISTS idx_state_compliance_state ON state_compliance_thresholds (state);

CREATE INDEX IF NOT EXISTS idx_state_compliance_key ON state_compliance_thresholds (threshold_key);

CREATE INDEX IF NOT EXISTS idx_state_compliance_active ON state_compliance_thresholds (is_active);

-- SECTION 2: INDEXES
-- ════════════════════════════════════════════════════════════════

-- SECTION 2: INDEXES
-- ════════════════════════════════════════════════════════════════
CREATE UNIQUE INDEX IF NOT EXISTS idx_assets_qr ON assets (qr_payload);

CREATE UNIQUE INDEX IF NOT EXISTS uq_receivable_entity_month ON receivables (entity_id, role, period_month);

CREATE INDEX IF NOT EXISTS idx_transactions_journal ON transactions (journal_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_expenses_qr ON expenses (qr_payload);

CREATE UNIQUE INDEX IF NOT EXISTS idx_receipts_qr ON receipts (qr_payload);

CREATE INDEX IF NOT EXISTS idx_bf_society_fy ON brought_forward (society_id, financial_year);

CREATE INDEX IF NOT EXISTS idx_visitors_society_date ON visitors (society_id, visit_date);

CREATE INDEX IF NOT EXISTS idx_event_ticket_items_qr ON event_ticket_items (qr_payload);

CREATE INDEX IF NOT EXISTS idx_event_tickets_event ON event_tickets (event_id);

CREATE INDEX IF NOT EXISTS idx_event_tickets_user ON event_tickets (user_id);

CREATE INDEX IF NOT EXISTS idx_concerns_assigns_concern ON concerns_assigns (concern_id);

CREATE INDEX IF NOT EXISTS idx_concerns_assigns_society ON concerns_assigns (society_id);

CREATE INDEX IF NOT EXISTS idx_concerns_assigns_lookup ON concerns_assigns (society_id, role, entity_id);

CREATE INDEX IF NOT EXISTS idx_concerns_assigns_status ON concerns_assigns (concern_id, status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_concerns_qr ON concerns (qr_payload);

CREATE INDEX IF NOT EXISTS idx_apt_charges_society ON apt_charges_fines_basis (society_id, apt_id);

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

-- SECTION 3: EVENT QR TICKETS, VISITORS & SUBSCRIBABLE ALERTS
-- ════════════════════════════════════════════════════════════════
-- ════════════════════════════════════════════════════════════════
-- POLLING SYSTEM
-- ════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_polls_society ON polls (society_id);

CREATE INDEX IF NOT EXISTS idx_polls_status ON polls (status);

CREATE INDEX IF NOT EXISTS idx_poll_votes_poll ON poll_votes (poll_id);

CREATE INDEX IF NOT EXISTS idx_poll_votes_user ON poll_votes (user_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_poll_vote_user ON poll_votes (poll_id, user_id);

CREATE INDEX IF NOT EXISTS idx_tds_section_rates_lookup
    ON tds_section_rates (society_id, section, effective_from);

-- SECTION 3: FUNCTIONS
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_trg_validate_primary_bank_account () CASCADE;

CREATE OR REPLACE FUNCTION fn_trg_validate_primary_bank_account()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_acc_society_id INT;
    v_parent_tab     TEXT;
BEGIN
    IF NEW.primary_bank_account_id IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT a.society_id, p.tab_name
      INTO v_acc_society_id, v_parent_tab
      FROM accounts a
      LEFT JOIN accounts p ON p.id = a.parent_account_id
     WHERE a.id = NEW.primary_bank_account_id;

    IF v_acc_society_id IS NULL THEN
        RAISE EXCEPTION 'primary_bank_account_id % does not exist', NEW.primary_bank_account_id;
    END IF;
    IF v_acc_society_id <> NEW.id THEN
        RAISE EXCEPTION 'primary_bank_account_id % belongs to a different society (society %, not %)',
            NEW.primary_bank_account_id, v_acc_society_id, NEW.id;
    END IF;
    IF v_parent_tab IS DISTINCT FROM 'BkAc' THEN
        RAISE EXCEPTION 'primary_bank_account_id % is not a child of the Bank Accounts (BkAc) header account',
            NEW.primary_bank_account_id;
    END IF;

    RETURN NEW;
END;
$$;

-- SECTION 3: FUNCTIONS
-- ════════════════════════════════════════════════════════════════

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

-- Same for expenses: placeholder no-op triggers (expense hash feature not yet fully implemented).
DROP FUNCTION IF EXISTS fn_trg_expense_hash_issue () CASCADE;

CREATE OR REPLACE FUNCTION fn_trg_expense_hash_issue()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RETURN NEW;
END;
$$;

DROP FUNCTION IF EXISTS fn_trg_expense_hash_insert () CASCADE;

CREATE OR REPLACE FUNCTION fn_trg_expense_hash_insert()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RETURN NEW;
END;
$$;

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

-- Generic updated_at stamping trigger factory
DROP FUNCTION IF EXISTS fn_trg_set_updated_at () CASCADE;

CREATE OR REPLACE FUNCTION fn_trg_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- QR PAYLOAD AUTO-GENERATION TRIGGERS
-- Ensures every entity row carries a canonical <society_id>-<XXX>-<id> QR
-- ════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_trg_concerns_qr()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.qr_payload IS NULL OR TRIM(NEW.qr_payload) = '' THEN
        NEW.qr_payload := NEW.society_id || '-CON-' || NEW.id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION fn_trg_receipts_qr()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.qr_payload IS NULL OR TRIM(NEW.qr_payload) = '' THEN
        NEW.qr_payload := NEW.society_id || '-RPT-' || NEW.id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION fn_trg_expenses_qr()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.qr_payload IS NULL OR TRIM(NEW.qr_payload) = '' THEN
        NEW.qr_payload := NEW.society_id || '-EXP-' || NEW.id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION fn_trg_assets_qr()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.qr_payload IS NULL OR TRIM(NEW.qr_payload) = '' THEN
        NEW.qr_payload := NEW.society_id || '-AST-' || NEW.id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION fn_trg_visitors_qr()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.qr_payload IS NULL OR TRIM(NEW.qr_payload) = '' THEN
        NEW.qr_payload := NEW.society_id || '-VST-' || NEW.id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION fn_trg_patrol_locations_qr()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.qr_payload IS NULL OR TRIM(NEW.qr_payload) = '' THEN
        NEW.qr_payload := NEW.society_id || '-PTL-' || NEW.id;
    END IF;
    RETURN NEW;
END;
$$;

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
    v_active      BOOLEAN;
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
        -- NOTE (fixed 2026-08): previously only checked vendor_passes
        -- expiry — an offboarded/deactivated vendor with a still-unexpired
        -- pass would evaluate as PASS at the gate. Check vendors.active
        -- first.
        SELECT v.active INTO v_active FROM vendors v WHERE v.id = p_entity_id;
        IF v_active IS NOT TRUE THEN
            RETURN QUERY SELECT FALSE, 'Vendor account is inactive'::TEXT, 0::NUMERIC(15,2);
            RETURN;
        END IF;

        SELECT MAX(vp.valid_until) INTO v_pass_expiry
        FROM vendor_passes vp
        JOIN users u ON u.id = vp.user_id
        WHERE u.linked_id = p_entity_id
          AND u.role = 'vendor'
          AND vp.status = 'active';
        IF v_pass_expiry IS NULL OR v_pass_expiry < CURRENT_DATE THEN
            RETURN QUERY SELECT FALSE, 'No active vendor pass'::TEXT, 0::NUMERIC(15,2);
        ELSE
            RETURN QUERY SELECT TRUE,
                ('Pass valid until ' || v_pass_expiry::TEXT)::TEXT, 0::NUMERIC(15,2);
        END IF;

    ELSIF p_role = 'security' THEN
        SELECT EXISTS(
            SELECT 1 FROM gate_access
            WHERE entity_id = p_entity_id AND role = 'SEC' AND time_out IS NULL
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

-- Generates multi-line receivable rows per apartment per calendar month.
-- Each bill is split into: maintenance + sinking fund + repair fund + GST
-- (if applicable). All lines for one apartment/period share one bill_group_id.
DROP FUNCTION IF EXISTS fn_auto_generate_receivables CASCADE;

-- ════════════════════════════════════════════════════════════════
-- fn_post_receivable_accrual — accrual-side posting for a single
-- newly-billed receivable line (or a newly-applied interest
-- increment on an existing one).
--
-- Posts Dr Sundry Debtors (the "Sundry Debtors" header account, id
-- resolved by name — not a Digital/Cash leaf) / Cr <the line's own
-- income or GST-payable account> for the amount just billed, with
-- mode='journal' since no cash has moved yet (pure accrual
-- recognition — same convention as the existing depreciation
-- journals: no cash leg, excluded from the cashbook via
-- mode <> 'journal', included in ledger/trial balance/closing).
--
-- Posted to the CONTROL account rather than 81/82 because the
-- eventual collection mode is unknown at bill time — only
-- fn_verify_receivable / fn_pay_apartment_dues_fifo know that, at
-- collection, and post the clearing Cr leg to the correct
-- Digital/Cash leaf then. fn_fy_closing_report's recursive ancestry
-- rollup sums header + leaves together for reporting, so the split
-- still nets to the correct outstanding balance either way.
--
-- Silently no-ops (does nothing) if the amount is zero/NULL, the
-- income account is NULL, or no "Sundry Debtors" account is
-- configured for the society — callers are not expected to check
-- first, mirroring how the fund/GST account resolution in
-- fn_auto_generate_receivables already tolerates "not configured".
-- ════════════════════════════════════════════════════════════════
DROP FUNCTION IF EXISTS fn_post_receivable_accrual (INT, INT, INT, VARCHAR, INT, NUMERIC, TEXT) CASCADE;

CREATE OR REPLACE FUNCTION fn_post_receivable_accrual(
    p_society_id     INT,
    p_receivable_id  INT,
    p_entity_id      INT,
    p_role           VARCHAR,
    p_income_acc_id  INT,
    p_amount         NUMERIC,
    p_particulars    TEXT
)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    v_sdr_acc_id INT;
    v_journal_id INT;
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 OR p_income_acc_id IS NULL OR p_receivable_id IS NULL THEN
        RETURN;
    END IF;

    SELECT id INTO v_sdr_acc_id FROM accounts
    WHERE society_id = p_society_id
      AND name ILIKE 'Sundry Debtors'
    LIMIT 1;
    IF v_sdr_acc_id IS NULL THEN RETURN; END IF;

    v_journal_id := NEXTVAL('seq_transaction_number');

    -- Dr: Sundry Debtors control account (the member now owes this)
    INSERT INTO transactions(
        society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id, journal_id
    ) VALUES (
        p_society_id, 'Dr', CURRENT_DATE, v_sdr_acc_id, p_entity_id, p_role,
        p_particulars, p_amount, 'journal', 'paid', NULL, NOW(), 'receivables', p_receivable_id, v_journal_id
    );

    -- Cr: the line's own income / GST-payable account (accrual recognition)
    INSERT INTO transactions(
        society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id, journal_id
    ) VALUES (
        p_society_id, 'Cr', CURRENT_DATE, p_income_acc_id, p_entity_id, p_role,
        p_particulars, p_amount, 'journal', 'paid', NULL, NOW(), 'receivables', p_receivable_id, v_journal_id
    );
END;
$$;

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
    v_base_maint  NUMERIC(10,2);
    v_base_sinking NUMERIC(10,2);
    v_base_repair  NUMERIC(10,2);
    v_gst_cgst    NUMERIC(10,2);
    v_gst_sgst    NUMERIC(10,2);
    v_due_date    DATE;
    v_desc        TEXT;
    v_bill_group_id UUID;
    v_fallback_maint_acc  INT;
    v_fallback_int_acc    INT;
    v_sinking_acc_id      INT;
    v_repair_acc_id       INT;
    v_cgst_acc_id         INT;
    v_sgst_acc_id         INT;
    v_society_turnover    NUMERIC(15,2);
    v_current_fy          INT;
    v_cached_fy           INT := -1;
    v_new_rec_id          INT;  -- id of the row just inserted (NULL if ON CONFLICT skipped it — idempotent re-runs must not double-accrue)
    v_gst_threshold       NUMERIC(10,2);
    v_turnover_threshold  NUMERIC(15,2);
    v_cgst_rate           NUMERIC(5,2);
    v_sgst_rate           NUMERIC(5,2);
    v_total_taxable       NUMERIC(10,2);
BEGIN
    SELECT calc_start_date INTO v_society_calc_start FROM societies WHERE id = p_society_id;
    IF NOT FOUND THEN RETURN; END IF;

    -- Resolve fallback accounts once per society
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

    -- Resolve fund / GST accounts once per society (NULL = not configured,
    -- caller skips that line)
    SELECT id INTO v_sinking_acc_id FROM accounts
    WHERE society_id = p_society_id
      AND name ILIKE '%Sinking Fund%'
      AND drcr_account = 'Cr'
    LIMIT 1;

    SELECT id INTO v_repair_acc_id FROM accounts
    WHERE society_id = p_society_id
      AND name ILIKE '%Repair Fund%'
      AND drcr_account = 'Cr'
    LIMIT 1;

    SELECT id INTO v_cgst_acc_id FROM accounts
    WHERE society_id = p_society_id
      AND name ILIKE '%CGST Payable%'
      AND drcr_account = 'Cr'
    LIMIT 1;

    SELECT id INTO v_sgst_acc_id FROM accounts
    WHERE society_id = p_society_id
      AND name ILIKE '%SGST Payable%'
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
                   apt_interest_pct, start_date, end_date,
                   apt_sinking_fund_rate, apt_repair_fund_rate, charges_interest
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
                charge.apt_sinking_fund_rate  := 0;
                charge.apt_repair_fund_rate   := 0;
                charge.charges_interest       := TRUE;
            END IF;

            v_overlap_start := GREATEST(v_month_start, charge.start_date, v_calc_start);
            v_overlap_end   := LEAST(v_month_end, COALESCE(charge.end_date, v_month_end));
            v_overlap_days  := GREATEST((v_overlap_end - v_overlap_start + 1)::INT, 0);

            IF v_overlap_days = 0 THEN
                v_month := (v_month + INTERVAL '1 month')::DATE;
                CONTINUE;
            END IF;

            -- Maintenance base amount (existing logic, unchanged)
            IF charge.apt_maintenance_amount IS NOT NULL AND charge.apt_maintenance_amount > 0 THEN
                v_base_maint := ROUND(charge.apt_maintenance_amount * v_overlap_days::NUMERIC / v_days_in_month, 2);
            ELSE
                v_base_maint := ROUND(apt.apartment_size * charge.apt_maintenance_rate * v_overlap_days::NUMERIC / v_days_in_month, 2);
            END IF;

            -- Sinking fund and repair fund (per-sq-ft, same proration)
            v_base_sinking := ROUND(apt.apartment_size * COALESCE(charge.apt_sinking_fund_rate, 0) * v_overlap_days::NUMERIC / v_days_in_month, 2);
            v_base_repair  := ROUND(apt.apartment_size * COALESCE(charge.apt_repair_fund_rate, 0) * v_overlap_days::NUMERIC / v_days_in_month, 2);

            -- Fetch dynamic GST rates for this month
            SELECT cgst_rate_pct, sgst_rate_pct INTO v_cgst_rate, v_sgst_rate
              FROM gst_rates
             WHERE society_id = p_society_id
               AND effective_from <= v_month
               AND (effective_to IS NULL OR effective_to >= v_month)
             ORDER BY effective_from DESC LIMIT 1;
             
            v_cgst_rate := COALESCE(v_cgst_rate, 0);
            v_sgst_rate := COALESCE(v_sgst_rate, 0);

            -- Fetch dynamic thresholds
            SELECT value INTO v_gst_threshold FROM state_compliance_thresholds WHERE threshold_key = 'gst_per_member_monthly' AND is_active = TRUE LIMIT 1;
            SELECT value INTO v_turnover_threshold FROM state_compliance_thresholds WHERE threshold_key = 'gst_turnover_lakh' AND is_active = TRUE LIMIT 1;
            v_gst_threshold := COALESCE(v_gst_threshold, 7500);
            v_turnover_threshold := COALESCE(v_turnover_threshold, 20) * 100000; -- Convert lakhs to absolute

            -- GST threshold check (per-apartment maintenance > threshold AND society turnover > turnover_threshold)
            v_current_fy := CASE WHEN EXTRACT(MONTH FROM v_month) >= 4 THEN EXTRACT(YEAR FROM v_month)::INT ELSE (EXTRACT(YEAR FROM v_month)::INT - 1) END;
            IF v_current_fy != v_cached_fy THEN
                SELECT fn_society_turnover_fy(p_society_id, v_current_fy) INTO v_society_turnover;
                v_cached_fy := v_current_fy;
            END IF;

            -- Evaluate taxability on the common area maintenance components
            v_total_taxable := v_base_maint + v_base_sinking + v_base_repair;

            IF v_total_taxable > v_gst_threshold AND COALESCE(v_society_turnover, 0) > v_turnover_threshold THEN
                v_gst_cgst := ROUND(v_total_taxable * (v_cgst_rate / 100.0), 2);
                v_gst_sgst := ROUND(v_total_taxable * (v_sgst_rate / 100.0), 2);
            ELSE
                v_gst_cgst := 0;
                v_gst_sgst := 0;
            END IF;

            v_due_date := (v_month + ((COALESCE(charge.apt_due_day,5) - 1) * INTERVAL '1 day'))::DATE;
            v_bill_group_id := gen_random_uuid();

            -- Maintenance line
            IF v_base_maint > 0 THEN
                INSERT INTO receivables (
                    society_id, entity_id, role, bill_group_id,
                    acc_id, interest_acc_id,
                    description, period_month,
                    base_amount, amount, paid_principal, due_date, status, created_at
                ) VALUES (
                    p_society_id, apt.id, 'apartment', v_bill_group_id,
                    v_fallback_maint_acc,
                    CASE WHEN charge.charges_interest THEN v_fallback_int_acc ELSE NULL END,
                    'Maintenance ' || TO_CHAR(v_month, 'Mon-YYYY'), v_month,
                    v_base_maint, v_base_maint, 0, v_due_date, 'pending', NOW()
                )
                ON CONFLICT DO NOTHING
                RETURNING id INTO v_new_rec_id;

                PERFORM fn_post_receivable_accrual(
                    p_society_id, v_new_rec_id, apt.id, 'apartment',
                    v_fallback_maint_acc, v_base_maint,
                    'Maintenance ' || TO_CHAR(v_month, 'Mon-YYYY')
                );
            END IF;

            -- Sinking fund line
            IF v_base_sinking > 0 AND v_sinking_acc_id IS NOT NULL THEN
                INSERT INTO receivables (
                    society_id, entity_id, role, bill_group_id,
                    acc_id, interest_acc_id,
                    description, period_month,
                    base_amount, amount, paid_principal, due_date, status, created_at
                ) VALUES (
                    p_society_id, apt.id, 'apartment', v_bill_group_id,
                    v_sinking_acc_id,
                    CASE WHEN charge.charges_interest THEN v_fallback_int_acc ELSE NULL END,
                    'Sinking Fund ' || TO_CHAR(v_month, 'Mon-YYYY'), v_month,
                    v_base_sinking, v_base_sinking, 0, v_due_date, 'pending', NOW()
                )
                ON CONFLICT DO NOTHING
                RETURNING id INTO v_new_rec_id;

                PERFORM fn_post_receivable_accrual(
                    p_society_id, v_new_rec_id, apt.id, 'apartment',
                    v_sinking_acc_id, v_base_sinking,
                    'Sinking Fund ' || TO_CHAR(v_month, 'Mon-YYYY')
                );
            END IF;

            -- Repair fund line
            IF v_base_repair > 0 AND v_repair_acc_id IS NOT NULL THEN
                INSERT INTO receivables (
                    society_id, entity_id, role, bill_group_id,
                    acc_id, interest_acc_id,
                    description, period_month,
                    base_amount, amount, paid_principal, due_date, status, created_at
                ) VALUES (
                    p_society_id, apt.id, 'apartment', v_bill_group_id,
                    v_repair_acc_id,
                    CASE WHEN charge.charges_interest THEN v_fallback_int_acc ELSE NULL END,
                    'Repair Fund ' || TO_CHAR(v_month, 'Mon-YYYY'), v_month,
                    v_base_repair, v_base_repair, 0, v_due_date, 'pending', NOW()
                )
                ON CONFLICT DO NOTHING
                RETURNING id INTO v_new_rec_id;

                PERFORM fn_post_receivable_accrual(
                    p_society_id, v_new_rec_id, apt.id, 'apartment',
                    v_repair_acc_id, v_base_repair,
                    'Repair Fund ' || TO_CHAR(v_month, 'Mon-YYYY')
                );
            END IF;

            -- GST lines (CGST + SGST, both required for a valid GST collection)
            IF v_gst_cgst > 0 AND v_cgst_acc_id IS NOT NULL THEN
                INSERT INTO receivables (
                    society_id, entity_id, role, bill_group_id,
                    acc_id, interest_acc_id,
                    description, period_month,
                    base_amount, amount, paid_principal, due_date, status, created_at
                ) VALUES (
                    p_society_id, apt.id, 'apartment', v_bill_group_id,
                    v_cgst_acc_id, NULL,
                    'CGST on Maintenance ' || TO_CHAR(v_month, 'Mon-YYYY'), v_month,
                    v_gst_cgst, v_gst_cgst, 0, v_due_date, 'pending', NOW()
                )
                ON CONFLICT DO NOTHING
                RETURNING id INTO v_new_rec_id;

                PERFORM fn_post_receivable_accrual(
                    p_society_id, v_new_rec_id, apt.id, 'apartment',
                    v_cgst_acc_id, v_gst_cgst,
                    'CGST on Maintenance ' || TO_CHAR(v_month, 'Mon-YYYY')
                );
            END IF;

            IF v_gst_sgst > 0 AND v_sgst_acc_id IS NOT NULL THEN
                INSERT INTO receivables (
                    society_id, entity_id, role, bill_group_id,
                    acc_id, interest_acc_id,
                    description, period_month,
                    base_amount, amount, paid_principal, due_date, status, created_at
                ) VALUES (
                    p_society_id, apt.id, 'apartment', v_bill_group_id,
                    v_sgst_acc_id, NULL,
                    'SGST on Maintenance ' || TO_CHAR(v_month, 'Mon-YYYY'), v_month,
                    v_gst_sgst, v_gst_sgst, 0, v_due_date, 'pending', NOW()
                )
                ON CONFLICT DO NOTHING
                RETURNING id INTO v_new_rec_id;

                PERFORM fn_post_receivable_accrual(
                    p_society_id, v_new_rec_id, apt.id, 'apartment',
                    v_sgst_acc_id, v_gst_sgst,
                    'SGST on Maintenance ' || TO_CHAR(v_month, 'Mon-YYYY')
                );
            END IF;

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

        PERFORM fn_post_receivable_accrual(
            p_society_id, rec.id, rec.entity_id, 'apartment',
            COALESCE(rec.interest_acc_id, v_int_acc_id), v_total_increment,
            'Interest on ' || COALESCE(rec.description, 'Maintenance Due')
        );

    END LOOP;
END;
$$;

-- SECTION 4B: DOUBLE-ENTRY CASH ACCOUNT RESOLVER
-- Returns the Dr (cash/bank) account to pair against an income/expense
-- account for a given society + payment mode.
--   mode='bank' → SBI A/c - Society (6311) if present, else first Dr account
--   otherwise   → Cash-in-hand (633) if present, else first Dr account
-- ════════════════════════════════════════════════════════════════
DROP FUNCTION IF EXISTS fn_resolve_cash_account (INT, VARCHAR) CASCADE;

DROP FUNCTION IF EXISTS fn_resolve_bank_leg (INT, VARCHAR) CASCADE;

-- fn_resolve_bank_leg
-- ====================
-- Replaces fn_resolve_cash_account (2026-08). The old function always
-- resolved SOME account — CiH for mode='cash', a name-matched "SBI A/c"
-- for the literal mode='bank', and (bug) CiH again for every OTHER
-- non-cash mode (cheque/upi/card/crypto), since only that one literal
-- string hit the SBI branch. Every money-writing function then wrote a
-- second leg to whatever got resolved, which is what caused the
-- double-sided cashbook display bug: a cash-mode transaction's
-- "completing" CiH leg landed on the OPPOSITE side of the cashbook from
-- where the real transaction happened (e.g. a PropInc cash receipt's
-- completing Dr-CiH leg showed up on the Payment side, as if money had
-- also been paid out).
--
-- New contract:
--   mode = 'cash'  -> NULL. No second leg gets written at all — see each
--                     writer function below (`IF v_bank_acc IS NOT NULL
--                     THEN ... END IF;`). CIH Running in the cashbook is
--                     derived by directly summing every cash-mode
--                     transaction's own entry_side (see
--                     fn_cih_balance_asof below), not by reading a
--                     dedicated CiH ledger account — CiH now has NO
--                     transaction rows of its own.
--   mode <> 'cash' -> societies.primary_bank_account_id, the single
--                     society-wide bank leg for every non-cash mode
--                     (cheque/upi/card/bank/crypto alike). Raises loudly
--                     if not configured, rather than silently falling
--                     back to CiH like the old function did.
CREATE OR REPLACE FUNCTION fn_resolve_bank_leg(p_society_id INT, p_mode VARCHAR)
RETURNS INT LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_acc_id INT;
BEGIN
    -- 'journal' (pure book entry, e.g. depreciation) needs no completing
    -- leg at all, same as 'cash' — both legs of a journal entry are
    -- always written explicitly by the caller.
    IF p_mode IN ('cash', 'journal') THEN
        RETURN NULL;
    END IF;

    SELECT primary_bank_account_id INTO v_acc_id
    FROM societies WHERE id = p_society_id;

    IF v_acc_id IS NULL THEN
        RAISE EXCEPTION 'No primary_bank_account_id configured for society % — set Settings > Accounts > Primary Bank Account before recording a non-cash (%) transaction', p_society_id, p_mode;
    END IF;

    RETURN v_acc_id;
END;
$$;

-- fn_resolve_sdr_leg
-- ==================
-- Resolves which Sundry Debtors leaf a receivable COLLECTION should
-- clear against: "Sundry Debtors (Cash)" for mode='cash', else
-- "Sundry Debtors (Digital)" for every other mode (cheque/upi/card/
-- bank/crypto). Independent of fn_resolve_bank_leg — that function
-- decides the Dr cash/bank leg (and returns NULL for cash, since CiH
-- is derived implicitly, never posted to directly); this one decides
-- the Cr leg that relieves the member's outstanding balance, which
-- must exist for every mode, cash included. Falls back to the
-- "Sundry Debtors" control account itself if a society hasn't been
-- migrated to the 81/82 split yet, so this never blocks a payment.
DROP FUNCTION IF EXISTS fn_resolve_sdr_leg (INT, VARCHAR) CASCADE;

CREATE OR REPLACE FUNCTION fn_resolve_sdr_leg(p_society_id INT, p_mode VARCHAR)
RETURNS INT LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_acc_id INT;
    v_name   VARCHAR;
BEGIN
    v_name := CASE WHEN p_mode = 'cash' THEN 'Sundry Debtors (Cash)' ELSE 'Sundry Debtors (Digital)' END;

    SELECT id INTO v_acc_id FROM accounts
    WHERE society_id = p_society_id AND name = v_name
    LIMIT 1;

    IF v_acc_id IS NULL THEN
        SELECT id INTO v_acc_id FROM accounts
        WHERE society_id = p_society_id AND name ILIKE 'Sundry Debtors'
        LIMIT 1;
    END IF;

    RETURN v_acc_id;
END;
$$;

-- fn_cih_balance_asof
-- ====================
-- Single source of truth for "what is CiH's balance as of this date",
-- since CiH no longer has any transaction rows of its own to sum (cash-
-- mode legs post directly to the real income/expense/asset account —
-- see fn_resolve_bank_leg above). Computes: this date's FY's
-- brought_forward CiH row, plus the net Cr(+)/Dr(-) effect of every
-- mode='cash' transaction from that FY's start through p_as_of_date
-- inclusive, across ANY account (cash-mode legs can land on Salary,
-- PropInc, TDStoIT, an asset account, anywhere — CIH Running doesn't
-- care which account, only that mode='cash').
--
-- Shared by:
--   - fn_cashbook_month_page (month_opening_balance / month_closing_balance)
--   - fn_account_ledger_fy's CiH branch (its C/F figure)
--   - fn_dashboard_stats (live cash_balance)
-- so all three are guaranteed to always agree — none of them re-derive
-- this formula independently.
DROP FUNCTION IF EXISTS fn_cih_balance_asof (INT, DATE) CASCADE;

CREATE OR REPLACE FUNCTION fn_cih_balance_asof(p_society_id INT, p_as_of_date DATE)
RETURNS NUMERIC(15,2) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_fy       INT;
    v_fy_start DATE;
    v_bf       NUMERIC(15,2);
    v_delta    NUMERIC(15,2);
BEGIN
    v_fy := EXTRACT(YEAR FROM p_as_of_date)::INT
            - CASE WHEN EXTRACT(MONTH FROM p_as_of_date) < 4 THEN 1 ELSE 0 END;
    v_fy_start := make_date(v_fy, 4, 1);

    SELECT COALESCE(SUM(
        CASE WHEN bf.drcr_bf = 'Dr' THEN bf.bf_amount ELSE -bf.bf_amount END
    ), 0)
    INTO v_bf
    FROM accounts a
    JOIN brought_forward bf ON bf.acc_id = a.id AND bf.society_id = a.society_id
    WHERE a.society_id = p_society_id AND a.tab_name = 'CiH'
      AND bf.financial_year = v_fy;

    SELECT COALESCE(SUM(
        CASE WHEN t.entry_side = 'Cr' THEN t.amount
             WHEN t.entry_side = 'Dr' THEN -t.amount
             ELSE 0 END
    ), 0)
    INTO v_delta
    FROM transactions t
    WHERE t.society_id = p_society_id AND t.status = 'paid' AND t.mode = 'cash'
      AND t.trx_date >= v_fy_start AND t.trx_date <= p_as_of_date;

    RETURN v_bf + v_delta;
END;
$$;

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
    v_bank_acc INT;
    v_mode VARCHAR(20);
    v_number VARCHAR(64);
BEGIN
    SELECT * INTO v_rec FROM receipts WHERE id = p_receipt_id FOR UPDATE;
    IF NOT FOUND    THEN receipt_id := p_receipt_id; receipt_number := NULL; msg := 'Error: Receipt not found'; RETURN NEXT; RETURN; END IF;
    IF v_rec.status = 'confirmed'  THEN receipt_id := p_receipt_id; receipt_number := v_rec.receipt_number; msg := 'Already confirmed'; RETURN NEXT; RETURN; END IF;
    IF v_rec.status = 'cancelled'  THEN receipt_id := p_receipt_id; receipt_number := v_rec.receipt_number; msg := 'Error: Receipt is cancelled'; RETURN NEXT; RETURN; END IF;
    IF v_rec.acc_id IS NULL        THEN receipt_id := p_receipt_id; receipt_number := v_rec.receipt_number; msg := 'Error: No income account on this receipt'; RETURN NEXT; RETURN; END IF;

    v_mode := COALESCE(p_mode, v_rec.mode);
    v_bank_acc := fn_resolve_bank_leg(v_rec.society_id, v_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    -- Cr: income account (the receipt's acc_id)
    INSERT INTO transactions(
        society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id, journal_id
    ) VALUES (
        v_rec.society_id, 'Cr', v_rec.receipt_date, v_rec.acc_id, v_rec.entity_id, v_rec.role,
        v_rec.particulars,
        v_rec.amount, v_mode, 'paid',
        p_confirmed_by, NOW(), 'receipts', v_rec.id, v_journal_id
    ) RETURNING id INTO v_trx_id;

    -- Dr: cash / bank paired side (double-entry)
    IF v_bank_acc IS NOT NULL THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_rec.society_id, 'Dr', v_rec.receipt_date, v_bank_acc, v_rec.entity_id, v_rec.role,
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
    v_bank_acc INT;
    v_mode VARCHAR(20);
    v_number VARCHAR(64);
BEGIN
    SELECT * INTO v_rec FROM expenses WHERE id = p_expense_id FOR UPDATE;
    IF NOT FOUND    THEN expense_id := p_expense_id; receipt_number := NULL; msg := 'Error: Expense not found'; RETURN NEXT; RETURN; END IF;
    IF v_rec.status = 'confirmed'  THEN expense_id := p_expense_id; receipt_number := v_rec.receipt_number; msg := 'Already confirmed'; RETURN NEXT; RETURN; END IF;
    IF v_rec.status = 'cancelled'  THEN expense_id := p_expense_id; receipt_number := v_rec.receipt_number; msg := 'Error: Expense is cancelled'; RETURN NEXT; RETURN; END IF;
    IF v_rec.acc_id IS NULL        THEN expense_id := p_expense_id; receipt_number := v_rec.receipt_number; msg := 'Error: No expense account on this row'; RETURN NEXT; RETURN; END IF;

    v_mode := COALESCE(p_mode, v_rec.mode);
    v_bank_acc := fn_resolve_bank_leg(v_rec.society_id, v_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    -- Dr: expense account
    INSERT INTO transactions(
        society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id, journal_id
    ) VALUES (
        v_rec.society_id, 'Dr', v_rec.expense_date, v_rec.acc_id, v_rec.entity_id, v_rec.role,
        v_rec.particulars,
        v_rec.amount, v_mode, 'paid',
        p_confirmed_by, NOW(), 'expenses', v_rec.id, v_journal_id
    ) RETURNING id INTO v_trx_id;

    -- Cr: cash / bank paired side
    IF v_bank_acc IS NOT NULL THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_rec.society_id, 'Cr', v_rec.expense_date, v_bank_acc, v_rec.entity_id, v_rec.role,
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

-- fn_verify_receivable: entry_side + actual-amount-received support
-- ============================================
-- Previously this always posted (and force-settled) the FULL residual —
-- there was no way for Admin to record that less than the outstanding
-- balance was actually handed over at verification time (the bulk FIFO
-- path, fn_pay_apartment_dues_fifo, already supported partial amounts;
-- this single-row verify path did not). p_amount is now accepted,
-- capped at the residual, and the row is left 'partial' if it doesn't
-- fully clear — same shape as fn_pay_apartment_dues_fifo. NULL keeps the
-- old full-residual behavior for any caller not yet passing it.
--
-- Also fixes the interest-remaining formula, which used
-- `paid_amount - base_amount` — inconsistent with fn_pay_apartment_dues_fifo's
-- `paid_amount - paid_principal` (the column that's actually documented
-- and maintained for exactly this purpose; see the comment on
-- receivables.paid_principal). Brought in line with that here.
--
-- STATUS: draft, not yet run against a live PG16 instance. Verify with
-- pglast + a real instance before deploying, per usual workflow.

CREATE OR REPLACE FUNCTION fn_verify_receivable(
    p_receivable_id INT,
    p_confirmed_by  INT,
    p_mode          VARCHAR DEFAULT 'cash',
    p_amount        NUMERIC DEFAULT NULL   -- actual amount received; NULL = full residual (back-compat)
)
RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
    v_rec         receivables%ROWTYPE;
    v_residual    NUMERIC(15,2);
    v_take        NUMERIC(15,2);
    v_base_post   NUMERIC(15,2);
    v_int_post    NUMERIC(15,2);
    v_int_acc     INT;
    v_trx_id      INT;
    v_journal_id  INT;
    v_bank_acc    INT;
    v_new_paid    NUMERIC(15,2);
BEGIN
    SELECT * INTO v_rec FROM receivables WHERE id = p_receivable_id FOR UPDATE;
    IF NOT FOUND THEN RETURN 'Error: Receivable not found'; END IF;
    IF v_rec.status = 'paid' THEN RETURN 'Already fully paid'; END IF;
    IF v_rec.acc_id IS NULL THEN RETURN 'Error: No income account set on this receivable — check apt_charges_fines_basis'; END IF;

    v_residual := v_rec.amount - v_rec.paid_amount;
    IF v_residual <= 0 THEN RETURN 'Nothing outstanding on this row'; END IF;

    -- Actual money received this time. Caller-supplied, capped at the
    -- residual (can't collect more than is owed on this one row) — a
    -- larger overpayment should go through fn_pay_apartment_dues_fifo,
    -- which banks the excess as an advance credit; this single-row path
    -- doesn't have anywhere to put money beyond what this row is for.
    v_take := COALESCE(p_amount, v_residual);
    IF v_take <= 0 THEN RETURN 'Error: amount must be > 0'; END IF;
    IF v_take > v_residual THEN v_take := v_residual; END IF;

    v_int_acc  := v_rec.interest_acc_id;
    v_int_post := LEAST(v_rec.interest_amount - GREATEST(v_rec.paid_amount - v_rec.paid_principal, 0), v_take);
    v_int_post := GREATEST(COALESCE(v_int_post, 0), 0);
    v_base_post := v_take - v_int_post;

    v_bank_acc := fn_resolve_bank_leg(v_rec.society_id, p_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    -- Cr: Sundry Debtors (Digital/Cash leaf, by p_mode) — relieves the
    -- member's outstanding balance. Income/GST-payable was already
    -- recognized at BILL time by fn_post_receivable_accrual (accrual
    -- basis, 2026-08); collection no longer re-credits v_rec.acc_id /
    -- v_int_acc, which would double-count the income. One combined
    -- leg for base+interest since both clear the same debtor balance
    -- against the same leaf account.
    INSERT INTO transactions(
        society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id, journal_id
    ) VALUES (
        v_rec.society_id, 'Cr', CURRENT_DATE, fn_resolve_sdr_leg(v_rec.society_id, p_mode), v_rec.entity_id, v_rec.role,
        v_rec.description,
        v_take, p_mode, 'paid', p_confirmed_by, NOW(), 'receivables', v_rec.id, v_journal_id
    ) RETURNING id INTO v_trx_id;

    -- Dr: cash / bank paired side (actual amount received, not the full residual)
    IF v_bank_acc IS NOT NULL THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_rec.society_id, 'Dr', CURRENT_DATE, v_bank_acc, v_rec.entity_id, v_rec.role,
            'Cash received - ' || REPLACE(v_rec.description, ' + Interest', ''),
            v_take, p_mode, 'paid', p_confirmed_by, NOW(), 'receivables', v_rec.id, v_journal_id
        );
    END IF;

    v_new_paid := v_rec.paid_amount + v_take;

    UPDATE receivables
         SET paid_amount  = v_new_paid,
             paid_principal = v_rec.paid_principal + v_base_post,
             status       = CASE WHEN v_new_paid >= v_rec.amount THEN 'paid' ELSE 'partial' END,
             confirmed_by = p_confirmed_by,
             confirmed_at = NOW()
         WHERE id = p_receivable_id;

    RETURN 'Verified: transaction #' || v_trx_id::TEXT || ' — ₹' || v_take::TEXT ||
           CASE WHEN v_new_paid < v_rec.amount
                THEN ' received (partial — ₹' || (v_rec.amount - v_new_paid)::TEXT || ' still outstanding)'
                ELSE ' received (paid in full)' END;
END;
$$;

-- Bill-group verify wrapper: settles a whole bill_group_id as one payment,
-- calling fn_verify_receivable per row (FIFO within the group). Low-risk
-- because it reuses the already-correct single-row primitive rather than
-- reimplementing posting logic.
DROP FUNCTION IF EXISTS fn_verify_receivable_by_bill_group (UUID, INT, VARCHAR, NUMERIC) CASCADE;

CREATE OR REPLACE FUNCTION fn_verify_receivable_by_bill_group(
    p_bill_group_id UUID,
    p_confirmed_by  INT,
    p_mode          VARCHAR DEFAULT 'cash',
    p_amount        NUMERIC DEFAULT NULL
)
RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
    v_rec       RECORD;
    v_remaining NUMERIC(15,2);
    v_take      NUMERIC(15,2);
    v_residual  NUMERIC(15,2);
    v_msg       TEXT;
    v_first     BOOLEAN := TRUE;
BEGIN
    IF p_amount IS NOT NULL AND p_amount <= 0 THEN
        RETURN 'Error: amount must be > 0';
    END IF;

    SELECT COALESCE(SUM(amount - paid_amount), 0)::NUMERIC(15,2)
      INTO v_remaining
      FROM receivables
     WHERE bill_group_id = p_bill_group_id
       AND status IN ('pending','partial','unverified');

    IF v_remaining <= 0 THEN
        RETURN 'Nothing outstanding on this bill group';
    END IF;

    IF p_amount IS NOT NULL AND p_amount < v_remaining THEN
        v_remaining := p_amount;
    END IF;

    FOR v_rec IN
        SELECT id, amount, paid_amount, base_amount, interest_amount,
               paid_principal, interest_acc_id, acc_id, description
          FROM receivables
         WHERE bill_group_id = p_bill_group_id
           AND status IN ('pending','partial','unverified')
         ORDER BY due_date ASC NULLS LAST, id ASC
         FOR UPDATE
    LOOP
        EXIT WHEN v_remaining <= 0;

        v_residual := v_rec.amount - v_rec.paid_amount;
        IF v_residual <= 0 THEN CONTINUE; END IF;

        v_take := LEAST(v_remaining, v_residual);

        SELECT fn_verify_receivable(v_rec.id, p_confirmed_by, p_mode, v_take)
          INTO v_msg;

        v_remaining := v_remaining - v_take;
        IF v_first THEN
            RETURN v_msg;
            v_first := FALSE;
        END IF;
    END LOOP;

    RETURN COALESCE(v_msg, 'Bill group verified');
END;
$$;

-- Bulk FIFO payment across monthly rows (Pay Dues button).
-- Posts ONE journal (income side + cash Dr side) for the whole payment.
-- FIX (2026-08): the income side now emits ONE Cr leg per DISTINCT acc_id
-- actually settled, rather than a single lump leg against whichever account
-- belonged to the oldest receivable. Without this, split bills (maintenance
-- + sinking + repair) silently misattribute every rupee beyond the first
-- row's account to the wrong ledger account — dues tracking looks correct,
-- the trial balance is wrong. Also routes advance-credit overpayment to the
-- maintenance account explicitly, not "whichever row was oldest", and keeps
-- the journal balanced (overpayment is recognized as a maintenance Cr leg).
DROP FUNCTION IF EXISTS fn_pay_apartment_dues_fifo CASCADE;

-- fn_apply_apartment_dues_fifo_core: shared FIFO allocation + posting engine.
-- Extracted (2026-08) so both the admin-immediate path
-- (fn_pay_apartment_dues_fifo) and the self-pay confirm path
-- (fn_confirm_apartment_self_payment) share one implementation instead of
-- duplicating the FIFO/journal logic. p_source_table/p_source_id let the
-- caller trace every posted leg back to whatever record authorized it
-- (a receivable-direct admin payment, or a confirmed self-reported receipt).
CREATE OR REPLACE FUNCTION fn_apply_apartment_dues_fifo_core(
    p_apartment_id INT,
    p_amount       NUMERIC,
    p_mode         VARCHAR DEFAULT 'cash',
    p_confirmed_by INT     DEFAULT NULL,
    p_particulars  TEXT    DEFAULT NULL,
    p_source_table VARCHAR DEFAULT 'receivables',
    p_source_id    INT     DEFAULT NULL
)
RETURNS TABLE(transaction_id INT, allocated NUMERIC, unallocated NUMERIC, journal_id INT)
LANGUAGE plpgsql AS $$
DECLARE
    v_society_id INT;
    v_maint_acc_id INT;  -- explicit maintenance account for advance-credit fallback
    v_remaining  NUMERIC(15,2) := p_amount;
    v_trx_id     INT;
    v_journal_id INT;
    v_bank_acc   INT;
    rec          RECORD;
    v_take        NUMERIC(15,2);
    v_row_residual NUMERIC(15,2);
    v_row_int      NUMERIC(15,2);
    v_row_prin     NUMERIC(15,2);
    v_pay_int      NUMERIC(15,2);
    v_pay_prin     NUMERIC(15,2);
    v_fallback_int_acc INT;
    v_total_take   NUMERIC(15,2) := 0;  -- running total actually applied to open dues this call — one Cr leg to the SDr leaf covers all of it (accrual basis, 2026-08)
    v_first_trx_id INT;
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

    -- Resolve maintenance account explicitly — used for advance-credit
    -- fallback (overpayment is a maintenance credit, not a fund contribution)
    -- and as the home for any overpaid amount when no open dues exist.
    SELECT id INTO v_maint_acc_id FROM accounts
    WHERE society_id = v_society_id
      AND name ILIKE '%Society Maintenance Charge%'
      AND drcr_account = 'Cr'
    LIMIT 1;

    IF v_maint_acc_id IS NULL THEN
        RAISE EXCEPTION 'Maintenance account not found for society %', v_society_id;
    END IF;

    v_bank_acc := fn_resolve_bank_leg(v_society_id, p_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    FOR rec IN
        SELECT id, amount, paid_amount, paid_principal, base_amount,
               interest_amount, interest_acc_id, acc_id, confirmed_by
          FROM receivables
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

        v_total_take := v_total_take + v_take;
        v_remaining  := v_remaining - v_take;
    END LOOP;

    -- Cr: Sundry Debtors (Digital/Cash leaf, by p_mode) — ONE combined
    -- leg for every row actually settled this call, sharing one
    -- journal_id. Income/GST-payable was already recognized at BILL
    -- time by fn_post_receivable_accrual (accrual basis, 2026-08);
    -- collection just relieves the debtor now, so there's no longer a
    -- need to route per-row by acc_id — every row clears against the
    -- same leaf account regardless of which income category it billed
    -- under (base_maint / sinking / repair / GST / interest all land
    -- on the same "amount this member owed" balance).
    IF v_total_take > 0 THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_society_id, 'Cr', CURRENT_DATE, fn_resolve_sdr_leg(v_society_id, p_mode), p_apartment_id, 'apartment',
            COALESCE(p_particulars, 'Maintenance Payment'),
            v_total_take, p_mode, 'paid', p_confirmed_by, NOW(), p_source_table, p_source_id, v_journal_id
        ) RETURNING id INTO v_trx_id;
        IF v_first_trx_id IS NULL THEN v_first_trx_id := v_trx_id; END IF;
    END IF;

    -- Overpayment (or a payment with no open dues at all) is banked as a
    -- maintenance Cr leg so the journal stays balanced, then recorded as an
    -- advance-credit receivable. Routed to maintenance explicitly, not to
    -- whichever row happened to be oldest.
    IF v_remaining > 0 THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_society_id, 'Cr', CURRENT_DATE, v_maint_acc_id, p_apartment_id, 'apartment',
            COALESCE(p_particulars, 'Maintenance Payment') || ' (Advance)',
            v_remaining, p_mode, 'paid', p_confirmed_by, NOW(), p_source_table, p_source_id, v_journal_id
        ) RETURNING id INTO v_trx_id;
        IF v_first_trx_id IS NULL THEN v_first_trx_id := v_trx_id; END IF;
    END IF;

    -- Dr: cash / bank paired side (actual amount received). References the
    -- originating record (p_source_id, e.g. a confirmed self-pay receipt) when
    -- given, else the first Cr leg posted this call, so the journal is
    -- traceable as one event either way.
    IF v_bank_acc IS NOT NULL THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_society_id, 'Dr', CURRENT_DATE, v_bank_acc, p_apartment_id, 'apartment',
            'Cash received - Maintenance Payment',
            p_amount, p_mode, 'paid', p_confirmed_by, NOW(), p_source_table, COALESCE(p_source_id, v_first_trx_id), v_journal_id
        );
    END IF;

    -- Advance-credit receivable marker (status='credit') for any excess beyond
    -- every currently-open due. Not a separate ledger entry — the overpayment
    -- Cr leg above already recognizes the cash as maintenance income.
    IF v_remaining > 0 THEN
        INSERT INTO receivables (
            society_id, entity_id, role, acc_id, interest_acc_id,
            description, base_amount, amount, paid_amount, paid_principal,
            status, confirmed_by, confirmed_at, created_at
        ) VALUES (
            v_society_id, p_apartment_id, 'apartment', v_maint_acc_id,
            COALESCE(v_fallback_int_acc, v_maint_acc_id),
            'Advance Credit', v_remaining, v_remaining, 0, 0,
            'credit', p_confirmed_by, NOW(), NOW()
        );
    END IF;

    RETURN QUERY SELECT v_first_trx_id,
        (p_amount - v_remaining)::NUMERIC(15,2),
        v_remaining::NUMERIC(15,2),
        v_journal_id;
END;
$$;

-- fn_pay_apartment_dues_fifo: admin-immediate path (Pay Dues button).
-- Thin wrapper over fn_apply_apartment_dues_fifo_core — behavior/signature
-- unchanged from before the core was extracted (2026-08); source_table stays
-- 'receivables' with no source_id override, matching the original.
DROP FUNCTION IF EXISTS fn_pay_apartment_dues_fifo(INT, NUMERIC, VARCHAR, INT, TEXT) CASCADE;

CREATE OR REPLACE FUNCTION fn_pay_apartment_dues_fifo(
    p_apartment_id INT,
    p_amount       NUMERIC,
    p_mode         VARCHAR DEFAULT 'cash',
    p_confirmed_by INT     DEFAULT NULL,
    p_particulars  TEXT    DEFAULT NULL
)
RETURNS TABLE(transaction_id INT, allocated NUMERIC, unallocated NUMERIC, journal_id INT)
LANGUAGE plpgsql AS $$
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN
        RAISE EXCEPTION 'Amount must be > 0';
    END IF;
    RETURN QUERY
    SELECT * FROM fn_apply_apartment_dues_fifo_core(
        p_apartment_id, p_amount, p_mode, p_confirmed_by, p_particulars,
        'receivables', NULL
    );
END;
$$;

-- fn_report_apartment_payment_fifo: owner self-pay (FIFO toggle).
-- Creates ONE pending receipts row for the lump sum — no allocation, no
-- posting. acc_id is deliberately left NULL here rather than guessed via an
-- ILIKE account-name lookup: the actual income accounts are resolved
-- correctly inside fn_apply_apartment_dues_fifo_core at confirm time (via
-- fn_resolve_sdr_leg / the society's own Maintenance account), so nothing
-- needs to be guessed at report time.
-- Ownership check: the reporting user must be the 'apartment' user linked
-- to the target apartment — mirrors the IDOR-hardening convention already
-- used elsewhere in this codebase (SQL functions are the trust boundary,
-- not the client-supplied entity_id in the form payload).
CREATE OR REPLACE FUNCTION fn_report_apartment_payment_fifo(
    p_apartment_id INT,
    p_amount       NUMERIC,
    p_mode         VARCHAR DEFAULT 'cash',
    p_reported_by  INT     DEFAULT NULL,
    p_particulars  TEXT    DEFAULT NULL,
    p_reference    VARCHAR DEFAULT NULL
)
RETURNS TABLE(receipt_id INT, status TEXT) LANGUAGE plpgsql AS $$
DECLARE
    v_society_id INT;
    v_owns       BOOLEAN;
    v_receipt_id INT;
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN
        RETURN QUERY SELECT NULL::INT, 'Error: Amount must be > 0'::TEXT; RETURN;
    END IF;

    SELECT society_id INTO v_society_id FROM apartments WHERE id = p_apartment_id;
    IF NOT FOUND THEN
        RETURN QUERY SELECT NULL::INT, 'Error: Apartment not found'::TEXT; RETURN;
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM users
         WHERE id = p_reported_by AND role = 'apartment' AND linked_id = p_apartment_id
    ) INTO v_owns;
    IF NOT v_owns THEN
        RETURN QUERY SELECT NULL::INT, 'Error: You are not authorized to report a payment for this apartment'::TEXT; RETURN;
    END IF;

    INSERT INTO receipts (
        society_id, user_id, entity_id, role, receipt_date, acc_id,
        particulars, amount, mode, transaction_id, status, created_by
    ) VALUES (
        v_society_id, p_reported_by, p_apartment_id, 'apartment', CURRENT_DATE, NULL,
        COALESCE(p_particulars, 'Maintenance Payment (Self-reported, FIFO)'),
        p_amount, p_mode, p_reference, 'pending', p_reported_by
    ) RETURNING id INTO v_receipt_id;

    RETURN QUERY SELECT v_receipt_id, 'Success: Payment reported (FIFO). Awaiting verification.'::TEXT;
END;
$$;

-- fn_confirm_apartment_self_payment: admin confirms a FIFO-reported receipt.
-- Runs the same allocation core used by the admin-direct path, so a
-- confirmed self-pay clears receivables and posts transactions identically
-- to an admin-entered payment — the only difference is when the posting
-- happens (on confirm, not on report) and that every leg carries
-- source_table='receipts'/source_id=<this receipt> for traceability back to
-- the owner's original claim (UTR/reference included).
CREATE OR REPLACE FUNCTION fn_confirm_apartment_self_payment(
    p_receipt_id   INT,
    p_confirmed_by INT,
    p_mode         VARCHAR DEFAULT NULL
)
RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
    v_receipt   receipts%ROWTYPE;
    v_result    RECORD;
BEGIN
    SELECT * INTO v_receipt FROM receipts
     WHERE id = p_receipt_id AND role = 'apartment' AND status = 'pending'
     FOR UPDATE;
    IF NOT FOUND THEN
        RETURN 'Error: Receipt not found or not pending';
    END IF;

    SELECT * INTO v_result FROM fn_apply_apartment_dues_fifo_core(
        v_receipt.entity_id, v_receipt.amount, COALESCE(p_mode, v_receipt.mode),
        p_confirmed_by, v_receipt.particulars, 'receipts', v_receipt.id
    );

    UPDATE receipts
       SET status = 'confirmed', confirmed_by = p_confirmed_by, confirmed_at = NOW()
     WHERE id = p_receipt_id;

    RETURN 'Success: Payment confirmed and posted — transaction #' || v_result.transaction_id::TEXT;
END;
$$;

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
            AND ga.role = 'SEC'
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

-- fn_verify_payment: entry_side + TDS split
-- ============================================
-- Same two fixes as fn_save_expense: entry_side was entirely missing
-- (0 references, confirmed in the live repo), and this adds the same
-- p_tds_pct-driven split (default 10) using fn_resolve_tds_account.
--
-- NOT wired to any UI prompt yet — "Verify Payment" is currently a
-- single-click row action (drilldown_callbacks.py, action=="verify_payment")
-- with no modal and no field collection at all, unlike the "New Expense"
-- form which is schema-introspected from a real table. Exposing p_tds_pct
-- here means either:
--   (a) always applying the default 10% silently (no prompt), or
--   (b) building a small confirm-modal to ask before calling verify,
--       mirroring how other confirm actions in this codebase collect a
--       value before submitting (need to look at an existing example of
--       that pattern before building it, rather than inventing one).
-- Left as an open question rather than guessed at.
--
-- STATUS: draft, not yet run against a live PG16 instance.

DROP FUNCTION IF EXISTS fn_verify_payment CASCADE;

CREATE OR REPLACE FUNCTION fn_verify_payment(
    p_payment_id   INT,
    p_confirmed_by INT,
    p_mode         VARCHAR DEFAULT 'cash',
    p_tds_pct      NUMERIC DEFAULT 10
)
RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
    v_pay        payables%ROWTYPE;
    v_trx_id     INT;
    v_journal_id INT;
    v_bank_acc   INT;
    v_tds_acc    INT;
    v_tds_amt    NUMERIC(15,2) := 0;
    v_net_amt    NUMERIC(15,2);
BEGIN
    SELECT * INTO v_pay FROM payables WHERE id = p_payment_id FOR UPDATE;
    IF NOT FOUND THEN RETURN 'Error: Payment not found'; END IF;
    IF v_pay.status = 'verified' THEN RETURN 'Already verified'; END IF;
    IF v_pay.acc_id IS NULL THEN RETURN 'Error: No expense account set on this payment row'; END IF;
    IF p_tds_pct IS NOT NULL AND (p_tds_pct < 0 OR p_tds_pct > 100) THEN
        RETURN 'Error: TDS % must be between 0 and 100';
    END IF;

    v_bank_acc := fn_resolve_bank_leg(v_pay.society_id, p_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    IF COALESCE(p_tds_pct, 0) > 0 THEN
        v_tds_acc := fn_resolve_tds_account(v_pay.society_id);
    END IF;

    IF v_tds_acc IS NOT NULL THEN
        v_tds_amt := ROUND(v_pay.amount * p_tds_pct / 100.0, 2);
        v_net_amt := v_pay.amount - v_tds_amt;

        -- Dr: net expense amount, to the payable's own expense account
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_pay.society_id, 'Dr', CURRENT_DATE, v_pay.acc_id, v_pay.entity_id, v_pay.role,
            v_pay.description,
            v_net_amt, p_mode, 'paid', p_confirmed_by, NOW(), 'payables', v_pay.id, v_journal_id
        ) RETURNING id INTO v_trx_id;

        -- Dr: TDS amount, to the TDS account
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_pay.society_id, 'Dr', CURRENT_DATE, v_tds_acc, v_pay.entity_id, v_pay.role,
            'TDS on ' || v_pay.description,
            v_tds_amt, p_mode, 'paid', p_confirmed_by, NOW(), 'payables', v_pay.id, v_journal_id
        );
    ELSE
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_pay.society_id, 'Dr', CURRENT_DATE, v_pay.acc_id, v_pay.entity_id, v_pay.role,
            v_pay.description,
            v_pay.amount, p_mode, 'paid', p_confirmed_by, NOW(), 'payables', v_pay.id, v_journal_id
        ) RETURNING id INTO v_trx_id;
    END IF;

    -- Cr: cash/bank, full gross amount either way
    IF v_bank_acc IS NOT NULL THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_pay.society_id, 'Cr', CURRENT_DATE, v_bank_acc, v_pay.entity_id, v_pay.role,
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
    v_bank_acc    INT;
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

    v_bank_acc := fn_resolve_bank_leg(v_society_id, p_mode);
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
                society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id, journal_id
            ) VALUES (
                v_society_id, 'Cr', p_issued_date, v_acc_id, v_vendor_id, 'vendor', v_desc,
                v_rate, p_mode, 'paid', p_created_by, NOW(), 'receipts', v_receipt_id, v_journal_id
            );

            -- Dr: cash / bank paired side
            IF v_bank_acc IS NOT NULL THEN
                INSERT INTO transactions(
                    society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                    amount, mode, status, created_by, created_at, source_table, source_id, journal_id
                ) VALUES (
                    v_society_id, 'Dr', p_issued_date, v_bank_acc, v_vendor_id, 'vendor',
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
    v_bank_acc     INT;
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

    v_bank_acc   := fn_resolve_bank_leg(v_society_id, p_mode);
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
                society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id, journal_id
            ) VALUES (
                v_society_id, 'Cr', p_issued_date, v_acc_id, v_apt_id, 'apartment', v_desc,
                v_amount, p_mode, 'paid', p_created_by, NOW(), 'receipts', v_receipt_id, v_journal_id
            );

            IF v_bank_acc IS NOT NULL THEN
                INSERT INTO transactions(
                    society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                    amount, mode, status, created_by, created_at, source_table, source_id, journal_id
                ) VALUES (
                    v_society_id, 'Dr', p_issued_date, v_bank_acc, v_apt_id, 'apartment',
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
    v_bank_acc   INT;
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
    v_bank_acc := fn_resolve_bank_leg(p_society_id, p_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    -- Dr: asset class account
    INSERT INTO transactions(
        society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id, journal_id
    ) VALUES (
        p_society_id, 'Dr', p_purchase_date, p_acc_id, v_asset_id, 'assets', v_desc,
        p_purchase_value, p_mode, 'paid', p_created_by, NOW(), 'assets', v_asset_id, v_journal_id
    ) RETURNING id INTO v_trx_id;

    -- Cr: cash / bank paired side
    IF v_bank_acc IS NOT NULL THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            p_society_id, 'Cr', p_purchase_date, v_bank_acc, v_asset_id, 'assets',
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
    v_bank_acc   INT;
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
    v_bank_acc := fn_resolve_bank_leg(v_asset.society_id, p_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    -- Fixed (2026-08): this leg was previously written unconditionally
    -- (no IF v_bank_acc IS NOT NULL guard, unlike every other writer
    -- function) — mode='cash' now resolves v_bank_acc to NULL (see
    -- fn_resolve_bank_leg), so an unconditional INSERT here would have
    -- written a transaction with acc_id=NULL for every cash-mode
    -- disposal. Skipped entirely for cash mode instead, same as every
    -- other writer function — CIH Running is derived from the OTHER
    -- (asset/gain-loss) legs' own entry_side, not from a dedicated CiH
    -- leg. v_trx_id is captured from the always-present asset write-off
    -- leg below instead, since this one may not run.
    --
    -- Dr: cash / bank (sale proceeds) — non-cash mode only
    IF v_bank_acc IS NOT NULL THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_asset.society_id, 'Dr', p_sale_date, v_bank_acc, p_asset_id, 'assets',
            'Cash received - ' || v_desc,
            p_sale_value, p_mode, 'paid', p_created_by, NOW(), 'assets', p_asset_id, v_journal_id
        );
    END IF;

    -- Cr: asset class account (book value removal)
    INSERT INTO transactions(
        society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id, journal_id
    ) VALUES (
        v_asset.society_id, 'Cr', p_sale_date, v_asset.acc_id, p_asset_id, 'assets',
        'Asset written off - ' || v_asset.asset_name,
        v_book_value, p_mode, 'paid', p_created_by, NOW(), 'assets', p_asset_id, v_journal_id
    ) RETURNING id INTO v_trx_id;

    -- Cr (balancing): gain, or Dr (balancing): loss via the sale income account
    IF v_gain_loss <> 0 THEN
        IF v_gain_loss > 0 THEN
            -- Gain: Cr income account
            INSERT INTO transactions(
                society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id, journal_id
            ) VALUES (
                v_asset.society_id, 'Cr', p_sale_date, v_acc_id, p_asset_id, 'assets',
                'Gain on sale - ' || v_asset.asset_name,
                v_gain_loss, p_mode, 'paid', p_created_by, NOW(), 'assets', p_asset_id, v_journal_id
            );
        ELSE
            -- Loss: Dr loss account (the same income account, debited)
            INSERT INTO transactions(
                society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id, journal_id
            ) VALUES (
                v_asset.society_id, 'Dr', p_sale_date, v_acc_id, p_asset_id, 'assets',
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
    v_bank_acc   INT;
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
        source_reference, created_at, created_by
    ) VALUES (
        p_society_id, p_created_by, p_entity_id, p_role, p_receipt_date, p_acc_id, p_particulars,
        p_amount, p_mode, p_cheque_no, p_trx_id, v_status,
        CASE WHEN v_status = 'confirmed' THEN p_created_by ELSE NULL END,
        CASE WHEN v_status = 'confirmed' THEN NOW() ELSE NULL END,
        p_source_reference, NOW(), p_created_by
    ) RETURNING id INTO v_receipt_id;

    IF v_status = 'confirmed' THEN
        v_bank_acc := fn_resolve_bank_leg(p_society_id, p_mode);
        v_journal_id := NEXTVAL('seq_transaction_number');

        -- entry_side mirrors fn_save_expense's convention, just the opposite
        -- direction: the receipt/income account (already validated Cr above)
        -- gets entry_side='Cr' on its own leg; the cash/bank account gets
        -- entry_side='Dr' since cash is increasing. Previously this function
        -- inserted no entry_side at all, leaving every receipt-originated
        -- transaction row NULL on the one column the balance/ledger readers
        -- (fn_account_ledger_fy, v_financial_trial_balance, etc.) key off.
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            p_society_id, 'Cr', p_receipt_date, p_acc_id, p_entity_id, p_role, p_particulars,
            p_amount, p_mode, 'paid', p_created_by, NOW(), 'receipts', v_receipt_id, v_journal_id
        ) RETURNING id INTO v_trx_id;

        IF v_bank_acc IS NOT NULL THEN
            INSERT INTO transactions(
                society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id, journal_id
            ) VALUES (
                p_society_id, 'Dr', p_receipt_date, v_bank_acc, p_entity_id, p_role,
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
    p_source_reference VARCHAR DEFAULT NULL,
    p_tds_pct          NUMERIC DEFAULT 10,
    p_tds_section      VARCHAR DEFAULT NULL
)
RETURNS TABLE(expense_id INT, transaction_id INT, journal_id INT, status VARCHAR(20))
LANGUAGE plpgsql AS $$
DECLARE
    v_expense_id INT;
    v_trx_id     INT;
    v_journal_id INT;
    v_bank_acc   INT;
    v_tds_acc    INT;
    v_tds_amt    NUMERIC(15,2) := 0;
    v_net_amt    NUMERIC(15,2);
    v_drcr       VARCHAR(2);
    v_is_admin   BOOLEAN;
    v_status     VARCHAR(20);
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN RAISE EXCEPTION 'Amount must be > 0'; END IF;
    IF p_acc_id IS NULL THEN RAISE EXCEPTION 'acc_id is required'; END IF;
    IF p_particulars IS NULL OR TRIM(p_particulars) = '' THEN RAISE EXCEPTION 'particulars is required'; END IF;
    IF p_tds_pct IS NOT NULL AND (p_tds_pct < 0 OR p_tds_pct > 100) THEN
        RAISE EXCEPTION 'TDS %% must be between 0 and 100';
    END IF;
 
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
        source_reference, created_at, created_by, tds_pct, tds_section
    ) VALUES (
        p_society_id, p_created_by, p_entity_id, p_role, p_expense_date, p_acc_id, p_particulars,
        p_amount, p_mode, p_cheque_no, p_trx_id, v_status,
        CASE WHEN v_status = 'confirmed' THEN p_created_by ELSE NULL END,
        CASE WHEN v_status = 'confirmed' THEN NOW() ELSE NULL END,
        p_source_reference, NOW(), p_created_by, p_tds_pct, p_tds_section
    ) RETURNING id INTO v_expense_id;
 
    IF v_status = 'confirmed' THEN
        v_bank_acc := fn_resolve_bank_leg(p_society_id, p_mode);
        v_journal_id := NEXTVAL('seq_transaction_number');
 
        -- Resolve TDS only if a percentage was actually asked for and the
        -- society has a TDS account configured. Anything else falls
        -- through to the pre-existing single-leg behavior.
        IF COALESCE(p_tds_pct, 0) > 0 THEN
            v_tds_acc := fn_resolve_tds_account(p_society_id);
        END IF;
 
        IF v_tds_acc IS NOT NULL THEN
            v_tds_amt := ROUND(p_amount * p_tds_pct / 100.0, 2);
            v_net_amt := p_amount - v_tds_amt;
 
            -- Leg 1a: net expense amount, Dr, to the chosen expense account
            INSERT INTO transactions(
                society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id, journal_id
            ) VALUES (
                p_society_id, 'Dr', p_expense_date, p_acc_id, p_entity_id, p_role, p_particulars,
                v_net_amt, p_mode, 'paid', p_created_by, NOW(), 'expenses', v_expense_id, v_journal_id
            ) RETURNING id INTO v_trx_id;
 
            -- Leg 1b: TDS amount, Dr, to the TDS account
            INSERT INTO transactions(
                society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id, journal_id
            ) VALUES (
                p_society_id, 'Dr', p_expense_date, v_tds_acc, p_entity_id, p_role,
                'TDS on ' || p_particulars,
                v_tds_amt, p_mode, 'paid', p_created_by, NOW(), 'expenses', v_expense_id, v_journal_id
            );
        ELSE
            -- No TDS configured/requested — original single Dr leg, full amount.
            INSERT INTO transactions(
                society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id, journal_id
            ) VALUES (
                p_society_id, 'Dr', p_expense_date, p_acc_id, p_entity_id, p_role, p_particulars,
                p_amount, p_mode, 'paid', p_created_by, NOW(), 'expenses', v_expense_id, v_journal_id
            ) RETURNING id INTO v_trx_id;
        END IF;
 
        -- Leg 2: cash/bank, Cr, always the FULL gross amount — matches
        -- the confirmed example (Cr ICICI 1000 whether or not TDS splits
        -- the Dr side into 900+100).
        IF v_bank_acc IS NOT NULL THEN
            INSERT INTO transactions(
                society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id, journal_id
            ) VALUES (
                p_society_id, 'Cr', p_expense_date, v_bank_acc, p_entity_id, p_role,
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

--   1. fn_save_expense still had ZERO entry_side references in the repo
--      as of this session — the earlier entry_side migration draft
--      covering the 11 writer functions was never actually merged in.
--      This patch adds entry_side to both of fn_save_expense's legs
--      (Dr on the expense account, Cr on the cash/bank account) — same
--      direction assignment as before, just finally landing here too.
--
--   2. New: p_tds_pct parameter (default 10, matching "on expenses form,
--      default 10%"). When > 0 and a TDS-target account can be resolved
--      for the society, the expense leg splits into TWO Dr rows sharing
--      the same journal_id — net expense amount to p_acc_id, TDS amount
--      to the resolved TDS account — while the cash/bank Cr leg still
--      posts the FULL gross amount, matching the pattern confirmed
--      earlier this session (Cr bank 1000 / Dr Salary 900 / Dr TDS 100).
--      When p_tds_pct = 0 or no TDS account is configured for the
--      society, behavior is unchanged (single Dr leg) — backward
--      compatible with existing callers that don't pass the new param.
--
-- fn_resolve_tds_account mirrors fn_resolve_cash_account's existing
-- ILIKE-name-lookup pattern (same fragility, same convention — this
-- codebase already does this for the cash/bank resolver, so matching it
-- here is more consistent than introducing a different mechanism).
-- Flagging that fragility rather than hiding it: if a society renames
-- its TDS account away from containing "TDS to IT", this silently stops
-- resolving and TDS splitting silently stops happening (falls back to
-- single-leg behavior) rather than erroring — worth a follow-up look at
-- a proper flag/reference column if this matters enough to harden.
--
-- STATUS: draft, not yet run against a live PG16 instance this session
-- (unlike fn_fy_closing_report / fn_cashbook_paired_v3, which were
-- actually executed and had real bugs caught). Verify with pglast +
-- a real DB pass, including a live run, before deploying.
-- ════════════════════════════════════════════════════════════════

-- ── Schema: TDS % field on the expenses table itself ──
-- This is what makes the New-Expense form pick it up automatically —
-- forms in this codebase are built from live schema introspection
-- (schema_introspect.py), not hand-authored field lists, so adding the
-- column is the actual UI change; DEFAULT_FIELD_VALUES["expenses"] in
-- schema_introspect.py additionally pre-fills 10 on the New form (see
-- accompanying Python patch).
CREATE OR REPLACE FUNCTION fn_resolve_tds_account(p_society_id INT)
RETURNS INT LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_acc_id INT;
BEGIN
    SELECT id INTO v_acc_id FROM accounts
    WHERE society_id = p_society_id AND drcr_account = 'Dr'
      AND name ILIKE '%TDS to IT%'
    LIMIT 1;
  
    RETURN v_acc_id;  -- NULL if not found — caller treats that as "TDS not configured"
END;
$$;

CREATE OR REPLACE FUNCTION fn_resolve_gst_accounts(p_society_id INT)
RETURNS TABLE(cgst_acc_id INT, sgst_acc_id INT) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_cgst INT;
    v_sgst INT;
BEGIN
    SELECT id INTO v_cgst FROM accounts
    WHERE society_id = p_society_id AND drcr_account = 'Cr'
      AND name ILIKE '%CGST Payable%'
    LIMIT 1;

    SELECT id INTO v_sgst FROM accounts
    WHERE society_id = p_society_id AND drcr_account = 'Cr'
      AND name ILIKE '%SGST Payable%'
    LIMIT 1;

    RETURN QUERY SELECT v_cgst, v_sgst;  -- NULLs if not found — caller treats that as "GST not configured"
END;
$$;

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

DROP FUNCTION IF EXISTS fn_vendors_list CASCADE;

CREATE OR REPLACE FUNCTION fn_vendors_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL,
    p_has_passes BOOLEAN DEFAULT NULL
)
RETURNS TABLE (
    id INT, user_id INT, email VARCHAR(30), society_id INT, name VARCHAR(100),
    business_name VARCHAR(100), service_type VARCHAR(30), mobile VARCHAR(15), active BOOLEAN,
    pass_expiry DATE, gate_pass BOOLEAN, active_passes INT,
    pan_number VARCHAR(10), gstin VARCHAR(15)
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        v.id::INT, u.id::INT, u.email::VARCHAR(100), v.society_id::INT,
        COALESCE(v.name, u.email, 'Vendor #'||v.id)::VARCHAR(100),
        v.business_name::VARCHAR(100),
        COALESCE(v.service_type,'—')::VARCHAR(100),
        COALESCE(v.mobile,'—')::VARCHAR(15),
        COALESCE(v.active,TRUE)::BOOLEAN,
        COALESCE(pass.pass_expiry, p_pass_max.expiry)::DATE,
        COALESCE(pass.pass_expiry >= CURRENT_DATE, FALSE),
        COALESCE(pass.active_passes, 0)::INT,
        v.pan_number::VARCHAR(10), v.gstin::VARCHAR(15)
    FROM vendors v
    LEFT JOIN users u ON u.linked_id = v.id AND u.role = 'vendor'
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
    WHERE v.society_id = p_society_id
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
    id INT, user_id INT, email VARCHAR(30), society_id INT, name VARCHAR(100),
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
        s.id::INT, u.id::INT, u.email::VARCHAR(100), s.society_id::INT,
        COALESCE(s.name, u.email, 'Security #'||s.id)::VARCHAR(100), COALESCE(s.shift,'—')::VARCHAR(20),
        COALESCE(s.mobile,'—')::VARCHAR(15), COALESCE(s.active,TRUE)::BOOLEAN,
        COALESCE(s.salary_per_shift,0)::NUMERIC(10,2), s.joining_date::DATE,
        COALESCE(ps.shifts_completed, 0)::BIGINT AS shift_count,
        COALESCE(ps.salary_due, 0)::NUMERIC(15,2), COALESCE(ps.salary_paid, 0)::NUMERIC(15,2),
        EXISTS(SELECT 1 FROM gate_access ga WHERE ga.entity_id=s.id AND ga.role='SEC' AND ga.time_out IS NULL)::BOOLEAN AS gate_pass
    FROM security_staff s
    LEFT JOIN users u ON u.linked_id = s.id AND u.role = 'security'
    LEFT JOIN pay_sum ps ON ps.staff_id = s.id
    WHERE s.society_id = p_society_id
      AND (p_search IS NULL OR s.name ILIKE '%'||p_search||'%')
    ORDER BY s.name;
END;
$$;

-- SECTION 10: NAMED RECEIVABLES / payables
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_receivables_named CASCADE;

CREATE OR REPLACE FUNCTION fn_receivables_named(
    p_society_id  INT, p_search TEXT DEFAULT NULL, p_status TEXT DEFAULT NULL,
    p_entity_id   INT DEFAULT NULL, p_entity_role TEXT DEFAULT NULL,
    p_date_from   DATE DEFAULT NULL, p_date_to DATE DEFAULT NULL
)
RETURNS TABLE (
    id INT, society_id INT, entity_id INT, role VARCHAR(10), entity_name TEXT,
    acc_id INT, account_name TEXT, interest_acc_id INT, interest_account_name TEXT,
    description TEXT, period_month DATE, bill_group_id UUID,
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
        r.description::TEXT, r.period_month::DATE, r.bill_group_id::UUID,
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
      AND (p_date_from IS NULL OR r.period_month >= p_date_from)
      AND (p_date_to IS NULL OR r.period_month <= p_date_to)
    ORDER BY r.due_date ASC, r.created_at DESC;
END;
$$;

DROP FUNCTION IF EXISTS fn_payables_named CASCADE;

CREATE OR REPLACE FUNCTION fn_payables_named(
    p_society_id  INT, p_search TEXT DEFAULT NULL,
    p_status      TEXT DEFAULT NULL, p_entity_role TEXT DEFAULT NULL,
    p_entity_id   INT  DEFAULT NULL,
    p_shift_date_from DATE DEFAULT NULL, p_shift_date_to DATE DEFAULT NULL
)
RETURNS TABLE (
    id INT, society_id INT, entity_id INT, role VARCHAR(10), entity_name TEXT,
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
      AND (p_shift_date_from IS NULL OR p.shift_date >= p_shift_date_from)
      AND (p_shift_date_to IS NULL OR p.shift_date <= p_shift_date_to)
    ORDER BY p.due_date ASC, p.created_at DESC;
END;
$$;

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
    id INT, society_id INT, entity_id INT, role VARCHAR(10), entity_name TEXT,
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
    id INT, society_id INT, entity_id INT, role VARCHAR(10), entity_name TEXT,
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

-- Fixed (2026-08): p_financial_year was SMALLINT. Plain integer literals/
-- Python ints default to `integer` (int4), and int4→int2 is only an
-- "assignment" cast in Postgres, not "implicit" — so it's NOT applied
-- during function-call resolution. Every caller (loaders.py's plain `%s`
-- placeholders, and any raw `SELECT fn(...)` testing) hit
-- "function ... does not exist / no function matches" as a result. INT
-- is what a literal/Python int actually resolves to, so this — and every
-- other function in this FY-parameter family below — now takes INT.
DROP FUNCTION IF EXISTS fn_resolve_bf_amount_fy (INT, INT, SMALLINT) CASCADE;

CREATE OR REPLACE FUNCTION fn_resolve_bf_amount_fy(
    p_society_id     INT,
    p_account_id     INT,
    p_financial_year INT
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
    --
    -- Fixed (2026-08): cr_sum/dr_sum previously bucketed every transaction
    -- by the CHILD account's fixed drcr_account rather than that
    -- transaction's own entry_side — same class of bug as
    -- fn_accounts_list/fn_account_ledger_fy. For a Dr-natured child every
    -- transaction landed in dr_sum only (cr_sum always 0 for that
    -- account), so a receipt and a payment on the same account were
    -- indistinguishable and this fallback always summed gross activity
    -- instead of a true net pre-FY closing position.
    SELECT COALESCE(SUM(
        CASE WHEN a.drcr_account = 'Cr'
             THEN COALESCE(t.cr_sum, 0) - COALESCE(t.dr_sum, 0)
             ELSE COALESCE(t.dr_sum, 0) - COALESCE(t.cr_sum, 0)
        END
    ), 0) INTO v_bf
    FROM accounts a
    LEFT JOIN (
        SELECT t.acc_id,
               SUM(t.amount) FILTER (WHERE t.entry_side = 'Cr') AS cr_sum,
               SUM(t.amount) FILTER (WHERE t.entry_side = 'Dr') AS dr_sum
        FROM transactions t
        WHERE t.status = 'paid' AND t.trx_date < v_fy_start
        GROUP BY t.acc_id
    ) t ON t.acc_id = a.id
    WHERE a.parent_account_id = p_account_id AND a.society_id = p_society_id;
 
    RETURN COALESCE(v_bf, 0);
END;
$$;

-- SECTION 4: DEPRECIATION CALCULATION
-- Full-year depreciation on brought-forward WDV; half-year depreciation
-- on assets purchased on/after 1-Sep of the financial year (per spec:
-- "Half depreciation if asset date > 1 Sep of the year").
-- ════════════════════════════════════════════════════════════════

-- Fixed (2026-08): same SMALLINT->INT fix as fn_resolve_bf_amount_fy
-- above, same reason — plain integer literals/Python ints don't
-- implicitly cast to smallint for function-call resolution.
DROP FUNCTION IF EXISTS fn_account_depreciation (INT, INT, SMALLINT) CASCADE;

CREATE OR REPLACE FUNCTION fn_account_depreciation(
    p_society_id     INT,
    p_account_id     INT,
    p_financial_year INT
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

-- fn_account_depreciation_split
-- ===============================
-- Same three components fn_account_depreciation sums into one total, but
-- returned as (full_amount, half_amount) instead — for
-- fn_account_ledger_fy's ledger display, which shows these as two
-- distinct rows ('Full Depreciation' on opening WDV + pre-1-Sep
-- additions, 'Half post-30Sep Depreciation' on post-1-Sep additions)
-- rather than one combined figure. full_amount + half_amount always
-- equals fn_account_depreciation's own total for the same arguments —
-- this doesn't recompute the total differently, just doesn't collapse
-- the two rates together before returning.
--
-- fn_account_depreciation itself is left as a single-total function
-- rather than changed to return this same pair, since its 3 existing
-- call sites (fn_fy_closing_report, fn_trial_balance, fn_balance_sheet)
-- all consume it as a plain scalar in a SUM/aggregate context, not
-- something that would benefit from the split.
DROP FUNCTION IF EXISTS fn_account_depreciation_split (INT, INT, INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_account_depreciation_split(
    p_society_id     INT,
    p_account_id     INT,
    p_financial_year INT
)
RETURNS TABLE (full_amount NUMERIC(15,2), half_amount NUMERIC(15,2))
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_dep_pct      NUMERIC(5,2);
    v_is_dep       BOOLEAN;
    v_opening_wdv  NUMERIC(15,2);
    v_dep_opening  NUMERIC(15,2) := 0;
    v_dep_full_additions NUMERIC(15,2) := 0;
    v_dep_half_additions NUMERIC(15,2) := 0;
    v_half_cutoff  DATE := MAKE_DATE(p_financial_year, 9, 1);
    v_fy_start     DATE := MAKE_DATE(p_financial_year, 4, 1);
    v_fy_end       DATE := MAKE_DATE(p_financial_year + 1, 3, 31);
BEGIN
    SELECT depreciation_percent, is_depreciable
      INTO v_dep_pct, v_is_dep
      FROM accounts WHERE id = p_account_id AND society_id = p_society_id;

    IF NOT FOUND OR NOT COALESCE(v_is_dep, FALSE) OR COALESCE(v_dep_pct, 100) >= 100 THEN
        RETURN QUERY SELECT 0::NUMERIC(15,2), 0::NUMERIC(15,2);
        RETURN;
    END IF;

    v_opening_wdv := fn_resolve_bf_amount_fy(p_society_id, p_account_id, p_financial_year);
    v_dep_opening := GREATEST(v_opening_wdv, 0) * v_dep_pct / 100.0;

    SELECT COALESCE(SUM(purchase_value * v_dep_pct / 100.0), 0)
    INTO v_dep_full_additions
    FROM assets
    WHERE society_id = p_society_id AND acc_id = p_account_id
      AND purchase_date BETWEEN v_fy_start AND v_fy_end
      AND purchase_date < v_half_cutoff
      AND disposed = FALSE;

    SELECT COALESCE(SUM(purchase_value * v_dep_pct / 100.0 * 0.5), 0)
    INTO v_dep_half_additions
    FROM assets
    WHERE society_id = p_society_id AND acc_id = p_account_id
      AND purchase_date BETWEEN v_fy_start AND v_fy_end
      AND purchase_date >= v_half_cutoff
      AND disposed = FALSE;

    RETURN QUERY SELECT
        ROUND(v_dep_opening + v_dep_full_additions, 2)::NUMERIC(15,2),
        ROUND(v_dep_half_additions, 2)::NUMERIC(15,2);
END;
$$;

-- SECTION 5: LEDGER v2 — FY-aware BF + depreciation-aware closing
-- ════════════════════════════════════════════════════════════════

-- Fixed (2026-08): same SMALLINT->INT fix — this backs the live Admin
-- Ledger screen (via loaders.py, plain `%s` placeholders passing a
-- Python int), which was silently broken by this exact type-resolution
-- issue every time it was called.
DROP FUNCTION IF EXISTS fn_account_ledger_fy (INT, INT, INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_account_ledger_fy(
    p_society_id     INT,
    p_account_id     INT,
    p_financial_year INT
)
RETURNS TABLE (
    row_date        DATE,
    account_name    TEXT,
    entity_name     TEXT,
    particulars     TEXT,
    cb_folio        INT,
    debit           NUMERIC(15,2),
    credit          NUMERIC(15,2),
    running_balance NUMERIC(15,2),
    row_type        TEXT,
    parent_name     TEXT
) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_acc          RECORD;
    v_fy_start     DATE := MAKE_DATE(p_financial_year, 4, 1);
    v_fy_end       DATE := MAKE_DATE(p_financial_year + 1, 3, 31);
    v_bf           NUMERIC(15,2);
    v_bf_drcr      VARCHAR(2);
    v_balance      NUMERIC(15,2);
    v_dep_acc_id   INT;
    v_dep_full     NUMERIC(15,2) := 0;
    v_dep_half     NUMERIC(15,2) := 0;
    v_dep_acc_tab  TEXT;
    v_dep_total    NUMERIC(15,2) := 0;
    v_running_balance NUMERIC(15,2);
    v_final_balance NUMERIC(15,2);
    v_transfer_amt  NUMERIC(15,2);
BEGIN
    SELECT a.id, a.name, a.drcr_account, a.is_depreciable, a.depreciation_percent, a.parent_account_id,
           a.has_bf, a.tab_name, COALESCE(p.tab_name, p.name, '--') AS parent_name
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

    -- CiH special case (2026-08): CiH no longer has ANY transaction rows
    -- of its own — cash-mode legs post directly to the real
    -- income/expense/asset account (see fn_resolve_bank_leg), so the
    -- itemized-transaction loop below would find nothing and the closing
    -- transfer would silently equal just the opening balance, missing a
    -- full year of cash movement. Per spec, CiH's ledger has exactly TWO
    -- records: the B/F row (opening, same as any other has_bf account)
    -- and a C/F row using fn_cih_balance_asof — the same shared formula
    -- the Cashbook card's CIH Running column uses — so this figure can
    -- never drift out of sync with what the Cashbook itself shows.
    -- Returned unconditionally (not gated on <> 0 like the generic
    -- closing row below) since "two records, always" is the spec, not
    -- "two records unless the balance happens to net to zero".
    IF v_acc.tab_name = 'CiH' THEN
        IF v_bf <> 0 THEN
            -- Fixed (2026-08): row_date is declared DATE, but
            -- `DATE - INTERVAL` evaluates to timestamp without time zone
            -- in Postgres, not date — RETURN QUERY enforces an exact type
            -- match against the RETURNS TABLE signature (no implicit
            -- narrowing cast), so this raised "structure of query does
            -- not match function result type ... Returned type timestamp
            -- without time zone does not match expected type date".
            -- Every account with has_bf=TRUE hits this same expression
            -- (see the identical fix a few lines below); CapAc surfaced
            -- it first only because it's the account most people click
            -- first with a nonzero seeded BF.
            RETURN QUERY SELECT
                (v_fy_start - INTERVAL '1 day')::DATE, COALESCE(v_acc.tab_name::TEXT, v_acc.name::TEXT), ''::TEXT, 'B/F'::TEXT,
                NULL::INT,
                CASE WHEN v_bf_drcr = 'Dr' THEN v_bf ELSE 0 END,
                CASE WHEN v_bf_drcr = 'Cr' THEN v_bf ELSE 0 END,
                v_balance, 'bf'::TEXT, v_acc.parent_name::TEXT;
        END IF;

        v_final_balance := fn_cih_balance_asof(p_society_id, v_fy_end);
        -- Fixed (2026-08): same signed-value-into-a-fixed-column bug as
        -- the generic closing row below — always dropped v_final_balance
        -- straight into Credit, so cash run overdrawn (a genuine
        -- possibility once cash-mode transactions can post to any
        -- account) showed as a negative Credit instead of flipping to
        -- Debit with the magnitude.
        RETURN QUERY SELECT
            v_fy_end, COALESCE(v_acc.tab_name::TEXT, v_acc.name::TEXT), ''::TEXT,
            ('C/F -> ' || COALESCE(v_acc.parent_name, 'Parent'))::TEXT,
            NULL::INT,
            CASE WHEN v_final_balance < 0 THEN ABS(v_final_balance) ELSE 0::NUMERIC(15,2) END,
            CASE WHEN v_final_balance >= 0 THEN v_final_balance ELSE 0::NUMERIC(15,2) END,
            0::NUMERIC(15,2), 'closing'::TEXT, v_acc.parent_name::TEXT;
        RETURN;
    END IF;

    -- Fixed (2026-08): gated on accounts.has_bf — previously this emitted a
    -- B/F row for ANY account with a nonzero fn_resolve_bf_amount_fy
    -- result, including has_bf=FALSE P&L leaves that resolve a nonzero
    -- figure purely from that function's child-account-sum fallback (see
    -- fn_resolve_bf_amount_fy's comment) rather than a real carried
    -- balance. has_bf=TRUE is what actually marks an account as carrying
    -- its own balance forward across FYs (CapAc, bank/cash accounts,
    -- depreciable assets, Sundry Debtors, etc. — see the ACCOUNTS seed
    -- table); has_bf=FALSE accounts (expense/income leaves) should never
    -- show a B/F line of their own.
    IF v_acc.has_bf AND v_bf <> 0 THEN
        -- Fixed (2026-08): same DATE-vs-timestamp cast issue as the CiH
        -- branch above — see that comment.
        RETURN QUERY SELECT
            (v_fy_start - INTERVAL '1 day')::DATE, COALESCE(v_acc.tab_name::TEXT, v_acc.name::TEXT), ''::TEXT, 'Balance B/F'::TEXT,
            NULL::INT,
            CASE WHEN v_bf_drcr = 'Dr' THEN v_bf ELSE 0 END,
            CASE WHEN v_bf_drcr = 'Cr' THEN v_bf ELSE 0 END,
            v_balance, 'bf'::TEXT, v_acc.parent_name::TEXT;
    END IF;

    -- Transaction rows, running balance
    RETURN QUERY
    WITH txns AS (
        SELECT t.trx_date,
               t.acc_particulars::TEXT,
               CASE 
                   WHEN EXTRACT(MONTH FROM t.trx_date) >= 4 
                   THEN EXTRACT(MONTH FROM t.trx_date) - 3 
                   ELSE EXTRACT(MONTH FROM t.trx_date) + 9 
               END::INT AS cb_folio,
               COALESCE(SUM(t.amount) FILTER (WHERE t.entry_side = 'Dr'), 0) AS debit,
               COALESCE(SUM(t.amount) FILTER (WHERE t.entry_side = 'Cr'), 0) AS credit,
               CASE v_acc.drcr_account
                   WHEN 'Cr' THEN COALESCE(SUM(CASE WHEN t.entry_side = 'Cr' THEN t.amount
                                                    WHEN t.entry_side = 'Dr' THEN -t.amount
                                                    ELSE 0 END), 0)
                   ELSE COALESCE(SUM(CASE WHEN t.entry_side = 'Dr' THEN t.amount
                                         WHEN t.entry_side = 'Cr' THEN -t.amount
                                         ELSE 0 END), 0)
               END AS net_delta,
               COALESCE(MAX(ap.flat_number), MAX(v.name), MAX(s.name), '')::TEXT AS entity_name
        FROM transactions t
        LEFT JOIN apartments ap ON ap.id = t.entity_id AND ap.society_id = t.society_id AND t.role = 'apartment'
        LEFT JOIN vendors v ON v.id = t.entity_id AND v.society_id = t.society_id AND t.role = 'vendor'
        LEFT JOIN security_staff s ON s.id = t.entity_id AND s.society_id = t.society_id AND t.role = 'security'
        WHERE t.acc_id = p_account_id AND t.society_id = p_society_id AND t.status = 'paid'
          AND t.trx_date BETWEEN v_fy_start AND v_fy_end
        GROUP BY t.trx_date, t.acc_particulars, v_acc.drcr_account
        ORDER BY t.trx_date ASC
    )
    SELECT
        tx.trx_date, COALESCE(v_acc.tab_name::TEXT, v_acc.name::TEXT), tx.entity_name, tx.acc_particulars, tx.cb_folio,
        tx.debit, tx.credit,
        v_bf + SUM(tx.net_delta) OVER (ORDER BY tx.trx_date, tx.acc_particulars ROWS UNBOUNDED PRECEDING),
        'txn'::TEXT, v_acc.parent_name::TEXT
    FROM txns tx;

    -- Final balance before depreciation/closing — net movement is
    -- per-transaction entry_side, flipped into the account's own natural
    -- direction (same fix as fn_accounts_list / fn_account_profile above).
    -- Previously this joined a.drcr_account (constant for every row on
    -- this account, since t.acc_id = p_account_id throughout), so the
    -- inner CASE was always true or always false and it degenerated into
    -- an unsigned SUM(t.amount) — every transaction added, none ever
    -- netted against the other side, regardless of direction.
    SELECT v_bf + COALESCE(
        CASE v_acc.drcr_account
            WHEN 'Cr' THEN SUM(CASE WHEN t.entry_side='Cr' THEN t.amount
                                     WHEN t.entry_side='Dr' THEN -t.amount
                                     ELSE 0 END)
            ELSE SUM(CASE WHEN t.entry_side='Dr' THEN t.amount
                          WHEN t.entry_side='Cr' THEN -t.amount
                          ELSE 0 END)
        END, 0)
    INTO v_final_balance
    FROM transactions t
    WHERE t.acc_id = p_account_id AND t.society_id = p_society_id AND t.status = 'paid'
      AND t.trx_date BETWEEN v_fy_start AND v_fy_end;

    v_transfer_amt := v_final_balance;

    -- Depreciation (only for is_depreciable accounts with % < 100)
    IF COALESCE(v_acc.is_depreciable, FALSE) AND COALESCE(v_acc.depreciation_percent, 100) < 100 THEN
        SELECT full_amount + half_amount
          INTO v_dep_total
          FROM fn_account_depreciation_split(p_society_id, p_account_id, p_financial_year);

        IF v_dep_total > 0 THEN
            SELECT id INTO v_dep_acc_id FROM accounts
            WHERE society_id = p_society_id AND tab_name = 'Dep' LIMIT 1;

            v_dep_acc_tab := COALESCE((SELECT tab_name FROM accounts WHERE id = v_dep_acc_id), 'Dep');
            v_running_balance := v_final_balance - v_dep_total;
            RETURN QUERY SELECT
                v_fy_end, COALESCE(v_acc.tab_name::TEXT, v_acc.name::TEXT), ''::TEXT,
                ('Depreciation @ ' || v_acc.depreciation_percent || '% -> Dep A/c')::TEXT,
                NULL::INT,
                CASE WHEN v_acc.drcr_account = 'Cr' THEN v_dep_total ELSE 0::NUMERIC(15,2) END,
                CASE WHEN v_acc.drcr_account = 'Dr' THEN v_dep_total ELSE 0::NUMERIC(15,2) END,
                v_running_balance, 'depreciation'::TEXT, v_dep_acc_tab;
            v_transfer_amt := v_final_balance - v_dep_total;
        END IF;
    END IF;

    -- Closing row: transfer remainder to parent, balance -> 0
    --
    -- Fixed (2026-08): flipped Debit/Credit — the "zeroing" figure that
    -- closes an account out to carry its balance to its parent is the
    -- OPPOSITE of the account's own natural side, same as any standard
    -- closing entry (crediting a Dr-natured account's ledger reduces its
    -- running balance to 0; debiting it would have pushed the balance
    -- further AWAY from zero, reading as a fourth same-side entry rather
    -- than a close-out). This does not change the account's own nature
    -- or the actual value carried forward — brought_forward next FY and
    -- the parent's own rollup are untouched either way — it only fixes
    -- which column this display row's figure lands in, matching
    -- CB2024-2025.xlsx's BkAc->CurAs example (a Dr-natured BkAc's C/F row
    -- shows in the Credit column).
    -- Fixed (2026-08): v_transfer_amt was assumed to always be
    -- non-negative in the account's own natural direction, so this CASE
    -- just dropped the raw signed value straight into whichever column
    -- drcr_account picked, unconditionally. That breaks whenever an
    -- account's balance for the year actually sits on the OPPOSITE side
    -- from its own nature (e.g. a Dr-natured expense account net-
    -- credited, or a Dr-natured cash-derived account run overdrawn) —
    -- v_transfer_amt comes out negative there, and it landed in the
    -- column as a literal negative number instead of flipping columns
    -- with its magnitude, same failure mode as fn_fy_closing_report's
    -- display_side/display_amount was built to avoid. Fixed the same
    -- way: derive which column from the SIGN of v_transfer_amt (XORed
    -- against drcr_account, since a natural-side-negative balance is
    -- actually sitting on the opposite side), and use ABS() so neither
    -- column ever shows a signed number.
    IF v_transfer_amt <> 0 THEN
        RETURN QUERY SELECT
            v_fy_end, COALESCE(v_acc.tab_name::TEXT, v_acc.name::TEXT), ''::TEXT,
            ('Balance C/F -> ' || COALESCE(v_acc.parent_name, 'Parent'))::TEXT,
            NULL::INT,
            CASE WHEN (v_acc.drcr_account = 'Cr') = (v_transfer_amt >= 0)
                 THEN ABS(v_transfer_amt) ELSE 0::NUMERIC(15,2) END,
            CASE WHEN (v_acc.drcr_account = 'Dr') = (v_transfer_amt >= 0)
                 THEN ABS(v_transfer_amt) ELSE 0::NUMERIC(15,2) END,
            0::NUMERIC(15,2), 'closing'::TEXT, v_acc.parent_name::TEXT;
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

-- SECTION 12: CASHBOOK (paired Cr/Dr over transactions table)
-- fn_cashbook_paired (v1) and fn_cashbook_paired_v2 have both been
-- retired — v2's replacement (v3, below) is the only cashbook function
-- left in this schema. loaders.py and cashbook_export.py both call it.
-- (NOTE 2026-08: this comment previously still said "v2" here — v2 was
-- already gone from this schema file with nothing left to CREATE it, so
-- that was stale/misleading, not just imprecise. loaders.py's `cashbook`
-- entity handler had in fact been left calling fn_cashbook_paired_v2
-- directly — a function that doesn't exist in the database — which broke
-- the live Cashbook list view for every portal. Fixed alongside this
-- comment; see loaders.py's `entity == "cashbook"` branches.)
DROP FUNCTION IF EXISTS fn_cashbook_paired_v3 (
    INT,
    INT,
    TEXT,
    TEXT,
    DATE,
    DATE
) CASCADE;

-- fn_cashbook_paired_v3
-- ======================
-- entry_side is the single source of truth for which side of the
-- cashbook a leg lands on: entry_side='Cr' (money in) -> Cr Account/Cr
-- Cash/Cr Chq columns, entry_side='Dr' (money out) -> Dr Account/Dr
-- Cash/Dr Chq columns — never a.drcr_account (the account's own natural
-- type), which is what let a non-natural-direction leg (refund,
-- correction, TDS split) land on the wrong side or vanish from the join.
--
-- Column contract rewritten (2026-08) to match CB2024-2025.xlsx's
-- Cr Account / Dr Account layout directly, simplified per spec: no
-- separate Cash1/Cash2/Cash Total columns (the app only ever has one
-- cash leg per side), one CIH Running column (not separate "Cash
-- Receipts Running Total" / "Cash Payments Running Total" — those are
-- workbook scratch columns, not something worth storing). Cr LF / Dr LF
-- (ledger folio) are deliberately NOT included yet — added once the
-- Ledger Index/pagination exists to assign folio numbers against.
--
-- Fixed (2026-08): every money-writing function (fn_save_receipt,
-- fn_save_expense, fn_buy_asset, fn_verify_payment, ...) now writes a
-- bank/cash-completing leg ONLY for non-cash modes (see
-- fn_resolve_bank_leg) — a cash-mode transaction has exactly ONE leg,
-- posted to the real income/expense/asset account, never to CiH itself.
-- CiH has NO transaction rows of its own any more. That means:
--   - cr_rows/dr_rows below need no CiH-exclusion filter (there is
--     nothing to exclude — a cash-mode journal simply has no counterpart
--     leg to pair against, and naturally lands as a single-sided row via
--     the FULL OUTER JOIN below, same as CB2024-2025.xlsx's blank-side
--     daily rows).
--   - cih_running (below) is a plain cumulative sum of every row's Cr
--     Cash minus Dr Cash — correct with no double-counting, since each
--     cash-mode leg now contributes to exactly one side of exactly one
--     row, never both.
--   - Non-cash (cheque/upi/card/bank/crypto) legs still show BOTH
--     accounts on one row (e.g. Cr SBI paired with Dr Salary) — those
--     Cash columns stay 0 either way (informational, in the Chq columns
--     only) since they never touched physical cash-in-hand.
--
-- Opening balance is resolved via fn_cih_balance_asof (the same shared
-- formula fn_cashbook_month_page and fn_account_ledger_fy's CiH branch
-- use), rather than re-deriving brought_forward + cumulative movement
-- independently here.
CREATE OR REPLACE FUNCTION fn_cashbook_paired_v3(
    p_society_id  INT,
    p_entity_id   INT  DEFAULT NULL,
    p_entity_role TEXT DEFAULT NULL,
    p_search      TEXT DEFAULT NULL,
    p_start_date  DATE DEFAULT NULL,
    p_end_date    DATE DEFAULT NULL
)
RETURNS TABLE (
    row_date        DATE,
    cr_acc_id       INT, cr_account_name TEXT, cr_entity_name TEXT, cr_particulars TEXT,
    cr_cash NUMERIC(15,2), cr_chq NUMERIC(15,2),
    dr_acc_id       INT, dr_account_name TEXT, dr_entity_name TEXT, dr_particulars TEXT,
    dr_cash NUMERIC(15,2), dr_chq NUMERIC(15,2),
    cih_running     NUMERIC(15,2)
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_opening_balance NUMERIC(15,2);
    v_range_start      DATE;
BEGIN
    -- Same range-start resolution fn_cih_balance_asof's call below already
    -- used inline; captured into a variable so the synthetic B/F row (see
    -- header comment) can reuse the exact same date without re-deriving it.
    v_range_start := COALESCE(p_start_date, MAKE_DATE(fn_current_financial_year()::INT, 4, 1));

    -- Fixed: was fn_cih_balance_asof(society_id, v_range_start - 1 day) --
    -- subtracting a day to get "the balance right before this range"
    -- crosses a fiscal-year boundary whenever v_range_start is a FY's own
    -- first day (1-Apr): e.g. v_range_start=2026-04-01 minus a day is
    -- 2026-03-31, which fn_cih_balance_asof's OWN (correct, in isolation)
    -- FY-resolution maps to FY2025 — a fiscal year this system never
    -- seeds a brought_forward row for, since each FY's BF is entered
    -- directly (there's no assumption that FY2025 "closed into" FY2026's
    -- BF). That silently returned 0 instead of FY2026's real seeded BF,
    -- which is exactly why the B/F row could show ₹0.00 while the C/F row
    -- (correctly calling fn_cih_balance_asof(v_end_date), never crossing
    -- a boundary since a FY's own end date always resolves to that same
    -- FY) showed the right closing figure a full BF-amount higher.
    --
    -- Fixed by calling fn_cih_balance_asof with v_range_start itself
    -- (always resolves to the FY that owns it — no boundary-crossing
    -- risk, since a FY's own first day is unambiguously part of that FY)
    -- and then subtracting off any transactions dated exactly on
    -- v_range_start, so the result is still "balance strictly before this
    -- range's own transactions" rather than double-counting whatever
    -- happened on v_range_start itself into both the B/F figure and that
    -- day's own visible row.
    v_opening_balance := fn_cih_balance_asof(p_society_id, v_range_start)
        - COALESCE((
            SELECT SUM(CASE WHEN t.entry_side = 'Cr' THEN t.amount
                             WHEN t.entry_side = 'Dr' THEN -t.amount
                             ELSE 0 END)
            FROM transactions t
            WHERE t.society_id = p_society_id AND t.status = 'paid' AND t.mode = 'cash'
              AND t.trx_date = v_range_start
        ), 0);

    RETURN QUERY
    WITH cr_rows AS (
        -- entry_side = 'Cr' means this leg is the receipt (money-in) side.
        -- mode <> 'journal' excludes pure book entries (e.g. depreciation)
        -- from the Cashbook entirely — they involve no cash or bank
        -- movement at all, so they belong only on the relevant accounts'
        -- Ledger sheets (fn_account_ledger_fy), never here. Fixed (2026-08):
        -- previously such entries had no honest mode of their own and were
        -- posted with mode='cash' (see database/seed.py), which meant this
        -- CASE only ever routed them into the Cash vs Chq/UPI column split
        -- — never excluded them — so a depreciation journal displayed as a
        -- phantom cash transaction in the Cashbook.
        SELECT t.id, t.journal_id, t.trx_date,
               a.id AS acc_id, COALESCE(a.tab_name, a.name)::TEXT AS account_name,
               COALESCE(ap.flat_number, v.name, s.name, '')::TEXT AS entity_name,
               COALESCE(t.acc_particulars,'')::TEXT AS particulars,
               CASE WHEN t.mode = 'cash' THEN t.amount ELSE 0 END AS cash_amt,
               CASE WHEN t.mode <> 'cash' THEN t.amount ELSE 0 END AS chq_amt,
               ROW_NUMBER() OVER (PARTITION BY COALESCE(t.journal_id, -t.id) ORDER BY t.id) AS rn
        FROM transactions t
        JOIN accounts a ON a.id = t.acc_id
        LEFT JOIN apartments ap ON ap.id = t.entity_id AND ap.society_id = p_society_id AND t.role = 'apartment'
        LEFT JOIN vendors v ON v.id = t.entity_id AND v.society_id = p_society_id AND t.role = 'vendor'
        LEFT JOIN security_staff s ON s.id = t.entity_id AND s.society_id = p_society_id AND t.role = 'security'
        WHERE t.society_id = p_society_id AND t.status = 'paid'
          AND t.entry_side = 'Cr'
          AND t.mode <> 'journal'
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
        -- entry_side = 'Dr' means this leg is the payment (money-out) side.
        -- mode <> 'journal': see cr_rows above — same exclusion, same reason.
        SELECT t.id, t.journal_id, t.trx_date,
               a.id AS acc_id, COALESCE(a.tab_name, a.name)::TEXT AS account_name,
               COALESCE(ap.flat_number, v.name, s.name, '')::TEXT AS entity_name,
               COALESCE(t.acc_particulars,'')::TEXT AS particulars,
               CASE WHEN t.mode = 'cash' THEN t.amount ELSE 0 END AS cash_amt,
               CASE WHEN t.mode <> 'cash' THEN t.amount ELSE 0 END AS chq_amt,
               ROW_NUMBER() OVER (PARTITION BY COALESCE(t.journal_id, -t.id) ORDER BY t.id) AS rn
        FROM transactions t
        JOIN accounts a ON a.id = t.acc_id
        LEFT JOIN apartments ap ON ap.id = t.entity_id AND ap.society_id = p_society_id AND t.role = 'apartment'
        LEFT JOIN vendors v ON v.id = t.entity_id AND v.society_id = p_society_id AND t.role = 'vendor'
        LEFT JOIN security_staff s ON s.id = t.entity_id AND s.society_id = p_society_id AND t.role = 'security'
        WHERE t.society_id = p_society_id AND t.status = 'paid'
          AND t.entry_side = 'Dr'
          AND t.mode <> 'journal'
          AND (p_start_date IS NULL OR t.trx_date >= p_start_date)
          AND (p_end_date IS NULL OR t.trx_date <= p_end_date)
          AND (p_entity_id IS NULL OR t.entity_id = p_entity_id)
          AND (p_entity_role IS NULL OR
               (p_entity_role = 'apartment' AND ap.id IS NOT NULL) OR
               (p_entity_role = 'vendor' AND v.id IS NOT NULL) OR
               (p_entity_role = 'security' AND s.id IS NOT NULL))
          AND (p_search IS NULL OR a.name ILIKE '%'||p_search||'%' OR t.acc_particulars ILIKE '%'||p_search||'%')
    ),
    paired AS (
        SELECT COALESCE(c.trx_date, d.trx_date) AS row_date,
               COALESCE(c.journal_id, -c.id, -d.id) AS pair_key,
               c.acc_id AS cr_acc_id, c.account_name AS cr_account_name,
               c.entity_name AS cr_entity_name, c.particulars AS cr_particulars,
               c.cash_amt AS cr_cash, c.chq_amt AS cr_chq,
               d.acc_id AS dr_acc_id, d.account_name AS dr_account_name,
               d.entity_name AS dr_entity_name, d.particulars AS dr_particulars,
               d.cash_amt AS dr_cash, d.chq_amt AS dr_chq
        FROM cr_rows c
        FULL OUTER JOIN dr_rows d
          -- Pair leg N on the Cr side with leg N on the Dr side, within the
          -- same journal_id. A cash-mode leg has no counterpart at all in
          -- its own journal any more (see header comment) and simply falls
          -- through to the unmatched branch of this FULL OUTER JOIN, one
          -- side blank — exactly CB2024-2025.xlsx's blank-side daily rows.
          -- For an N Dr : 1 Cr journal (e.g. a non-cash salary's Cr Bank +
          -- Dr Salary + Dr TDStoIT), only rn=1 on each side finds a
          -- same-rn counterpart; rn=2+ has no match and is preserved as
          -- its own row, other side blank — no extra WHERE filtering,
          -- since that risks re-dropping legitimate uneven-leg rows.
          ON COALESCE(c.journal_id, -c.id) = COALESCE(d.journal_id, -d.id)
         AND c.rn = d.rn
    ),
    real_rows AS (
        SELECT p.row_date, p.pair_key, p.cr_acc_id, p.cr_account_name, p.cr_entity_name, p.cr_particulars,
               p.cr_cash, p.cr_chq, p.dr_acc_id, p.dr_account_name, p.dr_entity_name, p.dr_particulars,
               p.dr_cash, p.dr_chq,
               v_opening_balance + SUM(COALESCE(p.cr_cash,0) - COALESCE(p.dr_cash,0))
                   OVER (ORDER BY p.row_date, p.pair_key ROWS UNBOUNDED PRECEDING) AS cih_running,
               1 AS sort_bucket
        FROM paired p
    ),
    -- Fixed (2026-08): CiH's B/F was computed (v_opening_balance, above)
    -- and silently folded into every real row's cih_running total, but
    -- never itself surfaced as a visible row — every OTHER account's B/F
    -- lives on that account's own Ledger sheet, but CiH's B/F belongs IN
    -- the Cashbook (it has no transaction rows of its own to build a
    -- Ledger view from at all — see fn_resolve_bank_leg / the CiH branch
    -- in fn_account_ledger_fy). bf_row/cf_row below bracket real_rows the
    -- same way _shape_cashbook_month_rows() already brackets
    -- fn_cashbook_month_page's output for the Month-Selector view — and,
    -- since bf_row sorts first and cf_row sorts last (sort_bucket 0/2),
    -- the caller's existing external LIMIT/OFFSET pagination naturally
    -- shows B/F only on page 1 and C/F only on the last page, with no
    -- pagination-side changes needed.
    bf_row AS (
        SELECT v_range_start AS row_date, 0 AS pair_key,
               NULL::INT AS cr_acc_id, 'CiH'::TEXT AS cr_account_name, NULL::TEXT AS cr_entity_name, 'B/F'::TEXT AS cr_particulars,
               v_opening_balance AS cr_cash, NULL::NUMERIC(15,2) AS cr_chq,
               NULL::INT AS dr_acc_id, NULL::TEXT AS dr_account_name, NULL::TEXT AS dr_entity_name, NULL::TEXT AS dr_particulars,
               NULL::NUMERIC(15,2) AS dr_cash, NULL::NUMERIC(15,2) AS dr_chq,
               v_opening_balance AS cih_running,
               0 AS sort_bucket
    ),
    cf_row AS (
        SELECT p_end_date AS row_date, 0 AS pair_key,
               NULL::INT AS cr_acc_id, NULL::TEXT AS cr_account_name, NULL::TEXT AS cr_entity_name, NULL::TEXT AS cr_particulars,
               NULL::NUMERIC(15,2) AS cr_cash, NULL::NUMERIC(15,2) AS cr_chq,
               NULL::INT AS dr_acc_id, 'CiH'::TEXT AS dr_account_name, NULL::TEXT AS dr_entity_name, 'C/F'::TEXT AS dr_particulars,
               NULL::NUMERIC(15,2) AS dr_cash, NULL::NUMERIC(15,2) AS dr_chq,
               fn_cih_balance_asof(p_society_id, p_end_date) AS cih_running,
               2 AS sort_bucket
        WHERE p_end_date IS NOT NULL
    )
    -- Fixed: unqualified column names here were ambiguous between the
    -- all_rows subquery's own columns and the RETURNS TABLE output
    -- columns of the same name, which PL/pgSQL implicitly declares as
    -- variables in scope for the whole function body ("row_date" could
    -- mean either) — explicit all_rows. qualification on every reference,
    -- including inside ORDER BY, resolves it.
    SELECT all_rows.row_date, all_rows.cr_acc_id, all_rows.cr_account_name,
           all_rows.cr_entity_name, all_rows.cr_particulars,
           all_rows.cr_cash, all_rows.cr_chq, all_rows.dr_acc_id, all_rows.dr_account_name,
           all_rows.dr_entity_name, all_rows.dr_particulars,
           all_rows.dr_cash, all_rows.dr_chq, all_rows.cih_running
    FROM (
        SELECT * FROM bf_row
        UNION ALL
        SELECT * FROM real_rows
        UNION ALL
        SELECT * FROM cf_row
    ) all_rows
    ORDER BY all_rows.sort_bucket, all_rows.row_date, all_rows.pair_key;
END;
$$;

-- fn_cashbook_month_page
-- =======================
-- Paginated single-month cashbook feed for the Financials > KPI (open
-- Cashbook) card: Month Selector + Financial Year Selector in the header,
-- rows paginated underneath, with 'CiH' B/F on the first entry and 'CiH'
-- C/F on the last entry of the month per the CB2024-2025.xlsx reference
-- layout — everything else is a plain cash-increase/decrease row.
--
-- Built on the same cr_rows/dr_rows/paired pattern as
-- fn_cashbook_paired_v3 (entry_side-driven pairing — see that function's
-- header comment), re-scoped to one calendar month so pagination doesn't
-- have to slice a full-FY result set app-side.
--
-- Column contract matches fn_cashbook_paired_v3's cr_/dr_ rename
-- (2026-08) — see that function's header for the full rationale.
--
-- month_opening_balance / month_closing_balance are returned on EVERY row
-- (and on the synthetic empty-month row below), so the card can display
-- the calculated B/F and C/F regardless of which page is currently in
-- view, per spec — not just on page 1 / the last page. cih_running is
-- computed over the FULL month before OFFSET/LIMIT is applied, so
-- page 2+ continues the running total correctly instead of restarting
-- from month_opening_balance at the top of the page.
--
-- Calendar/FY mapping: p_month is a plain calendar month (1-12); month>=4
-- belongs to calendar year p_fy, month<4 belongs to p_fy+1 (e.g. FY2025
-- Jan = Jan 2026), computed once via a CASE rather than an incrementing
-- (month, year) loop variable — this is the class of bug flagged against
-- generate_cashbook_excel_fy's Dec->Jan rollover.
--
-- A month with zero transactions returns exactly one synthetic row (all
-- cr_/dr_ columns NULL, row_date = month_start, cih_running =
-- month_opening_balance = month_closing_balance, total_row_count = 0)
-- instead of an empty result set, so the card always has something to
-- render B/F and C/F from.
DROP FUNCTION IF EXISTS fn_cashbook_month_page (
    INT, INT, INT, INT, TEXT, INT, INT
) CASCADE;

CREATE OR REPLACE FUNCTION fn_cashbook_month_page(
    p_society_id  INT,
    p_fy          INT,
    p_month       INT,
    p_entity_id   INT  DEFAULT NULL,
    p_entity_role TEXT DEFAULT NULL,
    p_page        INT  DEFAULT 1,
    p_page_size   INT  DEFAULT 15
)
RETURNS TABLE (
    row_date               DATE,
    cr_acc_id               INT,
    cr_account_name          TEXT,
    cr_entity_name           TEXT,
    cr_particulars           TEXT,
    cr_cash                  NUMERIC(15,2),
    cr_chq                   NUMERIC(15,2),
    dr_acc_id                INT,
    dr_account_name          TEXT,
    dr_entity_name            TEXT,
    dr_particulars           TEXT,
    dr_cash                  NUMERIC(15,2),
    dr_chq                   NUMERIC(15,2),
    cih_running               NUMERIC(15,2),
    month_opening_balance    NUMERIC(15,2),
    month_closing_balance    NUMERIC(15,2),
    total_row_count          BIGINT,
    total_pages              INT,
    is_first_page             BOOLEAN,
    is_last_page              BOOLEAN
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_calendar_year   INT;
    v_month_start     DATE;
    v_month_end       DATE;
    v_month_opening   NUMERIC(15,2);
    v_month_closing   NUMERIC(15,2);
    v_total_rows      BIGINT;
    v_total_pages     INT;
    v_offset          INT;
BEGIN
    IF p_month IS NULL OR p_month NOT BETWEEN 1 AND 12 THEN
        RAISE EXCEPTION 'p_month must be between 1 and 12, got %', p_month;
    END IF;
    IF p_page IS NULL OR p_page < 1 THEN p_page := 1; END IF;
    IF p_page_size IS NULL OR p_page_size < 1 THEN p_page_size := 15; END IF;

    v_calendar_year := CASE WHEN p_month >= 4 THEN p_fy ELSE p_fy + 1 END;
    v_month_start   := make_date(v_calendar_year, p_month, 1);
    v_month_end     := (v_month_start + INTERVAL '1 month')::DATE;

    -- Fixed (2026-08): opening balance comes from fn_cih_balance_asof —
    -- same shared formula fn_cashbook_paired_v3 and fn_account_ledger_fy's
    -- CiH branch use, so all three can never drift out of sync with each
    -- other.
    --
    -- Fixed: was fn_cih_balance_asof(society_id, v_month_start - 1 day) —
    -- only actually wrong for April (p_month=4), where v_month_start is
    -- also the FY's own first day, so subtracting a day crosses into the
    -- PRIOR fiscal year (e.g. 2026-04-01 minus a day is 2026-03-31 =
    -- FY2025), which this system never seeds a brought_forward row for —
    -- each FY's BF is entered directly, with no assumption that the prior
    -- FY "closed into" this one. That silently returned 0 for April
    -- instead of the FY's real seeded BF. Every other month (May..Mar)
    -- was unaffected, since subtracting a day stays within the same FY.
    -- Same fix as fn_cashbook_paired_v3's opening-balance call above:
    -- call with v_month_start itself (always resolves to the FY that
    -- owns it) and subtract that day's own transactions back out, rather
    -- than asking for a date that can cross into a different FY.
    v_month_opening := fn_cih_balance_asof(p_society_id, v_month_start)
        - COALESCE((
            SELECT SUM(CASE WHEN t.entry_side = 'Cr' THEN t.amount
                             WHEN t.entry_side = 'Dr' THEN -t.amount
                             ELSE 0 END)
            FROM transactions t
            WHERE t.society_id = p_society_id AND t.status = 'paid' AND t.mode = 'cash'
              AND t.trx_date = v_month_start
        ), 0);

    CREATE TEMP TABLE _cb_month_rows ON COMMIT DROP AS
    WITH cr_rows AS (
        -- mode <> 'journal' excludes pure book entries (e.g. depreciation)
        -- from the Cashbook — see fn_cashbook_paired_v3's header comment.
        SELECT t.id, t.journal_id, t.trx_date,
               a.id AS acc_id, COALESCE(a.tab_name, a.name)::TEXT AS account_name,
               COALESCE(ap.flat_number, v.name, s.name, '')::TEXT AS entity_name,
               COALESCE(t.acc_particulars,'')::TEXT AS particulars,
               CASE WHEN t.mode = 'cash' THEN t.amount ELSE 0 END AS cash_amt,
               CASE WHEN t.mode <> 'cash' THEN t.amount ELSE 0 END AS chq_amt,
               ROW_NUMBER() OVER (PARTITION BY COALESCE(t.journal_id, -t.id) ORDER BY t.id) AS rn
        FROM transactions t
        JOIN accounts a ON a.id = t.acc_id
        LEFT JOIN apartments ap ON ap.id = t.entity_id AND ap.society_id = p_society_id AND t.role = 'apartment'
        LEFT JOIN vendors v ON v.id = t.entity_id AND v.society_id = p_society_id AND t.role = 'vendor'
        LEFT JOIN security_staff s ON s.id = t.entity_id AND s.society_id = p_society_id AND t.role = 'security'
        WHERE t.society_id = p_society_id AND t.status = 'paid'
          AND t.entry_side = 'Cr'
          AND t.mode <> 'journal'
          AND t.trx_date >= v_month_start AND t.trx_date < v_month_end
          AND (p_entity_id IS NULL OR t.entity_id = p_entity_id)
          AND (p_entity_role IS NULL OR
               (p_entity_role = 'apartment' AND ap.id IS NOT NULL) OR
               (p_entity_role = 'vendor' AND v.id IS NOT NULL) OR
               (p_entity_role = 'security' AND s.id IS NOT NULL))
    ),
    dr_rows AS (
        -- mode <> 'journal': see cr_rows above.
        SELECT t.id, t.journal_id, t.trx_date,
               a.id AS acc_id, COALESCE(a.tab_name, a.name)::TEXT AS account_name,
               COALESCE(ap.flat_number, v.name, s.name, '')::TEXT AS entity_name,
               COALESCE(t.acc_particulars,'')::TEXT AS particulars,
               CASE WHEN t.mode = 'cash' THEN t.amount ELSE 0 END AS cash_amt,
               CASE WHEN t.mode <> 'cash' THEN t.amount ELSE 0 END AS chq_amt,
               ROW_NUMBER() OVER (PARTITION BY COALESCE(t.journal_id, -t.id) ORDER BY t.id) AS rn
        FROM transactions t
        JOIN accounts a ON a.id = t.acc_id
        LEFT JOIN apartments ap ON ap.id = t.entity_id AND ap.society_id = p_society_id AND t.role = 'apartment'
        LEFT JOIN vendors v ON v.id = t.entity_id AND v.society_id = p_society_id AND t.role = 'vendor'
        LEFT JOIN security_staff s ON s.id = t.entity_id AND s.society_id = p_society_id AND t.role = 'security'
        WHERE t.society_id = p_society_id AND t.status = 'paid'
          AND t.entry_side = 'Dr'
          AND t.mode <> 'journal'
          AND t.trx_date >= v_month_start AND t.trx_date < v_month_end
          AND (p_entity_id IS NULL OR t.entity_id = p_entity_id)
          AND (p_entity_role IS NULL OR
               (p_entity_role = 'apartment' AND ap.id IS NOT NULL) OR
               (p_entity_role = 'vendor' AND v.id IS NOT NULL) OR
               (p_entity_role = 'security' AND s.id IS NOT NULL))
    ),
    paired AS (
        SELECT COALESCE(c.trx_date, d.trx_date) AS row_date,
               COALESCE(c.journal_id, -c.id, -d.id) AS pair_key,
               c.acc_id AS cr_acc_id, c.account_name AS cr_account_name,
               c.entity_name AS cr_entity_name, c.particulars AS cr_particulars,
               c.cash_amt AS cr_cash, c.chq_amt AS cr_chq,
               d.acc_id AS dr_acc_id, d.account_name AS dr_account_name,
               d.entity_name AS dr_entity_name, d.particulars AS dr_particulars,
               d.cash_amt AS dr_cash, d.chq_amt AS dr_chq
        FROM cr_rows c
        FULL OUTER JOIN dr_rows d
          ON COALESCE(c.journal_id, -c.id) = COALESCE(d.journal_id, -d.id)
         AND c.rn = d.rn
    )
    SELECT p.*,
           ROW_NUMBER() OVER (ORDER BY p.row_date, p.pair_key) AS ord,
           v_month_opening + SUM(COALESCE(p.cr_cash,0) - COALESCE(p.dr_cash,0))
               OVER (ORDER BY p.row_date, p.pair_key ROWS UNBOUNDED PRECEDING) AS cih_running
    FROM paired p;

    SELECT COUNT(*) INTO v_total_rows FROM _cb_month_rows;
    v_total_pages := GREATEST(1, CEIL(v_total_rows::NUMERIC / p_page_size)::INT);
    IF p_page > v_total_pages THEN p_page := v_total_pages; END IF;
    v_offset := (p_page - 1) * p_page_size;

    IF v_total_rows = 0 THEN
        v_month_closing := v_month_opening;
        RETURN QUERY
        SELECT v_month_start, NULL::INT, NULL::TEXT, NULL::TEXT, NULL::TEXT,
               NULL::NUMERIC(15,2), NULL::NUMERIC(15,2),
               NULL::INT, NULL::TEXT, NULL::TEXT, NULL::TEXT,
               NULL::NUMERIC(15,2), NULL::NUMERIC(15,2),
               v_month_opening,
               v_month_opening, v_month_closing,
               0::BIGINT, 1, TRUE, TRUE;
        RETURN;
    END IF;

    -- Fixed: bare `cih_running` here is ambiguous — it's both this
    -- function's own RETURNS TABLE output column (implicitly a variable
    -- in scope throughout the function body) and a column on
    -- _cb_month_rows, same ambiguity class fn_cashbook_paired_v3 hit.
    -- Table-qualified to resolve it; `ord` isn't a RETURNS TABLE column so
    -- it was never actually ambiguous, but qualified too for consistency.
    SELECT _cb_month_rows.cih_running INTO v_month_closing
    FROM _cb_month_rows ORDER BY _cb_month_rows.ord DESC LIMIT 1;

    RETURN QUERY
    SELECT r.row_date, r.cr_acc_id, r.cr_account_name, r.cr_entity_name, r.cr_particulars,
           r.cr_cash, r.cr_chq, r.dr_acc_id, r.dr_account_name, r.dr_entity_name, r.dr_particulars,
           r.dr_cash, r.dr_chq, r.cih_running,
           v_month_opening, v_month_closing,
           v_total_rows, v_total_pages,
           (p_page = 1), (p_page = v_total_pages)
    FROM _cb_month_rows r
    ORDER BY r.ord
    OFFSET v_offset LIMIT p_page_size;
END;
$$;

-- ═══════════════-- fn_fy_closing_report
-- ======================
-- The closing engine. For a given society + financial year, computes every
-- account's FY closing figure AND rolls it up through parent_account_id so
-- every ancestor (Movable Assets, Current Assets, Income & Expenditure,
-- Capital Account, Balance Sheet Root, ...) gets a correct aggregate too.
--
-- STATUS: draft, not yet run against a live PG16 instance. Verify with
-- pglast + a real instance before deploying, per usual workflow.
--
-- DESIGN, confirmed over several rounds this session:
--   - Purely presentational / computed-on-read. Nothing is posted to
--     `transactions`, nothing is written to `brought_forward`. Re-run
--     this any time someone picks a different FY in the UI.
--   - has_bf=TRUE accounts carry their own real balance forward
--     independently (via brought_forward, entered at Settings > Accounts,
--     or auto-derived e.g. cashbook closing cash / depreciated WDV) —
--     this function's C/F-to-parent rollup for them is a DISPLAY line
--     only, it does not reset or replace their own persisted BF.
--   - has_bf=FALSE accounts (P&L leaves, and the Income Expenditure A/c
--     node itself) have no persisted BF at all — they start every FY at
--     zero and their FY movement genuinely is what rolls up into the
--     parent; there is nothing "next FY" for them to carry.
--   - Depreciable accounts (is_depreciable, depreciation_percent<100) are
--     the one hybrid: they keep their own WDV as next-FY BF (has_bf=TRUE),
--     but this FY's depreciation charge is split off and routed into the
--     Dep account, which itself is a has_bf=FALSE P&L leaf and rolls up
--     normally from there.
--
-- SIGN CONVENTION: everything internally is Cr-positive (a Cr movement
-- adds, a Dr movement subtracts), regardless of the account's own
-- drcr_account. This means rolling up through the hierarchy needs no
-- sign-flipping at each level — a subtree's total is simply the sum of
-- Cr-positive own_closing values across every account in it. The
-- account's own drcr_account is only used at the very end, to decide
-- whether to *display* the total as a Dr or Cr balance.
--
-- ACCEPTANCE TEST (per your instruction): the root (Balance Sheet Root,
-- p_account_id with parent_account_id IS NULL) should sum to 0 if the
-- books balance — that's the double-entry identity (total debits =
-- total credits) expressed in this sign convention, equivalent to
-- "total Assets = total Liabilities + Capital" on the rendered sheet.
-- A nonzero root total means either a data problem (unbalanced
-- transaction, direction bug) or a bug in this function — treat it as
-- a hard error signal, not something to silently absorb.
--
-- Dep is resolved by an ILIKE name lookup (fn_resolve_depreciation_account
-- below), same convention as fn_resolve_cash_account — reversing the
-- earlier "pass the account id in explicitly" approach, which needed a new
-- societies.dep_account_id column and broke on already-provisioned
-- databases (CREATE TABLE IF NOT EXISTS doesn't retroactively add columns
-- to an existing table, so the FK migration failed with "column
-- dep_account_id ... does not exist" against real environments).
-- Income & Expenditure and Capital Account are still reached purely via
-- the parent_account_id hierarchy walk below, not by name at all.

-- Resolves a society's 'Dep' (Depreciation) account by name, same ILIKE
-- convention as fn_resolve_cash_account. No dedicated societies column
-- needed — CREATE TABLE IF NOT EXISTS is a no-op against an existing
-- database, so a new column there requires an explicit ALTER TABLE
-- migration on every already-provisioned society's DB; a name lookup
-- avoids that entirely.
CREATE OR REPLACE FUNCTION fn_resolve_depreciation_account(p_society_id INT)
RETURNS INT LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_acc_id INT;
BEGIN
    SELECT id INTO v_acc_id FROM accounts
    WHERE society_id = p_society_id AND name ILIKE 'Depreciation%'
    LIMIT 1;

    RETURN v_acc_id;
END;
$$;

-- Fixed (2026-08): two issues compounded here.
-- 1. p_fy was SMALLINT — same resolution failure as the other three
--    functions above ("function fn_fy_closing_report(integer, integer)
--    does not exist" when called with plain integers, which is what
--    both loaders.py and any raw SQL literal test naturally pass).
-- 2. CREATE OR REPLACE FUNCTION only replaces a function whose signature
--    (name + exact parameter types) already matches. This function's
--    signature changed twice across recent patches — first losing its
--    p_depreciation_acc_id third parameter, now changing p_fy's type —
--    and neither change was paired with a DROP FUNCTION IF EXISTS for
--    the signature being replaced, so every prior version is still
--    sitting in the database as an orphaned overload rather than being
--    replaced. Both are dropped explicitly below before the current
--    (INT, INT) version is created.
DROP FUNCTION IF EXISTS fn_fy_closing_report (INT, SMALLINT, INT) CASCADE;

-- original: explicit p_depreciation_acc_id param
DROP FUNCTION IF EXISTS fn_fy_closing_report (INT, SMALLINT) CASCADE;

-- previous patch: ILIKE fix, still SMALLINT

CREATE OR REPLACE FUNCTION fn_fy_closing_report(
    p_society_id             INT,
    p_fy                     INT
)
 RETURNS TABLE (
    account_id           INT,
    account_name         TEXT,
    tab_name             TEXT,
    parent_account_id    INT,
    drcr_account         TEXT,
    has_bf               BOOLEAN,
    own_bf               NUMERIC(15,2),   -- Cr-positive; 0 for has_bf=FALSE
    own_movement         NUMERIC(15,2),   -- Cr-positive; this FY's direct transactions only
    depreciation_charge  NUMERIC(15,2),   -- positive amount, added back to own_closing (a Dr-natured asset's Cr-positive value moves toward zero as it depreciates)
    own_closing          NUMERIC(15,2),   -- own_bf + own_movement + depreciation_charge (this account alone, no descendants)
    total_closing        NUMERIC(15,2),   -- own_closing summed across this account + its entire subtree
    display_side         TEXT,            -- 'Dr' or 'Cr', sign of total_closing
     display_amount       NUMERIC(15,2),   -- ABS(total_closing)
     depth                INT,
     sort_path            TEXT
 )
 LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_fy_start DATE := MAKE_DATE(p_fy, 4, 1);
    v_fy_end   DATE := MAKE_DATE(p_fy + 1, 3, 31);
    v_total_depreciation NUMERIC(15,2);
    v_depreciation_acc_id INT;
BEGIN
    -- Resolved by name (fn_resolve_depreciation_account) rather than
    -- taken as a caller-supplied parameter — see that function's comment.
    v_depreciation_acc_id := fn_resolve_depreciation_account(p_society_id);

    -- Total depreciation charged across every depreciable account this FY —
    -- this is what gets added into the Dep account's own_movement below.
    -- fn_account_depreciation already returns 0 for non-depreciable
    -- accounts / depreciation_percent>=100, so no extra filtering needed.
    SELECT COALESCE(SUM(fn_account_depreciation(p_society_id, a.id, p_fy)), 0)
    INTO v_total_depreciation
    FROM accounts a
    WHERE a.society_id = p_society_id;

    RETURN QUERY
    WITH RECURSIVE tree AS (
        SELECT a.id, a.parent_account_id, 0 AS depth,
               LPAD(a.id::TEXT, 10, '0') AS sort_path
        FROM accounts a
        WHERE a.society_id = p_society_id AND a.parent_account_id IS NULL
        UNION ALL
        SELECT c.id, c.parent_account_id, t.depth + 1,
               t.sort_path || '.' || LPAD(c.id::TEXT, 10, '0')
        FROM accounts c
        JOIN tree t ON c.parent_account_id = t.id
        WHERE c.society_id = p_society_id
    ),
    leaf_closing AS (
        SELECT
            a.id,
            a.name::TEXT,
            a.tab_name::TEXT,
            a.parent_account_id,
            a.drcr_account::TEXT,
            a.has_bf,
            CASE WHEN a.has_bf THEN -fn_resolve_bf_amount_fy(p_society_id, a.id, p_fy) ELSE 0 END AS own_bf,
            CASE 
                WHEN a.tab_name = 'CiH' THEN 
                    COALESCE((
                        SELECT SUM(
                            CASE WHEN t.entry_side = 'Dr' THEN t.amount
                                 WHEN t.entry_side = 'Cr' THEN -t.amount
                                 ELSE 0 END
                        )
                        FROM transactions t
                        WHERE t.society_id = p_society_id AND t.status = 'paid' AND t.mode = 'cash'
                          AND t.trx_date BETWEEN v_fy_start AND v_fy_end
                    ), 0)
                ELSE 
                    COALESCE((
                        SELECT SUM(CASE WHEN t.entry_side = 'Cr' THEN t.amount
                                         WHEN t.entry_side = 'Dr' THEN -t.amount
                                         ELSE 0 END)
                        FROM transactions t
                        WHERE t.acc_id = a.id AND t.society_id = p_society_id
                          AND t.status = 'paid'
                          AND t.trx_date BETWEEN v_fy_start AND v_fy_end
                    ), 0)
            END
            - CASE WHEN a.id = v_depreciation_acc_id THEN v_total_depreciation ELSE 0 END
              AS own_movement_raw,
            fn_account_depreciation(p_society_id, a.id, p_fy) AS depreciation_charge,
            tree.depth,
            tree.sort_path
        FROM accounts a
        JOIN tree ON tree.id = a.id
        WHERE a.society_id = p_society_id
    ),
    leaf_final AS (
        SELECT
            lc.id, lc.name, lc.tab_name, lc.parent_account_id, lc.drcr_account, lc.has_bf,
            lc.depth, lc.sort_path,
            -- Depreciation reduces a Dr-natured asset's balance, which in
            -- this Cr-positive frame means its value moves TOWARD zero —
            -- i.e. it's added back, not subtracted.
            lc.own_bf, (lc.own_movement_raw + lc.depreciation_charge) AS own_movement,
            lc.depreciation_charge,
            (lc.own_bf + lc.own_movement_raw + lc.depreciation_charge) AS own_closing
        FROM leaf_closing lc
    ),
    -- Every account paired with every ancestor of itself (including itself),
    -- walking up parent_account_id to the root. Summing own_closing grouped
    -- by ancestor_id gives that ancestor's full subtree total in one pass —
    -- no per-level sign flip needed thanks to the Dr-positive convention.
    ancestry AS (
        SELECT id AS acc_id, id AS ancestor_id
        FROM leaf_final
        UNION ALL
        SELECT anc.acc_id, lf.parent_account_id
        FROM ancestry anc
        JOIN leaf_final lf ON lf.id = anc.ancestor_id
        WHERE lf.parent_account_id IS NOT NULL
    ),
    rollup AS (
        SELECT anc.ancestor_id AS id, SUM(lf.own_closing) AS total_closing
        FROM ancestry anc
        JOIN leaf_final lf ON lf.id = anc.acc_id
        GROUP BY anc.ancestor_id
    )
    SELECT
        lf.id, lf.name, lf.tab_name, lf.parent_account_id, lf.drcr_account, lf.has_bf,
        lf.own_bf, lf.own_movement, lf.depreciation_charge, lf.own_closing,
        r.total_closing,
        CASE WHEN r.total_closing >= 0 THEN 'Cr' ELSE 'Dr' END,
        ABS(r.total_closing),
        lf.depth,
        lf.sort_path
    FROM leaf_final lf
    JOIN rollup r ON r.id = lf.id
        ORDER BY lf.sort_path;
END;
$$;

-- Trailing / FY-scoped turnover from Cr-side income transactions.
-- Used for the GST threshold check (society-level ₹20L) and for
-- determining filing cadence. Computed on demand, never stored.
DROP FUNCTION IF EXISTS fn_society_turnover_fy (INT, INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_society_turnover_fy(
    p_society_id INT,
    p_fy         INT
)
RETURNS NUMERIC(15,2) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_fy_start DATE := MAKE_DATE(p_fy, 4, 1);
    v_fy_end   DATE := MAKE_DATE(p_fy + 1, 3, 31);
    v_total    NUMERIC(15,2);
BEGIN
    SELECT COALESCE(SUM(t.amount), 0)::NUMERIC(15,2)
      INTO v_total
      FROM transactions t
      JOIN accounts a ON a.id = t.acc_id
     WHERE t.society_id = p_society_id
       AND t.status = 'paid'
       AND t.trx_date BETWEEN v_fy_start AND v_fy_end
       AND t.entry_side = 'Cr'
       AND a.drcr_account = 'Cr'
       AND a.tab_name NOT IN ('BkAc', 'CiH', 'Dp', 'SCr');

    RETURN COALESCE(v_total, 0);
END;
$$;

-- Usage note for ledger_export.py's C/F row: for a given account_id, its
-- "transfer to hierarchy parent" line is:
--   target account  = parent_account_id
--   amount           = own_closing (NOT total_closing — the parent's own
--                       row already gets this via its own subtree rollup,
--                       so don't double count by using total_closing here)
--   side             = the sign needed to zero this account's own_closing
--                       out ('Dr' if own_closing is positive/Cr, 'Cr' if
--                       own_closing is negative/Dr, per this function's
--                       Cr-positive convention)
-- This only produces a *meaningful, distinct* C/F transfer for has_bf=FALSE
-- accounts — for has_bf=TRUE accounts the "transfer" is real in the sense
-- that the Balance Sheet reflects it, but the account's own persisted BF
-- for next FY is untouched by it (see design note above).

-- Usage note for the Balance Sheet screen: query this function for
-- p_society_id/p_fy, take the row where parent_account_id IS NULL (the
-- root), and confirm total_closing = 0. If it isn't, something's wrong
-- upstream (an unbalanced transaction, or a bug here) — surface it as an
-- error rather than rendering a Balance Sheet that doesn't balance.

-- TODO before deploying (2026-08 status):
--   1. Requires the account_category migration to be dropped/ignored
--      (superseded by the has_bf correction discussed) and the has_bf
--      corrections in seed.py to be applied first — this function is
--      only correct once has_bf is TRUE on every genuine carrying
--      Asset-side account (per your confirmation) and FALSE on Income
--      Expenditure A/c and the one-off Capital-Account-direct items.
--      STILL OPEN — verify against the live schema before relying on
--      real closing figures.
--   2. Not tested against a live PG16 instance — run pglast + a real DB
--      pass, including a case with a depreciable asset that has both
--      opening WDV and an in-year purchase, to confirm
--      fn_account_depreciation's two components both flow through
--      correctly. STILL OPEN.
--
-- (Previously a 3rd item here said fn_resolve_bf_amount_fy's no-row
-- fallback still summed children via drcr_account rather than
-- entry_side. That's been fixed — see fn_resolve_bf_amount_fy's own
-- comment — so it's removed rather than left as a misleading TODO.)
-- ═════════════════════════════════════════════════
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
            WHEN g.role = 'ADM' THEN COALESCE(ap.flat_number||' — '||COALESCE(ap.owner_name,''), 'Apt #'||g.entity_id::TEXT)
            WHEN g.role = 'VND' THEN COALESCE(v.name||COALESCE(' ('||v.service_type||')',''), 'Vendor #'||g.entity_id::TEXT)
            WHEN g.role = 'SEC' THEN COALESCE(ss.name||COALESCE(' ('||ss.shift||')',''), 'Security #'||g.entity_id::TEXT)
            ELSE 'Unknown #'||g.entity_id::TEXT
        END::TEXT,
        g.time_in::TIMESTAMP, g.time_out::TIMESTAMP,
        CASE WHEN g.time_out IS NOT NULL
             THEN EXTRACT(EPOCH FROM (g.time_out - g.time_in))::INT / 60
             ELSE NULL END::INT
    FROM gate_access g
    LEFT JOIN apartments   ap ON ap.id = g.entity_id AND g.role = 'ADM'
    LEFT JOIN vendors       v ON  v.id = g.entity_id AND g.role = 'VND'
    LEFT JOIN security_staff ss ON ss.id = g.entity_id AND g.role = 'SEC'
    LEFT JOIN users su ON su.id = g.entity_id AND g.role = 'SEC'
    WHERE g.society_id = p_society_id
      AND (p_date   IS NULL OR g.time_in::DATE = p_date)
      AND (p_search IS NULL OR CASE
           WHEN g.role='ADM' THEN ap.flat_number||' '||COALESCE(ap.owner_name,'')
           WHEN g.role='VND' THEN v.name
           WHEN g.role='SEC' THEN ss.name
           ELSE '' END ILIKE '%'||p_search||'%')
    ORDER BY g.time_in DESC;
END;
$$;

-- SECTION 14: ACCOUNTS LIST / PROFILE
-- ════════════════════════════════════════════════════════════════

-- fn_accounts_hierarchy
-- =======================
-- Depth-first chart-of-accounts listing (parent immediately followed by
-- all its descendants, recursively), for the Accounts list card's
-- TreeView and the Ledger card's Ledger Account selector — both need the
-- same "walk the tree in hierarchy order" traversal, so this is the one
-- shared source for it rather than duplicating a recursive CTE in two
-- places.
--
-- Sort key: sort_path is each account's own id zero-padded and
-- dot-joined with every ancestor's id (root first), so a plain
-- ORDER BY sort_path yields exactly the depth-first tree order — a
-- child's path is always a prefix-extension of its parent's, so it
-- always sorts immediately after its parent and before any of the
-- parent's later siblings.
--
-- Same current_balance formula as fn_accounts_list/fn_account_profile
-- (nets per-transaction entry_side, not the account's fixed
-- drcr_account), with one addition: CiH has no transaction rows of its
-- own any more (cash-mode legs post to the real account instead — see
-- fn_resolve_bank_leg), so summing transactions.acc_id=CiH now always
-- gives 0 movement regardless of actual activity. CiH's balance is
-- computed via fn_cih_balance_asof(CURRENT_DATE) instead — same shared
-- formula the Cashbook card's CIH Running and the ledger's CiH branch
-- already use.
DROP FUNCTION IF EXISTS fn_accounts_hierarchy (INT, TEXT) CASCADE;

CREATE OR REPLACE FUNCTION fn_accounts_hierarchy(
    p_society_id INT,
    p_search     TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT, name TEXT, tab_name TEXT, header TEXT, parent_account_id INT,
    parent_tab_name TEXT, drcr_account TEXT, has_bf BOOLEAN,
    is_depreciable BOOLEAN, depth INT,
    bf_amount NUMERIC(15,2), current_balance NUMERIC(15,2),
    transaction_count INT
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    WITH RECURSIVE tree AS (
        SELECT a.id, a.parent_account_id, 0 AS depth,
               LPAD(a.id::TEXT, 10, '0') AS sort_path
        FROM accounts a
        WHERE a.society_id = p_society_id AND a.parent_account_id IS NULL
        UNION ALL
        SELECT c.id, c.parent_account_id, t.depth + 1,
               t.sort_path || '.' || LPAD(c.id::TEXT, 10, '0')
        FROM accounts c
        JOIN tree t ON c.parent_account_id = t.id
        WHERE c.society_id = p_society_id
    ),
    balances AS (
        SELECT a.id,
               COALESCE(MAX(bf.bf_amount), 0)::NUMERIC(15,2) AS bf_amount,
               CASE WHEN a.tab_name = 'CiH' THEN fn_cih_balance_asof(p_society_id, CURRENT_DATE)
                    ELSE (CASE WHEN a.drcr_account = 'Cr'
                               THEN COALESCE(SUM(CASE WHEN t.entry_side='Cr' THEN t.amount
                                                       WHEN t.entry_side='Dr' THEN -t.amount
                                                       ELSE 0 END), 0)
                               ELSE COALESCE(SUM(CASE WHEN t.entry_side='Dr' THEN t.amount
                                                       WHEN t.entry_side='Cr' THEN -t.amount
                                                       ELSE 0 END), 0)
                          END + COALESCE(MAX(bf.bf_amount), 0))
               END::NUMERIC(15,2) AS current_balance,
               COUNT(t.id)::INT AS transaction_count
        FROM accounts a
        LEFT JOIN transactions t ON t.acc_id = a.id AND t.status = 'paid'
        LEFT JOIN brought_forward bf ON bf.acc_id = a.id AND bf.society_id = a.society_id
                                     AND bf.financial_year = fn_current_financial_year()
        WHERE a.society_id = p_society_id
        GROUP BY a.id, a.tab_name, a.drcr_account
    )
    SELECT a.id, a.name::TEXT, a.tab_name::TEXT, a.header::TEXT, a.parent_account_id,
           p.tab_name::TEXT, a.drcr_account::TEXT, a.has_bf, a.is_depreciable,
           tree.depth, b.bf_amount, b.current_balance, b.transaction_count
    FROM accounts a
    JOIN tree ON tree.id = a.id
    JOIN balances b ON b.id = a.id
    LEFT JOIN accounts p ON p.id = a.parent_account_id
    WHERE a.society_id = p_society_id
      AND (p_search IS NULL OR a.name ILIKE '%'||p_search||'%' OR a.tab_name ILIKE '%'||p_search||'%')
    ORDER BY tree.sort_path;
END;
$$;

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
        -- Net movement is computed per-transaction (t.entry_side), then
        -- flipped into the account's own natural Dr/Cr direction — NOT
        -- derived from the account's fixed drcr_account per row, which
        -- previously meant every transaction on a Dr-natured account
        -- (e.g. Bank/Cash) subtracted regardless of whether it was a
        -- receipt or a payment.
        (CASE 
                WHEN a.tab_name = 'CiH' THEN fn_cih_balance_asof(p_society_id, CURRENT_DATE)
                ELSE (CASE WHEN a.drcr_account = 'Cr'
                      THEN COALESCE(SUM(CASE WHEN t.entry_side='Cr' THEN t.amount
                                              WHEN t.entry_side='Dr' THEN -t.amount
                                              ELSE 0 END), 0)
                      ELSE COALESCE(SUM(CASE WHEN t.entry_side='Dr' THEN t.amount
                                              WHEN t.entry_side='Cr' THEN -t.amount
                                              ELSE 0 END), 0)
                   END + COALESCE(MAX(bf.bf_amount), 0))
             END)::NUMERIC(15,2),
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

-- NOTE (fixed 2026-08): previously took only p_account_id with no tenant
-- check — same IDOR class as fn_concern_profile / fn_get_poll_detail
-- (see migration_fn_concern_profile_scope.sql / migration_poll_security_fixes.sql).
-- Any account id could be loaded regardless of society. p_society_id is
-- now required and enforced in the WHERE clause.
--
-- Also fixed (2026-08): current_balance now nets per t.entry_side instead
-- of the account's fixed drcr_account — same class of bug as
-- fn_accounts_list above, same fix.
CREATE OR REPLACE FUNCTION fn_account_profile(p_account_id INT, p_society_id INT)
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
        (CASE 
                WHEN a.tab_name = 'CiH' THEN fn_cih_balance_asof(p_society_id, CURRENT_DATE)
                ELSE (CASE WHEN a.drcr_account = 'Cr'
                      THEN COALESCE(SUM(CASE WHEN t.entry_side='Cr' THEN t.amount
                                              WHEN t.entry_side='Dr' THEN -t.amount
                                              ELSE 0 END), 0)
                      ELSE COALESCE(SUM(CASE WHEN t.entry_side='Dr' THEN t.amount
                                              WHEN t.entry_side='Cr' THEN -t.amount
                                              ELSE 0 END), 0)
                   END + COALESCE(MAX(bf.bf_amount), 0))
             END)::NUMERIC(15,2),
        a.created_at::TIMESTAMP
    FROM accounts a
    LEFT JOIN accounts p ON p.id = a.parent_account_id
    LEFT JOIN transactions t ON t.acc_id = a.id AND t.status = 'paid'
    LEFT JOIN brought_forward bf ON bf.acc_id = a.id AND bf.society_id = a.society_id
                                 AND bf.financial_year = fn_current_financial_year()
    WHERE a.id = p_account_id AND a.society_id = p_society_id
    GROUP BY a.id, a.society_id, a.name, a.tab_name, a.header, a.drcr_account,
             a.depreciation_percent, a.is_depreciable, p.name, a.created_at;
$$;

-- SECTION 15: SOCIETIES LIST / PROFILE
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_societies_list CASCADE;

CREATE OR REPLACE FUNCTION fn_societies_list(
    p_search     TEXT    DEFAULT NULL,
    p_plan       VARCHAR DEFAULT NULL,
    p_status     VARCHAR DEFAULT NULL,
    p_society_id INT     DEFAULT NULL
)
RETURNS TABLE (
    id INT, name VARCHAR(100), email VARCHAR(30), phone VARCHAR(20),
    pan_number VARCHAR(10), gstin VARCHAR(15), secretary_name VARCHAR(100),
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
        s.PAN_number::VARCHAR(10), s.gstin::VARCHAR(15), s.secretary_name::VARCHAR(100),
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
    WHERE (p_search     IS NULL OR s.name ILIKE '%'||p_search||'%')
      AND (p_plan       IS NULL OR s.plan = p_plan)
      AND (p_society_id IS NULL OR s.id = p_society_id)
    ORDER BY s.name;
END;
$$;

DROP FUNCTION IF EXISTS fn_society_profile CASCADE;

CREATE OR REPLACE FUNCTION fn_society_profile(p_society_id INT)
RETURNS TABLE (
    id INT, name VARCHAR(100), logo VARCHAR(100), login_background VARCHAR(100),
    email VARCHAR(30), phone VARCHAR(20), address TEXT, plan VARCHAR(20),
    plan_status VARCHAR(10), plan_validity DATE, calc_start_date DATE,
    secretary_name VARCHAR(100), secretary_phone VARCHAR(20), secretary_sign VARCHAR(100),
    PAN_number VARCHAR(10), gstin VARCHAR(15), payment_qr VARCHAR(255),
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
        s.PAN_number::VARCHAR(10), s.gstin::VARCHAR(15), s.payment_qr::VARCHAR(255),
        (SELECT COUNT(*)::INT FROM apartments    WHERE society_id=s.id),
        (SELECT COUNT(*)::INT FROM vendors       WHERE society_id=s.id),
        (SELECT COUNT(*)::INT FROM security_staff WHERE society_id=s.id),
        (SELECT COUNT(*)::INT FROM users         WHERE society_id=s.id),
        (SELECT COALESCE(SUM(amount-paid_amount),0)::NUMERIC(15,2)
         FROM receivables WHERE society_id=s.id AND status IN ('pending','partial')),
        s.created_at::TIMESTAMP, s.id::INT
    FROM societies s WHERE s.id = p_society_id;
$$;

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

DROP FUNCTION IF EXISTS fn_concern_profile (INT, INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_concern_profile(p_concern_id INT, p_society_id INT)
RETURNS TABLE (
    id INT, society_id INT, apartment_id INT, concern_type VARCHAR(50),
    description TEXT, status VARCHAR(20), assigned_to VARCHAR(100),
    preferred_time VARCHAR(20), days_open BIGINT, created_at TIMESTAMP, image TEXT, subtitle TEXT,
    flat_number VARCHAR(20)
)
LANGUAGE SQL STABLE AS $$
    SELECT c.id::INT, c.society_id::INT, c.apartment_id::INT, c.concern_type::VARCHAR(50),
           c.description::TEXT, c.status::VARCHAR(20),
           (SELECT string_agg(
                CASE ca.role
                    WHEN 'ADM' THEN COALESCE(u.name, u.email, 'Admin')
                    WHEN 'VND' THEN COALESCE(v.business_name, v.name, 'Vendor')
                    WHEN 'SEC' THEN COALESCE(s.name, 'Security')
                END, ', '
            )
            FROM concerns_assigns ca
            LEFT JOIN users u ON u.id = ca.entity_id AND ca.role = 'ADM'
            LEFT JOIN vendors v ON v.id = ca.entity_id AND ca.role = 'VND'
            LEFT JOIN security_staff s ON s.id = ca.entity_id AND ca.role = 'SEC'
            WHERE ca.concern_id = c.id
           )::VARCHAR(100) AS assigned_to,
           c.preferred_time::VARCHAR(20),
           EXTRACT(DAY FROM AGE(CURRENT_DATE, c.created_at))::BIGINT,
           c.created_at::TIMESTAMP, c.image::TEXT,
           ('Flat '||COALESCE(a.flat_number, c.apartment_id::TEXT)||' - '||c.concern_type)::TEXT,
           a.flat_number::VARCHAR(20)
    FROM concerns c
    LEFT JOIN apartments a ON a.id = c.apartment_id AND a.society_id = c.society_id
    WHERE c.id = p_concern_id
      AND c.society_id = p_society_id;
$$;

DROP FUNCTION IF EXISTS fn_concern_assignments CASCADE;

CREATE OR REPLACE FUNCTION fn_concern_assignments(p_concern_id INT)
RETURNS TABLE (
    id INT, concern_id INT, society_id INT, role VARCHAR(10),
    entity_id INT, assigned_by INT, created_at TIMESTAMP,
    entity_name TEXT, status VARCHAR(20), bid_amount NUMERIC(10,2)
)
LANGUAGE SQL STABLE AS $$
    SELECT ca.id, ca.concern_id, ca.society_id, ca.role, ca.entity_id,
           ca.assigned_by, ca.created_at,
           CASE ca.role
               WHEN 'ADM' THEN COALESCE(u.name, u.email, 'Admin')
               WHEN 'VND' THEN COALESCE(v.business_name, v.name, 'Vendor')
               WHEN 'SEC' THEN COALESCE(s.name, 'Security')
           END,
           ca.status::VARCHAR(20), ca.bid_amount::NUMERIC(10,2)
    FROM concerns_assigns ca
    LEFT JOIN users u ON u.id = ca.entity_id AND ca.role = 'ADM'
    LEFT JOIN vendors v ON v.id = ca.entity_id AND ca.role = 'VND'
    LEFT JOIN security_staff s ON s.id = ca.entity_id AND ca.role = 'SEC'
    WHERE ca.concern_id = p_concern_id
    ORDER BY ca.role, ca.created_at;
$$;

-- fn_concern_invite_profile / fn_concern_invite_assignments (concerns_invite
-- readers) are RETIRED as of the 2026-07 unification — fn_concern_assignments
-- above is now the single source for a concern's assignee list, at every
-- lifecycle stage (invited/bid_submitted/assigned/resolved/closed).
DROP FUNCTION IF EXISTS fn_concern_invite_profile CASCADE;

DROP FUNCTION IF EXISTS fn_concern_invite_assignments CASCADE;

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
BEGIN
    -- Fixed (2026-08): cash_balance previously summed
    -- `transactions WHERE acc_id = ANY(name-ILIKE-matched cash/bank
    -- accounts)` — but CiH no longer has any transaction rows of its own
    -- (cash-mode legs post directly to the real income/expense/asset
    -- account; see fn_resolve_bank_leg), so that sum would silently
    -- settle to 0 regardless of actual cash position. Delegates to
    -- fn_cih_balance_asof(CURRENT_DATE) instead — the same shared
    -- formula the Cashbook card and CiH's own ledger use, so this stat
    -- can't drift out of sync with either of them.
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
        fn_cih_balance_asof(p_society_id, CURRENT_DATE)
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
RETURNS TABLE (receivable_id INT, role VARCHAR(10), entity_id INT, issue TEXT) LANGUAGE SQL STABLE AS $$
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
RETURNS TABLE (entity_id INT, role VARCHAR(10), period_month DATE, acc_id INT, dup_count BIGINT, issue TEXT) LANGUAGE SQL STABLE AS $$
    SELECT r.entity_id, r.role, r.period_month, r.acc_id, COUNT(*) AS dup_count,
           'Multiple receivables for same entity/role/period/account'::TEXT
    FROM receivables r
    WHERE r.society_id = p_society_id AND r.period_month IS NOT NULL
    GROUP BY r.entity_id, r.role, r.period_month, r.acc_id
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
    WHERE g.society_id = p_society_id AND g.role = 'SEC'
      AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id = g.entity_id);
$$;

-- ============================================================
-- SECTION 21: LEDGER FUNCTIONS
-- ============================================================

-- fn_close_financial_year — REMOVED (2026-08).
--
-- It computed each has_bf account's closing balance by self-joining
-- transactions back to accounts on the SAME account (`a2.id = t.acc_id`
-- where `t.acc_id = rec.acc_id`), so `a2.drcr_account` was always equal
-- to `rec.drcr_account` for every row. The CASE meant to net Dr vs Cr
-- therefore always resolved the same way regardless of each individual
-- transaction's actual direction — the exact class of bug that was fixed
-- in fn_accounts_list / fn_account_profile / fn_account_ledger_fy /
-- fn_resolve_bf_amount_fy by switching them onto per-transaction
-- t.entry_side. This function was never fixed the same way, and — unlike
-- those four — was never called from anywhere in the Python layer either
-- (grep confirms zero callers), so it was dead code carrying a live bug.
--
-- It's also redundant with the design fn_fy_closing_report already
-- implements: that function computes every account's FY closing figure
-- (including the full parent-hierarchy rollup) purely on read, with no
-- need to persist anything to `brought_forward`. If a persisted year-end
-- close is wanted later (locking a year's numbers so they don't shift if
-- a back-dated transaction is entered), rebuild it keyed off entry_side
-- from scratch rather than resurrecting this version.
DROP FUNCTION IF EXISTS fn_close_financial_year (INT, SMALLINT, BOOLEAN) CASCADE;

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

-- ════════════════════════════════════════════════════════════════
-- POLLING SYSTEM FUNCTIONS
-- ════════════════════════════════════════════════════════════════

-- fn_create_poll: Admin creates a new poll
CREATE OR REPLACE FUNCTION fn_create_poll(
    p_society_id   INT,
    p_created_by   INT,
    p_title        VARCHAR(200),
    p_description  TEXT DEFAULT NULL,
    p_choice_count SMALLINT DEFAULT 2,
    p_choice_1     VARCHAR(100) DEFAULT '',
    p_choice_2     VARCHAR(100) DEFAULT '',
    p_choice_3     VARCHAR(100) DEFAULT NULL,
    p_choice_4     VARCHAR(100) DEFAULT NULL,
    p_choice_5     VARCHAR(100) DEFAULT NULL,
    p_ends_at      TIMESTAMP DEFAULT NULL
) RETURNS INT LANGUAGE plpgsql AS $$
DECLARE
    v_poll_id INT;
BEGIN
    IF p_choice_count < 2 OR p_choice_count > 5 THEN
        RAISE EXCEPTION 'choice_count must be between 2 and 5';
    END IF;

    INSERT INTO polls (society_id, created_by, title, description, choice_count, choice_1, choice_2, choice_3, choice_4, choice_5, ends_at)
    VALUES (p_society_id, p_created_by, p_title, p_description, p_choice_count, p_choice_1, p_choice_2, p_choice_3, p_choice_4, p_choice_5, p_ends_at)
    RETURNING id INTO v_poll_id;

    RETURN v_poll_id;
END;
$$;

-- fn_get_polls: List active polls for a society (owner portal)
CREATE OR REPLACE FUNCTION fn_get_polls(p_society_id INT)
RETURNS TABLE (
    id              INT,
    title           VARCHAR(200),
    description     TEXT,
    status          VARCHAR(20),
    choice_count    SMALLINT,
    choice_1        VARCHAR(100),
    choice_2        VARCHAR(100),
    choice_3        VARCHAR(100),
    choice_4        VARCHAR(100),
    choice_5        VARCHAR(100),
    results_announced_at TIMESTAMP,
    created_at      TIMESTAMP,
    total_votes     BIGINT,
    has_voted       BOOLEAN,
    ends_at         TIMESTAMP
) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        p.id,
        p.title,
        p.description,
        p.status,
        p.choice_count,
        p.choice_1,
        p.choice_2,
        p.choice_3,
        p.choice_4,
        p.choice_5,
        p.results_announced_at,
        p.created_at,
        COALESCE(v.total_votes, 0)::BIGINT,
        FALSE AS has_voted,
        p.ends_at
    FROM polls p
    LEFT JOIN (SELECT poll_id, COUNT(*) AS total_votes FROM poll_votes GROUP BY poll_id) v
        ON v.poll_id = p.id
    WHERE p.society_id = p_society_id
      AND p.status = 'active'
    ORDER BY p.created_at DESC;
END;
$$;

-- fn_polls_list: Paginated poll list for the generic drilldown system
-- (winning_choice added 2026-08 so list_polls can highlight the
-- leading choice once results are declared — NULL until then, and
-- NULL on a tie so nothing is misleadingly highlighted)
-- DROP required: same params, but RETURNS TABLE column set changed
-- (added winning_choice) — CREATE OR REPLACE alone errors on a
-- return-type change in Postgres.
DROP FUNCTION IF EXISTS fn_polls_list (INT, VARCHAR, VARCHAR);

CREATE OR REPLACE FUNCTION fn_polls_list(
    p_society_id INT,
    p_search VARCHAR DEFAULT NULL,
    p_status VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id                  INT,
    title               VARCHAR(200),
    description         TEXT,
    status              VARCHAR(20),
    choice_count        SMALLINT,
    choice_1            VARCHAR(100),
    choice_2            VARCHAR(100),
    choice_3            VARCHAR(100),
    choice_4            VARCHAR(100),
    choice_5            VARCHAR(100),
    results_announced_at TIMESTAMP,
    created_at          TIMESTAMP,
    ends_at             TIMESTAMP,
    total_votes         BIGINT,
    winning_choice      SMALLINT
) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        p.id,
        p.title,
        p.description,
        p.status,
        p.choice_count,
        p.choice_1,
        p.choice_2,
        p.choice_3,
        p.choice_4,
        p.choice_5,
        p.results_announced_at,
        p.created_at,
        p.ends_at,
        COALESCE(v.total_votes, 0)::BIGINT,
        w.winning_choice
    FROM polls p
    LEFT JOIN (SELECT poll_id, COUNT(*) AS total_votes FROM poll_votes GROUP BY poll_id) v
        ON v.poll_id = p.id
    LEFT JOIN LATERAL (
        -- Only one choice qualifies as "winning" if its vote count is a
        -- strict, unique max — a tie (or zero votes) yields NULL so the
        -- list never highlights an arbitrary choice.
        SELECT CASE WHEN COUNT(*) FILTER (WHERE x.cnt = x.maxcnt) = 1
                    THEN (ARRAY_AGG(x.choice) FILTER (WHERE x.cnt = x.maxcnt))[1]
                    ELSE NULL END AS winning_choice
        FROM (
            SELECT choice, COUNT(*) AS cnt, MAX(COUNT(*)) OVER () AS maxcnt
            FROM poll_votes
            WHERE poll_id = p.id
            GROUP BY choice
        ) x
    ) w ON TRUE
    WHERE p.society_id = p_society_id
      AND (p_status IS NULL OR p.status = p_status)
      AND (p_search IS NULL OR p.title ILIKE '%' || p_search || '%' OR p.description ILIKE '%' || p_search || '%')
    ORDER BY p.created_at DESC;
END;
$$;

-- fn_get_poll_detail: Get a single poll with vote counts per choice
-- (tenant-scoped — see migration_poll_security_fixes.sql)
DROP FUNCTION IF EXISTS fn_get_poll_detail (INT, INT);

CREATE OR REPLACE FUNCTION fn_get_poll_detail(p_poll_id INT, p_user_id INT, p_society_id INT)
RETURNS TABLE (
    id              INT,
    title           VARCHAR(200),
    description     TEXT,
    status          VARCHAR(20),
    choice_count    SMALLINT,
    choice_1        VARCHAR(100),
    choice_2        VARCHAR(100),
    choice_3        VARCHAR(100),
    choice_4        VARCHAR(100),
    choice_5        VARCHAR(100),
    results_announced_at TIMESTAMP,
    created_at      TIMESTAMP,
    total_votes     BIGINT,
    has_voted       BOOLEAN,
    user_vote       SMALLINT,
    vote_counts     JSONB,
    ends_at         TIMESTAMP
) LANGUAGE plpgsql AS $$
DECLARE
    v_total_votes BIGINT;
    v_has_voted   BOOLEAN;
    v_user_vote   SMALLINT;
BEGIN
    SELECT
        p.id,
        p.title,
        p.description,
        p.status,
        p.choice_count,
        p.choice_1,
        p.choice_2,
        p.choice_3,
        p.choice_4,
        p.choice_5,
        p.results_announced_at,
        p.created_at,
        COALESCE((SELECT COUNT(*) FROM poll_votes WHERE poll_id = p.id), 0)::BIGINT,
        EXISTS (SELECT 1 FROM poll_votes WHERE poll_id = p.id AND user_id = p_user_id),
        (SELECT choice FROM poll_votes WHERE poll_id = p.id AND user_id = p_user_id),
        p.ends_at
    FROM polls p
    WHERE p.id = p_poll_id
      AND p.society_id = p_society_id
    INTO
        id, title, description, status, choice_count, choice_1, choice_2, choice_3, choice_4, choice_5,
        results_announced_at, created_at, total_votes, has_voted, user_vote, ends_at;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    vote_counts := (
        SELECT jsonb_object_agg(
            'choice_' || v.choice,
            v.cnt
        )
        FROM (
            SELECT choice, COUNT(*) AS cnt
            FROM poll_votes
            WHERE poll_id = p_poll_id
            GROUP BY choice
        ) v
    );

    RETURN NEXT;
END;
$$;

-- fn_cast_vote: User casts a vote (server-side auth via p_user_id)
CREATE OR REPLACE FUNCTION fn_cast_vote(
    p_poll_id  INT,
    p_user_id  INT,
    p_choice   SMALLINT
) RETURNS TABLE (success BOOLEAN, message TEXT, total_votes BIGINT) LANGUAGE plpgsql AS $$
DECLARE
    v_poll      polls%ROWTYPE;
    v_existing  INT;
    v_total     BIGINT;
BEGIN
    SELECT * INTO v_poll FROM polls WHERE id = p_poll_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'Poll not found'::TEXT, 0::BIGINT;
        RETURN;
    END IF;

    IF v_poll.status <> 'active' THEN
        RETURN QUERY SELECT FALSE, 'This poll is no longer active'::TEXT, 0::BIGINT;
        RETURN;
    END IF;

    IF v_poll.ends_at IS NOT NULL AND v_poll.ends_at <= NOW() THEN
        PERFORM fn_declare_expired_polls();
        RETURN QUERY SELECT FALSE, 'This poll has ended'::TEXT, 0::BIGINT;
        RETURN;
    END IF;

    IF p_choice < 1 OR p_choice > v_poll.choice_count THEN
        RETURN QUERY SELECT FALSE, format('Invalid choice. Please select between 1 and %s', v_poll.choice_count)::TEXT, 0::BIGINT;
        RETURN;
    END IF;

    SELECT id INTO v_existing FROM poll_votes WHERE poll_id = p_poll_id AND user_id = p_user_id;
    IF v_existing IS NOT NULL THEN
        RETURN QUERY SELECT FALSE, 'You have already voted in this poll'::TEXT, 0::BIGINT;
        RETURN;
    END IF;

    INSERT INTO poll_votes (poll_id, user_id, choice)
    VALUES (p_poll_id, p_user_id, p_choice);

    SELECT COUNT(*) INTO v_total FROM poll_votes WHERE poll_id = p_poll_id;

    RETURN QUERY SELECT TRUE, 'Vote cast successfully'::TEXT, v_total;
EXCEPTION
    WHEN unique_violation THEN
        RETURN QUERY SELECT FALSE, 'You have already voted in this poll'::TEXT, 0::BIGINT;
END;
$$;

-- fn_edit_poll: Admin edits an existing poll. Server-side guarded
-- (defense-in-depth alongside the UI-level guard in renderers.py) —
-- only allowed while status='active' AND zero votes have been cast,
-- since changing choices out from under existing votes would corrupt
-- the tally. Editing after a vote exists (or once closed/declared)
-- must go through Close Poll -> a new poll instead.
CREATE OR REPLACE FUNCTION fn_edit_poll(
    p_poll_id      INT,
    p_society_id   INT,
    p_title        VARCHAR(200),
    p_description  TEXT DEFAULT NULL,
    p_choice_count SMALLINT DEFAULT 2,
    p_choice_1     VARCHAR(100) DEFAULT '',
    p_choice_2     VARCHAR(100) DEFAULT '',
    p_choice_3     VARCHAR(100) DEFAULT NULL,
    p_choice_4     VARCHAR(100) DEFAULT NULL,
    p_choice_5     VARCHAR(100) DEFAULT NULL,
    p_ends_at      TIMESTAMP DEFAULT NULL
) RETURNS BOOLEAN LANGUAGE plpgsql AS $$
DECLARE
    v_poll       polls%ROWTYPE;
    v_vote_count BIGINT;
BEGIN
    IF p_choice_count < 2 OR p_choice_count > 5 THEN
        RAISE EXCEPTION 'choice_count must be between 2 and 5';
    END IF;

    SELECT * INTO v_poll FROM polls WHERE id = p_poll_id AND society_id = p_society_id;
    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    IF v_poll.status <> 'active' THEN
        RETURN FALSE;
    END IF;

    SELECT COUNT(*) INTO v_vote_count FROM poll_votes WHERE poll_id = p_poll_id;
    IF v_vote_count > 0 THEN
        RETURN FALSE;
    END IF;

    UPDATE polls
       SET title        = p_title,
           description  = p_description,
           choice_count = p_choice_count,
           choice_1     = p_choice_1,
           choice_2     = p_choice_2,
           choice_3     = p_choice_3,
           choice_4     = p_choice_4,
           choice_5     = p_choice_5,
           ends_at      = p_ends_at,
           updated_at   = NOW()
     WHERE id = p_poll_id;

    RETURN TRUE;
END;
$$;

-- fn_declare_results: Admin declares results at a specified time
-- (tenant-scoped + no-op guard against re-declaring — see
-- migration_poll_security_fixes.sql)
DROP FUNCTION IF EXISTS fn_declare_results (INT, INT);

CREATE OR REPLACE FUNCTION fn_declare_results(p_poll_id INT, p_user_id INT, p_society_id INT)
RETURNS BOOLEAN LANGUAGE plpgsql AS $$
DECLARE
    v_poll polls%ROWTYPE;
BEGIN
    SELECT * INTO v_poll FROM polls WHERE id = p_poll_id AND society_id = p_society_id;
    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    IF v_poll.status = 'results_declared' THEN
        RETURN FALSE;
    END IF;

    UPDATE polls
       SET status = 'results_declared',
           results_announced_at = NOW(),
           updated_at = NOW()
     WHERE id = p_poll_id;

    RETURN TRUE;
END;
$$;

-- fn_close_poll: Admin closes a poll (tenant-scoped — see
-- migration_poll_security_fixes.sql)
DROP FUNCTION IF EXISTS fn_close_poll (INT, INT);

CREATE OR REPLACE FUNCTION fn_close_poll(p_poll_id INT, p_user_id INT, p_society_id INT)
RETURNS BOOLEAN LANGUAGE plpgsql AS $$
DECLARE
    v_poll polls%ROWTYPE;
BEGIN
    SELECT * INTO v_poll FROM polls WHERE id = p_poll_id AND society_id = p_society_id;
    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    IF v_poll.status <> 'active' THEN
        RETURN FALSE;
    END IF;

    UPDATE polls
       SET status = 'closed',
           updated_at = NOW()
     WHERE id = p_poll_id;

    RETURN FOUND;
END;
$$;

-- fn_declare_expired_polls: Auto-declare results for polls that have passed their end time
CREATE OR REPLACE FUNCTION fn_declare_expired_polls()
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    UPDATE polls
       SET status = 'results_declared',
           results_announced_at = NOW(),
           updated_at = NOW()
     WHERE status = 'active'
       AND ends_at IS NOT NULL
       AND ends_at <= NOW();
END;
$$;

-- fn_get_polls_ending_soon: Find active polls ending within the given minutes
CREATE OR REPLACE FUNCTION fn_get_polls_ending_soon(
    p_society_id INT,
    p_minutes INT DEFAULT 15
)
RETURNS TABLE (
    id INT,
    title VARCHAR(200),
    ends_at TIMESTAMP
) LANGUAGE sql STABLE AS $$
    SELECT
        p.id,
        p.title,
        p.ends_at
    FROM polls p
    WHERE p.society_id = p_society_id
      AND p.status = 'active'
      AND p.ends_at IS NOT NULL
      AND p.ends_at > NOW()
      AND p.ends_at <= NOW() + (p_minutes || ' minutes')::INTERVAL
      AND p.reminder_sent_at IS NULL
    ORDER BY p.ends_at ASC;
$$;

-- fn_poll_vote_count_kpi: Returns total votes cast across all active polls in a society
CREATE OR REPLACE FUNCTION fn_poll_vote_count_kpi(p_society_id INT)
RETURNS BIGINT LANGUAGE SQL STABLE AS $$
    SELECT COUNT(*)::BIGINT FROM poll_votes pv
    JOIN polls p ON p.id = pv.poll_id
    WHERE p.society_id = p_society_id;
$$;

-- fn_poll_total_count_kpi: Returns total number of polls in a society
CREATE OR REPLACE FUNCTION fn_poll_total_count_kpi(p_society_id INT)
RETURNS BIGINT LANGUAGE SQL STABLE AS $$
    SELECT COUNT(*)::BIGINT FROM polls WHERE society_id = p_society_id;
$$;

-- ── fn_sync_concern_status: aggregate concerns_assigns.status -> concerns.status ──
-- This is now the ONLY trigger writing concerns.status from delegation state
-- (previously a second, independently-ruled trigger on concerns_invite could
-- race this one and leave concerns.status reflecting whichever fired last).
--
-- 2026-08 fix: the aggregate is now computed ONLY over "touched" rows —
-- rows that actually reached 'assigned' or beyond. Rows still sitting at
-- 'invited'/'bid_submitted' (candidates who were never formally chosen,
-- e.g. losing bidders) are excluded entirely from this calculation, so
-- they can no longer block a concern from reaching 'resolved'. Previously
-- a single leftover invited/bid_submitted row from an unselected candidate
-- would keep a concern stuck at 'assigned' forever, even after the actual
-- assignee(s) had resolved their work — see Concerns_Workflow_Review.md §2.9.
CREATE OR REPLACE FUNCTION fn_sync_concern_status(p_concern_id INT)
RETURNS VOID
LANGUAGE plpgsql AS $$
DECLARE
    v_touched INT;
    v_touched_closed INT;
    v_touched_resolved_or_closed INT;
    v_new_status VARCHAR(20);
BEGIN
    PERFORM 1 FROM concerns WHERE id=p_concern_id FOR UPDATE; -- lock the concern row to prevent race conditions
    SELECT COUNT(*) FILTER (WHERE status IN ('assigned', 'accepted', 'resolved', 'closed')),
           COUNT(*) FILTER (WHERE status = 'closed'),
           COUNT(*) FILTER (WHERE status IN ('resolved', 'closed'))
      INTO v_touched, v_touched_closed, v_touched_resolved_or_closed
      FROM concerns_assigns
     WHERE concern_id = p_concern_id
       AND status IN ('assigned', 'accepted', 'resolved', 'closed');

    IF v_touched = 0 THEN
        -- No one has ever been formally assigned yet — still open, whether
        -- there are zero rows or only invited/bid_submitted candidates.
        v_new_status := 'open';
    ELSIF v_touched_closed = v_touched THEN
        v_new_status := 'closed';
    ELSIF v_touched_resolved_or_closed = v_touched THEN
        v_new_status := 'resolved';
    ELSE
        v_new_status := 'assigned';
    END IF;

    UPDATE concerns
       SET status = v_new_status,
           updated_at = NOW()
     WHERE id = p_concern_id
       AND status IS DISTINCT FROM v_new_status;
END;
$$;

CREATE OR REPLACE FUNCTION fn_trg_sync_concern_status()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM fn_sync_concern_status(OLD.concern_id);
        RETURN OLD;
    ELSE
        PERFORM fn_sync_concern_status(NEW.concern_id);
        RETURN NEW;
    END IF;
END;
$$;

-- ── Resolve the active rate row for a section as of a given date ──
DROP FUNCTION IF EXISTS fn_tds_section_rate (INT, VARCHAR, DATE) CASCADE;

CREATE OR REPLACE FUNCTION fn_tds_section_rate(
    p_society_id INT,
    p_section    VARCHAR,
    p_as_of      DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    rate NUMERIC(5, 2),
    rate_no_pan NUMERIC(5, 2),
    single_bill_threshold NUMERIC(12, 2),
    annual_aggregate_threshold NUMERIC(12, 2)
) LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT r.rate,
           COALESCE(r.rate_no_pan, r.rate),
           r.single_bill_threshold,
           r.annual_aggregate_threshold
      FROM tds_section_rates r
     WHERE r.society_id = p_society_id
       AND r.section = p_section
       AND r.effective_from <= p_as_of
       AND (r.effective_to IS NULL OR r.effective_to >= p_as_of)
     ORDER BY r.effective_from DESC
     LIMIT 1;
END;
$$;

-- ── Cumulative annual TDS tracking for one vendor/section (Phase 4.2) ──
-- Sum of confirmed, TDS-relevant expense amounts for this vendor within
-- the FY, excluding the row being edited (so a re-save doesn't double
-- count itself). Drives the "has this vendor crossed the F1,00,000 annual
-- aggregate" check. Threshold 0 in the rate row means "no aggregate test".
DROP FUNCTION IF EXISTS fn_vendor_tds_cumulative_fy (INT, INT, VARCHAR, VARCHAR, INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_vendor_tds_cumulative_fy(
    p_society_id INT,
    p_vendor_id  INT,
    p_section    VARCHAR,
    p_fy         VARCHAR,
    p_exclude_expense_id INT DEFAULT NULL
)
RETURNS NUMERIC(15, 2) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_fy_start DATE := make_date(p_fy::INT, 4, 1);
    v_fy_end   DATE := make_date(p_fy::INT + 1, 3, 31);
    v_total    NUMERIC(15, 2);
BEGIN
    SELECT COALESCE(SUM(e.amount), 0)::NUMERIC(15, 2)
      INTO v_total
      FROM expenses e
     WHERE e.society_id = p_society_id
       AND e.entity_id = p_vendor_id
       AND e.role = 'vendor'
       AND e.tds_section = p_section
       AND e.status = 'confirmed'
       AND e.tds_pct > 0
       AND e.expense_date BETWEEN v_fy_start AND v_fy_end
       AND (p_exclude_expense_id IS NULL OR e.id <> p_exclude_expense_id);

    RETURN COALESCE(v_total, 0);
END;
$$;

-- ── Auto-compute TDS % for one bill (Phase 4.3) ──
-- Applies the section rate only when the bill is actually TDS-relevant:
--   * single-bill threshold met (amount >= single_bill_threshold), OR
--   * annual aggregate threshold met (this vendor's FY cumulative, including
--     this bill, crosses annual_aggregate_threshold; 0 = no aggregate test),
--   * the rate row exists for the section.
-- Returns 0 (and applies=FALSE) otherwise, so callers pre-fill the form
-- with 0 and don't split. no_pan_uplift applies the higher rate when the
-- vendor has no PAN on file (the caller passes p_pan_captured).
DROP FUNCTION IF EXISTS fn_compute_tds_pct (INT, INT, VARCHAR, VARCHAR, NUMERIC, BOOLEAN) CASCADE;

CREATE OR REPLACE FUNCTION fn_compute_tds_pct(
    p_society_id      INT,
    p_vendor_id       INT,
    p_section         VARCHAR,
    p_fy              VARCHAR,
    p_amount          NUMERIC,
    p_pan_captured    BOOLEAN DEFAULT TRUE
)
RETURNS TABLE (
    tds_pct NUMERIC(5, 2),
    applies BOOLEAN,
    basis TEXT
) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_rate     NUMERIC(5, 2);
    v_rate_nopan NUMERIC(5, 2);
    v_single   NUMERIC(12, 2);
    v_annual   NUMERIC(12, 2);
    v_cum      NUMERIC(15, 2);
BEGIN
    IF p_section IS NULL OR p_amount IS NULL OR p_amount <= 0 THEN
        RETURN QUERY SELECT 0::NUMERIC(5, 2), FALSE, 'no-section-or-zero-amount'::TEXT;
        RETURN;
    END IF;

    SELECT r.rate, COALESCE(r.rate_no_pan, r.rate),
           r.single_bill_threshold, r.annual_aggregate_threshold
      INTO v_rate, v_rate_nopan, v_single, v_annual
      FROM tds_section_rates r
     WHERE r.society_id = p_society_id
       AND r.section = p_section
       AND r.effective_from <= CURRENT_DATE
       AND (r.effective_to IS NULL OR r.effective_to >= CURRENT_DATE)
     ORDER BY r.effective_from DESC
     LIMIT 1;

    IF NOT FOUND THEN
        RETURN QUERY SELECT 0::NUMERIC(5, 2), FALSE, 'section-not-configured'::TEXT;
        RETURN;
    END IF;

    IF NOT p_pan_captured THEN
        v_rate := v_rate_nopan;
    END IF;

    -- Single-bill test: threshold 0 means "no minimum single bill" (e.g. 194J).
    -- Annual-aggregate test: threshold 0 means "aggregate test disabled".
    IF p_amount >= v_single THEN
        RETURN QUERY SELECT v_rate, TRUE, 'single-bill'::TEXT;
        RETURN;
    END IF;

    IF v_annual > 0 THEN
        v_cum := fn_vendor_tds_cumulative_fy(p_society_id, p_vendor_id, p_section, p_fy);
        IF (v_cum + p_amount) >= v_annual THEN
            RETURN QUERY SELECT v_rate, TRUE, 'annual-aggregate'::TEXT;
            RETURN;
        END IF;
    END IF;

    RETURN QUERY SELECT 0::NUMERIC(5, 2), FALSE, 'below-threshold'::TEXT;
END;
$$;

-- SECTION 16: CAPITAL vs REVENUE EXPENSE (Phase 5)
-- ════════════════════════════════════════════════════════════════
-- An expense is CAPITAL (is_capital) when the chosen acc_id sits on the
-- Balance-Sheet branch of the chart of accounts (asset/liability), as
-- opposed to the Income & Expenditure (P&L) branch. Determined purely
-- by walking the parent_account_id chain: if any ancestor (or the
-- account itself) is a BS-header tab (MAs/ImAs/CurAs/SCr/CapAc/Bal...
-- i.e. NOT the InExp node and not a child of it), it's a balance-sheet
-- account → capital.
DROP FUNCTION IF EXISTS fn_is_capital_account (INT, INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_is_capital_account(
    p_society_id INT,
    p_acc_id     INT
)
RETURNS BOOLEAN LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_cur     INT := p_acc_id;
    v_tab     TEXT;
    v_parent  INT;
    v_depth   INT := 0;
BEGIN
    IF p_acc_id IS NULL THEN
        RETURN FALSE;
    END IF;

    LOOP
        SELECT a.tab_name, a.parent_account_id
          INTO v_tab, v_parent
          FROM accounts a
         WHERE a.id = v_cur AND a.society_id = p_society_id;

        IF NOT FOUND THEN
            RETURN FALSE;
        END IF;

        -- The Income & Expenditure node (and everything under it) is P&L.
        IF v_tab = 'InExp' THEN
            RETURN FALSE;
        END IF;

        -- A header/leaf on the Balance-Sheet side: reached a structural
        -- node (root, MAs, ImAs, CurAs, SCr, CapAc, Bal...) without having
        -- passed through InExp → capital.
        IF v_parent IS NULL THEN
            RETURN TRUE;
        END IF;

        v_cur := v_parent;
        v_depth := v_depth + 1;
        IF v_depth > 20 THEN
            RETURN FALSE;
        END IF;
    END LOOP;
END;
$$;

-- SECTION 16: GST SUMMARY — monthly GST report (Phase 2d)
-- ════════════════════════════════════════════════════════════════
-- One row per month: taxable_value, cgst_collected, sgst_collected,
-- exempt_value, total_bills_gst_applicable, total_bills_exempt.
-- Source: receivables (taxable/exempt split, joined via bill_group_id)
-- and transactions (actual Cr legs on the CGST/SGST payable accounts,
-- resolved via fn_resolve_gst_accounts).
DROP FUNCTION IF EXISTS fn_gst_summary_fy (INT, INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_gst_summary_fy(
    p_society_id INT,
    p_fy         INT
)
RETURNS TABLE (
    period_month DATE,
    taxable_value NUMERIC(15,2),
    cgst_collected NUMERIC(15,2),
    sgst_collected NUMERIC(15,2),
    exempt_value NUMERIC(15,2),
    total_bills_gst_applicable BIGINT,
    total_bills_exempt BIGINT
) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_fy_start DATE := MAKE_DATE(p_fy, 4, 1);
    v_fy_end   DATE := MAKE_DATE(p_fy + 1, 3, 31);
    v_cgst_acc INT;
    v_sgst_acc INT;
BEGIN
    SELECT id INTO v_cgst_acc FROM accounts
    WHERE society_id = p_society_id AND drcr_account = 'Cr'
      AND name ILIKE '%CGST Payable%'
    LIMIT 1;

    SELECT id INTO v_sgst_acc FROM accounts
    WHERE society_id = p_society_id AND drcr_account = 'Cr'
      AND name ILIKE '%SGST Payable%'
    LIMIT 1;

    RETURN QUERY
    WITH bill_group_lines AS (
        SELECT 
            period_month,
            bill_group_id,
            SUM(CASE WHEN description LIKE 'Maintenance %' THEN base_amount ELSE 0 END) as maint_amount,
            SUM(CASE WHEN description LIKE 'Sinking Fund %' OR description LIKE 'Repair Fund %' THEN base_amount ELSE 0 END) as fund_amount,
            MAX(CASE WHEN description LIKE 'CGST on Maintenance %' OR description LIKE 'SGST on Maintenance %' THEN 1 ELSE 0 END) as has_gst
        FROM receivables
        WHERE society_id = p_society_id
          AND period_month BETWEEN v_fy_start AND v_fy_end
          AND bill_group_id IS NOT NULL
        GROUP BY period_month, bill_group_id
    ),
    monthly_receivables AS (
        SELECT 
            period_month,
            SUM(CASE WHEN has_gst = 1 THEN maint_amount ELSE 0 END) as taxable_value,
            SUM(fund_amount) as exempt_value,
            SUM(CASE WHEN has_gst = 1 THEN 0 ELSE maint_amount + fund_amount END) as exempt_from_bills,
            COUNT(CASE WHEN has_gst = 1 THEN 1 END) as gst_bills,
            COUNT(CASE WHEN has_gst = 0 THEN 1 END) as exempt_bills
        FROM bill_group_lines
        GROUP BY period_month
    ),
    monthly_transactions AS (
        SELECT 
            DATE_TRUNC('month', trx_date)::DATE as period_month,
            COALESCE(SUM(CASE WHEN acc_id = v_cgst_acc THEN amount ELSE 0 END), 0) as cgst_collected,
            COALESCE(SUM(CASE WHEN acc_id = v_sgst_acc THEN amount ELSE 0 END), 0) as sgst_collected
        FROM transactions
        WHERE society_id = p_society_id
          AND trx_date BETWEEN v_fy_start AND v_fy_end
          AND entry_side = 'Cr'
          AND status = 'paid'
          AND (
              (v_cgst_acc IS NOT NULL AND acc_id = v_cgst_acc)
              OR (v_sgst_acc IS NOT NULL AND acc_id = v_sgst_acc)
          )
        GROUP BY DATE_TRUNC('month', trx_date)::DATE
    )
    SELECT 
        COALESCE(mr.period_month, mt.period_month) as period_month,
        COALESCE(mr.taxable_value, 0) as taxable_value,
        COALESCE(mt.cgst_collected, 0) as cgst_collected,
        COALESCE(mt.sgst_collected, 0) as sgst_collected,
        COALESCE(mr.exempt_value + mr.exempt_from_bills, 0) as exempt_value,
        COALESCE(mr.gst_bills, 0) as total_bills_gst_applicable,
        COALESCE(mr.exempt_bills, 0) as total_bills_exempt
    FROM monthly_receivables mr
    FULL OUTER JOIN monthly_transactions mt ON mt.period_month = mr.period_month
    ORDER BY period_month;
END;
$$;

-- SECTION 17: TDS RETURN SUMMARY — Form 26Q quarterly (Phase 4d)
-- ════════════════════════════════════════════════════════════════
-- One row per TDS-deducted payment (per-transaction, NOT vendor-
-- aggregated — 26Q wants individual deduction records with dates).
-- Source: Dr legs on the TDS-payable account (fn_resolve_tds_account),
-- tagged source_table='expenses'/source_id, joined through expenses →
-- vendors. Straddles the FY boundary exactly like fn_fy_closing_report
-- (Q1 Apr-Jun ... Q4 Jan-Mar), so quarter p_quarter is 1..4 within FY
-- p_fy (the FY START year, e.g. 2026 = FY 1-Apr-2026..31-Mar-2027).
--
-- no_pan is flagged so the export can highlight filing-blocking rows.
DROP FUNCTION IF EXISTS fn_tds_summary_fy (INT, VARCHAR, INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_tds_summary_fy(
    p_society_id INT,
    p_fy         VARCHAR,
    p_quarter    INT
)
RETURNS TABLE (
    vendor_name VARCHAR(100),
    vendor_pan  VARCHAR(10),
    tds_section VARCHAR(10),
    gross_amount_paid NUMERIC(15, 2),
    tds_deducted NUMERIC(15, 2),
    net_paid     NUMERIC(15, 2),
    payment_date DATE,
    no_pan      BOOLEAN
) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_tds_acc  INT;
    v_q_start  DATE;
    v_q_end    DATE;
    v_fy_year  INT;
BEGIN
    v_tds_acc := fn_resolve_tds_account(p_society_id);
    IF v_tds_acc IS NULL THEN
        RETURN;
    END IF;

    v_fy_year := p_fy::INT;
    -- Quarter start month relative to FY (Apr=month 4 of v_fy_year).
    -- Q1: Apr-Jun, Q2: Jul-Sep, Q3: Oct-Dec, Q4: Jan-Mar(next calendar year).
    -- Month sequence is 4,7,10 then wraps to 1 (Jan) of the next calendar year.
    v_q_start := make_date(
        v_fy_year + CASE WHEN p_quarter >= 4 THEN 1 ELSE 0 END,
        CASE WHEN p_quarter = 4 THEN 1 ELSE ((p_quarter - 1) * 3) + 4 END,
        1
    );
    v_q_end := (v_q_start + INTERVAL '3 months' - INTERVAL '1 day')::DATE;

    RETURN QUERY
    SELECT v.business_name::VARCHAR(100),
           v.pan_number::VARCHAR(10),
           e.tds_section::VARCHAR(10),
           e.amount AS gross_amount_paid,
           tdr.amount AS tds_deducted,
           (e.amount - tdr.amount) AS net_paid,
           tdr.trx_date AS payment_date,
           (v.pan_number IS NULL OR TRIM(v.pan_number) = '') AS no_pan
      FROM transactions tdr
      JOIN expenses e
        ON e.id = tdr.source_id
       AND e.society_id = p_society_id
       AND e.status = 'confirmed'
      JOIN vendors v
        ON v.id = e.entity_id
     WHERE tdr.society_id = p_society_id
       AND tdr.acc_id = v_tds_acc
       AND tdr.entry_side = 'Dr'
       AND tdr.source_table = 'expenses'
       AND tdr.trx_date BETWEEN v_q_start AND v_q_end
     ORDER BY tdr.trx_date, e.id;
END;
$$;

-- SECTION 4: VIEWS
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
            ga.role = 'SEC'
            AND ga.time_out IS NOT NULL
    ) AS shift_count,
    EXISTS (
        SELECT 1
        FROM gate_access ga2
        WHERE
            ga2.entity_id = u.id
            AND ga2.role = 'SEC'
            AND ga2.time_out IS NULL
    ) AS gate_pass
FROM
    users u
    JOIN security_staff s ON s.id = u.linked_id
    LEFT JOIN gate_access ga ON ga.entity_id = u.id
    AND ga.role = 'SEC'
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

-- SECTION 5: TRIGGERS
-- ════════════════════════════════════════════════════════════════

DROP TRIGGER IF EXISTS trg_validate_primary_bank_account ON societies;

CREATE TRIGGER trg_validate_primary_bank_account
    BEFORE INSERT OR UPDATE OF primary_bank_account_id ON societies
    FOR EACH ROW EXECUTE FUNCTION fn_trg_validate_primary_bank_account();

DROP TRIGGER IF EXISTS trg_receipt_hash_issue ON receipts;

CREATE TRIGGER trg_receipt_hash_issue
    BEFORE UPDATE OF status ON receipts
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_receipt_hash_issue();

DROP TRIGGER IF EXISTS trg_receipt_hash_insert ON receipts;

CREATE TRIGGER trg_receipt_hash_insert
    BEFORE INSERT ON receipts
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_receipt_hash_insert();

DROP TRIGGER IF EXISTS trg_expense_hash_issue ON expenses;

CREATE TRIGGER trg_expense_hash_issue
    BEFORE UPDATE OF status ON expenses
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_expense_hash_issue();

DROP TRIGGER IF EXISTS trg_expense_hash_insert ON expenses;

CREATE TRIGGER trg_expense_hash_insert
    BEFORE INSERT ON expenses
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_expense_hash_insert();

DROP TRIGGER IF EXISTS trg_transaction_number ON transactions;

CREATE TRIGGER trg_transaction_number
    BEFORE INSERT ON transactions
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_transaction_number();

DROP TRIGGER IF EXISTS trg_apartment_active_guard ON apartments;

CREATE TRIGGER trg_apartment_active_guard
    BEFORE UPDATE ON apartments
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_apartment_active_guard();

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

DROP TRIGGER IF EXISTS trg_concerns_assigns_updated ON concerns_assigns;

CREATE TRIGGER trg_concerns_assigns_updated
    BEFORE UPDATE ON concerns_assigns
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

DROP TRIGGER IF EXISTS trg_concerns_qr ON concerns;

CREATE TRIGGER trg_concerns_qr
    BEFORE INSERT ON concerns
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_concerns_qr();

DROP TRIGGER IF EXISTS trg_receipts_qr ON receipts;

CREATE TRIGGER trg_receipts_qr
    BEFORE INSERT ON receipts
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_receipts_qr();

DROP TRIGGER IF EXISTS trg_expenses_qr ON expenses;

CREATE TRIGGER trg_expenses_qr
    BEFORE INSERT ON expenses
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_expenses_qr();

DROP TRIGGER IF EXISTS trg_assets_qr ON assets;

CREATE TRIGGER trg_assets_qr
    BEFORE INSERT ON assets
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_assets_qr();

DROP TRIGGER IF EXISTS trg_visitors_qr ON visitors;

CREATE TRIGGER trg_visitors_qr
    BEFORE INSERT ON visitors
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_visitors_qr();

DROP TRIGGER IF EXISTS trg_patrol_locations_qr ON patrol_locations;

CREATE TRIGGER trg_patrol_locations_qr
    BEFORE INSERT ON patrol_locations
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_patrol_locations_qr();

DROP TRIGGER IF EXISTS trg_concerns_assigns_sync_status ON concerns_assigns;

CREATE TRIGGER trg_concerns_assigns_sync_status
    AFTER INSERT OR UPDATE OF status OR DELETE ON concerns_assigns
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_sync_concern_status();

-- ════════════════════════════════════════════════════════════════
-- SELF-PAYMENT REPORTING & CONFIRMATION
-- ════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_self_report_receivable_by_bill_group(
    p_bill_group_id UUID,
    p_reported_by INT,
    p_mode VARCHAR,
    p_amount NUMERIC,
    p_reference VARCHAR
) RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
    v_has_unverified BOOLEAN;
    v_total_pending NUMERIC;
    v_entity_id INT;
    v_role VARCHAR(10);
    v_owns BOOLEAN;
BEGIN
    IF p_amount <= 0 THEN RETURN 'Error: amount must be > 0'; END IF;

    SELECT entity_id, role INTO v_entity_id, v_role
      FROM receivables WHERE bill_group_id = p_bill_group_id LIMIT 1;
    IF NOT FOUND THEN
        RETURN 'Error: Bill group not found';
    END IF;
    IF v_role <> 'apartment' THEN
        RETURN 'Error: Only apartment dues can be self-reported';
    END IF;

    -- Ownership check: the reporting user must be the 'apartment' user
    -- linked to this bill group's apartment — the SQL function is the trust
    -- boundary, not the client-supplied bill_group_id in the form payload
    -- (mirrors this codebase's existing IDOR-hardening convention).
    SELECT EXISTS (
        SELECT 1 FROM users
         WHERE id = p_reported_by AND role = 'apartment' AND linked_id = v_entity_id
    ) INTO v_owns;
    IF NOT v_owns THEN
        RETURN 'Error: You are not authorized to report a payment for this bill';
    END IF;

    -- Check for race conditions / existing claims
    SELECT EXISTS (
        SELECT 1 FROM receivables 
        WHERE bill_group_id = p_bill_group_id 
          AND status = 'unverified'
    ) INTO v_has_unverified;

    IF v_has_unverified THEN
        RETURN 'Error: A claim is already pending verification for this bill group.';
    END IF;

    SELECT COALESCE(SUM(amount - paid_amount), 0)
      INTO v_total_pending
      FROM receivables
     WHERE bill_group_id = p_bill_group_id
       AND status IN ('pending', 'partial');
       
    IF v_total_pending <= 0 THEN
        RETURN 'Error: Nothing outstanding on this bill group.';
    END IF;

    UPDATE receivables
       SET status = 'unverified',
           reported_amount = p_amount,
           reported_mode = p_mode,
           reported_reference = p_reference,
           reported_at = NOW(),
           reported_by = p_reported_by
     WHERE bill_group_id = p_bill_group_id
       AND status IN ('pending', 'partial');

    RETURN 'Success: Payment reported. Awaiting verification.';
END;
$$;

CREATE OR REPLACE FUNCTION fn_reject_apartment_self_payment(
    p_type VARCHAR, -- 'receipt' or 'bill_group'
    p_id TEXT,      -- receipt_id or bill_group_id
    p_confirmed_by INT,
    p_penalty_amount NUMERIC DEFAULT 0
) RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
    v_entity_id INT;
    v_society_id INT;
    v_penalty_acc INT;
BEGIN
    IF p_type = 'receipt' THEN
        UPDATE receipts
           SET status = 'rejected',
               confirmed_by = p_confirmed_by,
               confirmed_at = NOW()
         WHERE id = p_id::INT AND status = 'pending'
         RETURNING entity_id, society_id INTO v_entity_id, v_society_id;
         
        IF NOT FOUND THEN RETURN 'Error: Receipt not found or not pending.'; END IF;
        
    ELSIF p_type = 'bill_group' THEN
        -- UPDATE doesn't support LIMIT in Postgres; capture entity_id/
        -- society_id first (identical across every row in one bill group),
        -- then update all matching rows without relying on RETURNING...INTO
        -- to silently pick a row.
        SELECT entity_id, society_id INTO v_entity_id, v_society_id
          FROM receivables
         WHERE bill_group_id = p_id::UUID AND status = 'unverified'
         LIMIT 1;

        IF NOT FOUND THEN RETURN 'Error: Bill group not found or not unverified.'; END IF;

        UPDATE receivables
           SET status = 'pending', -- revert to pending
               reported_amount = NULL,
               reported_mode = NULL,
               reported_reference = NULL,
               reported_at = NULL,
               reported_by = NULL
         WHERE bill_group_id = p_id::UUID AND status = 'unverified';
    ELSE
        RETURN 'Error: Invalid type';
    END IF;

    IF p_penalty_amount > 0 THEN
        -- Find Bank Charges account or fallback to Maintenance
        SELECT id INTO v_penalty_acc FROM accounts 
         WHERE society_id = v_society_id AND name ILIKE '%Bank Charges%' LIMIT 1;
         
        IF v_penalty_acc IS NULL THEN
            SELECT id INTO v_penalty_acc FROM accounts 
             WHERE society_id = v_society_id AND name ILIKE '%Maintenance%' LIMIT 1;
        END IF;

        INSERT INTO receivables (
            society_id, entity_id, role,
            acc_id, description, period_month,
            base_amount, amount, paid_principal, due_date, status
        ) VALUES (
            v_society_id, v_entity_id, 'apartment',
            v_penalty_acc, 'Bank Bounce Penalty', DATE_TRUNC('month', CURRENT_DATE)::DATE,
            p_penalty_amount, p_penalty_amount, 0, CURRENT_DATE, 'pending'
        );
    END IF;

    RETURN 'Success: Payment rejected.';
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- INCOME TAX MUTUALITY REPORTING
-- ════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION fn_income_tax_summary_fy(
    p_society_id INT,
    p_fy         INT
) RETURNS TABLE (
    category VARCHAR, -- 'Income' or 'Expense'
    nature VARCHAR,   -- 'mutual' or 'non_mutual'
    total_amount NUMERIC
) LANGUAGE plpgsql AS $$
DECLARE
    v_fy_start DATE := MAKE_DATE(p_fy, 4, 1);
    v_fy_end   DATE := MAKE_DATE(p_fy + 1, 3, 31);
BEGIN
    RETURN QUERY
    SELECT 
        'Income'::VARCHAR as category,
        a.mutuality_nature as nature,
        SUM(t.amount) as total_amount
    FROM transactions t
    JOIN accounts a ON t.acc_id = a.id
    WHERE t.society_id = p_society_id
      AND t.trx_date BETWEEN v_fy_start AND v_fy_end
      AND t.entry_side = 'Cr'
      AND t.status = 'paid'
    GROUP BY a.mutuality_nature
    
    UNION ALL
    
    SELECT 
        'Expense'::VARCHAR as category,
        a.mutuality_nature as nature,
        SUM(t.amount) as total_amount
    FROM transactions t
    JOIN accounts a ON t.acc_id = a.id
    WHERE t.society_id = p_society_id
      AND t.trx_date BETWEEN v_fy_start AND v_fy_end
      AND t.entry_side = 'Dr'
      AND t.status = 'paid'
    GROUP BY a.mutuality_nature;
END;
$$;
