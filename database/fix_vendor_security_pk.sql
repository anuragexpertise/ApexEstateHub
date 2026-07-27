-- ============================================================================
-- MIGRATION: vendor/security pk consistency
--
-- Makes fn_vendors_list.id = vendors.id and fn_security_list.id =
-- security_staff.id, matching the convention already used everywhere else
-- in the app (apartments.id, accounts.id, concerns.id, assets.id, ...) and
-- already used by receivables/payables/receipts/expenses.entity_id for
-- role='vendor'/'security' (confirmed via their JOIN conditions, e.g.
-- `LEFT JOIN vendors v ON v.id = r.entity_id AND r.role='vendor'`).
--
-- Before this, fn_vendors_list/fn_security_list returned users.id as `id`
-- — an outlier convention that several places in the app (the vendor-pass
-- sale flow, portal self-scoping) had already worked around with explicit
-- comments explaining the mismatch. This migration removes the need for
-- those workarounds; the accompanying Python patch updates them.
--
-- Both functions also now return `user_id` (the linked login's users.id)
-- as a separate column, for the handful of places that genuinely need the
-- login identity specifically (QR encoding, vendor_passes.user_id,
-- gate_access.entity_id) rather than the domain entity id.
-- ============================================================================

DROP FUNCTION IF EXISTS fn_vendors_list CASCADE;

CREATE OR REPLACE FUNCTION fn_vendors_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL,
    p_has_passes BOOLEAN DEFAULT NULL
)
RETURNS TABLE (
    id INT, user_id INT, email VARCHAR(100), society_id INT, name VARCHAR(100),
    business_name VARCHAR(100), service_type VARCHAR(100), mobile VARCHAR(15), active BOOLEAN,
    pass_expiry DATE, gate_pass BOOLEAN, active_passes INT
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        v.id::INT, u.id::INT, u.email::VARCHAR(100), v.society_id::INT,
        COALESCE(v.name, u.email, 'Vendor #'||v.id)::VARCHAR(100),
        v.business_name::VARCHAR(100),
        COALESCE(v.service_type,'—')::VARCHAR(100),
        COALESCE(v.mobile,'—')::VARCHAR(15),
        COALESCE(v.active,TRUE)::BOOLEAN,
        COALESCE(pass.pass_expiry, p_pass_max.expiry)::DATE,
        COALESCE(pass.pass_expiry >= CURRENT_DATE, FALSE),
        (COALESCE(pass.active_passes, 0))::INT
    FROM vendors v
    LEFT JOIN users u ON u.linked_id = v.id AND u.role = 'vendor'
    LEFT JOIN LATERAL (
        SELECT MAX(valid_until) AS pass_expiry,
               COUNT(*)::INT   AS active_passes
        FROM vendor_passes vp
        WHERE vp.user_id = u.id
          AND vp.status = 'active'
          AND vp.valid_until >= CURRENT_DATE
    ) pass ON TRUE
    LEFT JOIN LATERAL (
        SELECT MAX(valid_until) AS expiry
        FROM vendor_passes vp2
        WHERE vp2.user_id = u.id AND vp2.status = 'active'
    ) p_pass_max ON TRUE
    WHERE v.society_id = p_society_id
      AND (p_search IS NULL OR v.name ILIKE '%'||p_search||'%' OR u.email ILIKE '%'||p_search||'%')
      AND (p_has_passes IS NULL
           OR (p_has_passes AND COALESCE(pass.active_passes, 0) > 0)
           OR (NOT p_has_passes AND COALESCE(pass.active_passes, 0) <= 0))
    ORDER BY v.name;
END;
$$;

DROP FUNCTION IF EXISTS fn_security_list CASCADE;

CREATE OR REPLACE FUNCTION fn_security_list(p_society_id INT, p_search TEXT DEFAULT NULL)
RETURNS TABLE (
    id INT, user_id INT, email VARCHAR(100), society_id INT, name VARCHAR(100),
    shift VARCHAR(20), mobile VARCHAR(15), active BOOLEAN, salary_per_shift NUMERIC(10,2),
    joining_date DATE, shift_count BIGINT, salary_due NUMERIC(15,2), salary_paid NUMERIC(15,2), gate_pass BOOLEAN
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM fn_auto_generate_payables(p_society_id);
    RETURN QUERY
    WITH pay_sum AS (
        SELECT entity_id AS staff_id,
            COUNT(*)::BIGINT AS shifts_completed,
            COALESCE(SUM(amount) FILTER (WHERE status='pending'), 0)::NUMERIC(15,2) AS salary_due,
            COALESCE(SUM(amount) FILTER (WHERE status='verified'), 0)::NUMERIC(15,2) AS salary_paid
        FROM payables p WHERE p.society_id = p_society_id AND p.role = 'security' GROUP BY entity_id
    )
    SELECT
        s.id::INT, u.id::INT, u.email::VARCHAR(100), s.society_id::INT,
        COALESCE(s.name, u.email, 'Security #'||s.id)::VARCHAR(100), COALESCE(s.shift,'—')::VARCHAR(20),
        COALESCE(s.mobile,'—')::VARCHAR(15), COALESCE(s.active,TRUE)::BOOLEAN,
        COALESCE(s.salary_per_shift,0)::NUMERIC(10,2), s.joining_date::DATE,
        COALESCE(ps.shifts_completed, 0)::BIGINT AS shift_count,
        COALESCE(ps.salary_due, 0)::NUMERIC(15,2), COALESCE(ps.salary_paid, 0)::NUMERIC(15,2),
        EXISTS(SELECT 1 FROM gate_access ga WHERE ga.entity_id=u.id AND ga.role='s' AND ga.time_out IS NULL)::BOOLEAN AS gate_pass
    FROM security_staff s
    LEFT JOIN users u ON u.linked_id = s.id AND u.role = 'security'
    LEFT JOIN pay_sum ps ON ps.staff_id = s.id
    WHERE s.society_id = p_society_id
      AND (p_search IS NULL OR s.name ILIKE '%'||p_search||'%')
    ORDER BY s.name;
END;
$$;
