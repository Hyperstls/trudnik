"""Reputation helpers (J162): role-specific ratings, weighted score, metrics."""
import re
from datetime import timedelta

from django.db.models import Avg, Count, ExpressionWrapper, F, FloatField, Value
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Application, Job, Profile, Rating, UserReport

EDIT_WINDOW_DAYS = 14
RATING_FALLBACK_DAYS = 3
MIN_PUBLIC_REVIEWS = 3
PRIOR_AVG = 4.2
PRIOR_WEIGHT = 5
RESPONSE_WINDOW_DAYS = 90
RESPONSE_MIN_SAMPLE = 3
RESPONSE_SAMPLE_LIMIT = 500

URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
CONTACT_RE = re.compile(
    r"(?:\+7|8)?[\s\-()]*(?:\d{3})[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2}"
)
WORKER_CRITERIA = (
    ("quality", _("Качество работы")),
    ("punctuality", _("Пунктуальность")),
    ("responsibility", _("Ответственность")),
    ("communication", _("Коммуникация")),
)
WORKER_TAGS = (
    ("on_time", _("Работа сдана в срок")),
    ("neat", _("Аккуратно")),
    ("responsive", _("Быстро отвечает")),
    ("recommend", _("Рекомендую")),
)
EMPLOYER_CRITERIA = (
    ("payment_on_time", _("Оплата в срок")),
    ("clear_task", _("Понятная задача")),
    ("communication", _("Коммуникация")),
    ("safety", _("Безопасные условия")),
)
EMPLOYER_TAGS = (
    ("paid_on_time", _("Оплата вовремя")),
    ("clear_task", _("Чёткое ТЗ")),
    ("responsive", _("Быстро отвечает")),
    ("recommend", _("Рекомендую")),
)


def rating_options(target_type):
    if target_type == "worker":
        return WORKER_CRITERIA, WORKER_TAGS
    return EMPLOYER_CRITERIA, EMPLOYER_TAGS


def criteria_labels(target_type):
    return dict(rating_options(target_type)[0])


def tag_labels(target_type):
    return dict(rating_options(target_type)[1])


ABUSE_WORDS = (
    "дурак", "идиот", "кретин", "дебил", "ублюдок", "мразь",
    "сволочь", "подонок", "тварь", "скотина",
)


def weighted_rating(rating, count, prior_avg=PRIOR_AVG, prior_weight=PRIOR_WEIGHT):
    """Bayesian-smoothed score: (sum + C*m) / (n + C)."""
    count = int(count or 0)
    return round(((float(rating or 0) * count) + (prior_avg * prior_weight)) / (count + prior_weight), 2)


def weighted_expr(rating_field, count_field):
    """QuerySet expression for the same weighted score."""
    return ExpressionWrapper(
        (F(rating_field) * F(count_field) + Value(PRIOR_AVG * PRIOR_WEIGHT))
        / (F(count_field) + Value(PRIOR_WEIGHT)),
        output_field=FloatField(),
    )


def public_ratings(profile_id, target_type=None):
    qs = Rating.objects.filter(
        rated_user_id=profile_id,
        published_at__isnull=False,
        moderation_status=Rating.ModerationStatus.OK,
    )
    if target_type:
        qs = qs.filter(target_type=target_type)
    return qs


def rating_distribution(profile_id, target_type):
    counts = dict(
        public_ratings(profile_id, target_type)
        .values_list("rating")
        .annotate(total=Count("id"))
        .values_list("rating", "total")
    )
    total = sum(counts.values())
    return [
        {
            "stars": stars,
            "count": counts.get(stars, 0),
            "pct": round(counts.get(stars, 0) / total * 100) if total else 0,
        }
        for stars in (5, 4, 3, 2, 1)
    ]


def recent_rating(profile_id, target_type, days=365):
    since = timezone.now() - timedelta(days=days)
    qs = public_ratings(profile_id, target_type).filter(published_at__gte=since)
    return {
        "rating": round(qs.aggregate(avg=Avg("rating"))["avg"] or 0, 1),
        "count": qs.count(),
        "days": days,
    }


def _human_duration(minutes):
    """Компактная подпись длительности: 'N мин', 'N,N ч', 'N д'."""
    minutes = max(int(round(float(minutes or 0))), 0)
    if minutes < 60:
        return "%d мин" % minutes
    if minutes < 24 * 60:
        return ("%.1f" % (minutes / 60)).replace(".", ",") + " ч"
    return "%d д" % int(round(minutes / (24 * 60)))


def employer_response_metrics(profile_id):
    """Скорость ответа работодателя: среднее/медиана от created_at до responded_at.

    Берём только разрешённые отклики (accepted/rejected) за последние 90 дней,
    не больше 500 последних ответов. Отрицательные интервалы (responded_at
    раньше created_at) игнорируются. Меньше трёх ответов — сигнала нет.
    """
    since = timezone.now() - timedelta(days=RESPONSE_WINDOW_DAYS)
    rows = (
        Application.objects.filter(
            job__employer_id=profile_id,
            status__in=(Application.Status.ACCEPTED, Application.Status.REJECTED),
            responded_at__isnull=False,
            responded_at__gte=since,
            created_at__lte=F("responded_at"),
        )
        .order_by("-responded_at")
        .values_list("created_at", "responded_at")[:RESPONSE_SAMPLE_LIMIT]
    )
    minutes = sorted((responded - created).total_seconds() / 60 for created, responded in rows)
    count = len(minutes)
    if count < RESPONSE_MIN_SAMPLE:
        return {}
    middle = count // 2
    median = minutes[middle] if count % 2 else (minutes[middle - 1] + minutes[middle]) / 2
    avg = sum(minutes) / count
    return {
        "response_count": count,
        "response_avg_minutes": round(avg, 1),
        "response_median_minutes": round(median, 1),
        "response_avg_label": _human_duration(avg),
    }


def profile_metrics(profile_id, role):
    """Behavioural signals shown next to the stars (not a replacement for reviews)."""
    profile = Profile.objects.filter(pk=profile_id).first()
    if profile is None:
        return {}
    if role == Profile.Role.EMPLOYER:
        jobs = Job.objects.filter(employer_id=profile_id)
        completed_jobs = jobs.filter(status=Job.Status.COMPLETED).count()
        accepted = Application.objects.filter(job__employer_id=profile_id, status=Application.Status.ACCEPTED)
        accepted_count = accepted.count()
        completed_apps = accepted.filter(job__status=Job.Status.COMPLETED).count()
        repeat_hires = (
            accepted.filter(job__status=Job.Status.COMPLETED)
            .values("worker_id").annotate(total=Count("id")).filter(total__gte=2).count()
        )
    else:
        accepted = Application.objects.filter(worker_id=profile_id, status=Application.Status.ACCEPTED)
        accepted_count = accepted.count()
        completed_apps = accepted.filter(job__status=Job.Status.COMPLETED).count()
        completed_jobs = completed_apps
        repeat_hires = (
            accepted.filter(job__status=Job.Status.COMPLETED)
            .values("job__employer_id").annotate(total=Count("id")).filter(total__gte=2).count()
        )
    reports = UserReport.objects.filter(reported_id=profile_id).exclude(status="reviewed").count()
    metrics = {
        "accepted": accepted_count,
        "completed": completed_apps,
        "completed_jobs": completed_jobs,
        "completion_rate": round(completed_apps / accepted_count * 100) if accepted_count else 0,
        "repeat_hires": repeat_hires,
        "open_reports": reports,
        "verified": bool(profile.email_verified or profile.verification_status == "approved"),
    }
    if role == Profile.Role.EMPLOYER:
        metrics.update(employer_response_metrics(profile_id))
    return metrics


def reliable_badge(profile, metrics):
    """Transparent 'Надёжный' rule: enough completed jobs, high completion and rating."""
    if not metrics:
        return False
    count = profile.worker_ratings_count if profile.role == Profile.Role.WORKER else profile.employer_ratings_count
    rating = profile.worker_rating if profile.role == Profile.Role.WORKER else profile.employer_rating
    return (
        metrics.get("completed_jobs", 0) >= 5
        and metrics.get("completion_rate", 0) >= 80
        and metrics.get("open_reports", 0) == 0
        and (count < MIN_PUBLIC_REVIEWS or rating >= 4.5)
    )


def review_moderation_reason(comment, criteria=None, tags=None):
    """Basic anti-spam/profanity check; suspicious reviews go to manual review."""
    text = (comment or "").lower()
    if not text:
        return None
    if any(word in text for word in ABUSE_WORDS):
        return "Обнаружены оскорбления"
    if URL_RE.search(text):
        return "Ссылка в отзыве"
    if CONTACT_RE.search(text):
        return "Контактные данные в отзыве"
    return None


def lock_rating_pair(job_id):
    """Сериализовать парную публикацию оценок одного задания.

    SELECT ... FOR UPDATE по строке jobs: одновременные взаимные оценки
    выполняются последовательно, и вторая транзакция видит уже закоммиченную
    первую — publish_reciprocal срабатывает сразу, а не ждёт Celery.

    Вызывать только внутри transaction.atomic(): вне транзакции Django
    выбрасывает TransactionManagementError. Возвращает задание или None.
    """
    return Job.objects.select_for_update().filter(pk=job_id).first()


def publish_reciprocal(rating):
    """Publish a rating together with its counterpart, or alone after 14 days."""
    if rating.published_at is not None or rating.moderation_status != Rating.ModerationStatus.OK:
        return []
    counterpart = Rating.objects.filter(
        job_id=rating.job_id,
        rater_user_id=rating.rated_user_id,
        rated_user_id=rating.rater_user_id,
        published_at__isnull=True,
        moderation_status=Rating.ModerationStatus.OK,
    ).exclude(pk=rating.pk).first()
    now = timezone.now()
    if counterpart is not None:
        Rating.objects.filter(pk__in=[rating.pk, counterpart.pk]).update(published_at=now)
        return [rating, counterpart]
    if rating.created_at <= now - timedelta(days=EDIT_WINDOW_DAYS):
        Rating.objects.filter(pk=rating.pk).update(published_at=now)
        return [rating]
    return []
