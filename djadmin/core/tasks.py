"""Фоновые задачи (перенос Celery-задач Flask, фаза 3).

Паритет app/tasks/: drain_notification_outbox (доставка web+email с учётом
notification_prefs, >3 попыток → failed, лог в email_log), expire_old_jobs
(плюс RPC expire_unfilled_jobs), auto_freeze_on_complaints (RPC
users_exceeding_reports → suspend_user), cleanup_old_email_logs.
Push-доставка — следующий инкремент (после VAPID).
"""
import logging
from datetime import timedelta
from urllib.parse import parse_qs
from uuid import UUID

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.db.models import Q
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .celery_app import app
from .models import Application, EmailLog, Job, Notification, NotificationOutbox, Profile, Rating
from .notifications import enqueue_notification
from .reputation import publish_reciprocal
from .rpc import call_rpc, call_rpc_rows

logger = logging.getLogger(__name__)

OUTBOX_BATCH = 50
MAX_ATTEMPTS = 3


def _pref_on(prefs: dict | None, key: str, default: bool = True) -> bool:
    value = (prefs or {}).get(key, default)
    return value not in (False, "false", "off", 0)


def _email_allowed(profile_prefs: dict | None) -> bool:
    prefs = profile_prefs or {}
    if "email_enabled" in prefs:
        return _pref_on(prefs, "email_enabled")
    return _pref_on(prefs, "email", True)  # backward compatibility


def _push_allowed(profile_prefs: dict | None) -> bool:
    return _pref_on(profile_prefs, "push_enabled")


def _in_app_allowed(profile_prefs: dict | None) -> bool:
    return _pref_on(profile_prefs, "in_app_enabled")


TYPE_PREF_KEYS = {
    "application_received": "application",
    "application_accepted": "application",
    "application_rejected": "application",
    "invitation": "invitation",
    "new_message": "chat",
    "new_rating": "rating",
    "rating_reminder": "rating",
    "job_completed": "job",
    "job_expired": "job",
    "saved_search": "saved_search",
}


def _type_allowed(profile_prefs: dict | None, notification_type: str) -> bool:
    key = TYPE_PREF_KEYS.get(notification_type)
    return True if key is None else _pref_on(profile_prefs, key)


@app.task(bind=True, max_retries=3, default_retry_delay=60, ignore_result=True)
def send_transactional_email(self, subject: str, message: str, to_email: str) -> None:
    """Транзакционное письмо (регистрация/сброс). SMTP-сбой → retry (3 попытки)."""
    try:
        send_mail(subject, message, None, [to_email])
    except Exception as exc:
        from .privacy import mask_email

        logger.warning(
            "send_transactional_email failed to=%s: %s", mask_email(to_email), exc
        )
        raise self.retry(exc=exc)


@app.task(ignore_result=True)
def drain_notification_outbox() -> str:
    rows = list(
        NotificationOutbox.objects.filter(status="pending")
        .select_related("user")
        .order_by("created_at")[:OUTBOX_BATCH]
    )
    processed = failed = skipped = 0
    for row in rows:
        prefs = getattr(row.user, "notification_prefs", None) or {}
        if not _type_allowed(prefs, row.type):
            row.status = "sent"
            row.processed_at = timezone.now()
            row.save(update_fields=["status", "processed_at"])
            skipped += 1
            continue

        delivered = False
        if _in_app_allowed(prefs):
            with transaction.atomic():
                notif = Notification.objects.create(
                    user=row.user, type=row.type[:50], title=row.title,
                    message=row.body, data=row.data or {},
                )
            from .consumers_notify import notify_user

            notify_user(row.user_id, {
                "id": str(notif.pk), "type": notif.type, "title": notif.title,
                "message": notif.message or "", "unread": True,
            })
            delivered = True

        email_failed = False
        if _email_allowed(prefs) and row.user.email:
            if _send_email(row):
                processed += 1
                delivered = True
            else:
                failed += 1
                email_failed = True
        else:
            skipped += 1

        if _push_allowed(prefs) and _send_pushes(row):
            delivered = True

        row.attempts += 1
        if email_failed and row.attempts < MAX_ATTEMPTS:
            row.save(update_fields=["attempts"])
            continue
        if email_failed:
            row.status = "failed"
        else:
            row.status = "sent"
        row.processed_at = timezone.now()
        row.save(update_fields=["status", "attempts", "processed_at"])
        if not delivered and not email_failed:
            # channel disabled / no recipient — already counted in skipped
            pass
    summary = "drain: processed=%d failed=%d skipped=%d" % (processed, failed, skipped)
    if processed or failed or skipped:
        logger.info(summary)
    return summary


def _send_email(row: NotificationOutbox) -> bool:
    log = EmailLog(user=row.user, to_email=row.user.email, subject=row.title,
                   template_name="outbox", status="pending")
    try:
        send_mail(row.title, row.body or "", None, [row.user.email], fail_silently=False)
        log.status, log.sent_at = "sent", timezone.now()
        return True
    except Exception as exc:
        log.status, log.error_message = "failed", str(exc)[:500]
        return False
    finally:
        log.attempts = 1
        log.last_attempt_at = timezone.now()
        try:
            log.save()
        except Exception:
            logger.exception("email_log save failed")


def _send_pushes(row: NotificationOutbox) -> int:
    """Отправить push по всем подпискам пользователя; мёртвые (410) — удалить."""
    from .models import PushSubscription
    from .push import send_web_push, vapid_configured
    if not vapid_configured():
        return 0
    sent = 0
    for sub in PushSubscription.objects.filter(user=row.user):
        result = send_web_push(
            {"endpoint": sub.endpoint, "p256dh": sub.p256dh, "auth": sub.auth},
            row.title, row.body or "", url="/notifications",
        )
        if result["gone"]:
            sub.delete()  # подписка отозвана браузером
        elif result["success"]:
            sent += 1
    return sent


@app.task(ignore_result=True)
def expire_old_jobs() -> int:
    from .models import Job

    updated = Job.objects.filter(
        status=Job.Status.OPEN, expires_at__lt=timezone.now()
    ).update(status=Job.Status.EXPIRED)
    rpc_expired = 0
    try:
        result = call_rpc("expire_unfilled_jobs")
        # call_rpc отдаёт первую строку как dict ({'expire_unfilled_jobs': N}),
        # поэтому скалярный RETURNS integer приходит в обёртке, а не числом.
        if isinstance(result, dict):
            rpc_expired = int(result.get("expire_unfilled_jobs") or 0)
        else:
            rpc_expired = int(result or 0)
    except Exception:
        logger.warning("expire_unfilled_jobs rpc failed", exc_info=True)
    if updated or rpc_expired:
        logger.info("expire_old_jobs: orm=%d rpc=%d", updated, rpc_expired)
    return updated + rpc_expired


@app.task(ignore_result=True)
def auto_freeze_on_complaints(threshold: int = 5, hours: int = 24) -> int:
    frozen = 0
    try:
        result = call_rpc_rows("users_exceeding_reports", threshold, hours)
    except Exception:
        logger.warning("users_exceeding_reports rpc failed", exc_info=True)
        return 0
    for item in result or []:
        reported_id = item.get("reported_id") if isinstance(item, dict) else None
        if not reported_id:
            continue
        is_admin = Profile.objects.filter(pk=reported_id, role=Profile.Role.ADMIN).exists()
        if is_admin:
            continue
        try:
            call_rpc("suspend_user", reported_id,
                     "Авто-заморозка: %d жалоб за %dч" % (threshold, hours))
            frozen += 1
        except Exception:
            logger.warning("suspend_user failed for %s", reported_id, exc_info=True)
    if frozen:
        logger.info("auto_freeze_on_complaints: frozen=%d", frozen)
    return frozen


@app.task(ignore_result=True)
def cleanup_old_email_logs() -> int:
    now = timezone.now()
    deleted, _ = EmailLog.objects.filter(
        status="sent", sent_at__lt=now - timedelta(days=30)
    ).delete()
    _, _2 = EmailLog.objects.filter(
        status="failed", created_at__lt=now - timedelta(days=7)
    ).delete()
    if deleted:
        logger.info("cleanup_old_email_logs: removed=%d", deleted)
    return int(deleted)


@app.task(ignore_result=True)
def cleanup_personal_data_retention() -> dict:
    """R057 (152-ФЗ): сроки хранения персональных данных.

    outbox: sent/skipped > 30 дн, failed > 7 дн (копии текстов уведомлений,
    включая превью чатов, не живут вечно);
    audit_log: > 180 дн (IP и ФИО/email в JSON);
    django_session: истёкшие (UA в метаданных);
    push_subscriptions: не обновлявшиеся > 90 дн (мёртвые браузеры).
    Каждая ветка независима: падение одной не блокирует остальные.
    """
    now = timezone.now()
    counts = {}
    try:
        deleted, _ = NotificationOutbox.objects.filter(
            status__in=("sent", "skipped"), processed_at__lt=now - timedelta(days=30)
        ).delete()
        deleted2, _ = NotificationOutbox.objects.filter(
            status="failed", created_at__lt=now - timedelta(days=7)
        ).delete()
        counts["notification_outbox"] = int(deleted) + int(deleted2)
    except Exception:
        logger.exception("retention: notification_outbox cleanup failed")
        counts["notification_outbox"] = None
    try:
        from .models import AuditLog

        deleted, _ = AuditLog.objects.filter(
            created_at__lt=now - timedelta(days=180)
        ).delete()
        counts["audit_log"] = int(deleted)
    except Exception:
        logger.exception("retention: audit_log cleanup failed")
        counts["audit_log"] = None
    try:
        from django.contrib.sessions.models import Session

        deleted, _ = Session.objects.filter(expire_date__lt=now).delete()
        counts["expired_sessions"] = int(deleted)
    except Exception:
        logger.exception("retention: expired sessions cleanup failed")
        counts["expired_sessions"] = None
    try:
        from .models import PushSubscription

        deleted, _ = PushSubscription.objects.filter(
            updated_at__lt=now - timedelta(days=90)
        ).delete()
        counts["stale_push_subscriptions"] = int(deleted)
    except Exception:
        logger.exception("retention: stale push subscriptions cleanup failed")
        counts["stale_push_subscriptions"] = None
    if any(counts.values()):
        logger.info("cleanup_personal_data_retention: %s", counts)
    return counts


def _saved_search_jobs(user, item, since):
    from decimal import Decimal
    from .models import Application, Job

    params = parse_qs(item.get("query") or "")
    def one(key):
        return (params.get(key) or [""])[0].strip()

    qs = Job.objects.filter(
        status="open", moderation_status="ok", created_at__gt=since
    ).exclude(employer=user)
    q = one("q")
    if q:
        qs = qs.filter(
            Q(work_type__icontains=q) | Q(organization_name__icontains=q)
            | Q(city__icontains=q) | Q(detailed_description__icontains=q)
            | Q(object_description__icontains=q)
        ).distinct()
    city = one("city")
    if city:
        qs = qs.filter(city__icontains=city)
    skill_ids = []
    for raw in params.get("skills") or []:
        try:
            skill_ids.append(UUID(str(raw)))
        except (TypeError, ValueError):
            continue
    if skill_ids:
        qs = qs.filter(job_skills__skill_id__in=skill_ids).distinct()
    try:
        qs = qs.filter(payment_amount__gte=Decimal(one("payment_min")))
    except Exception:
        pass
    try:
        qs = qs.filter(payment_amount__lte=Decimal(one("payment_max")))
    except Exception:
        pass
    job_filter = one("filter")
    from .models import Application
    active_apps = Application.objects.filter(worker=user).exclude(
        status__in=("withdrawn", "cancelled")
    ).values("job_id")
    if job_filter == "new":
        qs = qs.exclude(pk__in=active_apps)
    elif job_filter == "applied":
        qs = qs.filter(pk__in=active_apps)
    return list(qs.order_by("-created_at")[:3])


@app.task(ignore_result=True)
def notify_saved_searches() -> str:
    """Ежедневный (не чаще 24ч) дайджест по сохранённым поискам."""
    now = timezone.now()
    users = Profile.objects.filter(notification_prefs__has_key="saved_searches")
    notified = 0
    for user in users.iterator():
        prefs = user.notification_prefs or {}
        searches = [item for item in (prefs.get("saved_searches") or []) if isinstance(item, dict)]
        if not searches:
            continue
        frequency = prefs.get("digest_frequency", "daily")
        if frequency == "off":
            continue
        instant = frequency == "instant"
        since = now - (timedelta(minutes=5) if instant else timedelta(hours=24))
        raw_since = prefs.get("saved_search_digest_at")
        if raw_since:
            try:
                last_digest = timezone.datetime.fromisoformat(raw_since)
                if timezone.is_naive(last_digest):
                    last_digest = timezone.make_aware(last_digest)
                if not instant and now - last_digest < timedelta(hours=24):
                    continue
                since = last_digest
            except (TypeError, ValueError):
                pass
        found = []
        seen = set()
        for item in searches[:10]:
            if item.get("notify", True) is False:
                continue
            name = item.get("name") or "Мой поиск"
            for job in _saved_search_jobs(user, item, since):
                if job.pk in seen:
                    continue
                seen.add(job.pk)
                found.append((name, job))
        found = found[:9]
        if found:
            titles = "; ".join("%s — %s" % (name, job.work_type or "Задание") for name, job in found)
            first = found[0][1]
            link = (getattr(settings, "SITE_URL", "") or "").rstrip("/") + reverse("core:job_detail", args=[first.pk])
            enqueue_notification(
                user.pk, "saved_search", "Новые задания по сохранённому поиску",
                titles, {"link": link, "job_id": str(first.pk)},
            )
            notified += 1
        prefs["saved_search_digest_at"] = now.isoformat()
        Profile.objects.filter(pk=user.pk).update(notification_prefs=prefs)
    return "saved_search_digest: users=%d" % notified


@app.task(ignore_result=True)
def ensure_max_webhook() -> str:
    """Self-heal MAX webhook subscription (bot_started + message_created)."""
    from .views_messenger import ensure_max_webhook as ensure

    result = ensure()
    if result.get("ok"):
        return "max_webhook: %s" % result.get("action", "ok")
    logger.warning("max_webhook not registered: %s", result.get("error"))
    return "max_webhook: %s" % result.get("error", "failed")


@app.task(ignore_result=True)
def publish_due_ratings(limit: int = 500) -> int:
    """Publish reciprocal ratings and ratings whose 14-day window has passed."""
    pending = Rating.objects.filter(
        published_at__isnull=True,
        moderation_status=Rating.ModerationStatus.OK,
    ).order_by("created_at")[:limit]
    published = 0
    for rating in pending:
        for item in publish_reciprocal(rating):
            enqueue_notification(
                item.rated_user_id,
                "new_rating",
                "Новая оценка",
                "Вас оценили на %d из 5." % item.rating,
                {
                    "rating_id": str(item.pk),
                    "link": "%s%s" % (
                        settings.SITE_URL, reverse("core:user_ratings", args=[item.rated_user_id])
                    ),
                },
            )
            published += 1
    if published:
        logger.info("publish_due_ratings: published=%d", published)
    return published


@app.task(ignore_result=True)
def remind_pending_ratings(limit: int = 200) -> int:
    """Remind participants to rate after completion or 3 days past the date."""
    now = timezone.now()
    cutoff_date = now - timedelta(days=3)
    apps = (
        Application.objects.filter(status=Application.Status.ACCEPTED)
        .select_related("job", "worker", "job__employer")
        .filter(
            Q(job__status=Job.Status.COMPLETED)
            | Q(
                job__status__in=(Job.Status.OPEN, Job.Status.ACTIVE, Job.Status.IN_PROGRESS),
                job__date_time__lte=cutoff_date,
            )
        )
        .exclude(job__status=Job.Status.CANCELLED)
        .order_by("-job__date_time")[:limit]
    )
    sent = 0
    for app in apps:
        pairs = (
            (app.worker_id, app.job.employer_id),
            (app.job.employer_id, app.worker_id),
        )
        for rater_id, rated_id in pairs:
            if Rating.objects.filter(
                job_id=app.job_id, rater_user_id=rater_id, rated_user_id=rated_id,
            ).exists():
                continue
            key = "rating_reminder:%s:%s:%s" % (app.job_id, rater_id, rated_id)
            try:
                if not cache.add(key, 1, 7 * 86400):
                    continue
            except Exception:
                continue
            enqueue_notification(
                rater_id,
                "rating_reminder",
                "Оцените вторую сторону",
                "Задание завершено. Расскажите, как всё прошло.",
                {
                    "application_id": str(app.pk),
                    "link": "%s/rate/%s" % (settings.SITE_URL, app.pk),
                },
            )
            sent += 1
    if sent:
        logger.info("remind_pending_ratings: sent=%d", sent)
    return sent
