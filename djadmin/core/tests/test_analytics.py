"""First-party aggregate funnel counters (J123/J134)."""
import json
import uuid
from datetime import date, datetime, timedelta

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
        self.assertEqual(analytics.job_view_total(self.job.pk), 1)

    def test_anonymous_beacon_counts_per_job(self):
        self.client.post(
            reverse("core:analytics_event"),
            data=json.dumps({"event": "job_view", "job_id": str(self.job.pk)}),
            content_type="application/json",
        )
        self.assertEqual(analytics.job_view_total(self.job.pk), 1)

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


class _RegisterFormStub:
    """Минимальная замена RegisterForm для проверки сохранения меток."""

    cleaned_data = {}

    def __init__(self, data=None):
        pass

    def is_valid(self):
        return True

    def add_error(self, field, message):
        raise AssertionError("unexpected form error: %s" % message)

    def role_and_visibility(self):
        return "worker", True


@override_settings(CACHES=CACHE_LOCMEM)
class GrowthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.today = timezone.localdate()

    def _activity_days(self, user_id):
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT day FROM user_activity WHERE user_id = %s ORDER BY day",
                [str(user_id)],
            )
            return [row[0] for row in cursor.fetchall()]

    def test_first_touch_utm_kept_in_session(self):
        url = reverse("core:register")
        self.client.get(
            url + "?utm_source=habr&utm_medium=cpc&utm_campaign=launch&utm_content=banner"
        )
        attribution = self.client.session["attribution"]
        self.assertEqual(attribution["source"], "habr")
        self.assertEqual(attribution["medium"], "cpc")
        self.assertEqual(attribution["campaign"], "launch")
        self.assertEqual(attribution["content"], "banner")
        self.assertEqual(attribution["landing"], "/register")

        # Повторный заход с другой меткой не перезаписывает first-touch.
        self.client.get(url + "?utm_source=vc")
        self.assertEqual(self.client.session["attribution"]["source"], "habr")

    def test_attribution_ignored_without_source_or_campaign(self):
        self.client.get(reverse("core:register") + "?utm_medium=cpc")
        self.assertNotIn("attribution", self.client.session)

    def test_registration_saves_attribution(self):
        from unittest.mock import patch

        profile = make_profile("utm-reg@example.com")
        self.client.get(reverse("core:register") + "?utm_source=habr&utm_campaign=launch")
        stub = _RegisterFormStub()
        stub.cleaned_data = {
            "email": "utm-reg@example.com",
            "password": "Aa1!aaaa",  # pragma: allowlist secret
            "full_name": "Иван Меточный",
            "city": "Москва",
            "portfolio_link": "",
            "contact": "",
            "experience": "",
            "desired_payment": None,
            "inn": "",
            "is_self_employed": False,
            "skills": [],
        }
        with patch("core.views_auth.RegisterForm", return_value=stub), \
                patch("core.views_auth.call_rpc", return_value={"register_user": str(profile.pk)}), \
                patch("core.views_auth.verify_captcha_token", return_value=True), \
                patch("core.views_auth.sync_user_skills_raw"), \
                patch("core.views_auth._send_mail"):
            response = self.client.post(reverse("core:register"), data={})
        self.assertEqual(response.status_code, 302)
        profile.refresh_from_db()
        self.assertEqual(profile.acquisition["source"], "habr")
        self.assertEqual(profile.acquisition["campaign"], "launch")
        self.assertNotIn("attribution", self.client.session)

    def test_activity_middleware_records_one_row_per_day(self):
        worker = make_profile("activity@example.com")
        self.client.force_login(worker)
        self.client.get(reverse("core:jobs"))
        self.client.get(reverse("core:jobs"))
        self.assertEqual(self._activity_days(worker.pk), [self.today])

    def test_retention_matrix_counts_cohort_weeks(self):
        from core.growth import _month_start, record_activity, retention_matrix

        # Месяц без реальных пользователей в клоне dev-БД: когорта изолирована.
        cohort_start = _month_start(self.today, -12) + timedelta(days=2)
        first = make_profile("cohort-1@example.com")
        second = make_profile("cohort-2@example.com")
        from core.models import Profile

        Profile.objects.filter(pk__in=[first.pk, second.pk]).update(
            created_at=timezone.make_aware(
                datetime.combine(cohort_start, datetime.min.time())
            )
        )
        record_activity(first.pk, cohort_start)
        record_activity(first.pk, cohort_start + timedelta(days=14))
        record_activity(second.pk, cohort_start)

        matrix = retention_matrix(months=13, weeks=4)
        row = next(item for item in matrix if item["cohort"] == cohort_start.strftime("%Y-%m"))
        self.assertEqual(row["size"], 2)
        self.assertEqual(row["weeks"][0]["pct"], 100)
        self.assertEqual(row["weeks"][1]["pct"], 0)
        self.assertEqual(row["weeks"][2]["pct"], 50)

    def test_acquisition_breakdown_groups_and_activation(self):
        from core.growth import acquisition_breakdown

        employer = make_profile(
            "utm-emp@example.com", role="employer",
            acquisition={"source": "habr", "medium": "cpc", "campaign": "launch"},
        )
        make_profile(
            "utm-worker@example.com", role="worker",
            acquisition={"source": "habr", "medium": "cpc", "campaign": "launch"},
        )
        make_job(employer)

        row = next(item for item in acquisition_breakdown() if item["source"] == "habr")
        self.assertEqual(row["users"], 2)
        self.assertEqual(row["activated"], 1)
        self.assertEqual(row["pct"], 50)

    def test_activity_summary_counts_active_user(self):
        from core.growth import activity_summary, record_activity

        worker = make_profile("summary@example.com")
        record_activity(worker.pk)
        summary = activity_summary()
        self.assertGreaterEqual(summary["dau"], 1)
        self.assertGreaterEqual(summary["wau"], 1)
        self.assertGreaterEqual(summary["total_users"], 1)

    def test_dashboard_shows_growth_sections(self):
        from core import analytics as analytics_module

        staff = make_profile("growth-staff@example.com", role="admin")
        analytics_module.incr("job_view", 1)
        self.client.force_login(staff)
        response = self.client.get("/admin/analytics/")
        self.assertContains(response, "Удержание по когортам")
        self.assertContains(response, "Источники регистраций")
        self.assertContains(response, "Активность и база")
