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

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Application, Job, Message, Profile, Rating


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
# Уникальность (rater, job) — миграция 145; профиль пересчитывает триггер БД.
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
    try:
        with transaction.atomic():
            Rating.objects.create(
                rated_user_id=rated_id, rater_user=request.user, job=app.job,
                rating=stars, comment=comment,
                rating_type=rating_type, target_type=target_type,
            )
    except IntegrityError:
        # upsert: одна оценка (rater, job) — обновляем существующую
        Rating.objects.filter(rater_user=request.user, job=app.job).update(
            rated_user_id=rated_id, rating=stars, comment=comment,
            rating_type=rating_type, target_type=target_type,
        )
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
        .values("id", "sender_id", "content", "created_at")
    )
    return render(request, "core/chat.html", {
        "app": app,
        "chat_messages": messages_qs,
        "client_message_id": str(uuid_lib.uuid4()),
        "last_id": messages_qs[-1]["id"] if messages_qs else 0,
    })


@login_required
@require_POST
def chat_send(request, app_id):
    app = _chat_app_or_none(request, app_id)
    if app is None:
        raise Http404("Чат не найден")
    content = (request.POST.get("content") or "").strip()[:4000]
    client_message_id = request.POST.get("client_message_id") or ""
    if not content:
        return redirect("core:chat_room", app_id=app.pk)
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
            )
    except IntegrityError:
        pass  # повторная отправка того же клиентского сообщения — идемпотентно
    if created is not None:
        from .consumers import notify_new_message
        from django.utils import timezone

        notify_new_message(app.pk, {
            "id": created.pk, "sender_id": str(request.user.pk),
            "content": created.content, "created_at": timezone.now().isoformat(),
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
        .values("id", "sender_id", "content", "created_at")
    )
    return JsonResponse({"messages": [
        {"id": r["id"], "sender_id": str(r["sender_id"]),
         "content": r["content"], "created_at": r["created_at"].isoformat()}
        for r in rows
    ]})


@login_required
def chats_list(request):
    apps = (
        Application.objects.select_related("job", "job__employer", "worker")
        .filter(Q_apps(request))
        .order_by("-updated_at")
    )
    rows = []
    for a in apps[:50]:
        last = Message.objects.filter(application=a).order_by("-id").values_list("content", flat=True).first()
        counterpart = a.job.employer if request.user.pk == a.worker_id else a.worker
        rows.append({"app": a, "counterpart": counterpart, "last": (last or "")[:80]})
    return render(request, "core/chats.html", {"rows": rows})


def Q_apps(request):
    from django.db.models import Q

    my_jobs = Job.objects.filter(employer=request.user).values("id")
    return Q(worker=request.user) | Q(job_id__in=my_jobs)
