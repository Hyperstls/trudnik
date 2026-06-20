"""Сервис уведомлений: типизация, создание, проверка настроек.

БЕЗОПАСНОСТЬ (service_role):
    create() и get_user_prefs() используют supabase_admin_request (service_role),
    потому что:
    - Создание уведомлений (INSERT в notifications) — системная операция.
      RLS-политика notifications разрешает INSERT только для service_role
      (политика "Service can insert notifications").
    - Чтение notification_prefs из profiles и email из profiles — вызывается
      из контекста, где user_id может не совпадать с auth.uid()
      (например, при создании уведомления от имени системы другому пользователю).
    - Профиль читается для получения email при отправке email/push-уведомлений
      через Celery, где нет сессии пользователя.
"""

import logging
import traceback
from app.utils import supabase_admin_request, supabase_request

logger = logging.getLogger(__name__)

# Безопасный импорт: если redis не установлен — redis_publisher будет в режиме no-op,
# все вызовы publish_notification() будут молча возвращать False.
try:
    from app.services.redis_publisher import redis_publisher
except ImportError:
    redis_publisher = None
    logger.warning("redis_publisher не загружен — WebSocket-уведомления отключены")

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


def create(user_id, notification_type, title, message, data=None, email=None, username=None):
    """Создать уведомление с проверкой настроек пользователя.

    Args:
        user_id: UUID получателя
        notification_type: ключ из NOTIFICATION_TYPES
        title: заголовок
        message: текст
        data: dict с доп. данными (job_id, application_id)
        email: (опционально) email получателя для ускорения отправки
        username: (опционально) имя получателя для ускорения отправки

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
    headers = {'Prefer': 'return=representation'}
    resp = supabase_admin_request('POST', 'notifications', json=base_payload, headers=headers)
    if not resp.ok:
        logger.error('Failed to create notification: user=%s type=%s status=%s body=%s',
                     user_id, notification_type, resp.status_code, resp.text)
        return False

    # Получаем ID созданного уведомления из ответа
    notification_id = None
    try:
        resp_data = resp.json()
        if isinstance(resp_data, list) and len(resp_data) > 0:
            notification_id = resp_data[0].get('id')
    except Exception:
        pass

    # full_message уже вычислен в base_payload['message'] (строка 79)
    full_message = base_payload['message']

    # Публикуем событие в Redis для мгновенной WebSocket-доставки
    if redis_publisher is not None:
        try:
            redis_publisher.publish_notification(
                user_id=user_id,
                notification_type=notification_type,
                data={
                    'notification_id': notification_id,
                    'type': notification_type,
                    'text': full_message,
                    'title': title,
                    'data': data if data else {},
                    'is_read': False
                }
            )
        except Exception as e:
            logger.warning("Не удалось опубликовать уведомление в Redis: %s", e)

    # Ставим задачи в очередь Celery для email и push
    try:
        from app.tasks.email_tasks import send_email_notification
        from app.tasks.push_tasks import send_push_notification
    except ImportError:
        send_email_notification = None
        send_push_notification = None
        logger.warning("Celery tasks не найдены — email/push уведомления отключены")

    # Получаем email и имя пользователя из профиля (если не переданы явно)
    user_email = email
    user_name = username
    if user_email is None or user_name is None:
        try:
            profile_resp = supabase_admin_request('GET', f'profiles?id=eq.{user_id}&select=email,username')
            if profile_resp.ok and profile_resp.json():
                profile = profile_resp.json()[0]
                if user_email is None:
                    user_email = profile.get('email')
                if user_name is None:
                    user_name = profile.get('username', 'Пользователь')
        except Exception:
            logger.warning("Не удалось получить профиль для user_id=%s", user_id)

    # Проверяем настройки уведомлений пользователя
    user_prefs = prefs  # уже получены выше

    # Отправка email через Celery — отдельный try/except
    if send_email_notification and user_email and user_prefs.get('email_enabled', True):
        try:
            send_email_notification.delay(
                user_id=user_id,
                notification_id=notification_id,
                user_email=user_email,
                user_name=user_name or 'Пользователь',
                notification_text=full_message,
                notification_type=notification_type,
                notification_url=data.get('link', '') if data else ''
            )
        except Exception:
            logger.error(
                "Не удалось поставить email-задачу в очередь Celery: user=%s type=%s",
                user_id, notification_type
            )
            logger.error(traceback.format_exc())

    # Отправка push через Celery — отдельный try/except
    if send_push_notification and user_prefs.get('push_enabled', True):
        try:
            send_push_notification.delay(
                user_id=user_id,
                notification_data={
                    'title': title or 'Trudnik',
                    'body': message,
                    'url': data.get('link', '') if data else '',
                    'notification_id': notification_id,
                    'type': notification_type,
                    'tag': f'notification-{notification_id}' if notification_id else None
                }
            )
        except Exception:
            logger.error(
                "Не удалось поставить push-задачу в очередь Celery: user=%s type=%s",
                user_id, notification_type
            )
            logger.error(traceback.format_exc())

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
