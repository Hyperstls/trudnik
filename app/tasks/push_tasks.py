"""
Celery-задачи для push-уведомлений (Web Push API).

Отправка push-уведомлений пользователям и периодическая очистка
невалидных подписок.
"""

import logging

from .celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def send_push_notification(self, user_id: str, notification_data: dict, _request_id: str | None = None) -> dict:
    """Отправляет push-уведомление пользователю через Web Push API.

    Args:
        user_id: UUID пользователя-получателя.
        notification_data: данные уведомления (title, body, url, tag и т.д.).

    Returns:
        Словарь с результатами отправки:
            {'user_id': str, 'results': list[dict]}
    """
    from app.services.push_service import PushService

    push_service = PushService()

    try:
        results = push_service.send_to_user(user_id, notification_data)
        success_count = sum(1 for r in results if r.get('success'))
        fail_count = len(results) - success_count

        logger.info(
            'Push-уведомление отправлено: user=%s успешно=%d ошибок=%d',
            user_id, success_count, fail_count
        )

        return {
            'user_id': user_id,
            'results': results,
            'success_count': success_count,
            'fail_count': fail_count,
        }

    except Exception as e:
        logger.error(
            'Ошибка отправки push-уведомления: user=%s error=%s',
            user_id, str(e)
        )
        # Retry с exponential backoff
        countdown = 30 * (2 ** self.request.retries)
        raise self.retry(exc=e, countdown=countdown)


@celery_app.task
def cleanup_expired_subscriptions() -> dict:
    """Периодическая очистка устаревших push-подписок (Celery Beat).

    Проверяет все подписки: отправляет тестовый push без payload.
    Удаляет невалидные (410 Gone, 400/401).

    Returns:
        Словарь с результатами очистки:
            {'total': int, 'removed': int, 'checked': int}
    """
    from app.services.push_service import PushService

    push_service = PushService()

    removed = 0
    checked = 0
    total_processed = 0
    page_size = 100
    offset = 0

    # Пагинированный обход всех подписок — не загружаем всё в память
    while True:
        subscriptions = push_service.get_all_subscriptions(limit=page_size, offset=offset)
        if not subscriptions:
            break

        for sub in subscriptions:
            endpoint = sub.get('endpoint', '')
            if not endpoint:
                continue

            checked += 1

            # Отправляем тестовый payload с флагом healthcheck для проверки валидности подписки.
            # Service Worker должен игнорировать сообщения с типом healthcheck, не показывая уведомление.
            result = push_service.send_notification(sub, {
                'title': '',
                'body': '',
                'tag': 'healthcheck-cleanup',
                'data': {'type': 'healthcheck', 'action': 'cleanup'}
            })

            if result.get('should_unsubscribe'):
                user_id = sub.get('user_id', '')
                if user_id:
                    push_service.delete_subscription(endpoint, user_id=user_id)
                    removed += 1
                    logger.info(
                        'Удалена невалидная подписка при очистке: user=%s endpoint=%s',
                        user_id, endpoint[:60]
                    )
                else:
                    logger.warning(
                        'Не удалось удалить подписку: отсутствует user_id для endpoint=%s',
                        endpoint[:60]
                    )

        total_processed += len(subscriptions)
        if len(subscriptions) < page_size:
            break
        offset += page_size

    logger.info(
        'Очистка push-подписок завершена: проверено=%d удалено=%d из %d (обработано страниц)',
        checked, removed, total_processed
    )

    return {
        'total': total_processed,
        'removed': removed,
        'checked': checked,
    }
