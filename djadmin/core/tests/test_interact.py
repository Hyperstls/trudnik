"""Фаза 2г: оценки (RPC + триггер пересчёта) и чат (доступ, идемпотентность, poll)."""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Application, Job, Message, Profile, Rating
from core.tests.test_auth import make_profile
from core.tests.test_flows import make_job
import uuid


def make_accepted(employer, worker, status="completed"):
    job = make_job(employer, work_type="Оценочная работа", status=status)
    app = Application.objects.create(job=job, worker=worker, status="accepted")
    return job, app


class RatingTests(TestCase):
    def setUp(self):
        self.employer = make_profile("rate-emp@example.com")
        self.worker = make_profile("rate-worker@example.com", role="worker")
        self.job, self.app = make_accepted(self.employer, self.worker)

    def test_employer_rates_worker_trigger_recomputes(self):
        self.client.force_login(self.employer)
        response = self.client.post(
            reverse("core:rate_participant", args=[self.app.pk]), {"rating": "5", "comment": "Отлично"}
        )
        self.assertEqual(response.status_code, 302)
        rating = Rating.objects.get(rater_user=self.employer, job=self.job)
        self.assertEqual(rating.rating, 5)
        self.assertEqual(rating.target_type, "worker")
        # триггер recompute_profile_rating пересчитал профиль (БД, не Python)
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.ratings_count, 1)
        self.assertEqual(self.worker.rating, 5.0)

    def test_worker_rates_employer(self):
        self.client.force_login(self.worker)
        self.client.post(reverse("core:rate_participant", args=[self.app.pk]), {"rating": "4"})
        rating = Rating.objects.get(rater_user=self.worker, job=self.job)
        self.assertEqual(rating.target_type, "employer")
        self.employer.refresh_from_db()
        self.assertEqual(self.employer.ratings_count, 1)

    def test_upsert_updates_not_duplicates(self):
        self.client.force_login(self.employer)
        self.client.post(reverse("core:rate_participant", args=[self.app.pk]), {"rating": "3"})
        self.client.post(reverse("core:rate_participant", args=[self.app.pk]), {"rating": "5"})
        self.assertEqual(Rating.objects.filter(rater_user=self.employer, job=self.job).count(), 1)
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.rating, 5.0)

    def test_only_after_completed(self):
        job = make_job(self.employer, status="open")
        app = Application.objects.create(job=job, worker=self.worker, status="accepted")
        self.client.force_login(self.employer)
        self.client.post(reverse("core:rate_participant", args=[app.pk]), {"rating": "5"})
        self.assertFalse(Rating.objects.exists())

    def test_stranger_cannot_rate(self):
        stranger = make_profile("rate-stranger@example.com")
        self.client.force_login(stranger)
        response = self.client.post(reverse("core:rate_participant", args=[self.app.pk]), {"rating": "5"})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Rating.objects.exists())

    def test_bad_stars_rejected(self):
        self.client.force_login(self.employer)
        self.client.post(reverse("core:rate_participant", args=[self.app.pk]), {"rating": "9"})
        self.assertFalse(Rating.objects.exists())


class ChatTests(TestCase):
    def setUp(self):
        self.employer = make_profile("chat-emp@example.com")
        self.worker = make_profile("chat-worker@example.com", role="worker")
        self.job = make_job(self.employer, work_type="Чатовая работа")
        self.app = Application.objects.create(job=self.job, worker=self.worker, status="accepted")

    def test_room_requires_participant(self):
        stranger = make_profile("chat-stranger@example.com")
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(reverse("core:chat_room", args=[self.app.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("core:chat_poll", args=[self.app.pk])).status_code, 404)

    def test_participants_see_room(self):
        self.client.force_login(self.worker)
        self.assertEqual(self.client.get(reverse("core:chat_room", args=[self.app.pk])).status_code, 200)
        self.client.force_login(self.employer)
        self.assertEqual(self.client.get(reverse("core:chat_room", args=[self.app.pk])).status_code, 200)

    def test_send_and_poll(self):
        self.client.force_login(self.worker)
        cmid = str(uuid.uuid4())
        self.client.post(reverse("core:chat_send", args=[self.app.pk]),
                         {"content": "Здравствуйте!", "client_message_id": cmid})
        self.assertEqual(Message.objects.filter(application=self.app).count(), 1)
        # poll: работодатель видит сообщение
        self.client.force_login(self.employer)
        data = self.client.get(reverse("core:chat_poll", args=[self.app.pk]), {"after": 0}).json()
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["content"], "Здравствуйте!")
        # after=последний id → пусто
        data2 = self.client.get(reverse("core:chat_poll", args=[self.app.pk]),
                                {"after": data["messages"][0]["id"]}).json()
        self.assertEqual(data2["messages"], [])

    def test_send_idempotent_by_client_message_id(self):
        self.client.force_login(self.worker)
        cmid = str(uuid.uuid4())
        for _ in range(2):
            self.client.post(reverse("core:chat_send", args=[self.app.pk]),
                             {"content": "Только один раз", "client_message_id": cmid})
        self.assertEqual(Message.objects.filter(application=self.app).count(), 1)

    def test_empty_message_ignored(self):
        self.client.force_login(self.worker)
        self.client.post(reverse("core:chat_send", args=[self.app.pk]),
                         {"content": "   ", "client_message_id": str(uuid.uuid4())})
        self.assertEqual(Message.objects.filter(application=self.app).count(), 0)

    def test_chats_list_both_sides(self):
        Message.objects.create(sender=self.worker, application=self.app, content="привет")
        self.client.force_login(self.worker)
        self.assertContains(self.client.get(reverse("core:chats")), "привет")
        self.client.force_login(self.employer)
        self.assertContains(self.client.get(reverse("core:chats")), "привет")

class ChatConsumerLogicTests(TestCase):
    """Логика WS-consumer (participation + безопасный notify) — без транспорта."""

    def setUp(self):
        self.employer = make_profile("ws-emp@example.com")
        self.worker = make_profile("ws-worker@example.com", role="worker")
        self.job = make_job(self.employer, work_type="WS-работа")
        self.app = Application.objects.create(job=self.job, worker=self.worker, status="accepted")

    def test_participant_check(self):
        from core.consumers import ChatConsumer

        self.assertTrue(ChatConsumer._is_participant(self.app.pk, self.worker.pk))
        self.assertTrue(ChatConsumer._is_participant(self.app.pk, self.employer.pk))
        stranger = make_profile("ws-stranger@example.com")
        self.assertFalse(ChatConsumer._is_participant(self.app.pk, stranger.pk))
        self.assertFalse(ChatConsumer._is_participant("00000000-0000-0000-0000-000000000000", self.worker.pk))

    def test_notify_new_message_safe_without_redis(self):
        from core.consumers import notify_new_message

        # InMemoryChannelLayer в тестах; вызов не должен падать и не обязан доставлять
        notify_new_message(self.app.pk, {"id": 1, "sender_id": str(self.worker.pk), "content": "x", "created_at": ""})
