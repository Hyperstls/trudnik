"""First-party aggregate funnel counters (J123/J134)."""
import json
import uuid
from datetime import date, timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core import analytics
from core.tests.test_auth import CACHE_LOCMEM, make_profile
from core.tests.test_flows import make_job


@override_settings(CACHES=CACHE_LOCMEM)
class AnalyticsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.employer = make_profile("analytics-emp@example.com", role="employer")
        self.worker = make_profile("analytics-worker@example.com", role="worker")
        self.job = make_job(self.employer)

    def counter(self, event):
        return int(cache.get(analytics._key(event, date.today())) or 0)

    def test_job_view_counted_once_per_authenticated_session(self):
        self.client.force_login(self.worker)
        self.client.get(reverse("core:job_detail", args=[self.job.pk]))
        self.client.get(reverse("core:job_detail", args=[self.job.pk]))
        self.assertEqual(self.counter("job_view"), 1)

    def test_anonymous_job_view_not_counted_server_side(self):
        # Anonymous views come from job-view.js once per browser/day.
        self.client.get(reverse("core:job_detail", args=[self.job.pk]))
        self.client.get(reverse("core:job_detail", args=[self.job.pk]))
        self.assertEqual(self.counter("job_view"), 0)

    def test_job_view_beacon_counts_public_job(self):
        response = self.client.post(
            reverse("core:analytics_event"),
            data=json.dumps({"event": "job_view", "job_id": str(self.job.pk)}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.counter("job_view"), 1)

    def test_job_view_beacon_rejects_unknown_job(self):
        response = self.client.post(
            reverse("core:analytics_event"),
            data=json.dumps({"event": "job_view", "job_id": str(uuid.uuid4())}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.counter("job_view"), 0)

    def test_pwa_usage_events(self):
        for event in ("app_open", "app_return"):
            response = self.client.post(
                reverse("core:analytics_event"),
                data=json.dumps({"event": event}),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.counter("app_open"), 1)
        self.assertEqual(self.counter("app_return"), 1)

    def test_application_sent_counter(self):
        self.client.force_login(self.worker)
        response = self.client.post(reverse("core:job_apply", args=[self.job.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.counter("application_sent"), 1)

    def test_job_created_counter(self):
        self.client.force_login(self.employer)
        response = self.client.post(reverse("core:job_create"), {
            "work_type": "Аналитика",
            "organization_name": "Приход",
            "detailed_description": "Проверка счётчика",
            "city": "Москва",
            "payment_amount": "1000",
            "max_workers": "1",
            "preferred_religion": "не важно",
            "date_time": (timezone.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.counter("job_created"), 1)

    def test_install_endpoint(self):
        response = self.client.post(
            reverse("core:analytics_event"),
            data=json.dumps({"event": "install"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.counter("install"), 1)

    def test_install_endpoint_rejects_unknown_event(self):
        response = self.client.post(
            reverse("core:analytics_event"),
            data=json.dumps({"event": "password"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.counter("install"), 0)

    def test_dashboard_requires_staff(self):
        self.client.force_login(self.worker)
        response = self.client.get("/admin/analytics/")
        self.assertEqual(response.status_code, 302)
        staff = make_profile(
            "analytics-staff@example.com", role="admin",
        )
        self.client.force_login(staff)
        response = self.client.get("/admin/analytics/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Воронка")

    def test_dashboard_shows_totals(self):
        staff = make_profile(
            "analytics-staff2@example.com", role="admin",
        )
        analytics.incr("job_view", 5)
        analytics.incr("application_sent", 2)
        analytics.incr("app_open", 3)
        analytics.incr("app_return", 1)
        self.client.force_login(staff)
        response = self.client.get("/admin/analytics/")
        self.assertContains(response, "Просмотры заданий")
        self.assertContains(response, "<strong>5</strong>", html=False)
        self.assertContains(response, "40,0%")
        self.assertContains(response, "Повторные открытия PWA")
        self.assertContains(response, "25,0%")
