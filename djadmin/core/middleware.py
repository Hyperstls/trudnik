"""Мидлвари Django-компаньона."""
from django.conf import settings
from django.http import HttpResponseForbidden


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
    """Глобальный лимит запросов с IP (паритет Flask _global_ip_rate_limit).

    120 req/min на IP (GLOBAL_RATE_LIMIT_PER_MIN). Fail-open: сбой кэша не
    блокирует трафик. Исключения: /health, /ready, /static/, /uploads/,
    /favicon.ico, /sw.js — healthcheck и статика не должны лимитироваться.
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
        limit = getattr(settings, "GLOBAL_RATE_LIMIT_PER_MIN", 120)
        ip = client_ip(request)
        try:
            import time

            window = int(time.time() // 60)
            key = "iprl:%s:%s" % (ip, window)
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
