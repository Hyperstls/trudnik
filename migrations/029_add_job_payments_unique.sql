-- Migration 029: Защита от race condition двойной оплаты
-- Уникальный индекс для предотвращения дублирования paid-платежей на одно задание

CREATE UNIQUE INDEX IF NOT EXISTS idx_job_payments_paid_unique 
ON job_payments (job_id) WHERE status = 'paid';
