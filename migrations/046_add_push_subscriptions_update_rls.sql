-- Миграция 046: Добавление UPDATE RLS-политики для push_subscriptions
-- Позволяет пользователям обновлять свои push-подписки без service_role.
-- Часть улучшения безопасности: минимизация использования SUPABASE_SERVICE_ROLE_KEY.
-- Связанный TODO: app/services/push_service.py (метод save_subscription).

-- Добавляем политику UPDATE для push_subscriptions
DROP POLICY IF EXISTS "Users can update own push subscriptions" ON public.push_subscriptions;
CREATE POLICY "Users can update own push subscriptions"
    ON public.push_subscriptions
    FOR UPDATE
    USING ((SELECT auth.uid()) = user_id)
    WITH CHECK ((SELECT auth.uid()) = user_id);
