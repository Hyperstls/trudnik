"""R004: двухэтапный вход — переключатель в профиле и полный флоу входа.

Профиль: POST /profile action=twofa включает/выключает только свой флаг.
Вход: пароль → код из письма → сессия; 5 неверных кодов сбрасывают pending.
"""
import re

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Profile
from core.tests.test_auth import CACHE_LOCMEM, make_profile

PASSWORD = "Aa1!aaaa"  # pragma: allowlist secret

EMAIL_LOCMEM = {
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "TRANSACTIONAL_EMAIL_ASYNC": False,
}


class ProfileTwoFAToggleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_profile("twofa-toggle@example.com")
        self.other = make_profile("twofa-other@example.com")
        self.client.force_login(self.user)

    def test_enable_two_factor(self):
        response = self.client.post(
            reverse("core:profile"), {"action": "twofa", "enabled": "on"}
        )
        self.assertRedirects(response, reverse("core:profile"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.two_factor_enabled)

    def test_disable_two_factor(self):
        Profile.objects.filter(pk=self.user.pk).update(two_factor_enabled=True)
        response = self.client.post(reverse("core:profile"), {"action": "twofa"})
        self.assertRedirects(response, reverse("core:profile"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.two_factor_enabled)

    @override_settings(
        AUTHENTICATION_BACKENDS=["django.contrib.auth.backends.ModelBackend"]
    )
    def test_enable_rejected_without_verified_email(self):
        # Сценарий: сессия уже открыта, но email перестал быть подтверждённым.
        # Штатный ProfileBackend не пустил бы такого пользователя в get_user,
        # поэтому для edge-state берём базовый ModelBackend.
        Profile.objects.filter(pk=self.user.pk).update(email_verified=False)
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("core:profile"),
            {"action": "twofa", "enabled": "on"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "только после подтверждения email")
        self.user.refresh_from_db()
        self.assertFalse(self.user.two_factor_enabled)

    def test_other_profile_is_untouched(self):
        response = self.client.post(
            reverse("core:profile"),
            {
                "action": "twofa",
                "enabled": "on",
                "user_id": str(self.other.pk),
                "pk": str(self.other.pk),
            },
        )
        self.assertRedirects(response, reverse("core:profile"))
        self.user.refresh_from_db()
        self.other.refresh_from_db()
        self.assertTrue(self.user.two_factor_enabled)
        self.assertFalse(self.other.two_factor_enabled)


@override_settings(CACHES=CACHE_LOCMEM, **EMAIL_LOCMEM)
class TwoFactorLoginTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.client.logout()
        self.user = make_profile(
            "twofa-login@example.com", password=PASSWORD, two_factor_enabled=True
        )

    def _submit_password(self):
        return self.client.post(
            "/login", {"email": self.user.email, "password": PASSWORD}
        )

    def _code_from_mail(self):
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(r"\b(\d{6})\b", mail.outbox[0].body)
        self.assertIsNotNone(match)
        return match.group(1)

    @staticmethod
    def _wrong_code(stored):
        return "000000" if stored != "000000" else "111111"

    def test_password_step_returns_code_form_without_authentication(self):
        response = self._submit_password()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Подтверждение входа")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(str(self.client.session.get("twofa_user")), str(self.user.pk))
        code = self._code_from_mail()
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())

    def test_wrong_code_does_not_authenticate(self):
        self._submit_password()
        stored = self._code_from_mail()
        response = self.client.post("/login", {"code": self._wrong_code(stored)})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Неверный код")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_five_wrong_codes_clear_pending_session(self):
        self._submit_password()
        wrong = self._wrong_code(self._code_from_mail())
        for _attempt in range(5):
            response = self.client.post("/login", {"code": wrong})
            self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotIn("twofa_user", self.client.session)
        response = self.client.post("/login", {"code": wrong})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Сессия входа истекла")

    def test_correct_code_authenticates_and_redirects(self):
        self._submit_password()
        code = self._code_from_mail()
        response = self.client.post("/login", {"code": code})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")
        self.assertIn("_auth_user_id", self.client.session)
        self.assertNotIn("twofa_user", self.client.session)

    def test_non_ascii_code_does_not_500(self):
        self._submit_password()
        self._code_from_mail()
        for bad_code in ("abcdef", "１２３４５６", "код123"):
            response = self.client.post("/login", {"code": bad_code})
            self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_without_two_factor_authenticates_immediately(self):
        Profile.objects.filter(pk=self.user.pk).update(two_factor_enabled=False)
        response = self._submit_password()
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)
        self.assertEqual(len(mail.outbox), 0)
