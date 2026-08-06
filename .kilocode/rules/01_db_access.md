@rule code review architect
НИКОГДА не используй SQLAlchemy, ORM-паттерны или raw SQL для бизнес-логики. 

99% операций с БД должны реализовываться ИСКЛЮЧИТЕЛЬНО через HTTP-клиент (requests.Session) к PostgREST API. 
Для парсинга JSON-ответов от PostgREST используй существующий класс PostgrestResponse (app/utils/postgrest_client.py). 
НЕ используй Pydantic для парсинга ответов PostgREST — проект использует обычные dict/list.

Исключения (где psycopg2 разрешён):
1. app/services/auth_service.py (_login_direct_sql — fallback логин)
2. scripts/emergency_reset_users.py (CLI-only)
3. scripts/emergency_fix_permissions.py (CLI-only)
4. scripts/check_schema.py (диагностика)
5. scripts/apply_migrations.py (применение SQL-миграций)
6. app/tasks/maintenance_tasks.py (self-heal: ensure_postgrest_role_grants — DDL/GRANT/ALTER FUNCTION через DATABASE_ADMIN_URL; применяет миграции 123-137 + NOTIFY pgrst 'reload schema')
```
