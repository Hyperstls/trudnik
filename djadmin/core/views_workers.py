"""Каталог и карточка работника.

RLS-паритет: Django ходит в БД напрямую (роль с BYPASSRLS), поэтому видимость
профилей фильтруется явно — Profile.objects.public_workers()/public_visible().
Карточка отдаёт только PUBLIC_PROFILE_FIELDS (без email/phone/inn).
"""
from decimal import Decimal
from uuid import UUID

from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.http import Http404
from django.shortcuts import render

from .models import (
    Application, Favorite, Invitation, Job, Profile, Skill, UserReport, UserSkill,
)
from .reputation import (
    criteria_labels, profile_metrics, public_ratings, rating_distribution,
    recent_rating, reliable_badge, tag_labels, weighted_expr,
)
from .search import ts_query
from .views import PAGE_SIZE

# Публичные колонки профиля (паритет колоночных грантов RLS, миграция 132)
PUBLIC_PROFILE_FIELDS = (
    "id", "full_name", "avatar_url", "photo_url", "age", "bio", "city",
    "experience", "desired_payment", "verification_status", "rating",
    "total_reviews", "ratings_count", "worker_rating", "worker_ratings_count",
    "employer_rating", "employer_ratings_count", "portfolio_link", "is_self_employed",
    "created_at",
)
# contact/email_public/religion_id — НЕ публичные (152-ФЗ, P0-03/P0-04):
# контакты открываются после отклика на задание, вероисповедание — спецкатегория.

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
        qs = qs.filter(worker_rating__gte=rating_value)
    payment_from = request.GET.get("payment_from") or ""
    payment_to = request.GET.get("payment_to") or ""
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
    if sort == "name":
        qs = qs.order_by("full_name")
    elif sort == "price_asc":
        qs = qs.order_by(F("desired_payment").asc(nulls_last=True))
    elif sort == "price_desc":
        qs = qs.order_by(F("desired_payment").desc(nulls_last=True))
    else:
        sort = "rating"
        qs = qs.annotate(
            weighted_rating=weighted_expr("worker_rating", "worker_ratings_count")
        ).order_by("-weighted_rating", "-worker_ratings_count", "-created_at")
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    worker_ids = [w.pk for w in page.object_list]
    reliable_worker_ids = set()
    invited_worker_ids = set()
    pending_invited_worker_ids = set()
    pending_invitations_by_worker = {}
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
    completed_by_id = {}
    if worker_ids:
        accepted_counts = dict(
            Application.objects.filter(
                worker_id__in=worker_ids, status=Application.Status.ACCEPTED,
            ).values_list("worker_id").annotate(total=Count("id"))
        )
        completed_counts = dict(
            Application.objects.filter(
                worker_id__in=worker_ids,
                status=Application.Status.ACCEPTED,
                job__status=Job.Status.COMPLETED,
            ).values_list("worker_id").annotate(total=Count("id"))
        )
        report_counts = dict(
            UserReport.objects.filter(reported_id__in=worker_ids)
            .exclude(status="reviewed")
            .values_list("reported_id").annotate(total=Count("id"))
        )
        for worker in page.object_list:
            completed = completed_counts.get(worker.pk, 0)
            accepted = accepted_counts.get(worker.pk, 0)
            completed_by_id[worker.pk] = completed
            metrics = {
                "completed_jobs": completed,
                "completion_rate": round(completed / accepted * 100) if accepted else 0,
                "open_reports": report_counts.get(worker.pk, 0),
            }
            if reliable_badge(worker, metrics):
                reliable_worker_ids.add(worker.pk)
        if request.user.is_authenticated:
            invitation_rows = list(
                Invitation.objects.filter(
                    employer=request.user,
                    worker_id__in=worker_ids,
                    status__in=("pending", "accepted"),
                ).select_related("job")
            )
            invited_worker_ids = {inv.worker_id for inv in invitation_rows}
            pending_invited_worker_ids = {
                inv.worker_id for inv in invitation_rows
                if inv.status == Invitation.Status.PENDING
            }
            for inv in invitation_rows:
                if inv.status == Invitation.Status.PENDING:
                    pending_invitations_by_worker.setdefault(inv.worker_id, []).append(inv)
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
        "completed_by_id": completed_by_id,
        "invited_worker_ids": invited_worker_ids,
        "pending_invited_worker_ids": pending_invited_worker_ids,
        "pending_invitations_by_worker": pending_invitations_by_worker,
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
    skills = list(
        UserSkill.objects.filter(user_id=profile["id"]).select_related("skill")
        .values_list("skill__name", flat=True)
    )
    context = {"p": profile, "skills": skills}
    context["ratings"] = list(
        public_ratings(profile["id"], "worker")
        .select_related("rater_user", "job").order_by("-published_at")[:5]
    )
    profile_obj = Profile.objects.filter(pk=profile["id"]).first()
    metrics = profile_metrics(profile["id"], Profile.Role.WORKER)
    context.update({
        "distribution": rating_distribution(profile["id"], "worker"),
        "recent": recent_rating(profile["id"], "worker"),
        "metrics": metrics,
        "is_reliable": reliable_badge(profile_obj, metrics) if profile_obj else False,
        "review_criteria_labels": criteria_labels("worker"),
        "review_tag_labels": tag_labels("worker"),
    })
    if request.user.is_authenticated and profile["id"] != request.user.pk:
        my_open_jobs = list(
            Job.objects.filter(employer=request.user, status=Job.Status.OPEN)
            .order_by("date_time").values("id", "work_type", "date_time")[:20]
        )
        pending_invitations = list(
            Invitation.objects.filter(
                employer=request.user, worker_id=profile["id"],
                status=Invitation.Status.PENDING,
            ).select_related("job").order_by("-created_at")
        )
        invited_job_ids = {inv.job_id for inv in pending_invitations}
        context["my_open_jobs"] = [
            j for j in my_open_jobs if j["id"] not in invited_job_ids
        ]
        context["is_fav_person"] = Favorite.objects.filter(
            user=request.user, target_id=profile["id"]
        ).exists()
        context["pending_invitations"] = pending_invitations
    return render(request, "core/worker_detail.html", context)
