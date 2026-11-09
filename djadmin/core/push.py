"""Web Push через pywebpush (паритет app/services/push_service.py).

VAPID-ключи из env; payload — JSON c title/body/tag/url.
"""
import ipaddress
import json
import logging
import re
import socket
import urllib.parse

from django.conf import settings

logger = logging.getLogger(__name__)

# endpoint/токены в тексте исключений не должны попадать в лог (152-ФЗ)
URL_RE = re.compile(r"https?://[^\s'\"]+")


def _redact_urls(text: str) -> str:
    return URL_RE.sub("<url>", text or "")


def vapid_claims() -> dict:
    return {"sub": "mailto:%s" % getattr(settings, "VAPID_CLAIMS_EMAIL", "notifications@trudnik.ru")}


def vapid_configured() -> bool:
    if not getattr(settings, "WEB_PUSH_ENABLED", False):
        return False
    return bool(getattr(settings, "VAPID_PRIVATE_KEY", "") and getattr(settings, "VAPID_PUBLIC_KEY", ""))


def _endpoint_host_global(endpoint: str) -> bool:
    """R080: host endpoint'а должен резолвиться ТОЛЬКО в публичные IP.

    Проверка при подписке не спасает от DNS-rebinding: домен может начать
    резолвиться во внутренний адрес уже после подписки. Резолвим перед
    каждой отправкой; любая приватная/loopback-адресация или сбой DNS —
    отказ (fail-closed).
    """
    try:
        parsed = urllib.parse.urlsplit(endpoint or "")
    except ValueError:
        return False
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError, UnicodeError):
        return False
    addresses = []
    for info in infos:
        sockaddr = info[4] if len(info) > 4 else None
        if sockaddr:
            addresses.append(sockaddr[0])
    if not addresses:
        return False
    for address in addresses:
        try:
            if not ipaddress.ip_address(address).is_global:
                return False
        except ValueError:
            return False
    return True


def send_web_push(subscription_info: dict, title: str, body: str, url: str = "/") -> dict:
    """Отправить push. Возвращает {'success': bool, 'error': str, 'gone': bool}.

    gone=True — подписка отозвана браузером (410), подлежит удалению.
    """
    if not getattr(settings, "WEB_PUSH_ENABLED", False):
        return {"success": False, "error": "push_disabled", "gone": False}
    if not vapid_configured():
        return {"success": False, "error": "vapid_not_configured", "gone": False}
    if not _endpoint_host_global(subscription_info.get("endpoint", "")):
        logger.warning("webpush blocked: endpoint host is not global (R080)")
        return {"success": False, "error": "endpoint_not_global", "gone": False}
    from pywebpush import WebPushException, WebPusher

    payload = json.dumps({"title": title, "body": body or "", "tag": "trudnik-notification", "url": url})
    try:
        pusher = WebPusher({
            "endpoint": subscription_info["endpoint"],
            "keys": {"p256dh": subscription_info["p256dh"], "auth": subscription_info["auth"]},
        })
        pusher.send(
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims=vapid_claims(),
        )
        return {"success": True, "error": "", "gone": False}
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        gone = status in (404, 410)
        logger.warning("webpush failed (status=%s): %s", status, _redact_urls(str(exc))[:120])
        return {"success": False, "error": str(exc)[:200], "gone": gone}
    except Exception as exc:
        logger.warning("webpush unexpected: %s", _redact_urls(str(exc))[:120])
        return {"success": False, "error": str(exc)[:200], "gone": False}
