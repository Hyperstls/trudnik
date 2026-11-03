"""MAX messenger verification: one-time deep link, webhook and bot replies.

Flow:
- `/messenger/start/max` creates a one-time token and MAX deep link;
- MAX sends `bot_started`/`message_created` to `/messenger/webhook/max`;
- the token is consumed and `verify_via_messenger` marks the profile;
- the bot replies in the chat (success/expired/instruction), so a user always
  sees a reaction instead of silence.

Webhook is fail-closed via `X-Max-Bot-Api-Secret`. Subscription is self-healed
by the Celery task (`ensure_max_webhook`, every 10 min) and on the start page.
"""
import hmac
import logging
import os
import secrets as pysecrets

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .rpc import call_rpc

logger = logging.getLogger(__name__)
TOKEN_TTL = 600  # 10 минут
PLATFORMS = {"max"}
BOT_LINK = {"max": "https://max.ru/{bot}?start={token}"}
NEEDED_UPDATE_TYPES = ("bot_started", "message_created")

INSTRUCTION_TEXT = (
    "Это бот подтверждения профиля платформы «Трудник».\n\n"
    "Чтобы подтвердить профиль:\n"
    "1. Откройте «Трудник» → Профиль.\n"
    "2. Нажмите «Подтвердить через MAX» и перейдите по ссылке.\n"
    "3. Подтверждение произойдёт автоматически — здесь появится сообщение.\n\n"
    "Вводить команды вручную не нужно."
)


def _cache():
    from django.core.cache import cache

    return cache


def _max_token() -> str:
    return (getattr(settings, "MAX_BOT_TOKEN", "") or "").strip()


def _max_verify():
    """Use the Russian Trusted Root CA bundle when present; else system CAs."""
    bundle = (getattr(settings, "MAX_CA_BUNDLE", "") or "").strip()
    if bundle and os.path.isfile(bundle):
        return bundle
    return True


def _max_headers() -> dict:
    return {
        "Authorization": _max_token(),
        "Content-Type": "application/json",
    }


def _api_timeout():
    return getattr(settings, "MESSENGER_API_TIMEOUT", 10)


def _send_max(chat_id, text: str, button: dict | None = None) -> bool:
    token = _max_token()
    if not token or not chat_id:
        return False
    payload = {"chat_id": chat_id, "text": text}
    if button:
        payload["attachments"] = [button]
    try:
        response = requests.post(
            "%s/messages" % settings.MAX_API_URL,
            json=payload,
            headers=_max_headers(),
            timeout=_api_timeout(),
            verify=_max_verify(),
        )
        if response.status_code >= 300:
            logger.warning(
                "MAX send chat=%s failed: HTTP %s", chat_id, response.status_code,
            )
            return False
        return True
    except Exception:
        logger.warning("MAX send chat=%s failed", chat_id, exc_info=True)
        return False


def _link_button(text: str, url: str) -> dict:
    return {
        "type": "inline_keyboard",
        "payload": {"buttons": [[{"type": "link", "text": text, "url": url}]]},
    }


def _profile_url() -> str:
    return settings.SITE_URL.rstrip("/") + "/profile"


def _webhook_url() -> str:
    base = settings.WORKER_SITE_URL or settings.SITE_URL
    return base.rstrip("/") + "/messenger/webhook/max"


def _send_instruction(chat_id) -> None:
    _send_max(chat_id, INSTRUCTION_TEXT, _link_button("Открыть профиль", _profile_url()))


def _ensure_webhook_best_effort() -> None:
    """Register the webhook once per 10 min; never break the page."""
    if not _max_token():
        return
    try:
        if not _cache().add("max_webhook:ensure", 1, 600):
            return
        ensure_max_webhook()
    except Exception:
        logger.warning("MAX webhook ensure failed", exc_info=True)


@login_required
def start(request, platform: str):
    if platform not in PLATFORMS:
        raise Http404("Неизвестная платформа")
    bot = (getattr(settings, "MAX_BOT_USERNAME", "") or "").strip()
    if not bot:
        messages.error(request, _("Верификация через мессенджер не настроена (обратитесь к администратору)."))
        return render(request, "core/messenger_start.html", {"link": None, "platform": platform})
    _ensure_webhook_best_effort()
    token = pysecrets.token_urlsafe(24)
    _cache().set("msg_verify:%s" % token, str(request.user.pk), TOKEN_TTL)
    link = BOT_LINK[platform].format(bot=bot, token=token)
    return render(request, "core/messenger_start.html",
                  {"link": link, "platform": platform, "ttl_minutes": TOKEN_TTL // 60})


@csrf_exempt  # external MAX webhook; protected by the shared secret header
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
    if update_type == "bot_started":
        token = str(data.get("payload") or "").strip()
        uid = str((data.get("user") or {}).get("user_id") or "")
        if token and uid:
            _complete(token, uid, chat_id)
        elif chat_id:
            _send_instruction(chat_id)
    elif update_type == "message_created":
        message = data.get("message") or {}
        body = message.get("body") or {}
        text = str(body.get("text") or message.get("text") or "").strip()
        uid = str((message.get("sender") or {}).get("user_id") or "")
        token = _extract_token(text)
        if token and uid:
            _complete(token, uid, chat_id)
        elif chat_id:
            # /start, «start», кнопка или любой текст — всегда отвечаем инструкцией.
            _send_instruction(chat_id)
    return JsonResponse({"ok": True})


def _json_body(request) -> dict:
    try:
        import json

        return json.loads(request.body.decode("utf-8", "replace") or "{}")
    except Exception:
        return {}


def _extract_token(text: str) -> str:
    if not text:
        return ""
    parts = text.split()
    if parts and parts[0].lower().startswith(("/start", "start")):
        parts = parts[1:]
    return parts[0] if parts else ""


def _complete(token: str, messenger_uid: str, chat_id=None) -> None:
    cache = _cache()
    key = "msg_verify:%s" % token
    user_id = cache.get(key)
    if not user_id:
        if chat_id:
            _send_max(
                chat_id,
                "Ссылка устарела или уже использована. Откройте «Трудник» → "
                "Профиль → «Подтвердить через MAX» и получите новую ссылку.",
                _link_button("Открыть профиль", _profile_url()),
            )
        return
    cache.delete(key)
    try:
        call_rpc("verify_via_messenger", user_id, "max", messenger_uid)
    except Exception:
        logger.exception("verify_via_messenger failed for %s", user_id)
        if chat_id:
            _send_max(
                chat_id,
                "Не удалось подтвердить профиль (ошибка сервера). "
                "Попробуйте позже или напишите в поддержку.",
            )
        return
    if chat_id:
        _send_max(
            chat_id,
            "Ваш профиль на «Трудник» подтверждён. "
            "Теперь доступен значок «Проверенный».",
            _link_button("Вернуться в профиль", _profile_url()),
        )


def get_max_subscriptions() -> list:
    token = _max_token()
    if not token:
        return []
    try:
        response = requests.get(
            "%s/subscriptions" % settings.MAX_API_URL,
            headers=_max_headers(),
            timeout=_api_timeout(),
            verify=_max_verify(),
        )
        if response.ok:
            data = response.json()
            return data if isinstance(data, list) else data.get("subscriptions", [])
    except Exception:
        logger.warning("MAX GET subscriptions failed", exc_info=True)
    return []


def _find_subscription(subscriptions, url: str):
    wanted = url.rstrip("/")
    for sub in subscriptions:
        if isinstance(sub, dict) and (sub.get("url") or "").rstrip("/") == wanted:
            return sub
    return None


def _register_subscription(url: str) -> tuple[bool, str]:
    payload = {"url": url, "update_types": list(NEEDED_UPDATE_TYPES)}
    secret = (getattr(settings, "MAX_WEBHOOK_SECRET", "") or "").strip()
    if secret:
        payload["secret"] = secret
    try:
        response = requests.post(
            "%s/subscriptions" % settings.MAX_API_URL,
            json=payload,
            headers=_max_headers(),
            timeout=_api_timeout(),
            verify=_max_verify(),
        )
        if response.status_code < 300:
            return True, ""
        return False, "HTTP %s" % response.status_code
    except Exception as exc:
        return False, str(exc)[:200]


def ensure_max_webhook() -> dict:
    """Idempotently ensure our URL is subscribed to both update types."""
    url = _webhook_url()
    result = {"ok": False, "url": url, "action": "", "error": ""}
    if not _max_token():
        result["error"] = "MAX_BOT_TOKEN not set"
        return result
    try:
        existing = _find_subscription(get_max_subscriptions(), url)
        if existing is not None:
            have = set(existing.get("update_types") or [])
            if set(NEEDED_UPDATE_TYPES) <= have:
                result.update(ok=True, action="already_registered")
                return result
            try:
                requests.delete(
                    "%s/subscriptions" % settings.MAX_API_URL,
                    params={"url": url},
                    headers=_max_headers(),
                    timeout=_api_timeout(),
                    verify=_max_verify(),
                )
            except Exception:
                logger.warning("MAX subscription delete failed", exc_info=True)
        ok, error = _register_subscription(url)
        if ok:
            result.update(ok=True, action="registered" if existing is None else "updated")
            logger.info("MAX webhook %s: %s", result["action"], url)
        else:
            result["error"] = error
            logger.warning("MAX subscription failed: %s", error)
    except Exception as exc:
        result["error"] = str(exc)[:200]
        logger.warning("MAX ensure webhook failed", exc_info=True)
    return result


@login_required
def diagnose(request):
    if not request.user.is_staff:
        raise Http404()
    webhook = ensure_max_webhook() if _max_token() else {
        "ok": False, "url": _webhook_url(), "action": "", "error": "MAX_BOT_TOKEN not set",
    }
    return render(request, "core/messenger_diagnose.html", {
        "secret_set": bool((getattr(settings, "MAX_WEBHOOK_SECRET", "") or "").strip()),
        "bot_set": bool((getattr(settings, "MAX_BOT_USERNAME", "") or "").strip()),
        "token_set": bool(_max_token()),
        "api_url": settings.MAX_API_URL,
        "webhook": webhook,
        "cache_backend": settings.CACHES["default"]["BACKEND"],
        "platforms": sorted(PLATFORMS),
    })
