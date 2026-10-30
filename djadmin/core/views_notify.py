"""Фаза 2д: web-уведомления (read-only inbox, паритет Flask GET /notifications).

Уведомления создаёт Flask-конвейер (notification_outbox → notifications через
Celery); djadmin только читает и отмечает прочтение — вставки не делает
(RLS в PostgREST разрешает INSERT только service_role).
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .models import Notification

PAGE_SIZE = 30


@login_required
def notifications_list(request):
    qs = Notification.objects.filter(user=request.user).order_by("-created_at")
    from django.core.paginator import Paginator

    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "core/notifications.html", {"page": page})


@login_required
@require_POST
def notification_mark_read(request, notification_id):
    updated = Notification.objects.filter(
        pk=notification_id, user=request.user
    ).update(is_read=True)
    if not updated:
        raise Http404("Уведомление не найдено")
    return redirect("core:notifications")


@login_required
@require_POST
def notifications_mark_all_read(request):
    count = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    messages.info(request, "Отмечено прочитанными: %d." % count)
    return redirect("core:notifications")


@login_required
@require_POST
def notification_delete(request, notification_id):
    deleted, _ = Notification.objects.filter(pk=notification_id, user=request.user).delete()
    if not deleted:
        raise Http404("Уведомление не найдено")
    return redirect("core:notifications")


@login_required
def notifications_unread_count(request):
    return JsonResponse({
        "unread_count": Notification.objects.filter(user=request.user, is_read=False).count()
    })
