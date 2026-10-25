-- society_signing_keys: per-society, per-purpose wrapped signing keys
CREATE TABLE IF NOT EXISTS society_signing_keys (
    id SERIAL PRIMARY KEY,
    society_id INTEGER NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    purpose TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    key_id TEXT NOT NULL,
    wrapped_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retired_at TIMESTAMPTZ,
    UNIQUE (society_id, purpose, version)
);
CREATE INDEX IF NOT EXISTS idx_ssk_society_purpose ON society_signing_keys(society_id, purpose);
