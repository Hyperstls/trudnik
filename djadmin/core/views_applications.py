"""Отклики на задания и избранное.

Инварианты: user_id берётся из request.user (IDOR невозможен), мутации — только
через SECURITY DEFINER RPC, скрытые/чужие объекты ведут себя как несуществующие.
"""
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .analytics import incr
from .anti_fraud import allow_application
from .models import Application, Job, JobFavorite, Rating, Skill
from .notifications import enqueue_notification
from .ratelimit import rate_limit_write
from .rpc import call_rpc
from .views_flow import _bulk_ids, _public_job_or_none, _rpc_message, _safe_back


# ── Отклики ─────────────────────────────────────────────────────────────────
@login_required
@require_POST
@rate_limit_write(limit=10, window=60)
def job_apply(request, job_id):
    job = _public_job_or_none(job_id)
    if job is None or job.employer_id == request.user.pk:
        messages.error(request, _("Задание не найдено или отклик невозможен."))
        return redirect("core:jobs")
    if not allow_application(request.user.pk):
        messages.error(
            request,
            _("Дневной лимит откликов исчерпан. Попробуйте снова завтра."),
        )
        return redirect("core:job_detail", job_id=job.pk)
    result = call_rpc("apply_job_atomic", job.pk, request.user.pk) or {}
    ok = _rpc_message(request, result, _("Отклик отправлен."))
    if ok:
        incr("application_sent")
        enqueue_notification(
            job.employer_id, "application_received", _("Новый отклик"),
            _("На ваше задание поступил новый отклик"),
            {
                "job_id": str(job.pk),
                "link": request.build_absolute_uri(
                    reverse("core:job_detail", args=[job.pk])
                ),
            },
        )
        return redirect(reverse("core:job_detail", args=[job.pk]) + "?push=1")
    return redirect("core:job_detail", job_id=job.pk)


@login_required
@require_POST
def job_unapply(request, job_id):
    application = Application.objects.filter(job_id=job_id, worker=request.user).exclude(
        status__in=("withdrawn", "cancelled")
    ).first()
    if application is None:
        messages.error(request, _("Активного отклика нет."))
        return redirect("core:job_detail", job_id=job_id)
    result = call_rpc("withdraw_application_atomic", application.pk, request.user.pk) or {}
    _rpc_message(request, result, _("Отклик отозван."))
    return redirect("core:job_detail", job_id=job_id)


@login_required
def my_applications(request):
    tab = request.GET.get("tab")
    if tab not in ("received", "sent"):
        # Паритет Flask: у кого есть свои задания — сразу в «Полученные».
        tab = "received" if Job.objects.filter(employer=request.user).exists() else "sent"
    skill_ids = []
    for raw in request.GET.getlist("skills"):
        for part in raw.split(","):
            try:
                skill_ids.append(UUID(part.strip()))
            except (TypeError, ValueError):
                continue
    skill_ids = list(dict.fromkeys(skill_ids))
    if tab == "received":
        qs = (
            Application.objects.filter(job__employer=request.user)
            .select_related("job", "worker")
            .prefetch_related("worker__user_skills__skill")
        )
        if skill_ids:
            qs = qs.filter(worker__user_skills__skill_id__in=skill_ids).distinct()
    else:
        qs = Application.objects.filter(worker=request.user).select_related("job")
        if skill_ids:
            qs = qs.filter(job__job_skills__skill_id__in=skill_ids).distinct()
    page = Paginator(qs.order_by("-created_at"), 20).get_page(request.GET.get("page"))
    apps = list(page.object_list)
    if apps:
        job_ids = {app.job_id for app in apps}
        rated_ids = {
            app.worker_id if tab == "received" else app.job.employer_id
            for app in apps
        }
        ratings = Rating.objects.filter(
            rater_user=request.user, job_id__in=job_ids, rated_user_id__in=rated_ids,
        )
        by_pair = {(rating.job_id, rating.rated_user_id): rating for rating in ratings}
        for app in apps:
            rated_id = app.worker_id if tab == "received" else app.job.employer_id
            app.my_rating = by_pair.get((app.job_id, rated_id))
    return render(request, "core/my_applications.html", {
        "page": page,
        "apps": apps,
        "tab": tab,
        "skills": list(Skill.objects.order_by("sort_order", "name")),
        "selected_skills": [str(skill_id) for skill_id in skill_ids],
    })


@login_required
@require_POST
@rate_limit_write(limit=10, window=60, redirect_to="/my-applications")
def worker_confirm_completion(request, app_id):
    """Accepted worker marks the work as done; employer still completes the job."""
    application = (
        Application.objects.select_related("job")
        .filter(pk=app_id, worker=request.user)
        .first()
    )
    if application is None or application.status != Application.Status.ACCEPTED:
        messages.error(request, _("Можно отметить только принятый отклик."))
        return redirect(reverse("core:my_applications") + "?tab=sent")
    result = call_rpc(
        "worker_confirm_completion", application.pk, request.user.pk
    ) or {}
    ok = _rpc_message(request, result, _("Выполнение отмечено. Работодатель увидит это."))
    if ok:
        job = application.job
        enqueue_notification(
            job.employer_id,
            "worker_completed",
            _("Трудник отметил выполнение"),
            _("Трудник отметил, что работа по заданию выполнена."),
            {
                "job_id": str(job.pk),
                "link": request.build_absolute_uri(
                    reverse("core:job_applicants", args=[job.pk])
                ),
            },
        )
    return redirect(reverse("core:my_applications") + "?tab=sent")


@login_required
def job_applicants(request, job_id):
    """Отклики на своё задание (владелец или админ)."""
    job = Job.objects.filter(pk=job_id).first()
    if job is None or (job.employer_id != request.user.pk and request.user.role != "admin"):
        raise Http404("Задание не найдено")
    apps = list(
        Application.objects.filter(job=job)
        .select_related("job", "worker").order_by("-created_at")
    )
    existing = {
        rating.rated_user_id: rating
        for rating in Rating.objects.filter(rater_user=request.user, job=job)
    }
    for app in apps:
        app.my_rating = existing.get(app.worker_id)
    return render(request, "core/job_applicants.html", {"job": job, "apps": apps})


@login_required
@require_POST
def application_action(request, app_id, action):
    """accept / reject (работодатель), withdraw (работник), cancel (работодатель)."""
    if action not in ("accept", "reject", "reopen", "cancel", "withdraw"):
        return HttpResponseNotAllowed(["POST"])
    application = Application.objects.select_related("job").filter(pk=app_id).first()
    if application is None:
        messages.error(request, _("Отклик не найден."))
        return redirect("core:jobs")
    job = application.job
    user = request.user
    result = {}
    if action == "withdraw":  # свой отклик
        if application.worker_id != user.pk:
            return redirect("core:jobs")
        result = call_rpc("withdraw_application_atomic", application.pk, user.pk) or {}
        ok_text = _("Отклик отозван.")
    else:
        if job.employer_id != user.pk and user.role != "admin":
            return redirect("core:jobs")
        if action == "accept":
            result = call_rpc("accept_application", job.pk, application.pk) or {}
            ok_text = _("Отклик принят.")
        elif action == "reject":
            result = call_rpc("reject_application", job.pk, application.pk) or {}
            ok_text = _("Отклик отклонён.")
        elif action == "cancel":  # работодатель снимает конкретного работника
            result = call_rpc("cancel_worker_atomic", application.pk, user.pk) or {}
            ok_text = _("Работник снят с задания.")
        elif action == "reopen":  # паритет Flask: reopen делегирует в accept-RPC
            result = call_rpc("accept_application", job.pk, application.pk) or {}
            ok_text = _("Отклик принят повторно.")
    ok = _rpc_message(request, result, ok_text)
    if ok and action in ("accept", "reject", "reopen"):
        accepted = action != "reject"
        enqueue_notification(
            application.worker_id,
            "application_accepted" if accepted else "application_rejected",
            _("Отклик принят") if accepted else _("Отклик отклонён"),
            _("Ваш отклик на задание #%s был %s") % (
                job.pk, _("принят") if accepted else _("отклонён"),
            ),
            {
                "job_id": str(job.pk),
                "link": request.build_absolute_uri(reverse("core:my_applications")),
            },
        )
    return redirect("core:job_applicants", job_id=job.pk)


@login_required
@require_POST
def my_applications_bulk(request):
    """Массовые accept/reject/reopen откликов на свои задания (≤50)."""
    action = request.POST.get("action")
    if action not in ("accept", "reject", "reopen"):
        return HttpResponseNotAllowed(["POST"])
    app_ids = _bulk_ids(request.POST.getlist("app_ids"))
    if not app_ids:
        messages.error(request, _("Не выбрано ни одного отклика."))
        return redirect("core:my_applications")
    apps = list(
        Application.objects.filter(
            pk__in=app_ids, job__employer=request.user
        ).select_related("job")
    )
    done = skipped = 0
    for app in apps:
        if action == "reopen" and app.status != Application.Status.REJECTED:
            skipped += 1
            continue
        if action == "reject":
            result = call_rpc("reject_application", app.job_id, app.pk) or {}
        else:
            result = call_rpc("accept_application", app.job_id, app.pk) or {}
        if not result.get("success"):
            skipped += 1
            continue
        done += 1
        accepted = action != "reject"
        enqueue_notification(
            app.worker_id,
            "application_accepted" if accepted else "application_rejected",
            _("Отклик принят") if accepted else _("Отклик отклонён"),
            _("Ваш отклик на задание #%s был %s") % (
                app.job_id, _("принят") if accepted else _("отклонён"),
            ),
            {
                "job_id": str(app.job_id),
                "link": request.build_absolute_uri(reverse("core:my_applications")),
            },
        )
    if done:
        messages.success(request, _("Выполнено: %d.") % done)
    if skipped:
        messages.warning(request, _("Пропущено/ошибок: %d.") % skipped)
    return redirect(reverse("core:my_applications") + "?tab=received")



# ── Избранное заданий ───────────────────────────────────────────────────────
@login_required
@require_POST
def job_favorite_toggle(request, job_id):
    # только публично видимые задания (без оракула существования скрытых)
    if not Job.objects.public().filter(pk=job_id).exists():
        messages.error(request, _("Задание не найдено."))
        return redirect("core:jobs")
    fav, created = JobFavorite.objects.get_or_create(user=request.user, job_id=job_id)
    if not created:
        fav.delete()
        messages.info(request, _("Удалено из избранного."))
    else:
        messages.success(request, _("Добавлено в избранное."))
    return redirect(_safe_back(request, reverse("core:jobs")))


@login_required
def favorite_jobs(request):
    favs = (
        JobFavorite.objects.filter(user=request.user)
        .select_related("job").order_by("-created_at")
    )
    return render(request, "core/favorite_jobs.html", {"favs": favs})
