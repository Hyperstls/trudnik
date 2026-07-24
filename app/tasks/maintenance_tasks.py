"""
Периодические Celery-задачи обслуживания Trudnik.

Содержит задачи очистки orphaned-уведомлений, устаревших записей
и другую фоновую работу по поддержанию целостности данных.
"""

import logging
import os
import re as _re
from datetime import datetime, timezone
from typing import Any

from .celery_app import celery_app
from app.utils import postgrest_admin_request

logger = logging.getLogger(__name__)

# UUID-паттерн для поиска в тексте уведомлений
_UUID_RE = _re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', _re.IGNORECASE)


@celery_app.task
def cleanup_orphaned_notifications() -> dict[str, Any]:
    """Удаляет уведомления, ссылающиеся на несуществующие задания/заявки.

    Периодическая задача (рекомендуется запускать раз в час через Celery Beat).
    Проверяет:
      1. Уведомления с job_id (новая колонка из миграции 063), чьи задания удалены.
      2. Уведомления с application_id, чьи заявки удалены.
      3. Уведомления-приглашения, в тексте которых есть UUID несуществующих заданий.

    Returns:
        Словарь с результатами очистки:
            {'deleted_by_job_id': int, 'deleted_by_app_id': int,
             'deleted_by_message': int, 'errors': int}
    """
    deleted_by_job_id = 0
    deleted_by_app_id = 0
    deleted_by_message = 0
    errors = 0

    # ── 1. Уведомления с колонкой job_id, ссылающиеся на удалённые задания ──
    try:
        # Получаем все существующие job_id
        jobs_resp = postgrest_admin_request('GET', 'jobs?select=id')
        existing_job_ids: set[str] = set()
        if jobs_resp.ok and jobs_resp.json():
            existing_job_ids = {j['id'] for j in jobs_resp.json() if j.get('id')}

        # Получаем уведомления с непустым job_id
        notif_resp = postgrest_admin_request(
            'GET',
            'notifications?job_id=not.is.null&select=id,job_id'
        )
        if notif_resp.ok and notif_resp.json():
            orphan_ids = [
                n['id'] for n in notif_resp.json()
                if n.get('job_id') and n['job_id'] not in existing_job_ids
            ]
            if orphan_ids:
                # Удаляем пачками по 100
                for i in range(0, len(orphan_ids), 100):
                    batch = orphan_ids[i:i + 100]
                    ids_filter = ','.join(batch)
                    del_resp = postgrest_admin_request(
                        'DELETE',
                        f'notifications?id=in.({ids_filter})',
                        headers={'Prefer': 'count=exact'}
                    )
                    if del_resp.ok:
                        content_range = del_resp.headers.get('Content-Range', '')
                        if '/' in content_range:
                            deleted_by_job_id += int(content_range.split('/')[-1])
                        else:
                            deleted_by_job_id += len(batch)
                    else:
                        errors += 1
                        logger.error(
                            'Ошибка удаления orphaned уведомлений (job_id): status=%s body=%s',
                            del_resp.status_code,
                            (del_resp.text or '')[:500]
                        )
    except Exception as e:
        logger.exception('Ошибка при очистке orphaned уведомлений по job_id: %s', e)
        errors += 1

    # ── 2. Уведомления с колонкой application_id, ссылающиеся на удалённые заявки ──
    try:
        apps_resp = postgrest_admin_request('GET', 'applications?select=id')
        existing_app_ids: set[str] = set()
        if apps_resp.ok and apps_resp.json():
            existing_app_ids = {a['id'] for a in apps_resp.json() if a.get('id')}

        notif_resp = postgrest_admin_request(
            'GET',
            'notifications?application_id=not.is.null&select=id,application_id'
        )
        if notif_resp.ok and notif_resp.json():
            orphan_ids = [
                n['id'] for n in notif_resp.json()
                if n.get('application_id') and n['application_id'] not in existing_app_ids
            ]
            if orphan_ids:
                for i in range(0, len(orphan_ids), 100):
                    batch = orphan_ids[i:i + 100]
                    ids_filter = ','.join(batch)
                    del_resp = postgrest_admin_request(
                        'DELETE',
                        f'notifications?id=in.({ids_filter})',
                        headers={'Prefer': 'count=exact'}
                    )
                    if del_resp.ok:
                        content_range = del_resp.headers.get('Content-Range', '')
                        if '/' in content_range:
                            deleted_by_app_id += int(content_range.split('/')[-1])
                        else:
                            deleted_by_app_id += len(batch)
                    else:
                        errors += 1
                        logger.error(
                            'Ошибка удаления orphaned уведомлений (app_id): status=%s body=%s',
                            del_resp.status_code,
                            (del_resp.text or '')[:500]
                        )
    except Exception as e:
        logger.exception('Ошибка при очистке orphaned уведомлений по application_id: %s', e)
        errors += 1

    # ── 3. Уведомления-приглашения с UUID несуществующих заданий в тексте ──
    try:
        # Получаем уведомления типа invitation с текстом, содержащим UUID
        notif_resp = postgrest_admin_request(
            'GET',
            'notifications?type=eq.invitation&select=id,message'
        )
        if notif_resp.ok and notif_resp.json():
            orphan_notification_ids: set[str] = set()
            for n in notif_resp.json():
                msg = n.get('message', '')
                matches = _UUID_RE.findall(msg)
                for match in matches:
                    if match not in existing_job_ids:
                        orphan_notification_ids.add(n['id'])

            if orphan_notification_ids:
                orphan_list = list(orphan_notification_ids)
                for i in range(0, len(orphan_list), 100):
                    batch = orphan_list[i:i + 100]
                    ids_filter = ','.join(batch)
                    del_resp = postgrest_admin_request(
                        'DELETE',
                        f'notifications?id=in.({ids_filter})',
                        headers={'Prefer': 'count=exact'}
                    )
                    if del_resp.ok:
                        content_range = del_resp.headers.get('Content-Range', '')
                        if '/' in content_range:
                            deleted_by_message += int(content_range.split('/')[-1])
                        else:
                            deleted_by_message += len(batch)
                    else:
                        errors += 1
                        logger.error(
                            'Ошибка удаления orphaned уведомлений (message): status=%s body=%s',
                            del_resp.status_code,
                            (del_resp.text or '')[:500]
                        )
    except Exception as e:
        logger.exception('Ошибка при очистке orphaned уведомлений по тексту: %s', e)
        errors += 1

    total = deleted_by_job_id + deleted_by_app_id + deleted_by_message
    logger.info(
        'Очистка orphaned-уведомлений завершена: job_id=%d app_id=%d message=%d total=%d errors=%d',
        deleted_by_job_id, deleted_by_app_id, deleted_by_message, total, errors
    )

    return {
        'deleted_by_job_id': deleted_by_job_id,
        'deleted_by_app_id': deleted_by_app_id,
        'deleted_by_message': deleted_by_message,
        'total': total,
        'errors': errors,
    }


@celery_app.task
def expire_old_jobs() -> dict[str, Any]:
    """Переводит просроченные задания из 'open' в 'expired'.

    Периодическая задача (рекомендуется запускать раз в час через Celery Beat).
    Находит задания со статусом 'open', у которых expires_at < now(),
    и меняет их статус на 'expired'.

    Returns:
        Словарь с результатами: {'expired_count': int, 'errors': int}
    """
    expired_count = 0
    errors = 0

    try:
        resp = postgrest_admin_request(
            'PATCH',
            'jobs?status=eq.open&expires_at=lt.now()',
            json={'status': 'expired', 'updated_at': datetime.now(timezone.utc).isoformat()}
        )
        if resp.ok:
            content_range = resp.headers.get('Content-Range', '')
            if '/' in content_range:
                try:
                    expired_count = int(content_range.split('/')[-1])
                except (ValueError, IndexError):
                    pass
        else:
            errors += 1
            logger.error(
                'Ошибка при переводе просроченных заданий в expired: status=%s body=%s',
                resp.status_code,
                (resp.text or '')[:500]
            )
    except Exception as e:
        logger.exception('Ошибка при expire_old_jobs: %s', e)
        errors += 1

    logger.info('expire_old_jobs: переведено в expired=%d, ошибок=%d', expired_count, errors)

    return {
        'expired_count': expired_count,
        'errors': errors,
    }


@celery_app.task
def ensure_postgrest_role_grants() -> dict[str, Any]:
    """Self-heal: восстанавливает гранты ролей PostgREST, если Amvera
    перезапустил/фейловернул БД и trudnikapp потерял членство в
    anon/authenticated/service_role.

    Без этих грантов PostgREST не может SET ROLE и возвращает 403 для всех
    запросов (ломая всё приложение). PostgREST сам не умеет GRANT и сам
    падает при слетевших грантахах, поэтому проверяем/чиним через прямое
    psycopg2-подключение. Идемпотентно.

    Returns:
        {'status': 'ok'|'healed'|'skipped'|'error', ...}
    """
    import pathlib

    import psycopg2

    from app.config import Config

    # Суперпользовательское подключение (нужно для GRANT/CREATE ROLE ролей).
    # Без него гранты восстановить нельзя — только проверить и предупредить.
    admin_url = (
        os.environ.get('DATABASE_ADMIN_URL')
        or os.environ.get('ADMIN_DATABASE_URL')
    )
    db_url = (
        os.environ.get('DATABASE_URL')
        or os.environ.get('PGDATABASE_URL')
        or getattr(Config, 'DATABASE_URL', '')
    )
    if not (admin_url or db_url):
        logger.warning('ensure_postgrest_role_grants: DATABASE_URL/DATABASE_ADMIN_URL не заданы — пропуск')
        return {'status': 'skipped', 'reason': 'no DATABASE_URL'}

    # Миграции лежат в <project>/migrations (в контейнере — /app/migrations)
    mig_dir = pathlib.Path(__file__).resolve().parents[2] / 'migrations'

    def _apply_migration(filename: str) -> None:
        """Применяет SQL-файл миграции целиком (psycopg2 simple-query)."""
        cur.execute((mig_dir / filename).read_text(encoding='utf-8'))

    healed: list[str] = []
    conn = None
    try:
        # Prefer superuser (DATABASE_ADMIN_URL): GRANT/CREATE ROLE требуют его.
        conn = psycopg2.connect(admin_url or db_url, connect_timeout=10)
        conn.autocommit = True
        cur = conn.cursor()

        # Advisory lock — предотвращает гонку двух одновременных self-heal циклов
        cur.execute("SELECT pg_try_advisory_lock(42123)")
        if not bool(cur.fetchone()[0]):
            logger.debug('self-heal: другой цикл уже выполняется (advisory lock занят) — пропуск')
            return {'status': 'skipped', 'reason': 'advisory_lock_busy'}

        # 1) Гранты ролей PostgREST (миграция 123) — без них PostgREST 403 на всём.
        #    CREATE ROLE/GRANT требуют суперпользователя, поэтому чиним только при наличии admin_url.
        cur.execute("SELECT pg_has_role('trudnikapp','authenticated','member')")
        if not bool(cur.fetchone()[0]):
            if admin_url:
                logger.warning('self-heal: trudnikapp потерял членство в ролях — миграция 123 (superuser)')
                _apply_migration('123_fix_postgrest_role_grants.sql')
                healed.append('grants')
            else:
                logger.warning(
                    'self-heal: гранты ролей потеряны, но DATABASE_ADMIN_URL не задан — '
                    'требуется ручной GRANT суперпользователем (pgAdmin): '
                    "GRANT anon, authenticated, service_role TO trudnikapp;. "
                    'Без этого PostgREST отдаёт 403.'
                )

        # 1b) profiles: сузить SELECT до публичных колонок (миграция 132).
        #     123 даёт table-level SELECT на все таблицы; password_hash/email/inn/phone
        #     НЕ должны читаться anon/authenticated (P0: был слив хешей паролей).
        #     Ре-применяем КАЖДЫЙ цикл (идемпотентно), чтобы ограничение пережило
        #     ре-применение 123 при потере грантов ролей. Порядок: шаг 1 (123) → шаг 1b (132).
        try:
            _apply_migration('132_restrict_profile_sensitive_columns.sql')
        except Exception as e:
            logger.warning('self-heal: failed to re-apply 132 (profile columns): %s', e)
            try:
                conn.rollback()  # очистить aborted-состояние транзакции, не отравлять шаги дальше
            except Exception:
                pass

        # 1c) RLS на внутренних/админ-таблицах (миграция 133): audit_log,
        #     employer_subscriptions, _migrations, schema_migrations — anon не читает.
        try:
            _apply_migration('133_enable_rls_internal_tables.sql')
        except Exception as e:
            logger.warning('self-heal: failed to re-apply 133 (internal RLS): %s', e)
            try:
                conn.rollback()
            except Exception:
                pass

        # 2) Политика чтения profiles может быть удалена — гарантируем наличие,
        #    иначе профиль/выход/списки пустые (RLS deny-all).
        cur.execute(
            "SELECT count(*) FROM pg_policy WHERE polrelid='profiles'::regclass AND polcmd='r'"
        )
        if int(cur.fetchone()[0]) == 0:
            cur.execute(
                "CREATE POLICY \"Users can read own full profile\" ON public.profiles "
                "FOR SELECT USING ("
                "(current_setting('request.jwt.claims', true)::json->>'user_id')::uuid = id "
                "OR role IN ('worker', 'employer'))"
            )
            healed.append('profiles_read_policy')

        # 3) RLS-политики в старом сломанном виде request.jwt.claim.<name>
        #    (PostgREST выставляет только request.jwt.claims JSON) — миграция 125.
        cur.execute(
            "SELECT count(*) FROM pg_policy p "
            "JOIN pg_class c ON c.oid = p.polrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND ("
            "pg_get_expr(p.polqual, p.polrelid) ~ 'request\\.jwt\\.claim\\.' "
            "OR pg_get_expr(p.polwithcheck, p.polrelid) ~ 'request\\.jwt\\.claim\\.')"
        )
        if int(cur.fetchone()[0]) > 0:
            logger.warning('self-heal: RLS-политики в сломанном виде — миграция 125')
            _apply_migration('125_rls_use_jwt_claims_json.sql')
            healed.append('rls_policies')

        # 4) Триггер profiles_search_update ссылается на удалённую колонку skills — миграция 126.
        cur.execute(
            "SELECT count(*) FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE p.proname = 'profiles_search_update' AND n.nspname = 'public' "
            "AND pg_get_functiondef(p.oid) LIKE '%NEW.skills%'"
        )
        if int(cur.fetchone()[0]) > 0:
            logger.warning('self-heal: profiles_search_update битый (NEW.skills) — миграция 126')
            _apply_migration('126_fix_profiles_search_trigger.sql')
            healed.append('search_trigger')

        # 5) Auth/cascade RPC (register_user, login_user, change_password,
        #    delete_user_cascade, delete_job_cascade) используют pgcrypto и/или
        #    ссылаются на таблицы без schema-квалификации, но созданы с
        #    SET search_path = '' -> регистрация и удаление падают — миграция 130.
        cur.execute(
            "SELECT count(*) FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE p.proname IN ('register_user', 'delete_user_cascade', 'delete_job_cascade') "
            "AND n.nspname = 'public' "
            "AND coalesce(array_to_string(proconfig, ','), '') NOT LIKE '%pg_catalog%'"
        )
        if int(cur.fetchone()[0]) > 0:
            logger.warning('self-heal: auth/cascade RPC без pg_catalog в search_path — миграция 130')
            _apply_migration('130_fix_auth_rpc_pgcrypto_search_path.sql')
            healed.append('auth_rpc_search_path')

        # 6) delete_user_cascade ссылается на несуществующие колонки (rater_id/payer_id/
        #    receiver_id/favorites.employer_id) -> удаление пользователя падает — миграция 131.
        cur.execute(
            "SELECT count(*) FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE p.proname = 'delete_user_cascade' AND n.nspname = 'public' "
            "AND (pg_get_functiondef(p.oid) LIKE '%payer_id%' "
            "  OR pg_get_functiondef(p.oid) LIKE '%receiver_id%' "
            "  OR pg_get_functiondef(p.oid) LIKE '%rater_id %')"
        )
        if int(cur.fetchone()[0]) > 0:
            logger.warning('self-heal: delete_user_cascade с битыми колонками — миграция 131')
            _apply_migration('131_fix_delete_user_cascade_favorites.sql')
            healed.append('delete_user_cascade')

        if healed:
            logger.warning('self-heal: восстановлено — %s', ', '.join(healed))
            return {'status': 'healed', 'restored': healed}
        logger.debug('self-heal: БД в норме')
        return {'status': 'ok'}
    except Exception as e:
        logger.warning('ensure_postgrest_role_grants: ошибка — %s', e, exc_info=True)
        return {'status': 'error', 'error': str(e), 'restored': healed}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
