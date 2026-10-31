"""Rate-limit для write-эндпоинтов (паритет Flask @rate_limit: Redis INCR+Lua).

Реализация на Django cache (Redis в проде): счётчик key на окно 60с.
Декоратор write-эндпоинтов — fail-open (сбой кэша не блокирует),
limit 10 запросов/мин на пользователя+эндпоинт (как во Flask по умолчанию).
enforce_ip_limit (login) — наоборот, fail-closed: непроверяемый лимит
не должен пропускать перебор паролей.
"""
import functools

from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import redirect


class RateLimitExceeded(Exception):
    """Лимит исчерпан; retry_after — через сколько секунд пробовать снова."""

    def __init__(self, retry_after: int = 0):
        self.retry_after = retry_after
        super().__init__("rate limit exceeded")


class RateLimitUnavailable(Exception):
    """Кэш недоступен — лимит проверить нельзя (fail-closed для login)."""


def enforce_ip_limit(request, bucket: str, limit: int, window: int) -> int:
    """Per-IP лимит на Django cache: count > limit → RateLimitExceeded.

    Ключ 'rl:ip:<bucket>:<ip>' (ip = REMOTE_ADDR). Любой сбой кэша —
    RateLimitUnavailable: без счётчика лимит не проверить, поэтому закрываем.
    """
    ip = request.META.get("REMOTE_ADDR", "unknown")
    key = "rl:ip:%s:%s" % (bucket, ip)
    try:
        if cache.add(key, 1, window):
            count = 1
        else:
            try:
                count = cache.incr(key)
            except ValueError:  # ключ истёк между add и incr — начинаем окно заново
                cache.set(key, 1, window)
                count = 1
    except Exception as exc:
        raise RateLimitUnavailable("rate limit cache unavailable") from exc
    if count > limit:
        raise RateLimitExceeded(retry_after=window)
    return count


def rate_limit_write(limit: int = 10, window: int = 60, redirect_to: str | None = None):
    def decorator(view):
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            user = getattr(request, "user", None)
            if user is None or not user.is_authenticated:
                return view(request, *args, **kwargs)
            key = "rl:%s:%s:%s" % (view.__name__, user.pk, request.path.split("/")[1])
            try:
                if cache.add(key, 1, window):
                    count = 1
                else:
                    try:
                        count = cache.incr(key)
                    except ValueError:
                        cache.set(key, 1, window)
                        count = 1
                if count > limit:
                    if redirect_to:
                        from django.contrib import messages

                        messages.warning(request, "Слишком часто. Попробуйте через минуту.")
                        return redirect(redirect_to)
                    return JsonResponse({"error": "rate_limited"}, status=429)
            except Exception:
                pass  # fail-open: кэш недоступен — не блокируем
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
