"""Server-side Yandex Geosuggest proxy (J079).

The API key stays server-side; the address text travels in a POST body so it is
not written to access logs or browser history. On any failure the form falls
back to Yandex Geocoder client-side.
"""
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .ratelimit import RateLimitExceeded, RateLimitUnavailable, enforce_ip_limit

SUGGEST_URL = "https://suggest-maps.yandex.ru/v1/suggest"


def _text(value):
    if isinstance(value, dict):
        return (value.get("text") or "").strip()
    return (value or "").strip() if isinstance(value, str) else ""


@login_required
@require_POST
def geo_suggest(request):
    if len(request.body or b"") > 4096:
        return JsonResponse({"error": "too_large"}, status=400)
    try:
        payload = json.loads(request.body.decode("utf-8", "replace"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "bad_json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "bad_json"}, status=400)

    raw_q = payload.get("q")
    raw_city = payload.get("city")
    query = raw_q.strip()[:120] if isinstance(raw_q, str) else ""
    city = raw_city.strip()[:80] if isinstance(raw_city, str) else ""
    if len(query) < 3:
        return JsonResponse({"results": []})

    try:
        enforce_ip_limit(request, "geo_suggest", 60, 60)
    except RateLimitExceeded:
        return JsonResponse({"error": "rate_limited"}, status=429)
    except RateLimitUnavailable:
        pass  # suggestions are optional; do not break the form

    api_key = os.getenv("YANDEX_SUGGEST_API_KEY", "").strip()
    if not api_key:
        return JsonResponse({"results": [], "enabled": False})

    text = query
    if city and city.lower() not in query.lower():
        text = "%s, %s" % (city, query)
    params = {
        "apikey": api_key,
        "text": text,
        "lang": "ru_RU",
        "results": "6",
        "print_address": "1",
    }
    try:
        req = Request(
            SUGGEST_URL + "?" + urlencode(params),
            headers={"User-Agent": "Trudnik/1.0", "Accept": "application/json"},
        )
        with urlopen(req, timeout=4) as upstream:
            data = json.loads(upstream.read().decode("utf-8", "replace"))
    except Exception:
        # Never echo upstream details or the key; client will use Geocoder.
        return JsonResponse({"results": []}, headers={"Cache-Control": "no-store"})

    results = []
    for item in (data.get("results") or [])[:6]:
        if not isinstance(item, dict):
            continue
        title = _text(item.get("title"))
        subtitle = _text(item.get("subtitle"))
        address = item.get("address") if isinstance(item.get("address"), dict) else {}
        formatted = _text(address.get("formatted_address"))
        label = formatted or title
        if not label:
            continue
        if not formatted and subtitle and subtitle.lower() not in label.lower():
            label = "%s, %s" % (subtitle, label)
        results.append({
            "displayName": label,
            "value": label,
            "subtitle": subtitle or title,
        })
    response = JsonResponse({"results": results})
    response["Cache-Control"] = "no-store"
    return response
