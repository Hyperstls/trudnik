"""Остаток паритета Flask: работодатели, просмотр оценок, rate-workers,
массовые отклики (apply-selected), reject-all приглашений, FAQ, sitemap,
загрузка фото задания.

Контракты: employers_bp (список/карточка), ratings_bp (/ratings/user/<id>,
/jobs/<job_id>/rate-workers), applications (/apply-selected ≤ лимит),
invitations (/api/invitations/reject-all), jobs (photo upload).
"""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import Application, Invitation, Job, JobPhoto, Profile, Rating, UserReport
from .notifications import enqueue_notification
from .rpc import call_rpc
from .storage import UploadError, delete_upload_url, save_upload
from .views import job_photo_urls

BULK_LIMIT = 20
SKIPPED_APPLY_CODES = {
    "duplicate", "already_applied", "no_slots", "job_not_open",
    "own_job", "job_expired", "job_in_past",
}


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
    applied = skipped = failed = 0
    employer_jobs = {}
    for job_id in ids:
        try:
            job = Job.objects.public().filter(pk=job_id).first()
        except (ValidationError, ValueError):
            failed += 1
            continue
        if job is None:
            failed += 1
            continue
        if job.employer_id == request.user.pk:
            skipped += 1
            continue
        if apply:
            try:
                result = call_rpc("apply_job_atomic", job.pk, request.user.pk) or {}
            except Exception:
                failed += 1
                continue
            if result.get("success"):
                applied += 1
                employer_id = str(result.get("employer_id") or job.employer_id)
                employer_jobs.setdefault(employer_id, []).append(str(job.pk))
            elif result.get("code") in SKIPPED_APPLY_CODES:
                skipped += 1
            else:
                failed += 1
        else:
            app_obj = (
                Application.objects.filter(job=job, worker=request.user)
                .exclude(status__in=("withdrawn", "cancelled")).first()
            )
            if app_obj is None:
                skipped += 1
                continue
            try:
                result = call_rpc("withdraw_application_atomic", app_obj.pk, request.user.pk) or {}
            except Exception:
                failed += 1
                continue
            if result.get("success"):
                applied += 1
            else:
                failed += 1
    for employer_id, job_ids in employer_jobs.items():
        enqueue_notification(
            employer_id, "application_received", "Новые отклики",
            "На ваши задания поступили новые отклики",
            {
                "job_ids": job_ids,
                "link": request.build_absolute_uri(reverse("core:my_applications")),
            },
        )
    messages.info(
        request,
        "Выполнено: %d, пропущено: %d, ошибок: %d." % (applied, skipped, failed),
    )
    referer = request.META.get("HTTP_REFERER") or ""
    if not url_has_allowed_host_and_scheme(referer, allowed_hosts={request.get_host()}):
        referer = "/jobs"
    return redirect(referer)


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
    if len(job_photo_urls(job)) >= 3:
        messages.error(request, "Можно добавить не более 3 фото.")
        return redirect("core:job_edit", job_id=job.pk)
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
    photo = JobPhoto.objects.filter(
        pk=photo_id, job_id=job_id, job__employer=request.user
    ).first()
    if photo:
        url = photo.photo_url
        photo.delete()
        # Файл общий, если на него ссылаются другие JobPhoto/legacy photo_urls.
        still_used = (
            JobPhoto.objects.filter(photo_url=url).exists()
            or Job.objects.filter(photo_urls__contains=[url]).exists()
        )
        if not still_used:
            delete_upload_url(url)
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

# ── Перепубликация (repost-job) ────────────────────────────────────────────
@login_required
@require_POST
def repost_job(request, job_id):
    """Копия задания (контракт app/utils/business.py copy_job)."""
    from django.db import connection as _c
    from django.utils import timezone

    job = Job.objects.filter(pk=job_id, employer=request.user).first()
    if job is None:
        raise Http404("Задание не найдено")
    with transaction.atomic():
        new_job = Job.objects.create(
            employer=request.user,
            organization_name=job.organization_name,
            org_description=job.org_description,
            object_description=job.object_description,
            work_type=job.work_type,
            detailed_description=job.detailed_description,
            date_time=job.date_time if job.date_time > timezone.now() else timezone.now() + timedelta(days=1),
            payment_amount=job.payment_amount,
            address=job.address,
            city=job.city,
            lat=job.lat,
            lng=job.lng,
            status="open",
            is_paid=False,
            tariff=job.tariff or "Базовый",
            max_workers=job.max_workers or 1,
            current_workers=0,
            expires_at=timezone.now() + timedelta(days=30),
            photo_urls=list(job.photo_urls or []),
        )
        photos = list(job.photos.all())
        if photos:
            JobPhoto.objects.bulk_create([
                JobPhoto(job=new_job, photo_url=p.photo_url, order_num=p.order_num)
                for p in photos
            ])
        with _c.cursor() as cur:
            cur.execute(
                "INSERT INTO job_skills (job_id, skill_id) "
                "SELECT %s, skill_id FROM job_skills WHERE job_id = %s ON CONFLICT DO NOTHING",
                [new_job.pk, job.pk],
            )
    messages.success(request, "Задание перепубликовано.")
    return redirect("core:job_detail", job_id=new_job.pk)
