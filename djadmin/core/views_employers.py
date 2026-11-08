"""Работодатели: каталог, карточка, избранное.

RLS-паритет: видимость — Profile.objects.public_visible(), скрытые/заблокированные
ведут себя как несуществующие. Карточка отдаёт только публичные поля профиля.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .http import safe_referer
from .models import Application, Blacklist, EmployerDetail, Favorite, Job, Profile
from .reputation import (
    criteria_labels, profile_metrics, public_ratings, rating_distribution,
    recent_rating, reliable_badge, tag_labels, weighted_expr,
)

# ── Работодатели ───────────────────────────────────────────────────────────
@login_required
def employers_list(request):
    qs = (
        Profile.objects.public_visible()
        .annotate(open_jobs=Count("jobs", filter=Q(jobs__status="open")))
        .filter(open_jobs__gt=0)
    )
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(full_name__icontains=q) | Q(city__icontains=q) | Q(bio__icontains=q)
        ).distinct()
    city = (request.GET.get("city") or "").strip()
    if city:
        qs = qs.filter(city__icontains=city)
    qs = qs.exclude(
        pk__in=Blacklist.objects.filter(blocked_user=request.user).values("user_id")
    )
    sort = request.GET.get("sort") or "rating"
    if sort == "name":
        qs = qs.order_by("full_name")
    elif sort == "jobs_count":
        qs = qs.order_by("-open_jobs", "-employer_rating", "-employer_ratings_count")
    else:
        sort = "rating"
        qs = qs.annotate(
            weighted_rating=weighted_expr("employer_rating", "employer_ratings_count")
        ).order_by("-weighted_rating", "-employer_ratings_count", "-created_at")
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    favorited_ids = set(
        Favorite.objects.filter(
            user=request.user, favorite_type="employer"
        ).values_list("target_id", flat=True)
    )
    return render(request, "core/employers.html", {
        "page": page, "q": q, "city": city, "sort": sort,
        "favorited_ids": favorited_ids,
    })


@login_required
@require_POST
def employer_favorite_toggle(request, employer_id):
    employer = Profile.objects.public_visible().filter(pk=employer_id).first()
    if employer is None or employer.pk == request.user.pk:
        messages.error(request, _("Работодатель недоступен."))
    else:
        fav, created = Favorite.objects.get_or_create(
            user=request.user, target=employer, favorite_type="employer",
        )
        if created:
            messages.success(request, _("Работодатель добавлен в избранное."))
        else:
            fav.delete()
            messages.info(request, _("Работодатель удалён из избранного."))
    return redirect(safe_referer(request, reverse("core:employers")))


@login_required
def employer_detail(request, employer_id):
    profile = Profile.objects.public_visible().filter(pk=employer_id).first()
    if profile is None:
        raise Http404("Работодатель не найден")
    if Blacklist.objects.filter(user=profile, blocked_user=request.user).exists():
        raise Http404("Работодатель не найден")
    jobs = list(
        Job.objects.public().filter(employer=profile, status="open").order_by("-created_at")
    )
    ratings = (
        public_ratings(profile.pk, "employer")
        .select_related("rater_user", "job").order_by("-published_at")[:10]
    )
    metrics = profile_metrics(profile.pk, profile.role)
    is_favorited = Favorite.objects.filter(
        user=request.user, target=profile, favorite_type="employer"
    ).exists()
    already_applied_job_ids = set(
        Application.objects.filter(worker=request.user, job__in=jobs)
        .values_list("job_id", flat=True)
    )
    return render(request, "core/employer_detail.html", {
        "p": profile, "jobs": jobs, "ratings": ratings,
        "distribution": rating_distribution(profile.pk, "employer"),
        "recent": recent_rating(profile.pk, "employer"),
        "metrics": metrics,
        "is_reliable": reliable_badge(profile, metrics),
        "review_criteria_labels": criteria_labels("employer"),
        "review_tag_labels": tag_labels("employer"),
        "employer_card": EmployerDetail.objects.filter(user=profile).first(),
        "is_favorited": is_favorited,
        "already_applied_job_ids": already_applied_job_ids,
    })
