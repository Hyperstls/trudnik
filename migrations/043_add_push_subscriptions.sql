-- Миграция 043: Таблицы для push-подписок и лога email-отправки
-- Часть системы уведомлений v2

BEGIN;

-- Таблица push-подписок (Web Push API)
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    endpoint TEXT NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, endpoint)
);

-- Индекс для быстрого поиска подписок пользователя
CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user_id 
    ON push_subscriptions(user_id);

-- Индекс для поиска по endpoint (для удаления/обновления)
CREATE INDEX IF NOT EXISTS idx_push_subscriptions_endpoint 
    ON push_subscriptions(endpoint);

-- Таблица лога email-отправки
CREATE TABLE IF NOT EXISTS email_log (
    id BIGSERIAL PRIMARY KEY,
    notification_id BIGINT REFERENCES notifications(id) ON DELETE SET NULL,
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    to_email TEXT,
    subject TEXT,
    template_name VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- status: pending, sent, failed, dead (dead-letter queue)
    attempts INT NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    error_message TEXT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Индексы для email_log
CREATE INDEX IF NOT EXISTS idx_email_log_user_id ON email_log(user_id);
CREATE INDEX IF NOT EXISTS idx_email_log_status ON email_log(status);
CREATE INDEX IF NOT EXISTS idx_email_log_notification_id ON email_log(notification_id);

-- Обновление notification_prefs: добавляем значения по умолчанию для email и push
-- Если поле notification_prefs в profiles ещё не имеет значений для новых типов
UPDATE profiles 
SET notification_prefs = jsonb_build_object(
    'email_enabled', COALESCE((notification_prefs->>'email_enabled')::boolean, true),
    'push_enabled', COALESCE((notification_prefs->>'push_enabled')::boolean, true),
    'in_app_enabled', COALESCE((notification_prefs->>'in_app_enabled')::boolean, true)
)
WHERE notification_prefs IS NOT NULL 
  AND notification_prefs::text <> '{}'::text
  AND (
    NOT (notification_prefs ? 'email_enabled') 
    OR NOT (notification_prefs ? 'push_enabled')
    OR NOT (notification_prefs ? 'in_app_enabled')
  );

COMMIT;
