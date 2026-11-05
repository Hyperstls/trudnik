"""Информационная страница /info (R017): активные объявления Announcement."""
from urllib.parse import urlsplit

from django.shortcuts import render

from .models import Announcement


def _safe_external_url(value):
    """Только http/https со схемой и хостом; остальное не выводим ссылкой."""
    if not value:
        return ""
    try:
        parts = urlsplit(value)
    except ValueError:
        return ""
    if parts.scheme.lower() in ("http", "https") and parts.netloc:
        return value
    return ""


def info_page(request):
    announcements = list(Announcement.objects.filter(is_active=True))
    for announcement in announcements:
        announcement.safe_url = _safe_external_url(announcement.url)
    return render(request, "core/info.html", {"announcements": announcements})
