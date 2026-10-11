-- ============================================================================
-- migrations/004_pnl_anchor_fix_v2.sql
--
-- 003_pnl_anchor_fix.sql anchored fn_income_expenditure_fy and
-- fn_balance_sheet_fy's ie_surplus on tab_name='InExp' (5100). That correctly
-- captured the expenditure side but MISSED the income side, because under
-- the block scheme income and expenses are in TWO separate top-level
-- blocks:
--
--     4000 Income  (all Cr-natured: SocM, SocC, IntSav, EventT, ...)
--     5000 Expenses (Dr-natured leaves + 5100 InExp clearing account)
--
-- The old scheme nested ALL of P&L (income + expense) under account 2
-- Capital Account, so a single anchor worked. The block scheme split them.
--
-- This migration re-anchors both functions on BOTH block roots, and
-- classifies by block membership rather than by drcr_account — because
-- the P&L clearing account (5100 InExp, Cr-natured) must not be treated
-- as income, and the depreciation clearing pattern puts Dr movements on
-- a Cr-natured account, which drcr_account-based classification gets
-- backwards.
--
-- Classification rule:
--   * Under 4000 Income         -> Income
--   * Under 5000 Expenses       -> Expenditure
--   * Under 3000 Equity         -> Equity (handled separately in Balance Sheet)
-- ============================================================================

-- ═════════════════════════════════════════════════════════════════════════════
-- Fix 1 v2: fn_income_expenditure_fy — anchor on 4000 AND 5000 blocks
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
    -- Anchor roots: both P&L blocks. tab_name='Inc' (4000) and tab_name='Exp' (5000).
    pl_roots AS (
        SELECT sort_path, tab_name
        FROM closing
        WHERE tab_name IN ('Inc', 'Exp')
    ),
    -- Every account strictly under one of the P&L blocks (excludes the block
    -- header rows themselves, which are rollups with no own movement of their own).
    pl_accs AS (
        SELECT c.*, a.mutuality_nature,
               (SELECT pr.tab_name FROM pl_roots pr
                 WHERE c.sort_path LIKE pr.sort_path || '.%'
                 ORDER BY pr.sort_path
                 LIMIT 1) AS block_tab
        FROM closing c
        LEFT JOIN accounts a ON a.id = c.account_id
        WHERE c.own_closing IS NOT NULL
          AND c.own_closing != 0
          AND EXISTS (
              SELECT 1 FROM pl_roots pr
              WHERE c.sort_path LIKE pr.sort_path || '.%'
          )
    ),
    income_accs AS (
        -- Everything under 4000 Income block = Income. Covers SocM/SocC/SocF/
        -- EventT/Holi/Diwali/IntBK/IntSav/IntFD/IncExmpt/IntDue/SellAs/PropInc.
        SELECT 'Income'::VARCHAR AS statement_section,
               pa.account_id::INT AS account_code,
               pa.account_name::VARCHAR AS account_name,
               pa.own_closing::NUMERIC(15,2) AS amount,
               pa.mutuality_nature
        FROM pl_accs pa
        WHERE pa.block_tab = 'Inc'
    ),
    expense_accs AS (
        -- Everything under 5000 Expenses block = Expenditure. Covers all the
        -- 5xxxx leaves AND the 5100 InExp clearing account. For Dr-natured
        -- leaves, own_closing is already negative (Cr-positive convention);
        -- for 5100 InExp (Cr-natured) it's also negative in practice (it
        -- carries the depreciation-transfer Dr entry). Negate for display.
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


-- ═════════════════════════════════════════════════════════════════════════════
-- Fix 2 v2: fn_balance_sheet_fy — ie_surplus anchored on 4000 AND 5000 blocks
--
-- Reserves & Surplus = net movement across the whole P&L subtree, which is
-- the year's net Surplus/Deficit. Under block scheme, that's
-- SUM(own_closing) over everything under 4000 OR 5000.
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
    -- P&L block roots, for ie_surplus below.
    pl_roots AS (
        SELECT sort_path FROM closing WHERE tab_name IN ('Inc', 'Exp')
    ),
    bs_accs AS (
        SELECT c.*, a.mutuality_nature
        FROM closing c
        LEFT JOIN accounts a ON a.id = c.account_id
        CROSS JOIN cap_ac ca
        WHERE c.own_closing IS NOT NULL
          -- Exclude Capital Account's own subtree from the plain Liabilities
          -- list; Capital Account is written separately under Equity below.
          -- ALSO exclude the P&L blocks (4000/5000), whose net is written
          -- as Reserves & Surplus in Equity. Without this, Income accounts
          -- (Cr-natured, 4xxx) would appear as fake Liabilities and Expense
          -- accounts (Dr-natured, 5xxx) as fake Assets.
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
        -- Unconditionally negate own_closing: a genuine negative asset
        -- position (e.g. cash shortfall) shows honestly.
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
    -- Block-COA fix v2: net movement across BOTH P&L blocks (4000 and 5000),
    -- which is the year's net Surplus/Deficit.
    -- Cr-positive convention: income (Cr) adds, expenses (Dr) subtract.
    -- Summing own_closing across both blocks gives the net directly.
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