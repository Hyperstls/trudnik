"""Мидлвари Django-компаньона."""
from django.conf import settings
from django.http import HttpResponseForbidden


class AdminIpAllowlistMiddleware:
    """Опциональный IP-allowlist на /admin/ (аналог ADMIN_API_ALLOWED_IPS Flask).

    Включается переменной DJANGO_ADMIN_ALLOWED_IPS (CSV). Пусто — ограничений нет.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        allowed = settings.DJANGO_ADMIN_ALLOWED_IPS
        if allowed and request.path.startswith("/admin"):
            xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
            ip = xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")
            if ip not in allowed:
                return HttpResponseForbidden("Доступ к админке с этого IP запрещён.")
        return self.get_response(request)
