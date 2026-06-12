
-- ── KPI: kpi_arrear_start_date  (Arrear Start Date) ─────────────────────────
-- Format: date  |  Params: 1
SELECT arrear_start_date AS v FROM societies WHERE id = %s;
