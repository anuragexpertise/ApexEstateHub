-- rollback_concerns_assigns_accepted_status.sql
-- Reverts migration_concerns_assigns_accepted_status.sql.
--
-- NOTE: run this only after re-pointing any 'accepted' rows to another
-- status (e.g. back to 'assigned') — the tightened CHECK constraint will
-- otherwise fail to apply while such rows still exist.

BEGIN;

UPDATE concerns_assigns SET status = 'assigned' WHERE status = 'accepted';

ALTER TABLE concerns_assigns DROP CONSTRAINT IF EXISTS concerns_assigns_status_check;

ALTER TABLE concerns_assigns ADD CONSTRAINT concerns_assigns_status_check
    CHECK (status IN ('invited', 'bid_submitted', 'declined', 'assigned', 'resolved', 'closed'));

COMMENT ON COLUMN concerns_assigns.status IS
    'invited -> bid_submitted | declined -> assigned -> resolved -> closed. '
    'declined is re-invitable (resets to invited). Added declined 2026-08.';

CREATE OR REPLACE FUNCTION fn_sync_concern_status(p_concern_id INT)
RETURNS VOID
LANGUAGE plpgsql AS $$
DECLARE
    v_touched INT;
    v_touched_closed INT;
    v_touched_resolved_or_closed INT;
    v_new_status VARCHAR(20);
BEGIN
    SELECT COUNT(*) FILTER (WHERE status IN ('assigned', 'resolved', 'closed')),
           COUNT(*) FILTER (WHERE status = 'closed'),
           COUNT(*) FILTER (WHERE status IN ('resolved', 'closed'))
      INTO v_touched, v_touched_closed, v_touched_resolved_or_closed
      FROM concerns_assigns
     WHERE concern_id = p_concern_id
       AND status IN ('assigned', 'resolved', 'closed');

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
