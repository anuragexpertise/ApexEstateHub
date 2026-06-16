
-- ── KPI: kpi_security_on_duty  (On Duty Now) ─────────────────────────
-- Format: number  |  Params: 1
SELECT COUNT(*) AS v 
            FROM gate_access 
            WHERE society_id = %s 
              AND role = 's' 
              AND time_in IS NOT NULL
              AND time_out IS NULL;
