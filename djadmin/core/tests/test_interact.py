"""Фаза 2г: оценки (RPC + триггер пересчёта) и чат (доступ, идемпотентность, poll)."""
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Application, Job, Message, Profile, Rating
from core.storage import delete_upload_url
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

    def test_pending_application_cannot_rate(self):
        job = make_job(self.employer, status="completed")
        app = Application.objects.create(job=job, worker=self.worker, status="pending")
        self.client.force_login(self.employer)
        self.client.post(reverse("core:rate_participant", args=[app.pk]), {"rating": "5"})
        self.client.force_login(self.worker)
        self.client.post(reverse("core:rate_participant", args=[app.pk]), {"rating": "5"})
        self.assertFalse(Rating.objects.filter(job=job).exists())

    def test_ratings_page_works_for_admin_employer(self):
        admin = make_profile("admin-ratings@example.com", role="admin")
        job = make_job(admin, status="open")
        response = self.client.get(reverse("core:user_ratings", args=[admin.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Отзывы о")
        self.assertContains(response, reverse("core:jobs"))

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

    def test_employer_rates_two_workers_update_keeps_other(self):
        worker2 = make_profile("rate-worker2@example.com", role="worker")
        app2 = Application.objects.create(job=self.job, worker=worker2, status="accepted")
        self.client.force_login(self.employer)
        self.client.post(reverse("core:rate_participant", args=[self.app.pk]), {"rating": "5"})
        self.client.post(reverse("core:rate_participant", args=[app2.pk]), {"rating": "4"})
        self.assertEqual(
            Rating.objects.filter(rater_user=self.employer, job=self.job).count(), 2
        )
        # повторная оценка первого работника не должна затирать оценку второго
        self.client.post(reverse("core:rate_participant", args=[self.app.pk]), {"rating": "3"})
        first = Rating.objects.get(
            rater_user=self.employer, job=self.job, rated_user=self.worker
        )
        second = Rating.objects.get(
            rater_user=self.employer, job=self.job, rated_user=worker2
        )
        self.assertEqual((first.rating, second.rating), (3, 4))

    def test_pending_worker_cannot_rate_employer(self):
        job = make_job(self.employer, status="completed")
        app = Application.objects.create(job=job, worker=self.worker, status="pending")
        self.client.force_login(self.worker)
        self.client.post(reverse("core:rate_participant", args=[app.pk]), {"rating": "5"})
        self.assertFalse(Rating.objects.filter(rater_user=self.worker).exists())

    def test_job_detail_reviews_filter_by_target_type(self):
        Rating.objects.create(
            rated_user=self.employer, rater_user=self.worker, job=self.job,
            rating=5, comment="Отзыв о работодателе целевой",
            rating_type="worker", target_type="employer",
        )
        Rating.objects.create(
            rated_user=self.worker, rater_user=self.employer, job=self.job,
            rating=4, comment="Оценка работнику не в блоке отзывов",
            rating_type="employer", target_type="worker",
        )
        response = self.client.get(f"/jobs/{self.job.pk}")
        self.assertContains(response, "Отзыв о работодателе целевой")
        self.assertNotContains(response, "Оценка работнику не в блоке отзывов")


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

    def test_send_attachment_and_render(self):
        self.client.force_login(self.worker)
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
        upload = SimpleUploadedFile("photo.png", png, content_type="image/png")
        self.client.post(
            reverse("core:chat_send", args=[self.app.pk]),
            {"content": "", "client_message_id": str(uuid.uuid4()), "attachment": upload},
        )
        msg = Message.objects.get(application=self.app)
        try:
            self.assertEqual(msg.attachment_name, "photo.png")
            self.assertEqual(msg.attachment_mime, "image/png")
            self.assertTrue(msg.attachment_url.startswith("/uploads/chat/"))
            self.assertEqual(msg.content, "")
            response = self.client.get(reverse("core:chat_room", args=[self.app.pk]))
            self.assertContains(response, msg.attachment_url)
            poll = self.client.get(
                reverse("core:chat_poll", args=[self.app.pk]), {"after": 0}
            ).json()
            self.assertEqual(poll["messages"][0]["attachment_url"], msg.attachment_url)
        finally:
            delete_upload_url(msg.attachment_url)

    def test_invalid_attachment_is_rejected(self):
        self.client.force_login(self.worker)
        upload = SimpleUploadedFile("notes.txt", b"not an image", content_type="text/plain")
        self.client.post(
            reverse("core:chat_send", args=[self.app.pk]),
            {"content": "", "client_message_id": str(uuid.uuid4()), "attachment": upload},
        )
        self.assertEqual(Message.objects.filter(application=self.app).count(), 0)

    def test_read_receipt_on_room_open_and_poll(self):
        self.client.force_login(self.worker)
        self.client.post(
            reverse("core:chat_send", args=[self.app.pk]),
            {"content": "Прочитай меня", "client_message_id": str(uuid.uuid4())},
        )
        msg = Message.objects.get(application=self.app)
        self.assertIsNone(msg.read_at)

        self.client.force_login(self.employer)
        self.client.get(reverse("core:chat_room", args=[self.app.pk]))
        msg.refresh_from_db()
        self.assertIsNotNone(msg.read_at)

        self.client.force_login(self.worker)
        data = self.client.get(
            reverse("core:chat_poll", args=[self.app.pk]), {"after": 0}
        ).json()
        self.assertIn(msg.pk, data["read_ids"])

    def test_mark_read_endpoint(self):
        self.client.force_login(self.worker)
        self.client.post(
            reverse("core:chat_send", args=[self.app.pk]),
            {"content": "Непрочитанное", "client_message_id": str(uuid.uuid4())},
        )
        msg = Message.objects.get(application=self.app)
        self.client.force_login(self.employer)
        response = self.client.post(reverse("core:chat_mark_read", args=[self.app.pk]))
        self.assertEqual(response.status_code, 200)
        msg.refresh_from_db()
        self.assertIsNotNone(msg.read_at)

    def test_chats_list_preview_and_unread_badge(self):
        Message.objects.create(
            sender=self.worker, application=self.app,
            content="Последнее сообщение",
        )
        self.client.force_login(self.employer)
        response = self.client.get(reverse("core:chats"))
        self.assertContains(response, "Последнее сообщение")
        self.assertContains(response, "Непрочитанных: 1")
        row = response.context["rows"][0]
        self.assertEqual(row["unread_count"], 1)
        self.assertEqual(row["last"], "Последнее сообщение")
        count = self.client.get(reverse("core:chats_unread_count")).json()
        self.assertEqual(count["unread_count"], 1)

    def test_chats_list_attachment_preview(self):
        Message.objects.create(
            sender=self.worker, application=self.app,
            content="", attachment_url="/uploads/chat/x.png",
            attachment_name="photo.png", attachment_mime="image/png",
        )
        self.client.force_login(self.employer)
        response = self.client.get(reverse("core:chats"))
        self.assertContains(response, "Изображение")
        self.assertEqual(response.context["rows"][0]["last"], "Изображение")

    def test_edit_own_message(self):
        msg = Message.objects.create(
            sender=self.worker, application=self.app, content="Старый текст",
        )
        self.client.force_login(self.worker)
        response = self.client.post(
            reverse("core:chat_edit_message", args=[self.app.pk, msg.pk]),
            {"content": "Новый текст"},
        )
        self.assertEqual(response.status_code, 302)
        msg.refresh_from_db()
        self.assertEqual(msg.content, "Новый текст")
        self.assertIsNotNone(msg.edited_at)

    def test_cannot_edit_foreign_message(self):
        msg = Message.objects.create(
            sender=self.worker, application=self.app, content="Чужое",
        )
        self.client.force_login(self.employer)
        self.client.post(
            reverse("core:chat_edit_message", args=[self.app.pk, msg.pk]),
            {"content": "Взлом"},
        )
        msg.refresh_from_db()
        self.assertEqual(msg.content, "Чужое")

    def test_delete_own_message_is_soft(self):
        msg = Message.objects.create(
            sender=self.worker, application=self.app, content="Удалить",
        )
        self.client.force_login(self.worker)
        response = self.client.post(
            reverse("core:chat_delete_message", args=[self.app.pk, msg.pk])
        )
        self.assertEqual(response.status_code, 302)
        msg.refresh_from_db()
        self.assertIsNotNone(msg.deleted_at)
        self.assertEqual(msg.content, "")
        response = self.client.get(reverse("core:chat_room", args=[self.app.pk]))
        self.assertContains(response, "Сообщение удалено")

    def test_cannot_delete_foreign_message(self):
        msg = Message.objects.create(
            sender=self.worker, application=self.app, content="Чужое",
        )
        self.client.force_login(self.employer)
        self.client.post(reverse("core:chat_delete_message", args=[self.app.pk, msg.pk]))
        msg.refresh_from_db()
        self.assertIsNone(msg.deleted_at)
        self.assertEqual(msg.content, "Чужое")

    def test_poll_returns_edits_and_deletions(self):
        msg = Message.objects.create(
            sender=self.worker, application=self.app, content="Было",
        )
        msg.content = "Стало"
        msg.edited_at = timezone.now()
        msg.save(update_fields=["content", "edited_at"])
        deleted = Message.objects.create(
            sender=self.worker, application=self.app, content="Удалить",
        )
        deleted.deleted_at = timezone.now()
        deleted.save(update_fields=["deleted_at"])
        self.client.force_login(self.employer)
        data = self.client.get(
            reverse("core:chat_poll", args=[self.app.pk]), {"after": 0}
        ).json()
        by_id = {item["id"]: item for item in data["changes"]}
        self.assertEqual(by_id[msg.pk]["content"], "Стало")
        self.assertIsNotNone(by_id[deleted.pk]["deleted_at"])

    def test_send_idempotent_by_client_message_id(self):
        self.client.force_login(self.worker)
        cmid = str(uuid.uuid4())
        for _ in range(2):
            self.client.post(reverse("core:chat_send", args=[self.app.pk]),
                             {"content": "Только один раз", "client_message_id": cmid})
        self.assertEqual(Message.objects.filter(application=self.app).count(), 1)

    def test_send_two_distinct_messages_not_deduped(self):
        self.client.force_login(self.worker)
        for text in ("Первое", "Второе"):
            self.client.post(reverse("core:chat_send", args=[self.app.pk]),
                             {"content": text, "client_message_id": str(uuid.uuid4())})
        self.assertEqual(Message.objects.filter(application=self.app).count(), 2)

    def test_chat_room_has_offline_queue_markup(self):
        self.client.force_login(self.worker)
        response = self.client.get(reverse("core:chat_room", args=[self.app.pk]))
        self.assertContains(response, 'id="chat-send-status"')
        self.assertContains(response, "trudnik-chat-queue-v1")
        self.assertContains(response, "navigator.onLine")

    def test_empty_message_ignored(self):
        self.client.force_login(self.worker)
        self.client.post(reverse("core:chat_send", args=[self.app.pk]),
                         {"content": "   ", "client_message_id": str(uuid.uuid4())})
        self.assertEqual(Message.objects.filter(application=self.app).count(), 0)

    def test_chat_empty_state_and_autoscroll(self):
        self.client.force_login(self.worker)
        response = self.client.get(reverse("core:chat_room", args=[self.app.pk]))
        self.assertContains(response, "Сообщений пока нет")
        self.assertContains(response, "log.scrollTop = log.scrollHeight")

    def test_chat_groups_messages_by_date(self):
        Message.objects.create(sender=self.worker, application=self.app, content="дата")
        self.client.force_login(self.worker)
        response = self.client.get(reverse("core:chat_room", args=[self.app.pk]))
        self.assertContains(response, timezone.localdate().strftime("%d.%m.%Y"))

    def test_chats_list_both_sides(self):
        Message.objects.create(sender=self.worker, application=self.app, content="привет")
        self.client.force_login(self.worker)
        self.assertContains(self.client.get(reverse("core:chats")), "привет")
        self.client.force_login(self.employer)
        self.assertContains(self.client.get(reverse("core:chats")), "привет")

    def test_chats_list_excludes_pending(self):
        pending = Application.objects.create(
            job=self.job, worker=make_profile("chat-pending@example.com"),
            status="pending",
        )
        Message.objects.create(sender=self.worker, application=self.app, content="принятый чат")
        Message.objects.create(sender=pending.worker, application=pending, content="ожидающий чат")
        self.client.force_login(self.employer)
        response = self.client.get(reverse("core:chats"))
        self.assertContains(response, "принятый чат")
        self.assertNotContains(response, "ожидающий чат")

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

    def test_chats_list_uses_annotated_last_message(self):
        second = Application.objects.create(
            job=self.job, worker=make_profile("chat-second@example.com"),
            status="accepted",
        )
        Message.objects.create(sender=self.worker, application=self.app, content="последнее A")
        Message.objects.create(sender=second.worker, application=second, content="последнее B")
        self.client.force_login(self.employer)
        response = self.client.get(reverse("core:chats"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "последнее A")
        self.assertContains(response, "последнее B")
