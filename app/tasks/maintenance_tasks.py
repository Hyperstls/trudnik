"""
Периодические Celery-задачи обслуживания Trudnik.

Содержит задачи очистки orphaned-уведомлений, устаревших записей
и другую фоновую работу по поддержанию целостности данных.
"""

import logging
import re as _re
from typing import Any

from .celery_app import celery_app
from app.utils import supabase_admin_request

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
        jobs_resp = supabase_admin_request('GET', 'jobs?select=id')
        existing_job_ids: set[str] = set()
        if jobs_resp.ok and jobs_resp.json():
            existing_job_ids = {j['id'] for j in jobs_resp.json() if j.get('id')}

        # Получаем уведомления с непустым job_id
        notif_resp = supabase_admin_request(
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
                    del_resp = supabase_admin_request(
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
        apps_resp = supabase_admin_request('GET', 'applications?select=id')
        existing_app_ids: set[str] = set()
        if apps_resp.ok and apps_resp.json():
            existing_app_ids = {a['id'] for a in apps_resp.json() if a.get('id')}

        notif_resp = supabase_admin_request(
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
                    del_resp = supabase_admin_request(
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
        notif_resp = supabase_admin_request(
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
                    del_resp = supabase_admin_request(
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
