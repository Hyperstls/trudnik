"""R058: маскировка email в логах (152-ФЗ)."""
from unittest.mock import patch

from django.test import TestCase

from core.privacy import mask_email, mask_text
from core.tasks import send_transactional_email
from core.tests.test_auth import make_profile


class MaskEmailTests(TestCase):
    def test_regular_email(self):
        self.assertEqual(mask_email("user@example.com"), "us***@example.com")

    def test_short_local_part(self):
        self.assertEqual(mask_email("a@x.y"), "a***@x.y")
        self.assertEqual(mask_email("ab@x.y"), "ab***@x.y")

    def test_no_at_sign(self):
        self.assertEqual(mask_email("just-a-string"), "ju***")
        self.assertEqual(mask_email("a"), "a***")

    def test_empty_and_none(self):
        self.assertEqual(mask_email(""), "")
        self.assertEqual(mask_email(None), "")

    def test_not_a_string_is_coerced(self):
        self.assertEqual(mask_email(12345), "12***")


class TaskLoggingMaskedTests(TestCase):
    def test_send_failure_logs_masked_email(self):
        user = make_profile("veryprivate@example.com")
        with patch("core.tasks.send_mail", side_effect=RuntimeError("smtp down")):
            with self.assertLogs("core.tasks", level="WARNING") as captured:
                try:
                    send_transactional_email("subject", "body", user.email)
                except Exception:
                    pass  # retry-исключение ожидаемо
        joined = "\n".join(captured.output)
        self.assertNotIn("veryprivate@example.com", joined)
        self.assertIn("ve***@example.com", joined)


class ViewsAuthLoggingStaticTests(TestCase):
    def test_no_raw_email_in_auth_log_statements(self):
        """views_auth.py не логирует сырой to_email рядом с to=%s."""
        import pathlib

        source = pathlib.Path("djadmin/core/views_auth.py").read_text(encoding="utf-8")
        self.assertIn("from .privacy import mask_email", source)
        self.assertNotIn('"transactional email enqueue failed to=%s", to_email', source)
        self.assertNotIn('"email send failed to=%s", to_email', source)


class MaskTextTests(TestCase):
    def test_masks_all_emails_inside_text(self):
        text = "SMTPRecipientsRefused: {'victim@example.com': (550, b'no'), 'b@x.yz': (1, b'')}"
        masked = mask_text(text)
        self.assertNotIn("victim@example.com", masked)
        self.assertNotIn("b@x.yz", masked)
        self.assertIn("vi***@example.com", masked)
        self.assertIn("b***@x.yz", masked)

    def test_plain_text_untouched(self):
        self.assertEqual(mask_text("smtp down"), "smtp down")
        self.assertEqual(mask_text(""), "")
        self.assertEqual(mask_text(None), "")


class SmtpExceptionMaskedTests(TestCase):
    def test_task_log_and_email_log_have_no_raw_address(self):
        import smtplib

        from core.models import EmailLog, NotificationOutbox
        from core.tasks import _send_email, send_transactional_email
        from core.tests.test_auth import make_profile

        user = make_profile("victim-r068@example.com")
        refused = smtplib.SMTPRecipientsRefused({"victim-r068@example.com": (550, b"no")})
        with patch("core.tasks.send_mail", side_effect=refused):
            with self.assertLogs("core.tasks", level="WARNING") as captured:
                try:
                    send_transactional_email("s", "m", user.email)
                except Exception:
                    pass  # Retry — ожидаемо
        joined = "\n".join(captured.output)
        self.assertNotIn("victim-r068@example.com", joined)
        self.assertIn("vi***@example.com", joined)
        # EmailLog: тот же сбой, но через _send_email (в том же patch-контексте)
        row = NotificationOutbox.objects.create(
            user=user, type="test", title="t", body="b"
        )
        with patch("core.tasks.send_mail", side_effect=refused):
            self.assertFalse(_send_email(row))
        log = EmailLog.objects.filter(user=user).latest("id")
        self.assertNotIn(user.email, log.error_message or "")
        self.assertIn("vi***@example.com", log.error_message or "")
