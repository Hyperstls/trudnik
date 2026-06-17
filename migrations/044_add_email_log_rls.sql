-- Миграция 044: RLS политики для email_log и push_subscriptions
-- Часть системы уведомлений v2

BEGIN;

-- Включаем RLS для новых таблиц
ALTER TABLE push_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_log ENABLE ROW LEVEL SECURITY;

-- RLS политики для push_subscriptions
-- Пользователи могут видеть только свои подписки
DROP POLICY IF EXISTS "Users can view own push subscriptions" ON push_subscriptions;
CREATE POLICY "Users can view own push subscriptions"
    ON push_subscriptions FOR SELECT
    USING (auth.uid() = user_id);

-- Пользователи могут создавать свои подписки
DROP POLICY IF EXISTS "Users can create own push subscriptions" ON push_subscriptions;
CREATE POLICY "Users can create own push subscriptions"
    ON push_subscriptions FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Пользователи могут удалять свои подписки
DROP POLICY IF EXISTS "Users can delete own push subscriptions" ON push_subscriptions;
CREATE POLICY "Users can delete own push subscriptions"
    ON push_subscriptions FOR DELETE
    USING (auth.uid() = user_id);

-- Администраторы имеют полный доступ
DROP POLICY IF EXISTS "Admins have full access to push_subscriptions" ON push_subscriptions;
CREATE POLICY "Admins have full access to push_subscriptions"
    ON push_subscriptions FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'admin'
        )
    );

-- RLS политики для email_log
-- Пользователи могут видеть только свои логи
DROP POLICY IF EXISTS "Users can view own email logs" ON email_log;
CREATE POLICY "Users can view own email logs"
    ON email_log FOR SELECT
    USING (auth.uid() = user_id);

-- Системные функции могут создавать записи (для Celery задач)
DROP POLICY IF EXISTS "Service can insert email logs" ON email_log;
CREATE POLICY "Service can insert email logs"
    ON email_log FOR INSERT
    WITH CHECK (true);  -- Разрешено для сервисных функций (используют service_role)

-- Администраторы имеют полный доступ
DROP POLICY IF EXISTS "Admins have full access to email_log" ON email_log;
CREATE POLICY "Admins have full access to email_log"
    ON email_log FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'admin'
        )
    );

COMMIT;
