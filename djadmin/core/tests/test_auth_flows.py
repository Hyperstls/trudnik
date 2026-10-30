"""Фаза 2б: регистрация, подтверждение email, сброс пароля.

Всё гоняется против клона dev-БД: register_user/change_password RPC — настоящие,
токены — itsdangerous в формате Flask (кросс-совместимость проверена прямым тестом).
"""
from datetime import timedelta

from django.core import mail
from django.test import TestCase, override_settings

LOCMEM = {"EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend"}
from django.utils import timezone
from itsdangerous import URLSafeTimedSerializer

from core import tokens
from core.models import Profile
from core.tests.test_auth import make_profile

REG = {
    "email": "New.User@Example.com",
    "full_name": "Новый Пользователь",
    "city": "Сергиев Посад",
    "password": "Aa1!bbbb",  # pragma: allowlist secret
    "intent": "both",
    "consent": "on",
    "website": "",
    "smart_token": "",
}

@override_settings(**LOCMEM)
class RegisterTests(TestCase):
    def setUp(self):
        mail.outbox.clear()
        self.client.logout()

    def test_register_happy_path(self):
        response = self.client.post("/register", REG)
        self.assertEqual(response.status_code, 302)
        profile = Profile.objects.get(email="new.user@example.com")  # нормализован
        self.assertEqual(profile.role, "worker")
        self.assertTrue(profile.worker_visibility)
        self.assertFalse(profile.email_verified)  # RPC ставит FALSE — вход закрыт
        self.assertIsNotNone(profile.consented_at)
        self.assertEqual(profile.city, "Сергиев Посад")
        self.assertTrue(profile.password.startswith("$2a$"))  # pgcrypto-совместимый хэш
        # письмо с ссылкой подтверждения
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/verify-email/", mail.outbox[0].body)
        # до подтверждения вход запрещён
        self.assertFalse(self.client.login(username="new.user@example.com", password="Aa1!bbbb"))  # pragma: allowlist secret

    def test_register_intent_post_jobs_maps_to_employer(self):
        self.client.post("/register", {**REG, "email": "employer-reg@example.com", "intent": "post_jobs"})
        profile = Profile.objects.get(email="employer-reg@example.com")
        self.assertEqual(profile.role, "employer")
        self.assertFalse(profile.worker_visibility)

    def test_honeypot_rejected(self):
        self.client.post("/register", {**REG, "email": "bot@example.com", "website": "http://spam.io"})
        self.assertFalse(Profile.objects.filter(email="bot@example.com").exists())

    def test_weak_password_rejected(self):
        self.client.post("/register", {**REG, "email": "weak@example.com", "password": "simple"})  # pragma: allowlist secret
        self.assertFalse(Profile.objects.filter(email="weak@example.com").exists())

    def test_consent_required(self):
        data = {k: v for k, v in REG.items() if k != "consent"}
        self.client.post("/register", {**data, "email": "noconsent@example.com"})
        self.assertFalse(Profile.objects.filter(email="noconsent@example.com").exists())

    def test_duplicate_email_friendly_error(self):
        make_profile("dup-reg@example.com")
        response = self.client.post("/register", {**REG, "email": "DUP-REG@example.com"})
        self.assertEqual(response.status_code, 200)  # форма с ошибкой, не 500
        self.assertContains(response, "уже зарегистрирован")

    @override_settings(SMARTCAPTCHA_SERVER_KEY="test-server-key")
    def test_captcha_fail_closed(self):
        # ключ задан, токена нет → отказ без создания профиля
        response = self.client.post("/register", {**REG, "email": "captcha@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Капча не пройдена")
        self.assertFalse(Profile.objects.filter(email="captcha@example.com").exists())


@override_settings(**LOCMEM)
class VerifyEmailTests(TestCase):
    def test_django_token_roundtrip(self):
        user = make_profile("verify-dj@example.com", email_verified=False)
        token = tokens.generate_email_verification_token("verify-dj@example.com")
        response = self.client.get("/verify-email/%s" % token)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Profile.objects.get(pk=user.pk).email_verified)

    def test_flask_format_token_accepted(self):
        """Контракт: токен, сгенерированный Flask-кодом (та же соль/секрет), работает."""
        from django.conf import settings

        user = make_profile("verify-fl@example.com", email_verified=False)
        flask_token = URLSafeTimedSerializer(settings.SECRET_KEY, salt="email-verify").dumps(
            "verify-fl@example.com"
        )
        self.client.get("/verify-email/%s" % flask_token)
        self.assertTrue(Profile.objects.get(pk=user.pk).email_verified)

    def test_garbage_token_rejected(self):
        response = self.client.get("/verify-email/not-a-token")
        self.assertEqual(response.status_code, 302)  # на resend с сообщением об ошибке
        self.assertIn("verify-email/resend", response["Location"])


@override_settings(**LOCMEM)
class PasswordResetTests(TestCase):
    def setUp(self):
        mail.outbox.clear()
        # модульные cooldown-словари живут между тестами — изолируем
        from core import views_auth

        views_auth._COOLDOWNS.clear()
        self.user = make_profile("reset-me@example.com")

    def _request(self, email="reset-me@example.com"):
        return self.client.post("/password-reset/request", {"email": email, "smart_token": ""})

    def test_request_universal_response_and_letter(self):
        response = self._request()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/password-reset/confirm/", mail.outbox[0].body)
        # несуществующий email — тот же UX, письмо не уходит
        mail.outbox.clear()
        response = self._request("ghost@nowhere.io")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_request_cooldown(self):
        self._request()
        mail.outbox.clear()
        self._request()  # повтор в течение cooldown — письма нет
        self.assertEqual(len(mail.outbox), 0)

    def test_confirm_changes_password_and_old_token_dies(self):
        self._request()
        token = mail.outbox[0].body.split("/password-reset/confirm/")[1].split()[0]
        response = self.client.post(
            "/password-reset/confirm/%s" % token,
            {"new_password": "Aa1!cccc", "confirm_password": "Aa1!cccc"},  # pragma: allowlist secret
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.client.login(username="reset-me@example.com", password="Aa1!aaaa"))  # pragma: allowlist secret
        self.assertTrue(self.client.login(username="reset-me@example.com", password="Aa1!cccc"))  # pragma: allowlist secret
        # B11: после смены пароля password_changed_at изменился — старый токен мёртв
        response = self.client.post(
            "/password-reset/confirm/%s" % token,
            {"new_password": "Aa1!dddd", "confirm_password": "Aa1!dddd"},  # pragma: allowlist secret
        )
        self.assertEqual(response["Location"], "/password-reset/request")
        self.assertTrue(self.client.login(username="reset-me@example.com", password="Aa1!cccc"))  # pragma: allowlist secret

    def test_flask_format_reset_token_with_future_stamp(self):
        """Контракт: токен Flask-формата c корректным pwd_changed_at принимается."""
        from django.conf import settings

        pwd_changed_at = self.user.password_changed_at or timezone.now()
        self.user.password_changed_at = pwd_changed_at
        self.user.save(update_fields=["password_changed_at"])
        flask_token = URLSafeTimedSerializer(
            settings.SECRET_KEY, salt="password-reset"
        ).dumps({"email": "reset-me@example.com", "pwd_changed_at": pwd_changed_at.isoformat()})
        response = self.client.post(
            "/password-reset/confirm/%s" % flask_token,
            {"new_password": "Aa1!eeee", "confirm_password": "Aa1!eeee"},  # pragma: allowlist secret
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.client.login(username="reset-me@example.com", password="Aa1!eeee"))  # pragma: allowlist secret

    def test_stale_token_rejected(self):
        token = tokens.generate_reset_token("reset-me@example.com", "2000-01-01T00:00:00+00:00")
        response = self.client.post(
            "/password-reset/confirm/%s" % token,
            {"new_password": "Aa1!ffff", "confirm_password": "Aa1!ffff"},  # pragma: allowlist secret
        )
        self.assertEqual(response["Location"], "/password-reset/request")
        self.assertTrue(self.client.login(username="reset-me@example.com", password="Aa1!aaaa"))  # pragma: allowlist secret


@override_settings(**LOCMEM)
class ResendCooldownTests(TestCase):
    def setUp(self):
        from core import views_auth

        views_auth._COOLDOWNS.clear()

    def test_resend_sends_once_per_cooldown(self):
        make_profile("resend@example.com", email_verified=False)
        self.client.post("/verify-email/resend", {"email": "resend@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        mail.outbox.clear()
        self.client.post("/verify-email/resend", {"email": "resend@example.com"})
        self.assertEqual(len(mail.outbox), 0)
