"""Диспетчер уведомлений: очередь email/push через Celery.

Вынесен в отдельный модуль для разрыва циклической зависимости:
notification_service -> tasks -> notification_service.
"""

import logging
import traceback

logger = logging.getLogger(__name__)


def dispatch_email_notification(user_id, notification_id, user_email, user_name,
                                 notification_text, notification_type, notification_url):
    """Поставить email-уведомление в очередь Celery.

    Args:
        user_id: UUID получателя.
        notification_id: ID уведомления.
        user_email: email получателя.
        user_name: имя получателя.
        notification_text: текст уведомления.
        notification_type: тип уведомления.
        notification_url: ссылка из data.link.

    Returns:
        True если задача успешно поставлена в очередь, иначе False.
    """
    try:
        from app.tasks.email_tasks import send_email_notification
    except ImportError:
        logger.warning("Celery email tasks не найдены — email уведомления отключены")
        return False

    if not user_email:
        return False

    try:
        send_email_notification.delay(
            user_id=user_id,
            notification_id=notification_id,
            user_email=user_email,
            user_name=user_name or 'Пользователь',
            notification_text=notification_text,
            notification_type=notification_type,
            notification_url=notification_url
        )
        return True
    except Exception:
        logger.error(
            "Не удалось поставить email-задачу в очередь Celery: user=%s type=%s",
            user_id, notification_type
        )
        logger.error(traceback.format_exc())
        return False


def dispatch_push_notification(user_id, title, message, notification_data,
                                notification_id=None, notification_type=None):
    """Поставить push-уведомление в очередь Celery.

    Args:
        user_id: UUID получателя.
        title: заголовок.
        message: текст.
        notification_data: dict с доп. данными (link и т.д.).
        notification_id: ID уведомления.
        notification_type: тип уведомления.

    Returns:
        True если задача успешно поставлена в очередь, иначе False.
    """
    try:
        from app.tasks.push_tasks import send_push_notification
    except ImportError:
        logger.warning("Celery push tasks не найдены — push уведомления отключены")
        return False

    payload = {
        'title': title or 'Trudnik',
        'body': message,
        'url': notification_data.get('link', '') if notification_data else '',
        'notification_id': notification_id,
        'type': notification_type,
        'tag': f'notification-{notification_id}' if notification_id else None
    }

    try:
        send_push_notification.delay(
            user_id=user_id,
            notification_data=payload
        )
        return True
    except Exception:
        logger.error(
            "Не удалось поставить push-задачу в очередь Celery: user=%s type=%s",
            user_id, notification_type
        )
        logger.error(traceback.format_exc())
        return False
