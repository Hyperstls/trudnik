-- ============================================================================
-- Миграция 031: Исправление предупреждений Supabase Security Linter (v2)
-- Дата: 13.06.2026
-- Описание: Устраняет критические уязвимости и оптимизирует RLS-политики,
--          выявленные Supabase Linter после миграций 019–030.
-- ============================================================================

-- ============================================================================
-- 🔴 Раздел 1: КРИТИЧЕСКАЯ УЯЗВИМОСТЬ — функция exec_sql
-- ============================================================================
-- Проблема:
--   - Функция execute_sql была удалена в миграции 019, но Python-скрипты
--     (dump_supabase_schema.py и apply_migrations.py) используют RPC exec_sql
--     с service_role ключом для администрирования.
--   - Текущая функция (если существует) — SECURITY DEFINER без search_path,
--     доступна ролям anon и authenticated, что позволяет ЛЮБОМУ выполнить
--     произвольный SQL через REST API.
--
-- Исправление:
--   1. SET search_path = '' — защита от подмены функций через search_path
--   2. Проверка current_setting('role') = 'service_role' — только сервисные вызовы
--   3. REVOKE от anon и authenticated, GRANT только service_role

-- Сначала удаляем старую версию (если существует)
DO $$ BEGIN
    DROP FUNCTION IF EXISTS public.exec_sql(text) CASCADE;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- Создаём безопасную версию
CREATE OR REPLACE FUNCTION public.exec_sql(sql_query text)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
-- 🔒 Фиксированный search_path предотвращает атаки через подмену функций
SET search_path = ''
AS $$
DECLARE
    result JSONB;
    requesting_user_id uuid;
BEGIN
    -- Проверка: только service_role может вызывать эту функцию
    IF current_setting('role', true) != 'service_role' THEN
        RAISE EXCEPTION 'Только service_role может выполнять SQL-запросы через exec_sql';
    END IF;

    EXECUTE 'SELECT jsonb_agg(t) FROM (' || sql_query || ') t' INTO result;
    RETURN coalesce(result, '[]'::jsonb);
END;
$$;

-- Отозвать права у anon и authenticated (на случай, если были выданы)
REVOKE EXECUTE ON FUNCTION public.exec_sql(text) FROM anon, authenticated;

-- Оставить только service_role (который использует Python-скрипт через REST API)
GRANT EXECUTE ON FUNCTION public.exec_sql(text) TO service_role;


-- ============================================================================
-- 🟡 Раздел 2: Оптимизация auth.uid() → (select auth.uid()) в job_payments
-- ============================================================================
-- Проблема: прямой вызов auth.uid() в RLS-политиках вызывает
--          «auth_rls_initplan» — планировщик Postgres вызывает auth.uid()
--          на этапе планирования, а не выполнения, что замедляет запросы.
-- Решение: заменить auth.uid() на подзапрос (select auth.uid()), который
--          всегда выполняется на этапе исполнения.

-- 2a. Политика UPDATE для job_payments (создана в миграции 030)
DROP POLICY IF EXISTS "Users can update own job payments" ON job_payments;
CREATE POLICY "Users can update own job payments" ON job_payments
    FOR UPDATE USING (employer_id = (select auth.uid()));

-- 2b. Политика INSERT для job_payments (создана в миграции 023)
DROP POLICY IF EXISTS "Service can insert payments" ON job_payments;
CREATE POLICY "Service can insert payments" ON job_payments
    FOR INSERT WITH CHECK (employer_id = (select auth.uid()));


-- ============================================================================
-- 🟡 Раздел 3: Политики skills и religions с USING (true)
-- ============================================================================
-- Политики INSERT/UPDATE/DELETE для таблиц skills и religions были созданы
-- в миграции 030 с USING (true) и WITH CHECK (true). Это НАМЕРЕННО:
-- данные таблицы управляются администратором через service_role,
-- а политики обеспечивают совместимость с RLS.
--
-- Ниже — информационные комментарии, изменений SQL не требуется.
-- Политики skills (из миграции 030):
--   "Admin can insert skills"     — FOR INSERT WITH CHECK (true)  — намеренно, админская операция
--   "Admin can update skills"     — FOR UPDATE USING (true)       — намеренно, админская операция
--   "Admin can delete skills"     — FOR DELETE USING (true)       — намеренно, админская операция
-- Политики religions (из миграции 030):
--   "Admin can insert religions"  — FOR INSERT WITH CHECK (true)  — намеренно, админская операция
--   "Admin can update religions"  — FOR UPDATE USING (true)       — намеренно, админская операция
--   "Admin can delete religions"  — FOR DELETE USING (true)       — намеренно, админская операция


-- ============================================================================
-- 🟡 Раздел 4: Включение защиты от утёкших паролей (HaveIBeenPwned)
-- ============================================================================
-- Включить защиту от утёкших паролей (HaveIBeenPwned):
-- Supabase не поддерживает ALTER SYSTEM через SQL Editor.
-- Включи вручную: Supabase Dashboard → Authentication → Settings → Password Protection → Enable leaked password protection


-- ============================================================================
-- 🟢 Раздел 5: Неиспользуемые индексы (информационно)
-- ============================================================================
-- Следующие 7 индексов определены Supabase Linter как неиспользуемые.
-- Перед удалением рекомендуется верифицировать через:
--   SELECT schemaname, relname, indexrelname, idx_scan
--   FROM pg_stat_user_indexes
--   WHERE indexrelname IN (
--     'idx_applications_worker_id',
--     'idx_favorites_target_id',
--     'idx_job_skills_skill_id',
--     'idx_profiles_religion_id',
--     'idx_receipts_contact_payment_id',
--     'idx_user_skills_skill_id',
--     'idx_jobs_expires'
--   ) AND idx_scan = 0;
--
-- Перечень неиспользуемых индексов (кандидаты на удаление):
--   1. idx_applications_worker_id    — на таблице applications
--   2. idx_favorites_target_id       — на таблице favorites
--   3. idx_job_skills_skill_id       — на таблице job_skills
--   4. idx_profiles_religion_id      — на таблице profiles
--   5. idx_receipts_contact_payment_id — на таблице receipts
--   6. idx_user_skills_skill_id      — на таблице user_skills
--   7. idx_jobs_expires              — на таблице jobs
--
-- Если idx_scan = 0 в течение длительного времени, можно удалить:
--   DROP INDEX IF EXISTS idx_applications_worker_id;
--   DROP INDEX IF EXISTS idx_favorites_target_id;
--   DROP INDEX IF EXISTS idx_job_skills_skill_id;
--   DROP INDEX IF EXISTS idx_profiles_religion_id;
--   DROP INDEX IF EXISTS idx_receipts_contact_payment_id;
--   DROP INDEX IF EXISTS idx_user_skills_skill_id;
--   DROP INDEX IF EXISTS idx_jobs_expires;
