"""R029: staff-2FA — сервис кода на email и middleware для админки.

Проверяем: выдача/проверка кода (TTL, попытки, non-ASCII), сессионную
отметку, needs_admin_2fa и поведение middleware (redirect/exempt/next).
"""
import re
import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, quote, urlsplit

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core import mail
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from core.admin_2fa import (
    CODE_TTL,
    MAX_ATTEMPTS,
    SESSION_KEY,
    Admin2FAMiddleware,
    clear_verified,
    is_verified,
    issue_code,
    mark_verified,
    needs_admin_2fa,
    verify_code,
)
from core.models import Profile
from core.tests.test_auth import CACHE_LOCMEM, make_profile

PASSWORD = "Aa1!aaaa"  # pragma: allowlist secret

EMAIL_LOCMEM = {
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "TRANSACTIONAL_EMAIL_ASYNC": False,
}


def code_key(user):
    return "admin_2fa_code:%s" % user.pk


def tries_key(user):
    return "admin_2fa_tries:%s" % user.pk


def _wrong_code(stored):
    return "000000" if stored != "000000" else "111111"


@override_settings(CACHES=CACHE_LOCMEM, **EMAIL_LOCMEM)
class Admin2FACodeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_profile("admin-2fa-code@example.com")

    def setUp(self):
        cache.clear()
        mail.outbox.clear()

    def _code_from_mail(self):
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(r"\b(\d{6})\b", mail.outbox[0].body)
        self.assertIsNotNone(match)
        return match.group(1)

    def test_issue_code_sends_mail_and_caches_six_digits(self):
        self.assertTrue(issue_code(self.user))
        self.assertEqual(mail.outbox[0].subject, "Трудник: код входа в админку")
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        code = self._code_from_mail()
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isascii() and code.isdigit())
        self.assertEqual(cache.get(code_key(self.user)), code)

    def test_issue_code_ttl_is_600(self):
        self.assertEqual(CODE_TTL, 600)
        issue_code(self.user)
        expires_at = cache._expire_info[cache.make_key(code_key(self.user))]
        now = time.time()
        self.assertGreater(expires_at, now + CODE_TTL - 60)
        self.assertLessEqual(expires_at, now + CODE_TTL + 60)

    def test_issue_code_resets_attempts(self):
        cache.set(tries_key(self.user), MAX_ATTEMPTS - 1, CODE_TTL)
        issue_code(self.user)
        self.assertIsNone(cache.get(tries_key(self.user)))

    def test_verify_correct_code_returns_true_and_clears_state(self):
        issue_code(self.user)
        code = cache.get(code_key(self.user))
        self.assertTrue(verify_code(self.user, code))
        self.assertIsNone(cache.get(code_key(self.user)))
        self.assertIsNone(cache.get(tries_key(self.user)))

    def test_verify_wrong_code_increments_attempts(self):
        issue_code(self.user)
        stored = cache.get(code_key(self.user))
        self.assertFalse(verify_code(self.user, _wrong_code(stored)))
        self.assertEqual(cache.get(tries_key(self.user)), 1)
        self.assertEqual(cache.get(code_key(self.user)), stored)

    def test_five_wrong_codes_reset_code_and_attempts(self):
        issue_code(self.user)
        stored = cache.get(code_key(self.user))
        wrong = _wrong_code(stored)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self.assertFalse(verify_code(self.user, wrong))
        self.assertIsNone(cache.get(code_key(self.user)))
        self.assertIsNone(cache.get(tries_key(self.user)))
        # Код сброшен: даже правильное значение больше не проходит.
        self.assertFalse(verify_code(self.user, stored))

    def test_non_ascii_and_malformed_codes_rejected_without_500(self):
        issue_code(self.user)
        stored = cache.get(code_key(self.user))
        for bad_code in ("abcdef", "１２３４５６", "код123", "12345", "1234567", "", None, 123456):
            with self.subTest(code=bad_code):
                self.assertFalse(verify_code(self.user, bad_code))
        self.assertEqual(cache.get(code_key(self.user)), stored)

    def test_verify_without_issued_code_is_false(self):
        self.assertFalse(verify_code(self.user, "123456"))

    def test_verify_uses_constant_time_compare_on_bytes(self):
        issue_code(self.user)
        with patch("core.admin_2fa.hmac.compare_digest", return_value=True) as compare:
            self.assertTrue(verify_code(self.user, "123456"))
        self.assertEqual(compare.call_count, 1)
        args = compare.call_args[0]
        self.assertEqual(args[0], b"123456")
        self.assertIsInstance(args[1], bytes)


class Admin2FASessionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_profile("admin-2fa-session@example.com")
        cls.other = make_profile("admin-2fa-session-other@example.com")

    def test_mark_and_is_verified(self):
        request = SimpleNamespace(user=self.user, session={})
        self.assertFalse(is_verified(request))
        mark_verified(request)
        self.assertEqual(request.session[SESSION_KEY], str(self.user.pk))
        self.assertTrue(is_verified(request))

    def test_clear_verified(self):
        request = SimpleNamespace(user=self.user, session={SESSION_KEY: str(self.user.pk)})
        self.assertTrue(is_verified(request))
        clear_verified(request)
        self.assertFalse(is_verified(request))
        self.assertNotIn(SESSION_KEY, request.session)

    def test_clear_verified_is_idempotent(self):
        request = SimpleNamespace(user=self.user, session={})
        clear_verified(request)
        self.assertFalse(is_verified(request))

    def test_other_users_pk_is_not_verified(self):
        request = SimpleNamespace(user=self.user, session={SESSION_KEY: str(self.other.pk)})
        self.assertFalse(is_verified(request))

    def test_anonymous_is_not_verified(self):
        request = SimpleNamespace(user=AnonymousUser(), session={SESSION_KEY: "1"})
        self.assertFalse(is_verified(request))


class NeedsAdmin2FATests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = Profile.objects.create_superuser("admin-2fa-needs-staff@example.com", PASSWORD)
        cls.plain = make_profile("admin-2fa-needs-plain@example.com")

    @staticmethod
    def _request(path="/admin/", user=None, session=None):
        return SimpleNamespace(path=path, user=user, session=session or {})

    @override_settings(ADMIN_2FA_REQUIRED=False)
    def test_flag_off_never_needs(self):
        self.assertFalse(needs_admin_2fa(self._request(user=self.staff)))

    @override_settings(ADMIN_2FA_REQUIRED=True)
    def test_staff_without_mark_needs(self):
        self.assertTrue(needs_admin_2fa(self._request(user=self.staff)))

    @override_settings(ADMIN_2FA_REQUIRED=True)
    def test_admin_root_without_trailing_slash_needs(self):
        self.assertTrue(needs_admin_2fa(self._request(path="/admin", user=self.staff)))

    @override_settings(ADMIN_2FA_REQUIRED=True)
    def test_staff_with_mark_does_not_need(self):
        request = self._request(user=self.staff, session={SESSION_KEY: str(self.staff.pk)})
        self.assertFalse(needs_admin_2fa(request))

    @override_settings(ADMIN_2FA_REQUIRED=True)
    def test_non_staff_does_not_need(self):
        self.assertFalse(needs_admin_2fa(self._request(user=self.plain)))

    @override_settings(ADMIN_2FA_REQUIRED=True)
    def test_non_admin_path_does_not_need(self):
        self.assertFalse(needs_admin_2fa(self._request(path="/profile", user=self.staff)))

    @override_settings(ADMIN_2FA_REQUIRED=True)
    def test_anonymous_does_not_need(self):
        self.assertFalse(needs_admin_2fa(self._request(user=AnonymousUser())))


@override_settings(ADMIN_2FA_REQUIRED=True)
class Admin2FAMiddlewareTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = Profile.objects.create_superuser("admin-2fa-mw-staff@example.com", PASSWORD)
        cls.plain = make_profile("admin-2fa-mw-plain@example.com")

    def setUp(self):
        self.middleware = Admin2FAMiddleware(lambda request: HttpResponse("ok"))

    @staticmethod
    def _request(path="/admin/", user=None, session=None):
        request = RequestFactory().get(path)
        request.user = user if user is not None else AnonymousUser()
        request.session = session or {}
        return request

    def test_staff_without_mark_is_redirected(self):
        response = self.middleware(self._request(user=self.staff))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/admin/2fa/?next="))

    def test_next_is_encoded_and_roundtrips(self):
        path = "/admin/core/profile/?q=test&page=2"
        response = self.middleware(self._request(path=path, user=self.staff))
        location = response["Location"]
        self.assertEqual(location, "/admin/2fa/?next=" + quote(path))
        self.assertIn("%3F", location)
        self.assertIn("%26", location)
        next_value = parse_qs(urlsplit(location).query)["next"][0]
        self.assertEqual(next_value, path)

    def test_exempt_paths_pass(self):
        for path in (
            "/admin/login/",
            "/admin/logout/",
            "/admin/2fa/",
            "/admin/jsi18n/",
            "/admin/static/admin/css/base.css",
        ):
            with self.subTest(path=path):
                response = self.middleware(self._request(path=path, user=self.staff))
                self.assertEqual(response.status_code, 200)

    def test_verified_staff_passes(self):
        request = self._request(
            user=self.staff, session={SESSION_KEY: str(self.staff.pk)}
        )
        self.assertEqual(self.middleware(request).status_code, 200)

    def test_non_staff_passes(self):
        self.assertEqual(self.middleware(self._request(user=self.plain)).status_code, 200)

    def test_anonymous_passes(self):
        self.assertEqual(self.middleware(self._request()).status_code, 200)

    @override_settings(ADMIN_2FA_REQUIRED=False)
    def test_flag_off_passes(self):
        self.assertEqual(self.middleware(self._request(user=self.staff)).status_code, 200)


@override_settings(ADMIN_2FA_REQUIRED=True)
class Admin2FAEndToEndTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = Profile.objects.create_superuser("admin-2fa-e2e@example.com", PASSWORD)

    def test_staff_admin_redirected_to_code_screen(self):
        self.client.force_login(self.staff)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/admin/2fa/?next="))
        self.assertIn(quote("/admin/"), response["Location"])

    def test_staff_admin_passes_after_session_mark(self):
        self.client.force_login(self.staff)
        session = self.client.session
        session[SESSION_KEY] = str(self.staff.pk)
        session.save()
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)

    def test_admin_login_page_is_not_redirected_to_2fa(self):
        self.client.force_login(self.staff)
        response = self.client.get("/admin/login/")
        self.assertNotIn("/admin/2fa/", response.get("Location", ""))


@override_settings(ADMIN_2FA_REQUIRED=True, CACHES=CACHE_LOCMEM, **EMAIL_LOCMEM)
class Admin2FAScreenTests(TestCase):
    """R030: экран /admin/2fa/ — выдача кода, проверка, next и выключенный флаг."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = Profile.objects.create_superuser(
            "admin-2fa-screen@example.com", PASSWORD
        )

    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.client.force_login(self.staff)

    def _code(self):
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(r"\b(\d{6})\b", mail.outbox[0].body)
        self.assertIsNotNone(match)
        return match.group(1)

    def test_get_screen_is_200_sends_code_and_renders_form(self):
        response = self.client.get("/admin/2fa/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.staff.email])
        code = self._code()
        self.assertEqual(len(code), 6)
        self.assertEqual(cache.get(code_key(self.staff)), code)
        self.assertContains(
            response,
            "Введите код из письма, отправленного на %s" % self.staff.email,
        )
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertContains(response, 'name="code"')
        self.assertContains(response, 'name="next"')
        self.assertContains(response, "Подтвердить")
        self.assertContains(response, 'inputmode="numeric"')
        self.assertContains(response, 'maxlength="6"')
        self.assertContains(response, 'autocomplete="one-time-code"')

    def test_repeat_get_within_60s_does_not_send_another_mail(self):
        self.assertEqual(self.client.get("/admin/2fa/").status_code, 200)
        self.assertEqual(self.client.get("/admin/2fa/").status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    def test_wrong_code_stays_on_form_without_session_mark(self):
        self.client.get("/admin/2fa/")
        wrong = _wrong_code(self._code())
        response = self.client.post("/admin/2fa/", {"code": wrong})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(self.client.session.get(SESSION_KEY), str(self.staff.pk))
        self.assertContains(response, "Неверный")
        self.assertEqual(len(mail.outbox), 1)

    def test_correct_code_marks_session_and_redirects_to_next(self):
        self.client.get("/admin/2fa/")
        code = self._code()
        next_url = "/admin/core/profile/"
        response = self.client.post("/admin/2fa/", {"code": code, "next": next_url})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], next_url)
        self.assertEqual(self.client.session.get(SESSION_KEY), str(self.staff.pk))
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_next_outside_admin_prefix_is_replaced(self):
        for bad_next in ("https://evil.example/x", "//evil.example/x", "/jobs"):
            with self.subTest(next=bad_next):
                cache.clear()
                mail.outbox.clear()
                self.client.logout()
                self.client.force_login(self.staff)
                self.client.get("/admin/2fa/")
                code = self._code()
                response = self.client.post(
                    "/admin/2fa/", {"code": code, "next": bad_next}
                )
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], "/admin/")

    def test_get_after_verify_redirects_to_admin_index(self):
        self.client.get("/admin/2fa/")
        code = self._code()
        self.client.post("/admin/2fa/", {"code": code})
        response = self.client.get("/admin/2fa/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/admin/")

    @override_settings(ADMIN_2FA_REQUIRED=False)
    def test_flag_off_redirects_to_admin_index_without_mail(self):
        response = self.client.get("/admin/2fa/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/admin/")
        self.assertEqual(len(mail.outbox), 0)


class Admin2FASettingsTests(SimpleTestCase):
    def test_middleware_registered_after_authentication(self):
        middleware = list(settings.MIDDLEWARE)
        self.assertIn("core.admin_2fa.Admin2FAMiddleware", middleware)
        self.assertGreater(
            middleware.index("core.admin_2fa.Admin2FAMiddleware"),
            middleware.index("django.contrib.auth.middleware.AuthenticationMiddleware"),
        )

    def test_flag_defaults_off(self):
        self.assertFalse(settings.ADMIN_2FA_REQUIRED)
