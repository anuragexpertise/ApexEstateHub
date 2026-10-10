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

CREATE TABLE societies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    PAN_number VARCHAR(10),
    TAN_number VARCHAR(10),
    logo VARCHAR(100),
    address TEXT,
    email VARCHAR(100),
    phone VARCHAR(20),
    secretary_name VARCHAR(100),
    secretary_phone VARCHAR(20),
    secretary_email VARCHAR(100),
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
    gate_logic VARCHAR(10) DEFAULT 'both' CHECK (
        gate_logic IN ('entry', 'exit', 'both')
    ),
    duty_hrs VARCHAR(2) DEFAULT '8' CHECK (duty_hrs IN ('8', '12')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    gstin VARCHAR(15),
    registration_number VARCHAR(100),
    -- state (2026-09, RCM Phase 3): the society's own state, for
    -- intra- vs. inter-state determination on RCM supplies (compared
    -- against vendors.state to decide CGST+SGST vs. IGST). Previously
    -- absent entirely — flagged in an earlier audit as blocking any
    -- state-aware GST logic; state_compliance_thresholds could never
    -- actually be resolved per-society state either, though that
    -- remains a separate, still-open gap (thresholds table has no
    -- per-state row differentiation to key off of yet).
    state VARCHAR(50),
    -- How the society is constituted; with `state` it selects the legal scheme (fn_sync_society_regime).
    -- Existing societies were all treated as apartment owners' associations, hence the default.
    constitution VARCHAR(20) NOT NULL DEFAULT 'AOA' CHECK (constitution IN ('AOA', 'REG_SOCIETY', 'COOP', 'GENERIC')),
    -- signing_secret_enc: this society's own QR SIGNING_SECRET, Fernet-encrypted
    -- (reversible) under the deployment's SECRET_VAULT_KEY — see
    -- app/services/secret_vault.py. It must be reversible, because an HMAC key
    -- cannot be recovered from a hash: a one-way value could only ever act as a
    -- "setup completed" flag, never as real key material. NULL means this society
    -- hasn't completed the Setup Wizard yet (or hasn't set a signing secret), so
    -- its QR codes stay unsigned until it is. Also doubles as the "has this
    -- society finished onboarding" flag the Setup Wizard trigger checks.
    signing_secret_enc TEXT,
    primary_bank_account_id INT,
    -- Per-society override of the legal regime's cash-payment enforcement:
    -- 'warn' (default NULL behaviour) logs an over-limit cash payment,
    -- 'block' refuses it. Kept as society data rather than a global switch
    -- because the rule is enforced per AOA bye-laws / general-body resolution.
    cash_limit_mode VARCHAR(5) CHECK (cash_limit_mode IN ('warn', 'block'))
);

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    email VARCHAR(100) NOT NULL UNIQUE,
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
    user_type VARCHAR(20) CHECK (user_type IN ('owner', 'family', 'tenant', 'visitor')) DEFAULT 'owner',
    -- Fallback qr_version for admin logins with no apartments row to key
    -- off (linked_id IS NULL — the seeded first-admin case). A promoted
    -- apartment owner (linked_id = apartments.id) uses apartments.qr_version
    -- instead; this column is only ever consulted when linked_id is NULL.
    -- See app/services/qr_service.py _current_qr_version's ADM branch.
    -- Random 4-digit nonce, not a sequential counter — the ALTER COLUMN
    -- ... SET DEFAULT right after push_subscriptions below covers already-
    -- provisioned databases; see qr_service.revoke_and_reissue for how it
    -- actually gets bumped (always admin-initiated, never automatic).
    qr_version INT NOT NULL DEFAULT (1000 + FLOOR(RANDOM() * 9000))::INT,
    login_method VARCHAR(20) DEFAULT 'password',
    is_master_admin BOOLEAN NOT NULL DEFAULT FALSE,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMP,
    reset_token VARCHAR(64),
    reset_token_expires TIMESTAMP,
    -- A4: TRUE until the user sets a password of their own. Every account is
    -- created with a password someone else chose (Master for the admin, the
    -- admin for residents/vendors/guards), so this defaults to TRUE and is
    -- cleared by change_password() / reset_password().
    must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
    -- A11: shared (cross-worker) 5-second throttle for Setup Wizard submits.
    setup_submit_at TIMESTAMP,
    push_token TEXT,
    push_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    last_login TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INT REFERENCES users (id)
);

-- qr_version is a random 4-digit nonce, not a sequential counter, and
-- only ever changes via an explicit admin revoke/reissue action — see
-- app/services/qr_service.py revoke_and_reissue.

CREATE TABLE push_subscriptions (
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
CREATE TABLE accounts (
    id SERIAL,
    PRIMARY KEY (society_id, id),
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
    depreciation_percent NUMERIC(5, 2) DEFAULT 100.00,
    is_depreciable BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    -- created_by/updated_by removed: accounts (chart-of-accounts) are
    -- admin-only create+edit per _PORTAL_PERMS — no other role ever
    -- touches this table, so tracking WHICH admin added no value.
    CONSTRAINT uq_account_society_name UNIQUE (society_id, name),
    CONSTRAINT fk_account_parent FOREIGN KEY (society_id, parent_account_id) REFERENCES accounts (society_id, id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED,
    mutuality_nature VARCHAR(10) CHECK (
        mutuality_nature IN ('mutual', 'non_mutual')
    ) DEFAULT 'mutual',
    tds_section VARCHAR(10),
    -- Statutory principal lock on a fund account. 100 means "100% of this
    -- account's balance is statutory principal that may not be drawn down",
    -- which is what UP RERA / the UP AOA Model Bye-Laws say about a builder's
    -- Corpus Fund handover: interest earned on it is income (cr. Interest
    -- Income, freely usable), but the principal itself is inviolable.
    -- Previously this rule existed only as display text in
    -- fund_management_callbacks.py's FUND_TYPE_PATTERNS —
    -- fn_process_fund_utilization would draw from the Corpus account without
    -- complaint. The lock is data, not prose, so the guard is
    -- jurisdiction-neutral: any fund account an admin sets to 100 is
    -- protected, whatever it is called. Expressed as a percentage rather than
    -- an absolute amount so the lock survives further contributions: a Corpus
    -- Fund that accrues is still fully locked, while a fund an admin
    -- deliberately unlocks just sets 0.
    statutory_lock_pct NUMERIC(5,2) NOT NULL DEFAULT 0
        CHECK (statutory_lock_pct >= 0 AND statutory_lock_pct <= 100)
);

CREATE TABLE apartments (
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
    qr_version INT NOT NULL DEFAULT (1000 + FLOOR(RANDOM() * 9000))::INT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    -- Act s.5(2) area share: until the Declaration of Apartment/Deed of
    -- Apartment percentage is keyed in, a flat's share of the common
    -- expenses is its carpet-area share. fn_backfill_undivided_interest
    -- seeds it from apartment_size; the UI lets an admin override it once
    -- the real Declaration figures are available.
    undivided_interest_pct NUMERIC(9, 6)
        CHECK (undivided_interest_pct IS NULL OR (undivided_interest_pct > 0 AND undivided_interest_pct <= 100)),
    CONSTRAINT uq_apartment_society_flat UNIQUE (society_id, flat_number)
);

CREATE TABLE vendors (
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
    qr_version INT NOT NULL DEFAULT (1000 + FLOOR(RANDOM() * 9000))::INT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    -- created_by removed: only admin ever creates a vendor (enrollment).
    -- updated_by kept: a vendor can self-edit their own profile too.
    updated_by INT REFERENCES users (id),
    pan_number VARCHAR(10),
    gstin VARCHAR(15),
    rcm_category VARCHAR(50),
    state VARCHAR(50),
    payee_type VARCHAR(20) CHECK (payee_type IN ('individual', 'huf', 'company', 'firm', 'llp', 'other')) DEFAULT 'other'
);

CREATE TABLE security_staff (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    photo VARCHAR(255),
    id_proof VARCHAR(255),
    mobile VARCHAR(15),
    joining_date DATE DEFAULT CURRENT_DATE,
    shift VARCHAR(20),
    salary_per_shift NUMERIC(10, 2),
    ptl_penalty NUMERIC(10, 2) DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    qr_version INT NOT NULL DEFAULT (1000 + FLOOR(RANDOM() * 9000))::INT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    -- created_by removed: only admin ever creates a guard (enrollment).
    -- updated_by kept: a guard can self-edit their own profile too.
    updated_by INT REFERENCES users (id)
);

-- Direct employees for EPF/ESIC tracking (distinct from security_staff)
CREATE TABLE employees (
    id                  SERIAL PRIMARY KEY,
    society_id          INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    name                VARCHAR(100) NOT NULL,
    designation         VARCHAR(50),
    department          VARCHAR(50),
    pan_number          VARCHAR(10),
    uan_number          VARCHAR(20),          -- Universal Account Number for EPF
    esic_number         VARCHAR(20),
    date_of_joining     DATE NOT NULL,
    date_of_leaving     DATE,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    basic_salary        NUMERIC(12,2),
    created_by          INT REFERENCES users (id),
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP,
    updated_by          INT REFERENCES users (id)
);
CREATE INDEX idx_employees_society ON employees (society_id, is_active);

-- Same DROP-then-reset-DEFAULT treatment as users above — see that
-- comment block for why last_printed_at/last_emailed_at are being
-- removed again in the same release they were added.

CREATE TABLE assets (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    company_name VARCHAR(100),
    asset_name VARCHAR(100) NOT NULL,
    asset_SNo VARCHAR(50),
    purchase_date DATE,
    installation_date DATE,
    purchase_value NUMERIC(12, 2),
    acc_id INT,
    FOREIGN KEY (society_id, acc_id) REFERENCES accounts (society_id, id), -- asset class account (e.g. Furniture 61)
    depreciation_rate NUMERIC(5, 2),
    last_depreciation_date DATE,
    disposed BOOLEAN NOT NULL DEFAULT FALSE,
    disposed_at DATE,
    sale_value NUMERIC(12, 2),
    sale_acc_id INT,
    FOREIGN KEY (society_id, sale_acc_id) REFERENCES accounts (society_id, id), -- Selling Asset income account (e.g. 212)
    disposed_by INT REFERENCES users (id),
    itc_claimed NUMERIC(12, 2) DEFAULT 0, -- ITC claimed at purchase, if any (sec. 16 CGST Act); 0 = no ITC ever claimed on this asset
    gst_disposal_liability NUMERIC(12, 2), -- sec. 18(6)/Rule 44(6) liability computed at disposal, for audit trail
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    -- created_by/updated_by removed: assets are admin-only create+edit
    -- (dispose_asset is also roles:["admin"]) — disposed_by is kept,
    -- that's a distinct action already covered above.
    qr_payload VARCHAR(255),
    qr_version INT NOT NULL DEFAULT (1000 + FLOOR(RANDOM() * 9000))::INT
);

-- deposits (2026-09): intangible investment register — FDs, bonds, mutual
-- fund units, etc — the "ALL Deposits" counterpart to `assets` above (which
-- covers tangible fixed assets only). Mirrors `assets`' shape (purchase/
-- disposal pair + acc_id/sale_acc_id posting accounts) so fn_deposit_holdings_fy
-- and future ledger-posting functions can follow the exact same pattern as
-- fn_buy_asset/fn_dispose_asset. No admin create/dispose UI wired up yet —
-- see fn_deposit_holdings_fy's comment.
CREATE TABLE deposits (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    deposit_name VARCHAR(100) NOT NULL, -- e.g. "SBI FD 40021", "HDFC Liquid Fund"
    isin VARCHAR(20), -- ISIN, or the bank's FD/account reference if no ISIN applies
    purchase_date DATE,
    purchase_value NUMERIC(12, 2),
    acc_id INT,
    FOREIGN KEY (society_id, acc_id) REFERENCES accounts (society_id, id), -- Investments asset account
    disposed BOOLEAN NOT NULL DEFAULT FALSE,
    sale_date DATE,
    sale_value NUMERIC(12, 2),
    sale_acc_id INT,
    FOREIGN KEY (society_id, sale_acc_id) REFERENCES accounts (society_id, id), -- Cash/Bank account credited on maturity/sale
    disposed_by INT REFERENCES users (id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- DEPOSIT CREATION / DISPOSAL (2026-09): mirrors fn_buy_asset / fn_dispose_asset
-- for the intangible `deposits` table (FDs, bonds, mutual fund units, etc.)
-- ════════════════════════════════════════════════════════════════════════════

-- fn_buy_deposit: create a new intangible investment (FD, bond, MF unit, etc.)
-- Mirrors fn_buy_asset but for the `deposits` table; posts Dr investment account,
-- Cr cash/bank, and an expense row for the purchase.

CREATE OR REPLACE FUNCTION fn_buy_deposit(
    p_society_id        INT,
    p_deposit_name      VARCHAR,
    p_isin              VARCHAR,
    p_purchase_value    NUMERIC,
    p_acc_id            INT,
    p_purchase_date     DATE    DEFAULT CURRENT_DATE,
    p_mode              VARCHAR DEFAULT 'cash',
    p_created_by        INT     DEFAULT NULL,
    p_particulars       TEXT    DEFAULT NULL
)
RETURNS TABLE(deposit_id INT, expense_id INT, transaction_id INT, journal_id INT)
LANGUAGE plpgsql AS $$
DECLARE
    v_deposit_id INT;
    v_expense_id INT;
    v_trx_id     INT;
    v_journal_id INT;
    v_bank_acc   INT;
    v_desc       TEXT;
BEGIN
    IF p_acc_id IS NULL THEN
        RAISE EXCEPTION 'acc_id (investment class account) is required';
    END IF;
    IF p_purchase_value IS NULL OR p_purchase_value <= 0 THEN
        RAISE EXCEPTION 'purchase_value must be > 0';
    END IF;

    INSERT INTO deposits(
        society_id, deposit_name, isin, purchase_date, purchase_value,
        acc_id, created_at
    ) VALUES (
        p_society_id, p_deposit_name, p_isin, p_purchase_date, p_purchase_value,
        p_acc_id, NOW()
    ) RETURNING id INTO v_deposit_id;

    v_desc := COALESCE(p_particulars, 'Deposit Purchase - ' || p_deposit_name);
    v_bank_acc := fn_resolve_bank_leg(p_society_id, p_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    -- Dr: investment class account
    INSERT INTO transactions(
        society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id, journal_id
    ) VALUES (
        p_society_id, 'Dr', p_purchase_date, p_acc_id, v_deposit_id, 'deposits', v_desc,
        p_purchase_value, p_mode, 'paid', p_created_by, NOW(), 'deposits', v_deposit_id, v_journal_id
    ) RETURNING id INTO v_trx_id;

    -- Cr: cash / bank paired side
    IF v_bank_acc IS NOT NULL THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            p_society_id, 'Cr', p_purchase_date, v_bank_acc, v_deposit_id, 'deposits',
            'Cash paid - ' || v_desc,
            p_purchase_value, p_mode, 'paid', p_created_by, NOW(), 'deposits', v_deposit_id, v_journal_id
        );
    END IF;

    INSERT INTO expenses(
        society_id, user_id, entity_id, role,
        expense_date, acc_id, particulars, amount, mode,
        status, confirmed_by, confirmed_at, source_reference, created_at
    ) VALUES (
        p_society_id, p_created_by, v_deposit_id, 'deposits',
        p_purchase_date, p_acc_id, v_desc, p_purchase_value, p_mode,
        'confirmed', p_created_by, NOW(), NULL, NOW()
    ) RETURNING id INTO v_expense_id;

    RETURN QUERY SELECT v_deposit_id, v_expense_id, v_trx_id, v_journal_id;
END;
$$;

-- fn_dispose_deposit: dispose/mature an intangible investment (FD maturity, bond sale, MF redemption)
-- Mirrors fn_dispose_asset but for the `deposits` table; posts Dr cash/bank, Cr investment account,
-- and records gain/loss via STCG/LTCG per the 36-month test (sec 2(42A)).

CREATE OR REPLACE FUNCTION fn_dispose_deposit(
    p_deposit_id    INT,
    p_sale_value    NUMERIC,
    p_mode          VARCHAR DEFAULT 'cash',
    p_created_by    INT     DEFAULT NULL,
    p_sale_date     DATE    DEFAULT CURRENT_DATE,
    p_particulars   TEXT    DEFAULT NULL,
    p_acc_id        INT     DEFAULT NULL,
    p_tds_amount    NUMERIC DEFAULT 0
)
RETURNS TABLE(receipt_id INT, transaction_id INT, journal_id INT)
LANGUAGE plpgsql AS $$
DECLARE
    v_deposit     deposits%ROWTYPE;
    v_acc_id      INT;
    v_bank_acc    INT;
    v_receipt_id  INT;
    v_trx_id      INT;
    v_journal_id  INT;
    v_desc        TEXT;
    v_net_sale    NUMERIC(15,2);
    v_tds_rec_acc INT;
BEGIN
    SELECT * INTO v_deposit FROM deposits WHERE id = p_deposit_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Deposit not found'; END IF;
    IF v_deposit.disposed THEN RAISE EXCEPTION 'Deposit already disposed'; END IF;
    IF p_sale_value IS NULL OR p_sale_value <= 0 THEN
        RAISE EXCEPTION 'sale_value must be > 0';
    END IF;

    v_acc_id := COALESCE(p_acc_id, v_deposit.sale_acc_id);
    IF v_acc_id IS NULL THEN
        SELECT id INTO v_acc_id FROM accounts
        WHERE society_id = v_deposit.society_id AND tab_name = 'SellAs'
        LIMIT 1;
    END IF;

    v_desc := COALESCE(p_particulars, 'Deposit Sale/Maturity - ' || v_deposit.deposit_name);
    v_bank_acc := fn_resolve_bank_leg(v_deposit.society_id, p_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    v_net_sale := p_sale_value - COALESCE(p_tds_amount, 0);
    IF v_net_sale < 0 THEN RAISE EXCEPTION 'TDS amount cannot exceed sale value'; END IF;

    -- Dr: TDS Receivable
    IF COALESCE(p_tds_amount, 0) > 0 THEN
        SELECT id INTO v_tds_rec_acc FROM accounts
        WHERE society_id = v_deposit.society_id AND tab_name = 'TDSRec'
        LIMIT 1;

        IF v_tds_rec_acc IS NULL THEN
            RAISE EXCEPTION 'Cannot apply TDS: No TDS Receivable account configured for this society.';
        END IF;

        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_deposit.society_id, 'Dr', p_sale_date, v_tds_rec_acc, p_deposit_id, 'deposits',
            'TDS Deducted on Deposit Sale/Maturity - ' || v_deposit.deposit_name,
            p_tds_amount, 'journal', 'paid', p_created_by, NOW(), 'deposits', p_deposit_id, v_journal_id
        );
    END IF;

    -- Dr: cash / bank (sale proceeds) — non-cash mode only
    IF v_bank_acc IS NOT NULL AND v_net_sale > 0 THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_deposit.society_id, 'Dr', p_sale_date, v_bank_acc, p_deposit_id, 'deposits',
            'Cash received - ' || v_desc,
            v_net_sale, p_mode, 'paid', p_created_by, NOW(), 'deposits', p_deposit_id, v_journal_id
        );
    END IF;

    -- Cr: investment class account, for the FULL sale value — this is the
    -- "deductions" leg for the block-of-assets deduction logic (applies
    -- to the intangible block too). No per-deposit gain/loss leg is
    -- posted here; the STCG/LTCG split is purely informational and
    -- computed in fn_deposit_holdings_fy at the time of the statement.
    INSERT INTO transactions(
        society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id, journal_id
    ) VALUES (
        v_deposit.society_id, 'Cr', p_sale_date, v_deposit.acc_id, p_deposit_id, 'deposits',
        'Deposit disposed (moneys payable) - ' || v_deposit.deposit_name,
        p_sale_value, p_mode, 'paid', p_created_by, NOW(), 'deposits', p_deposit_id, v_journal_id
    ) RETURNING id INTO v_trx_id;

    RETURN QUERY SELECT v_receipt_id, v_trx_id, v_journal_id;
END;
$$;

CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    event_date DATE NOT NULL,
    event_time TIME,
    venue VARCHAR(200),
    open_to VARCHAR(20) DEFAULT 'all',
    account_id INT,
    FOREIGN KEY (society_id, account_id) REFERENCES accounts (society_id, id), -- e.g. event income or event expense account
    ticket_name VARCHAR(20) DEFAULT 'Adult',
    ticket_price NUMERIC(10, 2) DEFAULT 0,
    ticket_name2 VARCHAR(20) DEFAULT 'Child',
    ticket_price2 NUMERIC(10, 2) DEFAULT 0,
    image TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE concerns (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    apartment_id INT REFERENCES apartments (id) ON DELETE SET NULL,
    concern_type VARCHAR(50),
    description TEXT,
    preferred_time TIME,
    status VARCHAR(20) NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'assigned', 'resolved', 'closed')),
    image TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by INT REFERENCES users (id),
    updated_at TIMESTAMP,
    updated_by INT REFERENCES users (id),
    qr_payload VARCHAR(255),
    qr_version INT NOT NULL DEFAULT (1000 + FLOOR(RANDOM() * 9000))::INT
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
-- migration_concerns_assigns_accepted_status.sql.) VND rows normally
-- start at 'invited' and progress through 'bid_submitted' before an admin
-- formally 'assigned's them — though a direct "Assign" is still allowed at
-- any point as a shortcut (e.g. price already agreed offline), which simply
-- promotes whatever row exists straight to 'assigned'. A VND row can also
-- revise its bid while still at 'bid_submitted'.
--
-- SEC rows skip 'invited'/'bid_submitted' ENTIRELY: security staff never
-- bid, so there is no invitation round for them. They are placed straight on
-- a concern at 'assigned' (the Invite modal's SEC branch, and
-- loaders.assign_concern), then follow the same assigned -> resolved path
-- as a vendor — gated on an ADM row having reached 'accepted' first.
--
-- concerns.status is KEPT (existing code, KPIs, and the
-- idx_concerns_society_status index all depend on it), but it is a
-- read-only aggregate cache synced by ONE trigger (fn_sync_concern_status,
-- below) from these rows — application code should stop writing
-- concerns.status directly for anything except the initial INSERT ('open').
--
-- Aggregate rule — "touched rows only":
--   The calculation ONLY considers rows that reached 'assigned' or beyond
--   (assigned / accepted / resolved / closed). Rows still at
--   'invited' / 'bid_submitted' / 'declined' are CANDIDATES who were never
--   formally chosen (losing bidders, everyone who opted out) and are
--   excluded entirely, so they can never hold a concern back. Counting them
--   meant a single leftover invited row kept a concern pinned at 'assigned'
--   forever even after its actual assignee had resolved — fixed 2026-08,
--   see fn_sync_concern_status below.
--
--   no touched rows                                  -> concerns.status='open'
--   all touched rows status='closed'                 -> 'closed'
--   all touched rows IN ('resolved','closed')        -> 'resolved'
--   otherwise (some touched row still working)       -> 'assigned'
--
-- Note that 'open' is a bucket covering three distinct situations — nothing
-- invited yet, candidates invited/bidding, and every candidate declined —
-- which is why the profile banner derives its wording from the actual
-- assignment rows rather than from this column alone.
-- ════════════════════════════════════════════════════════════════════════

CREATE TABLE concerns_assigns (
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

-- ════════════════════════════════════════════════════════════════════════
-- concern_transitions — D2 (append-only, source of truth for audit)
--
-- Append-only log of every state change on a concerns_assigns row.
-- concerns_assigns.status remains a materialized cache (written by the
-- workflow service, rolled up to concerns.status by the existing
-- fn_sync_concern_status trigger); THIS table is the authoritative audit trail.
-- The workflow service (app/services/workflow.py) is the only writer: it rejects
-- illegal jumps and is idempotent on (assignment_id, from_state, to_state, actor).
-- ════════════════════════════════════════════════════════════════════════
CREATE TABLE concern_transitions (
    id              SERIAL PRIMARY KEY,
    concern_id      INT NOT NULL REFERENCES concerns (id) ON DELETE CASCADE,
    assignment_id   INT REFERENCES concerns_assigns (id) ON DELETE SET NULL,
    society_id      INT REFERENCES societies (id) ON DELETE CASCADE,
    entity_role     VARCHAR(10) CHECK (entity_role IN ('ADM', 'VND', 'SEC')),
    entity_id       INT,
    from_state      VARCHAR(20),
    to_state        VARCHAR(20) NOT NULL CHECK (
        to_state IN ('invited', 'bid_submitted', 'declined', 'assigned',
                     'accepted', 'resolved', 'closed')
    ),
    actor_id        INT REFERENCES users (id),
    permission_used VARCHAR(60),  -- e.g. 'concern.assign', 'concern.resolve'
    comment         TEXT,
    evidence        JSONB,        -- doc_hash / correlation_id / before-after snapshot
    correlation_id  UUID,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_concern_transitions_concern
    ON concern_transitions (concern_id, created_at);
CREATE INDEX idx_concern_transitions_assignment
    ON concern_transitions (assignment_id, created_at);
CREATE INDEX idx_concern_transitions_society
    ON concern_transitions (society_id, created_at);

-- ── security_roster & attendance (needed before payables FK) ──
CREATE TABLE security_roster (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    security_id INT NOT NULL REFERENCES security_staff (id) ON DELETE CASCADE,
    roster_date DATE NOT NULL,
    shift_type VARCHAR(20) CHECK (
        shift_type IN (
            'morning',
            'evening',
            'night',
            'day'
        )
    ),
    attendance_status VARCHAR(20) DEFAULT 'scheduled' CHECK (
        attendance_status IN (
            'scheduled',
            'present',
            'absent',
            'leave_paid',
            'leave_unpaid'
        )
    ),
    assigned_by INT REFERENCES users (id),
    created_at TIMESTAMP DEFAULT NOW(),
    -- created_by removed: roster assignment is admin-only (assigned_by
    -- already records who assigned the shift).
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
CREATE TABLE receivables (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    entity_id INT NOT NULL,
    role VARCHAR(10) NOT NULL CHECK (
        role IN (
            'apartment',
            'vendor',
            'security',
            'society'
        )
    ),
    acc_id INT, -- income account for base amount
    FOREIGN KEY (society_id, acc_id) REFERENCES accounts (society_id, id),
    interest_acc_id INT, -- income account for interest (NULL = same as acc_id)
    FOREIGN KEY (society_id, interest_acc_id) REFERENCES accounts (society_id, id),
    description TEXT NOT NULL DEFAULT 'Receivable', -- becomes acc_particulars in transactions
    period_month DATE, -- first-of-month; NULL for non-periodic rows
    base_amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    interest_amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    interest_months_applied NUMERIC(10, 4) NOT NULL DEFAULT 0,
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
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
    -- created_by removed: receivables are always system-generated (auto
    -- billing, penalties, advance-credit) or admin-confirmed
    -- (confirmed_by already covers that) — no INSERT path ever stamped it.
,
    bill_group_id UUID DEFAULT gen_random_uuid (),
    reported_amount NUMERIC(10, 2),
    reported_mode VARCHAR(20),
    reported_reference VARCHAR(255),
    reported_at TIMESTAMP,
    reported_by INT REFERENCES users (id),
    -- 'common_expense' (default) = maintenance, fund contributions, GST on them and any other sum
    -- the Association assesses on owners (Act s.2 "common expenses"). 'transfer_fee' = the bye-law
    -- transfer fee: payable by the TRANSFEROR on a sale, so it is not a common-expense arrear for
    -- bye-law 7 or the s.22 six-month test (and does not pass to a purchaser under s.23).
    charge_kind VARCHAR(20) NOT NULL DEFAULT 'common_expense'
        CHECK (charge_kind IN ('common_expense', 'transfer_fee', 'depreciation_fund', 'other'))
);

-- ── PAYMENT LOG ────────────────────────────────────────────────────
-- Bye-law 7 tests arrears ON A PAST DATE (last day of the year before the election), so the
-- balance today is the wrong number: an owner who paid after that date is still barred, one who
-- fell behind after it is not. receivables only stores running totals, so every change to
-- paid_amount / paid_principal is logged here by trigger, whatever code path made it.
-- paid_on is the posting date (CURRENT_DATE) unless the session sets app.payment_date
-- (SET LOCAL app.payment_date = 'YYYY-MM-DD') to back-date a late-entered receipt.
CREATE TABLE receivable_payment_log (
    id              BIGSERIAL PRIMARY KEY,
    society_id      INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    receivable_id   INT NOT NULL REFERENCES receivables (id) ON DELETE CASCADE,
    paid_on         DATE NOT NULL,
    principal_delta NUMERIC(12, 2) NOT NULL,
    total_delta     NUMERIC(12, 2) NOT NULL,
    logged_at       TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_receivable_payment_log_rec ON receivable_payment_log (receivable_id, paid_on);

CREATE OR REPLACE FUNCTION fn_trg_log_receivable_payment() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    v_total NUMERIC := NEW.paid_amount - COALESCE(OLD.paid_amount, 0);
    v_prin  NUMERIC;
    v_on    DATE := COALESCE(NULLIF(current_setting('app.payment_date', TRUE), '')::DATE, CURRENT_DATE);
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_prin := NEW.paid_principal;
    ELSIF NEW.paid_principal IS DISTINCT FROM OLD.paid_principal THEN
        v_prin := NEW.paid_principal - OLD.paid_principal;
    ELSE
        -- paid_amount moved without paid_principal (a hand-written UPDATE): treat it as principal
        -- up to what principal is still unpaid, so such a payment is never lost from the log.
        v_prin := LEAST(v_total, GREATEST((NEW.amount - NEW.interest_amount) - OLD.paid_principal, 0));
    END IF;
    IF v_total <> 0 OR v_prin <> 0 THEN
        INSERT INTO receivable_payment_log (society_id, receivable_id, paid_on, principal_delta, total_delta)
        VALUES (NEW.society_id, NEW.id, v_on, v_prin, v_total);
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER trg_receivable_payment_log_upd
    AFTER UPDATE OF paid_amount, paid_principal ON receivables
    FOR EACH ROW
    WHEN (NEW.paid_amount IS DISTINCT FROM OLD.paid_amount OR NEW.paid_principal IS DISTINCT FROM OLD.paid_principal)
    EXECUTE FUNCTION fn_trg_log_receivable_payment();
CREATE TRIGGER trg_receivable_payment_log_ins
    AFTER INSERT ON receivables
    FOR EACH ROW
    WHEN (NEW.paid_amount > 0 OR NEW.paid_principal > 0)
    EXECUTE FUNCTION fn_trg_log_receivable_payment();

-- ── BANK RECONCILIATION ────────────────────────────────────────────
-- bank_statement_lines: raw rows from an admin-uploaded CSV/Excel bank
-- statement, kept even after matching (unlike a "consume and discard"
-- import) so every reconciliation is traceable back to the actual bank
-- line — mirrors the audit-trail convention already used by receipts/
-- expenses (confirmed_by/confirmed_at). batch_id groups all rows from
-- one upload so a bad upload can be identified together, though rows
-- are not deleted as a batch (a matched row shouldn't vanish once a
-- receipt/expense depends on it).
CREATE TABLE bank_statement_lines (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    txn_date DATE NOT NULL,
    description TEXT,
    debit NUMERIC(10, 2),
    credit NUMERIC(10, 2),
    reference_no VARCHAR(100),
    balance NUMERIC(12, 2),
    batch_id UUID NOT NULL,
    matched_entity VARCHAR(10) CHECK (
        matched_entity IN ('receipt', 'expense')
    ),
    matched_id INT,
    match_confidence VARCHAR(10) CHECK (
        match_confidence IN ('exact', 'fuzzy', 'manual')
    ),
    reconciled BOOLEAN NOT NULL DEFAULT FALSE,
    -- Which bank account this statement was drawn from (2026-09). NULL
    -- means "the society's primary account" and is exactly what every row
    -- uploaded before this column existed already means, so the whole
    -- existing reconciliation history stays valid untouched. It only has to
    -- be populated once a society actually keeps a second, separately-held
    -- account (e.g. the fund -> bank mapping in fund_bank_account_map),
    -- because before this column a statement from a non-primary account was
    -- reconciled against receipts regardless of which physical account the
    -- money had actually landed in — the money landed correctly, but the
    -- statement it was matched against was the wrong document.
    bank_acc_id INT,
    uploaded_by INT REFERENCES users (id),
    uploaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CHECK (
        num_nonnulls (debit, credit) = 1
    ),
    -- The bank account a line belongs to can never be another society's
    -- account. A single-column FK on bank_acc_id alone would permit exactly
    -- that, because accounts.id is only unique per society.
    CONSTRAINT fk_bank_lines_account FOREIGN KEY (society_id, bank_acc_id)
        REFERENCES accounts (society_id, id) ON DELETE SET NULL
);

-- ── RECEIPTS — manual credits, deemed paid on creation ────────
CREATE TABLE receipts (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id),
    entity_id INT,
    role VARCHAR(10) CHECK (
        role IN (
            'apartment',
            'vendor',
            'security',
            'assets',
            'other'
        )
    ),
    receipt_date DATE NOT NULL,
    acc_id INT, -- income account (Cr) — IS the category
    FOREIGN KEY (society_id, acc_id) REFERENCES accounts (society_id, id),
    particulars TEXT NOT NULL, -- human-readable label; suggested from Python PARTICULARS_TEMPLATES
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    mode VARCHAR(20) DEFAULT 'cash' CHECK (
        mode IN (
            'cash',
            'cheque',
            'upi',
            'card',
            'bank',
            'crypto',
            'neft',
            'rtgs',
            'imp'
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
    created_by INT REFERENCES users (id),
    reconciled_at TIMESTAMP,
    reconciled_by INT REFERENCES users(id),
    bank_statement_line_id INT REFERENCES bank_statement_lines (id),
    qr_version INT NOT NULL DEFAULT (1000 + FLOOR(RANDOM() * 9000))::INT
);

COMMENT ON COLUMN receipts.user_id IS 'User who recorded/submitted this receipt (creator), NOT who verified it — see confirmed_by.';

-- ── NOCS — persisted No-Objection Certificates, one row per issuance ──
-- Previously NOCs were generated on the fly with no DB record at all, so
-- there was nothing for a verification QR to point at. This gives every
-- issued NOC a real id/certificate number, an audit trail (who issued it,
-- when, for which apartment), and a status a security guard's scan can
-- check (valid / expired / revoked) — mirrors the receipts/expenses
-- pattern (qr_payload, last_printed_at, last_emailed_at) already in use.
CREATE TABLE nocs (
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
    valid_until DATE NOT NULL, -- last day of the current month
    revoked_at TIMESTAMP,
    revoked_by INT REFERENCES users (id),
    qr_payload VARCHAR(255),
    last_printed_at TIMESTAMP,
    last_emailed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    -- created_by removed: "Issue NOC" is roles:["admin"] only.
    qr_version INT NOT NULL DEFAULT (1000 + FLOOR(RANDOM() * 9000))::INT
);

COMMENT ON COLUMN nocs.status IS 'valid/expired are derived by validate_noc_qr() comparing valid_until to today; revoked is the only status ever written directly (via an explicit revoke action).';

-- society_agreements (2026-09) — persisted record of the EstateHub
-- Software License / Terms of Service Agreement's execution page,
-- auto-generated the moment a society completes the Setup Wizard (see
-- submit_setup_wizard / _get_or_create_agreement). Mirrors nocs' pattern
-- of a body_text snapshot: society/secretary details are copied in at
-- generation time rather than always read live off `societies`, so a
-- later profile edit (secretary changes, address changes) never rewrites
-- what was actually agreed to and signed at onboarding. UNIQUE(society_id)
-- — one agreement per society, get-or-create, not reissued.
CREATE TABLE society_agreements (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL UNIQUE REFERENCES societies (id) ON DELETE CASCADE,
    agreement_no VARCHAR(64) UNIQUE,
    body_text TEXT NOT NULL DEFAULT '', -- the exact text issued; see body_text comment on nocs for why this isn't regenerated from the live template later
    society_name VARCHAR(100),
    society_address TEXT,
    registration_number VARCHAR(100),
    secretary_name VARCHAR(100),
    secretary_email VARCHAR(100),
    secretary_sign VARCHAR(100), -- path snapshot at generation time, same convention as secretary_sign elsewhere
    qr_payload VARCHAR(255),
    last_printed_at TIMESTAMP,
    last_emailed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
    -- created_by removed: only created via the admin-only Setup Wizard
    -- completion (_get_or_create_agreement) — never by any other role.
);

-- ── EXPENSES — manual debits, deemed paid on creation ─────────
CREATE TABLE expenses (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id),
    entity_id INT,
    role VARCHAR(10) CHECK (
        role IN (
            'vendor',
            'security',
            'other',
            'assets',
            'deposits'
        )
    ),
    expense_date DATE NOT NULL,
    acc_id INT, -- expense account (Dr) — IS the category
    FOREIGN KEY (society_id, acc_id) REFERENCES accounts (society_id, id),
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
    -- created_by removed: it was a pure duplicate of user_id (see
    -- fn_save_expense — both were always set to p_created_by).
    tds_section VARCHAR(10),
    rcm_applicable BOOLEAN DEFAULT FALSE,
    rcm_category VARCHAR(50),
    receipt_number VARCHAR(64),
    reconciled_at TIMESTAMP,
    reconciled_by INT REFERENCES users(id),
    bank_statement_line_id INT REFERENCES bank_statement_lines (id),
    qr_version INT NOT NULL DEFAULT (1000 + FLOOR(RANDOM() * 9000))::INT
);

-- ── FUND UTILIZATIONS — admin-only withdrawals from Capital/Reserve/Sinking/Repair/Corpus funds ─────────
CREATE TABLE fund_utilizations (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id), -- admin who initiated
    fund_acc_id INT NOT NULL, -- fund ledger account (3000, 3200, 3210, 3220, 3230)
    FOREIGN KEY (society_id, fund_acc_id) REFERENCES accounts (society_id, id),
    expense_acc_id INT NOT NULL, -- expense/payment account to debit (bank, creditor, etc.)
    FOREIGN KEY (society_id, expense_acc_id) REFERENCES accounts (society_id, id),
    particulars TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    mode VARCHAR(20) DEFAULT 'bank' CHECK (
        mode IN (
            'cash',
            'cheque',
            'upi',
            'card',
            'bank',
            'transfer'
        )
    ),
    cheque_no VARCHAR(50),
    transaction_id VARCHAR(255),
    approval_ref VARCHAR(255), -- General Body / Managing Committee resolution reference
    approval_date DATE, -- date of the resolution
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (
        status IN (
            'pending', -- awaiting admin confirmation
            'confirmed', -- posted to ledger
            'cancelled' -- voided before posting
        )
    ),
    confirmed_by INT REFERENCES users (id),
    confirmed_at TIMESTAMP,
    previous_hash VARCHAR(64), -- for audit trail linking
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════════
-- FUND ↔ BANK ACCOUNT MAPPING (2026-09, fund management audit follow-up)
--
-- WHY THIS TABLE EXISTS: every non-cash receipt/receivable payment was
-- hard-wired by fn_resolve_bank_leg to societies.primary_bank_account_id —
-- a single society-wide bank account — regardless of which fund the money
-- was actually for. A society that keeps its Corpus Fund (or Sinking Fund)
-- in a physically separate bank account/FD (common practice, and often
-- expected under RERA/bye-laws) had no way to route those specific
-- contributions there automatically; every contribution landed in whichever
-- one account was "primary", however many real bank accounts existed in the
-- chart. Fund Management's own Utilize Fund form already lets an admin pick
-- ANY bank account for the OUTFLOW leg (see get_expense_bank_accounts) — this
-- table gives the INFLOW leg the same ability, per fund.
--
-- One row per (society, fund) — a fund with no row here simply falls back to
-- primary_bank_account_id (see fn_resolve_bank_leg below), so mapping is
-- opt-in and every existing society keeps working unchanged until an admin
-- sets one.
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE fund_bank_account_map (
    society_id  INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    fund_acc_id INT NOT NULL,
    bank_acc_id INT NOT NULL,
    updated_by  INT REFERENCES users (id),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (society_id, fund_acc_id),
    FOREIGN KEY (society_id, fund_acc_id) REFERENCES accounts (society_id, id) ON DELETE CASCADE,
    FOREIGN KEY (society_id, bank_acc_id) REFERENCES accounts (society_id, id) ON DELETE CASCADE
);

-- ═══════════════════════════════════════════════════════════════════════════
-- FUND APPROPRIATIONS (2026-09) — ad-hoc Dr Income / Cr Fund journal, e.g.
-- "Corpus Fund interest -> Repair & Maintenance Fund Reserve". A locked
-- fund's interest is credited to an Income account rather than the fund
-- itself (see fn_process_fund_utilization's lock-breach message), so moving
-- that interest INTO another fund is an income-to-equity appropriation, not
-- a fund utilization — fn_process_fund_utilization rejects it outright
-- because it requires a Dr-natured (expense/asset) account on the debit
-- side, and an income account is Cr-natured. This table/function pair mirrors
-- fund_utilizations/fn_process_fund_utilization's shape (including the
-- pending-unless-admin status and previous_hash carry-forward, the same
-- non-cryptographic chaining fund_utilizations already uses) but for the
-- from_income_acc_id -> to_fund_acc_id direction instead of
-- fund_acc_id -> expense_acc_id.
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE fund_appropriations (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id INT REFERENCES users (id), -- admin who initiated
    from_income_acc_id INT NOT NULL, -- Cr-natured income account (e.g. Interest Income)
    FOREIGN KEY (society_id, from_income_acc_id) REFERENCES accounts (society_id, id),
    to_fund_acc_id INT NOT NULL, -- Cr-natured fund/equity account being topped up
    FOREIGN KEY (society_id, to_fund_acc_id) REFERENCES accounts (society_id, id),
    particulars TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    approval_ref VARCHAR(255), -- General Body / Managing Committee resolution reference
    approval_date DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'confirmed', 'cancelled')
    ),
    confirmed_by INT REFERENCES users (id),
    confirmed_at TIMESTAMP,
    previous_hash VARCHAR(64),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- The card's appropriation log (and the pending-confirm scan behind it)
-- reads this table newest-first per society; without this it is a seq scan
-- over every appropriation ever made, on every Fund Management render.
CREATE INDEX idx_fund_appropr_society_created
    ON fund_appropriations (society_id, created_at DESC, id DESC);

-- Partial on the rows that actually have work outstanding — pending rows
-- are a small slice of the table but are the only ones ever looked up by
-- status.
CREATE INDEX idx_fund_appropr_pending
    ON fund_appropriations (society_id, created_at DESC)
    WHERE status = 'pending';

-- ═══════════════════════════════════════════════════════════════════════════
-- FY CLOSURES — one row per society per financial year, recording that the
-- year has been closed and how much of the net surplus was appropriated to
-- the statutory Reserve Fund.
--
-- WHY THIS TABLE HAD TO BE CREATED: fn_fy_closing_report is a *read-time*
-- computation (see its header at ~line 7900 — "Nothing is posted to
-- transactions, nothing is written to brought_forward"), so before this
-- table there was no persistent notion of "this FY is closed" anywhere in
-- the schema. The reserve appropriation (a share of net surplus to the
-- Reserve Fund; the percentage is society policy, see reserve_appropriation_pct) was
-- therefore not just un-implemented but un-representable — and, crucially,
-- there was no way to make it idempotent. A close that could run twice
-- would silently double-appropriation the reserve.
--
-- The UNIQUE (society_id, financial_year) is the idempotency guard:
-- fn_fy_close_reserve_appropriation relies on it to refuse a second close
-- rather than relying only on a read-then-write check, which would be racy
-- under two admins clicking at once.
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE fy_closures (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    financial_year SMALLINT NOT NULL, -- START year of FY, e.g. 2026 = FY 1-Apr-2026..31-Mar-2027
    -- Net surplus computed at close time, Cr-positive (same convention as
    -- fn_fy_closing_report's own_closing). Negative = deficit.
    surplus NUMERIC(15,2) NOT NULL DEFAULT 0,
    -- The percentage of surplus that was appropriated, e.g. 25.00. Stored
    -- per-closure rather than read from a settings table so that a later
    -- change to the society's policy cannot retroactively rewrite what a
    -- past year's close actually did.
    reserve_pct NUMERIC(5,2) NOT NULL DEFAULT 0
        CHECK (reserve_pct >= 0 AND reserve_pct <= 100),
    -- Amount actually credited to the reserve account. May be less than
    -- surplus * reserve_pct/100 only via ROUND; it is 0 for a deficit close.
    reserve_transferred NUMERIC(15,2) NOT NULL DEFAULT 0
        CHECK (reserve_transferred >= 0),
    -- Which ledger account received the appropriation. Resolved
    -- jurisdiction-aware (see fn_resolve_reserve_account), never hardcoded.
    reserve_acc_id INT,
    reserve_acc_name TEXT,
    -- The contra account debited (the P&L "Income Expenditure A/c").
    contra_acc_id INT,
    -- journal_id ties to the two transactions rows this close wrote.
    journal_id INT,
    status VARCHAR(20) NOT NULL DEFAULT 'closed' CHECK (
        status IN (
            'closed',         -- year closed, appropriation posted
            'no_surplus',     -- year closed, nothing appropriated (deficit or zero surplus)
            'reversed'        -- administrator reversed the appropriation
        )
    ),
    reversed_journal_id INT,       -- reversing journal, if status='reversed'
    reversal_reason TEXT,
    closed_by INT REFERENCES users (id),
    closed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    reversed_by INT REFERENCES users (id),
    reversed_at TIMESTAMP,
    CONSTRAINT uq_fy_closure UNIQUE (society_id, financial_year),
    CONSTRAINT fk_fy_closure_reserve_acc
        FOREIGN KEY (society_id, reserve_acc_id)
        REFERENCES accounts (society_id, id) ON DELETE SET NULL,
    CONSTRAINT fk_fy_closure_contra_acc
        FOREIGN KEY (society_id, contra_acc_id)
        REFERENCES accounts (society_id, id) ON DELETE SET NULL
);

CREATE INDEX idx_fy_closures_society ON fy_closures (society_id, financial_year DESC);

CREATE TABLE rcm_liability (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    expense_id INT REFERENCES expenses (id) ON DELETE SET NULL,
    vendor_id INT REFERENCES vendors (id) ON DELETE SET NULL,
    rcm_category VARCHAR(50) NOT NULL,
    taxable_value NUMERIC(12, 2) NOT NULL,
    cgst_amount NUMERIC(12, 2) NOT NULL,
    sgst_amount NUMERIC(12, 2) NOT NULL,
    -- igst_amount (2026-09, Phase 3): set instead of cgst/sgst when the
    -- vendor's state differs from the society's state (inter-state RCM
    -- supply) — previously unmodeled, every RCM entry was assumed
    -- intra-state.
    igst_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    -- itc_eligible (2026-09, Phase 3): whether this liability's GST was
    -- booked to the Input Tax Credit (RCM) asset account (recoverable)
    -- vs. expensed outright (non-recoverable, e.g. society below the
    -- GST registration threshold). Sec. 17(5) blocked-credit categories
    -- are out of scope — this only reflects the registration gate.
    itc_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    liability_date DATE NOT NULL,
    gstr_filed BOOLEAN DEFAULT FALSE,
    gstr_filed_date DATE,
    -- paid_at/paid_transaction_id (2026-09, Phase 3): set by
    -- fn_pay_rcm_liability when the actual cash/bank remittance to the
    -- government is posted — distinct from gstr_filed, which previously
    -- had no linked real-money leg at all.
    paid_at TIMESTAMP,
    paid_transaction_id INT, -- references transactions(id), not a formal FK: the
    -- transactions table is created later in this schema file
    created_at TIMESTAMP DEFAULT NOW(),
    created_by INT REFERENCES users (id)
);

-- rcm_liability (2026-09, Phase 3): composite index for the fixed
-- "current month RCM liability" lookup (society_id + liability_date range)
-- used by the GSTR/RCM export and the RCM Liability Register card. Without
-- it every such query scans the whole table; with it the range predicate
-- is an index-only scan once the society is pinned.
CREATE INDEX idx_rcm_liability_society_date ON rcm_liability (society_id, liability_date);

-- rcm_rates (2026-09, Phase 2): per-category RCM rate configuration,
-- replacing the inline CASE WHEN v_rcm_cat ... 5.00/18.00 previously
-- hardcoded in fn_compute_rcm_liability — the exact anti-pattern this
-- codebase already moved out of fn_auto_generate_receivables (see
-- gst_rates). society_id NULL rows are statutory defaults (Notification
-- No. 13/2017-Central Tax (Rate)) used until a society configures its
-- own override; society_id-scoped rows take priority when present.
CREATE TABLE rcm_rates (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    rcm_category VARCHAR(50) NOT NULL,
    rate_pct NUMERIC(5, 2) NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_rcm_rates_lookup ON rcm_rates (rcm_category, effective_from);

-- Statutory default rates (society_id NULL = global fallback), seeded
-- once at schema load. A society can override any of these by inserting
-- its own society_id-scoped row with a later effective_from.
INSERT INTO
    rcm_rates (
        society_id,
        rcm_category,
        rate_pct,
        effective_from
    )
SELECT NULL, cat, rate, DATE '2017-07-01'
FROM (
        VALUES ('gta', 5.00), ('advocate', 18.00), ('arbitration', 18.00), ('sponsorship', 18.00), ('government', 18.00), ('director', 18.00), ('insurance', 18.00), ('recovery', 18.00), ('other', 18.00)
    ) AS defaults (cat, rate)
WHERE
    NOT EXISTS (
        SELECT 1
        FROM rcm_rates
        WHERE
            society_id IS NULL
            AND rcm_category = defaults.cat
    );

COMMENT ON
TABLE bank_statement_lines IS 'One row per line of an uploaded bank statement (CSV/XLSX). matched_id/matched_entity are set once reconciled against a receipts or expenses row; unmatched rows remain visible as reconciliation candidates. bank_acc_id names the account the statement was drawn from; NULL means the society primary account (the pre-2026-09 behaviour).';

CREATE INDEX idx_bank_lines_society_unmatched ON bank_statement_lines (society_id, matched_id)
WHERE
    matched_id IS NULL;

CREATE INDEX idx_bank_lines_batch ON bank_statement_lines (batch_id);

-- Per-account statement lookup (2026-09). Partial on matched_id IS NULL
-- because that is the only state the reconciliation screens ever filter by,
-- and it keeps the index small on a table that keeps every historical line.
CREATE INDEX idx_bank_lines_account ON bank_statement_lines (society_id, bank_acc_id, txn_date)
WHERE
    matched_id IS NULL;

-- Reconciliation state lives on the transaction side (receipts/expenses),
-- mirroring how status/confirmed_by/confirmed_at already work there.
-- bank_statement_line_id is nullable: a manual reconcile (no matching
-- bank line found/uploaded yet) stamps reconciled_at/reconciled_by with
-- no line reference.

CREATE INDEX idx_receipts_reconciled ON receipts (society_id, reconciled_at);

CREATE INDEX idx_expenses_reconciled ON expenses (society_id, reconciled_at);

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
CREATE TABLE payables (
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
    acc_id INT, -- expense account (Dr) — IS the category
    FOREIGN KEY (society_id, acc_id) REFERENCES accounts (society_id, id),
    description TEXT NOT NULL DEFAULT 'Payment', -- becomes acc_particulars in transactions
    roster_id INT REFERENCES security_roster (id),
    shift_date DATE,
    shift_fraction NUMERIC(3, 2) DEFAULT 1.0,
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
    -- created_by removed: payables are always auto-generated by the
    -- payroll calc function, never stamped by any INSERT path.
    CONSTRAINT uq_payment_roster UNIQUE (roster_id)
);

-- ── TRANSACTIONS — single ledger source of truth ───────────────
-- source_table / source_id trace every row back to its origin
-- (receipts / expenses / receivables / payables).
-- journal_id links the paired Dr + Cr lines of one financial event
-- for double-entry bookkeeping.
CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    entry_side VARCHAR(2),
    trx_date DATE NOT NULL,
    acc_id INT,
    FOREIGN KEY (society_id, acc_id) REFERENCES accounts (society_id, id),
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
            'assets',
            'deposits'
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
            'journal',
            'neft',
            'rtgs',
            'imp'
        )
    ),
    payment_gateway_id VARCHAR(50),
    status VARCHAR(20) NOT NULL DEFAULT 'paid',
    source_table VARCHAR(50),
    source_id INT,
    created_by INTEGER REFERENCES users (id),
    journal_id INT,
    transaction_number VARCHAR(64) UNIQUE,
    bank_reconciled BOOLEAN NOT NULL DEFAULT TRUE,
    bank_line_id INT REFERENCES bank_statement_lines (id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ── Vendor passes ─────────────────────────────────────────────
CREATE TABLE vendor_passes (
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
    receipt_id INT REFERENCES receipts (id),
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
-- event's account_id, e.g. "Holi" = 23191 under "Event
-- Ticket" = 2319), same pattern as vendor_passes -> receipts.
CREATE TABLE event_tickets (
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
CREATE TABLE apt_charges_fines_basis (
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
    -- created_by/updated_by removed: apt charge/fine basis is an
    -- admin-only settings table (no self-service, no PROFILE_ACTIONS).
    apt_sinking_fund_rate NUMERIC(10, 2) DEFAULT 0,
    apt_repair_fund_rate NUMERIC(10, 2) DEFAULT 0,
    charges_interest BOOLEAN DEFAULT TRUE,
    -- Billing basis:
    --   'per_sqft'           : apt_maintenance_rate x apartment_size (default).
    --                          apt_maintenance_amount stays a hard override.
    --   'undivided_interest' : common_expense_budget_monthly x
    --                          apartments.undivided_interest_pct / 100.
    -- Sinking / repair fund levies stay per-sq-ft in both modes.
    billing_basis VARCHAR(20) NOT NULL DEFAULT 'per_sqft'
        CHECK (billing_basis IN ('per_sqft', 'undivided_interest')),
    common_expense_budget_monthly NUMERIC(12, 2)
        CHECK (common_expense_budget_monthly IS NULL OR common_expense_budget_monthly >= 0)
);

-- ── Vendor charges ─────────────────────────────────────────────
CREATE TABLE ven_charges_fines_basis (
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
    updated_at TIMESTAMP
    -- created_by/updated_by removed: ven charge/fine basis is an
    -- admin-only settings table (no self-service, no PROFILE_ACTIONS).
);

-- ── Gate access & other tables ─────────────────────────────────
CREATE TABLE gate_access (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    entity_id INTEGER NOT NULL,
    role VARCHAR(10),
    time_in TIMESTAMP NOT NULL DEFAULT NOW(),
    time_out TIMESTAMP,
    created_by INT REFERENCES users (id),
    updated_by INT
);

CREATE TABLE brought_forward (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    financial_year SMALLINT NOT NULL, -- START year of FY, e.g. 2025 = FY 1-Apr-2025..31-Mar-2026
    acc_id INT NOT NULL,
    FOREIGN KEY (society_id, acc_id) REFERENCES accounts (society_id, id) ON DELETE CASCADE,
    drcr_bf VARCHAR(2) NOT NULL CHECK (drcr_bf IN ('Dr', 'Cr')),
    bf_amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00 CHECK (bf_amount >= 0),
    is_auto_calculated BOOLEAN NOT NULL DEFAULT FALSE, -- FALSE once a human hand-edits this row (see drilldown_callbacks.py); no automatic writer exists as of 2026-08 (fn_close_financial_year removed)
    remarks VARCHAR(200),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP,
    -- created_by/updated_by removed: brought_forward is only ever
    -- touched via admin's Settings -> Accounts edit or the admin-only
    -- Setup Wizard — no other role reaches _upsert_brought_forward.
    CONSTRAINT uq_bf_society_fy_acc UNIQUE (
        society_id,
        financial_year,
        acc_id
    )
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- RBAC FOUNDATION (Phase 1 — Option B: hardened coarse roles + targeted permissions)
--
-- D1 (2026-10-04, decided Option B): users.role stays the PORTAL gate. Fine-grained,
-- society-scoped authorization lives in the tables below and is consumed by
-- app/security/policy.py's can_do() engine, applied ONLY on the security-critical
-- surface (financial actions, role grants, period close, concern resolution,
-- poll declaration).
--
-- Declaration order matters here and is top-down: role_definitions and
-- permissions are declared before role_permissions so role_permissions' grant
-- columns can carry their foreign keys inline.
-- ═══════════════════════════════════════════════════════════════════════════════

-- 1. role_definitions — the society-scoped / platform role vocabulary.
--    scope 'platform' => applies system-wide (NULL society in assignments).
--    scope 'society'  => must carry a society_id in user_role_assignments.
CREATE TABLE role_definitions (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(40) NOT NULL,
    scope       VARCHAR(10) NOT NULL CHECK (scope IN ('platform', 'society')),
    name        VARCHAR(100) NOT NULL,
    description TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (code, scope)
);
CREATE INDEX idx_role_definitions_code ON role_definitions (code);
CREATE INDEX idx_role_definitions_scope ON role_definitions (scope);

-- 2. permissions — (resource, action) pairs the policy engine checks.
--    resource is namespaced (e.g. 'concern', 'poll', 'finance', 'enrollment',
--    'role', 'visitor'). action is the verb on that resource.
CREATE TABLE permissions (
    id          SERIAL PRIMARY KEY,
    resource    VARCHAR(60) NOT NULL,
    action      VARCHAR(60) NOT NULL,
    description TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (resource, action)
);
CREATE INDEX idx_permissions_resource ON permissions (resource);

-- 3. role_permissions — GRANT: which role_definition may do which permission.
--    scope_society_id NULL  => the grant applies wherever the role is held
--                             (platform-wide for platform-scoped roles).
--    scope_society_id set  => the grant only applies to that one society.
--    min_amount          => money amount at/above which the action needs approval.
--    approval_threshold  => max amount this role may approve without escalation.
--    One row shape only. The earlier card-catalogue grant columns (society_id,
--    role, card_id, permission) had no readers — policy.can_do joins on
--    role_definition_id + permission_id — so they are gone rather than left
--    nullable; keeping them only meant every grant row carried a NULL past the
--    old NOT NULL constraint. Both grant columns are therefore NOT NULL, and
--    uniqueness is enforced by the two partial indexes below (a plain UNIQUE
--    cannot cover it, because NULLs compare as distinct).
CREATE TABLE role_permissions (
    id SERIAL PRIMARY KEY,
    role_definition_id INT NOT NULL REFERENCES role_definitions (id) ON DELETE CASCADE,
    permission_id INT NOT NULL REFERENCES permissions (id) ON DELETE CASCADE,
    scope_society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    min_amount NUMERIC(12,2),
    approval_threshold NUMERIC(12,2),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_role_permissions_role_def  ON role_permissions (role_definition_id);
CREATE INDEX idx_role_permissions_perm      ON role_permissions (permission_id);
CREATE INDEX idx_role_permissions_scope     ON role_permissions (scope_society_id);
-- A grant must be unique, or a re-run silently stacks duplicates that the
-- policy engine then has to de-duplicate at read time. NULL scope_society_id
-- means "applies wherever the role is held" (platform-wide), and NULLs compare
-- as distinct in a plain unique index, so the two cases need two partial
-- indexes. The grant seeds below name them explicitly in ON CONFLICT.
CREATE UNIQUE INDEX uq_role_permissions_grant_global
    ON role_permissions (role_definition_id, permission_id)
    WHERE scope_society_id IS NULL;
CREATE UNIQUE INDEX uq_role_permissions_grant_scoped
    ON role_permissions (role_definition_id, permission_id, scope_society_id)
    WHERE scope_society_id IS NOT NULL;

-- 4. user_role_assignments — effective-dated membership of a user in a role.
--    The auth-store / users.role gate the PORTAL; these rows drive policy.can_do.
--    NULL society_id is only valid for a platform-scoped role_definition.
CREATE TABLE user_role_assignments (
    id                SERIAL PRIMARY KEY,
    user_id           INT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role_definition_id INT NOT NULL REFERENCES role_definitions (id) ON DELETE CASCADE,
    society_id        INT REFERENCES societies (id) ON DELETE CASCADE,
    entity_link       INT,  -- nullable FK to apartments/vendors/security_staff by context
    effective_from    TIMESTAMP NOT NULL DEFAULT NOW(),
    effective_to      TIMESTAMP,
    granted_by        INT REFERENCES users (id),
    source            VARCHAR(20) NOT NULL CHECK (source IN ('seed', 'grant', 'aoa', 'inherit')),
    status            VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked', 'expired')),
    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_ura_user_role_society_entity UNIQUE
        (user_id, role_definition_id, society_id, entity_link, effective_from)
);
CREATE INDEX idx_ura_user_active
    ON user_role_assignments (user_id, status) WHERE status = 'active';
CREATE INDEX idx_ura_role_society
    ON user_role_assignments (role_definition_id, society_id, status);
CREATE INDEX idx_ura_effective
    ON user_role_assignments (user_id, role_definition_id, society_id) WHERE status = 'active';

-- 5. delegations — maker/checker hand-over: delegator grants a permission to a
--    delegatee for a bounded scope + time window.
CREATE TABLE delegations (
    id              SERIAL PRIMARY KEY,
    delegator_id    INT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    delegatee_id    INT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    permission_id   INT NOT NULL REFERENCES permissions (id) ON DELETE CASCADE,
    society_id      INT REFERENCES societies (id) ON DELETE CASCADE,
    entity_id       INT,  -- scope the delegation to one entity, if applicable
    effective_from  TIMESTAMP NOT NULL DEFAULT NOW(),
    effective_to    TIMESTAMP,
    revoked_at      TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_delegation UNIQUE
        (delegator_id, delegatee_id, permission_id, society_id, effective_from)
);
CREATE INDEX idx_delegations_delegatee
    ON delegations (delegatee_id) WHERE revoked_at IS NULL;
CREATE INDEX idx_delegations_delegator
    ON delegations (delegator_id) WHERE revoked_at IS NULL;

-- 6. societies_memberships — normalised link between a user and the entity they
--    act through (apartment / vendor / security) in a society. This is the
--    long-term home for what users.linked_id currently models; existing callers
--    keep using linked_id until the migration is complete (deferred per D1).
CREATE TABLE societies_memberships (
    id                 SERIAL PRIMARY KEY,
    society_id         INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id            INT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    entity_type        VARCHAR(20) NOT NULL CHECK (entity_type IN ('apartment', 'vendor', 'security')),
    entity_id          INT NOT NULL,
    role_definition_id INT REFERENCES role_definitions (id) ON DELETE SET NULL,
    effective_from     TIMESTAMP NOT NULL DEFAULT NOW(),
    effective_to       TIMESTAMP,
    status             VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'revoked')),
    created_at         TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by         INT REFERENCES users (id),
    CONSTRAINT uq_sm_society_entity UNIQUE (society_id, entity_type, entity_id),
    CONSTRAINT uq_sm_society_user    UNIQUE (society_id, user_id)
);
CREATE INDEX idx_sm_entity   ON societies_memberships (entity_type, entity_id);
CREATE INDEX idx_sm_user     ON societies_memberships (society_id, user_id);
CREATE INDEX idx_sm_active   ON societies_memberships (society_id, user_id, status)
    WHERE status = 'active';

-- Seed reference data for the RBAC vocabulary (mirrors
-- database/migrations/006_rbac_foundation.sql). These rows define the system's
-- role + permission catalogue; the backfill of real users happens in seed.py.

INSERT INTO role_definitions (code, scope, name, description) VALUES
    ('platform_operator',  'platform', 'Platform Operator',  'System-wide operator (migrated master_admin).'),
    ('society_secretary',  'society',  'Society Secretary',  'AOA secretary: assign concerns, declare poll results, approve payments.'),
    ('treasurer',          'society',  'Treasurer',          'AOA treasurer: view receipts, approve payments, close periods.'),
    ('committee_member',   'society',  'Committee Member',   'MC member: declare poll results.'),
    ('accountant',         'society',  'Accountant',         'Society accountant: view receipts, approve payments up to threshold.'),
    ('resident_owner',     'society',  'Resident Owner',     'Apartment owner: view own receipts.'),
    ('resident_tenant',    'society',  'Resident Tenant',    'Apartment tenant: view own receipts.'),
    ('vendor_contact',     'society',  'Vendor Contact',     'Registered vendor: view own concerns/bids.'),
    ('security_staff',     'society',  'Security Staff',     'Society security: manage channel events, view roster.')
ON CONFLICT (code, scope) DO NOTHING;

INSERT INTO permissions (resource, action, description) VALUES
    ('concern',     'assign',              'Assign/invite an entity to a concern'),
    ('concern',     'resolve',             'Mark a concern assignment resolved/closed'),
    ('poll',        'declare_results',     'Declare poll results and close a poll'),
    ('finance',     'receipt.view_own',    'View own financial receipts'),
    ('finance',     'payment.approve',     'Approve a payment against the approval threshold'),
    ('finance',     'period.close',        'Close a financial period / FY'),
    ('enrollment',  'import',              'Bulk-enroll apartment/vendor/security members'),
    ('role',        'grant',               'Grant or revoke a society role on a user'),
    ('visitor',     'approve',             'Approve / deny a visitor / gate alert')
ON CONFLICT (resource, action) DO NOTHING;

-- Default role->permission grants. scope_society_id NULL => grant applies
-- wherever the role is held (society-scoped roles are tied to a society via
-- user_role_assignments.society_id, not here). Accountant payment.approve has a
-- min_amount floor: amounts at/above this require a higher authority.
INSERT INTO role_permissions (role_definition_id, permission_id, scope_society_id, min_amount, approval_threshold)
SELECT rd.id, p.id, NULL, NULL, NULL
FROM role_definitions rd, permissions p
WHERE (rd.code = 'platform_operator' AND p.resource = 'role' AND p.action = 'grant')
   OR (rd.code = 'platform_operator' AND p.resource = 'finance' AND p.action = 'period.close')
   OR (rd.code = 'society_secretary' AND p.resource = 'concern' AND p.action = 'assign')
   OR (rd.code = 'society_secretary' AND p.resource = 'concern' AND p.action = 'resolve')
   OR (rd.code = 'society_secretary' AND p.resource = 'poll' AND p.action = 'declare_results')
   OR (rd.code = 'society_secretary' AND p.resource = 'finance' AND p.action = 'payment.approve')
   OR (rd.code = 'society_secretary' AND p.resource = 'role' AND p.action = 'grant')
   OR (rd.code = 'society_secretary' AND p.resource = 'enrollment' AND p.action = 'import')
ON CONFLICT (role_definition_id, permission_id) WHERE scope_society_id IS NULL DO NOTHING;

INSERT INTO role_permissions (role_definition_id, permission_id, scope_society_id)
SELECT rd.id, p.id, NULL
FROM role_definitions rd, permissions p
WHERE (rd.code = 'treasurer' AND p.resource = 'finance' AND p.action = 'receipt.view_own')
   OR (rd.code = 'treasurer' AND p.resource = 'finance' AND p.action = 'period.close')
   OR (rd.code = 'accountant' AND p.resource = 'finance' AND p.action = 'receipt.view_own')
   OR (rd.code = 'committee_member' AND p.resource = 'poll' AND p.action = 'declare_results')
   OR (rd.code = 'resident_owner' AND p.resource = 'finance' AND p.action = 'receipt.view_own')
   OR (rd.code = 'resident_tenant' AND p.resource = 'finance' AND p.action = 'receipt.view_own')
   OR (rd.code = 'treasurer' AND p.resource = 'finance' AND p.action = 'payment.approve')
ON CONFLICT (role_definition_id, permission_id) WHERE scope_society_id IS NULL DO NOTHING;

-- Accountant payment approval is capped: min_amount = 5000 means a payment at/above
-- this threshold needs escalation beyond the accountant role.
INSERT INTO role_permissions (role_definition_id, permission_id, scope_society_id, min_amount)
SELECT rd.id, p.id, NULL, 5000
FROM role_definitions rd, permissions p
WHERE rd.code = 'accountant' AND p.resource = 'finance' AND p.action = 'payment.approve'
ON CONFLICT (role_definition_id, permission_id) WHERE scope_society_id IS NULL DO UPDATE
    SET min_amount = EXCLUDED.min_amount;

-- ═══════════════════════════════════════════════════════════════════════════════
-- AUDIT, APPROVAL & OUTBOX FOUNDATIONS
--
-- The workflow-specific logs (concern_transitions, poll_transitions,
-- channel_event_transitions, regime_rule_audit) cover individual domains but
-- nothing recorded the actor/society/resource/action/before-after of the other
-- writes the blueprint §6 requires to be attributable: financial edits,
-- enrollments, role grants, exports, master actions. audit_events is that
-- cross-domain log. approval_steps is the maker/checker record the doc §2
-- "prevent self-approval" rule needs. outbox is the transactional hand-off
-- from a committed workflow change to notification/reporting/accounting
-- consumers, so a push-provider failure can no longer lose the event and a
-- retry can no longer duplicate the business transition.
-- ═══════════════════════════════════════════════════════════════════════════════

-- 7. audit_events — cross-domain, attributable, append-only.
--    Restrict writes to a dedicated writer role at deployment time (see the
--    REVOKE note after the trigger): the application connects as one role, so
--    the trigger below is what actually stops an ordinary code path from
--    rewriting history. Back this table up separately from the rest of the
--    database and test retrieval after restore.
CREATE TABLE audit_events (
    id                BIGSERIAL PRIMARY KEY,
    society_id        INT REFERENCES societies (id) ON DELETE SET NULL,
    actor_id          INT REFERENCES users (id) ON DELETE SET NULL,
    actor_role        VARCHAR(20),
    action            VARCHAR(60) NOT NULL,
    resource_type     VARCHAR(60) NOT NULL,
    resource_id       VARCHAR(64),
    -- before/after as JSONB so one log covers every domain's shape; the
    -- sensitive-value concern is handled by restricting read access, not by
    -- splitting the schema per resource.
    before_value      JSONB,
    after_value       JSONB,
    reason            TEXT,
    source            VARCHAR(30) NOT NULL DEFAULT 'app'
                      CHECK (source IN ('app', 'seed', 'sql', 'migration', 'import', 'system')),
    -- Correlation ties one user action to the workflow rows, notification and
    -- accounting entries it produced, across all three logs.
    correlation_id    UUID,
    permission_used   VARCHAR(60),
    policy_version    VARCHAR(20),   -- authorization policy version that decided (RWA3 §3.3 inv. 5)
    document_hash     VARCHAR(128),
    approval_ref      VARCHAR(100),
    ip_address        VARCHAR(45),
    created_at        TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_events_society_time
    ON audit_events (society_id, created_at DESC);
CREATE INDEX idx_audit_events_resource
    ON audit_events (resource_type, resource_id, created_at DESC);
CREATE INDEX idx_audit_events_actor
    ON audit_events (actor_id, created_at DESC);
CREATE INDEX idx_audit_events_correlation
    ON audit_events (correlation_id) WHERE correlation_id IS NOT NULL;
CREATE INDEX idx_audit_events_action
    ON audit_events (action, created_at DESC);

CREATE OR REPLACE FUNCTION trg_audit_events_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only (attempted %)', TG_OP;
END
$$;

CREATE TRIGGER audit_events_immutable BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION trg_audit_events_immutable();

-- 8. approval_steps — maker/checker record behind the thresholds that
--    role_permissions.min_amount / approval_threshold only describe. One
--    request, N steps, each with the authority that satisfied it. The CHECK on
--    requested_by/decided_by is deliberately absent: a maker who is also the
--    approver is exactly the case the application must reject, and a
--    constraint here would block recording the attempt rather than prevent it.
CREATE TABLE approval_steps (
    id                SERIAL PRIMARY KEY,
    society_id        INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    resource_type     VARCHAR(60) NOT NULL,
    resource_id       VARCHAR(64) NOT NULL,
    step_no           INT NOT NULL CHECK (step_no > 0),
    action            VARCHAR(60) NOT NULL,
    -- Maker / Checker / Approver are the roles in the chain, not users: the
    -- same request can need a treasurer then a secretary then the general body.
    required_role     VARCHAR(60),
    threshold_amount  NUMERIC(14, 2),
    requested_by      INT REFERENCES users (id) ON DELETE SET NULL,
    requested_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    decided_by        INT REFERENCES users (id) ON DELETE SET NULL,
    decided_at        TIMESTAMP,
    outcome           VARCHAR(20) CHECK (outcome IN ('pending', 'approved', 'rejected', 'skipped', 'expired')),
    decision_reason   TEXT,
    -- General-body resolution / bye-law clause / board minute this step rests
    -- on, so an approval is traceable to an authority rather than a name.
    resolution_ref    VARCHAR(100),
    delegation_id     INT REFERENCES delegations (id) ON DELETE SET NULL,
    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_approval_step UNIQUE (society_id, resource_type, resource_id, step_no),
    CONSTRAINT approval_step_decided CHECK (
        (outcome IS NULL OR outcome = 'pending')
        OR decided_by IS NOT NULL
    )
);
CREATE INDEX idx_approval_steps_resource
    ON approval_steps (society_id, resource_type, resource_id, step_no);
CREATE INDEX idx_approval_steps_pending
    ON approval_steps (society_id, outcome) WHERE outcome = 'pending';

-- 9. outbox — transactional hand-off. The business change and this row commit
--    together; a separate consumer drains it. Consumers MUST be idempotent on
--    (event_type, aggregate_type, aggregate_id) so a redelivery cannot repeat a
--    business transition, and a notification failure can never roll back — or
--    silently lose — the workflow change that produced it.
CREATE TABLE outbox (
    id                BIGSERIAL PRIMARY KEY,
    society_id        INT REFERENCES societies (id) ON DELETE CASCADE,
    event_type        VARCHAR(80) NOT NULL,
    aggregate_type    VARCHAR(60) NOT NULL,
    aggregate_id      VARCHAR(64) NOT NULL,
    payload           JSONB NOT NULL,
    correlation_id    UUID,
    status            VARCHAR(20) NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'processing', 'delivered', 'failed', 'dead')),
    attempts          INT NOT NULL DEFAULT 0,
    available_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    claimed_by        VARCHAR(80),
    claimed_at        TIMESTAMP,
    delivered_at      TIMESTAMP,
    last_error        TEXT,
    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    -- The idempotency key, on the business identity and nothing else: one
    -- committed business change produces at most one outbox row per
    -- (event_type, aggregate). Keying this on correlation_id instead would not
    -- work — that column is nullable and NULLs compare as DISTINCT in a unique
    -- index, so every retry of an event written without one would insert a fresh
    -- row and the guarantee would silently evaporate.
    CONSTRAINT uq_outbox_event UNIQUE (event_type, aggregate_type, aggregate_id)
);
CREATE INDEX idx_outbox_ready
    ON outbox (available_at, id) WHERE status IN ('pending', 'failed');
CREATE INDEX idx_outbox_society
    ON outbox (society_id, created_at DESC);
CREATE INDEX idx_outbox_correlation
    ON outbox (correlation_id) WHERE correlation_id IS NOT NULL;

CREATE TABLE Dashboard_settings (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    key VARCHAR(100) NOT NULL,
    value TEXT,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (society_id, key)
);

CREATE TABLE society_compliance_settings (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    sinking_fund_rate_basis VARCHAR(20) DEFAULT 'per_sq_ft' CHECK (
        sinking_fund_rate_basis IN (
            'per_sq_ft',
            'construction_cost'
        )
    ),
    repair_fund_rate_basis VARCHAR(20) DEFAULT 'per_sq_ft' CHECK (
        repair_fund_rate_basis IN (
            'per_sq_ft',
            'construction_cost'
        )
    ),
    fund_gst_exempt BOOLEAN DEFAULT TRUE,
    fund_charges_interest BOOLEAN DEFAULT TRUE,
    gst_filing_cadence VARCHAR(20) DEFAULT 'monthly' CHECK (
        gst_filing_cadence IN ('monthly', 'qrmp')
    ),
    gst_registered BOOLEAN DEFAULT FALSE,
    gstin VARCHAR(15),
    tds_no_pan_action VARCHAR(10) DEFAULT 'warn' CHECK (
        tds_no_pan_action IN ('warn', 'block')
    ),
    default_export_format VARCHAR(20) DEFAULT 'structured' CHECK (
        default_export_format IN (
            'structured',
            'gstn_offline',
            'traces_26q'
        )
    ),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_society_compliance_settings UNIQUE (society_id)
);

-- ════════════════════════════════════════════════════════════════════════════
-- GST RATES — Society-specific GST rates with effective dates
-- ════════════════════════════════════════════════════════════════════════════
CREATE TABLE gst_rates (
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
CREATE TABLE kpi_rule_links (
    id SERIAL PRIMARY KEY,
    category VARCHAR(50) NOT NULL CHECK (
        category IN (
            'sinking_fund',
            'repair_fund',
            'fund_gst',
            'fund_interest',
            'gst_registered',
            'tds_no_pan',
            'rera',
            'apartment_act',
            'cooperative_act',
            'income_tax_mutuality',
            'other'
        )
    ),
    state VARCHAR(10) NOT NULL DEFAULT 'ALL' CHECK (
        state IN (
            'ALL',
            'UP',
            'MH',
            'KA',
            'TN',
            'DL',
            'RJ',
            'MP',
            'WB',
            'GJ',
            'TS',
            'AP',
            'BR',
            'HR',
            'PB',
            'KL'
        )
    ),
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
CREATE TABLE state_compliance_thresholds (
    id SERIAL PRIMARY KEY,
    state VARCHAR(10) NOT NULL CHECK (
        state IN (
            'ALL',
            'UP',
            'MH',
            'KA',
            'TN',
            'DL',
            'RJ',
            'MP',
            'WB',
            'GJ',
            'TS',
            'AP',
            'BR',
            'HR',
            'PB',
            'KL'
        )
    ),
    threshold_key VARCHAR(60) NOT NULL CHECK (
        threshold_key IN (
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
        )
    ),
    value NUMERIC(12, 4),
    value_text TEXT,
    unit VARCHAR(20),
    effective_from DATE,
    effective_to DATE,
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_state_threshold UNIQUE (
        state,
        threshold_key,
        effective_from
    )
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- LEGAL REGIME PROFILES — jurisdiction-specific statutory frameworks
-- (e.g., UP_AOA_2010 for Uttar Pradesh Apartment Act 2010, MH_COOP_1965 for
-- Maharashtra Co-operative Societies Act). Each profile defines the legal
-- basis, applicable acts/rules/bye-laws, and effective dates.
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE legal_regime_profiles (
    code VARCHAR(30) PRIMARY KEY,
    state_code VARCHAR(2) NOT NULL,
    -- A scheme is state x constitution: the same state has different statutes for an apartment owners'
    -- association, a registered society and a co-operative housing society. GENERIC = no state rules loaded.
    constitution VARCHAR(20) NOT NULL DEFAULT 'AOA' CHECK (constitution IN ('AOA', 'REG_SOCIETY', 'COOP', 'GENERIC')),
    name VARCHAR(120) NOT NULL,
    primary_law VARCHAR(255) NOT NULL,
    rules_version VARCHAR(100),
    model_bye_laws_version VARCHAR(100),
    effective_from DATE NOT NULL,
    effective_to DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'retired', 'draft')
    ),
    source_reference TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- SOCIETY LEGAL REGIME ASSIGNMENT — each society is assigned one legal regime
-- (e.g., UP_AOA_2010). This determines which statutory head catalog and
-- compliance thresholds apply. Effective dates allow historical changes.
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE society_legal_regime (
    society_id INT PRIMARY KEY REFERENCES societies (id) ON DELETE CASCADE,
    regime_code VARCHAR(30) NOT NULL REFERENCES legal_regime_profiles (code),
    effective_from DATE NOT NULL,
    effective_to DATE,
    source_reference TEXT,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- STATUTORY HEAD CATALOG — statutory head definitions per legal regime.
-- Each head maps to a statement section (Assets, Liabilities, Equity, Income, Expenditure)
-- and defines display order. Parent heads allow hierarchical statutory grouping.
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE statutory_head_catalog (
    regime_code VARCHAR(30) NOT NULL REFERENCES legal_regime_profiles (code) ON DELETE CASCADE,
    head_code VARCHAR(50) NOT NULL,
    parent_head_code VARCHAR(50),
    statement_section VARCHAR(20) NOT NULL CHECK (
        statement_section IN (
            'Assets',
            'Liabilities',
            'Equity',
            'Income',
            'Expenditure'
        )
    ),
    label VARCHAR(200) NOT NULL,
    display_order INT NOT NULL,
    is_statutory_required BOOLEAN NOT NULL DEFAULT FALSE,
    source_reference TEXT,
    effective_from DATE NOT NULL,
    effective_to DATE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (regime_code, head_code)
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- ACCOUNT STATUTORY MAPPINGS — maps each society's chart of accounts to
-- statutory heads. One account can map to one statutory head per regime.
-- This is orthogonal to the parent_account_id hierarchy (which drives arithmetic).
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE account_statutory_mappings (
    society_id INT NOT NULL,
    account_id INT NOT NULL,
    regime_code VARCHAR(30) NOT NULL,
    head_code VARCHAR(50) NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    source_reference TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (
        society_id,
        account_id,
        regime_code,
        effective_from
    ),
    FOREIGN KEY (society_id, account_id) REFERENCES accounts (society_id, id) ON DELETE CASCADE,
    FOREIGN KEY (regime_code, head_code) REFERENCES statutory_head_catalog (regime_code, head_code) ON DELETE RESTRICT
);

CREATE INDEX idx_account_statutory_mappings_society ON account_statutory_mappings (society_id);

CREATE INDEX idx_account_statutory_mappings_regime ON account_statutory_mappings (regime_code);

CREATE INDEX idx_statutory_head_catalog_regime ON statutory_head_catalog (regime_code);

-- ═══════════════════════════════════════════════════════════════════════════════
-- LEGAL INSTRUMENT CATALOG — one row per Act / Rules / Bye-law / Notification
-- governing a legal_regime_profiles regime (e.g. every statute behind
-- UP_AOA_2010, not just the 3 summary strings legal_regime_profiles carries).
-- Populated by periodic web research (see the Master Portal → "RWA
-- Compliance (UP)" tab) and pushed live via Master Settings → Integrate to DB.
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE legal_instrument_catalog (
    id SERIAL PRIMARY KEY,
    regime_code VARCHAR(30) NOT NULL REFERENCES legal_regime_profiles (code) ON DELETE CASCADE,
    instrument_type VARCHAR(30) NOT NULL CHECK (
        instrument_type IN (
            'Act', 'Rules', 'Bye-laws', 'Notification',
            'Central Act', 'Central Rules'
        )
    ),
    title VARCHAR(300) NOT NULL,
    enactment_year INT,
    issuing_authority VARCHAR(150),
    applicability TEXT,
    key_provisions TEXT NOT NULL,
    source_reference TEXT NOT NULL,
    display_order INT NOT NULL DEFAULT 100,
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'superseded', 'draft')
    ),
    last_verified_on DATE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_legal_instrument UNIQUE (regime_code, title, enactment_year)
);

CREATE INDEX idx_legal_instrument_catalog_regime ON legal_instrument_catalog (regime_code);

CREATE TABLE notifications (
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

CREATE TABLE event_ticket_items (
    id SERIAL PRIMARY KEY,
    event_ticket_id INT NOT NULL REFERENCES event_tickets (id) ON DELETE CASCADE,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    ticket_type VARCHAR(20) NOT NULL CHECK (
        ticket_type IN ('ADULT', 'CHILD')
    ),
    qr_payload VARCHAR(255) UNIQUE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'pending', 'used', 'cancelled')
    ),
    scanned_at TIMESTAMP,
    scanned_by INT REFERENCES users (id),
    last_printed_at TIMESTAMP,
    last_emailed_at TIMESTAMP,
    qr_version INT NOT NULL DEFAULT (1000 + FLOOR(RANDOM() * 9000))::INT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE visitors (
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

CREATE TABLE alert_channels (
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

CREATE TABLE alert_subscriptions (
    id SERIAL PRIMARY KEY,
    channel_id INT NOT NULL REFERENCES alert_channels (id) ON DELETE CASCADE,
    apartment_id INT NOT NULL REFERENCES apartments (id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (channel_id, apartment_id)
);

CREATE TABLE alert_events (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    channel_id INT REFERENCES alert_channels (id) ON DELETE CASCADE,
    visitor_id INT REFERENCES visitors (id) ON DELETE CASCADE,
    -- Must stay in step with app/services/workflow.py STATE_MACHINES['alert_events']:
    -- pending -> arrived | calling | denied | expired, calling -> resolved |
    -- denied | expired. 'expired' was missing here while the engine allowed it,
    -- so the one legal way to retire an unanswered alert raised a constraint
    -- violation instead of recording the expiry.
    state VARCHAR(30) NOT NULL CHECK (
        state IN (
            'idle',
            'pending',
            'arrived',
            'calling',
            'resolved',
            'denied',
            'expired'
        )
    ),
    triggered_by INT REFERENCES users (id),
    triggered_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP
);

-- channel_event_transitions — D2 append-only audit for alert_channels events.
-- alert_events.state is a read-only materialized cache; this table is the source
-- of truth (pending -> arrived/calling -> resolved/denied/expired).
CREATE TABLE channel_event_transitions (
    id              SERIAL PRIMARY KEY,
    event_id        INT NOT NULL REFERENCES alert_events (id) ON DELETE CASCADE,
    society_id      INT REFERENCES societies (id) ON DELETE CASCADE,
    from_state      VARCHAR(30),
    to_state        VARCHAR(30) NOT NULL,
    actor_id        INT REFERENCES users (id),
    permission_used VARCHAR(60),
    comment         TEXT,
    evidence        JSONB,
    correlation_id  UUID,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_cet_event
    ON channel_event_transitions (event_id, created_at);
CREATE INDEX idx_cet_society
    ON channel_event_transitions (society_id, created_at);

CREATE TABLE patrol_locations (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    location_name VARCHAR(100) NOT NULL,
    description TEXT,
    qr_payload VARCHAR(255) UNIQUE NOT NULL,
    -- Reissue nonce (2026-09): patrol_location is now a versioned/signable
    -- role like apartments/vendors/security_staff — see
    -- app/services/qr_service.py _QR_VERSIONED_ROLES and revoke_and_reissue.
    -- Random 4-digit range, same convention as those three tables.
    qr_version INT NOT NULL DEFAULT (1000 + FLOOR(RANDOM() * 9000))::INT,
    schedule_start TIME,
    schedule_end TIME,
    scan_interval INT DEFAULT 120,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    nfc_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
    -- created_by removed: patrol_location create/edit is admin-only
    -- per _PORTAL_PERMS (no self-service role).
);

CREATE TABLE patrol_scans (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    location_id INT NOT NULL REFERENCES patrol_locations (id) ON DELETE CASCADE,
    security_user_id INT NOT NULL REFERENCES users (id),
    scanned_at TIMESTAMP DEFAULT NOW(),
    notes TEXT
);

CREATE TABLE polls (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    -- created_by removed: save_poll requires role=="admin" explicitly;
    -- fn_create_poll/fn_edit_poll are admin-only reachable.
    title VARCHAR(200) NOT NULL,
    description TEXT,
    open_to VARCHAR(20) NOT NULL DEFAULT 'no_dues' CHECK (open_to IN ('no_dues', 'all_members')),
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
    -- Phase 4: Poll quorum and majority requirements
    quorum_pct NUMERIC(5,2) NOT NULL DEFAULT 33.33 CHECK (quorum_pct > 0 AND quorum_pct <= 100),
    majority_pct NUMERIC(5,2) NOT NULL DEFAULT 50.00 CHECK (majority_pct > 0 AND majority_pct <= 100),
    -- Bye-law 8 / Act s.12(1)(f): in the Model Bye-Laws a vote carries the owner's undivided-interest
    -- percentage, not one vote per flat. 'apartment' (default) is the advisory one-flat-one-vote poll;
    -- 'undivided_interest' tallies each flat's percentage and takes quorum / majority from the society's
    -- rules (poll_quorum_pct, poll_majority_pct). Either way an online poll is NOT a General Body
    -- resolution (bye-law 10: votes are cast in person) - see fn_declare_results.
    vote_basis VARCHAR(20) NOT NULL DEFAULT 'apartment' CHECK (vote_basis IN ('apartment', 'undivided_interest')),
    results_announced_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP,
    ends_at TIMESTAMP,
    reminder_sent_at TIMESTAMP,
    -- app/services/qr_service.py _QR_VERSIONED_ROLES and revoke_and_reissue.
    qr_version INT NOT NULL DEFAULT (1000 + FLOOR(RANDOM() * 9000))::INT
);

-- SECRET BALLOT. "Who voted" and "what was chosen" are kept in two tables
-- that cannot be joined:
--   poll_participation  one row per (poll, apartment): enforces the
--                       one-vote-per-apartment rule and drives turnout /
--                       quorum / has_voted. It carries NO choice, NO user_id
--                       and only a DATE (no time-of-day), so it cannot be
--                       lined up against the ballot rows.
--   poll_ballots        the choices only: NO user, NO apartment, NO id and NO
--                       timestamp. Admins get counts through the fn_* poll
--                       functions only; no function returns individual rows.
-- Both rows are written inside fn_cast_vote's single transaction.
CREATE TABLE poll_participation (
    poll_id INT NOT NULL REFERENCES polls (id) ON DELETE CASCADE,
    apartment_id INT NOT NULL REFERENCES apartments (id) ON DELETE CASCADE,
    cast_on DATE NOT NULL DEFAULT CURRENT_DATE,
    PRIMARY KEY (poll_id, apartment_id)
);

CREATE TABLE poll_ballots (
    poll_id INT NOT NULL REFERENCES polls (id) ON DELETE CASCADE,
    choice SMALLINT NOT NULL CHECK (choice BETWEEN 1 AND 5)
);

-- Weighted polls (vote_basis = 'undivided_interest') keep the secret ballot: the weight is added to a
-- per-choice running total, never stored beside an individual ballot, so a flat's percentage cannot be
-- matched to its choice. Only fn_cast_vote writes here; only fn_declare_results reads it.
CREATE TABLE poll_weight_tally (
    poll_id    INT NOT NULL REFERENCES polls (id) ON DELETE CASCADE,
    choice     SMALLINT NOT NULL CHECK (choice BETWEEN 1 AND 5),
    weight_sum NUMERIC(10, 4) NOT NULL DEFAULT 0 CHECK (weight_sum >= 0),
    PRIMARY KEY (poll_id, choice)
);

-- ════════════════════════════════════════════════════════════════════════
-- Poll audit (D2): append-only transition log + eligibility snapshot
--
-- poll_transitions is the source of truth for the poll lifecycle
-- (created -> opened -> closed -> results_declared). polls.status is a
-- read-only materialized cache refreshed by the workflow service.
-- poll_eligibility_snapshot freezes the eligible voter set at poll creation so
-- a later change to an apartment's dues standing can't retroactively widen or
-- narrow who could vote on an already-cast ballot.
-- ════════════════════════════════════════════════════════════════════════
CREATE TABLE poll_transitions (
    id              SERIAL PRIMARY KEY,
    poll_id         INT NOT NULL REFERENCES polls (id) ON DELETE CASCADE,
    society_id      INT REFERENCES societies (id) ON DELETE CASCADE,
    from_state      VARCHAR(20),
    to_state        VARCHAR(20) NOT NULL CHECK (
        to_state IN ('created', 'opened', 'closed', 'results_declared')
    ),
    actor_id        INT REFERENCES users (id),
    permission_used VARCHAR(60),
    comment         TEXT,
    evidence        JSONB,
    correlation_id  UUID,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_poll_transitions_poll
    ON poll_transitions (poll_id, created_at);
CREATE INDEX idx_poll_transitions_society
    ON poll_transitions (society_id, created_at);

CREATE TABLE poll_eligibility_snapshot (
    id          SERIAL PRIMARY KEY,
    poll_id     INT NOT NULL REFERENCES polls (id) ON DELETE CASCADE,
    apartment_id INT NOT NULL REFERENCES apartments (id),
    eligible    BOOLEAN NOT NULL DEFAULT FALSE,
    reason      TEXT,
    captured_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (poll_id, apartment_id)
);
CREATE INDEX idx_poll_elig_poll
    ON poll_eligibility_snapshot (poll_id, apartment_id);

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
CREATE TABLE tds_section_rates (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    section VARCHAR(10) NOT NULL,
    nature_of_income VARCHAR(255),
    discriminator VARCHAR(50),
    rate NUMERIC(5, 2) NOT NULL,
    rate_no_pan NUMERIC(5, 2),
    single_bill_threshold NUMERIC(12, 2) NOT NULL DEFAULT 30000,
    annual_aggregate_threshold NUMERIC(12, 2) NOT NULL DEFAULT 0,
    effective_from DATE NOT NULL DEFAULT '2024-04-01',
    effective_to DATE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tds_section_rate UNIQUE (
        society_id,
        section,
        discriminator,
        effective_from
    )
);

-- Circular-reference FKs (societies <-> users)

-- societies.primary_bank_account_id (2026-08)
-- ==============================================
-- Single default bank account used for every non-cash transaction leg
-- (cheque/upi/card/bank/crypto alike) society-wide. See
-- fn_resolve_bank_leg below for how writer functions consume this.
--
-- The FK cannot be declared inline on the societies CREATE TABLE: `accounts`
-- forward-references `societies` (every account belongs to a society), so
-- `accounts` is declared after it and this one composite FK has to wait
-- until both exist. It is the only such forward reference left in this file.
--
-- The FK alone can't express "must be a child of THIS society's own Bank
-- Accounts header" — a trigger (defense-in-depth alongside the FK)
-- enforces both (a) the referenced account belongs to this same society,
-- and (b) its parent_account_id is that society's 'BkAc' (Bank Accounts)
-- header account. Per-mode bank routing (UPI -> ICICI, Cheque -> SBI,
-- etc.) may replace this single column later; for now every non-cash
-- mode routes through it uniformly.
-- Forward reference: accounts is declared later in this file, so this FK
-- cannot be inline on societies.
ALTER TABLE societies
    ADD CONSTRAINT fk_primary_bank_account
    FOREIGN KEY (id, primary_bank_account_id)
    REFERENCES accounts (society_id, id);

-- societies.signing_secret_enc / secretary_email: signing_secret_enc holds
-- Fernet ciphertext (reversible, so it can actually be used as an HMAC key; see
-- app/services/secret_vault.py and qr_service.py). secretary_email backs the
-- post-onboarding society Agreement (see society_agreements below), which needs
-- an email field to print/send to.

-- concerns/receipts/expenses/assets/nocs qr_version (2026-09 security fix):
-- these five document-verification QR roles (CON/RPT/EXP/AST/NOC) were left
-- out of the 2026-08 signing rollout that covered apartment/vendor/security/
-- patrol_location/admin. All five use small sequential ids with no proof of
-- having been legitimately issued, and — unlike the static gate passes —
-- several expose sensitive data straight off an unauthenticated guess: a
-- NOC leaks an owner's name and flat number, receipts/expenses leak amounts.
-- Registering these tables in qr_service.py's _QR_VERSIONED_ROLES (which
-- automatically adds them to _QR_SIGNABLE_ROLES) makes generate_qr_code and
-- validate_qr_code start signing/verifying them exactly like the other five
-- roles, with no other code changes needed since every call site already
-- goes through those two generic functions. Same DEFAULT expression as the
-- existing qr_version columns; same reissue mechanism (revoke_and_reissue)
-- for entities that need their QR invalidated (e.g. a NOC gets reissued if
-- a new one is printed for the same apartment).

-- SECTION 2B: NUMBERING SEQUENCES & TRIGGERS
-- Auto-generate human-friendly receipt_number / transaction_number.
-- ════════════════════════════════════════════════════════════════
CREATE SEQUENCE seq_receipt_number;

CREATE SEQUENCE seq_transaction_number;

-- SECTION 2: INDEXES
-- ════════════════════════════════════════════════════════════════

CREATE INDEX idx_push_subscriptions_user ON push_subscriptions (user_id);

CREATE INDEX idx_push_subscriptions_endpoint ON push_subscriptions (endpoint);

CREATE INDEX idx_society_compliance_settings_society ON society_compliance_settings (society_id);

CREATE INDEX idx_kpi_rule_links_category ON kpi_rule_links (category);

CREATE INDEX idx_kpi_rule_links_state ON kpi_rule_links (state);

CREATE INDEX idx_kpi_rule_links_active ON kpi_rule_links (is_active);

CREATE INDEX idx_state_compliance_state ON state_compliance_thresholds (state);

CREATE INDEX idx_state_compliance_key ON state_compliance_thresholds (threshold_key);

CREATE INDEX idx_state_compliance_active ON state_compliance_thresholds (is_active);

-- SECTION 2: INDEXES
-- ════════════════════════════════════════════════════════════════

-- SECTION 2: INDEXES
-- ════════════════════════════════════════════════════════════════
CREATE UNIQUE INDEX idx_assets_qr ON assets (qr_payload);

CREATE UNIQUE INDEX uq_receivable_entity_month ON receivables (entity_id, role, period_month);

CREATE INDEX idx_transactions_journal ON transactions (journal_id);

CREATE UNIQUE INDEX idx_expenses_qr ON expenses (qr_payload);

CREATE UNIQUE INDEX idx_receipts_qr ON receipts (qr_payload);

CREATE INDEX idx_bf_society_fy ON brought_forward (society_id, financial_year);

CREATE INDEX idx_visitors_society_date ON visitors (society_id, visit_date);

CREATE INDEX idx_event_ticket_items_qr ON event_ticket_items (qr_payload);

CREATE INDEX idx_event_tickets_event ON event_tickets (event_id);

CREATE INDEX idx_event_tickets_user ON event_tickets (user_id);

CREATE INDEX idx_concerns_assigns_concern ON concerns_assigns (concern_id);

CREATE INDEX idx_concerns_assigns_society ON concerns_assigns (society_id);

CREATE INDEX idx_concerns_assigns_lookup ON concerns_assigns (society_id, role, entity_id);

CREATE INDEX idx_concerns_assigns_status ON concerns_assigns (concern_id, status);

CREATE UNIQUE INDEX idx_concerns_qr ON concerns (qr_payload);

CREATE INDEX idx_apt_charges_society ON apt_charges_fines_basis (society_id, apt_id);

CREATE INDEX idx_notifications_user ON notifications (
    user_id,
    read,
    created_at DESC
);

CREATE INDEX idx_gate_entity_role_time ON gate_access (entity_id, role, time_in);

CREATE INDEX idx_users_email ON users (email);

CREATE INDEX idx_users_society_role ON users (society_id, role);

CREATE INDEX idx_apartments_society ON apartments (society_id);

CREATE INDEX idx_apartments_active ON apartments (society_id, active);

CREATE INDEX idx_vendors_society ON vendors (society_id);

CREATE INDEX idx_security_society ON security_staff (society_id);

CREATE INDEX idx_accounts_society ON accounts (society_id);

CREATE INDEX idx_accounts_drcr ON accounts (society_id, drcr_account);

CREATE INDEX idx_transactions_society_date ON transactions (society_id, trx_date DESC);

CREATE INDEX idx_transactions_source ON transactions (source_table, source_id);

CREATE INDEX idx_transactions_acc_date ON transactions (acc_id, trx_date);

CREATE INDEX idx_txn_unreconciled_bank ON transactions (society_id, acc_id, trx_date)
WHERE
    bank_reconciled = FALSE;

CREATE INDEX idx_transactions_entity_date ON transactions (entity_id, trx_date);

CREATE INDEX idx_payables_society_status ON payables (society_id, status);

CREATE INDEX idx_payables_roster ON payables (roster_id);

CREATE INDEX idx_receipts_society_status ON receipts (society_id, status);

CREATE INDEX idx_receipts_entity_role ON receipts (entity_id, role);

CREATE INDEX idx_expenses_society_status ON expenses (society_id, status);

CREATE INDEX idx_expenses_entity_role ON expenses (entity_id, role);

CREATE INDEX idx_payables_entity_role ON payables (entity_id, role);

CREATE INDEX idx_receivables_society_status ON receivables (society_id, status);

CREATE INDEX idx_receivables_entity ON receivables (entity_id, role);

CREATE INDEX idx_receivables_due_date ON receivables (due_date);

CREATE INDEX idx_receivables_entity_status_date ON receivables (
    entity_id,
    role,
    status,
    due_date
);

CREATE INDEX idx_events_society_date ON events (society_id, event_date);

CREATE INDEX idx_concerns_society_status ON concerns (society_id, status);

CREATE INDEX idx_gate_society_time ON gate_access (society_id, time_in);

CREATE INDEX idx_security_roster_date ON security_roster (society_id, roster_date);

CREATE INDEX idx_ven_charges_society ON ven_charges_fines_basis (society_id, ven_id);

CREATE INDEX idx_ven_charges_status ON ven_charges_fines_basis (society_id, ven_status);

CREATE INDEX idx_vendor_passes_user ON vendor_passes (user_id, valid_until);

CREATE INDEX idx_assets_society ON assets (society_id, disposed);

CREATE INDEX idx_dashboard_settings_lookup ON Dashboard_settings (society_id, key);

-- SECTION 3: EVENT QR TICKETS, VISITORS & SUBSCRIBABLE ALERTS
-- ════════════════════════════════════════════════════════════════
-- ════════════════════════════════════════════════════════════════
-- POLLING SYSTEM
-- ════════════════════════════════════════════════════════════════

CREATE INDEX idx_polls_society ON polls (society_id);

CREATE INDEX idx_polls_status ON polls (status);

CREATE INDEX idx_poll_participation_apartment ON poll_participation (apartment_id);

CREATE INDEX idx_poll_ballots_poll ON poll_ballots (poll_id, choice);

CREATE INDEX idx_tds_section_rates_lookup ON tds_section_rates (
    society_id,
    section,
    discriminator,
    effective_from
);

-- SECTION 3: FUNCTIONS
-- ════════════════════════════════════════════════════════════════

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
      LEFT JOIN accounts p ON p.society_id = a.society_id AND p.id = a.parent_account_id
     WHERE a.society_id = NEW.id AND a.id = NEW.primary_bank_account_id;

    IF v_acc_society_id IS NULL THEN
        RAISE EXCEPTION 'primary_bank_account_id % does not exist for society %', NEW.primary_bank_account_id, NEW.id;
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

-- AFTER UPDATE trigger: activate event tickets when receipt is confirmed.

CREATE OR REPLACE FUNCTION fn_trg_receipt_confirm_activate_tickets()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status = 'confirmed' AND OLD.status = 'pending' THEN
        UPDATE event_tickets SET status = 'active' WHERE receipt_id = NEW.id;
        UPDATE event_ticket_items SET status = 'active'
        WHERE event_ticket_id IN (SELECT id FROM event_tickets WHERE receipt_id = NEW.id);
        UPDATE vendor_passes SET status = 'active' WHERE receipt_id = NEW.id;
    END IF;
    RETURN NEW;
END;
$$;

-- BEFORE INSERT/UPDATE trigger: auto-issue receipt_number when status flips to 'confirmed'.

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

CREATE OR REPLACE FUNCTION fn_trg_expense_hash_issue()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION fn_trg_expense_hash_insert()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RETURN NEW;
END;
$$;

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

CREATE OR REPLACE FUNCTION fn_apartment_outstanding(p_apartment_id INT)
RETURNS NUMERIC(15,2) LANGUAGE SQL STABLE AS $$
    SELECT COALESCE(SUM(amount - paid_amount), 0)::NUMERIC(15,2)
    FROM receivables r
    WHERE r.entity_id = p_apartment_id AND r.role = 'apartment'
      AND r.status IN ('pending','partial');
$$;

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

CREATE OR REPLACE FUNCTION fn_trg_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- QR REISSUE AUDIT LOG (2026-09)
-- One row per admin-initiated revoke/reissue of a versioned QR
-- (apartment/vendor/security/admin/patrol_location). This is the ONLY
-- way qr_version ever changes post-issuance — see
-- app/services/qr_service.py revoke_and_reissue. Exported as an xlsx
-- via database/qr_reissue_export.py.
-- ════════════════════════════════════════════════════════════════
CREATE TABLE qr_reissue_log (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    role_code VARCHAR(5) NOT NULL, -- APT / VND / SEC / ADM / PTL
    entity_id INT NOT NULL, -- role_code's own table.id (ADM = users.id, per the same convention _current_qr_version already uses)
    entity_label VARCHAR(150), -- human label captured at reissue time (flat number, vendor name, etc.) so the log stays readable if the entity is later renamed/removed
    old_nonce VARCHAR(4),
    new_nonce VARCHAR(4) NOT NULL,
    reason VARCHAR(20) NOT NULL CHECK (
        reason IN (
            'lost',
            'theft',
            'mutilated',
            'request',
            'other'
        )
    ),
    actor_user_id INT NOT NULL REFERENCES users (id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_qr_reissue_log_society ON qr_reissue_log (society_id, created_at DESC);

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

CREATE OR REPLACE FUNCTION fn_trg_polls_qr()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.qr_version = (1000 + FLOOR(RANDOM() * 9000))::INT;
    RETURN NEW;
END;
$$;

-- SECTION 3B: GATE-PASS EVALUATION
-- ════════════════════════════════════════════════════════════════

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
          AND vp.status = 'active'
          AND CURRENT_DATE >= vp.issued_date
          AND CURRENT_DATE <= vp.valid_until;

        IF v_pass_expiry IS NULL THEN
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

CREATE OR REPLACE FUNCTION fn_check_noc_eligibility(p_apartment_id INT)
RETURNS TABLE(eligible BOOLEAN, reason TEXT, outstanding NUMERIC(15,2))
LANGUAGE plpgsql STABLE AS $$
DECLARE v_standing RECORD;
BEGIN
    SELECT * INTO v_standing FROM fn_get_standing(
        (SELECT society_id FROM apartments WHERE id = p_apartment_id),
        p_apartment_id,
        CURRENT_DATE
    );
    IF v_standing.noc_blocked THEN
        RETURN QUERY SELECT FALSE,
            ('NOC blocked: ' || 
             CASE WHEN v_standing.dues_outstanding > 0 THEN 'outstanding dues Rs.' || v_standing.dues_outstanding ELSE '' END ||
             CASE WHEN v_standing.dues_outstanding > 0 AND v_standing.loan_outstanding > 0 THEN '; ' ELSE '' END ||
             CASE WHEN v_standing.loan_outstanding > 0 THEN 'outstanding owner loan Rs.' || v_standing.loan_outstanding ELSE '' END)::TEXT,
            (v_standing.dues_outstanding + v_standing.loan_outstanding)::NUMERIC(15,2);
    ELSE
        RETURN QUERY SELECT TRUE, 'No outstanding dues — eligible for NOC'::TEXT, 0::NUMERIC(15,2);
    END IF;
END;
$$;

-- SECTION 4: RECEIVABLES ENGINE (apartment maintenance, monthly)
-- ════════════════════════════════════════════════════════════════

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
    v_fund_gst_exempt     BOOLEAN;
    v_first_rate          NUMERIC(5,2);
    v_first_inc           NUMERIC(10,2);
BEGIN
    SELECT calc_start_date INTO v_society_calc_start FROM societies WHERE id = p_society_id;
    IF NOT FOUND THEN RETURN; END IF;

    -- Read fund_gst_exempt setting (default TRUE = exempt)
    SELECT fund_gst_exempt INTO v_fund_gst_exempt FROM society_compliance_settings WHERE society_id = p_society_id;
    v_fund_gst_exempt := COALESCE(v_fund_gst_exempt, TRUE);

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
      AND name ILIKE '%Sinking Fund Reserve%'
      AND drcr_account = 'Cr'
    LIMIT 1;

    SELECT id INTO v_repair_acc_id FROM accounts
    WHERE society_id = p_society_id
      AND name ILIKE '%Repair & Maintenance Fund Reserve%'
      AND drcr_account = 'Cr'
    LIMIT 1;

    SELECT id INTO v_cgst_acc_id FROM accounts
    WHERE society_id = p_society_id
      AND tab_name = 'CGST'
    LIMIT 1;

    SELECT id INTO v_sgst_acc_id FROM accounts
    WHERE society_id = p_society_id
      AND tab_name = 'SGST'
    LIMIT 1;


    -- Act s.18(2): where an owner is not in occupation, the occupier (tenant) is jointly and
    -- severally liable for the owner's common expenses, in addition to and not in substitution
    -- of the owner's own liability. For a UP AOA society that is hard-wired by the regime
    -- parameter 'tenant_joint_liability'; for other regimes it is read from the same parameter
    -- if configured. The bill generator records the linkage once per periodic receivable so
    -- recovery and statement reports can act on both parties from the books, not from a
    -- lookup-only function that nobody calls.
    IF fn_regime_param_num(p_society_id, 'tenant_joint_liability', v_month) = 1 THEN
        INSERT INTO tenant_liability_links (society_id, apartment_id, receivable_id, liability_as_of, created_at)
        SELECT p_society_id, apt.id, currval(pg_get_serial_sequence('receivables','id')), v_month_start, NOW()
        WHERE EXISTS (
            SELECT 1 FROM tenants t
            WHERE t.society_id = p_society_id
              AND t.apartment_id = apt.id
              AND t.is_active
              AND (t.tenancy_end IS NULL OR t.tenancy_end >= v_month_start)
        );
    END IF;
    FOR apt IN
        SELECT id, apartment_size, apt_calc_start_date, undivided_interest_pct FROM apartments
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
                   apt_sinking_fund_rate, apt_repair_fund_rate, charges_interest,
                   billing_basis, common_expense_budget_monthly
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
                charge.apt_interest_pct       := CASE
                    WHEN fn_regime_param_exists(p_society_id, 'arrears_interest_pct', v_month)
                        THEN NULL
                    ELSE 1.75
                END;
                charge.start_date             := v_month_start;
                charge.end_date               := v_month_end;
                charge.apt_sinking_fund_rate  := 0;
                charge.apt_repair_fund_rate   := 0;
                charge.charges_interest       := TRUE;
                charge.billing_basis          := 'per_sqft';
                charge.common_expense_budget_monthly := NULL;
            END IF;

            v_overlap_start := GREATEST(v_month_start, charge.start_date, v_calc_start);
            v_overlap_end   := LEAST(v_month_end, COALESCE(charge.end_date, v_month_end));
            v_overlap_days  := GREATEST((v_overlap_end - v_overlap_start + 1)::INT, 0);

            IF v_overlap_days = 0 THEN
                v_month := (v_month + INTERVAL '1 month')::DATE;
                CONTINUE;
            END IF;

            -- Maintenance base amount.
            -- 'undivided_interest' (UP Apartment Act 2010 s.18(1)): the society's monthly common-expense
            -- budget x this flat's declared % of undivided interest. That is the statutory basis for a
            -- UP AOA society. For that regime the parameter 'billing_basis_required' is set to 1, so an
            -- unpaid flat MUST have a budget and a declared undivided-interest percentage before the
            -- engine will bill it — a missing percentage or missing budget is treated as a compliance gap
            -- (logged to compliance_flags) and the flat is NOT silently billed at the per-sq-ft default.
            -- For other regimes (or a UP society whose board has deliberately chosen per-sqft under a
            -- board/general-body resolution the regime parameter does not forbid) the existing fallback
            -- order applies: hard maintenance amount override, then per-sq-ft rate.
            IF charge.billing_basis = 'undivided_interest'
               AND COALESCE(charge.common_expense_budget_monthly, 0) > 0
               AND apt.undivided_interest_pct IS NOT NULL THEN
                v_base_maint := ROUND(charge.common_expense_budget_monthly * apt.undivided_interest_pct / 100
                                      * v_overlap_days::NUMERIC / v_days_in_month, 2);
            ELSIF charge.billing_basis = 'undivided_interest' THEN
                -- UP AOA s.18(1) regime: undivided-interest billing was selected but the flat is missing
                -- the percentage and/or the society is missing the monthly common-expense budget. That is
                -- not a default-able gap — the flat cannot be billed at per-sqft as if nothing were wrong.
                IF fn_regime_param_num(p_society_id, 'billing_basis_required', v_month) = 1 THEN
                    INSERT INTO compliance_flags (society_id, rule_code, source_table, source_id, detail)
                    VALUES (p_society_id, 'BILLING_BASIS_UNDIVIDED_INTEREST_MISSING',
                            'apt_charges_fines_basis', charge.id,
                            format('Flat %s cannot be billed under undivided-interest basis for %s: '
                                   'budget = %s, undivided_interest_pct = %s',
                                   COALESCE(apt.flat_number, apt.id::TEXT),
                                   TO_CHAR(v_month, 'YYYY-MM'),
                                   charge.common_expense_budget_monthly,
                                   apt.undivided_interest_pct))
                    ON CONFLICT (source_table, source_id, rule_code) DO NOTHING;
                    v_base_maint := 0;
                ELSE
                    v_base_maint := ROUND(apt.apartment_size * charge.apt_maintenance_rate * v_overlap_days::NUMERIC / v_days_in_month, 2);
                END IF;
            ELSIF charge.apt_maintenance_amount IS NOT NULL AND charge.apt_maintenance_amount > 0 THEN
                v_base_maint := ROUND(charge.apt_maintenance_amount * v_overlap_days::NUMERIC / v_days_in_month, 2);
            ELSE
                v_base_maint := ROUND(apt.apartment_size * charge.apt_maintenance_rate * v_overlap_days::NUMERIC / v_days_in_month, 2);
            END IF;

            -- Sinking fund and repair fund (per-sq-ft, same proration as maintenance).
            -- Each levy is billed only when the society has configured a rate for it
            -- on the apt_charges_fines_basis row; the rates are driven by resolutions
            -- the UP scheme can record through regime parameters, so the engine stops
            -- billing them as silent per-sq-ft defaults in every mode.
            v_base_sinking := CASE WHEN COALESCE(charge.apt_sinking_fund_rate, 0) > 0
                THEN ROUND(apt.apartment_size * charge.apt_sinking_fund_rate * v_overlap_days::NUMERIC / v_days_in_month, 2)
                ELSE 0 END;
            v_base_repair  := CASE WHEN COALESCE(charge.apt_repair_fund_rate, 0) > 0
                THEN ROUND(apt.apartment_size * charge.apt_repair_fund_rate * v_overlap_days::NUMERIC / v_days_in_month, 2)
                ELSE 0 END;

            -- First-overdue-month interest on the common-expense component.
            -- Model Bye-laws 2011, bye-law 46(a): interest on overdue common
            -- expenses is a General Body resolution decision, recorded as the regime
            -- parameter 'arrears_interest_pct'. For a UP AOA society
            -- this replaces the old hard-coded 1.75%/month default with a value the
            -- association actually resolved. Interest is seeded only on the first
            -- month the bill is overdue, so a flat billed in April with due_date in
            -- April does not pick up interest at creation time; interest from May
            -- onward is still added by fn_apply_receivable_interest when it next runs.
            IF fn_regime_param_num(p_society_id, 'arrears_interest_pct', v_month) > 0
               AND v_base_maint > 0
               AND v_month < period_first_day(v_month)
            THEN
                v_first_rate := fn_regime_param_num(p_society_id, 'arrears_interest_pct', v_month);
                v_first_inc  := ROUND(v_base_maint * v_first_rate / 100.0, 2);
                IF v_first_inc > 0 THEN
                    v_base_maint := v_base_maint + v_first_inc;
                END IF;
            END IF;

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
            -- fund_gst_exempt = TRUE means sinking & repair funds are exempt from GST taxable base
            -- (they are still tracked as receivables but not included in GST calculation)
            IF v_fund_gst_exempt THEN
                v_total_taxable := v_base_maint;
            ELSE
                v_total_taxable := v_base_maint + v_base_sinking + v_base_repair;
            END IF;

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

CREATE OR REPLACE FUNCTION fn_apply_receivable_interest(p_society_id INT)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    rec               RECORD;
    v_rate            NUMERIC(5,2);
    v_months_elapsed  NUMERIC(10,4);
    v_months_new      NUMERIC(10,4);
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
        -- Model Bye-Laws 2011, bye-law 46(a): interest on overdue common expenses
        -- is set by General Body resolution and recorded as a regime parameter, so the
        -- rate is a governance decision, not a free per-flat default. Before UP_AOA_2010
        -- societies set the regime parameter 'arrears_interest_pct', a
        -- society that hits this path has a compliance gap: interest is accruing at the
        -- legacy default with no resolution trail. Caller (or the UP compliance card) must
        -- record the resolution and set the parameter; this function never guesses.
        v_rate := fn_regime_param_num(p_society_id, 'arrears_interest_pct', CURRENT_DATE);

        IF v_rate IS NULL OR v_rate <= 0 THEN
            CONTINUE;
        END IF;

        v_months_elapsed := ROUND((CURRENT_DATE - rec.due_date) / 30.0, 4);

        v_months_new := ROUND(v_months_elapsed - rec.interest_months_applied, 4);

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
--                     (cheque/upi/card/bank/crypto alike) — UNLESS the
--                     optional p_credit_acc_id names a fund that has its
--                     own entry in fund_bank_account_map (2026-09, fund
--                     management audit follow-up), in which case that
--                     fund's dedicated bank account is used instead. This
--                     is what lets a society keep Corpus/Sinking Fund
--                     money in a physically separate account/FD rather
--                     than everything landing in the one "primary" bank
--                     account regardless of which fund it was for.
--                     Raises loudly if no primary account is configured
--                     and no mapping applies, rather than silently
--                     falling back to CiH like the old function did.
--
-- p_credit_acc_id is OPTIONAL and NULL by default so every call site that
-- isn't specifically about a fund (fn_verify_expense, fn_verify_payment,
-- fn_save_expense, fn_sell_vendor_pass/event_ticket, fn_buy/dispose_asset/
-- deposit, fn_pay_rcm_liability) keeps resolving to primary_bank_account_id
-- exactly as before, completely unaffected by this change.
--
-- Call sites that DO pass it:
--   fn_verify_receipt / fn_verify_receivable / fn_save_receipt — a single,
--     unambiguous credit/fund account is known up front.
--   fn_apply_apartment_dues_fifo_core / ..._selective_core — one "Pay Dues"
--     payment can settle several receivable rows spanning different funds
--     and Maintenance at once, so these do NOT collapse to one bank leg:
--     they resolve a bank account PER settled row and emit one Dr leg per
--     distinct account, attributing each row's share of the money to the
--     account that row's acc_id maps to (any overpayment goes to the
--     primary account, since an advance is maintenance income, not a fund
--     contribution). Without that per-row split the mapping was silently
--     inconsistent: verifying dues one flat at a time banked into the
--     mapped account while the ordinary FIFO "Pay Dues" path did not.
CREATE OR REPLACE FUNCTION fn_resolve_bank_leg(p_society_id INT, p_mode VARCHAR, p_credit_acc_id INT DEFAULT NULL)
RETURNS INT LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_acc_id INT;
    v_mapped_acc_id INT;
BEGIN
    -- 'journal' (pure book entry, e.g. depreciation) needs no completing
    -- leg at all, same as 'cash' — both legs of a journal entry are
    -- always written explicitly by the caller.
    IF p_mode IN ('cash', 'journal') THEN
        RETURN NULL;
    END IF;

    IF p_credit_acc_id IS NOT NULL THEN
        SELECT bank_acc_id INTO v_mapped_acc_id
        FROM fund_bank_account_map
        WHERE society_id = p_society_id AND fund_acc_id = p_credit_acc_id;

        IF v_mapped_acc_id IS NOT NULL THEN
            RETURN v_mapped_acc_id;
        END IF;
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
    -- Pass v_rec.acc_id as the credit account so a fund-specific bank
    -- mapping (fund_bank_account_map) can route this receipt's money into
    -- a dedicated account (e.g. a separate Corpus Fund account) instead of
    -- always landing in primary_bank_account_id — see fn_resolve_bank_leg.
    v_bank_acc := fn_resolve_bank_leg(v_rec.society_id, v_mode, v_rec.acc_id);
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
    v_limit_msg TEXT;
BEGIN
    SELECT * INTO v_rec FROM expenses WHERE id = p_expense_id FOR UPDATE;
    IF NOT FOUND    THEN expense_id := p_expense_id; receipt_number := NULL; msg := 'Error: Expense not found'; RETURN NEXT; RETURN; END IF;
    IF v_rec.status = 'confirmed'  THEN expense_id := p_expense_id; receipt_number := v_rec.receipt_number; msg := 'Already confirmed'; RETURN NEXT; RETURN; END IF;
    IF v_rec.status = 'cancelled'  THEN expense_id := p_expense_id; receipt_number := v_rec.receipt_number; msg := 'Error: Expense is cancelled'; RETURN NEXT; RETURN; END IF;
    IF v_rec.acc_id IS NULL        THEN expense_id := p_expense_id; receipt_number := v_rec.receipt_number; msg := 'Error: No expense account on this row'; RETURN NEXT; RETURN; END IF;

    v_mode := COALESCE(p_mode, v_rec.mode);

    -- UP Model Bye-Laws (financial provisions): payments above the cheque threshold
    -- must not be made in cash. Regime-driven (NULL threshold = rule off); 'warn'
    -- records a compliance flag, 'block' (societies.cash_limit_mode) refuses it.
    IF v_mode = 'cash' THEN
        v_limit_msg := fn_check_cash_payment_limit(v_rec.society_id, v_rec.amount, v_mode);
        IF v_limit_msg IS NOT NULL THEN
            IF fn_cash_limit_mode(v_rec.society_id) = 'block' THEN
                expense_id := p_expense_id; receipt_number := v_rec.receipt_number;
                msg := 'Error: ' || v_limit_msg; RETURN NEXT; RETURN;
            END IF;
            INSERT INTO compliance_flags (society_id, rule_code, source_table, source_id, detail)
            VALUES (v_rec.society_id, 'CASH_PAYMENT_LIMIT', 'expenses', v_rec.id, v_limit_msg)
            ON CONFLICT (source_table, source_id, rule_code) DO NOTHING;
        END IF;
    END IF;
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

    -- RCM: self-invoiced GST liability on payments to unregistered parties.
    -- Mirrors the immediate-confirm branch in fn_save_expense — expenses
    -- submitted as 'pending' and confirmed here previously never triggered
    -- this at all, silently skipping RCM liability for them.
    IF v_rec.rcm_applicable THEN
        DECLARE
            v_rcm_cgst NUMERIC(15,2) := 0;
            v_rcm_sgst NUMERIC(15,2) := 0;
            v_rcm_igst NUMERIC(15,2) := 0;
            v_rcm_itc_eligible BOOLEAN := FALSE;
        BEGIN
            SELECT COALESCE(rcm.cgst_amount, 0), COALESCE(rcm.sgst_amount, 0),
                   COALESCE(rcm.igst_amount, 0), COALESCE(rcm.itc_eligible, FALSE)
              INTO v_rcm_cgst, v_rcm_sgst, v_rcm_igst, v_rcm_itc_eligible
              FROM fn_compute_rcm_liability(v_rec.society_id, p_expense_id) AS rcm;
            IF v_rcm_cgst > 0 OR v_rcm_sgst > 0 OR v_rcm_igst > 0 THEN
                PERFORM fn_post_rcm_liability(v_rec.society_id, p_expense_id, v_rcm_cgst, v_rcm_sgst, v_rcm_igst, v_rcm_itc_eligible);
            END IF;
        END;
    END IF;

    expense_id := p_expense_id;
    receipt_number := NULL;
    msg := 'Verified: transaction #' || v_trx_id::TEXT;
    RETURN NEXT;
END;
$$;

-- Single-row verify. Writes the income side(s), then the cash/bank Dr side.

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

    -- Pass v_rec.acc_id (the receivable's fund/income account) so a
    -- fund-specific bank mapping can apply — see fn_resolve_bank_leg.
    v_bank_acc := fn_resolve_bank_leg(v_rec.society_id, p_mode, v_rec.acc_id);
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

CREATE OR REPLACE FUNCTION fn_verify_receivable_by_bill_group(
    p_bill_group_id UUID,
    p_confirmed_by  INT,
    p_mode          VARCHAR DEFAULT 'cash',
    p_amount        NUMERIC DEFAULT NULL
)
RETURNS TABLE(msg TEXT, receipt_id INT) LANGUAGE plpgsql AS $$
DECLARE
    v_rec        RECORD;
    v_remaining  NUMERIC(15,2);
    v_take       NUMERIC(15,2);
    v_residual   NUMERIC(15,2);
    v_msg        TEXT;
    v_total_take NUMERIC(15,2) := 0;
    v_society_id INT;
    v_entity_id  INT;
    v_period     DATE;
    v_desc       TEXT;
    v_receipt_id INT;
BEGIN
    IF p_amount IS NOT NULL AND p_amount <= 0 THEN
        RETURN QUERY SELECT 'Error: amount must be > 0'::TEXT, NULL::INT; RETURN;
    END IF;

    SELECT COALESCE(SUM(amount - paid_amount), 0)::NUMERIC(15,2)
      INTO v_remaining
      FROM receivables
     WHERE bill_group_id = p_bill_group_id
       AND status IN ('pending','partial','unverified');

    IF v_remaining <= 0 THEN
        RETURN QUERY SELECT 'Nothing outstanding on this bill group'::TEXT, NULL::INT; RETURN;
    END IF;

    IF p_amount IS NOT NULL AND p_amount < v_remaining THEN
        v_remaining := p_amount;
    END IF;

    SELECT society_id, entity_id, MIN(period_month), STRING_AGG(DISTINCT description, ', ')
      INTO v_society_id, v_entity_id, v_period, v_desc
      FROM receivables
     WHERE bill_group_id = p_bill_group_id
     GROUP BY society_id, entity_id;

    -- Bug fix (2026-08): this loop previously RETURNed on its first
    -- iteration (inside the IF v_first block), which exited the whole
    -- function immediately — so only the first receivable line of a
    -- multi-line bill (e.g. just Maintenance) was ever actually verified;
    -- GST/sinking/repair lines in the same bill group silently stayed
    -- 'pending'/'partial' even though the toast reported success. Now the
    -- loop runs to completion (or until v_remaining is exhausted) before
    -- returning anything.
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

        v_total_take := v_total_take + v_take;
        v_remaining := v_remaining - v_take;
    END LOOP;

    IF v_total_take <= 0 THEN
        RETURN QUERY SELECT COALESCE(v_msg, 'Nothing outstanding on this bill group')::TEXT, NULL::INT; RETURN;
    END IF;

    -- One receipt per bill-group payment, for print/save/email — this
    -- function previously created no receipts record at all for admin
    -- direct/confirmed bill-group payments, so there was nothing to open.
    INSERT INTO receipts (
        society_id, user_id, entity_id, role, receipt_date, acc_id,
        particulars, amount, mode, status, created_by, confirmed_by, confirmed_at
    ) VALUES (
        v_society_id, p_confirmed_by, v_entity_id, 'apartment', CURRENT_DATE, NULL,
        COALESCE(v_desc, 'Maintenance Payment') || COALESCE(' — ' || TO_CHAR(v_period, 'Mon YYYY'), ''),
        v_total_take, p_mode, 'confirmed', p_confirmed_by, p_confirmed_by, NOW()
    ) RETURNING id INTO v_receipt_id;

    RETURN QUERY SELECT COALESCE(v_msg, 'Bill group verified')::TEXT, v_receipt_id;
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
RETURNS TABLE(transaction_id INT, allocated NUMERIC, unallocated NUMERIC, journal_id INT, receipt_id INT)
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
    v_receipt_id   INT;  -- new (2026-08): the receipt this payment is recorded against — either newly
                          -- created here (admin-direct path) or the pre-existing self-reported receipt
                          -- being confirmed (p_source_id, when p_source_table='receipts')
    -- Per-bank-account split of the incoming money (2026-09). A split bill
    -- settles rows carrying DIFFERENT acc_ids — a Sinking Fund line (3210),
    -- a Repair Fund line (3220), a Maintenance line (4210) — and those can
    -- be mapped to different physical bank accounts via
    -- fund_bank_account_map. Posting one lump Dr to the single primary bank
    -- account is what made the mapping silently inconsistent: verifying
    -- dues one flat at a time banked into the mapped account, while paying
    -- through the FIFO path (the common case) did not. Accumulated here as
    -- {bank_acc_id: amount} and emitted as one Dr leg per distinct account
    -- after the loop, so the journal still balances (the legs sum to
    -- v_total_take + v_remaining = p_amount, exactly as the old single leg
    -- did).
    v_legs      JSONB := '{}'::JSONB;
    v_leg_bank  INT;
    v_leg       RECORD;
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

        -- Attribute this row's money to whatever bank account its own
        -- acc_id maps to (NULL for cash mode, and NULL for any account
        -- without a mapping — both fall through to the society's primary
        -- account below via v_bank_acc).
        v_leg_bank := COALESCE(fn_resolve_bank_leg(v_society_id, p_mode, rec.acc_id), v_bank_acc);
        IF v_leg_bank IS NOT NULL THEN
            v_legs := v_legs || jsonb_build_object(
                v_leg_bank::TEXT,
                COALESCE((v_legs ->> v_leg_bank::TEXT)::NUMERIC, 0) + v_take
            );
        END IF;
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

    -- Any overpayment is a maintenance receipt, so it belongs on the
    -- primary account (maintenance is not a fund) — attribute it before
    -- the Dr legs are emitted, so it lands in the same accumulator as the
    -- rest of the payment.
    IF v_remaining > 0 AND v_bank_acc IS NOT NULL THEN
        v_legs := v_legs || jsonb_build_object(
            v_bank_acc::TEXT,
            COALESCE((v_legs ->> v_bank_acc::TEXT)::NUMERIC, 0) + v_remaining
        );
    END IF;

    -- Dr: cash / bank paired side (actual amount received), split across
    -- the distinct bank accounts the settled rows map to. References the
    -- originating record (p_source_id, e.g. a confirmed self-pay receipt)
    -- when given, else the first Cr leg posted this call, so the journal is
    -- traceable as one event either way. When nothing maps anywhere
    -- (cash mode, or no fund has a mapping) this is the single primary
    -- leg exactly as before.
    FOR v_leg IN
        SELECT e.key::INT AS bank_acc, e.value::NUMERIC(15,2) AS amt
          FROM jsonb_each_text(v_legs) e
         WHERE e.value::NUMERIC > 0
         ORDER BY e.key::INT
    LOOP
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_society_id, 'Dr', CURRENT_DATE, v_leg.bank_acc, p_apartment_id, 'apartment',
            'Cash received - Maintenance Payment',
            v_leg.amt, p_mode, 'paid', p_confirmed_by, NOW(), p_source_table, COALESCE(p_source_id, v_first_trx_id), v_journal_id
        );
    END LOOP;

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

    -- Receipt of record for this payment, for print/save/email. When
    -- confirming a pre-existing self-reported receipt (p_source_table=
    -- 'receipts', p_source_id set), that receipt already exists and the
    -- caller (fn_confirm_apartment_self_payment) marks it confirmed itself
    -- — don't create a duplicate. Otherwise (the admin-direct path, no
    -- pre-existing receipt) create one now; this function previously never
    -- created any receipts record for admin-direct FIFO payments, so there
    -- was nothing to open/print/email afterward.
    IF p_source_table = 'receipts' AND p_source_id IS NOT NULL THEN
        v_receipt_id := p_source_id;
    ELSE
        INSERT INTO receipts (
            society_id, user_id, entity_id, role, receipt_date, acc_id,
            particulars, amount, mode, status, created_by, confirmed_by, confirmed_at
        ) VALUES (
            v_society_id, p_confirmed_by, p_apartment_id, 'apartment', CURRENT_DATE, NULL,
            COALESCE(p_particulars, 'Maintenance Payment'),
            p_amount, p_mode, 'confirmed', p_confirmed_by, p_confirmed_by, NOW()
        ) RETURNING id INTO v_receipt_id;
    END IF;

    RETURN QUERY SELECT v_first_trx_id,
        (p_amount - v_remaining)::NUMERIC(15,2),
        v_remaining::NUMERIC(15,2),
        v_journal_id,
        v_receipt_id;
END;
$$;

-- fn_pay_apartment_dues_fifo: admin-immediate path (Pay Dues button).
-- Thin wrapper over fn_apply_apartment_dues_fifo_core — behavior/signature
-- unchanged from before the core was extracted (2026-08); source_table stays
-- 'receivables' with no source_id override, matching the original.

CREATE OR REPLACE FUNCTION fn_pay_apartment_dues_fifo(
    p_apartment_id INT,
    p_amount       NUMERIC,
    p_mode         VARCHAR DEFAULT 'cash',
    p_confirmed_by INT     DEFAULT NULL,
    p_particulars  TEXT    DEFAULT NULL
)
RETURNS TABLE(transaction_id INT, allocated NUMERIC, unallocated NUMERIC, journal_id INT, receipt_id INT)
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

-- Core logic for selective payments
CREATE OR REPLACE FUNCTION fn_apply_apartment_dues_selective_core(
    p_apartment_id INT,
    p_amount       NUMERIC,
    p_receivable_ids INT[],
    p_mode         VARCHAR DEFAULT 'cash',
    p_confirmed_by INT     DEFAULT NULL,
    p_particulars  TEXT    DEFAULT NULL,
    p_source_table VARCHAR DEFAULT 'receivables',
    p_source_id    INT     DEFAULT NULL
)
RETURNS TABLE(transaction_id INT, allocated NUMERIC, unallocated NUMERIC, journal_id INT, receipt_id INT)
LANGUAGE plpgsql AS $$
DECLARE
    v_society_id INT;
    v_maint_acc_id INT;
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
    v_total_take   NUMERIC(15,2) := 0;
    v_first_trx_id INT;
    v_receipt_id   INT;
    -- Per-bank-account split of the incoming money — see the identical
    -- accumulator in fn_apply_apartment_dues_fifo_core. Both "Pay Dues"
    -- engines have to agree here, or a society that maps its Sinking Fund
    -- to a separate account would see the same payment banked into that
    -- account when taken FIFO and into the primary account when the very
    -- same dues were selected by hand.
    v_legs      JSONB := '{}'::JSONB;
    v_leg_bank  INT;
    v_leg       RECORD;
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN RAISE EXCEPTION 'Amount must be > 0'; END IF;

    SELECT society_id INTO v_society_id FROM apartments WHERE id = p_apartment_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Apartment not found'; END IF;

    SELECT id INTO v_fallback_int_acc FROM accounts
    WHERE society_id = v_society_id AND name ILIKE '%Due Interest%' AND drcr_account = 'Cr' LIMIT 1;

    SELECT id INTO v_maint_acc_id FROM accounts
    WHERE society_id = v_society_id AND name ILIKE '%Society Maintenance Charge%' AND drcr_account = 'Cr' LIMIT 1;

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
           AND id = ANY(p_receivable_ids)
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

        -- Attribute this row's money to whatever bank account its own
        -- acc_id maps to (falls through to the society's primary account
        -- via v_bank_acc when the account has no mapping, and to no leg at
        -- all in cash mode).
        v_leg_bank := COALESCE(fn_resolve_bank_leg(v_society_id, p_mode, rec.acc_id), v_bank_acc);
        IF v_leg_bank IS NOT NULL THEN
            v_legs := v_legs || jsonb_build_object(
                v_leg_bank::TEXT,
                COALESCE((v_legs ->> v_leg_bank::TEXT)::NUMERIC, 0) + v_take
            );
        END IF;
    END LOOP;

    IF v_total_take > 0 THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_society_id, 'Cr', CURRENT_DATE, fn_resolve_sdr_leg(v_society_id, p_mode), p_apartment_id, 'apartment',
            COALESCE(p_particulars, 'Selective Maintenance Payment'),
            v_total_take, p_mode, 'paid', p_confirmed_by, NOW(), p_source_table, p_source_id, v_journal_id
        ) RETURNING id INTO v_trx_id;
        IF v_first_trx_id IS NULL THEN v_first_trx_id := v_trx_id; END IF;
    END IF;

    IF v_remaining > 0 THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_society_id, 'Cr', CURRENT_DATE, v_maint_acc_id, p_apartment_id, 'apartment',
            COALESCE(p_particulars, 'Selective Maintenance Payment') || ' (Advance)',
            v_remaining, p_mode, 'paid', p_confirmed_by, NOW(), p_source_table, p_source_id, v_journal_id
        ) RETURNING id INTO v_trx_id;
        IF v_first_trx_id IS NULL THEN v_first_trx_id := v_trx_id; END IF;
    END IF;

    -- Overpayment is a maintenance receipt, so it belongs on the primary
    -- account (maintenance is not a mapped fund).
    IF v_remaining > 0 AND v_bank_acc IS NOT NULL THEN
        v_legs := v_legs || jsonb_build_object(
            v_bank_acc::TEXT,
            COALESCE((v_legs ->> v_bank_acc::TEXT)::NUMERIC, 0) + v_remaining
        );
    END IF;

    -- Dr: cash / bank paired side, one leg per distinct mapped account.
    -- Identical total to the single-leg version it replaces.
    FOR v_leg IN
        SELECT e.key::INT AS bank_acc, e.value::NUMERIC(15,2) AS amt
          FROM jsonb_each_text(v_legs) e
         WHERE e.value::NUMERIC > 0
         ORDER BY e.key::INT
    LOOP
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_society_id, 'Dr', CURRENT_DATE, v_leg.bank_acc, p_apartment_id, 'apartment',
            'Cash received - Selective Payment',
            v_leg.amt, p_mode, 'paid', p_confirmed_by, NOW(), p_source_table, COALESCE(p_source_id, v_first_trx_id), v_journal_id
        );
    END LOOP;

    IF v_remaining > 0 THEN
        INSERT INTO receivables (
            society_id, entity_id, role, acc_id, interest_acc_id,
            description, base_amount, amount, paid_amount, paid_principal,
            status, confirmed_by, confirmed_at, created_at
        ) VALUES (
            v_society_id, p_apartment_id, 'apartment', v_maint_acc_id,
            COALESCE(v_fallback_int_acc, v_maint_acc_id),
            'Advance Credit (Selective)', v_remaining, v_remaining, 0, 0,
            'credit', p_confirmed_by, NOW(), NOW()
        );
    END IF;

    IF p_source_table = 'receipts' AND p_source_id IS NOT NULL THEN
        v_receipt_id := p_source_id;
    ELSE
        INSERT INTO receipts (
            society_id, user_id, entity_id, role, receipt_date, acc_id,
            particulars, amount, mode, status, created_by, confirmed_by, confirmed_at
        ) VALUES (
            v_society_id, p_confirmed_by, p_apartment_id, 'apartment', CURRENT_DATE, NULL,
            COALESCE(p_particulars, 'Selective Maintenance Payment'),
            p_amount, p_mode, 'confirmed', p_confirmed_by, p_confirmed_by, NOW()
        ) RETURNING id INTO v_receipt_id;
    END IF;

    RETURN QUERY SELECT v_first_trx_id,
        (p_amount - v_remaining)::NUMERIC(15,2),
        v_remaining::NUMERIC(15,2),
        v_journal_id,
        v_receipt_id;
END;
$$;

-- Admin-immediate selective payment
CREATE OR REPLACE FUNCTION fn_pay_apartment_dues_selective(
    p_apartment_id INT,
    p_amount       NUMERIC,
    p_receivable_ids INT[],
    p_mode         VARCHAR DEFAULT 'cash',
    p_confirmed_by INT     DEFAULT NULL,
    p_particulars  TEXT    DEFAULT NULL
)
RETURNS TABLE(transaction_id INT, allocated NUMERIC, unallocated NUMERIC, journal_id INT, receipt_id INT)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT * FROM fn_apply_apartment_dues_selective_core(
        p_apartment_id, p_amount, p_receivable_ids, p_mode, p_confirmed_by, p_particulars,
        'receivables', NULL
    );
END;
$$;

-- Owner self-reporting selective payment
CREATE OR REPLACE FUNCTION fn_report_apartment_payment_selective(
    p_apartment_id INT,
    p_amount       NUMERIC,
    p_receivable_ids INT[],
    p_mode         VARCHAR,
    p_reported_by  INT,
    p_cheque_no    VARCHAR DEFAULT NULL,
    p_trx_id       VARCHAR DEFAULT NULL
)
RETURNS INT LANGUAGE plpgsql AS $$
DECLARE
    v_society_id INT;
    v_receipt_id INT;
    v_owns       BOOLEAN;
    v_ref        VARCHAR(255);
BEGIN
    SELECT society_id INTO v_society_id FROM apartments WHERE id = p_apartment_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Apartment not found'; END IF;

    SELECT EXISTS (
        SELECT 1 FROM users
        WHERE id = p_reported_by
          AND (role = 'admin' OR is_master_admin OR linked_id = p_apartment_id)
    ) INTO v_owns;
    IF NOT v_owns THEN RAISE EXCEPTION 'Unauthorized: User does not own apartment %', p_apartment_id; END IF;

    v_ref := 'SELECTIVE:' || array_to_string(p_receivable_ids, ',');

    INSERT INTO receipts(
        society_id, user_id, entity_id, role, receipt_date,
        acc_id, particulars, amount, mode, cheque_no, transaction_id, status, created_by, source_reference
    ) VALUES (
        v_society_id, p_reported_by, p_apartment_id, 'apartment', CURRENT_DATE,
        NULL, 'Owner Reported Payment (Selective)', p_amount, p_mode, p_cheque_no, p_trx_id, 'pending', p_reported_by, v_ref
    ) RETURNING id INTO v_receipt_id;

    RETURN v_receipt_id;
END;
$$;

-- Admin confirmation of owner's reported selective payment
CREATE OR REPLACE FUNCTION fn_confirm_apartment_self_payment_selective(
    p_receipt_id   INT,
    p_confirmed_by INT,
    p_mode         VARCHAR DEFAULT NULL
)
RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
    v_receipt   receipts%ROWTYPE;
    v_result    RECORD;
    v_receivable_ids INT[];
BEGIN
    SELECT * INTO v_receipt FROM receipts
     WHERE id = p_receipt_id AND role = 'apartment' AND status = 'pending'
     FOR UPDATE;
    IF NOT FOUND THEN
        RETURN 'Error: Receipt not found or not pending';
    END IF;

    IF v_receipt.source_reference NOT LIKE 'SELECTIVE:%' THEN
        RETURN 'Error: Receipt is not a selective payment receipt';
    END IF;

    v_receivable_ids := string_to_array(substring(v_receipt.source_reference from 11), ',')::INT[];

    SELECT * INTO v_result FROM fn_apply_apartment_dues_selective_core(
        v_receipt.entity_id, v_receipt.amount, v_receivable_ids, COALESCE(p_mode, v_receipt.mode),
        p_confirmed_by, v_receipt.particulars, 'receipts', v_receipt.id
    );

    UPDATE receipts
       SET status = 'confirmed', confirmed_by = p_confirmed_by, confirmed_at = NOW()
     WHERE id = p_receipt_id;

    RETURN 'Success: Selective payment confirmed and posted — transaction #' || v_result.transaction_id::TEXT;
END;
$$;

-- SECTION 5: payables ENGINE (security payroll, roster-driven)
-- ════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_auto_generate_payables(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    rec          RECORD;
    v_acc_id     INT;
    v_desc       TEXT;
BEGIN
    SELECT id INTO v_acc_id FROM accounts
    WHERE society_id = p_society_id AND tab_name = 'Salary'
    LIMIT 1;

    FOR rec IN
        SELECT sr.id AS roster_id, sr.security_id, sr.roster_date, ss.salary_per_shift, ss.ptl_penalty, sr.attendance_status,
               EXTRACT(EPOCH FROM (ga.time_out - ga.time_in)) / 3600.0 AS duration_hours,
               ga.time_in, ga.time_out, u2.id AS user_id
        FROM security_roster sr
        JOIN security_staff ss ON ss.id = sr.security_id
        JOIN users u2 ON u2.linked_id = sr.security_id AND u2.role = 'security'
        LEFT JOIN gate_access ga
             ON ga.entity_id = u2.id
            AND ga.role = 'SEC'
            AND ga.time_in::DATE = sr.roster_date
            AND ga.time_out IS NOT NULL
        WHERE sr.society_id = p_society_id
          AND sr.roster_date <= CURRENT_DATE
          AND (ga.id IS NOT NULL OR sr.attendance_status = 'leave_paid')
          AND NOT EXISTS (SELECT 1 FROM payables p WHERE p.roster_id = sr.id)
    LOOP
        v_desc := 'Salary ' || TO_CHAR(rec.roster_date, 'DD-Mon-YYYY');
        
        DECLARE
            v_fraction NUMERIC(3, 2);
            v_expected_scans INT := 0;
            v_actual_scans INT := 0;
            v_missed_scans INT := 0;
            v_penalty NUMERIC(10, 2) := 0;
            v_final_amount NUMERIC(10, 2) := 0;
        BEGIN
            IF rec.attendance_status = 'leave_paid' THEN
                v_fraction := 1.0;
                v_desc := v_desc || ' (Paid Leave)';
            ELSIF rec.duration_hours >= 8.0 THEN
                v_fraction := 1.0;
            ELSIF rec.duration_hours >= 4.0 THEN
                v_fraction := 0.5;
            ELSE
                v_fraction := 0.0;
                v_desc := v_desc || ' (Short shift: ' || ROUND(rec.duration_hours::NUMERIC, 1) || 'h - Review required)';
            END IF;

            v_final_amount := COALESCE(rec.salary_per_shift, 0) * v_fraction;

            IF rec.attendance_status != 'leave_paid' AND v_fraction > 0 THEN
                SELECT COALESCE(SUM(FLOOR((rec.duration_hours * 60.0) / NULLIF(pl.scan_interval, 120))), 0)
                INTO v_expected_scans
                FROM patrol_locations pl
                WHERE pl.society_id = p_society_id AND pl.active = TRUE;

                SELECT COUNT(*) INTO v_actual_scans
                FROM patrol_scans
                WHERE security_user_id = rec.user_id
                  AND scanned_at >= rec.time_in
                  AND scanned_at <= rec.time_out;

                IF v_actual_scans < v_expected_scans THEN
                    v_missed_scans := v_expected_scans - v_actual_scans;
                    v_penalty := v_missed_scans * COALESCE(rec.ptl_penalty, 0);
                    v_final_amount := GREATEST(0, v_final_amount - v_penalty);
                    IF v_penalty > 0 THEN
                        v_desc := v_desc || ' (Penalty: ₹' || v_penalty || ' for ' || v_missed_scans || ' missed patrol scans)';
                    END IF;
                END IF;
            END IF;

            INSERT INTO payables(
                society_id, entity_id, role, acc_id, description,
                roster_id, shift_date, shift_fraction, amount, status, due_date, created_at
            ) VALUES (
                p_society_id, rec.security_id, 'security', v_acc_id, v_desc,
                rec.roster_id, rec.roster_date, v_fraction, v_final_amount,
                'pending', rec.roster_date, NOW()
            );

            -- Automatically mark attendance as present if they worked at all and weren't on leave
            IF rec.attendance_status NOT IN ('leave_paid', 'leave_unpaid', 'absent') THEN
                UPDATE security_roster 
                SET attendance_status = 'present' 
                WHERE id = rec.roster_id AND attendance_status = 'scheduled';
            END IF;
        END;
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION trg_payable_update_amount() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.role = 'security' AND NEW.shift_fraction IS DISTINCT FROM OLD.shift_fraction THEN
        NEW.amount := (SELECT salary_per_shift FROM security_staff WHERE id = NEW.entity_id) * NEW.shift_fraction;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER payable_update_amount BEFORE UPDATE ON payables
FOR EACH ROW EXECUTE FUNCTION trg_payable_update_amount();

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

CREATE OR REPLACE FUNCTION fn_verify_payment(
    p_payment_id   INT,
    p_confirmed_by INT,
    p_mode         VARCHAR DEFAULT 'cash',
    p_tds_pct      NUMERIC DEFAULT 10
)
RETURNS TABLE(expense_id INT, msg TEXT) LANGUAGE plpgsql AS $$
DECLARE
    v_pay        payables%ROWTYPE;
    v_trx_id     INT;
    v_journal_id INT;
    v_bank_acc   INT;
    v_tds_acc    INT;
    v_tds_amt    NUMERIC(15,2) := 0;
    v_net_amt    NUMERIC(15,2);
    v_expense_id INT;
    v_limit_msg  TEXT;
BEGIN
    SELECT * INTO v_pay FROM payables WHERE id = p_payment_id FOR UPDATE;
    IF NOT FOUND THEN msg := 'Error: Payment not found'; expense_id := NULL; RETURN NEXT; RETURN; END IF;
    IF v_pay.status = 'verified' THEN msg := 'Already verified'; expense_id := NULL; RETURN NEXT; RETURN; END IF;
    IF v_pay.acc_id IS NULL THEN msg := 'Error: No expense account set on this payment row'; expense_id := NULL; RETURN NEXT; RETURN; END IF;
    IF p_tds_pct IS NOT NULL AND (p_tds_pct < 0 OR p_tds_pct > 100) THEN
        msg := 'Error: TDS % must be between 0 and 100'; expense_id := NULL; RETURN NEXT; RETURN;
    END IF;

    -- Cash / cheque limit (bye-laws 46–52). A vendor payment in cash above the
    -- cheque threshold is treated like any other cash disbursement: 'warn' flags
    -- the payment and still posts (so accounts staff can explain it), 'block'
    -- refuses it outright. This closes the hole where fn_verify_payment (vendor
    -- payables, default mode cash) was never passing through fn_check_cash_payment_limit.
    IF p_mode = 'cash' THEN
        v_limit_msg := fn_check_cash_payment_limit(v_pay.society_id, v_pay.amount, p_mode);
        IF v_limit_msg IS NOT NULL THEN
            IF fn_cash_limit_mode(v_pay.society_id) = 'block' THEN
                msg := 'Error: ' || v_limit_msg; expense_id := NULL; RETURN NEXT; RETURN;
            END IF;
            INSERT INTO compliance_flags (society_id, rule_code, source_table, source_id, detail)
            VALUES (v_pay.society_id, 'CASH_PAYMENT_LIMIT', 'payables', v_pay.id, v_limit_msg)
            ON CONFLICT (source_table, source_id, rule_code) DO NOTHING;
        END IF;
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

    INSERT INTO expenses(
        society_id, user_id, entity_id, role,
        expense_date, acc_id, particulars, amount, mode,
        status, confirmed_by, confirmed_at, source_reference, created_at
    ) VALUES (
        v_pay.society_id, p_confirmed_by, v_pay.entity_id, v_pay.role,
        CURRENT_DATE, v_pay.acc_id, v_pay.description, v_pay.amount, p_mode,
        'confirmed', p_confirmed_by, NOW(), NULL, NOW()
    ) RETURNING id INTO v_expense_id;

    UPDATE payables
    SET status       = 'verified',
        confirmed_by = p_confirmed_by,
        confirmed_at = NOW(),
        paid_at      = NOW()
    WHERE id = p_payment_id;

    msg := 'Payment verified — expense #' || v_expense_id::TEXT || ' posted (transaction #' || v_trx_id::TEXT || ')';
    expense_id := v_expense_id;
    RETURN NEXT;
END;
$$;

-- SECTION 6: VENDOR PASS SALE
-- ════════════════════════════════════════════════════════════════

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
        WHERE society_id = v_society_id AND tab_name = 'SocC'
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
        society_id, user_id, pass_type, issued_date, valid_until, status, receipt_id, created_at
    ) VALUES (
        v_society_id, p_user_id, p_pass_type, p_issued_date, v_valid_until, v_status, v_receipt_id, NOW()
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
-- (events.account_id, e.g. "Holi" = 23191 under the
-- "Event Ticket" = 2319 header) + Dr cash/bank paired side —
-- same double-entry shape as fn_sell_vendor_pass, but the
-- income account and per-unit price both come from the event
-- row itself instead of a rate table.
-- ════════════════════════════════════════════════════════════════

-- 2026-08: generalized from apartment-only to apartment/vendor/security so
-- "Buy Tickets" can be opened to every portal. Eligibility is now gated by
-- the event's own open_to column instead of a hardcoded role restriction:
--   'all'            -> apartment, vendor, security
--   'members_only'   -> apartment (society members/owners) only
--   'residents_only' -> apartment + security (on-site residents; vendors
--                        are not residents of the society)
-- Also (Tweak 3): p_cheque_no/p_transaction_id added and written straight
-- into receipts.cheque_no/receipts.transaction_id (columns that already
-- existed) instead of the caller string-concatenating them into
-- particulars as a display-only workaround.
CREATE OR REPLACE FUNCTION fn_sell_event_ticket(
    p_user_id      INT,
    p_event_id     INT,
    p_quantity_adult  INT DEFAULT 0,
    p_quantity_child  INT DEFAULT 0,
    p_mode         VARCHAR DEFAULT 'cash',
    p_created_by   INT DEFAULT NULL,
    p_issued_date  DATE DEFAULT CURRENT_DATE,
    p_particulars  TEXT DEFAULT NULL,
    p_cheque_no       VARCHAR DEFAULT NULL,
    p_transaction_id  VARCHAR DEFAULT NULL
)
RETURNS TABLE(receipt_id INT, ticket_id INT, amount NUMERIC, journal_id INT, status VARCHAR(20))
LANGUAGE plpgsql AS $$
DECLARE
    v_society_id   INT;
    v_role         VARCHAR(20);
    v_entity_id    INT;
    v_buyer_label  VARCHAR;
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

    SELECT society_id, role, linked_id INTO v_society_id, v_role, v_entity_id
    FROM users WHERE id = p_user_id AND role IN ('apartment', 'vendor', 'security');
    IF NOT FOUND THEN RAISE EXCEPTION 'Buyer not found or not eligible to buy tickets'; END IF;

    SELECT e.* INTO v_event FROM events e
    WHERE e.id = p_event_id AND e.society_id = v_society_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Event not found'; END IF;

    IF v_event.open_to = 'members_only' AND v_role <> 'apartment' THEN
        RAISE EXCEPTION 'This event is open to members only';
    ELSIF v_event.open_to = 'residents_only' AND v_role NOT IN ('apartment', 'security') THEN
        RAISE EXCEPTION 'This event is open to residents only';
    END IF;

    IF v_event.event_date < CURRENT_DATE THEN
        RAISE EXCEPTION 'Cannot sell tickets for past events';
    END IF;

    IF v_role = 'apartment' THEN
        SELECT flat_number INTO v_buyer_label FROM apartments WHERE id = v_entity_id;
    ELSIF v_role = 'vendor' THEN
        SELECT business_name INTO v_buyer_label FROM vendors WHERE id = v_entity_id;
    ELSE
        SELECT name INTO v_buyer_label FROM security_staff WHERE id = v_entity_id;
    END IF;

    v_acc_id := v_event.account_id;
    IF v_acc_id IS NULL THEN
        RAISE EXCEPTION 'This event has no ticket account set — tickets cannot be sold for it';
    END IF;

    SELECT (a.tab_name = 'EventT' OR p.tab_name = 'EventT') INTO v_is_ticket_ac
    FROM accounts a
    LEFT JOIN accounts p ON p.society_id = a.society_id AND p.id = a.parent_account_id
    WHERE a.id = v_acc_id AND a.society_id = v_society_id;
    IF v_is_ticket_ac IS NOT TRUE THEN
        RAISE EXCEPTION 'Event''s account is not an Event Ticket (2319) account — tickets cannot be sold for it';
    END IF;

    v_amount := COALESCE(v_event.ticket_price, 0) * COALESCE(p_quantity_adult, 0)
             + COALESCE(v_event.ticket_price2, 0) * COALESCE(p_quantity_child, 0);
    v_total_qty := COALESCE(p_quantity_adult, 0) + COALESCE(p_quantity_child, 0);

    v_desc := COALESCE(p_particulars,
        'Event Ticket x' || v_total_qty || ' - ' || COALESCE(v_event.title,'') ||
        ' - ' || COALESCE(v_buyer_label,''));

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
            cheque_no, transaction_id,
            status, confirmed_by, confirmed_at, source_reference, created_at
        ) VALUES (
            v_society_id, p_user_id, v_entity_id, v_role,
            p_issued_date, v_acc_id, v_desc, v_amount, p_mode,
            p_cheque_no, p_transaction_id,
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
                v_society_id, 'Cr', p_issued_date, v_acc_id, v_entity_id, v_role, v_desc,
                v_amount, p_mode, 'paid', p_created_by, NOW(), 'receipts', v_receipt_id, v_journal_id
            );

            IF v_bank_acc IS NOT NULL THEN
                INSERT INTO transactions(
                    society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                    amount, mode, status, created_by, created_at, source_table, source_id, journal_id
                ) VALUES (
                    v_society_id, 'Dr', p_issued_date, v_bank_acc, v_entity_id, v_role,
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
        v_society_id, p_event_id, p_user_id, COALESCE(p_quantity_adult, 0), COALESCE(p_quantity_child, 0), v_amount, v_receipt_id, p_issued_date, CASE WHEN v_status = 'confirmed' THEN 'active' ELSE 'pending' END, NOW()
    ) RETURNING id INTO v_ticket_id;

    receipt_id := v_receipt_id;
    ticket_id := v_ticket_id;
    amount := v_amount;
    journal_id := v_journal_id;
    status := v_status;
    RETURN NEXT;
END;
$$;

-- fn_verify_event_ticket: Admin verifies a pending event ticket purchase
-- (created by apartment/vendor/security portal) → verifies the associated
-- receipt and updates event_tickets + event_ticket_items to 'active'.
-- ════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_verify_event_ticket(
    p_event_ticket_id INT,
    p_confirmed_by    INT,
    p_mode            VARCHAR DEFAULT NULL
)
RETURNS TABLE(event_ticket_id INT, receipt_id INT, msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_et     event_tickets%ROWTYPE;
    v_rec    receipts%ROWTYPE;
    v_result RECORD;
    v_journal_id INT;
BEGIN
    -- Lock and fetch the event ticket
    SELECT * INTO v_et FROM event_tickets WHERE id = p_event_ticket_id FOR UPDATE;
    IF NOT FOUND THEN
        event_ticket_id := p_event_ticket_id; receipt_id := NULL; msg := 'Error: Event ticket not found'; RETURN NEXT; RETURN;
    END IF;
    
    IF v_et.status = 'active' THEN
        event_ticket_id := p_event_ticket_id; receipt_id := v_et.receipt_id; msg := 'Already verified'; RETURN NEXT; RETURN;
    END IF;
    
    IF v_et.status = 'cancelled' THEN
        event_ticket_id := p_event_ticket_id; receipt_id := v_et.receipt_id; msg := 'Error: Event ticket is cancelled'; RETURN NEXT; RETURN;
    END IF;
    
    -- Verify the associated receipt if exists
    IF v_et.receipt_id IS NOT NULL THEN
        SELECT * INTO v_rec FROM receipts WHERE id = v_et.receipt_id FOR UPDATE;
        IF NOT FOUND THEN
            event_ticket_id := p_event_ticket_id; receipt_id := v_et.receipt_id; msg := 'Error: Associated receipt not found'; RETURN NEXT; RETURN;
        END IF;
        
        IF v_rec.status = 'pending' THEN
            -- Call fn_verify_receipt to post transactions and update receipt
            FOR v_result IN SELECT * FROM fn_verify_receipt(v_et.receipt_id, p_confirmed_by, p_mode) LOOP
                IF v_result.msg LIKE 'Error:%' THEN
                    event_ticket_id := p_event_ticket_id; receipt_id := v_et.receipt_id; msg := v_result.msg; RETURN NEXT; RETURN;
                END IF;
            END LOOP;
        ELSIF v_rec.status = 'cancelled' THEN
            event_ticket_id := p_event_ticket_id; receipt_id := v_et.receipt_id; msg := 'Error: Receipt is cancelled'; RETURN NEXT; RETURN;
        END IF;
    END IF;
    
    -- Update event_tickets to active
    UPDATE event_tickets
    SET status = 'active'
    WHERE id = p_event_ticket_id;
    
    -- Update event_ticket_items to active
    UPDATE event_ticket_items
    SET status = 'active'
    WHERE event_ticket_id = p_event_ticket_id;
    
    event_ticket_id := p_event_ticket_id;
    receipt_id := v_et.receipt_id;
    msg := 'Verified: event ticket #' || p_event_ticket_id::TEXT || ' and ' || COALESCE(v_et.receipt_id, 0)::TEXT || ' items updated to active';
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

CREATE OR REPLACE FUNCTION fn_buy_asset(
    p_society_id        INT,
    p_company_name      VARCHAR,
    p_asset_name        VARCHAR,
    p_asset_sno         VARCHAR,
    p_purchase_value    NUMERIC,
    p_acc_id            INT,
    p_purchase_date     DATE    DEFAULT CURRENT_DATE,
    p_installation_date DATE    DEFAULT NULL,
    p_mode              VARCHAR DEFAULT 'cash',
    p_created_by        INT     DEFAULT NULL,
    p_particulars       TEXT    DEFAULT NULL,
    p_itc_claimed       NUMERIC DEFAULT 0 -- ITC claimed on this purchase, if any (sec. 16 CGST Act) — leave 0 unless a GST tax invoice's ITC was actually claimed
)
RETURNS TABLE(asset_id INT, expense_id INT, transaction_id INT, journal_id INT)
LANGUAGE plpgsql AS $$
DECLARE
    v_asset_id   INT;
    v_expense_id INT;
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

    SELECT depreciation_percent INTO v_dep_rate FROM accounts WHERE id = p_acc_id AND society_id = p_society_id;

    INSERT INTO assets(
        society_id, company_name, asset_name, asset_SNo, purchase_date, installation_date, purchase_value,
        acc_id, depreciation_rate, created_at, itc_claimed
    ) VALUES (
        p_society_id, p_company_name, p_asset_name, p_asset_sno, p_purchase_date, p_installation_date, p_purchase_value,
        p_acc_id, v_dep_rate, NOW(), COALESCE(p_itc_claimed, 0)
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

    INSERT INTO expenses(
        society_id, user_id, entity_id, role,
        expense_date, acc_id, particulars, amount, mode,
        status, confirmed_by, confirmed_at, source_reference, created_at
    ) VALUES (
        p_society_id, p_created_by, v_asset_id, 'assets',
        p_purchase_date, p_acc_id, v_desc, p_purchase_value, p_mode,
        'confirmed', p_created_by, NOW(), NULL, NOW()
    ) RETURNING id INTO v_expense_id;

    RETURN QUERY SELECT v_asset_id, v_expense_id, v_trx_id, v_journal_id;
END;
$$;

-- fn_asset_gst_disposal_liability (2026-09, CA compliance pass)
-- ==============================================
-- Sec. 18(6) CGST Act / Rule 44(6): when capital goods on which ITC was
-- claimed are supplied (sold/disposed), the registered person must pay an
-- amount equal to the HIGHER of:
--   (a) ITC taken on the goods, reduced by 5% per quarter (or part
--       thereof) of use since the date of the invoice, or
--   (b) tax on the transaction value of the supply (sec. 15).
-- This is a separate GST output-tax liability — it does NOT reduce the
-- Income-tax block WDV (that's still just the sale value, per
-- fn_dispose_asset / fn_account_depreciation), and it only applies at
-- all if ITC was actually claimed on the asset (assets.itc_claimed > 0);
-- the vast majority of RWA capital purchases never claim ITC, so this is
-- 0 for them and the disposal is unaffected.
--
-- Quarter count: (days elapsed + 1) / 91, rounded up — any part-quarter
-- counts as a full quarter per the statute's "or part thereof" wording.

CREATE OR REPLACE FUNCTION fn_asset_gst_disposal_liability(
    p_asset_id   INT,
    p_sale_value NUMERIC,
    p_sale_date  DATE
) RETURNS TABLE (liability NUMERIC(15,2), cgst_amount NUMERIC(15,2), sgst_amount NUMERIC(15,2))
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_asset         assets%ROWTYPE;
    v_itc_reversal  NUMERIC(15,2);
    v_tax_on_value  NUMERIC(15,2);
    v_quarters      INT;
    v_cgst_rate     NUMERIC(5,2);
    v_sgst_rate     NUMERIC(5,2);
    v_liability     NUMERIC(15,2);
BEGIN
    SELECT * INTO v_asset FROM assets WHERE id = p_asset_id;
    IF NOT FOUND OR COALESCE(v_asset.itc_claimed, 0) <= 0 THEN
        RETURN QUERY SELECT 0::NUMERIC(15,2), 0::NUMERIC(15,2), 0::NUMERIC(15,2);
        RETURN;
    END IF;

    v_quarters := CEIL((p_sale_date - v_asset.purchase_date + 1) / 91.0);
    v_itc_reversal := GREATEST(v_asset.itc_claimed * (1 - 0.05 * v_quarters), 0);

    SELECT cgst_rate_pct, sgst_rate_pct INTO v_cgst_rate, v_sgst_rate
      FROM gst_rates
     WHERE society_id = v_asset.society_id
       AND effective_from <= p_sale_date
       AND (effective_to IS NULL OR effective_to >= p_sale_date)
     ORDER BY effective_from DESC LIMIT 1;
    v_cgst_rate := COALESCE(v_cgst_rate, 0);
    v_sgst_rate := COALESCE(v_sgst_rate, 0);
    v_tax_on_value := ROUND(p_sale_value * (v_cgst_rate + v_sgst_rate) / 100.0, 2);

    v_liability := GREATEST(v_itc_reversal, v_tax_on_value);

    -- Split the liability CGST:SGST in the same ratio as the current
    -- rates (normally 1:1); if no rate is configured for this society,
    -- the whole liability (from the ITC-reversal branch) still needs
    -- somewhere to go — fall back to a straight 50:50 split rather than
    -- silently dropping half of it.
    IF v_cgst_rate + v_sgst_rate > 0 THEN
        RETURN QUERY SELECT
            v_liability,
            ROUND(v_liability * v_cgst_rate / (v_cgst_rate + v_sgst_rate), 2)::NUMERIC(15,2),
            ROUND(v_liability * v_sgst_rate / (v_cgst_rate + v_sgst_rate), 2)::NUMERIC(15,2);
    ELSE
        RETURN QUERY SELECT
            v_liability,
            ROUND(v_liability / 2, 2)::NUMERIC(15,2),
            ROUND(v_liability / 2, 2)::NUMERIC(15,2);
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION fn_dispose_asset(
    p_asset_id    INT,
    p_sale_value  NUMERIC,
    p_mode        VARCHAR DEFAULT 'cash',
    p_created_by  INT     DEFAULT NULL,
    p_sale_date   DATE    DEFAULT CURRENT_DATE,
    p_particulars TEXT    DEFAULT NULL,
    p_acc_id      INT     DEFAULT NULL,
    p_tds_amount  NUMERIC DEFAULT 0
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
    v_desc       TEXT;
    v_gst         RECORD;
    v_gst_exp_acc INT;
    v_cgst_acc    INT;
    v_sgst_acc    INT;
    v_tds_rec_acc INT;
    v_net_sale    NUMERIC(15,2);
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
        WHERE society_id = v_asset.society_id AND tab_name = 'SellAs'
        LIMIT 1;
    END IF;

    -- Fixed (2026-09, CA compliance pass): this used to compute a
    -- straight-line "book value" per asset and post the gain/loss over
    -- book value to a separate income account. That's individual-asset
    -- accounting, not the Block-of-Assets method the rest of the ledger
    -- (fn_account_depreciation, fn_fixed_asset_register_fy) uses. Under
    -- sec. 43(6)(c) of the Income-tax Act, a disposal simply reduces the
    -- BLOCK by the actual moneys payable (sale value) — there is no
    -- per-asset gain/loss to recognise at the time of sale; any excess of
    -- deductions over the block's WDV becomes sec. 50 short-term capital
    -- gain, computed at the block/FY level (see fn_account_depreciation
    -- and fn_fixed_asset_register_fy), not per-transaction here.
    v_desc := COALESCE(p_particulars, 'Asset Sale - ' || v_asset.asset_name);
    v_bank_acc := fn_resolve_bank_leg(v_asset.society_id, p_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    v_net_sale := p_sale_value - COALESCE(p_tds_amount, 0);
    IF v_net_sale < 0 THEN RAISE EXCEPTION 'TDS amount cannot exceed sale value'; END IF;

    -- Dr: TDS Receivable
    IF COALESCE(p_tds_amount, 0) > 0 THEN
        SELECT id INTO v_tds_rec_acc FROM accounts
        WHERE society_id = v_asset.society_id AND tab_name = 'TDSRec' -- returns null
        LIMIT 1;

        IF v_tds_rec_acc IS NULL THEN
            RAISE EXCEPTION 'Cannot apply TDS: No TDS Receivable account configured for this society. Please set one in Settings > Accounts.';
        END IF;

        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_asset.society_id, 'Dr', p_sale_date, v_tds_rec_acc, p_asset_id, 'assets',
            'TDS Deducted on Asset Sale - ' || v_asset.asset_name,
            p_tds_amount, 'journal', 'paid', p_created_by, NOW(), 'assets', p_asset_id, v_journal_id
        );
    END IF;

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
    IF v_bank_acc IS NOT NULL AND v_net_sale > 0 THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_asset.society_id, 'Dr', p_sale_date, v_bank_acc, p_asset_id, 'assets',
            'Cash received - ' || v_desc,
            v_net_sale, p_mode, 'paid', p_created_by, NOW(), 'assets', p_asset_id, v_journal_id
        );
    END IF;

    -- Cr: asset class (block) account, for the FULL sale value — this is
    -- the "deductions" leg fn_account_depreciation / fn_fixed_asset_register_fy
    -- read back as moneys payable reducing the block, per sec. 43(6)(c).
    -- No separate gain/loss leg: the block method has none at this stage.
    INSERT INTO transactions(
        society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id, journal_id
    ) VALUES (
        v_asset.society_id, 'Cr', p_sale_date, v_asset.acc_id, p_asset_id, 'assets',
        'Asset disposed (moneys payable) - ' || v_asset.asset_name,
        p_sale_value, p_mode, 'paid', p_created_by, NOW(), 'assets', p_asset_id, v_journal_id
    ) RETURNING id INTO v_trx_id;

    -- sec. 18(6) CGST Act / Rule 44(6): if ITC was ever claimed on this
    -- asset, disposal triggers a separate GST output-tax liability (the
    -- higher of ITC-reversal or tax on transaction value — see
    -- fn_asset_gst_disposal_liability). This is independent of the
    -- Income-tax block reduction above; it's booked as Dr the disposal's
    -- GST cost, Cr CGST/SGST Payable. Skipped (with a WARNING) if the
    -- society hasn't set up a "GST on Asset Disposal" expense account —
    -- same defensive, name-resolved-account convention used everywhere
    -- else in this file (fn_resolve_depreciation_account etc.) — the
    -- liability is still recorded on the assets row either way so it's
    -- never silently lost from the audit trail/FAR export.
    SELECT * INTO v_gst FROM fn_asset_gst_disposal_liability(p_asset_id, p_sale_value, p_sale_date);
    IF v_gst.liability > 0 THEN
        SELECT id INTO v_gst_exp_acc FROM accounts
        WHERE society_id = v_asset.society_id AND tab_name = 'GSTDisp'
        LIMIT 1;
        SELECT id INTO v_cgst_acc FROM accounts
        WHERE society_id = v_asset.society_id AND tab_name = 'CGST'
        LIMIT 1;
        SELECT id INTO v_sgst_acc FROM accounts
        WHERE society_id = v_asset.society_id AND tab_name = 'SGST'
        LIMIT 1;

        IF v_gst_exp_acc IS NOT NULL THEN
            INSERT INTO transactions(
                society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id, journal_id
            ) VALUES (
                v_asset.society_id, 'Dr', p_sale_date, v_gst_exp_acc, p_asset_id, 'assets',
                'GST on disposal (sec 18(6)/Rule 44(6)) - ' || v_asset.asset_name,
                v_gst.liability, p_mode, 'paid', p_created_by, NOW(), 'assets', p_asset_id, v_journal_id
            );
            IF v_cgst_acc IS NOT NULL AND v_gst.cgst_amount > 0 THEN
                INSERT INTO transactions(
                    society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                    amount, mode, status, created_by, created_at, source_table, source_id, journal_id
                ) VALUES (
                    v_asset.society_id, 'Cr', p_sale_date, v_cgst_acc, p_asset_id, 'assets',
                    'CGST on disposal - ' || v_asset.asset_name,
                    v_gst.cgst_amount, p_mode, 'paid', p_created_by, NOW(), 'assets', p_asset_id, v_journal_id
                );
            END IF;
            IF v_sgst_acc IS NOT NULL AND v_gst.sgst_amount > 0 THEN
                INSERT INTO transactions(
                    society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                    amount, mode, status, created_by, created_at, source_table, source_id, journal_id
                ) VALUES (
                    v_asset.society_id, 'Cr', p_sale_date, v_sgst_acc, p_asset_id, 'assets',
                    'SGST on disposal - ' || v_asset.asset_name,
                    v_gst.sgst_amount, p_mode, 'paid', p_created_by, NOW(), 'assets', p_asset_id, v_journal_id
                );
            END IF;
        ELSE
            RAISE WARNING 'Asset % disposal has a GST liability of % (sec 18(6)/Rule 44(6)) but no "GST on Asset Disposal" account exists for society % — liability recorded on the asset row but NOT posted to the ledger. Add that account and post it manually.',
                p_asset_id, v_gst.liability, v_asset.society_id;
        END IF;
    END IF;

    -- Create receipt for the asset sale proceeds
    INSERT INTO receipts(
        society_id, user_id, entity_id, role,
        receipt_date, acc_id, particulars, amount, mode,
        status, confirmed_by, confirmed_at, source_reference, created_at, created_by
    ) VALUES (
        v_asset.society_id, p_created_by, p_asset_id, 'assets',
        p_sale_date, v_acc_id, v_desc, p_sale_value, p_mode,
        'confirmed', p_created_by, NOW(), NULL, NOW(), p_created_by
    ) RETURNING id INTO v_receipt_id;

    UPDATE assets
    SET disposed    = TRUE,
        disposed_at = p_sale_date,
        sale_value  = p_sale_value,
        sale_acc_id = v_acc_id,
        disposed_by = p_created_by,
        gst_disposal_liability = v_gst.liability
    WHERE id = p_asset_id;

    RETURN QUERY SELECT v_receipt_id, v_trx_id, v_journal_id;
END;
$$;

-- SECTION 8: MANUAL RECEIPT / EXPENSE SAVE HELPER (double-entry)
-- ════════════════════════════════════════════════════════════════

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
RETURNS TABLE(receipt_id INT, transaction_id INT, journal_id INT, status VARCHAR(20), cash_warning TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_receipt_id INT;
    v_trx_id     INT;
    v_journal_id INT;
    v_bank_acc   INT;
    v_drcr       VARCHAR(2);
    v_is_admin   BOOLEAN;
    v_status     VARCHAR(20);
    v_cash_warning TEXT;
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN RAISE EXCEPTION 'Amount must be > 0'; END IF;
    IF p_acc_id IS NULL THEN RAISE EXCEPTION 'acc_id is required'; END IF;
    IF p_particulars IS NULL OR TRIM(p_particulars) = '' THEN RAISE EXCEPTION 'particulars is required'; END IF;

    -- Cash transaction warnings (P1 Item 1)
    -- Sec 40A(3): Cash expenses > 10,000 not deductible
    -- Sec 269SS/269T: Cash loans/deposits/repayments > 20,000 attract penalty = amount
    IF p_mode = 'cash' AND p_amount >= 10000 THEN
        v_cash_warning := 'Cash receipt ≥ ₹10,000 — may attract Sec 40A(3) disallowance if treated as expense. ';
        IF p_amount >= 20000 THEN
            v_cash_warning := v_cash_warning || 'Cash receipt ≥ ₹20,000 — Sec 269SS/269T may apply for loan/deposit transactions (penalty = amount).';
        END IF;
    ELSE
        v_cash_warning := NULL;
    END IF;

    SELECT drcr_account INTO v_drcr FROM accounts WHERE id = p_acc_id AND society_id = p_society_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Account % not found for this society', p_acc_id; END IF;
    IF v_drcr = 'Dr' THEN
        RAISE EXCEPTION 'Account % is a Dr (expense) account — use fn_save_expense for expenses', p_acc_id;
    END IF;

    -- SECURITY FIX: Verify entity_id belongs to p_society_id to prevent cross-tenant IDOR
    IF p_entity_id IS NOT NULL THEN
        IF p_role = 'apartment' AND NOT EXISTS (SELECT 1 FROM apartments WHERE id = p_entity_id AND society_id = p_society_id) THEN
            RAISE EXCEPTION 'Entity ID % is not a valid apartment in society %', p_entity_id, p_society_id;
        ELSIF p_role = 'vendor' AND NOT EXISTS (SELECT 1 FROM vendors WHERE id = p_entity_id AND society_id = p_society_id) THEN
            RAISE EXCEPTION 'Entity ID % is not a valid vendor in society %', p_entity_id, p_society_id;
        ELSIF p_role = 'security' AND NOT EXISTS (SELECT 1 FROM security_staff WHERE id = p_entity_id AND society_id = p_society_id) THEN
            RAISE EXCEPTION 'Entity ID % is not valid security staff in society %', p_entity_id, p_society_id;
        ELSIF p_role = 'assets' AND NOT EXISTS (SELECT 1 FROM assets WHERE id = p_entity_id AND society_id = p_society_id) THEN
            RAISE EXCEPTION 'Entity ID % is not a valid asset in society %', p_entity_id, p_society_id;
        END IF;
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
        -- Pass p_acc_id (the receipt's fund/income account) so a
        -- fund-specific bank mapping can apply — see fn_resolve_bank_leg.
        -- This is how a manual Corpus Fund receipt (builder handover,
        -- donation, GB-approved levy) can land directly in a dedicated
        -- Corpus bank account instead of the society-wide primary one.
        v_bank_acc := fn_resolve_bank_leg(p_society_id, p_mode, p_acc_id);
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
    cash_warning := v_cash_warning;

    RETURN NEXT;
END;
$$;

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
    p_tds_section      VARCHAR DEFAULT NULL,
    p_rcm_applicable   BOOLEAN DEFAULT FALSE,
    p_rcm_category     VARCHAR DEFAULT NULL
)
RETURNS TABLE(expense_id INT, transaction_id INT, journal_id INT, status VARCHAR(20), cash_warning TEXT)
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
    v_cash_warning TEXT;
    v_rcm_cgst   NUMERIC(15,2) := 0;
    v_rcm_sgst   NUMERIC(15,2) := 0;
    v_rcm_igst   NUMERIC(15,2) := 0;
    v_rcm_itc_eligible BOOLEAN := FALSE;
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN RAISE EXCEPTION 'Amount must be > 0'; END IF;
    IF p_acc_id IS NULL THEN RAISE EXCEPTION 'acc_id is required'; END IF;
    IF p_particulars IS NULL OR TRIM(p_particulars) = '' THEN RAISE EXCEPTION 'particulars is required'; END IF;
    IF p_tds_pct IS NOT NULL AND (p_tds_pct < 0 OR p_tds_pct > 100) THEN
        RAISE EXCEPTION 'TDS %% must be between 0 and 100';
    END IF;

    -- Cash transaction warnings (P1 Item 1)
    -- Sec 40A(3): Cash expenses > 10,000 not deductible
    -- Sec 269SS/269T: Cash loans/deposits/repayments > 20,000 attract penalty = amount
    IF p_mode = 'cash' AND p_amount >= 10000 THEN
        v_cash_warning := 'Cash expense ≥ ₹10,000 — Sec 40A(3) disallows as tax deduction. ';
        IF p_amount >= 20000 THEN
            v_cash_warning := v_cash_warning || 'Cash expense ≥ ₹20,000 — Sec 269SS/269T may apply for loan/deposit/repayment transactions (penalty = amount).';
        END IF;
    ELSE
        v_cash_warning := NULL;
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
        source_reference, created_at, tds_pct, tds_section,
        rcm_applicable, rcm_category
    ) VALUES (
        p_society_id, p_created_by, p_entity_id, p_role, p_expense_date, p_acc_id, p_particulars,
        p_amount, p_mode, p_cheque_no, p_trx_id, v_status,
        CASE WHEN v_status = 'confirmed' THEN p_created_by ELSE NULL END,
        CASE WHEN v_status = 'confirmed' THEN NOW() ELSE NULL END,
        p_source_reference, NOW(), p_tds_pct, p_tds_section,
        p_rcm_applicable, p_rcm_category
    ) RETURNING id INTO v_expense_id;
 
    IF v_status = 'confirmed' THEN
        v_bank_acc := fn_resolve_bank_leg(p_society_id, p_mode);
        v_journal_id := NEXTVAL('seq_transaction_number');
 
        -- Resolve TDS only if a percentage was actually asked for and the
        -- society has a TDS account configured. Anything else falls
        -- through to the pre-existing single-leg behavior.
        IF COALESCE(p_tds_pct, 0) > 0 THEN
            v_tds_acc := fn_resolve_tds_account(p_society_id);
            IF v_tds_acc IS NULL THEN
                RAISE EXCEPTION 'Cannot apply TDS: No TDS Payable account configured for this society. Please set one in Settings > Accounts.';
            END IF;
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

        -- RCM: self-invoiced GST liability on payments to unregistered parties
        IF p_rcm_applicable THEN
            v_rcm_cgst := 0;
            v_rcm_sgst := 0;
            v_rcm_igst := 0;
            v_rcm_itc_eligible := FALSE;
            SELECT COALESCE(rcm.cgst_amount, 0), COALESCE(rcm.sgst_amount, 0),
                   COALESCE(rcm.igst_amount, 0), COALESCE(rcm.itc_eligible, FALSE)
              INTO v_rcm_cgst, v_rcm_sgst, v_rcm_igst, v_rcm_itc_eligible
              FROM fn_compute_rcm_liability(p_society_id, v_expense_id) AS rcm;
            IF v_rcm_cgst > 0 OR v_rcm_sgst > 0 OR v_rcm_igst > 0 THEN
                PERFORM fn_post_rcm_liability(p_society_id, v_expense_id, v_rcm_cgst, v_rcm_sgst, v_rcm_igst, v_rcm_itc_eligible);
            END IF;
        END IF;
    ELSE
        v_trx_id := NULL;
        v_journal_id := NULL;
    END IF;
 
status := v_status;
    expense_id := v_expense_id;
    transaction_id := v_trx_id;
    journal_id := v_journal_id;
    cash_warning := v_cash_warning;

    RETURN NEXT;
END;
$$;

-- ═════════════════════════════════════════════════════════════════════════
-- FUND UTILIZATION — admin-only withdrawal from Capital/Reserve/Sinking/Repair/Corpus funds
-- Per UP AOA 2010 / Model Bye-Laws:
--   - Capital Account (3000): Share subscriptions, entrance fees → Capital expenditure, loan repayment (General Body)
--   - Reserve Fund (3200): 25% surplus, entrance fees, common profits → Unforeseen expenses (General Body)
--   - Sinking Fund (3210): Member contributions → Major structural repairs, lift/DG replacement (General Body)
--   - Repair & Maintenance Fund (3220): Member contributions → Routine common area maintenance (Managing Committee)
--   - Corpus Fund (3230): Builder handover (RERA) → ONLY INTEREST usable, principal inviolable (General Body)
--
-- STATUTORY PRINCIPAL LOCK (2026-09): the Corpus Fund line above used to be
-- documentation only. This function would happily Dr the builder-handover
-- principal out of account 3230, which is exactly what UP RERA and the Model
-- Bye-Laws forbid. The rule now lives in data, as accounts.statutory_lock_pct
-- (100 on the Corpus account), and is enforced below against the drawable
-- balance rather than the raw balance.
--
-- Expressed as a percentage of the *current* balance rather than an absolute
-- amount, so a Corpus Fund that keeps accruing stays fully locked instead of
-- quietly becoming drawable pound-for-pound. The unlocked headroom is the
-- interest earned on the corpus, which lands in Interest Income (a Cr income
-- account) rather than in the corpus account itself — so in the seeded chart
-- a fully-locked corpus correctly reports zero headroom and the admin is
-- pointed at the interest income instead.
--
-- Both available_amount and locked_amount are returned, so the Fund Management
-- card can show the restriction before the admin types an amount, instead of
-- only rejecting it after.
-- ═════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_process_fund_utilization(
    p_society_id       INT,
    p_fund_acc_id      INT,      -- fund ledger account (3000, 3200, 3210, 3220, 3230)
    p_expense_acc_id   INT,      -- expense/bank account to debit
    p_particulars      TEXT,
    p_amount           NUMERIC,
    p_mode             VARCHAR  DEFAULT 'bank',
    p_created_by       INT      DEFAULT NULL,
    p_cheque_no        VARCHAR  DEFAULT NULL,
    p_trx_id           VARCHAR  DEFAULT NULL,
    p_approval_ref     VARCHAR  DEFAULT NULL, -- GB/MC resolution reference
    p_approval_date    DATE     DEFAULT NULL
)
RETURNS TABLE(
    utilization_id INT,
    transaction_id INT,
    journal_id     INT,
    status         VARCHAR(20),
    available_amount NUMERIC(15,2),  -- balance net of the statutory principal lock
    locked_amount    NUMERIC(15,2)   -- portion of the balance the law protects
)
LANGUAGE plpgsql AS $$
DECLARE
    v_utilization_id INT;
    v_trx_id         INT;
    v_journal_id     INT;
    v_drcr_fund      VARCHAR(2);
    v_drcr_expense   VARCHAR(2);
    v_fund_name      TEXT;
    v_expense_name   TEXT;
    v_is_admin       BOOLEAN;
    v_status         VARCHAR(20);
    v_prev_hash      VARCHAR(64);
    v_lock_pct       NUMERIC(5,2);
    v_fund_balance   NUMERIC(15,2);
    v_locked         NUMERIC(15,2);
    v_available      NUMERIC(15,2);
BEGIN
    -- Validate amount
    IF p_amount IS NULL OR p_amount <= 0 THEN RAISE EXCEPTION 'Amount must be > 0'; END IF;
    IF p_fund_acc_id IS NULL THEN RAISE EXCEPTION 'Fund account (fund_acc_id) is required'; END IF;
    IF p_expense_acc_id IS NULL THEN RAISE EXCEPTION 'Expense account (expense_acc_id) is required'; END IF;
    IF p_particulars IS NULL OR TRIM(p_particulars) = '' THEN RAISE EXCEPTION 'Particulars is required'; END IF;

    -- Validate fund account exists and is a Cr (liability/equity) account
    SELECT drcr_account, name, COALESCE(statutory_lock_pct, 0)
      INTO v_drcr_fund, v_fund_name, v_lock_pct
    FROM accounts WHERE id = p_fund_acc_id AND society_id = p_society_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Fund account % not found for this society', p_fund_acc_id; END IF;
    IF v_drcr_fund != 'Cr' THEN
        RAISE EXCEPTION 'Fund account % (%) must be a Cr (liability/equity) account', p_fund_acc_id, v_fund_name;
    END IF;

    -- Validate expense account exists and is a Dr (expense/asset) account
    SELECT drcr_account, name INTO v_drcr_expense, v_expense_name
    FROM accounts WHERE id = p_expense_acc_id AND society_id = p_society_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Expense account % not found for this society', p_expense_acc_id; END IF;
    IF v_drcr_expense != 'Dr' THEN
        RAISE EXCEPTION 'Expense account % (%) must be a Dr (expense/asset) account', p_expense_acc_id, v_expense_name;
    END IF;

    -- Fund balance (Cr normal = positive balance = credit balance).
    -- Fund accounts are Cr-normal, so positive balance = credit balance.
    --
    -- Two separate limits are enforced, and the statutory one is checked
    -- FIRST so a locked fund reports the reason it is locked rather than a
    -- bare "insufficient balance" that reads like an accounting error:
    --   1. statutory_lock_pct of the balance is law-protected principal
    --      (Corpus Fund: builder handover, UP RERA / Model Bye-Laws Ch.VII)
    --   2. whatever headroom remains must still cover the request
    SELECT COALESCE(SUM(
        CASE WHEN entry_side = 'Cr' THEN amount ELSE -amount END
    ), 0) INTO v_fund_balance
    FROM transactions
    WHERE society_id = p_society_id AND acc_id = p_fund_acc_id;

    v_locked := ROUND(v_fund_balance * v_lock_pct / 100, 2);
    -- GREATEST guards against a negative balance (an overdrawn fund) making
    -- the headroom larger than the balance itself.
    v_available := GREATEST(v_fund_balance - v_locked, 0);

    IF p_amount > v_available THEN
        IF v_lock_pct > 0 THEN
            RAISE EXCEPTION
                'Fund % (%) is protected: % of its balance (₹%, of ₹%) is statutory principal that cannot be drawn down. Drawable: ₹%, Requested: ₹%. The interest earned on this fund is usable via the Interest Income account instead.',
                v_fund_name, p_fund_acc_id, v_lock_pct, v_locked, v_fund_balance,
                v_available, p_amount;
        END IF;
        RAISE EXCEPTION 'Insufficient balance in fund % (%). Available: ₹%, Requested: ₹%',
            v_fund_name, p_fund_acc_id, v_available, p_amount;
    END IF;

    -- Only admins can confirm immediately; others go to pending
    SELECT (role = 'admin' OR is_master_admin) INTO v_is_admin
    FROM users WHERE id = p_created_by;

    IF v_is_admin THEN
        v_status := 'confirmed';
    ELSE
        v_status := 'pending';
    END IF;

    -- Get previous hash for audit trail
    SELECT previous_hash INTO v_prev_hash
    FROM fund_utilizations
    WHERE society_id = p_society_id
    ORDER BY created_at DESC LIMIT 1;

    -- Insert fund_utilization record
    INSERT INTO fund_utilizations (
        society_id, user_id, fund_acc_id, expense_acc_id, particulars,
        amount, mode, cheque_no, transaction_id, approval_ref, approval_date,
        status, confirmed_by, confirmed_at, previous_hash, created_at
    ) VALUES (
        p_society_id, p_created_by, p_fund_acc_id, p_expense_acc_id, p_particulars,
        p_amount, p_mode, p_cheque_no, p_trx_id, p_approval_ref, p_approval_date,
        v_status,
        CASE WHEN v_status = 'confirmed' THEN p_created_by ELSE NULL END,
        CASE WHEN v_status = 'confirmed' THEN NOW() ELSE NULL END,
        v_prev_hash, NOW()
    ) RETURNING id INTO v_utilization_id;

    IF v_status = 'confirmed' THEN
        v_journal_id := NEXTVAL('seq_transaction_number');

        -- Post journal entries:
        -- 1. Dr Fund Account (reduce fund balance - Cr account, so Dr reduces it)
        -- 2. Cr Expense/Bank Account (increase expense or reduce bank)
        --
        -- trx_date / acc_particulars / source_table are the real column
        -- names. This previously wrote `particulars`, `entity_type` and
        -- omitted `trx_date` entirely — none of which exist on
        -- `transactions` (its columns are acc_particulars, source_table and
        -- a NOT NULL trx_date, per the CREATE TABLE at ~line 1124). The
        -- INSERT therefore raised "column \"particulars\" does not exist" on
        -- every confirmed utilization, so the *only* code path that
        -- actually moves money out of a fund had never successfully run —
        -- and no test caught it, because test/fake_db.py has no
        -- `_fn_process_fund_utilization` handler, so the call silently
        -- returned None (see _handle_function's `return None`).
        -- mode is taken from the caller (p_mode), NOT hardcoded to 'journal':
        -- this is a real money movement out to a bank/expense, unlike the
        -- depreciation and reserve-appropriation journals which are pure
        -- book entries.
        INSERT INTO transactions (
            society_id, journal_id, acc_id, entry_side, trx_date, amount,
            acc_particulars, mode, status, source_table, source_id, created_by
        ) VALUES (
            p_society_id, v_journal_id, p_fund_acc_id, 'Dr', CURRENT_DATE, p_amount,
            p_particulars, p_mode, 'paid', 'fund_utilization', v_utilization_id, p_created_by
        );

        INSERT INTO transactions (
            society_id, journal_id, acc_id, entry_side, trx_date, amount,
            acc_particulars, mode, status, source_table, source_id, created_by
        ) VALUES (
            p_society_id, v_journal_id, p_expense_acc_id, 'Cr', CURRENT_DATE, p_amount,
            p_particulars, p_mode, 'paid', 'fund_utilization', v_utilization_id, p_created_by
        );
    END IF;

    utilization_id := v_utilization_id;
    transaction_id := v_trx_id;
    journal_id := v_journal_id;
    status := v_status;
    available_amount := v_available;
    locked_amount := v_locked;

    RETURN NEXT;
END;
$$;

-- fn_set_fund_bank_mapping (2026-09, fund management audit follow-up)
-- ======================================================================
-- Admin-facing upsert for fund_bank_account_map. Validates both accounts
-- belong to the calling society and have the right Dr/Cr nature (mirrors
-- the same validation shape as fn_process_fund_utilization above) so a bad
-- mapping can't be saved from the UI layer, whatever calls this.
-- p_bank_acc_id = NULL clears the mapping for that fund (reverts it to
-- primary_bank_account_id).

-- OUT columns are prefixed out_* (rather than fund_acc_id/bank_acc_id) —
-- names matching fund_bank_account_map's own columns made the ON CONFLICT
-- target list below ambiguous (PL/pgSQL variable vs. table column) since
-- Postgres won't accept a table-qualified column in a conflict target.
CREATE OR REPLACE FUNCTION fn_set_fund_bank_mapping(
    p_society_id  INT,
    p_fund_acc_id INT,
    p_bank_acc_id INT,      -- NULL clears the mapping
    p_updated_by  INT DEFAULT NULL
)
RETURNS TABLE(out_fund_acc_id INT, out_bank_acc_id INT, msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_drcr_fund VARCHAR(2);
    v_fund_name TEXT;
    v_drcr_bank VARCHAR(2);
    v_bank_name TEXT;
    v_is_admin  BOOLEAN;
BEGIN
    IF p_fund_acc_id IS NULL THEN RAISE EXCEPTION 'Fund account is required'; END IF;

    -- The acting user is looked up INSIDE p_society_id, not just by id. The
    -- earlier version matched on users.id alone, so an admin of society A
    -- could set a fund-bank mapping on society B by passing its id — the
    -- accounts are validated against p_society_id, but the AUTHORIZATION
    -- was not. Master admins and unassigned (seeded first-admin) users carry
    -- a NULL society_id, so they stay allowed; anyone else whose society_id
    -- disagrees is simply "not found" here and gets the same refusal as a
    -- non-admin.
    SELECT (u.role = 'admin' OR u.is_master_admin) INTO v_is_admin
    FROM users u
    WHERE u.id = p_updated_by
      AND (u.is_master_admin OR u.society_id IS NULL OR u.society_id = p_society_id);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Only an admin of this society can change fund-bank account mapping';
    END IF;
    IF NOT COALESCE(v_is_admin, FALSE) THEN
        RAISE EXCEPTION 'Only an admin can change fund-bank account mapping';
    END IF;

    SELECT drcr_account, name INTO v_drcr_fund, v_fund_name
    FROM accounts WHERE id = p_fund_acc_id AND society_id = p_society_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Fund account % not found for this society', p_fund_acc_id; END IF;
    -- IS DISTINCT FROM, not !=: accounts.drcr_account is NULLABLE (the
    -- rollup "Balance Sheet Root" has no Dr/Cr nature), and `NULL != 'Cr'`
    -- evaluates to NULL rather than TRUE, so a plain `!=` guard lets every
    -- null-natured account straight through the validation.
    IF v_drcr_fund IS DISTINCT FROM 'Cr' THEN
        RAISE EXCEPTION 'Account % (%) must be a Cr (equity/reserve) fund account', p_fund_acc_id, v_fund_name;
    END IF;

    IF p_bank_acc_id IS NULL THEN
        DELETE FROM fund_bank_account_map
        WHERE society_id = p_society_id AND fund_acc_id = p_fund_acc_id;

        out_fund_acc_id := p_fund_acc_id;
        out_bank_acc_id := NULL;
        msg := format('%s now uses the primary bank account', v_fund_name);
        RETURN NEXT;
        RETURN;
    END IF;

    -- A fund mapped to itself would be a silent no-op that still reports
    -- success (the Cr-nature check above already rules out the Dr/Cr pair,
    -- but an explicit check keeps the invariant local and self-evident).
    IF p_bank_acc_id = p_fund_acc_id THEN
        RAISE EXCEPTION 'A fund cannot be mapped to its own account';
    END IF;

    SELECT drcr_account, name INTO v_drcr_bank, v_bank_name
    FROM accounts WHERE id = p_bank_acc_id AND society_id = p_society_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Bank account % not found for this society', p_bank_acc_id; END IF;
    IF v_drcr_bank IS DISTINCT FROM 'Dr' THEN
        RAISE EXCEPTION 'Account % (%) must be a Dr (bank/asset) account', p_bank_acc_id, v_bank_name;
    END IF;

    INSERT INTO fund_bank_account_map (society_id, fund_acc_id, bank_acc_id, updated_by, updated_at)
    VALUES (p_society_id, p_fund_acc_id, p_bank_acc_id, p_updated_by, NOW())
    ON CONFLICT (society_id, fund_acc_id)
    DO UPDATE SET bank_acc_id = EXCLUDED.bank_acc_id,
                  updated_by  = EXCLUDED.updated_by,
                  updated_at  = NOW();

    out_fund_acc_id := p_fund_acc_id;
    out_bank_acc_id := p_bank_acc_id;
    msg := format('%s contributions will now be deposited into %s', v_fund_name, v_bank_name);
    RETURN NEXT;
END;
$$;

-- fn_appropriate_income_to_fund (2026-09, fund management audit follow-up)
-- ======================================================================
-- Ad-hoc Dr Income / Cr Fund journal — e.g. moving Corpus Fund's interest
-- (credited to Interest Income, since Corpus's principal is 100% statutory-
-- locked — see fn_process_fund_utilization's lock-breach message) into
-- Repair & Maintenance Fund Reserve or Sinking Fund Reserve.
--
-- fn_process_fund_utilization cannot do this: it requires the debit leg to
-- be Dr-natured (expense/asset), and an income account is Cr-natured, so it
-- raises 'must be a Dr (expense/asset) account' on exactly this case. This
-- function is fn_process_fund_utilization's mirror image — Cr-natured on
-- BOTH legs (Dr reduces the income account's Cr-positive balance, Cr raises
-- the fund's) — mode is always 'journal' since no real cash/bank moves; the
-- money already sits in the society's bank account from whenever the
-- interest was originally credited.
--
-- Balance check is over the account's whole SUBTREE, not the account row
-- alone. This is the difference between the function working and not: the
-- account an admin actually picks for "Corpus Fund interest" is the rollup
-- "Interest Income" (4110), which has no transactions of its own — bank
-- interest is credited to its 4111 child, FD interest to 4112, and so on.
-- The earlier account-only SUM therefore always returned 0 and every
-- attempt died with "Insufficient balance ... Available: ₹0" no matter how
-- much interest the society had actually earned. Summing the subtree
-- matches how the reports already present a header's balance (the trial
-- balance rolls each parent's own movement up on top of its children), so
-- the check and the resulting statement agree.

CREATE OR REPLACE FUNCTION fn_appropriate_income_to_fund(
    p_society_id       INT,
    p_income_acc_id    INT,      -- Cr-natured income account (or header), e.g. Interest Income
    p_fund_acc_id      INT,      -- Cr-natured fund/equity account to top up
    p_particulars      TEXT,
    p_amount           NUMERIC,
    p_created_by       INT      DEFAULT NULL,
    p_approval_ref     VARCHAR  DEFAULT NULL, -- GB/MC resolution reference
    p_approval_date    DATE     DEFAULT NULL
)
RETURNS TABLE(
    appropriation_id INT,
    journal_id       INT,
    status           VARCHAR(20)
)
LANGUAGE plpgsql AS $$
#variable_conflict use_column
-- The OUT parameters (appropriation_id / journal_id / status) collide by name
-- with fund_appropriations' own columns of the same name; the pragma pins
-- ambiguous references to the column, the same defensive measure
-- fn_funds_account_fy below takes for its own OUT/column overlap.
DECLARE
    v_appropriation_id INT;
    v_journal_id       INT;
    v_drcr_income      VARCHAR(2);
    v_drcr_fund        VARCHAR(2);
    v_income_name      TEXT;
    v_fund_name        TEXT;
    v_is_admin         BOOLEAN;
    v_status           VARCHAR(20);
    v_prev_hash        VARCHAR(64);
    v_income_balance   NUMERIC(15,2);
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN RAISE EXCEPTION 'Amount must be > 0'; END IF;
    IF p_income_acc_id IS NULL THEN RAISE EXCEPTION 'Income account is required'; END IF;
    IF p_fund_acc_id IS NULL THEN RAISE EXCEPTION 'Fund account is required'; END IF;
    IF p_particulars IS NULL OR TRIM(p_particulars) = '' THEN RAISE EXCEPTION 'Particulars is required'; END IF;
    IF p_income_acc_id = p_fund_acc_id THEN RAISE EXCEPTION 'Source and destination accounts must differ'; END IF;

    SELECT drcr_account, name INTO v_drcr_income, v_income_name
    FROM accounts WHERE id = p_income_acc_id AND society_id = p_society_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Income account % not found for this society', p_income_acc_id; END IF;
    -- IS DISTINCT FROM, not !=: accounts.dcr_account is NULLABLE, and
    -- `NULL != 'Cr'` is NULL rather than TRUE, so `!=` silently admits any
    -- null-natured (rollup) account through this guard.
    IF v_drcr_income IS DISTINCT FROM 'Cr' THEN
        RAISE EXCEPTION 'Account % (%) must be a Cr-natured income account to appropriate FROM', p_income_acc_id, v_income_name;
    END IF;

    SELECT drcr_account, name INTO v_drcr_fund, v_fund_name
    FROM accounts WHERE id = p_fund_acc_id AND society_id = p_society_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Fund account % not found for this society', p_fund_acc_id; END IF;
    IF v_drcr_fund IS DISTINCT FROM 'Cr' THEN
        RAISE EXCEPTION 'Fund account % (%) must be a Cr (equity/reserve) account', p_fund_acc_id, v_fund_name;
    END IF;

    -- Can't appropriate more income than has actually accrued — mirrors
    -- fn_process_fund_utilization's balance check, but over the income
    -- account's entire subtree (see the note above the CREATE: "Interest
    -- Income" 4110 is a header whose children 4111/4112/4113 carry the
    -- actual postings, so an account-only SUM is always 0).
    WITH RECURSIVE income_subtree AS (
        SELECT a.id
          FROM accounts a
         WHERE a.society_id = p_society_id AND a.id = p_income_acc_id
        UNION ALL
        SELECT c.id
          FROM accounts c
          JOIN income_subtree s ON c.parent_account_id = s.id
         WHERE c.society_id = p_society_id
    )
    SELECT COALESCE(SUM(
        CASE WHEN t.entry_side = 'Cr' THEN t.amount ELSE -t.amount END
    ), 0) INTO v_income_balance
    FROM transactions t
    WHERE t.society_id = p_society_id
      AND t.acc_id IN (SELECT id FROM income_subtree);

    IF p_amount > v_income_balance THEN
        RAISE EXCEPTION 'Insufficient unappropriated income in % (%). Available: ₹%, Requested: ₹%',
            v_income_name, p_income_acc_id, v_income_balance, p_amount;
    END IF;

    -- Society-scoped authorization. A NULL p_created_by is treated as
    -- "not an admin" and lands on the pending path below, so the Dr/Cr
    -- journal is only ever written by a verified admin of THIS society —
    -- previously a user id alone was enough, and an admin of another
    -- society could post into this one.
    SELECT (u.role = 'admin' OR u.is_master_admin) INTO v_is_admin
    FROM users u
    WHERE u.id = p_created_by
      AND (u.is_master_admin OR u.society_id IS NULL OR u.society_id = p_society_id);

    IF COALESCE(v_is_admin, FALSE) THEN
        v_status := 'confirmed';
    ELSE
        v_status := 'pending';
    END IF;

    SELECT previous_hash INTO v_prev_hash
    FROM fund_appropriations
    WHERE society_id = p_society_id
    ORDER BY created_at DESC, id DESC LIMIT 1;

    INSERT INTO fund_appropriations (
        society_id, user_id, from_income_acc_id, to_fund_acc_id, particulars,
        amount, approval_ref, approval_date, status, confirmed_by, confirmed_at,
        previous_hash, created_at
    ) VALUES (
        p_society_id, p_created_by, p_income_acc_id, p_fund_acc_id, p_particulars,
        p_amount, p_approval_ref, p_approval_date, v_status,
        CASE WHEN v_status = 'confirmed' THEN p_created_by ELSE NULL END,
        CASE WHEN v_status = 'confirmed' THEN NOW() ELSE NULL END,
        v_prev_hash, NOW()
    ) RETURNING id INTO v_appropriation_id;

    IF v_status = 'confirmed' THEN
        v_journal_id := NEXTVAL('seq_transaction_number');

        -- 1. Dr the income account (reduces its Cr-positive balance)
        -- 2. Cr the fund account (raises the fund's Cr-positive balance)
        -- mode='journal': a pure book entry, no cash/bank leg — the rupees
        -- were already banked when the interest was first credited.
        INSERT INTO transactions (
            society_id, journal_id, acc_id, entry_side, trx_date, amount,
            acc_particulars, mode, status, source_table, source_id, created_by
        ) VALUES (
            p_society_id, v_journal_id, p_income_acc_id, 'Dr', COALESCE(p_approval_date, CURRENT_DATE), p_amount,
            p_particulars, 'journal', 'paid', 'fund_appropriation', v_appropriation_id, p_created_by
        );

        INSERT INTO transactions (
            society_id, journal_id, acc_id, entry_side, trx_date, amount,
            acc_particulars, mode, status, source_table, source_id, created_by
        ) VALUES (
            p_society_id, v_journal_id, p_fund_acc_id, 'Cr', COALESCE(p_approval_date, CURRENT_DATE), p_amount,
            p_particulars, 'journal', 'paid', 'fund_appropriation', v_appropriation_id, p_created_by
        );
    END IF;

    appropriation_id := v_appropriation_id;
    journal_id := v_journal_id;
    status := v_status;

    RETURN NEXT;
END;
$$;

-- fn_confirm_fund_appropriation (2026-09)
-- ======================================================================
-- Turns a 'pending' appropriation written by a non-admin into a posted
-- journal. Without this the pending branch of fn_appropriate_income_to_fund
-- was a dead end: the row was inserted, the toast said "submitted for
-- approval", and NOTHING could ever move it to 'confirmed' or post the
-- Dr income / Cr fund legs. Re-validates the accrued balance at confirm
-- time (income can be appropriated away by someone else in the interim),
-- re-checks that the two accounts still exist and are still Cr-natured,
-- and refuses to run twice on the same row.

CREATE OR REPLACE FUNCTION fn_confirm_fund_appropriation(
    p_appropriation_id INT,
    p_confirmed_by     INT
)
RETURNS TABLE(
    appropriation_id INT,
    journal_id       INT,
    status           VARCHAR(20)
)
LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE
    v_row            fund_appropriations%ROWTYPE;
    v_journal_id     INT;
    v_is_admin       BOOLEAN;
    v_income_balance NUMERIC(15,2);
    v_income_name    TEXT;
    v_fund_name      TEXT;
    v_drcr_income    VARCHAR(2);
    v_drcr_fund      VARCHAR(2);
BEGIN
    SELECT * INTO v_row
    FROM fund_appropriations
    WHERE id = p_appropriation_id
    FOR UPDATE;

    IF NOT FOUND THEN RAISE EXCEPTION 'Appropriation % not found', p_appropriation_id; END IF;

    SELECT (u.role = 'admin' OR u.is_master_admin) INTO v_is_admin
    FROM users u
    WHERE u.id = p_confirmed_by
      AND (u.is_master_admin OR u.society_id IS NULL OR u.society_id = v_row.society_id);
    IF NOT FOUND OR NOT COALESCE(v_is_admin, FALSE) THEN
        RAISE EXCEPTION 'Only an admin of this society can confirm an appropriation';
    END IF;

    IF v_row.status <> 'pending' THEN
        RAISE EXCEPTION 'Appropriation % is already % — nothing to confirm', p_appropriation_id, v_row.status;
    END IF;

    SELECT name, drcr_account INTO v_income_name, v_drcr_income FROM accounts
    WHERE society_id = v_row.society_id AND id = v_row.from_income_acc_id;
    SELECT name, drcr_account INTO v_fund_name, v_drcr_fund FROM accounts
    WHERE society_id = v_row.society_id AND id = v_row.to_fund_acc_id;
    IF v_income_name IS NULL THEN
        RAISE EXCEPTION 'Source income account % no longer exists for this society', v_row.from_income_acc_id;
    END IF;
    IF v_fund_name IS NULL THEN
        RAISE EXCEPTION 'Destination fund account % no longer exists for this society', v_row.to_fund_acc_id;
    END IF;
    -- Re-check the Dr/Cr nature too, not just existence: an admin can
    -- re-nature an account in the chart of accounts between the request
    -- being raised and it being confirmed, and posting a Cr to a Dr-natured
    -- account (or vice versa) would silently distort both balances.
    IF v_drcr_income IS DISTINCT FROM 'Cr' THEN
        RAISE EXCEPTION 'Source account % (%) is no longer a Cr-natured income account', v_row.from_income_acc_id, v_income_name;
    END IF;
    IF v_drcr_fund IS DISTINCT FROM 'Cr' THEN
        RAISE EXCEPTION 'Destination account % (%) is no longer a Cr (equity/reserve) account', v_row.to_fund_acc_id, v_fund_name;
    END IF;

    -- Re-check the accrued balance: between submission and confirmation
    -- another appropriation may already have drawn the same income down,
    -- and the row was written with no reservation on it.
    WITH RECURSIVE income_subtree AS (
        SELECT a.id FROM accounts a
         WHERE a.society_id = v_row.society_id AND a.id = v_row.from_income_acc_id
        UNION ALL
        SELECT c.id FROM accounts c
          JOIN income_subtree s ON c.parent_account_id = s.id
         WHERE c.society_id = v_row.society_id
    )
    SELECT COALESCE(SUM(
        CASE WHEN t.entry_side = 'Cr' THEN t.amount ELSE -t.amount END
    ), 0) INTO v_income_balance
    FROM transactions t
    WHERE t.society_id = v_row.society_id
      AND t.acc_id IN (SELECT id FROM income_subtree);

    IF v_row.amount > v_income_balance THEN
        RAISE EXCEPTION 'Cannot confirm: only ₹% of unappropriated income remains in % (%)',
            v_income_balance, v_income_name, v_row.from_income_acc_id;
    END IF;

    v_journal_id := NEXTVAL('seq_transaction_number');

    INSERT INTO transactions (
        society_id, journal_id, acc_id, entry_side, trx_date, amount,
        acc_particulars, mode, status, source_table, source_id, created_by
    ) VALUES (
        v_row.society_id, v_journal_id, v_row.from_income_acc_id, 'Dr',
        COALESCE(v_row.approval_date, v_row.created_at::DATE, CURRENT_DATE), v_row.amount,
        v_row.particulars, 'journal', 'paid', 'fund_appropriation', v_row.id, p_confirmed_by
    );

    INSERT INTO transactions (
        society_id, journal_id, acc_id, entry_side, trx_date, amount,
        acc_particulars, mode, status, source_table, source_id, created_by
    ) VALUES (
        v_row.society_id, v_journal_id, v_row.to_fund_acc_id, 'Cr',
        COALESCE(v_row.approval_date, v_row.created_at::DATE, CURRENT_DATE), v_row.amount,
        v_row.particulars, 'journal', 'paid', 'fund_appropriation', v_row.id, p_confirmed_by
    );

    UPDATE fund_appropriations
       SET status = 'confirmed', confirmed_by = p_confirmed_by, confirmed_at = NOW()
     WHERE id = v_row.id;

    appropriation_id := v_row.id;
    journal_id := v_journal_id;
    status := 'confirmed';
    RETURN NEXT;
END;
$$;

-- fn_cancel_fund_appropriation (2026-09)
-- ======================================================================
-- Withdraws a still-pending appropriation. Only ever legal on a 'pending'
-- row, so a posted journal can never be orphaned by "cancelling" it after
-- the fact — reversing a confirmed appropriation is a separate, deliberate
-- act, not something a status flip should be able to do.

CREATE OR REPLACE FUNCTION fn_cancel_fund_appropriation(
    p_appropriation_id INT,
    p_cancelled_by     INT
)
RETURNS TABLE(appropriation_id INT, status VARCHAR(20))
LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE
    v_row      fund_appropriations%ROWTYPE;
    v_is_admin BOOLEAN;
BEGIN
    SELECT * INTO v_row FROM fund_appropriations WHERE id = p_appropriation_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Appropriation % not found', p_appropriation_id; END IF;

    SELECT (u.role = 'admin' OR u.is_master_admin) INTO v_is_admin
    FROM users u
    WHERE u.id = p_cancelled_by
      AND (u.is_master_admin OR u.society_id IS NULL OR u.society_id = v_row.society_id);
    IF NOT FOUND OR NOT COALESCE(v_is_admin, FALSE) THEN
        RAISE EXCEPTION 'Only an admin of this society can cancel an appropriation';
    END IF;

    IF v_row.status <> 'pending' THEN
        RAISE EXCEPTION 'Appropriation % is % — only a pending request can be cancelled',
            p_appropriation_id, v_row.status;
    END IF;

    UPDATE fund_appropriations SET status = 'cancelled' WHERE id = v_row.id;

    appropriation_id := v_row.id;
    status := 'cancelled';
    RETURN NEXT;
END;
$$;

-- fn_funds_account_fy (2026-09): the 5th/1st Financial Statement — "Funds
-- Account" schedule (Opening B/F, Additions, Deductions, Closing C/F) for
-- every statutory fund/equity account, alongside the existing 6 Statements
-- (Depreciation, Income & Expenditure, Capital Account & Equity, Balance
-- Sheet). Mirrors the Depreciation Account schedule's B/F-Additions-
-- Deductions-C/F shape, but for Capital/Reserves/Sinking/Repair/Corpus.
--
-- Funds are resolved dynamically by walking the subtree of whichever
-- account is named ILIKE '%Equity%' (== "Equity / Reserves & Funds" in the
-- seeded chart of accounts), the same approach now used by
-- loaders.get_fund_balances/get_expense_bank_accounts for the Fund
-- Management card — NOT hardcoded account ids, since a jurisdiction/legal
-- regime with a different chart-of-accounts numbering (see
-- legal_regime_profiles) would silently break a fixed-id list. This also
-- naturally excludes the "Equity / Reserves & Funds" header itself (its own
-- name matches '%Equity%' so it's the recursion ROOT, never a row in the
-- tree) and any Dr-natured child (e.g. "Gifts Given") that isn't itself a
-- fund/equity balance.

CREATE OR REPLACE FUNCTION fn_funds_account_fy(
    p_society_id INT,
    p_fy         INT
)
RETURNS TABLE (
    account_id   INT,
    account_name TEXT,
    own_bf       NUMERIC(15,2),  -- named to match cap_rows/fn_fy_closing_report's own_bf convention, not opening_bf
    additions    NUMERIC(15,2),
    deductions   NUMERIC(15,2),
    own_closing  NUMERIC(15,2)   -- named to match own_closing convention, not closing_cf
)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
-- Same RETURNS TABLE(...) implicit-variable-collision class of bug already
-- hit twice in this codebase (fn_gst_summary_fy, fn_compute_rcm_liability)
-- — own_bf/additions/deductions/own_closing are OUT parameters AND the
-- top-level SELECT list below, so the pragma is added defensively up front
-- rather than waiting to rediscover the same failure a third time.
DECLARE
    v_fy_start DATE := MAKE_DATE(p_fy, 4, 1);
    v_fy_end   DATE := MAKE_DATE(p_fy + 1, 3, 31);
BEGIN
    RETURN QUERY
    WITH RECURSIVE equity_root AS (
        SELECT a.id FROM accounts a
        WHERE a.society_id = p_society_id AND a.name ILIKE '%Equity%'
    ),
    fund_tree AS (
        SELECT a.id, a.name::TEXT AS acc_name
        FROM accounts a
        JOIN equity_root er ON a.parent_account_id = er.id
        WHERE a.society_id = p_society_id AND a.drcr_account = 'Cr'
        UNION ALL
        SELECT a.id, a.name::TEXT AS acc_name
        FROM accounts a
        JOIN fund_tree ft ON a.parent_account_id = ft.id
        WHERE a.society_id = p_society_id AND a.drcr_account = 'Cr'
    )
    SELECT
        ft.id,
        ft.acc_name,
        (-fn_resolve_bf_amount_fy(p_society_id, ft.id, p_fy)) AS own_bf,
        COALESCE((
            SELECT SUM(t.amount) FROM transactions t
            WHERE t.society_id = p_society_id AND t.acc_id = ft.id
              AND t.entry_side = 'Cr' AND t.trx_date BETWEEN v_fy_start AND v_fy_end
        ), 0) AS additions,
        COALESCE((
            SELECT SUM(t.amount) FROM transactions t
            WHERE t.society_id = p_society_id AND t.acc_id = ft.id
              AND t.entry_side = 'Dr' AND t.trx_date BETWEEN v_fy_start AND v_fy_end
        ), 0) AS deductions,
        (-fn_resolve_bf_amount_fy(p_society_id, ft.id, p_fy))
            + COALESCE((
                SELECT SUM(t.amount) FROM transactions t
                WHERE t.society_id = p_society_id AND t.acc_id = ft.id
                  AND t.entry_side = 'Cr' AND t.trx_date BETWEEN v_fy_start AND v_fy_end
              ), 0)
            - COALESCE((
                SELECT SUM(t.amount) FROM transactions t
                WHERE t.society_id = p_society_id AND t.acc_id = ft.id
                  AND t.entry_side = 'Dr' AND t.trx_date BETWEEN v_fy_start AND v_fy_end
              ), 0) AS own_closing
    FROM fund_tree ft
    ORDER BY ft.id;
END;
$$;

-- ═══════════════════════════════════════════════════════════════════════════
-- FY CLOSE — statutory reserve appropriation
-- ═══════════════════════════════════════════════════════════════════════════
-- The Model Bye-Laws say common profits form the nucleus of the reserve funds
-- but set NO percentage, so the share of net surplus moved to the Reserve Fund
-- each year is society policy (regime parameter reserve_appropriation_pct, seeded
-- 25, set by General Body resolution). That rule was previously only prose: it appeared in
-- the comment block above fn_process_fund_utilization and as a "Manual —
-- not yet implemented" row in the README, with no SQL, no loader, no button.
-- These three functions implement it end to end.
--
-- WHY THIS IS A WRITE AND NOT A DISPLAY TWEAK: fn_fy_closing_report is
-- explicitly read-time and non-persisting, so an appropriation has to be a
-- real journal or the reserve simply never grows. fn_fy_close_reserve_
-- appropriation is therefore the first VOLATILE function in this area, and
-- it is deliberately conservative:
--   - It refuses to run on books that do not balance (see the root-total
--     acceptance test documented on fn_fy_closing_report: a nonzero root
--     total is "a hard error signal, not something to silently absorb").
--     Appropriating from unbalanced books would bake the error into equity.
--   - It is idempotent via UNIQUE (society_id, financial_year) on fy_closures,
--     not merely by a read-then-write check, so two concurrent admins cannot
--     both appropriate.
--   - It never appropriates from a deficit year. A loss is carried forward
--     against the reserve implicitly, not by posting a negative transfer.
--
-- The read-only sibling fn_fy_close_preview exists so the card can show the
-- surplus, the proposed amount and every blocker BEFORE the admin commits
-- to an irreversible ledger write.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── Resolve the society's Reserve Fund ledger account ─────────────────────
-- Resolved jurisdiction-aware, through account_statutory_mappings for the
-- society's own legal regime, so a differently-numbered chart under another
-- regime still works. The seeded UP_AOA_2010 mapping puts BOTH the Repair &
-- Maintenance Fund Reserve (3220) and the Corpus Fund (3230) under head
-- RESERVE_FUND, so "mapped to RESERVE_FUND" alone is ambiguous and cannot be
-- used directly. The ORDER BY below disambiguates deterministically,
-- preferring the account that is not a statutorily-locked fund and not
-- named corpus/sinking, then lowest id:
--     1. statutory_lock_pct = 0  (not a law-protected principal fund)
--     2. name NOT ILIKE '%corpus%'
--     3. name NOT ILIKE '%sinking%'
--     4. account id ASC (stable tiebreak)
-- Falls back to a plain ILIKE '%reserve fund%' name match for a society
-- with no statutory mappings at all, and returns NULL if neither finds
-- anything — callers must treat NULL as "cannot appropriate", not as an
-- error to swallow.

CREATE OR REPLACE FUNCTION fn_resolve_reserve_account(p_society_id INT)
RETURNS INT
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_acc_id INT;
    v_regime VARCHAR(30);
BEGIN
    SELECT regime_code INTO v_regime
    FROM society_legal_regime
    WHERE society_id = p_society_id
    ORDER BY effective_from DESC
    LIMIT 1;

    IF v_regime IS NOT NULL THEN
        SELECT a.id INTO v_acc_id
        FROM accounts a
        JOIN account_statutory_mappings m
          ON m.account_id = a.id
         AND m.society_id = a.society_id
         AND m.regime_code = v_regime
        WHERE a.society_id = p_society_id
          AND m.head_code = 'RESERVE_FUND'
          AND m.effective_to IS NULL
          AND a.drcr_account = 'Cr'
        ORDER BY
            (COALESCE(a.statutory_lock_pct, 0) > 0),
            (a.name ILIKE '%corpus%'),
            (a.name ILIKE '%sinking%'),
            a.id
        LIMIT 1;
    END IF;

    IF v_acc_id IS NULL THEN
        SELECT a.id INTO v_acc_id
        FROM accounts a
        WHERE a.society_id = p_society_id
          AND a.drcr_account = 'Cr'
          AND a.name ILIKE '%reserve fund%'
        ORDER BY
            (COALESCE(a.statutory_lock_pct, 0) > 0),
            (a.name ILIKE '%corpus%'),
            (a.name ILIKE '%sinking%'),
            a.id
        LIMIT 1;
    END IF;

    RETURN v_acc_id;
END;
$$;

-- ── Resolve the P&L contra account used for the appropriation ─────────────
-- The debit side of the year-end journal is the "Income Expenditure A/c"
-- (tab_name 'InExp', id 5100 in the seeded chart), a Cr-natured node under
-- the Expenses block that exists precisely to accumulate P&L transfers —
-- the depreciation journal already posts "Dr InExp / Cr Depreciation"
-- against it (see the seed's year-end transfer journal). Reusing it means
-- the appropriation lands in the same accumulator the closing report
-- already understands, rather than inventing a new balancing account.
-- Name fallback covers a chart where tab_name was renamed.

CREATE OR REPLACE FUNCTION fn_resolve_inexp_appropriation_account(p_society_id INT)
RETURNS INT
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_acc_id INT;
BEGIN
    SELECT id INTO v_acc_id
    FROM accounts
    WHERE society_id = p_society_id AND tab_name = 'InExp'
    LIMIT 1;

    IF v_acc_id IS NULL THEN
        SELECT id INTO v_acc_id
        FROM accounts
        WHERE society_id = p_society_id AND name ILIKE 'Income Expenditure%'
        LIMIT 1;
    END IF;

    RETURN v_acc_id;
END;
$$;

-- ── Read-only preview ────────────────────────────────────────────────────
-- Everything the FY Closing card needs to decide whether to enable its
-- "Close Year & Transfer to Reserve" button, and to explain itself if the
-- button is disabled. STABLE, writes nothing.

CREATE OR REPLACE FUNCTION fn_fy_close_preview(
    p_society_id  INT,
    p_fy          INT,
    p_reserve_pct NUMERIC DEFAULT NULL
)
RETURNS TABLE(
    fy                INT,
    already_closed    BOOLEAN,
    closure_status    VARCHAR(20),
    closure_date      TIMESTAMP,
    books_balanced    BOOLEAN,
    imbalance_amount  NUMERIC(15,2),
    surplus           NUMERIC(15,2),
    reserve_pct       NUMERIC(5,2),
    proposed_transfer NUMERIC(15,2),
    reserve_acc_id    INT,
    reserve_acc_name  TEXT,
    contra_acc_id     INT,
    can_close         BOOLEAN,
    blockers          TEXT,
    notes             TEXT
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_fy_start   DATE := MAKE_DATE(p_fy, 4, 1);
    v_fy_end     DATE := MAKE_DATE(p_fy + 1, 3, 31);
    v_closure    RECORD;
    v_root       NUMERIC(15,2) := 0;
    v_surplus    NUMERIC(15,2) := 0;
    v_pct        NUMERIC(5,2);
    v_transfer   NUMERIC(15,2);
    v_reserve_id INT;
    v_contra_id  INT;
    v_blockers   TEXT := '';
    v_notes      TEXT := '';
BEGIN
    v_pct := LEAST(GREATEST(COALESCE(p_reserve_pct, fn_regime_param_num(p_society_id, 'reserve_appropriation_pct'), 25.0), 0), 100);

    -- Root total: the double-entry identity in fn_fy_closing_report's
    -- Cr-positive sign convention. Must be ~0 for the books to balance.
    SELECT COALESCE(MAX(ABS(c.total_closing)), 0) INTO v_root
    FROM fn_fy_closing_report(p_society_id, p_fy) c
    WHERE c.parent_account_id IS NULL;

    -- Net surplus, computed exactly as fn_balance_sheet_fy's ie_surplus CTE
    -- does (same strict-descendant sort_path match, same Cr-positive sum), so
    -- what the card proposes and what the Balance Sheet reports as
    -- "Reserves & Surplus" can never disagree.
    SELECT COALESCE(SUM(c.own_closing), 0) INTO v_surplus
    FROM fn_fy_closing_report(p_society_id, p_fy) c
    WHERE c.own_closing IS NOT NULL
      AND c.own_closing != 0
      AND EXISTS (
          SELECT 1
          FROM fn_fy_closing_report(p_society_id, p_fy) r
          WHERE r.tab_name IN ('Inc', 'Exp')
            AND c.sort_path LIKE r.sort_path || '.%'
      );

    v_reserve_id := fn_resolve_reserve_account(p_society_id);
    v_contra_id  := fn_resolve_inexp_appropriation_account(p_society_id);
    v_transfer   := GREATEST(ROUND(GREATEST(v_surplus, 0) * v_pct / 100, 2), 0);

    SELECT c.id, c.status, c.closed_at INTO v_closure
    FROM fy_closures c
    WHERE c.society_id = p_society_id AND c.financial_year = p_fy;

    -- Blockers, accumulated as readable sentences. Order matters: the most
    -- fundamental reason (unbalanced books) is reported first, because a
    -- deficit caused by a data-entry error should not be presented as a
    -- legitimate loss of the year.
    --
    -- A BLOCKER means "the close must not happen". A NOTE means "the close is
    -- allowed but does something other than the usual appropriation". Keeping
    -- them apart matters: a deficit year still has to be closeable, otherwise
    -- the year can never be closed at all and every later year inherits an
    -- open, unbalanced-looking predecessor.
    IF v_root > 0.01 THEN
        v_blockers := v_blockers ||
            format('Books do not balance (out by ₹%s). Fix the ledger before closing — appropriating from unbalanced books would bake the error into equity. ',
                   trim(to_char(v_root, 'FM999,999,999,990.00')));
    END IF;
    IF v_closure IS NOT NULL AND v_closure.status <> 'reversed' THEN
        v_blockers := v_blockers ||
            format('FY %s is already closed (%s). ', p_fy, v_closure.status);
    END IF;
    IF v_surplus <= 0 AND v_closure IS NULL THEN
        v_notes := v_notes ||
            format('FY %s has no net surplus (₹%s), so there is nothing to appropriate — a deficit year carries forward against the reserve, it is not funded from it. Closing will record the year with no reserve transfer. ',
                   p_fy, trim(to_char(v_surplus, 'FM999,999,999,990.00')));
    END IF;
    IF v_transfer > 0 AND v_reserve_id IS NULL THEN
        v_blockers := v_blockers ||
            'No Reserve Fund account could be resolved (looked for an account mapped to statutory head RESERVE_FUND, then a name matching ''%reserve fund%''). Map one, or this appropriation cannot be posted. ';
    END IF;
    -- s.18(1) common profits / bye-law 46(c): the note the scheme pack itself asked for.
    -- When no General Body resolution has set reserve_appropriation_pct, the engine's
    -- 25% co-operative convention is used and the preview says so, so the close is never
    -- mistaken for a resolved statutory percentage.
    IF p_reserve_pct IS NULL AND fn_regime_param_num(p_society_id, 'reserve_appropriation_pct', MAKE_DATE(p_fy, 4, 1)) IS NULL THEN
        v_notes := v_notes ||
            format('The reserve percentage is the engine''s provisional 25%% default: no General Body resolution has set reserve_appropriation_pct for this society. Record the resolution (or pass an explicit percentage on this call) before relying on the transfer. ');
    END IF;
    IF v_transfer > 0 AND v_contra_id IS NULL THEN
        v_blockers := v_blockers ||
            'No Income Expenditure A/c (tab_name ''InExp'') found to debit the appropriation against. Add it to the chart of accounts first. ';
    END IF;

    fy                := p_fy;
    already_closed    := (v_closure IS NOT NULL AND v_closure.status <> 'reversed');
    closure_status    := v_closure.status;
    closure_date      := v_closure.closed_at;
    books_balanced    := (v_root <= 0.01);
    imbalance_amount  := v_root;
    surplus           := v_surplus;
    reserve_pct       := v_pct;
    proposed_transfer := v_transfer;
    reserve_acc_id    := v_reserve_id;
    reserve_acc_name  := (SELECT name FROM accounts
                          WHERE id = v_reserve_id AND society_id = p_society_id);
    contra_acc_id     := v_contra_id;
    -- can_close is gated on the hard blockers only. A year with no surplus
    -- is still closeable (the write records status 'no_surplus'); what
    -- changes is that no journal is posted.
    can_close         := (v_blockers = '');
    blockers          := NULLIF(v_blockers, '');
    notes             := NULLIF(v_notes, '');

    RETURN NEXT;
END;
$$;

-- ── The write path ───────────────────────────────────────────────────────
-- Posts, in ONE journal:
--     Dr  Income Expenditure A/c   (the P&L accumulator)
--         Cr  Reserve Fund
-- for `reserve_pct` of the FY's net surplus, then records the closure.
--
-- Cr-positive reasoning: the InExp node is Cr-natured, so a Dr posting
-- reduces its Cr-positive own_closing, which reduces the P&L surplus the
-- closing report computes; crediting the Reserve Fund (a Cr account under
-- Equity) raises equity by the same amount. The root total is unchanged
-- either way, so the books still balance.
--
-- The remaining 75% (or whatever is left) deliberately stays in the P&L and
-- keeps showing up as "Reserves & Surplus" on the Balance Sheet — this
-- function appropriates a share, it does not close the books.

CREATE OR REPLACE FUNCTION fn_fy_close_reserve_appropriation(
    p_society_id  INT,
    p_fy          INT,
    p_reserve_pct NUMERIC DEFAULT NULL,
    p_created_by  INT  DEFAULT NULL
)
RETURNS TABLE(
    closure_id         INT,
    fy                 INT,
    status             VARCHAR(20),
    surplus            NUMERIC(15,2),
    reserve_pct        NUMERIC(5,2),
    reserve_transferred NUMERIC(15,2),
    journal_id         INT,
    reserve_acc_name   TEXT,
    message            TEXT
)
LANGUAGE plpgsql AS $$
DECLARE
    v_fy_end     DATE := MAKE_DATE(p_fy + 1, 3, 31);
    v_pct        NUMERIC(5,2);
    v_prev_id    INT;
    v_prev_status VARCHAR(20);
    v_prev_surplus NUMERIC(15,2);
    v_prev_pct   NUMERIC(5,2);
    v_prev_xfer  NUMERIC(15,2);
    v_prev_journal INT;
    v_prev_name  TEXT;
    v_prev_at    TIMESTAMP;
    v_reserve_id INT;
    v_contra_id  INT;
    v_journal_id INT;
    v_closure_id INT;
    v_surplus    NUMERIC(15,2);
    v_transfer   NUMERIC(15,2);
    v_root       NUMERIC(15,2);
    v_name       TEXT;
    v_tn         VARCHAR(64);
BEGIN
    v_pct := LEAST(GREATEST(COALESCE(p_reserve_pct, fn_regime_param_num(p_society_id, 'reserve_appropriation_pct'), 25.0), 0), 100);
    -- s.18(1)/46(c): a percentage that exists with no General Body resolution behind it
    -- must not be silently appropriated on the engine's provisional default. The caller
    -- (FY Closing card) either records the resolution through the rule editor first, or
    -- passes the resolved p_reserve_pct explicitly; only then does the journal post.
    IF p_reserve_pct IS NULL AND fn_regime_param_num(p_society_id, 'reserve_appropriation_pct') IS NULL THEN
        RAISE EXCEPTION
            'FY %s cannot be closed: no General Body resolution sets the reserve percentage. Record reserve_appropriation_pct through the AOA Rule Editor (or pass the resolved percentage explicitly) - appropriating the provisional engine default without a resolution would leave no decision trail for the common-profits transfer.',
            p_fy;
    END IF;

    -- Idempotency.
    --
    -- Deliberately NOT written as `SELECT c.* INTO v_prev RECORD` +
    -- `IF v_prev IS NOT NULL`. IS NULL on a RECORD is true only when *every*
    -- field is null, which is a subtle test to rely on for control flow — and
    -- when it was tried here the guard let a second close straight through to
    -- the journal INSERT. Typed scalars plus FOUND is the idiomatic and
    -- unambiguous form.
    --
    -- This SELECT gives a friendly 'already_closed' row instead of a raw
    -- unique-violation error. It is NOT the concurrency guard — two admins
    -- can both pass it. UNIQUE (society_id, financial_year) on fy_closures is
    -- that guard, and the EXCEPTION block at the bottom of this function
    -- turns a losing race into the same friendly row rather than an error.
    SELECT c.id, c.status, c.surplus, c.reserve_pct, c.reserve_transferred,
           c.journal_id, c.reserve_acc_name, c.closed_at
      INTO v_prev_id, v_prev_status, v_prev_surplus, v_prev_pct, v_prev_xfer,
           v_prev_journal, v_prev_name, v_prev_at
    FROM fy_closures c
    WHERE c.society_id = p_society_id AND c.financial_year = p_fy;

    IF FOUND AND v_prev_status <> 'reversed' THEN
        closure_id         := v_prev_id;
        fy                 := p_fy;
        status             := 'already_closed';
        surplus            := v_prev_surplus;
        reserve_pct        := v_prev_pct;
        reserve_transferred := v_prev_xfer;
        journal_id         := v_prev_journal;
        reserve_acc_name   := v_prev_name;
        message            := format(
            'FY %s was already closed on %s — ₹%s was appropriated to %s at %s%%. Nothing further was posted.',
            p_fy,
            to_char(v_prev_at, 'DD/MM/YYYY HH24:MI'),
            trim(to_char(v_prev_xfer, 'FM999,999,999,990.00')),
            COALESCE(v_prev_name, 'the reserve fund'),
            trim(to_char(v_prev_pct, 'FM990.00'))
        );
        RETURN NEXT;
        RETURN;
    END IF;

    -- Refuse on unbalanced books. fn_fy_closing_report documents a nonzero
    -- root total as "a hard error signal, not something to silently absorb".
    SELECT COALESCE(MAX(ABS(c.total_closing)), 0) INTO v_root
    FROM fn_fy_closing_report(p_society_id, p_fy) c
    WHERE c.parent_account_id IS NULL;

    IF v_root > 0.01 THEN
        RAISE EXCEPTION
            'FY %s cannot be closed: books are out of balance by ₹%. Fix the ledger first — appropriating a surplus computed from unbalanced books would post the error into the Reserve Fund.',
            p_fy, v_root;
    END IF;

    SELECT COALESCE(SUM(c.own_closing), 0) INTO v_surplus
    FROM fn_fy_closing_report(p_society_id, p_fy) c
    WHERE c.own_closing IS NOT NULL
      AND c.own_closing != 0
      AND EXISTS (
          SELECT 1
          FROM fn_fy_closing_report(p_society_id, p_fy) r
          WHERE r.tab_name IN ('Inc', 'Exp')
            AND c.sort_path LIKE r.sort_path || '.%'
      );

    v_reserve_id := fn_resolve_reserve_account(p_society_id);
    v_contra_id  := fn_resolve_inexp_appropriation_account(p_society_id);
    v_transfer   := GREATEST(ROUND(GREATEST(v_surplus, 0) * v_pct / 100, 2), 0);

    SELECT name INTO v_name FROM accounts
    WHERE id = v_reserve_id AND society_id = p_society_id;

    -- A deficit year still gets a closure row, with nothing appropriated: a
    -- loss is carried forward against the reserve implicitly. Recording the
    -- close keeps the year from being re-closed later and makes the
    -- no-transfer explicit in the audit trail instead of silent.
    IF v_transfer <= 0 THEN
        INSERT INTO fy_closures (
            society_id, financial_year, surplus, reserve_pct, reserve_transferred,
            reserve_acc_id, reserve_acc_name, contra_acc_id, status, closed_by
        ) VALUES (
            p_society_id, p_fy, v_surplus, v_pct, 0,
            v_reserve_id, v_name, v_contra_id, 'no_surplus', p_created_by
        ) RETURNING id INTO v_closure_id;

        closure_id         := v_closure_id;
        fy                 := p_fy;
        status             := 'no_surplus';
        surplus            := v_surplus;
        reserve_pct        := v_pct;
        reserve_transferred := 0;
        journal_id         := NULL;
        reserve_acc_name   := v_name;
        message            := format(
            'FY %s closed with no appropriation: net surplus is ₹%s, so there is nothing to transfer to the reserve. The deficit carries forward.',
            p_fy, trim(to_char(v_surplus, 'FM999,999,999,990.00'))
        );
        RETURN NEXT;
        RETURN;
    END IF;

    IF v_reserve_id IS NULL THEN
        RAISE EXCEPTION
            'FY %s cannot be closed: no Reserve Fund account resolved. Map an account to statutory head RESERVE_FUND, or name one "%%Reserve Fund%%".', p_fy;
    END IF;
    IF v_contra_id IS NULL THEN
        RAISE EXCEPTION
            'FY %s cannot be closed: no Income Expenditure A/c (tab_name ''InExp'') found to debit the appropriation against.', p_fy;
    END IF;

    v_journal_id := NEXTVAL('seq_transaction_number');
    v_tn := format('FYCLOSE-%s-%s', p_society_id, p_fy);

    -- The journal legs and the closure row are written inside one inner block
    -- so that an EXCEPTION handler can roll all three back together — plpgsql
    -- only allows EXCEPTION on a block boundary, and the subtransaction it
    -- opens is what makes "post nothing if we lose the race" true rather than
    -- aspirational.
    BEGIN
        -- Dr Income Expenditure A/c / Cr Reserve Fund.
        -- mode='journal': a pure book entry, no cash or bank leg (the same
        -- convention as the seed's Dr Dep / Cr Asset year-end journal, and the
        -- reason these rows stay out of the cashbook while still counting in
        -- the ledger, trial balance and closing report). status='paid' is
        -- required because fn_fy_closing_report only counts paid transactions —
        -- without it the appropriation would post but not show up in the very
        -- report that justified it.
        INSERT INTO transactions (
            society_id, journal_id, acc_id, entry_side, trx_date, amount,
            acc_particulars, mode, status, source_table, source_id, created_by,
            transaction_number
        ) VALUES (
            p_society_id, v_journal_id, v_contra_id, 'Dr', v_fy_end, v_transfer,
            format('Statutory reserve appropriation: %s%% of FY %s net surplus', trim(to_char(v_pct, 'FM990.00')), p_fy),
            'journal', 'paid', 'fy_close', NULL, p_created_by, v_tn
        );

        INSERT INTO transactions (
            society_id, journal_id, acc_id, entry_side, trx_date, amount,
            acc_particulars, mode, status, source_table, source_id, created_by,
            transaction_number
        ) VALUES (
            p_society_id, v_journal_id, v_reserve_id, 'Cr', v_fy_end, v_transfer,
            format('Transfer from Income & Expenditure A/c — statutory reserve appropriation (FY %s)', p_fy),
            'journal', 'paid', 'fy_close', NULL, p_created_by, format('%s-B', v_tn)
        );

        -- Written LAST on purpose. Two admins can both pass the idempotency
        -- SELECT above; exactly one INSERT into fy_closures survives the
        -- UNIQUE constraint, and because it is the last statement in this
        -- block, the loser's subtransaction rollback also undoes their two
        -- journal legs — so the loser posts nothing at all.
        INSERT INTO fy_closures (
            society_id, financial_year, surplus, reserve_pct, reserve_transferred,
            reserve_acc_id, reserve_acc_name, contra_acc_id, journal_id, status, closed_by
        ) VALUES (
            p_society_id, p_fy, v_surplus, v_pct, v_transfer,
            v_reserve_id, v_name, v_contra_id, v_journal_id, 'closed', p_created_by
        ) RETURNING id INTO v_closure_id;

    -- Losing a concurrent close: hand back the same friendly 'already_closed'
    -- row the sequential path returns, instead of surfacing a raw
    -- unique-violation to the UI.
    EXCEPTION WHEN unique_violation THEN
        SELECT c.id, c.surplus, c.reserve_pct, c.reserve_transferred,
               c.journal_id, c.reserve_acc_name
          INTO v_prev_id, v_prev_surplus, v_prev_pct, v_prev_xfer,
               v_prev_journal, v_prev_name
        FROM fy_closures c
        WHERE c.society_id = p_society_id AND c.financial_year = p_fy;

        closure_id         := v_prev_id;
        fy                 := p_fy;
        status             := 'already_closed';
        surplus            := v_prev_surplus;
        reserve_pct        := v_prev_pct;
        reserve_transferred := v_prev_xfer;
        journal_id         := v_prev_journal;
        reserve_acc_name   := v_prev_name;
        message            := format(
            'FY %s was closed concurrently by another administrator — ₹%s was appropriated to %s. Nothing further was posted.',
            p_fy, trim(to_char(v_prev_xfer, 'FM999,999,999,990.00')),
            COALESCE(v_prev_name, 'the reserve fund'));
        RETURN NEXT;
        RETURN;
    END;

    closure_id         := v_closure_id;
    fy                 := p_fy;
    status             := 'closed';
    surplus            := v_surplus;
    reserve_pct        := v_pct;
    reserve_transferred := v_transfer;
    journal_id         := v_journal_id;
    reserve_acc_name   := v_name;
    message            := format(
        'FY %s closed. ₹%s (=%s%% of the ₹%s net surplus) transferred from Income & Expenditure A/c to %s. Journal %s. The remaining ₹%s stays in the P&L and is reported as Reserves & Surplus on the Balance Sheet.',
        p_fy,
        trim(to_char(v_transfer, 'FM999,999,999,990.00')),
        trim(to_char(v_pct, 'FM990.00')),
        trim(to_char(v_surplus, 'FM999,999,999,990.00')),
        v_name, v_journal_id,
        trim(to_char(v_surplus - v_transfer, 'FM999,999,999,990.00'))
    );

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
    WHERE society_id = p_society_id AND tab_name = 'CGST'
    LIMIT 1;

    SELECT id INTO v_sgst FROM accounts
    WHERE society_id = p_society_id AND tab_name = 'SGST'
    LIMIT 1;

    RETURN QUERY SELECT v_cgst, v_sgst;  -- NULLs if not found — caller treats that as "GST not configured"
END;
$$;

-- fn_resolve_rcm_gst_accounts (2026-09, Phase 2): dedicated RCM ledger
-- heads, segregated from the society's own outward-supply GST accounts
-- (fn_resolve_gst_accounts above). Previously RCM was posted to the same
-- "CGST Payable"/"SGST Payable" accounts as regular output tax, making
-- GSTR-3B Table 3.1(d) (RCM) vs. Table 3.1(a) (outward supply)
-- reconciliation impossible from the books alone. itc_acc_id is a
-- Dr-normal asset account for GST that is recoverable as Input Tax
-- Credit (see fn_compute_rcm_liability's itc_eligible gate).

CREATE OR REPLACE FUNCTION fn_resolve_rcm_gst_accounts(p_society_id INT)
RETURNS TABLE(cgst_acc_id INT, sgst_acc_id INT, igst_acc_id INT, itc_acc_id INT)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
DECLARE
    v_cgst INT; v_sgst INT; v_igst INT; v_itc INT;
BEGIN
    SELECT id INTO v_cgst FROM accounts
    WHERE society_id = p_society_id AND tab_name = 'CGSTRCM' LIMIT 1;
    SELECT id INTO v_sgst FROM accounts
    WHERE society_id = p_society_id AND tab_name = 'SGSTRCM' LIMIT 1;
    SELECT id INTO v_igst FROM accounts
    WHERE society_id = p_society_id AND tab_name = 'IGSTRCM' LIMIT 1;
    SELECT id INTO v_itc FROM accounts
    WHERE society_id = p_society_id AND tab_name = 'ITCRCM' LIMIT 1;

    RETURN QUERY SELECT v_cgst, v_sgst, v_igst, v_itc;  -- NULLs if not configured — caller warns and falls back
END;
$$;

-- fn_resolve_rcm_rate (2026-09, Phase 2): config-driven replacement for
-- the inline CASE WHEN previously hardcoded in fn_compute_rcm_liability.
-- Society-specific override (rcm_rates.society_id = p_society_id) wins
-- over the statutory default row (society_id IS NULL) when both have an
-- effective window covering p_date. Falls back to 18% with a warning
-- only if a category has no matching row at all (should not happen —
-- schema load seeds all nine statutory categories).

CREATE OR REPLACE FUNCTION fn_resolve_rcm_rate(
    p_society_id  INT,
    p_category    VARCHAR,
    p_date        DATE
)
RETURNS NUMERIC(5,2) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_rate NUMERIC(5,2);
BEGIN
    SELECT rate_pct INTO v_rate FROM rcm_rates
    WHERE society_id = p_society_id AND rcm_category = p_category
      AND effective_from <= p_date AND (effective_to IS NULL OR effective_to >= p_date)
    ORDER BY effective_from DESC LIMIT 1;

    IF v_rate IS NULL THEN
        SELECT rate_pct INTO v_rate FROM rcm_rates
        WHERE society_id IS NULL AND rcm_category = p_category
          AND effective_from <= p_date AND (effective_to IS NULL OR effective_to >= p_date)
        ORDER BY effective_from DESC LIMIT 1;
    END IF;

    IF v_rate IS NULL THEN
        RAISE WARNING 'No rcm_rates row for category % — falling back to 18%% default', p_category;
        v_rate := 18.00;
    END IF;

    RETURN v_rate;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- RCM: Compute GST liability on expenses paid to unregistered
-- parties (self-invoiced mechanism).
--
-- Triggered when an expense has rcm_applicable = TRUE.
-- Rate mapping (Notification No. 13/2017-Central Tax (Rate)) now lives
-- in rcm_rates — see fn_resolve_rcm_rate. Gated on the society actually
-- being liable to register for GST (Sec. 9(3)/9(4) apply only to a
-- "registered person") using the same turnover-threshold test already
-- established in fn_auto_generate_receivables, rather than posting RCM
-- unconditionally. Splits into CGST+SGST (intra-state) or IGST
-- (inter-state) by comparing vendor.state to societies.state.
-- ════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_compute_rcm_liability(
    p_society_id  INT,
    p_expense_id  INT
)
RETURNS TABLE (
    taxable_value NUMERIC(15,2),
    cgst_amount   NUMERIC(15,2),
    sgst_amount   NUMERIC(15,2),
    igst_amount   NUMERIC(15,2),
    cgst_acc_id   INT,
    sgst_acc_id   INT,
    igst_acc_id   INT,
    itc_acc_id    INT,
    itc_eligible  BOOLEAN
)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
-- Fixed (2026-09, live-tested): RETURNS TABLE(...) declares implicit
-- OUT-parameter variables in scope for the whole function body, which
-- collide with fn_resolve_rcm_gst_accounts'/fn_resolve_gst_accounts'
-- identically named result columns ("column reference is ambiguous").
-- Same bug class already fixed once in fn_gst_summary_fy; the pragma
-- makes plpgsql prefer the table column, which is what the query intends.
DECLARE
    v_expense       expenses%ROWTYPE;
    v_vendor_rcm    VARCHAR(50);
    v_rcm_cat       VARCHAR(50);
    v_rate          NUMERIC(5,2);
    v_society_state VARCHAR(50);
    v_vendor_state  VARCHAR(50);
    v_interstate    BOOLEAN;
    v_turnover_threshold NUMERIC;
    v_society_turnover   NUMERIC;
    v_current_fy    INT;
BEGIN
    SELECT * INTO v_expense
      FROM expenses WHERE id = p_expense_id AND society_id = p_society_id;
    IF NOT FOUND THEN
        RETURN QUERY SELECT 0::NUMERIC(15,2), 0::NUMERIC(15,2), 0::NUMERIC(15,2),
            0::NUMERIC(15,2), NULL::INT, NULL::INT, NULL::INT, NULL::INT, FALSE;
        RETURN;
    END IF;

    -- Registration gate: Sec. 9(3)/9(4) RCM liability applies only to a
    -- "registered person" — a society below the GST registration
    -- threshold has no GST liability at all, including RCM. Mirrors the
    -- exact threshold test fn_auto_generate_receivables already uses for
    -- outward-supply taxability, rather than the (unused for this
    -- purpose) societies.gst_registered flag.
    SELECT value INTO v_turnover_threshold FROM state_compliance_thresholds
      WHERE threshold_key = 'gst_turnover_lakh' AND is_active = TRUE LIMIT 1;
    v_turnover_threshold := COALESCE(v_turnover_threshold, 20) * 100000;

    v_current_fy := CASE WHEN EXTRACT(MONTH FROM v_expense.expense_date) >= 4
        THEN EXTRACT(YEAR FROM v_expense.expense_date)::INT
        ELSE EXTRACT(YEAR FROM v_expense.expense_date)::INT - 1 END;
    SELECT fn_society_turnover_fy(p_society_id, v_current_fy) INTO v_society_turnover;

    IF COALESCE(v_society_turnover, 0) <= v_turnover_threshold THEN
        RETURN QUERY SELECT 0::NUMERIC(15,2), 0::NUMERIC(15,2), 0::NUMERIC(15,2),
            0::NUMERIC(15,2), NULL::INT, NULL::INT, NULL::INT, NULL::INT, FALSE;
        RETURN;
    END IF;

    -- Determine RCM category: vendor pre-classification takes
    -- priority, else use the expense form selection.
    SELECT rcm_category, state INTO v_vendor_rcm, v_vendor_state
      FROM vendors WHERE id = v_expense.entity_id AND society_id = p_society_id;

    v_rcm_cat := COALESCE(v_vendor_rcm, v_expense.rcm_category);
    IF v_rcm_cat IS NULL OR v_rcm_cat = '' THEN
        RETURN QUERY SELECT 0::NUMERIC(15,2), 0::NUMERIC(15,2), 0::NUMERIC(15,2),
            0::NUMERIC(15,2), NULL::INT, NULL::INT, NULL::INT, NULL::INT, FALSE;
        RETURN;
    END IF;

    v_rate := fn_resolve_rcm_rate(p_society_id, v_rcm_cat, v_expense.expense_date);

    SELECT state INTO v_society_state FROM societies WHERE id = p_society_id;
    v_interstate := (v_vendor_state IS NOT NULL AND v_society_state IS NOT NULL
                      AND v_vendor_state <> v_society_state);

    taxable_value := v_expense.amount;

    -- Sec. 17(5) blocked-credit gate: ITC is NOT eligible for certain categories
    -- even if the society is registered. Check the expense/rcm category against
    -- the blocked list from GST rules.
    itc_eligible  := TRUE;
    IF v_rcm_cat IN ('motor_vehicle', 'food_beverages', 'outdoor_catering', 'beauty_treatment',
                     'health_fitness', 'club_membership', 'travel_benefits', 'life_insurance',
                     'health_insurance', 'rent_a_cab', 'construction_immovable_property') THEN
        itc_eligible := FALSE;
    END IF;

    IF v_interstate THEN
        cgst_amount := 0; sgst_amount := 0;
        igst_amount := ROUND(taxable_value * v_rate / 100.0, 2);
    ELSE
        igst_amount := 0;
        cgst_amount := ROUND(taxable_value * (v_rate / 2) / 100.0, 2);
        sgst_amount := ROUND(taxable_value * (v_rate / 2) / 100.0, 2);
    END IF;

    SELECT rcm.cgst_acc_id, rcm.sgst_acc_id, rcm.igst_acc_id, rcm.itc_acc_id
      INTO cgst_acc_id, sgst_acc_id, igst_acc_id, itc_acc_id
      FROM fn_resolve_rcm_gst_accounts(p_society_id) AS rcm;

    RETURN QUERY SELECT
        taxable_value, cgst_amount, sgst_amount, igst_amount,
        cgst_acc_id, sgst_acc_id, igst_acc_id, itc_acc_id, itc_eligible;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- RCM: Post self-invoiced GST liability.
--
-- Inserts into rcm_liability and posts journal entries (mode='journal'
-- — pure book entries, no cash/bank movement):
--   Dr Input Tax Credit (RCM) [if itc_eligible] or Dr Expense Account
--       [if not itc_eligible, non-recoverable]
--   Cr CGST/SGST Payable (RCM), or Cr IGST Payable (RCM) for
--       inter-state supplies
-- Same journal_id as the parent expense for traceability. Segregated
-- RCM accounts (see fn_resolve_rcm_gst_accounts) keep this liability
-- distinguishable from the society's own outward-supply GST in the
-- trial balance.
-- ════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_post_rcm_liability(
    p_society_id   INT,
    p_expense_id   INT,
    p_cgst         NUMERIC,
    p_sgst         NUMERIC,
    p_igst         NUMERIC DEFAULT 0,
    p_itc_eligible BOOLEAN DEFAULT FALSE
)
RETURNS VOID
LANGUAGE plpgsql AS $$
DECLARE
    v_expense     expenses%ROWTYPE;
    v_exp_acc     INT;
    v_dr_acc      INT;
    v_cgst_acc    INT;
    v_sgst_acc    INT;
    v_igst_acc    INT;
    v_itc_acc     INT;
    v_journal_id  INT;
    v_vendor_id   INT;
    v_rcm_cat     VARCHAR(50);
BEGIN
    SELECT * INTO v_expense
      FROM expenses WHERE id = p_expense_id AND society_id = p_society_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Expense % not found', p_expense_id; END IF;

    v_exp_acc   := v_expense.acc_id;
    v_vendor_id := v_expense.entity_id;
    v_rcm_cat   := COALESCE(v_expense.rcm_category, '');

    SELECT rcm.cgst_acc_id, rcm.sgst_acc_id, rcm.igst_acc_id, rcm.itc_acc_id
      INTO v_cgst_acc, v_sgst_acc, v_igst_acc, v_itc_acc
      FROM fn_resolve_rcm_gst_accounts(p_society_id) AS rcm;

    -- Dr side: recoverable GST goes to Input Tax Credit (RCM), an asset
    -- account, rather than re-inflating the operating expense account —
    -- previously both CGST and SGST legs debited the expense account
    -- even though the comment called it "ITC claimable". Non-eligible
    -- (unregistered/below-threshold) liability still expenses it, since
    -- it's genuinely not recoverable in that case.
    IF p_itc_eligible AND v_itc_acc IS NOT NULL THEN
        v_dr_acc := v_itc_acc;
    ELSE
        v_dr_acc := v_exp_acc;
        IF p_itc_eligible THEN
            RAISE WARNING 'RCM liability for expense % debited to expense account: Input Tax Credit (RCM) account not configured for society %',
                p_expense_id, p_society_id;
        END IF;
    END IF;

    IF (p_cgst > 0 OR p_sgst > 0) AND (v_cgst_acc IS NULL OR v_sgst_acc IS NULL) THEN
        RAISE WARNING 'RCM liability for expense % not posted to ledger: CGST/SGST Payable (RCM) accounts not configured for society % — liability recorded in rcm_liability table only',
            p_expense_id, p_society_id;
    END IF;
    IF p_igst > 0 AND v_igst_acc IS NULL THEN
        RAISE WARNING 'RCM liability for expense % not posted to ledger: IGST Payable (RCM) account not configured for society % — liability recorded in rcm_liability table only',
            p_expense_id, p_society_id;
    END IF;

    v_journal_id := NEXTVAL('seq_transaction_number');

    INSERT INTO rcm_liability (
        society_id, expense_id, vendor_id, rcm_category,
        taxable_value, cgst_amount, sgst_amount, igst_amount, itc_eligible,
        liability_date, created_by
    ) VALUES (
        p_society_id, p_expense_id, v_vendor_id, v_rcm_cat,
        v_expense.amount, p_cgst, p_sgst, p_igst, p_itc_eligible,
        v_expense.expense_date, v_expense.user_id
    );

    IF v_cgst_acc IS NOT NULL AND p_cgst > 0 THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            p_society_id, 'Dr', v_expense.expense_date, v_dr_acc, v_vendor_id, v_expense.role,
            'RCM CGST — ' || v_expense.particulars,
            p_cgst, 'journal', 'paid', v_expense.user_id, NOW(), 'expenses', p_expense_id, v_journal_id
        );
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            p_society_id, 'Cr', v_expense.expense_date, v_cgst_acc, v_vendor_id, v_expense.role,
            'CGST Payable (RCM) — ' || v_expense.particulars,
            p_cgst, 'journal', 'paid', v_expense.user_id, NOW(), 'expenses', p_expense_id, v_journal_id
        );
    END IF;

    IF v_sgst_acc IS NOT NULL AND p_sgst > 0 THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            p_society_id, 'Dr', v_expense.expense_date, v_dr_acc, v_vendor_id, v_expense.role,
            'RCM SGST — ' || v_expense.particulars,
            p_sgst, 'journal', 'paid', v_expense.user_id, NOW(), 'expenses', p_expense_id, v_journal_id
        );
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            p_society_id, 'Cr', v_expense.expense_date, v_sgst_acc, v_vendor_id, v_expense.role,
            'SGST Payable (RCM) — ' || v_expense.particulars,
            p_sgst, 'journal', 'paid', v_expense.user_id, NOW(), 'expenses', p_expense_id, v_journal_id
        );
    END IF;

    IF v_igst_acc IS NOT NULL AND p_igst > 0 THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            p_society_id, 'Dr', v_expense.expense_date, v_dr_acc, v_vendor_id, v_expense.role,
            'RCM IGST — ' || v_expense.particulars,
            p_igst, 'journal', 'paid', v_expense.user_id, NOW(), 'expenses', p_expense_id, v_journal_id
        );
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            p_society_id, 'Cr', v_expense.expense_date, v_igst_acc, v_vendor_id, v_expense.role,
            'IGST Payable (RCM) — ' || v_expense.particulars,
            p_igst, 'journal', 'paid', v_expense.user_id, NOW(), 'expenses', p_expense_id, v_journal_id
        );
    END IF;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- fn_pay_rcm_liability (2026-09, Phase 3): records the actual cash/bank
-- remittance of RCM tax to the government via GSTR-3B challan —
-- previously there was no such function at all; gstr_filed was a bare
-- compliance flag with no linked real-money leg, making this payment
-- impossible to bank-reconcile. Sums unpaid CGST/SGST/IGST for the
-- society+month, posts one real (non-journal) Cr to the bank/cash
-- account resolved via fn_resolve_bank_leg and a matching Dr clearing
-- each RCM payable account, then marks the covered rcm_liability rows
-- filed. Per Sec. 49(4)/Rule 85, RCM liability must be discharged in
-- cash — this function has no ITC-ledger offset path by design.
-- ════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_pay_rcm_liability(
    p_society_id INT,
    p_month      DATE,
    p_mode       VARCHAR,
    p_bank_ref   VARCHAR DEFAULT NULL,
    p_paid_by    INT     DEFAULT NULL
)
RETURNS TABLE(transaction_id INT, rows_marked INT, total_paid NUMERIC(15,2))
LANGUAGE plpgsql AS $$
DECLARE
    v_cgst_due   NUMERIC(15,2);
    v_sgst_due   NUMERIC(15,2);
    v_igst_due   NUMERIC(15,2);
    v_bank_acc   INT;
    v_cgst_acc   INT;
    v_sgst_acc   INT;
    v_igst_acc   INT;
    v_journal_id INT;
    v_tid        INT;
    v_rows       INT;
BEGIN
    SELECT COALESCE(SUM(cgst_amount), 0), COALESCE(SUM(sgst_amount), 0), COALESCE(SUM(igst_amount), 0)
      INTO v_cgst_due, v_sgst_due, v_igst_due
      FROM rcm_liability
     WHERE society_id = p_society_id AND gstr_filed = FALSE
       AND DATE_TRUNC('month', liability_date) = DATE_TRUNC('month', p_month);

    IF v_cgst_due = 0 AND v_sgst_due = 0 AND v_igst_due = 0 THEN
        transaction_id := NULL; rows_marked := 0; total_paid := 0;
        RETURN NEXT; RETURN;
    END IF;

    SELECT rcm.cgst_acc_id, rcm.sgst_acc_id, rcm.igst_acc_id
      INTO v_cgst_acc, v_sgst_acc, v_igst_acc
      FROM fn_resolve_rcm_gst_accounts(p_society_id) AS rcm;
    v_bank_acc := fn_resolve_bank_leg(p_society_id, p_mode);

    v_journal_id := NEXTVAL('seq_transaction_number');

    -- Dr: clear each RCM payable account (real cash/bank mode — this is
    -- an actual remittance, unlike the accrual legs in fn_post_rcm_liability)
    IF v_cgst_due > 0 AND v_cgst_acc IS NOT NULL THEN
        INSERT INTO transactions(society_id, entry_side, trx_date, acc_id, mode, status,
            acc_particulars, amount, created_by, created_at, journal_id)
        VALUES (p_society_id, 'Dr', p_month, v_cgst_acc, p_mode, 'paid',
            'RCM CGST remittance' || COALESCE(' — Ref ' || p_bank_ref, ''), v_cgst_due, p_paid_by, NOW(), v_journal_id);
    END IF;
    IF v_sgst_due > 0 AND v_sgst_acc IS NOT NULL THEN
        INSERT INTO transactions(society_id, entry_side, trx_date, acc_id, mode, status,
            acc_particulars, amount, created_by, created_at, journal_id)
        VALUES (p_society_id, 'Dr', p_month, v_sgst_acc, p_mode, 'paid',
            'RCM SGST remittance' || COALESCE(' — Ref ' || p_bank_ref, ''), v_sgst_due, p_paid_by, NOW(), v_journal_id);
    END IF;
    IF v_igst_due > 0 AND v_igst_acc IS NOT NULL THEN
        INSERT INTO transactions(society_id, entry_side, trx_date, acc_id, mode, status,
            acc_particulars, amount, created_by, created_at, journal_id)
        VALUES (p_society_id, 'Dr', p_month, v_igst_acc, p_mode, 'paid',
            'RCM IGST remittance' || COALESCE(' — Ref ' || p_bank_ref, ''), v_igst_due, p_paid_by, NOW(), v_journal_id);
    END IF;

    -- Cr: bank/cash leg for the total actually remitted
    INSERT INTO transactions(society_id, entry_side, trx_date, acc_id, mode, status,
        acc_particulars, amount, created_by, created_at, journal_id)
    VALUES (p_society_id, 'Cr', p_month, v_bank_acc, p_mode, 'paid',
        'RCM GST paid to government' || COALESCE(' — Ref ' || p_bank_ref, ''),
        v_cgst_due + v_sgst_due + v_igst_due, p_paid_by, NOW(), v_journal_id)
    RETURNING id INTO v_tid;

    UPDATE rcm_liability
       SET gstr_filed = TRUE, gstr_filed_date = CURRENT_DATE,
           paid_at = NOW(), paid_transaction_id = v_tid
     WHERE society_id = p_society_id AND gstr_filed = FALSE
       AND DATE_TRUNC('month', liability_date) = DATE_TRUNC('month', p_month);
    GET DIAGNOSTICS v_rows = ROW_COUNT;

    transaction_id := v_tid;
    rows_marked := v_rows;
    total_paid := v_cgst_due + v_sgst_due + v_igst_due;
    RETURN NEXT;
END;
$$;

-- SECTION 9: LIST FUNCTIONS (apartments, vendors, security)
-- ════════════════════════════════════════════════════════════════

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

CREATE OR REPLACE FUNCTION fn_vendors_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL,
    p_has_passes BOOLEAN DEFAULT NULL
)
RETURNS TABLE (
    id INT, user_id INT, email VARCHAR(100), society_id INT, name VARCHAR(100),
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

CREATE OR REPLACE FUNCTION fn_security_list(p_society_id INT, p_search TEXT DEFAULT NULL)
RETURNS TABLE (
    id INT, user_id INT, email VARCHAR(100), society_id INT, name VARCHAR(100),
    shift VARCHAR(20), mobile VARCHAR(15), active BOOLEAN, salary_per_shift NUMERIC(10,2),
    joining_date DATE, shift_count BIGINT, shifts_this_month BIGINT, salary_due NUMERIC(15,2), salary_paid NUMERIC(15,2), gate_pass BOOLEAN
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM fn_auto_generate_payables(p_society_id);
    RETURN QUERY
    WITH pay_sum AS (
        SELECT entity_id AS staff_id,
            COUNT(*)::BIGINT AS shift_count,
            COUNT(*) FILTER (WHERE shift_date >= DATE_TRUNC('month', CURRENT_DATE))::BIGINT AS shifts_this_month,
            COALESCE(SUM(amount) FILTER (WHERE status='pending'), 0)::NUMERIC(15,2) AS salary_due,
            COALESCE(SUM(amount) FILTER (WHERE status='verified'), 0)::NUMERIC(15,2) AS salary_paid
        FROM payables p WHERE p.society_id = p_society_id AND p.role = 'security' GROUP BY entity_id
    )
    SELECT
        s.id::INT, u.id::INT, u.email::VARCHAR(100), s.society_id::INT,
        COALESCE(s.name, u.email, 'Security #'||s.id)::VARCHAR(100), COALESCE(s.shift,'—')::VARCHAR(20),
        COALESCE(s.mobile,'—')::VARCHAR(15), COALESCE(s.active,TRUE)::BOOLEAN,
        COALESCE(s.salary_per_shift,0)::NUMERIC(10,2), s.joining_date::DATE,
        COALESCE(ps.shift_count, 0)::BIGINT AS shift_count,
        COALESCE(ps.shifts_this_month, 0)::BIGINT AS shifts_this_month,
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
    last_printed_at TIMESTAMP, last_emailed_at TIMESTAMP, created_at TIMESTAMP,
    reconciled_at TIMESTAMP, reconciled_by INT, bank_statement_line_id INT,
    initiated_by VARCHAR(100)
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
        r.created_at::TIMESTAMP,
        r.reconciled_at::TIMESTAMP, r.reconciled_by::INT, r.bank_statement_line_id::INT,
        COALESCE(u.name, '')::VARCHAR(100) AS initiated_by
    FROM receipts r
    LEFT JOIN accounts      a  ON a.id  = r.acc_id
    LEFT JOIN apartments   ap  ON ap.id = r.entity_id AND r.role = 'apartment'
    LEFT JOIN vendors       v  ON  v.id = r.entity_id AND r.role = 'vendor'
    LEFT JOIN security_staff s ON  s.id = r.entity_id AND r.role = 'security'
    LEFT JOIN users          u ON  u.id = COALESCE(r.user_id, r.created_by)
    WHERE r.society_id = p_society_id
      AND (p_entity_id   IS NULL OR r.entity_id = p_entity_id)
      AND (p_entity_role IS NULL OR r.role = p_entity_role)
      AND (p_search IS NULL
           OR r.particulars ILIKE '%'||p_search||'%'
           OR a.name        ILIKE '%'||p_search||'%')
    ORDER BY r.receipt_date DESC, r.id DESC;
END;
$$;

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
    last_printed_at TIMESTAMP, last_emailed_at TIMESTAMP, created_at TIMESTAMP,
    reconciled_at TIMESTAMP, reconciled_by INT, bank_statement_line_id INT
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
        e.created_at::TIMESTAMP,
        e.reconciled_at::TIMESTAMP, e.reconciled_by::INT, e.bank_statement_line_id::INT
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
        WHERE t.society_id = p_society_id AND t.status = 'paid' AND t.trx_date < v_fy_start
        GROUP BY t.acc_id
    ) t ON t.acc_id = a.id
    WHERE a.parent_account_id = p_account_id AND a.society_id = p_society_id;
 
    RETURN COALESCE(v_bf, 0);
END;
$$;

-- SECTION 4: DEPRECIATION CALCULATION
-- Block-of-Assets WDV method per Section 32 / 43(6)(c) of the Income-tax
-- Act, 1961.
--
-- Fixed (2026-09, CA compliance pass — see fixed_asset_register_compliance
-- patch notes):
--   1. Half-year test was a fixed "1-Sep" calendar cutoff. The actual
--      statutory test (Explanation 5 to sec. 32 / Rule 5) is 180 days of
--      use before FY-end (31 Mar), which falls around 3 Oct, not 1 Sep —
--      the old cutoff wrongly denied full depreciation to any asset put
--      to use between ~1 Sep and ~3 Oct. Replaced with a per-asset day
--      count (fn_asset_gets_full_year_dep helper) so it's exact for every
--      year including leap years, instead of a second hardcoded date.
--   2. Deductions (assets disposed during the FY) were previously ignored
--      by this function entirely — depreciation was charged on the full
--      opening WDV + additions even when part of the block was sold
--      mid-year. Sec. 43(6)(c) requires moneys payable for assets sold
--      during the year to reduce the block BEFORE depreciation is
--      computed on it. Deductions are now netted off (full-rate portion
--      first, spilling into the half-rate portion) before applying the
--      rate.
--   3. If deductions exceed the block's WDV + additions, the block value
--      goes negative — that excess is a short-term capital gain under
--      sec. 50(1), not depreciation, and no depreciation is allowed on
--      the block for that year. This function returns 0 in that case;
--      the STCG figure itself is surfaced by fn_fixed_asset_register_fy
--      (this function's contract is just the P&L depreciation figure).

-- fn_asset_gets_full_year_dep: TRUE if an asset put to use on p_purchase_date
-- has been used for 180 days or more by p_fy_end (statutory test for full
-- vs. half depreciation), FALSE otherwise.

CREATE OR REPLACE FUNCTION fn_asset_gets_full_year_dep(
    p_purchase_date DATE,
    p_fy_end        DATE
) RETURNS BOOLEAN LANGUAGE sql IMMUTABLE AS $$
    SELECT (p_fy_end - p_purchase_date + 1) >= 180;
$$;

-- fn_block_dep_base: shared netting logic — given a block's opening WDV,
-- full-rate additions, half-rate additions, and in-year deductions
-- (moneys payable for disposals), returns (full_rate_base, half_rate_base,
-- stcg). Deductions are absorbed against the full-rate base first (opening
-- WDV + pre-cutoff additions), any excess against the half-rate base
-- (post-cutoff additions), and any further excess is sec. 50(1) STCG with
-- both bases floored at 0.

CREATE OR REPLACE FUNCTION fn_block_dep_base(
    p_opening_wdv NUMERIC,
    p_add_full    NUMERIC,
    p_add_half    NUMERIC,
    p_deductions  NUMERIC
) RETURNS TABLE (full_rate_base NUMERIC, half_rate_base NUMERIC, stcg NUMERIC)
LANGUAGE sql IMMUTABLE AS $$
    SELECT
        GREATEST(COALESCE(p_opening_wdv, 0) + COALESCE(p_add_full, 0) - COALESCE(p_deductions, 0), 0) AS full_rate_base,
        GREATEST(COALESCE(p_add_half, 0) - GREATEST(COALESCE(p_deductions, 0) - (COALESCE(p_opening_wdv, 0) + COALESCE(p_add_full, 0)), 0), 0) AS half_rate_base,
        GREATEST(COALESCE(p_deductions, 0) - (COALESCE(p_opening_wdv, 0) + COALESCE(p_add_full, 0) + COALESCE(p_add_half, 0)), 0) AS stcg;
$$;

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
    v_add_full     NUMERIC(15,2) := 0;
    v_add_half     NUMERIC(15,2) := 0;
    v_deductions   NUMERIC(15,2) := 0;
    v_base         RECORD;
    v_fy_start     DATE := MAKE_DATE(p_financial_year, 4, 1);
    v_fy_end       DATE := MAKE_DATE(p_financial_year + 1, 3, 31);
BEGIN
    SELECT depreciation_percent, is_depreciable
      INTO v_dep_pct, v_is_dep
      FROM accounts WHERE id = p_account_id AND society_id = p_society_id;

    IF NOT FOUND OR NOT COALESCE(v_is_dep, FALSE) OR COALESCE(v_dep_pct, 100) >= 100 THEN
        RETURN 0;
    END IF;

    v_opening_wdv := fn_resolve_bf_amount_fy(p_society_id, p_account_id, p_financial_year);

    SELECT
        COALESCE(SUM(purchase_value) FILTER (WHERE fn_asset_gets_full_year_dep(COALESCE(installation_date, purchase_date), v_fy_end)), 0),
        COALESCE(SUM(purchase_value) FILTER (WHERE NOT fn_asset_gets_full_year_dep(COALESCE(installation_date, purchase_date), v_fy_end)), 0)
      INTO v_add_full, v_add_half
      FROM assets
     WHERE society_id = p_society_id
       AND acc_id = p_account_id
       AND purchase_date BETWEEN v_fy_start AND v_fy_end;
       -- Fixed (2026-09): no "disposed = FALSE" filter here — an asset
       -- bought AND sold within the same FY still adds its cost to the
       -- block per sec. 43(6)(c); its sale proceeds reduce the block
       -- separately via the deductions query below. Excluding it here
       -- silently dropped its acquisition cost from the block entirely.

    -- Deductions: moneys payable for assets of this block disposed during
    -- the FY (fn_dispose_asset posts this as a single Cr leg on the block
    -- account for the actual sale value — see that function's notes).
    SELECT COALESCE(SUM(t.amount), 0) INTO v_deductions
      FROM transactions t
     WHERE t.society_id = p_society_id
       AND t.acc_id = p_account_id
       AND t.entry_side = 'Cr'
       AND t.status = 'paid'
       AND t.source_table = 'assets'
       AND t.trx_date BETWEEN v_fy_start AND v_fy_end;

    SELECT * INTO v_base FROM fn_block_dep_base(v_opening_wdv, v_add_full, v_add_half, v_deductions);

    RETURN ROUND(v_base.full_rate_base * v_dep_pct / 100.0 + v_base.half_rate_base * v_dep_pct / 100.0 * 0.5, 2);
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

-- Same block-netted base as fn_account_depreciation (see that function's
-- header notes for the 2026-09 compliance fixes) — just returned as the
-- (full-rate, half-rate) pair instead of a single total, for the ledger's
-- two-row display. full_amount + half_amount always equals
-- fn_account_depreciation's own total for the same arguments.
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
    v_add_full     NUMERIC(15,2) := 0;
    v_add_half     NUMERIC(15,2) := 0;
    v_deductions   NUMERIC(15,2) := 0;
    v_base         RECORD;
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

    SELECT
        COALESCE(SUM(purchase_value) FILTER (WHERE fn_asset_gets_full_year_dep(COALESCE(installation_date, purchase_date), v_fy_end)), 0),
        COALESCE(SUM(purchase_value) FILTER (WHERE NOT fn_asset_gets_full_year_dep(COALESCE(installation_date, purchase_date), v_fy_end)), 0)
      INTO v_add_full, v_add_half
      FROM assets
     WHERE society_id = p_society_id AND acc_id = p_account_id
       AND purchase_date BETWEEN v_fy_start AND v_fy_end;
       -- Fixed (2026-09): same fix as fn_account_depreciation — no
       -- disposed=FALSE filter; a same-FY buy-then-sell still adds cost
       -- here and is netted via deductions below.

    SELECT COALESCE(SUM(t.amount), 0) INTO v_deductions
      FROM transactions t
     WHERE t.society_id = p_society_id
       AND t.acc_id = p_account_id
       AND t.entry_side = 'Cr'
       AND t.status = 'paid'
       AND t.source_table = 'assets'
       AND t.trx_date BETWEEN v_fy_start AND v_fy_end;

    SELECT * INTO v_base FROM fn_block_dep_base(v_opening_wdv, v_add_full, v_add_half, v_deductions);

    RETURN QUERY SELECT
        ROUND(v_base.full_rate_base * v_dep_pct / 100.0, 2)::NUMERIC(15,2),
        ROUND(v_base.half_rate_base * v_dep_pct / 100.0 * 0.5, 2)::NUMERIC(15,2);
END;
$$;

-- SECTION 5: LEDGER v2 — FY-aware BF + depreciation-aware closing
-- ════════════════════════════════════════════════════════════════

-- Fixed (2026-08): same SMALLINT->INT fix — this backs the live Admin
-- Ledger screen (via loaders.py, plain `%s` placeholders passing a
-- Python int), which was silently broken by this exact type-resolution
-- issue every time it was called.

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
       LEFT JOIN accounts p ON p.id = a.parent_account_id AND p.society_id = a.society_id
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

            v_dep_acc_tab := COALESCE((SELECT tab_name FROM accounts WHERE id = v_dep_acc_id AND society_id = p_society_id), 'Dep');
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
        JOIN accounts a ON a.id = t.acc_id AND a.society_id = t.society_id
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
        JOIN accounts a ON a.id = t.acc_id AND a.society_id = t.society_id
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
LANGUAGE plpgsql VOLATILE AS $$
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

    -- A second call in the same transaction (a loop over months, a report
    -- that fetches several pages) would fail with "relation _cb_month_rows
    -- already exists" because ON COMMIT DROP only fires at commit. This DROP
    -- is not a legacy-schema guard — the temp table is created by the
    -- statement two lines below, in this same function.
    DROP TABLE IF EXISTS _cb_month_rows;
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
        JOIN accounts a ON a.id = t.acc_id AND a.society_id = t.society_id
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
        JOIN accounts a ON a.id = t.acc_id AND a.society_id = t.society_id
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
-- below), same convention as fn_resolve_cash_account. Passing the account id
-- in explicitly would need a dedicated societies.dep_account_id column that
-- nothing else reads; the chart of accounts is already the source of truth for
-- which account a society uses for a given purpose.
-- Income & Expenditure and Capital Account are still reached purely via
-- the parent_account_id hierarchy walk below, not by name at all.

-- Resolves a society's 'Dep' (Depreciation) account by name, same ILIKE
-- convention as fn_resolve_cash_account. No dedicated societies column
-- needed — a name lookup keeps the Depreciation account's home in the
-- chart of accounts instead of in societies.
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

-- Fixed (2026-08): p_fy was SMALLINT, so a plain integer argument ("function
-- fn_fy_closing_report(integer, integer) does not exist") failed to resolve —
-- which is what both loaders.py and any raw SQL literal test naturally pass.
-- p_fy is INT below. Depreciation is resolved by name
-- (fn_resolve_depreciation_account) rather than taken as a caller-supplied
-- parameter; see that function's comment.

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
      sort_path            TEXT,
      -- Jurisdiction-aware statutory metadata (added 2026-09)
      statutory_head_code       VARCHAR(50),
      statutory_head_label      VARCHAR(200),
      statutory_statement_section VARCHAR(20),
      statutory_display_order   INT
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
                WHEN a.tab_name = 'CiH'                 THEN 
                    COALESCE((
                        SELECT SUM(
                            CASE WHEN t.entry_side = 'Dr' THEN t.amount
                                 WHEN t.entry_side = 'Cr' THEN -t.amount
                                 ELSE 0 END
                        )
                        FROM transactions t
                        WHERE t.society_id = p_society_id AND t.status = 'paid' AND t.mode = 'cash'
                          AND (t.bank_reconciled = TRUE OR t.bank_reconciled IS NULL)
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
                          AND (t.bank_reconciled = TRUE OR t.bank_reconciled IS NULL)
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
    ),
    -- Jurisdiction-aware statutory head resolution
    regime AS (
        SELECT slr.regime_code
        FROM society_legal_regime slr
        WHERE slr.society_id = p_society_id
          AND slr.effective_from <= MAKE_DATE(p_fy + 1, 3, 31)
          AND (slr.effective_to IS NULL OR slr.effective_to >= MAKE_DATE(p_fy, 4, 1))
        ORDER BY slr.effective_from DESC
        LIMIT 1
    ),
    statutory_map AS (
        SELECT asm.account_id, shc.head_code, shc.label, shc.statement_section, shc.display_order
        FROM account_statutory_mappings asm
        JOIN statutory_head_catalog shc
          ON shc.regime_code = asm.regime_code AND shc.head_code = asm.head_code
        JOIN regime rg ON rg.regime_code = asm.regime_code
        WHERE asm.society_id = p_society_id
          AND asm.effective_from <= MAKE_DATE(p_fy + 1, 3, 31)
          AND (asm.effective_to IS NULL OR asm.effective_to >= MAKE_DATE(p_fy, 4, 1))
          AND shc.effective_from <= MAKE_DATE(p_fy + 1, 3, 31)
          AND (shc.effective_to IS NULL OR shc.effective_to >= MAKE_DATE(p_fy, 4, 1))
    )
    SELECT
        lf.id, lf.name, lf.tab_name, lf.parent_account_id, lf.drcr_account, lf.has_bf,
        lf.own_bf, lf.own_movement, lf.depreciation_charge, lf.own_closing,
        r.total_closing,
        CASE WHEN r.total_closing >= 0 THEN 'Cr' ELSE 'Dr' END,
        ABS(r.total_closing),
        lf.depth,
        lf.sort_path,
        sm.head_code AS statutory_head_code,
        sm.label AS statutory_head_label,
        sm.statement_section AS statutory_statement_section,
        sm.display_order AS statutory_display_order
    FROM leaf_final lf
    JOIN rollup r ON r.id = lf.id
    LEFT JOIN statutory_map sm ON sm.account_id = lf.id
        ORDER BY lf.sort_path;
END;
$$;

-- ═════════════════════════════════════════════════════════════════════════════
-- SECTION 12b: THREE-STATEMENT FINANCIAL REPORTS (P2 Item 1)
-- ═════════════════════════════════════════════════════════════════════════════

-- fn_receipts_payments_fy
-- =========================
-- Receipts & Payments Account (Cash Basis) for a given FY.
-- Returns: line_type ('Opening'|'Receipt'|'Payment'|'Closing'), account_code,
-- account_name, dr_amount, cr_amount
-- Logic:
--   1. Opening balances of cash/bank accounts from fn_fy_closing_report
--   2. Receipts: all cash/bank receipt transactions (mode IN cash/cheque/upi/card/bank/crypto)
--      grouped by income account (Cr side, drcr_account='Cr')
--   3. Payments: all cash/bank expense transactions grouped by expense account
--      (Dr side, drcr_account='Dr')
--   4. Closing balances of cash/bank accounts from fn_fy_closing_report
-- Journal entries (mode='journal') are excluded (non-cash).
-- Traditional two-column format: Dr column = Receipts, Cr column = Payments.

CREATE OR REPLACE FUNCTION fn_receipts_payments_fy(
    p_society_id INT,
    p_fy         INT
)
RETURNS TABLE (
    line_type    VARCHAR,
    account_code INT,
    account_name VARCHAR,
    dr_amount    NUMERIC(15,2),
    cr_amount    NUMERIC(15,2)
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_fy_start DATE := MAKE_DATE(p_fy, 4, 1);
    v_fy_end   DATE := MAKE_DATE(p_fy + 1, 3, 31);
BEGIN
    RETURN QUERY
    WITH closing AS (
        SELECT * FROM fn_fy_closing_report(p_society_id, p_fy)
    ),
    bkac_base AS (
        SELECT sort_path FROM closing WHERE tab_name = 'BkAc' LIMIT 1
    ),
    cash_bank_accs AS (
        SELECT c.account_id, c.account_name, c.own_bf, c.total_closing
        FROM closing c
        CROSS JOIN bkac_base b
        WHERE c.tab_name = 'CiH'
           OR (b.sort_path IS NOT NULL AND c.sort_path LIKE b.sort_path || '.%')
    ),
    receipts AS (
        -- Fixed (2026-09, live-tested): previously required a.drcr_account
        -- = 'Cr', which silently dropped any real-cash Cr-leg against a
        -- Dr-natured account (e.g. a refund credited back reducing an
        -- asset/expense account). Keying off "not the cash/bank leg
        -- itself" instead of the account's fixed nature is the general,
        -- correct condition for a cash-basis Receipts & Payments Account.
        SELECT 'Receipt'::VARCHAR AS line_type,
               t.acc_id::INT AS account_code,
               a.name::VARCHAR AS account_name,
               SUM(t.amount)::NUMERIC(15,2) AS dr_amount,
               0::NUMERIC(15,2) AS cr_amount
        FROM transactions t
        JOIN accounts a ON a.id = t.acc_id AND a.society_id = p_society_id
        WHERE t.society_id = p_society_id
          AND t.status = 'paid'
          AND t.trx_date BETWEEN v_fy_start AND v_fy_end
          AND t.entry_side = 'Cr'
          AND t.mode IN ('cash', 'cheque', 'upi', 'card', 'bank', 'crypto')
          AND t.acc_id NOT IN (SELECT account_id FROM cash_bank_accs)
        GROUP BY t.acc_id, a.name
    ),
    payments AS (
        -- Fixed (2026-09, live-tested): previously required a.drcr_account
        -- = 'Dr', which silently dropped any real-cash Dr-leg against a
        -- Cr-natured account — e.g. fn_pay_rcm_liability's remittance,
        -- which debits CGST/SGST/IGST Payable (RCM), all Cr-natured
        -- liabilities, with real (non-journal) cash/bank mode. That whole
        -- transaction pair vanished from this statement entirely (its
        -- mirror cash/bank leg is excluded below by definition), silently
        -- understating total cash payments — the same defect will hit any
        -- future liability repayment (e.g. a loan principal repayment)
        -- for the same reason. Same "not the cash/bank leg" fix as receipts.
        SELECT 'Payment'::VARCHAR AS line_type,
               t.acc_id::INT AS account_code,
               a.name::VARCHAR AS account_name,
               0::NUMERIC(15,2) AS dr_amount,
               SUM(t.amount)::NUMERIC(15,2) AS cr_amount
        FROM transactions t
        JOIN accounts a ON a.id = t.acc_id AND a.society_id = p_society_id
        WHERE t.society_id = p_society_id
          AND t.status = 'paid'
          AND t.trx_date BETWEEN v_fy_start AND v_fy_end
          AND t.entry_side = 'Dr'
          AND t.mode IN ('cash', 'cheque', 'upi', 'card', 'bank', 'crypto')
          AND t.acc_id NOT IN (SELECT account_id FROM cash_bank_accs)
        GROUP BY t.acc_id, a.name
    )
    SELECT o.line_type, o.account_code, o.account_name, o.dr_amount, o.cr_amount
    FROM (
        -- Opening balance (single aggregate line)
        SELECT 1 AS sort_order,
               'Opening'::VARCHAR AS line_type,
               NULL::INT AS account_code,
               'Cash & Bank Balances b/f'::VARCHAR AS account_name,
               COALESCE(SUM(CASE WHEN c.own_bf < 0 THEN ABS(c.own_bf) ELSE 0 END), 0)::NUMERIC(15,2) AS dr_amount,
               COALESCE(SUM(CASE WHEN c.own_bf >= 0 THEN c.own_bf ELSE 0 END), 0)::NUMERIC(15,2) AS cr_amount
        FROM cash_bank_accs c
        WHERE c.own_bf IS NOT NULL AND c.own_bf != 0
        HAVING COALESCE(SUM(CASE WHEN c.own_bf < 0 THEN ABS(c.own_bf) ELSE 0 END), 0) > 0
            OR COALESCE(SUM(CASE WHEN c.own_bf >= 0 THEN c.own_bf ELSE 0 END), 0) > 0

        UNION ALL

        -- Receipts
        SELECT 2 AS sort_order, r.line_type, r.account_code, r.account_name, r.dr_amount, r.cr_amount
        FROM receipts r

        UNION ALL

        -- Payments
        SELECT 3 AS sort_order, p.line_type, p.account_code, p.account_name, p.dr_amount, p.cr_amount
        FROM payments p

        UNION ALL

        -- Closing balance (single aggregate line)
        SELECT 4 AS sort_order,
               'Closing'::VARCHAR AS line_type,
               NULL::INT AS account_code,
               'Cash & Bank Balances c/f'::VARCHAR AS account_name,
               COALESCE(SUM(CASE WHEN c.total_closing < 0 THEN ABS(c.total_closing) ELSE 0 END), 0)::NUMERIC(15,2) AS dr_amount,
               COALESCE(SUM(CASE WHEN c.total_closing >= 0 THEN c.total_closing ELSE 0 END), 0)::NUMERIC(15,2) AS cr_amount
        FROM cash_bank_accs c
        WHERE c.total_closing IS NOT NULL AND c.total_closing != 0
        HAVING COALESCE(SUM(CASE WHEN c.total_closing < 0 THEN ABS(c.total_closing) ELSE 0 END), 0) > 0
            OR COALESCE(SUM(CASE WHEN c.total_closing >= 0 THEN c.total_closing ELSE 0 END), 0) > 0
    ) o
    ORDER BY o.sort_order, o.account_name;
END;
$$;

-- fn_income_expenditure_fy
-- ========================
-- Income & Expenditure Account (Accrual Basis) for a given FY.
-- Returns: statement_section ('Income'|'Expenditure'|'Surplus/Deficit'),
-- account_code, account_name, amount
-- Logic:
--   Pulls from fn_fy_closing_report, classifies accounts by:
--   - Capital Account (tab_name='CapAc') descendants = P&L accounts
--   - Income: drcr_account='Cr' (Cr-natured P&L accounts)
--   - Expenditure: drcr_account='Dr' (Dr-natured P&L accounts)
--   - Amount = ABS(total_closing) from fn_fy_closing_report
--   Surplus/Deficit = Total Income - Total Expenditure

CREATE OR REPLACE FUNCTION fn_income_expenditure_fy(
    p_society_id INT,
    p_fy         INT
)
RETURNS TABLE (
    statement_section VARCHAR,
    account_code      INT,
    account_name      VARCHAR,
    amount            NUMERIC(15,2),
    mutuality_nature  VARCHAR(10)
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    WITH closing AS (
        SELECT * FROM fn_fy_closing_report(p_society_id, p_fy)
    ),
    pl_roots AS (
        SELECT sort_path, tab_name
        FROM closing
        WHERE tab_name IN ('Inc', 'Exp')
    ),
    pl_accs AS (
        SELECT c.*, a.mutuality_nature,
               (SELECT pr.tab_name FROM pl_roots pr
                 WHERE c.sort_path LIKE pr.sort_path || '.%'
                 ORDER BY pr.sort_path
                 LIMIT 1) AS block_tab
        FROM closing c
        LEFT JOIN accounts a ON a.id = c.account_id AND a.society_id = p_society_id
        WHERE c.own_closing IS NOT NULL
          AND c.own_closing != 0
          AND EXISTS (
              SELECT 1 FROM pl_roots pr
              WHERE c.sort_path LIKE pr.sort_path || '.%'
          )
    ),
    income_accs AS (
        -- Fixed alongside the above: ABS(total_closing) turned a
        -- reversing/contra entry against a Cr-natured account (own_closing
        -- negative — e.g. that same depreciation-transfer entry, a Dr
        -- posting against the Cr-natured "Income Expenditure A/c") into
        -- fake extra positive income instead of correctly reducing it.
        -- own_closing's natural sign is honest here: a genuine reversal
        -- shows as a negative income line rather than silently inflating
        -- the total.
        SELECT 'Income'::VARCHAR AS statement_section,
               pa.account_id::INT AS account_code,
               pa.account_name::VARCHAR AS account_name,
               pa.own_closing::NUMERIC(15,2) AS amount,
               pa.mutuality_nature
        FROM pl_accs pa
        WHERE pa.block_tab = 'Inc'
    ),
    expense_accs AS (
        SELECT 'Expenditure'::VARCHAR AS statement_section,
               pa.account_id::INT AS account_code,
               pa.account_name::VARCHAR AS account_name,
               (-pa.own_closing)::NUMERIC(15,2) AS amount,
               pa.mutuality_nature
        FROM pl_accs pa
        WHERE pa.block_tab = 'Exp'
    ),
    totals AS (
        SELECT COALESCE(SUM(ia.amount), 0) AS income_total
        FROM income_accs ia
    )
    SELECT o.statement_section, o.account_code, o.account_name, o.amount, o.mutuality_nature
    FROM (
        SELECT 1 AS sort_order, i.statement_section, i.account_code, i.account_name, i.amount, i.mutuality_nature
        FROM income_accs i
        UNION ALL
        SELECT 2, e.statement_section, e.account_code, e.account_name, e.amount, e.mutuality_nature
        FROM expense_accs e
        UNION ALL
        SELECT 3, 'Surplus/Deficit'::VARCHAR, NULL::INT,
               CASE WHEN t.income_total >= (SELECT COALESCE(SUM(ea.amount),0) FROM expense_accs ea)
                    THEN 'Surplus' ELSE 'Deficit' END,
               ABS(t.income_total - (SELECT COALESCE(SUM(ea.amount),0) FROM expense_accs ea))::NUMERIC(15,2),
               NULL::VARCHAR
        FROM totals t
    ) o
    ORDER BY o.sort_order, o.account_name;
END;
$$;

-- fn_balance_sheet_fy
-- ===================
-- Balance Sheet (Position Statement) for a given FY.
-- Returns: statement_section ('Assets'|'Liabilities'|'Equity'),
-- account_code, account_name, amount, mutuality_nature,
-- statutory_head_code, statutory_head_label, statutory_statement_section, statutory_display_order
-- Logic:
--   Uses fn_fy_closing_report closing balances.
--   Assets: drcr_account='Dr' AND NOT under Capital Account
--   Liabilities: drcr_account='Cr' AND NOT under Capital Account
--   Equity: Capital Account (tab_name='CapAc') + Surplus/Deficit from I&E
--   Amount = ABS(total_closing) with proper sign per section

CREATE OR REPLACE FUNCTION fn_balance_sheet_fy(
    p_society_id INT,
    p_fy         INT
)
RETURNS TABLE (
    statement_section       VARCHAR,
    account_code            INT,
    account_name            VARCHAR,
    amount                  NUMERIC(15,2),
    mutuality_nature        VARCHAR(10),
    statutory_head_code     VARCHAR(50),
    statutory_head_label    VARCHAR(200),
    statutory_statement_section VARCHAR(20),
    statutory_display_order INT
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    WITH closing AS (
        SELECT * FROM fn_fy_closing_report(p_society_id, p_fy)
    ),
    cap_ac AS (
        SELECT sort_path FROM closing WHERE tab_name = 'CapAc' LIMIT 1
    ),
    pl_roots AS (
        SELECT sort_path FROM closing WHERE tab_name IN ('Inc', 'Exp')
    ),
    bs_accs AS (
        SELECT c.*, a.mutuality_nature
        FROM closing c
        LEFT JOIN accounts a ON a.id = c.account_id AND a.society_id = p_society_id
        CROSS JOIN cap_ac ca
        WHERE c.own_closing IS NOT NULL
          AND (ca.sort_path IS NULL
               OR (c.sort_path NOT LIKE ca.sort_path || '.%'
                   AND c.sort_path != ca.sort_path))
          AND NOT EXISTS (
              SELECT 1 FROM pl_roots pr
              WHERE c.sort_path = pr.sort_path
                 OR c.sort_path LIKE pr.sort_path || '.%'
          )
    ),
    asset_accs AS (
        -- Fixed alongside the above: the previous "ABS if negative, else
        -- pass through" logic assumed a Dr-natured account can only ever
        -- have a normal (negative-total_closing) balance. Cash-in-Hand
        -- proved that wrong live: when cash-mode outflows exceed inflows
        -- for the year, its own_closing goes positive (a genuine net cash
        -- shortfall), and the old logic passed that through as a false
        -- positive asset instead of the true negative position — silently
        -- overstating Assets by double the shortfall. Unconditionally
        -- negating own_closing is correct for both the normal and
        -- shortfall cases, and shows a real deficit honestly as negative
        -- rather than hiding it.
        SELECT 'Assets'::VARCHAR AS statement_section,
               ba.account_id::INT AS account_code,
               ba.account_name::VARCHAR AS account_name,
               (-ba.own_closing)::NUMERIC(15,2) AS amount,
               ba.mutuality_nature,
               ba.statutory_head_code,
               ba.statutory_head_label,
               ba.statutory_statement_section,
               ba.statutory_display_order
        FROM bs_accs ba
        WHERE ba.drcr_account = 'Dr'
    ),
    liability_accs AS (
        SELECT 'Liabilities'::VARCHAR AS statement_section,
               ba.account_id::INT AS account_code,
               ba.account_name::VARCHAR AS account_name,
               ba.own_closing::NUMERIC(15,2) AS amount,
               ba.mutuality_nature,
               ba.statutory_head_code,
               ba.statutory_head_label,
               ba.statutory_statement_section,
               ba.statutory_display_order
        FROM bs_accs ba
        WHERE ba.drcr_account = 'Cr'
    ),
    ie_surplus AS (
        SELECT COALESCE(SUM(c.own_closing), 0) AS surplus
        FROM closing c
        WHERE c.own_closing IS NOT NULL
          AND c.own_closing != 0
          AND EXISTS (
              SELECT 1 FROM pl_roots pr
              WHERE c.sort_path LIKE pr.sort_path || '.%'
          )
    ),
    cap_ac_own AS (
        SELECT c.account_id, c.account_name, c.own_closing, a.mutuality_nature,
               c.statutory_head_code, c.statutory_head_label,
               c.statutory_statement_section, c.statutory_display_order
        FROM closing c
        CROSS JOIN cap_ac ca
        LEFT JOIN accounts a ON a.id = c.account_id AND a.society_id = p_society_id
        WHERE ca.sort_path IS NOT NULL
          AND c.sort_path = ca.sort_path
          AND c.own_closing IS NOT NULL
    )
    SELECT o.statement_section, o.account_code, o.account_name, o.amount, o.mutuality_nature,
           o.statutory_head_code, o.statutory_head_label, o.statutory_statement_section, o.statutory_display_order
    FROM (
        SELECT 1 AS sort_order, a.statement_section, a.account_code, a.account_name, a.amount, a.mutuality_nature,
               a.statutory_head_code, a.statutory_head_label, a.statutory_statement_section, a.statutory_display_order
        FROM asset_accs a
        UNION ALL
        SELECT 2, l.statement_section, l.account_code, l.account_name, l.amount, l.mutuality_nature,
               l.statutory_head_code, l.statutory_head_label, l.statutory_statement_section, l.statutory_display_order
        FROM liability_accs l
        UNION ALL
        SELECT 3, 'Equity'::VARCHAR, c.account_id::INT,
               c.account_name::VARCHAR,
               c.own_closing::NUMERIC(15,2),
               c.mutuality_nature,
               c.statutory_head_code, c.statutory_head_label, c.statutory_statement_section, c.statutory_display_order
        FROM cap_ac_own c
        UNION ALL
        SELECT 3, 'Equity'::VARCHAR, NULL::INT,
               'Reserves & Surplus'::VARCHAR,
               s.surplus::NUMERIC(15,2),
               NULL,
               'ACCUMULATED_SURPLUS'::VARCHAR,
               'Accumulated Surplus / Deficit'::VARCHAR,
               'Equity'::VARCHAR,
               20
        FROM ie_surplus s
    ) o
    ORDER BY o.sort_order, o.statutory_display_order NULLS LAST, o.account_name;
END;
$$;

-- Trailing / FY-scoped turnover from Cr-side income transactions.
-- Used for the GST threshold check (society-level ₹20L) and for
-- determining filing cadence. Computed on demand, never stored.

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
      JOIN accounts a ON a.id = t.acc_id AND a.society_id = t.society_id
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
--   2. The full schema + seed now installs cleanly against a live PG16
--      instance, but the specific fixture below is still unverified:
--      a depreciable asset with both opening WDV and an in-year purchase,
--      to confirm fn_account_depreciation's two components both flow
--      through correctly.
-- ═════════════════════════════════════════════════
-- SECTION 13: GATE LOGS
-- ════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_gate_logs_named(
    p_society_id INT,
    p_search     TEXT DEFAULT NULL,
    p_date       DATE DEFAULT NULL
)
RETURNS TABLE (
    id INT, society_id INT, role VARCHAR(3), entity_id INT,
    entity_name TEXT, time_in TIMESTAMP, time_out TIMESTAMP, duration_min INT, scanned_by TEXT
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        g.id::INT, g.society_id::INT, g.role::VARCHAR(3), g.entity_id::INT,
        CASE
            WHEN g.role = 'APT' THEN COALESCE(ap.flat_number||' — '||COALESCE(ap.owner_name,''), 'Apt #'||g.entity_id::TEXT)
            WHEN g.role = 'VND' THEN COALESCE(v.name||COALESCE(' ('||v.service_type||')',''), 'Vendor #'||g.entity_id::TEXT)
            WHEN g.role = 'SEC' THEN COALESCE(ss.name||COALESCE(' ('||ss.shift||')',''), 'Security #'||g.entity_id::TEXT)
            WHEN g.role = 'ADM' THEN COALESCE(u.name, u.email, 'Admin #'||g.entity_id::TEXT)
            ELSE 'Unknown #'||g.entity_id::TEXT
        END::TEXT,
        g.time_in::TIMESTAMP, g.time_out::TIMESTAMP,
        CASE WHEN g.time_out IS NOT NULL
             THEN EXTRACT(EPOCH FROM (g.time_out - g.time_in))::INT / 60
             ELSE NULL END::INT,
        COALESCE(
            CASE WHEN creator.role = 'security' THEN (SELECT s.name FROM security_staff s WHERE s.id = creator.linked_id)
                 ELSE creator.name 
            END, 
            creator.email, 
            'System'
        )::TEXT AS scanned_by
    FROM gate_access g
    LEFT JOIN apartments   ap ON ap.id = g.entity_id AND g.role = 'APT'
    LEFT JOIN vendors       v ON  v.id = g.entity_id AND g.role = 'VND'
    LEFT JOIN security_staff ss ON ss.id = g.entity_id AND g.role = 'SEC'
    LEFT JOIN users         u ON u.id = g.entity_id AND g.role = 'ADM'
    LEFT JOIN users   creator ON creator.id = g.created_by
    WHERE g.society_id = p_society_id
      AND (p_date   IS NULL OR g.time_in::DATE = p_date)
      AND (p_search IS NULL OR CASE
           WHEN g.role='APT' THEN ap.flat_number||' '||COALESCE(ap.owner_name,'')
           WHEN g.role='VND' THEN v.name
           WHEN g.role='SEC' THEN ss.name
           WHEN g.role='ADM' THEN u.name
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
                          END + COALESCE(MAX(CASE WHEN bf.drcr_bf = a.drcr_account
                                   THEN bf.bf_amount ELSE -bf.bf_amount END), 0))
               END::NUMERIC(15,2) AS current_balance,
               COUNT(t.id)::INT AS transaction_count
        FROM accounts a
        LEFT JOIN transactions t ON t.acc_id = a.id AND t.society_id = a.society_id
                              AND t.status = 'paid'
                              AND t.trx_date BETWEEN MAKE_DATE(fn_current_financial_year(), 4, 1)
                                       AND MAKE_DATE(fn_current_financial_year() + 1, 3, 31)
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
    LEFT JOIN accounts p ON p.id = a.parent_account_id AND p.society_id = a.society_id
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
                   END + COALESCE(MAX(CASE WHEN bf.drcr_bf = a.drcr_account
                                   THEN bf.bf_amount ELSE -bf.bf_amount END), 0))
             END)::NUMERIC(15,2),
        COUNT(t.id)::INT,
        COALESCE(p.name,'—')::VARCHAR(100)
    FROM accounts a
    LEFT JOIN accounts p ON p.id = a.parent_account_id AND p.society_id = a.society_id
    LEFT JOIN transactions t ON t.acc_id = a.id AND t.society_id = a.society_id
                              AND t.status = 'paid'
                              AND t.trx_date BETWEEN MAKE_DATE(fn_current_financial_year(), 4, 1)
                                       AND MAKE_DATE(fn_current_financial_year() + 1, 3, 31)
    LEFT JOIN brought_forward bf ON bf.acc_id = a.id AND bf.society_id = a.society_id
                                 AND bf.financial_year = fn_current_financial_year()
    WHERE a.society_id = p_society_id
      AND (p_tab_name IS NULL OR a.tab_name = p_tab_name)
      AND (p_search   IS NULL OR a.name ILIKE '%'||p_search||'%')
    GROUP BY a.id, a.name, a.tab_name, a.header, a.drcr_account, p.name
    ORDER BY a.tab_name NULLS LAST, a.id;
END;
$$;

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
                   END + COALESCE(MAX(CASE WHEN bf.drcr_bf = a.drcr_account
                                   THEN bf.bf_amount ELSE -bf.bf_amount END), 0))
             END)::NUMERIC(15,2),
        a.created_at::TIMESTAMP
    FROM accounts a
    LEFT JOIN accounts p ON p.id = a.parent_account_id AND p.society_id = a.society_id
    LEFT JOIN transactions t ON t.acc_id = a.id AND t.society_id = a.society_id
                              AND t.status = 'paid'
                              AND t.trx_date BETWEEN MAKE_DATE(fn_current_financial_year(), 4, 1)
                                       AND MAKE_DATE(fn_current_financial_year() + 1, 3, 31)
    LEFT JOIN brought_forward bf ON bf.acc_id = a.id AND bf.society_id = a.society_id
                                 AND bf.financial_year = fn_current_financial_year()
    WHERE a.id = p_account_id AND a.society_id = p_society_id
    GROUP BY a.id, a.society_id, a.name, a.tab_name, a.header, a.drcr_account,
             a.depreciation_percent, a.is_depreciable, p.name, a.created_at;
$$;

-- SECTION 15: SOCIETIES LIST / PROFILE
-- ════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_societies_list(
    p_search     TEXT    DEFAULT NULL,
    p_plan       VARCHAR DEFAULT NULL,
    p_status     VARCHAR DEFAULT NULL,
    p_society_id INT     DEFAULT NULL
)
RETURNS TABLE (
    id INT, name VARCHAR(100), PAN_number VARCHAR(10), TAN_number VARCHAR(10), logo VARCHAR(100),
    address TEXT, email VARCHAR(100), phone VARCHAR(20), secretary_name VARCHAR(100),
    secretary_phone VARCHAR(20), secretary_email VARCHAR(100), secretary_sign VARCHAR(100),
    payment_qr VARCHAR(255), plan VARCHAR(20), plan_validity DATE, calc_start_date DATE,
    login_background VARCHAR(100), created_at TIMESTAMP, gstin VARCHAR(15),
    registration_number VARCHAR(100), signing_secret_enc TEXT, primary_bank_account_id INT,
    plan_status VARCHAR(10), total_apartments INT, total_users INT, total_receivables NUMERIC(15,2)
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.id::INT, s.name::VARCHAR(100), s.PAN_number::VARCHAR(10), s.TAN_number::VARCHAR(10), s.logo::VARCHAR(100),
        s.address::TEXT, s.email::VARCHAR(100), s.phone::VARCHAR(20), s.secretary_name::VARCHAR(100),
        s.secretary_phone::VARCHAR(20), s.secretary_email::VARCHAR(100), s.secretary_sign::VARCHAR(100),
        s.payment_qr::VARCHAR(255), s.plan::VARCHAR(20), s.plan_validity::DATE, s.calc_start_date::DATE,
        s.login_background::VARCHAR(100), s.created_at::TIMESTAMP, s.gstin::VARCHAR(15),
        s.registration_number::VARCHAR(100), s.signing_secret_enc::TEXT, s.primary_bank_account_id::INT,
        CASE WHEN s.plan='Free' THEN 'Free'
             WHEN s.plan_validity >= CURRENT_DATE THEN 'Active'
             ELSE 'Expired' END::VARCHAR(10),
        (SELECT COUNT(*)::INT FROM apartments WHERE society_id=s.id AND active=TRUE),
        (SELECT COUNT(*)::INT FROM users        WHERE society_id=s.id),
        (SELECT COALESCE(SUM(amount-paid_amount),0)::NUMERIC(15,2)
         FROM receivables WHERE society_id=s.id AND status IN ('pending','partial'))
    FROM societies s
    WHERE (p_search     IS NULL OR s.name ILIKE '%'||p_search||'%')
      AND (p_plan       IS NULL OR s.plan = p_plan)
      AND (p_society_id IS NULL OR s.id = p_society_id)
      AND (p_status IS NULL OR
           (p_status = 'expired' AND s.plan_validity < CURRENT_DATE) OR
           (p_status = 'expiring_soon' AND s.plan_validity <= CURRENT_DATE + INTERVAL '30 days' AND s.plan_validity >= CURRENT_DATE)
          )
    ORDER BY s.name;
END;
$$;

CREATE OR REPLACE FUNCTION fn_society_profile(p_society_id INT)
RETURNS TABLE (
    id INT, name VARCHAR(100), logo VARCHAR(100), login_background VARCHAR(100),
    email VARCHAR(100), phone VARCHAR(20), address TEXT, plan VARCHAR(20),
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

CREATE OR REPLACE FUNCTION fn_events_list(
    p_society_id INT, p_search TEXT DEFAULT NULL, p_status VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id INT, title VARCHAR(200), description TEXT, event_date DATE, event_time VARCHAR(20),
    venue VARCHAR(200), open_to VARCHAR(20), account_id INT,
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
        e.account_id::INT,
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

CREATE OR REPLACE FUNCTION fn_event_profile(p_event_id INT)
RETURNS TABLE (
    id INT, society_id INT, title VARCHAR(200), description TEXT, event_date DATE,
    event_time VARCHAR(20), venue VARCHAR(200), open_to VARCHAR(20),
    account_id INT,
    ticket_name VARCHAR(20), ticket_price NUMERIC(10,2),
    ticket_name2 VARCHAR(20), ticket_price2 NUMERIC(10,2),
    created_at TIMESTAMP, image TEXT, subtitle TEXT
)
LANGUAGE SQL STABLE AS $$
    SELECT id::INT, society_id::INT, title::VARCHAR(200), description::TEXT,
           event_date::DATE, event_time::VARCHAR(20), venue::VARCHAR(200),
           open_to::VARCHAR(20), account_id::INT,
           ticket_name::VARCHAR(20), ticket_price::NUMERIC(10,2),
           ticket_name2::VARCHAR(20), ticket_price2::NUMERIC(10,2),
           created_at::TIMESTAMP, image::TEXT,
           (event_date::TEXT||' '||COALESCE(event_time::TEXT,''))::TEXT
    FROM events WHERE id = p_event_id;
$$;

CREATE OR REPLACE FUNCTION fn_concern_profile(p_concern_id INT, p_society_id INT)
RETURNS TABLE (
    id INT, society_id INT, apartment_id INT, concern_type VARCHAR(50),
    description TEXT, status VARCHAR(20), assigned_to VARCHAR(100),
    preferred_time TIME, days_open BIGINT, created_at TIMESTAMP, image TEXT, subtitle TEXT,
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
           c.preferred_time::TIME,
           EXTRACT(DAY FROM AGE(CURRENT_DATE, c.created_at))::BIGINT,
           c.created_at::TIMESTAMP, c.image::TEXT,
           ('Flat '||COALESCE(a.flat_number, c.apartment_id::TEXT)||' - '||c.concern_type)::TEXT,
           a.flat_number::VARCHAR(20)
    FROM concerns c
    LEFT JOIN apartments a ON a.id = c.apartment_id AND a.society_id = c.society_id
    WHERE c.id = p_concern_id
      AND c.society_id = p_society_id;
$$;

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

-- SECTION 17: ASSET REGISTER LIST / PROFILE
-- ════════════════════════════════════════════════════════════════

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
    LEFT JOIN accounts a ON a.id = ar.acc_id AND a.society_id = ar.society_id
    WHERE ar.society_id = p_society_id
      AND ar.disposed = COALESCE(p_disposed, FALSE)
      AND (p_search IS NULL OR ar.asset_name ILIKE '%'||p_search||'%')
    ORDER BY ar.purchase_date DESC;
END;
$$;

-- fn_asset_holdings_fy (2026-09): "ALL Holdings" Financial Statement —
-- the complete tangible fixed-asset register: every asset ever purchased,
-- active or already disposed, NOT filtered down to active-only, sorted by
-- sell/disposal date (still-active assets, which have no disposed_at,
-- sort last). Each row has a per-asset STCG/LTCG split by the standard
-- 36-month holding-period test (sec 2(42A), movable property other than
-- listed securities).
--
-- IMPORTANT caveat this statement does NOT override: for depreciable
-- business assets forming part of a block, sec 50 of the Income Tax Act
-- deems ANY gain on disposal to be SHORT-TERM regardless of holding
-- period — that block-of-assets STCG/STCL treatment is what
-- fn_fixed_asset_register_fy / asset_export.py already compute and is
-- what actually gets filed. This per-asset 36-month STCG/LTCG split is a
-- supplementary informational view for the "ALL Holdings" register
-- (matches how this statement's sibling "ALL Deposits" is computed), not
-- a second, conflicting tax position — say so wherever both are shown
-- together (e.g. an export workbook) so a reader doesn't mistake one for
-- overriding the other. p_fy is accepted for interface symmetry with the
-- other statements but unused: this is an all-time register, not FY-scoped.

CREATE OR REPLACE FUNCTION fn_asset_holdings_fy(
    p_society_id INT,
    p_fy         INT DEFAULT NULL
)
RETURNS TABLE (
    name           TEXT,
    ref_no         TEXT,
    purchase_date  DATE,
    exit_date      DATE,
    purchase_value NUMERIC(12,2),
    sale_value     NUMERIC(12,2),
    stcg           NUMERIC(12,2),
    ltcg           NUMERIC(12,2),
    closing_wdv    NUMERIC(12,2)   -- per-asset written-down value (see note below)
)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT
        a.asset_name::TEXT,
        a.asset_sno::TEXT,
        a.purchase_date,
        a.disposed_at,
        a.purchase_value,
        a.sale_value,
        CASE WHEN a.disposed AND a.sale_value IS NOT NULL
                  AND a.disposed_at <= a.purchase_date + INTERVAL '3 years'
             THEN ROUND(a.sale_value - a.purchase_value, 2) ELSE 0 END,
        CASE WHEN a.disposed AND a.sale_value IS NOT NULL
                  AND a.disposed_at > a.purchase_date + INTERVAL '3 years'
             THEN ROUND(a.sale_value - a.purchase_value, 2) ELSE 0 END,
        -- Per-asset Closing WDV (supplementary informational figure — NOT the
        -- sec. 43(6)(c) block WDV that actually gets filed). The schema
        -- tracks depreciation at the BLOCK/account level (fn_account_depreciation,
        -- fn_fixed_asset_register_fy), never per-asset, so there is no true
        -- per-asset accumulated-depreciation column to read. This applies the
        -- asset's OWN depreciation_rate straight-line from purchase to the
        -- valuation date (disposal date if sold, else end of FY p_fy, else
        -- today) and subtracts the disposal proceeds. It is a reasonable
        -- approximation for the "ALL Holdings" register's WDV column only —
        -- say so wherever it sits next to the block-level Depreciation
        -- Account statement so a reader doesn't mistake one for the other.
        GREATEST(
            a.purchase_value
            - a.purchase_value * COALESCE(a.depreciation_rate, 0) / 100.0
              * GREATEST(
                  (COALESCE(a.disposed_at,
                            CASE WHEN p_fy IS NOT NULL THEN MAKE_DATE(p_fy + 1, 3, 31)
                                 ELSE CURRENT_DATE END)
                   - a.purchase_date) / 365.25, 0)
            - COALESCE(a.sale_value, 0), 0) AS closing_wdv
    FROM assets a
    WHERE a.society_id = p_society_id
    ORDER BY a.disposed_at ASC NULLS LAST, a.purchase_date DESC;
END;
$$;

-- fn_deposit_holdings_fy (2026-09): "ALL Deposits" Financial Statement —
-- the intangible investment register (FDs, bonds, mutual fund units, etc,
-- tracked in the new `deposits` table below), same shape and same
-- 36-month STCG/LTCG convention as fn_asset_holdings_fy above (see its
-- caveat comment — this split is informational, and for a plain bank FD
-- the maturity gain is actually "Income from Other Sources" under the
-- Income Tax Act, not a capital gain at all; a society's CA should confirm
-- the correct head per instrument type before filing).
--
-- NOTE: the `deposits` table has no data-entry UI yet (no create/dispose
-- form or admin card wired up) — this function and the "ALL Deposits"
-- statement row will correctly show empty until that admin UI is built
-- (tracked as a follow-up; see the patch notes).

CREATE OR REPLACE FUNCTION fn_deposit_holdings_fy(
    p_society_id INT,
    p_fy         INT DEFAULT NULL
)
RETURNS TABLE (
    name           TEXT,
    ref_no         TEXT,
    purchase_date  DATE,
    exit_date      DATE,
    purchase_value NUMERIC(12,2),
    sale_value     NUMERIC(12,2),
    stcg           NUMERIC(12,2),
    ltcg           NUMERIC(12,2),
    closing_wdv    NUMERIC(12,2)   -- per-deposit written-down value (see note below)
)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT
        d.deposit_name::TEXT,
        d.isin::TEXT,
        d.purchase_date,
        d.sale_date,
        d.purchase_value,
        d.sale_value,
        CASE WHEN d.disposed AND d.sale_value IS NOT NULL
                  AND d.sale_date <= d.purchase_date + INTERVAL '3 years'
             THEN ROUND(d.sale_value - d.purchase_value, 2) ELSE 0 END,
        CASE WHEN d.disposed AND d.sale_value IS NOT NULL
                  AND d.sale_date > d.purchase_date + INTERVAL '3 years'
             THEN ROUND(d.sale_value - d.purchase_value, 2) ELSE 0 END,
        -- Per-deposit Closing WDV (supplementary informational figure).
        -- Deposits are intangible investments (FDs, bonds, MF units) — there
        -- is no depreciation_rate column on `deposits` and no block-level
        -- WDV schedule for them, so this is simply the remaining book value:
        -- purchase cost minus disposal proceeds if sold, else the full
        -- purchase cost while still held. It mirrors the ALL Holdings
        -- closing_wdv's intent (a per-row "what this is worth on the books
        -- today") without pretending deposits are depreciable assets.
        CASE WHEN d.disposed AND d.sale_value IS NOT NULL
             THEN GREATEST(d.purchase_value - d.sale_value, 0)
             ELSE d.purchase_value END AS closing_wdv
    FROM deposits d
    WHERE d.society_id = p_society_id
    ORDER BY d.disposed ASC, d.purchase_date DESC;
END;
$$;

-- SECTION 19: APT CHARGES LIST / VEN CHARGES LIST
-- ════════════════════════════════════════════════════════════════

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

CREATE OR REPLACE FUNCTION fn_check_orphan_receipts(p_society_id INT)
RETURNS TABLE (receipt_id INT, issue TEXT) LANGUAGE SQL STABLE AS $$
    SELECT r.id, 'Receipt references missing income account'::TEXT
    FROM receipts r
    WHERE r.society_id = p_society_id
      AND r.acc_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM accounts a WHERE a.id = r.acc_id);
$$;

-- Vendors with no linked user account.

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

CREATE OR REPLACE FUNCTION fn_check_duplicate_journals(p_society_id INT)
RETURNS TABLE (journal_id INT, dr_count BIGINT, cr_count BIGINT, dr_sum NUMERIC(15,2), cr_sum NUMERIC(15,2), issue TEXT) LANGUAGE SQL STABLE AS $$
    SELECT t.journal_id,
           COUNT(*) FILTER (WHERE a.drcr_account = 'Dr') AS dr_count,
           COUNT(*) FILTER (WHERE a.drcr_account = 'Cr') AS cr_count,
           COALESCE(SUM(t.amount) FILTER (WHERE a.drcr_account = 'Dr'),0)::NUMERIC(15,2) AS dr_sum,
           COALESCE(SUM(t.amount) FILTER (WHERE a.drcr_account = 'Cr'),0)::NUMERIC(15,2) AS cr_sum,
           'Unbalanced journal (Dr != Cr)'::TEXT
    FROM transactions t
    JOIN accounts a ON a.id = t.acc_id AND a.society_id = t.society_id
    WHERE t.society_id = p_society_id AND t.journal_id IS NOT NULL AND t.status = 'paid'
    GROUP BY t.journal_id
    HAVING COUNT(*) FILTER (WHERE a.drcr_account = 'Dr') <> 1
        OR COUNT(*) FILTER (WHERE a.drcr_account = 'Cr') <> 1
        OR COALESCE(SUM(t.amount) FILTER (WHERE a.drcr_account = 'Dr'),0)
           <> COALESCE(SUM(t.amount) FILTER (WHERE a.drcr_account = 'Cr'),0);
$$;

-- Broken foreign keys across the major tables.

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

-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 2E: AUDITOR VERIFICATION — Parallel (society_id, acc_id) SHA256 chains
-- ═══════════════════════════════════════════════════════════════════════════════

-- Verify a single confirmed receipt's hash and chain link.

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

-- fn_create_poll: Admin creates a new poll.
-- No p_created_by param: poll creation is admin-only (save_poll requires
-- role=="admin"), so a creator column/param adds no value.

CREATE OR REPLACE FUNCTION fn_create_poll(
    p_society_id   INT,
    p_title        VARCHAR(200),
    p_description  TEXT DEFAULT NULL,
    p_choice_count SMALLINT DEFAULT 2,
    p_choice_1     VARCHAR(100) DEFAULT '',
    p_choice_2     VARCHAR(100) DEFAULT '',
    p_choice_3     VARCHAR(100) DEFAULT NULL,
    p_choice_4     VARCHAR(100) DEFAULT NULL,
    p_choice_5     VARCHAR(100) DEFAULT NULL,
    p_ends_at      TIMESTAMP DEFAULT NULL,
    p_open_to      VARCHAR(20) DEFAULT 'no_dues',
    p_vote_basis   VARCHAR(20) DEFAULT 'apartment'
) RETURNS INT LANGUAGE plpgsql AS $$
DECLARE
    v_poll_id INT;
    v_quorum  NUMERIC := NULL;
    v_major   NUMERIC := NULL;
    v_missing INT;
    v_sum     NUMERIC;
BEGIN
    IF p_choice_count < 2 OR p_choice_count > 5 THEN
        RAISE EXCEPTION 'choice_count must be between 2 and 5';
    END IF;

    IF p_open_to NOT IN ('no_dues', 'all_members') THEN
        RAISE EXCEPTION 'open_to must be no_dues or all_members';
    END IF;

    IF p_vote_basis IS NULL OR p_vote_basis NOT IN ('apartment', 'undivided_interest') THEN
        RAISE EXCEPTION 'vote_basis must be apartment or undivided_interest';
    END IF;

    IF p_ends_at IS NOT NULL AND p_ends_at <= NOW() THEN
        RAISE EXCEPTION 'ends_at must be in the future';
    END IF;

    IF p_vote_basis = 'undivided_interest' THEN
        -- A weighted poll is only meaningful if every flat has a percentage and they add up to the whole
        -- building (Act s.5(2), s.12(1)(f)); otherwise the tally would silently under- or over-count.
        SELECT COUNT(*) FILTER (WHERE undivided_interest_pct IS NULL), COALESCE(SUM(undivided_interest_pct), 0)
          INTO v_missing, v_sum
          FROM apartments WHERE society_id = p_society_id AND active;
        IF v_missing > 0 THEN
            RAISE EXCEPTION '% flat(s) have no undivided-interest percentage; enter the Declaration figures (or run the backfill) before a weighted poll', v_missing;
        END IF;
        IF v_sum < 99.9 OR v_sum > 100.1 THEN
            RAISE EXCEPTION 'undivided-interest percentages add up to %, not 100; correct them before a weighted poll', ROUND(v_sum, 4);
        END IF;
        v_quorum := fn_regime_param_num(p_society_id, 'poll_quorum_pct');
        v_major  := fn_regime_param_num(p_society_id, 'poll_majority_pct');
    END IF;

    INSERT INTO polls (society_id, title, description, choice_count, choice_1, choice_2, choice_3, choice_4, choice_5,
                       ends_at, open_to, vote_basis, quorum_pct, majority_pct)
    VALUES (p_society_id, p_title, p_description, p_choice_count, p_choice_1, p_choice_2, p_choice_3, p_choice_4, p_choice_5,
            p_ends_at, p_open_to, p_vote_basis, COALESCE(v_quorum, 33.33), COALESCE(v_major, 50.00))
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
    LEFT JOIN (SELECT poll_id, COUNT(*) AS total_votes FROM poll_participation GROUP BY poll_id) v
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
    LEFT JOIN (SELECT poll_id, COUNT(*) AS total_votes FROM poll_participation GROUP BY poll_id) v
        ON v.poll_id = p.id
    LEFT JOIN LATERAL (
        -- Only one choice qualifies as "winning" if its vote count is a
        -- strict, unique max — a tie (or zero votes) yields NULL so the
        -- list never highlights an arbitrary choice.
        -- Only revealed once the admin has declared results; before that the
        -- interim leader is not shown to anyone.
        SELECT CASE WHEN p.status = 'results_declared'
                     AND COUNT(*) FILTER (WHERE x.cnt = x.maxcnt) = 1
                    THEN (ARRAY_AGG(x.choice) FILTER (WHERE x.cnt = x.maxcnt))[1]
                    ELSE NULL END AS winning_choice
        FROM (
            SELECT choice, COUNT(*) AS cnt, MAX(COUNT(*)) OVER () AS maxcnt
            FROM poll_ballots
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
        COALESCE((SELECT COUNT(*) FROM poll_participation WHERE poll_id = p.id), 0)::BIGINT,
        EXISTS (SELECT 1 FROM poll_participation WHERE poll_id = p.id AND apartment_id = (SELECT linked_id FROM users WHERE users.id = p_user_id)),
        NULL::SMALLINT,   -- secret ballot: a voter's own choice is not retrievable
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

    -- Per-choice tallies exist only after the admin declares results; while
    -- voting is open (or merely closed) only the total turnout is visible.
    IF status = 'results_declared' THEN
        vote_counts := (
            SELECT jsonb_object_agg(
                'choice_' || v.choice,
                v.cnt
            )
            FROM (
                SELECT choice, COUNT(*) AS cnt
                FROM poll_ballots
                WHERE poll_id = p_poll_id
                GROUP BY choice
            ) v
        );
    END IF;

    RETURN NEXT;
END;
$$;

-- fn_cast_vote: User casts a vote (server-side auth via p_user_id)

CREATE OR REPLACE FUNCTION fn_cast_vote(
    p_poll_id  INT,
    p_user_id  INT,
    p_society_id INT,
    p_choice   SMALLINT
) RETURNS TABLE (success BOOLEAN, message TEXT, total_votes BIGINT) LANGUAGE plpgsql AS $$
DECLARE
    v_poll      polls%ROWTYPE;
    v_user      users%ROWTYPE;
    v_apt_id    INT;
    v_existing  INT;
    v_total     BIGINT;
    v_standing  RECORD;
    v_weight    NUMERIC;
BEGIN
    SELECT * INTO v_poll FROM polls WHERE id = p_poll_id AND society_id = p_society_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'Poll not found'::TEXT, 0::BIGINT;
        RETURN;
    END IF;

    SELECT * INTO v_user FROM users WHERE id = p_user_id;
    IF NOT FOUND OR v_user.role != 'apartment' OR v_user.user_type != 'owner' THEN
        RETURN QUERY SELECT FALSE, 'Only apartment owners can vote'::TEXT, 0::BIGINT;
        RETURN;
    END IF;

    IF v_user.society_id IS DISTINCT FROM v_poll.society_id THEN
        RETURN QUERY SELECT FALSE, 'User and poll belong to different societies'::TEXT, 0::BIGINT;
        RETURN;
    END IF;

    SELECT id INTO v_apt_id FROM apartments WHERE id = v_user.linked_id AND society_id = v_poll.society_id;
    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'Apartment not found in this society'::TEXT, 0::BIGINT;
        RETURN;
    END IF;

    IF v_poll.open_to = 'no_dues' THEN
        SELECT * INTO v_standing FROM fn_get_standing(v_poll.society_id, v_apt_id, CURRENT_DATE);
        IF v_standing.ineligible_vote THEN
            RETURN QUERY SELECT FALSE, 'Your apartment has outstanding dues or overdue loans — not eligible to vote'::TEXT, 0::BIGINT;
            RETURN;
        END IF;
    END IF;

    IF v_poll.status <> 'active' THEN
        RETURN QUERY SELECT FALSE, 'This poll is no longer active'::TEXT, 0::BIGINT;
        RETURN;
    END IF;

    IF v_poll.ends_at IS NOT NULL AND v_poll.ends_at <= NOW() THEN
        RETURN QUERY SELECT FALSE, 'This poll has ended'::TEXT, 0::BIGINT;
        RETURN;
    END IF;

    IF p_choice < 1 OR p_choice > v_poll.choice_count THEN
        RETURN QUERY SELECT FALSE, format('Invalid choice. Please select between 1 and %s', v_poll.choice_count)::TEXT, 0::BIGINT;
        RETURN;
    END IF;

    SELECT apartment_id INTO v_existing FROM poll_participation WHERE poll_id = p_poll_id AND apartment_id = v_apt_id;
    IF v_existing IS NOT NULL THEN
        RETURN QUERY SELECT FALSE, 'A vote has already been cast for this apartment'::TEXT, 0::BIGINT;
        RETURN;
    END IF;

    -- Same transaction: the participation row enforces one vote per apartment
    -- (its PK raises unique_violation on a race); the ballot row carries only
    -- the choice, so nothing links this apartment/user to what was chosen.
    INSERT INTO poll_participation (poll_id, apartment_id) VALUES (p_poll_id, v_apt_id);
    INSERT INTO poll_ballots (poll_id, choice) VALUES (p_poll_id, p_choice);

    IF v_poll.vote_basis = 'undivided_interest' THEN
        SELECT undivided_interest_pct INTO v_weight FROM apartments WHERE id = v_apt_id;
        IF v_weight IS NULL OR v_weight <= 0 THEN
            -- Roll the whole call back: the two inserts above must not survive without a weight.
            RAISE EXCEPTION 'no_weight';
        END IF;
        INSERT INTO poll_weight_tally (poll_id, choice, weight_sum) VALUES (p_poll_id, p_choice, v_weight)
        ON CONFLICT (poll_id, choice) DO UPDATE SET weight_sum = poll_weight_tally.weight_sum + EXCLUDED.weight_sum;
    END IF;

    SELECT COUNT(*) INTO v_total FROM poll_participation WHERE poll_id = p_poll_id;

    RETURN QUERY SELECT TRUE, 'Vote cast successfully'::TEXT, v_total;
EXCEPTION
    WHEN unique_violation THEN
        RETURN QUERY SELECT FALSE, 'A vote has already been cast for this apartment'::TEXT, 0::BIGINT;
        RETURN;
    WHEN raise_exception THEN
        IF SQLERRM = 'no_weight' THEN
            RETURN QUERY SELECT FALSE, 'This apartment has no undivided-interest percentage, so it cannot vote in a weighted poll - ask the Secretary to record it'::TEXT, 0::BIGINT;
            RETURN;
        END IF;
        RAISE;
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

    IF p_ends_at IS NOT NULL AND p_ends_at <= NOW() THEN
        RETURN FALSE;
    END IF;

    SELECT COUNT(*) INTO v_vote_count FROM poll_participation WHERE poll_id = p_poll_id;
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
-- Phase 4: Now checks quorum and majority requirements

CREATE OR REPLACE FUNCTION fn_declare_results(p_poll_id INT, p_user_id INT, p_society_id INT)
RETURNS TABLE (success BOOLEAN, message TEXT, results JSONB) LANGUAGE plpgsql AS $$
DECLARE
    v_poll polls%ROWTYPE;
    v_total_votes BIGINT;
    v_eligible_voters BIGINT;
    v_quorum_met BOOLEAN;
    v_winning_choice SMALLINT;
    v_winning_votes BIGINT;
    v_majority_met BOOLEAN;
    v_results JSONB;
    v_weighted BOOLEAN;
    v_win_weight NUMERIC;
    v_cast_weight NUMERIC;
    v_base_weight NUMERIC;
    v_basis TEXT;
    v_pct NUMERIC;
    v_note TEXT;
BEGIN
    SELECT * INTO v_poll FROM polls WHERE id = p_poll_id AND society_id = p_society_id;
    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'Poll not found'::TEXT, NULL::JSONB;
        RETURN;
    END IF;

    IF v_poll.status = 'results_declared' THEN
        RETURN QUERY SELECT FALSE, 'Results already declared'::TEXT, NULL::JSONB;
        RETURN;
    END IF;

    v_weighted := (v_poll.vote_basis = 'undivided_interest');

    -- Count total votes
    SELECT COUNT(*) INTO v_total_votes FROM poll_ballots WHERE poll_id = p_poll_id;

    -- Count eligible voters (apartments that can vote based on open_to) and, for a weighted poll, their
    -- combined undivided-interest percentage (the "100%" a majority is measured against).
    IF v_poll.open_to = 'no_dues' THEN
        SELECT COUNT(*), COALESCE(SUM(a.undivided_interest_pct), 0) INTO v_eligible_voters, v_base_weight
        FROM apartments a
        LEFT JOIN LATERAL fn_get_standing(p_society_id, a.id, CURRENT_DATE) s ON TRUE
        WHERE a.society_id = p_society_id AND a.active
          AND NOT s.ineligible_vote;
    ELSE
        SELECT COUNT(*), COALESCE(SUM(undivided_interest_pct), 0) INTO v_eligible_voters, v_base_weight
        FROM apartments WHERE society_id = p_society_id AND active;
    END IF;

    -- Quorum is a head-count of owners (bye-law 9: "30 percent of owners"), for both vote bases.
    v_quorum_met := (v_eligible_voters = 0) OR (v_total_votes * 100.0 / NULLIF(v_eligible_voters, 0) >= v_poll.quorum_pct);

    IF v_weighted THEN
        -- Bye-law 8: a vote carries the owner's percentage. Bye-law 2(e): a "majority" is owners holding 51%
        -- of the votes. By default (poll_majority_of = all_votes) that is 51% of ALL eligible votes, so
        -- abstentions count against a motion; the society may not loosen that, only choose it explicitly.
        SELECT choice, weight_sum INTO v_winning_choice, v_win_weight
          FROM poll_weight_tally WHERE poll_id = p_poll_id
         ORDER BY weight_sum DESC, choice ASC LIMIT 1;
        SELECT COALESCE(SUM(weight_sum), 0) INTO v_cast_weight FROM poll_weight_tally WHERE poll_id = p_poll_id;
        SELECT COUNT(*) INTO v_winning_votes FROM poll_ballots WHERE poll_id = p_poll_id AND choice = v_winning_choice;
        v_basis := COALESCE(fn_regime_param_text(p_society_id, 'poll_majority_of'), 'all_votes');
        IF v_basis NOT IN ('all_votes', 'votes_cast') THEN v_basis := 'all_votes'; END IF;
        IF v_basis = 'all_votes' THEN
            v_pct := v_win_weight * 100.0 / NULLIF(v_base_weight, 0);
        ELSE
            v_pct := v_win_weight * 100.0 / NULLIF(v_cast_weight, 0);
        END IF;
        v_majority_met := COALESCE(v_pct >= v_poll.majority_pct, FALSE);
        v_note := 'Weighted online poll (bye-laws 8 and 2(e)). Bye-laws 9-10 require a General Body quorum present in person, '
                  'so this result is evidence of owners'' will, not a General Body resolution: record it in a meeting and '
                  'resolution before acting on it as a statutory decision.';
    ELSE
        -- Determine winning choice
        SELECT choice, COUNT(*) INTO v_winning_choice, v_winning_votes
        FROM poll_ballots
        WHERE poll_id = p_poll_id
        GROUP BY choice
        ORDER BY COUNT(*) DESC, choice ASC
        LIMIT 1;

        -- Check majority (if only one choice has votes, it wins; otherwise need majority_pct)
        IF v_winning_votes IS NULL THEN
            v_majority_met := FALSE;
        ELSIF v_total_votes = v_winning_votes THEN
            v_majority_met := TRUE; -- unanimous
        ELSE
            v_majority_met := (v_winning_votes * 100.0 / NULLIF(v_total_votes, 0) >= v_poll.majority_pct);
        END IF;
        v_pct := v_winning_votes * 100.0 / NULLIF(v_total_votes, 0);
        v_note := 'Advisory one-flat-one-vote poll. The Model Bye-Laws weight votes by undivided interest (bye-law 8) and '
                  'require a quorum present in person (bye-law 9), so this is not a General Body resolution.';
    END IF;

    -- Build results JSON
    v_results := jsonb_build_object(
        'total_votes', v_total_votes,
        'eligible_voters', v_eligible_voters,
        'quorum_pct', v_poll.quorum_pct,
        'quorum_met', v_quorum_met,
        'majority_pct', v_poll.majority_pct,
        'majority_met', v_majority_met,
        'winning_choice', v_winning_choice,
        'winning_votes', v_winning_votes,
        'vote_basis', v_poll.vote_basis,
        'statutory_resolution', FALSE,
        'note', v_note,
        'choice_breakdown', (
            SELECT jsonb_object_agg('choice_' || choice, cnt)
            FROM (
                SELECT choice, COUNT(*) AS cnt
                FROM poll_ballots
                WHERE poll_id = p_poll_id
                GROUP BY choice
            ) sub
        )
    );
    IF v_weighted THEN
        v_results := v_results || jsonb_build_object(
            'winning_weight_pct', ROUND(COALESCE(v_win_weight, 0), 4),
            'cast_weight_pct', ROUND(v_cast_weight, 4),
            'eligible_weight_pct', ROUND(v_base_weight, 4),
            'majority_of', v_basis,
            'weight_breakdown', (
                SELECT COALESCE(jsonb_object_agg('choice_' || choice, ROUND(weight_sum, 4)), '{}'::JSONB)
                FROM poll_weight_tally WHERE poll_id = p_poll_id)
        );
    END IF;

    -- A poll that misses quorum or majority is NOT declared: it stays as it was so the admin sees
    -- the reason (and the poll is not silently closed out as if it had carried).
    IF v_quorum_met AND v_majority_met THEN
        UPDATE polls
           SET status = 'results_declared',
               results_announced_at = NOW(),
               updated_at = NOW()
         WHERE id = p_poll_id;
    END IF;

    RETURN QUERY SELECT v_quorum_met AND v_majority_met,
           CASE WHEN v_quorum_met AND v_majority_met THEN
                    CASE WHEN v_weighted THEN 'Results declared - quorum and weighted majority met (advisory: not a General Body resolution)'
                         ELSE 'Results declared - quorum and majority met' END
                WHEN NOT v_quorum_met THEN 'Quorum not met (' || ROUND(v_total_votes * 100.0 / NULLIF(v_eligible_voters, 0), 1) || '% of ' || v_eligible_voters || ' eligible)'
                WHEN v_weighted THEN 'Majority not met (' || COALESCE(ROUND(v_pct, 1)::TEXT, '0') || '% of '
                                     || CASE WHEN v_basis = 'all_votes' THEN 'all eligible votes' ELSE 'votes cast' END
                                     || ' for choice ' || COALESCE(v_winning_choice::TEXT, '-') || ', need ' || v_poll.majority_pct || '%)'
                ELSE 'Majority not met (' || ROUND(v_winning_votes * 100.0 / NULLIF(v_total_votes, 0), 1) || '% for choice ' || v_winning_choice || ')'
           END,
           v_results;
END;
$$;

-- fn_close_poll: Admin closes a poll (tenant-scoped — see
-- migration_poll_security_fixes.sql)

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

CREATE OR REPLACE FUNCTION fn_declare_expired_polls(p_society_id INT DEFAULT NULL)
RETURNS TABLE (id INT, society_id INT, title VARCHAR(200)) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    UPDATE polls
       SET status = 'results_declared',
           results_announced_at = NOW(),
           updated_at = NOW()
     WHERE status = 'active'
       AND ends_at IS NOT NULL
       AND ends_at <= NOW()
       AND (p_society_id IS NULL OR society_id = p_society_id)
     RETURNING polls.id, polls.society_id, polls.title;
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
    SELECT COUNT(*)::BIGINT FROM poll_participation pv
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

CREATE OR REPLACE FUNCTION fn_tds_section_rate(
    p_society_id INT,
    p_section    VARCHAR,
    p_discriminator VARCHAR DEFAULT NULL,
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
       AND (r.discriminator = p_discriminator OR (r.discriminator IS NULL AND p_discriminator IS NULL))
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

CREATE OR REPLACE FUNCTION fn_compute_tds_pct(
    p_society_id      INT,
    p_vendor_id       INT,
    p_section         VARCHAR,
    p_discriminator   VARCHAR,
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
       AND (r.discriminator = p_discriminator OR (r.discriminator IS NULL AND p_discriminator IS NULL))
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
#variable_conflict use_column
-- Fixed (2026-09): RETURNS TABLE(period_month DATE, ...) declares an
-- implicit `period_month` variable in scope for the whole function body,
-- which collided with `receivables.period_month`/CTE column references
-- inside the RETURN QUERY below ("column reference period_month is
-- ambiguous") — this function has been failing on every call. The
-- #variable_conflict pragma tells plpgsql to prefer the table column over
-- the OUT-parameter variable wherever they clash, which is what every
-- query in this function actually intends.
DECLARE
    v_fy_start DATE := MAKE_DATE(p_fy, 4, 1);
    v_fy_end   DATE := MAKE_DATE(p_fy + 1, 3, 31);
    v_cgst_acc INT;
    v_sgst_acc INT;
BEGIN
    SELECT id INTO v_cgst_acc FROM accounts
    WHERE society_id = p_society_id AND tab_name = 'CGST'
    LIMIT 1;

    SELECT id INTO v_sgst_acc FROM accounts
    WHERE society_id = p_society_id AND tab_name = 'SGST'
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
            ga2.entity_id = s.id
            AND ga2.role = 'SEC'
            AND ga2.time_out IS NULL
    ) AS gate_pass
FROM
    users u
    JOIN security_staff s ON s.id = u.linked_id
    LEFT JOIN gate_access ga ON ga.entity_id = s.id
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

CREATE TRIGGER trg_validate_primary_bank_account
    BEFORE INSERT OR UPDATE OF primary_bank_account_id ON societies
    FOR EACH ROW EXECUTE FUNCTION fn_trg_validate_primary_bank_account();

CREATE TRIGGER trg_receipt_hash_issue
    BEFORE UPDATE OF status ON receipts
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_receipt_hash_issue();

CREATE TRIGGER trg_receipt_hash_insert
    BEFORE INSERT ON receipts
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_receipt_hash_insert();

CREATE TRIGGER trg_receipt_confirm_activate_tickets
    AFTER UPDATE OF status ON receipts
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_receipt_confirm_activate_tickets();

CREATE TRIGGER trg_expense_hash_issue
    BEFORE UPDATE OF status ON expenses
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_expense_hash_issue();

CREATE TRIGGER trg_expense_hash_insert
    BEFORE INSERT ON expenses
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_expense_hash_insert();

CREATE TRIGGER trg_transaction_number
    BEFORE INSERT ON transactions
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_transaction_number();

CREATE TRIGGER trg_apartment_active_guard
    BEFORE UPDATE ON apartments
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_apartment_active_guard();

CREATE TRIGGER trg_vendors_updated
    BEFORE UPDATE ON vendors
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_set_updated_at();

CREATE TRIGGER trg_security_updated
    BEFORE UPDATE ON security_staff
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_set_updated_at();

CREATE TRIGGER trg_assets_updated
    BEFORE UPDATE ON assets
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_set_updated_at();

CREATE TRIGGER trg_events_updated
    BEFORE UPDATE ON events
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_set_updated_at();

CREATE TRIGGER trg_concerns_updated
    BEFORE UPDATE ON concerns
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_set_updated_at();

CREATE TRIGGER trg_concerns_assigns_updated
    BEFORE UPDATE ON concerns_assigns
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_set_updated_at();

CREATE TRIGGER trg_apt_charges_updated
    BEFORE UPDATE ON apt_charges_fines_basis
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_set_updated_at();

CREATE TRIGGER trg_ven_charges_updated
    BEFORE UPDATE ON ven_charges_fines_basis
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_set_updated_at();

CREATE TRIGGER trg_concerns_qr
    BEFORE INSERT ON concerns
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_concerns_qr();

CREATE TRIGGER trg_receipts_qr
    BEFORE INSERT ON receipts
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_receipts_qr();

CREATE TRIGGER trg_expenses_qr
    BEFORE INSERT ON expenses
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_expenses_qr();

CREATE TRIGGER trg_assets_qr
    BEFORE INSERT ON assets
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_assets_qr();

CREATE TRIGGER trg_visitors_qr
    BEFORE INSERT ON visitors
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_visitors_qr();

CREATE TRIGGER trg_patrol_locations_qr
    BEFORE INSERT ON patrol_locations
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_patrol_locations_qr();

CREATE TRIGGER trg_polls_qr
    BEFORE UPDATE ON polls
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_polls_qr();

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
    JOIN accounts a ON t.acc_id = a.id AND a.society_id = t.society_id
    WHERE t.society_id = p_society_id
      AND t.trx_date BETWEEN v_fy_start AND v_fy_end
      AND t.entry_side = 'Cr'
      AND t.status = 'paid'
      AND (t.bank_reconciled = TRUE OR t.bank_reconciled IS NULL)
    GROUP BY a.mutuality_nature
    
    UNION ALL
    
    SELECT 
        'Expense'::VARCHAR as category,
        a.mutuality_nature as nature,
        SUM(t.amount) as total_amount
    FROM transactions t
    JOIN accounts a ON t.acc_id = a.id AND a.society_id = t.society_id
    WHERE t.society_id = p_society_id
      AND t.trx_date BETWEEN v_fy_start AND v_fy_end
      AND t.entry_side = 'Dr'
      AND t.status = 'paid'
      AND (t.bank_reconciled = TRUE OR t.bank_reconciled IS NULL)
    GROUP BY a.mutuality_nature;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- SECTION 18: FIXED ASSET REGISTER
-- ════════════════════════════════════════════════════════════════
-- Fixed (2026-09, CA compliance pass):
--   - additions_first_half/additions_second_half now split on the
--     statutory 180-day test (fn_asset_gets_full_year_dep) instead of a
--     fixed 1-Sep cutoff.
--   - deductions/depreciation_charge/closing_wdv now go through the same
--     block-netting helper (fn_block_dep_base) as fn_account_depreciation,
--     so this register can never disagree with the P&L depreciation
--     figure — closing_wdv is floored at 0 rather than allowed negative.
--   - stcg_u_s_50 / stcl_u_s_50 columns added: sec. 50(1) short-term
--     capital gain when deductions exceed the block's WDV+additions;
--     sec. 50(2) short-term capital loss when the block is fully
--     disposed (no active assets remain) while WDV is still positive.
--     Both are separate from ordinary P&L depreciation/income and need
--     their own line in the tax computation — this register surfaces
--     them, it does not post them anywhere.

CREATE OR REPLACE FUNCTION fn_fixed_asset_register_fy(
    p_society_id INT,
    p_fy         INT
)
RETURNS TABLE (
    account_id            INT,
    account_name          VARCHAR,
    depreciation_percent  NUMERIC(5,2),
    opening_wdv           NUMERIC(15,2),
    additions_first_half  NUMERIC(15,2),
    additions_second_half NUMERIC(15,2),
    deductions            NUMERIC(15,2),
    depreciation_charge   NUMERIC(15,2),
    closing_wdv           NUMERIC(15,2),
    stcg_u_s_50           NUMERIC(15,2),
    stcl_u_s_50           NUMERIC(15,2)
) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_fy_start DATE := MAKE_DATE(p_fy, 4, 1);
    v_fy_end   DATE := MAKE_DATE(p_fy + 1, 3, 31);
BEGIN
    RETURN QUERY
    WITH blocks AS (
        SELECT id AS acc_id, name AS acc_name, a.depreciation_percent AS dep_pct
        FROM accounts a
        WHERE a.society_id = p_society_id AND COALESCE(a.is_depreciable, FALSE) = TRUE
    ),
    wdv AS (
        SELECT b.acc_id, fn_resolve_bf_amount_fy(p_society_id, b.acc_id, p_fy) AS op_wdv
        FROM blocks b
    ),
    adds AS (
        SELECT acc_id,
               SUM(purchase_value) FILTER (WHERE fn_asset_gets_full_year_dep(COALESCE(installation_date, purchase_date), v_fy_end)) AS add_fh,
               SUM(purchase_value) FILTER (WHERE NOT fn_asset_gets_full_year_dep(COALESCE(installation_date, purchase_date), v_fy_end)) AS add_sh
        FROM assets
        WHERE society_id = p_society_id AND purchase_date BETWEEN v_fy_start AND v_fy_end
        -- Fixed (2026-09): no disposed=FALSE filter — see fn_account_depreciation's notes.
        GROUP BY acc_id
    ),
    deds AS (
        SELECT t.acc_id, SUM(t.amount) AS deds_val
        FROM transactions t
        JOIN blocks b ON t.acc_id = b.acc_id
        WHERE t.society_id = p_society_id
          AND t.trx_date BETWEEN v_fy_start AND v_fy_end
          AND t.entry_side = 'Cr'
          AND t.status = 'paid'
          AND t.source_table = 'assets'
        GROUP BY t.acc_id
    ),
    -- Asset headcount as of FY end — used to detect sec. 50(2) "block
    -- ceases to exist" (every itemised asset in the block disposed, WDV
    -- still positive => residual is a short-term capital loss). Gated on
    -- total_count > 0: many blocks (e.g. a lump-sum opening WDV brought
    -- forward from before this system existed) have NO rows in `assets`
    -- at all — active_count=0 there means "never itemised", not "all
    -- sold", and must NOT trigger sec. 50(2). Only a block with at least
    -- one itemised asset, all of them now disposed, is genuine evidence
    -- the block ceased to exist.
    active AS (
        SELECT acc_id,
               COUNT(*) AS total_count,
               COUNT(*) FILTER (WHERE NOT disposed) AS active_count
        FROM assets
        WHERE society_id = p_society_id
          AND purchase_date <= v_fy_end
        GROUP BY acc_id
    ),
    base AS (
        SELECT
            b.acc_id, b.acc_name, b.dep_pct,
            COALESCE(w.op_wdv, 0) AS op_wdv,
            COALESCE(a.add_fh, 0) AS add_fh,
            COALESCE(a.add_sh, 0) AS add_sh,
            COALESCE(d.deds_val, 0) AS deds_val,
            COALESCE(act.total_count, 0) AS total_count,
            COALESCE(act.active_count, 0) AS active_count,
            (COALESCE(w.op_wdv, 0) + COALESCE(a.add_fh, 0) + COALESCE(a.add_sh, 0) - COALESCE(d.deds_val, 0)) AS pre_dep_value
        FROM blocks b
        LEFT JOIN wdv w ON b.acc_id = w.acc_id
        LEFT JOIN adds a ON b.acc_id = a.acc_id
        LEFT JOIN deds d ON b.acc_id = d.acc_id
        LEFT JOIN active act ON b.acc_id = act.acc_id
    )
    SELECT
        base.acc_id,
        base.acc_name,
        base.dep_pct,
        base.op_wdv,
        base.add_fh,
        base.add_sh,
        base.deds_val,
        CASE
            WHEN base.pre_dep_value <= 0 THEN 0::NUMERIC(15,2)
            WHEN base.total_count > 0 AND base.active_count = 0 THEN 0::NUMERIC(15,2)  -- block ceases to exist: sec. 50(2), no further depreciation
            ELSE fn_account_depreciation(p_society_id, base.acc_id, p_fy)
        END AS depreciation_charge,
        CASE
            WHEN base.pre_dep_value <= 0 THEN 0::NUMERIC(15,2)
            WHEN base.total_count > 0 AND base.active_count = 0 THEN 0::NUMERIC(15,2)
            ELSE GREATEST(base.pre_dep_value - fn_account_depreciation(p_society_id, base.acc_id, p_fy), 0)
        END AS closing_wdv,
        GREATEST(-base.pre_dep_value, 0) AS stcg_u_s_50,
        CASE WHEN base.total_count > 0 AND base.active_count = 0
             THEN GREATEST(base.pre_dep_value, 0) ELSE 0::NUMERIC(15,2) END AS stcl_u_s_50
    FROM base
    ORDER BY base.acc_name;
END;
$$;

CREATE OR REPLACE FUNCTION fn_fixed_assets_list_fy(
    p_society_id INT,
    p_fy         INT
)
RETURNS TABLE (
    asset_id      INT,
    asset_name    VARCHAR,
    asset_sno     VARCHAR,
    account_name  VARCHAR,
    purchase_date DATE,
    purchase_value NUMERIC(15,2),
    disposed      BOOLEAN,
    disposal_date DATE,
    sale_value    NUMERIC(15,2),
    gst_disposal_liability NUMERIC(15,2)
) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_fy_start DATE := MAKE_DATE(p_fy, 4, 1);
    v_fy_end   DATE := MAKE_DATE(p_fy + 1, 3, 31);
BEGIN
    RETURN QUERY
    SELECT
        ast.id AS asset_id,
        ast.asset_name,
        ast.asset_sno,
        acc.name AS account_name,
        ast.purchase_date,
        ast.purchase_value,
        ast.disposed,
        ast.disposed_at AS disposal_date,
        (
            SELECT SUM(amount)
            FROM transactions t
            WHERE t.society_id = p_society_id
              AND t.source_table = 'assets'
              AND t.source_id = ast.id
              AND t.acc_id = ast.acc_id -- Fixed (2026-09): scope to the block account's own leg only —
                                         -- the GST-on-disposal CGST/SGST Cr legs share source_table='assets'/
                                         -- source_id=ast.id too but post to different accounts, and would
                                         -- otherwise be double-counted into "sale_value" here.
              AND t.entry_side = 'Cr'
              AND t.status = 'paid'
        ) AS sale_value,
        ast.gst_disposal_liability
    FROM assets ast
    JOIN accounts acc ON ast.acc_id = acc.id
    WHERE ast.society_id = p_society_id
      AND ast.purchase_date <= v_fy_end
    ORDER BY acc.name, ast.purchase_date;
END;
$$;

-- ════════════════════════════════════════════════════════════════════════════
-- SECTION 24: SOCIETY SETUP WIZARD — first-time onboarding finisher (2026-09)
-- ════════════════════════════════════════════════════════════════════════════
-- Persists everything collected by the Admin portal's first-time Setup
-- Wizard (app/dash_apps/pages/setup_wizard.py). Before this function
-- existed, submit_setup_wizard() only ever wrote the setup-completion
-- secret column (signing_secret_enc, née qr_signing_secret_hash) — the
-- TDS Rates, GST Rates, Apartment Charges, Vendor Charges and Brought
-- Forward steps collected input on-screen but never persisted any of it,
-- so every newly onboarded society ended up with zero tds_section_rates
-- rows, zero gst_rates rows, and no apartment/vendor charge defaults
-- until someone filled them in by hand later.
--
-- Deliberately NOT accepted here: the wizard's "Society Compliance" step
-- (State Compliance Thresholds, Reference KPI Rule Links) and the GST
-- turnover/exemption limits shown under "GST Rates". Those live in the
-- global state_compliance_thresholds / kpi_rule_links tables, shared
-- across every society in that state/nationwide — letting one society's
-- admin edit them from this wizard would silently rewrite statutory
-- constants for every other tenant. The wizard UI now renders those
-- read-only; this function has no parameters for them at all.
--
-- Validation (brought_forward.acc_id must belong to the calling society —
-- a plain FK can't express that) runs before any write, so a bad id
-- fails the whole call with nothing written yet, rather than needing a
-- rollback partway through.
--
-- p_tds_rates is a JSON array of {"section":..., "discriminator":...,
-- "rate":...} objects (see setup_wizard_callbacks.py, which already
-- includes discriminator per row, and TDS_SECTION_RATE_SEED in
-- database/seed.py, which already seeds separate Ind/HUF vs Others rows
-- for 194C/194D via the discriminator column — the schema was never
-- missing a payee-type column; see the fix note on the TDS section-rates
-- write below for what was actually broken).
-- p_signing_secret_enc is the Fernet ciphertext already encrypted in
-- Python (secret_vault.encrypt_secret) before this call — this function
-- never sees the plaintext SIGNING_SECRET and does no hashing/encryption
-- of its own (contrast the old p_qr_hash, which arrived pre-hashed too,
-- but as a one-way werkzeug hash instead of reversible ciphertext).
-- 2026-09 fix: p_duty_hrs was missing from this parameter list even
-- though the body below already referenced it (duty_hrs =
-- COALESCE(p_duty_hrs, duty_hrs)) and setup_wizard_callbacks.py already
-- passed a :duty_hrs value positionally in this exact slot. The extra
-- argument with no matching parameter made every call fail to resolve
-- ("function fn_complete_society_setup(integer, unknown, ...) does not
-- exist") before the body ever ran. Added here, matching the Python
-- call's position (right after gate_logic, before tds_effective_date).
CREATE OR REPLACE FUNCTION fn_complete_society_setup(
    p_society_id        INT,
    p_signing_secret_enc TEXT,
    p_logo              VARCHAR(100),
    p_address           TEXT,
    p_phone             VARCHAR(20),
    p_login_bg          VARCHAR(100),
    p_tan               VARCHAR(10),
    p_gstin             VARCHAR(15),
    p_payment_qr        VARCHAR(255),
    p_calc_start        DATE,
    p_sec_name          VARCHAR(100),
    p_sec_phone         VARCHAR(20),
    p_sec_email         VARCHAR(100),
    p_sec_sign          VARCHAR(100),
    p_tds_rates         JSONB,
    p_cgst              NUMERIC,
    p_sgst              NUMERIC,
    p_apt_amt           NUMERIC,
    p_apt_rate          NUMERIC,
    p_apt_due_day       INT,
    p_apt_sinking       NUMERIC,
    p_apt_repair        NUMERIC,
    p_ven_1day          NUMERIC,
    p_ven_7day          NUMERIC,
    p_ven_1mth          NUMERIC,
    p_bf_fy             INT,
    p_bf_json           JSONB,
    p_created_by        INT,  -- kept for signature compat; no longer stored (apt/ven charge basis and brought_forward are admin-only, so created_by/updated_by were removed from those tables)
    p_email             VARCHAR(100) DEFAULT NULL,
    p_reg_num           VARCHAR(100) DEFAULT NULL,
    p_apt_interest      NUMERIC DEFAULT 0,
    p_sinking_fund_basis VARCHAR(20) DEFAULT 'per_sq_ft',
    p_repair_fund_basis VARCHAR(20) DEFAULT 'per_sq_ft',
    p_fund_gst_exempt   BOOLEAN DEFAULT TRUE,
    p_fund_charges_int  BOOLEAN DEFAULT TRUE,
    p_gst_cadence       VARCHAR(20) DEFAULT 'monthly',
    p_gst_registered    BOOLEAN DEFAULT FALSE,
    p_tds_no_pan        VARCHAR(10) DEFAULT 'warn',
    p_export_fmt        VARCHAR(20) DEFAULT 'structured',
    p_gate_logic        VARCHAR(10) DEFAULT 'both',
    p_duty_hrs           VARCHAR(2) DEFAULT '8',
    p_tds_effective_date DATE DEFAULT NULL,
    p_state              VARCHAR(50) DEFAULT NULL
) RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
    v_item   JSONB;
    v_apt_id INT;
    v_ven_id INT;
    v_gst_id INT;
    v_tds_eff DATE;
    v_dr NUMERIC;
    v_cr NUMERIC;
BEGIN
    IF p_society_id IS NULL THEN
        RETURN 'Error: society not identified';
    END IF;

    -- Validate brought-forward (if present, fy is required)
    IF p_bf_json IS NOT NULL AND jsonb_array_length(p_bf_json) > 0 THEN
        IF p_bf_fy IS NULL THEN
            RETURN 'Error: Brought Forward Financial Year is required.';
        END IF;
    END IF;

    -- A8: no stale hard-coded date. When the caller sends none, default to the
    -- start of the CURRENT Indian financial year (1 April).
    v_tds_eff := COALESCE(
        p_tds_effective_date,
        make_date(
            CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 4
                 THEN EXTRACT(YEAR FROM CURRENT_DATE)::INT
                 ELSE EXTRACT(YEAR FROM CURRENT_DATE)::INT - 1 END,
            4, 1)
    );

    -- A9: opening balances must balance (Dr = Cr). Checked BEFORE any write so
    -- a rejected submission leaves the society untouched.
    IF p_bf_json IS NOT NULL AND jsonb_array_length(p_bf_json) > 0 THEN
        SELECT COALESCE(SUM(CASE WHEN COALESCE(a.drcr_account, 'Dr') = 'Dr'
                                 THEN (j->>'bf_amount')::NUMERIC END), 0),
               COALESCE(SUM(CASE WHEN a.drcr_account = 'Cr'
                                 THEN (j->>'bf_amount')::NUMERIC END), 0)
          INTO v_dr, v_cr
          FROM jsonb_array_elements(p_bf_json) j
          JOIN accounts a ON a.id = (j->>'acc_id')::INT AND a.society_id = p_society_id
         WHERE (j->>'bf_amount')::NUMERIC > 0;
        IF ABS(v_dr - v_cr) > 0.005 THEN
            RETURN 'Error: Brought Forward does not balance - total Debits '
                   || TO_CHAR(v_dr, 'FM999999999990.00') || ' vs total Credits '
                   || TO_CHAR(v_cr, 'FM999999999990.00') || ' (difference '
                   || TO_CHAR(ABS(v_dr - v_cr), 'FM999999999990.00') || ').';
        END IF;
    END IF;

    -- 1) Setup-completion flag and society details
    UPDATE societies SET 
        signing_secret_enc = p_signing_secret_enc,
        logo = COALESCE(p_logo, logo),
        address = COALESCE(NULLIF(BTRIM(p_address), ''), address),
        phone = COALESCE(NULLIF(BTRIM(p_phone), ''), phone),
        email = COALESCE(NULLIF(BTRIM(p_email), ''), email),
        registration_number = COALESCE(NULLIF(BTRIM(p_reg_num), ''), registration_number),
        login_background = COALESCE(p_login_bg, login_background),
        tan_number = COALESCE(NULLIF(BTRIM(p_tan), ''), tan_number),
        gstin = COALESCE(NULLIF(BTRIM(p_gstin), ''), gstin),
        payment_qr = COALESCE(p_payment_qr, payment_qr),
        calc_start_date = COALESCE(p_calc_start, calc_start_date),
        secretary_name = COALESCE(NULLIF(BTRIM(p_sec_name), ''), secretary_name),
        secretary_phone = COALESCE(NULLIF(BTRIM(p_sec_phone), ''), secretary_phone),
        secretary_email = COALESCE(NULLIF(BTRIM(p_sec_email), ''), secretary_email),
        secretary_sign = COALESCE(p_sec_sign, secretary_sign),
        gate_logic = COALESCE(p_gate_logic, gate_logic),
        duty_hrs = COALESCE(p_duty_hrs, duty_hrs),
        -- A10: State is written in the SAME statement (so the state->legal-regime
        -- trigger fires inside this call and a failure is not swallowed).
        state = COALESCE(NULLIF(BTRIM(p_state), ''), state),
        -- A7/R1: the seeded 'SBI' account (child of the Bank Accounts header) is
        -- the society's primary bank account from day one, so non-cash receipts
        -- and payments work immediately (fn_resolve_bank_leg raises if this is
        -- NULL). An already-chosen primary is never overwritten. The wizard
        -- text says so; an admin who banks elsewhere changes it afterwards.
        primary_bank_account_id = COALESCE(primary_bank_account_id,
            (SELECT id FROM accounts
              WHERE society_id = p_society_id AND tab_name = 'SBI'
              LIMIT 1)
        )
    WHERE id = p_society_id;

    -- 2) TDS section rates (per-society; keyed by section+discriminator — see note above)
    --
    -- Fixed (2026-09, CA audit): this previously dropped `discriminator`
    -- from the INSERT entirely (every wizard-submitted row silently became
    -- discriminator=NULL) and its ON CONFLICT target
    -- (society_id, section, effective_from) didn't match the table's real
    -- unique constraint, uq_tds_section_rate
    -- (society_id, section, discriminator, effective_from) — a 3-column
    -- target can't resolve against a 4-column constraint, so Postgres
    -- raised "there is no unique or exclusion constraint matching the ON
    -- CONFLICT specification" on the very first call, for ANY society,
    -- the moment p_tds_rates carried a row for a discriminated section
    -- (194C/194D/194-I/194J all are, per TDS_SECTION_RATE_SEED) — which
    -- setup_wizard_callbacks.py always sends. Setup Wizard completion was
    -- broken end-to-end for every new society, not just a 194C rate
    -- ambiguity.
    --
    -- discriminator is nullable (most sections have none), and Postgres
    -- unique constraints never treat two NULLs as conflicting — so even
    -- with the target column list corrected, ON CONFLICT would silently
    -- never fire for those non-discriminated sections and a fresh
    -- duplicate row would be inserted on every wizard re-save. Using an
    -- explicit UPDATE-then-INSERT-if-not-found, with
    -- `IS NOT DISTINCT FROM` for the discriminator comparison, sidesteps
    -- that NULL-uniqueness pitfall entirely (the same pattern
    -- seed_tds_section_rates() already uses in Python for this exact
    -- reason) instead of relying on ON CONFLICT at all.
    IF p_tds_rates IS NOT NULL THEN
        FOR v_item IN SELECT * FROM jsonb_array_elements(p_tds_rates)
        LOOP
            UPDATE tds_section_rates SET
                nature_of_income = v_item->>'nature_of_income',
                rate = (v_item->>'rate')::NUMERIC,
                rate_no_pan = (v_item->>'rate_no_pan')::NUMERIC,
                single_bill_threshold = (v_item->>'single_bill_threshold')::NUMERIC,
                annual_aggregate_threshold = (v_item->>'annual_aggregate_threshold')::NUMERIC
            WHERE society_id = p_society_id
              AND section = v_item->>'section'
              AND discriminator IS NOT DISTINCT FROM (v_item->>'discriminator')
              AND effective_from = v_tds_eff;

            IF NOT FOUND THEN
                INSERT INTO tds_section_rates (
                    society_id, section, discriminator, nature_of_income, rate, rate_no_pan,
                    single_bill_threshold, annual_aggregate_threshold, effective_from
                )
                VALUES (
                    p_society_id,
                    v_item->>'section',
                    v_item->>'discriminator',
                    v_item->>'nature_of_income',
                    (v_item->>'rate')::NUMERIC,
                    (v_item->>'rate_no_pan')::NUMERIC,
                    (v_item->>'single_bill_threshold')::NUMERIC,
                    (v_item->>'annual_aggregate_threshold')::NUMERIC,
                    v_tds_eff
                );
            END IF;
        END LOOP;
    END IF;

    -- 3) GST rate (per-society default). Updates the currently-open row
    --    (effective_to IS NULL) in place rather than versioning — this is
    --    initial setup, not a mid-year rate change event.
    SELECT id INTO v_gst_id FROM gst_rates
    WHERE society_id = p_society_id AND effective_to IS NULL
    ORDER BY effective_from DESC LIMIT 1;

    IF v_gst_id IS NOT NULL THEN
        UPDATE gst_rates SET cgst_rate_pct = p_cgst, sgst_rate_pct = p_sgst WHERE id = v_gst_id;
    ELSE
        INSERT INTO gst_rates (society_id, cgst_rate_pct, sgst_rate_pct, effective_from)
        VALUES (p_society_id, p_cgst, p_sgst, CURRENT_DATE);
    END IF;

    -- 4) Apartment charges default (apt_id IS NULL row = society-wide fallback,
    --    per the existing (apt_id = apt.id OR apt_id IS NULL) lookup convention)
    SELECT id INTO v_apt_id FROM apt_charges_fines_basis
    WHERE society_id = p_society_id AND apt_id IS NULL AND end_date IS NULL
    LIMIT 1;

    IF v_apt_id IS NOT NULL THEN
        UPDATE apt_charges_fines_basis
        SET apt_maintenance_amount = p_apt_amt, apt_maintenance_rate = p_apt_rate,
            apt_due_day = p_apt_due_day, apt_sinking_fund_rate = p_apt_sinking,
            apt_repair_fund_rate = p_apt_repair, apt_interest_pct = p_apt_interest,
            updated_at = NOW()
        WHERE id = v_apt_id;
    ELSE
        INSERT INTO apt_charges_fines_basis
            (society_id, apt_id, start_date, apt_maintenance_amount, apt_maintenance_rate,
             apt_due_day, apt_sinking_fund_rate, apt_repair_fund_rate, apt_interest_pct)
        VALUES
            (p_society_id, NULL, CURRENT_DATE, p_apt_amt, p_apt_rate,
             p_apt_due_day, p_apt_sinking, p_apt_repair, p_apt_interest);
    END IF;

    -- 4.5) Society compliance settings
    INSERT INTO society_compliance_settings (
        society_id, sinking_fund_rate_basis, repair_fund_rate_basis, 
        fund_gst_exempt, fund_charges_interest, gst_filing_cadence, 
        gst_registered, gstin, tds_no_pan_action, default_export_format
    )
    VALUES (
        p_society_id, p_sinking_fund_basis, p_repair_fund_basis,
        p_fund_gst_exempt, p_fund_charges_int, p_gst_cadence,
        p_gst_registered, p_gstin, p_tds_no_pan, p_export_fmt
    )
    ON CONFLICT (society_id)
    DO UPDATE SET 
        sinking_fund_rate_basis = EXCLUDED.sinking_fund_rate_basis,
        repair_fund_rate_basis = EXCLUDED.repair_fund_rate_basis,
        fund_gst_exempt = EXCLUDED.fund_gst_exempt,
        fund_charges_interest = EXCLUDED.fund_charges_interest,
        gst_filing_cadence = EXCLUDED.gst_filing_cadence,
        gst_registered = EXCLUDED.gst_registered,
        gstin = EXCLUDED.gstin,
        tds_no_pan_action = EXCLUDED.tds_no_pan_action,
        default_export_format = EXCLUDED.default_export_format,
        updated_at = NOW();

    -- 5) Vendor charges default (ven_id IS NULL row = society-wide fallback)
    SELECT id INTO v_ven_id FROM ven_charges_fines_basis
    WHERE society_id = p_society_id AND ven_id IS NULL AND end_date IS NULL
    LIMIT 1;

    IF v_ven_id IS NOT NULL THEN
        UPDATE ven_charges_fines_basis
        SET vendor_1day = p_ven_1day, vendor_7day = p_ven_7day, vendor_1mth = p_ven_1mth,
            updated_at = NOW()
        WHERE id = v_ven_id;
    ELSE
        INSERT INTO ven_charges_fines_basis
            (society_id, ven_id, start_date, vendor_1day, vendor_7day, vendor_1mth)
        VALUES
            (p_society_id, NULL, CURRENT_DATE, p_ven_1day, p_ven_7day, p_ven_1mth);
    END IF;

    -- 6) Brought forward (multiple opening-balance rows passed as JSON)
    IF p_bf_json IS NOT NULL THEN
        FOR v_item IN SELECT * FROM jsonb_array_elements(p_bf_json)
        LOOP
            IF (v_item->>'bf_amount')::NUMERIC > 0 THEN
                INSERT INTO brought_forward (society_id, financial_year, acc_id, drcr_bf, bf_amount, remarks, is_auto_calculated)
                SELECT p_society_id, p_bf_fy, (v_item->>'acc_id')::INT, COALESCE(a.drcr_account, 'Dr'), (v_item->>'bf_amount')::NUMERIC, v_item->>'remarks', FALSE
                FROM accounts a WHERE a.id = (v_item->>'acc_id')::INT AND a.society_id = p_society_id
                ON CONFLICT (society_id, financial_year, acc_id)
                DO UPDATE SET drcr_bf = EXCLUDED.drcr_bf, bf_amount = EXCLUDED.bf_amount,
                              remarks = EXCLUDED.remarks, updated_at = NOW(),
                              is_auto_calculated = FALSE;
            END IF;
        END LOOP;
    END IF;

    RETURN 'OK';
END;
$$;

CREATE OR REPLACE VIEW vw_apartment_users AS
SELECT
    id,
    society_id,
    name,
    email,
    user_type,
    created_at,
    linked_id AS apartment_id
FROM users
WHERE
    role = 'apartment';

-- ═══════════════════════════════════════════════════════════════════════════════
-- UP AOA COMPLIANCE LAYER — UP Apartment Act 2010 / Model Bye-Laws 2011
--
-- Everything below is keyed off society_legal_regime → regime_rule_parameters, so
-- a society with no regime (or a non-UP regime) simply gets NULL / no rows back:
-- these rules switch on only where the regime row says they apply.
-- Provision numbers cite the 2011 Model Bye-Laws (UP Gazette, 16 Nov 2011) and the
-- 2010 Act; confirm against the gazette copy / an advocate before relying on them
-- for a filing. The 2016 amendment Act was repealed without being enforced and is
-- NOT relied on anywhere.
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE regime_rule_parameters (
    regime_code      VARCHAR(30) NOT NULL,   -- deliberately no FK: loadable before seed.py creates the regime row
    rule_key         VARCHAR(60) NOT NULL,
    value            NUMERIC(14, 4),
    value_text       TEXT,
    unit             VARCHAR(20),
    source_reference TEXT NOT NULL,
    effective_from   DATE NOT NULL DEFAULT DATE '2011-11-16',
    effective_to     DATE,
    PRIMARY KEY (regime_code, rule_key, effective_from)
);

-- ── RULE PARAMETER DEFINITIONS ───────────────────────────────────────────────────
-- What each regime_rule_parameters row IS: which instrument and provision it comes from, whether it is
-- statutory (Layer 0, society cannot change it) or non-statutory, who may vary it and within what limits,
-- how it is enforced and which code reads it. Generated from schemes/<CODE>.toml (see below); the Master
-- rule editor's RULE_SPECS and the society-level resolver fn_rule() read it too, so a rule is written once.
CREATE TABLE rule_parameter_defs (
    regime_code    VARCHAR(30) NOT NULL,     -- no FK, like regime_rule_parameters
    rule_key       VARCHAR(30) NOT NULL,     -- <= 30: also used as resolutions.clause_id
    label          VARCHAR(200) NOT NULL,
    instrument     VARCHAR(300) NOT NULL,
    provision      VARCHAR(200) NOT NULL,
    clause_id      VARCHAR(30),              -- Model Bye-Law clause the parameter belongs to, if any
    nature         VARCHAR(15) NOT NULL CHECK (nature IN ('statutory', 'non_statutory')),
    base_source    VARCHAR(20) NOT NULL CHECK (base_source IN ('central', 'state_act_rules', 'model_bye_law', 'engine_default')),
    value_type     VARCHAR(5)  NOT NULL CHECK (value_type IN ('int', 'num', 'text')),
    unit           VARCHAR(20),
    min_value      NUMERIC(14, 4),           -- sanity bounds for any value of the rule
    max_value      NUMERIC(14, 4),
    vary_min       NUMERIC(14, 4),           -- the envelope a SOCIETY may vary within (default = min/max)
    vary_max       NUMERIC(14, 4),
    choices        TEXT[] NOT NULL DEFAULT '{}',   -- text rules, ordered loosest -> strictest
    layers         INT[]  NOT NULL DEFAULT '{}' CHECK (layers <@ ARRAY[1, 2, 3]),   -- layers that may set a value
    tighten        VARCHAR(6) NOT NULL DEFAULT 'none' CHECK (tighten IN ('lower', 'higher', 'none')),
    droppable      BOOLEAN NOT NULL DEFAULT FALSE,
    enforcement    VARCHAR(10) NOT NULL CHECK (enforcement IN ('hard_wired', 'gated', 'tracked', 'policy')),
    feeds          TEXT[] NOT NULL DEFAULT '{}',
    verification   VARCHAR(12) NOT NULL DEFAULT 'provisional' CHECK (verification IN ('provisional', 'checked', 'verified', 'disputed')),
    verified_on    DATE,
    needs_decision BOOLEAN NOT NULL DEFAULT FALSE,
    implemented    BOOLEAN NOT NULL DEFAULT TRUE,
    description    TEXT,
    PRIMARY KEY (regime_code, rule_key),
    CONSTRAINT ck_rule_defs_statutory CHECK ((nature = 'statutory') = (base_source IN ('central', 'state_act_rules'))),
    CONSTRAINT ck_rule_defs_statutory_locked CHECK (nature <> 'statutory' OR (layers = '{}' AND NOT droppable))
);

-- >>> GENERATED by scripts/build_scheme_sql.py from schemes/*.toml. Do not edit by hand.
INSERT INTO rule_parameter_defs (regime_code, rule_key, label, instrument, provision, clause_id, nature,
    base_source, value_type, unit, min_value, max_value, vary_min, vary_max, choices, layers, tighten,
    droppable, enforcement, feeds, verification, verified_on, needs_decision, implemented, description) VALUES
 ('GENERIC', 'cash_limit_default_mode', 'Cash-limit enforcement default (engine policy)', 'Engine policy (no statutory source)', '-', NULL, 'non_statutory', 'engine_default', 'text', NULL, NULL, NULL, NULL, NULL, ARRAY['warn', 'block']::TEXT[], ARRAY[1, 2, 3]::INT[], 'higher', FALSE, 'policy', ARRAY['fn_cash_limit_mode']::TEXT[], 'provisional', NULL, TRUE, TRUE, NULL),
 ('GENERIC', 'reserve_appropriation_pct', 'Reserve Fund share of net surplus at FY close (%)', 'Engine policy (no statutory source)', '-', NULL, 'non_statutory', 'engine_default', 'num', '%', 0, 100, 0, 100, ARRAY[]::TEXT[], ARRAY[1, 2]::INT[], 'none', FALSE, 'policy', ARRAY['fn_fy_close_preview', 'fn_fy_close_reserve_appropriation']::TEXT[], 'provisional', NULL, TRUE, TRUE, NULL),
 ('UP_AOA_2010', 's22_default_months', 's.22 default must exceed (months)', 'UP Apartment (Promotion of Construction, Ownership and Maintenance) Act, 2010', 's.22(1)', NULL, 'statutory', 'state_act_rules', 'int', 'months', 1, 60, 1, 60, ARRAY[]::TEXT[], ARRAY[]::INT[], 'none', FALSE, 'gated', ARRAY['fn_service_cutoff_check', 'fn_get_standing']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 's22_notice_days', 's.22 notice to defaulter (days)', 'UP Apartment (Promotion of Construction, Ownership and Maintenance) Act, 2010', 's.22(1)', NULL, 'statutory', 'state_act_rules', 'int', 'days', 1, 90, 1, 90, ARRAY[]::TEXT[], ARRAY[]::INT[], 'none', FALSE, 'gated', ARRAY['fn_service_cutoff_check', 'fn_get_standing']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 's22_wait_months', 's.22 wait after certified copy (months)', 'UP Apartment (Promotion of Construction, Ownership and Maintenance) Act, 2010', 's.22(1) proviso', NULL, 'statutory', 'state_act_rules', 'int', 'months', 1, 12, 1, 12, ARRAY[]::TEXT[], ARRAY[]::INT[], 'none', FALSE, 'gated', ARRAY['fn_service_cutoff_check', 'fn_get_standing']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 's22_appeal_days', 's.22 appeal window (days)', 'UP Apartment (Promotion of Construction, Ownership and Maintenance) Act, 2010', 's.22(2)', NULL, 'statutory', 'state_act_rules', 'int', 'days', 1, 90, 1, 90, ARRAY[]::TEXT[], ARRAY[]::INT[], 'none', FALSE, 'gated', ARRAY['fn_service_cutoff_check', 'fn_get_standing']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 's20_recovery_months', 's.20 recovery after unpaid (months)', 'UP Apartment (Promotion of Construction, Ownership and Maintenance) Act, 2010', 's.20(2)', NULL, 'statutory', 'state_act_rules', 'int', 'months', 1, 60, 1, 60, ARRAY[]::TEXT[], ARRAY[]::INT[], 'none', FALSE, 'tracked', ARRAY['fn_s20_recovery_candidates']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, 'Reported, not automated: fn_s20_recovery_candidates lists the flats whose common-expense bills are older than this; the application to the Competent Authority is made by the association.'),
 ('UP_AOA_2010', 'arrears_disqualify_days', 'Bye-law 7 arrears bar after (days)', 'UP Model Bye-Laws, 2011', 'bye-law 7', 'BL_07', 'non_statutory', 'model_bye_law', 'int', 'days', 1, 365, 1, 60, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'lower', FALSE, 'gated', ARRAY['fn_get_standing', 'fn_bye_law7_eligibility', 'fn_common_expense_arrears_asof']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, 'A society may only shorten the 60 days (General Body policy); lengthening would loosen the Model Bye-Law.'),
 ('UP_AOA_2010', 'transfer_fee_pct', 'Bye-law 39 transfer fee (% of value)', 'UP Model Bye-Laws, 2011', 'bye-law 39', 'BL_39', 'non_statutory', 'model_bye_law', 'num', '% of value', 0.0001, 5, 0.0001, 5, ARRAY[]::TEXT[], ARRAY[]::INT[], 'none', FALSE, 'gated', ARRAY['fn_record_apartment_transfer']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'nodues_deemed_days', 'No Dues deemed granted after (days)', 'UP Model Bye-Laws, 2011', 'bye-law 39', 'BL_39', 'non_statutory', 'model_bye_law', 'int', 'days', 1, 90, 1, 15, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'lower', FALSE, 'gated', ARRAY['fn_nodues_certificate_status']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'cash_payment_cheque_threshold', 'Cash payments above this breach (INR)', 'UP Model Bye-Laws, 2011', 'bye-laws 46-52 (financial provisions)', 'BL_49', 'non_statutory', 'model_bye_law', 'num', 'INR', 1, 10000000, 1, 2500, ARRAY[]::TEXT[], ARRAY[2, 3]::INT[], 'lower', FALSE, 'gated', ARRAY['fn_check_cash_payment_limit']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'petty_cash_limit', 'Petty cash ceiling (INR)', 'UP Model Bye-Laws, 2011', 'bye-laws 46-52 (financial provisions)', 'BL_49', 'non_statutory', 'model_bye_law', 'num', 'INR', 1, 10000000, 1, 20000, ARRAY[]::TEXT[], ARRAY[2, 3]::INT[], 'lower', FALSE, 'gated', ARRAY['fn_petty_cash_check']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'statement_publish_due_month', 'Bye-law 49 publish deadline - month', 'UP Model Bye-Laws, 2011', 'bye-law 49', 'BL_49', 'non_statutory', 'model_bye_law', 'int', 'month', 1, 12, 1, 12, ARRAY[]::TEXT[], ARRAY[]::INT[], 'none', FALSE, 'tracked', ARRAY['fn_statutory_calendar']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'statement_publish_due_day', 'Bye-law 49 publish deadline - day', 'UP Model Bye-Laws, 2011', 'bye-law 49', 'BL_49', 'non_statutory', 'model_bye_law', 'int', 'day', 1, 31, 1, 31, ARRAY[]::TEXT[], ARRAY[]::INT[], 'none', FALSE, 'tracked', ARRAY['fn_statutory_calendar']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'authority_copy_due_month', 'Bye-law 49 authority copy - month', 'UP Model Bye-Laws, 2011', 'bye-law 49', 'BL_49', 'non_statutory', 'model_bye_law', 'int', 'month', 1, 12, 1, 12, ARRAY[]::TEXT[], ARRAY[]::INT[], 'none', FALSE, 'tracked', ARRAY['fn_statutory_calendar']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'authority_copy_due_day', 'Bye-law 49 authority copy - day', 'UP Model Bye-Laws, 2011', 'bye-law 49', 'BL_49', 'non_statutory', 'model_bye_law', 'int', 'day', 1, 31, 1, 31, ARRAY[]::TEXT[], ARRAY[]::INT[], 'none', FALSE, 'tracked', ARRAY['fn_statutory_calendar']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'owner_summary_days', 'Bye-law 49 owner summary within (days)', 'UP Model Bye-Laws, 2011', 'bye-law 49', 'BL_49', 'non_statutory', 'model_bye_law', 'int', 'days', 1, 90, 1, 90, ARRAY[]::TEXT[], ARRAY[]::INT[], 'none', FALSE, 'tracked', ARRAY['fn_statutory_calendar']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'bye_law7_year_basis', 'Bye-law 7 ''year'' basis (contested; default)', 'UP Model Bye-Laws, 2011', 'bye-law 7', 'BL_07', 'non_statutory', 'engine_default', 'text', NULL, NULL, NULL, NULL, NULL, ARRAY['financial_year', 'calendar_year']::TEXT[], ARRAY[1, 2]::INT[], 'none', FALSE, 'policy', ARRAY['fn_bye_law7_cutoff_date', 'fn_bye_law7_eligibility']::TEXT[], 'disputed', NULL, TRUE, TRUE, NULL),
 ('UP_AOA_2010', 'cash_limit_default_mode', 'Cash-limit enforcement default (engine policy)', 'Engine policy (no statutory source)', '-', NULL, 'non_statutory', 'engine_default', 'text', NULL, NULL, NULL, NULL, NULL, ARRAY['warn', 'block']::TEXT[], ARRAY[2, 3]::INT[], 'higher', FALSE, 'policy', ARRAY['fn_cash_limit_mode']::TEXT[], 'provisional', NULL, TRUE, TRUE, NULL),
 ('UP_AOA_2010', 'owner_loan_blocks_nodues', 'Outstanding owner loan blocks issuing No Dues (1 = yes)', 'Engine policy (no statutory source)', 'bye-law 3(1)(f) (loans)', NULL, 'non_statutory', 'engine_default', 'int', '0/1', 0, 1, 0, 1, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'higher', FALSE, 'policy', ARRAY['fn_get_standing', 'fn_nodues_issue_check']::TEXT[], 'provisional', NULL, FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'owner_loan_counts_bye_law7', 'Overdue owner loan counts as bye-law 7 arrears (1 = yes)', 'Engine policy (no statutory source)', 'bye-law 7', NULL, 'non_statutory', 'engine_default', 'int', '0/1', 0, 1, 0, 1, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'higher', FALSE, 'policy', ARRAY['fn_get_standing', 'fn_bye_law7_eligibility']::TEXT[], 'provisional', NULL, FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'owner_loan_counts_s22', 'Overdue owner loan counts toward the s.22 dues test (1 = yes)', 'Engine policy (no statutory source)', 's.22', NULL, 'non_statutory', 'engine_default', 'int', '0/1', 0, 1, 0, 1, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'none', FALSE, 'policy', ARRAY['fn_get_standing']::TEXT[], 'provisional', NULL, FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'reserve_appropriation_pct', 'Reserve Fund share of net surplus at FY close (%)', 'Engine policy (no statutory source)', 'bye-law 46(c) (common profits form the nucleus of reserve funds)', NULL, 'non_statutory', 'engine_default', 'num', '%', 0, 100, 0, 100, ARRAY[]::TEXT[], ARRAY[1, 2]::INT[], 'none', FALSE, 'policy', ARRAY['fn_fy_close_preview', 'fn_fy_close_reserve_appropriation']::TEXT[], 'provisional', NULL, TRUE, TRUE, NULL),
 ('UP_AOA_2010', 'poll_quorum_pct', 'Poll quorum: owners voting (% of owners)', 'UP Model Bye-Laws, 2011', 'bye-law 9', 'BL_09', 'non_statutory', 'model_bye_law', 'num', '% of owners', 1, 100, 30, 100, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'higher', FALSE, 'gated', ARRAY['fn_create_poll', 'fn_declare_results']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, 'Applied to weighted polls only. A society may raise it, never lower it. Bye-law 9 speaks of owners present IN PERSON, so an online poll reaching this figure still does not make a General Body quorum.'),
 ('UP_AOA_2010', 'poll_majority_pct', 'Poll majority: share of the votes (%)', 'UP Model Bye-Laws, 2011', 'bye-law 2(e)', 'BL_02', 'non_statutory', 'model_bye_law', 'num', '% of votes', 1, 100, 51, 100, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'higher', FALSE, 'gated', ARRAY['fn_create_poll']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, 'Applied to weighted polls only (polls.vote_basis = undivided_interest). A society may raise it, never lower it.'),
 ('UP_AOA_2010', 'poll_majority_of', 'Weighted-poll majority is measured against', 'Engine policy (no statutory source)', 'bye-laws 2(e) and 10', 'BL_10', 'non_statutory', 'engine_default', 'text', NULL, NULL, NULL, NULL, NULL, ARRAY['votes_cast', 'all_votes']::TEXT[], ARRAY[2]::INT[], 'higher', FALSE, 'policy', ARRAY['fn_declare_results']::TEXT[], 'disputed', NULL, TRUE, TRUE, NULL),
 ('UP_AOA_2010', 'owner_loan_resolution_mode', 'Owner-loan consent must be a recorded resolution', 'Engine policy (no statutory source)', 'bye-law 3(1)(f)', 'BL_03', 'non_statutory', 'engine_default', 'text', NULL, NULL, NULL, NULL, NULL, ARRAY['text', 'linked']::TEXT[], ARRAY[2]::INT[], 'higher', FALSE, 'policy', ARRAY['fn_disburse_owner_loan']::TEXT[], 'provisional', NULL, TRUE, TRUE, NULL),
 ('UP_AOA_2010', 'owner_loan_max_term_days', 'Owner loan: longest repayment term (days)', 'Engine policy (no statutory source)', 'bye-law 3(1)(f) (''short-term'')', 'BL_03', 'non_statutory', 'engine_default', 'int', 'days', 1, 3650, 1, 3650, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'lower', FALSE, 'policy', ARRAY['fn_disburse_owner_loan']::TEXT[], 'provisional', NULL, TRUE, TRUE, NULL),
 ('UP_AOA_2010', 'entrance_fee', 'Bye-law 4 entrance fee (INR)', 'UP Model Bye-Laws, 2011', 'bye-law 4', 'BL_04', 'non_statutory', 'model_bye_law', 'int', 'INR', 0, 100000, 0, 100000, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'none', FALSE, 'gated', ARRAY['fn_entrance_fee_due']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'share_face_value', 'Bye-law 5 share face value (INR)', 'UP Model Bye-Laws, 2011', 'bye-law 5', 'BL_05', 'non_statutory', 'model_bye_law', 'int', 'INR', 1, 1000, 1, 1000, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'none', FALSE, 'gated', ARRAY['fn_share_capital_due']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'cashbook_daily_signature', 'Bye-law 23(f) daily cashbook signature required', 'UP Model Bye-Laws, 2011', 'bye-law 23(f)', 'BL_23', 'non_statutory', 'model_bye_law', 'int', '0/1', 0, 1, 0, 1, ARRAY[]::TEXT[], ARRAY[2, 3]::INT[], 'higher', FALSE, 'tracked', ARRAY['fn_cashbook_signature_check']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'investment_allowed_types', 'Bye-law 45 permitted investment types', 'UP Model Bye-Laws, 2011', 'bye-law 45', 'BL_45', 'non_statutory', 'model_bye_law', 'text', NULL, NULL, NULL, NULL, NULL, ARRAY['coop_bank,trust_securities,approved_bank', 'coop_bank,trust_securities', 'coop_bank_only']::TEXT[], ARRAY[2]::INT[], 'lower', FALSE, 'gated', ARRAY['fn_investment_check']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'borrowing_ca_approval', 'Bye-law 44(d) borrowing needs Competent Authority approval', 'UP Model Bye-Laws, 2011', 'bye-law 44(d)', 'BL_44', 'non_statutory', 'model_bye_law', 'int', '0/1', 0, 1, 0, 1, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'none', FALSE, 'gated', ARRAY['fn_borrowing_check']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'tenant_joint_liability', 'Act s.18(2) tenant jointly liable with owner', 'UP Apartment (Promotion of Construction, Ownership and Maintenance) Act, 2010', 's.18(2)', NULL, 'statutory', 'state_act_rules', 'int', '0/1', 0, 1, 0, 1, ARRAY[]::TEXT[], ARRAY[]::INT[], 'none', FALSE, 'hard_wired', ARRAY['fn_tenant_liability']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'board_election_voting_basis', 'Board election voting basis (Model Bye-Law 8)', 'UP Model Bye-Laws, 2011', 'bye-law 8', 'BL_08', 'non_statutory', 'model_bye_law', 'text', NULL, NULL, NULL, NULL, NULL, ARRAY['one_apartment_one_vote', 'undivided_interest']::TEXT[], ARRAY[2]::INT[], 'none', FALSE, 'gated', ARRAY['fn_board_election_eligibility']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'depreciation_fund_pct', 'Bye-law 46(d) depreciation fund (% of asset value or fixed amount)', 'UP Model Bye-Laws, 2011', 'bye-law 46(d)', 'BL_46', 'non_statutory', 'model_bye_law', 'num', '% or INR', 0, 100, 0, 10, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'none', FALSE, 'gated', ARRAY['fn_ensure_depreciation_fund', 'fn_appropriate_depreciation_fund']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'depreciation_fund_basis', 'Depreciation fund contribution basis', 'UP Model Bye-Laws, 2011', 'bye-law 46(d)', 'BL_46', 'non_statutory', 'model_bye_law', 'text', NULL, NULL, NULL, NULL, NULL, ARRAY['pct_of_asset_value', 'fixed_amount_per_sqft', 'fixed_amount_per_flat']::TEXT[], ARRAY[2]::INT[], 'none', FALSE, 'gated', ARRAY['fn_appropriate_depreciation_fund']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'depreciation_fund_rate', 'Depreciation fund rate (per sq ft or per flat)', 'UP Model Bye-Laws, 2011', 'bye-law 46(d)', 'BL_46', 'non_statutory', 'model_bye_law', 'num', 'INR per sq ft/flat', 0, 1000, 0, 10, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'none', FALSE, 'gated', ARRAY['fn_appropriate_depreciation_fund']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'investment_register', 'Bye-law 47 investment register maintained', 'UP Model Bye-Laws, 2011', 'bye-law 47', 'BL_47', 'non_statutory', 'model_bye_law', 'int', '0/1', 0, 1, 0, 1, ARRAY[]::TEXT[], ARRAY[2, 3]::INT[], 'higher', FALSE, 'tracked', ARRAY['fn_investment_register_check']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'affiliation_register', 'Bye-law 48 affiliation register maintained', 'UP Model Bye-Laws, 2011', 'bye-law 48', 'BL_48', 'non_statutory', 'model_bye_law', 'int', '0/1', 0, 1, 0, 1, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'none', FALSE, 'tracked', ARRAY['fn_affiliation_check']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'accounts_inspection_allowed', 'Bye-law 48 accounts open for member inspection', 'UP Model Bye-Laws, 2011', 'bye-law 48', 'BL_48', 'non_statutory', 'model_bye_law', 'int', '0/1', 0, 1, 0, 1, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'higher', FALSE, 'tracked', ARRAY['fn_accounts_inspection_check']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'accounts_publication_enabled', 'Bye-law 50 publication of accounts', 'UP Model Bye-Laws, 2011', 'bye-law 50', 'BL_50', 'non_statutory', 'model_bye_law', 'int', '0/1', 0, 1, 0, 1, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'none', FALSE, 'tracked', ARRAY['fn_accounts_publication_check']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'auditor_appointment_by_gbm', 'Bye-law 51 auditor appointed by General Body', 'UP Model Bye-Laws, 2011', 'bye-law 51', 'BL_51', 'non_statutory', 'model_bye_law', 'int', '0/1', 0, 1, 0, 1, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'none', FALSE, 'gated', ARRAY['fn_auditor_appointment_check']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'auditor_remuneration_gbm', 'Bye-law 52 auditor remuneration fixed by General Body', 'UP Model Bye-Laws, 2011', 'bye-law 52', 'BL_52', 'non_statutory', 'model_bye_law', 'int', '0/1', 0, 1, 0, 1, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'none', FALSE, 'gated', ARRAY['fn_auditor_remuneration_check']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'mortgage_notice_required', 'Bye-law 53 mortgage notice to association', 'UP Model Bye-Laws, 2011', 'bye-law 53', 'BL_53', 'non_statutory', 'model_bye_law', 'int', '0/1', 0, 1, 0, 1, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'none', FALSE, 'tracked', ARRAY['fn_mortgage_notice_check']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'unpaid_assessments_notice', 'Bye-law 54 notice of unpaid assessments on transfer', 'UP Model Bye-Laws, 2011', 'bye-law 54', 'BL_54', 'non_statutory', 'model_bye_law', 'int', '0/1', 0, 1, 0, 1, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'none', FALSE, 'tracked', ARRAY['fn_unpaid_assessments_notice']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'act_prevails_over_byelaws', 'Bye-law 55 Act prevails over bye-laws', 'UP Model Bye-Laws, 2011', 'bye-law 55', 'BL_55', 'non_statutory', 'model_bye_law', 'int', '0/1', 0, 1, 0, 1, ARRAY[]::TEXT[], ARRAY[]::INT[], 'none', FALSE, 'hard_wired', ARRAY['fn_act_prevails_check']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, 'UP Apartment Act 2010 provisions prevail over any inconsistent bye-law'),
 ('UP_AOA_2010', 'seal_register_maintained', 'Bye-law 56 common seal register', 'UP Model Bye-Laws, 2011', 'bye-law 56', 'BL_56', 'non_statutory', 'model_bye_law', 'int', '0/1', 0, 1, 0, 1, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'none', FALSE, 'tracked', ARRAY['fn_seal_register_check']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'ca_inspection', 'Bye-law 57 Competent Authority inspection', 'UP Model Bye-Laws, 2011', 'bye-law 57', 'BL_57', 'non_statutory', 'model_bye_law', 'int', '0/1', 0, 1, 0, 1, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'none', FALSE, 'tracked', ARRAY['fn_ca_inspection_check']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'bye_law_amendment_tracker', 'Bye-law 58 amendment tracking enabled', 'UP Model Bye-Laws, 2011', 'bye-law 58', 'BL_58', 'non_statutory', 'model_bye_law', 'int', '0/1', 0, 1, 0, 1, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'none', FALSE, 'tracked', ARRAY['fn_bye_law_amendment_log']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'arrears_interest_pct', 'Bye-law 46(a) arrears interest rate (per month)', 'UP Model Bye-Laws, 2011', 'bye-law 46(a)', 'BL_46', 'non_statutory', 'model_bye_law', 'num', '%/month', 0, 100, 0, 100, ARRAY[]::TEXT[], ARRAY[2]::INT[], 'none', FALSE, 'gated', ARRAY['fn_apply_receivable_interest', 'fn_auto_generate_receivables']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL),
 ('UP_AOA_2010', 'billing_basis_required', 'UP AOA society must bill common expenses by undivided interest (s.18(1))', 'UP Apartment (Promotion of Construction, Ownership and Maintenance) Act, 2010', 's.18(1)', NULL, 'statutory', 'state_act_rules', 'int', '0/1', 0, 1, 0, 1, ARRAY[]::TEXT[], ARRAY[]::INT[], 'none', FALSE, 'hard_wired', ARRAY['fn_auto_generate_receivables']::TEXT[], 'checked', DATE '2026-10-07', FALSE, TRUE, NULL)
ON CONFLICT DO NOTHING;

INSERT INTO regime_rule_parameters (regime_code, rule_key, value, value_text, unit, source_reference, effective_from) VALUES
 ('GENERIC', 'cash_limit_default_mode', NULL, 'warn', NULL, 'Engine policy, not statute: warn = record a compliance flag; block = refuse the posting', DATE '2000-01-01'),
 ('GENERIC', 'reserve_appropriation_pct', 25, NULL, '%', 'Engine policy: share of net surplus moved to the Reserve Fund at FY close. No state statute is loaded for this scheme; the society sets it by resolution', DATE '2000-01-01'),
 ('UP_AOA_2010', 's22_default_months', 6, NULL, 'months', 'UP Apartment Act 2010 s.22: service cut-off only after MORE than 6 months of default', DATE '2011-11-16'),
 ('UP_AOA_2010', 's22_notice_days', 7, NULL, 'days', 'UP Apartment Act 2010 s.22: 7 days notice to the defaulter', DATE '2011-11-16'),
 ('UP_AOA_2010', 's22_wait_months', 1, NULL, 'months', 'UP Apartment Act 2010 s.22: one-month wait after the certified copy is sent to the competent authority and the owner', DATE '2011-11-16'),
 ('UP_AOA_2010', 's22_appeal_days', 15, NULL, 'days', 'UP Apartment Act 2010 s.22: 15 days for the owner to appeal', DATE '2011-11-16'),
 ('UP_AOA_2010', 's20_recovery_months', 12, NULL, 'months', 'UP Apartment Act 2010 s.20(2): common expenses unpaid for more than 12 months may be recovered through the Competent Authority as arrears of land revenue', DATE '2011-11-16'),
 ('UP_AOA_2010', 'arrears_disqualify_days', 60, NULL, 'days', 'Model Bye-Laws 2011, bye-law 7: arrears of more than 60 days bar voting / standing for the Board', DATE '2011-11-16'),
 ('UP_AOA_2010', 'transfer_fee_pct', 0.5, NULL, '% of value', 'Model Bye-Laws 2011, bye-law 39: 1/2% of transfer value, payable by the transferor on a sale, to the association for the major-repair fund', DATE '2011-11-16'),
 ('UP_AOA_2010', 'nodues_deemed_days', 15, NULL, 'days', 'Model Bye-Laws 2011, bye-law 39: No Dues Certificate deemed granted if not refused within 15 days', DATE '2011-11-16'),
 ('UP_AOA_2010', 'cash_payment_cheque_threshold', 2500, NULL, 'INR', 'Model Bye-Laws 2011, financial provisions (bye-laws 46-52): payments above this by cheque (Secretary + one Board member). Pre-dates UPI/NEFT; this engine treats only mode=cash as the breach', DATE '2011-11-16'),
 ('UP_AOA_2010', 'petty_cash_limit', 20000, NULL, 'INR', 'Model Bye-Laws 2011, financial provisions (bye-laws 46-52): petty cash ceiling', DATE '2011-11-16'),
 ('UP_AOA_2010', 'statement_publish_due_month', 7, NULL, 'month', 'Model Bye-Laws 2011, bye-law 49: audited statement published by 31 July', DATE '2011-11-16'),
 ('UP_AOA_2010', 'statement_publish_due_day', 31, NULL, 'day', 'Model Bye-Laws 2011, bye-law 49', DATE '2011-11-16'),
 ('UP_AOA_2010', 'authority_copy_due_month', 8, NULL, 'month', 'Model Bye-Laws 2011, bye-law 49: copy to the competent authority by 15 August', DATE '2011-11-16'),
 ('UP_AOA_2010', 'authority_copy_due_day', 15, NULL, 'day', 'Model Bye-Laws 2011, bye-law 49', DATE '2011-11-16'),
 ('UP_AOA_2010', 'owner_summary_days', 15, NULL, 'days', 'Model Bye-Laws 2011, bye-law 49: summary to every owner within 15 days of publication', DATE '2011-11-16'),
 ('UP_AOA_2010', 'bye_law7_year_basis', NULL, 'financial_year', NULL, 'Bye-law 7 says "the year preceding the election". Whether that is the financial or the calendar year is contested (advocate commentary differs); default financial_year, overridable per call', DATE '2011-11-16'),
 ('UP_AOA_2010', 'cash_limit_default_mode', NULL, 'warn', NULL, 'Engine policy, not statute: warn = record a compliance flag; block = refuse the posting. Override per society in societies.cash_limit_mode', DATE '2011-11-16'),
 ('UP_AOA_2010', 'owner_loan_blocks_nodues', 1, NULL, '0/1', 'Engine policy (not statute): a loan outstanding from the association is a due to it, so the No Dues Certificate is not issued until it is recovered; the Board may instead record a refusal', DATE '2011-11-16'),
 ('UP_AOA_2010', 'owner_loan_counts_bye_law7', 0, NULL, '0/1', 'Engine policy (not statute): OFF by default - bye-law 7 speaks only of arrears of contributions for common expenses, so an overdue owner loan is not counted unless the society opts in on advice', DATE '2011-11-16'),
 ('UP_AOA_2010', 'owner_loan_counts_s22', 0, NULL, '0/1', 'Engine policy (not statute): off by default - s.22 concerns unpaid charges, so an overdue loan does not by itself justify cutting a service; enable only on advice', DATE '2011-11-16'),
 ('UP_AOA_2010', 'reserve_appropriation_pct', 25, NULL, '%', 'Engine policy (not statute): share of net surplus moved to the Reserve Fund at FY close. Neither the UP Apartment Act 2010 nor the 2011 Model Bye-Laws fix a percentage (common profits are only said to form the nucleus of the reserve funds); 25% follows the co-operative-society convention. Set it by General Body resolution', DATE '2011-11-16'),
 ('UP_AOA_2010', 'poll_quorum_pct', 30, NULL, '% of owners', 'Model Bye-Laws 2011, bye-law 9: the presence in person of 30 percent of owners is a quorum (a head-count of owners, not of votes)', DATE '2011-11-16'),
 ('UP_AOA_2010', 'poll_majority_pct', 51, NULL, '% of votes', 'Model Bye-Laws 2011, bye-law 2(e): ''majority'' of owners means owners holding 51 per cent of the votes; bye-law 8 weights each vote by the owner''s percentage in the Declaration (Act s.12(1)(f): percentage ''for all purposes, including voting'')', DATE '2011-11-16'),
 ('UP_AOA_2010', 'poll_majority_of', NULL, 'all_votes', NULL, 'Engine policy, not statute: bye-law 2(e) defines a majority as owners holding 51% of THE votes (read here as all eligible votes, so abstentions count against a motion), while bye-law 10 speaks of a majority of owners CASTING votes. The stricter reading is the default; choose votes_cast only on advice', DATE '2011-11-16'),
 ('UP_AOA_2010', 'owner_loan_resolution_mode', NULL, 'linked', NULL, 'Engine policy, not statute: bye-law 3(1)(f) allows a short-term loan to an owner ''with the consent of the apartment owners'' in an emergent necessity. linked = the loan must cite a passed Approve Owner Loan resolution of a General Body meeting with quorum; text = any resolution reference is accepted (the old behaviour)', DATE '2011-11-16'),
 ('UP_AOA_2010', 'owner_loan_max_term_days', 365, NULL, 'days', 'Engine policy, not statute: the bye-law says only ''short-term'' and fixes no number of days. Applied when owner_loan_resolution_mode = linked, where a repayment date is mandatory', DATE '2011-11-16'),
 ('UP_AOA_2010', 'entrance_fee', 1000, NULL, 'INR', 'Model Bye-Laws 2011, bye-law 4: entrance fee of ₹1,000 per owner on admission', DATE '2011-11-16'),
 ('UP_AOA_2010', 'share_face_value', 100, NULL, 'INR', 'Model Bye-Laws 2011, bye-law 5: one share per owner, face value set by General Body', DATE '2011-11-16'),
 ('UP_AOA_2010', 'cashbook_daily_signature', 1, NULL, '0/1', 'Model Bye-Laws 2011, bye-law 23(f): daily cashbook to be signed by the Secretary and one Board member', DATE '2011-11-16'),
 ('UP_AOA_2010', 'investment_allowed_types', NULL, 'coop_bank,trust_securities,approved_bank', NULL, 'Model Bye-Laws 2011, bye-law 45: investments only in co-operative banks, Trust Act securities, or banks approved by the Competent Authority', DATE '2011-11-16'),
 ('UP_AOA_2010', 'borrowing_ca_approval', 1, NULL, '0/1', 'Model Bye-Laws 2011, bye-law 44(d): borrowing requires Competent Authority approval', DATE '2011-11-16'),
 ('UP_AOA_2010', 'tenant_joint_liability', 1, NULL, '0/1', 'UP Apartment Act 2010 s.18(2): tenant is jointly liable with the owner for common expenses', DATE '2011-11-16'),
 ('UP_AOA_2010', 'board_election_voting_basis', NULL, 'undivided_interest', NULL, 'Model Bye-Laws 2011, bye-law 8: voting by percentage in Declaration (Act s.12(1)(f): percentage for all purposes including voting). Advisory polls may use one-apartment-one-vote.', DATE '2011-11-16'),
 ('UP_AOA_2010', 'depreciation_fund_pct', 5, NULL, '% or INR', 'Model Bye-Laws 2011, bye-law 46(d): depreciation fund for replacement of assets; rate set by General Body resolution (no statutory rate)', DATE '2011-11-16'),
 ('UP_AOA_2010', 'depreciation_fund_basis', NULL, 'pct_of_asset_value', NULL, 'Model Bye-Laws 2011, bye-law 46(d): basis for depreciation fund contribution', DATE '2011-11-16'),
 ('UP_AOA_2010', 'depreciation_fund_rate', 2.0, NULL, 'INR per sq ft/flat', 'Model Bye-Laws 2011, bye-law 46(d): rate when basis is fixed amount', DATE '2011-11-16'),
 ('UP_AOA_2010', 'investment_register', 1, NULL, '0/1', 'Model Bye-Laws 2011, bye-law 47: Board shall maintain a register of all investments', DATE '2011-11-16'),
 ('UP_AOA_2010', 'affiliation_register', 1, NULL, '0/1', 'Model Bye-Laws 2011, bye-law 48: association may affiliate with federation; register maintained', DATE '2011-11-16'),
 ('UP_AOA_2010', 'accounts_inspection_allowed', 1, NULL, '0/1', 'Model Bye-Laws 2011, bye-law 48: books of account open to inspection by any member at reasonable times', DATE '2011-11-16'),
 ('UP_AOA_2010', 'accounts_publication_enabled', 1, NULL, '0/1', 'Model Bye-Laws 2011, bye-law 50: annual accounts to be published and circulated to members', DATE '2011-11-16'),
 ('UP_AOA_2010', 'auditor_appointment_by_gbm', 1, NULL, '0/1', 'Model Bye-Laws 2011, bye-law 51: auditor appointed at each Annual General Body Meeting', DATE '2011-11-16'),
 ('UP_AOA_2010', 'auditor_remuneration_gbm', 1, NULL, '0/1', 'Model Bye-Laws 2011, bye-law 52: auditor remuneration fixed by General Body Meeting', DATE '2011-11-16'),
 ('UP_AOA_2010', 'mortgage_notice_required', 1, NULL, '0/1', 'Model Bye-Laws 2011, bye-law 53: owner must notify association of any mortgage/charge', DATE '2011-11-16'),
 ('UP_AOA_2010', 'unpaid_assessments_notice', 1, NULL, '0/1', 'Model Bye-Laws 2011, bye-law 54: association provides statement of unpaid assessments on transfer', DATE '2011-11-16'),
 ('UP_AOA_2010', 'act_prevails_over_byelaws', 1, NULL, '0/1', 'Model Bye-Laws 2011, bye-law 55: UP Apartment Act 2010 prevails over inconsistent bye-laws', DATE '2011-11-16'),
 ('UP_AOA_2010', 'seal_register_maintained', 1, NULL, '0/1', 'Model Bye-Laws 2011, bye-law 56: association shall have a common seal and maintain register of its use', DATE '2011-11-16'),
 ('UP_AOA_2010', 'ca_inspection', 1, NULL, '0/1', 'Model Bye-Laws 2011, bye-law 57: Competent Authority may inspect association records', DATE '2011-11-16'),
 ('UP_AOA_2010', 'bye_law_amendment_tracker', 1, NULL, '0/1', 'Model Bye-Laws 2011, bye-law 58: track all amendments to society bye-laws with GBM resolution references (2/3 majority + CA approval)', DATE '2011-11-16'),
 ('UP_AOA_2010', 'arrears_interest_pct', 1.75, NULL, '%/month', 'Model Bye-Laws 2011, bye-law 46(a): interest on overdue contributions is set by General Body resolution and recorded as a regime parameter; it is not a free default in the ledger.', DATE '2011-11-16'),
 ('UP_AOA_2010', 'billing_basis_required', 1, NULL, '0/1', 'UP Apartment Act 2010 s.18(1): common expenses are charged by percentage of undivided interest; for a UP AOA society this is the statutory basis, not an optional toggle.', DATE '2011-11-16')
ON CONFLICT DO NOTHING;
-- <<< END GENERATED

-- ── LAYERED RULE RESOLVER ─────────────────────────────────────────────────────
-- Effective value of a rule for a society on a date. Authority decides VALIDITY, specificity decides VALUE:
--   baseline  regime_rule_parameters (Layer 0 Act/Rules/Central, or Layer 1 Model Bye-Law, or an engine default)
--   then the society's own decisions, lowest layer first: 1 Model Bye-Law adoption, 2 Society policy (GBM),
--   3 Board decision (MC). A decision counts only if it is backed by a passed resolution (resolution_id),
--   has not been flagged on spot-check, is in date, and passes fn_rule_decision_check against the value
--   below it (inside the rule's limits; Layers 2-3 may only tighten). An invalid decision is ignored, never
--   applied. Statutory rules are Layer 0: no society decision can touch them. A Model Bye-Law clause recorded
--   'not adopted' (droppable rules only) resolves to value NULL = "rule not active".
-- p_below_layer lets the write path ask "what value applies beneath the layer I am about to set?".
CREATE OR REPLACE FUNCTION fn_rule_decision_check(
    p_society_id INT, p_key VARCHAR, p_layer INT, p_status VARCHAR,
    p_value NUMERIC, p_value_text TEXT, p_current_value NUMERIC, p_current_text TEXT, p_on DATE DEFAULT CURRENT_DATE)
RETURNS TEXT LANGUAGE plpgsql STABLE AS $$
DECLARE d rule_parameter_defs%ROWTYPE; v_pos INT; v_cur_pos INT;
BEGIN
    SELECT df.* INTO d FROM society_legal_regime slr
      JOIN rule_parameter_defs df ON df.regime_code = slr.regime_code AND df.rule_key = p_key
     WHERE slr.society_id = p_society_id;
    IF NOT FOUND THEN RETURN format('%s is not a configurable rule in this society''s legal scheme', p_key); END IF;
    IF p_layer NOT IN (1, 2, 3) THEN RETURN 'Layer must be 1, 2 or 3'; END IF;
    IF d.nature = 'statutory' THEN
        RETURN format('%s is fixed by %s (%s): it is Layer 0 and a society cannot vary or drop it', p_key, d.instrument, d.provision);
    END IF;
    IF p_status = 'adopted_as_is' THEN
        IF d.base_source <> 'model_bye_law' THEN RETURN format('%s is not a Model Bye-Law value, so there is nothing to adopt as-is; set a value', p_key); END IF;
        IF p_layer <> 1 THEN RETURN 'Adopting as-is is a Layer 1 (Model Bye-Law) decision'; END IF;
        RETURN NULL;
    ELSIF p_status = 'not_adopted' THEN
        IF p_layer <> 1 THEN RETURN 'Only a Model Bye-Law (Layer 1) rule can be recorded as not adopted'; END IF;
        IF NOT d.droppable THEN RETURN format('%s is backed by the Act/Rules or enforced by the engine and cannot be not-adopted', p_key); END IF;
        RETURN NULL;
    ELSIF p_status <> 'adopted_with_variation' THEN
        RETURN 'Unknown decision status';
    END IF;
    IF NOT (p_layer = ANY (d.layers)) THEN
        RETURN format('%s may be set at Layer %s only, not Layer %s', p_key, COALESCE(array_to_string(d.layers, '/'), '-'), p_layer);
    END IF;
    IF d.value_type = 'text' THEN
        IF p_value_text IS NULL OR NOT (p_value_text = ANY (d.choices)) THEN
            RETURN format('%s must be one of: %s', p_key, array_to_string(d.choices, ', '));
        END IF;
        IF p_layer >= 2 AND d.tighten <> 'none' AND p_current_text IS NOT NULL THEN
            v_pos := array_position(d.choices, p_value_text); v_cur_pos := array_position(d.choices, p_current_text);
            IF (d.tighten = 'higher' AND v_pos < v_cur_pos) OR (d.tighten = 'lower' AND v_pos > v_cur_pos) THEN
                RETURN format('A Layer %s decision may only tighten %s (%s), not loosen it to %s', p_layer, p_key, p_current_text, p_value_text);
            END IF;
        END IF;
        RETURN NULL;
    END IF;
    IF p_value IS NULL THEN RETURN format('%s needs a value', p_key); END IF;
    IF d.value_type = 'int' AND p_value <> trunc(p_value) THEN RETURN format('%s must be a whole number', p_key); END IF;
    IF (d.vary_min IS NOT NULL AND p_value < d.vary_min) OR (d.vary_max IS NOT NULL AND p_value > d.vary_max) THEN
        RETURN format('%s must be between %s and %s for a society decision', p_key, trim_scale(d.vary_min), trim_scale(d.vary_max));
    END IF;
    IF p_layer >= 2 AND d.tighten <> 'none' AND p_current_value IS NOT NULL THEN
        IF (d.tighten = 'lower' AND p_value > p_current_value) OR (d.tighten = 'higher' AND p_value < p_current_value) THEN
            RETURN format('A Layer %s decision may only tighten %s (now %s), not loosen it to %s', p_layer, p_key, trim_scale(p_current_value), trim_scale(p_value));
        END IF;
    END IF;
    RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION fn_rule(p_society_id INT, p_key VARCHAR, p_on DATE DEFAULT CURRENT_DATE, p_below_layer INT DEFAULT 4)
RETURNS TABLE (value NUMERIC, value_text TEXT, layer INT, status TEXT, source TEXT,
               nature TEXT, base_source TEXT, decision_id BIGINT, ignored INT)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_regime VARCHAR(30);
    b regime_rule_parameters%ROWTYPE;
    d rule_parameter_defs%ROWTYPE;
    r RECORD;   -- not %ROWTYPE: society_rule_decisions is created later in this file
    v_val NUMERIC; v_txt TEXT; v_layer INT; v_status TEXT; v_source TEXT; v_dec BIGINT := NULL; v_ign INT := 0; v_err TEXT;
BEGIN
    SELECT slr.regime_code INTO v_regime FROM society_legal_regime slr WHERE slr.society_id = p_society_id;
    IF v_regime IS NULL THEN RETURN; END IF;
    SELECT rp.* INTO b FROM regime_rule_parameters rp
     WHERE rp.regime_code = v_regime AND rp.rule_key = p_key
       AND rp.effective_from <= p_on AND (rp.effective_to IS NULL OR rp.effective_to >= p_on)
     ORDER BY rp.effective_from DESC LIMIT 1;
    IF NOT FOUND THEN RETURN; END IF;
    v_val := b.value; v_txt := b.value_text; v_source := b.source_reference;
    SELECT df.* INTO d FROM rule_parameter_defs df WHERE df.regime_code = v_regime AND df.rule_key = p_key;
    IF NOT FOUND THEN
        RETURN QUERY SELECT v_val, v_txt, NULL::INT, 'baseline'::TEXT, v_source, NULL::TEXT, NULL::TEXT, NULL::BIGINT, 0;
        RETURN;
    END IF;
    v_layer := CASE d.base_source WHEN 'central' THEN 0 WHEN 'state_act_rules' THEN 0 WHEN 'model_bye_law' THEN 1 ELSE NULL END;
    v_status := CASE d.base_source WHEN 'model_bye_law' THEN 'model_default' WHEN 'engine_default' THEN 'engine_default' ELSE 'statute' END;

    IF d.nature = 'non_statutory' THEN
        FOR r IN
            SELECT q.* FROM (
                SELECT DISTINCT ON (x.layer) x.* FROM society_rule_decisions x
                WHERE x.society_id = p_society_id AND x.rule_key = p_key AND x.layer < p_below_layer
                  AND x.status IN ('adopted_as_is', 'adopted_with_variation', 'not_adopted')
                  AND x.resolution_id IS NOT NULL AND x.review_status <> 'flagged'
                  AND x.effective_from <= p_on AND (x.effective_to IS NULL OR x.effective_to >= p_on)
                  -- Exclude Layer 3 decisions that are pending/expired/rejected ratification:
                  -- the Board is acting within delegated powers, but until the GBM ratifies,
                  -- the engine falls through to the Society policy (Layer 2) beneath it.
                  AND NOT EXISTS (
                      SELECT 1 FROM loa_ratification lr WHERE lr.decision_id = x.id AND lr.status IN ('pending', 'expired')
                  )
                ORDER BY x.layer, x.effective_from DESC, x.id DESC) q
            ORDER BY q.layer
        LOOP
            IF r.status = 'not_adopted' THEN
                IF r.layer = 1 AND d.droppable THEN
                    RETURN QUERY SELECT NULL::NUMERIC, NULL::TEXT, 1, 'not_adopted'::TEXT,
                                        'Not adopted by the society (Model Bye-Law clause dropped by resolution)'::TEXT,
                                        d.nature::TEXT, d.base_source::TEXT, r.id, v_ign;
                    RETURN;
                END IF;
                v_ign := v_ign + 1; CONTINUE;
            END IF;
            v_err := fn_rule_decision_check(p_society_id, p_key, r.layer, r.status, r.value, r.value_text, v_val, v_txt, p_on);
            IF v_err IS NOT NULL THEN v_ign := v_ign + 1; CONTINUE; END IF;
            IF r.status = 'adopted_as_is' THEN
                v_layer := 1; v_status := 'adopted_as_is'; v_source := 'Model Bye-Law adopted as-is by the society'; v_dec := r.id;
            ELSE
                v_val := r.value; v_txt := r.value_text; v_layer := r.layer; v_status := 'adopted_with_variation'; v_dec := r.id;
                v_source := CASE r.layer WHEN 1 THEN 'Model Bye-Law variation (General Body resolution)'
                                         WHEN 2 THEN 'Society policy (General Body resolution)'
                                         ELSE 'Board decision (Managing Committee resolution)' END;
            END IF;
        END LOOP;
    END IF;
    RETURN QUERY SELECT v_val, v_txt, v_layer, v_status, v_source, d.nature::TEXT, d.base_source::TEXT, v_dec, v_ign;
END $$;

-- Every SQL function reads rules through these two, so a society's adopted variation reaches the engine
-- with no change at the call sites. With no decisions they return exactly the regime baseline, as before.
CREATE OR REPLACE FUNCTION fn_regime_param_num(p_society_id INT, p_key VARCHAR, p_on DATE DEFAULT CURRENT_DATE)
RETURNS NUMERIC LANGUAGE sql STABLE AS $$
    SELECT r.value FROM fn_rule(p_society_id, p_key, p_on) r
$$;

CREATE OR REPLACE FUNCTION fn_regime_param_text(p_society_id INT, p_key VARCHAR, p_on DATE DEFAULT CURRENT_DATE)
RETURNS TEXT LANGUAGE sql STABLE AS $$
    SELECT r.value_text FROM fn_rule(p_society_id, p_key, p_on) r
$$;

-- ───────────────────────────────────────────────────────────────────────────────
-- Statutory heads added for UP (live DBs; fresh installs get them from seed.py)
-- and corrections to mappings that were wrong in the original seed.
-- ───────────────────────────────────────────────────────────────────────────────
INSERT INTO statutory_head_catalog
    (regime_code, head_code, parent_head_code, statement_section, label, display_order,
     is_statutory_required, source_reference, effective_from)
SELECT 'UP_AOA_2010', v.head_code, NULL, 'Liabilities', v.label, v.ord, v.req, v.src, DATE '2011-11-16'
FROM (VALUES
    ('MAJOR_REPAIR_FUND', 'Major Repair Fund (Transfer-Fee ½%)', 15, TRUE,
     'Model Bye-Laws 2011, bye-law 39 (½% of transfer value held for major repairs)'),
    ('SINKING_FUND', 'Sinking Fund (voluntary; no statutory rate in UP)', 25, FALSE,
     'Not prescribed by the UP Apartment Act 2010 or the 2011 Model Bye-Laws; levied by general-body resolution')
) AS v(head_code, label, ord, req, src)
WHERE EXISTS (SELECT 1 FROM legal_regime_profiles WHERE code = 'UP_AOA_2010')
ON CONFLICT (regime_code, head_code) DO NOTHING;

-- Sinking Fund (3210) was mapped to IFMS_CORPUS "per Sec 14(5)": wrong head. The
-- builder's corpus handover (3230) is the s.14(5) interest-free maintenance security.
UPDATE account_statutory_mappings
   SET head_code = 'SINKING_FUND',
       source_reference = 'Sinking Fund: voluntary fund, no statutory rate in UP (Act 2010 / Model Bye-Laws 2011)',
       updated_at = NOW()
 WHERE regime_code = 'UP_AOA_2010' AND account_id = 3210 AND head_code = 'IFMS_CORPUS'
   AND EXISTS (SELECT 1 FROM statutory_head_catalog WHERE regime_code = 'UP_AOA_2010' AND head_code = 'SINKING_FUND');

UPDATE account_statutory_mappings
   SET head_code = 'IFMS_CORPUS',
       source_reference = 'Corpus Fund (builder handover) is the interest-free maintenance security under UP Apartment Act 2010 s.14(5)',
       updated_at = NOW()
 WHERE regime_code = 'UP_AOA_2010' AND account_id = 3230 AND head_code = 'RESERVE_FUND';

UPDATE account_statutory_mappings
   SET source_reference = regexp_replace(source_reference, 'Model Bye-Laws Ch\.VII', 'Model Bye-Laws 2011, bye-law 46'),
       updated_at = NOW()
 WHERE regime_code = 'UP_AOA_2010' AND source_reference LIKE '%Ch.VII%';

UPDATE statutory_head_catalog SET updated_at = NOW(), source_reference = CASE head_code
    WHEN 'IFMS_CORPUS'            THEN 'UP Apartment Act 2010, Sec 14(5)'
    WHEN 'RESERVE_FUND'           THEN 'Model Bye-Laws 2011, bye-laws 3(1)(d) and 46; Act Sec 14(8)(a)'
    WHEN 'CAPITAL_ACCOUNT'        THEN 'Model Bye-Laws 2011, bye-laws 5 and 46 (share capital, ₹1,000 entrance fee)'
    WHEN 'STAFF_BENEFITS_PAYABLE' THEN 'Model Bye-Laws 2011, bye-law 3(1)(h)'
    WHEN 'COMMON_EXPENSES_PAYABLE' THEN 'UP Apartment Act 2010, Sec 18, 20; Model Bye-Laws 2011, bye-law 35'
    WHEN 'SUNDRY_DEBTORS'         THEN 'UP Apartment Act 2010, Sec 18, 20; Model Bye-Laws 2011, bye-law 35'
    WHEN 'REPAIR_MAINTENANCE_EXP' THEN 'Model Bye-Laws 2011, bye-law 3'
    WHEN 'COMMON_PROFITS'         THEN 'UP Apartment Act 2010, Sec 14(8)(a), 18(1); Model Bye-Laws 2011, bye-law 3(1)(d)'
    ELSE source_reference END
 WHERE regime_code = 'UP_AOA_2010'
   AND head_code IN ('IFMS_CORPUS','RESERVE_FUND','CAPITAL_ACCOUNT','STAFF_BENEFITS_PAYABLE',
                     'COMMON_EXPENSES_PAYABLE','SUNDRY_DEBTORS','REPAIR_MAINTENANCE_EXP','COMMON_PROFITS');

UPDATE state_compliance_thresholds
   SET notes = 'No sinking-fund / repair-fund percentage is prescribed by the UP Apartment Act 2010 or the 2011 Model Bye-Laws. '
               || 'The rate is set by general-body resolution or the promoter agreement.',
       updated_at = NOW()
 WHERE state = 'UP'
   AND threshold_key IN ('sinking_fund_pct_construction_cost', 'repair_fund_pct_construction_cost')
   AND notes LIKE '%Ch.VII%';

-- ───────────────────────────────────────────────────────────────────────────────
-- 1. Undivided interest (Act s.5(2), s.12(1)(f), s.18(1)) — the Declaration's % per flat
-- ───────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_undivided_interest_report(p_society_id INT)
RETURNS TABLE (apartment_id INT, flat_number VARCHAR, apartment_size INT,
               declared_pct NUMERIC, area_based_pct NUMERIC, variance_pct NUMERIC, status TEXT)
LANGUAGE sql STABLE AS $$
    WITH t AS (SELECT NULLIF(SUM(a.apartment_size), 0) AS tot
               FROM apartments a WHERE a.society_id = p_society_id AND a.active)
    SELECT a.id, a.flat_number, a.apartment_size,
           a.undivided_interest_pct,
           ROUND(a.apartment_size::NUMERIC / t.tot * 100, 6),
           ROUND(a.undivided_interest_pct - a.apartment_size::NUMERIC / t.tot * 100, 6),
           CASE WHEN a.undivided_interest_pct IS NULL THEN 'missing'
                WHEN ABS(a.undivided_interest_pct - a.apartment_size::NUMERIC / t.tot * 100) <= 0.01 THEN 'matches_area'
                ELSE 'differs_from_area' END
    FROM apartments a CROSS JOIN t
    WHERE a.society_id = p_society_id AND a.active
    ORDER BY a.flat_number
$$;

CREATE OR REPLACE FUNCTION fn_undivided_interest_summary(p_society_id INT)
RETURNS TABLE (apartments_total INT, apartments_missing INT, total_declared_pct NUMERIC, balanced BOOLEAN)
LANGUAGE sql STABLE AS $$
    SELECT COUNT(*)::INT,
           COUNT(*) FILTER (WHERE undivided_interest_pct IS NULL)::INT,
           COALESCE(SUM(undivided_interest_pct), 0),
           COUNT(*) FILTER (WHERE undivided_interest_pct IS NULL) = 0
             AND ABS(COALESCE(SUM(undivided_interest_pct), 0) - 100) <= 0.001
    FROM apartments WHERE society_id = p_society_id AND active
$$;

-- Fills NULLs from the area share. The Declaration is authoritative: if it weights
-- by something other than area, enter its figures instead of using this.
CREATE OR REPLACE FUNCTION fn_backfill_undivided_interest(p_society_id INT, p_overwrite BOOLEAN DEFAULT FALSE)
RETURNS INT LANGUAGE plpgsql AS $$
DECLARE v_tot NUMERIC; v_n INT;
BEGIN
    SELECT SUM(apartment_size) INTO v_tot FROM apartments
     WHERE society_id = p_society_id AND active AND apartment_size > 0;
    IF v_tot IS NULL OR v_tot = 0 THEN RETURN 0; END IF;
    UPDATE apartments
       SET undivided_interest_pct = ROUND(apartment_size::NUMERIC / v_tot * 100, 6), updated_at = NOW()
     WHERE society_id = p_society_id AND active AND apartment_size > 0
       AND (p_overwrite OR undivided_interest_pct IS NULL);
    GET DIAGNOSTICS v_n = ROW_COUNT;

    -- 6-decimal rounding can leave the total a hair off 100; give the residual to the largest
    -- flat, but only when every active flat now has a percentage (never disturb a partial fill).
    IF NOT EXISTS (SELECT 1 FROM apartments WHERE society_id = p_society_id AND active AND undivided_interest_pct IS NULL) THEN
        UPDATE apartments SET undivided_interest_pct = undivided_interest_pct
               + (100 - (SELECT SUM(undivided_interest_pct) FROM apartments WHERE society_id = p_society_id AND active))
         WHERE id = (SELECT id FROM apartments WHERE society_id = p_society_id AND active
                      ORDER BY undivided_interest_pct DESC, id LIMIT 1)
           AND ABS(100 - (SELECT SUM(undivided_interest_pct) FROM apartments WHERE society_id = p_society_id AND active)) < 0.001;
    END IF;
    RETURN v_n;
END $$;

-- ───────────────────────────────────────────────────────────────────────────────
-- 2. Major Repair Fund + ½% transfer fee + No Dues deemed grant (bye-law 39)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_ensure_major_repair_fund(p_society_id INT)
RETURNS INT LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO accounts (id, society_id, name, tab_name, header, parent_account_id,
                          drcr_account, has_bf, depreciation_percent, is_depreciable)
    SELECT 3270, p_society_id, 'Major Repair Fund (Transfer Fee)', 'MajRepFund', 'Major Repair Fund',
           (SELECT 3200 FROM accounts WHERE society_id = p_society_id AND id = 3200),
           'Cr', TRUE, 100, FALSE
    WHERE NOT EXISTS (SELECT 1 FROM accounts WHERE society_id = p_society_id AND id = 3270);

    INSERT INTO account_statutory_mappings
        (society_id, account_id, regime_code, head_code, effective_from, source_reference)
    SELECT p_society_id, 3270, slr.regime_code, 'MAJOR_REPAIR_FUND', DATE '2011-11-16',
           'Model Bye-Laws 2011, bye-law 39'
    FROM society_legal_regime slr
    WHERE slr.society_id = p_society_id AND slr.regime_code = 'UP_AOA_2010'
      AND EXISTS (SELECT 1 FROM statutory_head_catalog WHERE regime_code = 'UP_AOA_2010' AND head_code = 'MAJOR_REPAIR_FUND')
    ON CONFLICT DO NOTHING;
    RETURN 3270;
END $$;

-- 3. Depreciation Fund (bye-law 46(d))
-- ───────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_ensure_depreciation_fund(p_society_id INT)
RETURNS INT LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO accounts (id, society_id, name, tab_name, header, parent_account_id,
                          drcr_account, has_bf, depreciation_percent, is_depreciable)
    SELECT 3240, p_society_id, 'Depreciation Fund', 'DeprFund', 'Depreciation Fund',
           (SELECT 3200 FROM accounts WHERE society_id = p_society_id AND id = 3200),
           'Cr', TRUE, 100, FALSE
    WHERE NOT EXISTS (SELECT 1 FROM accounts WHERE society_id = p_society_id AND id = 3240);

    INSERT INTO account_statutory_mappings
        (society_id, account_id, regime_code, head_code, effective_from, source_reference)
    SELECT p_society_id, 3240, slr.regime_code, 'DEPRECIATION_FUND', DATE '2011-11-16',
           'Model Bye-Laws 2011, bye-law 46(d)'
    FROM society_legal_regime slr
    WHERE slr.society_id = p_society_id AND slr.regime_code = 'UP_AOA_2010'
      AND EXISTS (SELECT 1 FROM statutory_head_catalog WHERE regime_code = 'UP_AOA_2010' AND head_code = 'DEPRECIATION_FUND')
    ON CONFLICT DO NOTHING;
    RETURN 3240;
END $$;

CREATE OR REPLACE FUNCTION fn_appropriate_depreciation_fund(
    p_society_id INT, p_as_of DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (appropriation_id INT, amount NUMERIC(14,2), msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_basis TEXT;
    v_pct NUMERIC;
    v_rate NUMERIC;
    v_asset_value NUMERIC(18,2);
    v_total_sqft NUMERIC(14,2);
    v_total_flats INT;
    v_appropriation_amount NUMERIC(18,2);
    v_fund_acc INT;
    v_rec_id INT;
    v_period_start DATE;
    v_period_end DATE;
BEGIN
    v_basis := fn_regime_param_text(p_society_id, 'depreciation_fund_basis', p_as_of);
    v_pct   := fn_regime_param_num(p_society_id, 'depreciation_fund_pct', p_as_of);
    v_rate  := fn_regime_param_num(p_society_id, 'depreciation_fund_rate', p_as_of);

    IF v_basis IS NULL OR v_pct IS NULL THEN
        appropriation_id := NULL; amount := NULL;
        msg := 'Error: depreciation fund parameters not set for this society/regime';
        RETURN NEXT; RETURN;
    END IF;

    v_fund_acc := fn_ensure_depreciation_fund(p_society_id);

    v_period_start := DATE_TRUNC('year', p_as_of)::DATE;
    v_period_end   := (v_period_start + INTERVAL '1 year - 1 day')::DATE;

    IF v_basis = 'pct_of_asset_value' THEN
        SELECT COALESCE(SUM(purchase_value), 0) INTO v_asset_value
        FROM assets
        WHERE society_id = p_society_id
          AND purchase_date <= v_period_end
          AND (disposed_at IS NULL OR disposed_at > v_period_end);
        v_appropriation_amount := ROUND(v_asset_value * v_pct / 100, 2);
    ELSIF v_basis = 'fixed_amount_per_sqft' THEN
        SELECT COALESCE(SUM(built_up_area), 0) INTO v_total_sqft
        FROM apartments
        WHERE society_id = p_society_id;
        v_appropriation_amount := ROUND(v_total_sqft * COALESCE(v_rate, 0), 2);
    ELSIF v_basis = 'fixed_amount_per_flat' THEN
        SELECT COUNT(*) INTO v_total_flats
        FROM apartments
        WHERE society_id = p_society_id;
        v_appropriation_amount := ROUND(v_total_flats * COALESCE(v_rate, 0), 2);
    ELSE
        appropriation_id := NULL; amount := NULL;
        msg := 'Error: invalid depreciation_fund_basis value: ' || v_basis;
        RETURN NEXT; RETURN;
    END IF;

    IF v_appropriation_amount <= 0 THEN
        appropriation_id := NULL; amount := 0;
        msg := 'No appropriation needed (calculated amount is zero or negative)';
        RETURN NEXT; RETURN;
    END IF;

    INSERT INTO receivables (society_id, entity_id, role, acc_id, description,
                             base_amount, interest_amount, amount, due_date, status, charge_kind)
    VALUES (p_society_id, 0, 'society', v_fund_acc,
            'Depreciation Fund appropriation for FY ' || EXTRACT(YEAR FROM v_period_start)::INT
            || ' (basis: ' || v_basis || ', pct: ' || trim_scale(v_pct) || '%, rate: ' || trim_scale(v_rate) || ')',
            v_appropriation_amount, 0, v_appropriation_amount, v_period_end, 'pending', 'depreciation_fund')
    RETURNING id INTO v_rec_id;

    appropriation_id := v_rec_id;
    amount := v_appropriation_amount;
    msg := 'OK: Depreciation Fund appropriation created for ' || v_appropriation_amount;
    RETURN NEXT; RETURN;
END $$;

-- 4. Investment Register (bye-law 47)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE investment_register (
    id              SERIAL PRIMARY KEY,
    society_id      INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    investment_date DATE NOT NULL,
    institution     VARCHAR(100) NOT NULL,
    institution_type VARCHAR(30) NOT NULL CHECK (institution_type IN ('coop_bank', 'trust_securities', 'approved_bank', 'other')),
    amount          NUMERIC(14,2) NOT NULL CHECK (amount >= 0),
    maturity_date   DATE,
    rate_pct        NUMERIC(6,3),
    purpose         VARCHAR(200),
    resolution_id   INT,
    created_by      INT REFERENCES users (id),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_investment_register_society ON investment_register (society_id, investment_date);

CREATE OR REPLACE FUNCTION fn_investment_register_check(p_society_id INT, p_as_of DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (total_invested NUMERIC, compliant BOOLEAN, msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_allowed_types TEXT;
    v_total NUMERIC;
    v_enabled INT;
BEGIN
    v_enabled := COALESCE(fn_regime_param_num(p_society_id, 'investment_register', p_as_of)::INT, 1);
    IF v_enabled = 0 THEN
        total_invested := 0; compliant := TRUE;
        msg := 'OK: Investment register check skipped (disabled by bye-law 47)';
        RETURN NEXT; RETURN;
    END IF;
    v_allowed_types := fn_regime_param_text(p_society_id, 'investment_allowed_types', p_as_of);
    IF v_allowed_types IS NULL THEN
        total_invested := 0; compliant := TRUE;
        msg := 'Investment register check: no allowed types configured';
        RETURN NEXT; RETURN;
    END IF;

    SELECT COALESCE(SUM(amount), 0) INTO v_total
    FROM investment_register
    WHERE society_id = p_society_id;

    -- Check if any investment is in a non-allowed type
    WITH non_compliant AS (
        SELECT 1 FROM investment_register
        WHERE society_id = p_society_id
          AND institution_type = 'other'
          AND investment_date <= p_as_of
    )
    SELECT CASE WHEN EXISTS (SELECT 1 FROM non_compliant) THEN FALSE ELSE TRUE END INTO compliant;

    total_invested := v_total;
    msg := 'OK: Investment register check completed';
    RETURN NEXT; RETURN;
END $$;

-- 4b. Affiliation Register (bye-law 48)
-- ───────────────────────────────────────────────────────────────────────────────
-- Model Bye-Law 48: Association may affiliate with a federation/apex body
CREATE TABLE affiliation_register (
    id                  SERIAL PRIMARY KEY,
    society_id          INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    federation_name     VARCHAR(150) NOT NULL,
    affiliation_date    DATE NOT NULL,
    affiliation_number  VARCHAR(50),
    expiry_date         DATE,
    resolution_id       INT,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_by          INT REFERENCES users (id),
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_affiliation_register_society ON affiliation_register (society_id, is_active);

CREATE OR REPLACE FUNCTION fn_affiliation_check(p_society_id INT, p_as_of DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (total_affiliations INT, active_affiliations INT, msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_total INT;
    v_active INT;
    v_enabled INT;
BEGIN
    v_enabled := COALESCE(fn_regime_param_num(p_society_id, 'affiliation_register', p_as_of)::INT, 1);
    IF v_enabled = 0 THEN
        total_affiliations := 0; active_affiliations := 0;
        msg := 'OK: Affiliation register check skipped (disabled by bye-law 48)';
        RETURN NEXT; RETURN;
    END IF;
    SELECT COUNT(*) INTO v_total
    FROM affiliation_register
    WHERE society_id = p_society_id;

    SELECT COUNT(*) INTO v_active
    FROM affiliation_register
    WHERE society_id = p_society_id
      AND is_active
      AND (expiry_date IS NULL OR expiry_date >= p_as_of);

    total_affiliations := v_total;
    active_affiliations := v_active;
    msg := 'OK: Affiliation register check completed';
    RETURN NEXT; RETURN;
END $$;

-- 5. Accounts Inspection (bye-law 48)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE accounts_inspection_log (
    id              SERIAL PRIMARY KEY,
    society_id      INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    member_id       INT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    apartment_id    INT REFERENCES apartments (id) ON DELETE SET NULL,
    inspection_date DATE NOT NULL,
    records_viewed  VARCHAR(500),
    created_by      INT REFERENCES users (id),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_accounts_inspection_log_society ON accounts_inspection_log (society_id, inspection_date);

CREATE OR REPLACE FUNCTION fn_accounts_inspection_check(p_society_id INT, p_as_of DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (inspection_count INT, compliant BOOLEAN, msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_count INT;
    v_enabled INT;
BEGIN
    v_enabled := COALESCE(fn_regime_param_num(p_society_id, 'accounts_inspection_allowed', p_as_of)::INT, 1);
    IF v_enabled = 0 THEN
        inspection_count := 0; compliant := TRUE;
        msg := 'OK: Accounts inspection check skipped (disabled by bye-law 48)';
        RETURN NEXT; RETURN;
    END IF;
    SELECT COUNT(*) INTO v_count
    FROM accounts_inspection_log
    WHERE society_id = p_society_id AND inspection_date <= p_as_of;

    inspection_count := v_count;
    compliant := TRUE; -- Always compliant if register exists
    msg := 'OK: Accounts inspection log available';
    RETURN NEXT; RETURN;
END $$;

-- 5b. Publication of Accounts (bye-law 50)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE accounts_publication (
    id              SERIAL PRIMARY KEY,
    society_id      INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    financial_year  INT NOT NULL,
    published_on    DATE,
    authority_copy_sent_on DATE,
    owner_summary_sent_on DATE,
    published_by    INT REFERENCES users (id),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_accounts_publication UNIQUE (society_id, financial_year)
);
CREATE INDEX idx_accounts_publication_society ON accounts_publication (society_id, financial_year);

CREATE OR REPLACE FUNCTION fn_accounts_publication_check(p_society_id INT, p_fy INT)
RETURNS TABLE (published BOOLEAN, published_on DATE, authority_copy_sent BOOLEAN, owner_summary_sent BOOLEAN, msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_pub accounts_publication%ROWTYPE;
    v_enabled INT;
BEGIN
    v_enabled := COALESCE(fn_regime_param_num(p_society_id, 'accounts_publication_enabled', CURRENT_DATE)::INT, 1);
    IF v_enabled = 0 THEN
        published := FALSE; published_on := NULL;
        authority_copy_sent := FALSE; owner_summary_sent := FALSE;
        msg := 'OK: Accounts publication check skipped (disabled by bye-law 50)';
        RETURN NEXT; RETURN;
    END IF;
    SELECT * INTO v_pub
    FROM accounts_publication
    WHERE society_id = p_society_id AND financial_year = p_fy;

    IF NOT FOUND THEN
        published := FALSE; published_on := NULL;
        authority_copy_sent := FALSE; owner_summary_sent := FALSE;
        msg := 'Warning: Accounts not yet published for FY ' || p_fy || ' (Bye-law 50)';
        RETURN NEXT; RETURN;
    END IF;

    published := v_pub.published_on IS NOT NULL;
    published_on := v_pub.published_on;
    authority_copy_sent := v_pub.authority_copy_sent_on IS NOT NULL;
    owner_summary_sent := v_pub.owner_summary_sent_on IS NOT NULL;

    IF published AND authority_copy_sent AND owner_summary_sent THEN
        msg := 'OK: Accounts fully published for FY ' || p_fy;
    ELSE
        msg := 'Partial: Accounts published=' || published::TEXT || ', authority copy=' || authority_copy_sent::TEXT || ', owner summary=' || owner_summary_sent::TEXT;
    END IF;
    RETURN NEXT; RETURN;
END $$;

-- 6. Auditor Appointment (bye-laws 51-52)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE auditor_appointments (
    id                  SERIAL PRIMARY KEY,
    society_id          INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    auditor_name        VARCHAR(100) NOT NULL,
    auditor_firm        VARCHAR(100),
    membership_number   VARCHAR(30),
    appointment_date    DATE NOT NULL,
    financial_year_from INT NOT NULL,
    financial_year_to   INT NOT NULL,
    remuneration        NUMERIC(12,2),
    resolution_id       INT,
    created_by          INT REFERENCES users (id),
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_auditor_appointments_society ON auditor_appointments (society_id, financial_year_from);

CREATE OR REPLACE FUNCTION fn_auditor_appointment_check(p_society_id INT, p_fy INT)
RETURNS TABLE (appointed BOOLEAN, auditor_name VARCHAR, msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_auditor_name VARCHAR;
    v_exists BOOLEAN;
    v_enabled INT;
BEGIN
    v_enabled := COALESCE(fn_regime_param_num(p_society_id, 'auditor_appointment_by_gbm', CURRENT_DATE)::INT, 1);
    IF v_enabled = 0 THEN
        appointed := FALSE; auditor_name := NULL;
        msg := 'OK: Auditor appointment check skipped (disabled by bye-law 51)';
        RETURN NEXT; RETURN;
    END IF;
    SELECT auditor_appointments.auditor_name INTO v_auditor_name
    FROM auditor_appointments
    WHERE society_id = p_society_id AND financial_year_from = p_fy
    ORDER BY appointment_date DESC LIMIT 1;

    v_exists := v_auditor_name IS NOT NULL;
    appointed := v_exists;
    auditor_name := v_auditor_name;
    IF v_exists THEN
        msg := 'OK: Auditor appointed for FY ' || p_fy;
    ELSE
        msg := 'Warning: No auditor appointed for FY ' || p_fy || ' (Bye-law 51)';
    END IF;
    RETURN NEXT; RETURN;
END $$;

CREATE OR REPLACE FUNCTION fn_auditor_remuneration_check(p_society_id INT, p_fy INT)
RETURNS TABLE (remuneration_fixed BOOLEAN, remuneration NUMERIC, msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_rem NUMERIC;
    v_enabled INT;
BEGIN
    v_enabled := COALESCE(fn_regime_param_num(p_society_id, 'auditor_remuneration_gbm', CURRENT_DATE)::INT, 1);
    IF v_enabled = 0 THEN
        remuneration_fixed := FALSE; remuneration := NULL;
        msg := 'OK: Auditor remuneration check skipped (disabled by bye-law 52)';
        RETURN NEXT; RETURN;
    END IF;
    SELECT auditor_appointments.remuneration INTO v_rem
    FROM auditor_appointments
    WHERE society_id = p_society_id AND financial_year_from = p_fy
    ORDER BY appointment_date DESC LIMIT 1;

    remuneration_fixed := v_rem IS NOT NULL;
    remuneration := v_rem;
    IF v_rem IS NOT NULL THEN
        msg := 'OK: Auditor remuneration fixed at ' || v_rem;
    ELSE
        msg := 'Warning: Auditor remuneration not fixed for FY ' || p_fy || ' (Bye-law 52)';
    END IF;
    RETURN NEXT; RETURN;
END $$;

-- 7. Mortgage Notice Register (bye-law 53)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE mortgage_notices (
    id              SERIAL PRIMARY KEY,
    society_id      INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    apartment_id    INT NOT NULL REFERENCES apartments (id) ON DELETE CASCADE,
    mortgagee_name  VARCHAR(100) NOT NULL,
    mortgagee_address VARCHAR(200),
    loan_amount     NUMERIC(14,2),
    mortgage_date   DATE NOT NULL,
    notice_received_on DATE NOT NULL,
    created_by      INT REFERENCES users (id),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_mortgage_notices_society ON mortgage_notices (society_id, apartment_id);

CREATE OR REPLACE FUNCTION fn_mortgage_notice_check(p_society_id INT, p_as_of DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (total_notices INT, pending_notices INT, msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_total INT;
    v_pending INT;
    v_enabled INT;
BEGIN
    v_enabled := COALESCE(fn_regime_param_num(p_society_id, 'mortgage_notice_required', p_as_of)::INT, 1);
    IF v_enabled = 0 THEN
        total_notices := 0; pending_notices := 0;
        msg := 'OK: Mortgage notice check skipped (disabled by bye-law 53)';
        RETURN NEXT; RETURN;
    END IF;
    SELECT COUNT(*) INTO v_total
    FROM mortgage_notices
    WHERE society_id = p_society_id AND notice_received_on <= p_as_of;

    -- Pending: notices received but not yet acknowledged by Board
    SELECT COUNT(*) INTO v_pending
    FROM mortgage_notices mn
    WHERE mn.society_id = p_society_id
      AND mn.notice_received_on <= p_as_of
      AND NOT EXISTS (
          SELECT 1 FROM resolutions r
          JOIN meetings m ON r.meeting_id = m.id
          WHERE m.society_id = p_society_id
            AND r.resolution_type = 'mortgage_notice_acknowledged'
            AND r.reference_id = mn.id
            AND r.status = 'passed'
      );

    total_notices := v_total;
    pending_notices := v_pending;
    msg := 'OK: Mortgage notice register check completed';
    RETURN NEXT; RETURN;
END $$;

-- 8. Unpaid Assessments Notice (bye-law 54)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_unpaid_assessments_notice(
    p_society_id INT, p_apartment_id INT, p_as_of DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (apartment_id INT, flat_number VARCHAR, total_unpaid NUMERIC, oldest_due DATE, msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_flat VARCHAR;
    v_total NUMERIC;
    v_oldest DATE;
    v_enabled INT;
BEGIN
    v_enabled := COALESCE(fn_regime_param_num(p_society_id, 'unpaid_assessments_notice', p_as_of)::INT, 1);
    IF v_enabled = 0 THEN
        apartment_id := NULL; flat_number := NULL; total_unpaid := NULL; oldest_due := NULL;
        msg := 'OK: Unpaid assessments notice skipped (disabled by bye-law 54)';
        RETURN NEXT; RETURN;
    END IF;
    SELECT apartments.flat_number INTO v_flat
    FROM apartments WHERE id = p_apartment_id AND society_id = p_society_id;

    IF v_flat IS NULL THEN
        apartment_id := NULL; flat_number := NULL; total_unpaid := NULL; oldest_due := NULL;
        msg := 'Error: Apartment not found';
        RETURN NEXT; RETURN;
    END IF;

    SELECT COALESCE(SUM(r.amount - r.paid_principal), 0), MIN(r.due_date)
    INTO v_total, v_oldest
    FROM receivables r
    WHERE r.society_id = p_society_id
      AND r.entity_id = p_apartment_id
      AND r.role = 'apartment'
      AND r.charge_kind = 'common_expense'
      AND r.status IN ('pending', 'partial', 'unverified')
      AND r.due_date IS NOT NULL
      AND r.due_date <= p_as_of;

    apartment_id := p_apartment_id;
    flat_number := v_flat;
    total_unpaid := v_total;
    oldest_due := v_oldest;
    msg := 'OK: Unpaid assessments statement generated';
    RETURN NEXT; RETURN;
END $$;

-- 9. Seal Register (bye-law 56)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE seal_register (
    id              SERIAL PRIMARY KEY,
    society_id      INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    document_date   DATE NOT NULL,
    document_type   VARCHAR(50) NOT NULL,
    document_ref    VARCHAR(100),
    purpose         VARCHAR(300),
    authorized_by   VARCHAR(100) NOT NULL,
    used_by         INT REFERENCES users (id),
    created_by      INT REFERENCES users (id),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_seal_register_society ON seal_register (society_id, document_date);

CREATE OR REPLACE FUNCTION fn_seal_register_check(p_society_id INT, p_as_of DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (total_uses INT, msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_total INT;
    v_enabled INT;
BEGIN
    v_enabled := COALESCE(fn_regime_param_num(p_society_id, 'seal_register_maintained', p_as_of)::INT, 1);
    IF v_enabled = 0 THEN
        total_uses := 0;
        msg := 'OK: Seal register check skipped (disabled by bye-law 56)';
        RETURN NEXT; RETURN;
    END IF;
    SELECT COUNT(*) INTO v_total
    FROM seal_register
    WHERE society_id = p_society_id AND document_date <= p_as_of;

    total_uses := v_total;
    msg := 'OK: Seal register check completed';
    RETURN NEXT; RETURN;
END $$;

-- 10. Competent Authority Inspection (bye-law 57)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE ca_inspections (
    id                  SERIAL PRIMARY KEY,
    society_id          INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    inspection_date     DATE NOT NULL,
    ca_officer_name     VARCHAR(100),
    ca_designation      VARCHAR(100),
    findings            TEXT,
    action_required     BOOLEAN DEFAULT FALSE,
    action_taken        TEXT,
    created_by          INT REFERENCES users (id),
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ca_inspections_society ON ca_inspections (society_id, inspection_date);

CREATE OR REPLACE FUNCTION fn_ca_inspection_check(p_society_id INT, p_as_of DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (total_inspections INT, pending_actions INT, msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_total INT;
    v_pending INT;
    v_enabled INT;
BEGIN
    v_enabled := COALESCE(fn_regime_param_num(p_society_id, 'ca_inspection', p_as_of)::INT, 1);
    IF v_enabled = 0 THEN
        total_inspections := 0; pending_actions := 0;
        msg := 'OK: CA inspection check skipped (disabled by bye-law 57)';
        RETURN NEXT; RETURN;
    END IF;
    SELECT COUNT(*) INTO v_total
    FROM ca_inspections
    WHERE society_id = p_society_id AND inspection_date <= p_as_of;

    SELECT COUNT(*) INTO v_pending
    FROM ca_inspections
    WHERE society_id = p_society_id
      AND inspection_date <= p_as_of
      AND action_required = TRUE
      AND (action_taken IS NULL OR action_taken = '');

    total_inspections := v_total;
    pending_actions := v_pending;
    msg := 'OK: Competent Authority inspection check completed';
    RETURN NEXT; RETURN;
END $$;

-- 11. Bye-law Amendment Tracker (bye-law 58)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE bye_law_amendments (
    id                  SERIAL PRIMARY KEY,
    society_id          INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    amendment_date      DATE NOT NULL,
    bye_law_number      VARCHAR(20) NOT NULL,
    old_text            TEXT,
    new_text            TEXT,
    gbm_resolution_id   INT,
    ca_approval_ref     VARCHAR(100),
    ca_approval_date    DATE,
    effective_date      DATE,
    created_by          INT REFERENCES users (id),
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_bye_law_amendments_society ON bye_law_amendments (society_id, amendment_date);

CREATE OR REPLACE FUNCTION fn_bye_law_amendment_log(p_society_id INT, p_as_of DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (total_amendments INT, pending_ca_approval INT, msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_total INT;
    v_pending INT;
    v_enabled INT;
BEGIN
    v_enabled := COALESCE(fn_regime_param_num(p_society_id, 'bye_law_amendment_tracker', p_as_of)::INT, 1);
    IF v_enabled = 0 THEN
        total_amendments := 0; pending_ca_approval := 0;
        msg := 'OK: Bye-law amendment log check skipped (disabled by bye-law 58)';
        RETURN NEXT; RETURN;
    END IF;
    SELECT COUNT(*) INTO v_total
    FROM bye_law_amendments
    WHERE society_id = p_society_id AND amendment_date <= p_as_of;

    SELECT COUNT(*) INTO v_pending
    FROM bye_law_amendments
    WHERE society_id = p_society_id
      AND amendment_date <= p_as_of
      AND ca_approval_date IS NULL;

    total_amendments := v_total;
    pending_ca_approval := v_pending;
    msg := 'OK: Bye-law amendment log check completed';
    RETURN NEXT; RETURN;
END $$;

-- 11. Act prevails over bye-laws (bye-law 55)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_act_prevails_check(p_society_id INT, p_as_of DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (prevails BOOLEAN, msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_enabled INT;
BEGIN
    v_enabled := COALESCE(fn_regime_param_num(p_society_id, 'act_prevails_over_byelaws', p_as_of)::INT, 1);
    prevails := (v_enabled = 1);
    IF v_enabled = 1 THEN
        msg := 'OK: UP Apartment Act 2010 prevails over inconsistent bye-laws (Bye-law 55)';
    ELSE
        msg := 'Warning: Act prevails rule disabled';
    END IF;
    RETURN NEXT; RETURN;
END $$;

CREATE TABLE apartment_transfers (
    id                  SERIAL PRIMARY KEY,
    society_id          INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    apartment_id        INT NOT NULL REFERENCES apartments (id) ON DELETE CASCADE,
    transfer_date       DATE NOT NULL,
    transferor_name     VARCHAR(100),
    transferee_name     VARCHAR(100),
    -- The model bye-law's ½% is payable by the transferor on a SALE. Gift / succession carry no fee.
    transfer_type       VARCHAR(20) NOT NULL DEFAULT 'sale' CHECK (transfer_type IN ('sale', 'gift', 'succession')),
    transfer_value      NUMERIC(14, 2) NOT NULL CHECK (transfer_value >= 0),
    fee_pct             NUMERIC(6, 3) NOT NULL,
    fee_amount          NUMERIC(12, 2) NOT NULL,
    fee_receivable_id   INT REFERENCES receivables (id) ON DELETE SET NULL,
    nodues_requested_on DATE,
    nodues_refused_on   DATE,
    nodues_issued_on    DATE,
    -- Act s.23(2): the Board's statement of unpaid common-expense assessment, frozen when issued.
    statement_amount    NUMERIC(12, 2),
    statement_issued_on DATE,
    statement_issued_by INT REFERENCES users (id),
    created_by          INT REFERENCES users (id),
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_apartment_transfers_society ON apartment_transfers (society_id, apartment_id);

CREATE OR REPLACE FUNCTION fn_record_apartment_transfer(
    p_society_id INT, p_apartment_id INT, p_transfer_date DATE, p_transfer_value NUMERIC,
    p_transferor VARCHAR, p_transferee VARCHAR, p_created_by INT, p_transfer_type VARCHAR DEFAULT 'sale')
RETURNS TABLE (transfer_id INT, receivable_id INT, fee_amount NUMERIC, msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE v_pct NUMERIC; v_fee NUMERIC; v_acc INT; v_rec INT; v_tr INT; v_flat VARCHAR;
BEGIN
    p_transfer_type := COALESCE(NULLIF(trim(p_transfer_type), ''), 'sale');
    IF p_transfer_type NOT IN ('sale', 'gift', 'succession') THEN
        transfer_id := NULL; receivable_id := NULL; fee_amount := NULL;
        msg := 'Error: transfer type must be sale, gift or succession'; RETURN NEXT; RETURN;
    END IF;
    SELECT flat_number INTO v_flat FROM apartments WHERE id = p_apartment_id AND society_id = p_society_id;
    IF NOT FOUND THEN
        transfer_id := NULL; receivable_id := NULL; fee_amount := NULL;
        msg := 'Error: apartment not found in this society'; RETURN NEXT; RETURN;
    END IF;
    v_pct := fn_regime_param_num(p_society_id, 'transfer_fee_pct', p_transfer_date);
    IF v_pct IS NULL THEN
        transfer_id := NULL; receivable_id := NULL; fee_amount := NULL;
        msg := 'Error: no transfer-fee rule for this society''s legal regime'; RETURN NEXT; RETURN;
    END IF;

    IF p_transfer_type <> 'sale' THEN
        -- Gift / succession: record the change of ownership, levy nothing.
        INSERT INTO apartment_transfers (society_id, apartment_id, transfer_date, transferor_name, transferee_name,
                                         transfer_type, transfer_value, fee_pct, fee_amount, fee_receivable_id, created_by)
        VALUES (p_society_id, p_apartment_id, p_transfer_date, p_transferor, p_transferee,
                p_transfer_type, COALESCE(p_transfer_value, 0), 0, 0, NULL, p_created_by)
        RETURNING id INTO v_tr;
        -- Ownership moves on gift / succession too (Act s.18): the flat's
        -- owner-of-record becomes the transferee even though no fee is levied.
        UPDATE apartments SET owner_name = COALESCE(p_transferee, owner_name), updated_at = NOW()
        WHERE id = p_apartment_id AND society_id = p_society_id;
        transfer_id := v_tr; receivable_id := NULL; fee_amount := 0;
        msg := 'OK: no transfer fee on a ' || p_transfer_type; RETURN NEXT; RETURN;
    END IF;

    IF p_transfer_value IS NULL OR p_transfer_value <= 0 THEN
        transfer_id := NULL; receivable_id := NULL; fee_amount := NULL;
        msg := 'Error: transfer value must be positive'; RETURN NEXT; RETURN;
    END IF;

    v_acc := fn_ensure_major_repair_fund(p_society_id);
    v_fee := ROUND(p_transfer_value * v_pct / 100, 2);

    INSERT INTO receivables (society_id, entity_id, role, acc_id, description,
                             base_amount, interest_amount, amount, due_date, status, charge_kind)
    VALUES (p_society_id, p_apartment_id, 'apartment', v_acc,
            'Major Repair Fund - transfer fee ' || trim_scale(v_pct) || '% on transfer of ' || v_flat || ' (payable by transferor)',
            v_fee, 0, v_fee, p_transfer_date, 'pending', 'transfer_fee')
    RETURNING id INTO v_rec;

    -- Accrual leg (Dr Sundry Debtors / Cr fund), exactly as the bill generator does
    -- for every other receivable line; without it the later collection would credit
    -- Sundry Debtors with no matching debit and the fund would never show a balance.
    PERFORM fn_post_receivable_accrual(
        p_society_id, v_rec, p_apartment_id, 'apartment', v_acc, v_fee,
        'Major Repair Fund - transfer fee on transfer of ' || v_flat);

    INSERT INTO apartment_transfers (society_id, apartment_id, transfer_date, transferor_name, transferee_name,
                                     transfer_type, transfer_value, fee_pct, fee_amount, fee_receivable_id, created_by)
    VALUES (p_society_id, p_apartment_id, p_transfer_date, p_transferor, p_transferee,
            'sale', p_transfer_value, v_pct, v_fee, v_rec, p_created_by)
    RETURNING id INTO v_tr;

    -- Act s.18 / bye-law 39: the transfer of title moves the flat's ownership record to the
    -- transferee, and the seller's No Dues request is deemed filed on the transfer date so the
    -- statutory deemed-grant window (nodues_deemed_days) starts immediately. The certificate
    -- itself is still issued only through the Board action, gated by fn_nodues_issue_check.
    UPDATE apartments SET owner_name = COALESCE(p_transferee, owner_name), updated_at = NOW()
    WHERE id = p_apartment_id AND society_id = p_society_id;

    transfer_id := v_tr; receivable_id := v_rec; fee_amount := v_fee; msg := 'OK';
    RETURN NEXT;
END $$;

-- No Dues Certificate (bye-law 39): deemed granted when not refused within the window.
CREATE OR REPLACE FUNCTION fn_nodues_certificate_status(p_transfer_id INT, p_asof DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (status TEXT, deemed_on DATE)
LANGUAGE plpgsql STABLE AS $$
DECLARE t apartment_transfers%ROWTYPE; v_days INT;
BEGIN
    SELECT * INTO t FROM apartment_transfers WHERE id = p_transfer_id;
    IF NOT FOUND THEN status := 'not_found'; deemed_on := NULL; RETURN NEXT; RETURN; END IF;
    v_days := COALESCE(fn_regime_param_num(t.society_id, 'nodues_deemed_days', p_asof)::INT, 15);
    IF t.nodues_issued_on IS NOT NULL THEN status := 'issued'; deemed_on := NULL; RETURN NEXT; RETURN; END IF;
    IF t.nodues_requested_on IS NULL THEN status := 'not_requested'; deemed_on := NULL; RETURN NEXT; RETURN; END IF;
    deemed_on := t.nodues_requested_on + v_days;
    IF t.nodues_refused_on IS NOT NULL AND t.nodues_refused_on <= deemed_on THEN status := 'refused';
    ELSIF p_asof > deemed_on THEN status := 'deemed_granted';   -- a refusal on day 15 itself is still in time
    ELSE status := 'pending'; END IF;
    RETURN NEXT;
END $$;

-- ───────────────────────────────────────────────────────────────────────────────
-- Utility: first day of period (month) for a given date
-- ───────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION period_first_day(p_date DATE)
RETURNS DATE LANGUAGE sql STABLE AS $$
    SELECT date_trunc('month', p_date)::DATE;
$$;

-- ───────────────────────────────────────────────────────────────────────────────
-- 3. Bye-law 7: arrears > 60 days bar voting / standing for the Board
--    Tested AS AT the cutoff date from receivable_payment_log (see
--    fn_common_expense_arrears_asof), not the balance today.
-- ───────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_bye_law7_cutoff_date(p_society_id INT, p_election_date DATE, p_basis TEXT DEFAULT NULL)
RETURNS DATE LANGUAGE plpgsql STABLE AS $$
DECLARE v_basis TEXT; v_fy_start DATE;
BEGIN
    v_basis := COALESCE(p_basis, fn_regime_param_text(p_society_id, 'bye_law7_year_basis', p_election_date), 'financial_year');
    IF v_basis = 'calendar_year' THEN
        RETURN make_date(EXTRACT(YEAR FROM p_election_date)::INT, 1, 1) - 1;
    END IF;
    v_fy_start := CASE WHEN EXTRACT(MONTH FROM p_election_date) >= 4
                       THEN make_date(EXTRACT(YEAR FROM p_election_date)::INT, 4, 1)
                       ELSE make_date(EXTRACT(YEAR FROM p_election_date)::INT - 1, 4, 1) END;
    RETURN v_fy_start - 1;
END $$;

-- Common-expense arrears AS AT p_asof: every common-expense receivable due more than p_margin_days
-- before p_asof, less the principal paid ON OR BEFORE p_asof (receivable_payment_log). Interest is
-- left out (bye-law 7 speaks of "contributions for common expenses"). A receivable with no log
-- rows but some principal paid predates the log: it is treated as paid in time rather than
-- guessing a date and disqualifying an owner on that guess.
CREATE OR REPLACE FUNCTION fn_common_expense_arrears_asof(
    p_society_id INT, p_apartment_id INT, p_asof DATE, p_margin_days INT DEFAULT 60)
RETURNS TABLE (arrears NUMERIC, oldest_due_date DATE, max_days_overdue INT)
LANGUAGE sql STABLE AS $$
    WITH x AS (
        SELECT r.due_date,
               GREATEST((r.amount - r.interest_amount) - CASE
                   WHEN EXISTS (SELECT 1 FROM receivable_payment_log g WHERE g.receivable_id = r.id)
                   THEN COALESCE((SELECT SUM(g.principal_delta) FROM receivable_payment_log g
                                  WHERE g.receivable_id = r.id AND g.paid_on <= p_asof), 0)
                   ELSE LEAST(r.paid_principal, r.amount - r.interest_amount) END, 0) AS owed
          FROM receivables r
         WHERE r.society_id = p_society_id AND r.entity_id = p_apartment_id AND r.role = 'apartment'
           AND r.charge_kind = 'common_expense'
           AND r.status IN ('pending', 'partial', 'unverified', 'paid')
           AND r.due_date IS NOT NULL AND r.due_date < p_asof - p_margin_days
    )
    SELECT COALESCE(SUM(owed), 0)::NUMERIC,
           MIN(due_date) FILTER (WHERE owed > 0),
           COALESCE(MAX(p_asof - due_date) FILTER (WHERE owed > 0), 0)::INT
      FROM x
$$;

-- Bye-law 7: arrears of MORE than 60 days ON THE LAST DAY of the year before the election bar a
-- person from voting or standing. Tested as at that date (not today) on common-expense contributions
-- only. An overdue owner-loan balance counts only if the society opts in (owner_loan_counts_bye_law7,
-- default 0); loans carry no payment dates, so that part still uses today's balance.
CREATE OR REPLACE FUNCTION fn_bye_law7_eligibility(p_society_id INT, p_election_date DATE, p_basis TEXT DEFAULT NULL)
RETURNS TABLE (apartment_id INT, flat_number VARCHAR, owner_name VARCHAR, cutoff_date DATE,
               overdue_amount NUMERIC, oldest_due_date DATE, days_overdue INT, eligible BOOLEAN)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_days INT; v_cut DATE; v_loans INT;
BEGIN
    v_days := fn_regime_param_num(p_society_id, 'arrears_disqualify_days', p_election_date)::INT;
    IF v_days IS NULL THEN RETURN; END IF;           -- rule not active for this society
    v_cut   := fn_bye_law7_cutoff_date(p_society_id, p_election_date, p_basis);
    v_loans := COALESCE(fn_regime_param_num(p_society_id, 'owner_loan_counts_bye_law7', p_election_date)::INT, 0);

    RETURN QUERY
    SELECT a.id, a.flat_number, a.owner_name, v_cut,
           (COALESCE(ar.arrears, 0) + COALESCE(lo.amt, 0))::NUMERIC,
           LEAST(ar.oldest_due_date, lo.oldest),
           GREATEST(COALESCE(ar.max_days_overdue, 0), COALESCE(lo.max_days, 0))::INT,
           (COALESCE(ar.arrears, 0) = 0 AND COALESCE(lo.amt, 0) = 0)
    FROM apartments a
    LEFT JOIN LATERAL fn_common_expense_arrears_asof(p_society_id, a.id, v_cut, v_days) ar ON TRUE
    LEFT JOIN LATERAL (
        SELECT SUM(l.principal - l.repaid_amount) AS amt, MIN(l.due_date) AS oldest, MAX(v_cut - l.due_date) AS max_days
          FROM owner_loans l
         WHERE v_loans = 1 AND l.society_id = p_society_id AND l.apartment_id = a.id
           AND l.principal > l.repaid_amount AND l.due_date IS NOT NULL AND l.due_date < v_cut - v_days
    ) lo ON TRUE
    WHERE a.society_id = p_society_id AND a.active
    ORDER BY a.flat_number;
END $$;

-- ───────────────────────────────────────────────────────────────────────────────
-- 4. Section 22 — procedure before cutting an essential service
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE service_cutoff_proceedings (
    id                         SERIAL PRIMARY KEY,
    society_id                 INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    apartment_id               INT NOT NULL REFERENCES apartments (id) ON DELETE CASCADE,
    service_type               VARCHAR(40) NOT NULL,
    arrears_amount             NUMERIC(12, 2),
    default_since              DATE NOT NULL,
    notice_served_on           DATE,
    gb_resolution_on           DATE,
    copy_sent_to_authority_on  DATE,
    copy_sent_to_owner_on      DATE,
    copy_received_by_owner_on  DATE,   -- the 15-day appeal runs from RECEIPT (s.22(2)); falls back to dispatch if blank
    display_notice_on          DATE,
    appeal_filed_on            DATE,
    appeal_outcome             VARCHAR(20) CHECK (appeal_outcome IN ('pending', 'dismissed', 'allowed')),
    cut_off_on                 DATE,
    status                     VARCHAR(20) NOT NULL DEFAULT 'in_progress'
                               CHECK (status IN ('in_progress', 'cut_off', 'withdrawn', 'restored')),
    notes                      TEXT,
    created_by                 INT REFERENCES users (id),
    created_at                 TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_service_cutoff_society ON service_cutoff_proceedings (society_id, apartment_id);

-- Does NOT cut anything: returns whether the s.22 preconditions are satisfied as of
-- p_asof, what blocks it, and the earliest date it could lawfully happen.
-- Now uses fn_get_standing for unified s22_blocked check (Phase 2).
CREATE OR REPLACE FUNCTION fn_service_cutoff_check(p_proceeding_id INT, p_asof DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (can_cut_off BOOLEAN, earliest_cutoff_date DATE, blockers TEXT[])
LANGUAGE plpgsql STABLE AS $$
DECLARE
    p service_cutoff_proceedings%ROWTYPE;
    v_months INT; v_notice INT; v_wait INT; v_appeal INT;
    b TEXT[] := ARRAY[]::TEXT[]; e DATE[] := ARRAY[]::DATE[];
    v_copy DATE; d DATE; v_since DATE; v_oldest DATE; v_recv DATE;
    v_standing RECORD;
BEGIN
    SELECT * INTO p FROM service_cutoff_proceedings WHERE id = p_proceeding_id;
    IF NOT FOUND THEN can_cut_off := FALSE; earliest_cutoff_date := NULL; blockers := ARRAY['proceeding not found']; RETURN NEXT; RETURN; END IF;
    v_months := fn_regime_param_num(p.society_id, 's22_default_months', p_asof)::INT;
    IF v_months IS NULL THEN
        can_cut_off := FALSE; earliest_cutoff_date := NULL;
        blockers := ARRAY['s.22 rules are not configured for this society''s legal regime']; RETURN NEXT; RETURN;
    END IF;
    v_notice := fn_regime_param_num(p.society_id, 's22_notice_days', p_asof)::INT;
    v_wait   := fn_regime_param_num(p.society_id, 's22_wait_months', p_asof)::INT;
    v_appeal := fn_regime_param_num(p.society_id, 's22_appeal_days', p_asof)::INT;

    -- The default clock starts at the oldest UNPAID common-expense bill on the books. A typed
    -- default_since can only push it later (conservative), never earlier than the records show.
    SELECT MIN(r.due_date) INTO v_oldest FROM receivables r
     WHERE r.society_id = p.society_id AND r.entity_id = p.apartment_id AND r.role = 'apartment'
       AND r.charge_kind = 'common_expense' AND r.status IN ('pending', 'partial', 'unverified')
       AND r.due_date IS NOT NULL AND r.due_date <= p_asof;
    v_since := GREATEST(p.default_since, COALESCE(v_oldest, p.default_since));
    d := (v_since + make_interval(months => v_months))::DATE + 1;     -- "more than" 6 months
    e := e || d;
    IF p_asof < d THEN b := b || format('default must exceed %s months (earliest %s)', v_months, d); END IF;

    IF p.notice_served_on IS NULL THEN b := array_append(b, 'no notice served on the defaulter');
    ELSE d := p.notice_served_on + v_notice; e := e || d;
         IF p_asof < d THEN b := b || format('%s-day notice period runs until %s', v_notice, d); END IF; END IF;

    IF p.gb_resolution_on IS NULL THEN b := array_append(b, 'no general-body resolution recorded');
    ELSIF p.notice_served_on IS NOT NULL AND p.gb_resolution_on < p.notice_served_on + v_notice THEN
        -- s.22(1): the resolution is passed AFTER notice of not less than 7 days
        b := b || format('resolution dated %s precedes the end of the %s-day notice (%s); it must be passed after the notice period',
                         p.gb_resolution_on, v_notice, p.notice_served_on + v_notice);
    END IF;

    IF p.copy_sent_to_authority_on IS NULL THEN b := array_append(b, 'certified copy not sent to the competent authority (registered/speed post)');
    ELSIF p.gb_resolution_on IS NOT NULL AND p.copy_sent_to_authority_on < p.gb_resolution_on THEN
        b := b || format('copy to the competent authority is dated %s, before the resolution (%s)', p.copy_sent_to_authority_on, p.gb_resolution_on);
    END IF;
    IF p.copy_sent_to_owner_on IS NULL THEN b := array_append(b, 'certified copy not sent to the owner (registered/speed post)');
    ELSIF p.gb_resolution_on IS NOT NULL AND p.copy_sent_to_owner_on < p.gb_resolution_on THEN
        b := b || format('copy to the owner is dated %s, before the resolution (%s)', p.copy_sent_to_owner_on, p.gb_resolution_on);
    END IF;
    IF p.copy_sent_to_authority_on IS NOT NULL AND p.copy_sent_to_owner_on IS NOT NULL THEN
        v_copy := GREATEST(p.copy_sent_to_authority_on, p.copy_sent_to_owner_on);
        d := (v_copy + make_interval(months => v_wait))::DATE; e := e || d;
        IF p_asof < d THEN b := b || format('one-month wait after dispatch runs until %s', d); END IF;
    END IF;

    IF p.display_notice_on IS NULL THEN b := array_append(b, 'notice not displayed');
    ELSIF p.gb_resolution_on IS NOT NULL AND p.display_notice_on < p.gb_resolution_on THEN
        b := b || format('display is dated %s, before the resolution (%s)', p.display_notice_on, p.gb_resolution_on);
    END IF;

    v_recv := COALESCE(p.copy_received_by_owner_on, p.copy_sent_to_owner_on);
    IF v_recv IS NOT NULL THEN
        d := v_recv + v_appeal; e := e || d;
        IF p_asof < d THEN b := b || format('%s-day appeal window open until %s', v_appeal, d); END IF;
    END IF;
    IF p.appeal_filed_on IS NOT NULL AND COALESCE(p.appeal_outcome, 'pending') <> 'dismissed' THEN
        b := array_append(b, 'appeal filed and not dismissed');
    END IF;

    -- s22_blocked = TRUE means NO common-expense dues are unpaid for more than the default period
    SELECT * INTO v_standing FROM fn_get_standing(p.society_id, p.apartment_id, p_asof);
    IF v_standing.s22_blocked THEN
        b := array_append(b, format('no common-expense dues are unpaid for more than %s months on this flat, so s.22 is not triggered', v_months));
    END IF;

    can_cut_off := COALESCE(array_length(b, 1), 0) = 0;
    earliest_cutoff_date := (SELECT MAX(x) FROM unnest(e) x);
    blockers := b;
    RETURN NEXT;
END $$;

-- ───────────────────────────────────────────────────────────────────────────────
-- 5. Cash / cheque limits (bye-laws 46-52)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE compliance_flags (
    id           SERIAL PRIMARY KEY,
    society_id   INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    rule_code    VARCHAR(40) NOT NULL,
    source_table VARCHAR(40) NOT NULL,
    source_id    INT NOT NULL,
    detail       TEXT,
    flagged_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_compliance_flag UNIQUE (source_table, source_id, rule_code)
);
CREATE INDEX idx_compliance_flags_society ON compliance_flags (society_id, rule_code);

CREATE OR REPLACE FUNCTION fn_cash_limit_mode(p_society_id INT)
RETURNS TEXT LANGUAGE sql STABLE AS $$
    SELECT COALESCE((SELECT cash_limit_mode FROM societies WHERE id = p_society_id),
                    fn_regime_param_text(p_society_id, 'cash_limit_default_mode'), 'warn')
$$;

CREATE OR REPLACE FUNCTION fn_check_cash_payment_limit(p_society_id INT, p_amount NUMERIC, p_mode VARCHAR)
RETURNS TEXT LANGUAGE plpgsql STABLE AS $$
DECLARE v_lim NUMERIC;
BEGIN
    IF p_mode IS DISTINCT FROM 'cash' THEN RETURN NULL; END IF;
    v_lim := fn_regime_param_num(p_society_id, 'cash_payment_cheque_threshold');
    IF v_lim IS NULL OR p_amount <= v_lim THEN RETURN NULL; END IF;
    RETURN format('cash payment of %s exceeds the %s limit above which the Model Bye-Laws require a cheque / bank transfer', p_amount, v_lim);
END $$;

CREATE OR REPLACE FUNCTION fn_petty_cash_check(p_society_id INT, p_asof DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (cash_in_hand NUMERIC, limit_amount NUMERIC, breach BOOLEAN)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    limit_amount := fn_regime_param_num(p_society_id, 'petty_cash_limit', p_asof);
    IF limit_amount IS NULL THEN RETURN; END IF;
    cash_in_hand := fn_cih_balance_asof(p_society_id, p_asof);
    breach := cash_in_hand > limit_amount;
    RETURN NEXT;
END $$;

-- ───────────────────────────────────────────────────────────────────────────────
-- 6. Bye-law 49 filing calendar (statements by 31 Jul, authority copy by 15 Aug,
--    owner summaries within 15 days of publication). Indian FY (April-March).
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE aoa_statutory_filings (
    id                       SERIAL PRIMARY KEY,
    society_id               INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    fy_start_year            INT NOT NULL,
    statements_published_on  DATE,
    copy_to_authority_on     DATE,
    owner_summaries_sent_on  DATE,
    auditor_name             VARCHAR(150),
    -- Bye-law 49(3) publishes an AUDITED statement; bye-law 51 has the general meeting appoint the auditor.
    -- A statement cannot be recorded as published unless an auditor is named and signed it off on or before
    -- the publication date.
    audit_signed_off_on      DATE,
    owner_list_attached      BOOLEAN NOT NULL DEFAULT FALSE,
    loanee_list_attached     BOOLEAN NOT NULL DEFAULT FALSE,
    notes                    TEXT,
    updated_by               INT REFERENCES users (id),
    updated_at               TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_aoa_filing UNIQUE (society_id, fy_start_year),
    CONSTRAINT chk_aoa_published_is_audited CHECK (
        statements_published_on IS NULL
        OR (COALESCE(btrim(auditor_name), '') <> '' AND audit_signed_off_on IS NOT NULL
            AND audit_signed_off_on <= statements_published_on))
);

CREATE OR REPLACE FUNCTION fn_statutory_calendar(p_society_id INT, p_asof DATE DEFAULT CURRENT_DATE, p_years INT DEFAULT 3)
RETURNS TABLE (fy_label TEXT, step TEXT, due_date DATE, done_on DATE, status TEXT, days_to_due INT)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_last INT; y INT; f aoa_statutory_filings%ROWTYPE;
    pm INT; pd INT; am INT; ad INT; sd INT; v_pub DATE; v_auth DATE; v_sum DATE;
BEGIN
    pm := fn_regime_param_num(p_society_id, 'statement_publish_due_month', p_asof)::INT;
    IF pm IS NULL THEN RETURN; END IF;
    pd := fn_regime_param_num(p_society_id, 'statement_publish_due_day', p_asof)::INT;
    am := fn_regime_param_num(p_society_id, 'authority_copy_due_month', p_asof)::INT;
    ad := fn_regime_param_num(p_society_id, 'authority_copy_due_day', p_asof)::INT;
    sd := fn_regime_param_num(p_society_id, 'owner_summary_days', p_asof)::INT;
    v_last := CASE WHEN EXTRACT(MONTH FROM p_asof) >= 4 THEN EXTRACT(YEAR FROM p_asof)::INT - 1
                   ELSE EXTRACT(YEAR FROM p_asof)::INT - 2 END;          -- last FY that has ended
    FOR y IN REVERSE v_last .. (v_last - GREATEST(p_years, 1) + 1) LOOP
        SELECT * INTO f FROM aoa_statutory_filings WHERE society_id = p_society_id AND fy_start_year = y;
        fy_label := y || '-' || RIGHT((y + 1)::TEXT, 2);

        step := 'Audited statement published'; due_date := make_date(y + 1, pm, pd); done_on := f.statements_published_on;
        status := CASE WHEN done_on IS NOT NULL THEN 'done' WHEN p_asof > due_date THEN 'overdue'
                       WHEN due_date - p_asof <= 30 THEN 'due_soon' ELSE 'upcoming' END;
        days_to_due := due_date - p_asof; RETURN NEXT;

        step := 'Copy to competent authority'; due_date := make_date(y + 1, am, ad); done_on := f.copy_to_authority_on;
        status := CASE WHEN done_on IS NOT NULL THEN 'done' WHEN p_asof > due_date THEN 'overdue'
                       WHEN due_date - p_asof <= 30 THEN 'due_soon' ELSE 'upcoming' END;
        days_to_due := due_date - p_asof; RETURN NEXT;

        step := 'Summary sent to owners';
        due_date := COALESCE(f.statements_published_on, make_date(y + 1, pm, pd)) + sd; done_on := f.owner_summaries_sent_on;
        status := CASE WHEN done_on IS NOT NULL THEN 'done' WHEN p_asof > due_date THEN 'overdue'
                       WHEN due_date - p_asof <= 30 THEN 'due_soon' ELSE 'upcoming' END;
        days_to_due := due_date - p_asof; RETURN NEXT;
    END LOOP;
END $$;

-- ───────────────────────────────────────────────────────────────────────────────
-- 7. Owner list and loanee list (annexures to the bye-law 49 statement)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE owner_loans (
    id                SERIAL PRIMARY KEY,
    society_id        INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    apartment_id      INT NOT NULL REFERENCES apartments (id) ON DELETE CASCADE,
    loan_date         DATE NOT NULL,
    principal         NUMERIC(12, 2) NOT NULL CHECK (principal > 0),
    interest_rate_pct NUMERIC(5, 2) NOT NULL DEFAULT 0,
    purpose           TEXT,
    resolution_ref    VARCHAR(100),
    -- Bye-law 3(1)(f): a loan needs "the consent of the apartment owners". resolution_id points at the passed
    -- Approve Owner Loan resolution that records it (FK added after the resolutions table, below);
    -- resolution_ref stays as free text for loans entered before this link existed.
    resolution_id     INT,
    repaid_amount     NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (repaid_amount >= 0),
    -- Bye-law 3(1)(f) lets the association lend to an owner. The register row
    -- alone is not a money movement: ledger_posted records whether the
    -- disbursal has actually been journalled (journal_id points at that
    -- journal), so a registered loan can never be mistaken for a posted one.
    ledger_posted     BOOLEAN NOT NULL DEFAULT FALSE,
    disbursal_mode    VARCHAR(20),
    journal_id        INT,
    -- A due date is optional — an interest-free, open-ended loan has none.
    -- When present it cannot predate the loan itself.
    due_date          DATE,
    created_by        INT REFERENCES users (id),
    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT owner_loans_due_after_loan CHECK (due_date IS NULL OR due_date >= loan_date)
);   -- register only: this table does not post to the ledger

CREATE OR REPLACE FUNCTION fn_aoa_owner_list(p_society_id INT)
RETURNS TABLE (sr_no BIGINT, flat_number VARCHAR, owner_name VARCHAR, mobile VARCHAR,
               apartment_size INT, undivided_interest_pct NUMERIC, outstanding_dues NUMERIC)
LANGUAGE sql STABLE AS $$
    SELECT ROW_NUMBER() OVER (ORDER BY a.flat_number), a.flat_number, a.owner_name, a.mobile,
           a.apartment_size, a.undivided_interest_pct,
           COALESCE((SELECT SUM(r.amount - r.paid_amount) FROM receivables r
                      WHERE r.society_id = a.society_id AND r.entity_id = a.id
                        AND r.role = 'apartment' AND r.status = 'pending'), 0)
    FROM apartments a WHERE a.society_id = p_society_id AND a.active
    ORDER BY a.flat_number
$$;

CREATE OR REPLACE FUNCTION fn_aoa_loanee_list(p_society_id INT)
RETURNS TABLE (sr_no BIGINT, flat_number VARCHAR, owner_name VARCHAR, loan_date DATE, principal NUMERIC,
               interest_rate_pct NUMERIC, repaid_amount NUMERIC, outstanding NUMERIC, resolution_ref VARCHAR)
LANGUAGE sql STABLE AS $$
    SELECT ROW_NUMBER() OVER (ORDER BY a.flat_number, l.loan_date), a.flat_number, a.owner_name, l.loan_date,
           l.principal, l.interest_rate_pct, l.repaid_amount, l.principal - l.repaid_amount, l.resolution_ref
    FROM owner_loans l JOIN apartments a ON a.id = l.apartment_id
    WHERE l.society_id = p_society_id AND l.principal > l.repaid_amount
    ORDER BY a.flat_number, l.loan_date
$$;

-- ═══════════════════════════════════════════════════════════════════════════════
-- UP AOA COMPLIANCE LAYER, PART 2
--   (a) billing by undivided-interest %   (b) owner loans posted to the ledger
-- ═══════════════════════════════════════════════════════════════════════════════

-- ── (a) Billing basis ─────────────────────────────────────────────────────────
-- 'per_sqft'            : apt_maintenance_rate x apartment_size (unchanged default)
-- 'undivided_interest'  : common_expense_budget_monthly x apartments.undivided_interest_pct / 100
-- apt_maintenance_amount stays a hard per-apartment override only in 'per_sqft' mode.
-- Sinking / repair fund levies stay per-sq-ft in both modes.
-- What each flat would pay for a given monthly common-expense budget, next to the
-- per-sq-ft rate that would produce the same total.
CREATE OR REPLACE FUNCTION fn_undivided_interest_bill_preview(p_society_id INT, p_monthly_budget NUMERIC)
RETURNS TABLE (apartment_id INT, flat_number VARCHAR, apartment_size INT, undivided_interest_pct NUMERIC,
               monthly_share NUMERIC, equivalent_rate_per_sqft NUMERIC)
LANGUAGE sql STABLE AS $$
    WITH t AS (SELECT NULLIF(SUM(apartment_size), 0) AS tot FROM apartments WHERE society_id = p_society_id AND active)
    SELECT a.id, a.flat_number, a.apartment_size, a.undivided_interest_pct,
           ROUND(p_monthly_budget * a.undivided_interest_pct / 100, 2),
           ROUND(p_monthly_budget * a.undivided_interest_pct / 100 / NULLIF(a.apartment_size, 0), 4)
    FROM apartments a CROSS JOIN t
    WHERE a.society_id = p_society_id AND a.active AND a.undivided_interest_pct IS NOT NULL
    ORDER BY a.flat_number
$$;

-- ── (b) Owner loans: ledger posting (bye-law 3(1)(f) lets the association lend to owners) ──
-- owner_loans.ledger_posted / disbursal_mode / journal_id are declared inline
-- on the owner_loans CREATE TABLE earlier in this file.
CREATE TABLE owner_loan_repayments (
    id               SERIAL PRIMARY KEY,
    loan_id          INT NOT NULL REFERENCES owner_loans (id) ON DELETE CASCADE,
    society_id       INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    repay_date       DATE NOT NULL,
    principal_amount NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (principal_amount >= 0),
    interest_amount  NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (interest_amount >= 0),
    mode             VARCHAR(20) NOT NULL,
    journal_id       INT,
    created_by       INT REFERENCES users (id),
    created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    CHECK (principal_amount + interest_amount > 0)
);

CREATE OR REPLACE FUNCTION fn_ensure_owner_loan_accounts(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO accounts (id, society_id, name, tab_name, header, parent_account_id,
                          drcr_account, has_bf, depreciation_percent, is_depreciable)
    SELECT 1410, p_society_id, 'Loans to Owners', 'LnOwn', 'Loans & Advances Given', 1400,
           'Dr', TRUE, 100, FALSE
    WHERE EXISTS (SELECT 1 FROM accounts WHERE society_id = p_society_id AND id = 1400)
      AND NOT EXISTS (SELECT 1 FROM accounts WHERE society_id = p_society_id AND id = 1410);

    INSERT INTO accounts (id, society_id, name, tab_name, header, parent_account_id,
                          drcr_account, has_bf, depreciation_percent, is_depreciable, mutuality_nature)
    SELECT 4116, p_society_id, 'Interest on Owner Loans', 'IntOwnLn', 'Interest on Owner Loans', 4110,
           'Cr', FALSE, 100, FALSE, 'mutual'
    WHERE EXISTS (SELECT 1 FROM accounts WHERE society_id = p_society_id AND id = 4110)
      AND NOT EXISTS (SELECT 1 FROM accounts WHERE society_id = p_society_id AND id = 4116);

    INSERT INTO account_statutory_mappings (society_id, account_id, regime_code, head_code, effective_from, source_reference)
    SELECT p_society_id, 1410, slr.regime_code, 'LOANS_GIVEN', DATE '2011-11-16', 'Model Bye-Laws 2011, bye-law 3(1)(f)'
    FROM society_legal_regime slr
    WHERE slr.society_id = p_society_id AND slr.regime_code = 'UP_AOA_2010'
      AND EXISTS (SELECT 1 FROM accounts WHERE society_id = p_society_id AND id = 1410)
    ON CONFLICT DO NOTHING;
END $$;

-- Is this resolution valid consent for an owner loan (bye-law 3(1)(f))? Returns NULL when it is, otherwise
-- the reason it is not. Engine policy on what counts as "the consent of the apartment owners": a PASSED
-- Approve Owner Loan resolution, of this society, taken at a General Body / Extraordinary meeting that
-- recorded a quorum, on or before the loan date.
CREATE OR REPLACE FUNCTION fn_check_loan_resolution(p_society_id INT, p_resolution_id INT, p_loan_date DATE)
RETURNS TEXT LANGUAGE plpgsql STABLE AS $$
DECLARE x RECORD;
BEGIN
    SELECT r.id, r.passed, r.passed_on, dt.code AS dcode, m.society_id, m.type AS mtype, m.quorum_met, m.held_on
      INTO x
      FROM resolutions r
      JOIN meetings m ON m.id = r.meeting_id
      JOIN decision_types dt ON dt.id = r.decision_type_id
     WHERE r.id = p_resolution_id;
    IF NOT FOUND OR x.society_id IS DISTINCT FROM p_society_id THEN RETURN 'that resolution is not one of this society''s'; END IF;
    IF x.dcode <> 'APPROVE_LOAN' THEN RETURN 'that resolution is not an Approve Owner Loan resolution'; END IF;
    IF NOT x.passed THEN RETURN 'that resolution did not pass'; END IF;
    IF x.mtype NOT IN ('GBM', 'EGM') THEN RETURN 'owner loans need the consent of the owners: the resolution must be taken at a General Body meeting, not a Board meeting'; END IF;
    IF NOT x.quorum_met THEN RETURN 'the meeting that passed that resolution did not record a quorum'; END IF;
    IF COALESCE(x.passed_on, x.held_on) > p_loan_date THEN RETURN 'that resolution was passed after the loan date'; END IF;
    RETURN NULL;
END $$;

-- Disbursement: Dr Loans to Owners / Cr cash or bank. The cash-payment limit applies. What counts as consent
-- depends on owner_loan_resolution_mode: 'linked' (UP default) needs a valid, passed Approve Owner Loan
-- resolution (p_resolution_id), a stated purpose (emergent necessity) and a repayment date within
-- owner_loan_max_term_days (short-term); 'text' keeps the old rule of any non-blank resolution reference.
CREATE OR REPLACE FUNCTION fn_disburse_owner_loan(
    p_society_id INT, p_apartment_id INT, p_loan_date DATE, p_principal NUMERIC, p_rate_pct NUMERIC,
    p_mode VARCHAR, p_purpose TEXT, p_resolution_ref VARCHAR, p_created_by INT,
    p_resolution_id INT DEFAULT NULL, p_due_date DATE DEFAULT NULL)
RETURNS TABLE (loan_id INT, msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE v_flat VARCHAR; v_loan INT; v_bank INT; v_journal INT; v_limit TEXT;
        v_mode TEXT; v_why TEXT; v_ref VARCHAR; v_max NUMERIC;
BEGIN
    SELECT flat_number INTO v_flat FROM apartments WHERE id = p_apartment_id AND society_id = p_society_id AND active;
    IF NOT FOUND THEN loan_id := NULL; msg := 'Error: apartment not found in this society'; RETURN NEXT; RETURN; END IF;
    IF p_principal IS NULL OR p_principal <= 0 THEN loan_id := NULL; msg := 'Error: principal must be positive'; RETURN NEXT; RETURN; END IF;
    IF COALESCE(p_rate_pct, 0) < 0 THEN loan_id := NULL; msg := 'Error: interest rate cannot be negative'; RETURN NEXT; RETURN; END IF;
    IF p_mode IS NULL OR p_mode = 'journal' THEN loan_id := NULL; msg := 'Error: choose how the money was paid out'; RETURN NEXT; RETURN; END IF;

    v_mode := COALESCE(fn_regime_param_text(p_society_id, 'owner_loan_resolution_mode', p_loan_date), 'text');
    v_ref := NULLIF(TRIM(COALESCE(p_resolution_ref, '')), '');
    IF v_mode = 'linked' THEN
        IF p_resolution_id IS NULL THEN
            loan_id := NULL; msg := 'Error: choose the General Body resolution that approved this loan (bye-law 3(1)(f): consent of the owners)'; RETURN NEXT; RETURN; END IF;
        v_why := fn_check_loan_resolution(p_society_id, p_resolution_id, p_loan_date);
        IF v_why IS NOT NULL THEN loan_id := NULL; msg := 'Error: ' || v_why; RETURN NEXT; RETURN; END IF;
        IF COALESCE(TRIM(p_purpose), '') = '' THEN
            loan_id := NULL; msg := 'Error: state the emergent necessity the loan is for (bye-law 3(1)(f))'; RETURN NEXT; RETURN; END IF;
        IF p_due_date IS NULL OR p_due_date <= p_loan_date THEN
            loan_id := NULL; msg := 'Error: a short-term loan needs a repayment date after the loan date'; RETURN NEXT; RETURN; END IF;
        v_max := fn_regime_param_num(p_society_id, 'owner_loan_max_term_days', p_loan_date);
        IF v_max IS NOT NULL AND p_due_date - p_loan_date > v_max THEN
            loan_id := NULL; msg := format('Error: repayment date is %s days out; the society''s short-term limit is %s days', p_due_date - p_loan_date, v_max::INT); RETURN NEXT; RETURN; END IF;
        IF v_ref IS NULL THEN
            SELECT format('GBM %s / resolution #%s', m.held_on, r.id) INTO v_ref
              FROM resolutions r JOIN meetings m ON m.id = r.meeting_id WHERE r.id = p_resolution_id;
        END IF;
    ELSE
        IF v_ref IS NULL THEN
            loan_id := NULL; msg := 'Error: a Board / general-body resolution reference is required'; RETURN NEXT; RETURN; END IF;
    END IF;

    v_limit := fn_check_cash_payment_limit(p_society_id, p_principal, p_mode);
    IF v_limit IS NOT NULL AND fn_cash_limit_mode(p_society_id) = 'block' THEN
        loan_id := NULL; msg := 'Error: ' || v_limit; RETURN NEXT; RETURN; END IF;

    PERFORM fn_ensure_owner_loan_accounts(p_society_id);
    IF NOT EXISTS (SELECT 1 FROM accounts WHERE society_id = p_society_id AND id = 1410) THEN
        loan_id := NULL; msg := 'Error: this society has no Loans & Advances Given account'; RETURN NEXT; RETURN; END IF;

    v_bank := fn_resolve_bank_leg(p_society_id, p_mode);
    v_journal := NEXTVAL('seq_transaction_number');

    INSERT INTO owner_loans (society_id, apartment_id, loan_date, principal, interest_rate_pct, purpose,
                             resolution_ref, resolution_id, due_date, created_by, ledger_posted, disbursal_mode, journal_id)
    VALUES (p_society_id, p_apartment_id, p_loan_date, p_principal, COALESCE(p_rate_pct, 0), p_purpose,
            v_ref, CASE WHEN v_mode = 'linked' THEN p_resolution_id END,
            CASE WHEN v_mode = 'linked' THEN p_due_date END, p_created_by, TRUE, p_mode, v_journal)
    RETURNING id INTO v_loan;

    INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                              amount, mode, status, created_by, created_at, source_table, source_id, journal_id)
    VALUES (p_society_id, 'Dr', p_loan_date, 1410, p_apartment_id, 'apartment',
            'Loan to owner of ' || v_flat || ' (' || v_ref || ')',
            p_principal, p_mode, 'paid', p_created_by, NOW(), 'owner_loans', v_loan, v_journal);
    IF v_bank IS NOT NULL THEN
        INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                                  amount, mode, status, created_by, created_at, source_table, source_id, journal_id)
        VALUES (p_society_id, 'Cr', p_loan_date, v_bank, p_apartment_id, 'apartment',
                'Loan paid out - ' || v_flat, p_principal, p_mode, 'paid', p_created_by, NOW(),
                'owner_loans', v_loan, v_journal);
    END IF;

    IF v_limit IS NOT NULL THEN
        INSERT INTO compliance_flags (society_id, rule_code, source_table, source_id, detail)
        VALUES (p_society_id, 'CASH_PAYMENT_LIMIT', 'owner_loans', v_loan, v_limit)
        ON CONFLICT (source_table, source_id, rule_code) DO NOTHING;
    END IF;
    loan_id := v_loan; msg := 'OK'; RETURN NEXT;
END $$;

-- Repayment: Dr cash/bank, Cr Loans to Owners (principal), Cr Interest on Owner Loans (interest).
CREATE OR REPLACE FUNCTION fn_repay_owner_loan(
    p_loan_id INT, p_repay_date DATE, p_principal NUMERIC, p_interest NUMERIC, p_mode VARCHAR, p_created_by INT)
RETURNS TABLE (repayment_id INT, msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE l owner_loans%ROWTYPE; v_p NUMERIC; v_i NUMERIC; v_bank INT; v_journal INT; v_rep INT; v_flat VARCHAR;
BEGIN
    SELECT * INTO l FROM owner_loans WHERE id = p_loan_id FOR UPDATE;
    IF NOT FOUND THEN repayment_id := NULL; msg := 'Error: loan not found'; RETURN NEXT; RETURN; END IF;
    IF NOT l.ledger_posted THEN
        repayment_id := NULL; msg := 'Error: this loan is a register-only entry (never posted to the ledger); repay it by editing the register';
        RETURN NEXT; RETURN; END IF;
    v_p := COALESCE(p_principal, 0); v_i := COALESCE(p_interest, 0);
    IF v_p < 0 OR v_i < 0 OR v_p + v_i <= 0 THEN repayment_id := NULL; msg := 'Error: enter a positive principal and/or interest amount'; RETURN NEXT; RETURN; END IF;
    IF v_p > l.principal - l.repaid_amount THEN
        repayment_id := NULL; msg := 'Error: principal exceeds the outstanding balance of ' || (l.principal - l.repaid_amount); RETURN NEXT; RETURN; END IF;
    IF p_mode IS NULL OR p_mode = 'journal' THEN repayment_id := NULL; msg := 'Error: choose how the money was received'; RETURN NEXT; RETURN; END IF;

    PERFORM fn_ensure_owner_loan_accounts(l.society_id);
    SELECT flat_number INTO v_flat FROM apartments WHERE id = l.apartment_id;
    v_bank := fn_resolve_bank_leg(l.society_id, p_mode);
    v_journal := NEXTVAL('seq_transaction_number');

    INSERT INTO owner_loan_repayments (loan_id, society_id, repay_date, principal_amount, interest_amount, mode, journal_id, created_by)
    VALUES (p_loan_id, l.society_id, p_repay_date, v_p, v_i, p_mode, v_journal, p_created_by)
    RETURNING id INTO v_rep;

    IF v_bank IS NOT NULL THEN
        INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                                  amount, mode, status, created_by, created_at, source_table, source_id, journal_id)
        VALUES (l.society_id, 'Dr', p_repay_date, v_bank, l.apartment_id, 'apartment',
                'Loan repayment received - ' || v_flat, v_p + v_i, p_mode, 'paid', p_created_by, NOW(),
                'owner_loan_repayments', v_rep, v_journal);
    END IF;
    IF v_p > 0 THEN
        INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                                  amount, mode, status, created_by, created_at, source_table, source_id, journal_id)
        VALUES (l.society_id, 'Cr', p_repay_date, 1410, l.apartment_id, 'apartment',
                'Loan principal repaid - ' || v_flat, v_p, p_mode, 'paid', p_created_by, NOW(),
                'owner_loan_repayments', v_rep, v_journal);
    END IF;
    IF v_i > 0 THEN
        INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                                  amount, mode, status, created_by, created_at, source_table, source_id, journal_id)
        VALUES (l.society_id, 'Cr', p_repay_date, 4116, l.apartment_id, 'apartment',
                'Loan interest received - ' || v_flat, v_i, p_mode, 'paid', p_created_by, NOW(),
                'owner_loan_repayments', v_rep, v_journal);
    END IF;

    UPDATE owner_loans SET repaid_amount = repaid_amount + v_p WHERE id = p_loan_id;
    repayment_id := v_rep; msg := 'OK'; RETURN NEXT;
END $$;

-- Simple-interest estimate on the outstanding principal since the later of the loan
-- date and the last repayment. A guide for the Board, not an accrual: interest is only
-- booked when it is actually received through fn_repay_owner_loan.
CREATE OR REPLACE FUNCTION fn_owner_loan_interest_estimate(p_loan_id INT, p_asof DATE DEFAULT CURRENT_DATE)
RETURNS NUMERIC LANGUAGE sql STABLE AS $$
    SELECT COALESCE(ROUND((l.principal - l.repaid_amount) * l.interest_rate_pct / 100
                  * GREATEST(p_asof - GREATEST(l.loan_date, COALESCE((SELECT MAX(repay_date) FROM owner_loan_repayments WHERE loan_id = l.id), l.loan_date)), 0)
                  / 365.0, 2), 0)
    FROM owner_loans l WHERE l.id = p_loan_id
$$;

-- ═══════════════════════════════════════════════════════════════════════════════
-- OWNER LOANS IN THE DUES CHECKS (No Dues, bye-law 7, s.22)
-- A loan is not a receivable, so fn_apartment_outstanding / the receivable-based checks never
-- saw it. owner_loans had no repayment date either, so "overdue" could not be decided.
-- What counts is engine POLICY, not statute, and is editable by master (AOA Rule Editor):
--   owner_loan_blocks_nodues    1  an outstanding loan blocks ISSUING a No Dues Certificate
--   owner_loan_counts_bye_law7  0  an overdue loan balance counts as arrears for bye-law 7 (opt-in)
--   owner_loan_counts_s22       0  an overdue loan balance counts toward the s.22 "dues remain" test
-- fn_apartment_outstanding is deliberately untouched (it also drives NOC and the deactivation guard).
-- owner_loans.due_date / owner_loans_due_after_loan are declared inline on the
-- table itself (see the owner_loans CREATE TABLE earlier in this file).
-- ═══════════════════════════════════════════════════════════════════════════════
-- (The default values of these three rules, and of reserve_appropriation_pct, are in schemes/UP_AOA_2010.toml.)

CREATE OR REPLACE FUNCTION fn_set_owner_loan_due_date(p_loan_id INT, p_due DATE) RETURNS TEXT
LANGUAGE plpgsql AS $$
DECLARE l owner_loans%ROWTYPE;
BEGIN
    SELECT * INTO l FROM owner_loans WHERE id = p_loan_id FOR UPDATE;
    IF NOT FOUND THEN RETURN 'Error: loan not found'; END IF;
    IF p_due IS NOT NULL AND p_due < l.loan_date THEN RETURN 'Error: the repayment date cannot be before the loan date'; END IF;
    UPDATE owner_loans SET due_date = p_due WHERE id = p_loan_id;
    RETURN 'OK';
END $$;

-- One flat's dues to the association as at a date. Receivable part matches fn_apartment_outstanding.
CREATE OR REPLACE FUNCTION fn_apartment_dues_position(p_apartment_id INT, p_asof DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (receivables_outstanding NUMERIC, loan_outstanding NUMERIC, loan_overdue NUMERIC,
               loan_interest_estimate NUMERIC, total_outstanding NUMERIC)
LANGUAGE sql STABLE AS $$
    WITH rec AS (
        SELECT COALESCE(SUM(r.amount - r.paid_amount), 0) AS v FROM receivables r
         WHERE r.entity_id = p_apartment_id AND r.role = 'apartment' AND r.status IN ('pending', 'partial')
    ), ln AS (
        SELECT COALESCE(SUM(l.principal - l.repaid_amount), 0) AS o,
               COALESCE(SUM(l.principal - l.repaid_amount) FILTER (WHERE l.due_date IS NOT NULL AND l.due_date < p_asof), 0) AS od,
               COALESCE(SUM(fn_owner_loan_interest_estimate(l.id, p_asof)), 0) AS ie
          FROM owner_loans l WHERE l.apartment_id = p_apartment_id AND l.principal > l.repaid_amount
    )
    SELECT rec.v::NUMERIC, ln.o::NUMERIC, ln.od::NUMERIC, ln.ie::NUMERIC, (rec.v + ln.o)::NUMERIC FROM rec, ln
$$;

-- ═══════════════════════════════════════════════════════════════════════════════
-- SOCIETY RESOLUTION POLICIES (Setup Wizard drop-downs)
-- Choices the engine used to hard-code. A row is PROVISIONAL (resolution_id NULL) until Master links a
-- passed resolution; fn_society_policy only reads rows that have one, else the default below.
--   nodues_blocks_on          loans_only* | dues_and_loans   what blocks ISSUING a No Dues Certificate
--   vote_ineligibility_basis  any_overdue* | margin_60_days  receivables that bar a "no dues" poll vote
--   vote_loan_basis           margin_60_days* | any_overdue  owner loans that bar a "no dues" poll vote
--   droppable_BL_07/39/49/55  locked* | droppable            may the clause be recorded 'not adopted'
-- (* = default). Clause numbers follow the Model Bye-Laws notified 16 Nov 2011 (No. 3977/8-1-11-115D.A./02T.C.-I).
-- Bye-law 7 itself governs Board elections, not polls: poll eligibility is engine policy.
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE society_policy_settings (
    id              BIGSERIAL PRIMARY KEY,
    society_id      INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    policy_key      VARCHAR(40) NOT NULL,
    value_text      VARCHAR(40) NOT NULL,
    resolution_id   INT,
    effective_from  DATE NOT NULL DEFAULT CURRENT_DATE,
    created_by      INT REFERENCES users (id),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
-- An earlier draft had UNIQUE (society_id, policy_key, effective_from): a provisional choice dated today then
-- failed to insert beside an active row of the same date. One open (unresolved) choice per policy instead —
-- enforced by the partial unique index below.
CREATE UNIQUE INDEX uq_society_policy_provisional ON society_policy_settings (society_id, policy_key) WHERE resolution_id IS NULL;
CREATE INDEX idx_society_policy_lookup ON society_policy_settings (society_id, policy_key, effective_from DESC, id DESC);

CREATE OR REPLACE FUNCTION fn_society_policy(p_society_id INT, p_key VARCHAR, p_on DATE DEFAULT CURRENT_DATE)
RETURNS TEXT LANGUAGE sql STABLE AS $$
    SELECT COALESCE(
        (SELECT sp.value_text FROM society_policy_settings sp
          WHERE sp.society_id = p_society_id AND sp.policy_key = p_key
            AND sp.resolution_id IS NOT NULL AND sp.effective_from <= p_on
          ORDER BY sp.effective_from DESC, sp.id DESC LIMIT 1),
        CASE p_key WHEN 'nodues_blocks_on'         THEN 'loans_only'
                   WHEN 'vote_ineligibility_basis' THEN 'any_overdue'
                   WHEN 'vote_loan_basis'          THEN 'margin_60_days'
                   WHEN 'droppable_BL_07' THEN 'locked' WHEN 'droppable_BL_39' THEN 'locked'
                   WHEN 'droppable_BL_49' THEN 'locked' WHEN 'droppable_BL_55' THEN 'locked'
                   ELSE NULL END)
$$;

-- ───────────────────────────────────────────────────────────────────────────────
-- Common-expense bills still unpaid AS AT a date (Act s.20(2), s.23). A bill counts from the month it accrues
-- (period_month, else due date, else creation date); what is owed is its principal less payments made on or
-- before the date (receivable_payment_log; rows without a log fall back to paid_principal). Interest, fines and
-- the transfer fee are not "common expenses" and are left out.
-- ───────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_common_expense_bills_asof(p_society_id INT, p_apartment_id INT, p_asof DATE)
RETURNS TABLE (receivable_id INT, accrued_on DATE, due_date DATE, owed NUMERIC)
LANGUAGE sql STABLE AS $$
    SELECT r.id,
           COALESCE(r.period_month, r.due_date, r.created_at::DATE),
           r.due_date,
           GREATEST((r.amount - r.interest_amount) - CASE
               WHEN EXISTS (SELECT 1 FROM receivable_payment_log g WHERE g.receivable_id = r.id)
               THEN COALESCE((SELECT SUM(g.principal_delta) FROM receivable_payment_log g
                              WHERE g.receivable_id = r.id AND g.paid_on <= p_asof), 0)
               ELSE LEAST(r.paid_principal, r.amount - r.interest_amount) END, 0)::NUMERIC
      FROM receivables r
     WHERE r.society_id = p_society_id AND r.entity_id = p_apartment_id AND r.role = 'apartment'
       AND r.charge_kind = 'common_expense'
       AND r.status IN ('pending', 'partial', 'unverified', 'paid')
       AND COALESCE(r.period_month, r.due_date, r.created_at::DATE) <= p_asof
$$;

-- Act s.20(2): common expenses unpaid for MORE than 12 months may be recovered, through the Competent
-- Authority, as arrears of land revenue. This lists the flats that have reached that point; the application
-- is the association's to make (nothing is filed from here). s20_recovery_months is a Layer-0 rule.
CREATE OR REPLACE FUNCTION fn_s20_recovery_candidates(p_society_id INT, p_asof DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (apartment_id INT, flat_number VARCHAR, owner_name VARCHAR, bills INT, oldest_due_date DATE,
               amount_due NUMERIC, months_threshold INT)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_months INT;
BEGIN
    v_months := fn_regime_param_num(p_society_id, 's20_recovery_months', p_asof)::INT;
    IF v_months IS NULL THEN RETURN; END IF;
    RETURN QUERY
    SELECT a.id, a.flat_number, a.owner_name, COUNT(*)::INT, MIN(b.due_date), SUM(b.owed)::NUMERIC, v_months
      FROM apartments a
      JOIN LATERAL fn_common_expense_bills_asof(p_society_id, a.id, p_asof) b ON TRUE
     WHERE a.society_id = p_society_id AND a.active
       AND b.owed > 0
       AND b.due_date IS NOT NULL AND b.due_date < (p_asof - make_interval(months => v_months))::DATE
     GROUP BY a.id, a.flat_number, a.owner_name
     ORDER BY SUM(b.owed) DESC, a.flat_number;
END $$;

-- Act s.23(2): on a sale, bequest or transfer the purchaser / transferee is entitled to a statement from the
-- Board of the unpaid common-expense assessment against the transferor, and is not liable for more than the
-- amount it sets out. This computes that figure as at the transfer date (what s.23(1) makes the transferee
-- jointly liable for); fn_issue_purchaser_statement freezes it on the transfer record. The transfer fee is
-- shown separately because it is not a common expense and so is outside s.23.
CREATE OR REPLACE FUNCTION fn_purchaser_dues_statement(p_transfer_id INT, p_asof DATE DEFAULT NULL)
RETURNS TABLE (transfer_id INT, apartment_id INT, flat_number VARCHAR, transferor_name VARCHAR, transferee_name VARCHAR,
               as_at DATE, bills INT, common_expense_unpaid NUMERIC, oldest_due_date DATE,
               transfer_fee_unpaid NUMERIC, statement_issued_on DATE, statement_amount NUMERIC)
LANGUAGE plpgsql STABLE AS $$
DECLARE t apartment_transfers%ROWTYPE; v_asof DATE;
BEGIN
    SELECT * INTO t FROM apartment_transfers WHERE id = p_transfer_id;
    IF NOT FOUND THEN RETURN; END IF;
    v_asof := COALESCE(p_asof, t.transfer_date);
    RETURN QUERY
    SELECT t.id, t.apartment_id, a.flat_number, t.transferor_name, t.transferee_name, v_asof,
           COALESCE(x.n, 0)::INT, COALESCE(x.amt, 0)::NUMERIC, x.oldest,
           COALESCE((SELECT GREATEST(r.amount - r.paid_amount, 0) FROM receivables r
                      WHERE r.id = t.fee_receivable_id AND r.status NOT IN ('cancelled', 'rejected')), 0)::NUMERIC,
           t.statement_issued_on, t.statement_amount
      FROM apartments a
      LEFT JOIN LATERAL (
            SELECT COUNT(*) FILTER (WHERE b.owed > 0) AS n, SUM(b.owed) AS amt, MIN(b.due_date) FILTER (WHERE b.owed > 0) AS oldest
              FROM fn_common_expense_bills_asof(t.society_id, t.apartment_id, v_asof) b) x ON TRUE
     WHERE a.id = t.apartment_id;
END $$;

-- Freeze the s.23(2) figure: the amount the Board states becomes the ceiling on what the purchaser can be
-- asked to pay, so it is recorded once and cannot be silently re-issued at a different number.
CREATE OR REPLACE FUNCTION fn_issue_purchaser_statement(p_transfer_id INT, p_issued_by INT, p_asof DATE DEFAULT NULL)
RETURNS TABLE (ok BOOLEAN, msg TEXT, statement_amount NUMERIC)
LANGUAGE plpgsql AS $$
DECLARE t apartment_transfers%ROWTYPE; v_amt NUMERIC;
BEGIN
    SELECT * INTO t FROM apartment_transfers WHERE id = p_transfer_id FOR UPDATE;
    IF NOT FOUND THEN ok := FALSE; msg := 'Error: transfer not found'; statement_amount := NULL; RETURN NEXT; RETURN; END IF;
    IF t.statement_issued_on IS NOT NULL THEN
        ok := FALSE; msg := format('Error: a statement of %s was already issued on %s', t.statement_amount, t.statement_issued_on);
        statement_amount := t.statement_amount; RETURN NEXT; RETURN; END IF;
    SELECT s.common_expense_unpaid INTO v_amt FROM fn_purchaser_dues_statement(p_transfer_id, p_asof) s;
    UPDATE apartment_transfers
       SET statement_amount = COALESCE(v_amt, 0), statement_issued_on = CURRENT_DATE, statement_issued_by = p_issued_by
     WHERE id = p_transfer_id;
    ok := TRUE; msg := 'OK'; statement_amount := COALESCE(v_amt, 0); RETURN NEXT;
END $$;

-- May the No Dues Certificate for this transfer be ISSUED? (Refusing is always allowed, and the bye-law
-- 39 deemed grant still runs by the calendar, so the Board must refuse inside the window.)
-- Now uses fn_get_standing for unified noc_blocked check (Phase 2).
CREATE OR REPLACE FUNCTION fn_nodues_issue_check(p_transfer_id INT, p_asof DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (can_issue BOOLEAN, reason TEXT, loan_outstanding NUMERIC)
LANGUAGE plpgsql STABLE AS $$
DECLARE t apartment_transfers%ROWTYPE; v_standing RECORD;
BEGIN
    SELECT * INTO t FROM apartment_transfers WHERE id = p_transfer_id;
    IF NOT FOUND THEN can_issue := FALSE; reason := 'transfer not found'; loan_outstanding := 0; RETURN NEXT; RETURN; END IF;
    SELECT * INTO v_standing FROM fn_get_standing(t.society_id, t.apartment_id, p_asof);
    loan_outstanding := COALESCE(v_standing.loan_outstanding, 0);
    -- Bye-law 39: the certificate is deemed granted after 15 days, so the Board must be able to REFUSE inside the
    -- window; what this check gates is recording it as ISSUED. Ordinary dues are the NOC check's concern
    -- (fn_check_noc_eligibility); by default only an owner loan blocks, as documented in the README and tested in
    -- test_owner_loan_dues_live.py. A society resolution may widen this to ordinary dues too (policy
    -- nodues_blocks_on = 'dues_and_loans'). (fn_get_standing.noc_blocked always counts receivables.)
    IF COALESCE(v_standing.dues_outstanding, 0) > 0 AND fn_society_policy(t.society_id, 'nodues_blocks_on', p_asof) = 'dues_and_loans' THEN
        can_issue := FALSE;
        reason := format('dues of %s are still outstanding on this flat; recover them first, or record the certificate as refused', v_standing.dues_outstanding);
    ELSIF loan_outstanding > 0 AND COALESCE(fn_regime_param_num(t.society_id, 'owner_loan_blocks_nodues', p_asof), 1) = 1 THEN
        can_issue := FALSE;
        reason := format('an owner loan of %s is still outstanding on this flat; recover it first, or record the certificate as refused', loan_outstanding);
    ELSE
        can_issue := TRUE; reason := 'OK';
    END IF;
    RETURN NEXT;
END $$;

-- ═══════════════════════════════════════════════════════════════════════════════
-- UP AOA COMPLIANCE — additional statutory requirements identified in audit
--   (1) Bye-law 4: entrance fee (₹1,000) on owner admission
--   (2) Bye-law 5: one share per owner on admission
--   (3) Bye-law 23(f): daily cashbook signature
--   (4) Bye-law 45: investment restriction (co-operative bank / Trust securities / approved bank)
--   (5) Bye-law 44(d): borrowing needs Competent Authority approval
--   (6) Act s.18(2): tenant jointly liable with owner
--   (7) Bye-law 8: Board election voting by undivided-interest percentage
-- ═══════════════════════════════════════════════════════════════════════════════

-- ── (1) Entrance fee + share capital (bye-laws 4 and 5) ─────────────────────────
-- Recorded when a flat changes ownership. The fee is a receivable on the flat
-- (a due to the association), charged once on first admission. The share capital
-- entry is a register record; the physical share certificate is outside this engine.
CREATE TABLE owner_admissions (
    id              SERIAL PRIMARY KEY,
    society_id      INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    apartment_id    INT NOT NULL REFERENCES apartments (id) ON DELETE CASCADE,
    admission_date  DATE NOT NULL,
    owner_name      VARCHAR(100),
    entrance_fee    NUMERIC(10, 2),              -- NULL = not yet applied / collected
    entrance_fee_paid BOOLEAN NOT NULL DEFAULT FALSE,
    share_count     INT DEFAULT 1,               -- one share per owner (bye-law 5)
    share_face_value NUMERIC(10, 2),
    share_paid      BOOLEAN NOT NULL DEFAULT FALSE,
    receivable_id   INT REFERENCES receivables (id) ON DELETE SET NULL,
    created_by      INT REFERENCES users (id),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_owner_admission_apartment UNIQUE (society_id, apartment_id)
);
CREATE INDEX idx_owner_admissions_society ON owner_admissions (society_id, apartment_id);

CREATE OR REPLACE FUNCTION fn_entrance_fee_due(p_society_id INT, p_apartment_id INT)
RETURNS TABLE (entrance_fee NUMERIC, is_paid BOOLEAN, receivable_id INT, message TEXT)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_fee NUMERIC; v_name TEXT; v_paid BOOLEAN; v_rec INT;
BEGIN
    v_fee := fn_regime_param_num(p_society_id, 'entrance_fee', CURRENT_DATE);
    IF v_fee IS NULL THEN
        RETURN QUERY SELECT NULL::NUMERIC, FALSE, NULL::INT, 'entrance fee not configured for this society''s regime'::TEXT;
        RETURN;
    END IF;
    SELECT o.entrance_fee_paid, o.receivable_id
      INTO v_paid, v_rec
    FROM owner_admissions oa
    JOIN apartments a ON a.id = oa.apartment_id
    WHERE oa.society_id = p_society_id AND oa.apartment_id = p_apartment_id
    ORDER BY oa.admission_date DESC LIMIT 1;

    IF found THEN
        RETURN QUERY SELECT v_fee, v_paid, v_rec,
            CASE WHEN v_paid THEN 'paid' ELSE 'due' END;
    ELSE
        RETURN QUERY SELECT v_fee, FALSE, NULL, 'no admission recorded for this flat';
    END IF;
END
$$;

-- fn_record_admission (bye-law 4 gap fix, 2026-10)
-- Atomically: upserts owner_admissions, then — if the entrance fee is > 0
-- and no receivable already exists — inserts a 'pending' receivable so the
-- amount appears in the flat's ledger balance immediately, without waiting
-- for a separate pay_admission_fee() call.
-- Returns: (admission_id INT, receivable_id INT, fee_amount NUMERIC, msg TEXT)
CREATE OR REPLACE FUNCTION fn_record_admission(
    p_society_id    INT,
    p_apartment_id  INT,
    p_admission_date DATE,
    p_owner_name    VARCHAR(100),
    p_fee_paid      BOOLEAN DEFAULT FALSE,
    p_share_paid    BOOLEAN DEFAULT FALSE,
    p_created_by    INT     DEFAULT NULL
)
RETURNS TABLE (admission_id INT, receivable_id INT, fee_amount NUMERIC, msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_fee       NUMERIC;
    v_face      NUMERIC;
    v_adm_id    INT;
    v_rec_id    INT;
    v_apt_id    INT;
    v_inc_acc   INT;
BEGIN
    -- Resolve regime-driven fee and share face value
    v_fee  := COALESCE(fn_regime_param_num(p_society_id, 'entrance_fee',   p_admission_date), 0);
    v_face := COALESCE(fn_regime_param_num(p_society_id, 'share_face_value', p_admission_date), 0);

    -- Upsert the admission record (ON CONFLICT because the table has a unique
    -- constraint on (society_id, apartment_id) — only one admission record per flat)
    INSERT INTO owner_admissions
        (society_id, apartment_id, admission_date, owner_name,
         entrance_fee, entrance_fee_paid, share_count, share_face_value, share_paid, created_by)
    VALUES
        (p_society_id, p_apartment_id, p_admission_date, p_owner_name,
         v_fee, p_fee_paid, 1, v_face, p_share_paid, p_created_by)
    ON CONFLICT (society_id, apartment_id) DO UPDATE
        SET admission_date    = EXCLUDED.admission_date,
            owner_name        = EXCLUDED.owner_name,
            entrance_fee      = EXCLUDED.entrance_fee,
            entrance_fee_paid = EXCLUDED.entrance_fee_paid,
            share_count       = EXCLUDED.share_count,
            share_face_value  = EXCLUDED.share_face_value,
            share_paid        = EXCLUDED.share_paid
    RETURNING id INTO v_adm_id;

    -- Retrieve the existing receivable_id (if any) from the admission row
    SELECT receivable_id INTO v_rec_id
    FROM owner_admissions
    WHERE id = v_adm_id;

    -- If the fee is > 0 and there is no receivable yet, create one now so that
    -- the amount appears in the flat's outstanding dues immediately (bye-law 4).
    IF v_fee > 0 AND v_rec_id IS NULL THEN
        -- Resolve the income account for entrance fees (tag: ENTRANCE_FEE or fallback to COMMON_PROFITS)
        SELECT id INTO v_inc_acc FROM accounts
        WHERE society_id = p_society_id
          AND (tab_name IN ('ENTRANCE_FEE', 'COMMON_PROFITS') OR name ILIKE '%entrance%fee%')
          AND active = TRUE
        ORDER BY CASE WHEN tab_name = 'ENTRANCE_FEE' THEN 0
                      WHEN tab_name = 'COMMON_PROFITS' THEN 1
                      ELSE 2 END
        LIMIT 1;

        IF v_inc_acc IS NOT NULL THEN
            INSERT INTO receivables
                (society_id, entity_id, role, description, amount, paid_amount,
                 balance, due_date, status, charge_kind, source_table, source_id)
            VALUES
                (p_society_id, p_apartment_id, 'apartment',
                 'Entrance fee — bye-law 4 (owner admission: ' || COALESCE(p_owner_name, 'new owner') || ')',
                 v_fee, CASE WHEN p_fee_paid THEN v_fee ELSE 0 END,
                 CASE WHEN p_fee_paid THEN 0 ELSE v_fee END,
                 p_admission_date,
                 CASE WHEN p_fee_paid THEN 'paid' ELSE 'pending' END,
                 'other', 'owner_admissions', v_adm_id)
            RETURNING id INTO v_rec_id;

            -- Link back so fn_entrance_fee_due can find the receivable
            UPDATE owner_admissions SET receivable_id = v_rec_id WHERE id = v_adm_id;

            -- Accrue to the income account if not already paid
            IF NOT p_fee_paid THEN
                PERFORM fn_post_receivable_accrual(
                    p_society_id, v_rec_id, p_apartment_id, 'apartment', v_inc_acc, v_fee,
                    'Entrance fee — bye-law 4 (' || COALESCE(p_owner_name, 'new owner') || ')'
                );
            END IF;
        END IF;
    END IF;

    admission_id  := v_adm_id;
    receivable_id := v_rec_id;
    fee_amount    := v_fee;
    msg := CASE
        WHEN v_fee = 0 THEN 'Admission recorded (entrance fee is zero for this regime).'
        WHEN v_rec_id IS NOT NULL AND NOT p_fee_paid THEN
            format('Admission recorded. Entrance fee ₹%s posted as pending receivable (bye-law 4).', trim_scale(v_fee))
        WHEN v_rec_id IS NOT NULL AND p_fee_paid THEN
            format('Admission recorded. Entrance fee ₹%s marked paid (bye-law 4).', trim_scale(v_fee))
        ELSE 'Admission recorded (income account not configured; receivable not posted).'
    END;
    RETURN NEXT;
END
$$;

CREATE OR REPLACE FUNCTION fn_share_capital_due(p_society_id INT, p_apartment_id INT)
RETURNS TABLE (share_count INT, face_value NUMERIC, is_paid BOOLEAN, message TEXT)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_count INT; v_face NUMERIC; v_paid BOOLEAN;
BEGIN
    v_face := fn_regime_param_num(p_society_id, 'share_face_value', CURRENT_DATE);
    IF v_face IS NULL THEN
        RETURN QUERY SELECT 0, NULL::NUMERIC, FALSE, 'share capital not configured for this society''s regime'::TEXT;
        RETURN;
    END IF;
    SELECT oa.share_count, oa.share_face_value, oa.share_paid INTO v_count, v_face, v_paid
    FROM owner_admissions oa JOIN apartments a ON a.id = oa.apartment_id
    WHERE oa.society_id = p_society_id AND oa.apartment_id = p_apartment_id
    ORDER BY oa.admission_date DESC LIMIT 1;
    IF FOUND THEN
        RETURN QUERY SELECT v_count, v_face, v_paid,
            CASE WHEN v_paid THEN 'paid' ELSE 'due' END;
    ELSE
        RETURN QUERY SELECT v_count, v_face, FALSE, 'no admission recorded for this flat';
    END IF;
END
$$;

-- ── (3) Daily cashbook signature (bye-law 23(f)) ────────────────────────────────
CREATE TABLE cashbook_signatures (
    id              SERIAL PRIMARY KEY,
    society_id      INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    day             DATE NOT NULL,
    signed_by       VARCHAR(100),            -- name/title of the signer (Secretary + 1 Board member)
    signed_at       TIMESTAMP,
    notes           TEXT,
    created_by      INT REFERENCES users (id),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_cashbook_day UNIQUE (society_id, day)
);
CREATE INDEX idx_cashbook_signatures_society ON cashbook_signatures (society_id, day);

CREATE OR REPLACE FUNCTION fn_cashbook_signature_check(p_society_id INT, p_day DATE)
RETURNS TABLE (is_signed BOOLEAN, signer TEXT, message TEXT)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_required INT;
BEGIN
    v_required := COALESCE(fn_regime_param_num(p_society_id, 'cashbook_daily_signature', CURRENT_DATE)::INT, 1);
    IF v_required = 0 THEN
        RETURN QUERY SELECT TRUE, NULL::TEXT, 'bye-law 23(f) signature tracking is not required for this society'::TEXT;
        RETURN;
    END IF;
    RETURN QUERY
    SELECT EXISTS (SELECT 1 FROM cashbook_signatures WHERE society_id = p_society_id AND day = p_day) AS is_signed,
           (SELECT signed_by::TEXT FROM cashbook_signatures WHERE society_id = p_society_id AND day = p_day) AS signer,
           CASE WHEN EXISTS (SELECT 1 FROM cashbook_signatures WHERE society_id = p_society_id AND day = p_day)
                THEN 'signed'
                ELSE 'unsigned: bye-law 23(f) requires the daily cashbook to be signed by the Secretary and one Board member'
           END AS message;
END
$$;

-- ── (4) Investment restriction (bye-law 45) ─────────────────────────────────────
-- Bye-law 45 limits investments to co-operative banks, Trust Act securities, or
-- banks approved by the Competent Authority. The `deposits` table (added in the main schema)
-- holds investments; the new `institution_type` column classifies them for the check.
ALTER TABLE deposits ADD COLUMN IF NOT EXISTS institution_type VARCHAR(50);
CREATE OR REPLACE FUNCTION fn_investment_check(p_society_id INT, p_institution_type TEXT)
RETURNS TABLE (allowed BOOLEAN, message TEXT)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_allowed TEXT; v_msg TEXT;
BEGIN
    v_allowed := fn_regime_param_text(p_society_id, 'investment_allowed_types', CURRENT_DATE);
    IF v_allowed IS NULL THEN
        RETURN QUERY SELECT TRUE, 'no investment restriction configured for this society''s regime'::TEXT;
        RETURN;
    END IF;
    IF p_institution_type = ANY (STRING_TO_ARRAY(v_allowed, ',')) THEN
        RETURN QUERY SELECT TRUE, 'allowed'::TEXT;
    ELSE
        RETURN QUERY SELECT FALSE,
            format('investment in "%s" is not permitted: bye-law 45 limits investments to %s',
                   p_institution_type, REPLACE(REPLACE(v_allowed, ',', ' / '), '_', ' '))::TEXT;
    END IF;
END
$$;

-- ── (5) Borrowing approval (bye-law 44(d)) ──────────────────────────────────────
-- By design, a borrowing over the society's threshold needs Competent Authority
-- approval. This is a gated check: the loan is recorded but flagged until the
-- approval is attached.
CREATE TABLE borrowing_approvals (
    id              SERIAL PRIMARY KEY,
    society_id      INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    loan_source     VARCHAR(50) NOT NULL,       -- e.g. 'housing_board', 'bank', 'member_loan'
    principal       NUMERIC(14, 2) NOT NULL,
    purpose         TEXT,
    ca_approval_ref VARCHAR(100),              -- Competent Authority approval reference
    ca_approved_on  DATE,
    resolution_id   INT,
    created_by      INT REFERENCES users (id),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_borrowing_approval UNIQUE (society_id, loan_source, principal)
);
CREATE INDEX idx_borrowing_approvals_society ON borrowing_approvals (society_id, ca_approved_on);

CREATE OR REPLACE FUNCTION fn_borrowing_check(p_society_id INT, p_principal NUMERIC, p_loan_source TEXT)
RETURNS TABLE (needs_approval BOOLEAN, has_approval BOOLEAN, message TEXT)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_requires INT; v_appr BOOLEAN;
BEGIN
    v_requires := fn_regime_param_num(p_society_id, 'borrowing_ca_approval', CURRENT_DATE)::INT;
    IF v_requires IS NULL OR v_requires = 0 THEN
        RETURN QUERY SELECT FALSE, TRUE, 'no CA approval required for this society''s regime'::TEXT;
        RETURN;
    END IF;
    -- If a borrowing approval row exists with a CA approval ref and date, it's approved.
    SELECT EXISTS (
        SELECT 1 FROM borrowing_approvals ba
        WHERE ba.society_id = p_society_id AND ba.principal = p_principal
          AND ba.loan_source = COALESCE(p_loan_source, ba.loan_source)
          AND ba.ca_approval_ref IS NOT NULL AND ba.ca_approved_on IS NOT NULL
    ) INTO v_appr;

    IF v_appr THEN
        RETURN QUERY SELECT TRUE, TRUE, 'approved by Competent Authority'::TEXT;
    ELSE
        RETURN QUERY SELECT TRUE, FALSE,
            format('borrowing of ₹%s needs Competent Authority approval under bye-law 44(d)', p_principal)::TEXT;
    END IF;
END
$$;

-- ── (6) Tenant joint liability (Act s.18(2)) ────────────────────────────────────
-- The tenant of record for a flat is jointly liable with the owner for common
-- expenses. This is a hard-wired statutory rule. The `tenants` table holds the
-- current tenant per apartment; receivables generated against the flat are
-- flagged to show the tenant is also on the hook.
CREATE TABLE tenants (
    id              SERIAL PRIMARY KEY,
    society_id      INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    apartment_id    INT NOT NULL REFERENCES apartments (id) ON DELETE CASCADE,
    tenant_name     VARCHAR(100) NOT NULL,
    tenant_mobile   VARCHAR(15),
    tenancy_start   DATE NOT NULL,
    tenancy_end     DATE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_by      INT REFERENCES users (id),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tenant_apartment UNIQUE (society_id, apartment_id, tenant_name)
);
CREATE INDEX idx_tenants_society_apartment ON tenants (society_id, apartment_id, is_active);

CREATE OR REPLACE FUNCTION fn_tenant_liability(p_society_id INT, p_apartment_id INT, p_asof DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (tenant_name VARCHAR, joint_liability BOOLEAN, message TEXT)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_active INT;
BEGIN
    -- s.18(2) is a hard-wired statute; the parameter confirms it is in force for this scheme.
    v_active := fn_regime_param_num(p_society_id, 'tenant_joint_liability', p_asof)::INT;
    IF v_active IS NULL OR v_active = 0 THEN
        RETURN QUERY SELECT NULL::VARCHAR, FALSE, 'tenant joint liability (s.18(2)) not configured for this society''s regime'::TEXT;
        RETURN;
    END IF;
     -- Check if any active tenant exists for this apartment
     PERFORM 1 FROM tenants t
     WHERE t.society_id = p_society_id AND t.apartment_id = p_apartment_id AND t.is_active
       AND (t.tenancy_end IS NULL OR t.tenancy_end >= p_asof)
     LIMIT 1;
     IF NOT FOUND THEN
         RETURN QUERY SELECT NULL::VARCHAR, FALSE, 'no active tenant on record'::TEXT;
         RETURN;
     END IF;
     RETURN QUERY
     SELECT t.tenant_name,
            EXISTS(SELECT 1 FROM tenants t2 WHERE t2.society_id = p_society_id AND t2.apartment_id = p_apartment_id
                     AND t2.is_active AND (t2.tenancy_end IS NULL OR t2.tenancy_end >= p_asof)) AS joint_liability,
            CASE WHEN EXISTS(SELECT 1 FROM tenants t2 WHERE t2.society_id = p_society_id AND t2.apartment_id = p_apartment_id
                             AND t2.is_active AND (t2.tenancy_end IS NULL OR t2.tenancy_end >= p_asof))
                 THEN 'tenant jointly liable with owner under s.18(2)'
                 ELSE 'no active tenant on record'
            END AS message
     FROM tenants t
     WHERE t.society_id = p_society_id AND t.apartment_id = p_apartment_id AND t.is_active
       AND (t.tenancy_end IS NULL OR t.tenancy_end >= p_asof)
     ORDER BY t.tenancy_start DESC LIMIT 1;
 END
$$;

-- ── (6b) Labour Compliance — EPF/ESIC/Contract Labour ──────────────────────────
-- Track EPF/ESIC challans for direct employees and manpower agency staff,
-- with invoice-hold gate when challans are missing.



-- ════════════════════════════════════════════════════════════════
-- TENANT JOINT-LIABILITY LINKAGE — statutory linkage of an active tenant to a
-- specific receivable (Act s.18(2)). This is the bookkeeper's trail for the rule
-- that the occupier is jointly and severally liable with the owner for the owner's
-- common expenses. It is written by the bill generator (fn_auto_generate_receivables)
-- for every periodic common-expense receivable on a flat that has an active tenant,
-- and it is read by recovery/statement/reporting paths, not by a lookup-only function.
-- ════════════════════════════════════════════════════════════════
CREATE TABLE tenant_liability_links (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    apartment_id INT NOT NULL REFERENCES apartments (id) ON DELETE CASCADE,
    receivable_id INT NOT NULL REFERENCES receivables (id) ON DELETE CASCADE,
    -- the beginning of the period this link is for (the month the receivable was generated for)
    liability_as_of DATE NOT NULL,
    -- recomputed/refresh marker: the bill generator writes a fresh link for the period;
    -- prior-period links are retained as the historical record of what was billed under
    -- joint liability, so recoveries / statements can always point at a specific period.
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tenant_liability_period UNIQUE (society_id, apartment_id, receivable_id)
);

CREATE INDEX idx_tenant_liability_links_apartment
    ON tenant_liability_links (society_id, apartment_id, liability_as_of);
CREATE INDEX idx_tenant_liability_links_receivable
    ON tenant_liability_links (receivable_id);

CREATE TABLE labour_challans (
    id                  SERIAL PRIMARY KEY,
    society_id          INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    challan_month       DATE NOT NULL,          -- first day of the month (e.g., '2025-01-01')
    challan_type        VARCHAR(20) NOT NULL CHECK (challan_type IN ('EPF', 'ESIC', 'BOTH')),
    entity_type         VARCHAR(20) NOT NULL CHECK (entity_type IN ('direct_employee', 'manpower_agency')),
    entity_name         VARCHAR(100),           -- employee name or agency name
    epf_challan_no      VARCHAR(50),
    epf_challan_date    DATE,
    epf_amount          NUMERIC(12,2),
    esic_challan_no     VARCHAR(50),
    esic_challan_date   DATE,
    esic_amount         NUMERIC(12,2),
    uploaded_by         INT REFERENCES users (id),
    uploaded_at         TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_labour_challan UNIQUE (society_id, challan_month, challan_type, entity_type, entity_name)
);
CREATE INDEX idx_labour_challans_society ON labour_challans (society_id, challan_month);

-- Track manpower agencies and their compliance requirements
CREATE TABLE manpower_agencies (
    id                  SERIAL PRIMARY KEY,
    society_id          INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    agency_name         VARCHAR(100) NOT NULL,
    service_type        VARCHAR(50) NOT NULL,   -- e.g., 'security', 'housekeeping', 'gardening'
    contract_start      DATE NOT NULL,
    contract_end        DATE,
    pf_code             VARCHAR(30),
    esic_code           VARCHAR(30),
    contact_person      VARCHAR(100),
    contact_mobile      VARCHAR(15),
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_by          INT REFERENCES users (id),
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_manpower_agencies_society ON manpower_agencies (society_id, is_active);

-- Compliance check: returns TRUE if all required challans for the month are uploaded
CREATE OR REPLACE FUNCTION fn_labour_compliance_check(
    p_society_id INT,
    p_month DATE   -- first day of month
)
RETURNS TABLE (
    entity_type VARCHAR,
    entity_name VARCHAR,
    epf_due BOOLEAN,
    epf_uploaded BOOLEAN,
    esic_due BOOLEAN,
    esic_uploaded BOOLEAN,
    compliant BOOLEAN,
    message TEXT
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    r RECORD;
BEGIN
    -- Check direct employees
    FOR r IN
        SELECT e.id, e.name
        FROM employees e
        WHERE e.society_id = p_society_id AND e.is_active
    LOOP
        SELECT EXISTS (
            SELECT 1 FROM labour_challans lc
            WHERE lc.society_id = p_society_id
              AND lc.challan_month = p_month
              AND lc.entity_type = 'direct_employee'
              AND lc.entity_name = e.name
              AND lc.challan_type IN ('EPF', 'BOTH')
              AND lc.epf_challan_no IS NOT NULL
        ) INTO epf_uploaded;

        SELECT EXISTS (
            SELECT 1 FROM labour_challans lc
            WHERE lc.society_id = p_society_id
              AND lc.challan_month = p_month
              AND lc.entity_type = 'direct_employee'
              AND lc.entity_name = e.name
              AND lc.challan_type IN ('ESIC', 'BOTH')
              AND lc.esic_challan_no IS NOT NULL
        ) INTO esic_uploaded;

        entity_type := 'direct_employee';
        entity_name := r.name;
        epf_due := TRUE;  -- Assume EPF due for all direct employees
        esic_due := TRUE; -- Assume ESIC due for all direct employees
        compliant := epf_uploaded AND esic_uploaded;
        message := CASE WHEN compliant THEN 'Compliant' ELSE 'Missing challan(s)' END;
        RETURN NEXT;
    END LOOP;

    -- Check manpower agencies
    FOR r IN
        SELECT ma.id, ma.agency_name
        FROM manpower_agencies ma
        WHERE ma.society_id = p_society_id AND ma.is_active
          AND (ma.contract_end IS NULL OR ma.contract_end >= p_month)
    LOOP
        SELECT EXISTS (
            SELECT 1 FROM labour_challans lc
            WHERE lc.society_id = p_society_id
              AND lc.challan_month = p_month
              AND lc.entity_type = 'manpower_agency'
              AND lc.entity_name = ma.agency_name
              AND lc.challan_type IN ('EPF', 'BOTH')
              AND lc.epf_challan_no IS NOT NULL
        ) INTO epf_uploaded;

        SELECT EXISTS (
            SELECT 1 FROM labour_challans lc
            WHERE lc.society_id = p_society_id
              AND lc.challan_month = p_month
              AND lc.entity_type = 'manpower_agency'
              AND lc.entity_name = ma.agency_name
              AND lc.challan_type IN ('ESIC', 'BOTH')
              AND lc.esic_challan_no IS NOT NULL
        ) INTO esic_uploaded;

        entity_type := 'manpower_agency';
        entity_name := r.agency_name;
        epf_due := TRUE;
        esic_due := TRUE;
        compliant := epf_uploaded AND esic_uploaded;
        message := CASE WHEN compliant THEN 'Compliant' ELSE 'Missing challan(s) - invoice hold recommended' END;
        RETURN NEXT;
    END LOOP;

    IF NOT FOUND THEN
        entity_type := NULL; entity_name := NULL;
        epf_due := FALSE; epf_uploaded := FALSE;
        esic_due := FALSE; esic_uploaded := FALSE;
        compliant := TRUE;
        message := 'No employees or agencies to check';
        RETURN NEXT;
    END IF;
END
$$;

-- Invoice hold gate: returns TRUE if any labour compliance is pending for the month
CREATE OR REPLACE FUNCTION fn_labour_invoice_hold_gate(
    p_society_id INT,
    p_vendor_name VARCHAR,
    p_month DATE
)
RETURNS TABLE (hold BOOLEAN, reason TEXT)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_compliant BOOLEAN;
BEGIN
    -- Check if this vendor is a manpower agency with pending challans
    SELECT EXISTS (
        SELECT 1 FROM manpower_agencies ma
        WHERE ma.society_id = p_society_id
          AND ma.agency_name ILIKE p_vendor_name
          AND ma.is_active
          AND (ma.contract_end IS NULL OR ma.contract_end >= p_month)
    ) INTO v_compliant;

    IF v_compliant THEN
        SELECT NOT compliant INTO v_compliant
        FROM fn_labour_compliance_check(p_society_id, p_month)
        WHERE entity_type = 'manpower_agency' AND entity_name ILIKE p_vendor_name
        LIMIT 1;

        IF v_compliant THEN
            hold := TRUE;
            reason := 'Labour compliance pending: missing EPF/ESIC challan for ' || to_char(p_month, 'Mon YYYY');
            RETURN NEXT; RETURN;
        END IF;
    END IF;

    hold := FALSE;
    reason := 'No labour compliance hold';
    RETURN NEXT; RETURN;
END
$$;

-- ── (7) Board election with weighted voting (bye-law 8) ─────────────────────────
-- Bye-law 8 weights each vote by the owner's undivided-interest percentage in the
-- Declaration (Act s.12(1)(f)). 'majority' means 51% of the votes. Quorum is 30%
-- of owners present in person. This function supports both voting bases:
-- one_apartment_one_vote (for advisory polls) and undivided_interest (for Board
-- elections, budget approval, s.22 resolutions — statutory acts).
CREATE TABLE board_candidates (
    id              SERIAL PRIMARY KEY,
    society_id      INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    apartment_id    INT NOT NULL REFERENCES apartments (id) ON DELETE CASCADE,
    candidate_name  VARCHAR(100) NOT NULL,
    position        VARCHAR(50),
    vote_basis      VARCHAR(30) NOT NULL DEFAULT 'undivided_interest'
                    CHECK (vote_basis IN ('undivided_interest', 'one_apartment_one_vote')),
    votes_received  NUMERIC(12, 6) DEFAULT 0,
    votes_weight    NUMERIC(9, 6) DEFAULT 0,     -- the weight of this candidate's vote (only for undivided_interest voting)
    created_by      INT REFERENCES users (id),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_board_candidates_society ON board_candidates (society_id, position);

CREATE TABLE board_election_votes (
    id              SERIAL PRIMARY KEY,
    society_id      INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    candidate_id    INT NOT NULL REFERENCES board_candidates (id) ON DELETE CASCADE,
    voter_apartment_id INT NOT NULL REFERENCES apartments (id),
    vote_date       DATE NOT NULL,
    vote_weight     NUMERIC(9, 6) NOT NULL DEFAULT 1,  -- 1 for one_apartment_one_vote, undivided_interest_pct for weighted
    cast_by         INT REFERENCES users (id),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_board_votes_society ON board_election_votes (society_id, candidate_id);

CREATE OR REPLACE FUNCTION fn_board_election_eligibility(p_society_id INT, p_election_date DATE, p_basis TEXT DEFAULT NULL)
RETURNS TABLE (apartment_id INT, flat_number VARCHAR, owner_name VARCHAR,
               eligible BOOLEAN, vote_weight NUMERIC, ineligible_reason TEXT)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_basis TEXT; v_arrears_days INT; v_blocks_loans INT; v_cut DATE;
BEGIN
    v_basis := COALESCE(p_basis, fn_regime_param_text(p_society_id, 'board_election_voting_basis', p_election_date), 'undivided_interest');
    v_arrears_days := COALESCE(fn_regime_param_num(p_society_id, 'arrears_disqualify_days', p_election_date)::INT, 60);
    v_blocks_loans := COALESCE(fn_regime_param_num(p_society_id, 'owner_loan_counts_bye_law7', p_election_date)::INT, 0);
    v_cut := fn_bye_law7_cutoff_date(p_society_id, p_election_date);

    RETURN QUERY
    SELECT a.id, a.flat_number, a.owner_name,
           CASE WHEN COALESCE(ar.arrears, 0) = 0 AND COALESCE(lo.overdue, 0) = 0 THEN TRUE ELSE FALSE END AS eligible,
           CASE WHEN v_basis = 'undivided_interest' THEN COALESCE(a.undivided_interest_pct, 0) ELSE 1 END AS vote_weight,
           CASE
               WHEN COALESCE(ar.arrears, 0) > 0 THEN format('arrears of ₹%s exceed %s days at cutoff', ar.arrears, v_arrears_days)
               WHEN COALESCE(lo.overdue, 0) > 0 THEN format('overdue owner loan of ₹%s', lo.overdue)
               ELSE NULL
           END AS ineligible_reason
    FROM apartments a
    LEFT JOIN LATERAL fn_common_expense_arrears_asof(p_society_id, a.id, v_cut, v_arrears_days) ar ON TRUE
    LEFT JOIN LATERAL (
        SELECT COALESCE(SUM(l.principal - l.repaid_amount) FILTER (
                   WHERE v_blocks_loans = 1 AND l.due_date IS NOT NULL AND l.due_date < v_cut - v_arrears_days), 0) AS overdue
        FROM owner_loans l WHERE l.society_id = p_society_id AND l.apartment_id = a.id AND l.principal > l.repaid_amount
    ) lo ON TRUE
    WHERE a.society_id = p_society_id AND a.active
    ORDER BY a.flat_number;
END
$$;

CREATE OR REPLACE FUNCTION fn_declare_board_election_results(p_society_id INT, p_position VARCHAR)
RETURNS TABLE (candidate_name VARCHAR, flat_number VARCHAR, vote_count NUMERIC, vote_weight NUMERIC,
               vote_pct NUMERIC, won BOOLEAN)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_basis TEXT; v_total_weight NUMERIC; v_quorum_owners INT;
BEGIN
    v_basis := fn_regime_param_text(p_society_id, 'board_election_voting_basis', CURRENT_DATE);
    v_total_weight := (SELECT SUM(vote_weight) FROM board_candidates WHERE society_id = p_society_id AND position = p_position);
    v_quorum_owners := (SELECT COUNT(*) FROM board_candidates bc
                         WHERE bc.society_id = p_society_id AND bc.position = p_position
                           AND EXISTS (SELECT 1 FROM apartments a WHERE a.id = bc.apartment_id AND a.society_id = p_society_id AND a.active));

    RETURN QUERY
    SELECT bc.candidate_name, a.flat_number,
           (SELECT COUNT(*) FROM board_election_votes WHERE candidate_id = bc.id) AS vote_count,
           bc.vote_weight,
           ROUND(100.0 * (SELECT COUNT(*) FROM board_election_votes WHERE candidate_id = bc.id) /
                 NULLIF(v_total_weight, 0), 2) AS vote_pct,
           CASE WHEN v_basis = 'undivided_interest'
                THEN (SELECT SUM(bev.vote_weight) FROM board_election_votes bev WHERE bev.candidate_id = bc.id) >=
                     COALESCE(fn_regime_param_num(p_society_id, 'poll_majority_pct', CURRENT_DATE), 51) / 100.0 * v_total_weight
                ELSE (SELECT COUNT(*) FROM board_election_votes WHERE candidate_id = bc.id) > 0
                    AND (SELECT COUNT(*) FROM board_election_votes) >=
                    COALESCE(fn_regime_param_num(p_society_id, 'poll_majority_pct', CURRENT_DATE), 51) / 100.0 *
                    NULLIF((SELECT COUNT(*) FROM board_election_votes), 0)
           END AS won
    FROM board_candidates bc
    JOIN apartments a ON a.id = bc.apartment_id
    WHERE bc.society_id = p_society_id AND bc.position = p_position
    ORDER BY vote_pct DESC, bc.id;
END
$$;

-- ═══════════════════════════════════════════════════════════════════════════════
-- MASTER RULE EDITOR — append-only audit log + societies.state → legal regime sync
-- Backs Master Portal → "AOA Rule Editor" (app/services/regime_rules_admin.py).
-- Idempotent: safe to re-run, safe to paste into Master Settings → Integrate to DB.
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE regime_rule_audit (
    id              BIGSERIAL PRIMARY KEY,
    target_table    VARCHAR(40) NOT NULL CHECK (target_table IN
                        ('regime_rule_parameters', 'legal_instrument_catalog', 'societies.cash_limit_mode', 'society_bye_laws', 'meetings', 'resolutions', 'society_policy_settings', 'society_rule_decisions')),
    regime_code     VARCHAR(30),
    society_id      INT,
    rule_key        VARCHAR(300),
    action          VARCHAR(20) NOT NULL CHECK (action IN ('new_version', 'update', 'set', 'confirm_provisional')),
    old_value       JSONB,
    new_value       JSONB,
    reason          TEXT NOT NULL CHECK (length(btrim(reason)) >= 10),
    changed_by      INT,
    changed_by_role VARCHAR(20),
    changed_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_regime_rule_audit_changed_at ON regime_rule_audit (changed_at DESC);
-- target_table's allowed-value CHECK is declared inline above; changing that
-- list means re-provisioning from this file.

CREATE OR REPLACE FUNCTION trg_regime_rule_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'regime_rule_audit is append-only';
END
$$;

CREATE TRIGGER regime_rule_audit_immutable BEFORE UPDATE OR DELETE ON regime_rule_audit
    FOR EACH ROW EXECUTE FUNCTION trg_regime_rule_audit_immutable();

-- The Setup Wizard writes societies.state as a code ('UP'); older rows hold the full name
-- ('Uttar Pradesh'). Every fn_regime_param_* / fn_* compliance function reads
-- society_legal_regime, so a society with a state but no regime row silently got "rule not
-- applicable" from all of them. This keeps the two in step, for every writer of societies.state.
-- Only an ACTIVE regime profile is ever assigned; a state with none leaves the row untouched.
CREATE OR REPLACE FUNCTION fn_sync_society_regime(p_society_id INT) RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
    v_state  TEXT;
    v_const  TEXT;
    v_code   TEXT;
    v_regime VARCHAR(30);
    v_from   DATE;
BEGIN
    SELECT btrim(state), constitution INTO v_state, v_const FROM societies WHERE id = p_society_id;
    IF v_state IS NULL OR v_state = '' THEN
        RETURN 'no_state';
    END IF;
    SELECT m.code INTO v_code
    FROM (VALUES ('UP','UTTAR PRADESH'), ('MH','MAHARASHTRA'), ('KA','KARNATAKA'), ('TN','TAMIL NADU'),
                 ('DL','DELHI'), ('RJ','RAJASTHAN'), ('MP','MADHYA PRADESH'), ('WB','WEST BENGAL'),
                 ('GJ','GUJARAT'), ('TS','TELANGANA'), ('AP','ANDHRA PRADESH'), ('BR','BIHAR'),
                 ('HR','HARYANA'), ('PB','PUNJAB'), ('KL','KERALA')) AS m(code, name)
    WHERE m.code = upper(v_state) OR m.name = upper(v_state);
    -- A scheme is state x constitution. Where no researched scheme exists for that pair (another state, or
    -- a UP society that is not an AOA) the society gets the GENERIC scheme: central laws only, the society decides.
    IF v_code IS NOT NULL THEN
        SELECT code, effective_from INTO v_regime, v_from
        FROM legal_regime_profiles
        WHERE state_code = v_code AND constitution = v_const AND status = 'active'
        ORDER BY effective_from DESC LIMIT 1;
    END IF;
    IF v_regime IS NULL THEN
        SELECT code, effective_from INTO v_regime, v_from
        FROM legal_regime_profiles WHERE code = 'GENERIC' AND status = 'active';
    END IF;
    IF v_regime IS NULL THEN
        RETURN CASE WHEN v_code IS NULL THEN 'unknown_state' ELSE 'no_active_regime' END;
    END IF;
    INSERT INTO society_legal_regime (society_id, regime_code, effective_from, source_reference)
    VALUES (p_society_id, v_regime, v_from, 'auto: societies.state = ' || v_state || ', constitution = ' || v_const)
    ON CONFLICT (society_id) DO UPDATE
        SET regime_code = EXCLUDED.regime_code, effective_from = EXCLUDED.effective_from,
            source_reference = EXCLUDED.source_reference, updated_at = NOW()
        WHERE society_legal_regime.regime_code <> EXCLUDED.regime_code;
    RETURN v_regime;
END
$$;

CREATE OR REPLACE FUNCTION trg_societies_sync_regime() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM fn_sync_society_regime(NEW.id);
    RETURN NULL;
END
$$;

CREATE TRIGGER societies_sync_regime AFTER INSERT OR UPDATE OF state, constitution ON societies
    FOR EACH ROW EXECUTE FUNCTION trg_societies_sync_regime();

-- One-off backfill for societies that already picked a state in the wizard.
SELECT fn_sync_society_regime(id) FROM societies;

-- ═══════════════════════════════════════════════════════════════════════════════
-- AOA BYE-LAWS ACCEPTANCE & GOVERNANCE LAYER
-- Phase 0: Core tables for clause-level bye-law register + governance workflow
-- ═══════════════════════════════════════════════════════════════════════════════

-- 1. decision_types — whitelisted decision codes (seeded below)
CREATE TABLE decision_types (
    id                  SERIAL PRIMARY KEY,
    code                VARCHAR(40) NOT NULL UNIQUE,
    label               VARCHAR(120) NOT NULL,
    required_body       VARCHAR(10) NOT NULL CHECK (required_body IN ('GBM', 'MC')),
    majority_pct        NUMERIC(5, 2) NOT NULL DEFAULT 50.00 CHECK (majority_pct > 0 AND majority_pct <= 100),
    description         TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 2. meetings — GBM / EGM / MC records
CREATE TABLE meetings (
    id                  SERIAL PRIMARY KEY,
    society_id          INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    type                VARCHAR(10) NOT NULL CHECK (type IN ('GBM', 'EGM', 'MC')),
    held_on             DATE NOT NULL,
    quorum_met          BOOLEAN NOT NULL DEFAULT FALSE,
    minutes_pdf         VARCHAR(255),
    created_by          INT REFERENCES users (id),
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_meetings_society ON meetings (society_id, held_on DESC);

-- 3. resolutions — Decisions linked to meetings and bye-law clauses
CREATE TABLE resolutions (
    id                  SERIAL PRIMARY KEY,
    meeting_id          INT NOT NULL REFERENCES meetings (id) ON DELETE CASCADE,
    clause_id           VARCHAR(30),
    decision_type_id    INT NOT NULL REFERENCES decision_types (id),
    body                TEXT NOT NULL,
    majority_required   NUMERIC(5, 2) NOT NULL,
    passed              BOOLEAN NOT NULL DEFAULT FALSE,
    passed_on           DATE,
    text                TEXT,
    resolution_type     VARCHAR(50),
    reference_id        INT,
    status              VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'passed', 'rejected')),
    created_by          INT REFERENCES users (id),
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
ALTER TABLE owner_loans
    ADD CONSTRAINT owner_loans_resolution_id_fkey
    FOREIGN KEY (resolution_id) REFERENCES resolutions (id) ON DELETE SET NULL;
CREATE INDEX idx_resolutions_meeting ON resolutions (meeting_id);
CREATE INDEX idx_resolutions_clause ON resolutions (clause_id);

-- society_policy_settings is defined earlier in this file than the governance
-- tables, so its resolution_id FK cannot be declared inline — the same single
-- forward reference as societies.fk_primary_bank_account above.
ALTER TABLE society_policy_settings
    ADD CONSTRAINT society_policy_settings_resolution_id_fkey
    FOREIGN KEY (resolution_id) REFERENCES resolutions (id) ON DELETE SET NULL;

-- investment_register was defined earlier than resolutions table
ALTER TABLE investment_register
    ADD CONSTRAINT investment_register_resolution_id_fkey
    FOREIGN KEY (resolution_id) REFERENCES resolutions (id) ON DELETE SET NULL;

-- affiliation_register was defined earlier than resolutions table
ALTER TABLE affiliation_register
    ADD CONSTRAINT affiliation_register_resolution_id_fkey
    FOREIGN KEY (resolution_id) REFERENCES resolutions (id) ON DELETE SET NULL;

-- auditor_appointments was defined earlier than resolutions table
ALTER TABLE auditor_appointments
    ADD CONSTRAINT auditor_appointments_resolution_id_fkey
    FOREIGN KEY (resolution_id) REFERENCES resolutions (id) ON DELETE SET NULL;

-- bye_law_amendments was defined earlier than resolutions table
ALTER TABLE bye_law_amendments
    ADD CONSTRAINT bye_law_amendments_gbm_resolution_id_fkey
    FOREIGN KEY (gbm_resolution_id) REFERENCES resolutions (id) ON DELETE SET NULL;

-- borrowing_approvals was defined earlier than resolutions table
ALTER TABLE borrowing_approvals
    ADD CONSTRAINT borrowing_approvals_resolution_id_fkey
    FOREIGN KEY (resolution_id) REFERENCES resolutions (id) ON DELETE SET NULL;

-- 4. resolution_effects — Enactment queue (whitelisted handlers only)
CREATE TABLE resolution_effects (
    id                  SERIAL PRIMARY KEY,
    resolution_id       INT NOT NULL REFERENCES resolutions (id) ON DELETE CASCADE,
    handler_name        VARCHAR(60) NOT NULL CHECK (handler_name IN ('set_regime_param', 'set_society_policy', 'set_board_param')),
    payload_json        JSONB NOT NULL,
    executed_at         TIMESTAMP,
    status              VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'executed', 'failed')),
    error_message       TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_resolution_effects_resolution ON resolution_effects (resolution_id);

-- 5. society_bye_laws — Clause-level bye-law register (4-layer hierarchy)
--    Layer 0: Statute (UP Apartment Act 2010) — LOCKED, not stored here
--    Layer 1: Model Bye-Laws 2011 — per clause: Adopt as-is | Adopt with variation | Not adopted
--    Layer 2: Society Policies — GBM resolution required; can tighten Layer 1, never loosen
--    Layer 3: Board Decisions — MC resolution; operational parameters within policy bounds
CREATE TABLE society_bye_laws (
    id                  BIGSERIAL PRIMARY KEY,
    society_id          INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    clause_id           VARCHAR(30) NOT NULL,
    layer               INT NOT NULL CHECK (layer IN (1, 2, 3)),
    status              VARCHAR(25) NOT NULL CHECK (status IN ('adopted_as_is', 'adopted_with_variation', 'not_adopted', 'provisional')),
    variation_text      TEXT,
    -- A provisional row remembers what the admin intends (adopt as-is / with
    -- variation / not adopted) until a passed resolution is linked; without
    -- this an 'adopt as-is' or 'not adopted' choice could not be held at all.
    proposed_status     VARCHAR(25)
        CHECK (proposed_status IN ('adopted_as_is', 'adopted_with_variation', 'not_adopted')),
    resolution_id       INT REFERENCES resolutions (id) ON DELETE SET NULL,
    effective_from      DATE NOT NULL DEFAULT CURRENT_DATE,
    effective_to        DATE,
    created_by          INT REFERENCES users (id),
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (society_id, clause_id, layer, effective_from)
);
CREATE INDEX idx_society_bye_laws_lookup ON society_bye_laws (society_id, clause_id, layer, effective_from DESC);
CREATE INDEX idx_society_bye_laws_provisional ON society_bye_laws (society_id, status) WHERE status = 'provisional';

-- 5b. society_rule_decisions - the same four-layer model at PARAMETER level.
--     society_bye_laws records "this clause is adopted / varied / not adopted" as free text; this table
--     records the actual VALUE a society has decided for a rule the engine reads (rule_parameter_defs), so
--     fn_rule() can apply it. Layer 1 = Model Bye-Law adoption (as-is / variation / not adopted),
--     2 = Society policy (GBM), 3 = Board decision (MC). Provisional until a passed resolution backs it.
--     review_status: the society admin records the decision with the meeting minutes attached; Master
--     spot-checks it. 'flagged' suspends it (fn_rule ignores it) until cleared.
CREATE TABLE society_rule_decisions (
    id              BIGSERIAL PRIMARY KEY,
    society_id      INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    rule_key        VARCHAR(30) NOT NULL,
    layer           INT NOT NULL CHECK (layer IN (1, 2, 3)),
    status          VARCHAR(25) NOT NULL CHECK (status IN ('adopted_as_is', 'adopted_with_variation', 'not_adopted', 'provisional')),
    proposed_status VARCHAR(25) CHECK (proposed_status IN ('adopted_as_is', 'adopted_with_variation', 'not_adopted')),
    value           NUMERIC(14, 4),
    value_text      TEXT,
    resolution_id   INT REFERENCES resolutions (id) ON DELETE SET NULL,
    review_status   VARCHAR(10) NOT NULL DEFAULT 'unreviewed' CHECK (review_status IN ('unreviewed', 'confirmed', 'flagged')),
    reviewed_by     INT REFERENCES users (id),
    reviewed_on     TIMESTAMP,
    review_note     TEXT,
    effective_from  DATE NOT NULL DEFAULT CURRENT_DATE,
    effective_to    DATE,
    created_by      INT REFERENCES users (id),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (society_id, rule_key, layer, effective_from),
    -- a variation carries exactly one of value / value_text; as-is and not-adopted carry neither
    CONSTRAINT ck_rule_decision_value CHECK (
        CASE WHEN COALESCE(CASE WHEN status = 'provisional' THEN proposed_status ELSE status END, '') = 'adopted_with_variation'
             THEN (value IS NOT NULL) <> (value_text IS NOT NULL)
             ELSE value IS NULL AND value_text IS NULL END)
);
CREATE INDEX idx_society_rule_decisions_lookup ON society_rule_decisions (society_id, rule_key, layer, effective_from DESC);
CREATE INDEX idx_society_rule_decisions_provisional ON society_rule_decisions (society_id) WHERE status = 'provisional';

-- ── LoA WORKFLOW: pending ratification tracking ──────────────────────────────────
-- Layer 3 Board decisions (SET_BOARD_PARAM) are operational: ratified by a simple MC majority,
-- but bye-law 47(1) requires Board resolutions to be placed before the next General Body for
-- ratification. Until ratified, the decision is "pending_ratification" — the engine still
-- applies it (the MC is a delegate acting within delegated powers), but it is flagged for
-- the pending-ratification list and auto-expires if not ratified within the ratification window.
CREATE TABLE loa_ratification (
    id              SERIAL PRIMARY KEY,
    society_id      INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    decision_id     BIGINT NOT NULL REFERENCES society_rule_decisions (id) ON DELETE CASCADE,
    rule_key        VARCHAR(30) NOT NULL,
    board_layer     INT NOT NULL CHECK (board_layer IN (1, 2, 3)),   -- the layer of the decision needing ratification
    status          VARCHAR(25) NOT NULL CHECK (status IN ('pending', 'ratified', 'rejected', 'expired')) DEFAULT 'pending',
    decision_effective DATE NOT NULL,                         -- when the Board decision took effect
    ratify_by       DATE NOT NULL,                           -- deadline for GBM ratification
    ratified_at     TIMESTAMP,
    ratified_by     INT REFERENCES users (id),
    ratified_resolution_id INT REFERENCES resolutions (id) ON DELETE SET NULL,
    rejected_at     TIMESTAMP,
    rejected_by     INT REFERENCES users (id),
    rejected_resolution_id INT REFERENCES resolutions (id) ON DELETE SET NULL,
    rejection_reason TEXT,
    created_by      INT REFERENCES users (id),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_loa_ratification_society ON loa_ratification (society_id, status, ratify_by);
CREATE INDEX idx_loa_ratification_decision ON loa_ratification (decision_id);

CREATE OR REPLACE FUNCTION fn_pending_ratification(p_society_id INT)
RETURNS TABLE (
    decision_id     BIGINT,
    rule_key        VARCHAR,
    label           VARCHAR,
    layer           INT,
    value           NUMERIC,
    value_text      TEXT,
    decision_effective DATE,
    ratify_by        DATE,
    days_remaining   INT,
    status          VARCHAR
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT lr.decision_id, lr.rule_key, d.label, lr.board_layer AS layer,
           sd.value, sd.value_text, lr.decision_effective, lr.ratify_by,
           lr.ratify_by - CURRENT_DATE AS days_remaining,
           lr.status
      FROM loa_ratification lr
      JOIN society_rule_decisions sd ON sd.id = lr.decision_id
      JOIN rule_parameter_defs d ON d.regime_code = (SELECT regime_code FROM society_legal_regime WHERE society_id = p_society_id)
                                 AND d.rule_key = lr.rule_key
     WHERE lr.society_id = p_society_id AND lr.status = 'pending'
     ORDER BY lr.ratify_by;
END $$;

CREATE OR REPLACE FUNCTION fn_ratify_board_decision(
    p_user_id INT,
    p_society_id INT,
    p_decision_id BIGINT,
    p_resolution_id INT,
    p_ratify BOOLEAN,              -- TRUE = ratify, FALSE = reject
    p_reason TEXT DEFAULT NULL     -- required if rejecting
)
RETURNS TABLE (ok BOOLEAN, message TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_status VARCHAR(25);
    v_days INT;
BEGIN
    -- Verify the decision belongs to this society and is pending ratification
    SELECT lr.status INTO v_status
      FROM loa_ratification lr
      JOIN society_rule_decisions sd ON sd.id = lr.decision_id
     WHERE lr.society_id = p_society_id AND lr.decision_id = p_decision_id
       AND lr.status = 'pending';
    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'No pending ratification found for that decision in this society.'::TEXT;
        RETURN;
    END IF;

    -- Verify the resolution is valid for this society and passed
    IF NOT EXISTS (
        SELECT 1 FROM resolutions r
        JOIN meetings m ON m.id = r.meeting_id
        WHERE r.id = p_resolution_id AND m.society_id IS NOT NULL
    ) THEN
        -- resolutions.society_id is derived from meeting.society_id
        IF NOT EXISTS (
            SELECT 1 FROM resolutions r
            JOIN meetings m ON m.id = r.meeting_id
            WHERE r.id = p_resolution_id AND m.society_id = p_society_id
        ) THEN
            RETURN QUERY SELECT FALSE, 'Resolution does not belong to this society.'::TEXT;
            RETURN;
        END IF;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM resolutions r
        JOIN meetings m ON m.id = r.meeting_id
        WHERE r.id = p_resolution_id AND m.society_id = p_society_id AND r.passed = TRUE
    ) THEN
        RETURN QUERY SELECT FALSE, 'Resolution must be a passed meeting resolution.'::TEXT;
        RETURN;
    END IF;

    IF p_ratify THEN
        UPDATE loa_ratification
           SET status = 'ratified',
               ratified_at = NOW(),
               ratified_by = p_user_id,
               ratified_resolution_id = p_resolution_id,
               updated_at = NOW()
         WHERE society_id = p_society_id AND decision_id = p_decision_id;
        RETURN QUERY SELECT TRUE, 'Board decision ratified by General Body.'::TEXT;
    ELSE
        IF p_reason IS NULL OR length(trim(p_reason)) < 10 THEN
            RETURN QUERY SELECT FALSE, 'Rejection requires a reason of at least 10 characters.'::TEXT;
            RETURN;
        END IF;
        UPDATE loa_ratification
           SET status = 'rejected',
               rejected_at = NOW(),
               rejected_by = p_user_id,
               rejected_resolution_id = p_resolution_id,
               rejection_reason = p_reason,
               updated_at = NOW()
         WHERE society_id = p_society_id AND decision_id = p_decision_id;
        -- Mark the decision as not_adopted so the resolver picks the next layer up
        UPDATE society_rule_decisions SET status = 'not_adopted', value = NULL, value_text = NULL
         WHERE id = p_decision_id;
        RETURN QUERY SELECT TRUE, format('Board decision rejected; effective rule reverts to the next layer up.')::TEXT;
    END IF;
END $$;

-- Auto-expire ratifications that miss the deadline (called by a scheduled job or on read).
CREATE OR REPLACE FUNCTION fn_expire_overdue_ratifications()
RETURNS INT
LANGUAGE plpgsql AS $$
DECLARE v_count INT;
BEGIN
    UPDATE loa_ratification lr
       SET status = 'expired'
     WHERE status = 'pending' AND ratify_by < CURRENT_DATE;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END $$;


INSERT INTO decision_types (code, label, required_body, majority_pct, description) VALUES
    ('ADOPT_BYE_LAW',        'Adopt Model Bye-Law Clause',            'GBM', 66.67, 'Adopt a Model Bye-Law 2011 clause as-is or with variation (2/3 majority per Model Bye-Law 58)'),
    ('VARY_BYE_LAW',         'Vary Adopted Bye-Law Clause',           'GBM', 66.67, 'Change variation text of an already-adopted clause (2/3 majority)'),
    ('REJECT_BYE_LAW',       'Not Adopt Model Bye-Law Clause',        'GBM', 50.00, 'Record that a non-mandatory Model Bye-Law clause is not adopted (simple majority)'),
    ('SET_SOCIETY_POLICY',   'Set Society Policy (Layer 2)',          'GBM', 66.67, 'Create or tighten a society policy within an adopted clause (2/3 majority; never loosens Model Bye-Law)'),
    ('SET_BOARD_PARAM',      'Set Board Parameter (Layer 3)',         'MC',  50.00, 'Operational parameter set by Managing Committee (simple majority; within policy bounds)'),
    ('APPROVE_LOAN',         'Approve Owner Loan',                    'GBM', 66.67, 'General Body approval for lending to an owner (Bye-Law 3(1)(f))'),
    ('APPROPRIATE_FUND',     'Appropriate Funds (Reserve/Sinking)',   'GBM', 66.67, 'General Body resolution for fund appropriation per Bye-Laws 46-52'),
    ('SERVICE_CUTOFF',       'Authorize Service Cut-Off (s.22)',      'GBM', 66.67, 'General Body resolution to cut essential service per UP Apartment Act s.22'),
    ('AMEND_CASH_LIMIT',     'Change Cash-Limit Enforcement Mode',    'GBM', 50.00, 'Override cash_limit_mode for this society (simple majority)'),
    ('GENERAL_RESOLUTION',   'General Resolution',                    'GBM', 50.00, 'Any other GBM resolution not covered above')
ON CONFLICT (code) DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════════════════
-- AOA BYE-LAWS ACCEPTANCE & GOVERNANCE LAYER — Phase 1
-- fn_resolve_rule + fn_get_standing (shadow mode: add column to card, don't replace yet)
-- ═══════════════════════════════════════════════════════════════════════════════

-- ───────────────────────────────────────────────────────────────────────────────
-- fn_resolve_rule — Four-layer rule resolver
--   Layer 0: Statute (UP Apartment Act 2010) — hardcoded defaults in this function
--   Layer 1: Model Bye-Laws 2011 — society_bye_laws layer=1 (adopted_as_is / adopted_with_variation)
--   Layer 2: Society Policies — society_bye_laws layer=2 (tighten only, never loosen)
--   Layer 3: Board Decisions — society_bye_laws layer=3 (operational params within policy bounds)
-- Returns first non-NULL value reading Layer 0 → 1 → 2 → 3. Enforces "lower never loosens higher".
-- ───────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION fn_resolve_rule(
    p_society_id INT,
    p_clause_id  VARCHAR,
    p_on         DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    layer          INT,
    status         VARCHAR,
    value_text     TEXT,
    effective_from DATE,
    source         TEXT
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_statute_text TEXT;
BEGIN
    -- Layer 0 baseline (statute / Model Bye-Laws default) for the clauses the engine enforces.
    v_statute_text := CASE p_clause_id
        WHEN 'BL_07' THEN 'arrears_disqualify_days=60'
        WHEN 'BL_39' THEN 'transfer_fee_pct=0.5; nodues_deemed_days=15'
        WHEN 'BL_49' THEN 'cash_payment_cheque_threshold=2500; petty_cash_limit=20000; publish_by=Jul 31; authority_copy_by=Aug 15; owner_summary_within=15 days'
        WHEN 'BL_55' THEN 'act_prevails=true'
        WHEN 'S22'   THEN 'default_exceeds_months=6; notice_days=7; wait_months=1; appeal_days=15'
        WHEN 'S20'   THEN 'recovery_after_months=12'
        ELSE NULL END;

    -- The most specific ACTIVE society adoption wins (Board decision 3 > Society policy 2 > Model bye-law 1).
    -- 'provisional' rows (not yet backed by a passed resolution) and 'not_adopted' rows never resolve.
    -- A layer-1 row says "adopted as-is", so it resolves to the baseline value; only a variation carries text.
    RETURN QUERY
    SELECT sbl.layer, sbl.status::VARCHAR,
           CASE WHEN sbl.status = 'adopted_as_is' THEN v_statute_text ELSE sbl.variation_text END,
           sbl.effective_from,
           CASE sbl.layer WHEN 1 THEN 'Model Bye-Laws 2011 (adopted by society)'
                          WHEN 2 THEN 'Society Policy (GBM resolution)'
                          ELSE 'Board Decision (MC resolution)' END
      FROM society_bye_laws sbl
     WHERE sbl.society_id = p_society_id AND sbl.clause_id = p_clause_id
       AND sbl.status IN ('adopted_as_is', 'adopted_with_variation')
       AND sbl.resolution_id IS NOT NULL
       AND sbl.effective_from <= p_on AND (sbl.effective_to IS NULL OR sbl.effective_to >= p_on)
     ORDER BY sbl.layer DESC, sbl.effective_from DESC
     LIMIT 1;
    IF FOUND THEN RETURN; END IF;

    IF v_statute_text IS NOT NULL THEN
        RETURN QUERY SELECT 0, 'statute'::VARCHAR, v_statute_text, DATE '2011-11-16',
                            'UP Apartment Act 2010 / Model Bye-Laws 2011'::TEXT;
    END IF;
    RETURN;
END $$;

-- ───────────────────────────────────────────────────────────────────────────────
-- fn_get_standing — Unified defaulter/standing resolver
-- Replaces the 5 ad-hoc checks:
--   fn_apartment_outstanding, fn_apartment_overdue_outstanding,
--   fn_bye_law7_eligibility, fn_nodues_issue_check, fn_service_cutoff_check,
--   fn_check_noc_eligibility, fn_cast_vote (via dues/overdue checks)
-- ───────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION fn_get_standing(
    p_society_id  INT,
    p_apartment_id INT,
    p_asof        DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    dues_outstanding       NUMERIC,   -- receivables pending + partial (excludes paid/credit)
    dues_overdue           NUMERIC,   -- receivables past due_date
    arrears_bye_law7       NUMERIC,   -- receivables past due_date by MORE than arrears_disqualify_days (bye-law 7; exactly 60 is eligible)
    loan_outstanding       NUMERIC,   -- owner_loans principal - repaid
    loan_overdue           NUMERIC,   -- loan_outstanding WHERE due_date <= asof - arrears_days
    ineligible_vote        BOOLEAN,   -- overdue bill (or, by society policy, bye-law-7 arrears) OR loan arrears
    ineligible_stand       BOOLEAN,   -- same as vote, plus any additional criteria
    noc_blocked            BOOLEAN,   -- dues_outstanding > 0 OR (loan_outstanding > 0 AND owner_loan_blocks_nodues)
    s22_blocked            BOOLEAN    -- TRUE if cut-off is BLOCKED (no >6mo overdue dues OR loan_overdue if policy)
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_arrears_days         INT;
    v_blocks_nodues        INT;
    v_counts_bye_law7      INT;
    v_counts_s22           INT;
    v_s22_months           INT;
BEGIN
    -- Fetch regime parameters (with defaults if not set)
    v_arrears_days    := COALESCE(fn_regime_param_num(p_society_id, 'arrears_disqualify_days', p_asof)::INT, 60);
    v_blocks_nodues   := COALESCE(fn_regime_param_num(p_society_id, 'owner_loan_blocks_nodues', p_asof)::INT, 1);
    v_counts_bye_law7 := COALESCE(fn_regime_param_num(p_society_id, 'owner_loan_counts_bye_law7', p_asof)::INT, 0);
    v_counts_s22      := COALESCE(fn_regime_param_num(p_society_id, 'owner_loan_counts_s22', p_asof)::INT, 0);
    v_s22_months      := COALESCE(fn_regime_param_num(p_society_id, 's22_default_months', p_asof)::INT, 6);

    RETURN QUERY
    WITH rec AS (
        -- Receivables: pending + partial only (excludes paid, credit)
        SELECT
            COALESCE(SUM(r.amount - r.paid_amount) FILTER (WHERE r.status IN ('pending', 'partial')), 0) AS outstanding,
            COALESCE(SUM(r.amount - r.paid_amount) FILTER (
                WHERE r.status IN ('pending', 'partial') AND r.due_date IS NOT NULL AND r.due_date < p_asof
            ), 0) AS overdue,
            COALESCE(SUM(r.amount - r.paid_amount) FILTER (
                WHERE r.status IN ('pending', 'partial') AND r.due_date IS NOT NULL
                  AND r.charge_kind = 'common_expense'
                  AND r.due_date < p_asof - v_arrears_days
            ), 0) AS arrears_bl7,
            COALESCE(SUM(r.amount - r.paid_amount) FILTER (
                WHERE r.status IN ('pending', 'partial') AND r.due_date IS NOT NULL
                  AND r.charge_kind = 'common_expense'
                  AND r.due_date <= p_asof - make_interval(months => v_s22_months)
            ), 0) AS overdue_s22_months
        FROM receivables r
        WHERE r.society_id = p_society_id
          AND r.entity_id = p_apartment_id
          AND r.role = 'apartment'
    ), ln AS (
        -- Owner loans: outstanding + overdue (if due_date set and past arrears threshold)
        SELECT
            COALESCE(SUM(l.principal - l.repaid_amount), 0) AS outstanding,
            COALESCE(SUM(l.principal - l.repaid_amount) FILTER (
                WHERE l.due_date IS NOT NULL
                  AND l.due_date < p_asof - v_arrears_days
            ), 0) AS overdue_bye_law7,
            COALESCE(SUM(l.principal - l.repaid_amount) FILTER (
                WHERE l.due_date IS NOT NULL AND l.due_date < p_asof
            ), 0) AS overdue_s22
        FROM owner_loans l
        WHERE l.society_id = p_society_id
          AND l.apartment_id = p_apartment_id
          AND l.principal > l.repaid_amount
    )
    SELECT
        rec.outstanding::NUMERIC,
        rec.overdue::NUMERIC,
        rec.arrears_bl7::NUMERIC,
        ln.outstanding::NUMERIC,
        CASE WHEN v_counts_bye_law7 = 1 THEN ln.overdue_bye_law7 ELSE 0 END::NUMERIC,
        -- poll vote ("no dues" polls): any receivable past its due date, or a bye-law-7 loan arrear
        -- society policy vote_ineligibility_basis: any_overdue (default) | margin_60_days (arrears_disqualify_days)
        -- society policy vote_loan_basis: margin_60_days (default) | any_overdue (a loan past its due_date)
        ((CASE WHEN fn_society_policy(p_society_id, 'vote_ineligibility_basis', p_asof) = 'margin_60_days'
               THEN rec.arrears_bl7 ELSE rec.overdue END) > 0
         OR (v_counts_bye_law7 = 1 AND
             (CASE WHEN fn_society_policy(p_society_id, 'vote_loan_basis', p_asof) = 'any_overdue'
                   THEN ln.overdue_s22 ELSE ln.overdue_bye_law7 END) > 0)) AS ineligible_vote,
        -- bye-law 7 candidacy: arrears must EXCEED arrears_disqualify_days (60) - 60 days exactly is still eligible
        (rec.arrears_bl7 > 0 OR (v_counts_bye_law7 = 1 AND ln.overdue_bye_law7 > 0)) AS ineligible_stand,
        (rec.outstanding > 0 OR (v_blocks_nodues = 1 AND ln.outstanding > 0)) AS noc_blocked,
        -- s22_blocked = TRUE means cut-off is BLOCKED
        -- Cut-off is allowed if there ARE receivables overdue > 6 months (default condition met)
        -- So blocked when overdue_s22_months = 0 (no >6mo default) OR loan_overdue if policy
        (rec.overdue_s22_months = 0 AND (v_counts_s22 = 0 OR ln.overdue_s22 = 0)) AS s22_blocked
    FROM rec, ln;
END $$;

-- SOCIETY GOVERNANCE: Provisional By-Law Choices, Policy Choices, Meetings, Resolutions, Enactments
CREATE TABLE IF NOT EXISTS `society_bylaw_provisional` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `society_id` BIGINT NOT NULL,
  `clause_no` VARCHAR(20) NOT NULL,
  `clause_title` VARCHAR(255) NULL,
  `clause_definition` TEXT NULL,
  `source_link` VARCHAR(512) NULL,
  `layer` ENUM('Layer 1','Layer 2','Layer 3') NOT NULL DEFAULT 'Layer 2',
  `option` ENUM('Adopted as-is','Adopted with variation','Not adopted') NOT NULL,
  `variation_text` TEXT NULL,
  `effective_date` DATE NULL,
  `reason` TEXT NULL,
  `state` ENUM('Draft','Pending Approval','Approved','Rejected','Enacted') NOT NULL DEFAULT 'Draft',
  `resolution_id` BIGINT NULL,
  `created_by` BIGINT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_society_clause` (`society_id`, `clause_no`),
  KEY `idx_soc_state` (`society_id`, `state`),
  KEY `idx_res_id` (`resolution_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `society_policy_choice` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `society_id` BIGINT NOT NULL,
  `policy_key` VARCHAR(64) NOT NULL,
  `value_json` JSON NULL,
  `value_text` VARCHAR(255) NULL,
  `reason` TEXT NULL,
  `effective_date` DATE NULL,
  `resolution_id` BIGINT NULL,
  `created_by` BIGINT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_soc_policy` (`society_id`, `policy_key`),
  KEY `idx_soc_pol` (`society_id`, `policy_key`),
  KEY `idx_res_pol` (`resolution_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `society_meetings` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `society_id` BIGINT NOT NULL,
  `meeting_type` ENUM('GBM','EGM','MC') NOT NULL,
  `meeting_no` VARCHAR(30) NULL,
  `held_on` DATE NULL,
  `venue` VARCHAR(255) NULL,
  `quorum_met` TINYINT(1) NOT NULL DEFAULT 0,
  `chaired_by` BIGINT NULL,
  `minutes_pdf` VARCHAR(512) NULL,
  `notes` TEXT NULL,
  `created_by` BIGINT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_soc_held` (`society_id`, `held_on`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `society_resolutions` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `society_id` BIGINT NOT NULL,
  `meeting_id` BIGINT NULL,
  `clause_no` VARCHAR(20) NULL,
  `subject` VARCHAR(150) NULL,
  `decision_type` ENUM('Adopt','Amend','Reject','Delegate') NOT NULL,
  `text` TEXT NOT NULL,
  `majority_pct` DECIMAL(5,2) NOT NULL DEFAULT 0.00,
  `passed` TINYINT(1) NOT NULL DEFAULT 0,
  `passed_date` DATE NULL,
  `mover` BIGINT NULL,
  `seconder` BIGINT NULL,
  `affects_bylaw` TINYINT(1) NOT NULL DEFAULT 0,
  `affects_policy` TINYINT(1) NOT NULL DEFAULT 0,
  `policy_keys` JSON NULL,
  `created_by` BIGINT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_soc_passed` (`society_id`, `passed`, `passed_date`),
  KEY `idx_meet` (`meeting_id`),
  KEY `idx_clause` (`society_id`, `clause_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `resolution_effects` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `society_id` BIGINT NOT NULL,
  `resolution_id` BIGINT NOT NULL,
  `effect_type` ENUM('BYLAW_PROVISIONAL','POLICY_CHOICE') NOT NULL,
  `target_key` VARCHAR(50) NOT NULL,
  `payload_json` JSON NOT NULL,
  `status` ENUM('PENDING','EXECUTED','SKIPPED','ERROR') NOT NULL DEFAULT 'PENDING',
  `executed_at` DATETIME NULL,
  `executed_by` BIGINT NULL,
  `error_text` TEXT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_res_effect` (`resolution_id`, `target_key`, `effect_type`),
  KEY `idx_soc_status` (`society_id`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE `societies`
  ADD COLUMN IF NOT EXISTS `cash_limit_mode` ENUM('warn','block','regime default') NOT NULL DEFAULT 'regime default';
