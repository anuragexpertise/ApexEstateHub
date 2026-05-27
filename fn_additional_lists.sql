-- =============================================
-- EVENTS LIST & PROFILE FUNCTIONS
-- =============================================

DROP FUNCTION IF EXISTS fn_events_list CASCADE;
DROP FUNCTION IF EXISTS fn_event_profile CASCADE;

CREATE OR REPLACE FUNCTION fn_events_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL,
    p_status VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id INT, title VARCHAR, description TEXT, event_date DATE,
    event_time VARCHAR, venue VARCHAR, open_to VARCHAR,
    attendees_count INT, created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT 
        e.id, e.title, e.description, e.event_date, e.event_time, e.venue, e.open_to,
        0::INT AS attendees_count,  -- TODO: Add attendees table
        e.created_at
    FROM events e
    WHERE e.society_id = p_society_id
      AND (p_search IS NULL OR e.title ILIKE '%'||p_search||'%')
      AND e.event_date >= CURRENT_DATE
    ORDER BY e.event_date ASC;
END;
$$;

CREATE OR REPLACE FUNCTION fn_event_profile(p_event_id INT)
RETURNS TABLE (
    id INT, society_id INT, title VARCHAR, description TEXT,
    event_date DATE, event_time VARCHAR, venue VARCHAR, open_to VARCHAR,
    created_at TIMESTAMP, subtitle VARCHAR
)
LANGUAGE SQL STABLE AS $$
    SELECT 
        id, society_id, title, description, event_date, event_time, venue, open_to,
        created_at,
        (event_date || ' ' || COALESCE(event_time, '')) AS subtitle
    FROM events
    WHERE id = p_event_id;
$$;

-- =============================================
-- CONCERNS LIST & PROFILE FUNCTIONS
-- =============================================

DROP FUNCTION IF EXISTS fn_concerns_list CASCADE;
DROP FUNCTION IF EXISTS fn_concern_profile CASCADE;

CREATE OR REPLACE FUNCTION fn_concerns_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL,
    p_status VARCHAR DEFAULT 'open'
)
RETURNS TABLE (
    id INT, flat_no VARCHAR, concern_type VARCHAR, description TEXT,
    status VARCHAR, assigned_to VARCHAR, priority VARCHAR, created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.id, c.flat_no, c.concern_type, c.description, c.status, c.assigned_to,
        CASE 
            WHEN c.status = 'resolved' THEN 'Low'
            WHEN EXTRACT(DAY FROM AGE(CURRENT_DATE, c.created_at)) > 7 THEN 'High'
            ELSE 'Medium'
        END AS priority,
        c.created_at
    FROM concerns c
    WHERE c.society_id = p_society_id
      AND (p_status IS NULL OR c.status = p_status)
      AND (p_search IS NULL OR c.flat_no ILIKE '%'||p_search||'%' 
           OR c.description ILIKE '%'||p_search||'%')
    ORDER BY 
        CASE WHEN c.status = 'open' THEN 0 ELSE 1 END,
        c.created_at DESC;
END;
$$;

CREATE OR REPLACE FUNCTION fn_concern_profile(p_concern_id INT)
RETURNS TABLE (
    id INT, society_id INT, flat_no VARCHAR, concern_type VARCHAR,
    description TEXT, status VARCHAR, assigned_to VARCHAR, preferred_time VARCHAR,
    days_open BIGINT, created_at TIMESTAMP, subtitle VARCHAR
)
LANGUAGE SQL STABLE AS $$
    SELECT 
        id, society_id, flat_no, concern_type, description, status,
        assigned_to, preferred_time,
        EXTRACT(DAY FROM AGE(CURRENT_DATE, created_at))::BIGINT AS days_open,
        created_at,
        'Flat ' || flat_no || ' - ' || concern_type AS subtitle
    FROM concerns
    WHERE id = p_concern_id;
$$;

-- =============================================
-- ACCOUNTS LIST & PROFILE FUNCTIONS
-- =============================================

DROP FUNCTION IF EXISTS fn_accounts_list CASCADE;
DROP FUNCTION IF EXISTS fn_account_profile CASCADE;

CREATE OR REPLACE FUNCTION fn_accounts_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL,
    p_tab_name VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id INT, name VARCHAR, tab_name VARCHAR, header VARCHAR,
    drcr_account VARCHAR, bf_amount NUMERIC, current_balance NUMERIC,
    transaction_count INT, parent_account_name VARCHAR
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    WITH account_balance AS (
        SELECT 
            a.id,
            a.name,
            a.tab_name,
            a.header,
            a.drcr_account,
            a.bf_amount,
            COALESCE(SUM(
                CASE 
                    WHEN a.drcr_account = 'Cr' THEN t.amount
                    WHEN a.drcr_account = 'Dr' THEN -t.amount
                    ELSE 0
                END
            ), 0) + a.bf_amount AS current_balance,
            COUNT(t.id) AS transaction_count,
            COALESCE(p.name, '—') AS parent_account_name
        FROM accounts a
        LEFT JOIN accounts p ON p.id = a.parent_account_id
        LEFT JOIN transactions t ON t.acc_id = a.id AND t.status = 'paid'
        WHERE a.society_id = p_society_id
          AND (p_tab_name IS NULL OR a.tab_name = p_tab_name)
          AND (p_search IS NULL OR a.name ILIKE '%'||p_search||'%')
        GROUP BY a.id, a.name, a.tab_name, a.header, a.drcr_account,
                 a.bf_amount, p.name
    )
    SELECT * FROM account_balance
    ORDER BY tab_name, name;
END;
$$;

CREATE OR REPLACE FUNCTION fn_account_profile(p_account_id INT)
RETURNS TABLE (
    id INT, society_id INT, name VARCHAR, tab_name VARCHAR, header VARCHAR,
    drcr_account VARCHAR, bf_amount NUMERIC, depreciation_percent NUMERIC,
    is_depreciable BOOLEAN, parent_account_name VARCHAR, current_balance NUMERIC,
    created_at TIMESTAMP
)
LANGUAGE SQL STABLE AS $$
    SELECT 
        a.id, a.society_id, a.name, a.tab_name, a.header, a.drcr_account,
        a.bf_amount, a.depreciation_percent, a.is_depreciable,
        COALESCE(p.name, '—') AS parent_account_name,
        COALESCE(SUM(
            CASE WHEN a.drcr_account = 'Cr' THEN t.amount
                 ELSE -t.amount END
        ), 0) + a.bf_amount AS current_balance,
        a.created_at
    FROM accounts a
    LEFT JOIN accounts p ON p.id = a.parent_account_id
    LEFT JOIN transactions t ON t.acc_id = a.id AND t.status = 'paid'
    WHERE a.id = p_account_id
    GROUP BY a.id, a.society_id, a.name, a.tab_name, a.header, a.drcr_account,
             a.bf_amount, a.depreciation_percent, a.is_depreciable, p.name, a.created_at;
$$;

-- =============================================
-- SOCIETIES LIST & PROFILE FUNCTIONS
-- =============================================

DROP FUNCTION IF EXISTS fn_societies_list CASCADE;
DROP FUNCTION IF EXISTS fn_society_profile CASCADE;

CREATE OR REPLACE FUNCTION fn_societies_list(
    p_search TEXT DEFAULT NULL,
    p_plan VARCHAR DEFAULT NULL,
    p_status VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id INT, name VARCHAR, email VARCHAR, phone VARCHAR, plan VARCHAR,
    plan_status VARCHAR, plan_validity DATE, total_apartments INT,
    total_users INT, total_receivables NUMERIC, created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.id, s.name, s.email, s.phone, s.plan,
        CASE 
            WHEN s.plan = 'Free' THEN 'Free'
            WHEN s.plan_validity >= CURRENT_DATE THEN 'Active'
            ELSE 'Expired'
        END AS plan_status,
        s.plan_validity,
        (SELECT COUNT(*) FROM apartments WHERE society_id = s.id AND active = TRUE),
        (SELECT COUNT(*) FROM users WHERE society_id = s.id),
        (SELECT COALESCE(SUM(amount), 0) FROM receivables WHERE society_id = s.id AND status = 'pending'),
        s.created_at
    FROM societies s
    WHERE (p_search IS NULL OR s.name ILIKE '%'||p_search||'%')
      AND (p_plan IS NULL OR s.plan = p_plan)
      AND (p_status IS NULL OR 
           (p_status = 'active' AND s.plan_validity >= CURRENT_DATE) OR
           (p_status = 'expired' AND s.plan_validity < CURRENT_DATE))
    ORDER BY s.name;
END;
$$;

CREATE OR REPLACE FUNCTION fn_society_profile(p_society_id INT)
RETURNS TABLE (
    id INT, name VARCHAR, logo VARCHAR, login_background VARCHAR,
    email VARCHAR, phone VARCHAR, address TEXT, plan VARCHAR,
    plan_status VARCHAR, plan_validity DATE, arrear_start_date DATE,
    secretary_name VARCHAR, secretary_phone VARCHAR, secretary_sign VARCHAR,
    total_apartments INT, total_vendors INT, total_security INT,
    total_users INT, total_receivables NUMERIC, created_at TIMESTAMP,
    _image_society_id INT
)
LANGUAGE SQL STABLE AS $$
    SELECT 
        s.id, s.name, s.logo, s.login_background, s.email, s.phone, s.address,
        s.plan,
        CASE 
            WHEN s.plan = 'Free' THEN 'Free'
            WHEN s.plan_validity >= CURRENT_DATE THEN 'Active'
            ELSE 'Expired'
        END AS plan_status,
        s.plan_validity, s.arrear_start_date,
        s.secretary_name, s.secretary_phone, s.secretary_sign,
        (SELECT COUNT(*) FROM apartments WHERE society_id = s.id),
        (SELECT COUNT(*) FROM vendors WHERE society_id = s.id),
        (SELECT COUNT(*) FROM security_staff WHERE society_id = s.id),
        (SELECT COUNT(*) FROM users WHERE society_id = s.id),
        (SELECT COALESCE(SUM(amount), 0) FROM receivables WHERE society_id = s.id AND status = 'pending'),
        s.created_at,
        s.id AS _image_society_id
    FROM societies s
    WHERE s.id = p_society_id;
$$;

-- =============================================
-- RECEIVABLES LIST & PROFILE FUNCTIONS
-- =============================================

DROP FUNCTION IF EXISTS fn_receivables_list CASCADE;
DROP FUNCTION IF EXISTS fn_receivable_profile CASCADE;

CREATE OR REPLACE FUNCTION fn_receivables_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL,
    p_status VARCHAR DEFAULT 'pending'
)
RETURNS TABLE (
    id INT, entity_type VARCHAR, entity_id INT, entity_name VARCHAR,
    charge_type VARCHAR, description TEXT, amount NUMERIC, due_date DATE,
    status VARCHAR, days_overdue INT, created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    WITH entity_names AS (
        SELECT 
            r.id,
            CASE 
                WHEN r.entity_type = 'apartment' THEN 'Flat ' || (SELECT flat_number FROM apartments WHERE id = r.entity_id)
                WHEN r.entity_type = 'vendor' THEN (SELECT name FROM vendors WHERE id = (SELECT linked_id FROM users WHERE id = r.entity_id))
                WHEN r.entity_type = 'security' THEN (SELECT name FROM security_staff WHERE id = (SELECT linked_id FROM users WHERE id = r.entity_id))
                ELSE 'Entity #' || r.entity_id
            END AS entity_name,
            r.entity_type, r.entity_id, r.charge_type, r.description, r.amount,
            r.due_date, r.status,
            EXTRACT(DAY FROM AGE(CURRENT_DATE, r.due_date))::INT AS days_overdue,
            r.created_at
        FROM receivables r
        WHERE r.society_id = p_society_id
          AND (p_status IS NULL OR r.status = p_status)
          AND (p_search IS NULL OR r.description ILIKE '%'||p_search||'%')
    )
    SELECT * FROM entity_names
    ORDER BY due_date ASC, created_at DESC;
END;
$$;

CREATE OR REPLACE FUNCTION fn_receivable_profile(p_receivable_id INT)
RETURNS TABLE (
    id INT, society_id INT, entity_type VARCHAR, entity_id INT,
    charge_type VARCHAR, description TEXT, amount NUMERIC,
    due_date DATE, status VARCHAR, source_table VARCHAR, source_id INT,
    confirmed_by INT, confirmed_at TIMESTAMP, created_at TIMESTAMP,
    days_overdue INT
)
LANGUAGE SQL STABLE AS $$
    SELECT 
        id, society_id, entity_type, entity_id, charge_type, description,
        amount, due_date, status, source_table, source_id, confirmed_by,
        confirmed_at, created_at,
        EXTRACT(DAY FROM AGE(CURRENT_DATE, due_date))::INT AS days_overdue
    FROM receivables
    WHERE id = p_receivable_id;
$$;

-- =============================================
-- CASHBOOK VIEW FUNCTIONS
-- =============================================

DROP FUNCTION IF EXISTS fn_cashbook_list CASCADE;

CREATE OR REPLACE FUNCTION fn_cashbook_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL,
    p_start_date DATE DEFAULT NULL,
    p_end_date DATE DEFAULT NULL
)
RETURNS TABLE (
    id INT, trx_date DATE, account_name VARCHAR, account_group VARCHAR,
    particulars VARCHAR, debit NUMERIC, credit NUMERIC, balance NUMERIC,
    mode VARCHAR, created_at TIMESTAMP
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_opening_balance NUMERIC;
BEGIN
    -- Get opening balance
    SELECT COALESCE(SUM(
        CASE 
            WHEN drcr_bf = 'Cr' THEN bf_amount
            ELSE -bf_amount
        END
    ), 0)
    INTO v_opening_balance
    FROM accounts
    WHERE society_id = p_society_id;

    RETURN QUERY
    WITH ordered_transactions AS (
        SELECT 
            t.id, t.trx_date, a.name AS account_name, a.tab_name AS account_group,
            t.acc_particulars, t.amount, t.mode, t.created_at,
            CASE WHEN a.drcr_account = 'Dr' THEN t.amount ELSE NULL::NUMERIC END AS debit,
            CASE WHEN a.drcr_account = 'Cr' THEN t.amount ELSE NULL::NUMERIC END AS credit,
            ROW_NUMBER() OVER (ORDER BY t.trx_date ASC, t.id ASC) AS row_num
        FROM transactions t
        JOIN accounts a ON a.id = t.acc_id
        WHERE t.society_id = p_society_id
          AND t.status = 'paid'
          AND (p_start_date IS NULL OR t.trx_date >= p_start_date)
          AND (p_end_date IS NULL OR t.trx_date <= p_end_date)
          AND (p_search IS NULL OR a.name ILIKE '%'||p_search||'%')
    )
    SELECT 
        ot.id, ot.trx_date, ot.account_name, ot.account_group, ot.acc_particulars,
        ot.debit, ot.credit,
        v_opening_balance + (SUM(COALESCE(ot.credit, 0) - COALESCE(ot.debit, 0)) 
            OVER (ORDER BY ot.row_num)) AS balance,
        ot.mode, ot.created_at
    FROM ordered_transactions ot
    ORDER BY ot.trx_date ASC, ot.id ASC;
END;
$$;
