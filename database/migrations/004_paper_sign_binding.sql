-- Paper-signing workflow: bind each signed scan to the generated document and the data snapshot it was printed from.
-- Safe to run more than once. Run after 003_paper_evidence_purposes.sql on an EXISTING database; a fresh database
-- gets all of this from estatehub.sql.
CREATE TABLE IF NOT EXISTS onboarding_documents (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    purpose TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    snapshot_sha256 CHAR(64) NOT NULL,
    document_sha256 CHAR(64) NOT NULL,
    fmt VARCHAR(8) NOT NULL DEFAULT 'pdf',
    row_count INT NOT NULL DEFAULT 0,
    signing_mode VARCHAR(12) NOT NULL DEFAULT 'paper',
    meta JSONB NOT NULL DEFAULT '{}',
    generated_by INT REFERENCES users (id),
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_onb_documents_soc ON onboarding_documents (society_id, purpose, generated_at DESC);
ALTER TABLE onboarding_evidence ADD COLUMN IF NOT EXISTS doc_id TEXT;
ALTER TABLE onboarding_evidence ADD COLUMN IF NOT EXISTS document_sha256 CHAR(64);
ALTER TABLE onboarding_evidence ADD COLUMN IF NOT EXISTS snapshot_sha256 CHAR(64);
