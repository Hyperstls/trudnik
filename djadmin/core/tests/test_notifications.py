"""Фаза 2д: уведомления (доступ только к своим, отметки, счётчик)."""
import uuid

from django.test import TestCase, override_settings
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
        response = self.client.get("/jobs")
        self.assertContains(response, ">1</output>")  # ровно один непрочитанный

    def test_list_grouped_by_day(self):
        make_notification(self.user, title="Первое J068")
        make_notification(self.user, title="Второе J068")
        response = self.client.get(reverse("core:notifications"))
        self.assertContains(response, "Сегодня")
        self.assertContains(response, "Первое J068")
        self.assertContains(response, "Второе J068")
        self.assertContains(response, 'aria-labelledby="notif-day-')

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


    def test_test_notification_queues_outbox(self):
        from core.models import NotificationOutbox
        response = self.client.post(reverse("core:notification_test"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            NotificationOutbox.objects.filter(user=self.user, type="test").count(), 1
        )


    def test_notifications_page_live_refresh(self):
        response = self.client.get(reverse("core:notifications"))
        self.assertContains(response, 'id="notifications-page"')
        self.assertContains(response, "trudnik:notification")
        self.assertContains(response, "setInterval(refresh, 30000)")


    def test_ws_frame_type_not_overridden(self):
        from core.consumers_notify import notification_frame
        frame = notification_frame({
            "id": "1", "type": "application_received", "title": "Новый отклик",
        })
        self.assertEqual(frame["type"], "notification")
        self.assertEqual(frame["notif_type"], "application_received")
        self.assertEqual(frame["title"], "Новый отклик")


    def test_notifications_mobile_actions_markup(self):
        make_notification(self.user, title="Mobile markup")
        response = self.client.get(reverse("core:notifications"))
        self.assertContains(response, "hidden sm:flex items-center gap-2")
        self.assertContains(response, "sm:hidden px-3 h-9")
        self.assertContains(response, "w-full px-3 h-9")


class NotificationSettingsDiagnosticsTests(TestCase):
    def setUp(self):
        self.user = make_profile("settings-diag@example.com", email_verified=True)
        self.user.notification_prefs = {
            "saved_searches": [{"id": "abc", "name": "Москва удалёнка", "query": "city=Москва", "notify": True}],
        }
        self.user.save(update_fields=["notification_prefs"])
        self.client.force_login(self.user)

    @override_settings(WEB_PUSH_ENABLED=True)
    def test_saved_search_and_ios_help_visible(self):
        response = self.client.get(reverse("core:notification_prefs"))
        self.assertContains(response, "Москва удалёнка")
        self.assertContains(response, "Инструкция для iPhone/iPad")
        self.assertContains(response, reverse("core:toggle_search", args=["abc"]))

    def test_digest_wording_is_plain(self):
        response = self.client.get(reverse("core:notification_prefs"))
        self.assertContains(response, "Новые задания по сохранённым поискам")
        self.assertContains(response, "Раз в день — одна сводка")
        self.assertContains(response, "Сразу — проверяем раз в 5 минут")
        self.assertContains(response, "Сохранённый поиск — это фильтр заданий")
        self.assertNotContains(response, "Частота дайджеста")

    def test_digest_frequency_saved(self):
        response = self.client.post(
            reverse("core:notification_prefs"), {"digest_frequency": "off"},
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.notification_prefs["digest_frequency"], "off")

    def test_toggle_from_settings_returns_to_settings(self):
        response = self.client.post(
            reverse("core:toggle_search", args=["abc"]),
            {"next": reverse("core:notification_prefs")},
        )
        self.assertRedirects(response, reverse("core:notification_prefs"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.notification_prefs["saved_searches"][0]["notify"])
