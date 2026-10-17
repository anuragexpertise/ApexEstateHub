-- =============================================================================
-- EstateHub — ER.md remediation, PHASE 1: ledger integrity
-- Migration: ER_phase1_ledger_integrity_2026_10
-- Covers:    A-01 (immutable ledger), A-02 (preventive double-entry),
--            A-04 (financial-year period locks)
--
-- HOW TO APPLY (one transaction; safe to re-run — every object is guarded):
--     psql -1 -v ON_ERROR_STOP=1 -f database/upgrades/ER_phase1_ledger_integrity_2026_10.sql
--   or let database/migrate.py / database/reset_database.py apply it after
--   estatehub.sql (they run the whole file as one transaction).
--   This file deliberately has no BEGIN/COMMIT of its own.
--
-- DESIGN NOTES (read before changing anything)
--
-- 1. Cash vouchers are single-sided BY DESIGN. fn_resolve_bank_leg returns NULL
--    for mode 'cash', and Cash-in-Hand is derived implicitly from cash-mode
--    legs — it is never posted. A plain "SUM(Dr) = SUM(Cr)" rule would reject
--    every cash receipt and expense. A-02 therefore requires exact balance for
--    every journal EXCEPT one whose legs are ALL mode='cash', where the missing
--    contra leg is the implicit Cash-in-Hand. Limitation: such a journal can
--    only be checked for shape, not amount — making Cash-in-Hand an explicit
--    leg is the real fix, and is out of scope for this phase.
--
-- 2. Reversals preserve each leg's mode. A reversed cash voucher must stay
--    cash so the implicit Cash-in-Hand contra reverses with it, and a reversed
--    bank voucher must stay bank so the bank account's own ledger shows it.
--
-- 3. The hash chain is TAMPER-EVIDENT, not tamper-proof: a database owner can
--    still disable triggers and rewrite history. What the chain gives an
--    auditor is that any such rewrite is DETECTABLE (fn_verify_ledger_chain).
--
-- 4. Statutory references used in comments, checked against the Income-tax
--    Department's text of the Income-tax Act, 2025 (in force from 1-Apr-2026):
--      s.33  deduction for depreciation          (was s.32, Act of 1961)
--      s.186 mode of receiving Rs 2,00,000+       (was s.269ST, Act of 1961)
--      s.393 tax deducted at source (residents/non-residents/any person)
--      s.392 TDS on salary
--    Nothing in Phase 1 computes tax; these are cited so the Phase 2 work
--    (TDS tables, cash-receipt rule) starts from the correct section numbers.
-- =============================================================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_name VARCHAR(120) PRIMARY KEY,
    applied_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    applied_by     TEXT
);


-- ---------------------------------------------------------------------------
-- A-04  FINANCIAL-YEAR PERIOD LOCKS
-- ---------------------------------------------------------------------------
-- locked_through is the START year of the last locked FY (same convention as
-- fy_closures.financial_year: 2025 = 1-Apr-2025 .. 31-Mar-2026). Locking FY n
-- locks every FY up to and including n.

CREATE TABLE IF NOT EXISTS fy_locks (
    id             SERIAL PRIMARY KEY,
    society_id     INT NOT NULL REFERENCES societies (id) ON DELETE RESTRICT,
    locked_through SMALLINT NOT NULL CHECK (locked_through BETWEEN 2000 AND 2200),
    locked_by      INT REFERENCES users (id),
    resolution_id  INT REFERENCES resolutions (id),
    notes          TEXT,
    locked_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_fy_lock UNIQUE (society_id, locked_through)
);
CREATE INDEX IF NOT EXISTS idx_fy_locks_society
    ON fy_locks (society_id, locked_through DESC);

COMMENT ON TABLE fy_locks IS
    'A-04: append-only period locks. A row means no ledger line may be dated in '
    'that FY or any earlier one; correct a locked year with a reversal dated in '
    'an open period. Rows cannot be updated or deleted (trg_fy_locks_append_only).';

CREATE OR REPLACE FUNCTION trg_fy_locks_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'fy_locks is append-only (attempted % on lock id=%). A period lock can '
        'only be lifted by a database administrator, deliberately.', TG_OP, OLD.id
        USING ERRCODE = 'restrict_violation';
END;
$$;

DROP TRIGGER IF EXISTS trg_fy_locks_append_only ON fy_locks;
CREATE TRIGGER trg_fy_locks_append_only
    BEFORE UPDATE OR DELETE ON fy_locks
    FOR EACH ROW EXECUTE FUNCTION trg_fy_locks_append_only();


-- FY start-year of a date (Indian FY: 1 April - 31 March).
CREATE OR REPLACE FUNCTION fn_fy_of(p_date DATE) RETURNS INT
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN EXTRACT(MONTH FROM p_date) >= 4
                THEN EXTRACT(YEAR FROM p_date)::INT
                ELSE EXTRACT(YEAR FROM p_date)::INT - 1 END;
$$;


-- NULL when the date is open; otherwise a human-readable refusal.
CREATE OR REPLACE FUNCTION fn_check_fy_lock(p_society_id INT, p_trx_date DATE)
RETURNS TEXT LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_locked INT;
    v_fy     INT := fn_fy_of(p_trx_date);
BEGIN
    SELECT MAX(locked_through) INTO v_locked
      FROM fy_locks WHERE society_id = p_society_id;
    IF v_locked IS NOT NULL AND v_fy <= v_locked THEN
        RETURN format(
            'Posting date %s falls in FY %s-%s, which is locked (locked through FY %s-%s). '
            'Post a reversal or adjustment dated in an open period instead.',
            p_trx_date, v_fy, v_fy + 1, v_locked, v_locked + 1);
    END IF;
    RETURN NULL;
END;
$$;


-- Preventive: enforced in the database, so no posting function can forget it.
CREATE OR REPLACE FUNCTION trg_transactions_fy_lock() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_msg TEXT;
BEGIN
    v_msg := fn_check_fy_lock(NEW.society_id, NEW.trx_date);
    IF v_msg IS NOT NULL THEN
        RAISE EXCEPTION '%', v_msg USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_transactions_fy_lock ON transactions;
CREATE TRIGGER trg_transactions_fy_lock
    BEFORE INSERT ON transactions
    FOR EACH ROW EXECUTE FUNCTION trg_transactions_fy_lock();


-- ---------------------------------------------------------------------------
-- A-01  LEDGER STRUCTURE: reversal linkage, hash chain, constraints
-- ---------------------------------------------------------------------------
ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS reverses_id       INT REFERENCES transactions (id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS reversal_reason   TEXT,
    ADD COLUMN IF NOT EXISTS is_reversal       BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS ledger_seq        BIGINT,
    ADD COLUMN IF NOT EXISTS ledger_hash       VARCHAR(64),
    ADD COLUMN IF NOT EXISTS prev_ledger_hash  VARCHAR(64);

COMMENT ON COLUMN transactions.reverses_id IS
    'A-01: on a reversal leg, the original leg it cancels. At most one reversal per leg (uq_transactions_one_reversal_per_leg).';
COMMENT ON COLUMN transactions.ledger_seq IS
    'A-01: position in the society''s hash chain (1,2,3...). Gaps mean a row was removed.';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_transactions_reversal_shape') THEN
        ALTER TABLE transactions ADD CONSTRAINT ck_transactions_reversal_shape CHECK (
            (is_reversal = FALSE AND reverses_id IS NULL)
            OR (is_reversal = TRUE AND reverses_id IS NOT NULL
                AND NULLIF(BTRIM(reversal_reason), '') IS NOT NULL));
    END IF;
    -- entry_side was unconstrained: a NULL side silently fell out of every
    -- Dr/Cr sum, which would also defeat the balance check below.
    -- (A CHECK passes on NULL, so NOT NULL has to be stated explicitly.)
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS ck_transactions_entry_side;
    ALTER TABLE transactions ADD CONSTRAINT ck_transactions_entry_side
        CHECK (entry_side IS NOT NULL AND entry_side IN ('Dr', 'Cr')) NOT VALID;
    BEGIN
        ALTER TABLE transactions VALIDATE CONSTRAINT ck_transactions_entry_side;
    EXCEPTION WHEN check_violation THEN
        RAISE WARNING 'ck_transactions_entry_side enforced for new rows only: existing rows with a NULL/invalid entry_side need correcting, then run VALIDATE CONSTRAINT.';
    END;
END;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_transactions_one_reversal_per_leg
    ON transactions (reverses_id) WHERE reverses_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_transactions_ledger_seq
    ON transactions (society_id, ledger_seq) WHERE ledger_seq IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_transactions_source
    ON transactions (source_table, source_id);

-- A ledger must outlive the society record it hangs off: deleting a society
-- used to cascade-delete its entire ledger.
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_society_id_fkey;
ALTER TABLE transactions
    ADD CONSTRAINT transactions_society_id_fkey
    FOREIGN KEY (society_id) REFERENCES societies (id) ON DELETE RESTRICT;


-- ---------------------------------------------------------------------------
-- A-01  HASH CHAIN
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_ledger_row_hash(
    p_prev TEXT, p_society INT, p_seq BIGINT, p_journal INT,
    p_side TEXT, p_acc INT, p_amount NUMERIC, p_date DATE
) RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
    SELECT encode(sha256(convert_to(
        COALESCE(p_prev, '0') || '|' || p_society::TEXT || '|' || p_seq::TEXT || '|' ||
        COALESCE(p_journal::TEXT, '') || '|' || COALESCE(p_side, '') || '|' ||
        COALESCE(p_acc::TEXT, '') || '|' || p_amount::NUMERIC(15,2)::TEXT || '|' ||
        p_date::TEXT, 'UTF8')), 'hex');
$$;

-- Serialised per society with an advisory lock, and chained on ledger_seq
-- rather than on id: two concurrent postings otherwise both pick the same
-- predecessor and fork the chain.
CREATE OR REPLACE FUNCTION trg_transactions_ledger_chain() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_prev_seq  BIGINT;
    v_prev_hash VARCHAR(64);
BEGIN
    PERFORM pg_advisory_xact_lock(1818, NEW.society_id);
    SELECT ledger_seq, ledger_hash INTO v_prev_seq, v_prev_hash
      FROM transactions
     WHERE society_id = NEW.society_id AND ledger_seq IS NOT NULL
     ORDER BY ledger_seq DESC LIMIT 1;
    NEW.ledger_seq       := COALESCE(v_prev_seq, 0) + 1;
    NEW.prev_ledger_hash := v_prev_hash;
    NEW.ledger_hash      := fn_ledger_row_hash(
        v_prev_hash, NEW.society_id, NEW.ledger_seq, NEW.journal_id,
        NEW.entry_side, NEW.acc_id, NEW.amount, NEW.trx_date);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_transactions_ledger_chain ON transactions;
CREATE TRIGGER trg_transactions_ledger_chain
    BEFORE INSERT ON transactions
    FOR EACH ROW EXECUTE FUNCTION trg_transactions_ledger_chain();


-- Rebuilds (or first-time backfills) the chain in id order. Not a routine
-- operation: without p_force it only chains societies that have no chain yet,
-- so it cannot be used to quietly re-sign a ledger that has been altered.
CREATE OR REPLACE FUNCTION fn_rebuild_ledger_chain(
    p_society_id INT DEFAULT NULL,
    p_force      BOOLEAN DEFAULT FALSE
) RETURNS BIGINT LANGUAGE plpgsql AS $$
DECLARE
    v_soc  INT;
    v_prev TEXT;
    v_seq  BIGINT;
    v_n    BIGINT := 0;
    r      RECORD;
BEGIN
    PERFORM set_config('estatehub.chain_rebuild', 'on', TRUE);
    FOR v_soc IN
        SELECT DISTINCT society_id FROM transactions
         WHERE (p_society_id IS NULL OR society_id = p_society_id)
         ORDER BY 1
    LOOP
        PERFORM pg_advisory_xact_lock(1818, v_soc);
        IF NOT p_force AND EXISTS (
            SELECT 1 FROM transactions WHERE society_id = v_soc AND ledger_seq IS NOT NULL) THEN
            RAISE NOTICE 'society %: chain already exists; skipped (pass p_force => TRUE to rebuild).', v_soc;
            CONTINUE;
        END IF;
        v_prev := NULL; v_seq := 0;
        FOR r IN SELECT id, journal_id, entry_side, acc_id, amount, trx_date
                   FROM transactions WHERE society_id = v_soc ORDER BY id
        LOOP
            v_seq := v_seq + 1;
            v_prev := fn_ledger_row_hash(v_prev, v_soc, v_seq, r.journal_id,
                                         r.entry_side, r.acc_id, r.amount, r.trx_date);
            UPDATE transactions
               SET ledger_seq = v_seq, ledger_hash = v_prev,
                   prev_ledger_hash = CASE WHEN v_seq = 1 THEN NULL
                        ELSE (SELECT t2.ledger_hash FROM transactions t2
                               WHERE t2.society_id = v_soc AND t2.ledger_seq = v_seq - 1) END
             WHERE id = r.id;
            v_n := v_n + 1;
        END LOOP;
    END LOOP;
    PERFORM set_config('estatehub.chain_rebuild', 'off', TRUE);
    RETURN v_n;
END;
$$;

-- Empty result = the chain is intact.
CREATE OR REPLACE FUNCTION fn_verify_ledger_chain(p_society_id INT DEFAULT NULL)
RETURNS TABLE (society_id INT, ledger_seq BIGINT, transaction_id INT, problem TEXT)
LANGUAGE sql STABLE AS $$
    WITH c AS (
        SELECT t.id, t.society_id AS soc, t.ledger_seq AS seq, t.ledger_hash AS h,
               t.prev_ledger_hash AS ph, t.journal_id, t.entry_side, t.acc_id,
               t.amount, t.trx_date,
               LAG(t.ledger_hash) OVER w AS lag_h,
               LAG(t.ledger_seq)  OVER w AS lag_seq
          FROM transactions t
         WHERE t.ledger_seq IS NOT NULL
           AND (p_society_id IS NULL OR t.society_id = p_society_id)
        WINDOW w AS (PARTITION BY t.society_id ORDER BY t.ledger_seq)
    )
    SELECT soc, seq, id, 'row content does not match its hash (altered after posting)'
      FROM c WHERE h IS DISTINCT FROM
           fn_ledger_row_hash(ph, soc, seq, journal_id, entry_side, acc_id, amount, trx_date)
    UNION ALL
    SELECT soc, seq, id, 'link to previous row broken (earlier row altered or removed)'
      FROM c WHERE ph IS DISTINCT FROM lag_h
    UNION ALL
    SELECT soc, seq, id, 'sequence gap (a row was removed)'
      FROM c WHERE seq <> COALESCE(lag_seq, 0) + 1
    UNION ALL
    SELECT t.society_id, NULL::BIGINT, t.id, 'row is not in the chain'
      FROM transactions t
     WHERE t.ledger_seq IS NULL
       AND (p_society_id IS NULL OR t.society_id = p_society_id)
    ORDER BY 1, 2 NULLS LAST, 3;
$$;


-- ---------------------------------------------------------------------------
-- A-01  IMMUTABILITY of posted ledger lines
-- ---------------------------------------------------------------------------
-- Allow-list, not block-list: only these columns may change after posting.
-- Everything else (amount, side, account, date, journal, mode, source, status,
-- entity, particulars, creator ...) is frozen. The chain columns are writable
-- only inside fn_rebuild_ledger_chain.
CREATE OR REPLACE FUNCTION trg_transactions_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_mutable TEXT[] := ARRAY['bank_reconciled', 'bank_line_id'];
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'transactions is append-only: line id=% (journal %) cannot be deleted. '
            'Correct it with fn_post_reversal_journal().', OLD.id, OLD.journal_id
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF current_setting('estatehub.chain_rebuild', TRUE) = 'on' THEN
        v_mutable := v_mutable || ARRAY['ledger_seq', 'ledger_hash', 'prev_ledger_hash'];
    END IF;
    IF (to_jsonb(NEW) - v_mutable) IS DISTINCT FROM (to_jsonb(OLD) - v_mutable) THEN
        RAISE EXCEPTION
            'transactions line id=% (journal %) is frozen after posting; only % may change. '
            'Correct it with fn_post_reversal_journal().', OLD.id, OLD.journal_id, v_mutable
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_transactions_immutable ON transactions;
CREATE TRIGGER trg_transactions_immutable
    BEFORE UPDATE OR DELETE ON transactions
    FOR EACH ROW EXECUTE FUNCTION trg_transactions_immutable();


-- ---------------------------------------------------------------------------
-- A-01  REVERSAL — the only way to correct a posted journal
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_post_reversal_journal(
    p_society_id    INT,
    p_journal_id    INT,
    p_reason        TEXT,
    p_reversed_by   INT,
    p_reversal_date DATE DEFAULT CURRENT_DATE
) RETURNS INT LANGUAGE plpgsql AS $$
DECLARE
    v_new_jid INT;
    v_leg     RECORD;
    v_count   INT;
    v_maxdate DATE;
    v_already INT;
BEGIN
    IF NULLIF(BTRIM(p_reason), '') IS NULL THEN
        RAISE EXCEPTION 'fn_post_reversal_journal: a reason is required.';
    END IF;
    PERFORM pg_advisory_xact_lock(1819, p_journal_id);

    SELECT COUNT(*), MAX(trx_date) INTO v_count, v_maxdate
      FROM transactions WHERE journal_id = p_journal_id AND society_id = p_society_id;
    IF v_count = 0 THEN
        RAISE EXCEPTION 'Journal % not found for society %.', p_journal_id, p_society_id;
    END IF;
    IF p_reversal_date < v_maxdate THEN
        RAISE EXCEPTION 'Reversal date % is earlier than the journal''s own date %.',
            p_reversal_date, v_maxdate;
    END IF;

    SELECT r.journal_id INTO v_already
      FROM transactions r JOIN transactions o ON o.id = r.reverses_id
     WHERE o.journal_id = p_journal_id AND o.society_id = p_society_id LIMIT 1;
    IF FOUND THEN
        RAISE EXCEPTION 'Journal % has already been reversed (by journal %).', p_journal_id, v_already;
    END IF;

    -- The period-lock trigger would refuse this too; checking here gives the
    -- caller the message before any row is written.
    IF fn_check_fy_lock(p_society_id, p_reversal_date) IS NOT NULL THEN
        RAISE EXCEPTION '%', fn_check_fy_lock(p_society_id, p_reversal_date);
    END IF;

    v_new_jid := NEXTVAL('seq_transaction_number');
    FOR v_leg IN
        SELECT * FROM transactions
         WHERE journal_id = p_journal_id AND society_id = p_society_id ORDER BY id
    LOOP
        INSERT INTO transactions (
            society_id, entry_side, trx_date, acc_id, entity_id, role,
            acc_particulars, amount, mode, status, source_table, source_id,
            created_by, journal_id, bank_reconciled,
            reverses_id, reversal_reason, is_reversal
        ) VALUES (
            p_society_id,
            CASE v_leg.entry_side WHEN 'Dr' THEN 'Cr' ELSE 'Dr' END,
            p_reversal_date, v_leg.acc_id, v_leg.entity_id, v_leg.role,
            LEFT('REVERSAL of txn#' || v_leg.id || ': ' || COALESCE(v_leg.acc_particulars, ''), 200),
            v_leg.amount,
            v_leg.mode,                 -- preserved: see design note 2
            'paid', v_leg.source_table, v_leg.source_id,
            p_reversed_by, v_new_jid, v_leg.bank_reconciled,
            v_leg.id, p_reason, TRUE
        );
    END LOOP;
    RETURN v_new_jid;
END;
$$;

COMMENT ON FUNCTION fn_post_reversal_journal(INT, INT, TEXT, INT, DATE) IS
    'The ONLY authorised way to correct a posted ledger journal (A-01). Posts a '
    'mirror-image journal dated p_reversal_date (default today, so it lands in an '
    'open period), keeps each leg''s mode, and refuses a second reversal.';


-- ---------------------------------------------------------------------------
-- A-02  PREVENTIVE DOUBLE-ENTRY
-- ---------------------------------------------------------------------------
-- NULL = the journal is acceptable; otherwise the reason it is not.
CREATE OR REPLACE FUNCTION fn_journal_balance_problem(p_society_id INT, p_journal_id INT)
RETURNS TEXT LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_dr NUMERIC; v_cr NUMERIC; v_all_cash BOOLEAN;
BEGIN
    SELECT COALESCE(SUM(amount) FILTER (WHERE entry_side = 'Dr'), 0),
           COALESCE(SUM(amount) FILTER (WHERE entry_side = 'Cr'), 0),
           COALESCE(BOOL_AND(mode = 'cash'), FALSE)
      INTO v_dr, v_cr, v_all_cash
      FROM transactions WHERE society_id = p_society_id AND journal_id = p_journal_id;
    IF v_dr = v_cr THEN RETURN NULL; END IF;
    IF v_all_cash THEN RETURN NULL; END IF;     -- implicit Cash-in-Hand contra
    RETURN format('journal %s is out of balance: Dr %s, Cr %s (difference %s)',
                  p_journal_id, v_dr, v_cr, v_dr - v_cr);
END;
$$;

CREATE OR REPLACE FUNCTION trg_transactions_balance() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_problem TEXT;
BEGIN
    IF NEW.journal_id IS NULL THEN
        RAISE EXCEPTION 'ledger line id=% has no journal_id, so its balance cannot be verified', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    v_problem := fn_journal_balance_problem(NEW.society_id, NEW.journal_id);
    IF v_problem IS NOT NULL THEN
        RAISE EXCEPTION 'Double-entry violated: %. Post all legs of a voucher in one transaction, '
                        'with Dr = Cr (only all-cash vouchers may omit the Cash-in-Hand leg).', v_problem
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_transactions_balance ON transactions;
CREATE CONSTRAINT TRIGGER trg_transactions_balance
    AFTER INSERT ON transactions
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION trg_transactions_balance();

-- Existing data is not re-checked by the trigger (it fires on new rows). This
-- lists journals that are out of balance today, for correction by reversal.
CREATE OR REPLACE FUNCTION fn_ledger_integrity_report(p_society_id INT DEFAULT NULL)
RETURNS TABLE (society_id INT, journal_id INT, legs BIGINT, dr NUMERIC, cr NUMERIC, problem TEXT)
LANGUAGE sql STABLE AS $$
    SELECT t.society_id, t.journal_id, COUNT(*),
           SUM(t.amount) FILTER (WHERE t.entry_side = 'Dr'),
           SUM(t.amount) FILTER (WHERE t.entry_side = 'Cr'),
           fn_journal_balance_problem(t.society_id, t.journal_id)
      FROM transactions t
     WHERE t.journal_id IS NOT NULL AND (p_society_id IS NULL OR t.society_id = p_society_id)
     GROUP BY t.society_id, t.journal_id
    HAVING fn_journal_balance_problem(t.society_id, t.journal_id) IS NOT NULL
     ORDER BY 1, 2;
$$;


-- ---------------------------------------------------------------------------
-- A-04  fn_lock_fy — the supported way to close a year
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_lock_fy(
    p_society_id    INT,
    p_fy            INT,
    p_locked_by     INT,
    p_resolution_id INT  DEFAULT NULL,
    p_notes         TEXT DEFAULT NULL
) RETURNS INT LANGUAGE plpgsql AS $$
DECLARE
    v_id INT; v_bad INT;
BEGIN
    IF MAKE_DATE(p_fy + 1, 3, 31) >= CURRENT_DATE THEN
        RAISE EXCEPTION 'FY %-% has not ended yet (it ends 31-Mar-%); it cannot be locked.',
            p_fy, p_fy + 1, p_fy + 1;
    END IF;
    SELECT COUNT(*) INTO v_bad FROM fn_ledger_integrity_report(p_society_id) r
     WHERE EXISTS (SELECT 1 FROM transactions t
                    WHERE t.society_id = r.society_id AND t.journal_id = r.journal_id
                      AND fn_fy_of(t.trx_date) <= p_fy);
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'Cannot lock FY %-%: % journal(s) dated up to that year are out of balance. '
                        'See fn_ledger_integrity_report(%).', p_fy, p_fy + 1, v_bad, p_society_id;
    END IF;
    IF p_resolution_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM resolutions WHERE id = p_resolution_id AND passed) THEN
        RAISE EXCEPTION 'Resolution % is not a passed resolution.', p_resolution_id;
    END IF;
    INSERT INTO fy_locks (society_id, locked_through, locked_by, resolution_id, notes)
    VALUES (p_society_id, p_fy, p_locked_by, p_resolution_id, p_notes)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;


-- ---------------------------------------------------------------------------
-- A-01  SOURCE DOCUMENTS: receipts and expenses
-- ---------------------------------------------------------------------------
-- Once a receipt/expense has ledger postings it may not be deleted, and its
-- money fields are frozen. Cancelling it now reverses its postings (before,
-- the UI flipped status to 'cancelled' and left the income/expense in the
-- books). Receivables/payables are NOT covered here: a part-paid receivable
-- shares source_id with its payment journals, so "cancel = reverse all" would
-- be wrong for them and needs its own design.
CREATE OR REPLACE FUNCTION trg_source_doc_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_frozen TEXT[];
    v_jid    INT;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM transactions
                    WHERE source_table = TG_TABLE_NAME AND source_id = OLD.id) THEN
        RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;     -- never posted
    END IF;

    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION '% id=% has ledger postings and cannot be deleted; cancel it instead '
                        '(which posts a reversal).', TG_TABLE_NAME, OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;

    v_frozen := ARRAY['amount', 'acc_id', 'society_id', 'entity_id', 'role',
                      CASE TG_TABLE_NAME WHEN 'receipts' THEN 'receipt_date' ELSE 'expense_date' END];
    IF (SELECT jsonb_object_agg(k, to_jsonb(NEW) -> k) FROM unnest(v_frozen) AS k)
       IS DISTINCT FROM
       (SELECT jsonb_object_agg(k, to_jsonb(OLD) -> k) FROM unnest(v_frozen) AS k) THEN
        RAISE EXCEPTION '% id=% is posted to the ledger; % are frozen. Cancel it (posts a reversal) '
                        'and enter a corrected one.', TG_TABLE_NAME, OLD.id, v_frozen
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF NEW.status = 'cancelled' AND OLD.status IS DISTINCT FROM 'cancelled' THEN
        FOR v_jid IN
            SELECT DISTINCT t.journal_id FROM transactions t
             WHERE t.source_table = TG_TABLE_NAME AND t.source_id = OLD.id
               AND NOT t.is_reversal
               AND NOT EXISTS (SELECT 1 FROM transactions r WHERE r.reverses_id = t.id)
        LOOP
            PERFORM fn_post_reversal_journal(
                OLD.society_id, v_jid,
                format('%s #%s cancelled', TG_TABLE_NAME, OLD.id), NULL);
        END LOOP;
    ELSIF OLD.status = 'confirmed' AND NEW.status IS DISTINCT FROM 'confirmed' THEN
        RAISE EXCEPTION '% id=% is confirmed and posted; it can only move to cancelled.',
            TG_TABLE_NAME, OLD.id USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_receipts_source_guard ON receipts;
CREATE TRIGGER trg_receipts_source_guard
    BEFORE UPDATE OR DELETE ON receipts
    FOR EACH ROW EXECUTE FUNCTION trg_source_doc_guard();

DROP TRIGGER IF EXISTS trg_expenses_source_guard ON expenses;
CREATE TRIGGER trg_expenses_source_guard
    BEFORE UPDATE OR DELETE ON expenses
    FOR EACH ROW EXECUTE FUNCTION trg_source_doc_guard();


-- ---------------------------------------------------------------------------
-- Backfill the hash chain for ledgers that predate this migration, and report
-- anything already out of balance. Both are informational: nothing here fails.
-- ---------------------------------------------------------------------------
DO $$
DECLARE v_n BIGINT; v_bad BIGINT;
BEGIN
    v_n := fn_rebuild_ledger_chain(NULL, FALSE);
    SELECT COUNT(*) INTO v_bad FROM fn_ledger_integrity_report(NULL);
    RAISE NOTICE 'ER phase 1: % ledger line(s) chained; % journal(s) currently out of balance (see fn_ledger_integrity_report()).', v_n, v_bad;
END;
$$;

INSERT INTO schema_migrations (migration_name, applied_by)
VALUES ('ER_phase1_ledger_integrity_2026_10', current_user)
ON CONFLICT (migration_name) DO NOTHING;
