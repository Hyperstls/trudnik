"""Transactional outbox: постановка уведомлений (JOB-P1-07).

Django работает ролью с BYPASSRLS и пишет outbox напрямую; доставку
(web/email/push) выполняет drain_notification_outbox. Ошибка постановки
не должна ломать пользовательское действие — логируем и возвращаем False.
"""
import logging

from django.db import transaction

from .models import NotificationOutbox

logger = logging.getLogger(__name__)


def enqueue_notification(user_id, type: str, title: str, body: str = "", data: dict | None = None) -> bool:
    if not user_id:
        logger.warning("enqueue_notification skipped: empty user_id type=%s", type)
        return False
    try:
        # Savepoint: сбой вставки не должен отравлять внешнюю транзакцию.
        with transaction.atomic():
            NotificationOutbox.objects.create(
                user_id=user_id,
                type=type[:50],
                title=title[:255],
                body=body,
                data=data or {},
                status=NotificationOutbox.Status.PENDING,
            )
        return True
    except Exception:
        logger.exception("enqueue_notification failed user=%s type=%s", user_id, type)
        return False
