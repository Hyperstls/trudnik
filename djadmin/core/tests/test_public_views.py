"""Публичные read-only страницы + health."""
import json
import os
import re
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core import views
from core.models import Application, Blacklist, Favorite, Invitation, Job, JobPhoto, JobSkill, Profile, Rating, Religion, SitePage, Skill, UserSkill
from core.storage import resolve_upload_url, save_upload
from core.tests.test_auth import CACHE_LOCMEM, make_profile
from core.tests.test_flows import make_job

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

    def test_active_filter_count(self):
        self.assertEqual(self.client.get("/jobs").context["active_filter_count"], 0)
        skill = Skill.objects.create(name="Фильтр-навык J065", sort_order=1)
        JobSkill.objects.create(job=self.job, skill=skill)
        response = self.client.get("/jobs", {
            "q": "уборка", "payment_max": "5000", "skills": str(skill.pk),
        })
        self.assertEqual(response.context["active_filter_count"], 3)
        self.assertContains(response, 'id="filters-open"')
        self.assertContains(response, "Применить")

    def test_job_detail_og_meta(self):
        response = self.client.get(reverse("core:job_detail", args=[self.job.pk]))
        self.assertContains(response, 'property="og:title"')
        self.assertContains(response, "Уборка территории")
        self.assertContains(response, "Москва")
        self.assertContains(response, 'property="og:image"')
        self.assertContains(response, "/og.png")
        self.assertContains(response, 'name="twitter:image"')

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
        self.assertContains(response, 'id="report-dialog"')
        self.assertContains(response, 'aria-labelledby="report-title"')
        self.assertContains(response, "Отправить жалобу")
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
            rating_type="worker", target_type="employer",
            published_at=timezone.now(),
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
        self.assertContains(response, "Подтверждён")

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
        self.worker.worker_rating = 4.5
        self.worker.worker_ratings_count = 3
        self.worker.desired_payment = 2000
        self.worker.save(update_fields=["worker_rating", "worker_ratings_count", "desired_payment"])
        other = make_profile("worker-cheap-j021@example.com", role="worker")
        other.full_name = "Дешёвый трудник J021"
        other.worker_rating = 1
        other.worker_ratings_count = 3
        other.desired_payment = 100
        other.save(update_fields=["full_name", "worker_rating", "worker_ratings_count", "desired_payment"])
        rated = self.client.get("/workers", {"rating_min": "4"})
        self.assertContains(rated, self.worker.full_name)
        self.assertNotContains(rated, other.full_name)
        paid = self.client.get("/workers", {"payment_from": "1500"})
        self.assertContains(paid, self.worker.full_name)
        self.assertNotContains(paid, other.full_name)

    def test_workers_weighted_rating_sort(self):
        established = make_profile(
            "worker-established@example.com", role="worker",
            full_name="Вес Устоявшийся", worker_rating=4.8, worker_ratings_count=20,
        )
        newcomer = make_profile(
            "worker-newcomer@example.com", role="worker",
            full_name="Вес Новичок", worker_rating=5.0, worker_ratings_count=1,
        )
        response = self.client.get("/workers", {"q": "Вес", "sort": "rating"})
        names = [w.full_name for w in response.context["page"].object_list]
        self.assertLess(names.index(established.full_name), names.index(newcomer.full_name))

    def test_worker_distribution_context(self):
        from core.models import Rating
        now = timezone.now()
        for i, stars in enumerate((5, 5, 4)):
            rater = make_profile("dist-rater-%d@example.com" % i)
            job = make_job(self.employer, work_type="Dist %d" % i)
            Rating.objects.create(
                rated_user=self.worker, rater_user=rater, job=job,
                rating=stars, rating_type="employer", target_type="worker",
                published_at=now,
            )
        response = self.client.get(reverse("core:worker_detail", args=[self.worker.pk]))
        distribution = {row["stars"]: row["count"] for row in response.context["distribution"]}
        self.assertEqual(distribution[5], 2)
        self.assertEqual(distribution[4], 1)
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.worker_ratings_count, 3)

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

    def _accepted_apps(self, count, completed=True):
        for i in range(count):
            job = Job.objects.create(
                employer=self.employer, work_type="Reliable %d" % i,
                organization_name="Приход", status="completed" if completed else "open", city="Москва",
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

    def test_workers_not_reliable_without_completed_jobs(self):
        self._accepted_apps(10, completed=False)
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
            status="open", city="Санкт-Петербург", address="Невский пр., 1",
            payment_amount=1000, lat=60.0, lng=30.0,
            date_time=timezone.now() + timedelta(days=2),
        )
        far = Job.objects.create(
            employer=self.employer, work_type="Far J024", organization_name="Приход",
            status="open", city="Санкт-Петербург", address="Невский пр., 2",
            payment_amount=1000, lat=60.1, lng=30.0,
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

    def test_geo_map_center_rounded(self):
        near, _far = self._geo_jobs()
        with patch.dict(os.environ, {"YANDEX_MAPS_API_KEY": "test-" + "map-key"}):  # pragma: allowlist secret
            with patch("core.views.call_rpc_rows") as rpc:
                rpc.return_value = [{"id": near.pk, "distance_meters": 100}]
                response = self.client.get(
                    "/jobs", {"q": "J024", "lat": "60.012345", "lng": "30.067890", "radius": "2"}
                )
        self.assertEqual(
            response.context["geo_center"],
            {"lat": 60.012, "lng": 30.068, "radius": 2.0},
        )
        self.assertContains(response, 'id="jobs-geo-data"')
        self.assertNotContains(response, "60.012345")

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
        self.assertContains(response, 'id="jobs-map-block"')
        self.assertContains(response, 'id="jobs-map"')
        self.assertContains(response, 'data-api-key="test-key"')
        self.assertContains(response, "js/jobs-map.js")
        # Lazy load: the external API is fetched only after the map is expanded.
        self.assertNotContains(response, "api-maps.yandex.ru")

    def test_jobs_map_absent_without_key(self):
        self._geo_jobs()
        from unittest.mock import patch

        with patch.dict(os.environ, {"YANDEX_MAPS_API_KEY": ""}):
            response = self.client.get("/jobs", {"q": "J024"})
        self.assertNotContains(response, 'id="jobs-map-block"')

    def test_jobs_map_is_below_filters_and_collapsed(self):
        self._geo_jobs()
        from unittest.mock import patch

        with patch.dict(os.environ, {"YANDEX_MAPS_API_KEY": "test-" + "key"}):  # pragma: allowlist secret
            response = self.client.get("/jobs", {"q": "J024"})
        html = response.content.decode()
        self.assertLess(html.index('id="filters-form"'), html.index('id="jobs-map-block"'))
        self.assertLess(html.index('id="jobs-map-block"'), html.index("data-job-id="))
        self.assertIn('id="jobs-map-block" class="jobs-map-block hidden"', html)
        self.assertContains(response, 'id="jobs-map-toggle"')

    def test_jobs_map_points_have_preview_fields(self):
        near, _ = self._geo_jobs()
        response = self.client.get("/jobs", {"q": "J024"})
        point = next(p for p in response.context["map_points"] if p["id"] == str(near.pk))
        self.assertEqual(point["price"], "1000")
        self.assertEqual(point["city"], "Санкт-Петербург")
        self.assertEqual(point["org"], "Приход")
        self.assertTrue(point["when"])

    def test_geo_active_map_auto_opens(self):
        near, _ = self._geo_jobs()
        from unittest.mock import patch

        with patch("core.views.call_rpc_rows") as rpc:
            rpc.return_value = [{"id": near.pk, "distance_meters": 100}]
            response = self.client.get(
                "/jobs", {"q": "J024", "lat": "60.0", "lng": "30.0", "radius": "2"}
            )
        self.assertContains(response, 'data-geo-active="true"')

    def test_jobs_map_skips_jobs_without_coords(self):
        Job.objects.create(
            employer=self.employer, work_type="NoCoord J025", organization_name="Приход",
            status="open", city="Москва", payment_amount=1000,
            date_time=timezone.now() + timedelta(days=2),
        )
        response = self.client.get("/jobs", {"q": "J025"})
        self.assertContains(response, "NoCoord J025")
        self.assertEqual(response.context["map_points"], [])

    def test_jobs_map_skips_remote_without_address(self):
        Job.objects.create(
            employer=self.employer, work_type="Remote J028", organization_name="Приход",
            status="open", city="Москва", address="", payment_amount=1000,
            lat=55.75, lng=37.61,
            date_time=timezone.now() + timedelta(days=2),
        )
        response = self.client.get("/jobs", {"q": "J028"})
        self.assertContains(response, "Remote J028")
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
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Disallow: /admin/")
        self.assertContains(response, "Sitemap: https://xn--d1aigknli.xn--p1ai/sitemap.xml")


LEGACY_PHOTO_URL = "https://cdn.example.com/legacy/photo.jpg"
NEW_AVATAR_URL = "https://cdn.example.com/new/avatar.jpg"


class SecurityHeadersTests(TestCase):
    def test_public_csp_nonce(self):
        response = self.client.get(reverse("core:jobs"))
        csp = response["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("'strict-dynamic'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        self.assertContains(response, 'nonce="%s"' % nonce)
        self.assertIn("geolocation=(self)", response["Permissions-Policy"])

    def test_admin_csp_relaxed(self):
        admin = make_profile("csp-admin@example.com", role="admin")
        self.client.force_login(admin)
        response = self.client.get("/admin/")
        csp = response["Content-Security-Policy"]
        self.assertIn("script-src 'self' 'unsafe-inline'", csp)
        self.assertIn("frame-ancestors 'none'", csp)

    def test_all_templates_have_script_nonce(self):
        root = settings.BASE_DIR / "core" / "templates"
        for path in root.rglob("*.html"):
            content = path.read_text(encoding="utf-8")
            self.assertNotRegex(
                content, r"<script(?![^>]*\bnonce=)[^>]*>", str(path)
            )


class LegalFallbackTests(TestCase):
    """LEGAL-P0-01: пустой site_pages -> legacy-фолбэк, SitePage -> override."""

    def setUp(self):
        SitePage.objects.filter(pk__in=("privacy", "terms", "safety", "faq")).delete()

    def test_privacy_fallback_without_site_page(self):
        response = self.client.get(reverse("core:privacy"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Политика конфиденциальности")
        self.assertContains(response, "1. Общие положения")
        self.assertContains(response, "версия 1.2")
        self.assertContains(response, "10.5. Черновик задания")
        self.assertContains(response, "14.5. Обезличенная статистика")
        self.assertContains(response, "Яндекс.Карты")

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

    def test_faq_site_page_overrides_template(self):
        fallback = self.client.get(reverse("core:faq"))
        self.assertContains(fallback, "Вопросы и ответы")
        SitePage.objects.create(
            slug="faq", title="FAQ из БД", content="<p>FAQ-DB</p>"
        )
        response = self.client.get(reverse("core:faq"))
        self.assertContains(response, "FAQ из БД")
        self.assertContains(response, "FAQ-DB")

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


class EmployersCatalogTests(TestCase):
    """J031/P2-13: каталог работодателей = пользователи с открытыми заданиями."""

    def setUp(self):
        self.viewer = make_profile("emp-cat-viewer@example.com")
        self.client.force_login(self.viewer)

    def _employer(self, email, name, city="", role="employer"):
        return make_profile(email, full_name=name, city=city, role=role)

    def test_multirole_user_with_open_job_visible(self):
        user = self._employer("emp-cat-multi@example.com", "Мультироль J031", role="worker")
        make_job(user, work_type="Открытое J031")
        response = self.client.get(reverse("core:employers"))
        self.assertContains(response, "Мультироль J031")

    def test_user_without_open_job_hidden(self):
        user = self._employer("emp-cat-closed@example.com", "Без открытых J031")
        make_job(user, status="completed")
        response = self.client.get(reverse("core:employers"))
        self.assertNotContains(response, "Без открытых J031")

    def test_city_filter_and_name_sort(self):
        alpha = self._employer("emp-cat-alpha@example.com", "Альфа J031", city="Москва")
        beta = self._employer("emp-cat-beta@example.com", "Бета J031", city="Казань")
        make_job(alpha)
        make_job(beta)
        city_response = self.client.get(reverse("core:employers"), {"city": "Казань"})
        self.assertContains(city_response, "Бета J031")
        self.assertNotContains(city_response, "Альфа J031")
        sorted_response = self.client.get(reverse("core:employers"), {"sort": "name"})
        names = [
            p.full_name for p in sorted_response.context["page"].object_list
            if p.full_name.endswith("J031")
        ]
        self.assertEqual(names, ["Альфа J031", "Бета J031"])

    def test_jobs_count_sort(self):
        one = self._employer("emp-cat-one@example.com", "Одно J031")
        many = self._employer("emp-cat-many@example.com", "Много J031")
        make_job(one, work_type="Одно-1")
        make_job(many, work_type="Много-1")
        make_job(many, work_type="Много-2")
        response = self.client.get(reverse("core:employers"), {"sort": "jobs_count"})
        names = [p.full_name for p in response.context["page"].object_list]
        self.assertLess(names.index("Много J031"), names.index("Одно J031"))

    def test_blacklisted_employer_hidden(self):
        user = self._employer("emp-cat-block@example.com", "Блокировщик J031")
        make_job(user)
        Blacklist.objects.create(user=user, blocked_user=self.viewer)
        response = self.client.get(reverse("core:employers"))
        self.assertNotContains(response, "Блокировщик J031")

    def test_favorite_toggle_and_state(self):
        user = self._employer("emp-cat-fav@example.com", "Избранный J031")
        make_job(user)
        url = reverse("core:employer_favorite_toggle", args=[user.pk])
        self.client.post(url)
        self.assertTrue(Favorite.objects.filter(
            user=self.viewer, target=user, favorite_type="employer"
        ).exists())
        listing = self.client.get(reverse("core:employers"))
        self.assertContains(listing, "Убрать из избранного")
        self.client.post(url)
        self.assertFalse(Favorite.objects.filter(
            user=self.viewer, target=user, favorite_type="employer"
        ).exists())

    def test_pagination_preserves_sort(self):
        for index in range(21):
            user = Profile.objects.create(
                email="emp-page-%02d@example.com" % index,
                password="x", full_name="Страница %02d J031" % index, role="worker",
            )
            make_job(user, work_type="Пагинация-%02d" % index)
        response = self.client.get(reverse("core:employers"), {"sort": "name"})
        content = response.content.decode()
        self.assertIn("page=2", content)
        self.assertIn("sort=name", content)


class EmployerDetailTests(TestCase):
    """J032/P2-13: карточка работодателя — open-задания, blacklist, отклик."""

    def setUp(self):
        self.viewer = make_profile("emp-det-viewer@example.com")
        self.client.force_login(self.viewer)

    def _employer(self, email, name, role="employer"):
        return make_profile(email, full_name=name, role=role)

    def test_multirole_employer_detail_accessible(self):
        user = self._employer("emp-det-multi@example.com", "Мультироль-карточка J032", role="worker")
        make_job(user, work_type="Открытое J032")
        response = self.client.get(reverse("core:employer_detail", args=[user.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Открытое J032")

    def test_detail_shows_only_open_jobs(self):
        user = self._employer("emp-det-open@example.com", "Только открытые J032")
        make_job(user, work_type="Активное J032")
        make_job(user, work_type="Завершённое J032", status="completed")
        response = self.client.get(reverse("core:employer_detail", args=[user.pk]))
        self.assertContains(response, "Активное J032")
        self.assertNotContains(response, "Завершённое J032")

    def test_detail_marks_applied_job(self):
        user = self._employer("emp-det-apply@example.com", "Отклик J032")
        job = make_job(user, work_type="С откликом J032")
        Application.objects.create(job=job, worker=self.viewer, status="pending")
        response = self.client.get(reverse("core:employer_detail", args=[user.pk]))
        self.assertContains(response, "Отклик отправлен")

    def test_detail_blocked_by_employer_returns_404(self):
        user = self._employer("emp-det-block@example.com", "Блок J032")
        make_job(user)
        Blacklist.objects.create(user=user, blocked_user=self.viewer)
        response = self.client.get(reverse("core:employer_detail", args=[user.pk]))
        self.assertEqual(response.status_code, 404)

    def test_detail_favorite_state(self):
        user = self._employer("emp-det-fav@example.com", "Избранный-карточка J032")
        make_job(user)
        Favorite.objects.create(user=self.viewer, target=user, favorite_type="employer")
        response = self.client.get(reverse("core:employer_detail", args=[user.pk]))
        self.assertContains(response, "В избранном")

    def test_detail_ratings_only_employer_target(self):
        user = self._employer("emp-det-rate@example.com", "Оценки J032")
        job = make_job(user, status="completed")
        Rating.objects.create(
            rated_user=user, rater_user=self.viewer, job=job, rating=5,
            comment="Отзыв о работодателе J032",
            rating_type="worker", target_type="employer",
            published_at=timezone.now(),
        )
        Rating.objects.create(
            rated_user=self.viewer, rater_user=user, job=job, rating=4,
            comment="Оценка работнику J032",
            rating_type="employer", target_type="worker",
            published_at=timezone.now(),
        )
        response = self.client.get(reverse("core:employer_detail", args=[user.pk]))
        self.assertContains(response, "Отзыв о работодателе J032")
        self.assertNotContains(response, "Оценка работнику J032")


class JobDetailChatTrustTests(TestCase):
    def setUp(self):
        self.employer = make_profile("detail-chat-emp@example.com", role="employer")
        self.worker = make_profile("detail-chat-worker@example.com", role="worker")
        self.job = make_job(self.employer, work_type="Чат J047")
        self.app = Application.objects.create(
            job=self.job, worker=self.worker, status="accepted"
        )

    def test_accepted_has_chat_and_trust(self):
        self.client.force_login(self.worker)
        response = self.client.get(reverse("core:job_detail", args=[self.job.pk]))
        self.assertContains(response, reverse("core:chat_room", args=[self.app.pk]))
        self.assertContains(response, "Написать в чат")
        self.assertContains(response, "Правила безопасности")
        self.assertContains(response, reverse("core:safety"))

    def test_pending_has_no_chat_button(self):
        self.app.status = "pending"
        self.app.save(update_fields=["status"])
        self.client.force_login(self.worker)
        response = self.client.get(reverse("core:job_detail", args=[self.job.pk]))
        self.assertNotContains(response, "Написать в чат")


class GlobalSearchTests(TestCase):
    def test_search_page_groups_results(self):
        employer = make_profile("search-emp@example.com", role="employer")
        worker = make_profile(
            "search-worker@example.com", role="worker",
            full_name="Уборщица Поискова", city="Москва",
        )
        make_job(employer, work_type="Поиск уборки", city="Москва")
        response = self.client.get(reverse("core:search"), {"q": "убор"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Поиск уборки")
        self.assertContains(response, worker.full_name)
        self.assertContains(response, "Найдено:")

    def test_empty_query_shows_prompt(self):
        response = self.client.get(reverse("core:search"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ищите задания")

    def test_short_query_shows_hint(self):
        response = self.client.get(reverse("core:search"), {"q": "у"})
        self.assertContains(response, "минимум 2 символа")

    def test_employers_are_shown_only_to_authenticated(self):
        employer = make_profile(
            "search-employer-private@example.com", role="employer",
            full_name="Работодатель Поиска",
        )
        make_job(employer)
        anon = self.client.get(reverse("core:search"), {"q": "Работодатель"})
        self.assertNotContains(anon, employer.full_name)
        user = make_profile("search-viewer@example.com")
        self.client.force_login(user)
        auth = self.client.get(reverse("core:search"), {"q": "Работодатель"})
        self.assertContains(auth, employer.full_name)
        self.assertContains(auth, "Работодатели")

    def test_header_search_points_to_global_page(self):
        response = self.client.get(reverse("core:jobs"))
        self.assertContains(response, reverse("core:search"))


class JobDetailGeoTests(TestCase):
    def setUp(self):
        self.employer = make_profile("detail-geo-emp@example.com", role="employer")
        self.job = Job.objects.create(
            employer=self.employer, work_type="Офлайн J050", organization_name="Приход",
            status="open", address="Москва, Тверская 1", city="Москва",
            lat=55.765, lng=37.605,
            date_time=timezone.now() + timedelta(days=2),
        )

    def test_detail_shows_address_map_and_route_with_key(self):
        with patch.dict(os.environ, {"YANDEX_MAPS_API_KEY": "test-" + "key"}):  # pragma: allowlist secret  # pragma: allowlist secret
            response = self.client.get(reverse("core:job_detail", args=[self.job.pk]))
        self.assertContains(response, "Москва, Тверская 1")
        self.assertContains(response, 'id="job-detail-map"')
        self.assertContains(response, "api-maps.yandex.ru")
        self.assertContains(response, "Открыть на карте")
        self.assertContains(response, "Маршрут")
        self.assertContains(response, "Карта показывает адрес задания")

    def test_detail_without_key_has_external_map_links(self):
        with patch.dict(os.environ, {"YANDEX_MAPS_API_KEY": ""}):
            response = self.client.get(reverse("core:job_detail", args=[self.job.pk]))
        self.assertNotContains(response, 'id="job-detail-map"')
        self.assertContains(response, "Открыть на карте")
        self.assertContains(response, "Маршрут")

    def test_detail_city_only_shows_city_and_search_link(self):
        self.job.address = ""
        self.job.save(update_fields=["address"])
        response = self.client.get(reverse("core:job_detail", args=[self.job.pk]))
        self.assertContains(response, "Москва")
        self.assertContains(response, "Найти город")
        self.assertNotContains(response, 'id="job-detail-map"')

    def test_detail_address_without_coords_has_search_link(self):
        self.job.lat = None
        self.job.lng = None
        self.job.save(update_fields=["lat", "lng"])
        response = self.client.get(reverse("core:job_detail", args=[self.job.pk]))
        self.assertContains(response, "Найти адрес")
        self.assertNotContains(response, 'id="job-detail-map"')


class GeoPrivacyTests(TestCase):
    def test_geo_set_rounds_and_stores_in_session_not_url(self):
        from unittest.mock import patch

        with patch("core.views.call_rpc_rows") as rpc:
            rpc.return_value = []
            response = self.client.post(
                reverse("core:jobs_geo_set"),
                {"lat": "60.12345", "lng": "30.54321", "radius": "2",
                 "next": "/jobs?geo=1&radius=2"},
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(self.client.session["geo_lat"], 60.123)
            self.assertEqual(self.client.session["geo_lng"], 30.543)
            self.assertEqual(self.client.session["geo_radius"], 2.0)
            listing = self.client.get("/jobs", {"geo": "1", "radius": "2"})
        rpc.assert_called_once_with("nearby_jobs", 60.123, 30.543, 2000.0)
        content = listing.content.decode()
        self.assertNotIn("lat=60.123", content)
        self.assertNotIn("lng=30.543", content)
        self.assertIn("geo=1", content)
        self.assertNotIn("geolocationControl", content)

    def test_geo_clear_removes_session(self):
        self.client.post(
            reverse("core:jobs_geo_set"),
            {"lat": "60.0", "lng": "30.0", "radius": "2", "next": "/jobs"},
        )
        self.assertIn("geo_lat", self.client.session)
        self.client.post(
            reverse("core:jobs_geo_set"), {"clear": "1", "next": "/jobs"}
        )
        self.assertNotIn("geo_lat", self.client.session)
        self.assertNotIn("geo_lng", self.client.session)

    def test_geo_forms_are_not_nested(self):
        response = self.client.get(reverse("core:jobs"))
        content = response.content.decode()
        start = content.index('id="filters-form"')
        end = content.index("</form>", start)
        self.assertNotIn('id="geo-form"', content[start:end])
        self.assertIn('id="geo-clear-form"', content)


class WorkerReportModalTests(TestCase):
    def test_worker_detail_has_report_modal(self):
        viewer = make_profile("report-modal-viewer@example.com")
        target = make_profile("report-modal-target@example.com", role="worker")
        self.client.force_login(viewer)
        response = self.client.get(reverse("core:worker_detail", args=[target.pk]))
        self.assertContains(response, 'id="report-dialog-worker"')
        self.assertContains(response, 'aria-labelledby="report-worker-title"')
        self.assertContains(response, reverse("core:report_user", args=[target.pk]))
        self.assertContains(response, "Отправить жалобу")


@override_settings(
    DEBUG=False,
    ALLOWED_HOSTS=["testserver", "xn--d1aigknli.xn--p1ai", "trudnik-hyperstls.msk1.amvera.tech"],
    CANONICAL_HOST="xn--d1aigknli.xn--p1ai",
)
class CanonicalHostTests(TestCase):
    def test_noncanonical_get_redirects_with_query(self):
        response = self.client.get(
            "/jobs?q=test", HTTP_HOST="trudnik-hyperstls.msk1.amvera.tech"
        )
        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response["Location"],
            "https://xn--d1aigknli.xn--p1ai/jobs?q=test",
        )

    def test_noncanonical_post_redirects_308(self):
        response = self.client.post(
            "/jobs", HTTP_HOST="trudnik-hyperstls.msk1.amvera.tech"
        )
        self.assertEqual(response.status_code, 308)
        self.assertEqual(
            response["Location"], "https://xn--d1aigknli.xn--p1ai/jobs"
        )

    def test_health_is_exempt(self):
        response = self.client.get(
            "/health", HTTP_HOST="trudnik-hyperstls.msk1.amvera.tech"
        )
        self.assertEqual(response.status_code, 200)

    def test_canonical_host_is_not_redirected(self):
        response = self.client.get(
            "/jobs", HTTP_HOST="xn--d1aigknli.xn--p1ai"
        )
        self.assertEqual(response.status_code, 200)

    def test_social_meta_present(self):
        response = self.client.get("/jobs")
        self.assertContains(response, 'rel="canonical"')
        self.assertContains(response, "og:image")
        self.assertContains(response, "og-preview.png")
        self.assertContains(response, 'name="twitter:card"')


class AppDownloadTests(TestCase):
    def test_app_page_and_apk(self):
        page = self.client.get(reverse("core:app_download"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Скачать APK")
        self.assertContains(page, "Android")
        self.assertContains(page, "iPhone")
        apk = self.client.get(reverse("core:download_apk"))
        self.assertEqual(apk.status_code, 200)
        self.assertEqual(
            apk["Content-Type"], "application/vnd.android.package-archive"
        )
        self.assertIn("attachment", apk["Content-Disposition"])

    def test_service_worker_cache_version(self):
        sw = (settings.BASE_DIR.parent / "static" / "sw.js").read_text(encoding="utf-8")
        self.assertIn("trudnik-v17", sw)

    def test_pwa_install_prompt_markup_and_script(self):
        response = self.client.get(reverse("core:jobs"))
        self.assertContains(response, 'id="install-prompt"')
        self.assertContains(response, 'id="install-action"')
        self.assertContains(response, 'id="install-help"')
        js = (settings.BASE_DIR.parent / "static" / "js" / "install-prompt.js").read_text(encoding="utf-8")
        self.assertIn("beforeinstallprompt", js)
        self.assertIn("trudnik-install-dismissed", js)
        self.assertIn("trudnik-install-installed", js)



class GeoSuggestProxyTests(TestCase):
    def setUp(self):
        self.user = make_profile("geo-suggest@example.com")
        self.client.force_login(self.user)

    def test_proxy_normalizes_results(self):
        payload = {
            "results": [{
                "title": {"text": "Тверская улица, 1"},
                "subtitle": {"text": "Москва"},
                "address": {"formatted_address": "Москва, Тверская улица, 1"},
            }]
        }

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return json.dumps(payload).encode()

        with patch.dict(os.environ, {"YANDEX_SUGGEST_API_KEY": "test-suggest"}):  # pragma: allowlist secret
            with patch("core.views_geo.urlopen", return_value=FakeResponse()):
                response = self.client.post(
                    reverse("core:geo_suggest"),
                    data=json.dumps({"q": "Тверская 1", "city": "Москва"}),
                    content_type="application/json",
                )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["results"][0]["displayName"], "Москва, Тверская улица, 1")
        self.assertEqual(data["results"][0]["value"], "Москва, Тверская улица, 1")

    def test_proxy_requires_login_and_post(self):
        self.client.logout()
        self.assertEqual(self.client.post(reverse("core:geo_suggest"), data="{}", content_type="application/json").status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("core:geo_suggest")).status_code, 405)

    def test_proxy_rejects_non_string_query(self):
        response = self.client.post(
            reverse("core:geo_suggest"),
            data=json.dumps({"q": 123}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])

    def test_proxy_rejects_bad_json(self):
        response = self.client.post(
            reverse("core:geo_suggest"), data="{", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    def test_proxy_without_key_returns_empty(self):
        with patch.dict(os.environ, {"YANDEX_SUGGEST_API_KEY": ""}):
            response = self.client.post(
                reverse("core:geo_suggest"),
                data=json.dumps({"q": "Москва"}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])

    def test_form_does_not_expose_suggest_key(self):
        with patch.dict(os.environ, {"YANDEX_MAPS_API_KEY": "test-" + "key"}):  # pragma: allowlist secret
            response = self.client.get(reverse("core:job_create"))
        self.assertNotContains(response, "suggest_apikey")


@override_settings(CACHES=CACHE_LOCMEM)
class GeoGeocodeProxyTests(TestCase):
    """Серверный Geocoder API: не зависит от прав JavaScript-ключа."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = make_profile("geo-geocode@example.com")
        self.client.force_login(self.user)

    def _fake_response(self, payload):
        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return json.dumps(payload).encode()
        return FakeResponse()

    def _payload(self):
        return {"response": {"GeoObjectCollection": {"featureMember": [{
            "GeoObject": {
                "metaDataProperty": {"GeocoderMetaData": {
                    "precision": "exact",
                    "text": "Россия, Москва, Тверская улица, 7",
                    "Address": {
                        "formatted": "Россия, Москва, Тверская улица, 7",
                        "components": [
                            {"kind": "country", "name": "Россия"},
                            {"kind": "locality", "name": "Москва"},
                        ],
                    },
                }},
                "Point": {"pos": "37.609429 55.765252"},
            }
        }]}}}

    def test_forward_geocode_normalizes_result(self):
        with patch.dict(os.environ, {"YANDEX_GEOCODER_KEY": "test-geo", "YANDEX_MAPS_API_KEY": ""}):  # pragma: allowlist secret
            with patch("core.views_geo.urlopen", return_value=self._fake_response(self._payload())):
                response = self.client.post(
                    reverse("core:geo_geocode"),
                    data=json.dumps({"mode": "forward", "text": "Тверская 7"}),
                    content_type="application/json",
                    REMOTE_ADDR="10.11.0.1",
                )
        self.assertEqual(response.status_code, 200)
        item = response.json()["results"][0]
        self.assertEqual(item["displayName"], "Россия, Москва, Тверская улица, 7")
        self.assertEqual(item["city"], "Москва")
        self.assertAlmostEqual(item["lat"], 55.765252)
        self.assertAlmostEqual(item["lng"], 37.609429)

    def test_reverse_geocode_sends_longitude_latitude(self):
        from urllib.parse import parse_qs, urlparse
        captured = {}

        def fake_urlopen(request, timeout=0):
            captured["url"] = request.full_url
            captured["referer"] = request.get_header("Referer")
            return self._fake_response(self._payload())

        with patch.dict(os.environ, {
            "YANDEX_GEOCODER_KEY": "test-geo",
            "YANDEX_MAPS_API_KEY": "",
            "WORKER_SITE_URL": "https://example.test",
        }):  # pragma: allowlist secret
            with patch("core.views_geo.urlopen", side_effect=fake_urlopen):
                response = self.client.post(
                    reverse("core:geo_geocode"),
                    data=json.dumps({"mode": "reverse", "lat": 55.75, "lng": 37.6}),
                    content_type="application/json",
                    REMOTE_ADDR="10.11.0.2",
                )
        self.assertEqual(response.status_code, 200)
        query = parse_qs(urlparse(captured["url"]).query)
        self.assertEqual(query["geocode"], ["37.600000,55.750000"])
        self.assertEqual(captured["referer"], "https://example.test/")
        self.assertAlmostEqual(response.json()["results"][0]["lat"], 55.765252)

    def test_geocode_requires_login_and_post(self):
        self.client.logout()
        self.assertEqual(
            self.client.post(reverse("core:geo_geocode"), data="{}", content_type="application/json").status_code,
            302,
        )
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("core:geo_geocode")).status_code, 405)

    def test_geocode_without_key_reports_disabled(self):
        with patch.dict(os.environ, {"YANDEX_GEOCODER_KEY": "", "YANDEX_MAPS_API_KEY": ""}):
            response = self.client.post(
                reverse("core:geo_geocode"),
                data=json.dumps({"mode": "forward", "text": "Москва Тверская"}),
                content_type="application/json",
                REMOTE_ADDR="10.11.0.3",
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["enabled"])
        self.assertEqual(response.json()["results"], [])

    def test_geocode_rejects_bad_coords(self):
        response = self.client.post(
            reverse("core:geo_geocode"),
            data=json.dumps({"mode": "reverse", "lat": 999, "lng": 37.6}),
            content_type="application/json",
            REMOTE_ADDR="10.11.0.4",
        )
        self.assertEqual(response.status_code, 400)

    def test_geocode_upstream_failure_is_soft(self):
        with patch.dict(os.environ, {"YANDEX_GEOCODER_KEY": "test-geo", "YANDEX_MAPS_API_KEY": ""}):  # pragma: allowlist secret
            with patch("core.views_geo.urlopen", side_effect=OSError("boom")):
                response = self.client.post(
                    reverse("core:geo_geocode"),
                    data=json.dumps({"mode": "forward", "text": "Москва Ленина"}),
                    content_type="application/json",
                    REMOTE_ADDR="10.11.0.5",
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])
        self.assertEqual(response.json()["error"], "upstream")

    def test_geocode_falls_back_to_legacy_endpoint(self):
        from urllib.error import HTTPError
        calls = []

        def fake_urlopen(request, timeout=0):
            calls.append(request.full_url)
            if len(calls) == 1:
                raise HTTPError(request.full_url, 403, "Forbidden", {}, None)
            return self._fake_response(self._payload())

        with patch.dict(os.environ, {"YANDEX_GEOCODER_KEY": "test-geo", "YANDEX_MAPS_API_KEY": ""}):  # pragma: allowlist secret
            with patch("core.views_geo.urlopen", side_effect=fake_urlopen):
                response = self.client.post(
                    reverse("core:geo_geocode"),
                    data=json.dumps({"mode": "forward", "text": "Москва Арбат"}),
                    content_type="application/json",
                    REMOTE_ADDR="10.11.0.6",
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 2)
        self.assertIn("/v1?", calls[0])
        self.assertIn("/1.x/", calls[1])
        self.assertAlmostEqual(response.json()["results"][0]["lat"], 55.765252)

    def test_v1_components_capitalized_city(self):
        payload = self._payload()
        address = payload["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"][
            "metaDataProperty"]["GeocoderMetaData"]["Address"]
        address["Components"] = address.pop("components")
        with patch.dict(os.environ, {"YANDEX_GEOCODER_KEY": "test-geo", "YANDEX_MAPS_API_KEY": ""}):  # pragma: allowlist secret
            with patch("core.views_geo.urlopen", return_value=self._fake_response(payload)):
                response = self.client.post(
                    reverse("core:geo_geocode"),
                    data=json.dumps({"mode": "forward", "text": "Новосибирск Красный"}),
                    content_type="application/json",
                    REMOTE_ADDR="10.11.0.7",
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["city"], "Москва")

    def test_job_form_uses_server_geocoder(self):
        with patch.dict(os.environ, {"YANDEX_MAPS_API_KEY": "test-" + "key"}):  # pragma: allowlist secret
            response = self.client.get(reverse("core:job_create"))
        self.assertContains(response, "/api/geo/geocode")
        self.assertNotContains(response, "searchControl")


class WorkersNavigationTests(TestCase):
    def test_workers_active_filter_count(self):
        self.assertEqual(self.client.get(reverse("core:workers")).context["active_filter_count"], 0)
        worker = make_profile("filter-worker@example.com", role="worker", city="Москва")
        skill = Skill.objects.create(name="Фильтр-навык J085", sort_order=1)
        UserSkill.objects.create(user=worker, skill=skill)
        response = self.client.get(reverse("core:workers"), {
            "q": "Москва", "rating_min": "4", "skills": str(skill.pk),
        })
        self.assertEqual(response.context["active_filter_count"], 3)
        self.assertContains(response, 'id="filters-open"')

    def test_worker_card_has_actions_and_details(self):
        employer = make_profile("worker-card-emp@example.com", email_verified=True)
        worker = make_profile(
            "worker-card@example.com", role="worker", city="Москва",
            desired_payment=1500, bio="Мастер",
        )
        skill = Skill.objects.create(name="Карточка-навык", sort_order=1)
        UserSkill.objects.create(user=worker, skill=skill)
        Favorite.objects.create(user=employer, target=worker, favorite_type="worker")
        make_job(employer)
        self.client.force_login(employer)
        response = self.client.get(reverse("core:workers"), {"q": "Мастер"})
        self.assertContains(response, "Пригласить")
        self.assertContains(response, "Профиль")
        self.assertContains(response, "В избранном")
        self.assertContains(response, "Карточка-навык")
        self.assertContains(response, "1500")

    def test_workers_mobile_links(self):
        response = self.client.get(reverse("core:jobs"))
        self.assertContains(response, reverse("core:workers"))
        self.assertContains(response, "Трудники")
        user = make_profile("workers-link@example.com")
        self.client.force_login(user)
        response = self.client.get(reverse("core:jobs"))
        self.assertContains(response, 'role="menuitem"')
        self.assertContains(response, reverse("core:workers"))


class SavedSearchTests(TestCase):
    def setUp(self):
        self.user = make_profile("saved-search@example.com", email_verified=True)
        self.client.force_login(self.user)

    def test_save_list_dedupe_delete(self):
        skill = Skill.objects.create(name="Сохранённый навык", sort_order=1)
        payload = {"q": "уборка", "city": "Москва", "skills": str(skill.pk)}
        response = self.client.post(reverse("core:save_search"), payload)
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(len(self.user.notification_prefs["saved_searches"]), 1)
        page = self.client.get(reverse("core:jobs"))
        self.assertContains(page, "Москва")
        self.assertContains(page, "skills=" + str(skill.pk))
        # повтор не создаёт дубль
        self.client.post(reverse("core:save_search"), payload)
        self.user.refresh_from_db()
        self.assertEqual(len(self.user.notification_prefs["saved_searches"]), 1)
        search_id = self.user.notification_prefs["saved_searches"][0]["id"]
        self.client.post(reverse("core:delete_search", args=[search_id]))
        self.user.refresh_from_db()
        self.assertEqual(self.user.notification_prefs["saved_searches"], [])

    def test_saved_search_notify_toggle(self):
        skill = Skill.objects.create(name="Toggle навык", sort_order=1)
        self.client.post(reverse("core:save_search"), {"q": "toggle", "skills": str(skill.pk)})
        self.user.refresh_from_db()
        item = self.user.notification_prefs["saved_searches"][0]
        self.assertTrue(item["notify"])
        self.client.post(reverse("core:toggle_search", args=[item["id"]]))
        self.user.refresh_from_db()
        self.assertFalse(self.user.notification_prefs["saved_searches"][0]["notify"])
        self.client.post(reverse("core:toggle_search", args=[item["id"]]))
        self.user.refresh_from_db()
        self.assertTrue(self.user.notification_prefs["saved_searches"][0]["notify"])

    def test_empty_search_not_saved(self):
        self.client.post(reverse("core:save_search"), {})
        self.user.refresh_from_db()
        self.assertEqual(self.user.notification_prefs.get("saved_searches", []), [])

    def test_save_search_rate_limited(self):
        from django.core.cache import cache
        cache.clear()
        for _ in range(20):
            self.client.post(reverse("core:save_search"), {"q": "rate-limit"})
        response = self.client.post(reverse("core:save_search"), {"q": "rate-limit"})
        self.assertEqual(response.status_code, 302)

    def test_saved_search_requires_login(self):
        self.client.logout()
        response = self.client.post(reverse("core:save_search"), {"q": "x"})
        self.assertEqual(response.status_code, 302)


class JobsFilterMarkupTests(TestCase):
    def test_job_type_filter_is_custom_radio_not_select(self):
        user = make_profile("filter-markup@example.com", email_verified=True)
        self.client.force_login(user)
        response = self.client.get(reverse("core:jobs"))
        self.assertNotContains(response, '<select name="filter"')
        self.assertContains(response, 'name="filter" value="new"')
        self.assertContains(response, 'name="filter" value="applied"')
        self.assertContains(response, "Все задания")


class ServerJobDraftTests(TestCase):
    def setUp(self):
        self.user = make_profile("server-draft@example.com", email_verified=True)
        self.client.force_login(self.user)

    def test_save_get_delete_and_sanitize(self):
        payload = {
            "saved_at": int(timezone.now().timestamp() * 1000),
            "fields": {
                "work_type": ["Уборка"],
                "address": ["Москва"],
                "lat": ["55.7"],
                "csrfmiddlewaretoken": ["secret"],
                "skills": ["a", "b"],
            },
        }
        response = self.client.post(
            reverse("core:job_draft_api"), data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        stored = self.user.notification_prefs["job_draft"]
        self.assertEqual(stored["fields"]["work_type"], ["Уборка"])
        self.assertNotIn("lat", stored["fields"])
        self.assertNotIn("csrfmiddlewaretoken", stored["fields"])
        got = self.client.get(reverse("core:job_draft_api")).json()["draft"]
        self.assertEqual(got["fields"]["address"], ["Москва"])
        self.client.delete(reverse("core:job_draft_api"))
        self.user.refresh_from_db()
        self.assertNotIn("job_draft", self.user.notification_prefs)

    def test_expired_draft_removed(self):
        old = int((timezone.now().timestamp() - 31 * 86400) * 1000)
        prefs = dict(self.user.notification_prefs or {})
        prefs["job_draft"] = {"saved_at": old, "fields": {"work_type": ["Old"]}}
        Profile.objects.filter(pk=self.user.pk).update(notification_prefs=prefs)
        self.assertIsNone(self.client.get(reverse("core:job_draft_api")).json()["draft"])

    def test_draft_rate_limited(self):
        payload = json.dumps({"fields": {"work_type": ["x"]}, "saved_at": 1})
        for _ in range(60):
            response = self.client.post(
                reverse("core:job_draft_api"), data=payload,
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("core:job_draft_api"), data=payload,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 429)

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("core:job_draft_api")).status_code, 302)


class EmployersNavigationTests(TestCase):
    def test_employer_links_are_visible(self):
        jobs = self.client.get(reverse("core:jobs"))
        self.assertContains(jobs, reverse("core:employers"))
        workers = self.client.get(reverse("core:workers"))
        self.assertContains(workers, reverse("core:employers"))
        user = make_profile("employers-nav@example.com", email_verified=True)
        employer = make_profile("employers-card@example.com", role="employer", email_verified=True)
        make_job(employer)
        self.client.force_login(user)
        employers = self.client.get(reverse("core:employers"))
        self.assertContains(employers, reverse("core:workers"))
        self.assertContains(employers, "Задания")


class JobOgImageTests(TestCase):
    def test_generated_og_image(self):
        employer = make_profile("og-employer@example.com", role="employer")
        job = make_job(
            employer, work_type="Покраска забора", city="Москва",
            payment_amount=2500, address="ул. Ленина, 1",
        )
        response = self.client.get(reverse("core:job_og_image", args=[job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(response.content), 5000)
        self.assertIn("max-age=3600", response["Cache-Control"])

    def test_private_job_og_is_hidden(self):
        employer = make_profile("og-private@example.com", role="employer")
        job = make_job(employer, status="draft")
        response = self.client.get(reverse("core:job_og_image", args=[job.pk]))
        self.assertEqual(response.status_code, 404)

    def test_detail_page_uses_generated_og(self):
        employer = make_profile("og-detail@example.com", role="employer")
        job = make_job(employer, work_type="OG detail")
        response = self.client.get(reverse("core:job_detail", args=[job.pk]))
        self.assertContains(response, "/jobs/%s/og.png" % job.pk)
