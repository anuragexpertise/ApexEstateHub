-- Let the platform master verify catalogue instruments (Central Acts), alongside the Treasurer and Auditor.
-- Idempotent: safe to run twice.
DO $$
DECLARE c RECORD;
BEGIN
    FOR c IN SELECT conname FROM pg_constraint
              WHERE conrelid = 'legal_instrument_catalog'::regclass AND contype = 'c'
                AND pg_get_constraintdef(oid) ILIKE '%verifier_role%' AND pg_get_constraintdef(oid) ILIKE '%treasurer%'
    LOOP
        EXECUTE format('ALTER TABLE legal_instrument_catalog DROP CONSTRAINT %I', c.conname);
    END LOOP;
    ALTER TABLE legal_instrument_catalog
        ADD CONSTRAINT legal_instrument_catalog_verifier_role_check CHECK (verifier_role IN ('treasurer', 'auditor', 'master'));
END $$;

CREATE OR REPLACE FUNCTION fn_verify_instrument(
    p_instrument_id INT, p_user INT, p_role TEXT, p_notification_no TEXT, p_source_url TEXT, p_opinion_ref TEXT, p_verified_on DATE
) RETURNS TEXT LANGUAGE plpgsql AS $$
BEGIN
    IF p_role NOT IN ('treasurer', 'auditor', 'master') THEN RAISE EXCEPTION 'Only the Treasurer, an Auditor or the platform master can verify an instrument.'; END IF;
    IF NULLIF(BTRIM(p_opinion_ref), '') IS NULL THEN RAISE EXCEPTION 'An opinion reference is required to verify.'; END IF;
    IF NULLIF(BTRIM(p_notification_no), '') IS NULL THEN RAISE EXCEPTION 'The notification number is required.'; END IF;
    IF p_source_url IS NULL OR p_source_url !~* '^https?://' THEN RAISE EXCEPTION 'A link to the source text is required.'; END IF;
    IF p_verified_on IS NULL OR p_verified_on > CURRENT_DATE THEN RAISE EXCEPTION 'The verified date must not be in the future.'; END IF;
    UPDATE legal_instrument_catalog SET notification_no = p_notification_no, source_url = p_source_url, opinion_ref = p_opinion_ref,
           last_verified_on = p_verified_on, verified_by = p_user, verifier_role = p_role, verification = 'verified', updated_at = NOW()
     WHERE id = p_instrument_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Instrument not found.'; END IF;
    RETURN 'verified';
END $$;
