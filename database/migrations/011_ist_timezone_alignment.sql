-- IST alignment: the app writes IST (today_ist()/now_ist()), so SQL that reads "today" must not depend on the session
-- timezone, which is UTC behind a connection pooler (Neon "-pooler" hosts reject the options=-c timezone startup setting).
-- Upgrade script only: database/estatehub.sql already declares all of this, so on a fresh install this file changes nothing
-- (test_migrations_are_folded_live). Keep this file and the matching blocks in estatehub.sql identical.

-- 1) Database/role default timezone, so pooled sessions run in IST too. Needs ownership; otherwise ask the DB owner.
DO $$
BEGIN
    EXECUTE format('ALTER DATABASE %I SET timezone = %L', current_database(), 'Asia/Kolkata');
    EXECUTE format('ALTER ROLE %I IN DATABASE %I SET timezone = %L', current_user, current_database(), 'Asia/Kolkata');
EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'Could not ALTER DATABASE/ROLE timezone (insufficient privilege); ask the DB owner to run: ALTER DATABASE % SET timezone = ''Asia/Kolkata''', current_database();
END $$;

-- 2) users.setup_submit_at (5 s submit throttle) and users.locked_until (login lockout) become TIMESTAMPTZ, so comparing
--    them with NOW() / an aware now_ist() no longer depends on which timezone the session happened to be in.
--    Existing values are short-lived; naive values are read as IST wall-clock, the app's own convention (as_ist()).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'users'
                  AND column_name = 'setup_submit_at' AND data_type = 'timestamp without time zone') THEN
        ALTER TABLE users ALTER COLUMN setup_submit_at TYPE TIMESTAMPTZ USING setup_submit_at AT TIME ZONE 'Asia/Kolkata';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'users'
                  AND column_name = 'locked_until' AND data_type = 'timestamp without time zone') THEN
        ALTER TABLE users ALTER COLUMN locked_until TYPE TIMESTAMPTZ USING locked_until AT TIME ZONE 'Asia/Kolkata';
    END IF;
END $$;

-- 3) Office-term checks in fn_activate_society and fn_sign_society_decision used CURRENT_DATE (session timezone), while
--    term_start is written with today_ist(): between 00:00 and 05:30 IST a UTC session hid a just-seated office-bearer.
--    Rewrite each function from its own definition, only while it still carries the old text.
DO $$
DECLARE
    f RECORD;
    old_txt CONSTANT TEXT := 'co.term_start <= CURRENT_DATE AND (co.term_end IS NULL OR co.term_end >= CURRENT_DATE)';
    new_txt CONSTANT TEXT := 'co.term_start <= (NOW() AT TIME ZONE ''Asia/Kolkata'')::date AND (co.term_end IS NULL OR co.term_end >= (NOW() AT TIME ZONE ''Asia/Kolkata'')::date)';
BEGIN
    FOR f IN SELECT p.oid FROM pg_proc p
              WHERE p.pronamespace = 'public'::regnamespace
                AND p.proname IN ('fn_activate_society', 'fn_sign_society_decision')
                AND position(old_txt IN p.prosrc) > 0
    LOOP
        EXECUTE replace(pg_get_functiondef(f.oid), old_txt, new_txt);
    END LOOP;
END $$;
