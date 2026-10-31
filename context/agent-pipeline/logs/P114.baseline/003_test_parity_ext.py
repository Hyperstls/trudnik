"""Паритет-остаток: 152-ФЗ, prefs, загрузки, работодатели, оценки, bulk."""
import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from core.models import Application, Favorite, JobPhoto, Profile, UserReport
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

