"""Публичные read-only страницы + health."""
import os
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from core import views
from core.models import Application, Blacklist, Favorite, Invitation, Job, JobPhoto, JobSkill, Rating, Religion, SitePage, Skill, UserSkill
from core.storage import resolve_upload_url, save_upload
from core.tests.test_auth import make_profile

CONTACTS_AFTER_RESPONSE_TEXT = "Контакты открываются после отклика на задание."
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 16


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

    def test_home_redirects_to_jobs_feed(self):
        """Flask-паритет: / — лента заданий (redirect на /jobs)."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/jobs")
        self.assertContains(self.client.get("/jobs"), "Уборка территории")

    def test_jobs_list_and_filters(self):
        self.assertEqual(self.client.get("/jobs").status_code, 200)
        self.assertContains(self.client.get("/jobs?q=уборка"), "Уборка территории")
        self.assertNotIn("Уборка территории".encode(), self.client.get("/jobs?q=сварка").content)
        self.assertContains(self.client.get("/jobs?city=москва"), "Уборка территории")
        self.assertContains(self.client.get("/jobs?payment_min=1000"), "Уборка территории")
        self.assertNotIn("Уборка территории".encode(), self.client.get("/jobs?payment_min=9999").content)

    def test_search_matches_object_description(self):
        Job.objects.create(
            employer=self.employer, work_type="Обычное задание",
            object_description="Уникальный объект J020", organization_name="Приход",
            status="open", city="Москва", payment_amount=1000,
            date_time=timezone.now() + timedelta(days=2),
        )
        self.assertContains(self.client.get("/jobs?q=Уникальный"), "Обычное задание")
        self.assertNotContains(
            self.client.get("/jobs?q=Несуществующий"), "Обычное задание"
        )

    def test_payment_max_filter(self):
        Job.objects.create(
            employer=self.employer, work_type="Дешёвое задание", organization_name="Приход",
            status="open", city="Москва", payment_amount=1000,
            date_time=timezone.now() + timedelta(days=2),
        )
        response = self.client.get("/jobs?payment_max=2000")
        self.assertContains(response, "Дешёвое задание")
        self.assertNotContains(response, "Уборка территории")

    def test_skill_filter(self):
        skill = Skill.objects.create(name="Тестовый навык J013", sort_order=1)
        JobSkill.objects.create(job=self.job, skill=skill)
        other = Job.objects.create(
            employer=self.employer, work_type="Без навыка", organization_name="Приход",
            status="open", city="Москва", payment_amount=1500,
            date_time=timezone.now() + timedelta(days=2),
        )
        response = self.client.get("/jobs", {"skills": str(skill.pk)})
        self.assertContains(response, "Уборка территории")
        self.assertNotContains(response, other.work_type)

    def test_multi_skill_filter(self):
        skill_a = Skill.objects.create(name="Навык A J019", sort_order=1)
        skill_b = Skill.objects.create(name="Навык B J019", sort_order=2)
        job_b = Job.objects.create(
            employer=self.employer, work_type="Задание B", organization_name="Приход",
            status="open", city="Москва", payment_amount=1500,
            date_time=timezone.now() + timedelta(days=2),
        )
        self.job.job_skills.create(skill=skill_a)
        job_b.job_skills.create(skill=skill_b)
        plain = Job.objects.create(
            employer=self.employer, work_type="Без навыков", organization_name="Приход",
            status="open", city="Москва", payment_amount=1500,
            date_time=timezone.now() + timedelta(days=2),
        )
        both = self.client.get(
            "/jobs", {"skills": "%s,%s" % (skill_a.pk, skill_b.pk)}
        )
        self.assertContains(both, "Уборка территории")
        self.assertContains(both, "Задание B")
        self.assertNotContains(both, plain.work_type)
        single = self.client.get("/jobs", {"skills": str(skill_a.pk)})
        self.assertContains(single, "Уборка территории")
        self.assertNotContains(single, "Задание B")

    def test_skill_filter_ignores_garbage_and_duplicates(self):
        skill = Skill.objects.create(name="Навык J019 dup", sort_order=1)
        self.job.job_skills.create(skill=skill)
        response = self.client.get(
            "/jobs", {"skills": "garbage,%s,%s" % (skill.pk, skill.pk)}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Уборка территории")

    def test_filter_new_and_applied(self):
        other = Job.objects.create(
            employer=self.employer, work_type="Без отклика", organization_name="Приход",
            status="open", city="Москва", payment_amount=1500,
            date_time=timezone.now() + timedelta(days=2),
        )
        Application.objects.create(
            job=self.job, worker=self.worker, status="pending"
        )
        self.client.force_login(self.worker)
        applied = self.client.get("/jobs", {"filter": "applied"})
        self.assertContains(applied, "Уборка территории")
        self.assertNotContains(applied, other.work_type)
        fresh = self.client.get("/jobs", {"filter": "new"})
        self.assertContains(fresh, other.work_type)
        self.assertNotContains(fresh, "Уборка территории")

    def test_jobs_list_shows_jobphoto(self):
        JobPhoto.objects.create(
            job=self.job, photo_url="/uploads/jobs/card.png", order_num=0
        )
        self.assertContains(self.client.get("/jobs"), "/uploads/jobs/card.png")

    def test_job_detail_legacy_photo_fallback(self):
        self.job.photo_urls = ["/uploads/jobs/legacy.png"]
        self.job.save(update_fields=["photo_urls"])
        self.assertContains(
            self.client.get(f"/jobs/{self.job.pk}"), "/uploads/jobs/legacy.png"
        )

    def test_photo_upload_limit_three(self):
        self.client.force_login(self.employer)
        for i in range(3):
            JobPhoto.objects.create(
                job=self.job, photo_url=f"/uploads/jobs/{i}.png", order_num=i
            )
        file = SimpleUploadedFile("p.png", PNG_BYTES, content_type="image/png")
        response = self.client.post(
            reverse("core:job_photo_upload", args=[self.job.pk]),
            {"photo": file}, follow=True,
        )
        self.assertContains(response, "не более 3 фото")
        self.assertEqual(JobPhoto.objects.filter(job=self.job).count(), 3)

    def test_photo_delete_removes_file(self):
        self.client.force_login(self.employer)
        url = save_upload(
            SimpleUploadedFile("p.png", PNG_BYTES, content_type="image/png"), "jobs"
        )
        photo = JobPhoto.objects.create(job=self.job, photo_url=url, order_num=0)
        self.client.post(
            reverse("core:job_photo_delete", args=[self.job.pk, photo.pk])
        )
        self.assertFalse(JobPhoto.objects.filter(pk=photo.pk).exists())
        self.assertIsNone(resolve_upload_url(url[len("/uploads/"):]))

    def test_photo_delete_keeps_shared_file(self):
        self.client.force_login(self.employer)
        url = save_upload(
            SimpleUploadedFile("p.png", PNG_BYTES, content_type="image/png"), "jobs"
        )
        other = Job.objects.create(
            employer=self.employer, work_type="Копия", status="open",
            date_time=timezone.now() + timedelta(days=2),
        )
        photo = JobPhoto.objects.create(job=self.job, photo_url=url, order_num=0)
        JobPhoto.objects.create(job=other, photo_url=url, order_num=0)
        self.client.post(
            reverse("core:job_photo_delete", args=[self.job.pk, photo.pk])
        )
        self.assertIsNotNone(resolve_upload_url(url[len("/uploads/"):]))

    def test_job_detail_ok_and_hidden_404(self):
        self.assertEqual(self.client.get(f"/jobs/{self.job.pk}").status_code, 200)
        hidden = Job.objects.create(
            employer=self.employer, work_type="Черновик", status="draft",
            date_time=timezone.now(),
        )
        self.assertEqual(self.client.get(f"/jobs/{hidden.pk}").status_code, 404)

    def test_detail_owner_application_count(self):
        Application.objects.create(
            job=self.job, worker=self.worker, status="pending"
        )
        self.client.force_login(self.employer)
        response = self.client.get(f"/jobs/{self.job.pk}")
        self.assertContains(response, "Отклики (1)")

    def test_detail_employer_favorite_toggle(self):
        self.client.force_login(self.worker)
        response = self.client.get(f"/jobs/{self.job.pk}")
        self.assertContains(
            response,
            reverse("core:people_favorite_toggle", args=[self.employer.pk]),
        )
        self.client.post(
            reverse("core:people_favorite_toggle", args=[self.employer.pk])
        )
        self.assertTrue(
            Favorite.objects.filter(
                user=self.worker, target=self.employer, favorite_type="employer"
            ).exists()
        )

    def test_detail_has_report_and_share(self):
        self.client.force_login(self.worker)
        response = self.client.get(f"/jobs/{self.job.pk}")
        self.assertContains(
            response, reverse("core:report_user", args=[self.employer.pk])
        )
        content = response.content.decode()
        self.assertIn("t.me/share/url?url=http%3A", content)
        self.assertIn("wa.me/?text=http%3A", content)

    def test_detail_guest_has_no_employer_actions(self):
        response = self.client.get(f"/jobs/{self.job.pk}")
        self.assertNotContains(response, "Пожаловаться")
        self.assertNotContains(response, "t.me/share")

    def test_detail_shows_employer_rating_and_reviews(self):
        Rating.objects.create(
            rated_user=self.employer, rater_user=self.worker, job=self.job,
            rating=5, comment="Отличный работодатель",
            rating_type="employer", target_type="employer",
        )
        response = self.client.get(f"/jobs/{self.job.pk}")
        self.assertContains(response, "Отличный работодатель")
        self.assertContains(
            response, reverse("core:user_ratings", args=[self.employer.pk])
        )

    def test_detail_empty_reviews(self):
        response = self.client.get(f"/jobs/{self.job.pk}")
        self.assertContains(response, "Отзывов пока нет.")

    def test_detail_shows_verified_employer_badge(self):
        self.employer.verification_status = "approved"
        self.employer.save(update_fields=["verification_status"])
        response = self.client.get(f"/jobs/{self.job.pk}")
        self.assertContains(response, "✓ Подтверждён")

    def test_detail_hides_unverified_badge(self):
        self.employer.verification_status = "pending"
        self.employer.save(update_fields=["verification_status"])
        response = self.client.get(f"/jobs/{self.job.pk}")
        self.assertNotContains(response, "Подтверждён")

    def test_workers_catalog(self):
        response = self.client.get("/workers")
        self.assertEqual(response.status_code, 200)
        # новый профиль (rating=0) может быть не на 1-й странице среди данных клона — ищем поиском
        self.assertContains(self.client.get("/workers?q=Иван"), self.worker.full_name)

    def test_workers_skill_filter(self):
        skill = Skill.objects.create(name="Навык трудника J021", sort_order=1)
        UserSkill.objects.create(user=self.worker, skill=skill)
        other = make_profile("worker-other-j021@example.com", role="worker")
        other.full_name = "Другой трудник J021"
        other.save(update_fields=["full_name"])
        response = self.client.get("/workers", {"skills": str(skill.pk)})
        self.assertContains(response, self.worker.full_name)
        self.assertNotContains(response, other.full_name)

    def test_workers_rating_and_payment_filters(self):
        self.worker.rating = 4.5
        self.worker.desired_payment = 2000
        self.worker.save(update_fields=["rating", "desired_payment"])
        other = make_profile("worker-cheap-j021@example.com", role="worker")
        other.full_name = "Дешёвый трудник J021"
        other.rating = 1
        other.desired_payment = 100
        other.save(update_fields=["full_name", "rating", "desired_payment"])
        rated = self.client.get("/workers", {"rating_min": "4"})
        self.assertContains(rated, self.worker.full_name)
        self.assertNotContains(rated, other.full_name)
        paid = self.client.get("/workers", {"payment_from": "1500"})
        self.assertContains(paid, self.worker.full_name)
        self.assertNotContains(paid, other.full_name)

    def test_workers_sort_by_name(self):
        self.worker.full_name = "Aaa J021sort"
        self.worker.save(update_fields=["full_name"])
        second = make_profile("worker-bbb-j021@example.com", role="worker")
        second.full_name = "Bbb J021sort"
        second.save(update_fields=["full_name"])
        response = self.client.get("/workers", {"q": "J021sort", "sort": "name"})
        names = [w.full_name for w in response.context["page"].object_list]
        self.assertEqual(names, ["Aaa J021sort", "Bbb J021sort"])

    def test_workers_nonfinite_payment_ignored(self):
        for value in ("NaN", "sNaN", "Infinity", "1e999"):
            with self.subTest(value=value):
                self.assertEqual(
                    self.client.get(
                        "/workers", {"payment_from": value, "payment_to": value}
                    ).status_code,
                    200,
                )

    def _accepted_apps(self, count):
        for i in range(count):
            job = Job.objects.create(
                employer=self.employer, work_type="Reliable %d" % i,
                organization_name="Приход", status="open", city="Москва",
                payment_amount=1000,
                date_time=timezone.now() + timedelta(days=2),
            )
            Application.objects.create(
                job=job, worker=self.worker, status="accepted"
            )

    def test_workers_reliable_badge(self):
        self._accepted_apps(10)
        response = self.client.get("/workers", {"q": self.worker.full_name})
        self.assertContains(response, "Надёжный")

    def test_workers_reliable_requires_zero_rejected(self):
        self._accepted_apps(10)
        job = Job.objects.create(
            employer=self.employer, work_type="Rejected", organization_name="Приход",
            status="open", city="Москва", payment_amount=1000,
            date_time=timezone.now() + timedelta(days=2),
        )
        Application.objects.create(
            job=job, worker=self.worker, status="rejected"
        )
        response = self.client.get("/workers", {"q": self.worker.full_name})
        self.assertNotContains(response, "Надёжный")

    def test_workers_invited_badge(self):
        Invitation.objects.create(
            job=self.job, employer=self.employer, worker=self.worker,
            status="pending",
        )
        self.client.force_login(self.employer)
        response = self.client.get("/workers", {"q": self.worker.full_name})
        self.assertContains(response, "Приглашён")

    def test_workers_invited_badge_accepted(self):
        Invitation.objects.create(
            job=self.job, employer=self.employer, worker=self.worker,
            status="accepted",
        )
        self.client.force_login(self.employer)
        response = self.client.get("/workers", {"q": self.worker.full_name})
        self.assertContains(response, "Приглашён")

    def test_workers_invited_badge_other_employer_ignored(self):
        other = make_profile("other-emp-j023@example.com", role="employer")
        job = Job.objects.create(
            employer=other, work_type="Other invite", organization_name="Приход",
            status="open", city="Москва", payment_amount=1000,
            date_time=timezone.now() + timedelta(days=2),
        )
        Invitation.objects.create(
            job=job, employer=other, worker=self.worker, status="pending",
        )
        self.client.force_login(self.employer)
        response = self.client.get("/workers", {"q": self.worker.full_name})
        self.assertNotContains(response, "Приглашён")

    def _geo_jobs(self):
        near = Job.objects.create(
            employer=self.employer, work_type="Near J024", organization_name="Приход",
            status="open", city="Санкт-Петербург", payment_amount=1000,
            lat=60.0, lng=30.0,
            date_time=timezone.now() + timedelta(days=2),
        )
        far = Job.objects.create(
            employer=self.employer, work_type="Far J024", organization_name="Приход",
            status="open", city="Санкт-Петербург", payment_amount=1000,
            lat=60.1, lng=30.0,
            date_time=timezone.now() + timedelta(days=2),
        )
        return near, far

    def test_geo_filter_nearby(self):
        near, far = self._geo_jobs()
        from unittest.mock import patch

        with patch("core.views.call_rpc_rows") as rpc:
            rpc.return_value = [{"id": near.pk, "distance_meters": 100}]
            response = self.client.get(
                "/jobs", {"q": "J024", "lat": "60.0", "lng": "30.0", "radius": "2"}
            )
        rpc.assert_called_once_with("nearby_jobs", 60.0, 30.0, 2000.0)
        self.assertContains(response, near.work_type)
        self.assertNotContains(response, far.work_type)

    def test_geo_invalid_coords_ignored(self):
        near, far = self._geo_jobs()
        from unittest.mock import patch

        with patch("core.views.call_rpc_rows") as rpc:
            response = self.client.get(
                "/jobs", {"q": "J024", "lat": "999", "lng": "30.0", "radius": "2"}
            )
        rpc.assert_not_called()
        self.assertContains(response, near.work_type)
        self.assertContains(response, far.work_type)

    def test_geo_distance_sort(self):
        near, far = self._geo_jobs()
        from unittest.mock import patch

        with patch("core.views.call_rpc_rows") as rpc:
            rpc.return_value = [
                {"id": near.pk, "distance_meters": 100},
                {"id": far.pk, "distance_meters": 12000},
            ]
            response = self.client.get(
                "/jobs",
                {"q": "J024", "lat": "60.0", "lng": "30.0", "radius": "20", "sort": "distance"},
            )
        names = [job.work_type for job in response.context["page"].object_list]
        self.assertEqual(names, ["Near J024", "Far J024"])

    def test_geo_rpc_failure_falls_open(self):
        near, far = self._geo_jobs()
        from unittest.mock import patch

        with patch("core.views.call_rpc_rows", side_effect=RuntimeError("rpc down")):
            response = self.client.get(
                "/jobs",
                {"q": "J024", "lat": "60.0", "lng": "30.0", "radius": "2"},
                follow=True,
            )
        self.assertContains(response, "Гео-поиск недоступен")
        self.assertContains(response, near.work_type)
        self.assertContains(response, far.work_type)

    def test_geo_card_shows_zero_distance(self):
        near, _ = self._geo_jobs()
        from unittest.mock import patch

        with patch("core.views.call_rpc_rows") as rpc:
            rpc.return_value = [{"id": near.pk, "distance_meters": 0}]
            response = self.client.get(
                "/jobs", {"q": "J024", "lat": "60.0", "lng": "30.0", "radius": "2"}
            )
        self.assertContains(response, "0.0 км")

    def test_jobs_map_points_context(self):
        near, far = self._geo_jobs()
        response = self.client.get("/jobs", {"q": "J024"})
        points = response.context["map_points"]
        self.assertEqual(len(points), 2)
        self.assertIn(str(near.pk), {p["id"] for p in points})
        self.assertIn("/jobs/%s" % near.pk, {p["url"] for p in points})

    def test_jobs_map_rendered_with_key(self):
        self._geo_jobs()
        from unittest.mock import patch

        with patch.dict(os.environ, {"YANDEX_MAPS_API_KEY": "test-" + "key"}):  # pragma: allowlist secret
            response = self.client.get("/jobs", {"q": "J024"})
        self.assertContains(response, 'id="jobs-map"')
        self.assertContains(response, "api-maps.yandex.ru")
        self.assertContains(response, "apikey=test-key")

    def test_jobs_map_absent_without_key(self):
        self._geo_jobs()
        from unittest.mock import patch

        with patch.dict(os.environ, {"YANDEX_MAPS_API_KEY": ""}):
            response = self.client.get("/jobs", {"q": "J024"})
        self.assertNotContains(response, 'id="jobs-map"')

    def test_jobs_map_skips_jobs_without_coords(self):
        Job.objects.create(
            employer=self.employer, work_type="NoCoord J025", organization_name="Приход",
            status="open", city="Москва", payment_amount=1000,
            date_time=timezone.now() + timedelta(days=2),
        )
        response = self.client.get("/jobs", {"q": "J025"})
        self.assertContains(response, "NoCoord J025")
        self.assertEqual(response.context["map_points"], [])

    def test_worker_detail_hides_private_fields(self):
        response = self.client.get(f"/workers/{self.worker.pk}")
        self.assertEqual(response.status_code, 200)
        # приватные колонки (email/phone) никогда не рендерятся
        self.assertNotContains(response, "worker-pub@example.com")
        self.assertNotContains(response, "+79990001122")

    def test_worker_detail_hides_contact_email_public_and_religion(self):
        """P0-03/P0-04 (152-ФЗ): contact/email_public/religion не публичны."""
        contact = "+7 999 555-44-33"
        email_public = "public-contact@example.com"
        religion, _ = Religion.objects.get_or_create(name="Тестовое вероисповедание")
        self.worker.contact = contact
        self.worker.email_public = email_public
        self.worker.religion = religion
        self.worker.save(update_fields=["contact", "email_public", "religion"])

        url = f"/workers/{self.worker.pk}"

        anon = self.client.get(url)
        self.assertEqual(anon.status_code, 200)
        for value in (contact, email_public, religion.name):
            self.assertNotContains(anon, value)
        self.assertContains(anon, CONTACTS_AFTER_RESPONSE_TEXT)

        other = make_profile("other-pub@example.com", role="employer")
        self.client.force_login(other)
        auth = self.client.get(url)
        self.assertEqual(auth.status_code, 200)
        for value in (contact, email_public, religion.name):
            self.assertNotContains(auth, value)
        self.assertContains(auth, CONTACTS_AFTER_RESPONSE_TEXT)

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


LEGACY_PHOTO_URL = "https://cdn.example.com/legacy/photo.jpg"
NEW_AVATAR_URL = "https://cdn.example.com/new/avatar.jpg"


class LegalFallbackTests(TestCase):
    """LEGAL-P0-01: пустой site_pages -> legacy-фолбэк, SitePage -> override."""

    def setUp(self):
        SitePage.objects.filter(pk__in=("privacy", "terms", "safety")).delete()

    def test_privacy_fallback_without_site_page(self):
        response = self.client.get(reverse("core:privacy"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Политика конфиденциальности")
        self.assertContains(response, "1. Общие положения")

    def test_terms_fallback_without_site_page(self):
        response = self.client.get(reverse("core:terms"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Условия использования")
        self.assertContains(response, "5. Правила использования")

    def test_safety_fallback_without_site_page(self):
        response = self.client.get(reverse("core:safety"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Как мы защищаем")
        self.assertContains(response, "Проверенные пользователи")

    def test_site_page_overrides_fallback(self):
        SitePage.objects.create(
            slug="privacy", title="Из БД", content="<p>DB-OVERRIDE</p>"
        )
        response = self.client.get(reverse("core:privacy"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DB-OVERRIDE")
        self.assertNotContains(response, "1. Общие положения")

    def test_unknown_slug_404(self):
        request = RequestFactory().get("/unknown")
        with self.assertRaises(Http404):
            views.legal_page(request, "unknown")


class AvatarFallbackTests(TestCase):
    """AUTH-P1-08: avatar_url приоритетен, legacy photo_url — фолбэк."""

    def setUp(self):
        self.worker = make_profile(
            "worker-avatar@example.com", role="worker",
            avatar_url="", photo_url=LEGACY_PHOTO_URL,
        )

    def test_profile_shows_legacy_photo_when_avatar_empty(self):
        self.client.force_login(self.worker)
        response = self.client.get("/profile")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, LEGACY_PHOTO_URL)

    def test_worker_detail_shows_legacy_photo_when_avatar_empty(self):
        response = self.client.get(f"/workers/{self.worker.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, LEGACY_PHOTO_URL)

    def test_workers_list_shows_legacy_photo_when_avatar_empty(self):
        response = self.client.get("/workers", {"q": self.worker.full_name})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, LEGACY_PHOTO_URL)

    def test_avatar_url_wins_over_legacy_photo(self):
        self.worker.avatar_url = NEW_AVATAR_URL
        self.worker.save(update_fields=["avatar_url"])

        detail = self.client.get(f"/workers/{self.worker.pk}")
        self.assertContains(detail, NEW_AVATAR_URL)
        self.assertNotContains(detail, LEGACY_PHOTO_URL)

        listing = self.client.get("/workers", {"q": self.worker.full_name})
        self.assertContains(listing, NEW_AVATAR_URL)
        self.assertNotContains(listing, LEGACY_PHOTO_URL)

        self.client.force_login(self.worker)
        own = self.client.get("/profile")
        self.assertContains(own, NEW_AVATAR_URL)
        self.assertNotContains(own, LEGACY_PHOTO_URL)
