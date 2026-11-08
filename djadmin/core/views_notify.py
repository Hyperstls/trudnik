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
from django.utils.translation import gettext as _
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
    messages.info(request, _("Отмечено прочитанными: %d.") % count)
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
    deleted, _omitted = (
        Notification.objects.filter(user=request.user)
        .annotate(_invitation_type=Coalesce(KeyTextTransform("type", "data"), Value(""), output_field=CharField()))
        .exclude(
            Q(_invitation_type="invitation")
            | Q(message__icontains="Вас пригласили")
        )
        .delete()
    )
    messages.info(request, _("Удалено уведомлений: %d.") % deleted)
    return redirect("core:notifications")


@login_required
@require_POST
@rate_limit_write(limit=3, window=60, redirect_to="/notifications/settings")
def notification_test(request):
    ok = enqueue_notification(
        request.user.pk, "test", _("Тестовое уведомление"),
        _("Если вы видите это — уведомления работают."),
        {"link": "/notifications"},
    )
    if ok:
        messages.success(request, _("Тестовое уведомление поставлено в очередь. Доставка — до 10 секунд."))
    else:
        messages.error(request, _("Не удалось поставить уведомление в очередь."))
    return redirect("core:notification_prefs")


@login_required
def notifications_unread_count(request):
    return JsonResponse({
        "unread_count": Notification.objects.filter(user=request.user, is_read=False).count()
    })

# ── Web Push подписки ───────────────────────────────────────────────────────

PUSH_MAX_SUBSCRIPTIONS = 10


def _parse_legacy_ipv4(host: str):
    """IPv4 в legacy-нотациях: 127.1, 0x7f.1, 0177.0.0.1, 2130706433.

    glibc getaddrinfo (прод-Linux) резолвит их в реальные адреса, поэтому
    «есть точка → домен» — дыра SSRF (аудит 2026-11-08, A2). Возвращает
    ipaddress.IPv4Address или None, если хост не является числовым IP.
    """
    import ipaddress

    parts = host.split(".")
    if not 1 <= len(parts) <= 4:
        return None
    numbers = []
    for part in parts:
        if not part:
            return None
        try:
            if part.lower().startswith("0x"):
                numbers.append(int(part, 16))
            elif len(part) > 1 and part.startswith("0"):
                numbers.append(int(part, 8))
            else:
                numbers.append(int(part))
        except ValueError:
            return None
    if any(n < 0 for n in numbers):
        return None
    if any(n > 255 for n in numbers[:-1]):
        return None
    if numbers[-1] >= 256 ** (5 - len(numbers)):
        return None
    value = 0
    for number in numbers[:-1]:
        value = (value << 8) | number
    value = (value << (8 * (5 - len(numbers)))) | numbers[-1]
    return ipaddress.IPv4Address(value)


def _push_endpoint_ok(endpoint: str) -> bool:
    """R055: анти-SSRF фильтр endpoint'а push-подписки.

    Сервер позже POST-ит на этот URL из Celery, поэтому принимаем только
    https-адреса с нормальным публичным хостом: без localhost/.local/.internal,
    без однословных имён; IP-литерал (v4/v6) обязан быть публичным.
    """
    import ipaddress
    from urllib.parse import urlparse

    try:
        parsed = urlparse(endpoint)
    except Exception:
        return False
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(
        (".localhost", ".local", ".internal", ".home.arpa")
    ):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        legacy = _parse_legacy_ipv4(host)
        if legacy is not None:
            ip = legacy
        else:
            # без точки/двоеточия — внутренний псевдоним, не домен
            return "." in host or ":" in host
    return bool(ip.is_global)
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
    if not _push_endpoint_ok(endpoint):
        return JsonResponse({"error": "endpoint отклонён"}, status=400)
    sub, _ = PushSubscription.objects.get_or_create(
        user=request.user, endpoint=endpoint, defaults={"p256dh": p256dh, "auth": auth}
    )
    # R055: не копим мусорные подписки — старейшие сверх лимита удаляем.
    newest_first = PushSubscription.objects.filter(user=request.user).order_by("-pk")
    for stale in newest_first[PUSH_MAX_SUBSCRIPTIONS:]:
        stale.delete()
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
