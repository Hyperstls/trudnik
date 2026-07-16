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
    import psycopg2

    from app.config import Config

    db_url = (
        os.environ.get('DATABASE_URL')
        or os.environ.get('PGDATABASE_URL')
        or getattr(Config, 'DATABASE_URL', '')
    )
    if not db_url:
        logger.warning('ensure_postgrest_role_grants: DATABASE_URL не задан — пропуск')
        return {'status': 'skipped', 'reason': 'no DATABASE_URL'}

    conn = None
    try:
        conn = psycopg2.connect(db_url, connect_timeout=10)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT pg_has_role('trudnikapp','authenticated','member')")
        grants_ok = bool(cur.fetchone()[0])
        if grants_ok:
            logger.debug('ensure_postgrest_role_grants: гранты на месте')
            return {'status': 'ok', 'grants_present': True}

        logger.warning('ensure_postgrest_role_grants: trudnikapp потерял членство в ролях — пере-применяем гранты')
        for stmt in (
            'GRANT anon, authenticated, service_role TO trudnikapp',
            'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO authenticated, anon',
            'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated, anon',
        ):
            cur.execute(stmt)
        logger.warning('ensure_postgrest_role_grants: гранты PostgREST восстановлены')
        return {'status': 'healed', 'grants_present': False}
    except Exception as e:
        logger.warning('ensure_postgrest_role_grants: ошибка — %s', e, exc_info=True)
        return {'status': 'error', 'error': str(e)}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
