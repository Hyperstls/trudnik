"""Сервис уведомлений: типизация, создание, проверка настроек."""

import logging
from app.utils import supabase_admin_request, supabase_request

logger = logging.getLogger(__name__)

NOTIFICATION_TYPES = {
    'application_received':  'Новый отклик',
    'application_accepted':  'Отклик принят',
    'application_rejected':  'Отклик отклонён',
    'application_cancelled': 'Отклик отменён',
    'new_message':           'Новое сообщение',
    'new_rating':            'Новая оценка',
    'job_filled':            'Задание укомплектовано',
    'job_completed':         'Задание завершено',
    'job_cancelled':         'Задание отменено',
    'job_published':         'Задание опубликовано',
    'job_restored':          'Задание восстановлено',
    'hire_limit_warning':    'Предупреждение',
    'cheque_reminder':       'Напоминание о чеке',
    'system':                'Системное',
}

DEFAULT_ENABLED_TYPES = {
    'application_received': True,
    'application_accepted': True,
    'application_rejected': True,
    'application_cancelled': True,
    'new_message': True,
    'new_rating': True,
    'job_filled': True,
    'job_completed': True,
    'job_cancelled': True,
    'job_published': True,
    'job_restored': True,
    'hire_limit_warning': True,
    'cheque_reminder': True,
    'system': True,
}


def get_user_prefs(user_id):
    """Получить настройки уведомлений пользователя.
    Используем admin_request — вызывается из любого контекста (не только владельцем)."""
    resp = supabase_admin_request('GET', f'profiles?id=eq.{user_id}&select=notification_prefs')
    if resp.ok and resp.json():
        prefs = resp.json()[0].get('notification_prefs')
        if prefs and isinstance(prefs, dict):
            return prefs
    return dict(DEFAULT_ENABLED_TYPES)


def create(user_id, notification_type, title, message, data=None):
    """Создать уведомление с проверкой настроек пользователя.

    Args:
        user_id: UUID получателя
        notification_type: ключ из NOTIFICATION_TYPES
        title: заголовок
        message: текст
        data: dict с доп. данными (job_id, application_id)

    Returns:
        bool: True если создано, False если отключено или ошибка
    """
    if notification_type not in NOTIFICATION_TYPES:
        logger.warning('Unknown notification type: %s', notification_type)
        return False

    prefs = get_user_prefs(user_id)
    if not prefs.get(notification_type, True):
        return False

    base_payload = {
        'user_id': user_id,
        'type': notification_type,
        'message': f'{title}: {message}' if title else message,
        'is_read': False,
    }
    optional_fields = {}
    if data:
        if data.get('job_id'):
            optional_fields['job_id'] = data['job_id']
        if data.get('application_id'):
            optional_fields['application_id'] = data['application_id']

    # Используем admin_request для обхода RLS:
    # уведомления создаются системой (не владельцем), user_id может не совпадать с auth.uid()
    payload = {**base_payload, **optional_fields}
    resp = supabase_admin_request('POST', 'notifications', json=payload)
    if not resp.ok:
        # Если 400 — возможно, в таблице нет колонок job_id/application_id.
        # Пробуем без опциональных полей.
        if resp.status_code == 400 and optional_fields:
            logger.warning('Notification 400 with optional fields, retrying without: %s',
                          list(optional_fields.keys()))
            resp = supabase_admin_request('POST', 'notifications', json=base_payload)
        if not resp.ok:
            logger.error('Failed to create notification: user=%s type=%s status=%s body=%s',
                         user_id, notification_type, resp.status_code, resp.text)
            return False
    return True


def get_notifications(user_id, page=1, per_page=20):
    """Получить уведомления пользователя с пагинацией (JSON-ready)."""
    offset = (page - 1) * per_page
    headers = {'Prefer': 'count=exact'}
    resp = supabase_request('GET',
        f'notifications?user_id=eq.{user_id}&order=created_at.desc'
        f'&limit={per_page}&offset={offset}', headers=headers)
    items = resp.json() if resp.ok else []
    total = int(resp.headers.get('Content-Range', '0-0/0').split('/')[-1]) if resp.ok else 0
    return {
        'results': items, 'total': total, 'page': page,
        'per_page': per_page,
        'pages': max(1, (total + per_page - 1) // per_page) if total else 1
    }


def get_unread_count(user_id):
    """Быстрый счётчик непрочитанных уведомлений."""
    resp = supabase_request('GET',
        f'notifications?user_id=eq.{user_id}&is_read=eq.false&select=id&limit=100')
    return len(resp.json()) if resp.ok else 0


def mark_all_read(user_id):
    """Пометить все уведомления пользователя прочитанными."""
    supabase_request('PATCH',
        f'notifications?user_id=eq.{user_id}&is_read=eq.false',
        json={'is_read': True})


def mark_read(notification_id):
    """Пометить одно уведомление прочитанным."""
    supabase_request('PATCH', f'notifications?id=eq.{notification_id}',
        json={'is_read': True})
