"""Фаза 2д: web-уведомления (read-only inbox, паритет Flask GET /notifications).

Уведомления создаёт Flask-конвейер (notification_outbox → notifications через
Celery); djadmin только читает и отмечает прочтение — вставки не делает
(RLS в PostgREST разрешает INSERT только service_role).
"""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Notification, Profile, PushSubscription
from .notifications import enqueue_notification
from .ratelimit import rate_limit_write

PAGE_SIZE = 30


@login_required
def notifications_list(request):
    qs = Notification.objects.filter(user=request.user).order_by("-created_at")
    from django.core.paginator import Paginator

    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    today = timezone.localdate()
    return render(request, "core/notifications.html", {
        "page": page,
        "today": today,
        "yesterday": today - timedelta(days=1),
    })


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
@require_POST
def notifications_delete_all(request):
    """Удалить все уведомления пользователя, кроме приглашений."""
    from django.db.models import CharField, Q, Value
    from django.db.models.fields.json import KeyTextTransform
    from django.db.models.functions import Coalesce

    # data->>'type' у обычных уведомлений NULL: NOT (NULL OR false) не сработает,
    # поэтому сначала приводим отсутствующий ключ к пустой строке.
    deleted, _ = (
        Notification.objects.filter(user=request.user)
        .annotate(_invitation_type=Coalesce(KeyTextTransform("type", "data"), Value(""), output_field=CharField()))
        .exclude(
            Q(_invitation_type="invitation")
            | Q(message__icontains="Вас пригласили")
        )
        .delete()
    )
    messages.info(request, "Удалено уведомлений: %d." % deleted)
    return redirect("core:notifications")


@login_required
@require_POST
@rate_limit_write(limit=3, window=60, redirect_to="/notifications/settings")
def notification_test(request):
    ok = enqueue_notification(
        request.user.pk, "test", "Тестовое уведомление",
        "Если вы видите это — уведомления работают.",
        {"link": "/notifications"},
    )
    if ok:
        messages.success(request, "Тестовое уведомление поставлено в очередь. Доставка — до 10 секунд.")
    else:
        messages.error(request, "Не удалось поставить уведомление в очередь.")
    return redirect("core:notification_prefs")


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
    prefs = dict(request.user.notification_prefs or {})
    if not prefs.get("push_enabled"):
        prefs["push_enabled"] = True
        Profile.objects.filter(pk=request.user.pk).update(notification_prefs=prefs)
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
