-- ICAI5 C1: reverse depreciation debits that landed on fund accounts.
--
-- Cause: fn_resolve_depreciation_account() used `name ILIKE 'Depreciation%'
-- LIMIT 1` with no ORDER BY, which could match "Depreciation Fund" (3280,
-- tab DepFund) instead of the Depreciation expense account (5110, tab Dep)
-- and post depreciation as a debit to the fund.
--
-- Fix (already applied to database/estatehub.sql): resolve by tab_name='Dep'
-- with ORDER BY id LIMIT 1 so depreciation always debits account 5110.
--
-- This migration corrects existing societies append-only style: for every
-- depreciation debit on a fund account it posts a reversal journal
-- (Cr fund / Dr Depreciation expense) whose legs point at the original leg
-- via reverses_id. No existing row is updated or deleted.
--
-- Idempotent: safe to run more than once; a second run finds no unreversed
-- bad legs (reversals already carry reverses_id to a depreciation fund leg)
-- and does nothing.
--
-- NOTE: verify on a scratch database before running against a live society.
-- Requires an admin user per society to stamp created_by; societies with no
-- admin user are skipped and reported.
DO $$
DECLARE
    bad RECORD;
    dep_acc INT;
    admin_user INT;
    j_id INT;
    txn_id INT;
    v_text TEXT;
BEGIN
    -- Per society: find unreversed depreciation debits on fund accounts and
    -- reverse each with a Cr on the fund plus a Dr on the depreciation account.
    FOR bad IN
        SELECT t.id AS id, t.trx_date AS trx_date, t.acc_id AS acc_id, t.amount AS amount,
               t.society_id AS society_id
        FROM transactions t
        JOIN accounts a ON a.id = t.acc_id AND a.society_id = t.society_id
        WHERE t.entry_side = 'Dr'
          AND a.tab_name IN ('DepFund','SinkFund','RepFund','CorpusFund','MajRepFund','Gifts')
          AND t.acc_particulars ILIKE '%depreciation%'
          AND NOT EXISTS (
              SELECT 1 FROM transactions r
              WHERE r.reverses_id = t.id AND r.source_table = 'depreciation_3280_fix')
    LOOP
        SELECT id INTO dep_acc FROM accounts
        WHERE society_id = bad.society_id AND tab_name = 'Dep' ORDER BY id LIMIT 1;
        IF dep_acc IS NULL THEN
            RAISE NOTICE 'skipping society %: no Depreciation (Dep) account to reverse to', bad.society_id;
            CONTINUE;
        END IF;

        SELECT u.id INTO admin_user
        FROM users u
        WHERE u.society_id = bad.society_id AND u.role = 'admin'
        ORDER BY u.id LIMIT 1;

        SELECT NEXTVAL('seq_transaction_number') INTO j_id;
        SELECT NEXTVAL('transactions_id_seq') INTO txn_id;

        -- Reversal leg: credit the fund account that wrongly received the debit.
        INSERT INTO transactions
            (id, society_id, entry_side, trx_date, acc_id, acc_particulars, amount, mode, status,
             created_by, source_table, journal_id, reverses_id)
        VALUES
            (txn_id, bad.society_id, 'Cr', bad.trx_date, bad.acc_id,
             'Reversal: depreciation wrongly debited to fund account', bad.amount,
             'journal', 'paid', admin_user, 'depreciation_3280_fix', j_id, bad.id);

        SELECT NEXTVAL('transactions_id_seq') INTO txn_id;
        -- Correcting leg: debit the Depreciation expense account.
        INSERT INTO transactions
            (id, society_id, entry_side, trx_date, acc_id, acc_particulars, amount, mode, status,
             created_by, source_table, journal_id, reverses_id)
        VALUES
            (txn_id, bad.society_id, 'Dr', bad.trx_date, dep_acc,
             'Depreciation moved off fund account to Depreciation expense (5110)',
             bad.amount, 'journal', 'paid', admin_user, 'depreciation_3280_fix', j_id, bad.id);

        RAISE NOTICE 'reversed depreciation debit txn % on fund account % in society % (journal %)',
                     bad.id, bad.acc_id, bad.society_id, j_id;
    END LOOP;
END $$;
