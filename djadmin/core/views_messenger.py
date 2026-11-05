"""MAX messenger verification: one-time deep link, webhook and bot replies.

Flow:
- `/messenger/start/max` creates a one-time token and MAX deep link;
- MAX sends `bot_started`/`message_created` to `/messenger/webhook/max`;
- the bot answers with the inline button «Подтвердить профиль» (callback
  `confirm:<token>`) — clicking it (`message_callback`) consumes the token and
  `verify_via_messenger` marks the profile, the answer replaces the message;
- so a user always sees a reaction instead of silence.

Webhook is fail-closed via `X-Max-Bot-Api-Secret`. Subscription is self-healed
by the Celery task (`ensure_max_webhook`, every 10 min) and on the start page:
a signature (url + update types + secret) in cache makes it re-register when
the secret or the needed update types change.
"""
import hashlib
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
MAX_WEBHOOK_BYTES = 64 * 1024
NEEDED_UPDATE_TYPES = ("bot_started", "message_created", "message_callback")
WEBHOOK_PATH_SUFFIX = "/messenger/webhook/max"
SIGNATURE_CACHE_KEY = "max_webhook:sig"

CONFIRM_TEXT = "Подтвердите профиль «Трудник»."
SUCCESS_TEXT = (
    "Профиль подтверждён. Теперь доступен значок «Проверенный»."
)
EXPIRED_TEXT = (
    "Ссылка устарела или уже использована. Откройте «Трудник» → "
    "Профиль → «Подтвердить через MAX» и получите новую ссылку."
)
ERROR_TEXT = (
    "Не удалось подтвердить профиль (ошибка сервера). "
    "Попробуйте позже или напишите в поддержку."
)
STALE_BUTTON_TEXT = "Кнопка устарела — получите новую ссылку в профиле."

INSTRUCTION_TEXT = (
    "Это бот подтверждения профиля платформы «Трудник».\n\n"
    "Чтобы подтвердить профиль:\n"
    "1. Откройте «Трудник» → Профиль.\n"
    "2. Нажмите «Подтвердить через MAX» и перейдите по ссылке.\n"
    "3. В чате нажмите кнопку «Подтвердить профиль» — здесь появится результат.\n\n"
    "Вводить команды вручную не нужно."
)


def _cache():
    from django.core.cache import cache

    return cache


def _max_token() -> str:
    return (getattr(settings, "MAX_BOT_TOKEN", "") or "").strip()


def _webhook_secret() -> str:
    return (getattr(settings, "MAX_WEBHOOK_SECRET", "") or "").strip()


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
    payload = {"text": text}
    if button:
        payload["attachments"] = [button]
    try:
        response = requests.post(
            "%s/messages" % settings.MAX_API_URL,
            params={"chat_id": chat_id},
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


def _answer_callback(callback_id, text: str, button: dict | None = None) -> bool:
    """Replace the message that carried the pressed button with a plain answer."""
    if not callback_id:
        return False
    payload = {
        "message": {
            "text": text,
            "attachments": [button] if button else [],
            "notify": True,
        }
    }
    try:
        response = requests.post(
            "%s/answers" % settings.MAX_API_URL,
            params={"callback_id": callback_id},
            json=payload,
            headers=_max_headers(),
            timeout=_api_timeout(),
            verify=_max_verify(),
        )
        if response.status_code >= 300:
            logger.warning("MAX callback answer failed: HTTP %s", response.status_code)
            return False
        return True
    except Exception:
        logger.warning("MAX callback answer failed", exc_info=True)
        return False


def _inline_keyboard(rows: list) -> dict:
    return {"type": "inline_keyboard", "payload": {"buttons": rows}}


def _link_button(text: str, url: str) -> dict:
    return _inline_keyboard([[{"type": "link", "text": text, "url": url}]])


def _confirm_attachment(token: str) -> dict:
    return _inline_keyboard([
        [{"type": "callback", "text": "Подтвердить профиль", "payload": "confirm:%s" % token}],
        [{"type": "link", "text": "Открыть профиль", "url": _profile_url()}],
    ])


def _profile_url() -> str:
    return settings.SITE_URL.rstrip("/") + "/profile"


def _webhook_url() -> str:
    base = settings.WORKER_SITE_URL or settings.SITE_URL
    return base.rstrip("/") + WEBHOOK_PATH_SUFFIX


def _send_instruction(chat_id) -> None:
    _send_max(chat_id, INSTRUCTION_TEXT, _link_button("Открыть профиль", _profile_url()))


def _send_confirm(chat_id, token: str) -> bool:
    return _send_max(chat_id, CONFIRM_TEXT, _confirm_attachment(token))


def _token_valid(token: str) -> bool:
    try:
        return bool(_cache().get("msg_verify:%s" % token))
    except Exception:
        logger.warning("MAX token cache read failed", exc_info=True)
        return False


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
    expected = _webhook_secret()
    if not expected:
        return JsonResponse({"ok": False, "error": "webhook not configured"}, status=503)
    provided = request.headers.get("X-Max-Bot-Api-Secret", "")
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        return JsonResponse({"ok": False, "error": "unauthorized"}, status=401)

    data = _json_body(request)
    update_type = data.get("update_type", "")
    handler = {
        "bot_started": _handle_bot_started,
        "message_created": _handle_message_created,
        "message_callback": _handle_message_callback,
    }.get(update_type)
    if handler is not None:
        try:
            handler(data)
        except Exception:
            # MAX retries non-2xx; a handler bug must not loop the update forever.
            logger.warning("MAX webhook handler failed: %s", update_type, exc_info=True)
    return JsonResponse({"ok": True})


def _handle_bot_started(data: dict) -> None:
    chat_id = data.get("chat_id")
    token = str(data.get("payload") or "").strip()
    uid = str((data.get("user") or {}).get("user_id") or "")
    if token and uid and chat_id and _token_valid(token):
        _send_confirm(chat_id, token)
    elif chat_id:
        _send_instruction(chat_id)


def _handle_message_created(data: dict) -> None:
    message = data.get("message") or {}
    recipient = message.get("recipient") or {}
    chat_id = recipient.get("chat_id")
    uid = str((message.get("sender") or {}).get("user_id") or "")
    body = message.get("body") or {}
    text = str(body.get("text") or message.get("text") or "").strip()
    token = _extract_token(text)
    if token and uid and chat_id and _token_valid(token):
        _send_confirm(chat_id, token)
    elif chat_id:
        # /start, «start», кнопка или любой текст — всегда отвечаем инструкцией.
        _send_instruction(chat_id)


def _handle_message_callback(data: dict) -> None:
    callback = data.get("callback") or {}
    callback_id = callback.get("callback_id")
    payload = str(callback.get("payload") or "")
    uid = str((callback.get("user") or {}).get("user_id") or "")
    message = callback.get("message") or {}
    chat_id = (message.get("recipient") or {}).get("chat_id")
    token = payload[len("confirm:"):].strip() if payload.startswith("confirm:") else ""
    if token and uid:
        _complete(token, uid, chat_id, callback_id)
    else:
        _answer_callback(
            callback_id,
            STALE_BUTTON_TEXT,
            _link_button("Открыть профиль", _profile_url()),
        )


def _json_body(request) -> dict:
    try:
        import json

        try:
            content_length = int(request.META.get("CONTENT_LENGTH") or 0)
        except (TypeError, ValueError):
            content_length = 0
        if content_length > MAX_WEBHOOK_BYTES:
            return {}
        raw = request.body
        if len(raw) > MAX_WEBHOOK_BYTES:
            return {}
        return json.loads(raw.decode("utf-8", "replace") or "{}")
    except Exception:
        return {}


def _extract_token(text: str) -> str:
    if not text:
        return ""
    parts = text.split()
    if parts and parts[0].lower().startswith(("/start", "start")):
        parts = parts[1:]
    return parts[0] if parts else ""


def _reply(chat_id, callback_id, text: str, button: dict | None = None) -> None:
    if callback_id and _answer_callback(callback_id, text, button):
        return
    if chat_id:
        _send_max(chat_id, text, button)


def _complete(token: str, messenger_uid: str, chat_id=None, callback_id=None) -> str:
    """Consume the one-time token and answer in the chat/callback.

    Returns "ok", "expired" or "error".
    """
    cache = _cache()
    key = "msg_verify:%s" % token
    user_id = cache.get(key)
    if not user_id or not cache.delete(key):
        _reply(
            chat_id, callback_id, EXPIRED_TEXT,
            _link_button("Открыть профиль", _profile_url()),
        )
        return "expired"
    try:
        call_rpc("verify_via_messenger", user_id, "max", messenger_uid)
    except Exception:
        logger.exception("verify_via_messenger failed for %s", user_id)
        try:
            cache.set(key, user_id, TOKEN_TTL)  # временный сбой — даём повторить
        except Exception:
            logger.warning("MAX token restore failed", exc_info=True)
        _reply(chat_id, callback_id, ERROR_TEXT)
        return "error"
    _reply(
        chat_id, callback_id, SUCCESS_TEXT,
        _link_button("Вернуться в профиль", _profile_url()),
    )
    return "ok"


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


def _delete_subscription(url: str) -> bool:
    try:
        response = requests.delete(
            "%s/subscriptions" % settings.MAX_API_URL,
            params={"url": url},
            headers=_max_headers(),
            timeout=_api_timeout(),
            verify=_max_verify(),
        )
        if response.status_code >= 300:
            logger.warning("MAX subscription delete failed: HTTP %s", response.status_code)
            return False
        return True
    except Exception:
        logger.warning("MAX subscription delete failed", exc_info=True)
        return False


def _register_subscription(url: str) -> tuple[bool, str]:
    payload = {"url": url, "update_types": list(NEEDED_UPDATE_TYPES)}
    secret = _webhook_secret()
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


def _subscription_signature(url: str, secret: str) -> str:
    material = "|".join([url.rstrip("/"), ",".join(NEEDED_UPDATE_TYPES), secret])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _cached_signature():
    try:
        return _cache().get(SIGNATURE_CACHE_KEY)
    except Exception:
        logger.warning("MAX webhook signature cache read failed", exc_info=True)
        return None


def _remember_signature(signature: str) -> None:
    try:
        _cache().set(SIGNATURE_CACHE_KEY, signature, None)
    except Exception:
        logger.warning("MAX webhook signature cache write failed", exc_info=True)


def ensure_max_webhook() -> dict:
    """Idempotently keep exactly one subscription to our URL with every type."""
    url = _webhook_url()
    result = {"ok": False, "url": url, "action": "", "error": ""}
    if not _max_token():
        result["error"] = "MAX_BOT_TOKEN not set"
        return result
    signature = _subscription_signature(url, _webhook_secret())
    try:
        subscriptions = get_max_subscriptions()
        existing = _find_subscription(subscriptions, url)
        if (
            existing is not None
            and set(NEEDED_UPDATE_TYPES) <= set(existing.get("update_types") or [])
            and _cached_signature() == signature
        ):
            result.update(ok=True, action="already_registered")
            return result

        current = url.rstrip("/")
        for sub in subscriptions:
            if not isinstance(sub, dict):
                continue
            sub_url = (sub.get("url") or "").rstrip("/")
            if not sub_url.endswith(WEBHOOK_PATH_SUFFIX) or sub_url == current:
                continue
            _delete_subscription(sub.get("url"))
        if existing is not None:
            _delete_subscription(url)

        ok, error = _register_subscription(url)
        if ok:
            _remember_signature(signature)
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
        "secret_set": bool(_webhook_secret()),
        "bot_set": bool((getattr(settings, "MAX_BOT_USERNAME", "") or "").strip()),
        "token_set": bool(_max_token()),
        "api_url": settings.MAX_API_URL,
        "webhook": webhook,
        "cache_backend": settings.CACHES["default"]["BACKEND"],
        "platforms": sorted(PLATFORMS),
    })
