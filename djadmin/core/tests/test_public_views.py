"""Публичные read-only страницы + health."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import Job, SitePage
from core.tests.test_auth import make_profile


class PublicViewsTests(TestCase):
    def setUp(self):
        self.employer = make_profile("emp-pub@example.com", role="employer")
        self.worker = make_profile(
            "worker-pub@example.com", role="worker",
            phone="+79990001122", bio="Мастер на все руки",
        )
        self.job = Job.objects.create(
            employer=self.employer,
            work_type="Уборка территории",
            organization_name="Приход",
            status="open",
            city="Москва",
            payment_amount=3000,
            date_time=timezone.now() + timedelta(days=2),
        )

    def test_health_ok(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["db"])

    def test_home(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Уборка территории")

    def test_jobs_list_and_filters(self):
        self.assertEqual(self.client.get("/jobs").status_code, 200)
        self.assertContains(self.client.get("/jobs?q=уборка"), "Уборка территории")
        self.assertNotIn("Уборка территории".encode(), self.client.get("/jobs?q=сварка").content)
        self.assertContains(self.client.get("/jobs?city=москва"), "Уборка территории")
        self.assertContains(self.client.get("/jobs?payment_min=1000"), "Уборка территории")
        self.assertNotIn("Уборка территории".encode(), self.client.get("/jobs?payment_min=9999").content)

    def test_job_detail_ok_and_hidden_404(self):
        self.assertEqual(self.client.get(f"/jobs/{self.job.pk}").status_code, 200)
        hidden = Job.objects.create(
            employer=self.employer, work_type="Черновик", status="draft",
            date_time=timezone.now(),
        )
        self.assertEqual(self.client.get(f"/jobs/{hidden.pk}").status_code, 404)

    def test_workers_catalog(self):
        response = self.client.get("/workers")
        self.assertEqual(response.status_code, 200)
        # новый профиль (rating=0) может быть не на 1-й странице среди данных клона — ищем поиском
        self.assertContains(self.client.get("/workers?q=Иван"), self.worker.full_name)

    def test_worker_detail_hides_private_fields(self):
        response = self.client.get(f"/workers/{self.worker.pk}")
        self.assertEqual(response.status_code, 200)
        # приватные колонки (email/phone) никогда не рендерятся
        self.assertNotContains(response, "worker-pub@example.com")
        self.assertNotContains(response, "+79990001122")

    def test_worker_detail_404_for_admin_profile(self):
        admin = make_profile("adm@example.com", role="admin")
        self.assertEqual(self.client.get(f"/workers/{admin.pk}").status_code, 404)

    def test_legal_page(self):
        SitePage.objects.create(slug="terms", title="Правила", content="<p>Текст правил</p>")
        response = self.client.get("/terms")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Текст правил")

    def test_robots(self):
        self.assertEqual(self.client.get("/robots.txt").status_code, 200)
