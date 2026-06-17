"""
Celery-задачи для email-рассылки уведомлений Trudnik.

Отправка email-уведомлений через SMTP с рендерингом Jinja2-шаблонов,
логированием в таблицу email_log и механизмом повторных попыток (exponential backoff).
"""

import logging
from datetime import datetime, timezone
from typing import Any

from celery import Task
from celery.exceptions import MaxRetriesExceededError

from .celery_app import celery_app
from app.services.email_service import EmailService
from app.utils import supabase_admin_request

logger = logging.getLogger(__name__)


def _log_to_db(
    user_id: int,
    notification_id: int,
    to_email: str,
    subject: str,
    status: str,
    error_message: str = "",
    template_name: str = "",
) -> bool:
    """Записывает результат отправки email в таблицу email_log через Supabase REST API.

    Args:
        user_id: ID пользователя-получателя.
        notification_id: ID уведомления в БД.
        to_email: Email получателя.
        subject: Тема письма.
        status: Статус отправки ('sent', 'failed', 'dead', 'skipped').
        error_message: Текст ошибки (если была).
        template_name: Имя использованного шаблона.

    Returns:
        True при успешной записи в БД, False при ошибке.
    """
    payload: dict[str, Any] = {
        "user_id": user_id,
        "notification_id": notification_id,
        "to_email": to_email,
        "subject": subject,
        "status": status,
        "template_name": template_name,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }

    if error_message:
        payload["error_message"] = error_message[:1000]  # Ограничиваем длину

    try:
        resp = supabase_admin_request("POST", "email_log", json=payload)
        if resp.ok:
            logger.debug(
                "email_log записан: user=%s notification=%s status=%s",
                user_id,
                notification_id,
                status,
            )
            return True
        else:
            logger.error(
                "Ошибка записи в email_log: status=%s body=%s",
                resp.status_code,
                resp.text[:500] if resp.text else "",
            )
            return False
    except Exception:
        logger.exception("Исключение при записи в email_log")
        return False


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_notification(
    self: Task,
    user_id: int,
    notification_id: int,
    user_email: str,
    user_name: str,
    notification_text: str,
    notification_type: str,
    notification_url: str = "",
) -> dict[str, Any]:
    """Отправляет email-уведомление пользователю.

    Args:
        user_id: ID пользователя-получателя.
        notification_id: ID уведомления в БД.
        user_email: Email получателя.
        user_name: Имя получателя (для персонализации).
        notification_text: Текст уведомления.
        notification_type: Тип уведомления (ключ из NOTIFICATION_TYPES).
        notification_url: Ссылка для кнопки «Перейти к уведомлению».

    Returns:
        Словарь с результатом отправки: {'status': str, 'error': str}.

    Raises:
        self.retry: При ошибке отправки для повторной попытки.
    """
    import os

    email_service = EmailService()
    base_url: str = os.environ.get("BASE_URL", "https://trudnik.ru")

    # Выбираем шаблон в зависимости от типа уведомления
    if notification_type == "new_message":
        template_name = "chat_message"
        subject = "Новое сообщение в чате — Trudnik"
    else:
        template_name = "notification"
        subject = f"Уведомление — Trudnik"

    # Формируем контекст для шаблона
    from datetime import date

    context: dict[str, Any] = {
        "user_name": user_name,
        "notification_text": notification_text,
        "notification_type": notification_type,
        "notification_url": notification_url,
        "base_url": base_url,
        "unsubscribe_url": f"{base_url}/unsubscribe?token={EmailService.create_unsubscribe_token(user_id)}",
        "year": date.today().year,
    }

    # Для шаблона chat_message добавляем дополнительные поля
    if notification_type == "new_message":
        context["sender_name"] = notification_text.split(":")[0] if ":" in notification_text else "Пользователь"
        context["message_preview"] = notification_text.split(":", 1)[-1].strip() if ":" in notification_text else notification_text
        context["chat_url"] = notification_url

    # Рендерим шаблоны
    try:
        html_body, text_body = email_service.render_template(template_name, context)
    except Exception as render_err:
        logger.exception("Ошибка рендеринга шаблона %s", template_name)
        # fallback — простой текст
        html_body = (
            f"<html><body>"
            f"<h2>Здравствуйте, {user_name}!</h2>"
            f"<p>{notification_text}</p>"
            f"<p><a href=\"{notification_url}\">Перейти</a></p>"
            f"</body></html>"
        )
        text_body = (
            f"Здравствуйте, {user_name}!\n\n"
            f"{notification_text}\n\n"
            f"Ссылка: {notification_url}"
        )

    # Отправляем email
    try:
        success = email_service.send_email(
            to_email=user_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )
    except Exception as send_err:
        logger.exception(
            "Ошибка отправки email: user=%s notification=%s attempt=%s",
            user_id,
            notification_id,
            self.request.retries + 1,
        )

        # Exponential backoff: 60s * 2^retry
        retry_delay = 60 * (2 ** self.request.retries)

        try:
            raise self.retry(exc=send_err, countdown=retry_delay)
        except MaxRetriesExceededError:
            # Все попытки исчерпаны — записываем dead-letter
            logger.error(
                "Dead-letter: email для user=%s notification=%s после %d попыток",
                user_id,
                notification_id,
                self.max_retries,
            )
            _log_to_db(
                user_id=user_id,
                notification_id=notification_id,
                to_email=user_email,
                subject=subject,
                status="dead",
                error_message=str(send_err),
                template_name=template_name,
            )
            return {"status": "dead", "error": str(send_err)}

    # Логируем результат
    if success:
        _log_to_db(
            user_id=user_id,
            notification_id=notification_id,
            to_email=user_email,
            subject=subject,
            status="sent",
            template_name=template_name,
        )
        logger.info(
            "Email-уведомление отправлено: user=%s notification=%s type=%s",
            user_id,
            notification_id,
            notification_type,
        )
        return {"status": "sent", "error": ""}
    else:
        # SMTP-ошибка, но не исключение — пробуем повторить
        retry_delay = 60 * (2 ** self.request.retries)
        try:
            raise self.retry(countdown=retry_delay)
        except MaxRetriesExceededError:
            _log_to_db(
                user_id=user_id,
                notification_id=notification_id,
                to_email=user_email,
                subject=subject,
                status="dead",
                error_message="SMTP-отправка не удалась после всех попыток",
                template_name=template_name,
            )
            return {"status": "dead", "error": "SMTP-отправка не удалась"}


@celery_app.task(bind=True, max_retries=1, default_retry_delay=300)
def send_batch_email_notifications(
    self: Task,
    recipients: list[dict[str, Any]],
) -> dict[str, Any]:
    """Диспатчит email-уведомления списку получателей в очередь Celery (пакетная задача).

    Важно: результат отражает факт постановки задач в очередь, а не финальную отправку.
    Реальный статус отправки каждого email будет известен только после выполнения
    отдельных задач send_email_notification.

    Args:
        recipients: Список словарей с ключами:
            user_id, notification_id, user_email, user_name,
            notification_text, notification_type, notification_url.

    Returns:
        Словарь с агрегированным результатом диспатча:
        {'dispatched': int, 'failed_to_dispatch': int, 'dead': int}.
    """
    results: dict[str, int] = {"dispatched": 0, "failed_to_dispatch": 0, "dead": 0}

    for recipient in recipients:
        try:
            result = send_email_notification.delay(
                user_id=recipient.get("user_id", 0),
                notification_id=recipient.get("notification_id", 0),
                user_email=recipient.get("user_email", ""),
                user_name=recipient.get("user_name", ""),
                notification_text=recipient.get("notification_text", ""),
                notification_type=recipient.get("notification_type", ""),
                notification_url=recipient.get("notification_url", ""),
            )
            # Асинхронный вызов — задачу поставили в очередь
            results["dispatched"] += 1
        except Exception as exc:
            logger.exception(
                "Ошибка постановки задачи send_email_notification для user=%s",
                recipient.get("user_id"),
            )
            results["failed_to_dispatch"] += 1

    logger.info(
        "Пакетный диспатч email-задач: %d поставлено в очередь, %d ошибок диспатча",
        results["dispatched"],
        results["failed_to_dispatch"],
    )
    return results


@celery_app.task
def cleanup_old_email_logs():
    """Очищает старые записи email_log (старше 30 дней) и dead-letter (старше 7 дней)."""
    from datetime import datetime, timedelta, timezone

    deleted_sent = 0
    deleted_dead = 0

    try:
        # Удаляем успешные записи старше 30 дней
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        resp_sent = supabase_admin_request(
            'DELETE',
            f'email_log?status=eq.sent&created_at=lt.{thirty_days_ago}',
            headers={'Prefer': 'count=exact'}
        )
        if resp_sent.ok:
            content_range = resp_sent.headers.get('Content-Range', '')
            if '/' in content_range:
                deleted_sent = int(content_range.split('/')[-1])
            logger.info("Удалено %d успешных записей email_log старше 30 дней", deleted_sent)
        else:
            logger.error("Ошибка удаления старых sent-записей email_log: status=%s body=%s",
                         resp_sent.status_code, (resp_sent.text or '')[:500])

        # Удаляем dead-letter записи старше 7 дней
        seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        resp_dead = supabase_admin_request(
            'DELETE',
            f'email_log?status=eq.dead&created_at=lt.{seven_days_ago}',
            headers={'Prefer': 'count=exact'}
        )
        if resp_dead.ok:
            content_range = resp_dead.headers.get('Content-Range', '')
            if '/' in content_range:
                deleted_dead = int(content_range.split('/')[-1])
            logger.info("Удалено %d dead-letter записей email_log старше 7 дней", deleted_dead)
        else:
            logger.error("Ошибка удаления старых dead-записей email_log: status=%s body=%s",
                         resp_dead.status_code, (resp_dead.text or '')[:500])

    except Exception as e:
        logger.error("Ошибка очистки email_log: %s", e)
        raise

    return {
        'deleted_sent': deleted_sent,
        'deleted_dead': deleted_dead
    }
