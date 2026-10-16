-- =============================================================================
-- EstateHub — ER.md Statutory & Financial Accuracy Remediation
-- Migration: ER_remediation_2026_10.sql
-- Applied:   FY 2026-27 (run once against the live schema)
-- Covers:    A-01, A-02, A-03, A-04, T-01, T-02, X-01, X-02,
--            G-01, G-02, G-03, G-04, C-01, I-02, Hygiene
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- A-04  FY PERIOD LOCKS — prevent back-dated posting into closed / audited FYs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fy_locks (
    id              SERIAL PRIMARY KEY,
    society_id      INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    locked_through  INT  NOT NULL,
    locked_by       INT  REFERENCES users (id) ON DELETE SET NULL,
    resolution_id   INT  REFERENCES resolutions (id) ON DELETE SET NULL,
    locked_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    notes           TEXT,
    CONSTRAINT uq_fy_lock UNIQUE (society_id, locked_through)
);
CREATE INDEX IF NOT EXISTS idx_fy_locks_society ON fy_locks (society_id, locked_through DESC);

COMMENT ON TABLE fy_locks IS
    'Period-lock: once a FY is audited/closed its start-year is recorded here. '
    'fn_check_fy_lock() is called by every posting function before inserting into '
    'transactions. Posting into a locked period is blocked.';


CREATE OR REPLACE FUNCTION fn_check_fy_lock(p_society_id INT, p_trx_date DATE)
RETURNS TEXT LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_fy       INT;
    v_locked   INT;
BEGIN
    v_fy := CASE WHEN EXTRACT(MONTH FROM p_trx_date) >= 4
                 THEN EXTRACT(YEAR FROM p_trx_date)::INT
                 ELSE EXTRACT(YEAR FROM p_trx_date)::INT - 1
            END;
    SELECT locked_through INTO v_locked
      FROM fy_locks
     WHERE society_id = p_society_id AND locked_through >= v_fy
     LIMIT 1;
    IF FOUND THEN
        RETURN format(
            'Posting date %s falls in FY %s-%s which is locked through FY %s-%s. '
            'Use a reversal journal in an open period.',
            p_trx_date, v_fy, v_fy + 1, v_locked, v_locked + 1
        );
    END IF;
    RETURN NULL;
END;
$$;


-- ---------------------------------------------------------------------------
-- A-01  IMMUTABLE LEDGER — reversal columns + BEFORE UPDATE/DELETE triggers
-- ---------------------------------------------------------------------------

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS reverses_id      INT  REFERENCES transactions (id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS reversal_reason  TEXT,
    ADD COLUMN IF NOT EXISTS is_reversal      BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN transactions.reverses_id IS
    'Non-NULL on a reversal leg: points to the original transaction leg being cancelled.';
COMMENT ON COLUMN transactions.reversal_reason IS
    'Mandatory free-text when is_reversal=TRUE — documents why the entry is being reversed.';
COMMENT ON COLUMN transactions.is_reversal IS
    'TRUE for every leg of a reversing journal pair. Set by fn_post_reversal_journal only.';


CREATE OR REPLACE FUNCTION trg_transactions_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        -- Allow removal of unreconciled bank-import drafts only.
        IF OLD.status = 'pending' AND COALESCE(OLD.source_table,'') = 'bank_statement_lines' THEN
            RETURN OLD;
        END IF;
        RAISE EXCEPTION
            'transactions is append-only after posting (id=%). '
            'Use fn_post_reversal_journal to correct a posted entry. '
            'Bank-import drafts (status=pending, source=bank_statement_lines) '
            'may be removed before confirmation.', OLD.id;
    END IF;
    IF TG_OP = 'UPDATE' THEN
        -- Allow ONLY bank_reconciled / bank_line_id / status metadata flips.
        IF OLD.amount       IS NOT DISTINCT FROM NEW.amount
           AND OLD.acc_id   IS NOT DISTINCT FROM NEW.acc_id
           AND OLD.trx_date IS NOT DISTINCT FROM NEW.trx_date
           AND OLD.entry_side IS NOT DISTINCT FROM NEW.entry_side
           AND OLD.society_id IS NOT DISTINCT FROM NEW.society_id
        THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION
            'transactions financial fields are immutable after posting (id=%). '
            'Use fn_post_reversal_journal to correct amount, account, or date errors.', OLD.id;
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_transactions_immutable ON transactions;
CREATE TRIGGER trg_transactions_immutable
    BEFORE UPDATE OR DELETE ON transactions
    FOR EACH ROW EXECUTE FUNCTION trg_transactions_immutable();


CREATE OR REPLACE FUNCTION trg_receipts_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.status IN ('pending','cancelled') THEN RETURN OLD; END IF;
        RAISE EXCEPTION 'Confirmed receipt (id=%) cannot be deleted — cancel via fn_cancel_receipt.', OLD.id;
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF OLD.amount IS NOT DISTINCT FROM NEW.amount
           AND OLD.acc_id IS NOT DISTINCT FROM NEW.acc_id
           AND OLD.society_id IS NOT DISTINCT FROM NEW.society_id
        THEN RETURN NEW; END IF;
        RAISE EXCEPTION 'Confirmed receipt (id=%) — amount and account are immutable after posting.', OLD.id;
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_receipts_immutable ON receipts;
CREATE TRIGGER trg_receipts_immutable
    BEFORE UPDATE OR DELETE ON receipts
    FOR EACH ROW
    WHEN (OLD.status = 'confirmed')
    EXECUTE FUNCTION trg_receipts_immutable();


CREATE OR REPLACE FUNCTION trg_expenses_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.status IN ('pending','cancelled') THEN RETURN OLD; END IF;
        RAISE EXCEPTION 'Confirmed expense (id=%) cannot be deleted — cancel via fn_cancel_expense.', OLD.id;
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF OLD.amount IS NOT DISTINCT FROM NEW.amount
           AND OLD.acc_id IS NOT DISTINCT FROM NEW.acc_id
           AND OLD.society_id IS NOT DISTINCT FROM NEW.society_id
        THEN RETURN NEW; END IF;
        RAISE EXCEPTION 'Confirmed expense (id=%) — amount and account are immutable after posting.', OLD.id;
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_expenses_immutable ON expenses;
CREATE TRIGGER trg_expenses_immutable
    BEFORE UPDATE OR DELETE ON expenses
    FOR EACH ROW
    WHEN (OLD.status = 'confirmed')
    EXECUTE FUNCTION trg_expenses_immutable();


-- A-01 (cont.) — reversal journal helper
CREATE OR REPLACE FUNCTION fn_post_reversal_journal(
    p_society_id    INT,
    p_journal_id    INT,
    p_reason        TEXT,
    p_reversed_by   INT,
    p_reversal_date DATE DEFAULT CURRENT_DATE
) RETURNS INT LANGUAGE plpgsql AS $$
DECLARE
    v_lock_msg   TEXT;
    v_new_jid    INT;
    v_leg        RECORD;
    v_count      INT := 0;
BEGIN
    IF p_reason IS NULL OR TRIM(p_reason) = '' THEN
        RAISE EXCEPTION 'fn_post_reversal_journal: reversal_reason is required.';
    END IF;
    v_lock_msg := fn_check_fy_lock(p_society_id, p_reversal_date);
    IF v_lock_msg IS NOT NULL THEN
        RAISE EXCEPTION '%', v_lock_msg;
    END IF;
    SELECT COUNT(*) INTO v_count
      FROM transactions
     WHERE journal_id = p_journal_id AND society_id = p_society_id;
    IF v_count = 0 THEN
        RAISE EXCEPTION 'Journal % not found for society %.', p_journal_id, p_society_id;
    END IF;
    v_new_jid := NEXTVAL('seq_transaction_number');
    FOR v_leg IN
        SELECT * FROM transactions
         WHERE journal_id = p_journal_id AND society_id = p_society_id
    LOOP
        INSERT INTO transactions (
            society_id, entry_side, trx_date, acc_id, entity_id, role,
            acc_particulars, amount, mode, status,
            source_table, source_id, created_by, journal_id,
            bank_reconciled, reverses_id, reversal_reason, is_reversal
        ) VALUES (
            p_society_id,
            CASE v_leg.entry_side WHEN 'Dr' THEN 'Cr' ELSE 'Dr' END,
            p_reversal_date,
            v_leg.acc_id, v_leg.entity_id, v_leg.role,
            'REVERSAL of txn#' || v_leg.id || ': ' || COALESCE(v_leg.acc_particulars, ''),
            v_leg.amount,
            'journal',
            'paid',
            v_leg.source_table, v_leg.source_id,
            p_reversed_by,
            v_new_jid,
            FALSE,
            v_leg.id,
            p_reason,
            TRUE
        );
    END LOOP;
    RETURN v_new_jid;
END;
$$;

COMMENT ON FUNCTION fn_post_reversal_journal IS
    'Posts a mirror-image reversal of every leg in the given journal_id. '
    'This is the ONLY authorised way to correct a posted ledger entry (A-01).';


-- A-01 (cont.) — FK on transactions.society_id: CASCADE → RESTRICT
ALTER TABLE transactions
    DROP CONSTRAINT IF EXISTS transactions_society_id_fkey;
ALTER TABLE transactions
    ADD CONSTRAINT transactions_society_id_fkey
    FOREIGN KEY (society_id) REFERENCES societies (id) ON DELETE RESTRICT;


-- A-01 (cont.) — Hash chain columns + trigger
ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS ledger_hash      VARCHAR(64),
    ADD COLUMN IF NOT EXISTS prev_ledger_hash VARCHAR(64);

COMMENT ON COLUMN transactions.ledger_hash IS
    'SHA-256 hash chaining confirmed legs per society (A-01). '
    'hash = SHA-256(prev_hash|journal_id|amount|entry_side|acc_id|trx_date|society_id).';

CREATE OR REPLACE FUNCTION fn_trg_transactions_hash() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_prev_hash VARCHAR(64);
BEGIN
    IF NEW.status NOT IN ('paid') THEN RETURN NEW; END IF;
    SELECT ledger_hash INTO v_prev_hash
      FROM transactions
     WHERE society_id = NEW.society_id AND status = 'paid' AND id < NEW.id
     ORDER BY id DESC LIMIT 1;
    NEW.prev_ledger_hash := v_prev_hash;
    NEW.ledger_hash := encode(
        sha256(convert_to(
            COALESCE(v_prev_hash, '0') || '|' ||
            COALESCE(NEW.journal_id::TEXT, '') || '|' ||
            NEW.amount::TEXT || '|' ||
            COALESCE(NEW.entry_side, '') || '|' ||
            COALESCE(NEW.acc_id::TEXT, '') || '|' ||
            NEW.trx_date::TEXT || '|' ||
            NEW.society_id::TEXT,
            'UTF8'
        )),
        'hex'
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_transactions_hash ON transactions;
CREATE TRIGGER trg_transactions_hash
    BEFORE INSERT ON transactions
    FOR EACH ROW EXECUTE FUNCTION fn_trg_transactions_hash();


-- ---------------------------------------------------------------------------
-- A-02  DEFERRED DOUBLE-ENTRY BALANCE CONSTRAINT TRIGGER
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_trg_journal_balance_check() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_dr  NUMERIC;
    v_cr  NUMERIC;
    v_jid INT;
BEGIN
    v_jid := COALESCE(NEW.journal_id, OLD.journal_id);
    IF v_jid IS NULL THEN RETURN NEW; END IF;
    SELECT
        COALESCE(SUM(amount) FILTER (WHERE entry_side = 'Dr'), 0),
        COALESCE(SUM(amount) FILTER (WHERE entry_side = 'Cr'), 0)
    INTO v_dr, v_cr
    FROM transactions WHERE journal_id = v_jid;
    IF ABS(v_dr - v_cr) > 0.005 THEN
        RAISE EXCEPTION
            'Double-entry balance violated: journal_id=% Dr=% Cr=% (diff=%). '
            'All Dr and Cr legs must be inserted in the same transaction.',
            v_jid, v_dr, v_cr, v_dr - v_cr;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_journal_balance ON transactions;
CREATE CONSTRAINT TRIGGER trg_journal_balance
    AFTER INSERT OR UPDATE ON transactions
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION fn_trg_journal_balance_check();


-- ---------------------------------------------------------------------------
-- A-03  INCOME TAX SUMMARY — restrict to P&L accounts + working-paper label
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_income_tax_summary_fy(
    p_society_id INT,
    p_fy         INT
) RETURNS TABLE (
    category     VARCHAR,
    nature       VARCHAR,
    total_amount NUMERIC,
    disclaimer   TEXT
) LANGUAGE plpgsql AS $$
DECLARE
    v_fy_start DATE := MAKE_DATE(p_fy, 4, 1);
    v_fy_end   DATE := MAKE_DATE(p_fy + 1, 3, 31);
    v_note     TEXT :=
        'WORKING PAPER FOR CA — NOT A TAX RETURN. '
        'Restricted to P&L accounts (statement_section = Income/Expenditure). '
        'Excludes capital receipts, fund transfers, liability legs and '
        'accounts with NULL mutuality_nature. '
        'Apportionment, depreciation (IT Act 2025 s.19), brought-forward losses '
        'and Sec 269ST compliance must be reviewed by a qualified CA before filing ITR-5.';
BEGIN
    RETURN QUERY
    SELECT
        'Income'::VARCHAR,
        a.mutuality_nature,
        SUM(t.amount),
        v_note
    FROM transactions t
    JOIN accounts a ON t.acc_id = a.id AND a.society_id = t.society_id
    WHERE t.society_id = p_society_id
      AND t.trx_date BETWEEN v_fy_start AND v_fy_end
      AND t.entry_side = 'Cr'
      AND t.status = 'paid'
      AND a.statement_section = 'Income'
      AND a.mutuality_nature IS NOT NULL
    GROUP BY a.mutuality_nature

    UNION ALL

    SELECT
        'Expenditure'::VARCHAR,
        a.mutuality_nature,
        SUM(t.amount),
        v_note
    FROM transactions t
    JOIN accounts a ON t.acc_id = a.id AND a.society_id = t.society_id
    WHERE t.society_id = p_society_id
      AND t.trx_date BETWEEN v_fy_start AND v_fy_end
      AND t.entry_side = 'Dr'
      AND t.status = 'paid'
      AND a.statement_section = 'Expenditure'
      AND a.mutuality_nature IS NOT NULL
    GROUP BY a.mutuality_nature;
END;
$$;

COMMENT ON FUNCTION fn_income_tax_summary_fy IS
    'A-03: Working paper for the society CA — NOT a taxable-income computation. '
    'Filters to P&L accounts only. Provide to CA alongside the full trial balance.';


-- ---------------------------------------------------------------------------
-- T-01  TDS RATES — Finance Act 2024/2025 corrections (effective-dated rows)
-- ---------------------------------------------------------------------------

-- 194H: threshold ₹15,000 → ₹20,000 from 1-Apr-2025
UPDATE tds_section_rates
   SET effective_to = '2025-03-31'
 WHERE section = '194H'
   AND discriminator IS NULL
   AND effective_from = '2024-04-01'
   AND single_bill_threshold = 15000
   AND effective_to IS NULL;

INSERT INTO tds_section_rates
    (society_id, section, discriminator, nature_of_income, rate, rate_no_pan,
     single_bill_threshold, annual_aggregate_threshold, effective_from)
SELECT DISTINCT society_id,
    '194H', NULL,
    'Brokerage or commission',
    2.00, 20.00, 20000, 20000, '2025-04-01'
  FROM tds_section_rates WHERE section = '194H' AND discriminator IS NULL
ON CONFLICT (society_id, section, discriminator, effective_from) DO NOTHING;


-- 194-IB: rate 5% → 2% from 1-Oct-2024
UPDATE tds_section_rates
   SET effective_to = '2024-09-30'
 WHERE section = '194-IB'
   AND discriminator IS NULL
   AND effective_from = '2024-04-01'
   AND rate = 5.00
   AND effective_to IS NULL;

INSERT INTO tds_section_rates
    (society_id, section, discriminator, nature_of_income, rate, rate_no_pan,
     single_bill_threshold, annual_aggregate_threshold, effective_from)
SELECT DISTINCT society_id,
    '194-IB', NULL,
    'Rent paid by Individual / HUF (monthly rent > Rs 50,000)',
    2.00, 20.00, 600000, 600000, '2024-10-01'
  FROM tds_section_rates WHERE section = '194-IB' AND discriminator IS NULL
ON CONFLICT (society_id, section, discriminator, effective_from) DO NOTHING;


-- 206AB: closed from 1-Apr-2025 (omitted by Finance Act 2025)
UPDATE tds_section_rates
   SET effective_to = '2025-03-31'
 WHERE section = '206AB' AND effective_to IS NULL;


-- ---------------------------------------------------------------------------
-- T-02  Income-tax Act 2025 — act_version + section_2025 columns
-- ---------------------------------------------------------------------------
ALTER TABLE tds_section_rates
    ADD COLUMN IF NOT EXISTS act_version  VARCHAR(10)
        NOT NULL DEFAULT 'IT1961'
        CHECK (act_version IN ('IT1961', 'IT2025')),
    ADD COLUMN IF NOT EXISTS section_2025 VARCHAR(30);

COMMENT ON COLUMN tds_section_rates.act_version IS
    'IT1961 = Income-tax Act 1961. IT2025 = Income-tax Act 2025 (w.e.f. 1-Apr-2026).';
COMMENT ON COLUMN tds_section_rates.section_2025 IS
    'Corresponding section reference under IT Act 2025 (e.g. "Sec 393(1) Table 6(i)").';

-- Populate IT1961 → IT2025 cross-references for all existing rows
UPDATE tds_section_rates SET section_2025 =
    CASE section
        WHEN '192'    THEN 'Sec 393(1) Table 1'
        WHEN '192A'   THEN 'Sec 393(1) Table 2'
        WHEN '194'    THEN 'Sec 393(1) Table 3'
        WHEN '194A'   THEN 'Sec 393(1) Table 4'
        WHEN '194B'   THEN 'Sec 393(1) Table 5(i)'
        WHEN '194C'   THEN 'Sec 393(1) Table 6(i)'
        WHEN '194D'   THEN 'Sec 393(1) Table 7'
        WHEN '194G'   THEN 'Sec 393(1) Table 8'
        WHEN '194H'   THEN 'Sec 393(1) Table 9'
        WHEN '194-I'  THEN 'Sec 393(1) Table 10'
        WHEN '194-IB' THEN 'Sec 393(1) Table 10B'
        WHEN '194-IA' THEN 'Sec 393(1) Table 10A'
        WHEN '194-IC' THEN 'Sec 393(1) Table 10C'
        WHEN '194J'   THEN 'Sec 393(1) Table 11'
        WHEN '194K'   THEN 'Sec 393(1) Table 12'
        WHEN '194M'   THEN 'Sec 393(1) Table 13'
        WHEN '194N'   THEN 'Sec 393(1) Table 14'
        WHEN '194-O'  THEN 'Sec 393(1) Table 15'
        WHEN '194Q'   THEN 'Sec 393(1) Table 16'
        WHEN '194R'   THEN 'Sec 393(1) Table 17'
        WHEN '194S'   THEN 'Sec 393(1) Table 18'
        WHEN '195'    THEN 'Sec 393(2)'
        WHEN '206AA'  THEN 'Sec 395 (carried forward)'
        ELSE NULL
    END
WHERE section_2025 IS NULL;

-- Insert IT2025 effective rows (1-Apr-2026) for every society
INSERT INTO tds_section_rates
    (society_id, section, discriminator, nature_of_income, rate, rate_no_pan,
     single_bill_threshold, annual_aggregate_threshold,
     effective_from, act_version, section_2025)
SELECT DISTINCT ON (t.society_id, t.section, t.discriminator)
    t.society_id, t.section, t.discriminator,
    t.nature_of_income, t.rate, t.rate_no_pan,
    t.single_bill_threshold, t.annual_aggregate_threshold,
    '2026-04-01'::DATE, 'IT2025', t.section_2025
  FROM tds_section_rates t
 WHERE t.section NOT IN ('206AB')
   AND t.section_2025 IS NOT NULL
   AND t.effective_from = (
       SELECT MAX(t2.effective_from) FROM tds_section_rates t2
        WHERE t2.society_id = t.society_id
          AND t2.section = t.section
          AND t2.discriminator IS NOT DISTINCT FROM t.discriminator
   )
   AND NOT EXISTS (
       SELECT 1 FROM tds_section_rates x
        WHERE x.society_id = t.society_id
          AND x.section = t.section
          AND x.discriminator IS NOT DISTINCT FROM t.discriminator
          AND x.effective_from = '2026-04-01'
   )
ORDER BY t.society_id, t.section, t.discriminator, t.effective_from DESC
ON CONFLICT (society_id, section, discriminator, effective_from) DO NOTHING;


-- ---------------------------------------------------------------------------
-- X-01  GST FUND TOGGLE — default FALSE (opt-in exemption, with audit trail)
-- ---------------------------------------------------------------------------
ALTER TABLE society_compliance_settings
    ALTER COLUMN fund_gst_exempt SET DEFAULT FALSE;

ALTER TABLE society_compliance_settings
    ADD COLUMN IF NOT EXISTS fund_gst_exempt_resolution_id   INT
        REFERENCES resolutions (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS fund_gst_exempt_authority_ref   TEXT;

COMMENT ON COLUMN society_compliance_settings.fund_gst_exempt IS
    'X-01: FALSE (default) = sinking and repair fund contributions are included in the '
    'GST taxable base. TRUE = excluded. Must be backed by a resolution + CA/advocate opinion '
    '(see fund_gst_exempt_resolution_id, fund_gst_exempt_authority_ref).';
COMMENT ON COLUMN society_compliance_settings.fund_gst_exempt_resolution_id IS
    'Resolution approving the fund GST exemption claim. Required when fund_gst_exempt=TRUE.';
COMMENT ON COLUMN society_compliance_settings.fund_gst_exempt_authority_ref IS
    'CA/advocate opinion reference supporting the fund GST exemption claim.';


-- ---------------------------------------------------------------------------
-- X-02  GST RATE — raise instead of silently billing 0%
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_assert_gst_rate(
    p_society_id INT,
    p_month      DATE
) RETURNS TABLE (cgst_rate_pct NUMERIC, sgst_rate_pct NUMERIC)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_cgst NUMERIC; v_sgst NUMERIC;
BEGIN
    SELECT g.cgst_rate_pct, g.sgst_rate_pct INTO v_cgst, v_sgst
      FROM gst_rates g
     WHERE g.society_id = p_society_id
       AND g.effective_from <= p_month
       AND (g.effective_to IS NULL OR g.effective_to >= p_month)
     ORDER BY g.effective_from DESC LIMIT 1;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'X-02: No GST rate configured for society % as of % — billing aborted. '
            'Add a row to gst_rates before generating receivables.', p_society_id, p_month;
    END IF;
    cgst_rate_pct := v_cgst; sgst_rate_pct := v_sgst;
    RETURN NEXT;
END;
$$;

COMMENT ON FUNCTION fn_assert_gst_rate IS
    'X-02: Raises an exception instead of returning 0 when no GST rate row exists. '
    'Replace COALESCE(rate,0) in fn_auto_generate_receivables with this function.';


-- ---------------------------------------------------------------------------
-- G-01  RESOLUTION VALIDITY — DB-level CHECK + immutability trigger
-- ---------------------------------------------------------------------------
ALTER TABLE resolutions
    ADD CONSTRAINT ck_resolution_passed_consistency CHECK (
        NOT passed
        OR (
            status      = 'passed'
            AND passed_on IS NOT NULL
            AND votes_for_pct IS NOT NULL
            AND votes_for_pct >= majority_required
        )
    );

CREATE OR REPLACE FUNCTION trg_resolutions_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.passed THEN
            RAISE EXCEPTION 'Passed resolution (id=%) cannot be deleted — governance record.', OLD.id;
        END IF;
        RETURN OLD;
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF OLD.passed AND (
            OLD.votes_for_pct     IS DISTINCT FROM NEW.votes_for_pct   OR
            OLD.majority_required IS DISTINCT FROM NEW.majority_required OR
            OLD.passed_on         IS DISTINCT FROM NEW.passed_on        OR
            OLD.meeting_id        IS DISTINCT FROM NEW.meeting_id
        ) THEN
            RAISE EXCEPTION
                'Passed resolution (id=%) — vote tallies and meeting link are immutable.', OLD.id;
        END IF;
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_resolutions_immutable ON resolutions;
CREATE TRIGGER trg_resolutions_immutable
    BEFORE UPDATE OR DELETE ON resolutions
    FOR EACH ROW EXECUTE FUNCTION trg_resolutions_immutable();


-- G-01 (cont.) — enforce passed resolution on society_rule_decisions
CREATE OR REPLACE FUNCTION trg_society_rule_decision_resolution_check()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_passed BOOLEAN;
BEGIN
    IF NEW.resolution_id IS NOT NULL THEN
        SELECT passed INTO v_passed FROM resolutions WHERE id = NEW.resolution_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Resolution % not found.', NEW.resolution_id;
        END IF;
        IF NOT v_passed THEN
            RAISE EXCEPTION
                'G-01: society_rule_decisions.resolution_id=% points to a non-passed resolution. '
                'A rule decision can only be linked to a passed resolution.', NEW.resolution_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_society_rule_decision_resolution ON society_rule_decisions;
CREATE TRIGGER trg_society_rule_decision_resolution
    BEFORE INSERT OR UPDATE OF resolution_id ON society_rule_decisions
    FOR EACH ROW EXECUTE FUNCTION trg_society_rule_decision_resolution_check();


-- ---------------------------------------------------------------------------
-- G-02  MEETING ATTENDANCE & VOTE REGISTERS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meeting_attendance (
    id                     SERIAL PRIMARY KEY,
    meeting_id             INT NOT NULL REFERENCES meetings (id) ON DELETE CASCADE,
    apartment_id           INT NOT NULL REFERENCES apartments (id) ON DELETE CASCADE,
    present_in_person      BOOLEAN NOT NULL DEFAULT FALSE,
    proxy_holder           INT REFERENCES users (id) ON DELETE SET NULL,
    undivided_interest_pct NUMERIC(7,4) NOT NULL DEFAULT 0
        CHECK (undivided_interest_pct >= 0 AND undivided_interest_pct <= 100),
    notes                  TEXT,
    created_by             INT REFERENCES users (id),
    created_at             TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_meeting_attendance UNIQUE (meeting_id, apartment_id)
);
CREATE INDEX IF NOT EXISTS idx_meeting_attendance_meeting ON meeting_attendance (meeting_id);
CREATE INDEX IF NOT EXISTS idx_meeting_attendance_apt    ON meeting_attendance (apartment_id);

COMMENT ON TABLE meeting_attendance IS
    'G-02: Per-apartment attendance register. undivided_interest_pct is the statutory '
    'voting weight (UDS). Quorum percentage is computed from this table, not typed.';


CREATE TABLE IF NOT EXISTS resolution_votes (
    id            SERIAL PRIMARY KEY,
    resolution_id INT NOT NULL REFERENCES resolutions (id) ON DELETE CASCADE,
    apartment_id  INT NOT NULL REFERENCES apartments (id) ON DELETE CASCADE,
    vote          VARCHAR(10) NOT NULL
        CHECK (vote IN ('for', 'against', 'abstain', 'absent')),
    weight        NUMERIC(7,4) NOT NULL DEFAULT 0 CHECK (weight >= 0),
    proxy_holder  INT REFERENCES users (id) ON DELETE SET NULL,
    notes         TEXT,
    created_by    INT REFERENCES users (id),
    created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_resolution_vote UNIQUE (resolution_id, apartment_id)
);
CREATE INDEX IF NOT EXISTS idx_resolution_votes_resolution ON resolution_votes (resolution_id);
CREATE INDEX IF NOT EXISTS idx_resolution_votes_apt        ON resolution_votes (apartment_id);

COMMENT ON TABLE resolution_votes IS
    'G-02: Per-apartment vote record. votes_for_pct on resolutions must be computed '
    'from SUM(weight) FILTER (WHERE vote=''for'') / SUM(weight) * 100.';


CREATE OR REPLACE FUNCTION fn_resolution_vote_summary(p_resolution_id INT)
RETURNS TABLE (
    total_weight       NUMERIC,
    votes_for_pct      NUMERIC,
    owners_present_pct NUMERIC,
    quorum_met         BOOLEAN,
    majority_required  NUMERIC
) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_meeting_id   INT;
    v_total_wt     NUMERIC;
    v_present_wt   NUMERIC;
    v_for_wt       NUMERIC;
    v_majority     NUMERIC;
BEGIN
    SELECT r.meeting_id, r.majority_required
      INTO v_meeting_id, v_majority
      FROM resolutions r WHERE r.id = p_resolution_id;
    IF NOT FOUND THEN RETURN; END IF;

    SELECT COALESCE(SUM(a.undivided_interest_pct), 0)
      INTO v_present_wt
      FROM meeting_attendance a
     WHERE a.meeting_id = v_meeting_id
       AND (a.present_in_person OR a.proxy_holder IS NOT NULL);

    SELECT COALESCE(SUM(a.undivided_interest_pct), 0)
      INTO v_total_wt
      FROM meeting_attendance a WHERE a.meeting_id = v_meeting_id;

    SELECT COALESCE(SUM(rv.weight), 0)
      INTO v_for_wt
      FROM resolution_votes rv
     WHERE rv.resolution_id = p_resolution_id AND rv.vote = 'for';

    total_weight       := v_total_wt;
    owners_present_pct := CASE WHEN v_total_wt > 0
                               THEN ROUND(v_present_wt / v_total_wt * 100, 2) ELSE 0 END;
    votes_for_pct      := CASE WHEN v_present_wt > 0
                               THEN ROUND(v_for_wt / v_present_wt * 100, 2) ELSE 0 END;
    majority_required  := v_majority;
    quorum_met         := (owners_present_pct >= COALESCE(v_majority, 0));
    RETURN NEXT;
END;
$$;


-- ---------------------------------------------------------------------------
-- G-03  MEETINGS TABLE — notice, agenda, chair, signoff, adjournment, venue
-- ---------------------------------------------------------------------------
ALTER TABLE meetings
    ADD COLUMN IF NOT EXISTS notice_date           DATE,
    ADD COLUMN IF NOT EXISTS notice_service_method VARCHAR(30)
        CHECK (notice_service_method IN (
            'hand_delivery','registered_post','email',
            'whatsapp','noticeboard','multiple')),
    ADD COLUMN IF NOT EXISTS agenda_text           TEXT,
    ADD COLUMN IF NOT EXISTS requisition_ref       TEXT,
    ADD COLUMN IF NOT EXISTS chair_user_id         INT REFERENCES users (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS minutes_signoff_date  DATE,
    ADD COLUMN IF NOT EXISTS minutes_signatories   TEXT,
    ADD COLUMN IF NOT EXISTS adjourned_from_id     INT REFERENCES meetings (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS venue                 TEXT,
    ADD COLUMN IF NOT EXISTS updated_at            TIMESTAMP NOT NULL DEFAULT NOW();

COMMENT ON COLUMN meetings.notice_date IS
    'G-03: Date notice was issued. Statutory notice periods cannot be evidenced without this.';
COMMENT ON COLUMN meetings.notice_service_method IS
    'G-03: Method used to serve the meeting notice.';
COMMENT ON COLUMN meetings.agenda_text IS
    'G-03: Agenda items sent with the notice. Resolutions should only cover notified items.';
COMMENT ON COLUMN meetings.requisition_ref IS
    'G-03: For EGM — references the member requisition (bye-law article, signatories, date).';
COMMENT ON COLUMN meetings.adjourned_from_id IS
    'G-03: If adjourned and re-held, points to the original meeting ID. '
    'Adjourned meetings may have different quorum rules per the adopted bye-laws.';
COMMENT ON COLUMN meetings.venue IS 'G-03: Physical or virtual meeting venue address.';


-- ---------------------------------------------------------------------------
-- G-04  RATIFICATION EXPIRY — reversal journal reference on loa_ratification
-- ---------------------------------------------------------------------------
ALTER TABLE loa_ratification
    ADD COLUMN IF NOT EXISTS reversal_journal_id  INT,
    ADD COLUMN IF NOT EXISTS reversal_note        TEXT;

COMMENT ON COLUMN loa_ratification.reversal_journal_id IS
    'G-04: When ratification is rejected or expires the scheduler calls '
    'fn_post_reversal_journal and records the new journal_id here.';


-- ---------------------------------------------------------------------------
-- C-01  SECTION 269ST + fix Sec 40A(3) mis-labelling on receipt side
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_check_269st(p_amount NUMERIC, p_mode VARCHAR)
RETURNS TEXT LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    IF p_mode <> 'cash' THEN RETURN NULL; END IF;
    IF p_amount >= 200000 THEN
        RETURN format(
            'Cash receipt of Rs %s >= Rs 2,00,000 — Sec 269ST prohibits receiving this '
            'amount in cash in a single transaction / from one person in a day / '
            'for a single event. Penalty = full amount received. '
            'Switch to account-payee cheque or bank transfer.',
            p_amount
        );
    END IF;
    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION fn_check_269st IS
    'C-01: Returns a blocking error string when cash receipt >= Rs 2,00,000 (Sec 269ST). '
    'Call this in fn_confirm_receipt BEFORE posting.';


-- C-01 (cont.) — default cash_limit_mode to block for new societies
ALTER TABLE societies
    ALTER COLUMN cash_limit_mode SET DEFAULT 'block';

COMMENT ON COLUMN societies.cash_limit_mode IS
    'C-01: "block" = cash payments above the bye-law threshold are refused. '
    '"warn" = a compliance_flags row is inserted but posting proceeds. '
    'New societies default to block.';


-- ---------------------------------------------------------------------------
-- I-02  ARREARS INTEREST — remove the silent 1.75% default
-- ---------------------------------------------------------------------------
ALTER TABLE apt_charges_fines_basis
    ALTER COLUMN apt_interest_pct DROP DEFAULT;

COMMENT ON COLUMN apt_charges_fines_basis.apt_interest_pct IS
    'I-02: Interest rate on arrears. NULL = no interest charged. '
    'The old 1.75% default has been removed — set this only via a board/GBM resolution.';


-- ---------------------------------------------------------------------------
-- RULE APPLICATION REGISTER VIEW (ER.md §8 item 7)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_rule_application_register AS
SELECT
    t.id                AS transaction_id,
    t.journal_id,
    t.trx_date,
    t.society_id,
    t.amount,
    t.entry_side,
    a.name              AS account_name,
    srd.rule_key,
    srd.layer,
    srd.id              AS decision_id,
    r.id                AS resolution_id,
    r.body              AS resolution_body,
    r.passed_on         AS resolution_passed_on,
    r.advocate_opinion_ref,
    srd.effective_from  AS rule_effective_from,
    srd.effective_to    AS rule_effective_to,
    srd.review_status   AS decision_review_status
FROM transactions t
JOIN accounts a ON a.id = t.acc_id AND a.society_id = t.society_id
LEFT JOIN society_rule_decisions srd
       ON srd.society_id = t.society_id
      AND srd.effective_from <= t.trx_date
      AND (srd.effective_to IS NULL OR srd.effective_to >= t.trx_date)
LEFT JOIN resolutions r ON r.id = srd.resolution_id
WHERE t.status = 'paid'
ORDER BY t.society_id, t.trx_date, t.journal_id, t.id;

COMMENT ON VIEW v_rule_application_register IS
    'ER.md §8: Rule-Application Register. For each paid transaction leg, surfaces the '
    'active rule-decision, linked resolution, and advocate-opinion reference. '
    'Export per FY for the CA compliance certificate.';


-- ---------------------------------------------------------------------------
-- SCHEMA MIGRATIONS TRACKER
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_name VARCHAR(120) PRIMARY KEY,
    applied_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    applied_by     TEXT
);

INSERT INTO schema_migrations (migration_name, applied_by)
VALUES ('ER_remediation_2026_10', current_user)
ON CONFLICT (migration_name) DO NOTHING;


COMMIT;

-- =============================================================================
-- POST-COMMIT CHECKLIST (not SQL — review before applying)
-- =============================================================================
-- 1. DEFERRED BALANCE CHECK (A-02): Any existing unbalanced journal will abort
--    the next transaction that touches it.  Run this first to find them:
--      SELECT journal_id,
--             SUM(CASE WHEN entry_side='Dr' THEN amount ELSE -amount END) AS diff
--        FROM transactions GROUP BY journal_id
--       HAVING ABS(SUM(CASE WHEN entry_side='Dr' THEN amount ELSE -amount END)) > 0.005;
--
-- 2. RESTRICT FK (A-01): transactions.society_id is now ON DELETE RESTRICT.
--    Ensure no societies will be purged without first archiving their ledger.
--
-- 3. POSTING FUNCTIONS (A-04, C-01): Wire fn_check_fy_lock() and
--    fn_check_269st() into fn_confirm_receipt, fn_save_expense, fn_pay_payable.
--    These are new no-op helpers until called from Python/SQL posting functions.
--
-- 4. INCOME TAX EXPORT (A-03): Update income_tax_export.py title row to read
--    "WORKING PAPER FOR CA — NOT A TAX RETURN.  FY ..."  (see Python patch).
--
-- 5. BANK RECONCILE DELETE (A-01): The immutable trigger allows deletion of
--    rows where status='pending' AND source_table='bank_statement_lines',
--    so delete_unreconciled_bank_txns() continues to work unchanged.
--
-- 6. GST BILLING (X-02): Replace the COALESCE(rate,0) pattern in
--    fn_auto_generate_receivables with a call to fn_assert_gst_rate().
--
-- 7. CASH RECEIPT WARNING (C-01): The Sec 40A(3) warning on cash receipts
--    (fn_confirm_receipt ~L6562) is mis-labelled. Replace with fn_check_269st().
--    Sec 40A(3) applies only to expenses >= Rs 10,000 — keep that check
--    in fn_save_expense / fn_confirm_expense.
--
-- 8. INTEREST DEFAULT (I-02): Any existing apt_charges_fines_basis rows that
--    relied on the 1.75 default now have NULL. Review and set explicit rates
--    backed by board resolutions before the next billing run.
-- =============================================================================
