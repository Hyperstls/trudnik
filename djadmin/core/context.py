"""Context processors для публичных шаблонов."""
from django.conf import settings


def workers_site_url(request):
    """WORKER_SITE_URL — чтобы абсолютизировать /uploads/... (файлы в volume Flask)."""
    return {"WORKER_SITE_URL": settings.WORKER_SITE_URL}


def absolute_upload(url: str | None) -> str:
    """Jinja/Django-фильтр: '/uploads/x' → 'https://<worker-site>/uploads/x'."""
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    base = settings.WORKER_SITE_URL
    return (base + url) if base else url
