"""Фаза 3: фоновые задачи (drain/expire/freeze/cleanup) — логика против клона БД."""
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import EmailLog, Job, Notification, NotificationOutbox, Profile, UserReport
from core.tasks import (
    auto_freeze_on_complaints,
    notify_saved_searches,
    cleanup_old_email_logs,
    cleanup_personal_data_retention,
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


class SavedSearchDigestTests(TestCase):
    def setUp(self):
        self.user = make_profile("digest-user@example.com", email_verified=True)
        self.user.notification_prefs = {
            "saved_searches": [{"id": "s1", "name": "Москва", "query": "city=Москва"}],
        }
        self.user.save(update_fields=["notification_prefs"])

    def test_digest_matches_and_deduplicates(self):
        from core.models import NotificationOutbox
        employer = make_profile("digest-emp@example.com")
        job = make_job(employer, work_type="Дайджест-задача", city="Москва")
        notify_saved_searches()
        row = NotificationOutbox.objects.get(user=self.user, type="saved_search")
        self.assertIn("Дайджест-задача", row.body)
        self.assertIn(str(job.pk), row.data["link"])
        notify_saved_searches()
        self.assertEqual(
            NotificationOutbox.objects.filter(user=self.user, type="saved_search").count(), 1
        )

    def test_two_searches_both_in_digest(self):
        from core.models import NotificationOutbox
        self.user.notification_prefs = {
            "saved_searches": [
                {"id": "s1", "name": "Москва", "query": "city=Москва"},
                {"id": "s2", "name": "Казань", "query": "city=Казань"},
            ],
        }
        self.user.save(update_fields=["notification_prefs"])
        employer = make_profile("digest-two@example.com")
        make_job(employer, work_type="Москва-работа", city="Москва")
        make_job(employer, work_type="Казань-работа", city="Казань")
        notify_saved_searches()
        row = NotificationOutbox.objects.get(user=self.user, type="saved_search")
        self.assertIn("Москва", row.body)
        self.assertIn("Казань", row.body)
        self.assertIn("Москва-работа", row.body)
        self.assertIn("Казань-работа", row.body)

    def test_digest_window_starts_at_last_digest(self):
        from core.models import NotificationOutbox
        from django.utils import timezone
        from datetime import timedelta
        self.user.notification_prefs = {
            "saved_searches": [{"id": "s1", "name": "Москва", "query": "city=Москва"}],
            "saved_search_digest_at": (timezone.now() - timedelta(hours=24, minutes=10)).isoformat(),
        }
        self.user.save(update_fields=["notification_prefs"])
        employer = make_profile("digest-boundary@example.com")
        job = make_job(employer, work_type="Пограничная задача", city="Москва")
        Job.objects.filter(pk=job.pk).update(created_at=timezone.now() - timedelta(hours=24, minutes=5))
        notify_saved_searches()
        self.assertTrue(
            NotificationOutbox.objects.filter(user=self.user, type="saved_search").exists()
        )

    def test_notify_off_skips_digest(self):
        from core.models import NotificationOutbox
        self.user.notification_prefs = {
            "saved_searches": [{
                "id": "s1", "name": "Москва", "query": "city=Москва", "notify": False,
            }],
        }
        self.user.save(update_fields=["notification_prefs"])
        make_job(make_profile("digest-off@example.com"), city="Москва")
        notify_saved_searches()
        self.assertFalse(
            NotificationOutbox.objects.filter(user=self.user, type="saved_search").exists()
        )

    def test_own_job_excluded(self):
        from core.models import NotificationOutbox
        make_job(self.user, work_type="Своя задача", city="Москва")
        notify_saved_searches()
        self.assertFalse(
            NotificationOutbox.objects.filter(user=self.user, type="saved_search").exists()
        )

    def test_disabled_type_blocks_delivery(self):
        from core.models import NotificationOutbox
        self.user.notification_prefs = {
            "saved_searches": [{"id": "s1", "name": "Москва", "query": "city=Москва"}],
            "saved_search": False,
        }
        self.user.save(update_fields=["notification_prefs"])
        make_job(make_profile("digest-emp2@example.com"), city="Москва")
        notify_saved_searches()
        drain_notification_outbox()
        self.assertFalse(
            Notification.objects.filter(user=self.user, type="saved_search").exists()
        )
        self.assertEqual(
            NotificationOutbox.objects.get(user=self.user, type="saved_search").status,
            "sent",
        )


class SavedSearchFrequencyTests(TestCase):
    def setUp(self):
        self.user = make_profile("digest-freq@example.com", email_verified=True)

    def _prefs(self, frequency, digest_at=None):
        prefs = {
            "saved_searches": [{"id": "s1", "name": "Москва", "query": "city=Москва"}],
            "digest_frequency": frequency,
        }
        if digest_at:
            prefs["saved_search_digest_at"] = digest_at.isoformat()
        self.user.notification_prefs = prefs
        self.user.save(update_fields=["notification_prefs"])

    def test_frequency_off_skips(self):
        from core.models import NotificationOutbox
        from django.utils import timezone
        self._prefs("off", timezone.now() - timedelta(hours=30))
        make_job(make_profile("digest-freq-emp@example.com"), city="Москва")
        notify_saved_searches()
        self.assertFalse(
            NotificationOutbox.objects.filter(user=self.user, type="saved_search").exists()
        )

    def test_frequency_instant_bypasses_daily_gate(self):
        from core.models import NotificationOutbox
        from django.utils import timezone
        self._prefs("instant", timezone.now() - timedelta(minutes=1))
        employer = make_profile("digest-freq-emp2@example.com")
        make_job(employer, work_type="Instant job", city="Москва")
        notify_saved_searches()
        self.assertTrue(
            NotificationOutbox.objects.filter(user=self.user, type="saved_search").exists()
        )


class RetentionTaskTests(TestCase):
    """R057: сроки хранения ПДн — outbox/audit/сессии/push-подписки."""

    def setUp(self):
        self.user = make_profile("retention-me@example.com")
        self.now = timezone.now()

    def _outbox(self, status, **fields):
        row = NotificationOutbox.objects.create(
            user=self.user, type="test", title="t", body="b", status=status
        )
        NotificationOutbox.objects.filter(pk=row.pk).update(**fields)
        return row

    def test_outbox_sent_skipped_and_failed_retention(self):
        self._outbox("sent", processed_at=self.now - timedelta(days=31))
        self._outbox("skipped", processed_at=self.now - timedelta(days=31))
        self._outbox("sent", processed_at=self.now - timedelta(days=29))   # остаётся
        self._outbox("failed", created_at=self.now - timedelta(days=8))    # удаляется
        self._outbox("failed", created_at=self.now - timedelta(days=6))    # остаётся
        old_pending = self._outbox("pending", created_at=self.now - timedelta(days=8))   # удаляется (C4)
        fresh_pending = self._outbox("pending", created_at=self.now - timedelta(days=6))  # остаётся

        counts = cleanup_personal_data_retention()

        self.assertEqual(counts["notification_outbox"], 4)
        self.assertEqual(NotificationOutbox.objects.count(), 3)
        statuses = sorted(NotificationOutbox.objects.values_list("status", flat=True))
        self.assertEqual(statuses, ["failed", "pending", "sent"])
        self.assertFalse(NotificationOutbox.objects.filter(pk=old_pending.pk).exists())
        self.assertTrue(NotificationOutbox.objects.filter(pk=fresh_pending.pk).exists())

    def test_audit_log_retention_180_days(self):
        from core.audit import log_admin_action
        from core.models import AuditLog

        old = AuditLog.objects.create(action="old", created_at=self.now - timedelta(days=181))
        AuditLog.objects.filter(pk=old.pk).update(created_at=self.now - timedelta(days=181))
        fresh = AuditLog.objects.create(action="fresh")

        counts = cleanup_personal_data_retention()

        self.assertEqual(counts["audit_log"], 1)
        self.assertEqual(AuditLog.objects.filter(pk=fresh.pk).count(), 1)
        self.assertFalse(AuditLog.objects.filter(pk=old.pk).exists())

    def test_expired_sessions_removed(self):
        from django.contrib.sessions.models import Session

        stale = Session.objects.create(
            session_key="retention-stale",
            session_data="x",
            expire_date=self.now - timedelta(hours=1),
        )
        fresh = Session.objects.create(
            session_key="retention-fresh",
            session_data="x",
            expire_date=self.now + timedelta(days=1),
        )

        counts = cleanup_personal_data_retention()

        self.assertGreaterEqual(counts["expired_sessions"], 1)
        self.assertFalse(Session.objects.filter(pk=stale.pk).exists())
        self.assertTrue(Session.objects.filter(pk=fresh.pk).exists())

    def test_error_events_retention_90_days(self):
        """R069: политика 10.8 — журнал ошибок не старше 90 дней."""
        from core.models import ErrorEvent

        old = ErrorEvent.objects.create(
            exception_type="ValueError", path="/old", method="GET"
        )
        ErrorEvent.objects.filter(pk=old.pk).update(
            created_at=self.now - timedelta(days=91)
        )
        fresh = ErrorEvent.objects.create(
            exception_type="KeyError", path="/fresh", method="GET"
        )

        counts = cleanup_personal_data_retention()

        self.assertEqual(counts["error_events"], 1)
        self.assertFalse(ErrorEvent.objects.filter(pk=old.pk).exists())
        self.assertTrue(ErrorEvent.objects.filter(pk=fresh.pk).exists())

    def test_stale_push_subscriptions_removed(self):
        from core.models import PushSubscription

        stale = PushSubscription.objects.create(
            user=self.user, endpoint="https://old.push.test/x", p256dh="k", auth="a"
        )
        PushSubscription.objects.filter(pk=stale.pk).update(
            updated_at=self.now - timedelta(days=91)
        )
        fresh = PushSubscription.objects.create(
            user=self.user, endpoint="https://new.push.test/x", p256dh="k", auth="a"
        )

        counts = cleanup_personal_data_retention()

        self.assertEqual(counts["stale_push_subscriptions"], 1)
        self.assertTrue(PushSubscription.objects.filter(pk=fresh.pk).exists())
        self.assertFalse(PushSubscription.objects.filter(pk=stale.pk).exists())

    def test_branch_failure_does_not_block_others(self):
        with patch(
            "core.models.NotificationOutbox.objects.filter",
            side_effect=RuntimeError("db down"),
        ):
            counts = cleanup_personal_data_retention()
        self.assertIsNone(counts["notification_outbox"])
        # остальные ветки отработали (числа или 0, но не None)
        for key in (
            "audit_log", "expired_sessions", "stale_push_subscriptions",
            "error_events",
        ):
            self.assertIsNotNone(counts[key], key)
