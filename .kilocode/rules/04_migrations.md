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
6. Для RLS-политик используй current_setting('request.jwt.claim.app_role', true), НЕ 'request.jwt.claim.role'.
```