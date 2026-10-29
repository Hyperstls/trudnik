"""Интерактивные флоу фазы 2а: вход/выход, задания, отклики, избранное.

Инварианты:
- user_id/employer_id всегда из request.user (не из формы) — IDOR невозможен;
- мутации бизнес-состояний — только SECURITY DEFINER RPC (контракт
  {'success': bool, 'error': code}); RPC-инварианты не дублируются в Python;
- прямой доступ к «чужому» — 404 (не раскрываем существование).
"""
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import JobForm
from .models import Application, Job, JobFavorite
from .rpc import call_rpc, sync_job_skills_raw

RPC_ERROR_TEXT = {
    "not_found": "Не найдено или недоступно.",
    "job_not_open": "Задание не открыто для откликов.",
    "no_slots": "Все места уже заняты.",
    "bad_status": "Недопустимый статус для этого действия.",
    "already_applied": "Вы уже откликнулись на это задание.",
    "expired": "Задание истекло.",
    "past_date": "Дата работ уже в прошлом.",
    "self_apply": "Нельзя откликнуться на собственное задание.",
    "not_owner": "Недостаточно прав.",
}


def _rpc_message(request, result: dict, ok_text: str = "Готово.") -> bool:
    if result.get("success"):
        messages.success(request, ok_text)
        return True
    code = result.get("error") or result.get("code") or "unknown"
    messages.error(request, RPC_ERROR_TEXT.get(code, "Действие отклонено: %s" % code))
    return False


# ── Вход / выход ────────────────────────────────────────────────────────────
def login_view(request):
    from .forms import LoginForm

    if request.user.is_authenticated:
        return redirect("/")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data["email"].strip().lower(),
            password=form.cleaned_data["password"],
        )
        if user is not None:
            auth_login(request, user)
            nxt = request.GET.get("next") or request.POST.get("next")
            return redirect(nxt if nxt and nxt.startswith("/") else "/")
        messages.error(request, "Неверный email или пароль, либо аккаунт заблокирован/не подтверждён.")
    return render(request, "core/login.html", {"form": form})


@require_POST
def logout_view(request):
    auth_logout(request)
    messages.info(request, "Вы вышли.")
    return redirect("core:jobs")


# ── Задания: создание/редактирование ───────────────────────────────────────
@login_required
def job_create(request):
    form = JobForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            job = form.save(commit=False)
            job.employer = request.user
            job.status = Job.Status.OPEN
            job.save()
            sync_job_skills_raw(job.pk, [s.pk for s in form.cleaned_data["skills"]])
        messages.success(request, "Задание создано.")
        return redirect("core:job_detail", job_id=job.pk)
    return render(request, "core/job_form.html", {"form": form, "title": "Новое задание"})


@login_required
def job_edit(request, job_id):
    job = get_object_or_404(Job, pk=job_id, employer=request.user)
    form = JobForm(request.POST or None, instance=job)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            job = form.save()
            sync_job_skills_raw(job.pk, [s.pk for s in form.cleaned_data["skills"]])
        messages.success(request, "Задание обновлено.")
        return redirect("core:job_detail", job_id=job.pk)
    return render(request, "core/job_form.html", {"form": form, "title": "Редактирование задания"})


@login_required
def my_jobs(request):
    jobs = Job.objects.filter(employer=request.user).order_by("-created_at")
    return render(request, "core/my_jobs.html", {"jobs": jobs})


@login_required
@require_POST
def job_action(request, job_id, action):
    """cancel / restore / force_complete / delete — всё через RPC от имени владельца."""
    job = get_object_or_404(Job, pk=job_id, employer=request.user)
    uid = request.user.pk
    if action == "cancel":
        ok = _rpc_message(request, call_rpc("cancel_job_atomic", job.pk, uid) or {}, "Задание отменено.")
    elif action == "restore":
        ok = _rpc_message(request, call_rpc("restore_job_atomic", job.pk, uid) or {}, "Задание восстановлено.")
    elif action == "force_complete":
        ok = _rpc_message(request, call_rpc("force_complete_job", job.pk, uid) or {}, "Задание завершено.")
    elif action == "delete":
        ok = _rpc_message(request, call_rpc("delete_job_cascade", job.pk) or {}, "Задание удалено.")
    else:
        return HttpResponseNotAllowed([])
    if action == "delete" and ok:
        return redirect("core:my_jobs")
    return redirect(request.META.get("HTTP_REFERER") or reverse("core:my_jobs"))


# ── Отклики ─────────────────────────────────────────────────────────────────
@login_required
@require_POST
def job_apply(request, job_id):
    job = Job.objects.filter(pk=job_id).first()
    if job is None or job.employer_id == request.user.pk:
        messages.error(request, "Отклик невозможен.")
        return redirect("core:jobs")
    result = call_rpc("apply_job_atomic", job.pk, request.user.pk) or {}
    _rpc_message(request, result, "Отклик отправлен.")
    return redirect("core:job_detail", job_id=job.pk)


@login_required
@require_POST
def job_unapply(request, job_id):
    application = Application.objects.filter(job_id=job_id, worker=request.user).exclude(
        status__in=("withdrawn", "cancelled")
    ).first()
    if application is None:
        messages.error(request, "Активного отклика нет.")
        return redirect("core:job_detail", job_id=job_id)
    result = call_rpc("withdraw_application_atomic", application.pk, request.user.pk) or {}
    _rpc_message(request, result, "Отклик отозван.")
    return redirect("core:job_detail", job_id=job_id)


@login_required
def my_applications(request):
    apps = (
        Application.objects.filter(worker=request.user)
        .select_related("job").order_by("-created_at")
    )
    return render(request, "core/my_applications.html", {"apps": apps})


@login_required
def job_applicants(request, job_id):
    """Отклики на своё задание (владелец или админ)."""
    job = Job.objects.filter(pk=job_id).first()
    if job is None or (job.employer_id != request.user.pk and request.user.role != "admin"):
        raise Http404("Задание не найдено")
    apps = (
        Application.objects.filter(job=job)
        .select_related("worker").order_by("-created_at")
    )
    return render(request, "core/job_applicants.html", {"job": job, "apps": apps})


@login_required
@require_POST
def application_action(request, app_id, action):
    """accept / reject (работодатель), withdraw (работник), cancel (работодатель)."""
    application = Application.objects.select_related("job").filter(pk=app_id).first()
    if application is None:
        messages.error(request, "Отклик не найден.")
        return redirect("core:jobs")
    job = application.job
    user = request.user
    result = {}
    if action == "withdraw":  # свой отклик
        if application.worker_id != user.pk:
            return redirect("core:jobs")
        result = call_rpc("withdraw_application_atomic", application.pk, user.pk) or {}
        ok_text = "Отклик отозван."
    elif action in ("accept", "reject", "reopen", "cancel"):
        if job.employer_id != user.pk and user.role != "admin":
            return redirect("core:jobs")
        if action == "accept":
            result = call_rpc("accept_application", job.pk, application.pk) or {}
            ok_text = "Отклик принят."
        elif action == "reject":
            result = call_rpc("reject_application", job.pk, application.pk) or {}
            ok_text = "Отклик отклонён."
        elif action == "cancel":  # работодатель снимает конкретного работника
            result = call_rpc("cancel_worker_atomic", application.pk, user.pk) or {}
            ok_text = "Работник снят с задания."
        else:  # reopen: rejected → pending (паритет /api/applications/<id>/reopen)
            if application.status == Application.Status.REJECTED:
                application.status = Application.Status.PENDING
                application.save(update_fields=["status", "updated_at"])
                messages.success(request, "Отклик возвращён в ожидание.")
            else:
                messages.error(request, "Вернуть можно только отклонённый отклик.")
            return redirect("core:job_applicants", job_id=job.pk)
    else:
        return HttpResponseNotAllowed([])
    _rpc_message(request, result, ok_text)
    return redirect("core:job_applicants", job_id=job.pk)


# ── Избранное заданий ───────────────────────────────────────────────────────
@login_required
@require_POST
def job_favorite_toggle(request, job_id):
    if not Job.objects.filter(pk=job_id).exists():
        messages.error(request, "Задание не найдено.")
        return redirect("core:jobs")
    fav, created = JobFavorite.objects.get_or_create(user=request.user, job_id=job_id)
    if not created:
        fav.delete()
        messages.info(request, "Удалено из избранного.")
    else:
        messages.success(request, "Добавлено в избранное.")
    return redirect(request.META.get("HTTP_REFERER") or reverse("core:jobs"))


@login_required
def favorite_jobs(request):
    favs = (
        JobFavorite.objects.filter(user=request.user)
        .select_related("job").order_by("-created_at")
    )
    return render(request, "core/favorite_jobs.html", {"favs": favs})
