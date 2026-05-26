-- =============================================
-- ASSET MANAGEMENT - INTEGRATED WITH ACCOUNTS TABLE
-- =============================================

-- =============================================
-- 1. SET DEPRECIATION FROM ACCOUNT (Recommended)
-- =============================================

CREATE OR REPLACE FUNCTION fn_asset_set_from_account(
    p_asset_id INT,
    p_account_id INT
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_acc RECORD;
    v_asset_name VARCHAR;
BEGIN
    SELECT name, depreciation_percent, is_depreciable 
    INTO v_acc 
    FROM accounts 
    WHERE id = p_account_id;

    IF NOT FOUND THEN
        RETURN 'Error: Account not found';
    END IF;

    IF NOT v_acc.is_depreciable THEN
        RETURN 'Warning: Selected account is not marked as depreciable';
    END IF;

    SELECT asset_name INTO v_asset_name 
    FROM asset_register WHERE id = p_asset_id;

    UPDATE asset_register 
    SET parent_account_id = p_account_id,
        depreciation_rate = v_acc.depreciation_percent,
        last_depreciation_date = NULL
    WHERE id = p_asset_id;

    RETURN 'Asset "' || v_asset_name || '" linked to account "' || v_acc.name || 
           '" with ' || v_acc.depreciation_percent || '% depreciation';
END;
$$;

-- =============================================
-- 2. ENHANCED ASSET LIST (Using Account Settings)
-- =============================================

CREATE OR REPLACE FUNCTION fn_asset_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT,
    asset_name VARCHAR,
    purchase_value NUMERIC,
    purchase_date DATE,
    account_name VARCHAR,
    depreciation_rate DECIMAL(5,2),
    expense_portion NUMERIC,
    asset_portion NUMERIC,
    current_book_value NUMERIC,
    status TEXT
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM fn_calculate_asset_depreciation(p_society_id);

    RETURN QUERY
    SELECT 
        ar.id,
        ar.asset_name,
        ar.purchase_value,
        ar.purchase_date,
        COALESCE(acc.name, '—') AS account_name,
        COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10.00) AS depreciation_rate,
        -- Expense Portion
        CASE 
            WHEN COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) = 100 
                THEN ar.purchase_value
            WHEN EXTRACT(MONTH FROM ar.purchase_date) >= 9 
                THEN ar.purchase_value * (COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) / 100) * 0.5
            ELSE ar.purchase_value * (COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) / 100)
        END AS expense_portion,
        -- Asset Portion (Balance Sheet)
        GREATEST(
            ar.purchase_value * (1 - COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) / 100), 
            0
        ) AS asset_portion,
        GREATEST(
            ar.purchase_value * (1 - COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) / 100), 
            0
        ) AS current_book_value,
        CASE 
            WHEN COALESCE(ar.depreciation_rate, acc.depreciation_percent, 10) = 100 THEN 'FULLY EXPENSED'
            ELSE 'ACTIVE'
        END AS status
    FROM asset_register ar
    LEFT JOIN accounts acc ON acc.id = ar.parent_account_id
    WHERE ar.society_id = p_society_id
      AND (p_search IS NULL OR ar.asset_name ILIKE '%' || p_search || '%')
    ORDER BY ar.purchase_date DESC;
END;
$$;

-- =============================================
-- 3. DEPRECIATION CALCULATION (Using Account Settings)
-- =============================================

CREATE OR REPLACE FUNCTION fn_calculate_asset_depreciation(p_society_id INT)
RETURNS VOID
LANGUAGE plpgsql AS $$
DECLARE
    rec RECORD;
    dep_rate DECIMAL(5,2);
    expense_amount NUMERIC;
    half_year_rule BOOLEAN;
BEGIN
    FOR rec IN 
        SELECT ar.*, COALESCE(acc.depreciation_percent, ar.depreciation_rate, 10) AS final_rate
        FROM asset_register ar
        LEFT JOIN accounts acc ON acc.id = ar.parent_account_id
        WHERE ar.society_id = p_society_id 
          AND (ar.last_depreciation_date IS NULL OR ar.last_depreciation_date < CURRENT_DATE - INTERVAL '25 days')
    LOOP
        dep_rate := rec.final_rate;

        IF dep_rate = 100 THEN
            expense_amount := rec.purchase_value;
        ELSE
            half_year_rule := (EXTRACT(MONTH FROM rec.purchase_date) >= 9);
            IF half_year_rule THEN
                expense_amount := rec.purchase_value * (dep_rate / 100) * 0.5;
            ELSE
                expense_amount := rec.purchase_value * (dep_rate / 100);
            END IF;
        END IF;

        INSERT INTO expenses (
            society_id, user_id, entity_id, entity_type, expense_date, 
            acc_id, particulars, amount, mode, status, created_at
        )
        VALUES (
            p_society_id, 1, rec.id, 'asset', CURRENT_DATE, 
            COALESCE(rec.parent_account_id, 5),
            'Depreciation - ' || rec.asset_name 
                || CASE WHEN half_year_rule THEN ' (Half Year)' ELSE '' END,
            expense_amount, 'cash', 'pending', NOW()
        );

        UPDATE asset_register 
        SET last_depreciation_date = CURRENT_DATE 
        WHERE id = rec.id;
    END LOOP;
END;
$$;

-- =============================================
-- USAGE EXAMPLES
-- =============================================
/*
-- Link asset to account (Recommended)
SELECT fn_asset_set_from_account(5, 42);     -- Asset ID 5 → Account ID 42

-- View all assets with account-linked depreciation
SELECT * FROM fn_asset_list(1);

-- Run depreciation
SELECT fn_calculate_asset_depreciation(1);
*/