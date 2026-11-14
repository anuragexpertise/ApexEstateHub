-- Widen notification_no from VARCHAR(100) to VARCHAR(500).
-- Full Gazette / notification numbers (e.g. "Act 36 of 2020; S.O. 5319(E) dated ...")
-- can exceed 100 characters and caused "value too long for type character varying(100)"
-- when verifying instruments from verified.xlsx.
ALTER TABLE legal_instrument_catalog
    ALTER COLUMN notification_no TYPE VARCHAR(500);
