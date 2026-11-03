"""Публичные read-only страницы (фаза 1) + health.

RLS-паритет (спека §1.3): Django ходит в БД напрямую (роль с BYPASSRLS), поэтому
видимость заданий/профилей фильтруется ЯВНО — Job.objects.public(),
Profile.objects.public_workers()/public_visible(). Публичные страницы никогда
не отображают приватные поля (email/phone/inn) — только колонки из PUBLIC_FIELDS.
"""
import os
import hashlib
import uuid
from urllib.parse import urlencode
from collections import Counter
from functools import lru_cache
from uuid import UUID

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator

from .models import Application, Blacklist, Favorite, Invitation, Job, JobFavorite, Profile, Rating, SitePage, Skill, UserSkill
from .analytics import track_job_view
from .og_image import render_job_og
from .search import ts_query
from .ratelimit import rate_limit_write
from .rpc import call_rpc_rows

PAGE_SIZE = 20

# JOB-P1-06: каталог по умолчанию — только open/completed (Flask jobs.py:164).
# cancelled доступен владельцу в «Моих заданиях», но не в публичной ленте.
PUBLIC_STATUSES = ("open", "completed")

# Публичные колонки профиля (паритет колоночных грантов RLS, миграция 132)
PUBLIC_PROFILE_FIELDS = (
    "id", "full_name", "avatar_url", "photo_url", "age", "bio", "city",
    "experience", "desired_payment", "verification_status", "rating",
    "total_reviews", "ratings_count", "portfolio_link", "is_self_employed",
    "created_at",
)
# contact/email_public/religion_id — НЕ публичные (152-ФЗ, P0-03/P0-04):
# контакты открываются после отклика на задание, вероисповедание — спецкатегория.


def _abs(url: str | None) -> str:
    if not url:
        return ""
    if url.startswith(("http://", "https://", "data:")):
        return url
    return (settings.WORKER_SITE_URL + url) if settings.WORKER_SITE_URL else url


def job_photo_urls(job, limit: int | None = None) -> list[str]:
    """Единый массив фото: JobPhoto + legacy photo_urls (без дублей, ≤limit)."""
    photos = [p.photo_url for p in job.photos.all() if p.photo_url]
    urls = photos + [u for u in (job.photo_urls or []) if u and u not in photos]
    return urls[:limit] if limit is not None else urls


def health(request):
    """Healthcheck платформы: БД обязательна, деградация → 503."""
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return JsonResponse({"status": "ok", "db": True})
    except Exception:
        return JsonResponse({"status": "degraded", "db": False}, status=503)


@lru_cache(maxsize=1)
def _apk_info():
    path = settings.REPO_ROOT / "static" / "apk" / "trudnik.apk"
    if not path.exists():
        return None
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "version": "1.2",
        "size_mb": round(path.stat().st_size / (1024 * 1024), 1),
        "sha256": digest,
    }


def app_download(request):
    """Как установить приложение: Android APK, iPhone/iPad PWA, ПК PWA."""
    return render(request, "core/app_download.html", {"apk": _apk_info()})


def download_apk(request):
    """Отдача подписанного APK как файла (не inline)."""
    path = settings.REPO_ROOT / "static" / "apk" / "trudnik.apk"
    if not path.exists():
        raise Http404("APK не найден")
    response = FileResponse(
        open(path, "rb"),
        content_type="application/vnd.android.package-archive",
        as_attachment=True,
        filename="trudnik-1.2.apk",
    )
    response["Cache-Control"] = "public, max-age=3600"
    return response


def home(request):
    """Flask-паритет: / — лента заданий (не отдельный лендинг)."""
    return redirect("core:jobs")


def _promoted_first():
    """is_promoted nullable: DESC по умолчанию даёт NULLS FIRST — продвигаемое тонет."""
    from django.db.models import F

    return F("is_promoted").desc(nulls_last=True)


@require_POST
def jobs_geo_set(request):
    """Сохранить гео-фильтр в сессии, не вынося координаты в URL."""
    nxt = request.POST.get("next") or reverse("core:jobs")
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        nxt = reverse("core:jobs")
    if request.POST.get("clear") == "1":
        for key in ("geo_lat", "geo_lng", "geo_radius"):
            request.session.pop(key, None)
        messages.info(request, "Гео-поиск отключён.")
        return redirect(nxt)
    try:
        lat = float(request.POST.get("lat") or "")
        lng = float(request.POST.get("lng") or "")
        radius = float(request.POST.get("radius") or 10)
    except (TypeError, ValueError):
        messages.error(request, "Не удалось получить координаты. Попробуйте ещё раз.")
        return redirect(nxt)
    if not (-90 <= lat <= 90 and -180 <= lng <= 180 and 0.1 <= radius <= 100):
        messages.error(request, "Некорректные координаты или радиус.")
        return redirect(nxt)
    # 152-ФЗ: минимальная точность для поиска (≈110 м) и короткий срок жизни.
    request.session["geo_lat"] = round(lat, 3)
    request.session["geo_lng"] = round(lng, 3)
    request.session["geo_radius"] = radius
    request.session.set_expiry(3600)
    return redirect(nxt)


def _saved_searches(user):
    prefs = user.notification_prefs or {}
    items = prefs.get("saved_searches") if isinstance(prefs.get("saved_searches"), list) else []
    result = []
    for item in items[:10]:
        if not isinstance(item, dict) or not item.get("id") or not item.get("query"):
            continue
        result.append({
            "id": item["id"],
            "name": item.get("name") or "Мой поиск",
            "url": reverse("core:jobs") + "?" + item["query"],
            "notify": item.get("notify", True) is not False,
        })
    return result


def _saved_search_data(post):
    skills = []
    for raw in post.getlist("skills"):
        try:
            skills.append(str(UUID(str(raw).strip())))
        except (TypeError, ValueError):
            continue
    skills = list(dict.fromkeys(skills))[:20]
    params = []
    for key in ("q", "city", "status", "payment_min", "payment_max", "filter"):
        value = (post.get(key) or "").strip()[:120]
        if value:
            params.append((key, value))
    for skill in skills:
        params.append(("skills", skill))
    query = urlencode(params)
    city = (post.get("city") or "").strip()
    q = (post.get("q") or "").strip()
    name = city or q or ("Все задания" if not query else "Мой поиск")
    return {"query": query, "name": name[:80]}


@login_required
@require_POST
@rate_limit_write(limit=20, window=60, redirect_to="/jobs")
def save_search(request):
    data = _saved_search_data(request.POST)
    if not data["query"]:
        messages.info(request, "Сначала выберите хотя бы один фильтр.")
        return redirect("core:jobs")
    prefs = request.user.notification_prefs or {}
    items = prefs.get("saved_searches") if isinstance(prefs.get("saved_searches"), list) else []
    items = [item for item in items if isinstance(item, dict)]
    if any(item.get("query") == data["query"] for item in items):
        messages.info(request, "Такой поиск уже сохранён.")
        return redirect(reverse("core:jobs") + (("?" + data["query"]) if data["query"] else ""))
    items.insert(0, {
        "id": uuid.uuid4().hex, "name": data["name"], "query": data["query"],
        "notify": True,
    })
    prefs["saved_searches"] = items[:10]
    Profile.objects.filter(pk=request.user.pk).update(notification_prefs=prefs)
    messages.success(request, "Поиск сохранён.")
    return redirect(reverse("core:jobs") + (("?" + data["query"]) if data["query"] else ""))


@login_required
@require_POST
@rate_limit_write(limit=20, window=60, redirect_to="/jobs")
def toggle_search(request, search_id):
    prefs = request.user.notification_prefs or {}
    items = prefs.get("saved_searches") if isinstance(prefs.get("saved_searches"), list) else []
    found = False
    updated = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("id") == search_id:
            item = dict(item)
            item["notify"] = item.get("notify", True) is False
            found = True
        updated.append(item)
    if found:
        prefs["saved_searches"] = updated[:10]
        Profile.objects.filter(pk=request.user.pk).update(notification_prefs=prefs)
        messages.info(request, "Настройка уведомлений поиска обновлена.")
    next_url = request.POST.get("next") or ""
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect("core:jobs")


@login_required
@require_POST
@rate_limit_write(limit=20, window=60, redirect_to="/jobs")
def delete_search(request, search_id):
    prefs = request.user.notification_prefs or {}
    items = prefs.get("saved_searches") if isinstance(prefs.get("saved_searches"), list) else []
    prefs["saved_searches"] = [
        item for item in items
        if isinstance(item, dict) and item.get("id") != search_id
    ][:10]
    Profile.objects.filter(pk=request.user.pk).update(notification_prefs=prefs)
    messages.info(request, "Сохранённый поиск удалён.")
    return redirect("core:jobs")


def jobs_list(request):
    job_filter = request.GET.get("filter") or ""
    if job_filter not in ("new", "applied") or not request.user.is_authenticated:
        job_filter = ""
    statuses = PUBLIC_STATUSES + (("cancelled",) if job_filter == "applied" else ())
    qs = Job.objects.filter(status__in=statuses).select_related("employer").prefetch_related(
        "photos"
    ).order_by(_promoted_first(), "-created_at")
    if request.user.is_authenticated:
        # Blacklist до пагинации: задания работодателей, заблокировавших пользователя.
        blocked_employer_ids = Blacklist.objects.filter(
            blocked_user=request.user
        ).values("user_id")
        qs = qs.exclude(employer_id__in=blocked_employer_ids)
    q = (request.GET.get("q") or "").strip()[:100]
    if q:
        ts = ts_query(q)
        if ts:
            qs = qs.extra(
                where=["jobs.search_vector @@ to_tsquery('russian', %s)"],
                params=[ts],
            )
        else:
            qs = qs.filter(
                Q(work_type__icontains=q)
                | Q(organization_name__icontains=q)
                | Q(city__icontains=q)
                | Q(detailed_description__icontains=q)
                | Q(object_description__icontains=q)
            ).distinct()
    city = (request.GET.get("city") or "").strip()
    if city:
        qs = qs.filter(city__icontains=city)
    status = request.GET.get("status") or ""
    if status in PUBLIC_STATUSES:
        qs = qs.filter(status=status)
    selected_skills = []
    raw_skills = []
    for value in request.GET.getlist("skills"):
        raw_skills.extend(value.split(","))
    skill_ids = []
    for raw in raw_skills:
        try:
            skill_ids.append(UUID(raw.strip()))
        except (TypeError, ValueError):
            continue
    skill_ids = list(dict.fromkeys(skill_ids))
    if skill_ids:
        selected_skills = [str(skill_id) for skill_id in skill_ids]
        qs = qs.filter(job_skills__skill_id__in=skill_ids).distinct()
    payment_min = request.GET.get("payment_min") or ""
    payment_max = request.GET.get("payment_max") or ""
    from decimal import Decimal

    try:
        qs = qs.filter(payment_amount__gte=Decimal(payment_min))
    except Exception:
        pass  # мусор в параметре — игнорируем фильтр
    try:
        qs = qs.filter(payment_amount__lte=Decimal(payment_max))
    except Exception:
        pass
    lat_raw = request.GET.get("lat") or ""
    lng_raw = request.GET.get("lng") or ""
    radius_raw = request.GET.get("radius") or ""
    geo_distances = {}
    geo_active = False
    geo_lat = geo_lng = geo_radius = None
    if request.GET.get("geo") == "1":
        # Координаты из серверной сессии: не попадают в URL/access-логи.
        try:
            geo_lat = float(request.session.get("geo_lat"))
            geo_lng = float(request.session.get("geo_lng"))
            geo_radius = float(request.session.get("geo_radius") or radius_raw or 10)
        except (TypeError, ValueError):
            geo_lat = geo_lng = geo_radius = None
    else:
        # Обратная совместимость со старыми ссылками до перехода на POST.
        try:
            geo_lat = float(lat_raw)
            geo_lng = float(lng_raw)
            geo_radius = float(radius_raw)
        except (TypeError, ValueError):
            geo_lat = geo_lng = geo_radius = None
    if (
        geo_lat is not None
        and -90 <= geo_lat <= 90
        and -180 <= geo_lng <= 180
        and 0.1 <= geo_radius <= 100
    ):
        try:
            nearby = call_rpc_rows("nearby_jobs", geo_lat, geo_lng, geo_radius * 1000)
        except Exception:
            messages.warning(request, "Гео-поиск недоступен — показаны все задания.")
        else:
            nearby = [row for row in (nearby or []) if row.get("id") is not None]
            nearby.sort(key=lambda row: row.get("distance_meters") or 0)
            geo_active = True
            if nearby:
                ids = [row["id"] for row in nearby]
                qs = qs.filter(pk__in=ids)
                geo_distances = {
                    str(row["id"]): (row.get("distance_meters") or 0) / 1000
                    for row in nearby
                }
            else:
                qs = qs.none()
    if job_filter:
        my_jobs = Application.objects.filter(worker=request.user).exclude(
            status__in=("withdrawn", "cancelled")
        ).values("job_id")
        if job_filter == "applied":
            qs = qs.filter(pk__in=my_jobs)
        else:
            qs = qs.exclude(pk__in=my_jobs)
    sort = request.GET.get("sort")
    if sort == "price_asc":
        from django.db.models import F

        qs = qs.order_by(F("payment_amount").asc(nulls_last=True))
    elif sort == "price_desc":
        from django.db.models import F

        qs = qs.order_by(F("payment_amount").desc(nulls_last=True))
    elif sort == "date":
        qs = qs.order_by("date_time")
    elif sort == "distance" and geo_distances:
        from django.db.models import Case, IntegerField, Value, When

        ordering = Case(
            *[
                When(pk=UUID(str(job_id)), then=Value(position))
                for position, job_id in enumerate(geo_distances)
            ],
            output_field=IntegerField(),
        )
        qs = qs.order_by(ordering)
    else:
        sort = "newest"

    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    for job in page.object_list:
        job.display_photo_urls = job_photo_urls(job, limit=3)
        if str(job.pk) in geo_distances:
            job.distance_km = "%.1f" % geo_distances[str(job.pk)]
    applied_ids = set()
    if request.user.is_authenticated:
        applied_ids = set(
            str(pk) for pk in Application.objects.filter(
                worker=request.user, job__in=page.object_list
            ).exclude(status__in=("withdrawn", "cancelled")).values_list("job_id", flat=True)
        )
    map_points = [
        {
            "id": str(job.pk),
            "lat": float(job.lat),
            "lng": float(job.lng),
            "title": job.work_type or "Задание",
            "url": reverse("core:job_detail", args=[job.pk]),
        }
        for job in page.object_list
        if job.lat is not None and job.lng is not None and (job.address or "").strip()
    ]
    if request.GET.get("geo") == "1" and geo_radius is not None:
        radius_raw = "%g" % geo_radius
    active_filter_count = sum(bool(value) for value in (
        q, city, status, skill_ids, payment_min, payment_max, job_filter, geo_active,
    ))
    geo_center = None
    if geo_active:
        # Round before rendering: the map needs a center, but the HTML must not
        # contain more precise device coordinates than ~100 m (152-FZ).
        geo_center = {
            "lat": round(geo_lat, 3),
            "lng": round(geo_lng, 3),
            "radius": round(geo_radius, 1),
        }
    return render(request, "core/jobs_list.html", {
        "page": page, "q": q, "city": city, "status": status,
        "payment_min": payment_min, "payment_max": payment_max, "sort": sort,
        "sort_options": (("newest", "Новые"), ("price_asc", "Дешевле"), ("price_desc", "Дороже"))
        + ((("distance", "Ближе"),) if geo_active else ()),
        "skills": list(Skill.objects.order_by("sort_order", "name")),
        "selected_skills": selected_skills,
        "job_filter": job_filter,
        "active_filter_count": active_filter_count,
        "saved_searches": _saved_searches(request.user) if request.user.is_authenticated else [],
        "applied_ids": applied_ids,
        "lat": lat_raw, "lng": lng_raw, "radius": radius_raw,
        "geo_mode": request.GET.get("geo") == "1",
        "geo_active": geo_active,
        "geo_center": geo_center,
        "map_points": map_points,
        "yandex_maps_key": os.getenv("YANDEX_MAPS_API_KEY", ""),
        "now": timezone.now(),
    })


def job_detail(request, job_id):
    # публичные статусы + собственные задания в любом статусе (владелец видит свои
    # draft/expired по ссылкам из «Моих заданий»)
    job = Job.objects.public().filter(pk=job_id).first()
    is_owner = False
    if job is None and request.user.is_authenticated:
        job = Job.objects.filter(pk=job_id, employer=request.user).first()
    if job is not None and request.user.is_authenticated:
        is_owner = job.employer_id == request.user.pk
    if job is None:
        raise Http404("Задание не найдено или недоступно")
    track_job_view(request, job.pk)
    photos = job_photo_urls(job, limit=3)
    skills = list(job.job_skills.select_related("skill").values_list("skill__name", flat=True))
    my_app = None
    can_withdraw = True
    is_owner = request.user.is_authenticated and job.employer_id == request.user.pk
    if request.user.is_authenticated and not is_owner:
        my_app = (
            Application.objects.filter(job=job, worker=request.user)
            .exclude(status__in=("withdrawn", "cancelled"))
            .values("id", "status")
            .first()
        )
    if my_app and job.date_time is not None:
        # Паритет Flask check_withdraw_window: <12 ч до начала — отзыв недоступен.
        can_withdraw = (job.date_time - timezone.now()).total_seconds() > 12 * 3600
    application_count = 0
    is_employer_fav = False
    if is_owner:
        application_count = Application.objects.filter(job=job).count()
    elif request.user.is_authenticated:
        is_employer_fav = Favorite.objects.filter(
            user=request.user, target_id=job.employer_id, favorite_type="employer"
        ).exists()
    employer = job.employer
    employer_reviews = list(
        Rating.objects.filter(
            rated_user_id=job.employer_id, target_type="employer"
        ).order_by("-created_at")[:3]
    )
    return render(request, "core/job_detail.html", {
        "job": job,
        "photos": [(i, _abs(url)) for i, url in enumerate(photos)],
        "skills": skills,
        "my_app": my_app,
        "can_withdraw": can_withdraw,
        "application_count": application_count,
        "is_employer_fav": is_employer_fav,
        "employer": employer,
        "employer_reviews": employer_reviews,
        "is_owner": is_owner,
        "show_push_prompt": request.GET.get("push") == "1",
        "yandex_maps_key": os.getenv("YANDEX_MAPS_API_KEY", ""),
        "is_fav": (
            request.user.is_authenticated
            and JobFavorite.objects.filter(user=request.user, job=job).exists()
        ),
    })


def job_og_image(request, job_id):
    """Сгенерированное OG-превью задания (1200×630, только публичные поля)."""
    job = Job.objects.public().filter(pk=job_id).first()
    if job is None:
        raise Http404("Задание не найдено")
    cache_key = "og:job:%s:%s" % (
        job.pk,
        job.updated_at.isoformat() if job.updated_at else "",
    )
    png = cache.get(cache_key)
    if png is None:
        try:
            png = render_job_og(job)
        except Exception:
            fallback = settings.REPO_ROOT / "static" / "icons" / "og-preview.png"
            if fallback.exists():
                return FileResponse(fallback.open("rb"), content_type="image/png")
            raise Http404("OG-превью недоступно")
        cache.set(cache_key, png, 3600)
    response = HttpResponse(png, content_type="image/png")
    response["Cache-Control"] = "public, max-age=3600"
    return response


def workers_list(request):
    qs = Profile.objects.public_workers().prefetch_related("user_skills__skill")
    q = (request.GET.get("q") or "").strip()
    if q:
        ts = ts_query(q)
        if ts:
            qs = qs.extra(
                where=["profiles.search_vector @@ to_tsquery('russian', %s)"],
                params=[ts],
            )
        else:
            qs = qs.filter(
                Q(full_name__icontains=q)
                | Q(city__icontains=q)
                | Q(bio__icontains=q)
            ).distinct()
    selected_skills = []
    raw_skills = []
    for value in request.GET.getlist("skills"):
        raw_skills.extend(value.split(","))
    skill_ids = []
    for raw in raw_skills:
        try:
            skill_ids.append(UUID(raw.strip()))
        except (TypeError, ValueError):
            continue
    skill_ids = list(dict.fromkeys(skill_ids))
    if skill_ids:
        selected_skills = [str(skill_id) for skill_id in skill_ids]
        qs = qs.filter(user_skills__skill_id__in=skill_ids).distinct()
    rating_min = request.GET.get("rating_min") or ""
    try:
        rating_value = float(rating_min)
    except (TypeError, ValueError):
        rating_value = None
    if rating_value is not None and 0 <= rating_value <= 5:
        qs = qs.filter(rating__gte=rating_value)
    payment_from = request.GET.get("payment_from") or ""
    payment_to = request.GET.get("payment_to") or ""
    from decimal import Decimal

    max_amount = Decimal("1000000000")
    try:
        payment_from_value = Decimal(payment_from)
    except Exception:
        payment_from_value = None
    if payment_from_value is not None and payment_from_value.is_finite() and 0 <= payment_from_value <= max_amount:
        qs = qs.filter(desired_payment__gte=payment_from_value)
    try:
        payment_to_value = Decimal(payment_to)
    except Exception:
        payment_to_value = None
    if payment_to_value is not None and payment_to_value.is_finite() and 0 <= payment_to_value <= max_amount:
        qs = qs.filter(desired_payment__lte=payment_to_value)
    invited_only = request.GET.get("invited") == "1" and request.user.is_authenticated
    if invited_only:
        qs = qs.filter(
            pk__in=Invitation.objects.filter(
                employer=request.user, status=Invitation.Status.PENDING,
            ).values("worker_id")
        )
    sort = request.GET.get("sort") or "rating"
    from django.db.models import F

    if sort == "name":
        qs = qs.order_by("full_name")
    elif sort == "price_asc":
        qs = qs.order_by(F("desired_payment").asc(nulls_last=True))
    elif sort == "price_desc":
        qs = qs.order_by(F("desired_payment").desc(nulls_last=True))
    else:
        sort = "rating"
        qs = qs.order_by("-rating", "-total_reviews")
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    worker_ids = [w.pk for w in page.object_list]
    reliable_worker_ids = set()
    invited_worker_ids = set()
    pending_invited_worker_ids = set()
    favorite_worker_ids = set()
    my_open_jobs = []
    if request.user.is_authenticated:
        favorite_worker_ids = set(
            Favorite.objects.filter(
                user=request.user, target_id__in=worker_ids, favorite_type="worker"
            ).values_list("target_id", flat=True)
        )
        my_open_jobs = list(
            Job.objects.filter(employer=request.user, status="open").order_by("date_time")[:50]
        )
    if worker_ids:
        status_rows = list(
            Application.objects.filter(
                worker_id__in=worker_ids, status__in=("accepted", "rejected")
            ).values_list("worker_id", "status")
        )
        accepted = Counter(wid for wid, status in status_rows if status == "accepted")
        rejected = Counter(wid for wid, status in status_rows if status == "rejected")
        reliable_worker_ids = {
            wid for wid in worker_ids
            if accepted.get(wid, 0) >= 10 and rejected.get(wid, 0) == 0
        }
        if request.user.is_authenticated:
            invitation_rows = Invitation.objects.filter(
                employer=request.user,
                worker_id__in=worker_ids,
                status__in=("pending", "accepted"),
            ).values_list("worker_id", "status")
            invited_worker_ids = {wid for wid, _status in invitation_rows}
            pending_invited_worker_ids = {
                wid for wid, status in invitation_rows if status == "pending"
            }
    active_filter_count = sum(bool(value) for value in (
        q, skill_ids, rating_min, payment_from, payment_to,
        request.GET.get("sort") not in (None, "", "rating"), invited_only,
    ))
    return render(request, "core/workers_list.html", {
        "page": page, "q": q,
        "active_filter_count": active_filter_count,
        "skills": list(Skill.objects.order_by("sort_order", "name")),
        "selected_skills": selected_skills,
        "rating_min": rating_min,
        "payment_from": payment_from,
        "payment_to": payment_to,
        "sort": sort,
        "invited_only": invited_only,
        "reliable_worker_ids": reliable_worker_ids,
        "invited_worker_ids": invited_worker_ids,
        "pending_invited_worker_ids": pending_invited_worker_ids,
        "favorite_worker_ids": favorite_worker_ids,
        "my_open_jobs": my_open_jobs,
    })


def worker_detail(request, user_id):
    profile = (
        Profile.objects.public_visible()
        .filter(pk=user_id)
        .values(*PUBLIC_PROFILE_FIELDS)
        .first()
    )
    if profile is None:
        raise Http404("Профиль не найден")
    from core.models import Favorite, Job, UserSkill

    skills = list(
        UserSkill.objects.filter(user_id=profile["id"]).select_related("skill")
        .values_list("skill__name", flat=True)
    )
    context = {"p": profile, "skills": skills}
    context["ratings"] = list(
        Rating.objects.filter(rated_user_id=profile["id"], target_type="worker")
        .select_related("rater_user", "job").order_by("-created_at")[:3]
    )
    if request.user.is_authenticated and profile["id"] != request.user.pk:
        context["my_open_jobs"] = list(
            Job.objects.filter(employer=request.user, status=Job.Status.OPEN)
            .order_by("date_time").values("id", "work_type", "date_time")[:20]
        )
        context["is_fav_person"] = Favorite.objects.filter(
            user=request.user, target_id=profile["id"]
        ).exists()
        context["pending_invitations"] = list(
            Invitation.objects.filter(
                employer=request.user, worker_id=profile["id"],
                status=Invitation.Status.PENDING,
            ).select_related("job").order_by("-created_at")
        )
    return render(request, "core/worker_detail.html", context)


# LEGAL-P0-01: заголовки legacy-страниц, рендерятся, когда site_pages пуст.
LEGAL_TITLES = {
    "privacy": "Политика конфиденциальности",
    "terms": "Условия использования",
    "safety": "Как мы защищаем",
}


def legal_page(request, slug):
    page = SitePage.objects.filter(pk=slug).first()
    if page is not None:
        return render(request, "core/legal_page.html", {"page": page})
    if slug in LEGAL_TITLES:
        return render(request, "core/legal_fallback.html", {
            "slug": slug,
            "title": LEGAL_TITLES[slug],
        })
    raise Http404("Страница не найдена")


def robots(request):
    lines = (
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Sitemap: %s/sitemap.xml" % settings.SITE_URL.rstrip("/"),
    )
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")
