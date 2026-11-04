"""Единые безопасные хелперы для next/Referer-редиректов.

Инвариант: разрешён только same-origin URL. Для secure-запроса
(require_https=request.is_secure()) дополнительно отсекается понижение
до http. Пустой/внешний/небезопасный URL заменяется fallback.
"""
from django.utils.http import url_has_allowed_host_and_scheme


def safe_next(request, fallback: str) -> str:
    """next из POST (приоритет) или GET, если он same-origin и безопасен."""
    value = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if value and url_has_allowed_host_and_scheme(
        value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return value
    return fallback


def safe_referer(request, fallback: str) -> str:
    """HTTP_REFERER, если он same-origin и безопасен, иначе fallback."""
    value = (request.META.get("HTTP_REFERER") or "").strip()
    if value and url_has_allowed_host_and_scheme(
        value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return value
    return fallback
