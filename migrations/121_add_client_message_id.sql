-- 121_add_client_message_id.sql
-- Добавление client_message_id для идемпотентности сообщений в чате
-- Предотвращает дубликаты при потере сети (клиент отправляет тот же client_message_id)

BEGIN;

-- Добавляем колонку client_message_id (опциональная, может быть NULL)
ALTER TABLE public.messages 
    ADD COLUMN IF NOT EXISTS client_message_id uuid;

-- Уникальный индекс для предотвращения дубликатов (только для non-NULL значений)
CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_client_msg_id
    ON public.messages (application_id, client_message_id)
    WHERE client_message_id IS NOT NULL;

COMMIT;
