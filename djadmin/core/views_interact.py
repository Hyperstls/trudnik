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
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Application, Job, Message, Profile, Rating
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
        Application.objects.select_related("job")
        .filter(pk=app_id)
        .first()
    )
    if app is None:
        return None
    if request.user.pk not in (app.worker_id, app.job.employer_id):
        return None
    return app


# ── Оценки ──────────────────────────────────────────────────────────────────
# Контракт (сверено с app/blueprints/ratings.py upsert_rating): RPC rate_user_atomic
# допускает только трудник→трудник (оба с accepted-заявкой), поэтому общий случай
# (работодатель↔работник) Flask реализует проверками + прямым upsert в ratings.
# Уникальность (rater, job, rated_user) — миграция 145; профиль пересчитывает триггер БД.
@login_required
@require_POST
def rate_participant(request, app_id):
    app = _chat_app_or_none(request, app_id)
    if app is None:
        raise Http404("Отклик не найден")
    if app.job.status != Job.Status.COMPLETED:
        messages.error(request, "Оценить можно только завершённое задание.")
        return redirect(request.META.get("HTTP_REFERER") or "/")
    try:
        stars = int(request.POST.get("rating", "0"))
    except ValueError:
        stars = 0
    if not 1 <= stars <= 5:
        messages.error(request, "Оценка — от 1 до 5.")
        return redirect(request.META.get("HTTP_REFERER") or "/")
    if request.user.pk == app.worker_id:  # работник оценивает работодателя задания
        if app.status != Application.Status.ACCEPTED:
            messages.error(request, "Оценить работодателя можно только после принятия отклика.")
            return redirect(request.META.get("HTTP_REFERER") or "/")
        rated_id, rating_type, target_type = app.job.employer_id, "worker", "employer"
    else:  # владелец задания оценивает принятого работника
        if app.status != Application.Status.ACCEPTED:
            messages.error(request, "Оценить можно только принятого работника.")
            return redirect(request.META.get("HTTP_REFERER") or "/")
        rated_id, rating_type, target_type = app.worker_id, "employer", "worker"
    if rated_id == request.user.pk:
        messages.error(request, "Нельзя оценить самого себя.")
        return redirect(request.META.get("HTTP_REFERER") or "/")
    comment = (request.POST.get("comment") or "")[:1000]
    defaults = {
        "rating": stars, "comment": comment,
        "rating_type": rating_type, "target_type": target_type,
    }
    try:
        with transaction.atomic():
            Rating.objects.update_or_create(
                rated_user_id=rated_id, rater_user=request.user, job=app.job,
                defaults=defaults,
            )
    except IntegrityError:
        # upsert: одна оценка (rater, job, rated_user) — обновляем только её
        Rating.objects.filter(
            rater_user=request.user, job=app.job, rated_user_id=rated_id
        ).update(updated_at=timezone.now(), **defaults)
    messages.success(request, "Оценка сохранена.")
    return redirect(request.META.get("HTTP_REFERER") or "/")


# ── Чат ─────────────────────────────────────────────────────────────────────
@login_required
def chat_room(request, app_id):
    app = _chat_app_or_none(request, app_id)
    if app is None:
        raise Http404("Чат не найден")
    messages_qs = list(
        Message.objects.filter(application=app).order_by("created_at", "id")
        .values(
            "id", "sender_id", "content", "created_at",
            "attachment_url", "attachment_name", "attachment_mime", "attachment_size",
        )
    )
    return render(request, "core/chat.html", {
        "app": app,
        "chat_messages": messages_qs,
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
    rows = list(
        Message.objects.filter(application=app, id__gt=after)
        .order_by("id")
        .values(
            "id", "sender_id", "content", "created_at",
            "attachment_url", "attachment_name", "attachment_mime", "attachment_size",
        )
    )
    return JsonResponse({"messages": [
        {"id": r["id"], "sender_id": str(r["sender_id"]),
         "content": r["content"], "created_at": r["created_at"].isoformat(),
         "attachment_url": r["attachment_url"],
         "attachment_name": r["attachment_name"],
         "attachment_mime": r["attachment_mime"],
         "attachment_size": r["attachment_size"]}
        for r in rows
    ]})


@login_required
def chats_list(request):
    from django.db.models import OuterRef, Subquery

    last_message = (
        Message.objects.filter(application=OuterRef("pk"))
        .order_by("-id").values("content")[:1]
    )
    apps = (
        Application.objects.select_related("job", "job__employer", "worker")
        .filter(Q_apps(request), status=Application.Status.ACCEPTED)
        .annotate(last_message=Subquery(last_message))
        .order_by("-updated_at")
    )
    rows = []
    for a in apps[:50]:
        counterpart = a.job.employer if request.user.pk == a.worker_id else a.worker
        rows.append({"app": a, "counterpart": counterpart, "last": (a.last_message or "")[:80]})
    return render(request, "core/chats.html", {"rows": rows})


def Q_apps(request):
    from django.db.models import Q

    my_jobs = Job.objects.filter(employer=request.user).values("id")
    return Q(worker=request.user) | Q(job_id__in=my_jobs)
