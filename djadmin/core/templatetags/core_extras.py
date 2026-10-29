"""Фильтры публичных шаблонов djadmin."""
from django import template
from django.conf import settings

register = template.Library()


@register.filter
def absurl(url):
    """/uploads/x → https://<WORKER_SITE_URL>/uploads/x (файлы в volume Flask)."""
    if not url:
        return ""
    if url.startswith(("http://", "https://", "data:")):
        return url
    base = settings.WORKER_SITE_URL
    return (base + url) if base else url
