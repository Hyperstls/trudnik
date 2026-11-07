"""Мидлвари Django-компаньона."""
import logging
import os
import secrets
import traceback

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden

logger = logging.getLogger(__name__)


def _public_csp(nonce: str, secure: bool = False) -> str:
    policy = (
        "default-src 'self'; "
        "script-src 'self' 'nonce-%s' 'strict-dynamic' "
        "https://api-maps.yandex.ru https://yastatic.net "
        "https://smartcaptcha.yandexcloud.net; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: https:; "
        "font-src 'self' data:; "
        "connect-src 'self' https://*.yandex.ru https://*.maps.yandex.net "
        "https://geocode-maps.yandex.ru https://suggest-maps.yandex.ru "
        "https://api-maps.yandex.ru https://yastatic.net wss:; "
        "frame-src https://smartcaptcha.yandexcloud.net https://*.yandex.ru; "
        "media-src 'self' https:; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'; manifest-src 'self'; "
        "worker-src 'self' blob:"
    ) % nonce
    if secure and not settings.DEBUG:
        policy += "; upgrade-insecure-requests"
    return policy


def _admin_csp() -> str:
    # Django admin uses inline JSON constants and inline handlers; it is staff-only.
    return (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: https:; font-src 'self' data:; "
        "connect-src 'self' wss:; frame-src 'self' https:; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; "
        "frame-ancestors 'none'"
    )


class CspMiddleware:
    """Per-request CSP nonce + security headers (public pages and admin)."""

    PERMISSIONS = (
        "camera=(), microphone=(), geolocation=(self), payment=(), usb=(), "
        "interest-cohort=()"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        nonce = secrets.token_urlsafe(16)
        request.csp_nonce = nonce
        response = self.get_response(request)
        if not response.has_header("Content-Security-Policy"):
            is_admin = request.path == "/admin" or request.path.startswith("/admin/")
            response["Content-Security-Policy"] = (
                _admin_csp() if is_admin else _public_csp(nonce, request.is_secure())
            )
        if not response.has_header("Permissions-Policy"):
            response["Permissions-Policy"] = self.PERMISSIONS
        return response


class CsrfHeaderAliasMiddleware:
    """Accept the legacy X-CSRF-Token header used by existing JS modules.

    Django checks HTTP_X_CSRFTOKEN (``X-CSRFToken``). The Flask-era client
    sends ``X-CSRF-Token``; without this alias every fetch-based mutation
    (push, favorites, invites) was rejected with 403. The cookie/token value
    is still validated by CsrfViewMiddleware, so security is unchanged.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if "HTTP_X_CSRFTOKEN" not in request.META:
            legacy = request.META.get("HTTP_X_CSRF_TOKEN")
            if legacy:
                request.META["HTTP_X_CSRFTOKEN"] = legacy
        return self.get_response(request)


class CanonicalHostMiddleware:
    """Все публичные запросы — на каноническом домене (трудник.рф)."""

    LOCAL_HOSTS = {"localhost", "127.0.0.1", "testserver", "[::1]"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.DEBUG:
            return self.get_response(request)
        canonical = getattr(settings, "CANONICAL_HOST", "").strip().lower()
        if not canonical:
            return self.get_response(request)
        host = request.get_host().split(":")[0].strip().lower()
        if host == canonical or host in self.LOCAL_HOSTS:
            return self.get_response(request)
        if request.path.startswith("/health"):
            return self.get_response(request)
        target = "https://%s%s" % (canonical, request.get_full_path())
        if request.method in ("GET", "HEAD"):
            response = HttpResponse(status=301)
        else:
            response = HttpResponse(status=308)
        response["Location"] = target
        return response


def client_ip(request) -> str:
    """IP клиента: ПОСЛЕДНИЙ hop X-Forwarded-For.

    При одном доверенном прокси (Amvera) платформа дописывает реальный IP клиента
    в конец заголовка; первый элемент контролирует клиент (спуфинг). Без прокси
    заголовка нет вовсе — используется REMOTE_ADDR.
    """
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "")


class AdminIpAllowlistMiddleware:
    """Опциональный IP-allowlist на /admin/ (аналог ADMIN_API_ALLOWED_IPS Flask).

    Включается переменной DJANGO_ADMIN_ALLOWED_IPS (CSV). Пусто — ограничений нет.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        allowed = settings.DJANGO_ADMIN_ALLOWED_IPS
        path = request.path
        if allowed and (path == "/admin" or path.startswith("/admin/")):
            if client_ip(request) not in allowed:
                return HttpResponseForbidden("Доступ к админке с этого IP запрещён.")
        return self.get_response(request)

class GlobalIpRateLimitMiddleware:
    """Глобальный лимит запросов (паритет Flask _global_ip_rate_limit).

    Анонимы: 120 req/min на IP (GLOBAL_RATE_LIMIT_PER_MIN), ключ по IP.
    Авторизованные: AUTH_RATE_LIMIT_PER_MIN (600) на пользователя, ключ по
    user_id — пользователи за общим NAT не блокируют друг друга.
    Fail-open: сбой кэша не блокирует трафик. Исключения: /health, /ready,
    /static/, /uploads/, /favicon.ico, /sw.js, /metrics — healthcheck и
    статика не должны лимитироваться.
    """

    EXEMPT_PREFIXES = ("/health", "/ready", "/static/", "/uploads/",
                       "/favicon.ico", "/sw.js", "/metrics")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings
        from django.core.cache import cache
        from django.http import HttpResponse

        path = request.path
        if any(path.startswith(prefix) for prefix in self.EXEMPT_PREFIXES):
            return self.get_response(request)
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            limit = getattr(settings, "AUTH_RATE_LIMIT_PER_MIN", 600)
            scope = "user:%s" % user.pk
        else:
            limit = getattr(settings, "GLOBAL_RATE_LIMIT_PER_MIN", 120)
            scope = client_ip(request)
        try:
            import time

            window = int(time.time() // 60)
            key = "iprl:%s:%s" % (scope, window)
            if cache.add(key, 1, 70):
                count = 1
            else:
                count = cache.incr(key)
            if count > limit:
                response = HttpResponse("Too Many Requests", status=429,
                                        content_type="text/plain; charset=utf-8")
                response["Retry-After"] = "60"
                return response
        except Exception:
            pass  # fail-open
        return self.get_response(request)


class AttributionMiddleware:
    """Запоминает first-touch UTM-метки в сессии (J157).

    Ставится сразу после SessionMiddleware. Метки попадают в
    ``profiles.acquisition`` при регистрации; повторные заходы их не
    перезаписывают.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from core.growth import capture_first_touch

        if not request.session.get("attribution"):
            attribution = capture_first_touch(request)
            if attribution:
                request.session["attribution"] = attribution
        return self.get_response(request)


class ActivityMiddleware:
    """Пишет одну строку активности пользователя в день (J157).

    Ставится после AuthenticationMiddleware. Дедупликация — в кэше, поэтому
    БД трогается не чаще одного раза на пользователя в сутки.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            from core.growth import record_activity

            record_activity(user.pk)
        return response


class SessionMetaMiddleware:
    """Метаданные сессии (UA, login_at, last_seen) — R006.

    Ставится после ActivityMiddleware. Ошибки метаданных только логируются:
    доступ уже определён AuthenticationMiddleware и от них не зависит.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            from core.sessions import set_session_meta

            set_session_meta(request)
        except Exception:
            logger.exception("Не удалось обновить метаданные сессии")
        return response


class ErrorEventMiddleware:
    """Внутренний error tracking необработанных 500 (R039, 152-ФЗ-safe).

    Сохраняет только тип исключения, путь без query string, метод, user_id и
    file:line-фреймы. Текст ошибки, тело запроса, заголовки, query string и
    email в БД не попадают. Штатные Http404/PermissionDenied/ValidationError
    не являются 500 и не пишутся. Сбой записи только логируется: обработка
    ошибки запроса не ломается.

    Ставится после AuthenticationMiddleware, чтобы request.user был доступен.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        from django.core.exceptions import PermissionDenied, ValidationError
        from django.http import Http404

        if isinstance(exception, (Http404, PermissionDenied, ValidationError)):
            return None
        try:
            from core.models import ErrorEvent

            frames = [
                {
                    "file": os.path.basename(frame.filename)[:120],
                    "line": frame.lineno,
                    "func": (frame.name or "")[:100],
                }
                for frame in traceback.extract_tb(exception.__traceback__)[-20:]
            ]
            user = getattr(request, "user", None)
            user_id = user.pk if user is not None and user.is_authenticated else None
            ErrorEvent.objects.create(
                exception_type=type(exception).__name__[:200],
                path=request.path[:500],
                method=request.method[:10],
                status_code=500,
                user_id=user_id,
                frames=frames,
            )
        except Exception:
            logger.exception("Не удалось сохранить ErrorEvent")
        return None
