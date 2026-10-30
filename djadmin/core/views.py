"""Публичные read-only страницы (фаза 1) + health.

RLS-паритет (спека §1.3): Django ходит в БД напрямую (роль с BYPASSRLS), поэтому
видимость заданий/профилей фильтруется ЯВНО — Job.objects.public(),
Profile.objects.public_workers()/public_visible(). Публичные страницы никогда
не отображают приватные поля (email/phone/inn) — только колонки из PUBLIC_FIELDS.
"""
from django.conf import settings
from django.db import connection
from django.http import Http404, HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from .models import Application, Job, JobFavorite, Profile, SitePage

PAGE_SIZE = 20

# Публичные колонки профиля (паритет колоночных грантов RLS, миграция 132)
PUBLIC_PROFILE_FIELDS = (
    "id", "full_name", "avatar_url", "photo_url", "age", "bio", "city",
    "experience", "desired_payment", "verification_status", "rating",
    "total_reviews", "ratings_count", "portfolio_link", "is_self_employed",
    "email_public", "contact", "created_at", "religion_id",
)


def _abs(url: str | None) -> str:
    if not url:
        return ""
    if url.startswith(("http://", "https://", "data:")):
        return url
    return (settings.WORKER_SITE_URL + url) if settings.WORKER_SITE_URL else url


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
    jobs = Job.objects.public().order_by(_promoted_first(), "-created_at")[:6]
    return render(request, "core/home.html", {"jobs": jobs})


def _promoted_first():
    """is_promoted nullable: DESC по умолчанию даёт NULLS FIRST — продвигаемое тонет."""
    from django.db.models import F

    return F("is_promoted").desc(nulls_last=True)


def jobs_list(request):
    qs = Job.objects.public().select_related("employer").order_by(_promoted_first(), "-created_at")
    q = (request.GET.get("q") or "").strip()[:100]
    if q:
        qs = qs.filter(work_type__icontains=q) | qs.filter(organization_name__icontains=q) | \
             qs.filter(city__icontains=q) | qs.filter(detailed_description__icontains=q)
        qs = qs.distinct()
    city = (request.GET.get("city") or "").strip()
    if city:
        qs = qs.filter(city__icontains=city)
    status = request.GET.get("status") or ""
    if status in ("open", "completed", "cancelled"):
        qs = qs.filter(status=status)
    payment_min = request.GET.get("payment_min") or ""
    try:
        from decimal import Decimal

        qs = qs.filter(payment_amount__gte=Decimal(payment_min))
    except Exception:
        pass  # мусор в параметре — игнорируем фильтр
    sort = request.GET.get("sort")
    if sort == "payment":
        from django.db.models import F

        qs = qs.order_by(F("payment_amount").desc(nulls_last=True))
    elif sort == "date":
        qs = qs.order_by("date_time")

    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "core/jobs_list.html", {
        "page": page, "q": q, "city": city, "status": status,
        "payment_min": payment_min, "sort": sort or "new",
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
    photos = list(job.photos.all())
    skills = list(job.job_skills.select_related("skill").values_list("skill__name", flat=True))
    my_app = None
    is_owner = request.user.is_authenticated and job.employer_id == request.user.pk
    if request.user.is_authenticated and not is_owner:
        my_app = (
            Application.objects.filter(job=job, worker=request.user)
            .exclude(status__in=("withdrawn", "cancelled"))
            .values("id", "status")
            .first()
        )
    return render(request, "core/job_detail.html", {
        "job": job,
        "photos": [(i, _abs(p.photo_url)) for i, p in enumerate(photos)],
        "skills": skills,
        "my_app": my_app,
        "is_owner": is_owner,
        "is_fav": (
            request.user.is_authenticated
            and JobFavorite.objects.filter(user=request.user, job=job).exists()
        ),
    })


def workers_list(request):
    qs = Profile.objects.public_workers().order_by("-rating", "-total_reviews")
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = (qs.filter(full_name__icontains=q) | qs.filter(city__icontains=q)
              | qs.filter(bio__icontains=q)).distinct()
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "core/workers_list.html", {"page": page, "q": q})


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


def legal_page(request, slug):
    page = get_object_or_404(SitePage, pk=slug)
    return render(request, "core/legal_page.html", {"page": page})


def robots(request):
    return HttpResponse("User-agent: *\nAllow: /\n", content_type="text/plain")
