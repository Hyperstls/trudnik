"""Фаза 3: фоновые задачи (drain/expire/freeze/cleanup) — логика против клона БД."""
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import EmailLog, Job, Notification, NotificationOutbox, Profile, UserReport
from core.tasks import (
    auto_freeze_on_complaints,
    cleanup_old_email_logs,
    drain_notification_outbox,
    expire_old_jobs,
)
from core.tests.test_auth import make_profile
from core.tests.test_flows import make_job

LOCMEM = {"EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend"}


def make_outbox(user, title="Тест-уведомление", body="Текст письма"):
    return NotificationOutbox.objects.create(user=user, type="test", title=title, body=body)


@override_settings(**LOCMEM)
class DrainTests(TestCase):
    def setUp(self):
        mail.outbox.clear()
        self.user = make_profile("drain-me@example.com")

    def test_drain_creates_notification_and_sends_email(self):
        make_outbox(self.user)
        summary = drain_notification_outbox()
        self.assertIn("processed=1", summary)
        self.assertEqual(Notification.objects.filter(user=self.user, title="Тест-уведомление").count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        row = NotificationOutbox.objects.get(user=self.user)
        self.assertEqual(row.status, "sent")
        self.assertIsNotNone(row.processed_at)
        self.assertEqual(EmailLog.objects.filter(user=self.user, status="sent").count(), 1)

    def test_drain_respects_prefs_off(self):
        self.user.notification_prefs = {"email": False}
        self.user.save(update_fields=["notification_prefs"])
        make_outbox(self.user, title="Без email")
        summary = drain_notification_outbox()
        self.assertIn("skipped=1", summary)
        self.assertEqual(len(mail.outbox), 0)
        # web-уведомление всё равно создано, outbox закрыт
        self.assertEqual(Notification.objects.filter(user=self.user, title="Без email").count(), 1)
        self.assertEqual(NotificationOutbox.objects.get(user=self.user).status, "sent")

    def test_email_enabled_off_keeps_in_app(self):
        self.user.notification_prefs = {"email_enabled": False, "in_app_enabled": True}
        self.user.save(update_fields=["notification_prefs"])
        make_outbox(self.user, title="Без email J088")
        drain_notification_outbox()
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(Notification.objects.filter(user=self.user, title="Без email J088").exists())

    def test_in_app_off_keeps_email(self):
        self.user.notification_prefs = {"email_enabled": True, "in_app_enabled": False}
        self.user.save(update_fields=["notification_prefs"])
        make_outbox(self.user, title="Только email J088")
        drain_notification_outbox()
        self.assertEqual(len(mail.outbox), 1)
        self.assertFalse(Notification.objects.filter(user=self.user, title="Только email J088").exists())

    def test_type_pref_off_skips_all_channels(self):
        self.user.notification_prefs = {"chat": False}
        self.user.save(update_fields=["notification_prefs"])
        NotificationOutbox.objects.create(
            user=self.user, type="new_message", title="Чат off J088", body="x"
        )
        drain_notification_outbox()
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(Notification.objects.filter(user=self.user, title="Чат off J088").exists())

    def test_push_pref_off_skips_push(self):
        self.user.notification_prefs = {"push_enabled": False}
        self.user.save(update_fields=["notification_prefs"])
        make_outbox(self.user, title="Push off J088")
        with patch("core.tasks._send_pushes") as pushes:
            drain_notification_outbox()
        pushes.assert_not_called()

    def test_failed_email_retries_then_fails_after_max(self):
        make_outbox(self.user, title="Три попытки")
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"):
            for _ in range(2):  # 2 неудачи (SMTP недоступен в тестах)
                drain_notification_outbox()
            row = NotificationOutbox.objects.get(user=self.user)
            self.assertEqual(row.status, "pending")  # попытки не исчерпаны
            self.assertEqual(row.attempts, 2)
        drain_notification_outbox()  # 3-я — с locmem, успешная
        row.refresh_from_db()
        self.assertEqual(row.status, "sent")


class ExpireTests(TestCase):
    def test_open_job_with_past_expiry_flips(self):
        employer = make_profile("exp-emp@example.com")
        job = make_job(employer, status="open")
        Job.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(hours=1))
        # RPC expire_unfilled_jobs тоже работает на клоне — суммарно ≥1
        total = expire_old_jobs()
        self.assertGreaterEqual(total, 1)
        job.refresh_from_db()
        self.assertEqual(job.status, "expired")

    def test_expire_old_jobs_uses_rpc_count(self):
        # call_rpc отдаёт строку как dict: {'expire_unfilled_jobs': N}; счётчик
        # RPC должен прибавиться к ORM-счётчику, а не упасть в int(dict).
        neutralize_preloaded_expired_jobs()
        with patch("core.tasks.call_rpc", return_value={"expire_unfilled_jobs": 3}):
            total = expire_old_jobs()
        self.assertEqual(total, 3)  # ORM=0, RPC=3, без TypeError

    def test_expire_old_jobs_keeps_orm_count_when_rpc_fails(self):
        neutralize_preloaded_expired_jobs()
        employer = make_profile("exp-emp-rpc@example.com")
        job = make_job(employer, status="open")
        Job.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(hours=1))
        with patch("core.tasks.call_rpc", side_effect=RuntimeError("rpc down")):
            with self.assertLogs("core.tasks", level="WARNING") as logs:
                total = expire_old_jobs()
        self.assertEqual(total, 1)  # только ORM-счётчик
        self.assertTrue(any("expire_unfilled_jobs rpc failed" in line for line in logs.output))


class AutoFreezeTests(TestCase):
    def test_reports_threshold_suspends_via_rpc(self):
        reporter = make_profile("frz-reporter@example.com")
        victim = make_profile("frz-victim@example.com", role="worker")
        UserReport.objects.create(reporter=reporter, reported=victim, reason="спам")
        UserReport.objects.create(reporter=make_profile("frz-r2@example.com"), reported=victim, reason="спам")
        UserReport.objects.create(reporter=make_profile("frz-r3@example.com"), reported=victim, reason="спам")
        UserReport.objects.create(reporter=make_profile("frz-r4@example.com"), reported=victim, reason="спам")
        UserReport.objects.create(reporter=make_profile("frz-r5@example.com"), reported=victim, reason="спам")
        frozen = auto_freeze_on_complaints(threshold=5, hours=24)
        self.assertGreaterEqual(frozen, 1)
        victim.refresh_from_db()
        self.assertTrue(victim.suspended)


class CleanupTests(TestCase):
    def test_old_sent_logs_removed(self):
        old = EmailLog.objects.create(user=this_user(), to_email="x@x.io", subject="s", status="sent")
        EmailLog.objects.filter(pk=old.pk).update(sent_at=timezone.now() - timedelta(days=31))
        fresh = EmailLog.objects.create(user=this_user(), to_email="y@x.io", subject="s", status="sent")
        removed = cleanup_old_email_logs()
        self.assertGreaterEqual(removed, 1)
        self.assertTrue(EmailLog.objects.filter(pk=fresh.pk).exists())
        self.assertFalse(EmailLog.objects.filter(pk=old.pk).exists())


def this_user():
    return Profile.objects.filter(email="cln-user@example.com").first() or make_profile("cln-user@example.com")


def neutralize_preloaded_expired_jobs():
    """Клон БД содержит open-задания с прошедшим expires_at: уводим их из окна
    задачи, чтобы ORM-счётчик теста зависел только от его собственных данных
    (TestCase откатит изменения)."""
    Job.objects.filter(
        status=Job.Status.OPEN, expires_at__lt=timezone.now()
    ).update(expires_at=timezone.now() + timedelta(days=365))
