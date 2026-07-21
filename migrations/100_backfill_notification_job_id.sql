-- ============================================================================
-- Миграция 100: Backfill job_id в notifications из data JSONB поля
-- Проблема: старые уведомления могут иметь job_id=NULL, но job_id хранится в data->>'job_id'
-- Это мешает корректному каскадному удалению через FK
-- Решение: заполнить job_id из JSONB data поля
-- ============================================================================
BEGIN;

-- Backfill job_id в notifications из data JSONB поля
UPDATE notifications
SET job_id = (data->>'job_id')::uuid
WHERE job_id IS NULL
  AND data ? 'job_id'
  AND data->>'job_id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';

COMMIT;
