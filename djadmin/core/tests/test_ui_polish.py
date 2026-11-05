"""R008A: тосты в base.html на мобильных + отсутствие дублей сообщений на /login."""
from django.core.cache import cache
from django.test import TestCase, override_settings

from core.tests.test_auth import CACHE_LOCMEM, make_profile

TOAST_CONTAINER_CLASS = "fixed top-16 left-4 right-4 sm:left-auto z-[90] space-y-2 sm:max-w-sm"
LOGIN_ERROR_TEXT = "Неверный email или пароль, либо аккаунт заблокирован/не подтверждён."


@override_settings(CACHES=CACHE_LOCMEM)
class LoginMessageToastTests(TestCase):
    def setUp(self):
        cache.clear()  # rate-limit/lockout живут в общем кэше — изолируем тесты

    def test_login_error_rendered_once(self):
        make_profile("ui-polish@example.com")
        response = self.client.post(
            "/login",
            {"email": "ui-polish@example.com", "password": "bad"},  # pragma: allowlist secret
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertEqual(html.count(LOGIN_ERROR_TEXT), 1)

    def test_toast_container_has_mobile_classes(self):
        make_profile("ui-polish-classes@example.com")
        response = self.client.post(
            "/login",
            {"email": "ui-polish-classes@example.com", "password": "bad"},  # pragma: allowlist secret
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, TOAST_CONTAINER_CLASS)
        html = response.content.decode("utf-8")
        for css_class in ("left-4", "right-4", "sm:left-auto", "sm:max-w-sm"):
            self.assertIn(css_class, html)

    def test_login_without_messages_has_no_toast_container(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, TOAST_CONTAINER_CLASS)
