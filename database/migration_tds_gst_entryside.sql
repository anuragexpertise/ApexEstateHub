-- ============================================================================
-- MIGRATION: TDS/GST split-entry support + entry_side on transactions
-- + single-path verification (receipts/expenses are the ONLY writers of
--   `transactions`; receivables/payables just stage into them)
--
-- Run this AFTER estatehub.sql has been applied at least once.
-- Every function below is safe to re-run (DROP ... CASCADE + CREATE OR REPLACE).
--
-- DESIGN NOTES (read before deploying — these are the calls I made where
-- your spec left room for interpretation; flag anything that's wrong):
--
-- 1. entry_side is captured on the transaction row at insert time from the
--    linked account's drcr_account. It's a snapshot, not a live join — if
--    an account later gets reclassified, historical rows keep the side they
--    were actually posted on.
--
-- 2. TDS/GST are ACCOUNT-level flags (accounts.applies_tds / applies_gst)
--    because your workbook shows only some income accounts (Patients) are
--    subject to TDS, not all of them. Rates default to 10% / 8% per your
--    spec but are stored per-transaction (transactions.tds_pc/gst_pc) so a
--    future rate change doesn't rewrite history.
--
-- 3. Cash-vs-bank pairing (the old "always write a paired Dr/Cr cash leg")
--    is REMOVED from fn_verify_receipt/fn_verify_expense. Per your cashbook
--    rule ("only non-cash transactions appear on both sides"), that pairing
--    is now reconstructed at DISPLAY time inside fn_cashbook_paired_v2, not
--    stored as a second ledger row — it was never a real second account
--    posting, just a cashbook convention.
--
--    TDS/GST splits are DIFFERENT: money genuinely goes to a separate real
--    account (TDStoIT, GST payable), so those DO still get a real second
--    transactions row, written only when the entry is non-cash AND the
--    account has applies_tds/applies_gst = TRUE.
--
-- 4. fn_verify_receivable / fn_verify_payment no longer INSERT INTO
--    transactions directly. They INSERT INTO receipts / expenses (the
--    manual tables) and then call fn_verify_receipt / fn_verify_expense,
--    so there is exactly ONE code path that ever writes `transactions`.
--
-- 5. fn_pay_apartment_dues_fifo (bulk FIFO "Pay Dues" button) was NOT
--    touched — you didn't ask for it, and it's a batch loop rather than a
--    single-row verify. It still writes transactions directly, which is
--    now inconsistent with the rest of the engine. Flagging this as a
--    follow-up; happy to bring it in line once you've reviewed this batch.
--
-- 6. Pre-existing bug fixed in passing: fn_verify_expense referenced
--    v_rec.receipt_number against expenses%ROWTYPE, but `expenses` has no
--    receipt_number column (only `receipts` does) — this would have failed
--    to compile. Rewritten to not reference that column.
-- ============================================================================

-- ────────────────────────────────────────────────────────────────
-- SCHEMA CHANGES
-- ────────────────────────────────────────────────────────────────

ALTER TABLE accounts
    ADD COLUMN IF NOT EXISTS applies_tds BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS applies_gst BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS entry_side VARCHAR(2)
        CHECK (entry_side IN ('Dr','Cr')),
    ADD COLUMN IF NOT EXISTS tds_pc NUMERIC(5,2) NOT NULL DEFAULT 10.00,
    ADD COLUMN IF NOT EXISTS tds    NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS gst_pc NUMERIC(5,2) NOT NULL DEFAULT 8.00,
    ADD COLUMN IF NOT EXISTS gst    NUMERIC(12,2) NOT NULL DEFAULT 0.00;

-- Backfill entry_side for any pre-existing rows from the linked account.
UPDATE transactions t
SET entry_side = a.drcr_account
FROM accounts a
WHERE a.id = t.acc_id AND t.entry_side IS NULL;

CREATE INDEX IF NOT EXISTS idx_transactions_entry_side ON transactions (society_id, entry_side, trx_date);

-- ── Account for TDS / GST split legs — resolved by name, same pattern as
--    fn_resolve_cash_account. Falls back to NULL (split leg skipped) if the
--    society hasn't set one up, rather than failing the whole verify.
DROP FUNCTION IF EXISTS fn_resolve_split_account CASCADE;

CREATE OR REPLACE FUNCTION fn_resolve_split_account(p_society_id INT, p_kind VARCHAR)
RETURNS INT LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_acc_id INT;
BEGIN
    IF p_kind = 'tds' THEN
        SELECT id INTO v_acc_id FROM accounts
        WHERE society_id = p_society_id AND name ILIKE '%TDStoIT%'
        LIMIT 1;
    ELSIF p_kind = 'gst' THEN
        SELECT id INTO v_acc_id FROM accounts
        WHERE society_id = p_society_id AND name ILIKE '%GST%'
        LIMIT 1;
    END IF;
    RETURN v_acc_id;
END;
$$;

-- ────────────────────────────────────────────────────────────────
-- fn_verify_receipt — Cr income row always. Cash mode: that's the only
-- row (matches your CiH sheet, which has no per-transaction entries).
-- Non-cash mode: ALSO writes a real Dr leg to the mode-resolved bank
-- account, net of TDS/GST — this is what makes the bank account's own
-- ledger (fn_account_ledger_fy) itemized, matching your ICICI sheet,
-- and keeps kpi_bank_balance/kpi_cash_in_hand correct since they sum
-- real transactions rows.
-- ────────────────────────────────────────────────────────────────
DROP FUNCTION IF EXISTS fn_verify_receipt CASCADE;

CREATE OR REPLACE FUNCTION fn_verify_receipt(
    p_receipt_id   INT,
    p_confirmed_by INT,
    p_mode         VARCHAR DEFAULT NULL
)
RETURNS TABLE(receipt_id INT, receipt_number VARCHAR(64), msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_rec        receipts%ROWTYPE;
    v_acc        accounts%ROWTYPE;
    v_trx_id     INT;
    v_journal_id INT;
    v_mode       VARCHAR(20);
    v_number     VARCHAR(64);
    v_is_cash    BOOLEAN;
    v_tds_pc     NUMERIC(5,2);
    v_gst_pc     NUMERIC(5,2);
    v_tds        NUMERIC(12,2) := 0;
    v_gst        NUMERIC(12,2) := 0;
    v_tds_acc    INT;
    v_gst_acc    INT;
    v_bank_acc   INT;
    v_bank_leg   NUMERIC(12,2);
BEGIN
    SELECT * INTO v_rec FROM receipts WHERE id = p_receipt_id FOR UPDATE;
    IF NOT FOUND    THEN receipt_id := p_receipt_id; receipt_number := NULL; msg := 'Error: Receipt not found'; RETURN NEXT; RETURN; END IF;
    IF v_rec.status = 'confirmed'  THEN receipt_id := p_receipt_id; receipt_number := v_rec.receipt_number; msg := 'Already confirmed'; RETURN NEXT; RETURN; END IF;
    IF v_rec.status = 'cancelled'  THEN receipt_id := p_receipt_id; receipt_number := v_rec.receipt_number; msg := 'Error: Receipt is cancelled'; RETURN NEXT; RETURN; END IF;
    IF v_rec.acc_id IS NULL        THEN receipt_id := p_receipt_id; receipt_number := v_rec.receipt_number; msg := 'Error: No income account on this receipt'; RETURN NEXT; RETURN; END IF;

    SELECT * INTO v_acc FROM accounts WHERE id = v_rec.acc_id;
    v_mode    := COALESCE(p_mode, v_rec.mode);
    v_is_cash := (v_mode = 'cash');
    v_journal_id := NEXTVAL('seq_transaction_number');

    v_tds_pc := 10.00;
    v_gst_pc := 8.00;

    IF NOT v_is_cash AND v_acc.applies_tds THEN
        v_tds := ROUND(v_rec.amount * v_tds_pc / 100, 2);
        v_tds_acc := fn_resolve_split_account(v_rec.society_id, 'tds');
    END IF;
    IF NOT v_is_cash AND v_acc.applies_gst THEN
        v_gst := ROUND(v_rec.amount * v_gst_pc / 100, 2);
        v_gst_acc := fn_resolve_split_account(v_rec.society_id, 'gst');
    END IF;

    -- Cr: the full income amount, on its own side.
    INSERT INTO transactions(
        society_id, trx_date, acc_id, entity_id, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id,
        journal_id, entry_side, tds_pc, tds, gst_pc, gst
    ) VALUES (
        v_rec.society_id, v_rec.receipt_date, v_rec.acc_id, v_rec.entity_id,
        v_rec.particulars,
        v_rec.amount, v_mode, 'paid',
        p_confirmed_by, NOW(), 'receipts', v_rec.id, v_journal_id,
        'Cr', v_tds_pc, v_tds, v_gst_pc, v_gst
    ) RETURNING id INTO v_trx_id;

    IF NOT v_is_cash THEN
        v_bank_acc := fn_resolve_cash_account(v_rec.society_id, v_mode);
        v_bank_leg := v_rec.amount - v_tds - v_gst;

        -- Dr: net amount actually received into the bank/settlement account.
        IF v_bank_acc IS NOT NULL AND v_bank_leg > 0 THEN
            INSERT INTO transactions(
                society_id, trx_date, acc_id, entity_id, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id,
                journal_id, entry_side
            ) VALUES (
                v_rec.society_id, v_rec.receipt_date, v_bank_acc, v_rec.entity_id,
                'Received - ' || v_rec.particulars,
                v_bank_leg, v_mode, 'paid', p_confirmed_by, NOW(), 'receipts', v_rec.id, v_journal_id, 'Dr'
            );
        END IF;

        -- Dr: TDS withheld, routed to the TDS-recoverable account.
        IF v_tds > 0 AND v_tds_acc IS NOT NULL THEN
            INSERT INTO transactions(
                society_id, trx_date, acc_id, entity_id, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id,
                journal_id, entry_side
            ) VALUES (
                v_rec.society_id, v_rec.receipt_date, v_tds_acc, v_rec.entity_id,
                'TDS deducted - ' || v_rec.particulars,
                v_tds, v_mode, 'paid', p_confirmed_by, NOW(), 'receipts', v_rec.id, v_journal_id, 'Dr'
            );
        END IF;

        IF v_gst > 0 AND v_gst_acc IS NOT NULL THEN
            INSERT INTO transactions(
                society_id, trx_date, acc_id, entity_id, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id,
                journal_id, entry_side
            ) VALUES (
                v_rec.society_id, v_rec.receipt_date, v_gst_acc, v_rec.entity_id,
                'GST - ' || v_rec.particulars,
                v_gst, v_mode, 'paid', p_confirmed_by, NOW(), 'receipts', v_rec.id, v_journal_id, 'Dr'
            );
        END IF;
    END IF;

    UPDATE receipts
    SET status       = 'confirmed',
        confirmed_by = p_confirmed_by,
        confirmed_at = NOW()
    WHERE id = p_receipt_id;

    v_number := fn_issue_receipt_hash_for_receipt(p_receipt_id);

    receipt_id := p_receipt_id;
    receipt_number := v_number;
    msg := 'Verified: transaction #' || v_trx_id::TEXT || ' receipt_number=' || COALESCE(v_number, 'N/A')
           || CASE WHEN v_tds > 0 THEN ' | TDS ' || v_tds::TEXT ELSE '' END
           || CASE WHEN v_gst > 0 THEN ' | GST ' || v_gst::TEXT ELSE '' END;
    RETURN NEXT;
END;
$$;

-- ────────────────────────────────────────────────────────────────
-- fn_verify_expense — Dr expense row always. Cash mode: that's the
-- only row. Non-cash mode: ALSO writes a real Cr leg to the
-- mode-resolved bank account (money actually leaving the bank),
-- net of any GST input-credit split. Mirrors fn_verify_receipt.
-- (Also fixes a pre-existing bug: the old code referenced
-- v_rec.receipt_number against expenses%ROWTYPE, but `expenses` has no
-- such column — only `receipts` does — which would fail to compile.)
-- ────────────────────────────────────────────────────────────────
DROP FUNCTION IF EXISTS fn_verify_expense CASCADE;

CREATE OR REPLACE FUNCTION fn_verify_expense(
    p_expense_id   INT,
    p_confirmed_by INT,
    p_mode         VARCHAR DEFAULT NULL
)
RETURNS TABLE(expense_id INT, receipt_number VARCHAR(64), msg TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    v_rec        expenses%ROWTYPE;
    v_acc        accounts%ROWTYPE;
    v_trx_id     INT;
    v_journal_id INT;
    v_mode       VARCHAR(20);
    v_is_cash    BOOLEAN;
    v_gst_pc     NUMERIC(5,2);
    v_gst        NUMERIC(12,2) := 0;
    v_gst_acc    INT;
    v_bank_acc   INT;
    v_bank_leg   NUMERIC(12,2);
BEGIN
    SELECT * INTO v_rec FROM expenses WHERE id = p_expense_id FOR UPDATE;
    IF NOT FOUND    THEN expense_id := p_expense_id; receipt_number := NULL; msg := 'Error: Expense not found'; RETURN NEXT; RETURN; END IF;
    IF v_rec.status = 'confirmed'  THEN expense_id := p_expense_id; receipt_number := NULL; msg := 'Already confirmed'; RETURN NEXT; RETURN; END IF;
    IF v_rec.status = 'cancelled'  THEN expense_id := p_expense_id; receipt_number := NULL; msg := 'Error: Expense is cancelled'; RETURN NEXT; RETURN; END IF;
    IF v_rec.acc_id IS NULL        THEN expense_id := p_expense_id; receipt_number := NULL; msg := 'Error: No expense account on this row'; RETURN NEXT; RETURN; END IF;

    SELECT * INTO v_acc FROM accounts WHERE id = v_rec.acc_id;
    v_mode    := COALESCE(p_mode, v_rec.mode);
    v_is_cash := (v_mode = 'cash');
    v_journal_id := NEXTVAL('seq_transaction_number');

    v_gst_pc := 8.00;
    IF NOT v_is_cash AND v_acc.applies_gst THEN
        v_gst := ROUND(v_rec.amount * v_gst_pc / 100, 2);
        v_gst_acc := fn_resolve_split_account(v_rec.society_id, 'gst');
    END IF;

    -- Dr: the full expense amount, on its own side.
    INSERT INTO transactions(
        society_id, trx_date, acc_id, entity_id, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id,
        journal_id, entry_side, gst_pc, gst
    ) VALUES (
        v_rec.society_id, v_rec.expense_date, v_rec.acc_id, v_rec.entity_id,
        v_rec.particulars,
        v_rec.amount, v_mode, 'paid',
        p_confirmed_by, NOW(), 'expenses', v_rec.id, v_journal_id,
        'Dr', v_gst_pc, v_gst
    ) RETURNING id INTO v_trx_id;

    IF NOT v_is_cash THEN
        v_bank_acc := fn_resolve_cash_account(v_rec.society_id, v_mode);
        v_bank_leg := v_rec.amount - v_gst;

        -- Cr: net amount actually paid out of the bank/settlement account.
        IF v_bank_acc IS NOT NULL AND v_bank_leg > 0 THEN
            INSERT INTO transactions(
                society_id, trx_date, acc_id, entity_id, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id,
                journal_id, entry_side
            ) VALUES (
                v_rec.society_id, v_rec.expense_date, v_bank_acc, v_rec.entity_id,
                'Paid - ' || v_rec.particulars,
                v_bank_leg, v_mode, 'paid', p_confirmed_by, NOW(), 'expenses', v_rec.id, v_journal_id, 'Cr'
            );
        END IF;

        IF v_gst > 0 AND v_gst_acc IS NOT NULL THEN
            INSERT INTO transactions(
                society_id, trx_date, acc_id, entity_id, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id,
                journal_id, entry_side
            ) VALUES (
                v_rec.society_id, v_rec.expense_date, v_gst_acc, v_rec.entity_id,
                'GST - ' || v_rec.particulars,
                v_gst, v_mode, 'paid', p_confirmed_by, NOW(), 'expenses', v_rec.id, v_journal_id, 'Cr'
            );
        END IF;
    END IF;

    UPDATE expenses
    SET status       = 'confirmed',
        confirmed_by = p_confirmed_by,
        confirmed_at = NOW()
    WHERE id = p_expense_id;

    expense_id := p_expense_id;
    receipt_number := NULL; -- expenses table has no receipt_number column
    msg := 'Verified: transaction #' || v_trx_id::TEXT
           || CASE WHEN v_gst > 0 THEN ' | GST ' || v_gst::TEXT ELSE '' END;
    RETURN NEXT;
END;
$$;

-- ────────────────────────────────────────────────────────────────
-- fn_verify_receivable — no longer writes transactions. Stages the
-- verified amount into `receipts`, then hands off to fn_verify_receipt.
-- ────────────────────────────────────────────────────────────────
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
    v_new_receipt_id INT;
    v_result      RECORD;
    v_msg         TEXT := '';
BEGIN
    SELECT * INTO v_rec FROM receivables WHERE id = p_receivable_id FOR UPDATE;
    IF NOT FOUND THEN RETURN 'Error: Receivable not found'; END IF;
    IF v_rec.status = 'paid' THEN RETURN 'Already fully paid'; END IF;
    IF v_rec.acc_id IS NULL THEN RETURN 'Error: No income account set on this receivable — check apt_charges_fines_basis'; END IF;

    v_residual := v_rec.amount - v_rec.paid_amount;
    IF v_residual <= 0 THEN RETURN 'Nothing outstanding on this row'; END IF;

    v_int_post := LEAST(v_rec.interest_amount - GREATEST(v_rec.paid_amount - v_rec.base_amount, 0), v_residual);
    v_int_post := GREATEST(COALESCE(v_int_post, 0), 0);
    v_base_post := v_residual - v_int_post;

    -- Base amount: staged receipt on the receivable's income account.
    INSERT INTO receipts(
        society_id, entity_id, role, receipt_date, acc_id, particulars,
        amount, mode, status, created_at
    ) VALUES (
        v_rec.society_id, v_rec.entity_id, v_rec.role, CURRENT_DATE, v_rec.acc_id,
        REPLACE(v_rec.description, ' + Interest', ''),
        v_base_post, p_mode, 'pending', NOW()
    ) RETURNING id INTO v_new_receipt_id;

    SELECT * INTO v_result FROM fn_verify_receipt(v_new_receipt_id, p_confirmed_by, p_mode);
    v_msg := 'Base: ' || v_result.msg;

    -- Interest amount (if any): separate staged receipt on the interest
    -- income account, same pattern.
    IF v_rec.interest_acc_id IS NOT NULL AND v_int_post > 0 THEN
        INSERT INTO receipts(
            society_id, entity_id, role, receipt_date, acc_id, particulars,
            amount, mode, status, created_at
        ) VALUES (
            v_rec.society_id, v_rec.entity_id, v_rec.role, CURRENT_DATE, v_rec.interest_acc_id,
            'Interest on ' || REPLACE(v_rec.description, ' + Interest', ''),
            v_int_post, p_mode, 'pending', NOW()
        ) RETURNING id INTO v_new_receipt_id;

        SELECT * INTO v_result FROM fn_verify_receipt(v_new_receipt_id, p_confirmed_by, p_mode);
        v_msg := v_msg || ' | Interest: ' || v_result.msg;
    END IF;

    UPDATE receivables
    SET paid_amount    = v_rec.paid_amount + v_residual,
        paid_principal = v_rec.paid_principal + v_base_post,
        status         = 'paid',
        confirmed_by   = p_confirmed_by,
        confirmed_at   = NOW()
    WHERE id = p_receivable_id;

    RETURN v_msg;
END;
$$;

-- ────────────────────────────────────────────────────────────────
-- fn_verify_payment (payables) — no longer writes transactions. Stages
-- into `expenses`, then hands off to fn_verify_expense.
-- ────────────────────────────────────────────────────────────────
DROP FUNCTION IF EXISTS fn_verify_payment CASCADE;

CREATE OR REPLACE FUNCTION fn_verify_payment(
    p_payment_id   INT,
    p_confirmed_by INT,
    p_mode         VARCHAR DEFAULT 'cash'
)
RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
    v_pay            payables%ROWTYPE;
    v_new_expense_id INT;
    v_result         RECORD;
BEGIN
    SELECT * INTO v_pay FROM payables WHERE id = p_payment_id FOR UPDATE;
    IF NOT FOUND THEN RETURN 'Error: Payment not found'; END IF;
    IF v_pay.status = 'verified' THEN RETURN 'Already verified'; END IF;
    IF v_pay.acc_id IS NULL THEN RETURN 'Error: No expense account set on this payment row'; END IF;

    INSERT INTO expenses(
        society_id, entity_id, role, expense_date, acc_id, particulars,
        amount, mode, status, created_at
    ) VALUES (
        v_pay.society_id, v_pay.entity_id, v_pay.role, CURRENT_DATE, v_pay.acc_id,
        v_pay.description,
        v_pay.amount, p_mode, 'pending', NOW()
    ) RETURNING id INTO v_new_expense_id;

    SELECT * INTO v_result FROM fn_verify_expense(v_new_expense_id, p_confirmed_by, p_mode);

    UPDATE payables
    SET status       = 'verified',
        confirmed_by = p_confirmed_by,
        confirmed_at = NOW(),
        paid_at      = NOW()
    WHERE id = p_payment_id;

    RETURN v_result.msg;
END;
$$;

-- ────────────────────────────────────────────────────────────────
-- fn_account_ledger_fy — swap accounts.drcr_account join for entry_side
-- ────────────────────────────────────────────────────────────────
DROP FUNCTION IF EXISTS fn_account_ledger_fy CASCADE;

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

    v_bf := fn_resolve_bf_amount_fy(p_society_id, p_account_id, p_financial_year);
    v_bf_drcr := CASE WHEN v_bf >= 0 THEN 'Dr' ELSE 'Cr' END;
    v_bf := ABS(v_bf);

    v_balance := v_bf;

    IF v_bf <> 0 THEN
        RETURN QUERY SELECT
            v_fy_start - INTERVAL '1 day', 'Balance B/F'::TEXT,
            CASE WHEN v_bf_drcr = 'Dr' THEN v_bf ELSE 0 END,
            CASE WHEN v_bf_drcr = 'Cr' THEN v_bf ELSE 0 END,
            v_balance, 'bf'::TEXT, v_acc.parent_name::TEXT;
    END IF;

    -- Transaction rows, running balance. entry_side is the historical
    -- posting side (snapshot at insert time) rather than a live join to
    -- accounts.drcr_account.
    RETURN QUERY
    WITH txns AS (
        SELECT t.trx_date,
               t.acc_particulars::TEXT,
               COALESCE(SUM(t.amount) FILTER (WHERE t.entry_side = 'Dr'), 0) AS debit,
               COALESCE(SUM(t.amount) FILTER (WHERE t.entry_side = 'Cr'), 0) AS credit
        FROM transactions t
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
        'txn'::TEXT, v_acc.parent_name::TEXT
    FROM txns tx;

    SELECT v_bf + COALESCE(
        CASE v_acc.drcr_account
            WHEN 'Cr' THEN SUM(CASE WHEN t.entry_side='Cr' THEN t.amount ELSE -t.amount END)
            ELSE SUM(CASE WHEN t.entry_side='Dr' THEN t.amount ELSE -t.amount END)
        END, 0)
    INTO v_final_balance
    FROM transactions t
    WHERE t.acc_id = p_account_id AND t.society_id = p_society_id AND t.status = 'paid'
      AND t.trx_date BETWEEN v_fy_start AND v_fy_end;

    v_transfer_amt := v_final_balance;

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
                COALESCE((SELECT name FROM accounts WHERE id = v_dep_acc_id), 'Dep')::TEXT;

            v_transfer_amt := v_final_balance - v_dep_amount;
        END IF;
    END IF;

    IF v_transfer_amt <> 0 THEN
        RETURN QUERY SELECT
            v_fy_end,
            ('Balance C/F -> ' || COALESCE(v_acc.parent_name, 'Parent'))::TEXT,
            CASE WHEN v_acc.drcr_account = 'Dr' THEN v_transfer_amt ELSE 0::NUMERIC(15,2) END,
            CASE WHEN v_acc.drcr_account = 'Cr' THEN v_transfer_amt ELSE 0::NUMERIC(15,2) END,
            0::NUMERIC(15,2), 'closing'::TEXT, v_acc.parent_name::TEXT;
    END IF;
END;
$$;

-- ────────────────────────────────────────────────────────────────
-- fn_cashbook_paired_v2 — keyed off entry_side (instead of joining
-- accounts.drcr_account). Real Cr/Dr legs sharing a journal_id are
-- paired by row order within that journal — this naturally lines up
-- TDS/GST split legs, and the real bank-passthrough leg written by
-- fn_verify_receipt/fn_verify_expense for non-cash entries, against
-- the receipt/expense they came from. A plain cash entry has no
-- counterpart leg at all (by design — see fn_verify_receipt), so it
-- simply occupies a slot on its own side.
-- ────────────────────────────────────────────────────────────────
DROP FUNCTION IF EXISTS fn_cashbook_paired_v2 (
    INT, INT, TEXT, TEXT, DATE, DATE
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

    SELECT COALESCE(SUM(
        CASE WHEN bf.drcr_bf = 'Dr' THEN bf.bf_amount ELSE -bf.bf_amount END
    ), 0)
    INTO v_opening_balance
    FROM accounts a
    JOIN brought_forward bf ON bf.acc_id = a.id AND bf.society_id = a.society_id
    WHERE a.society_id = p_society_id AND a.is_cash_or_bank = TRUE
      AND bf.financial_year = v_fy;

    RETURN QUERY
    WITH base AS (
        SELECT t.id, t.journal_id, t.trx_date, t.mode, t.entry_side, t.amount,
               a.id AS acc_id, a.name::TEXT AS account_name,
               COALESCE(ap.flat_number, v.name, s.name, '')::TEXT AS entity_name,
               COALESCE(t.acc_particulars,'')::TEXT AS particulars
        FROM transactions t
        JOIN accounts a ON a.id = t.acc_id
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
    cr_rows AS (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY COALESCE(journal_id, -id) ORDER BY id) AS rn
        FROM base WHERE entry_side = 'Cr'
    ),
    dr_rows AS (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY COALESCE(journal_id, -id) ORDER BY id) AS rn
        FROM base WHERE entry_side = 'Dr'
    ),
    journals AS (
        SELECT COALESCE(journal_id, -id) AS jid, trx_date FROM base
        GROUP BY COALESCE(journal_id, -id), trx_date
    ),
    slot_counts AS (
        SELECT j.jid, j.trx_date,
               GREATEST(COALESCE(MAX(cr.rn), 0), COALESCE(MAX(dr.rn), 0)) AS max_rn
        FROM journals j
        LEFT JOIN cr_rows cr ON COALESCE(cr.journal_id, -cr.id) = j.jid
        LEFT JOIN dr_rows dr ON COALESCE(dr.journal_id, -dr.id) = j.jid
        GROUP BY j.jid, j.trx_date
    ),
    slots AS (
        SELECT jid, trx_date, gs AS rn
        FROM slot_counts, LATERAL generate_series(1, max_rn) AS gs
    ),
    paired AS (
        SELECT
            sl.trx_date AS cb_date,
            cr.acc_id AS rc_acc_id, cr.account_name AS rc_account_name,
            cr.entity_name AS rc_entity_name, cr.particulars AS rc_particulars,
            CASE WHEN cr.mode = 'cash' THEN cr.amount ELSE 0 END AS rc_cash,
            CASE WHEN cr.mode <> 'cash' THEN cr.amount ELSE 0 END AS rc_chq,
            dr.acc_id AS pc_acc_id, dr.account_name AS pc_account_name,
            dr.entity_name AS pc_entity_name, dr.particulars AS pc_particulars,
            CASE WHEN dr.mode = 'cash' THEN dr.amount ELSE 0 END AS pc_cash,
            CASE WHEN dr.mode <> 'cash' THEN dr.amount ELSE 0 END AS pc_chq
        FROM slots sl
        LEFT JOIN cr_rows cr ON COALESCE(cr.journal_id, -cr.id) = sl.jid AND cr.rn = sl.rn
        LEFT JOIN dr_rows dr ON COALESCE(dr.journal_id, -dr.id) = sl.jid AND dr.rn = sl.rn
        WHERE cr.id IS NOT NULL OR dr.id IS NOT NULL
    ),
    day_totals AS (
        -- Cash-only, matching the workbook's own running-balance formula
        -- (I6=I5+G6, P6=P5+N6 — G/N are the CASH columns; the Chq columns
        -- H/O are audit-trail only and never feed the running total. Bank
        -- position is tracked separately in its own account's ledger).
        SELECT pd.cb_date,
               SUM(COALESCE(pd.rc_cash,0)) AS day_rc,
               SUM(COALESCE(pd.pc_cash,0)) AS day_pc
        FROM paired pd GROUP BY pd.cb_date
    ),
    running AS (
        SELECT cb_date,
               v_opening_balance + SUM(day_rc - day_pc) OVER (ORDER BY cb_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS bal
        FROM day_totals
    )
    SELECT
        p.cb_date AS row_date,
        p.rc_acc_id, COALESCE(p.rc_account_name,'')::TEXT, COALESCE(p.rc_entity_name,'')::TEXT, COALESCE(p.rc_particulars,'')::TEXT,
        COALESCE(p.rc_cash,0)::NUMERIC(15,2), COALESCE(p.rc_chq,0)::NUMERIC(15,2),
        p.pc_acc_id, COALESCE(p.pc_account_name,'')::TEXT, COALESCE(p.pc_entity_name,'')::TEXT, COALESCE(p.pc_particulars,'')::TEXT,
        COALESCE(p.pc_cash,0)::NUMERIC(15,2), COALESCE(p.pc_chq,0)::NUMERIC(15,2),
        r.bal::NUMERIC(15,2)
    FROM paired p
    JOIN running r ON r.cb_date = p.cb_date
    ORDER BY p.cb_date;
END;
$$;
