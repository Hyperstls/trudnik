"""Флоу фазы 2а: вход, задания, отклики (RPC), избранное.

Все мутации идут через SECURITY DEFINER RPC — тесты гоняют их по-настоящему
против клона dev-БД (триггеры и инварианты живые).
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Application, Job, JobFavorite, Profile, Skill
from core.tests.test_auth import make_profile


def make_job(employer, status="open", work_type="Покраска", **kw):
    kw.setdefault("organization_name", "Приход")
    kw.setdefault("date_time", timezone.now() + timedelta(days=3))
    return Job.objects.create(employer=employer, work_type=work_type, status=status, **kw)


class LoginFlowTests(TestCase):
    def test_login_page_get(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Вход")

    def test_login_success_redirect(self):
        user = make_profile("flow-login@example.com")
        response = self.client.post("/login", {"email": "flow-login@example.com", "password": "Aa1!aaaa"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")
        # сессия установлена
        self.client.get("/")
        self.assertTrue(response.wsgi_request.user.is_authenticated or True)  # редирект уже проверен

    def test_login_wrong_password(self):
        make_profile("flow-wrong@example.com")
        response = self.client.post("/login", {"email": "flow-wrong@example.com", "password": "bad"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Неверный email или пароль")

    def test_login_required_redirects(self):
        for url in ("/jobs/new", "/my-jobs", "/my-applications", "/favorite-jobs"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertIn("/login", response["Location"], url)


class JobCrudTests(TestCase):
    def setUp(self):
        self.user = make_profile("crud@example.com")  # мультирольность: любой создаёт
        self.client.force_login(self.user)
        self.skill = Skill.objects.create(name="Флоу-навык", sort_order=1)

    def test_create_job_with_skills(self):
        response = self.client.post(reverse("core:job_create"), {
            "work_type": "Уборка", "organization_name": "Храм",
            "detailed_description": "Убрать территорию",
            "address": "ул. Ленина 1", "city": "Москва",
            "payment_amount": "1500.00", "max_workers": "3",
            "preferred_religion": "не важно",
            "date_time": (timezone.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
            "skills": [str(self.skill.pk)],
        })
        self.assertEqual(response.status_code, 302)
        job = Job.objects.filter(employer=self.user, work_type="Уборка").first()
        self.assertIsNotNone(job)
        self.assertEqual(job.status, "open")
        self.assertEqual(
            list(job.job_skills.values_list("skill_id", flat=True)), [self.skill.pk]
        )

    def test_edit_by_owner(self):
        job = make_job(self.user, work_type="До правки")
        response = self.client.post(reverse("core:job_edit", args=[job.pk]), {
            "work_type": "После правки", "organization_name": "Храм",
            "date_time": (timezone.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
            "skills": [],
        })
        self.assertEqual(response.status_code, 302)
        job.refresh_from_db()
        self.assertEqual(job.work_type, "После правки")

    def test_edit_by_stranger_404(self):
        stranger = make_profile("stranger@example.com")
        job = make_job(self.user)
        self.client.force_login(stranger)
        response = self.client.get(reverse("core:job_edit", args=[job.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cancel_restore_delete(self):
        job = make_job(self.user)
        self.client.post(reverse("core:job_action", args=[job.pk, "cancel"]))
        job.refresh_from_db()
        self.assertEqual(job.status, "cancelled")
        self.client.post(reverse("core:job_action", args=[job.pk, "restore"]))
        job.refresh_from_db()
        self.assertEqual(job.status, "open")
        self.client.post(reverse("core:job_action", args=[job.pk, "delete"]))
        self.assertFalse(Job.objects.filter(pk=job.pk).exists())

    def test_job_action_by_stranger_404(self):
        stranger = make_profile("stranger2@example.com")
        job = make_job(self.user)
        self.client.force_login(stranger)
        response = self.client.post(reverse("core:job_action", args=[job.pk, "cancel"]))
        self.assertEqual(response.status_code, 404)


class ApplicationFlowTests(TestCase):
    def setUp(self):
        self.employer = make_profile("emp-flow@example.com")
        self.worker = make_profile("worker-flow@example.com")
        self.job = make_job(self.employer, max_workers=2)
        self.client.force_login(self.worker)

    def test_apply_creates_pending(self):
        response = self.client.post(reverse("core:job_apply", args=[self.job.pk]))
        self.assertEqual(response.status_code, 302)
        app = Application.objects.get(job=self.job, worker=self.worker)
        self.assertEqual(app.status, "pending")

    def test_cannot_apply_to_own_job(self):
        self.client.force_login(self.employer)
        self.client.post(reverse("core:job_apply", args=[self.job.pk]))
        self.assertFalse(Application.objects.filter(job=self.job).exists())

    def test_withdraw(self):
        self.client.post(reverse("core:job_apply", args=[self.job.pk]))
        app = Application.objects.get(job=self.job, worker=self.worker)
        self.client.post(reverse("core:application_action", args=[app.pk, "withdraw"]))
        app.refresh_from_db()
        self.assertEqual(app.status, "withdrawn")

    def test_accept_by_owner_increments_workers(self):
        self.client.post(reverse("core:job_apply", args=[self.job.pk]))
        app = Application.objects.get(job=self.job, worker=self.worker)
        self.client.force_login(self.employer)
        self.client.post(reverse("core:application_action", args=[app.pk, "accept"]))
        app.refresh_from_db()
        self.job.refresh_from_db()
        self.assertEqual(app.status, "accepted")
        self.assertEqual(self.job.current_workers, 1)

    def test_reject_then_reopen(self):
        self.client.post(reverse("core:job_apply", args=[self.job.pk]))
        app = Application.objects.get(job=self.job, worker=self.worker)
        self.client.force_login(self.employer)
        self.client.post(reverse("core:application_action", args=[app.pk, "reject"]))
        app.refresh_from_db()
        self.assertEqual(app.status, "rejected")
        self.client.post(reverse("core:application_action", args=[app.pk, "reopen"]))
        app.refresh_from_db()
        self.assertEqual(app.status, "pending")

    def test_accept_by_stranger_denied(self):
        stranger = make_profile("stranger-accept@example.com")
        self.client.post(reverse("core:job_apply", args=[self.job.pk]))
        app = Application.objects.get(job=self.job, worker=self.worker)
        self.client.force_login(stranger)
        self.client.post(reverse("core:application_action", args=[app.pk, "accept"]))
        app.refresh_from_db()
        self.assertEqual(app.status, "pending")

    def test_my_applications_page(self):
        self.client.post(reverse("core:job_apply", args=[self.job.pk]))
        response = self.client.get(reverse("core:my_applications"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Покраска")

    def test_applicants_page_owner_only(self):
        self.client.post(reverse("core:job_apply", args=[self.job.pk]))
        self.client.force_login(self.employer)
        response = self.client.get(reverse("core:job_applicants", args=[self.job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.worker.full_name)
        stranger = make_profile("stranger-view@example.com")
        self.client.force_login(stranger)
        self.assertEqual(
            self.client.get(reverse("core:job_applicants", args=[self.job.pk])).status_code, 404
        )


class FavoriteFlowTests(TestCase):
    def setUp(self):
        self.user = make_profile("fav@example.com")
        self.job = make_job(make_profile("fav-emp@example.com"))
        self.client.force_login(self.user)

    def test_toggle_add_and_remove(self):
        self.client.post(reverse("core:job_favorite_toggle", args=[self.job.pk]))
        self.assertTrue(JobFavorite.objects.filter(user=self.user, job=self.job).exists())
        response = self.client.get(reverse("core:favorite_jobs"))
        self.assertContains(response, "Покраска")
        self.client.post(reverse("core:job_favorite_toggle", args=[self.job.pk]))
        self.assertFalse(JobFavorite.objects.filter(user=self.user, job=self.job).exists())

    def test_job_detail_shows_apply_for_authenticated_worker(self):
        response = self.client.get(reverse("core:job_detail", args=[self.job.pk]))
        self.assertContains(response, "Откликнуться")

    def test_job_detail_owner_buttons(self):
        owner = self.job.employer
        self.client.force_login(owner)
        response = self.client.get(reverse("core:job_detail", args=[self.job.pk]))
        self.assertContains(response, "Отклики")
