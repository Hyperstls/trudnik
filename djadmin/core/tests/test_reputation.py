"""R021: время ответа работодателя (applications.responded_at).

Триггер 161 ставит метку при переходе в accepted/rejected, сбрасывает при
возврате в pending и не трогает её при прочих обновлениях. Метрики считаются
только по разрешённым откликам за 90 дней и только при >= 3 ответах.
"""
from datetime import timedelta

from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from core.models import Application, Profile
from core.reputation import _human_duration, employer_response_metrics, profile_metrics
from core.tests.test_auth import make_profile
from core.tests.test_flows import make_job


def set_status(application, status):
    """UPDATE со status в SET-списке — единственный путь, где срабатывает триггер."""
    Application.objects.filter(pk=application.pk).update(status=status)


def responded_at_of(application):
    return Application.objects.filter(pk=application.pk).values_list("responded_at", flat=True).get()


def make_application(employer, worker, status="accepted", created_at=None, responded_at=None):
    """Отклик с управляемыми метками: INSERT триггер не ловит, поэтому update."""
    job = make_job(employer, work_type="Ответ (%s)" % status, status="completed")
    application = Application.objects.create(job=job, worker=worker, status=status)
    if created_at is not None or responded_at is not None:
        Application.objects.filter(pk=application.pk).update(
            created_at=created_at or timezone.now(),
            responded_at=responded_at,
        )
    return application


class RespondedAtTriggerTests(TestCase):
    def setUp(self):
        self.employer = make_profile("responded-emp@example.com", role="employer")
        self.worker = make_profile("responded-worker@example.com")

    def _new_application(self, status="pending"):
        return make_application(self.employer, self.worker, status=status)

    def test_accepted_sets_responded_at(self):
        application = self._new_application()
        self.assertIsNone(responded_at_of(application))
        set_status(application, "accepted")
        self.assertIsNotNone(responded_at_of(application))

    def test_rejected_sets_responded_at(self):
        application = self._new_application()
        set_status(application, "rejected")
        self.assertIsNotNone(responded_at_of(application))

    def test_withdrawn_does_not_set_responded_at(self):
        application = self._new_application()
        set_status(application, "withdrawn")
        self.assertIsNone(responded_at_of(application))

    def test_same_status_update_keeps_responded_at(self):
        application = self._new_application()
        set_status(application, "accepted")
        first = responded_at_of(application)
        self.assertIsNotNone(first)

        set_status(application, "accepted")
        self.assertEqual(responded_at_of(application), first)

        Application.objects.filter(pk=application.pk).update(contact_paid=True)
        self.assertEqual(responded_at_of(application), first)

    def test_pending_resets_responded_at(self):
        application = self._new_application()
        set_status(application, "accepted")
        self.assertIsNotNone(responded_at_of(application))
        set_status(application, "pending")
        self.assertIsNone(responded_at_of(application))

    def test_backfill_fills_legacy_rows_and_keeps_existing(self):
        legacy = self._new_application(status="accepted")  # responded_at = NULL
        legacy_updated_at = (
            Application.objects.filter(pk=legacy.pk).values_list("updated_at", flat=True).get()
        )
        already = self._new_application()
        set_status(already, "accepted")
        existing = responded_at_of(already)
        pending = self._new_application()
        withdrawn = self._new_application()
        set_status(withdrawn, "withdrawn")

        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE public.applications SET responded_at = updated_at "
                "WHERE status IN ('accepted', 'rejected') AND responded_at IS NULL"
            )

        self.assertEqual(responded_at_of(legacy), legacy_updated_at)
        self.assertEqual(responded_at_of(already), existing)
        self.assertIsNone(responded_at_of(pending))
        self.assertIsNone(responded_at_of(withdrawn))


class EmployerResponseMetricsTests(TestCase):
    def setUp(self):
        self.employer = make_profile("metrics-emp@example.com", role="employer")
        self.worker = make_profile("metrics-worker@example.com")
        self.now = timezone.now()

    def _reply(self, minutes, status="accepted", age_days=1):
        responded_at = self.now - timedelta(days=age_days)
        created_at = responded_at - timedelta(minutes=minutes)
        return make_application(
            self.employer, self.worker,
            status=status, created_at=created_at, responded_at=responded_at,
        )

    def test_fewer_than_three_replies_returns_nothing(self):
        self._reply(10)
        self._reply(20)
        self.assertEqual(employer_response_metrics(self.employer.pk), {})

    def test_three_replies_avg_median_and_label(self):
        self._reply(10)
        self._reply(20)
        self._reply(90)
        metrics = employer_response_metrics(self.employer.pk)
        self.assertEqual(metrics["response_count"], 3)
        self.assertEqual(metrics["response_avg_minutes"], 40.0)
        self.assertEqual(metrics["response_median_minutes"], 20.0)
        self.assertEqual(metrics["response_avg_label"], "40 мин")

    def test_even_count_median_is_mean_of_middle_values(self):
        for minutes in (10, 20, 30, 100):
            self._reply(minutes)
        self.assertEqual(employer_response_metrics(self.employer.pk)["response_median_minutes"], 25.0)

    def test_withdrawn_and_cancelled_not_counted(self):
        self._reply(10)
        self._reply(20)
        self._reply(30, status="withdrawn")
        self._reply(40, status="cancelled")
        self.assertEqual(employer_response_metrics(self.employer.pk), {})

        self._reply(50)
        self.assertEqual(employer_response_metrics(self.employer.pk)["response_count"], 3)

    def test_negative_intervals_ignored(self):
        self._reply(10)
        self._reply(20)
        self._reply(-30)  # responded_at раньше created_at — игнорируется
        self.assertEqual(employer_response_metrics(self.employer.pk), {})

        self._reply(30)
        self.assertEqual(employer_response_metrics(self.employer.pk)["response_count"], 3)

    def test_replies_older_than_window_ignored(self):
        self._reply(10, age_days=1)
        self._reply(20, age_days=2)
        self._reply(30, age_days=100)
        self.assertEqual(employer_response_metrics(self.employer.pk), {})

    def test_label_switches_to_hours(self):
        for minutes in (60, 90, 120):
            self._reply(minutes)
        metrics = employer_response_metrics(self.employer.pk)
        self.assertEqual(metrics["response_avg_minutes"], 90.0)
        self.assertEqual(metrics["response_avg_label"], "1,5 ч")


class HumanDurationTests(SimpleTestCase):
    def test_labels(self):
        self.assertEqual(_human_duration(0), "0 мин")
        self.assertEqual(_human_duration(None), "0 мин")
        self.assertEqual(_human_duration(45), "45 мин")
        self.assertEqual(_human_duration(60), "1,0 ч")
        self.assertEqual(_human_duration(90), "1,5 ч")
        self.assertEqual(_human_duration(2880), "2 д")


class ProfileMetricsResponseTests(TestCase):
    def setUp(self):
        self.employer = make_profile("profile-metrics-emp@example.com", role="employer")
        self.worker = make_profile("profile-metrics-worker@example.com")
        self.now = timezone.now()

    def _reply(self, minutes):
        responded_at = self.now - timedelta(days=1)
        make_application(
            self.employer, self.worker,
            created_at=responded_at - timedelta(minutes=minutes),
            responded_at=responded_at,
        )

    def test_employer_metrics_include_response_fields_with_enough_data(self):
        for minutes in (10, 20, 30):
            self._reply(minutes)
        metrics = profile_metrics(self.employer.pk, Profile.Role.EMPLOYER)
        for key in ("response_count", "response_avg_minutes", "response_median_minutes", "response_avg_label"):
            self.assertIn(key, metrics)
        self.assertEqual(metrics["response_count"], 3)
        self.assertEqual(metrics["response_avg_minutes"], 20.0)

    def test_employer_metrics_have_no_response_keys_without_data(self):
        self._reply(10)
        metrics = profile_metrics(self.employer.pk, Profile.Role.EMPLOYER)
        for key in ("response_count", "response_avg_minutes", "response_median_minutes", "response_avg_label"):
            self.assertNotIn(key, metrics)

    def test_worker_metrics_have_no_response_keys(self):
        for minutes in (10, 20, 30):
            self._reply(minutes)
        metrics = profile_metrics(self.employer.pk, Profile.Role.WORKER)
        self.assertNotIn("response_count", metrics)
        self.assertNotIn("response_avg_label", metrics)
