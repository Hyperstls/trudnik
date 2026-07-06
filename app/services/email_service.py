"""Сервис отправки email через SMTP для Celery-задач Trudnik.

Использует синхронный smtplib (Celery-задачи синхронные).
Поддерживает TLS/SSL, аутентификацию, дневные лимиты (Redis), рендеринг Jinja2-шаблонов.
"""

import hashlib
import hmac
import logging
import os
import smtplib
import threading
import time as _time_module
import traceback
from datetime import date, datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)
 
 
class EmailService:
    """SMTP-клиент для отправки email-уведомлений.

    Конструктор читает настройки из os.environ.
    Все методы синхронные (для использования в Celery-задачах).
    Использует Redis для дневных лимитов и connection pooling для SMTP.
    """

    def __init__(self,
                 smtp_host: Optional[str] = None,
                 smtp_port: Optional[int] = None,
                 smtp_user: Optional[str] = None,
                 smtp_password: Optional[str] = None,
                 smtp_use_tls: Optional[bool] = None,
                 smtp_use_ssl: Optional[bool] = None,
                 smtp_timeout: Optional[int] = None,
                 smtp_from_email: Optional[str] = None,
                 smtp_from_name: Optional[str] = None,
                 daily_limit: Optional[int] = None,
                 rate_limit_pause: Optional[float] = None,
                 redis_url: Optional[str] = None) -> None:
        # SMTP-настройки (значения по умолчанию из os.environ, можно переопределить через параметры)
        self._smtp_host: str = smtp_host if smtp_host is not None else os.environ.get("SMTP_HOST", "localhost")
        self._smtp_port: int = smtp_port if smtp_port is not None else int(os.environ.get("SMTP_PORT", "587"))
        self._smtp_user: str = smtp_user if smtp_user is not None else os.environ.get("SMTP_USER", "")
        self._smtp_password: str = smtp_password if smtp_password is not None else os.environ.get("SMTP_PASSWORD", "")
        self._smtp_use_tls: bool = smtp_use_tls if smtp_use_tls is not None else os.environ.get("SMTP_USE_TLS", "True").lower() in ("true", "1", "yes")
        self._smtp_use_ssl: bool = smtp_use_ssl if smtp_use_ssl is not None else os.environ.get("SMTP_USE_SSL", "False").lower() in ("true", "1", "yes")
        self._smtp_timeout: int = smtp_timeout if smtp_timeout is not None else int(os.environ.get("SMTP_TIMEOUT", "30"))
        self._smtp_from_email: str = smtp_from_email if smtp_from_email is not None else os.environ.get("SMTP_FROM_EMAIL", "notifications@trudnik.ru")
        self._smtp_from_name: str = smtp_from_name if smtp_from_name is not None else os.environ.get("SMTP_FROM_NAME", "Trudnik")
        self._daily_limit: int = daily_limit if daily_limit is not None else int(os.environ.get("SMTP_DAILY_LIMIT", "1000"))
        self._rate_limit_pause: float = rate_limit_pause if rate_limit_pause is not None else float(os.environ.get("SMTP_RATE_LIMIT_PAUSE", "1.0"))

        # Redis-клиент для дневного лимита (общий для всех worker'ов)
        self._redis = None
        try:
            from app.utils.redis_client import get_redis_client
            self._redis = get_redis_client()
            if self._redis is None:
                logger.warning("Redis недоступен — дневной лимит email не будет соблюдаться между worker'ами")
        except Exception:
            logger.warning("Redis недоступен — дневной лимит email не будет соблюдаться между worker'ами")

        # SMTP connection pooling: ленивое соединение
        self._smtp_connection: Optional[smtplib.SMTP] = None
        self._smtp_conn_last_use: float = 0.0

        # Jinja2-окружение для шаблонов писем (изолированное, не зависит от Flask)
        _templates_dir: str = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "email")
        _templates_dir = os.path.abspath(_templates_dir)
        self._jinja_env: Environment = Environment(
            loader=FileSystemLoader(_templates_dir),
            autoescape=True,
        )

    # ═══════════════════════════════════════════════════════════════
    # Дневной лимит (Redis — общий для всех worker'ов)
    # ═══════════════════════════════════════════════════════════════

    def _check_daily_limit(self, user_id: str = "") -> bool:
        """Проверяет, не превышен ли дневной лимит отправки (через Redis).

        Ключ: email:daily:{date}:{user_id}
        При отсутствии Redis — всегда разрешает отправку (graceful degradation).

        Args:
            user_id: ID пользователя (0 = глобальный лимит).

        Returns:
            True, если лимит НЕ превышен (можно отправлять).
        """
        if self._redis is None:
            return True

        today = date.today().isoformat()
        key = f"email:daily:{today}:{user_id}"

        try:
            current = self._redis.incr(key)
            if current == 1:
                # Вычисляем секунды до полуночи для EXPIRE
                now = datetime.now(timezone.utc)
                tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                ttl_seconds = int((tomorrow - now).total_seconds()) + 1
                self._redis.expire(key, ttl_seconds)
            return current <= self._daily_limit
        except Exception:
            logger.warning("Ошибка Redis при проверке дневного лимита — разрешаем отправку")
            return True

    def _get_smtp_connection(self) -> smtplib.SMTP:
        """Возвращает переиспользуемое SMTP-соединение (connection pooling).

        Переподключается, если соединение отсутствует или старше 60 секунд.

        Returns:
            Активное SMTP-соединение.
        """
        now = _time_module.time()
        if self._smtp_connection is not None:
            # Проверяем, не устарело ли соединение (60 секунд)
            if now - self._smtp_conn_last_use < 60:
                try:
                    # Проверяем живо ли соединение
                    self._smtp_connection.noop()
                    self._smtp_conn_last_use = now
                    return self._smtp_connection
                except Exception:
                    # Соединение мертво — закроем и пересоздадим
                    try:
                        self._smtp_connection.close()
                    except Exception:
                        pass
                    self._smtp_connection = None

        # Создаём новое соединение
        if self._smtp_use_ssl:
            server = smtplib.SMTP_SSL(
                self._smtp_host, self._smtp_port, timeout=self._smtp_timeout
            )
        else:
            server = smtplib.SMTP(
                self._smtp_host, self._smtp_port, timeout=self._smtp_timeout
            )

        if self._smtp_use_tls and not self._smtp_use_ssl:
            server.starttls()

        if self._smtp_user and self._smtp_password:
            server.login(self._smtp_user, self._smtp_password)

        self._smtp_connection = server
        self._smtp_conn_last_use = now
        return server

    # ═══════════════════════════════════════════════════════════════
    # Отправка одного письма
    # ═══════════════════════════════════════════════════════════════

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str = "",
        user_id: str = "",
    ) -> bool:
        """Отправляет одно email-сообщение через SMTP (с connection pooling).

        Args:
            to_email: Email получателя.
            subject: Тема письма.
            html_body: HTML-версия письма.
            text_body: Текстовая версия письма (опционально).
            user_id: ID пользователя для дневного лимита (0 = глобальный).

        Returns:
            True при успешной отправке, False при ошибке.
        """
        if not self._check_daily_limit(user_id):
            logger.warning(
                "Дневной лимит отправки (%s) исчерпан для user=%s. Пропускаем письмо для %s.",
                self._daily_limit,
                user_id,
                to_email,
            )
            return False

        # Формируем MIME-сообщение
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self._smtp_from_name} <{self._smtp_from_email}>"
        msg["To"] = to_email

        # Текстовая версия (если не передана — используем заглушку)
        if text_body:
            msg.attach(MIMEText(text_body, "plain", "utf-8"))
        else:
            msg.attach(MIMEText(
                "Пожалуйста, откройте письмо в почтовом клиенте, поддерживающем HTML.",
                "plain", "utf-8",
            ))

        # HTML-версия
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            server = self._get_smtp_connection()
            server.send_message(msg)
            # Не закрываем соединение — переиспользуем (connection pooling)
            logger.info("Email отправлен: to=%s subject=%s", to_email, subject)
            return True

        except Exception:
            # При ошибке сбрасываем соединение, чтобы переподключиться в следующий раз
            if self._smtp_connection is not None:
                try:
                    self._smtp_connection.close()
                except Exception:
                    pass
                self._smtp_connection = None
            logger.error(
                "Ошибка отправки email для %s:\n%s",
                to_email,
                traceback.format_exc(),
            )
            return False

    # ═══════════════════════════════════════════════════════════════
    # Пакетная отправка
    # ═══════════════════════════════════════════════════════════════

    def send_batch(self, recipients: list[dict[str, str]]) -> dict[str, Any]:
        """Отправляет письма списку получателей последовательно.

        Args:
            recipients: Список словарей с ключами:
                to_email, subject, html_body, text_body (опционально),
                user_id (опционально).

        Returns:
            Словарь: {'sent': int, 'failed': int, 'skipped': int, 'errors': list}.
        """

        result: dict[str, Any] = {
            "sent": 0,
            "failed": 0,
            "skipped": 0,
            "errors": [],
        }

        for recipient in recipients:
            to_email = recipient.get("to_email", "")
            subject = recipient.get("subject", "")
            html_body = recipient.get("html_body", "")
            text_body = recipient.get("text_body", "")
            user_id = recipient.get("user_id", "")

            if not to_email or not subject or not html_body:
                result["skipped"] += 1
                result["errors"].append({
                    "to_email": to_email,
                    "error": "Отсутствуют обязательные поля (to_email, subject, html_body)",
                })
                continue

            if not self._check_daily_limit(user_id):
                result["skipped"] += 1
                result["errors"].append({
                    "to_email": to_email,
                    "error": f"Дневной лимит ({self._daily_limit}) исчерпан",
                })
                continue

            success = self.send_email(to_email, subject, html_body, text_body, user_id=user_id)
            if success:
                result["sent"] += 1
            else:
                result["failed"] += 1
                result["errors"].append({
                    "to_email": to_email,
                    "error": "Ошибка SMTP-отправки",
                })

            # Пауза между отправками
            _time_module.sleep(self._rate_limit_pause)

        logger.info(
            "Пакетная отправка завершена: отправлено=%d, ошибок=%d, пропущено=%d",
            result["sent"],
            result["failed"],
            result["skipped"],
        )
        return result

    def send_batch_async(self, recipients: list[dict[str, Any]]) -> dict[str, Any]:
        """Отправляет письма списку получателей параллельно через celery.group.

        В отличие от send_batch() (синхронный цикл с sleep), этот метод
        ставит все задачи в очередь Celery параллельно и возвращает
        результат диспатча немедленно.

        Args:
            recipients: Список словарей с ключами:
                to_email, subject, html_body, text_body (опционально),
                user_id (опционально).

        Returns:
            Словарь: {'dispatched': int, 'failed_to_dispatch': int, 'total': int}.
        """
        from celery import group

        total = len(recipients)
        if total == 0:
            return {"dispatched": 0, "failed_to_dispatch": 0, "total": 0}

        # Импортируем задачу отложенно (избегаем циклических импортов)
        try:
            from app.tasks.email_tasks import send_email_notification
        except ImportError:
            logger.warning("Celery-задача send_email_notification не найдена — fallback на синхронный send_batch")
            return self.send_batch(recipients)

        # Формируем список сигнатур задач для параллельной отправки
        task_sigs = [
            send_email_notification.s(
                user_id=str(r.get("user_id", "")),
                notification_id=int(r.get("notification_id", 0)),
                user_email=r.get("to_email", ""),
                user_name=r.get("user_name", ""),
                notification_text=r.get("html_body", ""),
                notification_type="batch",
                notification_url=r.get("notification_url", ""),
            )
            for r in recipients
        ]

        try:
            job = group(task_sigs).apply_async()
            logger.info(
                "Пакетный диспатч email через celery.group: %d задач поставлено (group_id=%s)",
                total, job.id,
            )
            return {"dispatched": total, "failed_to_dispatch": 0, "total": total}
        except Exception as exc:
            logger.exception(
                "Ошибка постановки celery.group для пакетной email-рассылки: %s. Fallback на send_batch.",
                exc,
            )
            # Fallback на синхронный метод при ошибке Celery
            return self.send_batch(recipients)

    def close(self):
        """Закрывает SMTP-соединение и Redis-клиент."""
        if self._smtp_connection is not None:
            try:
                self._smtp_connection.quit()
            except Exception:
                pass
            self._smtp_connection = None
        if self._redis is not None:
            try:
                self._redis.close()
            except Exception:
                pass
            self._redis = None

    # ═══════════════════════════════════════════════════════════════
    # Рендеринг шаблонов
    # ═══════════════════════════════════════════════════════════════

    def render_template(
        self, template_name: str, context: dict[str, Any]
    ) -> tuple[str, str]:
        """Рендерит HTML и текстовую версию письма из Jinja2-шаблонов.

        Ищет шаблоны: <template_name>.html и <template_name>.txt
        в директории templates/email/.

        Args:
            template_name: Имя шаблона (без расширения).
            context: Словарь переменных для шаблона.

        Returns:
            Кортеж (html_body, text_body).
        """
        html_body: str = ""
        text_body: str = ""

        try:
            html_template = self._jinja_env.get_template(f"{template_name}.html")
            html_body = html_template.render(context)
        except Exception:
            logger.error(
                "Ошибка рендеринга HTML-шаблона '%s.html':\n%s",
                template_name,
                traceback.format_exc(),
            )
            html_body = f"<p>Уведомление от Trudnik</p><p>{context.get('notification_text', '')}</p>"

        try:
            text_template = self._jinja_env.get_template(f"{template_name}.txt")
            text_body = text_template.render(context)
        except Exception:
            logger.error(
                "Ошибка рендеринга текстового шаблона '%s.txt':\n%s",
                template_name,
                traceback.format_exc(),
            )
            text_body = (
                f"Уведомление от Trudnik\n\n"
                f"{context.get('notification_text', '')}"
            )

        return html_body, text_body

    # ═══════════════════════════════════════════════════════════════
    # Токен отписки
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def create_unsubscribe_token(user_id: str) -> str:
        """Создаёт HMAC-SHA256 токен для ссылки отписки от рассылки.

        Args:
            user_id: ID пользователя.

        Returns:
            Строка с HMAC-токеном в hex-формате.
        """
        secret: str = os.environ.get("SECRET_KEY", "fallback-secret-key")
        message: str = f"unsubscribe:{user_id}"
        token: str = hmac.new(
            secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return token


# ═══════════════════════════════════════════════════════════════
# Lazy singleton: один экземпляр EmailService на процесс
# ═══════════════════════════════════════════════════════════════

_email_service_instance: Optional[EmailService] = None
_email_service_lock = threading.Lock()


def get_email_service() -> EmailService:
    """Вернуть глобальный экземпляр EmailService (lazy singleton).

    SMTP-соединение переиспользуется между вызовами (connection pooling).
    Потокобезопасно.
    """
    global _email_service_instance
    if _email_service_instance is None:
        with _email_service_lock:
            if _email_service_instance is None:
                _email_service_instance = EmailService()
    return _email_service_instance


def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str = "",
    user_id: str = "",
) -> bool:
    """Отправить email через глобальный синглтон EmailService."""
    return get_email_service().send_email(to_email, subject, html_body, text_body, user_id)


def get_smtp_connection() -> smtplib.SMTP:
    """Вернуть переиспользуемое SMTP-соединение из синглтона."""
    return get_email_service()._get_smtp_connection()


def render_template(template_name: str, context: dict[str, Any]) -> tuple[str, str]:
    """Рендерить шаблон через глобальный синглтон EmailService."""
    return get_email_service().render_template(template_name, context)


def create_unsubscribe_token(user_id: str) -> str:
    """Создать токен отписки (делегирует статическому методу)."""
    return EmailService.create_unsubscribe_token(user_id)
