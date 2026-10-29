-- 148: роль БД для Django-компаньона (djadmin/, ветка main-jango).
--
-- Назначение: Django-приложение (админка + публичные read-only страницы) ходит в БД
-- напрямую (не через PostgREST), поэтому ему нужна собственная роль с полным доступом
-- к таблицам/RPC и BYPASSRLS (админка обязана видеть все строки; публичная видимость
-- ограничивается queryset'ами — см. djadmin/core/models.py, JobManager/ProfileManager).
--
-- Пароль НЕ хранится в репозитории. После применения миграции суперпользователь
-- однократно включает вход и задаёт секрет (кладётся в env проекта Amvera trudnik-dj):
--   ALTER ROLE trudnik_dj LOGIN PASSWORD '<секрет>';
-- Локальная разработка это не использует (docker-compose: суперюзер trudnik).
--
-- Идемпотентно; применяется scripts/apply_migrations.py (DATABASE_ADMIN_URL).

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'trudnik_dj') THEN
        CREATE ROLE trudnik_dj NOLOGIN BYPASSRLS;
    END IF;
END
$$;

-- DML на все существующие таблицы (включая будущие системные таблицы Django,
-- которые создаются в public: django_session, django_admin_log, auth_group, ...).
GRANT USAGE, CREATE ON SCHEMA public TO trudnik_dj;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO trudnik_dj;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO trudnik_dj;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO trudnik_dj;

-- Права по умолчанию для будущих объектов, создаваемых владельцем схемы (trudnik):
ALTER DEFAULT PRIVILEGES FOR ROLE trudnik IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO trudnik_dj;
ALTER DEFAULT PRIVILEGES FOR ROLE trudnik IN SCHEMA public
    GRANT USAGE ON SEQUENCES TO trudnik_dj;
ALTER DEFAULT PRIVILEGES FOR ROLE trudnik IN SCHEMA public
    GRANT EXECUTE ON FUNCTIONS TO trudnik_dj;

-- Таблицы Django создаёт роль trudnik_dj: ей нужны права на свои объекты (владелец),
-- а также SELECT на справочники для ORM-валидации. Ничего сверх GRANT выше не требуется.
