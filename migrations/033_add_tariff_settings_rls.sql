-- ============================================================================
-- Миграция 033: Добавление INSERT и UPDATE RLS-политик для tariff_settings
-- Проблема: таблица tariff_settings имела только SELECT-политику,
-- поэтому админ не мог сохранить цены монетизации (PATCH блокировался RLS).
-- Актуально на: 13.06.2026
-- ============================================================================

-- INSERT: только администратор может создавать новые тарифы
DROP POLICY IF EXISTS "Admin can insert tariff settings" ON tariff_settings;
CREATE POLICY "Admin can insert tariff settings" ON tariff_settings
    FOR INSERT WITH CHECK (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

-- UPDATE: только администратор может изменять тарифы
DROP POLICY IF EXISTS "Admin can update tariff settings" ON tariff_settings;
CREATE POLICY "Admin can update tariff settings" ON tariff_settings
    FOR UPDATE USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    ) WITH CHECK (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );
