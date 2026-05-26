-- =============================================
-- SECURITY DUTY ROSTER MANAGEMENT
-- =============================================

-- Drop previous security functions
DROP FUNCTION IF EXISTS fn_security_list CASCADE;
DROP FUNCTION IF EXISTS fn_auto_generate_security_receivables CASCADE;
DROP FUNCTION IF EXISTS fn_auto_process_security_payments CASCADE;
DROP FUNCTION IF EXISTS fn_auto_process_security_salary CASCADE;
DROP FUNCTION IF EXISTS fn_security_roster_assign CASCADE;
DROP FUNCTION IF EXISTS fn_security_roster_today CASCADE;
DROP FUNCTION IF EXISTS fn_security_roster_report CASCADE;

-- =============================================
-- 1. MAIN SECURITY LIST (Enhanced with Roster)
-- =============================================

CREATE OR REPLACE FUNCTION fn_security_list(
    p_society_id INT,
    p_search TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT, email VARCHAR, society_id INT, name TEXT, shift VARCHAR, 
    mobile VARCHAR, active BOOLEAN, salary_per_shift NUMERIC, 
    joining_date DATE, days_worked BIGINT, salary_due NUMERIC, 
    salary_paid NUMERIC, salary_pending NUMERIC, active_fines NUMERIC,
    current_status TEXT, today_duty TEXT
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM fn_auto_generate_security_receivables(p_society_id);
    PERFORM fn_auto_process_security_payments(p_society_id);
    PERFORM fn_auto_process_security_salary(p_society_id);

    RETURN QUERY
    WITH security_base AS (
        SELECT u.id, u.email, u.society_id, COALESCE(s.name, u.email) AS name,
               COALESCE(s.shift, '—') AS shift, COALESCE(s.mobile, '—') AS mobile,
               COALESCE(s.active, TRUE) AS active, s.salary_per_shift, s.joining_date,
               EXTRACT(DAY FROM AGE(CURRENT_DATE, COALESCE(s.joining_date, CURRENT_DATE)))::BIGINT AS days_worked
        FROM users u LEFT JOIN security_staff s ON s.id = u.linked_id
        WHERE u.society_id = p_society_id AND u.role = 'security'
          AND (p_search IS NULL OR s.name ILIKE '%'||p_search||'%' OR u.email ILIKE '%'||p_search||'%')
    ),
    payment_summary AS (
        SELECT 
            p.user_id,
            SUM(CASE WHEN p.status = 'verified' AND p.payment_type = 'salary' THEN p.amount ELSE 0 END) AS salary_paid,
            SUM(CASE WHEN p.status IN ('pending','confirmed') THEN p.amount ELSE 0 END) AS total_pending
        FROM payments p
        WHERE p.society_id = p_society_id AND p.entity_type = 'security'
        GROUP BY p.user_id
    ),
    fine_summary AS (
        SELECT 
            u.id AS user_id,
            COALESCE(SUM(CASE WHEN scf.security_fine > 0 THEN scf.security_fine ELSE 0 END), 0) AS active_fines
        FROM users u
        LEFT JOIN security_charges_fines scf ON scf.sec_id = u.linked_id
        WHERE u.society_id = p_society_id AND u.role = 'security'
        GROUP BY u.id
    ),
    current_status AS (
        SELECT 
            g.entity_id,
            'PASS' AS status
        FROM gate_access g
        WHERE g.society_id = p_society_id
          AND g.role = 's'
          AND g.time_out IS NULL
          AND g.time_in >= CURRENT_DATE - INTERVAL '1 day'
          AND (
               -- Morning Shift: 9AM to 9PM
               (EXTRACT(HOUR FROM g.time_in) BETWEEN 9 AND 20) OR
               -- Evening Shift: 9PM to 9AM
               (EXTRACT(HOUR FROM g.time_in) >= 21 OR EXTRACT(HOUR FROM g.time_in) < 9)
          )
    ),
    today_roster AS (
        SELECT entity_id, 'ON DUTY' AS today_duty
        FROM security_roster 
        WHERE society_id = p_society_id 
          AND roster_date = CURRENT_DATE
    )
    SELECT 
        sb.*, 
        COALESCE(ps.salary_paid, 0),
        GREATEST((sb.salary_per_shift * sb.days_worked) - COALESCE(ps.salary_paid, 0), 0),
        COALESCE(fs.active_fines, 0),
        COALESCE(cs.status, 'ABSENT'),
        COALESCE(tr.today_duty, 'OFF') AS today_duty
    FROM security_base sb
    LEFT JOIN payment_summary ps ON ps.user_id = sb.id
    LEFT JOIN fine_summary fs ON fs.user_id = sb.id
    LEFT JOIN current_status cs ON cs.entity_id = sb.id
    LEFT JOIN today_roster tr ON tr.entity_id = sb.id
    ORDER BY sb.name;
END;
$$;

-- =============================================
-- 2. DUTY ROSTER TABLE (if not exists)
-- =============================================

CREATE TABLE IF NOT EXISTS security_roster (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    security_id INT NOT NULL REFERENCES security_staff(id) ON DELETE CASCADE,
    roster_date DATE NOT NULL,
    shift_type VARCHAR(20) CHECK (shift_type IN ('morning', 'evening', 'night')),
    assigned_by INT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(society_id, security_id, roster_date)
);

CREATE INDEX IF NOT EXISTS idx_security_roster_date ON security_roster(society_id, roster_date);
CREATE INDEX IF NOT EXISTS idx_security_roster_staff ON security_roster(security_id);

-- =============================================
-- 3. ASSIGN DUTY (Roster Management)
-- =============================================

CREATE OR REPLACE FUNCTION fn_security_roster_assign(
    p_society_id INT,
    p_security_id INT,
    p_roster_date DATE,
    p_shift_type VARCHAR DEFAULT 'morning',
    p_assigned_by INT DEFAULT NULL
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO security_roster (society_id, security_id, roster_date, shift_type, assigned_by)
    VALUES (p_society_id, p_security_id, p_roster_date, p_shift_type, p_assigned_by)
    ON CONFLICT (society_id, security_id, roster_date) 
    DO UPDATE SET 
        shift_type = EXCLUDED.shift_type,
        assigned_by = EXCLUDED.assigned_by;

    RETURN 'Duty assigned successfully for ' || p_roster_date;
END;
$$;

-- =============================================
-- 4. TODAY'S ROSTER
-- =============================================

CREATE OR REPLACE FUNCTION fn_security_roster_today(p_society_id INT)
RETURNS TABLE (
    id INT, name TEXT, shift_type VARCHAR, mobile VARCHAR,
    status TEXT, time_in TIMESTAMP, time_out TIMESTAMP
)
LANGUAGE SQL STABLE AS $$
    SELECT 
        s.id,
        s.name,
        r.shift_type,
        s.mobile,
        CASE 
            WHEN g.time_out IS NULL AND g.time_in IS NOT NULL THEN 'ON DUTY'
            WHEN g.time_in IS NOT NULL THEN 'COMPLETED'
            ELSE 'ABSENT'
        END AS status,
        g.time_in,
        g.time_out
    FROM security_roster r
    JOIN security_staff s ON s.id = r.security_id
    LEFT JOIN gate_access g ON g.entity_id = (SELECT id FROM users WHERE linked_id = s.id AND role = 'security')
        AND g.role = 's' 
        AND g.time_in::DATE = CURRENT_DATE
    WHERE r.society_id = p_society_id 
      AND r.roster_date = CURRENT_DATE
    ORDER BY r.shift_type, s.name;
$$;

-- =============================================
-- 5. ROSTER REPORT (Monthly / Period)
-- =============================================

CREATE OR REPLACE FUNCTION fn_security_roster_report(
    p_society_id INT,
    p_start_date DATE DEFAULT CURRENT_DATE - INTERVAL '30 days',
    p_end_date DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    security_id INT,
    name TEXT,
    total_assigned INT,
    days_present INT,
    attendance_rate NUMERIC,
    total_fines NUMERIC,
    total_salary_due NUMERIC
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.id AS security_id,
        s.name,
        COUNT(r.id) AS total_assigned,
        COUNT(DISTINCT g.time_in::DATE) AS days_present,
        ROUND(COUNT(DISTINCT g.time_in::DATE)::NUMERIC / NULLIF(COUNT(r.id), 0) * 100, 2) AS attendance_rate,
        COALESCE(SUM(scf.security_fine), 0) AS total_fines,
        SUM(s.salary_per_shift) * COUNT(r.id) AS total_salary_due
    FROM security_staff s
    LEFT JOIN security_roster r ON r.security_id = s.id 
        AND r.roster_date BETWEEN p_start_date AND p_end_date
    LEFT JOIN gate_access g ON g.entity_id = (SELECT id FROM users WHERE linked_id = s.id AND role='security')
        AND g.time_in::DATE = r.roster_date
    LEFT JOIN security_charges_fines scf ON scf.sec_id = s.id
    WHERE s.society_id = p_society_id
    GROUP BY s.id, s.name, s.salary_per_shift
    ORDER BY attendance_rate DESC;
END;
$$;

-- =============================================
-- USAGE EXAMPLES
-- =============================================
/*
-- Assign duty
SELECT fn_security_roster_assign(1, 5, CURRENT_DATE, 'morning', 1);

-- Today's roster
SELECT * FROM fn_security_roster_today(1);

-- Monthly report
SELECT * FROM fn_security_roster_report(1, '2026-05-01', '2026-05-31');

-- Full security list with roster info
SELECT * FROM fn_security_list(1);
*/