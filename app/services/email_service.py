"""Сервис отправки email через SMTP для Celery-задач Trudnik.

Использует синхронный smtplib (Celery-задачи синхронные).
Поддерживает TLS/SSL, аутентификацию, дневные лимиты, рендеринг Jinja2-шаблонов.
"""

import hashlib
import hmac
import logging
import os
import smtplib
import traceback
from datetime import date, datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)


class EmailService:
    """SMTP-клиент для отправки email-уведомлений.

    Конструктор читает настройки из os.environ.
    Все методы синхронные (для использования в Celery-задачах).
    """

    def __init__(self) -> None:
        # SMTP-настройки
        self._smtp_host: str = os.environ.get("SMTP_HOST", "localhost")
        self._smtp_port: int = int(os.environ.get("SMTP_PORT", "587"))
        self._smtp_user: str = os.environ.get("SMTP_USER", "")
        self._smtp_password: str = os.environ.get("SMTP_PASSWORD", "")
        self._smtp_use_tls: bool = os.environ.get("SMTP_USE_TLS", "True").lower() in ("true", "1", "yes")
        self._smtp_use_ssl: bool = os.environ.get("SMTP_USE_SSL", "False").lower() in ("true", "1", "yes")
        self._smtp_timeout: int = int(os.environ.get("SMTP_TIMEOUT", "30"))
        self._smtp_from_email: str = os.environ.get("SMTP_FROM_EMAIL", "notifications@trudnik.ru")
        self._smtp_from_name: str = os.environ.get("SMTP_FROM_NAME", "Trudnik")
        self._daily_limit: int = int(os.environ.get("SMTP_DAILY_LIMIT", "1000"))
        self._rate_limit_pause: float = float(os.environ.get("SMTP_RATE_LIMIT_PAUSE", "1.0"))

        # Счётчик отправок за день
        self._daily_count: int = 0
        self._last_reset_date: date = date.today()

        # Jinja2-окружение для шаблонов писем (изолированное, не зависит от Flask)
        _templates_dir: str = os.path.join(os.path.dirname(__file__), "..", "templates", "email")
        _templates_dir = os.path.abspath(_templates_dir)
        self._jinja_env: Environment = Environment(
            loader=FileSystemLoader(_templates_dir),
            autoescape=True,
        )

    # ═══════════════════════════════════════════════════════════════
    # Дневной лимит
    # ═══════════════════════════════════════════════════════════════

    def _check_daily_limit(self) -> bool:
        """Проверяет, не превышен ли дневной лимит отправки.

        При наступлении нового дня сбрасывает счётчик.

        Returns:
            True, если лимит НЕ превышен (можно отправлять).
        """
        today = date.today()
        if today != self._last_reset_date:
            self._daily_count = 0
            self._last_reset_date = today
        return self._daily_count < self._daily_limit

    # ═══════════════════════════════════════════════════════════════
    # Отправка одного письма
    # ═══════════════════════════════════════════════════════════════

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str = "",
    ) -> bool:
        """Отправляет одно email-сообщение через SMTP.

        Args:
            to_email: Email получателя.
            subject: Тема письма.
            html_body: HTML-версия письма.
            text_body: Текстовая версия письма (опционально).

        Returns:
            True при успешной отправке, False при ошибке.
        """
        if not self._check_daily_limit():
            logger.warning(
                "Дневной лимит отправки (%s) исчерпан. Пропускаем письмо для %s.",
                self._daily_limit,
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
            # SSL или TLS в зависимости от конфигурации
            if self._smtp_use_ssl:
                server = smtplib.SMTP_SSL(
                    self._smtp_host, self._smtp_port, timeout=self._smtp_timeout
                )
            else:
                server = smtplib.SMTP(
                    self._smtp_host, self._smtp_port, timeout=self._smtp_timeout
                )

            # STARTTLS (если не SSL-соединение и включён TLS)
            if self._smtp_use_tls and not self._smtp_use_ssl:
                server.starttls()

            # Аутентификация (если указаны учётные данные)
            if self._smtp_user and self._smtp_password:
                server.login(self._smtp_user, self._smtp_password)

            server.send_message(msg)
            server.quit()

            self._daily_count += 1
            logger.info("Email отправлен: to=%s subject=%s", to_email, subject)
            return True

        except Exception:
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
                to_email, subject, html_body, text_body (опционально).

        Returns:
            Словарь: {'sent': int, 'failed': int, 'skipped': int, 'errors': list}.
        """
        import time as _time

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

            if not to_email or not subject or not html_body:
                result["skipped"] += 1
                result["errors"].append({
                    "to_email": to_email,
                    "error": "Отсутствуют обязательные поля (to_email, subject, html_body)",
                })
                continue

            if not self._check_daily_limit():
                result["skipped"] += 1
                result["errors"].append({
                    "to_email": to_email,
                    "error": f"Дневной лимит ({self._daily_limit}) исчерпан",
                })
                continue

            success = self.send_email(to_email, subject, html_body, text_body)
            if success:
                result["sent"] += 1
            else:
                result["failed"] += 1
                result["errors"].append({
                    "to_email": to_email,
                    "error": "Ошибка SMTP-отправки",
                })

            # Пауза между отправками
            _time.sleep(self._rate_limit_pause)

        logger.info(
            "Пакетная отправка завершена: отправлено=%d, ошибок=%d, пропущено=%d",
            result["sent"],
            result["failed"],
            result["skipped"],
        )
        return result

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
    def create_unsubscribe_token(user_id: int) -> str:
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
