"""Остаток паритета Flask: работодатели, просмотр оценок, rate-workers,
массовые отклики (apply-selected), reject-all приглашений, FAQ, sitemap,
загрузка фото задания.

Контракты: employers_bp (список/карточка), ratings_bp (/ratings/user/<id>,
/jobs/<job_id>/rate-workers), applications (/apply-selected ≤ лимит),
invitations (/api/invitations/reject-all), jobs (photo upload).
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Application, Invitation, Job, JobPhoto, Profile, Rating, UserReport
from .rpc import call_rpc
from .storage import UploadError, save_upload

BULK_LIMIT = 20


# ── Работодатели ───────────────────────────────────────────────────────────
@login_required
def employers_list(request):
    qs = (
        Profile.objects.public_visible()
        .filter(role="employer")
        .annotate(open_jobs=Count("jobs", filter=Q(jobs__status="open")))
        .order_by("-rating", "-total_reviews")
    )
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(city__icontains=q)).distinct()
    from django.core.paginator import Paginator

    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "core/employers.html", {"page": page, "q": q})


@login_required
def employer_detail(request, employer_id):
    profile = Profile.objects.public_visible().filter(pk=employer_id, role="employer").first()
    if profile is None:
        raise Http404("Работодатель не найден")
    jobs = Job.objects.public().filter(employer=profile).order_by("-created_at")[:12]
    ratings = (
        Rating.objects.filter(rated_user=profile).select_related("rater_user", "job")
        .order_by("-created_at")[:10]
    )
    return render(request, "core/employer_detail.html", {
        "p": profile, "jobs": jobs, "ratings": ratings,
    })


# ── Оценки ─────────────────────────────────────────────────────────────────
def user_ratings(request, user_id):
    profile = Profile.objects.public_visible().filter(pk=user_id).first()
    if profile is None:
        raise Http404("Профиль не найден")
    ratings = (
        Rating.objects.filter(rated_user=profile).select_related("rater_user", "job")
        .order_by("-created_at")[:50]
    )
    return render(request, "core/user_ratings.html", {"p": profile, "ratings": ratings})


@login_required
def rate_workers(request, job_id):
    """Страница оценки принятых работников завершённого задания (владелец)."""
    job = Job.objects.filter(pk=job_id, employer=request.user).first()
    if job is None:
        raise Http404("Задание не найдено")
    apps = Application.objects.filter(job=job, status="accepted").select_related("worker")
    existing = {
        r.rated_user_id: r.rating
        for r in Rating.objects.filter(rater_user=request.user, job=job)
    }
    return render(request, "core/rate_workers.html", {
        "job": job, "apps": apps, "existing": existing, "now": timezone.now(),
    })


# ── Массовые отклики с ленты (apply-selected / unapply-selected) ──────────
@login_required
@require_POST
def bulk_apply(request):
    return _bulk(request, apply=True)


@login_required
@require_POST
def bulk_unapply(request):
    return _bulk(request, apply=False)


def _bulk(request, apply: bool):
    raw = request.POST.getlist("job_ids")
    ids = [x for x in raw if x][:BULK_LIMIT]
    done = failed = 0
    for job_id in ids:
        job = Job.objects.public().filter(pk=job_id).first()
        if job is None or job.employer_id == request.user.pk:
            failed += 1
            continue
        if apply:
            result = call_rpc("apply_job_atomic", job.pk, request.user.pk) or {}
        else:
            app_obj = (
                Application.objects.filter(job=job, worker=request.user)
                .exclude(status__in=("withdrawn", "cancelled")).first()
            )
            if app_obj is None:
                failed += 1
                continue
            result = call_rpc("withdraw_application_atomic", app_obj.pk, request.user.pk) or {}
        if result.get("success"):
            done += 1
        else:
            failed += 1
    messages.info(request, "Выполнено: %d, пропущено: %d." % (done, failed))
    return redirect(request.META.get("HTTP_REFERER") or "/jobs")


# ── Приглашения: отклонить все ─────────────────────────────────────────────
@login_required
@require_POST
def invitations_reject_all(request):
    count = Invitation.objects.filter(
        worker=request.user, status=Invitation.Status.PENDING
    ).update(status=Invitation.Status.REJECTED, responded_at=timezone.now())
    messages.info(request, "Отклонено приглашений: %d." % count)
    return redirect("core:invitations")


# ── Фото задания ───────────────────────────────────────────────────────────
@login_required
@require_POST
def job_photo_upload(request, job_id):
    job = Job.objects.filter(pk=job_id, employer=request.user).first()
    if job is None:
        raise Http404("Задание не найдено")
    file = request.FILES.get("photo")
    if file is None:
        messages.error(request, "Файл не выбран.")
        return redirect("core:job_edit", job_id=job.pk)
    try:
        url = save_upload(file, "jobs")
    except UploadError as exc:
        messages.error(request, str(exc))
        return redirect("core:job_edit", job_id=job.pk)
    last_order = JobPhoto.objects.filter(job=job).count()
    JobPhoto.objects.create(job=job, photo_url=url, order_num=last_order)
    messages.success(request, "Фото добавлено.")
    return redirect("core:job_edit", job_id=job.pk)


@login_required
@require_POST
def job_photo_delete(request, job_id, photo_id):
    deleted, _ = JobPhoto.objects.filter(pk=photo_id, job_id=job_id, job__employer=request.user).delete()
    if deleted:
        messages.info(request, "Фото удалено.")
    return redirect("core:job_edit", job_id=job_id)


# ── FAQ / sitemap ─────────────────────────────────────────────────────────
def faq(request):
    return render(request, "core/faq.html")


def sitemap(request):
    from .models import SitePage

    base = "https://xn--d1aigknli.xn--p1ai"
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    parts.append("<url><loc>%s/jobs</loc></url>" % base)
    parts.append("<url><loc>%s/workers</loc></url>" % base)
    for job in Job.objects.public().order_by("-created_at")[:500]:
        parts.append("<url><loc>%s/jobs/%s</loc></url>" % (base, job.pk))
    for page in SitePage.objects.all():
        parts.append("<url><loc>%s/%s</loc></url>" % (base, page.slug))
    parts.append("</urlset>")
    return HttpResponse("\n".join(parts), content_type="application/xml")
