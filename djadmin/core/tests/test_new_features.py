"""Email change, employer card, support and branded error pages (J144)."""
from unittest.mock import patch

from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models import EmployerDetail, Profile
from core.tests.test_auth import make_profile
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
