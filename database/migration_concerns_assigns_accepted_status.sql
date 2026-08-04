-- migration_concerns_assigns_accepted_status.sql
-- ApexEstateHub — add 'accepted' to concerns_assigns.status
--
-- Supports the Admin portal's Accept / Decline / Resolved actions on a
-- concern assigned to an admin (role='ADM'), per the authoritative
-- Concerns workflow spec:
--
--   button 'Accept'   -> admin's concerns_assigns.status = 'accepted'
--   button 'Decline'  -> admin's concerns_assigns.status = 'declined'
--   button 'Resolved' -> admin's concerns_assigns.status = 'resolved'
--                         (only once status = 'accepted')
--
-- An ADM row therefore follows its own sub-lifecycle after 'assigned':
--
--     assigned -> accepted -> resolved -> closed
--     assigned -> declined
--
-- fn_sync_concern_status is updated (in estatehub.sql) to treat 'accepted'
-- the same as 'assigned' for the purposes of the concerns.status aggregate
-- — an accepted-but-not-yet-resolved admin assignment should keep the
-- parent concern showing as 'assigned', not fall back to 'open'.
--
-- Validated against PostgreSQL 16. Apply with
-- database/apply_migration_concerns_assigns_accepted_status.py or psql -f.
-- Companion rollback: rollback_concerns_assigns_accepted_status.sql

BEGIN;

ALTER TABLE concerns_assigns DROP CONSTRAINT IF EXISTS concerns_assigns_status_check;

ALTER TABLE concerns_assigns ADD CONSTRAINT concerns_assigns_status_check
    CHECK (status IN ('invited', 'bid_submitted', 'declined', 'assigned', 'accepted', 'resolved', 'closed'));

COMMENT ON COLUMN concerns_assigns.status IS
    'invited -> bid_submitted | declined -> assigned -> accepted -> resolved -> closed '
    '(ADM rows only use accepted; VND/SEC rows go straight assigned -> resolved). '
    'Added accepted 2026-08.';

CREATE OR REPLACE FUNCTION fn_sync_concern_status(p_concern_id INT)
RETURNS VOID
LANGUAGE plpgsql AS $$
DECLARE
    v_touched INT;
    v_touched_closed INT;
    v_touched_resolved_or_closed INT;
    v_new_status VARCHAR(20);
BEGIN
    SELECT COUNT(*) FILTER (WHERE status IN ('assigned', 'accepted', 'resolved', 'closed')),
           COUNT(*) FILTER (WHERE status = 'closed'),
           COUNT(*) FILTER (WHERE status IN ('resolved', 'closed'))
      INTO v_touched, v_touched_closed, v_touched_resolved_or_closed
      FROM concerns_assigns
     WHERE concern_id = p_concern_id
       AND status IN ('assigned', 'accepted', 'resolved', 'closed');

    IF v_touched = 0 THEN
        v_new_status := 'open';
    ELSIF v_touched_closed = v_touched THEN
        v_new_status := 'closed';
    ELSIF v_touched_resolved_or_closed = v_touched THEN
        v_new_status := 'resolved';
    ELSE
        v_new_status := 'assigned';
    END IF;

    UPDATE concerns
       SET status = v_new_status,
           updated_at = NOW()
     WHERE id = p_concern_id
       AND status IS DISTINCT FROM v_new_status;
END;
$$;

COMMIT;
