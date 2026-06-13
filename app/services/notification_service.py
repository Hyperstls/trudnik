"""Сервис уведомлений: типизация, создание, проверка настроек."""

import logging
from app.utils import supabase_admin_request, supabase_request

logger = logging.getLogger(__name__)

NOTIFICATION_TYPES = {
    'status_change':         'Изменение статуса',
    'application_received':  'Новый отклик',
    'application_accepted':  'Отклик принят',
    'application_rejected':  'Отклик отклонён',
    'worker_accepted':       'Работник принят',
    'worker_rejected':       'Работник отклонён',
    'worker_applied':        'Отклик работника',
    'new_application':       'Новая заявка',
    'force_complete':        'Завершение задания',
    'withdraw':              'Отзыв отклика',
    'job_cancelled':         'Задание отменено',
    'invitation':            'Приглашение',
    'new_message':           'Новое сообщение',
    'cheque_reminder':       'Напоминание о чеке',
}

DEFAULT_ENABLED_TYPES = {
    'status_change': True,
    'application_received': True,
    'application_accepted': True,
    'application_rejected': True,
    'worker_accepted': True,
    'worker_rejected': True,
    'worker_applied': True,
    'new_application': True,
    'force_complete': True,
    'withdraw': True,
    'job_cancelled': True,
    'invitation': True,
    'new_message': True,
    'cheque_reminder': True,
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
        'data': data if data else {},
    }

    # Используем admin_request для обхода RLS:
    # уведомления создаются системой (не владельцем), user_id может не совпадать с auth.uid()
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
