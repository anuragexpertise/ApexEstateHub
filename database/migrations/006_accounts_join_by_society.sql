-- accounts is keyed by (society_id, id), but these list functions joined it on id alone, so with more than one society
-- every payable, receivable, receipt, expense and fixed-asset row was repeated once per society holding that account id.
-- Safe to run more than once. A fresh database gets all of this from estatehub.sql.

CREATE OR REPLACE FUNCTION fn_receivables_named(
    p_society_id  INT, p_search TEXT DEFAULT NULL, p_status TEXT DEFAULT NULL,
    p_entity_id   INT DEFAULT NULL, p_entity_role TEXT DEFAULT NULL,
    p_date_from   DATE DEFAULT NULL, p_date_to DATE DEFAULT NULL
)
RETURNS TABLE (
    id INT, society_id INT, entity_id INT, role VARCHAR(10), entity_name TEXT,
    acc_id INT, account_name TEXT, interest_acc_id INT, interest_account_name TEXT,
    description TEXT, period_month DATE, bill_group_id UUID,
    base_amount NUMERIC(10,2), interest_amount NUMERIC(10,2),
    amount NUMERIC(10,2), paid_amount NUMERIC(10,2), residual NUMERIC(10,2),
    due_date DATE, status VARCHAR(20), days_overdue INT,
    confirmed_by INT, confirmed_at TIMESTAMP, created_at TIMESTAMP, gst_exempt_authority TEXT
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        r.id::INT, r.society_id::INT, r.entity_id::INT, r.role::VARCHAR(20),
        CASE WHEN r.role='apartment' THEN COALESCE(ap.flat_number||' — '||COALESCE(ap.owner_name,''),'')
             WHEN r.role='vendor'    THEN COALESCE(v.name,'')
             WHEN r.role='security'  THEN COALESCE(s.name,'')
             ELSE 'Entity #'||r.entity_id::TEXT END::TEXT,
        r.acc_id::INT,
        COALESCE(a.name,'—')::TEXT,
        r.interest_acc_id::INT,
        COALESCE(ia.name,'—')::TEXT,
        r.description::TEXT, r.period_month::DATE, r.bill_group_id::UUID,
        r.base_amount::NUMERIC(10,2), r.interest_amount::NUMERIC(10,2),
        r.amount::NUMERIC(10,2), r.paid_amount::NUMERIC(10,2),
        (r.amount - r.paid_amount)::NUMERIC(10,2),
        r.due_date::DATE, r.status::VARCHAR(20),
        GREATEST(EXTRACT(DAY FROM AGE(CURRENT_DATE, r.due_date)),0)::INT,
        r.confirmed_by::INT, r.confirmed_at::TIMESTAMP, r.created_at::TIMESTAMP, r.gst_exempt_authority::TEXT
    FROM receivables r
    LEFT JOIN accounts a    ON a.society_id  = r.society_id AND a.id  = r.acc_id
    LEFT JOIN accounts ia   ON ia.society_id = r.society_id AND ia.id = r.interest_acc_id
    LEFT JOIN apartments ap ON ap.id = r.entity_id AND r.role='apartment'
    LEFT JOIN vendors v     ON  v.id = r.entity_id AND r.role='vendor'
    LEFT JOIN security_staff s ON s.id = r.entity_id AND r.role='security'
    WHERE r.society_id = p_society_id
      AND (p_status IS NULL OR
           (p_status = 'overdue' AND r.status IN ('pending','partial') AND r.due_date < CURRENT_DATE AND NOT fn_receivable_disputed_asof(r.id, CURRENT_DATE)) OR
           (p_status <> 'overdue' AND r.status = p_status))
      AND (p_entity_id   IS NULL OR r.entity_id = p_entity_id)
      AND (p_entity_role IS NULL OR r.role = p_entity_role)
      AND (p_search IS NULL OR r.description ILIKE '%'||p_search||'%' OR a.name ILIKE '%'||p_search||'%')
      AND (p_date_from IS NULL OR r.period_month >= p_date_from)
      AND (p_date_to IS NULL OR r.period_month <= p_date_to)
    ORDER BY r.due_date ASC, r.created_at DESC;
END;
$$;

CREATE OR REPLACE FUNCTION fn_payables_named(
    p_society_id  INT, p_search TEXT DEFAULT NULL,
    p_status      TEXT DEFAULT NULL, p_entity_role TEXT DEFAULT NULL,
    p_entity_id   INT  DEFAULT NULL,
    p_shift_date_from DATE DEFAULT NULL, p_shift_date_to DATE DEFAULT NULL
)
RETURNS TABLE (
    id INT, society_id INT, entity_id INT, role VARCHAR(10), entity_name TEXT,
    acc_id INT, account_name TEXT,
    description TEXT, roster_id INT, shift_date DATE,
    amount NUMERIC(10,2), status VARCHAR(20), due_date DATE, days_overdue INT,
    paid_at TIMESTAMP, confirmed_by INT, confirmed_at TIMESTAMP, created_at TIMESTAMP,
    shift_fraction NUMERIC, mode VARCHAR(20)      -- task 1.11: the list shows both columns, so the function must return them
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        p.id::INT, p.society_id::INT, p.entity_id::INT, p.role::VARCHAR(20),
        CASE WHEN p.role='security' THEN COALESCE(s.name,'') ELSE 'Entity #'||COALESCE(p.entity_id::TEXT,'—') END::TEXT,
        p.acc_id::INT,
        COALESCE(a.name,'—')::TEXT,
        p.description::TEXT, p.roster_id::INT, p.shift_date::DATE,
        p.amount::NUMERIC(10,2), p.status::VARCHAR(20), p.due_date::DATE,
        GREATEST(EXTRACT(DAY FROM AGE(CURRENT_DATE, p.due_date)),0)::INT,
        p.paid_at::TIMESTAMP, p.confirmed_by::INT, p.confirmed_at::TIMESTAMP, p.created_at::TIMESTAMP,
        p.shift_fraction::NUMERIC, p.mode::VARCHAR(20)
    FROM payables p
    LEFT JOIN accounts a       ON a.society_id = p.society_id AND a.id = p.acc_id
    LEFT JOIN security_staff s ON s.id = p.entity_id AND p.role='security'
    WHERE p.society_id = p_society_id
      AND (p_status      IS NULL OR p.status = p_status)
      AND (p_entity_role IS NULL OR p.role = p_entity_role)
      AND (p_entity_id   IS NULL OR p.entity_id = p_entity_id)
      AND (p_search IS NULL OR p.description ILIKE '%'||p_search||'%' OR a.name ILIKE '%'||p_search||'%')
      AND (p_shift_date_from IS NULL OR p.shift_date >= p_shift_date_from)
      AND (p_shift_date_to IS NULL OR p.shift_date <= p_shift_date_to)
    ORDER BY p.due_date ASC, p.created_at DESC;
END;
$$;

CREATE OR REPLACE FUNCTION fn_receipts_list(
    p_society_id  INT,
    p_search      TEXT DEFAULT NULL,
    p_entity_id   INT  DEFAULT NULL,
    p_entity_role TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT, society_id INT, entity_id INT, role VARCHAR(10), entity_name TEXT,
    receipt_date DATE, acc_id INT, account_name TEXT,
    particulars TEXT, amount NUMERIC(10,2), mode VARCHAR(20),
    cheque_no VARCHAR(50), transaction_id VARCHAR(255), status VARCHAR(20),
    confirmed_by INT, confirmed_at TIMESTAMP,
    last_printed_at TIMESTAMP, last_emailed_at TIMESTAMP, created_at TIMESTAMP,
    reconciled_at TIMESTAMP, reconciled_by INT, bank_statement_line_id INT,
    initiated_by VARCHAR(100)
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        r.id::INT, r.society_id::INT, r.entity_id::INT, r.role::VARCHAR(20),
        CASE
            WHEN r.role = 'apartment' THEN COALESCE(ap.flat_number||' — '||COALESCE(ap.owner_name,''), '')
            WHEN r.role = 'vendor'    THEN COALESCE(v.name||COALESCE(' ('||v.service_type||')',''), '')
            WHEN r.role = 'security'  THEN COALESCE(s.name, '')
            ELSE COALESCE('Other #'||r.entity_id::TEXT, '')
        END::TEXT,
        r.receipt_date::DATE,
        r.acc_id::INT,
        COALESCE(a.name, '—')::TEXT,
        r.particulars::TEXT,
        r.amount::NUMERIC(10,2), r.mode::VARCHAR(20),
        COALESCE(r.cheque_no,'')::VARCHAR(50),
        COALESCE(r.transaction_id,'')::VARCHAR(255),
        r.status::VARCHAR(20),
        r.confirmed_by::INT, r.confirmed_at::TIMESTAMP,
        r.last_printed_at::TIMESTAMP, r.last_emailed_at::TIMESTAMP,
        r.created_at::TIMESTAMP,
        r.reconciled_at::TIMESTAMP, r.reconciled_by::INT, r.bank_statement_line_id::INT,
        COALESCE(u.name, '')::VARCHAR(100) AS initiated_by
    FROM receipts r
    LEFT JOIN accounts      a  ON a.society_id = r.society_id AND a.id  = r.acc_id
    LEFT JOIN apartments   ap  ON ap.id = r.entity_id AND r.role = 'apartment'
    LEFT JOIN vendors       v  ON  v.id = r.entity_id AND r.role = 'vendor'
    LEFT JOIN security_staff s ON  s.id = r.entity_id AND r.role = 'security'
    LEFT JOIN users          u ON  u.id = COALESCE(r.user_id, r.created_by)
    WHERE r.society_id = p_society_id
      AND (p_entity_id   IS NULL OR r.entity_id = p_entity_id)
      AND (p_entity_role IS NULL OR r.role = p_entity_role)
      AND (p_search IS NULL
           OR r.particulars ILIKE '%'||p_search||'%'
           OR a.name        ILIKE '%'||p_search||'%')
    ORDER BY r.receipt_date DESC, r.id DESC;
END;
$$;

CREATE OR REPLACE FUNCTION fn_expenses_list(
    p_society_id  INT,
    p_search      TEXT DEFAULT NULL,
    p_entity_id   INT  DEFAULT NULL,
    p_entity_role TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT, society_id INT, entity_id INT, role VARCHAR(10), entity_name TEXT,
    expense_date DATE, acc_id INT, account_name TEXT,
    particulars TEXT, amount NUMERIC(10,2), mode VARCHAR(20),
    cheque_no VARCHAR(50), transaction_id VARCHAR(255), status VARCHAR(20),
    confirmed_by INT, confirmed_at TIMESTAMP,
    last_printed_at TIMESTAMP, last_emailed_at TIMESTAMP, created_at TIMESTAMP,
    reconciled_at TIMESTAMP, reconciled_by INT, bank_statement_line_id INT
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        e.id::INT, e.society_id::INT, e.entity_id::INT, e.role::VARCHAR(20),
        CASE
            WHEN e.role = 'vendor'   THEN COALESCE(v.name||COALESCE(' ('||v.service_type||')',''), '')
            WHEN e.role = 'security' THEN COALESCE(s.name||COALESCE(' ('||s.shift||')',''), '')
            WHEN e.role = 'assets'   THEN COALESCE(
                (SELECT asset_name FROM assets WHERE assets.id = e.entity_id),
                'Asset #'||e.entity_id::TEXT)
            ELSE 'Other'
        END::TEXT,
        e.expense_date::DATE,
        e.acc_id::INT,
        COALESCE(a.name, '—')::TEXT,
        e.particulars::TEXT,
        e.amount::NUMERIC(10,2), e.mode::VARCHAR(20),
        COALESCE(e.cheque_no,'')::VARCHAR(50),
        COALESCE(e.transaction_id,'')::VARCHAR(255),
        e.status::VARCHAR(20),
        e.confirmed_by::INT, e.confirmed_at::TIMESTAMP,
        e.last_printed_at::TIMESTAMP, e.last_emailed_at::TIMESTAMP,
        e.created_at::TIMESTAMP,
        e.reconciled_at::TIMESTAMP, e.reconciled_by::INT, e.bank_statement_line_id::INT
    FROM expenses e
    LEFT JOIN accounts       a ON a.society_id = e.society_id AND a.id = e.acc_id
    LEFT JOIN vendors        v ON v.id = e.entity_id AND e.role = 'vendor'
    LEFT JOIN security_staff s ON s.id = e.entity_id AND e.role = 'security'
    WHERE e.society_id = p_society_id
      AND (p_entity_id   IS NULL OR e.entity_id = p_entity_id)
      AND (p_entity_role IS NULL OR e.role = p_entity_role)
      AND (p_search IS NULL
           OR e.particulars ILIKE '%'||p_search||'%'
           OR a.name        ILIKE '%'||p_search||'%')
    ORDER BY e.expense_date DESC, e.id DESC;
END;
$$;

CREATE OR REPLACE FUNCTION fn_fixed_assets_list_fy(
    p_society_id INT,
    p_fy         INT
)
RETURNS TABLE (
    asset_id      INT,
    asset_name    VARCHAR,
    asset_sno     VARCHAR,
    account_name  VARCHAR,
    purchase_date DATE,
    purchase_value NUMERIC(15,2),
    disposed      BOOLEAN,
    disposal_date DATE,
    sale_value    NUMERIC(15,2),
    gst_disposal_liability NUMERIC(15,2)
) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_fy_start DATE := MAKE_DATE(p_fy, 4, 1);
    v_fy_end   DATE := MAKE_DATE(p_fy + 1, 3, 31);
BEGIN
    RETURN QUERY
    SELECT
        ast.id AS asset_id,
        ast.asset_name,
        ast.asset_sno,
        acc.name AS account_name,
        ast.purchase_date,
        ast.purchase_value,
        ast.disposed,
        ast.disposed_at AS disposal_date,
        (
            SELECT SUM(amount)
            FROM transactions t
            WHERE t.society_id = p_society_id
              AND t.source_table = 'assets'
              AND t.source_id = ast.id
              AND t.acc_id = ast.acc_id -- Fixed (2026-09): scope to the block account's own leg only —
                                         -- the GST-on-disposal CGST/SGST Cr legs share source_table='assets'/
                                         -- source_id=ast.id too but post to different accounts, and would
                                         -- otherwise be double-counted into "sale_value" here.
              AND t.entry_side = 'Cr'
              AND t.status = 'paid'
        ) AS sale_value,
        ast.gst_disposal_liability
    FROM assets ast
    JOIN accounts acc ON acc.society_id = ast.society_id AND ast.acc_id = acc.id
    WHERE ast.society_id = p_society_id
      AND ast.purchase_date <= v_fy_end
    ORDER BY acc.name, ast.purchase_date;
END;
$$;
