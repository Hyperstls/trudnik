"""Server-side job form draft (J094).

Stored in profiles.notification_prefs["job_draft"] to avoid a schema change.
Only whitelisted form fields are stored; coordinates, CSRF and files are not.
"""
import json
import time

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .models import Profile

TTL_SECONDS = 30 * 24 * 60 * 60
ALLOWED_FIELDS = {
    "work_type", "organization_name", "org_description", "object_description",
    "detailed_description", "address", "city", "payment_amount", "max_workers",
    "date_time", "skills",
}
MAX_FIELDS = 20
MAX_VALUE = 5000
MAX_TOTAL = 20000


def _clean_fields(raw):
    if not isinstance(raw, dict):
        return None
    clean = {}
    total = 0
    for name, values in list(raw.items())[:MAX_FIELDS]:
        if name not in ALLOWED_FIELDS:
            continue
        if not isinstance(values, list):
            values = [values]
        items = []
        for value in values[:50]:
            if not isinstance(value, str):
                continue
            value = value[:MAX_VALUE]
            total += len(value)
            if total > MAX_TOTAL:
                return None
            items.append(value)
        clean[name] = items
    return clean


@login_required
@require_http_methods(["GET", "POST", "DELETE"])
def job_draft(request):
    prefs = dict(request.user.notification_prefs or {})
    stored = prefs.get("job_draft") if isinstance(prefs.get("job_draft"), dict) else None

    if request.method == "GET":
        if stored:
            saved_at = stored.get("saved_at")
            try:
                age = time.time() - float(saved_at) / 1000.0
            except (TypeError, ValueError):
                age = TTL_SECONDS + 1
            if age > TTL_SECONDS:
                prefs.pop("job_draft", None)
                Profile.objects.filter(pk=request.user.pk).update(notification_prefs=prefs)
                stored = None
        response = JsonResponse({"draft": stored})
        response["Cache-Control"] = "no-store"
        return response

    if request.method == "DELETE":
        prefs.pop("job_draft", None)
        Profile.objects.filter(pk=request.user.pk).update(notification_prefs=prefs)
        response = JsonResponse({"success": True})
        response["Cache-Control"] = "no-store"
        return response

    if len(request.body or b"") > 65536:
        return JsonResponse({"error": "too_large"}, status=400)
    try:
        payload = json.loads(request.body.decode("utf-8", "replace"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "bad_json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "bad_json"}, status=400)
    fields = _clean_fields(payload.get("fields"))
    if fields is None:
        return JsonResponse({"error": "bad_fields"}, status=400)
    try:
        saved_at = int(payload.get("saved_at") or 0)
    except (TypeError, ValueError):
        saved_at = 0
    if saved_at <= 0:
        saved_at = int(time.time() * 1000)
    prefs["job_draft"] = {"saved_at": saved_at, "fields": fields}
    Profile.objects.filter(pk=request.user.pk).update(notification_prefs=prefs)
    response = JsonResponse({"success": True, "saved_at": saved_at})
    response["Cache-Control"] = "no-store"
    return response
