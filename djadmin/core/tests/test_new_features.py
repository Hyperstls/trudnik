"""Email change, employer card, support and branded error pages (J144)."""
from unittest.mock import patch

from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.core.cache import cache

from core.models import Application, EmployerDetail, Rating, Profile
from core.tests.test_auth import make_profile
from core.tests.test_flows import make_job
from core.tokens import generate_email_change_token


class EmailChangeTests(TestCase):
    def setUp(self):
        self.user = make_profile("email-old@example.com", role="worker")
        self.client.force_login(self.user)

    def test_wrong_password_does_not_send_email(self):
        with patch("core.views_auth._send_mail") as send:
            response = self.client.post(reverse("core:email_change_request"), {
                "new_email": "email-new@example.com",
                "current_password": "wrong",  # pragma: allowlist secret
            })
        self.assertRedirects(response, reverse("core:profile"))
        send.assert_not_called()
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "email-old@example.com")

    @patch("core.views_auth._send_mail")
    def test_request_sends_to_new_and_old_address(self, send):
        response = self.client.post(reverse("core:email_change_request"), {
            "new_email": "email-new@example.com",
            "current_password": "Aa1!aaaa",  # pragma: allowlist secret
        })
        self.assertRedirects(response, reverse("core:profile"))
        self.assertEqual(send.call_count, 2)
        self.assertEqual(send.call_args_list[0].args[2], "email-new@example.com")
        self.assertEqual(send.call_args_list[1].args[2], "email-old@example.com")

    def test_confirm_changes_email_and_verifies(self):
        token = generate_email_change_token(self.user.pk, "email-new@example.com")
        response = self.client.get(reverse("core:email_change_confirm", args=[token]))
        self.assertRedirects(response, reverse("core:profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "email-new@example.com")
        self.assertTrue(self.user.email_verified)

    def test_confirm_token_of_another_user_is_rejected(self):
        other = make_profile("other-email@example.com")
        token = generate_email_change_token(other.pk, "hijack@example.com")
        self.client.get(reverse("core:email_change_confirm", args=[token]))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "email-old@example.com")

    def test_taken_email_is_rejected(self):
        make_profile("taken@example.com")
        token = generate_email_change_token(self.user.pk, "taken@example.com")
        self.client.get(reverse("core:email_change_confirm", args=[token]))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "email-old@example.com")


class EmployerCardTests(TestCase):
    def test_employer_saves_and_public_page_shows_card(self):
        employer = make_profile("employer-card@example.com", role="employer")
        self.client.force_login(employer)
        response = self.client.post(reverse("core:profile"), {
            "action": "employer",
            "name": "Приход Святого Николая",
            "company_name": "АНО «Добро»",
            "city": "Москва",
            "address": "ул. Тверская, 7",
            "description": "Помогаем с разовыми задачами.",
            "inn": "7707083893",
        })
        self.assertRedirects(response, reverse("core:profile"))
        card = EmployerDetail.objects.get(user=employer)
        self.assertEqual(card.name, "Приход Святого Николая")

        response = self.client.get(reverse("core:employer_detail", args=[employer.pk]))
        self.assertContains(response, "Приход Святого Николая")
        self.assertContains(response, "ул. Тверская, 7")


class WorkerProfileExtrasTests(TestCase):
    def test_portfolio_and_reviews_are_visible(self):
        employer = make_profile("review-employer@example.com", role="employer")
        worker = make_profile(
            "review-worker@example.com", role="worker",
            full_name="Иван Портфолио", portfolio_link="https://example.com/portfolio",
        )
        job = make_job(employer, work_type="Оценённая работа")
        Rating.objects.create(
            rated_user=worker, rater_user=employer, job=job,
            rating_type="worker", target_type="worker", rating=5,
            comment="Отличная работа",
        )
        response = self.client.get(reverse("core:worker_detail", args=[worker.pk]))
        self.assertContains(response, "https://example.com/portfolio")
        self.assertContains(response, "Отличная работа")
        self.assertContains(response, "Все отзывы")

    def test_invitation_message_is_saved(self):
        employer = make_profile("message-employer@example.com", role="employer")
        worker = make_profile("message-worker@example.com", role="worker")
        job = make_job(employer, work_type="Приглашение с сообщением")
        self.client.force_login(employer)
        self.client.post(reverse("core:invite_worker", args=[worker.pk]), {
            "job_id": str(job.pk),
            "message": "Здравствуйте, есть опыт?",
        })
        invitation = worker.invitations_received.get(job=job)
        self.assertEqual(invitation.message, "Здравствуйте, есть опыт?")


class JobStatsTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_owner_sees_application_breakdown(self):
        employer = make_profile("stats-employer@example.com", role="employer")
        workers = [make_profile("stats-%d@example.com" % i, role="worker") for i in range(3)]
        job = make_job(employer, work_type="Статистика")
        Application.objects.create(job=job, worker=workers[0], status="pending")
        Application.objects.create(job=job, worker=workers[1], status="accepted")
        Application.objects.create(job=job, worker=workers[2], status="rejected")
        self.client.force_login(employer)
        response = self.client.get(reverse("core:job_detail", args=[job.pk]))
        self.assertEqual(response.context["job_stats"], {
            "total": 3, "pending": 1, "accepted": 1, "rejected": 1, "views": 1,
        })
        self.assertContains(response, "Всего откликов")
        self.assertContains(response, "Просмотры")


class AvatarDeleteTests(TestCase):
    def test_avatar_fields_are_cleared(self):
        user = make_profile("avatar-delete@example.com")
        Profile.objects.filter(pk=user.pk).update(
            avatar_url="/uploads/avatars/missing.jpg",
            photo_url="https://example.com/legacy.jpg",
        )
        self.client.force_login(user)
        response = self.client.post(reverse("core:delete_avatar"))
        self.assertRedirects(response, reverse("core:profile"))
        user.refresh_from_db()
        self.assertIsNone(user.avatar_url)
        self.assertIsNone(user.photo_url)


class SupportTests(TestCase):
    def test_get_support_page(self):
        response = self.client.get(reverse("core:support"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Поддержка")

    @patch("core.views_support.EmailMessage")
    def test_post_sends_email(self, email_class):
        response = self.client.post(reverse("core:support"), {
            "name": "Иван",
            "email": "ivan@example.com",
            "topic": "question",
            "message": "Не получается подтвердить email.",
        })
        self.assertRedirects(response, reverse("core:support"))
        self.assertTrue(email_class.called)
        self.assertTrue(email_class.return_value.send.called)

    def test_invalid_message_is_not_sent(self):
        with patch("core.views_support.EmailMessage") as email_class:
            response = self.client.post(reverse("core:support"), {
                "email": "bad",
                "topic": "question",
                "message": "short",
            })
        self.assertEqual(response.status_code, 200)
        email_class.assert_not_called()


class ErrorPageTests(SimpleTestCase):
    def test_branded_error_templates_render(self):
        for name in ("404.html", "500.html"):
            with self.subTest(name=name):
                html = render_to_string(name, {"request_path": "/missing"})
                self.assertIn("Трудник", html)
