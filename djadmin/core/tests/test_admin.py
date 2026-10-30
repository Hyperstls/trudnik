"""Доступ к админке и ключевым страницам: superuser да, остальные нет."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

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

    def test_dashboard_ok(self):
        self.client.force_login(self.admin)
        response = self.client.get("/admin/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Дашборд")

    def test_profile_skills_editor(self):
        worker = make_profile("skills@example.com")
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("admin:core_profile_skills", args=[worker.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Навыки")


class AdminLoginPageTests(TestCase):
    def test_login_page_renders(self):
        response = self.client.get("/admin/login/")
        self.assertEqual(response.status_code, 200)

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
