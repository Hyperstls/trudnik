"""Фаза 2г: оценки (rate_user_atomic) и чат (long-poll).

Контракты (pg_proc, 2026-10-30):
- rate_user_atomic(p_job_id, p_rater_user_id, p_rated_user_id, p_rating int,
  p_comment, p_rating_type, p_target_type) → jsonb (упсерт, миграция 145);
  рейтинг профиля пересчитывает триггер recompute_profile_rating — НЕ считать в коде.
  rating_type = сторона ОЦЕНИВАЮЩЕГО, target_type = сторона ОЦЕНИВАЕМОГО
  (worker↔employer в рамках задания).
- Чат: доступ = участие (worker заявки ИЛИ владелец задания — паритет
  app/services/chat_access.py; блэклист там не проверяется). Идемпотентность
  отправки — client_message_id (частичный UNIQUE в БД).
"""
import uuid as uuid_lib
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .anti_fraud import is_duplicate_message
from .models import Application, Job, Message, Profile, Rating, RatingReport
from .notifications import enqueue_notification
from .reputation import (
    EDIT_WINDOW_DAYS, publish_reciprocal, rating_options, review_moderation_reason,
)
from .ratelimit import rate_limit_write
from .storage import UploadError, delete_upload_url, save_upload

ATTACHMENT_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


def _chat_app_or_none(request, app_id):
    """Приложение+задание, если пользователь — участник чата (паритет chat_access)."""
    app = (
        Application.objects.select_related("job", "job__employer", "worker")
        .filter(pk=app_id)
        .first()
    )
    if app is None:
        return None
    if request.user.pk not in (app.worker_id, app.job.employer_id):
        return None
    return app


# ── Оценки ──────────────────────────────────────────────────────────────────
# Публикация двусторонняя: отзыв становится видимым после ответного отзыва
# второй стороны или через 14 дней (double-blind, защита от retaliatory review).
def _rating_options(target_type):
    return rating_options(target_type)


def _rating_target(app, user):
    """Return the counterparty and rating sides for an accepted application."""
    if app.status != Application.Status.ACCEPTED:
        return None
    if user.pk == app.worker_id:
        return {
            "target": app.job.employer,
            "rated_id": app.job.employer_id,
            "rating_type": "worker",
            "target_type": "employer",
        }
    if user.pk == app.job.employer_id:
        return {
            "target": app.worker,
            "rated_id": app.worker_id,
            "rating_type": "employer",
            "target_type": "worker",
        }
    return None


def _notify_rating_published(rating, request):
    enqueue_notification(
        rating.rated_user_id,
        "new_rating",
        _("Новая оценка"),
        _("Вас оценили на %d из 5.") % rating.rating,
        {
            "rating_id": str(rating.pk),
            "link": request.build_absolute_uri(
                reverse("core:user_ratings", args=[rating.rated_user_id])
            ),
        },
    )


@login_required
def rate_participant(request, app_id):
    app = _chat_app_or_none(request, app_id)
    if app is None:
        raise Http404("Отклик не найден")
    sides = _rating_target(app, request.user)
    if sides is None:
        messages.error(request, _("Оценить можно только принятого участника задания."))
        return redirect(reverse("core:my_applications"))
    target = sides["target"]
    existing = Rating.objects.filter(
        rater_user=request.user, job=app.job, rated_user_id=sides["rated_id"],
    ).first()
    criteria_options, tag_options = _rating_options(sides["target_type"])

    if request.method == "POST":
        if not app.rating_available:
            messages.error(request, _("Оценка станет доступна после завершения задания."))
            return redirect(reverse("core:rate_participant", args=[app.pk]))
        if existing is not None and (
            not existing.is_editable
            or existing.moderation_status == Rating.ModerationStatus.HIDDEN
        ):
            messages.error(request, _("Оценка зафиксирована или скрыта модератором."))
            return redirect(reverse("core:user_ratings", args=[sides["rated_id"]]))
        try:
            stars = int(request.POST.get("rating", "0"))
        except (TypeError, ValueError):
            stars = 0
        if not 1 <= stars <= 5:
            messages.error(request, _("Оценка — от 1 до 5."))
            return redirect(reverse("core:rate_participant", args=[app.pk]))
        comment = (request.POST.get("comment") or "").strip()[:1000]
        criteria = {}
        allowed_criteria = {key for key, _label in criteria_options}
        for key in allowed_criteria:
            raw = request.POST.get("criterion_%s" % key)
            if raw in ("1", "2", "3", "4", "5"):
                criteria[key] = int(raw)
        allowed_tags = {key for key, _label in tag_options}
        tags = [key for key in request.POST.getlist("tags") if key in allowed_tags]
        moderation_reason = review_moderation_reason(comment, criteria, tags)
        defaults = {
            "rating": stars,
            "comment": comment,
            "criteria": criteria,
            "tags": tags,
            "rating_type": sides["rating_type"],
            "target_type": sides["target_type"],
            "moderation_status": (
                Rating.ModerationStatus.REVIEW if moderation_reason else Rating.ModerationStatus.OK
            ),
            "moderation_reason": moderation_reason,
        }
        with transaction.atomic():
            rating, created = Rating.objects.update_or_create(
                rated_user_id=sides["rated_id"], rater_user=request.user, job=app.job,
                defaults=defaults,
            )
            if created:
                Rating.objects.filter(pk=rating.pk).update(published_at=None)
            rating.refresh_from_db()
            published = []
            if rating.moderation_status == Rating.ModerationStatus.OK:
                published = publish_reciprocal(rating)
        if published:
            for item in published:
                _notify_rating_published(item, request)
            messages.success(request, _("Оценка опубликована."))
        elif moderation_reason:
            messages.info(request, _("Отзыв отправлен на проверку модератору."))
        else:
            messages.success(
                request,
                _("Оценка сохранена. Она опубликуется после ответной оценки или через 14 дней."),
            )
        return redirect(reverse("core:user_ratings", args=[sides["rated_id"]]))

    return render(request, "core/rate_participant.html", {
        "app": app,
        "target": target,
        "target_type": sides["target_type"],
        "existing": existing,
        "criteria_options": criteria_options,
        "tag_options": tag_options,
        "selected_tags": set(existing.tags or []) if existing else set(),
        "selected_criteria": (existing.criteria if existing and isinstance(existing.criteria, dict) else {}),
        "rating_choices": (
            (5, _("Отлично")), (4, _("Хорошо")), (3, _("Нормально")),
            (2, _("Плохо")), (1, _("Очень плохо")),
        ),
        "rating_available": app.rating_available,
        "can_edit": existing is None or existing.is_editable,
        "edit_window_days": EDIT_WINDOW_DAYS,
    })


@login_required
@require_POST
@rate_limit_write(limit=10, window=60, redirect_to="/my-applications")
def rating_reply(request, rating_id):
    rating = Rating.objects.filter(pk=rating_id, rated_user=request.user).first()
    if rating is None:
        raise Http404("Оценка не найдена")
    reply = (request.POST.get("reply") or "").strip()[:1000]
    if not reply:
        messages.error(request, _("Введите ответ."))
        return redirect(reverse("core:user_ratings", args=[rating.rated_user_id]))
    Rating.objects.filter(pk=rating.pk).update(reply=reply, replied_at=timezone.now())
    messages.success(request, _("Ответ сохранён."))
    return redirect(reverse("core:user_ratings", args=[rating.rated_user_id]))


@login_required
@require_POST
@rate_limit_write(limit=5, window=600, redirect_to="/jobs")
def rating_report(request, rating_id):
    rating = Rating.objects.filter(pk=rating_id, published_at__isnull=False).first()
    if rating is None:
        raise Http404("Оценка не найдена")
    if rating.rated_user_id == request.user.pk:
        messages.error(request, _("Нельзя пожаловаться на свою оценку."))
        return redirect(reverse("core:user_ratings", args=[rating.rated_user_id]))
    reason = (request.POST.get("reason") or "").strip()[:1000]
    if not reason:
        messages.error(request, _("Опишите причину жалобы."))
        return redirect(reverse("core:user_ratings", args=[rating.rated_user_id]))
    RatingReport.objects.get_or_create(
        rating=rating, reporter=request.user, defaults={"reason": reason},
    )
    messages.success(request, _("Жалоба на отзыв отправлена модератору."))
    return redirect(reverse("core:user_ratings", args=[rating.rated_user_id]))


# ── Чат ─────────────────────────────────────────────────────────────────────
def _mark_chat_read(app, user):
    """Mark incoming unread messages as read; return their ids."""
    unread = Message.objects.filter(
        application=app, read_at__isnull=True,
    ).exclude(sender=user)
    ids = list(unread.values_list("id", flat=True))
    if ids:
        unread.update(read_at=timezone.now())
    return ids


@login_required
def chat_room(request, app_id):
    app = _chat_app_or_none(request, app_id)
    if app is None:
        raise Http404("Чат не найден")
    read_ids = _mark_chat_read(app, request.user)
    if read_ids:
        from .consumers import notify_read_receipts
        notify_read_receipts(app.pk, read_ids)
    search_query = (request.GET.get("q") or "").strip()[:100]
    base_messages = Message.objects.filter(application=app).order_by("created_at", "id")
    last_id = base_messages.order_by("-id").values_list("id", flat=True).first() or 0
    if search_query:
        base_messages = base_messages.filter(
            Q(content__icontains=search_query) | Q(attachment_name__icontains=search_query)
        )
    messages_qs = list(
        base_messages.values(
            "id", "sender_id", "content", "created_at",
            "attachment_url", "attachment_name", "attachment_mime", "attachment_size",
            "read_at", "edited_at", "deleted_at",
        )
    )
    prefs = dict(request.user.notification_prefs or {})
    return render(request, "core/chat.html", {
        "app": app,
        "chat_messages": messages_qs,
        "search_query": search_query,
        "is_muted": str(app.pk) in (prefs.get("muted_chats") or []),
        "client_message_id": str(uuid_lib.uuid4()),
        "last_id": messages_qs[-1]["id"] if messages_qs else 0,
    })


@login_required
@require_POST
@rate_limit_write(limit=20, window=60)
def chat_send(request, app_id):
    app = _chat_app_or_none(request, app_id)
    if app is None:
        raise Http404("Чат не найден")
    content = (request.POST.get("content") or "").strip()[:4000]
    attachment = request.FILES.get("attachment")
    if not content and not attachment:
        return redirect("core:chat_room", app_id=app.pk)
    if not attachment and is_duplicate_message(request.user.pk, app.pk, content):
        messages.info(request, _("Такое сообщение уже отправлено."))
        return redirect("core:chat_room", app_id=app.pk)

    attachment_url = attachment_name = attachment_mime = None
    attachment_size = None
    if attachment is not None:
        try:
            attachment_url = save_upload(attachment, "chat", allow_pdf=True)
        except UploadError as exc:
            messages.error(request, str(exc))
            return redirect("core:chat_room", app_id=app.pk)
        saved_ext = Path(attachment_url).suffix.lower()
        attachment_mime = ATTACHMENT_MIME.get(saved_ext, "application/octet-stream")
        attachment_name = Path(attachment.name or "file").name[:255]
        attachment_size = attachment.size

    client_message_id = request.POST.get("client_message_id") or ""
    try:
        cmid = uuid_lib.UUID(client_message_id)
    except ValueError:
        cmid = uuid_lib.uuid4()
    created = None
    try:
        with transaction.atomic():  # savepoint: дубль client_message_id не роняет транзакцию
            created = Message.objects.create(
                sender=request.user, application=app,
                content=content, client_message_id=cmid,
                attachment_url=attachment_url,
                attachment_name=attachment_name,
                attachment_mime=attachment_mime,
                attachment_size=attachment_size,
            )
    except IntegrityError:
        if attachment_url:
            delete_upload_url(attachment_url)
    if created is not None:
        from .consumers import notify_new_message
        from django.utils import timezone

        notify_new_message(app.pk, {
            "id": created.pk, "sender_id": str(request.user.pk),
            "content": created.content, "created_at": timezone.now().isoformat(),
            "attachment_url": created.attachment_url,
            "attachment_name": created.attachment_name,
            "attachment_mime": created.attachment_mime,
        })
        if app.status == Application.Status.ACCEPTED:
            recipient_id = (
                app.job.employer_id if request.user.pk == app.worker_id else app.worker_id
            )
            recipient_prefs = (
                Profile.objects.filter(pk=recipient_id)
                .values_list("notification_prefs", flat=True).first() or {}
            )
            if str(app.pk) not in (recipient_prefs.get("muted_chats") or []):
                preview = content or (
                    _("Вложение") if attachment_url else _("Новое сообщение")
                )
                enqueue_notification(
                    recipient_id,
                    "new_message",
                    _("Новое сообщение"),
                    preview[:200],
                    {
                        "application_id": str(app.pk),
                        "link": request.build_absolute_uri(
                            reverse("core:chat_room", args=[app.pk])
                        ),
                    },
                )
    return redirect("core:chat_room", app_id=app.pk)


@login_required
@require_POST
@rate_limit_write(limit=20, window=60)
def chat_mute(request, app_id):
    app = _chat_app_or_none(request, app_id)
    if app is None:
        raise Http404("Чат не найден")
    prefs = dict(request.user.notification_prefs or {})
    muted = list(prefs.get("muted_chats") or [])
    key = str(app.pk)
    if key in muted:
        muted.remove(key)
        messages.success(request, _("Уведомления по этому чату включены."))
    else:
        muted.append(key)
        messages.info(request, _("Уведомления по этому чату отключены."))
    prefs["muted_chats"] = muted
    Profile.objects.filter(pk=request.user.pk).update(notification_prefs=prefs)
    return redirect("core:chat_room", app_id=app.pk)


@login_required
@require_POST
@rate_limit_write(limit=20, window=60)
def chat_edit_message(request, app_id, message_id):
    app = _chat_app_or_none(request, app_id)
    if app is None:
        raise Http404("Чат не найден")
    msg = Message.objects.filter(
        pk=message_id, application=app, sender=request.user,
        deleted_at__isnull=True,
    ).first()
    if msg is None:
        messages.error(request, _("Сообщение не найдено или уже удалено."))
        return redirect("core:chat_room", app_id=app.pk)
    content = (request.POST.get("content") or "").strip()[:4000]
    if not content and not msg.attachment_url:
        messages.error(request, _("Сообщение не может быть пустым."))
        return redirect("core:chat_room", app_id=app.pk)
    msg.content = content
    msg.edited_at = timezone.now()
    msg.save(update_fields=["content", "edited_at"])
    from .consumers import notify_message_changed
    notify_message_changed(app.pk, {
        "action": "edited",
        "id": msg.pk,
        "content": msg.content,
        "edited_at": msg.edited_at.isoformat(),
    })
    return redirect(reverse("core:chat_room", args=[app.pk]) + "#message-%s" % msg.pk)


@login_required
@require_POST
@rate_limit_write(limit=20, window=60)
def chat_delete_message(request, app_id, message_id):
    app = _chat_app_or_none(request, app_id)
    if app is None:
        raise Http404("Чат не найден")
    msg = Message.objects.filter(
        pk=message_id, application=app, sender=request.user,
        deleted_at__isnull=True,
    ).first()
    if msg is None:
        messages.error(request, _("Сообщение не найдено или уже удалено."))
        return redirect("core:chat_room", app_id=app.pk)
    attachment_url = msg.attachment_url
    msg.content = ""
    msg.attachment_url = None
    msg.attachment_name = None
    msg.attachment_mime = None
    msg.attachment_size = None
    msg.deleted_at = timezone.now()
    msg.save(update_fields=[
        "content", "attachment_url", "attachment_name", "attachment_mime",
        "attachment_size", "deleted_at",
    ])
    if attachment_url:
        delete_upload_url(attachment_url)
    from .consumers import notify_message_changed
    notify_message_changed(app.pk, {"action": "deleted", "id": msg.pk})
    return redirect("core:chat_room", app_id=app.pk)


@login_required
def chat_poll(request, app_id):
    app = _chat_app_or_none(request, app_id)
    if app is None:
        return JsonResponse({"error": "not_found"}, status=404)
    try:
        after = int(request.GET.get("after", "0"))
    except ValueError:
        after = 0
    read_ids = _mark_chat_read(app, request.user)
    if read_ids:
        from .consumers import notify_read_receipts
        notify_read_receipts(app.pk, read_ids)
    rows = list(
        Message.objects.filter(application=app, id__gt=after)
        .order_by("id")
        .values(
            "id", "sender_id", "content", "created_at",
            "attachment_url", "attachment_name", "attachment_mime", "attachment_size",
            "read_at", "edited_at", "deleted_at",
        )
    )
    from django.db.models import Q

    changed = list(
        Message.objects.filter(
            Q(edited_at__isnull=False) | Q(deleted_at__isnull=False),
            application=app,
        ).order_by("-id").values(
            "id", "content", "edited_at", "deleted_at",
            "attachment_url", "attachment_name", "attachment_mime", "attachment_size",
        )[:200]
    )
    own_read_ids = list(
        Message.objects.filter(
            application=app, sender=request.user, read_at__isnull=False,
        ).order_by("-id").values_list("id", flat=True)[:200]
    )
    return JsonResponse({
        "messages": [
            {"id": r["id"], "sender_id": str(r["sender_id"]),
             "content": r["content"], "created_at": r["created_at"].isoformat(),
             "attachment_url": r["attachment_url"],
             "attachment_name": r["attachment_name"],
             "attachment_mime": r["attachment_mime"],
             "attachment_size": r["attachment_size"],
             "read_at": r["read_at"].isoformat() if r["read_at"] else None,
             "edited_at": r["edited_at"].isoformat() if r["edited_at"] else None,
             "deleted_at": r["deleted_at"].isoformat() if r["deleted_at"] else None}
            for r in rows
        ],
        "changes": [
            {"id": r["id"], "content": r["content"],
             "edited_at": r["edited_at"].isoformat() if r["edited_at"] else None,
             "deleted_at": r["deleted_at"].isoformat() if r["deleted_at"] else None,
             "attachment_url": r["attachment_url"],
             "attachment_name": r["attachment_name"],
             "attachment_mime": r["attachment_mime"]}
            for r in changed
        ],
        "read_ids": own_read_ids,
    })


@login_required
@require_POST
def chat_mark_read(request, app_id):
    app = _chat_app_or_none(request, app_id)
    if app is None:
        return JsonResponse({"error": "not_found"}, status=404)
    ids = _mark_chat_read(app, request.user)
    if ids:
        from .consumers import notify_read_receipts
        notify_read_receipts(app.pk, ids)
    return JsonResponse({"ok": True, "read_ids": ids})


@login_required
def chats_list(request):
    from django.db.models import Count, F, OuterRef, Q, Subquery

    last_rows = Message.objects.filter(application=OuterRef("pk")).order_by("-id")
    apps = (
        Application.objects.select_related("job", "job__employer", "worker")
        .filter(Q_apps(request), status=Application.Status.ACCEPTED)
        .annotate(
            last_content=Subquery(last_rows.values("content")[:1]),
            last_attachment_name=Subquery(last_rows.values("attachment_name")[:1]),
            last_attachment_mime=Subquery(last_rows.values("attachment_mime")[:1]),
            last_created_at=Subquery(last_rows.values("created_at")[:1]),
            unread_count=Count(
                "messages",
                filter=Q(messages__read_at__isnull=True) & ~Q(messages__sender=request.user),
                distinct=True,
            ),
        )
        .order_by(F("last_created_at").desc(nulls_last=True), "-updated_at")
    )
    rows = []
    for a in apps[:50]:
        counterpart = a.job.employer if request.user.pk == a.worker_id else a.worker
        if a.last_content:
            last = a.last_content[:80]
        elif a.last_attachment_mime and a.last_attachment_mime.startswith("image/"):
            last = _("Изображение")
        elif a.last_attachment_name:
            last = _("Файл: %s") % a.last_attachment_name[:70]
        else:
            last = ""
        rows.append({
            "app": a,
            "counterpart": counterpart,
            "last": last,
            "last_at": a.last_created_at or a.updated_at,
            "unread_count": a.unread_count,
            "has_attachment": bool(a.last_attachment_name),
        })
    return render(request, "core/chats.html", {"rows": rows})


@login_required
def chats_unread_count(request):
    from django.db.models import Q

    count = (
        Message.objects.filter(
            Q(application__worker=request.user) | Q(application__job__employer=request.user),
            application__status=Application.Status.ACCEPTED,
            read_at__isnull=True,
        )
        .exclude(sender=request.user)
        .count()
    )
    return JsonResponse({"unread_count": count})


def Q_apps(request):
    from django.db.models import Q

    my_jobs = Job.objects.filter(employer=request.user).values("id")
    return Q(worker=request.user) | Q(job_id__in=my_jobs)
