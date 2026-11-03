"""Доступ к админке и ключевым страницам: superuser да, остальные нет."""
import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Rating, SitePage
from core.tests.test_auth import make_profile

User = get_user_model()

CHANGELISTS = [
    "admin:core_profile_changelist",
    "admin:core_job_changelist",
    "admin:core_application_changelist",
    "admin:core_notification_changelist",
    "admin:core_userreport_changelist",
    "admin:core_skill_changelist",
    "admin:core_religion_changelist",
    "admin:core_sitepage_changelist",
    "admin:core_auditlog_changelist",
    "admin:core_notificationoutbox_changelist",
    "admin:core_emaillog_changelist",
    "admin:core_pushsubscription_changelist",
    "admin:core_message_changelist",
    "admin:core_rating_changelist",
    "admin:core_ratingreport_changelist",
    "admin:core_invitation_changelist",
    "admin:core_receipt_changelist",
]


class AdminAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("root@example.com", "Aa1!aaaa")  # pragma: allowlist secret
        # 'create_superuser' у нашего менеджера пишет в profiles напрямую

    def test_anonymous_redirected(self):
        for url_name in CHANGELISTS:
            with self.subTest(url=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 302, url_name)
                self.assertIn("/admin/login/", response["Location"])

    def test_non_staff_redirected(self):
        make_profile("worker@example.com")
        self.client.login(username="worker@example.com", password="Aa1!aaaa")  # pragma: allowlist secret
        response = self.client.get(reverse("admin:core_profile_changelist"))
        self.assertEqual(response.status_code, 302)

    def test_admin_changelists_ok(self):
        self.client.force_login(self.admin)
        for url_name in CHANGELISTS:
            with self.subTest(url=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200, url_name)

    def test_sitepage_add_with_string_pk(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("admin:core_sitepage_add"),
            {"slug": "faq-admin-test", "title": "FAQ", "content": "<p>ok</p>", "_save": "Сохранить"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(SitePage.objects.filter(pk="faq-admin-test").exists())

    def test_sitepage_change_is_previewable_and_slug_is_readonly(self):
        SitePage.objects.create(slug="privacy", title="Политика", content="<p>ok</p>")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:core_sitepage_change", args=["privacy"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/privacy")
        self.assertNotContains(response, 'name="slug"')
        self.assertContains(response, 'id="sitepage-preview"')
        self.assertContains(response, "admin-sitepage-preview.js")

    def test_dashboard_ok(self):
        self.client.force_login(self.admin)
        response = self.client.get("/admin/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Дашборд")

    def test_admin_index_has_grouped_links(self):
        self.client.force_login(self.admin)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)
        for text in (
            "Дашборд", "Аналитика", "Переменные окружения",
            "Профили", "Задания", "Платежи и подписки",
            "Уведомления и поддержка", "Контентные страницы", "Оценки",
        ):
            self.assertContains(response, text)
        self.assertContains(response, "/admin/env/")
        self.assertContains(response, "/admin/analytics/")

    def test_profile_skills_editor(self):
        worker = make_profile("skills@example.com")
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("admin:core_profile_skills", args=[worker.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Навыки")


    def test_env_page_staff_only(self):
        url = "/admin/env/"
        self.assertEqual(self.client.get(url).status_code, 302)  # аноним
        make_profile("env-plain@example.com")
        self.client.login(username="env-plain@example.com", password="Aa1!aaaa")  # pragma: allowlist secret
        self.assertEqual(self.client.get(url).status_code, 302)  # не-staff
        self.client.force_login(self.admin)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PATH")

class AdminEnvTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("env-root@example.com", "Aa1!aaaa")  # pragma: allowlist secret

    def test_env_page_masks_secrets(self):
        env = {
            "SECRET_KEY": "super-secret-value",  # pragma: allowlist secret
            "SMTP_PASSWORD": "smtp-secret",  # pragma: allowlist secret
            "DJANGO_ALLOWED_HOSTS": "example.com",
        }
        with patch.dict(os.environ, env):
            self.client.force_login(self.admin)
            response = self.client.get("/admin/env/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "super-secret-value")
        self.assertNotContains(response, "smtp-secret")
        self.assertContains(response, "****** (set)")
        self.assertContains(response, "example.com")


class AdminLoginPageTests(TestCase):
    def test_login_page_renders(self):
        response = self.client.get("/admin/login/")
        self.assertEqual(response.status_code, 200)


class RatingModerationAdminTests(TestCase):
    def setUp(self):
        from core.tests.test_flows import make_job
        self.staff = User.objects.create_superuser("rating-admin@example.com", "Aa1!aaaa")  # pragma: allowlist secret
        self.employer = make_profile("rating-mod-emp@example.com", role="employer")
        self.worker = make_profile("rating-mod-worker@example.com", role="worker")
        self.job = make_job(self.employer, status="completed")
        self.rating = Rating.objects.create(
            rated_user=self.worker, rater_user=self.employer, job=self.job,
            rating=5, comment="На проверке", rating_type="employer",
            target_type="worker", moderation_status=Rating.ModerationStatus.REVIEW,
        )

    def test_approve_publishes_and_recomputes(self):
        self.client.force_login(self.staff)
        response = self.client.post("/admin/core/rating/", {
            "action": "action_moderation_approve",
            "_selected_action": [str(self.rating.pk)],
        })
        self.assertEqual(response.status_code, 302)
        self.rating.refresh_from_db()
        self.assertEqual(self.rating.moderation_status, "ok")
        self.assertIsNotNone(self.rating.published_at)
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.worker_ratings_count, 1)

    def test_hide_removes_from_aggregates(self):
        self.rating.published_at = timezone.now()
        self.rating.save(update_fields=["published_at"])
        self.client.force_login(self.staff)
        response = self.client.post("/admin/core/rating/", {
            "action": "action_moderation_hide",
            "_selected_action": [str(self.rating.pk)],
        })
        self.assertEqual(response.status_code, 302)
        self.rating.refresh_from_db()
        self.assertEqual(self.rating.moderation_status, "hidden")
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.worker_ratings_count, 0)
