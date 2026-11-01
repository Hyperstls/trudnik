"""Флоу фазы 2а: вход, задания, отклики (RPC), избранное.

Все мутации идут через SECURITY DEFINER RPC — тесты гоняют их по-настоящему
против клона dev-БД (триггеры и инварианты живые).
"""
from datetime import timedelta
import os

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.admin.jobs import JobAdmin
from core.forms import JobForm
from core.models import Application, Blacklist, Job, JobFavorite, JobPhoto, JobSkill, NotificationOutbox, Profile, Skill
from core.storage import resolve_upload_url, save_upload
from core.tests.test_auth import make_profile

TINY_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


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
        make_profile("flow-login@example.com")
        response = self.client.post("/login", {"email": "flow-login@example.com", "password": "Aa1!aaaa"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")

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

    def _job_payload(self, **overrides):
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

    def test_create_job_sets_expires_at(self):
        response = self.client.post(reverse("core:job_create"), self._job_payload())
        self.assertEqual(response.status_code, 302)
        job = Job.objects.get(employer=self.user)
        self.assertIsNotNone(job.expires_at)
        delta = job.expires_at - timezone.now()
        self.assertGreater(delta, timedelta(days=29))
        self.assertLess(delta, timedelta(days=31))

    def test_create_job_rejects_past_date(self):
        response = self.client.post(reverse("core:job_create"), self._job_payload(
            date_time=(timezone.now() - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
        ))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Job.objects.filter(employer=self.user).exists())
        self.assertContains(response, "Дата выполнения не может быть в прошлом")
        self.assertIn("date_time", response.context["form"].errors)

    def test_create_job_rejects_stop_words(self):
        cases = (
            {"organization_name": "Оплата как зарплата"},
            {"detailed_description": "Работа в штат, постоянная работа"},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                response = self.client.post(reverse("core:job_create"), self._job_payload(**overrides))
                self.assertEqual(response.status_code, 200)
                self.assertFalse(Job.objects.filter(employer=self.user).exists())
                self.assertContains(response, "Обнаружены слова, характерные для трудовых отношений")
                self.assertIn("detailed_description", response.context["form"].errors)

    def test_create_job_rejects_payment_out_of_range(self):
        for amount in ("-1.00", "1000000.01"):
            with self.subTest(amount=amount):
                response = self.client.post(
                    reverse("core:job_create"), self._job_payload(payment_amount=amount)
                )
                self.assertEqual(response.status_code, 200)
                self.assertFalse(Job.objects.filter(employer=self.user).exists())
                self.assertContains(response, "Оплата должна быть от 0 до 1 000 000")
                self.assertIn("payment_amount", response.context["form"].errors)

    def test_create_job_rejects_max_workers(self):
        for workers in ("0", "101"):
            with self.subTest(workers=workers):
                response = self.client.post(
                    reverse("core:job_create"), self._job_payload(max_workers=workers)
                )
                self.assertEqual(response.status_code, 200)
                self.assertFalse(Job.objects.filter(employer=self.user).exists())
                self.assertContains(response, "Количество работников должно быть от 1 до 100")
                self.assertIn("max_workers", response.context["form"].errors)

    def test_create_job_rejects_too_long_name(self):
        response = self.client.post(
            reverse("core:job_create"),
            self._job_payload(organization_name="А" * 256),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Job.objects.filter(employer=self.user).exists())
        self.assertContains(response, "Название слишком длинное")
        self.assertIn("organization_name", response.context["form"].errors)

    def test_create_job_rejects_too_long_description(self):
        response = self.client.post(
            reverse("core:job_create"),
            self._job_payload(detailed_description="Б" * 5001),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Job.objects.filter(employer=self.user).exists())
        self.assertContains(response, "Описание слишком длинное")
        self.assertIn("detailed_description", response.context["form"].errors)

    def test_create_job_accepts_max_lengths(self):
        response = self.client.post(
            reverse("core:job_create"),
            self._job_payload(
                organization_name="А" * 255,
                detailed_description="Б" * 5000,
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Job.objects.filter(employer=self.user, work_type="Уборка").exists()
        )

    def test_create_job_saves_coordinates(self):
        response = self.client.post(
            reverse("core:job_create"),
            self._job_payload(lat="55.75", lng="37.61"),
        )
        self.assertEqual(response.status_code, 302)
        job = Job.objects.get(employer=self.user, work_type="Уборка")
        self.assertAlmostEqual(job.lat, 55.75)
        self.assertAlmostEqual(job.lng, 37.61)

    def test_create_job_rejects_invalid_coordinates(self):
        cases = ({"lat": "999", "lng": "37.61"}, {"lat": "55.75", "lng": "181"})
        for overrides in cases:
            with self.subTest(overrides=overrides):
                response = self.client.post(
                    reverse("core:job_create"), self._job_payload(**overrides)
                )
                self.assertEqual(response.status_code, 200)
                self.assertFalse(Job.objects.filter(employer=self.user).exists())
                self.assertIn(
                    "lat" if "lat" in overrides and overrides["lat"] == "999" else "lng",
                    response.context["form"].errors,
                )

    def test_job_form_renders_map_with_key(self):
        from unittest.mock import patch

        with patch.dict(os.environ, {"YANDEX_MAPS_API_KEY": "test-" + "key"}):  # pragma: allowlist secret
            response = self.client.get(reverse("core:job_create"))
        self.assertContains(response, 'id="job-map"')
        self.assertContains(response, "api-maps.yandex.ru")
        self.assertContains(response, 'id="id_lat"')
        self.assertContains(response, 'id="id_lng"')

    def test_job_form_without_key_has_no_map(self):
        from unittest.mock import patch

        with patch.dict(os.environ, {"YANDEX_MAPS_API_KEY": ""}):
            response = self.client.get(reverse("core:job_create"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="job-map"')
        self.assertContains(response, 'id="id_lat"')

    def test_job_edit_form_prefills_map_coordinates(self):
        from unittest.mock import patch

        job = make_job(self.user, lat=55.75, lng=37.61)
        with patch.dict(os.environ, {"YANDEX_MAPS_API_KEY": "test-" + "key"}):  # pragma: allowlist secret
            response = self.client.get(reverse("core:job_edit", args=[job.pk]))
        self.assertContains(response, 'data-lat="55.75"')
        self.assertContains(response, 'data-lng="37.61"')

    def test_preferred_religion_not_in_form_or_admin(self):
        self.assertNotIn("preferred_religion", JobForm().fields)
        admin_fields = []
        for _, options in JobAdmin.fieldsets:
            admin_fields.extend(options.get("fields", ()))
        self.assertNotIn("preferred_religion", admin_fields)
        response = self.client.get(reverse("core:job_create"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="preferred_religion"')

    def test_create_job_ignores_preferred_religion(self):
        response = self.client.post(reverse("core:job_create"), {
            "work_type": "Погрузка", "organization_name": "Храм",
            "detailed_description": "Разгрузить коробки",
            "address": "ул. Мира 2", "city": "Москва",
            "payment_amount": "1000.00", "max_workers": "2",
            "preferred_religion": "ислам",
            "date_time": (timezone.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
            "skills": [],
        })
        self.assertEqual(response.status_code, 302)
        job = Job.objects.filter(employer=self.user, work_type="Погрузка").first()
        self.assertIsNotNone(job)
        self.assertNotEqual(job.preferred_religion, "ислам")
        self.assertEqual(job.preferred_religion, "не важно")

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

    def test_edit_job_refreshes_expires_at(self):
        job = make_job(self.user, expires_at=timezone.now() - timedelta(days=1))
        response = self.client.post(reverse("core:job_edit", args=[job.pk]), {
            "work_type": "После правки", "organization_name": "Храм",
            "date_time": (timezone.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
            "skills": [],
        })
        self.assertEqual(response.status_code, 302)
        job.refresh_from_db()
        delta = job.expires_at - timezone.now()
        self.assertGreater(delta, timedelta(days=29))
        self.assertLess(delta, timedelta(days=31))

    def test_edit_locked_when_accepted_application(self):
        job = make_job(self.user, payment_amount=1000)
        worker = make_profile("edit-accepted-worker@example.com", role="worker")
        Application.objects.create(job=job, worker=worker, status="accepted")
        response = self.client.get(reverse("core:job_edit", args=[job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "есть принятые отклики")
        self.assertContains(response, 'name="detailed_description"')
        for locked in ("payment_amount", "work_type", "date_time", "skills", "lat", "lng"):
            self.assertNotContains(response, 'name="%s"' % locked)

    def test_edit_locked_rejects_locked_fields(self):
        job = make_job(self.user, payment_amount=1000, work_type="До блокировки")
        worker = make_profile("edit-locked-worker@example.com", role="worker")
        Application.objects.create(job=job, worker=worker, status="accepted")
        response = self.client.post(reverse("core:job_edit", args=[job.pk]), {
            "detailed_description": "Попытка изменить всё",
            "payment_amount": "99999",
            "work_type": "Взлом",
        })
        self.assertRedirects(
            response, reverse("core:job_detail", args=[job.pk])
        )
        job.refresh_from_db()
        self.assertEqual(job.payment_amount, 1000)
        self.assertEqual(job.work_type, "До блокировки")
        self.assertNotEqual(job.detailed_description, "Попытка изменить всё")

    def test_edit_locked_allows_description_only(self):
        job = make_job(self.user, payment_amount=1000, work_type="До описания")
        worker = make_profile("edit-desc-worker@example.com", role="worker")
        Application.objects.create(job=job, worker=worker, status="accepted")
        expires_before = job.expires_at
        response = self.client.post(reverse("core:job_edit", args=[job.pk]), {
            "detailed_description": "Только описание работы",
        })
        self.assertRedirects(
            response, reverse("core:job_detail", args=[job.pk])
        )
        job.refresh_from_db()
        self.assertEqual(job.detailed_description, "Только описание работы")
        self.assertEqual(job.payment_amount, 1000)
        self.assertEqual(job.work_type, "До описания")
        self.assertEqual(job.expires_at, expires_before)

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

    def test_delete_job_removes_photo_files(self):
        url = save_upload(
            SimpleUploadedFile("p.png", TINY_PNG, content_type="image/png"), "jobs"
        )
        job = make_job(self.user, work_type="С фото")
        job.photo_urls = [url]
        job.save(update_fields=["photo_urls"])
        JobPhoto.objects.create(job=job, photo_url=url, order_num=0)
        self.client.post(reverse("core:job_action", args=[job.pk, "delete"]))
        self.assertFalse(Job.objects.filter(pk=job.pk).exists())
        self.assertIsNone(resolve_upload_url(url[len("/uploads/"):]))

    def test_delete_job_keeps_shared_photo(self):
        url = save_upload(
            SimpleUploadedFile("p.png", TINY_PNG, content_type="image/png"), "jobs"
        )
        job = make_job(self.user, work_type="Оригинал")
        copy = make_job(self.user, work_type="Копия")
        JobPhoto.objects.create(job=job, photo_url=url, order_num=0)
        JobPhoto.objects.create(job=copy, photo_url=url, order_num=0)
        self.client.post(reverse("core:job_action", args=[job.pk, "delete"]))
        self.assertIsNotNone(resolve_upload_url(url[len("/uploads/"):]))


class WithdrawWindowTests(TestCase):
    """Окно отзыва: принятый отклик блокируется за 12 часов до начала (Flask parity)."""

    def setUp(self):
        self.employer = make_profile("window-emp@example.com")
        self.worker = make_profile("window-worker@example.com")
        self.client.force_login(self.worker)

    def _job_with_app(self, hours, status):
        job = make_job(
            self.employer, date_time=timezone.now() + timedelta(hours=hours),
        )
        Application.objects.create(job=job, worker=self.worker, status=status)
        return job

    def test_accepted_inside_12h_disables_withdraw(self):
        job = self._job_with_app(6, "accepted")
        response = self.client.get(reverse("core:job_detail", args=[job.pk]))
        self.assertContains(response, "disabled")
        self.assertContains(response, "Отзыв недоступен")

    def test_accepted_outside_12h_keeps_withdraw_enabled(self):
        job = self._job_with_app(24, "accepted")
        response = self.client.get(reverse("core:job_detail", args=[job.pk]))
        self.assertNotContains(response, "Отзыв недоступен")
        self.assertNotContains(response, "disabled")

    def test_pending_inside_12h_not_blocked(self):
        job = self._job_with_app(6, "pending")
        response = self.client.get(reverse("core:job_detail", args=[job.pk]))
        self.assertNotContains(response, "Отзыв недоступен")


class RpcContractTests(TestCase):
    """call_rpc: jsonb-объект разворачивается, boolean — прямой результат."""

    def test_jsonb_rpc_unwrapped(self):
        from uuid import uuid4

        from core.rpc import call_rpc

        result = call_rpc("apply_job_atomic", uuid4(), uuid4())
        self.assertIsInstance(result, dict)
        self.assertEqual(result["code"], "job_not_found")
        self.assertNotIn("apply_job_atomic", result)

    def test_boolean_rpc_unwrapped(self):
        from uuid import uuid4

        from core.rpc import call_rpc

        self.assertIs(call_rpc("change_password", uuid4(), "old", "new"), False)


class CatalogVisibilityTests(TestCase):
    """JOB-P1-06: лента не показывает cancelled и задания заблокировавших."""

    def setUp(self):
        self.employer = make_profile("catalog-emp@example.com", role="employer")
        self.worker = make_profile("catalog-worker@example.com", role="worker")
        self.job = make_job(self.employer, work_type="Уборка территории")

    def test_cancelled_hidden_by_default(self):
        make_job(self.employer, status="cancelled", work_type="Отменённая уборка")
        self.assertNotContains(self.client.get("/jobs"), "Отменённая уборка")
        self.assertNotContains(self.client.get("/jobs?status=cancelled"), "Отменённая уборка")

    def test_blacklisted_employer_hidden(self):
        other = make_profile("catalog-other@example.com", role="employer")
        visible = make_job(other, work_type="Видимая уборка")
        Blacklist.objects.create(user=self.employer, blocked_user=self.worker)
        self.client.force_login(self.worker)
        response = self.client.get("/jobs")
        self.assertNotContains(response, "Уборка территории")
        self.assertContains(response, visible.work_type)


class RepostJobTests(TestCase):
    def setUp(self):
        self.employer = make_profile("repost-emp@example.com", role="employer")
        self.job = make_job(self.employer, work_type="Репost")
        self.job.photo_urls = ["/uploads/a.jpg", "/uploads/b.jpg"]
        self.job.save(update_fields=["photo_urls"])
        JobPhoto.objects.create(job=self.job, photo_url="/uploads/a.jpg", order_num=0)
        JobPhoto.objects.create(job=self.job, photo_url="/uploads/b.jpg", order_num=1)
        self.client.force_login(self.employer)

    def test_repost_copies_photos_and_expiry(self):
        response = self.client.post(reverse("core:repost_job", args=[self.job.pk]))
        self.assertEqual(response.status_code, 302)
        new_job = Job.objects.exclude(pk=self.job.pk).get(employer=self.employer)
        delta = new_job.expires_at - timezone.now()
        self.assertGreater(delta, timedelta(days=29))
        self.assertLess(delta, timedelta(days=31))
        self.assertEqual(new_job.photo_urls, self.job.photo_urls)
        self.assertEqual(
            list(new_job.photos.order_by("order_num").values_list("photo_url", flat=True)),
            ["/uploads/a.jpg", "/uploads/b.jpg"],
        )


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

    def test_apply_enqueues_notification(self):
        self.client.post(reverse("core:job_apply", args=[self.job.pk]))
        row = NotificationOutbox.objects.get(
            user=self.employer, type="application_received"
        )
        self.assertEqual(row.status, "pending")
        self.assertEqual(row.data["job_id"], str(self.job.pk))

    def test_failed_apply_no_notification(self):
        self.client.force_login(self.employer)
        self.client.post(reverse("core:job_apply", args=[self.job.pk]))
        self.assertFalse(
            NotificationOutbox.objects.filter(
                user=self.employer, type="application_received"
            ).exists()
        )

    def test_enqueue_failure_does_not_break_apply(self):
        from unittest import mock

        with mock.patch(
            "core.notifications.NotificationOutbox.objects.create",
            side_effect=RuntimeError("outbox down"),
        ):
            response = self.client.post(reverse("core:job_apply", args=[self.job.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Application.objects.filter(job=self.job, worker=self.worker).exists()
        )
        self.assertFalse(
            NotificationOutbox.objects.filter(
                user=self.employer, type="application_received"
            ).exists()
        )

    def test_cannot_apply_to_own_job(self):
        self.client.force_login(self.employer)
        self.client.post(reverse("core:job_apply", args=[self.job.pk]))
        self.assertFalse(Application.objects.filter(job=self.job).exists())

    def test_apply_blacklisted_shows_message(self):
        Blacklist.objects.create(user=self.employer, blocked_user=self.worker)
        response = self.client.post(
            reverse("core:job_apply", args=[self.job.pk]), follow=True
        )
        self.assertContains(response, "ограничил приём откликов")
        self.assertFalse(
            Application.objects.filter(job=self.job, worker=self.worker).exists()
        )

    def test_apply_duplicate_shows_message(self):
        self.client.post(reverse("core:job_apply", args=[self.job.pk]))
        response = self.client.post(
            reverse("core:job_apply", args=[self.job.pk]), follow=True
        )
        self.assertContains(response, "Вы уже откликнулись на это задание")

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

    def test_accept_enqueues_notification(self):
        self.client.post(reverse("core:job_apply", args=[self.job.pk]))
        app = Application.objects.get(job=self.job, worker=self.worker)
        self.client.force_login(self.employer)
        self.client.post(reverse("core:application_action", args=[app.pk, "accept"]))
        row = NotificationOutbox.objects.get(
            user=self.worker, type="application_accepted"
        )
        self.assertEqual(row.status, "pending")

    def test_reject_enqueues_notification(self):
        self.client.post(reverse("core:job_apply", args=[self.job.pk]))
        app = Application.objects.get(job=self.job, worker=self.worker)
        self.client.force_login(self.employer)
        self.client.post(reverse("core:application_action", args=[app.pk, "reject"]))
        row = NotificationOutbox.objects.get(
            user=self.worker, type="application_rejected"
        )
        self.assertEqual(row.status, "pending")

    def test_applicants_reopen_label(self):
        self.client.post(reverse("core:job_apply", args=[self.job.pk]))
        app = Application.objects.get(job=self.job, worker=self.worker)
        self.client.force_login(self.employer)
        self.client.post(reverse("core:application_action", args=[app.pk, "reject"]))
        app.refresh_from_db()
        self.assertEqual(app.status, "rejected")
        response = self.client.get(reverse("core:job_applicants", args=[self.job.pk]))
        self.assertContains(response, "Принять повторно", count=1)
        self.assertContains(
            response, reverse("core:application_action", args=[app.pk, "reopen"])
        )

    def test_reopen_accepts_rejected(self):
        self.client.post(reverse("core:job_apply", args=[self.job.pk]))
        app = Application.objects.get(job=self.job, worker=self.worker)
        self.client.force_login(self.employer)
        self.client.post(reverse("core:application_action", args=[app.pk, "reject"]))
        app.refresh_from_db()
        self.assertEqual(app.status, "rejected")

        self.client.post(reverse("core:application_action", args=[app.pk, "reopen"]))
        app.refresh_from_db()
        self.job.refresh_from_db()
        self.assertEqual(app.status, "accepted")
        self.assertEqual(self.job.current_workers, 1)
        self.assertTrue(
            NotificationOutbox.objects.filter(
                user=self.worker, type="application_accepted"
            ).exists()
        )

        # Повторный reopen уже принятого — RPC bad_status, счётчик не растёт.
        self.client.post(reverse("core:application_action", args=[app.pk, "reopen"]))
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
        self.job.refresh_from_db()
        self.assertEqual(app.status, "accepted")
        self.assertEqual(self.job.current_workers, 1)

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


class MyJobsTests(TestCase):
    def setUp(self):
        self.employer = make_profile("myjobs-emp@example.com", role="employer")
        self.worker = make_profile("myjobs-worker@example.com", role="worker")
        self.open_job = make_job(self.employer, work_type="Открытое")
        self.completed_job = make_job(
            self.employer, status="completed", work_type="Завершённое"
        )
        self.cancelled_job = make_job(
            self.employer, status="cancelled", work_type="Отменённое"
        )
        Application.objects.create(
            job=self.open_job, worker=self.worker, status="pending"
        )
        self.client.force_login(self.employer)

    def test_all_jobs_and_counts(self):
        response = self.client.get(reverse("core:my_jobs"))
        self.assertEqual(len(response.context["jobs"]), 3)
        open_job = next(
            job for job in response.context["jobs"] if job.pk == self.open_job.pk
        )
        self.assertEqual(open_job.application_count, 1)
        self.assertContains(response, "Отклики · 1")

    def test_status_filter(self):
        for status in ("open", "completed", "cancelled"):
            with self.subTest(status=status):
                response = self.client.get(
                    reverse("core:my_jobs"), {"status": status}
                )
                jobs = list(response.context["jobs"])
                expected = getattr(self, "%s_job" % status)
                self.assertEqual([job.pk for job in jobs], [expected.pk])

    def test_bulk_ui_present(self):
        response = self.client.get(reverse("core:my_jobs"))
        self.assertContains(response, 'id="bulk-jobs-form"')
        self.assertContains(response, 'name="job_ids"')
        self.assertContains(response, reverse("core:my_jobs_bulk"))
        self.assertContains(response, 'name="action" value="cancel"')


class MyApplicationsTabsTests(TestCase):
    def setUp(self):
        self.employer = make_profile("tabs-emp@example.com", role="employer")
        self.worker = make_profile("tabs-worker@example.com", role="worker")
        self.job = make_job(self.employer, work_type="Tab-задание")
        self.app = Application.objects.create(
            job=self.job, worker=self.worker, status="pending"
        )

    def test_sent_default_and_received(self):
        self.client.force_login(self.worker)
        response = self.client.get(reverse("core:my_applications"))
        self.assertEqual(response.context["tab"], "sent")
        self.assertEqual(list(response.context["apps"]), [self.app])
        self.assertContains(response, "Tab-задание")

        self.client.force_login(self.employer)
        response = self.client.get(
            reverse("core:my_applications"), {"tab": "received"}
        )
        self.assertEqual(response.context["tab"], "received")
        self.assertEqual(list(response.context["apps"]), [self.app])
        self.assertContains(response, self.worker.full_name)

        self.client.force_login(self.worker)
        response = self.client.get(
            reverse("core:my_applications"), {"tab": "received"}
        )
        self.assertEqual(list(response.context["apps"]), [])

    def test_pagination(self):
        for i in range(20):
            job = make_job(self.employer, work_type="Pag %d" % i)
            Application.objects.create(
                job=job, worker=self.worker, status="pending"
            )
        self.client.force_login(self.worker)
        response = self.client.get(reverse("core:my_applications"), {"page": 2})
        self.assertEqual(response.context["page"].number, 2)
        self.assertEqual(len(response.context["apps"]), 1)

    def test_bulk_ui_only_received(self):
        self.client.force_login(self.employer)
        response = self.client.get(
            reverse("core:my_applications"), {"tab": "received"}
        )
        self.assertContains(response, 'id="bulk-apps-form"')
        self.assertContains(response, 'name="app_ids"')
        self.assertContains(response, reverse("core:my_applications_bulk"))
        self.assertContains(response, "Принять выбранные")

        self.client.force_login(self.worker)
        response = self.client.get(reverse("core:my_applications"))
        self.assertNotContains(response, 'name="app_ids"')
        self.assertNotContains(response, "Принять выбранные")


class BulkJobsTests(TestCase):
    def setUp(self):
        self.employer = make_profile("bulk-emp@example.com", role="employer")
        self.jobs = [
            make_job(self.employer, work_type="Bulk %d" % i) for i in range(3)
        ]
        self.client.force_login(self.employer)

    def test_cancel_restore_delete(self):
        ids = [str(job.pk) for job in self.jobs[:2]]
        self.client.post(
            reverse("core:my_jobs_bulk"), {"action": "cancel", "job_ids": ids}
        )
        self.assertEqual(
            Job.objects.filter(pk__in=ids, status="cancelled").count(), 2
        )
        self.client.post(
            reverse("core:my_jobs_bulk"), {"action": "restore", "job_ids": ids}
        )
        self.assertEqual(Job.objects.filter(pk__in=ids, status="open").count(), 2)
        self.client.post(
            reverse("core:my_jobs_bulk"),
            {"action": "delete", "job_ids": [ids[0]]},
        )
        self.assertFalse(Job.objects.filter(pk=ids[0]).exists())

    def test_stranger_ids_ignored(self):
        other = make_profile("bulk-other@example.com", role="employer")
        stranger = make_job(other, work_type="Чужое")
        self.client.post(
            reverse("core:my_jobs_bulk"),
            {"action": "delete", "job_ids": [str(stranger.pk)]},
        )
        self.assertTrue(Job.objects.filter(pk=stranger.pk).exists())

    def test_malformed_ids_do_not_500(self):
        response = self.client.post(
            reverse("core:my_jobs_bulk"),
            {"action": "cancel", "job_ids": ["not-a-uuid", ""]},
        )
        self.assertEqual(response.status_code, 302)

    def test_bulk_delete_removes_photo_files(self):
        url = save_upload(
            SimpleUploadedFile("p.png", TINY_PNG, content_type="image/png"), "jobs"
        )
        job = self.jobs[0]
        JobPhoto.objects.create(job=job, photo_url=url, order_num=0)
        self.client.post(
            reverse("core:my_jobs_bulk"),
            {"action": "delete", "job_ids": [str(job.pk)]},
        )
        self.assertFalse(Job.objects.filter(pk=job.pk).exists())
        self.assertIsNone(resolve_upload_url(url[len("/uploads/"):]))

    def test_bulk_delete_shared_photo_removed_after_last_ref(self):
        url = save_upload(
            SimpleUploadedFile("p.png", TINY_PNG, content_type="image/png"), "jobs"
        )
        first, second = self.jobs[:2]
        JobPhoto.objects.create(job=first, photo_url=url, order_num=0)
        JobPhoto.objects.create(job=second, photo_url=url, order_num=0)
        self.client.post(
            reverse("core:my_jobs_bulk"),
            {"action": "delete", "job_ids": [str(first.pk), str(second.pk)]},
        )
        self.assertFalse(Job.objects.filter(pk__in=[first.pk, second.pk]).exists())
        self.assertIsNone(resolve_upload_url(url[len("/uploads/"):]))

    def test_bulk_duplicate_copies_job(self):
        url = save_upload(
            SimpleUploadedFile("p.png", TINY_PNG, content_type="image/png"), "jobs"
        )
        job = self.jobs[0]
        job.photo_urls = [url]
        job.save(update_fields=["photo_urls"])
        JobPhoto.objects.create(job=job, photo_url=url, order_num=0)
        skill = Skill.objects.create(name="Bulk duplicate skill", sort_order=1)
        JobSkill.objects.create(job=job, skill=skill)

        self.client.post(
            reverse("core:my_jobs_bulk"),
            {"action": "duplicate", "job_ids": [str(job.pk)]},
        )
        self.assertEqual(Job.objects.filter(employer=self.employer).count(), 4)
        copy = Job.objects.exclude(pk__in=[j.pk for j in self.jobs]).get(
            employer=self.employer
        )
        delta = copy.expires_at - timezone.now()
        self.assertGreater(delta, timedelta(days=29))
        self.assertLess(delta, timedelta(days=31))
        self.assertEqual(copy.photo_urls, job.photo_urls)
        self.assertEqual(
            list(copy.photos.values_list("photo_url", flat=True)), [url]
        )
        self.assertEqual(
            list(copy.job_skills.values_list("skill_id", flat=True)), [skill.pk]
        )


class BulkApplicationsTests(TestCase):
    def setUp(self):
        self.employer = make_profile("bulk-app-emp@example.com", role="employer")
        self.worker = make_profile("bulk-app-worker@example.com", role="worker")
        self.jobs = [
            make_job(self.employer, work_type="BulkApp %d" % i) for i in range(2)
        ]
        self.apps = [
            Application.objects.create(job=job, worker=self.worker, status="pending")
            for job in self.jobs
        ]
        self.client.force_login(self.employer)

    def test_accept_reject_reopen(self):
        ids = [str(app.pk) for app in self.apps]
        self.client.post(
            reverse("core:my_applications_bulk"),
            {"action": "accept", "app_ids": ids},
        )
        self.assertEqual(
            Application.objects.filter(pk__in=ids, status="accepted").count(), 2
        )
        self.assertEqual(
            Job.objects.filter(pk__in=[j.pk for j in self.jobs], current_workers=1).count(),
            2,
        )
        self.client.post(
            reverse("core:my_applications_bulk"),
            {"action": "reject", "app_ids": ids},
        )
        self.assertEqual(
            Application.objects.filter(pk__in=ids, status="rejected").count(), 2
        )
        self.client.post(
            reverse("core:my_applications_bulk"),
            {"action": "reopen", "app_ids": ids},
        )
        self.assertEqual(
            Application.objects.filter(pk__in=ids, status="accepted").count(), 2
        )
        self.assertTrue(
            NotificationOutbox.objects.filter(
                user=self.worker, type="application_accepted"
            ).exists()
        )

    def test_worker_cannot_bulk_received(self):
        ids = [str(app.pk) for app in self.apps]
        self.client.force_login(self.worker)
        self.client.post(
            reverse("core:my_applications_bulk"),
            {"action": "accept", "app_ids": ids},
        )
        self.assertEqual(
            Application.objects.filter(pk__in=ids, status="pending").count(), 2
        )


class BulkApplyTests(TestCase):
    def setUp(self):
        self.employer = make_profile("bulk-apply-emp@example.com", role="employer")
        self.worker = make_profile("bulk-apply-worker@example.com", role="worker")
        self.jobs = [
            make_job(self.employer, work_type="BulkApply %d" % i) for i in range(2)
        ]
        self.client.force_login(self.worker)

    def test_bulk_apply_creates_applications_and_grouped_notification(self):
        response = self.client.post(
            reverse("core:bulk_apply"),
            {"job_ids": [str(job.pk) for job in self.jobs]},
            follow=True,
        )
        self.assertEqual(
            Application.objects.filter(
                worker=self.worker, job__in=self.jobs
            ).count(),
            2,
        )
        rows = NotificationOutbox.objects.filter(
            user=self.employer, type="application_received"
        )
        self.assertEqual(rows.count(), 1)
        self.assertEqual(len(rows.get().data["job_ids"]), 2)
        self.assertContains(response, "Выполнено: 2, пропущено: 0, ошибок: 0")

    def test_bulk_apply_duplicate_skipped(self):
        for job in self.jobs:
            Application.objects.create(
                job=job, worker=self.worker, status="pending"
            )
        response = self.client.post(
            reverse("core:bulk_apply"),
            {"job_ids": [str(job.pk) for job in self.jobs]},
            follow=True,
        )
        self.assertContains(response, "пропущено: 2")
        self.assertFalse(
            NotificationOutbox.objects.filter(
                user=self.employer, type="application_received"
            ).exists()
        )

    def test_bulk_apply_own_job_skipped(self):
        self.client.force_login(self.employer)
        response = self.client.post(
            reverse("core:bulk_apply"),
            {"job_ids": [str(self.jobs[0].pk)]},
            follow=True,
        )
        self.assertContains(response, "пропущено: 1")
        self.assertFalse(
            Application.objects.filter(
                job=self.jobs[0], worker=self.employer
            ).exists()
        )

    def test_bulk_apply_ignores_external_referer(self):
        response = self.client.post(
            reverse("core:bulk_apply"),
            {"job_ids": [str(self.jobs[0].pk)]},
            HTTP_REFERER="https://evil.example/phish",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/jobs")

    def test_bulk_apply_rpc_error_does_not_abort_batch(self):
        from unittest import mock

        calls = {"n": 0}

        def fake_call(name, *args):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("rpc down")
            return {"success": True, "employer_id": str(self.employer.pk)}

        with mock.patch("core.views_public_ext.call_rpc", side_effect=fake_call):
            response = self.client.post(
                reverse("core:bulk_apply"),
                {"job_ids": [str(job.pk) for job in self.jobs]},
                follow=True,
            )
        self.assertContains(response, "Выполнено: 1, пропущено: 0, ошибок: 1")
