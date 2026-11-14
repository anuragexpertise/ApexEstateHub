-- Add accumulated_depreciation column to assets table.
-- Cost is purchase_value (already exists). accumulated_depreciation tracks
-- lifetime depreciation charged so book_value = cost - accumulated_depreciation,
-- which is needed to calculate disposal gain/loss correctly.
ALTER TABLE assets
    ADD COLUMN IF NOT EXISTS accumulated_depreciation NUMERIC(12, 2) NOT NULL DEFAULT 0;
