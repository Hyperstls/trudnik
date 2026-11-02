"""Global search across public jobs, workers and employers (J119)."""
from django.db.models import Count, Q
from django.shortcuts import render

from .models import Blacklist, Job, Profile


def global_search(request):
    query = (request.GET.get("q") or "").strip()[:100]
    too_short = bool(query) and len(query) < 2
    jobs = []
    workers = []
    employers = []
    if len(query) >= 2:
        jobs_qs = Job.objects.public().filter(
            Q(work_type__icontains=query)
            | Q(organization_name__icontains=query)
            | Q(city__icontains=query)
            | Q(detailed_description__icontains=query)
            | Q(object_description__icontains=query)
        ).order_by("-created_at")
        workers_qs = Profile.objects.public_workers().filter(
            Q(full_name__icontains=query)
            | Q(city__icontains=query)
            | Q(bio__icontains=query)
        ).prefetch_related("user_skills__skill").order_by("-rating", "-total_reviews")
        employers_qs = None
        if request.user.is_authenticated:
            employers_qs = (
                Profile.objects.public_visible()
                .select_related("employer_detail")
                .annotate(open_jobs=Count("jobs", filter=Q(jobs__status="open")))
                .filter(open_jobs__gt=0)
                .filter(
                    Q(full_name__icontains=query)
                    | Q(employer_detail__name__icontains=query)
                    | Q(city__icontains=query)
                    | Q(bio__icontains=query)
                )
                .order_by("-rating", "-total_reviews")
            )
            blocked_ids = Blacklist.objects.filter(
                blocked_user=request.user
            ).values("user_id")
            jobs_qs = jobs_qs.exclude(employer_id__in=blocked_ids)
            employers_qs = employers_qs.exclude(pk__in=blocked_ids)
        jobs = list(jobs_qs[:8])
        workers = list(workers_qs[:6])
        if employers_qs is not None:
            employers = list(employers_qs[:6])
    total = len(jobs) + len(workers) + len(employers)
    return render(request, "core/search.html", {
        "q": query,
        "too_short": too_short,
        "jobs": jobs,
        "workers": workers,
        "employers": employers,
        "total": total,
    })
