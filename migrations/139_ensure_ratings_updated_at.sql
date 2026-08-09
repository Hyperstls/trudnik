-- 139_ensure_ratings_updated_at.sql
-- Страховка: ratings.updated_at должна быть (есть в 067 bootstrap, но backup мог быть старше).
-- Идемпотентно.

ALTER TABLE ratings ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();
