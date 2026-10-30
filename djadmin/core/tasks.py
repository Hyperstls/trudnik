"""Фоновые задачи (перенос Celery-задач Flask, фаза 3).

Паритет app/tasks/: drain_notification_outbox (доставка web+email с учётом
notification_prefs, >3 попыток → failed, лог в email_log), expire_old_jobs
(плюс RPC expire_unfilled_jobs), auto_freeze_on_complaints (RPC
users_exceeding_reports → suspend_user), cleanup_old_email_logs.
Push-доставка — следующий инкремент (после VAPID).
"""
import logging
from datetime import timedelta

from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .celery_app import app
from .models import EmailLog, Notification, NotificationOutbox, Profile
from .rpc import call_rpc, call_rpc_rows

logger = logging.getLogger(__name__)

OUTBOX_BATCH = 50
MAX_ATTEMPTS = 3


def _email_allowed(profile_prefs: dict | None) -> bool:
    prefs = profile_prefs or {}
    return prefs.get("email", True) not in (False, "false", "off", 0)


@app.task(ignore_result=True)
def drain_notification_outbox() -> str:
    rows = list(
        NotificationOutbox.objects.filter(status="pending")
        .select_related("user")
        .order_by("created_at")[:OUTBOX_BATCH]
    )
    processed = failed = skipped = 0
    for row in rows:
        with transaction.atomic():
            Notification.objects.create(
                user=row.user, type=row.type[:50], title=row.title,
                message=row.body, data=row.data or {},
            )
        prefs = getattr(row.user, "notification_prefs", None) or {}
        email_ok = True
        if _email_allowed(prefs) and row.user.email:
            email_ok = _send_email(row)
            if email_ok:
                processed += 1
            else:
                failed += 1
        else:
            skipped += 1
        # Web Push (VAPID): уведомляем активные подписки
        _send_pushes(row)
        if (email_ok and _email_allowed(prefs)) or not _email_allowed(prefs):
            processed_or_failed = "sent"
        elif email_ok:
            processed_or_failed = "skipped"
        else:
            processed_or_failed = None
        row.attempts += 1
        if processed_or_failed == "sent" or processed_or_failed == "skipped":
            row.status = "sent"
            row.processed_at = timezone.now()
        elif row.attempts >= MAX_ATTEMPTS:
            row.status = "failed"
            row.processed_at = timezone.now()
        row.save(update_fields=["status", "attempts", "processed_at"])
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
        rpc_expired = int(call_rpc("expire_unfilled_jobs") or 0)
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
