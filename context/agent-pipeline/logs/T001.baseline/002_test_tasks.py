"""Фаза 3: фоновые задачи (drain/expire/freeze/cleanup) — логика против клона БД."""
from datetime import timedelta

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
