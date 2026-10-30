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

from .models import Notification, PushSubscription

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

# ── Web Push подписки ───────────────────────────────────────────────────────
def push_vapid_public_key(request):
    """Публичный VAPID-ключ (для Service Worker, паритет Flask)."""
    from django.conf import settings
    from django.http import JsonResponse
    key = getattr(settings, "VAPID_PUBLIC_KEY", "")
    return JsonResponse({"public_key": key})


@login_required
@require_POST
def push_subscribe(request):
    """Регистрация push-подписки {endpoint, p256dh, auth}."""
    import json as _json
    try:
        data = _json.loads(request.body.decode("utf-8", "replace"))
    except Exception:
        return JsonResponse({"error": "bad_json"}, status=400)
    endpoint = (data.get("endpoint") or "").strip()
    p256dh = (data.get("p256dh") or (data.get("keys") or {}).get("p256dh") or "").strip()
    auth = (data.get("auth") or (data.get("keys") or {}).get("auth") or "").strip()
    if not (endpoint and p256dh and auth):
        return JsonResponse({"error": "endpoint, p256dh, auth обязательны"}, status=400)
    sub, _ = PushSubscription.objects.get_or_create(
        user=request.user, endpoint=endpoint, defaults={"p256dh": p256dh, "auth": auth}
    )
    return JsonResponse({"success": True, "id": sub.pk})


@login_required
@require_POST
def push_unsubscribe(request):
    import json as _json
    try:
        data = _json.loads(request.body.decode("utf-8", "replace"))
    except Exception:
        return JsonResponse({"error": "bad_json"}, status=400)
    endpoint = (data.get("endpoint") or "").strip()
    deleted, _ = PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
    return JsonResponse({"success": True, "deleted": deleted})


@login_required
def push_list(request):
    subs = list(PushSubscription.objects.filter(user=request.user).values("id", "endpoint", "created_at"))
    return JsonResponse({"subscriptions": subs})
