-- ============================================================================
-- migrations/005_aoa_bye_laws.sql
--
-- Phase 0: AOA Bye-Laws Acceptance & Governance
--
-- New tables for:
--   society_bye_laws      — clause-level bye-law register (4-layer hierarchy)
--   meetings              — GBM / EGM / MC meeting records
--   resolutions           — Decisions linked to meetings and clauses
--   decision_types        — Whitelisted decision codes (GBM/MC, majority %)
--   resolution_effects    — Enactment handlers (set_regime_param, set_society_policy, set_board_param)
--
-- Idempotent: safe to re-run via CREATE IF NOT EXISTS / ON CONFLICT DO NOTHING
-- ============================================================================

BEGIN;

-- ═══════════════════════════════════════════════════════════════════════════════
-- 1. decision_types — whitelisted decision codes (seeded below)
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS decision_types (
    id                  SERIAL PRIMARY KEY,
    code                VARCHAR(40) NOT NULL UNIQUE,
    label               VARCHAR(120) NOT NULL,
    required_body       VARCHAR(10) NOT NULL CHECK (required_body IN ('GBM', 'MC')),
    majority_pct        NUMERIC(5, 2) NOT NULL DEFAULT 50.00 CHECK (majority_pct > 0 AND majority_pct <= 100),
    description         TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- 2. meetings — GBM / EGM / MC records
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS meetings (
    id                  SERIAL PRIMARY KEY,
    society_id          INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    type                VARCHAR(10) NOT NULL CHECK (type IN ('GBM', 'EGM', 'MC')),
    held_on             DATE NOT NULL,
    quorum_met          BOOLEAN NOT NULL DEFAULT FALSE,
    minutes_pdf         VARCHAR(255),          -- path only; no blob storage
    created_by          INT REFERENCES users (id),
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_meetings_society ON meetings (society_id, held_on DESC);

-- ═══════════════════════════════════════════════════════════════════════════════
-- 3. resolutions — Decisions linked to meetings and bye-law clauses
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS resolutions (
    id                  SERIAL PRIMARY KEY,
    meeting_id          INT NOT NULL REFERENCES meetings (id) ON DELETE CASCADE,
    clause_id           VARCHAR(30),           -- links to society_bye_laws.clause_id (NULL for non-clause decisions)
    decision_type_id    INT NOT NULL REFERENCES decision_types (id),
    body                TEXT NOT NULL,         -- resolution text
    majority_required   NUMERIC(5, 2) NOT NULL, -- snapshot from decision_type at time of vote
    passed              BOOLEAN NOT NULL DEFAULT FALSE,
    passed_on           DATE,
    text                TEXT,                  -- full resolution text for records
    created_by          INT REFERENCES users (id),
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_resolutions_meeting ON resolutions (meeting_id);
CREATE INDEX IF NOT EXISTS idx_resolutions_clause ON resolutions (clause_id);

-- ═══════════════════════════════════════════════════════════════════════════════
-- 4. resolution_effects — Enactment queue (whitelisted handlers only)
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS resolution_effects (
    id                  SERIAL PRIMARY KEY,
    resolution_id       INT NOT NULL REFERENCES resolutions (id) ON DELETE CASCADE,
    handler_name        VARCHAR(60) NOT NULL CHECK (handler_name IN ('set_regime_param', 'set_society_policy', 'set_board_param')),
    payload_json        JSONB NOT NULL,
    executed_at         TIMESTAMP,
    status              VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'executed', 'failed')),
    error_message       TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_resolution_effects_resolution ON resolution_effects (resolution_id);

-- ═══════════════════════════════════════════════════════════════════════════════
-- 5. society_bye_laws — Clause-level bye-law register (4-layer hierarchy)
--    Layer 0: Statute (UP Apartment Act 2010) — LOCKED, not stored here
--    Layer 1: Model Bye-Laws 2011 — per clause: Adopt as-is | Adopt with variation | Not adopted
--    Layer 2: Society Policies — GBM resolution required; can tighten Layer 1, never loosen
--    Layer 3: Board Decisions — MC resolution; operational parameters within policy bounds
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS society_bye_laws (
    id                  BIGSERIAL PRIMARY KEY,
    society_id          INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    clause_id           VARCHAR(30) NOT NULL,          -- e.g., 'BL_07', 'BL_39', 'BL_46'
    layer               INT NOT NULL CHECK (layer IN (1, 2, 3)),
    status              VARCHAR(20) NOT NULL CHECK (status IN ('adopted_as_is', 'adopted_with_variation', 'not_adopted', 'provisional')),
    variation_text      TEXT,                          -- only when status = 'adopted_with_variation'
    resolution_id       INT REFERENCES resolutions (id) ON DELETE SET NULL, -- links provisional → active
    effective_from      DATE NOT NULL DEFAULT CURRENT_DATE,
    effective_to        DATE,
    created_by          INT REFERENCES users (id),
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (society_id, clause_id, layer, effective_from)
);
CREATE INDEX IF NOT EXISTS idx_society_bye_laws_lookup ON society_bye_laws (society_id, clause_id, layer, effective_from DESC);
CREATE INDEX IF NOT EXISTS idx_society_bye_laws_provisional ON society_bye_laws (society_id, status) WHERE status = 'provisional';

-- ═══════════════════════════════════════════════════════════════════════════════
-- 6. Seed decision_types (10 rows) — whitelisted codes for resolutions
-- ═══════════════════════════════════════════════════════════════════════════════
INSERT INTO decision_types (code, label, required_body, majority_pct, description) VALUES
    ('ADOPT_BYE_LAW',        'Adopt Model Bye-Law Clause',            'GBM', 66.67, 'Adopt a Model Bye-Law 2011 clause as-is or with variation (2/3 majority per Model Bye-Law 58)'),
    ('VARY_BYE_LAW',         'Vary Adopted Bye-Law Clause',           'GBM', 66.67, 'Change variation text of an already-adopted clause (2/3 majority)'),
    ('REJECT_BYE_LAW',       'Not Adopt Model Bye-Law Clause',        'GBM', 50.00, 'Record that a non-mandatory Model Bye-Law clause is not adopted (simple majority)'),
    ('SET_SOCIETY_POLICY',   'Set Society Policy (Layer 2)',          'GBM', 66.67, 'Create or tighten a society policy within an adopted clause (2/3 majority; never loosens Model Bye-Law)'),
    ('SET_BOARD_PARAM',      'Set Board Parameter (Layer 3)',         'MC',  50.00, 'Operational parameter set by Managing Committee (simple majority; within policy bounds)'),
    ('APPROVE_LOAN',         'Approve Owner Loan',                    'GBM', 66.67, 'General Body approval for lending to an owner (Bye-Law 3(1)(f))'),
    ('APPROPRIATE_FUND',     'Appropriate Funds (Reserve/Sinking)',   'GBM', 66.67, 'General Body resolution for fund appropriation per Bye-Laws 46-52'),
    ('SERVICE_CUTOFF',       'Authorize Service Cut-Off (s.22)',      'GBM', 66.67, 'General Body resolution to cut essential service per UP Apartment Act s.22'),
    ('AMEND_CASH_LIMIT',     'Change Cash-Limit Enforcement Mode',    'GBM', 50.00, 'Override cash_limit_mode for this society (simple majority)'),
    ('GENERAL_RESOLUTION',   'General Resolution',                    'GBM', 50.00, 'Any other GBM resolution not covered above')
ON CONFLICT (code) DO NOTHING;

COMMIT;

-- End of 005_aoa_bye_laws.sql