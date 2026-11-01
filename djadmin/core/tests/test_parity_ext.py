"""Паритет-остаток: 152-ФЗ, prefs, загрузки, работодатели, оценки, bulk."""
import json
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from core.models import Application, Favorite, JobFavorite, JobPhoto, Notification, Profile, Rating, UserReport
from core.tests.test_auth import make_profile
from core.tests.test_flows import make_job


class ExportDataTests(TestCase):
    def setUp(self):
        self.user = make_profile("exp-user@example.com")
        self.client.force_login(self.user)

    def test_export_json_sections_no_password(self):
        make_job(self.user, work_type="Экспорт-задание")
        response = self.client.get(reverse("core:export_data"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        data = json.loads(response.content)
        for key in ("exported_at", "user_id", "legal_basis", "profile", "skills",
                    "applications_as_worker", "applications_as_employer",
                    "favorites", "blacklist", "ratings_given", "ratings_received"):
            self.assertIn(key, data)
        self.assertNotIn("password", data["profile"])
        self.assertEqual(data["profile"]["email"], "exp-user@example.com")

    def test_export_data_only_own(self):
        """IDOR (AUTH-P1-12): экспорт A не содержит id/email и строк B."""
        other = make_profile(
            "exp-other@example.com", full_name="Другой Пользователь",
        )
        third = make_profile("exp-third@example.com", role="employer")
        job = make_job(third, work_type="Чужая работа")
        Application.objects.create(job=job, worker=other, status="pending")
        # избранное B на A: строка содержит user_id=B, при утечке попадёт в экспорт
        Favorite.objects.create(user=other, target=self.user, favorite_type="worker")

        response = self.client.get(reverse("core:export_data"))
        self.assertEqual(response.status_code, 200)
        payload = json.dumps(json.loads(response.content), ensure_ascii=False)
        self.assertNotIn(str(other.pk), payload)
        self.assertNotIn(other.email, payload)
        self.assertNotIn(other.full_name, payload)
        # собственные данные A в экспорте есть
        data = json.loads(response.content)
        self.assertEqual(data["user_id"], str(self.user.pk))
        self.assertEqual(data["profile"]["email"], self.user.email)

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("core:export_data")).status_code, 302)


class DeleteAccountTests(TestCase):
    def test_delete_via_rpc_and_logout(self):
        cache.clear()
        user = make_profile("del-user@example.com")
        self.client.force_login(user)
        response = self.client.post(reverse("core:delete_account"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Profile.objects.filter(pk=user.pk).exists())  # delete_user_cascade

    def test_delete_account_only_self(self):
        """IDOR (AUTH-P1-12): A удаляет только свою сессию/профиль, B остаётся."""
        cache.clear()
        other = make_profile("del-keep@example.com")
        me = make_profile("del-self@example.com")
        self.client.force_login(me)
        response = self.client.post(reverse("core:delete_account"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Profile.objects.filter(pk=me.pk).exists())
        self.assertTrue(Profile.objects.filter(pk=other.pk).exists())

    def test_rate_limit_one_per_hour(self):
        cache.clear()
        user = make_profile("del-rate@example.com")
        self.client.force_login(user)
        self.client.post(reverse("core:delete_account"))
        other = make_profile("del-rate2@example.com")
        self.client.force_login(other)
        # ключ кэша на конкретного пользователя: другой не задет
        self.assertEqual(self.client.post(reverse("core:delete_account")).status_code, 302)


class ReportUserTests(TestCase):
    def test_report_creates_row_via_rpc(self):
        reporter = make_profile("rep-me@example.com")
        victim = make_profile("rep-victim@example.com")
        self.client.force_login(reporter)
        response = self.client.post(reverse("core:report_user", args=[victim.pk]), {"reason": "спам"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(UserReport.objects.filter(reporter=reporter, reported=victim).exists())

    def test_report_user_uses_session_identity(self):
        """IDOR (AUTH-P1-12): reporter берётся из сессии, тело запроса его не подменяет."""
        cache.clear()
        reporter = make_profile("rep-session@example.com")
        reported = make_profile("rep-target@example.com")
        self.client.force_login(reporter)
        response = self.client.post(
            reverse("core:report_user", args=[reported.pk]),
            {
                "reason": "спам",
                # попытка подмены автора жалобы через тело запроса
                "reporter_id": str(reported.pk),
                "user_id": str(reported.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        report = UserReport.objects.get(reporter=reporter, reported=reported)
        self.assertEqual(report.reporter_id, reporter.pk)
        self.assertEqual(report.reported_id, reported.pk)
        self.assertFalse(UserReport.objects.filter(reporter=reported).exists())

        # self-report A → A не создаёт запись (RPC cannot_report_self).
        # Кэш лимитера чистим, иначе отказ мог бы прийти от rate-limit, а не от
        # проверки cannot_report_self, и тест замаскировал бы fail-open.
        cache.clear()
        response = self.client.post(
            reverse("core:report_user", args=[reporter.pk]), {"reason": "сам на себя"},
        )
        self.assertEqual(response.status_code, 302)
        # ветка ошибки RPC редиректит на профиль, а rate-limit — на /workers
        self.assertEqual(
            response["Location"],
            reverse("core:worker_detail", args=[reporter.pk]),
        )
        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(
            any("Не удалось отправить жалобу" in m for m in msgs),
            "ожидалось сообщение об ошибке RPC cannot_report_self, получено: %r" % msgs,
        )
        self.assertFalse(
            any("Слишком часто" in m for m in msgs),
            "self-report отклонён rate-limit, а не cannot_report_self: %r" % msgs,
        )
        self.assertFalse(
            UserReport.objects.filter(reporter=reporter, reported=reporter).exists()
        )

    def test_empty_reason_rejected(self):
        reporter = make_profile("rep-me2@example.com")
        victim = make_profile("rep-victim2@example.com")
        self.client.force_login(reporter)
        self.client.post(reverse("core:report_user", args=[victim.pk]), {"reason": ""})
        self.assertFalse(UserReport.objects.filter(reporter=reporter).exists())


class NotificationPrefsTests(TestCase):
    def test_save_and_api(self):
        user = make_profile("prefs@example.com")
        self.client.force_login(user)
        response = self.client.post(reverse("core:notification_prefs"), {"email_enabled": "on", "in_app_enabled": "on"})
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.notification_prefs.get("email_enabled"))
        self.assertFalse(user.notification_prefs.get("push_enabled"))  # не отмечен
        api = self.client.get(reverse("core:notification_prefs_api")).json()
        self.assertTrue(api["prefs"]["email_enabled"])
        self.assertFalse(api["prefs"]["push_enabled"])


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64
PDF_BYTES = b"%PDF-1.4\n" + b"0" * 64


class UploadTests(TestCase):
    def setUp(self):
        self.user = make_profile("upl@example.com")
        self.client.force_login(self.user)

    def _verification_doc(self, user=None):
        """Файл-скан в uploads/verification-docs + привязка к профилю (владелец)."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from core.storage import save_upload

        owner = user or self.user
        f = SimpleUploadedFile("scan.png", PNG_BYTES, content_type="image/png")
        url = save_upload(f, "verification-docs")
        Profile.objects.filter(pk=owner.pk).update(verification_doc_url=url)
        return url

    def test_avatar_upload_and_serve(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("a.png", PNG_BYTES, content_type="image/png")
        response = self.client.post(reverse("core:upload_avatar"), {"avatar": f})
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar_url.startswith("/uploads/avatars/"))
        served = self.client.get(self.user.avatar_url)
        self.assertEqual(served.status_code, 200)
        self.assertIn("public", served["Cache-Control"])
        # аватары по-прежнему публичны (гость без логина)
        guest = self.client.__class__()
        anonymous = guest.get(self.user.avatar_url)
        self.assertEqual(anonymous.status_code, 200)
        self.assertIn("public", anonymous["Cache-Control"])

    def test_bad_mime_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("a.txt", b"hello world", content_type="text/plain")
        self.client.post(reverse("core:upload_avatar"), {"avatar": f})
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar_url)

    def test_verification_doc_guest_404(self):
        url = self._verification_doc()
        guest = self.client.__class__()
        response = guest.get(url)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"\x89PNG", response.content)

    def test_verification_doc_other_user_404(self):
        url = self._verification_doc()
        other = make_profile("upl-other@example.com")
        self.client.force_login(other)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"\x89PNG", response.content)

    def test_verification_doc_owner_200_private_attachment(self):
        url = self._verification_doc()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(b"".join(response.streaming_content), PNG_BYTES)

    def test_verification_doc_admin_200(self):
        url = self._verification_doc()
        admin = make_profile("upl-admin@example.com", role="admin")
        self.client.force_login(admin)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])

    def test_verification_doc_alias_not_bypassable(self):
        url = self._verification_doc()
        name = url.rsplit("/", 1)[-1]
        alias = "/uploads/avatars/../verification-docs/" + name
        guest = self.client.__class__()
        self.assertEqual(guest.get(alias).status_code, 404)
        other = make_profile("upl-alias@example.com")
        self.client.force_login(other)
        self.assertEqual(self.client.get(alias).status_code, 404)

    def test_serve_upload_path_traversal_404(self):
        self.assertEqual(self.client.get("/uploads/../manage.py").status_code, 404)

    def test_verification_pdf_accepted(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from core.storage import resolve_upload_url

        f = SimpleUploadedFile("scan.pdf", PDF_BYTES, content_type="application/pdf")
        response = self.client.post(reverse("core:upload_verification_doc"), {"document": f})
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.verification_doc_url.endswith(".pdf"))
        self.assertEqual(self.user.verification_status, "pending")
        path = self.user.verification_doc_url[len("/uploads/"):]
        self.assertIsNotNone(resolve_upload_url(path))

    def test_avatar_pdf_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        before = self.user.avatar_url
        f = SimpleUploadedFile("a.pdf", PDF_BYTES, content_type="application/pdf")
        self.client.post(reverse("core:upload_avatar"), {"avatar": f})
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar_url, before)

    def test_job_photo_upload_owner(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        job = make_job(self.user)
        f = SimpleUploadedFile("p.png", PNG_BYTES, content_type="image/png")
        self.client.post(reverse("core:job_photo_upload", args=[job.pk]), {"photo": f})
        self.assertEqual(JobPhoto.objects.filter(job=job).count(), 1)
        # фото заданий остаются публичными
        photo = JobPhoto.objects.get(job=job)
        guest = self.client.__class__()
        served = guest.get(photo.photo_url)
        self.assertEqual(served.status_code, 200)
        self.assertIn("public", served["Cache-Control"])

    def test_delete_account_removes_uploads(self):
        """P1-14/152-ФЗ: удаление аккаунта удаляет аватар, скан и фото заданий."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from core.storage import resolve_upload_url, save_upload

        cache.clear()
        avatar = save_upload(
            SimpleUploadedFile("a.png", PNG_BYTES, content_type="image/png"), "avatars"
        )
        Profile.objects.filter(pk=self.user.pk).update(avatar_url=avatar)
        doc_url = self._verification_doc()
        job = make_job(self.user, work_type="Удаление фото")
        legacy_url = save_upload(
            SimpleUploadedFile("j.png", PNG_BYTES, content_type="image/png"), "jobs"
        )
        # несуществующий файл: ошибка удаления не должна ломать удаление аккаунта
        job.photo_urls = [legacy_url, "/uploads/jobs/missing.png"]
        job.save(update_fields=["photo_urls"])
        photo_url = save_upload(
            SimpleUploadedFile("p.png", PNG_BYTES, content_type="image/png"), "jobs"
        )
        JobPhoto.objects.create(job=job, photo_url=photo_url, order_num=0)

        response = self.client.post(reverse("core:delete_account"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Profile.objects.filter(pk=self.user.pk).exists())
        for url in (avatar, doc_url, legacy_url, photo_url):
            path = url[len("/uploads/"):]
            self.assertIsNone(resolve_upload_url(path), "файл остался на диске: %s" % url)


class EmployersTests(TestCase):
    def test_list_and_detail(self):
        emp = make_profile("emp-cat@example.com", role="employer")
        make_job(emp, work_type="Открытое")
        viewer = make_profile("emp-viewer@example.com")
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(reverse("core:employers")).status_code, 200)
        self.assertContains(self.client.get(reverse("core:employers")), emp.full_name)
        response = self.client.get(reverse("core:employer_detail", args=[emp.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Открытое")


class RatingsPagesTests(TestCase):
    def test_user_ratings_page(self):
        worker = make_profile("rt-worker@example.com")
        rater = make_profile("rt-rater@example.com")
        job = make_job(rater, status="completed")
        from core.models import Rating
        Rating.objects.create(rated_user=worker, rater_user=rater, job=job,
                              rating=5, comment="Отлично", rating_type="employer", target_type="worker")
        self.assertEqual(self.client.get(reverse("core:user_ratings", args=[worker.pk])).status_code, 200)

    def test_rate_workers_owner_only(self):
        owner = make_profile("rwk-owner@example.com")
        job = make_job(owner, status="completed")
        worker = make_profile("rwk-worker@example.com")
        Application.objects.create(job=job, worker=worker, status="accepted")
        self.client.force_login(owner)
        self.assertEqual(self.client.get(reverse("core:rate_workers", args=[job.pk])).status_code, 200)
        stranger = make_profile("rwk-stranger@example.com")
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(reverse("core:rate_workers", args=[job.pk])).status_code, 404)

    def test_rate_workers_prefills_existing_rating(self):
        owner = make_profile("rwk-prefill-owner@example.com")
        job = make_job(owner, status="completed")
        worker = make_profile("rwk-prefill-worker@example.com")
        Application.objects.create(job=job, worker=worker, status="accepted")
        Rating.objects.create(
            rated_user=worker, rater_user=owner, job=job, rating=5,
            comment="Комментарий J030", rating_type="employer", target_type="worker",
        )
        self.client.force_login(owner)
        response = self.client.get(reverse("core:rate_workers", args=[job.pk]))
        self.assertContains(response, "Обновить оценку")
        self.assertContains(response, "Оценён")
        self.assertContains(response, "Комментарий J030")
        self.assertContains(response, 'value="5" selected')

    def test_rate_workers_without_rating(self):
        owner = make_profile("rwk-empty-owner@example.com")
        job = make_job(owner, status="completed")
        worker = make_profile("rwk-empty-worker@example.com")
        Application.objects.create(job=job, worker=worker, status="accepted")
        self.client.force_login(owner)
        response = self.client.get(reverse("core:rate_workers", args=[job.pk]))
        self.assertContains(response, "Не оценён")
        self.assertContains(response, "Оценить")
        self.assertNotContains(response, "Обновить оценку")

    def test_user_ratings_labels_and_job_link(self):
        employer = make_profile("rt-label-emp@example.com", role="employer")
        worker = make_profile("rt-label-worker@example.com", role="worker")
        job = make_job(employer, status="completed")
        Rating.objects.create(
            rated_user=worker, rater_user=employer, job=job, rating=5,
            comment="Отзыв работодателя", rating_type="employer", target_type="worker",
        )
        Rating.objects.create(
            rated_user=employer, rater_user=worker, job=job, rating=4,
            comment="Отзыв работника", rating_type="worker", target_type="employer",
        )
        worker_page = self.client.get(reverse("core:user_ratings", args=[worker.pk]))
        self.assertContains(worker_page, "От работодателя")
        self.assertContains(worker_page, reverse("core:job_detail", args=[job.pk]))
        employer_page = self.client.get(reverse("core:user_ratings", args=[employer.pk]))
        self.assertContains(employer_page, "От работника")


class BulkActionsTests(TestCase):
    def test_bulk_apply_and_unapply(self):
        emp = make_profile("bulk-emp@example.com")
        j1, j2 = make_job(emp, work_type="B1"), make_job(emp, work_type="B2")
        worker = make_profile("bulk-worker@example.com")
        self.client.force_login(worker)
        self.client.post(reverse("core:bulk_apply"), {"job_ids": [str(j1.pk), str(j2.pk)]})
        self.assertEqual(Application.objects.filter(worker=worker).count(), 2)
        self.client.post(reverse("core:bulk_unapply"), {"job_ids": [str(j1.pk), str(j2.pk)]})
        self.assertEqual(Application.objects.filter(worker=worker, status="withdrawn").count(), 2)

    def test_reject_all_invitations(self):
        from core.models import Invitation
        emp = make_profile("invall-emp@example.com")
        worker = make_profile("invall-worker@example.com")
        j = make_job(emp)
        Invitation.objects.create(job=j, employer=emp, worker=worker)
        self.client.force_login(worker)
        self.client.post(reverse("core:invitations_reject_all"))
        self.assertEqual(Invitation.objects.filter(worker=worker, status="rejected").count(), 1)


class SeoFaqTests(TestCase):
    def test_faq(self):
        self.assertEqual(self.client.get(reverse("core:faq")).status_code, 200)

    def test_sitemap(self):
        response = self.client.get(reverse("core:sitemap"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<urlset", response.content)



class ApplicationContactsTests(TestCase):
    def test_received_application_shows_worker_contacts(self):
        employer = make_profile("contacts-emp@example.com", role="employer")
        worker = make_profile(
            "contacts-worker@example.com", role="worker",
            phone="+79991234567", contact="@contacts_worker",
        )
        job = make_job(employer, work_type="Контакты J038")
        Application.objects.create(job=job, worker=worker, status="pending")
        self.client.force_login(employer)

        received = self.client.get(reverse("core:my_applications"), {"tab": "received"})
        self.assertContains(received, "+79991234567")
        self.assertContains(received, "contacts-worker@example.com")
        self.assertContains(received, "@contacts_worker")

        applicants = self.client.get(reverse("core:job_applicants", args=[job.pk]))
        self.assertContains(applicants, "+79991234567")
        self.assertContains(applicants, "contacts-worker@example.com")

    def test_sent_tab_hides_worker_contacts(self):
        employer = make_profile("contacts-emp2@example.com", role="employer")
        worker = make_profile(
            "contacts-worker2@example.com", role="worker",
            phone="+79990000001", contact="@hidden_contact",
        )
        job = make_job(employer, work_type="Контакты J038 sent")
        Application.objects.create(job=job, worker=worker, status="pending")
        self.client.force_login(worker)
        sent = self.client.get(reverse("core:my_applications"), {"tab": "sent"})
        self.assertNotContains(sent, "+79990000001")
        self.assertNotContains(sent, "@hidden_contact")


class InvitationsRejectAllButtonTests(TestCase):
    def test_invitations_page_has_reject_all_button(self):
        from core.models import Invitation
        employer = make_profile("invbtn-emp@example.com", role="employer")
        worker = make_profile("invbtn-worker@example.com", role="worker")
        job = make_job(employer)
        Invitation.objects.create(job=job, employer=employer, worker=worker)
        self.client.force_login(worker)
        response = self.client.get(reverse("core:invitations"))
        self.assertContains(response, reverse("core:invitations_reject_all"))
        self.assertContains(response, "Отклонить все ожидающие")


class NotificationsDeleteAllTests(TestCase):
    def test_delete_all_keeps_invitations(self):
        user = make_profile("notif-clear@example.com")
        Notification.objects.create(
            user=user, type="application_received", title="Отклик",
            message="Обычное уведомление",
        )
        Notification.objects.create(
            user=user, type="application_received", title="Приглашение",
            message="Вас пригласили на задание", data={"type": "invitation"},
        )
        self.client.force_login(user)
        response = self.client.post(reverse("core:notifications_delete_all"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            list(Notification.objects.filter(user=user).values_list("title", flat=True)),
            ["Приглашение"],
        )


class FavoritesPageTests(TestCase):
    def test_unified_favorites_and_bulk_delete(self):
        user = make_profile("fav-page@example.com")
        employer = make_profile("fav-page-emp@example.com", role="employer")
        worker = make_profile("fav-page-worker@example.com", role="worker")
        job = make_job(employer, work_type="Избранное J043")
        JobFavorite.objects.create(user=user, job=job)
        Favorite.objects.create(user=user, target=worker, favorite_type="worker")
        Favorite.objects.create(user=user, target=employer, favorite_type="employer")
        self.client.force_login(user)

        response = self.client.get(reverse("core:favorites_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Избранное J043")
        self.assertContains(response, "Задания · 1")
        self.assertContains(response, "Трудники · 1")
        self.assertContains(response, "Работодатели · 1")
        self.assertContains(response, reverse("core:job_detail", args=[job.pk]))
        self.assertContains(response, reverse("core:worker_detail", args=[worker.pk]))

        self.client.post(reverse("core:favorites_bulk_delete"), {"kind": "jobs", "ids": [str(job.pk)]})
        self.assertFalse(JobFavorite.objects.filter(user=user, job=job).exists())
        self.client.post(reverse("core:favorites_bulk_delete"), {"kind": "worker", "ids": [str(worker.pk)]})
        self.assertFalse(Favorite.objects.filter(user=user, target=worker).exists())
        self.client.post(reverse("core:favorites_bulk_delete"), {"kind": "employer", "ids": [str(employer.pk)]})
        self.assertFalse(Favorite.objects.filter(user=user, target=employer).exists())
        self.assertEqual(self.client.get(reverse("core:favorite_jobs")).status_code, 200)

    def test_nav_links_to_unified_favorites(self):
        user = make_profile("fav-nav@example.com")
        self.client.force_login(user)
        response = self.client.get(reverse("core:jobs"))
        self.assertContains(response, reverse("core:favorites_page"))


class PushSettingsTests(TestCase):
    def test_settings_page_wires_push(self):
        user = make_profile("push-settings@example.com")
        self.client.force_login(user)
        response = self.client.get(reverse("core:notification_prefs"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "js/api.js")
        self.assertContains(response, "js/push-notifications.js")
        self.assertContains(response, "push-toggle")

    def test_push_manager_uses_meta_csrf(self):
        path = Path(settings.REPO_ROOT) / "static" / "js" / "push-notifications.js"
        source = path.read_text(encoding="utf-8")
        self.assertIn('meta[name="csrf-token"]', source)
        self.assertIn("csrftoken=", source)


class NotificationDeepLinksTests(TestCase):
    def test_notification_links_to_job_and_type_label(self):
        user = make_profile("notif-link@example.com")
        employer = make_profile("notif-link-emp@example.com", role="employer")
        job = make_job(employer, work_type="Уведомление J052")
        app_obj = Application.objects.create(job=job, worker=user, status="accepted")
        Notification.objects.create(
            user=user, type="new_message", title="Новое сообщение",
            message="Есть новое сообщение", job=job, application=app_obj,
        )
        self.client.force_login(user)
        response = self.client.get(reverse("core:notifications"))
        self.assertContains(response, "Сообщение")
        self.assertContains(response, reverse("core:job_detail", args=[job.pk]))

    def test_invitation_notification_links_to_invitations(self):
        user = make_profile("notif-invite@example.com")
        Notification.objects.create(
            user=user, type="application_received", title="Приглашение",
            message="Вас пригласили на задание", data={"type": "invitation"},
        )
        self.client.force_login(user)
        response = self.client.get(reverse("core:notifications"))
        self.assertContains(response, reverse("core:invitations"))
        self.assertContains(response, "Открыть приглашение")


class FaqAndExternalLinkTests(TestCase):
    def test_faq_has_groups_and_questions(self):
        response = self.client.get(reverse("core:faq"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Регистрация и возможности")
        self.assertContains(response, "Отклики и чат")
        self.assertContains(response, "Оплата")
        self.assertGreaterEqual(response.content.decode().count("<details"), 12)

    def test_register_privacy_link_is_safe(self):
        response = self.client.get(reverse("core:register"))
        self.assertContains(response, 'rel="noopener noreferrer"')


class MultiroleFavoriteTypeTests(TestCase):
    def test_employer_favorite_removed_with_explicit_type(self):
        target = make_profile("fav-multi-emp@example.com", role="worker", full_name="Мультирольный Работодатель")
        job = make_job(target, work_type="Мультироль J057")
        viewer = make_profile("fav-multi-viewer@example.com")
        Favorite.objects.create(user=viewer, target=target, favorite_type="employer")
        self.client.force_login(viewer)
        response = self.client.get(reverse("core:job_detail", args=[job.pk]))
        self.assertContains(response, 'name="as" value="employer"')
        self.client.post(
            reverse("core:people_favorite_toggle", args=[target.pk]), {"as": "employer"}
        )
        self.assertFalse(
            Favorite.objects.filter(user=viewer, target=target, favorite_type="employer").exists()
        )
        self.assertFalse(
            Favorite.objects.filter(user=viewer, target=target, favorite_type="worker").exists()
        )

    def test_worker_favorite_uses_worker_type(self):
        target = make_profile("fav-worker-type@example.com", role="worker")
        viewer = make_profile("fav-worker-viewer@example.com")
        self.client.force_login(viewer)
        self.client.post(
            reverse("core:people_favorite_toggle", args=[target.pk]), {"as": "worker"}
        )
        self.assertTrue(
            Favorite.objects.filter(user=viewer, target=target, favorite_type="worker").exists()
        )


class AppDownloadLinksTests(TestCase):
    def test_footer_links_to_app_page(self):
        response = self.client.get(reverse("core:jobs"))
        self.assertContains(response, reverse("core:app_download"))

    def test_profile_menu_links_to_app_page(self):
        user = make_profile("app-link@example.com")
        self.client.force_login(user)
        response = self.client.get(reverse("core:jobs"))
        self.assertContains(response, "Установить приложение")
