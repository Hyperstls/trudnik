"""Фаза 2д: уведомления (доступ только к своим, отметки, счётчик)."""
import uuid

from django.test import TestCase
from django.urls import reverse

from core.models import Notification, Profile
from core.tests.test_auth import make_profile


def make_notification(user, title="Тестовое", is_read=False, n_type="info"):
    return Notification.objects.create(
        user=user, type=n_type, title=title, message="Текст", is_read=is_read,
    )


class NotificationTests(TestCase):
    def setUp(self):
        self.user = make_profile("notify-me@example.com")
        self.other = make_profile("notify-other@example.com")
        self.client.force_login(self.user)

    def test_list_shows_own_only(self):
        mine = make_notification(self.user, title="Моё уведомление")
        make_notification(self.other, title="Чужое уведомление")
        response = self.client.get(reverse("core:notifications"))
        self.assertContains(response, "Моё уведомление")
        self.assertNotContains(response, "Чужое уведомление")

    def test_unread_badge_context(self):
        make_notification(self.user)
        make_notification(self.user, is_read=True)
        response = self.client.get("/")
        self.assertContains(response, ">1</span>")  # ровно один непрочитанный

    def test_mark_read(self):
        n = make_notification(self.user)
        self.client.post(reverse("core:notification_mark_read", args=[n.pk]))
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_cannot_touch_foreign(self):
        n = make_notification(self.other)
        self.assertEqual(
            self.client.post(reverse("core:notification_mark_read", args=[n.pk])).status_code, 404
        )
        self.assertEqual(
            self.client.post(reverse("core:notification_delete", args=[n.pk])).status_code, 404
        )
        self.assertTrue(Notification.objects.filter(pk=n.pk).exists())

    def test_mark_all_read(self):
        make_notification(self.user)
        make_notification(self.user)
        make_notification(self.other)  # чужие не трогаем
        self.client.post(reverse("core:notifications_mark_all_read"))
        self.assertFalse(Notification.objects.filter(user=self.user, is_read=False).exists())
        self.assertTrue(Notification.objects.filter(user=self.other, is_read=False).exists())

    def test_delete_own(self):
        n = make_notification(self.user)
        self.client.post(reverse("core:notification_delete", args=[n.pk]))
        self.assertFalse(Notification.objects.filter(pk=n.pk).exists())

    def test_unread_count_json(self):
        make_notification(self.user)
        make_notification(self.user)
        data = self.client.get(reverse("core:notifications_unread_count")).json()
        self.assertEqual(data["unread_count"], 2)

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("core:notifications")).status_code, 302)
