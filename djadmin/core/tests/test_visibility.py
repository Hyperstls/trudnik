"""RLS-паритет видимости (спека §1.3): публичные queryset'ы обязаны фильтровать
так же, как политики RLS для anon/authenticated в PostgREST.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import Job, Profile
from core.tests.test_auth import make_profile

HIDDEN = ("draft", "active", "in_progress", "paid", "expired")


class JobVisibilityTests(TestCase):
    def setUp(self):
        self.employer = make_profile("emp@example.com", role="employer")

    def _job(self, status):
        return Job.objects.create(
            employer=self.employer,
            work_type="Покраска забора",
            organization_name="Храм Николая",
            status=status,
            date_time=timezone.now() + timedelta(days=1),
        )

    def test_public_shows_only_open_completed_cancelled(self):
        for s in ("open", "completed", "cancelled"):
            self._job(s)
        for s in HIDDEN:
            self._job(s)
        got = set(Job.objects.public().values_list("status", flat=True))
        self.assertEqual(got, {"open", "completed", "cancelled"})

    def test_hidden_statuses_404_on_detail(self):
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        from core import views

        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        for status in HIDDEN:
            with self.assertRaises(Exception) as ctx:
                views.job_detail(request, self._job(status).pk)
            self.assertIn("404", type(ctx.exception).__name__, status)


class ProfileVisibilityTests(TestCase):
    def test_workers_catalog(self):
        visible = make_profile("w1@example.com", role="worker", worker_visibility=True)
        hidden = make_profile("w2@example.com", role="worker", worker_visibility=False)
        admin = Profile.objects.create_superuser("admin2@example.com", "Aa1!aaaa")

        got = set(Profile.objects.public_workers().values_list("id", flat=True))
        self.assertIn(visible.id, got)
        self.assertNotIn(hidden.id, got)
        self.assertNotIn(admin.id, got)

    def test_public_visible_excludes_admins(self):
        # тест-БД — клон dev: сравниваем только среди созданных в тесте id
        worker = make_profile("w3@example.com", role="worker")
        employer = make_profile("e3@example.com", role="employer")
        admin = Profile.objects.create_superuser("admin3@example.com", "Aa1!aaaa")
        ids = [worker.id, employer.id, admin.id]
        got = set(Profile.objects.public_visible().filter(id__in=ids).values_list("id", flat=True))
        self.assertEqual(got, {worker.id, employer.id})
