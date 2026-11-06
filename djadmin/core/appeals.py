"""R023: апелляции автора скрытого модератором отзыва.

Автор отзыва с moderation_status='hidden' может подать одну апелляцию.
Модератор одобряет её (отзыв возвращается в 'ok' и, если возможно,
публикуется) или отклоняет (отзыв остаётся скрытым). Решение и уведомление
фиксируются в одной транзакции.
"""
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Rating, RatingAppeal
from .notifications import enqueue_notification
from .reputation import publish_reciprocal

REASON_MIN_LENGTH = 10
REASON_MAX_LENGTH = 2000


def _block_reason(rating, user):
    """Почему апелляция недоступна, или None, если доступна."""
    if rating is None:
        return "Отзыв не найден"
    if getattr(user, "pk", None) != rating.rater_user_id:
        return "Апелляцию может подать только автор отзыва"
    if rating.moderation_status != Rating.ModerationStatus.HIDDEN:
        return "Отзыв не скрыт модератором"
    if RatingAppeal.objects.filter(
        rating_id=rating.pk, status=RatingAppeal.Status.PENDING
    ).exists():
        return "Апелляция уже подана"
    return None


def can_appeal(rating, user):
    return _block_reason(rating, user) is None


def create_appeal(rating_id, user, reason):
    """Создать pending-апелляцию; вернуть (appeal, None) или (None, error)."""
    text = (reason or "").strip()
    if len(text) < REASON_MIN_LENGTH:
        return None, "Причина должна быть не короче %d символов" % REASON_MIN_LENGTH
    if len(text) > REASON_MAX_LENGTH:
        return None, "Причина должна быть не длиннее %d символов" % REASON_MAX_LENGTH

    with transaction.atomic():
        rating = Rating.objects.select_for_update().filter(pk=rating_id).first()
        error = _block_reason(rating, user)
        if error:
            return None, error
        try:
            with transaction.atomic():
                appeal = RatingAppeal.objects.create(
                    rating=rating,
                    appellant=user,
                    reason=text,
                    status=RatingAppeal.Status.PENDING,
                )
        except IntegrityError:
            return None, "Апелляция уже подана"
    return appeal, None


def resolve_appeal(appeal_id, resolver, approve, note=""):
    """Решить pending-апелляцию; вернуть appeal или None, если решать нечего."""
    with transaction.atomic():
        appeal = (
            RatingAppeal.objects.select_for_update()
            .filter(pk=appeal_id, status=RatingAppeal.Status.PENDING)
            .first()
        )
        if appeal is None:
            return None
        rating = Rating.objects.select_for_update().filter(pk=appeal.rating_id).first()
        if rating is None:
            return None

        if approve:
            rating.moderation_status = Rating.ModerationStatus.OK
            rating.moderation_reason = None
            rating.save(update_fields=["moderation_status", "moderation_reason", "updated_at"])
            publish_reciprocal(rating)
            appeal.status = RatingAppeal.Status.APPROVED
            title = "Апелляция одобрена"
            body = "Ваш отзыв снова опубликован."
        else:
            appeal.status = RatingAppeal.Status.REJECTED
            title = "Апелляция отклонена"
            body = "Ваш отзыв остаётся скрытым."

        appeal.resolved_at = timezone.now()
        appeal.resolver = resolver
        appeal.resolution_note = (note or "").strip() or None
        appeal.save(update_fields=["status", "resolved_at", "resolver", "resolution_note"])
        enqueue_notification(
            appeal.appellant_id,
            "rating_appeal",
            title,
            body,
            {
                "appeal_id": str(appeal.pk),
                "rating_id": str(rating.pk),
                "status": appeal.status,
            },
        )
    return appeal
