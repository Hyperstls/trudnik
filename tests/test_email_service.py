"""Тесты для EmailService — отправка email через SMTP, рендеринг шаблонов, лимиты."""

import os
import unittest
from unittest.mock import MagicMock, patch

from app.services.email_service import EmailService


class TestEmailService(unittest.TestCase):
    """Unit-тесты сервиса отправки email."""

    def setUp(self) -> None:
        """Установка тестовых переменных окружения перед каждым тестом."""
        os.environ['SMTP_HOST'] = 'test-smtp.example.com'
        os.environ['SMTP_PORT'] = '587'
        os.environ['SMTP_USER'] = 'test@example.com'
        os.environ['SMTP_PASSWORD'] = 'test-password'
        os.environ['SMTP_FROM_EMAIL'] = 'notifications@trudnik.ru'
        os.environ['SMTP_FROM_NAME'] = 'Trudnik Test'
        os.environ['SMTP_DAILY_LIMIT'] = '10'
        os.environ['SMTP_RATE_LIMIT_PAUSE'] = '0.01'
        os.environ['SMTP_USE_TLS'] = 'True'
        os.environ['SMTP_USE_SSL'] = 'False'
        os.environ['SECRET_KEY'] = 'test-secret-key-for-testing'
        self.service = EmailService()

    # ────────────────────────────────────────────────────────────
    # Отправка одного письма
    # ────────────────────────────────────────────────────────────

    @patch('smtplib.SMTP')
    def test_send_email_success(self, mock_smtp: MagicMock) -> None:
        """Успешная отправка email — SMTP-соединение, аутентификация, отправка."""
        mock_server = MagicMock()
        # Код не использует context manager (with), поэтому mock на return_value
        mock_smtp.return_value = mock_server

        result = self.service.send_email(
            to_email='user@example.com',
            subject='Тестовое письмо',
            html_body='<p>Привет, мир!</p>',
            text_body='Привет, мир!',
        )

        self.assertTrue(result)
        mock_server.send_message.assert_called_once()
        # Проверяем, что login был вызван (учётные данные заданы)
        mock_server.login.assert_called_once_with('test@example.com', 'test-password')

    @patch('smtplib.SMTP')
    def test_send_email_auth_failure(self, mock_smtp: MagicMock) -> None:
        """Ошибка аутентификации — send_email возвращает False."""
        mock_server = MagicMock()
        mock_server.login.side_effect = Exception("Authentication failed")
        mock_smtp.return_value = mock_server

        result = self.service.send_email(
            to_email='user@example.com',
            subject='Тест',
            html_body='<p>Тест</p>',
            text_body='Тест',
        )

        self.assertFalse(result)

    @patch('smtplib.SMTP')
    def test_send_email_connection_error(self, mock_smtp: MagicMock) -> None:
        """Ошибка подключения к SMTP-серверу — возвращает False, не падает."""
        mock_smtp.side_effect = ConnectionRefusedError("Connection refused")

        result = self.service.send_email(
            to_email='user@example.com',
            subject='Тест',
            html_body='<p>Тест</p>',
            text_body='Тест',
        )

        self.assertFalse(result)

    @patch('smtplib.SMTP_SSL')
    def test_send_email_via_ssl(self, mock_smtp_ssl: MagicMock) -> None:
        """Отправка через SSL (SMTP_SSL) при SMTP_USE_SSL=True."""
        os.environ['SMTP_USE_SSL'] = 'True'
        os.environ['SMTP_USE_TLS'] = 'False'
        service = EmailService()

        mock_server = MagicMock()
        mock_smtp_ssl.return_value = mock_server

        result = service.send_email(
            to_email='user@example.com',
            subject='SSL тест',
            html_body='<p>SSL</p>',
        )

        self.assertTrue(result)
        mock_smtp_ssl.assert_called_once()
        mock_server.send_message.assert_called_once()

    # ────────────────────────────────────────────────────────────
    # Пакетная отправка
    # ────────────────────────────────────────────────────────────

    @patch('smtplib.SMTP')
    def test_send_batch_with_rate_limit(self, mock_smtp: MagicMock) -> None:
        """Пакетная отправка 3 писем — все успешно, с паузой между отправками."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        recipients = [
            {
                'to_email': f'user{i}@example.com',
                'subject': f'Тема {i}',
                'html_body': f'<p>Тело {i}</p>',
                'text_body': f'Тело {i}',
            }
            for i in range(3)
        ]

        result = self.service.send_batch(recipients)

        self.assertEqual(result['sent'], 3)
        self.assertEqual(result['failed'], 0)
        self.assertEqual(result['skipped'], 0)

    @patch('smtplib.SMTP')
    def test_send_batch_exceeds_daily_limit(self, mock_smtp: MagicMock) -> None:
        """Пакетная отправка с превышением дневного лимита — часть писем пропущена."""
        os.environ['SMTP_DAILY_LIMIT'] = '2'
        service = EmailService()

        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        recipients = [
            {
                'to_email': f'user{i}@example.com',
                'subject': f'Тема {i}',
                'html_body': f'<p>Тело {i}</p>',
            }
            for i in range(5)
        ]

        result = service.send_batch(recipients)

        self.assertEqual(result['sent'], 2)
        self.assertGreater(result['skipped'], 0)

    @patch('smtplib.SMTP')
    def test_send_batch_skips_incomplete_recipients(self, mock_smtp: MagicMock) -> None:
        """Пакетная отправка пропускает получателей без обязательных полей."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        recipients = [
            {'to_email': '', 'subject': 'Тема', 'html_body': '<p>Тело</p>'},  # нет email
            {'to_email': 'a@b.com', 'subject': '', 'html_body': '<p>Тело</p>'},  # нет темы
            {'to_email': 'c@d.com', 'subject': 'OK', 'html_body': ''},  # нет тела
        ]

        result = self.service.send_batch(recipients)

        self.assertEqual(result['sent'], 0)
        self.assertEqual(result['skipped'], 3)

    # ────────────────────────────────────────────────────────────
    # Дневной лимит
    # ────────────────────────────────────────────────────────────

    def test_daily_limit_reset(self) -> None:
        """Сброс дневного счётчика при наступлении нового дня."""
        from datetime import date, timedelta

        # Имитируем, что последний сброс был вчера
        self.service._daily_count = 5
        self.service._last_reset_date = date.today() - timedelta(days=1)

        # Проверка лимита должна сбросить счётчик
        can_send = self.service._check_daily_limit()
        self.assertTrue(can_send)
        self.assertEqual(self.service._daily_count, 0)
        self.assertEqual(self.service._last_reset_date, date.today())

    @patch('smtplib.SMTP')
    def test_daily_limit_blocks_when_exceeded(self, mock_smtp: MagicMock) -> None:
        """При превышении дневного лимита отправка блокируется."""
        self.service._daily_count = 10  # равен лимиту
        self.service._daily_limit = 10

        result = self.service.send_email(
            to_email='user@example.com',
            subject='Тест',
            html_body='<p>Тест</p>',
        )

        self.assertFalse(result)
        # SMTP не должен был вызываться
        mock_smtp.assert_not_called()

    # ────────────────────────────────────────────────────────────
    # Рендеринг шаблонов
    # ────────────────────────────────────────────────────────────

    def test_render_template_html(self) -> None:
        """Рендеринг HTML-шаблона письма с контекстом."""
        html_body, text_body = self.service.render_template(
            'notification',
            {'notification_text': 'У вас новое уведомление', 'user_name': 'Иван'},
        )

        self.assertIsInstance(html_body, str)
        self.assertTrue(len(html_body) > 0)
        # HTML-шаблон должен содержать текст уведомления
        self.assertIn('уведомление', html_body.lower())

    def test_render_template_text(self) -> None:
        """Рендеринг текстового шаблона письма с контекстом."""
        html_body, text_body = self.service.render_template(
            'notification',
            {'notification_text': 'У вас новое уведомление', 'user_name': 'Иван'},
        )

        self.assertIsInstance(text_body, str)
        self.assertTrue(len(text_body) > 0)

    def test_render_template_missing_template_fallback(self) -> None:
        """При отсутствии шаблона возвращается fallback HTML/текст."""
        html_body, text_body = self.service.render_template(
            'nonexistent_template_xyz',
            {'notification_text': 'Текст fallback'},
        )

        self.assertIsInstance(html_body, str)
        self.assertTrue(len(html_body) > 0)
        self.assertIn('Trudnik', html_body)

    # ────────────────────────────────────────────────────────────
    # Токен отписки
    # ────────────────────────────────────────────────────────────

    def test_create_unsubscribe_token(self) -> None:
        """Генерация токена отписки — HMAC-SHA256 hex-строка."""
        token = EmailService.create_unsubscribe_token(user_id=42)

        self.assertIsInstance(token, str)
        self.assertEqual(len(token), 64)  # SHA256 hex = 64 символа
        # Все символы должны быть hex
        self.assertTrue(all(c in '0123456789abcdef' for c in token))

    def test_create_unsubscribe_token_deterministic(self) -> None:
        """Токен отписки детерминирован для одного user_id и SECRET_KEY."""
        token1 = EmailService.create_unsubscribe_token(user_id=42)
        token2 = EmailService.create_unsubscribe_token(user_id=42)

        self.assertEqual(token1, token2)

    def test_create_unsubscribe_token_different_users(self) -> None:
        """Токены отписки различаются для разных пользователей."""
        token1 = EmailService.create_unsubscribe_token(user_id=1)
        token2 = EmailService.create_unsubscribe_token(user_id=2)

        self.assertNotEqual(token1, token2)


if __name__ == '__main__':
    unittest.main()
