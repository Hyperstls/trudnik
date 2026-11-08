"""Флоу заданий: создание, редактирование, действия владельца, мои задания.

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
import os
from uuid import UUID

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _, gettext_lazy as _lazy
from django.views.decorators.http import require_POST

from .analytics import incr
from .anti_fraud import allow_job_post, assess_job
from .forms import INPUT_CLS, JOB_FIELDS, JobForm
from .http import safe_referer
from .models import Application, Job, JobPhoto
from .rpc import call_rpc, sync_job_skills_raw
from .storage import delete_upload_url
from .views_public_ext import duplicate_job

RPC_ERROR_TEXT = {
    "not_found": _lazy("Не найдено или недоступно."),
    "job_not_found": _lazy("Задание не найдено."),
    "job_not_open": _lazy("Задание не открыто для откликов."),
    "no_slots": _lazy("Все места уже заняты."),
    "bad_status": _lazy("Недопустимый статус для этого действия."),
    "already_applied": _lazy("Вы уже откликнулись на это задание."),
    "duplicate": _lazy("Вы уже откликнулись на это задание."),
    "own_job": _lazy("Нельзя откликнуться на собственное задание."),
    "blacklisted": _lazy("Заказчик ограничил приём откликов от вас."),
    "expired": _lazy("Задание истекло."),
    "job_expired": _lazy("Срок размещения задания истёк."),
    "past_date": _lazy("Дата работ уже в прошлом."),
    "job_in_past": _lazy("Это задание уже началось или прошло."),
    "not_owner": _lazy("Недостаточно прав."),
    "unknown": _lazy("Действие не выполнено."),
}



def _safe_back(request, fallback: str):
    """Referer валидируется как same-origin; иначе — fallback."""
    return safe_referer(request, fallback)


def _rpc_message(request, result: dict, ok_text: str = _lazy("Готово.")) -> bool:
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


# ── Задания: создание/редактирование ───────────────────────────────────────
@login_required
def job_create(request):
    form = JobForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not allow_job_post(request.user.pk):
            messages.error(
                request,
                _(
                    "Слишком много новых заданий за последний час. "
                    "Подождите немного и попробуйте снова."
                ),
            )
        else:
            assessment = assess_job(
                request.user,
                work_type=form.cleaned_data.get("work_type") or "",
                city=form.cleaned_data.get("city") or "",
                texts=(
                    form.cleaned_data.get("organization_name"),
                    form.cleaned_data.get("org_description"),
                    form.cleaned_data.get("object_description"),
                    form.cleaned_data.get("detailed_description"),
                ),
            )
            with transaction.atomic():
                job = form.save(commit=False)
                job.employer = request.user
                job.status = Job.Status.OPEN
                job.expires_at = timezone.now() + timedelta(days=30)
                job.moderation_status = assessment["status"]
                job.moderation_reason = assessment["reason"] or None
                job.save()
                sync_job_skills_raw(job.pk, [s.pk for s in form.cleaned_data["skills"]])
            incr("job_created")
            if assessment["status"] == Job.ModerationStatus.REVIEW:
                messages.warning(
                    request,
                    _(
                        "Задание создано и отправлено на проверку. "
                        "Оно появится в каталоге после одобрения модератором."
                    ),
                )
            else:
                messages.success(request, _("Задание создано."))
            return redirect(reverse("core:job_detail", args=[job.pk]) + "?created=1&push=1")
    return render(request, "core/job_form.html", {
        "form": form, "title": _("Новое задание"), "selected_skills": set(),
        "yandex_maps_key": os.getenv("YANDEX_MAPS_API_KEY", ""),
    })


class JobDescriptionForm(forms.Form):
    """Ограниченная правка задания после принятого отклика (паритет Flask)."""

    detailed_description = forms.CharField(
        label=_lazy("Описание работы"), required=False, max_length=5000,
        widget=forms.Textarea(attrs={"class": INPUT_CLS, "rows": 6}),
    )


@login_required
def job_edit(request, job_id):
    # свои задания — в любом статусе (draft/expired видны владельцу)
    job = get_object_or_404(Job, pk=job_id, employer=request.user)
    has_accepted = Application.objects.filter(job=job, status="accepted").exists()
    if has_accepted:
        if request.method == "POST":
            locked_names = (set(JOB_FIELDS) - {"detailed_description"}) | {"skills"}
            forbidden = sorted(locked_names & set(request.POST))
            if forbidden:
                messages.error(
                    request,
                    _(
                        "Нельзя редактировать условия задания: есть принятые отклики. "
                        "Разрешено менять только описание работы."
                    ),
                )
                return redirect("core:job_detail", job_id=job.pk)
            description_form = JobDescriptionForm(request.POST)
            if description_form.is_valid():
                job.detailed_description = description_form.cleaned_data["detailed_description"]
                job.save(update_fields=["detailed_description"])
                messages.success(request, _("Описание задания обновлено."))
                return redirect("core:job_detail", job_id=job.pk)
        else:
            description_form = JobDescriptionForm(
                initial={"detailed_description": job.detailed_description or ""}
            )
        return render(request, "core/job_form.html", {
            "title": _("Редактирование задания"), "job": job, "locked": True,
            "accepted_count": Application.objects.filter(
                job=job, status="accepted"
            ).count(),
            "description_form": description_form,
        })
    form = JobForm(request.POST or None, instance=job)
    if request.method == "POST" and form.is_valid():
        assessment = assess_job(
            request.user,
            work_type=form.cleaned_data.get("work_type") or "",
            city=form.cleaned_data.get("city") or "",
            texts=(
                form.cleaned_data.get("organization_name"),
                form.cleaned_data.get("org_description"),
                form.cleaned_data.get("object_description"),
                form.cleaned_data.get("detailed_description"),
            ),
            exclude_job_id=job.pk,
        )
        with transaction.atomic():
            job = form.save(commit=False)
            job.expires_at = timezone.now() + timedelta(days=30)
            if job.moderation_status == Job.ModerationStatus.REJECTED:
                # Правка отклонённого задания возвращает его в очередь.
                job.moderation_status = Job.ModerationStatus.REVIEW
                job.moderation_reason = _("Повторная проверка после правки")
            elif assessment["status"] == Job.ModerationStatus.REVIEW:
                job.moderation_status = Job.ModerationStatus.REVIEW
                job.moderation_reason = assessment["reason"] or None
            job.save()
            sync_job_skills_raw(job.pk, [s.pk for s in form.cleaned_data["skills"]])
        if job.moderation_status == Job.ModerationStatus.REVIEW:
            messages.warning(request, _("Задание обновлено и отправлено на проверку."))
        else:
            messages.success(request, _("Задание обновлено."))
        return redirect("core:job_detail", job_id=job.pk)
    from django.db import connection as _c
    with _c.cursor() as cur:
        cur.execute("SELECT skill_id::text FROM job_skills WHERE job_id = %s", [job.pk])
        selected = {r[0] for r in cur.fetchall()}
    return render(request, "core/job_form.html", {
        "form": form, "title": _("Редактирование задания"), "job": job,
        "selected_skills": selected,
        "yandex_maps_key": os.getenv("YANDEX_MAPS_API_KEY", ""),
    })


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


def _job_file_urls(job) -> list[str]:
    """Собрать уникальные URL фото задания ДО удаления строк."""
    urls = [p.photo_url for p in job.photos.all() if p.photo_url]
    urls += [u for u in (job.photo_urls or []) if u]
    return list(dict.fromkeys(urls))


def _delete_job_files(urls: list[str]) -> None:
    """Удалить файлы, если на них больше нет ссылок у других заданий."""
    for url in urls:
        if (
            JobPhoto.objects.filter(photo_url=url).exists()
            or Job.objects.filter(photo_urls__contains=[url]).exists()
        ):
            continue
        delete_upload_url(url)


@login_required
@require_POST
def job_action(request, job_id, action):
    """cancel / restore / force_complete / delete — всё через RPC от имени владельца."""
    if action not in ("cancel", "restore", "force_complete", "delete"):
        return HttpResponseNotAllowed(["POST"])
    job = get_object_or_404(Job, pk=job_id, employer=request.user)
    file_urls = _job_file_urls(job) if action == "delete" else []
    uid = request.user.pk
    if action == "cancel":
        ok = _rpc_message(request, call_rpc("cancel_job_atomic", job.pk, uid) or {}, _("Задание отменено."))
    elif action == "restore":
        ok = _rpc_message(request, call_rpc("restore_job_atomic", job.pk, uid) or {}, _("Задание восстановлено."))
    elif action == "force_complete":
        ok = _rpc_message(request, call_rpc("force_complete_job", job.pk, uid) or {}, _("Задание завершено."))
    else:  # delete
        ok = _rpc_message(request, call_rpc("delete_job_cascade", job.pk) or {}, _("Задание удалено."))
    if action == "delete" and ok:
        _delete_job_files(file_urls)
        return redirect("core:my_jobs")
    return redirect(_safe_back(request, reverse("core:my_jobs")))


BULK_LIMIT = 50


def _bulk_ids(values) -> list[UUID]:
    """Валидные UUID из POST, без дублей и мусора (иначе pk__in → 500)."""
    cleaned = []
    for value in values:
        try:
            cleaned.append(UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return list(dict.fromkeys(cleaned))[:BULK_LIMIT]


@login_required
@require_POST
def my_jobs_bulk(request):
    """Массовые cancel/restore/delete своих заданий (≤50, только атомарные RPC)."""
    action = request.POST.get("action")
    if action not in ("cancel", "restore", "delete", "duplicate"):
        return HttpResponseNotAllowed(["POST"])
    job_ids = _bulk_ids(request.POST.getlist("job_ids"))
    if not job_ids:
        messages.error(request, _("Не выбрано ни одного задания."))
        return redirect("core:my_jobs")
    jobs = list(
        Job.objects.filter(pk__in=job_ids, employer=request.user).prefetch_related("photos")
    )
    done = 0
    if action == "duplicate":
        for job in jobs:
            duplicate_job(job, request.user)
            done += 1
    else:
        file_urls = {job.pk: _job_file_urls(job) for job in jobs} if action == "delete" else {}
        for job in jobs:
            if action == "cancel":
                result = call_rpc("cancel_job_atomic", job.pk, request.user.pk) or {}
            elif action == "restore":
                result = call_rpc("restore_job_atomic", job.pk, request.user.pk) or {}
            else:
                result = call_rpc("delete_job_cascade", job.pk) or {}
            if result.get("success"):
                done += 1
                if action == "delete":
                    _delete_job_files(file_urls[job.pk])
    if done:
        messages.success(request, _("Выполнено: %d.") % done)
    failed = len(job_ids) - done
    if failed:
        messages.warning(request, _("Не выполнено: %d.") % failed)
    return redirect("core:my_jobs")
