-- Add missing columns for enhanced authentication
-- Run this script to add columns for PIN, Pattern, JWT, push notifications, and forgot password

-- Migration: auth_enhanced.sql
-- Run: python3 database/migrate.py --sql database/auth_enhanced.sql

-- ═══════════════════════════════════════════════════════════════════════════
-- Add columns for rate limiting (failed login attempts tracking)
-- ════════════════════════════════════════════════════════════════════════════

ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP;

-- ═══════════════════════════════════════════════════════════════════════════
-- Add columns for password reset (forgot password feature)
-- ════════════════════════════════════════════════════════════════════════════

ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token VARCHAR(64);
ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expires TIMESTAMP;

-- ═══════════════════════════════════════════════════════════════════════════
-- Add columns for push notifications (device token tracking)
-- ════════════════════════════════════════════════════════════════════════════

ALTER TABLE users ADD COLUMN IF NOT EXISTS push_token TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS push_enabled BOOLEAN DEFAULT FALSE;

-- ═══════════════════════════════════════════════════════════════════════════
-- Add last login timestamp
-- ════════════════════════════════════════════════════════════════════════════

ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMP;

-- ═══════════════════════════════════════════════════════════════════════════
-- Create indexes for performance
-- ════════════════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_users_reset_token ON users(reset_token);
CREATE INDEX IF NOT EXISTS idx_users_reset_token_expires ON users(reset_token_expires);
CREATE INDEX IF NOT EXISTS idx_users_locked_until ON users(locked_until);
CREATE INDEX IF NOT EXISTS idx_users_login_method ON users(login_method);

-- ════════════════════════════════════════════════════════════════════════════
-- Set DEFAULT for push_enabled
-- ════════════════════════════════════════════════════════════════════════════

ALTER TABLE users ALTER COLUMN push_enabled SET DEFAULT FALSE;