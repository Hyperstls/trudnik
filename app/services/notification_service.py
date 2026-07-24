"""Сервис уведомлений: типизация, создание, проверка настроек.

БЕЗОПАСНОСТЬ (service_role):
    create() и get_user_prefs() используют postgrest_admin_request (service_role),
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
from app.utils import postgrest_admin_request, postgrest_request

logger = logging.getLogger(__name__)

# Безопасный импорт: если redis не установлен — redis_publisher будет в режиме no-op,
# все вызовы publish_notification() будут молча возвращать False.
try:
    from app.services.redis_publisher import redis_publisher
except ImportError:
    redis_publisher = None
    logger.warning("redis_publisher не загружен — WebSocket-уведомления отключены")

NOTIFICATION_TYPES = {
    'status_change':         'Изменение статуса задания',
    'application_received':  'Новый отклик на ваше задание',
    'application_accepted':  'Ваш отклик принят',
    'application_rejected':  'Ваш отклик отклонён',
    'force_complete':        'Задание завершено',
    'job_cancelled':         'Задание отменено',
    'new_message':           'Новое сообщение в чате',
}

DEFAULT_ENABLED_TYPES = {
    'status_change': True,
    'application_received': True,
    'application_accepted': True,
    'application_rejected': True,
    'force_complete': True,
    'job_cancelled': True,
    'new_message': True,
}


def get_user_prefs(user_id):
    """Получить настройки уведомлений пользователя.
    Используем admin_request — вызывается из любого контекста (не только владельцем)."""
    resp = postgrest_admin_request('GET', f'profiles?id=eq.{user_id}&select=notification_prefs')
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

    base_payload: dict = {
        'user_id': user_id,
        'type': notification_type,
        'message': f'{title}: {message}' if title else message,
        'is_read': False,
        'data': data if data else {},
    }
    # Прямая колонка job_id (миграция 063) — для быстрых JOIN и очистки orphaned
    if data and isinstance(data, dict) and data.get('job_id'):
        base_payload['job_id'] = data['job_id']
    if data and isinstance(data, dict) and data.get('application_id'):
        base_payload['application_id'] = data['application_id']

    # full_message уже вычислен в base_payload['message']
    full_message = base_payload['message']

    # Канал «в приложении» (in-app): запись в БД + мгновенная WebSocket-доставка.
    # Уважаем переключатель in_app_enabled; каналы email/push от него независимы.
    notification_id = None
    if prefs.get('in_app_enabled', True):
        # admin_request для обхода RLS: уведомления создаёт система, user_id может
        # не совпадать с auth.uid()
        headers = {'Prefer': 'return=representation'}
        resp = postgrest_admin_request('POST', 'notifications', json=base_payload, headers=headers)
        if not resp.ok:
            logger.error('Failed to create notification: user=%s type=%s status=%s body=%s',
                         user_id, notification_type, resp.status_code, resp.text)
            return False

        # Получаем ID созданного уведомления из ответа
        try:
            resp_data = resp.json()
            if isinstance(resp_data, list) and len(resp_data) > 0:
                notification_id = resp_data[0].get('id')
        except Exception as e:
            logger.warning('Failed to extract notification_id from response: %s', e, exc_info=True)

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
    # Используем notification_dispatcher для разрыва циклической зависимости
    from app.services.notification_dispatcher import (
        dispatch_email_notification,
        dispatch_push_notification
    )

    # Получаем email и имя пользователя из профиля (если не переданы явно)
    user_email = email
    user_name = username
    if user_email is None or user_name is None:
        try:
            profile_resp = postgrest_admin_request('GET', f'profiles?id=eq.{user_id}&select=email,username')
            if profile_resp.ok and profile_resp.json():
                profile = profile_resp.json()[0]
                if user_email is None:
                    user_email = profile.get('email')
                if user_name is None:
                    user_name = profile.get('username', 'Пользователь')
        except Exception as e:
            logger.warning("Не удалось получить профиль для user_id=%s: %s", user_id, e, exc_info=True)

    # Проверяем настройки уведомлений пользователя
    user_prefs = prefs  # уже получены выше

    # Отправка email через Celery — диспетчер (notification_dispatcher)
    if user_email and user_prefs.get('email_enabled', True):
        dispatch_email_notification(
            user_id=user_id,
            notification_id=notification_id,
            user_email=user_email,
            user_name=user_name or 'Пользователь',
            notification_text=full_message,
            notification_type=notification_type,
            notification_url=data.get('link', '') if data else ''
        )

    # Отправка push через Celery — диспетчер (notification_dispatcher)
    if user_prefs.get('push_enabled', True):
        dispatch_push_notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_data=data if data else {},
            notification_id=notification_id,
            notification_type=notification_type
        )

    # Инвалидируем Redis-кэш счётчика непрочитанных уведомлений
    from app.utils.redis_cache import redis_cache_delete
    try:
        redis_cache_delete(f'unread:{user_id}')
    except Exception as e:
        logger.warning('Failed to invalidate unread cache for user=%s: %s', user_id, e, exc_info=True)

    return True


def enqueue_notification(user_id, notification_type, title, message, data=None) -> bool:
    """Записать уведомление в transactional outbox (таблица notification_outbox).

    Это гарантирует at-least-once доставку: Celery-воркер периодически
    обрабатывает outbox и отправляет накопленные уведомления.

    В отличие от create(), этот метод только пишет в outbox, не выполняет
    проверку настроек, не отправляет email/push и не публикует в Redis.

    Args:
        user_id: UUID получателя
        notification_type: ключ из NOTIFICATION_TYPES
        title: заголовок
        message: текст
        data: dict с доп. данными (job_id, application_id, link)

    Returns:
        bool: True если запись создана, False при ошибке
    """
    if notification_type not in NOTIFICATION_TYPES:
        logger.warning('enqueue_notification: unknown notification type: %s', notification_type)
        return False

    payload: dict = {
        'user_id': user_id,
        'type': notification_type,
        'title': title,
        'body': message,
        'data': data if data else {},
        'status': 'pending',
    }
    if data and isinstance(data, dict) and data.get('job_id'):
        payload['job_id'] = data['job_id']
    if data and isinstance(data, dict) and data.get('application_id'):
        payload['application_id'] = data['application_id']

    try:
        resp = postgrest_admin_request('POST', 'notification_outbox', json=payload)
        if not resp.ok:
            logger.error('enqueue_notification: failed to write to outbox: user=%s type=%s status=%s body=%s',
                         user_id, notification_type, resp.status_code, resp.text)
            return False
        logger.debug('enqueue_notification: outbox entry created for user=%s type=%s', user_id, notification_type)
        return True
    except Exception as e:
        logger.error('enqueue_notification: exception for user=%s type=%s: %s', user_id, notification_type, e)
        return False


def get_notifications(user_id, page=1, per_page=20):
    """Получить уведомления пользователя с пагинацией (JSON-ready)."""
    offset = (page - 1) * per_page
    headers = {'Prefer': 'count=exact'}
    resp = postgrest_request('GET',
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
    """Точный счётчик непрочитанных уведомлений (через count=exact)."""
    resp = postgrest_request('GET',
        f'notifications?user_id=eq.{user_id}&is_read=eq.false&select=id&limit=0',
        headers={'Prefer': 'count=exact'})
    if resp.ok:
        content_range = resp.headers.get('Content-Range', '')
        if '/' in content_range:
            return int(content_range.split('/')[-1])
    return 0


def mark_all_read(user_id):
    """Пометить все уведомления пользователя прочитанными."""
    postgrest_request('PATCH',
        f'notifications?user_id=eq.{user_id}&is_read=eq.false',
        json={'is_read': True})


def mark_read(notification_id, user_id):
    """Пометить одно уведомление прочитанным (с проверкой принадлежности).

    Args:
        notification_id: ID уведомления.
        user_id: UUID пользователя (обязательно). PATCH только если уведомление
                 принадлежит этому пользователю.
    """
    if not user_id:
        logger.error('mark_read: user_id is required')
        return
    
    url = f'notifications?id=eq.{notification_id}&user_id=eq.{user_id}'
    postgrest_request('PATCH', url, json={'is_read': True})

    # Инвалидируем Redis-кэш счётчика непрочитанных уведомлений
    from app.utils.redis_cache import redis_cache_delete
    try:
        redis_cache_delete(f'unread:{user_id}')
    except Exception as e:
        logger.warning('Failed to clear unread cache: %s', e, exc_info=True)
