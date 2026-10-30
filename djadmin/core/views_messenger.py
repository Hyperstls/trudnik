"""Фаза 2е: мессенджер-верификация через MAX (зеркало Flask, контракт сверен).

Flask-контракт (app/blueprints/messenger_verify.py):
- токен: cache-ключ msg_verify:<token> → user_id, TTL 600с, одноразовый;
- ссылка: https://max.ru/<bot>?start=<token>;
- webhook: заголовок X-Max-Bot-Api-Secret (hmac.compare_digest), fail-closed
  (нет env → 503, неверный → 401); update_type: bot_started (payload=token,
  user.user_id) | message_created (message.body.text, sender.user_id);
- RPC verify_via_messenger(user, provider, uid) → verification_status='approved'.

Отличие: бот-ответы в чат (_send_max) не отправляем — требуется MAX API-токен и
исходящий клиент; верификация при этом полная (инструкция — на странице старта).
"""
import hmac
import secrets as pysecrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .rpc import call_rpc

TOKEN_TTL = 600  # 10 минут (паритет Flask)
PLATFORMS = {"max"}
BOT_LINK = {"max": "https://max.ru/{bot}?start={token}"}


def _cache():
    from django.core.cache import cache

    return cache


@login_required
def start(request, platform: str):
    if platform not in PLATFORMS:
        raise Http404("Неизвестная платформа")
    bot = getattr(settings, "MAX_BOT_USERNAME", "").strip()
    if not bot:
        messages.error(request, "Верификация через мессенджер не настроена (обратитесь к администратору).")
        return render(request, "core/messenger_start.html", {"link": None, "platform": platform})
    token = pysecrets.token_urlsafe(24)
    _cache().set("msg_verify:%s" % token, str(request.user.pk), TOKEN_TTL)
    link = BOT_LINK[platform].format(bot=bot, token=token)
    return render(request, "core/messenger_start.html",
                  {"link": link, "platform": platform, "ttl_minutes": TOKEN_TTL // 60})


@csrf_exempt  # внешний MAX Bot API; защита — секрет в заголовке (fail-closed)
@require_POST
def webhook_max(request):
    expected = (getattr(settings, "MAX_WEBHOOK_SECRET", "") or "").strip()
    if not expected:
        return JsonResponse({"ok": False, "error": "webhook not configured"}, status=503)
    provided = request.headers.get("X-Max-Bot-Api-Secret", "")
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        return JsonResponse({"ok": False, "error": "unauthorized"}, status=401)

    data = _json_body(request)
    update_type = data.get("update_type", "")
    chat_id = data.get("chat_id")
    token, uid = "", ""
    if update_type == "bot_started":
        token = str(data.get("payload") or "").strip()
        uid = str((data.get("user") or {}).get("user_id") or "")
    elif update_type == "message_created":
        message = data.get("message") or {}
        body = message.get("body") or {}
        text = str(body.get("text") or message.get("text") or "").strip()
        uid = str((message.get("sender") or {}).get("user_id") or "")
        token = _extract_token(text)
    if token and uid:
        _complete(token, uid)
    # неизвестные/пустые события молча ack — MAX не должен ретраить ботоведение
    return JsonResponse({"ok": True})


def _json_body(request) -> dict:
    try:
        import json

        return json.loads(request.body.decode("utf-8", "replace") or "{}")
    except Exception:
        return {}


def _extract_token(text: str) -> str:
    """'/start <token>' | '<token>' → token (произвольная urlsafe-строка)."""
    if not text:
        return ""
    parts = text.split()
    if parts and parts[0].lower().startswith(("/start", "start")):
        parts = parts[1:]  # /start[@bot] <token> | start <token>
    return parts[0] if parts else ""


def _complete(token: str, messenger_uid: str) -> None:
    cache = _cache()
    key = "msg_verify:%s" % token
    user_id = cache.get(key)
    if not user_id:
        return  # ссылка устарела/использована — бот-ответ не шлём (см. докстринг)
    cache.delete(key)  # одноразовость
    try:
        call_rpc("verify_via_messenger", user_id, "max", messenger_uid)
    except Exception:
        import logging

        logging.getLogger(__name__).exception("verify_via_messenger failed for %s", user_id)


@login_required
def diagnose(request):
    if not request.user.is_staff:
        raise Http404()
    return render(request, "core/messenger_diagnose.html", {
        "secret_set": bool((getattr(settings, "MAX_WEBHOOK_SECRET", "") or "").strip()),
        "bot_set": bool((getattr(settings, "MAX_BOT_USERNAME", "") or "").strip()),
        "cache_backend": settings.CACHES["default"]["BACKEND"],
        "platforms": sorted(PLATFORMS),
    })
