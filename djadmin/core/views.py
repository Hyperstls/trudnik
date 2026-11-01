"""Публичные read-only страницы (фаза 1) + health.

RLS-паритет (спека §1.3): Django ходит в БД напрямую (роль с BYPASSRLS), поэтому
видимость заданий/профилей фильтруется ЯВНО — Job.objects.public(),
Profile.objects.public_workers()/public_visible(). Публичные страницы никогда
не отображают приватные поля (email/phone/inn) — только колонки из PUBLIC_FIELDS.
"""
from collections import Counter
from uuid import UUID

from django.conf import settings
from django.db import connection
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.core.paginator import Paginator

from .models import Application, Blacklist, Favorite, Invitation, Job, JobFavorite, Profile, Rating, SitePage, Skill, UserSkill

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


def home(request):
    """Flask-паритет: / — лента заданий (не отдельный лендинг)."""
    return redirect("core:jobs")


def _promoted_first():
    """is_promoted nullable: DESC по умолчанию даёт NULLS FIRST — продвигаемое тонет."""
    from django.db.models import F

    return F("is_promoted").desc(nulls_last=True)


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
        qs = qs.filter(work_type__icontains=q) | qs.filter(organization_name__icontains=q) | \
             qs.filter(city__icontains=q) | qs.filter(detailed_description__icontains=q) | \
             qs.filter(object_description__icontains=q)
        qs = qs.distinct()
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
    else:
        sort = "newest"

    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    for job in page.object_list:
        job.display_photo_urls = job_photo_urls(job, limit=3)
    applied_ids = set()
    if request.user.is_authenticated:
        applied_ids = set(
            str(pk) for pk in Application.objects.filter(
                worker=request.user, job__in=page.object_list
            ).exclude(status__in=("withdrawn", "cancelled")).values_list("job_id", flat=True)
        )
    return render(request, "core/jobs_list.html", {
        "page": page, "q": q, "city": city, "status": status,
        "payment_min": payment_min, "payment_max": payment_max, "sort": sort,
        "sort_options": (("newest", "Новые"), ("price_asc", "Дешевле"), ("price_desc", "Дороже")),
        "skills": list(Skill.objects.order_by("sort_order", "name")),
        "selected_skills": selected_skills,
        "job_filter": job_filter,
        "applied_ids": applied_ids,
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
            rated_user_id=job.employer_id, rating_type="employer"
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
        "is_fav": (
            request.user.is_authenticated
            and JobFavorite.objects.filter(user=request.user, job=job).exists()
        ),
    })


def workers_list(request):
    qs = Profile.objects.public_workers()
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = (qs.filter(full_name__icontains=q) | qs.filter(city__icontains=q)
              | qs.filter(bio__icontains=q)).distinct()
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
    if worker_ids:
        accepted = Counter(
            Application.objects.filter(
                worker_id__in=worker_ids, status="accepted"
            ).values_list("worker_id", flat=True)
        )
        rejected = Counter(
            Application.objects.filter(
                worker_id__in=worker_ids, status="rejected"
            ).values_list("worker_id", flat=True)
        )
        reliable_worker_ids = {
            wid for wid in worker_ids
            if accepted.get(wid, 0) >= 10 and rejected.get(wid, 0) == 0
        }
        if request.user.is_authenticated:
            invited_worker_ids = set(
                Invitation.objects.filter(
                    employer=request.user,
                    worker_id__in=worker_ids,
                    status__in=("pending", "accepted"),
                ).values_list("worker_id", flat=True)
            )
    return render(request, "core/workers_list.html", {
        "page": page, "q": q,
        "skills": list(Skill.objects.order_by("sort_order", "name")),
        "selected_skills": selected_skills,
        "rating_min": rating_min,
        "payment_from": payment_from,
        "payment_to": payment_to,
        "sort": sort,
        "reliable_worker_ids": reliable_worker_ids,
        "invited_worker_ids": invited_worker_ids,
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
    if request.user.is_authenticated and profile["id"] != request.user.pk:
        context["my_open_jobs"] = list(
            Job.objects.filter(employer=request.user, status=Job.Status.OPEN)
            .order_by("date_time").values("id", "work_type", "date_time")[:20]
        )
        context["is_fav_person"] = Favorite.objects.filter(
            user=request.user, target_id=profile["id"]
        ).exists()
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
    return HttpResponse("User-agent: *\nAllow: /\n", content_type="text/plain")
