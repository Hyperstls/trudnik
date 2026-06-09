"""Сервис уведомлений: типизация, создание, проверка настроек."""

import logging
from app.utils import supabase_request

logger = logging.getLogger(__name__)

NOTIFICATION_TYPES = {
    'application_received':  'Новый отклик',
    'application_accepted':  'Отклик принят',
    'application_rejected':  'Отклик отклонён',
    'application_cancelled': 'Отклик отменён',
    'shift_checkin':         'Чек-ин',
    'shift_complete':        'Смена завершена',
    'shift_reminder':        'Напоминание о смене',
    'payment_confirmed':     'Оплата подтверждена',
    'payment_received':      'Оплата получена',
    'new_message':           'Новое сообщение',
    'new_rating':            'Новая оценка',
    'job_filled':            'Задание укомплектовано',
    'job_completed':         'Задание завершено',
    'job_cancelled':         'Задание отменено',
    'system':                'Системное',
}

DEFAULT_ENABLED_TYPES = {
    'application_received': True,
    'application_accepted': True,
    'application_rejected': True,
    'application_cancelled': True,
    'shift_checkin': True,
    'shift_complete': True,
    'shift_reminder': True,
    'payment_confirmed': True,
    'payment_received': True,
    'new_message': True,
    'new_rating': True,
    'job_filled': True,
    'job_completed': True,
    'job_cancelled': True,
    'system': True,
}


def get_user_prefs(user_id):
    """Получить настройки уведомлений пользователя."""
    resp = supabase_request('GET', f'profiles?id=eq.{user_id}&select=notification_prefs')
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
        data: dict с доп. данными (job_id, shift_id, application_id)

    Returns:
        bool: True если создано, False если отключено или ошибка
    """
    if notification_type not in NOTIFICATION_TYPES:
        logger.warning('Unknown notification type: %s', notification_type)
        return False

    prefs = get_user_prefs(user_id)
    if not prefs.get(notification_type, True):
        return False

    payload = {
        'user_id': user_id,
        'type': notification_type,
        'title': title,
        'message': message,
        'data': data or {},
        'is_read': False,
    }

    resp = supabase_request('POST', 'notifications', json=payload)
    if not resp.ok:
        logger.error('Failed to create notification: user=%s type=%s status=%s',
                     user_id, notification_type, resp.status_code)
        return False
    return True
