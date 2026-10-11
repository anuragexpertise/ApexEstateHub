-- ============================================================================
-- migrations/003_inexp_anchor_fix.sql
--
-- Block-COA follow-up fix.
--
-- Problem exposed by the renumber:
--   estatehub.sql's own comment above fn_fy_closing_report notes that
--   "the entire P&L nominal ledger is structurally nested under account 2
--   'Capital Account' in ACCOUNTS". fn_income_expenditure_fy and
--   fn_balance_sheet_fy were both written to that assumption:
--     - fn_income_expenditure_fy anchored its P&L scan on tab_name='CapAc'
--     - fn_balance_sheet_fy's ie_surplus CTE (Reserves & Surplus in Equity)
--       also anchored on tab_name='CapAc'
--
--   Under the block scheme the P&L moved to its own block:
--       5000 Expenses
--       └─ 5100 Income Expenditure A/c  (tab_name = 'InExp')
--          ├─ 5110 Depreciation
--          ├─ 5120 Rent Paid
--          └─ ... etc.
--   Capital Account (3100) is now its own Equity line with no P&L under it.
--   Both functions returned empty P&L / zero Reserves & Surplus.
--
-- Fix:
--   Re-anchor both scans on tab_name='InExp'. The P&L subtree is
--   unambiguously rooted there under the block scheme. Capital Account is
--   still read (for the Equity line itself) via the existing cap_ac CTE in
--   fn_balance_sheet_fy, unchanged.
--
-- Idempotent: DROP FUNCTION IF EXISTS ... CASCADE before each CREATE OR
-- REPLACE, so re-running replaces cleanly.
-- ============================================================================

-- ═════════════════════════════════════════════════════════════════════════════
-- Fix 1: fn_income_expenditure_fy — anchor the P&L scan on InExp
-- ═════════════════════════════════════════════════════════════════════════════
DROP FUNCTION IF EXISTS fn_income_expenditure_fy (INT, INT) CASCADE;

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
    -- Block-COA fix: anchor the P&L subtree on tab_name='InExp'
    -- (Income Expenditure A/c, id 5100) instead of tab_name='CapAc'.
    -- Under the old scheme the whole P&L nested under Capital Account;
    -- under the block scheme it lives under 5000 Expenses → 5100 InExp.
    inexp_ac AS (
        SELECT sort_path FROM closing WHERE tab_name = 'InExp' LIMIT 1
    ),
    pl_accs AS (
        -- own_closing (this account's own movement, never a subtree rollup)
        -- naturally avoids double-counting AND includes hybrid header+leaf
        -- accounts (e.g. "Income Expenditure A/c" itself, which carries the
        -- depreciation-transfer entry), with no leaf/header distinction
        -- needed. Same rationale as the pre-existing comment on this CTE.
        SELECT c.*, a.mutuality_nature
        FROM closing c
        LEFT JOIN accounts a ON a.id = c.account_id
        CROSS JOIN inexp_ac ie
        WHERE ie.sort_path IS NOT NULL
          AND c.sort_path LIKE ie.sort_path || '.%'
          AND c.own_closing IS NOT NULL
          AND c.own_closing != 0
    ),
    income_accs AS (
        -- own_closing's natural sign is honest: a genuine reversal against a
        -- Cr-natured account shows as a negative income line rather than
        -- silently inflating the total via ABS().
        SELECT 'Income'::VARCHAR AS statement_section,
               pa.account_id::INT AS account_code,
               pa.account_name::VARCHAR AS account_name,
               pa.own_closing::NUMERIC(15,2) AS amount,
               pa.mutuality_nature
        FROM pl_accs pa
        WHERE pa.drcr_account = 'Cr'
    ),
    expense_accs AS (
        SELECT 'Expenditure'::VARCHAR AS statement_section,
               pa.account_id::INT AS account_code,
               pa.account_name::VARCHAR AS account_name,
               (-pa.own_closing)::NUMERIC(15,2) AS amount,
               pa.mutuality_nature
        FROM pl_accs pa
        WHERE pa.drcr_account = 'Dr'
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


-- ═════════════════════════════════════════════════════════════════════════════
-- Fix 2: fn_balance_sheet_fy — ie_surplus CTE anchored on InExp
--
-- The cap_ac CTE stays (still used to exclude CapAc's own subtree from
-- Liabilities, and to compute cap_ac_own for the Equity line). Add a
-- parallel inexp_ac CTE and use it only in ie_surplus (Reserves & Surplus).
-- ═════════════════════════════════════════════════════════════════════════════
DROP FUNCTION IF EXISTS fn_balance_sheet_fy (INT, INT) CASCADE;

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
    -- Block-COA fix: separate anchor for the P&L subtree, used by ie_surplus
    -- below. tab_name='InExp' (id 5100), not tab_name='CapAc'.
    inexp_ac AS (
        SELECT sort_path FROM closing WHERE tab_name = 'InExp' LIMIT 1
    ),
    bs_accs AS (
        SELECT c.*, a.mutuality_nature
        FROM closing c
        LEFT JOIN accounts a ON a.id = c.account_id
        CROSS JOIN cap_ac ca
        WHERE c.own_closing IS NOT NULL
          -- Exclude Capital Account's own subtree from the plain Liabilities
          -- list; Capital Account is written separately under Equity below.
          AND (ca.sort_path IS NULL
               OR (c.sort_path NOT LIKE ca.sort_path || '.%'
                   AND c.sort_path != ca.sort_path))
    ),
    asset_accs AS (
        -- Unconditionally negate own_closing: a genuine negative asset
        -- position (e.g. cash shortfall) shows honestly rather than being
        -- passed through as a false positive.
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
    -- Block-COA fix: anchored on inexp_ac, not cap_ac. Sums the whole P&L
    -- subtree's own_closing (Cr-positive convention: income adds, expense
    -- subtracts), which is exactly the year's net Surplus/Deficit.
    ie_surplus AS (
        SELECT COALESCE(SUM(c.own_closing), 0) AS surplus
        FROM closing c
        CROSS JOIN inexp_ac ie
        WHERE ie.sort_path IS NOT NULL
          AND c.sort_path LIKE ie.sort_path || '.%'
          AND c.own_closing IS NOT NULL
          AND c.own_closing != 0
    ),
    cap_ac_own AS (
        SELECT c.account_id, c.account_name, c.own_closing, a.mutuality_nature,
               c.statutory_head_code, c.statutory_head_label,
               c.statutory_statement_section, c.statutory_display_order
        FROM closing c
        CROSS JOIN cap_ac ca
        LEFT JOIN accounts a ON a.id = c.account_id
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