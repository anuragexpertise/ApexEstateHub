-- ============================================================================
-- migrations/006_rbac_foundation.sql
--
-- Phase 1 (D1 = Option B): Fine-grained RBAC foundation.
--
-- Creates the role/permission vocabulary consumed by app/security/policy.py:
--   role_definitions        — society-scoped / platform role templates
--   permissions             — (resource, action) pairs
--   role_permissions        — GRANT table (ALTER: adds new cols, keeps legacy)
--   user_role_assignments   — effective-dated role membership
--   delegations             — maker/checker hand-over
--   societies_memberships   — normalised apartment/vendor/security link
--
-- Also creates the D2 append-only transition logs:
--   concern_transitions
--   poll_transitions  +  poll_eligibility_snapshot
--   channel_event_transitions
--
-- Idempotent: CREATE TABLE IF NOT EXISTS / ALTER ADD COLUMN IF NOT EXISTS
-- and INSERT ... ON CONFLICT DO NOTHING, so re-running is safe.
-- The canonical copy also lives in database/estatehub.sql (applied by
-- database/migrate.py via run_schema). This file mirrors it for direct
-- execution by a DBA against an already-provisioned database.
-- ============================================================================

BEGIN;

-- ═══════════════════════════════════════════════════════════════════════════════
-- 1. role_definitions — society-scoped / platform role vocabulary
--    scope 'platform' => system-wide (NULL society in assignments).
--    scope 'society'  => must carry a society_id in user_role_assignments.
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS role_definitions (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(40) NOT NULL,
    scope       VARCHAR(10) NOT NULL CHECK (scope IN ('platform', 'society')),
    name        VARCHAR(100) NOT NULL,
    description TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (code, scope)
);
CREATE INDEX IF NOT EXISTS idx_role_definitions_code ON role_definitions (code);
CREATE INDEX IF NOT EXISTS idx_role_definitions_scope ON role_definitions (scope);

INSERT INTO role_definitions (code, scope, name, description) VALUES
    ('platform_operator',  'platform', 'Platform Operator',  'System-wide operator (migrated master_admin). Can grant roles and close financial periods across societies.'),
    ('society_secretary',  'society',  'Society Secretary',  'AOA secretary: assign concerns, declare poll results, approve payments, grant society roles, import enrollments.'),
    ('treasurer',          'society',  'Treasurer',          'AOA treasurer: view own receipts, approve payments, close periods within approval_threshold.'),
    ('committee_member',   'society',  'Committee Member',   'Managing Committee member: declare poll results on behalf of the board.'),
    ('accountant',         'society',  'Accountant',         'Society accountant: view receipts, approve payments up to min_amount.'),
    ('resident_owner',     'society',  'Resident Owner',     'Apartment owner: view own receipts.'),
    ('resident_tenant',    'society',  'Resident Tenant',    'Apartment tenant: view own receipts.'),
    ('vendor_contact',     'society',  'Vendor Contact',     'Registered vendor: view own concerns/bids.'),
    ('security_staff',     'society',  'Security Staff',     'Society security: manage channel events, view own duty roster.')
ON CONFLICT (code, scope) DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════════════════
-- 2. permissions — (resource, action) pairs the policy engine checks
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS permissions (
    id          SERIAL PRIMARY KEY,
    resource    VARCHAR(60) NOT NULL,
    action      VARCHAR(60) NOT NULL,
    description TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (resource, action)
);
CREATE INDEX IF NOT EXISTS idx_permissions_resource ON permissions (resource);

INSERT INTO permissions (resource, action, description) VALUES
    ('concern',     'assign',              'Assign/invite an entity to a concern'),
    ('concern',     'resolve',             'Mark a concern assignment resolved/closed'),
    ('poll',        'declare_results',     'Declare poll results and close a poll'),
    ('finance',     'receipt.view_own',    'View own financial receipts'),
    ('finance',     'payment.approve',     'Approve a payment against the approval threshold'),
    ('finance',     'period.close',        'Close a financial period / FY'),
    ('enrollment',  'import',              'Bulk-enroll apartment/vendor/security members'),
    ('role',        'grant',               'Grant or revoke a society role on a user'),
    ('visitor',     'approve',             'Approve / deny a visitor / gate alert')
ON CONFLICT (resource, action) DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════════════════
-- 3. role_permissions — ALTER existing table for new columns (legacy retained)
--    Then seed the default role->permission grants.
-- ═══════════════════════════════════════════════════════════════════════════════
ALTER TABLE role_permissions
    ADD COLUMN IF NOT EXISTS role_definition_id INT REFERENCES role_definitions (id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS permission_id        INT REFERENCES permissions (id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS scope_society_id     INT REFERENCES societies (id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS min_amount           NUMERIC(12,2),
    ADD COLUMN IF NOT EXISTS approval_threshold   NUMERIC(12,2);
CREATE INDEX IF NOT EXISTS idx_role_permissions_role_def  ON role_permissions (role_definition_id);
CREATE INDEX IF NOT EXISTS idx_role_permissions_perm      ON role_permissions (permission_id);
CREATE INDEX IF NOT EXISTS idx_role_permissions_scope     ON role_permissions (scope_society_id);

-- Helper: seed a single (role_code, resource, action) grant row, idempotent.
-- scope_society_id NULL => the grant applies wherever the role is held.
INSERT INTO role_permissions (role_definition_id, permission_id, scope_society_id)
SELECT rd.id, p.id, NULL
FROM role_definitions rd, permissions p
WHERE rd.code = 'platform_operator' AND p.resource = 'role' AND p.action = 'grant'
ON CONFLICT (role_definition_id, permission_id, scope_society_id) DO NOTHING;

INSERT INTO role_permissions (role_definition_id, permission_id, scope_society_id)
SELECT rd.id, p.id, NULL
FROM role_definitions rd, permissions p
WHERE rd.code = 'platform_operator' AND p.resource = 'finance' AND p.action = 'period.close'
ON CONFLICT (role_definition_id, permission_id, scope_society_id) DO NOTHING;

INSERT INTO role_permissions (role_definition_id, permission_id, scope_society_id)
SELECT rd.id, p.id, NULL
FROM role_definitions rd, permissions p
WHERE rd.code = 'society_secretary' AND p.resource = 'concern' AND p.action = 'assign'
ON CONFLICT (role_definition_id, permission_id, scope_society_id) DO NOTHING;

INSERT INTO role_permissions (role_definition_id, permission_id, scope_society_id)
SELECT rd.id, p.id, NULL
FROM role_definitions rd, permissions p
WHERE rd.code = 'society_secretary' AND p.resource = 'concern' AND p.action = 'resolve'
ON CONFLICT (role_definition_id, permission_id, scope_society_id) DO NOTHING;

INSERT INTO role_permissions (role_definition_id, permission_id, scope_society_id)
SELECT rd.id, p.id, NULL
FROM role_definitions rd, permissions p
WHERE rd.code = 'society_secretary' AND p.resource = 'poll' AND p.action = 'declare_results'
ON CONFLICT (role_definition_id, permission_id, scope_society_id) DO NOTHING;

INSERT INTO role_permissions (role_definition_id, permission_id, scope_society_id)
SELECT rd.id, p.id, NULL
FROM role_definitions rd, permissions p
WHERE rd.code = 'society_secretary' AND p.resource = 'finance' AND p.action = 'payment.approve'
ON CONFLICT (role_definition_id, permission_id, scope_society_id) DO NOTHING;

INSERT INTO role_permissions (role_definition_id, permission_id, scope_society_id)
SELECT rd.id, p.id, NULL
FROM role_definitions rd, permissions p
WHERE rd.code = 'society_secretary' AND p.resource = 'role' AND p.action = 'grant'
ON CONFLICT (role_definition_id, permission_id, scope_society_id) DO NOTHING;

INSERT INTO role_permissions (role_definition_id, permission_id, scope_society_id)
SELECT rd.id, p.id, NULL
FROM role_definitions rd, permissions p
WHERE rd.code = 'society_secretary' AND p.resource = 'enrollment' AND p.action = 'import'
ON CONFLICT (role_definition_id, permission_id, scope_society_id) DO NOTHING;

INSERT INTO role_permissions (role_definition_id, permission_id, scope_society_id, min_amount)
SELECT rd.id, p.id, NULL, 5000
FROM role_definitions rd, permissions p
WHERE rd.code = 'accountant' AND p.resource = 'finance' AND p.action = 'payment.approve'
ON CONFLICT (role_definition_id, permission_id, scope_society_id) DO NOTHING;

INSERT INTO role_permissions (role_definition_id, permission_id, scope_society_id)
SELECT rd.id, p.id, NULL
FROM role_definitions rd, permissions p
WHERE rd.code IN ('treasurer','accountant') AND p.resource = 'finance' AND p.action = 'receipt.view_own'
ON CONFLICT (role_definition_id, permission_id, scope_society_id) DO NOTHING;

INSERT INTO role_permissions (role_definition_id, permission_id, scope_society_id)
SELECT rd.id, p.id, NULL
FROM role_definitions rd, permissions p
WHERE rd.code = 'treasurer' AND p.resource = 'finance' AND p.action = 'payment.approve'
ON CONFLICT (role_definition_id, permission_id, scope_society_id) DO NOTHING;

INSERT INTO role_permissions (role_definition_id, permission_id, scope_society_id)
SELECT rd.id, p.id, NULL
FROM role_definitions rd, permissions p
WHERE rd.code = 'treasurer' AND p.resource = 'finance' AND p.action = 'period.close'
ON CONFLICT (role_definition_id, permission_id, scope_society_id) DO NOTHING;

INSERT INTO role_permissions (role_definition_id, permission_id, scope_society_id)
SELECT rd.id, p.id, NULL
FROM role_definitions rd, permissions p
WHERE rd.code = 'committee_member' AND p.resource = 'poll' AND p.action = 'declare_results'
ON CONFLICT (role_definition_id, permission_id, scope_society_id) DO NOTHING;

INSERT INTO role_permissions (role_definition_id, permission_id, scope_society_id)
SELECT rd.id, p.id, NULL
FROM role_definitions rd, permissions p
WHERE rd.code = 'resident_owner' AND p.resource = 'finance' AND p.action = 'receipt.view_own'
ON CONFLICT (role_definition_id, permission_id, scope_society_id) DO NOTHING;

INSERT INTO role_permissions (role_definition_id, permission_id, scope_society_id)
SELECT rd.id, p.id, NULL
FROM role_definitions rd, permissions p
WHERE rd.code = 'resident_tenant' AND p.resource = 'finance' AND p.action = 'receipt.view_own'
ON CONFLICT (role_definition_id, permission_id, scope_society_id) DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════════════════
-- 4. user_role_assignments — then backfill existing admin/master users
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS user_role_assignments (
    id                SERIAL PRIMARY KEY,
    user_id           INT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role_definition_id INT NOT NULL REFERENCES role_definitions (id) ON DELETE CASCADE,
    society_id        INT REFERENCES societies (id) ON DELETE CASCADE,
    entity_link       INT,
    effective_from    TIMESTAMP NOT NULL DEFAULT NOW(),
    effective_to      TIMESTAMP,
    granted_by        INT REFERENCES users (id),
    source            VARCHAR(20) NOT NULL CHECK (source IN ('seed', 'grant', 'aoa', 'inherit')),
    status            VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked', 'expired')),
    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_ura_user_role_society_entity UNIQUE
        (user_id, role_definition_id, society_id, entity_link, effective_from)
);
CREATE INDEX IF NOT EXISTS idx_ura_user_active
    ON user_role_assignments (user_id, status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_ura_role_society
    ON user_role_assignments (role_definition_id, society_id, status);
CREATE INDEX IF NOT EXISTS idx_ura_effective
    ON user_role_assignments (user_id, role_definition_id, society_id) WHERE status = 'active'
        AND (effective_to IS NULL OR effective_to > NOW());

-- Backfill: existing is_master_admin users -> platform_operator (NULL society).
INSERT INTO user_role_assignments (user_id, role_definition_id, society_id, source, status)
SELECT u.id, rd.id, NULL, 'aoa', 'active'
FROM users u
CROSS JOIN role_definitions rd
WHERE u.is_master_admin = TRUE AND rd.code = 'platform_operator'
  AND NOT EXISTS (
      SELECT 1 FROM user_role_assignments ura
      WHERE ura.user_id = u.id
        AND ura.role_definition_id = rd.id
        AND ura.society_id IS NULL
        AND ura.status = 'active'
        AND (ura.effective_to IS NULL OR ura.effective_to > NOW())
  );

-- Backfill: society admins (admin + society_id set) -> society_secretary + treasurer.
-- Convention: the AOA bye-laws require a secretary and treasurer; until a formal
-- committee election the admin of record fills both offices.
INSERT INTO user_role_assignments (user_id, role_definition_id, society_id, source, status)
SELECT u.id, rd.id, u.society_id, 'aoa', 'active'
FROM users u
CROSS JOIN role_definitions rd
WHERE u.role = 'admin' AND u.society_id IS NOT NULL
  AND rd.code IN ('society_secretary', 'treasurer')
  AND NOT EXISTS (
      SELECT 1 FROM user_role_assignments ura
      WHERE ura.user_id = u.id
        AND ura.role_definition_id = rd.id
        AND ura.society_id = u.society_id
        AND ura.status = 'active'
        AND (ura.effective_to IS NULL OR ura.effective_to > NOW())
  );

-- ═══════════════════════════════════════════════════════════════════════════════
-- 5. delegations — maker/checker hand-over
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS delegations (
    id              SERIAL PRIMARY KEY,
    delegator_id    INT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    delegatee_id    INT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    permission_id   INT NOT NULL REFERENCES permissions (id) ON DELETE CASCADE,
    society_id      INT REFERENCES societies (id) ON DELETE CASCADE,
    entity_id       INT,
    effective_from  TIMESTAMP NOT NULL DEFAULT NOW(),
    effective_to    TIMESTAMP,
    revoked_at      TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_delegation UNIQUE
        (delegator_id, delegatee_id, permission_id, society_id, effective_from)
);
CREATE INDEX IF NOT EXISTS idx_delegations_delegatee
    ON delegations (delegatee_id) WHERE revoked_at IS NULL
        AND (effective_to IS NULL OR effective_to > NOW());
CREATE INDEX IF NOT EXISTS idx_delegations_delegator
    ON delegations (delegator_id) WHERE revoked_at IS NULL;

-- ═══════════════════════════════════════════════════════════════════════════════
-- 6. societies_memberships — normalised apartment/vendor/security link
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS societies_memberships (
    id                 SERIAL PRIMARY KEY,
    society_id         INT NOT NULL REFERENCES societies (id) ON DELETE CASCADE,
    user_id            INT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    entity_type        VARCHAR(20) NOT NULL CHECK (entity_type IN ('apartment', 'vendor', 'security')),
    entity_id          INT NOT NULL,
    role_definition_id INT REFERENCES role_definitions (id) ON DELETE SET NULL,
    effective_from     TIMESTAMP NOT NULL DEFAULT NOW(),
    effective_to       TIMESTAMP,
    status             VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'revoked')),
    created_at         TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by         INT REFERENCES users (id),
    CONSTRAINT uq_sm_society_entity UNIQUE (society_id, entity_type, entity_id),
    CONSTRAINT uq_sm_society_user    UNIQUE (society_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_sm_entity   ON societies_memberships (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_sm_user     ON societies_memberships (society_id, user_id);
CREATE INDEX IF NOT EXISTS idx_sm_active   ON societies_memberships (society_id, user_id, status)
    WHERE status = 'active';

-- ═══════════════════════════════════════════════════════════════════════════════
-- D2: Append-only transition logs (source of truth) + eligibility snapshot
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS concern_transitions (
    id              SERIAL PRIMARY KEY,
    concern_id      INT NOT NULL REFERENCES concerns (id) ON DELETE CASCADE,
    assignment_id   INT REFERENCES concerns_assigns (id) ON DELETE SET NULL,
    entity_role     VARCHAR(10) NOT NULL CHECK (entity_role IN ('ADM', 'VND', 'SEC')),
    entity_id       INT NOT NULL,
    from_state      VARCHAR(20),
    to_state        VARCHAR(20) NOT NULL CHECK (
        to_state IN ('invited', 'bid_submitted', 'declined', 'assigned',
                     'accepted', 'resolved', 'closed')
    ),
    actor_id        INT REFERENCES users (id),
    permission_used VARCHAR(60),
    comment         TEXT,
    evidence        JSONB,
    correlation_id  UUID,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_concern_transitions_concern
    ON concern_transitions (concern_id, created_at);
CREATE INDEX IF NOT EXISTS idx_concern_transitions_assignment
    ON concern_transitions (assignment_id, created_at);

CREATE TABLE IF NOT EXISTS poll_transitions (
    id              SERIAL PRIMARY KEY,
    poll_id         INT NOT NULL REFERENCES polls (id) ON DELETE CASCADE,
    from_state      VARCHAR(20),
    to_state        VARCHAR(20) NOT NULL CHECK (
        to_state IN ('created', 'opened', 'closed', 'results_declared')
    ),
    actor_id        INT REFERENCES users (id),
    permission_used VARCHAR(60),
    comment         TEXT,
    evidence        JSONB,
    correlation_id  UUID,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_poll_transitions_poll
    ON poll_transitions (poll_id, created_at);

CREATE TABLE IF NOT EXISTS poll_eligibility_snapshot (
    id          SERIAL PRIMARY KEY,
    poll_id     INT NOT NULL REFERENCES polls (id) ON DELETE CASCADE,
    apartment_id INT NOT NULL REFERENCES apartments (id),
    eligible    BOOLEAN NOT NULL DEFAULT FALSE,
    reason      TEXT,
    captured_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (poll_id, apartment_id)
);
CREATE INDEX IF NOT EXISTS idx_poll_elig_poll
    ON poll_eligibility_snapshot (poll_id, apartment_id);

CREATE TABLE IF NOT EXISTS channel_event_transitions (
    id              SERIAL PRIMARY KEY,
    event_id        INT NOT NULL REFERENCES alert_events (id) ON DELETE CASCADE,
    from_state      VARCHAR(30),
    to_state        VARCHAR(30) NOT NULL,
    actor_id        INT REFERENCES users (id),
    comment         TEXT,
    evidence        JSONB,
    correlation_id  UUID,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cet_event
    ON channel_event_transitions (event_id, created_at);

COMMIT;

-- End of 006_rbac_foundation.sql
