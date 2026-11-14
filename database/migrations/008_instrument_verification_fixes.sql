-- Two fixes for verifying catalogue instruments (Central / UP) from the master portal.
-- Idempotent: safe to run twice.
--
-- 1. notification_no was VARCHAR(100), but real gazette citations run longer (e.g. 'Code on Wages, 2019' is 114 characters), so
--    verifying such a row failed with 'value too long'. Widened to 255 (the same as candidate_notification_no).
-- 2. fn_verify_instrument compared the verified date with CURRENT_DATE, which is the database server's date (UTC on most hosts),
--    while the app validates against the IST date: between 00:00 and 05:30 IST a date the app accepted was rejected as 'in the
--    future'. It now compares with today's date in IST.
ALTER TABLE legal_instrument_catalog ALTER COLUMN notification_no TYPE VARCHAR(255);

CREATE OR REPLACE FUNCTION fn_verify_instrument(
    p_instrument_id INT, p_user INT, p_role TEXT, p_notification_no TEXT, p_source_url TEXT, p_opinion_ref TEXT, p_verified_on DATE
) RETURNS TEXT LANGUAGE plpgsql AS $$
BEGIN
    IF p_role NOT IN ('treasurer', 'auditor', 'master') THEN RAISE EXCEPTION 'Only the Treasurer, an Auditor or the platform master can verify an instrument.'; END IF;
    IF NULLIF(BTRIM(p_opinion_ref), '') IS NULL THEN RAISE EXCEPTION 'An opinion reference is required to verify.'; END IF;
    IF NULLIF(BTRIM(p_notification_no), '') IS NULL THEN RAISE EXCEPTION 'The notification number is required.'; END IF;
    IF p_source_url IS NULL OR p_source_url !~* '^https?://' THEN RAISE EXCEPTION 'A link to the source text is required.'; END IF;
    IF p_verified_on IS NULL OR p_verified_on > (NOW() AT TIME ZONE 'Asia/Kolkata')::date THEN RAISE EXCEPTION 'The verified date must not be in the future.'; END IF;
    UPDATE legal_instrument_catalog SET notification_no = p_notification_no, source_url = p_source_url, opinion_ref = p_opinion_ref,
           last_verified_on = p_verified_on, verified_by = p_user, verifier_role = p_role, verification = 'verified', updated_at = NOW()
     WHERE id = p_instrument_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Instrument not found.'; END IF;
    RETURN 'verified';
END $$;
