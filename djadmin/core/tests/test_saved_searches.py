"""Страница сохранённых поисков (J163)."""
from django.test import TestCase
from django.urls import reverse

from core.models import Profile, Skill
from core.tests.test_auth import make_profile


class SavedSearchesPageTests(TestCase):
    def setUp(self):
        self.user = make_profile("searches-page@example.com")
        self.skill = Skill.objects.create(name="Поисковый навык", sort_order=1)
        self.prefs = {
            "saved_searches": [{
                "id": "abc123",
                "name": "Москва — уборка",
                "query": "city=Москва&skills=%s&payment_max=2000&status=open" % self.skill.pk,
                "notify": True,
            }],
        }
        Profile.objects.filter(pk=self.user.pk).update(notification_prefs=self.prefs)
        self.client.force_login(self.user)

    def test_page_shows_search_and_filters(self):
        response = self.client.get(reverse("core:my_searches"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Москва — уборка")
        self.assertContains(response, "Город")
        self.assertContains(response, "Поисковый навык")
        self.assertContains(response, "Оплата до")
        self.assertContains(response, "Открытые")

    def test_toggle_returns_to_page(self):
        response = self.client.post(
            reverse("core:toggle_search", args=["abc123"]),
            {"next": reverse("core:my_searches")},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("core:my_searches"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.notification_prefs["saved_searches"][0]["notify"])

    def test_delete_returns_to_page(self):
        response = self.client.post(
            reverse("core:delete_search", args=["abc123"]),
            {"next": reverse("core:my_searches")},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("core:my_searches"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.notification_prefs["saved_searches"], [])

    def test_empty_state(self):
        Profile.objects.filter(pk=self.user.pk).update(notification_prefs={})
        response = self.client.get(reverse("core:my_searches"))
        self.assertContains(response, "Сохранённых поисков нет")
