"""PWA и служебные эндпоинты (паритет Flask core_bp):
/sw.js (из static/sw.js), /offline, /.well-known/assetlinks.json, /favicon.ico,
/metrics (X-Metrics-Token, prod без токена → 404), /api/client-error, /api/skills.
"""
import hmac
import json
import logging
import time
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)
_START_TS = time.time()


def _static_file(rel: str, content_type: str, cache: str = "public, max-age=86400"):
    path = Path(settings.REPO_ROOT) / "static" / rel
    if not path.is_file():
        raise Http404()
    response = FileResponse(open(path, "rb"), content_type=content_type)
    response["Cache-Control"] = cache
    response["X-Content-Type-Options"] = "nosniff"
    return response


def service_worker(request):
    """Service Worker на корне origin (иначе scope ограничен /static/)."""
    response = _static_file("sw.js", "application/javascript", cache="no-cache")
    response["Service-Worker-Allowed"] = "/"
    return response


def offline(request):
    from django.shortcuts import render

    return render(request, "core/offline.html")


def assetlinks(request):
    return _static_file(".well-known/assetlinks.json", "application/json")


def favicon(request):
    return _static_file("icons/favicon.svg", "image/svg+xml")


def metrics(request):
    """/metrics (Prometheus text): токен X-Metrics-Token против env METRICS_TOKEN.

    Прод без METRICS_TOKEN → 404 (не раскрываем существование), dev — открыт.
    """
    expected = (getattr(settings, "METRICS_TOKEN", "") or "").strip()
    if expected:
        provided = request.headers.get("X-Metrics-Token", "")
        if not hmac.compare_digest(provided.encode(), expected.encode()):
            raise Http404()
    elif not settings.DEBUG:
        raise Http404()

    from django.db import connection

    from .models import Application, Job, Profile

    db_ok = 1
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    except Exception:
        db_ok = 0
    lines = [
        "# HELP trudnik_uptime_seconds Process uptime",
        "# TYPE trudnik_uptime_seconds gauge",
        "trudnik_uptime_seconds %.0f" % (time.time() - _START_TS),
        "# HELP trudnik_db_up Database reachable",
        "# TYPE trudnik_db_up gauge",
        "trudnik_db_up %d" % db_ok,
        "# HELP trudnik_profiles_total Profiles count",
        "# TYPE trudnik_profiles_total gauge",
        "trudnik_profiles_total %d" % Profile.objects.count(),
        "# HELP trudnik_jobs_total Jobs count by status open",
        "# TYPE trudnik_jobs_total gauge",
        "trudnik_jobs_total %d" % Job.objects.filter(status="open").count(),
        "# HELP trudnik_applications_total Applications count",
        "# TYPE trudnik_applications_total gauge",
        "trudnik_applications_total %d" % Application.objects.count(),
    ]
    return HttpResponse("\n".join(lines) + "\n",
                        content_type="text/plain; version=0.0.4; charset=utf-8")


@csrf_protect
@require_POST
def client_error(request):
    """Приём отчётов об ошибках фронтенда (JSON, поля обрезаем и логируем)."""
    try:
        data = json.loads(request.body.decode("utf-8", "replace") or "{}")
    except Exception:
        data = {}
    safe = {
        k: str(data.get(k, ""))[:500]
        for k in ("message", "source", "lineno", "colno", "url", "userAgent")
    }
    logger.warning("client-error: %s", json.dumps(safe, ensure_ascii=False))
    return HttpResponse(status=204)


def skills_json(request):
    """GET /api/skills — справочник навыков для автокомплита (паритет Flask)."""
    from .models import Skill

    return JsonResponse({
        "skills": list(Skill.objects.order_by("sort_order", "name").values("id", "name"))
    })
