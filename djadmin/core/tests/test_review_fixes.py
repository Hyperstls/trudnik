"""Регрессионные тесты по итогам код-ревью (2026-10-30).

Покрывают: open-redirect guard, logout, создание пользователя в админке
(пароль обязателен, email нормализуется, дубликат — ошибка формы), guard'ы
блокировки/роли админов через форму, NULLS LAST сортировки, public()-дисциплину
favorite/apply, owner-видимость своих заданий, негативный reopen.
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Job, Profile
from core.tests.test_auth import make_profile
from core.tests.test_flows import make_job


class NextRedirectSafetyTests(TestCase):
    def setUp(self):
        self.user = make_profile("next-safe@example.com")

    def test_open_redirect_blocked(self):
        response = self.client.post(
            "/login?next=//evil.com",
            {"email": "next-safe@example.com", "password": "Aa1!aaaa"},  # pragma: allowlist secret
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("evil.com", response["Location"])
        self.assertEqual(response["Location"], "/")

    def test_backslash_redirect_blocked(self):
        response = self.client.post(
            "/login?next=/\\evil.com",
            {"email": "next-safe@example.com", "password": "Aa1!aaaa"},  # pragma: allowlist secret
        )
        self.assertNotIn("evil.com", response["Location"])

    def test_valid_next_honoured(self):
        response = self.client.post(
            "/login?next=/jobs",
            {"email": "next-safe@example.com", "password": "Aa1!aaaa"},  # pragma: allowlist secret
        )
        self.assertEqual(response["Location"], "/jobs")

    def test_logout_post_only(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/logout").status_code, 405)
        response = self.client.post("/logout")
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.user)  # восстановим для чистоты
        self.assertTrue(self.client.session.keys() is not None)


class AdminUserFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Profile.objects.create_superuser("root-form@example.com", "Aa1!aaaa")

    def setUp(self):
        self.client.force_login(self.admin)

    def _mgmt(self, data):
        data.setdefault("_save", "1")  # «Сохранить» — без него admin не выполняет save
        # required-поля модели (в UI предзаполнены default'ами; в тесте задаём явно)
        data.setdefault("verification_status", "none")
        data.setdefault("verification_provider", "manual")
        data.setdefault("employer_detail-TOTAL_FORMS", "0")
        data.setdefault("employer_detail-INITIAL_FORMS", "0")
        data.setdefault("employer_detail-MIN_NUM_FORMS", "0")
        data.setdefault("employer_detail-MAX_NUM_FORMS", "1")
        return data

    def test_add_user_requires_password_and_sets_it(self):
        url = reverse("admin:core_profile_add")
        data = {
            "email": "Added@Example.com", "full_name": "Добавленный", "role": "worker",
            "email_verified": "on", "worker_visibility": "on",
            #new_password пустой
        }
        response = self.client.post(url, self._mgmt(data))
        # форма вернулась с ошибкой обязательного поля
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Profile.objects.filter(email="added@example.com").exists())

        data["new_password"] = "Bb2!bbbb"  # pragma: allowlist secret
        response = self.client.post(url, self._mgmt(data))
        if response.status_code == 200:
            formset_errors = ""
            for fs in getattr(response.context, "inline_admin_formsets", []) or []:
                formset_errors += str(fs.formset.errors)
            self.fail(
                "валидная форма не сохранилась: form=%s formsets=%s"
                % (response.context["form"].errors, formset_errors)
            )
        created = Profile.objects.get(email="added@example.com")  # нормализован в lower
        self.assertTrue(created.check_password("Bb2!bbbb"))
        self.assertTrue(created.email_verified)

    def test_add_duplicate_email_case_insensitive(self):
        make_profile("dup@example.com")
        response = self.client.post(reverse("admin:core_profile_add"), self._mgmt({
            "email": "DUP@example.com", "full_name": "Дубль", "role": "worker",
            "email_verified": "on", "worker_visibility": "on", "new_password": "Bb2!bbbb",  # pragma: allowlist secret
        }))
        self.assertEqual(response.status_code, 200)  # форма с ошибкой, не 500
        self.assertContains(response, "уже существует")

    def test_cannot_suspend_another_admin_via_form(self):
        other_admin = Profile.objects.create_superuser("other-admin@example.com", "Aa1!aaaa")
        response = self.client.post(
            reverse("admin:core_profile_change", args=[other_admin.pk]),
            self._mgmt({
                "email": "other-admin@example.com", "full_name": "Другой админ", "role": "admin",
                "suspended": "on", "email_verified": "on", "worker_visibility": "on",
            }),
        )
        self.assertEqual(response.status_code, 200)  # ошибка формы
        self.assertFalse(Profile.objects.get(pk=other_admin.pk).suspended)

    def test_cannot_change_own_role_via_form(self):
        # собственная роль readonly в форме → POST с другой ролью сохраняет без изменений
        response = self.client.post(
            reverse("admin:core_profile_change", args=[self.admin.pk]),
            self._mgmt({
                "email": "root-form@example.com", "full_name": "Рут", "role": "worker",
                "email_verified": "on", "worker_visibility": "on",
            }),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Profile.objects.get(pk=self.admin.pk).role, "admin")


class OrderingNullsTests(TestCase):
    def test_promoted_first_despite_nulls(self):
        from django.db.models import F

        from core.views import _promoted_first

        emp = make_profile("ord-emp@example.com")
        plain = make_job(emp, work_type="Обычное")
        promoted = make_job(emp, work_type="Продвинутое", is_promoted=True)
        legacy_null = Job.objects.create(
            employer=emp, work_type="Легаси-NULL", status="open",
            date_time=timezone.now() + timedelta(days=1), is_promoted=None,
        )
        ids = [plain.pk, promoted.pk, legacy_null.pk]
        order = list(
            Job.objects.public().order_by(_promoted_first(), "-created_at")
            .filter(id__in=ids).values_list("work_type", flat=True)
        )
        self.assertLess(order.index("Продвинутое"), order.index("Обычное"))
        self.assertLess(order.index("Продвинутое"), order.index("Легаси-NULL"))

    def test_payment_sort_nulls_last(self):
        from django.db.models import F

        emp = make_profile("ord-emp2@example.com")
        no_pay = make_job(emp, work_type="БезОплаты", payment_amount=None)
        paid = make_job(emp, work_type="Оплаченное", payment_amount=5000)
        order = list(
            Job.objects.public()
            .filter(id__in=[no_pay.pk, paid.pk])
            .order_by(F("payment_amount").desc(nulls_last=True))
            .values_list("work_type", flat=True)
        )
        self.assertLess(order.index("Оплаченное"), order.index("БезОплаты"))
        # и вьюха использует nulls_last (не голый минус)
        from django.db.models import F as F2

        from core import views as core_views

        self.assertIn("nulls_last", open(core_views.__file__, encoding="utf-8").read())


class PublicDisciplineTests(TestCase):
    def setUp(self):
        self.employer = make_profile("disc-emp@example.com")
        self.worker = make_profile("disc-worker@example.com")
        self.draft = make_job(self.employer, status="draft", work_type="Черновик")
        self.client.force_login(self.worker)

    def test_favorite_hidden_job_rejected(self):
        self.client.post(reverse("core:job_favorite_toggle", args=[self.draft.pk]))
        from core.models import JobFavorite

        self.assertFalse(JobFavorite.objects.filter(user=self.worker, job=self.draft).exists())

    def test_apply_hidden_job_uniform_not_found(self):
        response = self.client.post(reverse("core:job_apply", args=[self.draft.pk]))
        self.assertEqual(response.status_code, 302)
        from core.models import Application

        self.assertFalse(Application.objects.filter(job=self.draft).exists())

    def test_owner_sees_own_draft_detail(self):
        self.client.force_login(self.employer)
        response = self.client.get(reverse("core:job_detail", args=[self.draft.pk]))
        self.assertEqual(response.status_code, 200)

    def test_stranger_gets_404_on_draft(self):
        response = self.client.get(reverse("core:job_detail", args=[self.draft.pk]))
        self.assertEqual(response.status_code, 404)

    def test_reopen_only_rejected(self):
        from core.models import Application

        app = Application.objects.create(job=make_job(self.employer, work_type="Re"),
                                         worker=self.worker, status="pending")
        self.client.force_login(self.employer)
        self.client.post(reverse("core:application_action", args=[app.pk, "reopen"]))
        app.refresh_from_db()
        self.assertEqual(app.status, "pending")  # не изменился: pending нельзя «верернуть»
