"""Доступ к админке и ключевым страницам: superuser да, остальные нет."""
import os
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Announcement, AuditLog, ErrorEvent, NotificationOutbox, Rating, RatingAppeal, SitePage,
)
from core.tests.test_auth import make_profile

User = get_user_model()

CHANGELISTS = [
    "admin:core_profile_changelist",
    "admin:core_job_changelist",
    "admin:core_application_changelist",
    "admin:core_notification_changelist",
    "admin:core_userreport_changelist",
    "admin:core_skill_changelist",
    "admin:core_religion_changelist",
    "admin:core_sitepage_changelist",
    "admin:core_auditlog_changelist",
    "admin:core_notificationoutbox_changelist",
    "admin:core_emaillog_changelist",
    "admin:core_pushsubscription_changelist",
    "admin:core_message_changelist",
    "admin:core_rating_changelist",
    "admin:core_ratingreport_changelist",
    "admin:core_invitation_changelist",
    "admin:core_receipt_changelist",
    "admin:core_announcement_changelist",
    "admin:core_ratingappeal_changelist",
]


class AdminAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("root@example.com", "Aa1!aaaa")  # pragma: allowlist secret
        # 'create_superuser' у нашего менеджера пишет в profiles напрямую

    def test_anonymous_redirected(self):
        for url_name in CHANGELISTS:
            with self.subTest(url=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 302, url_name)
                self.assertIn("/admin/login/", response["Location"])

    def test_non_staff_redirected(self):
        make_profile("worker@example.com")
        self.client.login(username="worker@example.com", password="Aa1!aaaa")  # pragma: allowlist secret
        response = self.client.get(reverse("admin:core_profile_changelist"))
        self.assertEqual(response.status_code, 302)

    def test_admin_changelists_ok(self):
        self.client.force_login(self.admin)
        for url_name in CHANGELISTS:
            with self.subTest(url=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200, url_name)

    def test_sitepage_add_with_string_pk(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("admin:core_sitepage_add"),
            {"slug": "faq-admin-test", "title": "FAQ", "content": "<p>ok</p>", "_save": "Сохранить"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(SitePage.objects.filter(pk="faq-admin-test").exists())

    def test_sitepage_change_is_previewable_and_slug_is_readonly(self):
        SitePage.objects.create(slug="privacy", title="Политика", content="<p>ok</p>")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:core_sitepage_change", args=["privacy"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/privacy")
        self.assertNotContains(response, 'name="slug"')
        self.assertContains(response, 'id="sitepage-preview"')
        self.assertContains(response, "admin-sitepage-preview.js")

    def test_dashboard_ok(self):
        self.client.force_login(self.admin)
        response = self.client.get("/admin/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Дашборд")

    def test_admin_index_has_grouped_links(self):
        self.client.force_login(self.admin)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)
        for text in (
            "Дашборд", "Аналитика", "Переменные окружения",
            "Профили", "Задания", "Платежи и подписки",
            "Уведомления и поддержка", "Контентные страницы", "Оценки",
        ):
            self.assertContains(response, text)
        self.assertContains(response, "/admin/env/")
        self.assertContains(response, "/admin/analytics/")

    def test_profile_skills_editor(self):
        worker = make_profile("skills@example.com")
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("admin:core_profile_skills", args=[worker.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Навыки")


    def test_env_page_staff_only(self):
        url = "/admin/env/"
        self.assertEqual(self.client.get(url).status_code, 302)  # аноним
        make_profile("env-plain@example.com")
        self.client.login(username="env-plain@example.com", password="Aa1!aaaa")  # pragma: allowlist secret
        self.assertEqual(self.client.get(url).status_code, 302)  # не-staff
        self.client.force_login(self.admin)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PATH")

class AnnouncementAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("announcement-admin@example.com", "Aa1!aaaa")  # pragma: allowlist secret

    def test_changelist_and_add_form_ok(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:core_announcement_changelist"))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse("admin:core_announcement_add"))
        self.assertEqual(response.status_code, 200)
        for field in ("title", "kind", "body", "url", "url_label", "is_pinned", "is_active"):
            with self.subTest(field=field):
                self.assertContains(response, 'name="%s"' % field)

    def test_add_saves_announcement(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admin:core_announcement_add"), {
            "title": "Админ-объявление",
            "kind": Announcement.Kind.EVENT,
            "body": "Текст объявления",
            "url": "https://example.com/event",
            "url_label": "Подробнее",
            "is_pinned": "on",
            "is_active": "on",
            "_save": "Сохранить",
        })
        self.assertEqual(response.status_code, 302)
        announcement = Announcement.objects.get(title="Админ-объявление")
        self.assertEqual(announcement.kind, Announcement.Kind.EVENT)
        self.assertEqual(announcement.body, "Текст объявления")
        self.assertEqual(announcement.url, "https://example.com/event")
        self.assertEqual(announcement.url_label, "Подробнее")
        self.assertTrue(announcement.is_pinned)
        self.assertTrue(announcement.is_active)


class AdminEnvTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("env-root@example.com", "Aa1!aaaa")  # pragma: allowlist secret

    def test_env_page_masks_secrets(self):
        env = {
            "SECRET_KEY": "super-secret-value",  # pragma: allowlist secret
            "SMTP_PASSWORD": "smtp-secret",  # pragma: allowlist secret
            "DJANGO_ALLOWED_HOSTS": "example.com",
        }
        with patch.dict(os.environ, env):
            self.client.force_login(self.admin)
            response = self.client.get("/admin/env/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "super-secret-value")
        self.assertNotContains(response, "smtp-secret")
        self.assertContains(response, "****** (set)")
        self.assertContains(response, "example.com")


class AdminEnvRevealTests(TestCase):
    """R027: поштучное раскрытие секрета POST-формой — только superuser, с аудитом."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("env-reveal@example.com", "Aa1!aaaa")  # pragma: allowlist secret

    def test_staff_without_superuser_sees_mask_and_cannot_reveal(self):
        env = {
            "SECRET_KEY": "super-secret-value",  # pragma: allowlist secret
            "DJANGO_ALLOWED_HOSTS": "example.com",
        }
        self.client.force_login(self.admin)
        # is_staff и is_superuser у Profile — оба role == admin; «staff без
        # superuser» моделируется только подменой is_superuser на уровне класса.
        with patch.dict(os.environ, env), patch.object(User, "is_superuser", new=False):
            response = self.client.get("/admin/env/")
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "super-secret-value")
            self.assertContains(response, "****** (set)")
            self.assertContains(response, "example.com")
            response = self.client.post("/admin/env/", {"reveal": "SECRET_KEY"})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("super-secret-value", response.content.decode())
        self.assertIsNone(getattr(response, "context", None))
        self.assertFalse(AuditLog.objects.filter(action="env_reveal").exists())

    def test_superuser_reveals_one_value_audited_and_not_cached(self):
        env = {
            "SECRET_KEY": "super-secret-value",  # pragma: allowlist secret
            "SMTP_PASSWORD": "smtp-secret",  # pragma: allowlist secret
            "DJANGO_ALLOWED_HOSTS": "example.com",
        }
        self.client.force_login(self.admin)
        with patch.dict(os.environ, env):
            response = self.client.get("/admin/env/")
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "super-secret-value")
            self.assertContains(response, "****** (set)")
            response = self.client.post("/admin/env/", {"reveal": "SECRET_KEY"})
        self.assertEqual(response.status_code, 200)
        # Раскрыт только выбранный секрет, соседний остался маской.
        self.assertContains(response, "super-secret-value")
        self.assertNotContains(response, "smtp-secret")
        # admin_view(never_cache) дописывает свои директивы к нашему заголовку,
        # поэтому проверяем ключевое требование — no-store.
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("max-age=0", response["Cache-Control"])
        self.assertEqual(response["Pragma"], "no-cache")
        entry = AuditLog.objects.get(action="env_reveal")
        self.assertEqual(entry.table_name, "env")
        self.assertEqual(entry.new_data, {"name": "SECRET_KEY"})
        self.assertNotIn("super-secret-value", str(entry.new_data))
        self.assertNotIn("smtp-secret", str(entry.new_data))

    def test_revealed_value_is_html_escaped(self):
        payload = "<script>alert(1)</script>"
        self.client.force_login(self.admin)
        with patch.dict(os.environ, {"SECRET_KEY": payload}):  # pragma: allowlist secret
            response = self.client.post("/admin/env/", {"reveal": "SECRET_KEY"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, payload)

    def test_unknown_or_public_name_is_not_revealed(self):
        env = {
            "DJANGO_ALLOWED_HOSTS": "example.com",
            "SECRET_KEY": "super-secret-value",  # pragma: allowlist secret
        }
        self.client.force_login(self.admin)
        with patch.dict(os.environ, env):
            for name in ("DJANGO_ALLOWED_HOSTS", "NO_SUCH_ENV_VAR"):
                with self.subTest(name=name):
                    response = self.client.post("/admin/env/", {"reveal": name})
                    self.assertEqual(response.status_code, 200)
                    self.assertIsNone(response.context["revealed"])
                    self.assertNotContains(response, "super-secret-value")
        self.assertFalse(AuditLog.objects.filter(action="env_reveal").exists())


class AdminLoginPageTests(TestCase):
    def test_login_page_renders(self):
        response = self.client.get("/admin/login/")
        self.assertEqual(response.status_code, 200)


class RatingModerationAdminTests(TestCase):
    def setUp(self):
        from core.tests.test_flows import make_job
        self.staff = User.objects.create_superuser("rating-admin@example.com", "Aa1!aaaa")  # pragma: allowlist secret
        self.employer = make_profile("rating-mod-emp@example.com", role="employer")
        self.worker = make_profile("rating-mod-worker@example.com", role="worker")
        self.job = make_job(self.employer, status="completed")
        self.rating = Rating.objects.create(
            rated_user=self.worker, rater_user=self.employer, job=self.job,
            rating=5, comment="На проверке", rating_type="employer",
            target_type="worker", moderation_status=Rating.ModerationStatus.REVIEW,
        )

    def test_approve_publishes_and_recomputes(self):
        self.client.force_login(self.staff)
        response = self.client.post("/admin/core/rating/", {
            "action": "action_moderation_approve",
            "_selected_action": [str(self.rating.pk)],
        })
        self.assertEqual(response.status_code, 302)
        self.rating.refresh_from_db()
        self.assertEqual(self.rating.moderation_status, "ok")
        self.assertIsNotNone(self.rating.published_at)
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.worker_ratings_count, 1)

    def test_hide_removes_from_aggregates(self):
        self.rating.published_at = timezone.now()
        self.rating.save(update_fields=["published_at"])
        self.client.force_login(self.staff)
        response = self.client.post("/admin/core/rating/", {
            "action": "action_moderation_hide",
            "_selected_action": [str(self.rating.pk)],
        })
        self.assertEqual(response.status_code, 302)
        self.rating.refresh_from_db()
        self.assertEqual(self.rating.moderation_status, "hidden")
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.worker_ratings_count, 0)


class RatingAppealAdminTests(TestCase):
    """R025: админка апелляций — changelist, массовые действия, ссылка в профиле."""

    def setUp(self):
        from core.appeals import create_appeal
        from core.tests.test_flows import make_job

        self.staff = User.objects.create_superuser("appeal-admin@example.com", "Aa1!aaaa")  # pragma: allowlist secret
        self.employer = make_profile("appeal-admin-emp@example.com", role="employer")
        self.worker = make_profile("appeal-admin-worker@example.com")
        self.job = make_job(self.employer, status="completed")
        self.rating = Rating.objects.create(
            rated_user=self.worker, rater_user=self.employer, job=self.job,
            rating=5, comment="Скрытый отзыв", rating_type="employer",
            target_type="worker", moderation_status=Rating.ModerationStatus.HIDDEN,
            moderation_reason="Спам",
        )
        self.appeal, error = create_appeal(
            self.rating.pk, self.employer, "Прошу пересмотреть решение модератора",
        )
        self.assertIsNone(error)

    def test_changelist_ok(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin:core_ratingappeal_changelist"))
        self.assertEqual(response.status_code, 200)

    def test_add_form_forbidden(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin:core_ratingappeal_add"))
        self.assertEqual(response.status_code, 403)

    def test_approve_action_resolves_and_notifies_author(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("admin:core_ratingappeal_changelist"), {
            "action": "action_approve",
            "_selected_action": [str(self.appeal.pk)],
        })
        self.assertEqual(response.status_code, 302)
        self.appeal.refresh_from_db()
        self.assertEqual(self.appeal.status, RatingAppeal.Status.APPROVED)
        self.assertEqual(self.appeal.resolver_id, self.staff.pk)
        self.rating.refresh_from_db()
        self.assertEqual(self.rating.moderation_status, Rating.ModerationStatus.OK)
        notification = NotificationOutbox.objects.get(
            user=self.employer, type="rating_appeal",
        )
        self.assertEqual(notification.data["status"], RatingAppeal.Status.APPROVED)

    def test_reject_action_keeps_rating_hidden(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("admin:core_ratingappeal_changelist"), {
            "action": "action_reject",
            "_selected_action": [str(self.appeal.pk)],
        })
        self.assertEqual(response.status_code, 302)
        self.appeal.refresh_from_db()
        self.assertEqual(self.appeal.status, RatingAppeal.Status.REJECTED)
        self.rating.refresh_from_db()
        self.assertEqual(self.rating.moderation_status, Rating.ModerationStatus.HIDDEN)
        notification = NotificationOutbox.objects.get(
            user=self.employer, type="rating_appeal",
        )
        self.assertEqual(notification.data["status"], RatingAppeal.Status.REJECTED)

    def test_profile_has_my_ratings_link(self):
        self.client.force_login(self.employer)
        response = self.client.get("/profile")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/my-ratings"')
        self.assertContains(response, "Мои отзывы")


class DashboardMetricsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("dash-admin@example.com", "Aa1!aaaa")  # pragma: allowlist secret
        cls.worker = make_profile("dash-worker@example.com")
        cls.employer = make_profile("dash-employer@example.com")

    def _rating(self, moderation_status):
        return Rating.objects.create(
            rated_user=self.worker,
            rater_user=self.employer,
            rating_type="worker",
            target_type="worker",
            rating=5,
            moderation_status=moderation_status,
        )

    def test_moderation_and_error_metrics(self):
        self._rating(Rating.ModerationStatus.HIDDEN)
        self._rating(Rating.ModerationStatus.REVIEW)
        published = self._rating(Rating.ModerationStatus.OK)
        now = timezone.now()
        Rating.objects.filter(pk=published.pk).update(
            created_at=now - timedelta(hours=4),
            published_at=now - timedelta(hours=2),
        )
        ErrorEvent.objects.create(exception_type="ValueError", path="/x", method="GET")
        stale = ErrorEvent.objects.create(exception_type="Old", path="/y", method="GET")
        ErrorEvent.objects.filter(pk=stale.pk).update(
            created_at=now - timedelta(hours=25),
        )

        self.client.force_login(self.admin)
        response = self.client.get("/admin/dashboard/")

        self.assertEqual(response.status_code, 200)
        quick = response.context["quick"]
        self.assertEqual(quick["Отзывы скрыты модерацией"], 1)
        self.assertEqual(quick["Отзывы ждут публикации"], 1)
        self.assertEqual(quick["Средняя задержка публикации (ч)"], "2.0")
        self.assertEqual(quick["События ошибок (24 ч)"], 1)
