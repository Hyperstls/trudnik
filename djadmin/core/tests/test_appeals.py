"""R023: апелляции на скрытые модератором отзывы."""
import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.appeals import can_appeal, create_appeal, resolve_appeal
from core.models import NotificationOutbox, Rating, RatingAppeal
from core.tests.test_auth import make_profile
from core.tests.test_flows import make_job

VALID_REASON = "Прошу пересмотреть решение модератора"


def make_rating(employer, worker, job=None, **kw):
    kw.setdefault("rating", 5)
    kw.setdefault("rating_type", "employer")
    kw.setdefault("target_type", "worker")
    return Rating.objects.create(
        rated_user=worker,
        rater_user=employer,
        job=job or make_job(employer, status="completed"),
        **kw,
    )


def make_hidden_rating(employer, worker, **kw):
    kw.setdefault("moderation_status", Rating.ModerationStatus.HIDDEN)
    kw.setdefault("moderation_reason", "Спам")
    return make_rating(employer, worker, **kw)


class AppealPermissionTests(TestCase):
    def setUp(self):
        self.employer = make_profile("appeal-emp@example.com", role="employer")
        self.worker = make_profile("appeal-worker@example.com")
        self.stranger = make_profile("appeal-stranger@example.com")
        self.rating = make_hidden_rating(self.employer, self.worker)

    def test_author_of_hidden_rating_can_appeal(self):
        self.assertTrue(can_appeal(self.rating, self.employer))

    def test_rated_user_and_stranger_cannot_appeal(self):
        self.assertFalse(can_appeal(self.rating, self.worker))
        self.assertFalse(can_appeal(self.rating, self.stranger))

    def test_not_hidden_rating_cannot_be_appealed(self):
        for status in (Rating.ModerationStatus.OK, Rating.ModerationStatus.REVIEW):
            self.rating.moderation_status = status
            self.rating.save(update_fields=["moderation_status"])
            self.assertFalse(can_appeal(self.rating, self.employer), status)

    def test_pending_appeal_blocks_second(self):
        appeal, error = create_appeal(self.rating.pk, self.employer, VALID_REASON)
        self.assertIsNone(error)
        self.assertIsNotNone(appeal)
        self.assertFalse(can_appeal(self.rating, self.employer))

    def test_non_author_cannot_create_appeal(self):
        appeal, error = create_appeal(self.rating.pk, self.stranger, VALID_REASON)
        self.assertIsNone(appeal)
        self.assertTrue(error)
        self.assertFalse(RatingAppeal.objects.exists())


class CreateAppealValidationTests(TestCase):
    def setUp(self):
        self.employer = make_profile("appeal-val-emp@example.com", role="employer")
        self.worker = make_profile("appeal-val-worker@example.com")
        self.rating = make_hidden_rating(self.employer, self.worker)

    def test_short_reason_rejected(self):
        appeal, error = create_appeal(self.rating.pk, self.employer, "коротко")
        self.assertIsNone(appeal)
        self.assertTrue(error)
        self.assertFalse(RatingAppeal.objects.exists())

    def test_short_reason_after_strip_rejected(self):
        appeal, error = create_appeal(self.rating.pk, self.employer, "   коротко   ")
        self.assertIsNone(appeal)
        self.assertTrue(error)

    def test_long_reason_rejected(self):
        appeal, error = create_appeal(self.rating.pk, self.employer, "а" * 2001)
        self.assertIsNone(appeal)
        self.assertTrue(error)

    def test_boundary_reason_accepted_and_stripped(self):
        appeal, error = create_appeal(self.rating.pk, self.employer, "  " + "а" * 2000 + "  ")
        self.assertIsNone(error)
        self.assertEqual(appeal.reason, "а" * 2000)
        self.assertEqual(appeal.status, RatingAppeal.Status.PENDING)
        self.assertIsNone(appeal.resolved_at)
        self.assertIsNone(appeal.resolver_id)

    def test_duplicate_pending_rejected(self):
        first, error = create_appeal(self.rating.pk, self.employer, VALID_REASON)
        self.assertIsNone(error)
        second, error = create_appeal(self.rating.pk, self.employer, "Другая причина для апелляции")
        self.assertIsNone(second)
        self.assertTrue(error)
        self.assertEqual(RatingAppeal.objects.filter(rating=self.rating).count(), 1)


class ResolveAppealTests(TestCase):
    def setUp(self):
        self.employer = make_profile("appeal-res-emp@example.com", role="employer")
        self.worker = make_profile("appeal-res-worker@example.com")
        self.moderator = make_profile("appeal-moderator@example.com", role="admin")
        self.job = make_job(self.employer, status="completed")
        self.rating = make_hidden_rating(self.employer, self.worker, job=self.job)
        self.appeal, error = create_appeal(self.rating.pk, self.employer, VALID_REASON)
        self.assertIsNone(error)

    def test_approve_returns_rating_to_ok_and_publishes_counterpart(self):
        counterpart = Rating.objects.create(
            rated_user=self.employer,
            rater_user=self.worker,
            job=self.job,
            rating=4,
            rating_type="worker",
            target_type="employer",
        )
        resolved = resolve_appeal(self.appeal.pk, self.moderator, True, "Претензия обоснована")
        self.assertIsNotNone(resolved)

        self.rating.refresh_from_db()
        self.assertEqual(self.rating.moderation_status, Rating.ModerationStatus.OK)
        self.assertIsNone(self.rating.moderation_reason)
        self.assertIsNotNone(self.rating.published_at)
        counterpart.refresh_from_db()
        self.assertIsNotNone(counterpart.published_at)

        resolved.refresh_from_db()
        self.assertEqual(resolved.status, RatingAppeal.Status.APPROVED)
        self.assertIsNotNone(resolved.resolved_at)
        self.assertEqual(resolved.resolver_id, self.moderator.pk)
        self.assertEqual(resolved.resolution_note, "Претензия обоснована")

    def test_approve_publishes_after_deadline_without_counterpart(self):
        Rating.objects.filter(pk=self.rating.pk).update(
            created_at=timezone.now() - timedelta(days=15)
        )
        resolve_appeal(self.appeal.pk, self.moderator, True)
        self.rating.refresh_from_db()
        self.assertEqual(self.rating.moderation_status, Rating.ModerationStatus.OK)
        self.assertIsNotNone(self.rating.published_at)

    def test_reject_keeps_rating_hidden(self):
        resolve_appeal(self.appeal.pk, self.moderator, False, "Оснований нет")
        self.rating.refresh_from_db()
        self.assertEqual(self.rating.moderation_status, Rating.ModerationStatus.HIDDEN)
        self.assertIsNone(self.rating.published_at)

        self.appeal.refresh_from_db()
        self.assertEqual(self.appeal.status, RatingAppeal.Status.REJECTED)
        self.assertEqual(self.appeal.resolution_note, "Оснований нет")
        self.assertIsNotNone(self.appeal.resolved_at)

    def test_second_resolution_returns_none(self):
        self.assertIsNotNone(resolve_appeal(self.appeal.pk, self.moderator, True))
        self.assertIsNone(resolve_appeal(self.appeal.pk, self.moderator, False))
        self.appeal.refresh_from_db()
        self.assertEqual(self.appeal.status, RatingAppeal.Status.APPROVED)
        self.assertEqual(
            NotificationOutbox.objects.filter(
                user=self.employer, type="rating_appeal"
            ).count(),
            1,
        )

    def test_author_notified_on_approve(self):
        resolve_appeal(self.appeal.pk, self.moderator, True)
        notification = NotificationOutbox.objects.get(
            user=self.employer, type="rating_appeal"
        )
        self.assertEqual(notification.status, NotificationOutbox.Status.PENDING)
        self.assertEqual(notification.data["status"], RatingAppeal.Status.APPROVED)

    def test_author_notified_on_reject(self):
        resolve_appeal(self.appeal.pk, self.moderator, False)
        notification = NotificationOutbox.objects.get(
            user=self.employer, type="rating_appeal"
        )
        self.assertEqual(notification.data["status"], RatingAppeal.Status.REJECTED)

    def test_unknown_appeal_returns_none(self):
        self.assertIsNone(resolve_appeal(uuid.uuid4(), self.moderator, True))
        self.appeal.delete()
        self.assertIsNone(resolve_appeal(self.appeal.pk, self.moderator, True))
