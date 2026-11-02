"""Фаза 2б: регистрация, подтверждение email, сброс пароля.

Всё гоняется против клона dev-БД: register_user/change_password RPC — настоящие,
токены — itsdangerous в формате Flask (кросс-совместимость проверена прямым тестом).
"""
import os
import sys
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings

PW_REG = "Aa1!" + "bbbb"
PW_RESET = "Aa1!" + "cccc"
PW_RESET2 = "Aa1!" + "dddd"
PW_RESET3 = "Aa1!" + "eeee"
PW_STALE = "Aa1!" + "ffff"
PW_CURRENT = "Aa1!" + "aaaa"

LOCMEM = {
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    # существующие mail-тесты проверяют письмо сразу — отправка синхронная
    "TRANSACTIONAL_EMAIL_ASYNC": False,
}
from django.utils import timezone
from itsdangerous import URLSafeTimedSerializer

from core import tokens
from core.models import Profile, Skill, UserSkill
from core.tests.test_auth import CACHE_LOCMEM, make_profile

REG = {
    "email": "New.User@Example.com",
    "full_name": "Новый Пользователь",
    "city": "Сергиев Посад",
    "password": PW_REG,  # pragma: allowlist secret
    "intent": "both",
    "consent": "on",
    "website": "",
    "smart_token": "",
}

class SmtpSettingsTests(TestCase):
    def test_smtp_user_alias(self):
        from config.settings import _smtp_username

        with patch.dict(
            os.environ,
            {"SMTP_USER": "primary@example.com", "SMTP_USERNAME": "legacy@example.com"},
        ):
            self.assertEqual(_smtp_username(), "primary@example.com")
        with patch.dict(
            os.environ,
            {"SMTP_USER": "", "SMTP_USERNAME": "legacy@example.com"},
        ):
            self.assertEqual(_smtp_username(), "legacy@example.com")


@override_settings(**LOCMEM)
@override_settings(CACHES=CACHE_LOCMEM)
class RegisterTests(TestCase):
    def setUp(self):
        mail.outbox.clear()
        cache.clear()  # IP-лимиты регистрации живут в общем кэше — изолируем тесты
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
        self.assertFalse(self.client.login(username="new.user@example.com", password=PW_REG))  # pragma: allowlist secret

    def test_register_stepper_markup(self):
        response = self.client.get("/register")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-register-stepper")
        for step in (1, 2, 3):
            self.assertContains(response, 'data-register-step="%d"' % step)
        self.assertContains(response, 'data-register-indicator="1"')
        self.assertContains(response, 'id="register-next"')
        self.assertContains(response, 'id="register-submit-wrap"')
        self.assertContains(response, "js/register-step.js")
        self.assertContains(response, "<noscript>")

    def test_register_preserves_intent_on_validation_error(self):
        data = {
            **REG,
            "email": "bad-email",
            "password": "short",  # pragma: allowlist secret
            "full_name": "",
            "intent": "find_work",
        }
        response = self.client.post("/register", data, REMOTE_ADDR="10.22.0.1")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="find_work" class="sr-only" checked')

    @patch("core.views_auth.verify_captcha_token", return_value=True)
    def test_register_redirects_to_resend_page(self, mock_verify):
        email = "resend-redirect@example.com"
        response = self.client.post("/register", {**REG, "email": email})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/verify-email/resend", response["Location"])
        self.assertIn("resend-redirect%40example.com", response["Location"])

    def test_register_intent_post_jobs_maps_to_employer(self):
        self.client.post("/register", {**REG, "email": "employer-reg@example.com", "intent": "post_jobs"})
        profile = Profile.objects.get(email="employer-reg@example.com")
        self.assertEqual(profile.role, "employer")
        self.assertFalse(profile.worker_visibility)

    def test_register_persists_extended_worker_fields(self):
        skill, _ = Skill.objects.get_or_create(name="Навык регистрации P101")
        response = self.client.post("/register", {
            **REG,
            "email": "ext-worker@example.com",
            "portfolio_link": "https://example.com/portfolio",
            "contact": "@ext_worker",
            "inn": "500100732259",
            "is_self_employed": "on",
            "experience": "5 лет отделки",
            "desired_payment": "1500.00",
            "skills": [str(skill.pk)],
        })
        self.assertEqual(response.status_code, 302)
        profile = Profile.objects.get(email="ext-worker@example.com")
        self.assertEqual(profile.city, "Сергиев Посад")
        self.assertEqual(profile.portfolio_link, "https://example.com/portfolio")
        self.assertEqual(profile.contact, "@ext_worker")
        self.assertEqual(profile.inn, "500100732259")
        self.assertTrue(profile.is_self_employed)
        self.assertEqual(profile.experience, "5 лет отделки")
        self.assertEqual(str(profile.desired_payment), "1500.00")
        self.assertTrue(UserSkill.objects.filter(user=profile, skill=skill).exists())

    def test_register_employer_ignores_worker_fields(self):
        skill, _ = Skill.objects.get_or_create(name="Навык работодателя P101")
        response = self.client.post("/register", {
            **REG,
            "email": "ext-employer@example.com",
            "intent": "post_jobs",
            "portfolio_link": "https://example.com/company",
            "contact": "@ext_employer",
            "inn": "123456789012",
            "is_self_employed": "on",
            "experience": "не сохранять",
            "desired_payment": "999.00",
            "skills": [str(skill.pk)],
        })
        self.assertEqual(response.status_code, 302)
        profile = Profile.objects.get(email="ext-employer@example.com")
        self.assertEqual(profile.role, "employer")
        # общие поля сохранены
        self.assertEqual(profile.city, "Сергиев Посад")
        self.assertEqual(profile.portfolio_link, "https://example.com/company")
        self.assertIsNotNone(profile.consented_at)
        # worker-only поля и навыки не сохранены
        self.assertFalse(profile.contact)
        self.assertFalse(profile.inn)
        self.assertFalse(profile.is_self_employed)
        self.assertFalse(profile.experience)
        self.assertIsNone(profile.desired_payment)
        self.assertFalse(UserSkill.objects.filter(user=profile).exists())

    def test_honeypot_rejected(self):
        self.client.post("/register", {**REG, "email": "bot@example.com", "website": "http://spam.io"})
        self.assertFalse(Profile.objects.filter(email="bot@example.com").exists())

    def test_weak_password_rejected(self):
        self.client.post("/register", {**REG, "email": "weak@example.com", "password": "simple"})  # pragma: allowlist secret
        self.assertFalse(Profile.objects.filter(email="weak@example.com").exists())

    def test_register_invalid_inn_checksum(self):
        # формат 12 цифр, но контрольная сумма не сходится (P102)
        response = self.client.post("/register", {
            **REG, "email": "bad-inn@example.com", "inn": "500100732258",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "контрольную сумму")
        self.assertFalse(Profile.objects.filter(email="bad-inn@example.com").exists())

    def test_register_invalid_contact(self):
        # короче 3 символов и мусорный формат — оба отклоняются (P102)
        for contact in ("ab", "!!@@@$$"):
            response = self.client.post("/register", {
                **REG, "email": "bad-contact@example.com", "contact": contact,
            })
            self.assertEqual(response.status_code, 200)
            self.assertFalse(Profile.objects.filter(email="bad-contact@example.com").exists())
        self.assertContains(response, "корректный контакт")

    def test_register_password_with_space_rejected(self):
        response = self.client.post("/register", {
            **REG, "email": "space-pw@example.com", "password": "Aa1! aaaa",  # pragma: allowlist secret
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "пробел")
        self.assertFalse(Profile.objects.filter(email="space-pw@example.com").exists())

    def test_register_cyrillic_password_rejected(self):
        # «Пароль1!» содержит кириллические верхний/нижний регистр — Flask-паритет:
        # [A-Z]/[a-z] их не засчитывает.
        response = self.client.post("/register", {
            **REG, "email": "cyr-pw@example.com", "password": "Пароль1!",  # pragma: allowlist secret
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "заглавную букву")
        self.assertFalse(Profile.objects.filter(email="cyr-pw@example.com").exists())

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
    @patch("core.captcha.urllib.request.urlopen")
    def test_captcha_uses_form_urlencoded(self, mock_urlopen):
        # Yandex принимает только form-urlencoded; JSON → 403 "No secret provided"
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"status":"ok"}'
        mock_urlopen.return_value = response
        from core.captcha import verify_captcha_token

        self.assertTrue(verify_captcha_token("tok-captcha"))
        request = mock_urlopen.call_args[0][0]
        self.assertEqual(
            request.full_url, "https://smartcaptcha.cloud.yandex.ru/validate"
        )
        self.assertEqual(
            request.get_header("Content-type"),
            "application/x-www-form-urlencoded",
        )
        self.assertEqual(
            request.data, b"secret=test-server-key&token=tok-captcha"
        )

    @override_settings(SMARTCAPTCHA_SERVER_KEY="test-server-key")
    def test_captcha_fail_closed(self):
        # ключ задан, токена нет → отказ без создания профиля
        response = self.client.post("/register", {**REG, "email": "captcha@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Капча не пройдена")
        self.assertFalse(Profile.objects.filter(email="captcha@example.com").exists())

    @override_settings(SMARTCAPTCHA_SERVER_KEY="test-server-key")
    @patch("core.views_auth.verify_captcha_token", return_value=True)
    def test_register_accepts_yandex_smart_token_field(self, mock_verify):
        # виджет Yandex кладёт токен в поле `smart-token`, а не `smart_token`
        response = self.client.post(
            "/register",
            {**REG, "email": "smart-token@example.com", "smart-token": "tok-register"},
        )
        mock_verify.assert_called_once_with("tok-register")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Profile.objects.filter(email="smart-token@example.com").exists())

    @override_settings(CACHES=CACHE_LOCMEM)
    def test_register_ip_rate_limit(self):
        # AUTH-P1-11: 10 POST с одного IP за час проходят, 11-й блокируется
        ip = "198.51.100.91"
        for _ in range(10):
            self.client.post("/register", REG, REMOTE_ADDR=ip)
        response = self.client.post("/register", REG, REMOTE_ADDR=ip)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Слишком много попыток регистрации")

    def test_register_cache_unavailable_fail_closed(self):
        # AUTH-P1-04: кэш недоступен — регистрация закрыта, профиль не создан
        with patch("core.ratelimit.cache.add", side_effect=RuntimeError("cache down")):
            response = self.client.post("/register", {**REG, "email": "cache-down@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "временно недоступен")
        self.assertFalse(Profile.objects.filter(email="cache-down@example.com").exists())

    @override_settings(TRANSACTIONAL_EMAIL_ASYNC=True)
    @patch("core.tasks.send_transactional_email.delay")
    def test_transactional_email_enqueued(self, mock_delay):
        # AUTH-P1-05: async-режим — письмо уходит в Celery, не в SMTP синхронно
        response = self.client.post("/register", {**REG, "email": "queued@example.com"})
        self.assertEqual(response.status_code, 302)
        mock_delay.assert_called_once()
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(TRANSACTIONAL_EMAIL_ASYNC=True)
    @patch("core.tasks.send_transactional_email.delay", side_effect=RuntimeError("broker down"))
    def test_transactional_email_fallback_on_broker_error(self, mock_delay):
        # AUTH-P1-05: брокер недоступен — синхронный fallback, регистрация не падает
        response = self.client.post("/register", {**REG, "email": "fallback@example.com"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Profile.objects.filter(email="fallback@example.com").exists())
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(TRANSACTIONAL_EMAIL_ASYNC=True)
    def test_transactional_email_fallback_on_import_error(self):
        # AUTH-P1-05: сбой импорта/Celery-конфига — тоже синхронный fallback
        with patch.dict(sys.modules, {"core.tasks": None}):
            response = self.client.post("/register", {**REG, "email": "import-fail@example.com"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Profile.objects.filter(email="import-fail@example.com").exists())
        self.assertEqual(len(mail.outbox), 1)


@override_settings(**LOCMEM)
@override_settings(CACHES=CACHE_LOCMEM)
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
@override_settings(CACHES=CACHE_LOCMEM)
class PasswordResetTests(TestCase):
    def setUp(self):
        mail.outbox.clear()
        cache.clear()  # cooldown/IP-лимиты живут в общем кэше — изолируем тесты
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

    @override_settings(SMARTCAPTCHA_SERVER_KEY="test-server-key")
    @patch("core.views_auth.verify_captcha_token", return_value=True)
    def test_reset_request_accepts_yandex_smart_token_field(self, mock_verify):
        # виджет Yandex кладёт токен в поле `smart-token`, а не `smart_token`
        response = self.client.post(
            "/password-reset/request",
            {"email": "reset-me@example.com", "smart-token": "tok-reset"},
        )
        mock_verify.assert_called_once_with("tok-reset")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/password-reset/confirm/", mail.outbox[0].body)

    def test_confirm_changes_password_and_old_token_dies(self):
        self._request()
        token = mail.outbox[0].body.split("/password-reset/confirm/")[1].split()[0]
        response = self.client.post(
            "/password-reset/confirm/%s" % token,
            {"new_password": PW_RESET, "confirm_password": PW_RESET},  # pragma: allowlist secret
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.client.login(username="reset-me@example.com", password=PW_CURRENT))  # pragma: allowlist secret
        self.assertTrue(self.client.login(username="reset-me@example.com", password=PW_RESET))  # pragma: allowlist secret
        # B11: после смены пароля password_changed_at изменился — старый токен мёртв
        response = self.client.post(
            "/password-reset/confirm/%s" % token,
            {"new_password": PW_RESET2, "confirm_password": PW_RESET2},  # pragma: allowlist secret
        )
        self.assertEqual(response["Location"], "/password-reset/request")
        self.assertTrue(self.client.login(username="reset-me@example.com", password=PW_RESET))  # pragma: allowlist secret

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
            {"new_password": PW_RESET3, "confirm_password": PW_RESET3},  # pragma: allowlist secret
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.client.login(username="reset-me@example.com", password=PW_RESET3))  # pragma: allowlist secret

    def test_stale_token_rejected(self):
        token = tokens.generate_reset_token("reset-me@example.com", "2000-01-01T00:00:00+00:00")
        response = self.client.post(
            "/password-reset/confirm/%s" % token,
            {"new_password": PW_STALE, "confirm_password": PW_STALE},  # pragma: allowlist secret
        )
        self.assertEqual(response["Location"], "/password-reset/request")
        self.assertTrue(self.client.login(username="reset-me@example.com", password=PW_CURRENT))  # pragma: allowlist secret


@override_settings(**LOCMEM)
@override_settings(CACHES=CACHE_LOCMEM)
class ResendCooldownTests(TestCase):
    def setUp(self):
        cache.clear()  # cooldown ресенда живёт в общем кэше — изолируем тесты

    def test_resend_page_prefills_email(self):
        response = self.client.get("/verify-email/resend", {"email": "prefill@example.com"})
        self.assertContains(response, 'value="prefill@example.com"')

    def test_resend_post_stays_on_resend_page(self):
        make_profile("resend-stay@example.com", email_verified=False)
        response = self.client.post(
            "/verify-email/resend", {"email": "resend-stay@example.com"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/verify-email/resend", response["Location"])
        self.assertIn("resend-stay%40example.com", response["Location"])

    def test_resend_sends_once_per_cooldown(self):
        make_profile("resend@example.com", email_verified=False)
        self.client.post("/verify-email/resend", {"email": "resend@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        mail.outbox.clear()
        self.client.post("/verify-email/resend", {"email": "resend@example.com"})
        self.assertEqual(len(mail.outbox), 0)
