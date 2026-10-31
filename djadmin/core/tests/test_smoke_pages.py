"""Сквозной smoke всех страниц: рендер шаблонов с реальными данными.

Проверяем, что КАЖДАЯ страница приложения рендерится (200), а не только те,
что покрыты юнит-тестами. Ловит битые шаблоны/контексты, как ручная приёмка.
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Application, Invitation, Job, Message, Profile, Rating, SitePage
from core.tests.test_auth import make_profile
from core.tests.test_flows import make_job


class SmokeAllPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employer = make_profile("smoke-emp@example.com", role="employer")
        cls.worker = make_profile("smoke-worker@example.com", role="worker")
        cls.admin = Profile.objects.create_superuser("smoke-admin@example.com", "Aa1!aaaa")
        cls.job = make_job(cls.employer, work_type="Smoke-задание", status="open")
        cls.completed_job = make_job(cls.employer, work_type="Smoke-завершённое", status="completed")
        cls.app_obj = Application.objects.create(job=cls.completed_job, worker=cls.worker, status="accepted")
        cls.pending_app = Application.objects.create(job=cls.job, worker=make_profile("smoke-w2@example.com"), status="pending")
        cls.msg = Message.objects.create(sender=cls.worker, application=cls.app_obj, content="привет")
        cls.inv = Invitation.objects.create(job=cls.job, employer=cls.employer, worker=cls.worker)
        cls.rating = Rating.objects.create(
            rated_user=cls.worker, rater_user=cls.employer, job=cls.completed_job,
            rating=5, comment="ok", rating_type="employer", target_type="worker")
        
        for slug, title in (("terms", "Условия"), ("privacy", "Политика"), ("safety", "Безопасность")):
            SitePage.objects.create(slug=slug, title=title, content="<p>текст</p>")

    def _get(self, name, *args, **kwargs):
        url = reverse(name, args=args) if args else reverse(name)
        response = self.client.get(url, **kwargs)
        self.assertLess(response.status_code, 500, "%s -> %s" % (name, response.status_code))
        return response

    def test_public_pages(self):
        self.client.logout()
        for name in ("core:jobs", "core:workers", "core:login", "core:register",
                     "core:terms", "core:privacy", "core:safety", "core:faq",
                     "core:password_reset_request", "core:verify_email_resend"):
            self.assertEqual(self._get(name).status_code, 200, name)
        self.assertEqual(self._get("core:job_detail", self.job.pk).status_code, 200)
        self.assertEqual(self._get("core:worker_detail", self.worker.pk).status_code, 200)
        self.assertEqual(self._get("core:sitemap").status_code, 200)
        self.assertEqual(self._get("core:offline").status_code, 200)

    def test_worker_pages(self):
        self.client.force_login(self.worker)
        for name, args in [
            ("core:profile", ()), ("core:my_applications", ()), ("core:my_jobs", ()),
            ("core:chats", ()), ("core:notifications", ()), ("core:favorite_jobs", ()),
            ("core:favorite_people", ()), ("core:blacklist", ()), ("core:invitations", ()),
            ("core:job_create", ()), ("core:notification_prefs", ()), ("core:verify_employer", ()),
            ("core:chat_room", (self.app_obj.pk,)), ("core:user_ratings", (self.worker.pk,)),
            ("core:employers", ()), ("core:employer_detail", (self.employer.pk,)),
        ]:
            self.assertEqual(self._get(name, *args).status_code, 200, name)

    def test_owner_pages(self):
        self.client.force_login(self.employer)
        for name, args in [
            ("core:job_edit", (self.job.pk,)),
            ("core:job_applicants", (self.job.pk,)),
            ("core:rate_workers", (self.completed_job.pk,)),
            ("core:profile", ()),
        ]:
            self.assertEqual(self._get(name, *args).status_code, 200, name)

    def test_admin_pages_render(self):
        self.client.force_login(self.admin)
        for name in ("admin:index", "admin:dashboard", "admin:env",
                     "admin:core_profile_changelist", "admin:core_job_changelist",
                     "admin:core_application_changelist", "admin:core_userreport_changelist",
                     "admin:core_skill_changelist", "admin:core_sitepage_changelist",
                     "admin:core_auditlog_changelist"):
            self.assertEqual(self._get(name).status_code, 200, name)

    def test_admin_forms_render(self):
        self.client.force_login(self.admin)
        for name, args in [
            ("admin:core_profile_change", (self.worker.pk,)),
            ("admin:core_job_change", (self.job.pk,)),
            ("admin:core_profile_add", ()),
        ]:
            self.assertEqual(self._get(name, *args).status_code, 200, name)

    def test_health(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
