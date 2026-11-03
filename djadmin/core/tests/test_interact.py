"""Фаза 2г: оценки (RPC + триггер пересчёта) и чат (доступ, идемпотентность, poll)."""
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Application, Job, Message, NotificationOutbox, Profile, Rating, RatingReport
from core.storage import delete_upload_url
from core.tests.test_auth import CACHE_LOCMEM, make_profile
from core.tests.test_flows import make_job
import uuid


def make_accepted(employer, worker, status="completed"):
    job = make_job(employer, work_type="Оценочная работа", status=status)
    app = Application.objects.create(job=job, worker=worker, status="accepted")
    return job, app


@override_settings(CACHES=CACHE_LOCMEM)
class RatingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.employer = make_profile("rate-emp@example.com")
        self.worker = make_profile("rate-worker@example.com", role="worker")
        self.job, self.app = make_accepted(self.employer, self.worker)

    def _post(self, user, stars=5, **extra):
        self.client.force_login(user)
        data = {"rating": str(stars), "comment": extra.pop("comment", "")}
        data.update(extra)
        return self.client.post(reverse("core:rate_participant", args=[self.app.pk]), data)

    def test_double_blind_requires_both_sides(self):
        self._post(self.employer, 5, comment="Отлично")
        rating = Rating.objects.get(rater_user=self.employer, job=self.job)
        self.assertIsNone(rating.published_at)
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.worker_ratings_count, 0)
        self.assertEqual(self.worker.ratings_count, 0)

        self._post(self.worker, 4)
        rating.refresh_from_db()
        counterpart = Rating.objects.get(rater_user=self.worker, job=self.job)
        self.assertIsNotNone(rating.published_at)
        self.assertIsNotNone(counterpart.published_at)
        self.worker.refresh_from_db()
        self.employer.refresh_from_db()
        self.assertEqual((self.worker.worker_rating, self.worker.worker_ratings_count), (5.0, 1))
        self.assertEqual((self.employer.employer_rating, self.employer.employer_ratings_count), (4.0, 1))
        # Роли не смешиваются: у трудника нет рейтинга работодателя.
        self.assertEqual(self.worker.employer_ratings_count, 0)
        self.assertEqual(
            NotificationOutbox.objects.filter(type="new_rating").count(), 2
        )

    def test_worker_rating_employer_is_pending(self):
        self._post(self.worker, 4)
        rating = Rating.objects.get(rater_user=self.worker, job=self.job)
        self.assertEqual(rating.target_type, "employer")
        self.assertIsNone(rating.published_at)
        self.employer.refresh_from_db()
        self.assertEqual(self.employer.employer_ratings_count, 0)

    def test_upsert_updates_not_duplicates(self):
        self._post(self.employer, 3)
        self._post(self.employer, 5)
        self.assertEqual(Rating.objects.filter(rater_user=self.employer, job=self.job).count(), 1)
        rating = Rating.objects.get(rater_user=self.employer, job=self.job)
        self.assertEqual(rating.rating, 5)
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.worker_ratings_count, 0)

    def test_role_specific_aggregates_do_not_mix(self):
        now = timezone.now()
        Rating.objects.create(
            rated_user=self.worker, rater_user=self.employer, job=self.job,
            rating=5, rating_type="employer", target_type="worker", published_at=now,
        )
        job2 = make_job(self.employer, work_type="Вторая роль")
        other = make_profile("rate-role-other@example.com")
        Rating.objects.create(
            rated_user=self.worker, rater_user=other, job=job2,
            rating=2, rating_type="worker", target_type="employer", published_at=now,
        )
        self.worker.refresh_from_db()
        self.assertEqual((self.worker.worker_rating, self.worker.worker_ratings_count), (5.0, 1))
        self.assertEqual((self.worker.employer_rating, self.worker.employer_ratings_count), (2.0, 1))
        self.assertEqual((self.worker.rating, self.worker.total_reviews), (3.5, 2))

    def test_only_after_completed_or_date_fallback(self):
        job = make_job(self.employer, status="open")
        app = Application.objects.create(job=job, worker=self.worker, status="accepted")
        self.client.force_login(self.employer)
        self.client.post(reverse("core:rate_participant", args=[app.pk]), {"rating": "5"})
        self.assertFalse(Rating.objects.exists())

        job.date_time = timezone.now() - timedelta(days=4)
        job.save(update_fields=["date_time"])
        self.client.post(reverse("core:rate_participant", args=[app.pk]), {"rating": "5"})
        self.assertTrue(Rating.objects.filter(job=job).exists())

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
        self._post(self.employer, 9)
        self.assertFalse(Rating.objects.exists())

    def test_employer_rates_two_workers_update_keeps_other(self):
        worker2 = make_profile("rate-worker2@example.com", role="worker")
        app2 = Application.objects.create(job=self.job, worker=worker2, status="accepted")
        self.client.force_login(self.employer)
        self.client.post(reverse("core:rate_participant", args=[self.app.pk]), {"rating": "5"})
        self.client.post(reverse("core:rate_participant", args=[app2.pk]), {"rating": "4"})
        self.assertEqual(Rating.objects.filter(rater_user=self.employer, job=self.job).count(), 2)
        self.client.post(reverse("core:rate_participant", args=[self.app.pk]), {"rating": "3"})
        first = Rating.objects.get(rater_user=self.employer, job=self.job, rated_user=self.worker)
        second = Rating.objects.get(rater_user=self.employer, job=self.job, rated_user=worker2)
        self.assertEqual((first.rating, second.rating), (3, 4))

    def test_rating_page_has_criteria_and_saves_tags(self):
        self.client.force_login(self.employer)
        page = self.client.get(reverse("core:rate_participant", args=[self.app.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Общая оценка")
        self.assertContains(page, "Качество работы")
        self.assertContains(page, "Работа сдана в срок")
        self.client.post(reverse("core:rate_participant", args=[self.app.pk]), {
            "rating": "4", "comment": "Хорошо",
            "criterion_quality": "5", "criterion_punctuality": "4",
            "tags": ["on_time", "recommend"],
        })
        rating = Rating.objects.get(rater_user=self.employer, job=self.job)
        self.assertEqual(rating.criteria["quality"], 5)
        self.assertEqual(rating.criteria["punctuality"], 4)
        self.assertIn("on_time", rating.tags)

    def test_link_in_comment_goes_to_moderation(self):
        response = self._post(self.employer, 5, comment="Смотрите https://spam.example")
        self.assertEqual(response.status_code, 302)
        rating = Rating.objects.get(rater_user=self.employer, job=self.job)
        self.assertEqual(rating.moderation_status, Rating.ModerationStatus.REVIEW)
        self.assertIsNone(rating.published_at)
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.worker_ratings_count, 0)

    def test_edit_window_is_14_days(self):
        rating = Rating.objects.create(
            rated_user=self.worker, rater_user=self.employer, job=self.job,
            rating=5, rating_type="employer", target_type="worker",
            published_at=timezone.now(),
        )
        Rating.objects.filter(pk=rating.pk).update(
            created_at=timezone.now() - timedelta(days=15)
        )
        self._post(self.employer, 1)
        rating.refresh_from_db()
        self.assertEqual(rating.rating, 5)

    def test_rpc_can_rate_employer(self):
        from core.rpc import call_rpc

        result = call_rpc(
            "rate_user_atomic", self.job.pk, self.worker.pk, self.employer.pk,
            5, "RPC", "worker", "employer",
        )
        self.assertTrue(result.get("success"))
        self.assertTrue(
            Rating.objects.filter(
                job=self.job, rater_user=self.worker, rated_user=self.employer,
            ).exists()
        )

    def test_publish_due_ratings_task(self):
        from core import tasks

        rating = Rating.objects.create(
            rated_user=self.worker, rater_user=self.employer, job=self.job,
            rating=5, rating_type="employer", target_type="worker",
        )
        Rating.objects.filter(pk=rating.pk).update(
            created_at=timezone.now() - timedelta(days=15)
        )
        self.assertEqual(tasks.publish_due_ratings(), 1)
        rating.refresh_from_db()
        self.assertIsNotNone(rating.published_at)
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.worker_ratings_count, 1)

    def test_remind_pending_ratings_task_is_deduplicated(self):
        from core import tasks

        self.assertGreaterEqual(tasks.remind_pending_ratings(), 2)
        self.assertTrue(
            NotificationOutbox.objects.filter(
                type="rating_reminder", data__application_id=str(self.app.pk),
            ).exists()
        )
        self.assertEqual(tasks.remind_pending_ratings(), 0)

    def test_reply_and_report(self):
        rating = Rating.objects.create(
            rated_user=self.worker, rater_user=self.employer, job=self.job,
            rating=4, comment="Нормально", rating_type="employer",
            target_type="worker", published_at=timezone.now(),
        )
        self.client.force_login(self.worker)
        response = self.client.post(
            reverse("core:rating_reply", args=[rating.pk]), {"reply": "Спасибо"}
        )
        self.assertEqual(response.status_code, 302)
        rating.refresh_from_db()
        self.assertEqual(rating.reply, "Спасибо")

        other = make_profile("rating-reporter@example.com")
        self.client.force_login(other)
        response = self.client.post(
            reverse("core:rating_report", args=[rating.pk]), {"reason": "Спам"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(RatingReport.objects.filter(rating=rating, reporter=other).exists())

    def test_job_detail_reviews_filter_by_target_type(self):
        now = timezone.now()
        Rating.objects.create(
            rated_user=self.employer, rater_user=self.worker, job=self.job,
            rating=5, comment="Отзыв о работодателе целевой",
            rating_type="worker", target_type="employer", published_at=now,
        )
        Rating.objects.create(
            rated_user=self.worker, rater_user=self.employer, job=self.job,
            rating=4, comment="Оценка работнику не в блоке отзывов",
            rating_type="employer", target_type="worker", published_at=now,
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

    def test_duplicate_message_ignored(self):
        self.client.force_login(self.worker)
        for _ in range(2):
            self.client.post(reverse("core:chat_send", args=[self.app.pk]),
                             {"content": "Одинаковый текст", "client_message_id": str(uuid.uuid4())})
        self.assertEqual(Message.objects.filter(application=self.app).count(), 1)

    def test_chat_room_has_offline_queue_markup(self):
        self.client.force_login(self.worker)
        response = self.client.get(reverse("core:chat_room", args=[self.app.pk]))
        self.assertContains(response, 'id="chat-send-status"')
        self.assertContains(response, "trudnik-chat-queue-v1")
        self.assertContains(response, "navigator.onLine")

    def test_chat_search_filters_messages(self):
        Message.objects.create(sender=self.worker, application=self.app, content="alpha")
        Message.objects.create(sender=self.worker, application=self.app, content="beta")
        self.client.force_login(self.employer)
        response = self.client.get(reverse("core:chat_room", args=[self.app.pk]), {"q": "alpha"})
        self.assertContains(response, "alpha")
        self.assertNotContains(response, ">beta<")
        self.assertEqual(response.context["search_query"], "alpha")

    def test_chat_mute_toggles_preferences(self):
        self.client.force_login(self.employer)
        response = self.client.post(reverse("core:chat_mute", args=[self.app.pk]))
        self.assertEqual(response.status_code, 302)
        self.employer.refresh_from_db()
        self.assertIn(str(self.app.pk), self.employer.notification_prefs["muted_chats"])
        response = self.client.get(reverse("core:chat_room", args=[self.app.pk]))
        self.assertContains(response, "Уведомления выключены")

    @patch("core.views_interact.enqueue_notification")
    def test_muted_chat_does_not_create_notification(self, enqueue):
        self.client.force_login(self.worker)
        self.client.post(reverse("core:chat_send", args=[self.app.pk]),
                         {"content": "first", "client_message_id": str(uuid.uuid4())})
        self.assertEqual(enqueue.call_count, 1)
        self.client.force_login(self.employer)
        self.client.post(reverse("core:chat_mute", args=[self.app.pk]))
        self.client.force_login(self.worker)
        self.client.post(reverse("core:chat_send", args=[self.app.pk]),
                         {"content": "second", "client_message_id": str(uuid.uuid4())})
        self.assertEqual(enqueue.call_count, 1)

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
