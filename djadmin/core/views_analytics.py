"""Staff-only funnel dashboard and the public install/usage counters (J123)."""
import json
import uuid

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .analytics import EVENTS, incr, incr_job_view, series
from .models import Job
from .ratelimit import RateLimitExceeded, RateLimitUnavailable, enforce_ip_limit

CLIENT_EVENTS = ("install", "job_view", "app_open", "app_return")


def render_dashboard(request, site=None):
    days = 30 if request.GET.get("days") == "30" else 7
    data = {event: series(event, days) for event in EVENTS}
    totals = {event: sum(value for _, value in data[event]) for event in EVENTS}
    conversion = (
        round(totals["application_sent"] / totals["job_view"] * 100, 1)
        if totals["job_view"] else 0
    )
    app_opens = totals["app_open"] + totals["app_return"]
    return_rate = (
        round(totals["app_return"] / app_opens * 100, 1) if app_opens else 0
    )
    rows = [
        {
            "date": day,
            **{event: dict(data[event]).get(day, 0) for event in EVENTS},
        }
        for day, _ in data["job_view"]
    ]
    context = dict(
        site.each_context(request) if site is not None else {},
        title="Воронка",
        days=days,
        totals=totals,
        rows=rows,
        conversion=conversion,
        return_rate=return_rate,
    )
    return render(request, "admin/analytics.html", context)


@staff_member_required(login_url="/admin/login/")
def dashboard(request):
    from core.admin import site
    return render_dashboard(request, site)


@require_POST
def track_event(request):
    try:
        payload = json.loads(request.body.decode("utf-8", "replace"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "bad_json"}, status=400)
    if not isinstance(payload, dict) or payload.get("event") not in CLIENT_EVENTS:
        return JsonResponse({"error": "bad_event"}, status=400)
    event = payload["event"]
    if event == "job_view":
        try:
            job_id = uuid.UUID(str(payload.get("job_id")))
        except (TypeError, ValueError, AttributeError):
            return JsonResponse({"error": "bad_job"}, status=400)
        if not Job.objects.public().filter(pk=job_id).exists():
            return JsonResponse({"error": "bad_job"}, status=400)
    try:
        enforce_ip_limit(request, "analytics_event", 20, 60)
    except RateLimitExceeded:
        return JsonResponse({"error": "rate_limited"}, status=429)
    except RateLimitUnavailable:
        pass
    incr(event)
    if event == "job_view":
        incr_job_view(job_id)
    return JsonResponse({"ok": True})
