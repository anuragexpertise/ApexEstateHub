-- ── KPI: kpi_calc_start_date  (Arrear Start Date) ─────────────────────────
-- Format: date  |  Params: 1
SELECT calc_start_date AS v FROM societies WHERE id = % s;