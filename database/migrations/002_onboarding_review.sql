-- 002_onboarding_review.sql
-- Onboarding review plan migrations (PR-0/PR-6/PR-9/PR-10)

-- societies
ALTER TABLE societies ADD COLUMN IF NOT EXISTS onboarding_phase TEXT
  CHECK (onboarding_phase IN ('enrollment','adoption','advisers','complete'));
UPDATE societies SET onboarding_phase = 'complete' WHERE onboarding_state = 'active' AND onboarding_phase IS NULL;

ALTER TABLE societies ADD COLUMN IF NOT EXISTS signing_mode TEXT NOT NULL DEFAULT 'password'
  CHECK (signing_mode IN ('password','esign','paper'));
UPDATE societies SET signing_mode = 'esign' WHERE esign_required IS TRUE;

ALTER TABLE societies ADD COLUMN IF NOT EXISTS stepup_review_required BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE societies ADD COLUMN IF NOT EXISTS stepup_initial BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE societies ADD COLUMN IF NOT EXISTS stepup_changed_at TIMESTAMPTZ;

-- step-up password change (3 signatures)
CREATE TABLE IF NOT EXISTS stepup_change_requests (
  id SERIAL PRIMARY KEY,
  society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
  requested_by INT NOT NULL REFERENCES users(id),
  new_hash TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','applied','declined','cancelled')),
  master_assist_ref TEXT,
  master_assist_sha256 TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  decided_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_stepup_open ON stepup_change_requests(society_id) WHERE status = 'open';

-- evidence
CREATE TABLE IF NOT EXISTS onboarding_evidence (
  id SERIAL PRIMARY KEY,
  society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
  purpose TEXT NOT NULL CHECK (purpose IN ('bank_statement','cash_count','audited_report','review_letter','paper_signature')),
  acc_id INT,
  filename TEXT NOT NULL,
  stored_name TEXT NOT NULL,
  sha256 CHAR(64) NOT NULL,
  size_bytes INT NOT NULL,
  meta JSONB NOT NULL DEFAULT '{}',
  uploaded_by INT REFERENCES users(id),
  uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_onb_evidence_soc ON onboarding_evidence(society_id, purpose);

-- opening receivables pending
CREATE TABLE IF NOT EXISTS opening_receivables_pending (
  id SERIAL PRIMARY KEY,
  society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
  flat_number TEXT NOT NULL,
  amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
  overdue_days INT,
  remarks TEXT,
  status TEXT NOT NULL DEFAULT 'pending_link' CHECK (status IN ('pending_link','linked','void_requested')),
  apartment_id INT,
  receivable_id INT,
  void_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  linked_at TIMESTAMPTZ,
  UNIQUE (society_id, flat_number)
);

-- jobs + events
CREATE TABLE IF NOT EXISTS onboarding_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','done','failed')),
  step INT NOT NULL DEFAULT 0,
  steps_total INT NOT NULL DEFAULT 7,
  message TEXT,
  error TEXT,
  result JSONB,
  created_by INT REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_onb_jobs_soc ON onboarding_jobs(society_id, created_at DESC);

CREATE TABLE IF NOT EXISTS onboarding_events (
  id SERIAL PRIMARY KEY,
  society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
  event TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_onb_events_soc ON onboarding_events(society_id, created_at DESC);

-- law catalog
ALTER TABLE legal_instrument_catalog ADD COLUMN IF NOT EXISTS applies_when TEXT NOT NULL DEFAULT 'always';

-- Ensure gen_random_uuid available if needed (pgcrypto) - best effort
DO $$ BEGIN
  CREATE EXTENSION IF NOT EXISTS pgcrypto;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;
