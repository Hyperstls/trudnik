"""Интерактивные флоу фазы 2а: вход/выход, задания, отклики, избранное.

Инварианты:
- user_id/employer_id всегда из request.user (не из формы) — IDOR невозможен;
- мутации бизнес-состояний — только SECURITY DEFINER RPC; машинный код ошибки
  берётся из result['code'], человекочитаемый текст — из result['error'] RPC;
- доступ к «чужому/скрытому» — единый ответ «не найдено» (не раскрываем существование);
- все редиректы (next/referer) валидируются на same-origin (анти open-redirect).

NB (из ревью B2-7): restore_job_atomic внутри БД сверяет владельца только при
заданном JWT-claim app_role — при прямом вызове из Django guard держит view
(get_object_or_404(..., employer=request.user)). Не вызывать этот RPC без
view-проверки владения.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .auth_backend import LOCKOUT_TEXT, ProfileBackend
from .forms import JobForm, LoginForm
from .models import Application, Job, JobFavorite
from .notifications import enqueue_notification
from .ratelimit import RateLimitExceeded, RateLimitUnavailable, enforce_ip_limit, rate_limit_write
from .rpc import call_rpc, sync_job_skills_raw

RPC_ERROR_TEXT = {
    "not_found": "Не найдено или недоступно.",
    "job_not_found": "Задание не найдено.",
    "job_not_open": "Задание не открыто для откликов.",
    "no_slots": "Все места уже заняты.",
    "bad_status": "Недопустимый статус для этого действия.",
    "already_applied": "Вы уже откликнулись на это задание.",
    "duplicate": "Вы уже откликнулись на это задание.",
    "own_job": "Нельзя откликнуться на собственное задание.",
    "blacklisted": "Заказчик ограничил приём откликов от вас.",
    "expired": "Задание истекло.",
    "job_expired": "Срок размещения задания истёк.",
    "past_date": "Дата работ уже в прошлом.",
    "job_in_past": "Это задание уже началось или прошло.",
    "not_owner": "Недостаточно прав.",
    "unknown": "Действие не выполнено.",
}


def _safe_next(request):
    """Только same-origin относительный redirect (блокирует //evil.com и \\evil.com)."""
    nxt = request.GET.get("next") or request.POST.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts=None):
        return nxt
    return settings.LOGIN_REDIRECT_URL


def _safe_back(request, fallback: str):
    """Referer валидируется как same-origin; иначе — fallback."""
    referer = request.META.get("HTTP_REFERER", "")
    if referer:
        # referer абсолютный: проверяем путь на нашем хосте
        from urllib.parse import urlsplit

        parts = urlsplit(referer)
        host = request.get_host()
        if (parts.netloc == host or not parts.netloc) and url_has_allowed_host_and_scheme(
            referer, allowed_hosts={host}
        ):
            return referer
    return fallback


def _rpc_message(request, result: dict, ok_text: str = "Готово.") -> bool:
    """Машинный 'code' приоритетен (стабилен), fallback — человекочитаемый 'error' RPC."""
    if result.get("success"):
        messages.success(request, ok_text)
        return True
    code = result.get("code") or "unknown"
    text = RPC_ERROR_TEXT.get(code) or result.get("error") or RPC_ERROR_TEXT["unknown"]
    messages.error(request, text)
    return False


def _public_job_or_none(job_id):
    """Скрытые задания ведут себя как несуществующие (RLS-паритет, без оракула)."""
    return Job.objects.public().filter(pk=job_id).first()


# ── Вход / выход ────────────────────────────────────────────────────────────
def login_view(request):
    if request.user.is_authenticated:
        return redirect("/")
    form = LoginForm(request.POST or None)
    if request.method == "POST":
        # per-IP лимит до любых проверок: fail-closed при недоступном кэше
        try:
            enforce_ip_limit(request, "login", 20, 3600)
        except RateLimitExceeded:
            messages.error(request, "Слишком много попыток с вашего IP. Попробуйте позже.")
            return render(request, "core/login.html", {"form": form})
        except RateLimitUnavailable:
            messages.error(request, "Сервис входа временно недоступен. Попробуйте позже.")
            return render(request, "core/login.html", {"form": form})
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        try:
            user = authenticate(
                request,
                username=email,
                password=form.cleaned_data["password"],
            )
        except PermissionDenied as exc:
            messages.error(request, str(exc))
        else:
            if user is not None:
                auth_login(request, user)
                return redirect(_safe_next(request))
            # authenticate() глушит PermissionDenied бэкенда — уточняем лок-аут сами
            try:
                remaining = ProfileBackend.lock_remaining(email)
            except PermissionDenied as exc:
                messages.error(request, str(exc))
            else:
                if remaining:
                    messages.error(request, LOCKOUT_TEXT % remaining)
                else:
                    messages.error(request, "Неверный email или пароль, либо аккаунт заблокирован/не подтверждён.")
    return render(request, "core/login.html", {"form": form})


@require_POST
def logout_view(request):
    auth_logout(request)
    messages.info(request, "Вы вышли.")
    return redirect(settings.LOGOUT_REDIRECT_URL or "core:jobs")


# ── Задания: создание/редактирование ───────────────────────────────────────
@login_required
def job_create(request):
    form = JobForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            job = form.save(commit=False)
            job.employer = request.user
            job.status = Job.Status.OPEN
            job.expires_at = timezone.now() + timedelta(days=30)
            job.save()
            sync_job_skills_raw(job.pk, [s.pk for s in form.cleaned_data["skills"]])
        messages.success(request, "Задание создано.")
        return redirect("core:job_detail", job_id=job.pk)
    return render(request, "core/job_form.html", {"form": form, "title": "Новое задание", "selected_skills": set()})


@login_required
def job_edit(request, job_id):
    # свои задания — в любом статусе (draft/expired видны владельцу)
    job = get_object_or_404(Job, pk=job_id, employer=request.user)
    form = JobForm(request.POST or None, instance=job)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            job = form.save(commit=False)
            job.expires_at = timezone.now() + timedelta(days=30)
            job.save()
            sync_job_skills_raw(job.pk, [s.pk for s in form.cleaned_data["skills"]])
        messages.success(request, "Задание обновлено.")
        return redirect("core:job_detail", job_id=job.pk)
    from django.db import connection as _c
    with _c.cursor() as cur:
        cur.execute("SELECT skill_id::text FROM job_skills WHERE job_id = %s", [job.pk])
        selected = {r[0] for r in cur.fetchall()}
    return render(request, "core/job_form.html", {"form": form, "title": "Редактирование задания", "selected_skills": selected})


@login_required
def my_jobs(request):
    status = request.GET.get("status") or ""
    if status not in ("open", "completed", "cancelled"):
        status = ""
    jobs = (
        Job.objects.filter(employer=request.user)
        .annotate(application_count=Count("applications"))
        .order_by("-created_at")
    )
    if status:
        jobs = jobs.filter(status=status)
    return render(request, "core/my_jobs.html", {"jobs": jobs, "status": status})


@login_required
@require_POST
def job_action(request, job_id, action):
    """cancel / restore / force_complete / delete — всё через RPC от имени владельца."""
    if action not in ("cancel", "restore", "force_complete", "delete"):
        return HttpResponseNotAllowed(["POST"])
    job = get_object_or_404(Job, pk=job_id, employer=request.user)
    uid = request.user.pk
    if action == "cancel":
        ok = _rpc_message(request, call_rpc("cancel_job_atomic", job.pk, uid) or {}, "Задание отменено.")
    elif action == "restore":
        ok = _rpc_message(request, call_rpc("restore_job_atomic", job.pk, uid) or {}, "Задание восстановлено.")
    elif action == "force_complete":
        ok = _rpc_message(request, call_rpc("force_complete_job", job.pk, uid) or {}, "Задание завершено.")
    else:  # delete
        ok = _rpc_message(request, call_rpc("delete_job_cascade", job.pk) or {}, "Задание удалено.")
    if action == "delete" and ok:
        return redirect("core:my_jobs")
    return redirect(_safe_back(request, reverse("core:my_jobs")))


# ── Отклики ─────────────────────────────────────────────────────────────────
@login_required
@require_POST
@rate_limit_write(limit=10, window=60)
def job_apply(request, job_id):
    job = _public_job_or_none(job_id)
    if job is None or job.employer_id == request.user.pk:
        messages.error(request, "Задание не найдено или отклик невозможен.")
        return redirect("core:jobs")
    result = call_rpc("apply_job_atomic", job.pk, request.user.pk) or {}
    ok = _rpc_message(request, result, "Отклик отправлен.")
    if ok:
        enqueue_notification(
            job.employer_id, "application_received", "Новый отклик",
            "На ваше задание поступил новый отклик",
            {
                "job_id": str(job.pk),
                "link": request.build_absolute_uri(
                    reverse("core:job_detail", args=[job.pk])
                ),
            },
        )
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
    tab = request.GET.get("tab") or "sent"
    if tab not in ("received", "sent"):
        tab = "sent"
    if tab == "received":
        qs = Application.objects.filter(job__employer=request.user).select_related(
            "job", "worker"
        )
    else:
        qs = Application.objects.filter(worker=request.user).select_related("job")
    page = Paginator(qs.order_by("-created_at"), 20).get_page(request.GET.get("page"))
    return render(request, "core/my_applications.html", {
        "page": page,
        "apps": page.object_list,
        "tab": tab,
    })


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
    if action not in ("accept", "reject", "reopen", "cancel", "withdraw"):
        return HttpResponseNotAllowed(["POST"])
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
    else:
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
        elif action == "reopen":  # паритет Flask: reopen делегирует в accept-RPC
            result = call_rpc("accept_application", job.pk, application.pk) or {}
            ok_text = "Отклик принят повторно."
    ok = _rpc_message(request, result, ok_text)
    if ok and action in ("accept", "reject", "reopen"):
        accepted = action != "reject"
        enqueue_notification(
            application.worker_id,
            "application_accepted" if accepted else "application_rejected",
            "Отклик принят" if accepted else "Отклик отклонён",
            "Ваш отклик на задание #%s был %s" % (
                job.pk, "принят" if accepted else "отклонён",
            ),
            {
                "job_id": str(job.pk),
                "link": request.build_absolute_uri(reverse("core:my_applications")),
            },
        )
    return redirect("core:job_applicants", job_id=job.pk)


# ── Избранное заданий ───────────────────────────────────────────────────────
@login_required
@require_POST
def job_favorite_toggle(request, job_id):
    # только публично видимые задания (без оракула существования скрытых)
    if not Job.objects.public().filter(pk=job_id).exists():
        messages.error(request, "Задание не найдено.")
        return redirect("core:jobs")
    fav, created = JobFavorite.objects.get_or_create(user=request.user, job_id=job_id)
    if not created:
        fav.delete()
        messages.info(request, "Удалено из избранного.")
    else:
        messages.success(request, "Добавлено в избранное.")
    return redirect(_safe_back(request, reverse("core:jobs")))


@login_required
def favorite_jobs(request):
    favs = (
        JobFavorite.objects.filter(user=request.user)
        .select_related("job").order_by("-created_at")
    )
    return render(request, "core/favorite_jobs.html", {"favs": favs})
