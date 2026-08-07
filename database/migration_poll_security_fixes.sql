-- migration_poll_security_fixes.sql
-- ════════════════════════════════════════════════════════════════
-- Poll workflow — security & lifecycle fixes (2026-08)
--
-- 1) fn_get_poll_detail had NO tenant (society_id) scoping — same bug
--    class as the fn_concern_profile IDOR fixed in
--    migration_fn_concern_profile_scope.sql. Any authenticated user
--    could load any OTHER society's poll profile just by guessing/
--    incrementing the poll id. Also the caller-side bug in loaders.py
--    passed `user_id or society_id` as a single positional arg, so a
--    falsy user_id silently substituted society_id in the user_id slot.
--    Fixed by adding an explicit p_society_id parameter and scoping
--    the query; loaders.py now passes both ids explicitly.
--
-- 2) fn_close_poll / fn_declare_results had the same missing tenant
--    scoping — any admin (of any society) who knew a poll_id could
--    close / force-declare results on another society's poll.
--
-- 3) fn_declare_results had no status guard at all, so it could be
--    called repeatedly (re-stamping results_announced_at) even on an
--    already-declared or already-closed poll. Added a guard mirroring
--    fn_close_poll's existing "must be active" check, except results
--    may be declared from 'active' OR 'closed' (an admin closing a
--    poll first, then declaring results, is a valid flow) — only
--    'results_declared' -> 'results_declared' is now rejected.
-- ════════════════════════════════════════════════════════════════

-- fn_get_poll_detail: now tenant-scoped.
DROP FUNCTION IF EXISTS fn_get_poll_detail(INT, INT);
CREATE OR REPLACE FUNCTION fn_get_poll_detail(p_poll_id INT, p_user_id INT, p_society_id INT)
RETURNS TABLE (
    id              INT,
    title           VARCHAR(200),
    description     TEXT,
    status          VARCHAR(20),
    choice_count    SMALLINT,
    choice_1        VARCHAR(100),
    choice_2        VARCHAR(100),
    choice_3        VARCHAR(100),
    choice_4        VARCHAR(100),
    choice_5        VARCHAR(100),
    results_announced_at TIMESTAMP,
    created_at      TIMESTAMP,
    total_votes     BIGINT,
    has_voted       BOOLEAN,
    user_vote       SMALLINT,
    vote_counts     JSONB,
    ends_at         TIMESTAMP
) LANGUAGE plpgsql AS $$
BEGIN
    SELECT
        p.id,
        p.title,
        p.description,
        p.status,
        p.choice_count,
        p.choice_1,
        p.choice_2,
        p.choice_3,
        p.choice_4,
        p.choice_5,
        p.results_announced_at,
        p.created_at,
        COALESCE((SELECT COUNT(*) FROM poll_votes WHERE poll_id = p.id), 0)::BIGINT,
        EXISTS (SELECT 1 FROM poll_votes WHERE poll_id = p.id AND user_id = p_user_id),
        (SELECT choice FROM poll_votes WHERE poll_id = p.id AND user_id = p_user_id),
        p.ends_at
    FROM polls p
    WHERE p.id = p_poll_id
      AND p.society_id = p_society_id
    INTO
        id, title, description, status, choice_count, choice_1, choice_2, choice_3, choice_4, choice_5,
        results_announced_at, created_at, total_votes, has_voted, user_vote, ends_at;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    vote_counts := (
        SELECT jsonb_object_agg(
            'choice_' || v.choice,
            v.cnt
        )
        FROM (
            SELECT choice, COUNT(*) AS cnt
            FROM poll_votes
            WHERE poll_id = p_poll_id
            GROUP BY choice
        ) v
    );

    RETURN NEXT;
END;
$$;

-- 4) NEW: fn_edit_poll — Poll now supports Edit (previously in
--    NO_EDIT_ACTION, treated as immutable like a ledger). Admin-only
--    edit, and only while status='active' AND zero votes cast — see
--    schema_introspect.py / renderers.py changes.
CREATE OR REPLACE FUNCTION fn_edit_poll(
    p_poll_id      INT,
    p_society_id   INT,
    p_title        VARCHAR(200),
    p_description  TEXT DEFAULT NULL,
    p_choice_count SMALLINT DEFAULT 2,
    p_choice_1     VARCHAR(100) DEFAULT '',
    p_choice_2     VARCHAR(100) DEFAULT '',
    p_choice_3     VARCHAR(100) DEFAULT NULL,
    p_choice_4     VARCHAR(100) DEFAULT NULL,
    p_choice_5     VARCHAR(100) DEFAULT NULL,
    p_ends_at      TIMESTAMP DEFAULT NULL
) RETURNS BOOLEAN LANGUAGE plpgsql AS $$
DECLARE
    v_poll       polls%ROWTYPE;
    v_vote_count BIGINT;
BEGIN
    IF p_choice_count < 2 OR p_choice_count > 5 THEN
        RAISE EXCEPTION 'choice_count must be between 2 and 5';
    END IF;

    SELECT * INTO v_poll FROM polls WHERE id = p_poll_id AND society_id = p_society_id;
    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    IF v_poll.status <> 'active' THEN
        RETURN FALSE;
    END IF;

    SELECT COUNT(*) INTO v_vote_count FROM poll_votes WHERE poll_id = p_poll_id;
    IF v_vote_count > 0 THEN
        RETURN FALSE;
    END IF;

    UPDATE polls
       SET title        = p_title,
           description  = p_description,
           choice_count = p_choice_count,
           choice_1     = p_choice_1,
           choice_2     = p_choice_2,
           choice_3     = p_choice_3,
           choice_4     = p_choice_4,
           choice_5     = p_choice_5,
           ends_at      = p_ends_at,
           updated_at   = NOW()
     WHERE id = p_poll_id;

    RETURN TRUE;
END;
$$;

-- fn_close_poll: now tenant-scoped.
DROP FUNCTION IF EXISTS fn_close_poll(INT, INT);
CREATE OR REPLACE FUNCTION fn_close_poll(p_poll_id INT, p_user_id INT, p_society_id INT)
RETURNS BOOLEAN LANGUAGE plpgsql AS $$
DECLARE
    v_poll polls%ROWTYPE;
BEGIN
    SELECT * INTO v_poll FROM polls WHERE id = p_poll_id AND society_id = p_society_id;
    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    IF v_poll.status <> 'active' THEN
        RETURN FALSE;
    END IF;

    UPDATE polls
       SET status = 'closed',
           updated_at = NOW()
     WHERE id = p_poll_id;

    RETURN TRUE;
END;
$$;

-- fn_declare_results: now tenant-scoped + status guard against
-- re-declaring an already-declared poll.
DROP FUNCTION IF EXISTS fn_declare_results(INT, INT);
CREATE OR REPLACE FUNCTION fn_declare_results(p_poll_id INT, p_user_id INT, p_society_id INT)
RETURNS BOOLEAN LANGUAGE plpgsql AS $$
DECLARE
    v_poll polls%ROWTYPE;
BEGIN
    SELECT * INTO v_poll FROM polls WHERE id = p_poll_id AND society_id = p_society_id;
    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    IF v_poll.status = 'results_declared' THEN
        RETURN FALSE;
    END IF;

    UPDATE polls
       SET status = 'results_declared',
           results_announced_at = NOW(),
           updated_at = NOW()
     WHERE id = p_poll_id;

    RETURN TRUE;
END;
$$;

-- ════════════════════════════════════════════════════════════════
-- Poll workflow — UX/feedback fixes (2026-08, follow-up)
--
-- 5) fn_cast_vote was being called from Python as
--    "SELECT fn_cast_vote(...) AS success" instead of
--    "SELECT * FROM fn_cast_vote(...)". Since fn_cast_vote RETURNS
--    TABLE(success, message, total_votes), the scalar-alias form
--    doesn't expand into named columns, so result.get("success")
--    never matched — voting silently produced no feedback. Fixed on
--    the Python side (drilldown_callbacks.py); fn_cast_vote itself is
--    unchanged, included here only for reference/no-op.
--
-- 6) fn_polls_list now also returns winning_choice (SMALLINT, the
--    choice number with a strict/unique max vote count, NULL on a
--    tie or zero votes) so list_polls can highlight the winning
--    choice once results are declared.
-- ════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS fn_polls_list(INT, VARCHAR, VARCHAR);
CREATE OR REPLACE FUNCTION fn_polls_list(
    p_society_id INT,
    p_search VARCHAR DEFAULT NULL,
    p_status VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id                  INT,
    title               VARCHAR(200),
    description         TEXT,
    status              VARCHAR(20),
    choice_count        SMALLINT,
    choice_1            VARCHAR(100),
    choice_2            VARCHAR(100),
    choice_3            VARCHAR(100),
    choice_4            VARCHAR(100),
    choice_5            VARCHAR(100),
    results_announced_at TIMESTAMP,
    created_at          TIMESTAMP,
    ends_at             TIMESTAMP,
    total_votes         BIGINT,
    winning_choice      SMALLINT
) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        p.id,
        p.title,
        p.description,
        p.status,
        p.choice_count,
        p.choice_1,
        p.choice_2,
        p.choice_3,
        p.choice_4,
        p.choice_5,
        p.results_announced_at,
        p.created_at,
        p.ends_at,
        COALESCE(v.total_votes, 0)::BIGINT,
        w.winning_choice
    FROM polls p
    LEFT JOIN (SELECT poll_id, COUNT(*) AS total_votes FROM poll_votes GROUP BY poll_id) v
        ON v.poll_id = p.id
    LEFT JOIN LATERAL (
        SELECT CASE WHEN COUNT(*) FILTER (WHERE x.cnt = x.maxcnt) = 1
                    THEN (ARRAY_AGG(x.choice) FILTER (WHERE x.cnt = x.maxcnt))[1]
                    ELSE NULL END AS winning_choice
        FROM (
            SELECT choice, COUNT(*) AS cnt, MAX(COUNT(*)) OVER () AS maxcnt
            FROM poll_votes
            WHERE poll_id = p.id
            GROUP BY choice
        ) x
    ) w ON TRUE
    WHERE p.society_id = p_society_id
      AND (p_status IS NULL OR p.status = p_status)
      AND (p_search IS NULL OR p.title ILIKE '%' || p_search || '%' OR p.description ILIKE '%' || p_search || '%')
    ORDER BY p.created_at DESC;
END;
$$;
