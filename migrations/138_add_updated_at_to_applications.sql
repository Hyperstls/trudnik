-- 138_add_updated_at_to_applications.sql
-- Fix: accept_application RPC references updated_at column which doesn't exist.
-- Idempotent.

ALTER TABLE applications ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();
CREATE INDEX IF NOT EXISTS idx_applications_updated_at ON applications (updated_at);
