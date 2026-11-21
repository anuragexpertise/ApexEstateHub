-- test/live_icai_checks.sql
--
-- Live ICAI correction checks, run against the seeded scratch DB:
--
#    psql -v ON_ERROR_STOP=1 -f test/live_icai_checks.sql
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
