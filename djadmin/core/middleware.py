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
