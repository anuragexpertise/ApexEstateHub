-- Trusted devices for PIN / pattern sign-in. A PIN or pattern is only accepted together with a device token that was issued
-- to THIS login after a password sign-in on that browser (httpOnly cookie "eh_device"); only a sha256 of the token is stored.
-- One row per trusted browser, so an account can have many; signing out on a browser, or signing in there as someone else,
-- deletes only that browser's row. failed_attempts counts wrong PIN/pattern tries on this device (the app deletes the row at 5).
-- Upgrade script only: database/estatehub.sql already declares all of this, so on a fresh install this file changes nothing
-- (test_migrations_are_folded_live). Keep this file and the block in estatehub.sql identical.
CREATE TABLE IF NOT EXISTS user_devices (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,
    label VARCHAR(160),
    failed_attempts INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_user_devices_user ON user_devices (user_id);
