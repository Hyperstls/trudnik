@rule code architect
При создании SQL-миграций:

1. Имена файлов: NNN_description.sql (например, 097_add_column.sql)
2. ВСЕГДА используй CREATE OR REPLACE, IF NOT EXISTS, ON CONFLICT — миграции должны быть идемпотентны.
3. Для RPC-функций ВСЕГДА добавляй:
   - LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
   - REVOKE EXECUTE ON FUNCTION ... FROM PUBLIC
   - GRANT EXECUTE ON FUNCTION ... TO authenticated, service_role
4. После DROP COLUMN сначала обнови код (перестань использовать колонку), потом деплой, потом миграция.
5. Миграции, изменяющие схему (DROP, DELETE), применять ТОЛЬКО после деплоя обновлённого кода.
6. Для RLS-политик используй current_setting('request.jwt.claims', true)::json->>'app_role' (JSON-экстракция для PostgREST v14). СТАРЫЙ формат 'request.jwt.claim.app_role' НЕ РАБОТАЕТ в v14 — миграция 125 переписала все RLS на JSON.
7. Миграции НЕ запускаются автоматически при деплое (entrypoint.sh отключён). Применяй вручную после деплоя: `MIGRATIONS_ENABLED=true python scripts/apply_migrations.py`. Учёт применённых — таблица _migrations.
8. ИСКЛЮЧЕНИЕ из `search_path = ''`: функции, использующие PostGIS (`ST_MakePoint`, `ST_SetSRID`, `ST_DWithin`, `ST_Distance`, тип `geography`), НЕ могут работать с пустым search_path — PostGIS живёт в схеме `public`. Для них пиши `SET search_path = pg_catalog, public` И квалифицируй вызовы (`public.ST_MakePoint(...)`). Пример — миграция 127 (фикс `jobs_geom_update`/`nearby_jobs`). Триггер на INSERT/UPDATE ломает создание сущности, если функция падает — проверяй geo-триггеры при ошибках INSERT.
9. PostgREST SCHEMA CACHE: новые RPC-функции (CREATE FUNCTION) НЕВИДИМЫ PostgREST (404 PGRST202) до перезагрузки кэша схемы. После создания функций выполни `NOTIFY pgrst, 'reload schema'` (psycopg2 или SQL). Self-heal делает это автоматически (шаг 1g). Без NOTIFY — RPC вернёт 404 из PostgREST.
```