"""Автоматический антиспам/антифрод (J158)."""
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core import anti_fraud
from core.models import Job, NotificationOutbox
from core.tests.test_auth import CACHE_LOCMEM, make_profile
from core.tests.test_flows import make_job


def _payload(**overrides):
    payload = {
        "work_type": "Уборка", "organization_name": "Храм",
        "detailed_description": "Убрать территорию",
        "address": "ул. Ленина 1", "city": "Москва",
        "payment_amount": "1500.00", "max_workers": "3",
        "date_time": (timezone.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
        "skills": [],
    }
    payload.update(overrides)
    return payload


@override_settings(CACHES=CACHE_LOCMEM)
class JobRiskTests(TestCase):
    def setUp(self):
        cache.clear()
        self.employer = make_profile("af-emp@example.com", role="employer")

    def test_normal_job_is_published(self):
        result = anti_fraud.assess_job(
            self.employer, work_type="Уборка", city="Москва",
            texts=("Убрать территорию", "Оплата после работы"),
        )
        self.assertEqual(result["status"], Job.ModerationStatus.OK)
        self.assertEqual(result["score"], 0)

    def test_duplicate_job_goes_to_review(self):
        make_job(self.employer, work_type="Уборка", city="Москва")
        result = anti_fraud.assess_job(
            self.employer, work_type="Уборка", city="Москва", texts=("Текст",),
        )
        self.assertEqual(result["status"], Job.ModerationStatus.REVIEW)
        self.assertIn("24 часа", result["reason"])

    def test_posting_burst_goes_to_review(self):
        for _ in range(5):
            make_job(self.employer, work_type="Разное")
        result = anti_fraud.assess_job(
            self.employer, work_type="Новая работа", texts=("Текст",),
        )
        self.assertEqual(result["status"], Job.ModerationStatus.REVIEW)
        self.assertIn("последний час", result["reason"])

    def test_external_contacts_go_to_review(self):
        result = anti_fraud.assess_job(
            self.employer, work_type="Уборка",
            texts=("Звонить +7 999 123-45-67", "Писать t.me/spam"),
        )
        self.assertEqual(result["status"], Job.ModerationStatus.REVIEW)
        self.assertIn("контакт", result["reason"])

    def test_create_view_quarantines_suspicious_job(self):
        self.client.force_login(self.employer)
        response = self.client.post(reverse("core:job_create"), _payload(
            detailed_description="Звонить +7 999 123-45-67 или t.me/spam",
        ))
        self.assertEqual(response.status_code, 302)
        job = Job.objects.get(employer=self.employer)
        self.assertEqual(job.moderation_status, Job.ModerationStatus.REVIEW)
        self.assertFalse(Job.objects.public().filter(pk=job.pk).exists())

        # Владелец видит баннер, остальные — 404.
        owner_page = self.client.get(reverse("core:job_detail", args=[job.pk]))
        self.assertContains(owner_page, "Задание на проверке")
        other = make_profile("af-other@example.com")
        self.client.force_login(other)
        self.assertEqual(
            self.client.get(reverse("core:job_detail", args=[job.pk])).status_code,
            404,
        )

    def test_create_view_blocks_job_hourly_flood(self):
        self.client.force_login(self.employer)
        for _ in range(anti_fraud.JOB_HOURLY_LIMIT):
            self.client.post(reverse("core:job_create"), _payload(work_type="Разное"))
        response = self.client.post(reverse("core:job_create"), _payload(work_type="Ещё"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Слишком много новых заданий")


@override_settings(CACHES=CACHE_LOCMEM)
class LimitsTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_application_daily_limit(self):
        user = make_profile("af-limit@example.com")
        for _ in range(anti_fraud.APPLICATION_DAILY_LIMIT):
            self.assertTrue(anti_fraud.allow_application(user.pk))
        self.assertFalse(anti_fraud.allow_application(user.pk))


@override_settings(CACHES=CACHE_LOCMEM)
class ModerationAdminTests(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = make_profile("af-staff@example.com", role="admin")
        self.employer = make_profile("af-admin-emp@example.com", role="employer")
        self.job = make_job(
            self.employer, work_type="Спам", moderation_status="review",
            moderation_reason="Похожее задание",
        )

    def test_admin_approves_review_job(self):
        self.client.force_login(self.staff)
        response = self.client.post("/admin/core/job/", {
            "action": "action_moderation_approve",
            "_selected_action": [str(self.job.pk)],
        })
        self.assertEqual(response.status_code, 302)
        self.job.refresh_from_db()
        self.assertEqual(self.job.moderation_status, "ok")
        self.assertTrue(Job.objects.public().filter(pk=self.job.pk).exists())
        self.assertTrue(
            NotificationOutbox.objects.filter(
                user_id=self.employer.pk, type="job_moderation",
            ).exists()
        )

    def test_admin_rejects_job(self):
        self.client.force_login(self.staff)
        response = self.client.post("/admin/core/job/", {
            "action": "action_moderation_reject",
            "_selected_action": [str(self.job.pk)],
        })
        self.assertEqual(response.status_code, 302)
        self.job.refresh_from_db()
        self.assertEqual(self.job.moderation_status, "rejected")
        self.assertFalse(Job.objects.public().filter(pk=self.job.pk).exists())
