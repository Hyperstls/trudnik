"""Управление пользовательскими сессиями (R006).

Метаданные хранятся прямо в django-сессии: ``ua``, ``login_at``, ``last_seen``.
Наружу (в шаблоны/UI) отдаётся только публичный HMAC-идентификатор:
raw ``session_key`` не покидает backend и не пишется в логи.
"""
import hashlib
import hmac
import logging

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

SEEN_CACHE_PREFIX = "sess_seen:"
SEEN_THROTTLE_SECONDS = 300
UA_MAX_LENGTH = 300


def session_public_id(session_key):
    """Стабильный публичный идентификатор сессии: HMAC-SHA256, hex[:16]."""
    digest = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        str(session_key).encode("utf-8"),
        hashlib.sha256,
    )
    return digest.hexdigest()[:16]


def describe_user_agent(ua):
    """Читаемое описание устройства: браузер и ОС из User-Agent."""
    value = str(ua or "").lower()

    browser = ""
    if "yabrowser" in value:
        browser = "Yandex Browser"
    elif "edg" in value or "edge" in value:
        browser = "Edge"
    elif "opr/" in value or "opera" in value:
        browser = "Opera"
    elif "firefox" in value or "fxios" in value:
        browser = "Firefox"
    elif "chrome" in value or "crios" in value:
        browser = "Chrome"
    elif "safari" in value:
        browser = "Safari"

    platform = ""
    if "windows" in value:
        platform = "Windows"
    elif "android" in value:
        platform = "Android"
    elif "iphone" in value or "ipad" in value or "ipod" in value:
        platform = "iOS"
    elif "mac os x" in value or "macintosh" in value:
        platform = "macOS"
    elif "linux" in value:
        platform = "Linux"

    parts = [part for part in (browser, platform) if part]
    if not parts:
        return _("Неизвестное устройство")
    return ", ".join(parts)


def _seen_cache_key(session_key):
    return "%s%s" % (SEEN_CACHE_PREFIX, session_key)


def _touch_allowed(session_key):
    """Троттлинг обновлений last_seen: не чаще раза в 300 секунд."""
    try:
        return bool(cache.add(_seen_cache_key(session_key), 1, SEEN_THROTTLE_SECONDS))
    except Exception:
        # Метаданные не критичны для доступа: сбой кэша не должен ломать запрос.
        logger.warning("session metadata: cache unavailable", exc_info=True)
        return False


def set_session_meta(request):
    """Записывает ua/login_at/last_seen для аутентифицированной сессии."""
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return

    session = getattr(request, "session", None)
    if session is None:
        return
    session_key = getattr(session, "session_key", None)

    # JSON-сериализатор сессий Django не умеет datetime — храним ISO-строки.
    now = timezone.now().isoformat()
    if not session.get("login_at"):
        meta = getattr(request, "META", None) or {}
        ua = str(meta.get("HTTP_USER_AGENT", "") or "")
        session["ua"] = ua[:UA_MAX_LENGTH]
        session["login_at"] = now
        session["last_seen"] = now
        if session_key:
            # Открываем 300-секундное окно и для первой записи.
            _touch_allowed(session_key)
        return

    if session_key and _touch_allowed(session_key):
        session["last_seen"] = now


def iter_user_sessions(user):
    """Сессии пользователя по ``_auth_user_id`` без raw session_key."""
    if user is None or not getattr(user, "is_authenticated", False):
        return []

    user_id = str(user.pk)
    result = []
    for session in Session.objects.filter(expire_date__gt=timezone.now()):
        try:
            data = session.get_decoded()
        except Exception:
            continue  # битые/поддельные session_data не должны ронять список
        if not isinstance(data, dict):
            continue
        if str(data.get("_auth_user_id", "")) != user_id:
            continue

        ua = data.get("ua") or ""
        if not isinstance(ua, str):
            ua = str(ua)
        result.append({
            "public_id": session_public_id(session.session_key),
            "ua": ua,
            "description": describe_user_agent(ua),
            "login_at": data.get("login_at"),
            "last_seen": data.get("last_seen"),
            "expire_date": session.expire_date,
        })
    return result


def revoke_user_session(user, public_id):
    """Удаляет сессию пользователя по публичному id.

    Возвращает public_id удалённой сессии; чужая или неизвестная — None.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    if not isinstance(public_id, str) or not public_id:
        return None

    user_id = str(user.pk)
    for session in Session.objects.all():
        try:
            matches = hmac.compare_digest(
                session_public_id(session.session_key), public_id
            )
        except (TypeError, ValueError):
            return None
        if not matches:
            continue
        try:
            data = session.get_decoded()
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if str(data.get("_auth_user_id", "")) != user_id:
            continue
        session.delete()
        return public_id
    return None
