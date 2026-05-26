-- =============================================
-- VIEW ESTATE HUB - Enhanced Payment & Receipt Automation
-- Supports Partial Payments + Smart Matching
-- =============================================

DROP FUNCTION IF EXISTS fn_apartments_list CASCADE;
DROP FUNCTION IF EXISTS fn_auto_generate_receivables CASCADE;
DROP FUNCTION IF EXISTS fn_auto_process_verified_payments CASCADE;

-- =============================================
-- MAIN LIST FUNCTION (Auto Triggers Processing)
-- =============================================

CREATE OR REPLACE FUNCTION fn_apartments_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL,
    p_has_dues BOOLEAN DEFAULT NULL
)
RETURNS TABLE (
    id INT, flat_number VARCHAR, owner_name VARCHAR, mobile VARCHAR,
    apartment_size INT, active BOOLEAN, society_id INT, months_due BIGINT,
    total_maintenance NUMERIC, paid_amount NUMERIC, pending_amount NUMERIC,
    late_fee NUMERIC, grand_total NUMERIC
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM fn_auto_generate_receivables(p_society_id);
    PERFORM fn_auto_process_verified_payments(p_society_id);

    RETURN QUERY
    -- (Same logic as previous version - kept concise)
    WITH apartment_base AS (
        SELECT a.id, a.flat_number, a.owner_name, a.mobile, a.apartment_size, a.active, a.society_id,
               COALESCE(acf.apt_maintenance_rate, 3.0) AS rate_per_sqft,
               acf.start_date
        FROM apartments a
        LEFT JOIN apt_charges_fines acf ON acf.apt_id = a.id AND acf.apt_status = TRUE
        WHERE a.society_id = p_society_id
          AND (p_search IS NULL OR a.flat_number ILIKE '%'||p_search||'%' OR a.owner_name ILIKE '%'||p_search||'%')
    ),
    maintenance_calc AS (
        SELECT *, GREATEST(EXTRACT(YEAR FROM AGE(CURRENT_DATE, COALESCE(start_date, CURRENT_DATE)))*12 +
                           EXTRACT(MONTH FROM AGE(CURRENT_DATE, COALESCE(start_date, CURRENT_DATE))), 0) AS months_due
        FROM apartment_base
    ),
    payments_summary AS (
        SELECT entity_id AS apartment_id,
               SUM(CASE WHEN status='verified' THEN amount ELSE 0 END) AS paid_amount,
               SUM(CASE WHEN status IN ('pending','confirmed') THEN amount ELSE 0 END) AS pending_amount
        FROM payments WHERE society_id = p_society_id AND entity_type = 'apartment'
        GROUP BY entity_id
    ),
    late_fee_calc AS (
        SELECT entity_id AS apartment_id,
               SUM(CASE WHEN due_date < CURRENT_DATE THEN amount * 0.02 * GREATEST(EXTRACT(DAY FROM AGE(CURRENT_DATE, due_date)),0)/30 ELSE 0 END) AS late_fee
        FROM payments 
        WHERE society_id = p_society_id AND entity_type = 'apartment' AND status IN ('pending','confirmed')
        GROUP BY entity_id
    )
    SELECT 
        mc.id, mc.flat_number, mc.owner_name, mc.mobile, mc.apartment_size, mc.active, mc.society_id,
        mc.months_due::BIGINT,
        (mc.apartment_size * mc.rate_per_sqft * GREATEST(mc.months_due, 0)) AS total_maintenance,
        COALESCE(ps.paid_amount, 0), COALESCE(ps.pending_amount, 0),
        COALESCE(lf.late_fee, 0),
        (mc.apartment_size * mc.rate_per_sqft * GREATEST(mc.months_due, 0) - COALESCE(ps.paid_amount, 0) + COALESCE(lf.late_fee, 0)) AS grand_total
    FROM maintenance_calc mc
    LEFT JOIN payments_summary ps ON ps.apartment_id = mc.id
    LEFT JOIN late_fee_calc lf ON lf.apartment_id = mc.id
    WHERE (p_has_dues IS NULL OR 
          (p_has_dues AND (COALESCE(ps.pending_amount,0) + COALESCE(lf.late_fee,0)) > 0) OR
          (NOT p_has_dues AND (COALESCE(ps.pending_amount,0) + COALESCE(lf.late_fee,0)) = 0))
    ORDER BY mc.flat_number;
END;
$$;

-- =============================================
-- AUTO GENERATE RECEIVABLES
-- =============================================

CREATE OR REPLACE FUNCTION fn_auto_generate_receivables(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO receivables (society_id, entity_id, entity_type, charge_type, description, 
                             amount, due_date, status, source_table, source_id, created_at)
    SELECT 
        acf.society_id, acf.apt_id, 'apartment', 'maintenance',
        'Maintenance - ' || a.flat_number,
        (a.apartment_size * acf.apt_maintenance_rate)::NUMERIC,
        (DATE_TRUNC('month', CURRENT_DATE) + (COALESCE(acf.apt_due_day, 10)-1) || ' days')::DATE,
        'pending', 'apt_charges_fines', acf.id, NOW()
    FROM apt_charges_fines acf
    JOIN apartments a ON a.id = acf.apt_id
    WHERE acf.society_id = p_society_id AND acf.apt_status = TRUE
      AND NOT EXISTS (SELECT 1 FROM receivables r 
                      WHERE r.source_table = 'apt_charges_fines' AND r.source_id = acf.id);
END;
$$;

-- =============================================
-- AUTO RECEIPT GENERATION + PARTIAL PAYMENT HANDLING
-- =============================================

CREATE OR REPLACE FUNCTION fn_auto_process_verified_payments(p_society_id INT)
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
          AND p.status = 'verified'
          AND NOT EXISTS (
              SELECT 1 FROM receipts r 
              WHERE r.transaction_id = p.transaction_id 
                 OR (r.entity_id = p.entity_id 
                     AND r.entity_type = p.entity_type 
                     AND r.amount = p.amount 
                     AND r.receipt_date = COALESCE(p.paid_at::DATE, CURRENT_DATE))
          )
    LOOP
        -- 1. Create Receipt for the verified payment
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
            1,  -- Default Cash/Bank Account ID (customize as needed)
            'Payment Received - ' || 
                CASE 
                    WHEN rec_payment.entity_type = 'apartment' THEN 'Flat ' || (SELECT flat_number FROM apartments WHERE id = rec_payment.entity_id)
                    WHEN rec_payment.entity_type = 'vendor' THEN (SELECT name FROM vendors WHERE id = rec_payment.entity_id)
                    WHEN rec_payment.entity_type = 'security' THEN (SELECT name FROM security_staff WHERE id = rec_payment.entity_id)
                    ELSE 'Entity #' || rec_payment.entity_id 
                END,
            rec_payment.amount,
            COALESCE(rec_payment.payment_method, 'cash'),
            rec_payment.transaction_id,
            'confirmed',
            rec_payment.confirmed_by,
            rec_payment.confirmed_at,
            NOW()
        );

        -- 2. Apply Payment to Pending Receivables (Partial Payment Support)
        remaining_amount := rec_payment.amount;

        FOR rec_receivable IN 
            SELECT * FROM receivables r
            WHERE r.society_id = p_society_id
              AND r.entity_id = rec_payment.entity_id
              AND r.entity_type = rec_payment.entity_type
              AND r.status = 'pending'
            ORDER BY r.due_date ASC, r.id ASC  -- FIFO by due date
        LOOP
            IF remaining_amount <= 0 THEN EXIT; END IF;

            IF rec_receivable.amount <= remaining_amount THEN
                -- Full settlement of this receivable
                UPDATE receivables 
                SET status = 'confirmed',
                    confirmed_by = rec_payment.confirmed_by,
                    confirmed_at = rec_payment.confirmed_at
                WHERE id = rec_receivable.id;

                remaining_amount := remaining_amount - rec_receivable.amount;
            ELSE
                -- Partial payment - reduce receivable amount
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
-- USAGE
-- =============================================
/*
SELECT * FROM fn_apartments_list(1);                    -- Auto everything
SELECT fn_auto_process_verified_payments(1);            -- Manual run
*/