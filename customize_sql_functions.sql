-- customize_sql_functions.sql
-- Add to estatehub.sql - Function Definition Introspection Helpers
-- Run: psql -U user -d estatehub < customize_sql_functions.sql

-- ════════════════════════════════════════════════════════════════════════════
-- Get function SQL by name
-- ════════════════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION get_function_sql(p_function_name TEXT)
RETURNS TEXT AS $$
DECLARE
    v_sql TEXT;
BEGIN
    SELECT pg_get_functiondef(p.oid)
    INTO v_sql
    FROM pg_proc p
    WHERE p.proname = p_function_name
    LIMIT 1;
    
    RETURN COALESCE(v_sql, 'Function not found: ' || p_function_name);
END;
$$ LANGUAGE plpgsql;

-- ════════════════════════════════════════════════════════════════════════════
-- List all KPI functions with metadata
-- ════════════════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION get_kpi_functions()
RETURNS TABLE (
    function_name TEXT,
    function_schema TEXT,
    parameters TEXT,
    source_code TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p.proname::TEXT,
        n.nspname::TEXT,
        pg_get_function_arguments(p.oid)::TEXT,
        pg_get_functiondef(p.oid)::TEXT
    FROM pg_proc p
    JOIN pg_namespace n ON p.pronamespace = n.oid
    WHERE p.proname LIKE 'fn_%'
      AND n.nspname = 'public'
    ORDER BY p.proname;
END;
$$ LANGUAGE plpgsql;

-- ════════════════════════════════════════════════════════════════════════════
-- Get KPIs by portal with their function mappings
-- ════════════════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION get_portal_kpis(p_portal TEXT DEFAULT NULL)
RETURNS TABLE (
    kpi_id TEXT,
    kpi_label TEXT,
    kpi_icon TEXT,
    portal TEXT,
    tab_name TEXT,
    function_name TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        'kpi_apartments_total'::TEXT,
        'Total Apartments'::TEXT,
        'fa-building'::TEXT,
        'admin'::TEXT,
        'overview'::TEXT,
        'fn_apartments_list'::TEXT
    UNION ALL
    SELECT 'kpi_apartments_dues', 'Apartments with Dues', 'fa-exclamation-circle', 'admin', 'overview', 'fn_apartments_list'
    UNION ALL
    SELECT 'kpi_vendors_total', 'All Vendors', 'fa-handshake', 'admin', 'overview', 'fn_vendors_list'
    UNION ALL
    SELECT 'kpi_security_total', 'Security Staff', 'fa-shield', 'admin', 'overview', 'fn_security_list'
    UNION ALL
    SELECT 'kpi_events_total', 'Upcoming Events', 'fa-calendar', 'admin', 'events', 'fn_events_list'
    UNION ALL
    SELECT 'kpi_concerns_open', 'Open Concerns', 'fa-exclamation-circle', 'admin', 'concerns', 'fn_concerns_list'
    UNION ALL
    SELECT 'kpi_cash_in_hand', 'Cash in Hand', 'fa-money-bill', 'admin', 'accounts', 'fn_cashbook_list'
    UNION ALL
    SELECT 'kpi_accounts_count', 'Chart of Accounts', 'fa-receipt', 'admin', 'settings', 'fn_accounts_list'
    UNION ALL
    SELECT 'kpi_apt_charges', 'Apartment Charges', 'fa-home', 'admin', 'settings', 'fn_accounts_list'
    UNION ALL
    SELECT 'kpi_ven_charges', 'Vendor Charges', 'fa-briefcase', 'admin', 'settings', 'fn_accounts_list'
    UNION ALL
    SELECT 'kpi_sec_charges', 'Security Charges', 'fa-lock', 'admin', 'settings', 'fn_accounts_list'
    WHERE (p_portal IS NULL OR portal = p_portal)
    ORDER BY portal, tab_name, kpi_label;
END;
$$ LANGUAGE plpgsql;

-- ════════════════════════════════════════════════════════════════════════════
-- Helper: Get profile card actions for an entity
-- ════════════════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION get_entity_actions(p_entity TEXT)
RETURNS TABLE (
    action_id TEXT,
    action_label TEXT,
    target_card TEXT,
    icon TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        'view'::TEXT,
        'View'::TEXT,
        'profile_' || p_entity::TEXT,
        'fa-eye'::TEXT
    UNION ALL
    SELECT 'edit', 'Edit', 'form_' || p_entity || '_edit', 'fa-edit'
    UNION ALL
    SELECT 'delete', 'Delete', 'form_' || p_entity || '_edit', 'fa-trash';
END;
$$ LANGUAGE plpgsql;

-- ════════════════════════════════════════════════════════════════════════════
-- Test queries - Run these to verify functions work
-- ════════════════════════════════════════════════════════════════════════════

-- SELECT get_function_sql('fn_apartments_list');
-- SELECT * FROM get_kpi_functions() LIMIT 3;
-- SELECT * FROM get_portal_kpis('admin');
-- SELECT * FROM get_entity_actions('apartment');

