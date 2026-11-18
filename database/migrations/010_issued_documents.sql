-- Issued Agreements and NOCs kept as PDF evidence (app/assets/<society_id>/agreements | NOCs, SHA-256 in this table).
-- Upgrade script only: database/estatehub.sql already declares all of this, so on a fresh install this file changes nothing
-- (test_migrations_are_folded_live). Keep this file and the block in estatehub.sql identical.
CREATE TABLE IF NOT EXISTS issued_documents (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    subject_kind VARCHAR(20) NOT NULL CHECK (
        subject_kind IN (
            'noc',
            'agreement'
        )
    ),
    subject_id INT NOT NULL,
    version INT NOT NULL,
    document_no VARCHAR(64),
    filename TEXT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    size_bytes INT NOT NULL,
    text_hash CHAR(64),
    origin VARCHAR(20) NOT NULL DEFAULT 'generated' CHECK (
        origin IN (
            'generated',
            'signed_scan'
        )
    ),
    event VARCHAR(20) NOT NULL DEFAULT 'issued' CHECK (
        event IN (
            'issued',
            'printed',
            'emailed',
            'sealed',
            'uploaded'
        )
    ),
    created_by INT REFERENCES users (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_issued_document_sha UNIQUE (society_id, subject_kind, subject_id, sha256)
);

CREATE INDEX IF NOT EXISTS ix_issued_documents_subject ON issued_documents (society_id, subject_kind, subject_id, version);

CREATE OR REPLACE FUNCTION trg_issued_documents_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        -- the one allowed change: ON DELETE SET NULL on created_by when that login is removed (a cascade, so depth > 1)
        IF pg_trigger_depth() > 1 AND NEW.created_by IS NULL
           AND to_jsonb(NEW) - 'created_by' = to_jsonb(OLD) - 'created_by' THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'An issued document record cannot be edited.';
    END IF;
    IF pg_trigger_depth() > 1 THEN RETURN OLD; END IF;          -- a society being removed by cascade
    RAISE EXCEPTION 'An issued document record cannot be deleted.';
END $$;

DROP TRIGGER IF EXISTS trg_issued_documents_append_only ON issued_documents;
CREATE TRIGGER trg_issued_documents_append_only BEFORE UPDATE OR DELETE ON issued_documents
    FOR EACH ROW EXECUTE FUNCTION trg_issued_documents_append_only();
