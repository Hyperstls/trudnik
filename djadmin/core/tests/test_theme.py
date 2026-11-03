"""Dark/light theme entry points (J142)."""
from django.test import SimpleTestCase
from django.urls import reverse


class ThemeTests(SimpleTestCase):
    def test_login_exposes_theme_toggle_and_controller(self):
        response = self.client.get(reverse("core:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="theme-toggle"')
        self.assertContains(response, "trudnik-theme")
        self.assertContains(response, "js/theme.js")

    def test_color_scheme_meta_allows_both(self):
        response = self.client.get(reverse("core:login"))
        self.assertContains(response, 'name="color-scheme" content="light dark"')
