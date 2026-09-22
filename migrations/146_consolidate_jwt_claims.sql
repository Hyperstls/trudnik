-- Migration 146: Консолидация JWT-claims — единый механизм (JSON-политики, 125)
--
-- КОНТЕКСТ (architect audit v2, 2026-09): активны ДВА механизма чтения JWT-claims:
--   124: pgrst_pre_request() — materialize request.jwt.claim.<name> GUCs из JSON
--        (требует PGRST_DB_PRE_REQUEST=pgrst_pre_request на PostgREST-сервисе);
--   125: RLS-политики переписаны на request.jwt.claims::json->>'<name>'
--        (работает БЕЗ какой-либо конфигурации PostgREST).
-- Канонический механизм — 125 (JSON). 124 избыточен: все политики читают JSON.
--
-- Что делает миграция:
--   1) ПРОВЕРКА: ни одна RLS-политика не использует старый GUC-формат
--      request.jwt.claim.<name> (иначе RAISE WARNING — значит 125 не завершена,
--      выкатывать удаление pre-request НЕЛЬЗЯ до починки).
--   2) pgrst_pre_request() становится no-op: функция остаётся (PGRST_DB_PRE_REQUEST
--      может ещё указывать на неё — удаление функции при установленном env сломало бы
--      ВСЕ запросы PostgREST), но больше не делает ничего.
--
-- После этой миграции можно (не обязательно) убрать PGRST_DB_PRE_REQUEST из env
-- trudnik-pr и docker-compose. Удаление самой функции — только после этого.
--
-- Идемпотентна (CREATE OR REPLACE). Применение: MIGRATIONS_ENABLED=true python scripts/apply_migrations.py

DO $$
DECLARE
    legacy_count int;
BEGIN
    SELECT COUNT(*) INTO legacy_count
    FROM pg_policy p
    WHERE pg_get_expr(p.polqual, p.polrelid) LIKE '%request.jwt.claim.%'
       OR pg_get_expr(p.polwithcheck, p.polrelid) LIKE '%request.jwt.claim.%';

    IF legacy_count > 0 THEN
        RAISE WARNING 'migration 146: найдено % политик в старом GUC-формате request.jwt.claim.<name> — сначала примените 125', legacy_count;
    ELSE
        RAISE NOTICE 'migration 146: все политики в JSON-формате (125), pre-request избыточен';
    END IF;
END $$;

-- pre-request становится no-op (сохраняем имя — env может ещё ссылаться на него)
CREATE OR REPLACE FUNCTION public.pgrst_pre_request() RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    -- no-op: claims читаются политиками напрямую из request.jwt.claims (миграция 125).
    -- Функция сохранена для совместимости с PGRST_DB_PRE_REQUEST; удалить после
    -- снятия env-переменной с сервиса PostgREST.
    RETURN;
END;
$$;

REVOKE ALL ON FUNCTION public.pgrst_pre_request() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.pgrst_pre_request() TO authenticated, service_role, anon;

NOTIFY pgrst, 'reload schema';
