"""Автоматический антиспам/антифрод (J158).

Правила намеренно консервативны: подозрительные задания попадают в очередь
модерации (``jobs.moderation_status='review'``), а не блокируются молча.
Жёстко ограничиваются только явные злоупотребления: дубли, флуд заявками и
повторяющиеся сообщения в чате.
"""
import logging
import re
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Job, Message

logger = logging.getLogger(__name__)

PHONE_RE = re.compile(
    r"(?:\+7|8)?[\s\-()]*(?:\d{3})[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2}"
)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MESSENGER_RE = re.compile(
    r"(?:t\.me/|wa\.me/|telegram|whatsapp|ватсап|телеграм)", re.IGNORECASE
)
URL_RE = re.compile(r"https?://", re.IGNORECASE)

JOB_REVIEW_SCORE = 4
JOB_HOURLY_LIMIT = 10
APPLICATION_DAILY_LIMIT = 40
CHAT_DUPLICATE_WINDOW_SECONDS = 60


def _limit_allows(user_id, bucket: str, limit: int, window: int) -> bool:
    """Fail-open User+action limit on the Django cache."""
    key = "af:%s:%s" % (bucket, user_id)
    try:
        if cache.add(key, 1, window):
            return True
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, window)
            count = 1
        return count <= limit
    except Exception:
        return True


def allow_job_post(user_id) -> bool:
    return _limit_allows(user_id, "job_post_hour", JOB_HOURLY_LIMIT, 3600)


def allow_application(user_id) -> bool:
    return _limit_allows(
        user_id, "application_day", APPLICATION_DAILY_LIMIT, 86400
    )


def assess_job(employer, *, work_type="", city="", texts=(), exclude_job_id=None) -> dict:
    """Score a new/edited job and decide whether it needs manual review.

    Returns ``{"status": "ok"|"review", "score": int, "reason": str}``.
    """
    now = timezone.now()
    reasons = []
    score = 0

    if work_type:
        duplicate_qs = Job.objects.filter(
            employer=employer,
            work_type__iexact=work_type,
            created_at__gte=now - timedelta(hours=24),
        ).exclude(moderation_status=Job.ModerationStatus.REJECTED)
        if exclude_job_id:
            duplicate_qs = duplicate_qs.exclude(pk=exclude_job_id)
        if city:
            duplicate_qs = duplicate_qs.filter(city__iexact=city)
        else:
            duplicate_qs = duplicate_qs.filter(Q(city__isnull=True) | Q(city=""))
        duplicate = duplicate_qs.exists()
        if duplicate:
            score += 4
            reasons.append(_("Похожее задание уже создавалось за последние 24 часа"))

    recent_qs = Job.objects.filter(
        employer=employer, created_at__gte=now - timedelta(hours=1)
    )
    if exclude_job_id:
        recent_qs = recent_qs.exclude(pk=exclude_job_id)
    recent = recent_qs.count()
    if recent >= 5:
        score += 4
        reasons.append(_("Слишком много заданий за последний час"))

    text = " ".join(str(value or "") for value in texts)
    contacts = (
        len(PHONE_RE.findall(text))
        + len(EMAIL_RE.findall(text))
        + len(MESSENGER_RE.findall(text))
    )
    if contacts >= 2:
        score += 4
        reasons.append(_("В описании несколько внешних контактов"))

    if len(URL_RE.findall(text)) >= 4:
        score += 1
        reasons.append(_("Слишком много внешних ссылок"))

    status = (
        Job.ModerationStatus.REVIEW
        if score >= JOB_REVIEW_SCORE
        else Job.ModerationStatus.OK
    )
    return {"status": status, "score": score, "reason": "; ".join(reasons)}


def is_duplicate_message(sender_id, application_id, content: str) -> bool:
    """Reject exact duplicate messages sent within the short window."""
    content = (content or "").strip()
    if not content:
        return False
    return Message.objects.filter(
        sender_id=sender_id,
        application_id=application_id,
        content=content,
        created_at__gte=timezone.now()
        - timedelta(seconds=CHAT_DUPLICATE_WINDOW_SECONDS),
        deleted_at__isnull=True,
    ).exists()
