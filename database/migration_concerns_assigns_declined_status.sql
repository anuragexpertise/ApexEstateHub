-- migration_concerns_assigns_declined_status.sql
-- ApexEstateHub — add 'declined' to concerns_assigns.status
--
-- Supports the new vendor/security "Decline" action (companion to "Bid"),
-- replacing the single "Save Bid" button on the concern profile. A vendor
-- sitting at 'invited' can now either:
--   - submit_concern_bid()          -> 'bid_submitted'  (Bid button)
--   - decline_concern_assignment()  -> 'declined'        (Decline button, NEW)
--
-- 'declined' is deliberately excluded from fn_sync_concern_status's
-- aggregate (that function only ever counts 'assigned'/'resolved'/'closed'
-- rows — see estatehub.sql — so declined rows, like invited/bid_submitted
-- ones, never block a concern from reaching 'resolved'; no change needed
-- there).
--
-- Re-inviting a declined vendor already works with zero code changes:
-- invite_concern_assignee()'s ON CONFLICT clause resets any row whose
-- status is NOT IN ('resolved','closed') back to 'invited', and 'declined'
-- was never in that exclusion list.
--
-- Validated against PostgreSQL 16. Apply with
-- database/apply_migration_concerns_declined_status.py or psql -f.
-- Companion rollback: rollback_concerns_assigns_declined_status.sql

BEGIN;

ALTER TABLE concerns_assigns DROP CONSTRAINT IF EXISTS concerns_assigns_status_check;

ALTER TABLE concerns_assigns ADD CONSTRAINT concerns_assigns_status_check
    CHECK (status IN ('invited', 'bid_submitted', 'declined', 'assigned', 'resolved', 'closed'));

COMMENT ON COLUMN concerns_assigns.status IS
    'invited -> bid_submitted | declined -> assigned -> resolved -> closed. '
    'declined is re-invitable (resets to invited). Added declined 2026-08.';

COMMIT;
