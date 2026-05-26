-- =============================================
-- VENDOR FUNCTIONS - Auto Receivables from Passes & Fines
-- =============================================

DROP FUNCTION IF EXISTS fn_vendors_list CASCADE;
DROP FUNCTION IF EXISTS fn_auto_generate_vendor_receivables CASCADE;
DROP FUNCTION IF EXISTS fn_auto_process_vendor_payments CASCADE;

-- =============================================
-- MAIN VENDOR LIST FUNCTION
-- =============================================

CREATE OR REPLACE FUNCTION fn_vendors_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT, 
    email VARCHAR, 
    society_id INT, 
    business_name TEXT, 
    service_type VARCHAR,
    mobile VARCHAR, 
    active BOOLEAN, 
    pending_dues NUMERIC, 
    paid_amount NUMERIC,
    active_passes INT
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    -- Auto trigger receivable generation and payment processing
    PERFORM fn_auto_generate_vendor_receivables(p_society_id);
    PERFORM fn_auto_process_vendor_payments(p_society_id);

    RETURN QUERY
    WITH vendor_data AS (
        SELECT 
            u.id,
            u.email,
            u.society_id,
            COALESCE(v.name, u.email) AS business_name,
            COALESCE(v.service_type, '—') AS service_type,
            COALESCE(v.mobile, '—') AS mobile,
            COALESCE(v.active, TRUE) AS active,
            -- Count active passes
            (SELECT COUNT(*) FROM vendor_passes vp 
             WHERE vp.society_id = u.society_id 
               AND vp.user_id = u.id 
               AND vp.status = 'active' 
               AND vp.valid_until >= CURRENT_DATE) AS active_passes
        FROM users u
        LEFT JOIN vendors v ON v.id = u.linked_id
        WHERE u.society_id = p_society_id 
          AND u.role = 'vendor'
          AND (p_search IS NULL 
               OR v.name ILIKE '%' || p_search || '%' 
               OR u.email ILIKE '%' || p_search || '%')
    ),
    payment_summary AS (
        SELECT 
            p.user_id,
            COALESCE(SUM(CASE WHEN p.status = 'verified' THEN p.amount ELSE 0 END), 0) AS paid_amount,
            COALESCE(SUM(CASE WHEN p.status IN ('pending', 'confirmed') THEN p.amount ELSE 0 END), 0) AS pending_dues
        FROM payments p
        WHERE p.society_id = p_society_id 
          AND p.entity_type = 'vendor'
        GROUP BY p.user_id
    )
    SELECT 
        vd.id, vd.email, vd.society_id, vd.business_name, vd.service_type,
        vd.mobile, vd.active, 
        COALESCE(ps.pending_dues, 0) AS pending_dues,
        COALESCE(ps.paid_amount, 0) AS paid_amount,
        vd.active_passes
    FROM vendor_data vd
    LEFT JOIN payment_summary ps ON ps.user_id = vd.id
    ORDER BY vd.business_name;
END;
$$;

-- =============================================
-- AUTO GENERATE RECEIVABLES FOR VENDORS
-- (From Vendor Passes + Fines)
-- =============================================

CREATE OR REPLACE FUNCTION fn_auto_generate_vendor_receivables(p_society_id INT)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    -- 1. Generate receivables from Active Vendor Passes
    INSERT INTO receivables (
        society_id, entity_id, entity_type, charge_type, description, 
        amount, due_date, status, source_table, source_id, created_at
    )
    SELECT 
        vp.society_id,
        vp.user_id AS entity_id,
        'vendor' AS entity_type,
        'vendor_pass' AS charge_type,
        'Vendor Pass - ' || v.name || ' (' || vp.pass_type || ')' AS description,
        500.00 AS amount,                    -- You can make this dynamic later
        vp.valid_until AS due_date,
        'pending' AS status,
        'vendor_passes' AS source_table,
        vp.id AS source_id,
        NOW()
    FROM vendor_passes vp
    JOIN vendors v ON v.id = (SELECT linked_id FROM users WHERE id = vp.user_id)
    WHERE vp.society_id = p_society_id
      AND vp.status = 'active'
      AND vp.valid_until >= CURRENT_DATE
      AND NOT EXISTS (
          SELECT 1 FROM receivables r 
          WHERE r.source_table = 'vendor_passes' 
            AND r.source_id = vp.id
      );

    -- 2. Generate receivables from Vendor Fines
    INSERT INTO receivables (
        society_id, entity_id, entity_type, charge_type, description, 
        amount, due_date, status, source_table, source_id, created_at
    )
    SELECT 
        vcf.society_id,
        u.id AS entity_id,
        'vendor' AS entity_type,
        'fine' AS charge_type,
        'Fine - ' || v.name || ' (' || vcf.vendor_1day || ' / ' || vcf.vendor_7day || ')' AS description,
        COALESCE(vcf.vendor_fine, 0) AS amount,
        CURRENT_DATE AS due_date,
        'pending' AS status,
        'ven_charges_fines' AS source_table,
        vcf.id AS source_id,
        NOW()
    FROM ven_charges_fines vcf
    JOIN vendors v ON v.id = vcf.ven_id
    JOIN users u ON u.linked_id = v.id AND u.role = 'vendor'
    WHERE vcf.society_id = p_society_id 
      AND vcf.ven_status = TRUE
      AND COALESCE(vcf.vendor_fine, 0) > 0
      AND NOT EXISTS (
          SELECT 1 FROM receivables r 
          WHERE r.source_table = 'ven_charges_fines' 
            AND r.source_id = vcf.id
      )
    ON CONFLICT DO NOTHING;
END;
$$;

-- =============================================
-- AUTO PROCESS VERIFIED PAYMENTS FOR VENDORS
-- (Creates Receipts + Handles Partial Payments)
-- =============================================

CREATE OR REPLACE FUNCTION fn_auto_process_vendor_payments(p_society_id INT)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    rec_payment RECORD;
    remaining_amount NUMERIC;
    rec_receivable RECORD;
BEGIN
    FOR rec_payment IN 
        SELECT * FROM payments p
        WHERE p.society_id = p_society_id 
          AND p.entity_type = 'vendor'
          AND p.status = 'verified'
          AND NOT EXISTS (
              SELECT 1 FROM receipts r 
              WHERE r.transaction_id = p.transaction_id
          )
    LOOP
        -- Create Receipt
        INSERT INTO receipts (
            society_id, user_id, entity_id, entity_type, receipt_date, acc_id,
            particulars, amount, mode, transaction_id, status, 
            confirmed_by, confirmed_at, created_at
        )
        VALUES (
            rec_payment.society_id,
            rec_payment.confirmed_by,
            rec_payment.entity_id,
            rec_payment.entity_type,
            COALESCE(rec_payment.paid_at::DATE, CURRENT_DATE),
            1,  -- Default account
            'Vendor Payment - ' || (SELECT name FROM vendors WHERE id = (SELECT linked_id FROM users WHERE id = rec_payment.entity_id)),
            rec_payment.amount,
            COALESCE(rec_payment.payment_method, 'cash'),
            rec_payment.transaction_id,
            'confirmed',
            rec_payment.confirmed_by,
            rec_payment.confirmed_at,
            NOW()
        );

        -- Apply to pending receivables (Partial Payment Logic)
        remaining_amount := rec_payment.amount;

        FOR rec_receivable IN 
            SELECT * FROM receivables r
            WHERE r.society_id = p_society_id
              AND r.entity_id = rec_payment.entity_id
              AND r.entity_type = 'vendor'
              AND r.status = 'pending'
            ORDER BY r.due_date ASC, r.id ASC
        LOOP
            IF remaining_amount <= 0 THEN EXIT; END IF;

            IF rec_receivable.amount <= remaining_amount THEN
                UPDATE receivables 
                SET status = 'confirmed',
                    confirmed_by = rec_payment.confirmed_by,
                    confirmed_at = rec_payment.confirmed_at
                WHERE id = rec_receivable.id;

                remaining_amount := remaining_amount - rec_receivable.amount;
            ELSE
                -- Partial payment
                UPDATE receivables 
                SET amount = rec_receivable.amount - remaining_amount
                WHERE id = rec_receivable.id;

                remaining_amount := 0;
            END IF;
        END LOOP;
    END LOOP;
END;
$$;

-- =============================================
-- USAGE EXAMPLES
-- =============================================
/*
SELECT * FROM fn_vendors_list(1, NULL);           -- All vendors
SELECT * FROM fn_vendors_list(1, 'ABC');          -- Search

-- Manual triggers
SELECT fn_auto_generate_vendor_receivables(1);
SELECT fn_auto_process_vendor_payments(1);
*/