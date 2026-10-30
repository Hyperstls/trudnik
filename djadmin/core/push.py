"""Web Push через pywebpush (паритет app/services/push_service.py).

VAPID-ключи из env; payload — JSON c title/body/tag/url.
"""
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def vapid_claims() -> dict:
    return {"sub": "mailto:%s" % getattr(settings, "VAPID_CLAIMS_EMAIL", "notifications@trudnik.ru")}


def vapid_configured() -> bool:
    return bool(getattr(settings, "VAPID_PRIVATE_KEY", "") and getattr(settings, "VAPID_PUBLIC_KEY", ""))


def send_web_push(subscription_info: dict, title: str, body: str, url: str = "/") -> dict:
    """Отправить push. Возвращает {'success': bool, 'error': str, 'gone': bool}.

    gone=True — подписка отозвана браузером (410), подлежит удалению.
    """
    if not vapid_configured():
        return {"success": False, "error": "vapid_not_configured", "gone": False}
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
        logger.warning("webpush failed (status=%s): %s", status, str(exc)[:120])
        return {"success": False, "error": str(exc)[:200], "gone": gone}
    except Exception as exc:
        logger.warning("webpush unexpected: %s", str(exc)[:120])
        return {"success": False, "error": str(exc)[:200], "gone": False}
