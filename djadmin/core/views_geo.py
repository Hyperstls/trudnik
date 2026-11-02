"""Server-side Yandex Geosuggest and Geocoder proxies (J079, J111).

API keys stay server-side; address text and coordinates travel in a POST body
so they are not written to access logs or browser history. The Geocoder proxy
does not depend on the JavaScript API key permissions: it uses a dedicated
``YANDEX_GEOCODER_KEY`` (falls back to ``YANDEX_MAPS_API_KEY`` if that key has
Geocoder access). On any failure the form falls back to client-side
``ymaps.geocode``.
"""
import hashlib
import json
import logging
import os
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .ratelimit import RateLimitExceeded, RateLimitUnavailable, enforce_ip_limit

logger = logging.getLogger(__name__)

SUGGEST_URL = "https://suggest-maps.yandex.ru/v1/suggest"
GEOCODER_URLS = (
    "https://geocode-maps.yandex.ru/v1",
    "https://geocode-maps.yandex.ru/1.x/",
)
GEOCODE_CACHE_TTL = 600


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


def _geocoder_key():
    return (
        os.getenv("YANDEX_GEOCODER_KEY", "").strip()
        or os.getenv("YANDEX_MAPS_API_KEY", "").strip()
    )


def _geocoder_referer():
    """Referer for server-side Geocoder calls.

    Yandex applies the key's HTTP Referer allow-list to server requests too and
    rejects requests without a matching header. Default is the canonical site.
    """
    referer = (
        os.getenv("YANDEX_GEOCODER_REFERER", "").strip()
        or os.getenv("WORKER_SITE_URL", "").strip()
        or "https://xn--d1aigknli.xn--p1ai"
    )
    if "://" not in referer:
        referer = "https://" + referer
    return referer.rstrip("/") + "/"


def _geocode_results(data):
    """Normalize Yandex Geocoder JSON into the client result shape."""
    response = data.get("response") if isinstance(data, dict) else None
    collection = (response or {}).get("GeoObjectCollection") or {}
    members = collection.get("featureMember") or []
    results = []
    for member in members:
        obj = (member or {}).get("GeoObject") or {}
        meta = ((obj.get("metaDataProperty") or {}).get("GeocoderMetaData")) or {}
        address = meta.get("Address") if isinstance(meta.get("Address"), dict) else {}
        formatted = (address.get("formatted") or meta.get("text") or "").strip()
        position = ((obj.get("Point") or {}).get("pos") or "").split()
        if len(position) != 2:
            continue
        try:
            lng, lat = float(position[0]), float(position[1])
        except ValueError:
            continue
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            continue
        city = ""
        components = address.get("components") or address.get("Components") or []
        for component in components:
            if isinstance(component, dict) and component.get("kind") == "locality":
                city = (component.get("name") or "").strip()
                if city:
                    break
        label = formatted or meta.get("text") or ""
        if not label:
            continue
        results.append({
            "displayName": label,
            "value": label,
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "city": city,
            "precision": meta.get("precision") or "",
        })
    return results


def _fetch_geocode(params):
    """Call Geocoder v1, falling back to the legacy 1.x endpoint.

    Returns None on failure. Never logs the request URL: it contains the key
    and the user's address.
    """
    for index, endpoint in enumerate(GEOCODER_URLS):
        upstream_request = Request(
            endpoint + "?" + urlencode(params),
            headers={
                "User-Agent": "Trudnik/1.0",
                "Accept": "application/json",
                "Referer": _geocoder_referer(),
            },
        )
        try:
            with urlopen(upstream_request, timeout=5) as upstream:
                return json.loads(upstream.read().decode("utf-8", "replace"))
        except HTTPError as exc:
            if exc.code in (403, 404) and index < len(GEOCODER_URLS) - 1:
                continue  # key may be scoped to the other endpoint version
            logger.warning("geo_geocode upstream HTTP %s", exc.code)
            return None
        except Exception as exc:
            logger.warning("geo_geocode upstream error: %s", type(exc).__name__)
            return None
    return None


@login_required
@require_POST
def geo_geocode(request):
    """Forward and reverse geocoding through the server-side Geocoder API."""
    if len(request.body or b"") > 4096:
        return JsonResponse({"error": "too_large"}, status=400)
    try:
        payload = json.loads(request.body.decode("utf-8", "replace"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "bad_json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "bad_json"}, status=400)

    mode = payload.get("mode") or "forward"
    if mode not in ("forward", "reverse"):
        return JsonResponse({"error": "bad_mode"}, status=400)

    if mode == "reverse":
        try:
            lat = float(payload.get("lat"))
            lng = float(payload.get("lng"))
        except (TypeError, ValueError):
            return JsonResponse({"error": "bad_coords"}, status=400)
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return JsonResponse({"error": "bad_coords"}, status=400)
        # Yandex expects "longitude,latitude" for reverse geocoding.
        query = "%.6f,%.6f" % (lng, lat)
        cache_key = "geo:rev:%s" % query
        limit = "1"
    else:
        raw_text = payload.get("text")
        text = raw_text.strip()[:160] if isinstance(raw_text, str) else ""
        if len(text) < 3:
            return JsonResponse({"results": [], "enabled": _geocoder_key() != ""})
        query = text
        digest = hashlib.sha256(text.lower().encode("utf-8")).hexdigest()
        cache_key = "geo:fwd:%s" % digest
        limit = "5"

    try:
        enforce_ip_limit(request, "geo_geocode", 60, 60)
    except RateLimitExceeded:
        return JsonResponse({"error": "rate_limited"}, status=429)
    except RateLimitUnavailable:
        pass  # geocoding is optional; do not break the form

    api_key = _geocoder_key()
    if not api_key:
        return JsonResponse({"results": [], "enabled": False})

    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse({"results": cached, "enabled": True})

    params = {
        "apikey": api_key,
        "geocode": query,
        "format": "json",
        "lang": "ru_RU",
        "results": limit,
    }
    data = _fetch_geocode(params)
    if data is None:
        # Never echo upstream details or the key; client will use ymaps.geocode.
        return JsonResponse(
            {"results": [], "enabled": True, "error": "upstream"},
            headers={"Cache-Control": "no-store"},
        )

    results = _geocode_results(data)
    if results:
        cache.set(cache_key, results, GEOCODE_CACHE_TTL)
    response = JsonResponse({"results": results, "enabled": True})
    response["Cache-Control"] = "no-store"
    return response
