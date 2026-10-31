"""Rate-limit для write-эндпоинтов (паритет Flask @rate_limit: Redis INCR+Lua).

Реализация на Django cache (Redis в проде): счётчик key на окно 60с.
Fail-open по умолчанию (сбой кэша не блокирует), limit 10 запросов/мин
на пользователя+эндпоинт (как во Flask по умолчанию).
"""
import functools

from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import redirect


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
