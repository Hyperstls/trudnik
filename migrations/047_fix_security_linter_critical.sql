-- Миграция 047: Закрытие критических уязвимостей Supabase Security Linter
-- Дата: 17.06.2026
-- Описание: Отзыв EXECUTE у anon для SECURITY DEFINER функций,
--          RLS на spatial_ref_sys, RLS-политики для email_log.
--
-- Контекст: миграции 025 и 031 уже пытались исправить exec_sql и st_estimatedextent,
-- но линтер продолжает жаловаться. Миграция 039 создала accept_application,
-- reject_application, delete_job_cascade, delete_user_cascade без REVOKE.
-- Данная миграция — идемпотентная перестраховка.

-- ============================================================================
-- 🔴 Раздел 1: exec_sql — только service_role
-- ============================================================================
-- Повторяем REVOKE из миграции 031 на случай, если она не была применена
-- или функция была пересоздана (Postgres по умолчанию даёт EXECUTE роли PUBLIC)
REVOKE EXECUTE ON FUNCTION public.exec_sql(text) FROM anon, authenticated, PUBLIC;
GRANT EXECUTE ON FUNCTION public.exec_sql(text) TO service_role;

-- ============================================================================
-- 🔴 Раздел 2: delete_user_cascade — только service_role
-- ============================================================================
-- Функция каскадно удаляет пользователя и все его данные. Должна быть
-- доступна только серверной стороне через service_role.
REVOKE EXECUTE ON FUNCTION public.delete_user_cascade(uuid) FROM anon, authenticated, PUBLIC;
GRANT EXECUTE ON FUNCTION public.delete_user_cascade(uuid) TO service_role;

-- ============================================================================
-- 🔴 Раздел 3: delete_job_cascade — только service_role
-- ============================================================================
-- Функция каскадно удаляет задание и все связанные записи.
REVOKE EXECUTE ON FUNCTION public.delete_job_cascade(uuid) FROM anon, authenticated, PUBLIC;
GRANT EXECUTE ON FUNCTION public.delete_job_cascade(uuid) TO service_role;

-- ============================================================================
-- 🟡 Раздел 4: accept_application / reject_application — только authenticated
-- ============================================================================
-- Эти функции вызываются из Flask с JWT-токеном пользователя (authenticated).
-- Анонимы не должны иметь к ним доступ.
REVOKE EXECUTE ON FUNCTION public.accept_application(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.accept_application(uuid, uuid) TO authenticated, service_role;

REVOKE EXECUTE ON FUNCTION public.reject_application(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.reject_application(uuid, uuid) TO authenticated, service_role;

-- ============================================================================
-- 🟡 Раздел 5: st_estimatedextent (PostGIS) — отзыв у anon/authenticated
-- ============================================================================
-- Повторяем REVOKE из миграции 025
DO $$
BEGIN
    REVOKE EXECUTE ON FUNCTION public.st_estimatedextent(text, text) FROM anon, authenticated, PUBLIC;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

DO $$
BEGIN
    REVOKE EXECUTE ON FUNCTION public.st_estimatedextent(text, text, text) FROM anon, authenticated, PUBLIC;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

DO $$
BEGIN
    REVOKE EXECUTE ON FUNCTION public.st_estimatedextent(text, text, text, boolean) FROM anon, authenticated, PUBLIC;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- ============================================================================
-- 🟡 Раздел 6: spatial_ref_sys — включение RLS (пропускаем)
-- ============================================================================
-- Системная таблица PostGIS. Владелец — postgres (суперпользователь).
-- На Supabase нет прав суперпользователя, поэтому ALTER TABLE ENABLE RLS
-- завершается ошибкой «must be owner of table spatial_ref_sys».
-- Это известный ложный positive Supabase Security Linter — данные таблицы
-- (~4000 строк с проекциями координат) не являются секретными.
-- Исправление невозможно без прав суперпользователя.
DO $$
BEGIN
    RAISE WARNING 'spatial_ref_sys: RLS cannot be enabled (not table owner). This is a known Supabase linter false positive for PostGIS system tables.';
END $$;

-- ============================================================================
-- 🟢 Раздел 7: email_log — RLS политики
-- ============================================================================
-- Таблица email_log имеет RLS включён, но без политик — полностью недоступна
-- через пользовательские токены. Доступ только через service_role (штатно).
-- Добавляем минимальные политики, чтобы линтер не ругался.
-- Пользователи могут видеть только свои email-логи.
DROP POLICY IF EXISTS "Users can view own email logs" ON public.email_log;
CREATE POLICY "Users can view own email logs"
    ON public.email_log
    FOR SELECT
    USING ((SELECT auth.uid()) = user_id);

-- ============================================================================
-- 🟢 Раздел 8: Очистка дублирующихся политик applications
-- ============================================================================
-- Линтер жалуется на multiple permissive policies для DELETE и UPDATE.
-- Удаляем дубликаты, оставляя по одной политике на операцию.

-- DELETE: оставляем одну политику вместо двух
DROP POLICY IF EXISTS "Users can delete own applications" ON public.applications;
DROP POLICY IF EXISTS "Workers can delete own applications" ON public.applications;
CREATE POLICY "Users can delete own applications"
    ON public.applications
    FOR DELETE
    USING ((SELECT auth.uid()) = worker_id);

-- UPDATE: оставляем одну политику вместо трёх
DROP POLICY IF EXISTS "Employers can update applications" ON public.applications;
DROP POLICY IF EXISTS "Employers can update applications on their jobs" ON public.applications;
DROP POLICY IF EXISTS "Users can update own applications" ON public.applications;
CREATE POLICY "Users can update own applications"
    ON public.applications
    FOR UPDATE
    USING (
        (SELECT auth.uid()) = worker_id
        OR
        EXISTS (
            SELECT 1 FROM jobs
            WHERE jobs.id = applications.job_id
            AND jobs.employer_id = (SELECT auth.uid())
        )
    );
