"""Staff-only funnel dashboard and the public install counter (J123)."""
import json

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .analytics import EVENTS, incr, series
from .ratelimit import RateLimitExceeded, RateLimitUnavailable, enforce_ip_limit


def render_dashboard(request, site=None):
    days = 30 if request.GET.get("days") == "30" else 7
    data = {event: series(event, days) for event in EVENTS}
    totals = {event: sum(value for _, value in data[event]) for event in EVENTS}
    conversion = (
        round(totals["application_sent"] / totals["job_view"] * 100, 1)
        if totals["job_view"] else 0
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
    if not isinstance(payload, dict) or payload.get("event") != "install":
        return JsonResponse({"error": "bad_event"}, status=400)
    try:
        enforce_ip_limit(request, "analytics_event", 20, 60)
    except RateLimitExceeded:
        return JsonResponse({"error": "rate_limited"}, status=429)
    except RateLimitUnavailable:
        pass
    incr("install")
    return JsonResponse({"ok": True})
