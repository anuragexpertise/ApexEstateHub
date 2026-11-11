-- Billing by undivided interest waits for the builder's Declaration while the society is in the Enrollment stage.
-- Safe to run more than once. A fresh database gets all of this from estatehub.sql.
CREATE OR REPLACE FUNCTION fn_billing_waits_for_declaration(p_society_id INT)
RETURNS BOOLEAN LANGUAGE plpgsql STABLE AS $$
BEGIN
    -- plpgsql (not sql): onboarding_evidence is created further down this file and a sql function is checked when it is created.
    RETURN EXISTS (SELECT 1 FROM societies WHERE id = p_society_id AND onboarding_phase = 'enrollment')
       AND COALESCE((SELECT c.billing_basis FROM apt_charges_fines_basis c
                      WHERE c.society_id = p_society_id AND c.apt_id IS NULL AND c.apt_status = TRUE
                        AND c.start_date <= CURRENT_DATE AND (c.end_date IS NULL OR c.end_date >= CURRENT_DATE)
                      ORDER BY c.start_date DESC LIMIT 1), '') = 'undivided_interest'
       AND NOT EXISTS (SELECT 1 FROM onboarding_evidence e
                        WHERE e.society_id = p_society_id AND e.purpose = 'declaration_undivided_interest'
                          AND e.meta ->> 'xlsx_sha256' IS NOT NULL);
END;
$$;

DO $mig$
DECLARE
    v_def  TEXT := pg_get_functiondef('fn_auto_generate_receivables(integer)'::regprocedure);
    v_anchor TEXT := E'    IF v_gate_state IS DISTINCT FROM \'active\' THEN\n        RETURN;\n    END IF;\n';
    v_gate TEXT := E'\n    -- Undivided-interest billing needs each flat\'s declared share: wait for the builder\'s Declaration.\n'
                || E'    IF fn_billing_waits_for_declaration(p_society_id) THEN\n        RETURN;\n    END IF;\n';
BEGIN
    IF position('fn_billing_waits_for_declaration' IN v_def) > 0 THEN
        RETURN;                                           -- already applied
    END IF;
    IF position(v_anchor IN v_def) = 0 THEN
        RAISE EXCEPTION 'fn_auto_generate_receivables does not have the expected activation gate; apply database/estatehub.sql instead';
    END IF;
    EXECUTE replace(v_def, v_anchor, v_anchor || v_gate);
END
$mig$;
