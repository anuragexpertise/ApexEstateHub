-- test/live_icai_checks.sql
--
-- Live ICAI correction checks, run against the seeded scratch DB:
--
--    psql -v ON_ERROR_STOP=1 -f test/live_icai_checks.sql
--
-- Every check is a DO $$ ... RAISE EXCEPTION ... $$ block that aborts the
-- script (ON_ERROR_STOP) when the condition it guards is not met.
--
-- Checks that fail TODAY (E2, E3, E5/E6) are kept in the "-- EXPECT FAIL
-- until C<n>" sections at the end and are run separately to prove the harness
-- catches the defect; they are NOT part of the exit-0 run. Do not use xfail.
--
-- Section 6 of ICAI_Correction_Plan.md is the source of these checks; each
-- later task appends its own checks here.

-- ============================================================================
-- MAIN SECTION — must pass on the seeded scratch DB (exit 0)
-- ============================================================================

-- 6.2 Balance sheet balances: Assets == Liabilities + Equity (+ Reserves & Surplus)
DO $$
DECLARE
    v_assets   NUMERIC(15,2);
    v_liab_eq  NUMERIC(15,2);
BEGIN
    SELECT
        COALESCE(SUM(amount) FILTER (WHERE statement_section = 'Assets'), 0),
        COALESCE(SUM(amount) FILTER (WHERE statement_section IN ('Liabilities', 'Equity')), 0)
    INTO v_assets, v_liab_eq
    FROM fn_balance_sheet_fy(1, 2026);

    IF ABS(v_assets - v_liab_eq) > 0.01 THEN
        RAISE EXCEPTION
            '6.2: balance sheet does not balance: Assets % != Liabilities + Equity %',
            v_assets, v_liab_eq;
    END IF;
END $$;

-- 6.3 Trial balance balances: SUM(closing_dr) - SUM(closing_cr) = 0
DO $$
DECLARE
    v_diff NUMERIC(15,2);
BEGIN
    SELECT SUM(closing_dr) - SUM(closing_cr) INTO v_diff
    FROM fn_trial_balance_fy(1, 2026);

    IF v_diff IS NULL OR ABS(v_diff) > 0.01 THEN
        RAISE EXCEPTION '6.3: trial balance does not balance (diff %)', v_diff;
    END IF;
END $$;

-- 6.6 Drift-check replacement: fn_trial_balance_check is balanced for FY 2025 and 2026
DO $$
DECLARE
    v_bal25 BOOLEAN;
    v_bal26 BOOLEAN;
BEGIN
    SELECT balanced INTO v_bal25 FROM fn_trial_balance_check(1, 2025);
    SELECT balanced INTO v_bal26 FROM fn_trial_balance_check(1, 2026);

    IF v_bal25 IS NOT TRUE OR v_bal26 IS NOT TRUE THEN
        RAISE EXCEPTION '6.6: fn_trial_balance_check not balanced: 2025=% 2026=%', v_bal25, v_bal26;
    END IF;
END $$;


-- ============================================================================
-- H2 (G4): trigger checks (C4) — each change is rolled back inside the block
-- ============================================================================

BEGIN;

-- C4-1: delete of accounts row 1/1500 raises
DO $$
DECLARE v_raised BOOLEAN := FALSE;
BEGIN
    BEGIN
        DELETE FROM accounts WHERE society_id = 1 AND id = 1500;
    EXCEPTION WHEN OTHERS THEN
        v_raised := TRUE;
    END;
    IF NOT v_raised THEN
        RAISE EXCEPTION 'C4: delete of accounts 1/1500 did not raise';
    END IF;
END $$;

-- C4-2: changing drcr_account of 1500 raises
DO $$
DECLARE v_raised BOOLEAN := FALSE;
BEGIN
    BEGIN
        UPDATE accounts SET drcr_account = 'Cr' WHERE society_id = 1 AND id = 1500;
    EXCEPTION WHEN OTHERS THEN
        v_raised := TRUE;
    END;
    IF NOT v_raised THEN
        RAISE EXCEPTION 'C4: changing drcr_account of 1500 did not raise';
    END IF;
END $$;

-- C4-3: renaming 1500 succeeds and adds exactly one audit_events row
DO $$
DECLARE v_before INT; v_after INT;
BEGIN
    SELECT count(*) INTO v_before FROM audit_events;
    UPDATE accounts SET name = 'Sundry Debtors (renamed)' WHERE society_id = 1 AND id = 1500;
    SELECT count(*) INTO v_after FROM audit_events;
    IF v_after IS NULL OR v_after <> v_before + 1 THEN
        RAISE EXCEPTION 'C4: rename did not add exactly one audit row (before % after %)', v_before, v_after;
    END IF;
END $$;

-- C4-4: is_active = false then inserting a transaction for 1500 raises
DO $$
DECLARE v_raised BOOLEAN := FALSE;
BEGIN
    BEGIN
        UPDATE accounts SET is_active = FALSE WHERE society_id = 1 AND id = 1500;
        INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, amount, status, mode, journal_id, transaction_number, created_by)
        VALUES (1, 'Dr', '2026-04-05', 1500, 100.00, 'paid', 'cash', 999999, 'C4-INACTIVE-A', 1),
               (1, 'Cr', '2026-04-05', 1311, 100.00, 'paid', 'cash', 999999, 'C4-INACTIVE-B', 1);
    EXCEPTION WHEN OTHERS THEN
        v_raised := TRUE;
    END;
    IF NOT v_raised THEN
        RAISE EXCEPTION 'C4: insert to inactive account 1500 did not raise';
    END IF;
END $$;

-- C4-5: inserting a transaction for active 1500 succeeds
DO $$
BEGIN
    UPDATE accounts SET is_active = TRUE WHERE society_id = 1 AND id = 1500;
    INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, amount, status, mode, journal_id, transaction_number, created_by)
    VALUES (1, 'Dr', '2026-04-05', 1500, 100.00, 'paid', 'cash', 999998, 'C4-ACTIVE-A', 1),
           (1, 'Cr', '2026-04-05', 1311, 100.00, 'paid', 'cash', 999998, 'C4-ACTIVE-B', 1);
EXCEPTION WHEN OTHERS THEN
    RAISE EXCEPTION 'C4: insert to active account 1500 failed: %', SQLERRM;
END $$;


-- ============================================================================
-- H2 (G4): year-end close appropriation (C5)
-- ============================================================================

-- C5: run fn_fy_close_reserve_appropriation(1, 2026) inside a rollback and
-- assert surplus unchanged, balance sheet still balanced, 3220 credit up by
-- 117,675.00, 3300 debit 117,675.00, 5100 zero.
DO $$
DECLARE
    v_surplus_before NUMERIC(15,2); v_surplus_after NUMERIC(15,2);
    v_assets_before NUMERIC(15,2); v_assets_after NUMERIC(15,2);
    v_lieq_before NUMERIC(15,2); v_lieq_after NUMERIC(15,2);
    v_3220_before NUMERIC(15,2); v_3220_after NUMERIC(15,2);
    v_3300_before NUMERIC(15,2); v_3300_after NUMERIC(15,2);
    v_5100_after NUMERIC(15,2);
BEGIN
    SELECT surplus INTO v_surplus_before FROM fn_fy_close_preview(1, 2026);
    SELECT COALESCE(SUM(amount) FILTER (WHERE statement_section='Assets'),0)
        INTO v_assets_before FROM fn_balance_sheet_fy(1,2026);
    SELECT COALESCE(SUM(amount) FILTER (WHERE statement_section IN ('Liabilities','Equity')),0)
        INTO v_lieq_before FROM fn_balance_sheet_fy(1,2026);
    SELECT COALESCE(closing_cr,0) INTO v_3220_before FROM fn_trial_balance_fy(1,2026) WHERE account_id=3220;
    SELECT COALESCE(closing_dr,0) INTO v_3300_before FROM fn_trial_balance_fy(1,2026) WHERE account_id=3300;

    PERFORM fn_fy_close_reserve_appropriation(1, 2026);

    SELECT surplus INTO v_surplus_after FROM fn_fy_close_preview(1, 2026);
    SELECT COALESCE(SUM(amount) FILTER (WHERE statement_section='Assets'),0)
        INTO v_assets_after FROM fn_balance_sheet_fy(1,2026);
    SELECT COALESCE(SUM(amount) FILTER (WHERE statement_section IN ('Liabilities','Equity')),0)
        INTO v_lieq_after FROM fn_balance_sheet_fy(1,2026);
    SELECT COALESCE(closing_cr,0) INTO v_3220_after FROM fn_trial_balance_fy(1,2026) WHERE account_id=3220;
    SELECT COALESCE(closing_dr,0) INTO v_3300_after FROM fn_trial_balance_fy(1,2026) WHERE account_id=3300;
    SELECT COALESCE(closing_dr,0)+COALESCE(closing_cr,0) INTO v_5100_after FROM fn_trial_balance_fy(1,2026) WHERE account_id=5100;

    IF v_surplus_after IS DISTINCT FROM v_surplus_before THEN
        RAISE EXCEPTION 'C5: surplus changed: % -> %', v_surplus_before, v_surplus_after;
    END IF;
    IF ABS(v_assets_after - v_assets_before) > 0.01 THEN
        RAISE EXCEPTION 'C5: assets changed: % -> %', v_assets_before, v_assets_after;
    END IF;
    IF ABS(v_lieq_after - v_lieq_before) > 0.01 THEN
        RAISE EXCEPTION 'C5: liabilities+equity changed: % -> %', v_lieq_before, v_lieq_after;
    END IF;
    IF ABS(v_assets_after - v_lieq_after) > 0.01 THEN
        RAISE EXCEPTION 'C5: after close balance sheet not balanced: Assets % != Liab+Eq %', v_assets_after, v_lieq_after;
    END IF;
    IF ABS(v_3220_after - v_3220_before - 117675.00) > 0.01 THEN
        RAISE EXCEPTION 'C5: 3220 credit not up by 117675: % -> %', v_3220_before, v_3220_after;
    END IF;
    IF ABS(v_3300_after - 117675.00) > 0.01 THEN
        RAISE EXCEPTION 'C5: 3300 debit not 117675: %', v_3300_after;
    END IF;
    IF ABS(v_5100_after) > 0.01 THEN
        RAISE EXCEPTION 'C5: 5100 not zero after close: %', v_5100_after;
    END IF;
END $$;


-- ============================================================================
-- H2 (G4): contra account (C1)
-- ============================================================================

-- C1: 1190 is in section Assets with amount -1,650.00; net fixed assets =
-- gross - 1,650.00
DO $$
DECLARE v_sec TEXT; v_amt NUMERIC(15,2); v_total NUMERIC(15,2); v_gross NUMERIC(15,2);
BEGIN
    SELECT statement_section, amount INTO v_sec, v_amt
    FROM fn_balance_sheet_fy(1, 2026) WHERE account_code = 1190;
    IF v_sec IS NULL OR v_sec <> 'Assets' OR v_amt IS NULL OR ABS(v_amt - (-1650.00)) > 0.01 THEN
        RAISE EXCEPTION 'C1: 1190 must be in Assets with -1650.00, got % %', v_sec, v_amt;
    END IF;
    SELECT SUM(amount) INTO v_total FROM fn_balance_sheet_fy(1, 2026) WHERE statement_section = 'Assets';
    SELECT SUM(amount) INTO v_gross FROM fn_balance_sheet_fy(1, 2026) WHERE statement_section = 'Assets' AND account_code <> 1190;
    IF v_total IS NULL OR v_gross IS NULL THEN
        RAISE EXCEPTION 'C1: missing asset rows';
    END IF;
    IF ABS(v_total - (v_gross - 1650.00)) > 0.01 THEN
        RAISE EXCEPTION 'C1: net fixed assets check failed: total % != gross % - 1650', v_total, v_gross;
    END IF;
END $$;


-- ============================================================================
-- H2 (G4): invariants (I5, I6, I7)
-- ============================================================================

-- I5: Assets = Liabilities + Equity for FY 2025 and FY 2026
DO $$
DECLARE v_fy INT; v_assets NUMERIC(15,2); v_lieq NUMERIC(15,2);
BEGIN
    FOR v_fy IN 2025 .. 2026 LOOP
        SELECT COALESCE(SUM(amount) FILTER (WHERE statement_section='Assets'),0),
               COALESCE(SUM(amount) FILTER (WHERE statement_section IN ('Liabilities','Equity')),0)
        INTO v_assets, v_lieq
        FROM fn_balance_sheet_fy(1, v_fy);
        IF ABS(v_assets - v_lieq) > 0.01 THEN
            RAISE EXCEPTION 'I5: FY % balance sheet not balanced: Assets % != Liab+Eq %', v_fy, v_assets, v_lieq;
        END IF;
    END LOOP;
END $$;

-- I7: surplus for the year = total income - total expense from the same
-- closing report (FY 2026)
DO $$
DECLARE v_surplus NUMERIC(15,2); v_income NUMERIC(15,2); v_expense NUMERIC(15,2);
BEGIN
    SELECT COALESCE(SUM(amount) FILTER (WHERE statement_section='Income'),0),
           COALESCE(SUM(amount) FILTER (WHERE statement_section='Expenditure'),0)
    INTO v_income, v_expense
    FROM fn_income_expenditure_fy(1, 2026);
    SELECT surplus INTO v_surplus FROM fn_fy_close_preview(1, 2026);
    IF ABS(v_surplus - (v_income - v_expense)) > 0.01 THEN
        RAISE EXCEPTION 'I7: surplus % != income % - expense %', v_surplus, v_income, v_expense;
    END IF;
END $$;


-- ============================================================================
-- H4 (G6): Depreciation Fund (3280) guard
-- ============================================================================

-- C6: 3280 may only be credited by the statutory reserve appropriation
-- (source_table 'fy_close', posted by fn_fy_close_reserve_appropriation).
-- A direct credit is refused; the appropriation path succeeds.
DO $$
DECLARE v_raised BOOLEAN := FALSE;
BEGIN
    BEGIN
        INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, amount, status, mode, journal_id, transaction_number, source_table, created_by)
        VALUES (1, 'Cr', '2026-04-05', 3280, 100.00, 'paid', 'cash', 999997, 'C6-DIRECT-A', 'manual', 1),
               (1, 'Dr', '2026-04-05', 1311, 100.00, 'paid', 'cash', 999997, 'C6-DIRECT-B', 'manual', 1);
    EXCEPTION WHEN OTHERS THEN
        v_raised := TRUE;
    END;
    IF NOT v_raised THEN
        RAISE EXCEPTION 'C6: direct credit to 3280 was not refused';
    END IF;

    INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, amount, status, mode, journal_id, transaction_number, source_table, created_by)
    VALUES (1, 'Cr', '2026-04-05', 3280, 100.00, 'paid', 'cash', 999996, 'C6-APPROP-A', 'fy_close', 1),
           (1, 'Dr', '2026-04-05', 3300, 100.00, 'paid', 'cash', 999996, 'C6-APPROP-B', 'fy_close', 1);
EXCEPTION WHEN OTHERS THEN
    RAISE EXCEPTION 'C6: appropriation-path credit to 3280 was refused: %', SQLERRM;
END $$;


-- ============================================================================
-- I3 / H7: MSME creditors split + 45-day compliance (live, rolled back)
-- ============================================================================

-- I3: one MSME-flagged vendor and one unflagged vendor, each with a bill;
-- fn_creditors_split splits correctly and mse_dues + other_dues = total_dues.
DO $$
DECLARE
    v_mse NUMERIC; v_oth NUMERIC; v_tot NUMERIC;
    v_mse_vid INT; v_oth_vid INT;
BEGIN
    INSERT INTO vendors (society_id, business_name, name, service_type, mobile, payee_type, msme_registered, msme_udyam_number)
    VALUES (1, 'MSE Vendor', 'MSE Vendor', 'Plumbing', '9000000001', 'individual', TRUE, 'UDYAM-MH-00-0000001'),
           (1, 'Other Vendor', 'Other Vendor', 'Gardening', '9000000002', 'individual', FALSE, NULL);

    SELECT id INTO v_mse_vid FROM vendors WHERE business_name = 'MSE Vendor' AND society_id = 1;
    SELECT id INTO v_oth_vid FROM vendors WHERE business_name = 'Other Vendor' AND society_id = 1;

    INSERT INTO payables (society_id, entity_id, role, acc_id, amount, mode, status, shift_date, due_date, description)
    VALUES (1, v_mse_vid, 'vendor', 2240, 5000.00, 'bank', 'pending', '2026-04-01', '2026-05-15', 'MSE bill'),
           (1, v_oth_vid, 'vendor', 2240, 10000.00, 'bank', 'pending', '2026-04-01', '2026-05-15', 'Other bill');

    SELECT mse_dues, other_dues, total_dues INTO v_mse, v_oth, v_tot FROM fn_creditors_split(1, 2026);
    IF v_mse IS NULL OR v_oth IS NULL OR v_tot IS NULL THEN
        RAISE EXCEPTION 'I3: fn_creditors_split returned NULL';
    END IF;
    IF ABS(v_mse - 5000.00) > 0.01 THEN
        RAISE EXCEPTION 'I3: mse_dues % expected 5000', v_mse;
    END IF;
    IF ABS(v_oth - 10000.00) > 0.01 THEN
        RAISE EXCEPTION 'I3: other_dues % expected 10000', v_oth;
    END IF;
    IF ABS(v_tot - 15000.00) > 0.01 THEN
        RAISE EXCEPTION 'I3: total_dues % expected 15000', v_tot;
    END IF;
    IF ABS(v_mse + v_oth - v_tot) > 0.01 THEN
        RAISE EXCEPTION 'I3: mse % + other % != total %', v_mse, v_oth, v_tot;
    END IF;
END $$;

-- fn_msme_payment_compliance: flags an invoice older than 45 days, does not
-- flag a 10-day-old one (MSE Vendor bill shift_date 2026-04-01).
DO $$
DECLARE v_comp BOOLEAN;
BEGIN
    SELECT compliant INTO v_comp
    FROM fn_msme_payment_compliance(1, (SELECT id FROM vendors WHERE business_name = 'MSE Vendor' AND society_id = 1), '2026-05-17');
    IF v_comp IS NOT FALSE THEN
        RAISE EXCEPTION 'I3: 46-day-old MSME bill should be non-compliant, got %', v_comp;
    END IF;
    SELECT compliant INTO v_comp
    FROM fn_msme_payment_compliance(1, (SELECT id FROM vendors WHERE business_name = 'MSE Vendor' AND society_id = 1), '2026-04-11');
    IF v_comp IS NOT TRUE THEN
        RAISE EXCEPTION 'I3: 10-day-old MSME bill should be compliant, got %', v_comp;
    END IF;
END $$;

ROLLBACK;

-- ============================================================================
-- EXPECT FAIL until C1 — E2: contra accounts belong in Assets
-- ============================================================================

-- 6.1 Contra accounts in the right section (fails today):
--     1190 Accumulated Depreciation must be in Assets with -1,650.00
DO $$
DECLARE
    v_sec  VARCHAR;
    v_amt  NUMERIC(15,2);
BEGIN
    SELECT statement_section, amount INTO v_sec, v_amt
    FROM fn_balance_sheet_fy(1, 2026)
    WHERE account_code = 1190;

    IF v_sec IS NULL OR v_sec <> 'Assets' OR v_amt IS NULL OR ABS(v_amt - (-1650.00)) > 0.01 THEN
        RAISE EXCEPTION
            '6.1: E2 not fixed — 1190 must be in Assets with amount -1650.00, got section % amount %',
            v_sec, v_amt;
    END IF;
END $$;

-- 6.1b Contra netting: Assets total = gross assets (excl 1190) + 1190 (negative)
DO $$
DECLARE
    v_total   NUMERIC(15,2);
    v_gross   NUMERIC(15,2);
    v_1190    NUMERIC(15,2);
BEGIN
    SELECT SUM(amount) INTO v_total
    FROM fn_balance_sheet_fy(1, 2026) WHERE statement_section = 'Assets';
    SELECT SUM(amount) INTO v_gross
    FROM fn_balance_sheet_fy(1, 2026) WHERE statement_section = 'Assets' AND account_code <> 1190;
    SELECT amount INTO v_1190
    FROM fn_balance_sheet_fy(1, 2026) WHERE statement_section = 'Assets' AND account_code = 1190;

    IF v_total IS NULL OR v_gross IS NULL OR v_1190 IS NULL THEN
        RAISE EXCEPTION '6.1b: missing asset rows';
    END IF;
    IF ABS(v_total - (v_gross + v_1190)) > 0.01 THEN
        RAISE EXCEPTION
            '6.1b: Assets net check failed: total % != gross % + 1190 %', v_total, v_gross, v_1190;
    END IF;
END $$;


-- ============================================================================
-- EXPECT FAIL until C2 — E3: every postable account has exactly one head
-- ============================================================================

-- 6.4 (final form, C2): every account with no child accounts (postable leaf)
-- has exactly one statutory head, except root id 1 (allow-list). Hybrid
-- accounts that hold their own postings (1500) also need a head.
DO $$
DECLARE
    v_unmapped INT;
    v_dup      INT;
    v_hybrid   INT;
BEGIN
    SELECT COUNT(*) INTO v_unmapped
    FROM accounts a
    WHERE a.society_id = 1
      AND a.id > 1
      AND NOT EXISTS (
          SELECT 1 FROM accounts c
          WHERE c.society_id = 1 AND c.parent_account_id = a.id
      )
      AND NOT EXISTS (
          SELECT 1 FROM account_statutory_mappings m
          WHERE m.society_id = 1 AND m.account_id = a.id
      );

    SELECT COUNT(*) INTO v_dup
    FROM (
        SELECT account_id
        FROM account_statutory_mappings
        WHERE society_id = 1
        GROUP BY account_id
        HAVING COUNT(*) > 1
    ) d;

    SELECT COUNT(*) INTO v_hybrid
    FROM accounts a
    WHERE a.society_id = 1 AND a.id = 1500
      AND NOT EXISTS (
          SELECT 1 FROM account_statutory_mappings m
          WHERE m.society_id = 1 AND m.account_id = a.id
      );

    IF v_unmapped <> 0 THEN
        RAISE EXCEPTION '6.4: E3 not fixed — % postable accounts have no statutory head', v_unmapped;
    END IF;
    IF v_dup <> 0 THEN
        RAISE EXCEPTION '6.4: % accounts have duplicate statutory heads', v_dup;
    END IF;
    IF v_hybrid <> 0 THEN
        RAISE EXCEPTION '6.4: hybrid account 1500 has no statutory head';
    END IF;
END $$;


-- ============================================================================
-- EXPECT FAIL until C5 — E6: year-end close debits 3300, not 5100
-- ============================================================================

-- 6.5 Year-end contra account (returns 5100 today; must return 3300)
DO $$
DECLARE
    v_contra INT;
BEGIN
    SELECT contra_acc_id INTO v_contra FROM fn_fy_close_preview(1, 2026);

    IF v_contra IS NULL OR v_contra <> 3300 THEN
        RAISE EXCEPTION
            '6.5: E6 not fixed — fn_fy_close_preview contra_acc_id is %, expected 3300',
            v_contra;
    END IF;
END $$;
