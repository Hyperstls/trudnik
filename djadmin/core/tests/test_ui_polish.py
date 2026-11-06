"""R008A: тосты в base.html на мобильных + отсутствие дублей сообщений на /login.

R036: футер без дублей навигации, «Информация» — иконка в шапке и пункт меню профиля.
"""
import re

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.tests.test_auth import CACHE_LOCMEM, make_profile

TOAST_CONTAINER_CLASS = "fixed top-16 left-4 right-4 sm:left-auto z-[90] space-y-2 sm:max-w-sm"
LOGIN_ERROR_TEXT = "Неверный email или пароль, либо аккаунт заблокирован/не подтверждён."

FOOTER_RE = re.compile(r"<footer\b.*?</footer>", re.DOTALL)
HEADER_RE = re.compile(r"<header\b.*?</header>", re.DOTALL)
PROFILE_MENU_RE = re.compile(r'<div id="profile-menu".*?</div>', re.DOTALL)


def _extract(pattern, html, label):
    match = pattern.search(html)
    if match is None:
        raise AssertionError("{} not found in rendered page".format(label))
    return match.group(0)


def _anchors_with_href(html, href):
    return re.findall(r'<a\b[^>]*href="' + re.escape(href) + r'"[^>]*>', html)


def _classes(tag):
    match = re.search(r'class="([^"]*)"', tag)
    return match.group(1).split() if match else []


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


class FooterNavTests(TestCase):
    """R036: дубли футера — только для анонимов; «Информация» из футера убрана."""

    LEGAL_LABELS = ("Условия", "Конфиденциальность", "Безопасность", "Вопросы", "Поддержка")

    def _footer(self):
        response = self.client.get(reverse("core:jobs"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        return _extract(FOOTER_RE, html, "footer")

    def test_footer_keeps_public_links_for_anonymous(self):
        footer = self._footer()
        for href in ('/workers', '/employers', '/app'):
            self.assertIn('href="{}"'.format(href), footer)
        self.assertNotIn("Информация", footer)
        for label in self.LEGAL_LABELS:
            self.assertIn(label, footer)

    def test_footer_has_no_duplicate_links_for_authenticated(self):
        user = make_profile("ui-polish-footer@example.com")
        self.client.force_login(user)
        footer = self._footer()
        for href in ('/workers', '/employers', '/app'):
            self.assertNotIn('href="{}"'.format(href), footer)
        self.assertNotIn('href="/app/download"', footer)
        self.assertNotIn("Информация", footer)
        for label in self.LEGAL_LABELS:
            self.assertIn(label, footer)


class HeaderInfoIconTests(TestCase):
    """R036: «Информация» — иконка в шапке; у анонимов видна и на мобильных."""

    def _header_and_icon(self):
        response = self.client.get(reverse("core:jobs"))
        self.assertEqual(response.status_code, 200)
        header = _extract(HEADER_RE, response.content.decode("utf-8"), "header")
        for tag in _anchors_with_href(header, "/info"):
            if 'aria-label="Информация"' in tag:
                return header, tag
        raise AssertionError("/info icon with aria-label not found in header")

    def test_header_info_icon_anonymous_visible_on_mobile(self):
        header, tag = self._header_and_icon()
        self.assertIn('title="Информация"', tag)
        classes = _classes(tag)
        self.assertIn("flex", classes)
        self.assertNotIn("hidden", classes)
        self.assertLess(header.index(tag), header.index('id="theme-toggle"'))

    def test_header_info_icon_authenticated_desktop_only(self):
        user = make_profile("ui-polish-header@example.com")
        self.client.force_login(user)
        header, tag = self._header_and_icon()
        self.assertIn('title="Информация"', tag)
        classes = _classes(tag)
        self.assertIn("hidden", classes)
        self.assertIn("md:flex", classes)
        self.assertNotIn("flex", classes)
        self.assertLess(header.index(tag), header.index('id="theme-toggle"'))


class ProfileMenuInfoTests(TestCase):
    """R036: пункт «Информация» в меню профиля."""

    def test_profile_menu_has_info_item(self):
        user = make_profile("ui-polish-menu@example.com")
        self.client.force_login(user)
        response = self.client.get(reverse("core:jobs"))
        self.assertEqual(response.status_code, 200)
        menu = _extract(
            PROFILE_MENU_RE, response.content.decode("utf-8"), "profile menu",
        )
        links = _anchors_with_href(menu, "/info")
        self.assertEqual(len(links), 1, "expected exactly one /info item in profile menu")
        self.assertIn('role="menuitem"', links[0])
        self.assertIn("Информация", menu)
