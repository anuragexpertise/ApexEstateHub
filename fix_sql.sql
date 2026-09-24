-- ============================================================================
-- estatehub_patch_2026_09_24.sql
--
-- Six CREATE OR REPLACE FUNCTION bodies to bring estatehub.sql into line with
-- the block-COA chart of accounts (1000/2000/3000/4000/5000 blocks). Applied
-- standalone against a live DB, or append to estatehub.sql so a fresh
-- reset_database.py install includes them.
--
-- Fixes:
--   1. fn_income_expenditure_fy   — anchor on tab_name IN ('Inc','Exp')
--                                    instead of tab_name = 'CapAc' (which
--                                    no longer contains the P&L under the
--                                    block scheme — returns empty otherwise)
--   2. fn_balance_sheet_fy        — same anchor change for ie_surplus;
--                                    bs_accs also excludes the P&L blocks
--                                    so income/expense accounts don't
--                                    leak into Assets/Liabilities
--   3. fn_resolve_gst_accounts    — tab_name = 'CGST'/'SGST' (was ILIKE
--                                    '%CGST Payable%'/'%SGST Payable%')
--   4. fn_gst_summary_fy          — same CGST/SGST tab_name swap
--   5. fn_sell_vendor_pass        — tab_name = 'SocC' (was ILIKE
--                                    '%Society Charge%')
--   6. fn_resolve_depreciation_account — tab_name = 'Dep' (was ILIKE
--                                    'Depreciation%'); previously declared
--                                    but the base version of the file still
--                                    has the ILIKE form
--
-- Idempotent: CREATE OR REPLACE FUNCTION only; safe to re-run.
-- ============================================================================

-- ────────────────────────────────────────────────────────────────────────────
-- 1. fn_income_expenditure_fy — two-block P&L anchor
-- ────────────────────────────────────────────────────────────────────────────
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
    -- Anchor roots: BOTH P&L top-level blocks. Under the block scheme the
    -- P&L is no longer nested under Capital Account — income lives under
    -- 4000 (tab_name='Inc') and expenses under 5000 (tab_name='Exp').
    -- Anchoring on a single one of these silently drops the other half.
    pl_roots AS (
        SELECT sort_path, tab_name
        FROM closing
        WHERE tab_name IN ('Inc', 'Exp')
    ),
    -- Every account strictly under one of the P&L blocks (excludes the
    -- block header rows themselves, which are rollups with no own movement).
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


-- ────────────────────────────────────────────────────────────────────────────
-- 2. fn_balance_sheet_fy — same two-block anchor for ie_surplus, plus
--    exclusion of the P&L blocks from Assets/Liabilities so income and
--    expense accounts don't mis-classify as balance-sheet lines.
-- ────────────────────────────────────────────────────────────────────────────
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
    -- P&L block roots, for ie_surplus below. tab_name IN ('Inc','Exp').
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
          -- ALSO exclude the P&L blocks (4000/5000): income accounts are
          -- Cr-natured and would show as fake Liabilities; expense accounts
          -- are Dr-natured and would show as fake Assets. Their net is
          -- written once as Reserves & Surplus in Equity (see ie_surplus).
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
    -- Net movement across BOTH P&L blocks = the year's net Surplus/Deficit.
    -- Cr-positive convention: income (Cr) adds, expenses (Dr) subtract.
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


-- ────────────────────────────────────────────────────────────────────────────
-- 3. fn_resolve_gst_accounts — tab_name lookup
-- ────────────────────────────────────────────────────────────────────────────
DROP FUNCTION IF EXISTS fn_resolve_gst_accounts (INT) CASCADE;

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

    RETURN QUERY SELECT v_cgst, v_sgst;
END;
$$;


-- ────────────────────────────────────────────────────────────────────────────
-- 4. fn_gst_summary_fy — same CGST/SGST tab_name swap at the two resolver
--    lookups at the top; the body is otherwise unchanged.
-- ────────────────────────────────────────────────────────────────────────────
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
#variable_conflict use_column
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


-- ────────────────────────────────────────────────────────────────────────────
-- 5. fn_sell_vendor_pass — tab_name = 'SocC' instead of ILIKE match
--    Only the account-resolution line changed; the rest of the body is
--    byte-identical to the file's version.
-- ────────────────────────────────────────────────────────────────────────────
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
            INSERT INTO transactions(
                society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
                amount, mode, status, created_by, created_at, source_table, source_id, journal_id
            ) VALUES (
                v_society_id, 'Cr', p_issued_date, v_acc_id, v_vendor_id, 'vendor', v_desc,
                v_rate, p_mode, 'paid', p_created_by, NOW(), 'receipts', v_receipt_id, v_journal_id
            );

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


-- ────────────────────────────────────────────────────────────────────────────
-- 6. fn_resolve_depreciation_account — tab_name = 'Dep'
-- ────────────────────────────────────────────────────────────────────────────
DROP FUNCTION IF EXISTS fn_resolve_depreciation_account (INT) CASCADE;

CREATE OR REPLACE FUNCTION fn_resolve_depreciation_account(p_society_id INT)
RETURNS INT LANGUAGE plpgsql STABLE AS $$
DECLARE v_acc_id INT;
BEGIN
    SELECT id INTO v_acc_id FROM accounts
     WHERE society_id = p_society_id AND tab_name = 'Dep'
     LIMIT 1;
    RETURN v_acc_id;
END;
$$;

-- End of patch.