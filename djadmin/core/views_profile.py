"""Фаза 2в: свой профиль, смена пароля, избранное людей, чёрный список, приглашения.

Контракты: change_password(p_user_id, p_old_password, p_new_password) → boolean
(3-арг, сверено pg_proc; после успеха двигаем password_changed_at — паритет B10);
accept_invitation_atomic(p_invitation_id, p_user_id) — worker_id из сессии.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms_profile import PasswordChangeForm, ProfileForm
from .models import Blacklist, Favorite, Invitation, Job, Profile
from .rpc import call_rpc, sync_user_skills_raw


# ── Свой профиль ────────────────────────────────────────────────────────────
@login_required
def profile_edit(request):
    user = request.user
    form = ProfileForm(request.POST or None, instance=user)
    change_form = PasswordChangeForm(request.POST or None) if request.method == "POST" and \
        request.POST.get("action") == "password" else PasswordChangeForm()
    skills_form_active = request.method == "POST" and request.POST.get("action") == "skills"

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "password":
            if change_form.is_valid():
                ok = False
                try:
                    ok = bool(call_rpc(
                        "change_password", user.pk,
                        change_form.cleaned_data["current_password"],
                        change_form.cleaned_data["new_password"],
                    ))
                except Exception:
                    ok = False
                if ok:
                    Profile.objects.filter(pk=user.pk).update(password_changed_at=timezone.now())
                    messages.success(request, "Пароль изменён.")
                    return redirect("core:profile")
                change_form.add_error(None, "Текущий пароль неверен или операция не выполнена.")
        elif action == "skills":
            posted = set(request.POST.getlist("skills"))
            chosen = [s.pk for s in form.fields["skills"].queryset if str(s.pk) in posted]
            sync_user_skills_raw(user.pk, chosen)
            messages.success(request, "Навыки обновлены: %d." % len(chosen))
            return redirect("core:profile")
        elif form.is_valid():
            from django.db import transaction

            with transaction.atomic():
                form.save()
                sync_user_skills_raw(user.pk, [s.pk for s in form.cleaned_data["skills"]])
            messages.success(request, "Профиль сохранён.")
            return redirect("core:profile")

    from .models import UserSkill

    return render(request, "core/profile.html", {
        "form": form, "change_form": change_form,
        "skills_selected": set(UserSkill.objects.filter(user=user).values_list("skill_id", flat=True)),
    })


# ── Избранное людей / чёрный список ────────────────────────────────────────
@login_required
@require_POST
def people_favorite_toggle(request, user_id):
    target = Profile.objects.filter(pk=user_id, role__in=("worker", "employer")).first()
    if target is None or target.pk == request.user.pk:
        messages.error(request, "Профиль недоступен.")
        return redirect("core:workers")
    fav, created = Favorite.objects.get_or_create(
        user=request.user, target=target, favorite_type=target.role,
    )
    if not created:
        fav.delete()
        messages.info(request, "Удалено из избранного.")
    else:
        messages.success(request, "Добавлено в избранное.")
    return redirect("core:worker_detail", user_id=target.pk)


@login_required
@require_POST
def people_block(request, user_id):
    target = Profile.objects.filter(pk=user_id).first()
    if target is None or target.pk == request.user.pk:
        messages.error(request, "Профиль недоступен.")
        return redirect("core:workers")
    _, created = Blacklist.objects.get_or_create(user=request.user, blocked_user=target)
    messages.info(request, "Пользователь заблокирован." if created else "Уже заблокирован.")
    return redirect("core:worker_detail", user_id=target.pk)


@login_required
@require_POST
def people_unblock(request, user_id):
    Blacklist.objects.filter(user=request.user, blocked_user_id=user_id).delete()
    messages.info(request, "Разблокирован.")
    return redirect("core:blacklist")


@login_required
def favorite_people(request):
    favs = Favorite.objects.filter(user=request.user).select_related("target").order_by("-created_at")
    return render(request, "core/favorite_people.html", {"favs": favs})


@login_required
def blacklist_view(request):
    rows = Blacklist.objects.filter(user=request.user).select_related("blocked_user").order_by("-created_at")
    return render(request, "core/blacklist.html", {"rows": rows})


# ── Приглашения ─────────────────────────────────────────────────────────────
@login_required
@require_POST
def invite_worker(request, user_id):
    worker = Profile.objects.public_workers().filter(pk=user_id).first()
    job_id = request.POST.get("job_id", "")
    job = None
    try:
        job = Job.objects.filter(pk=job_id, employer=request.user, status=Job.Status.OPEN).first()
    except (ValueError, ValidationError):
        job = None
    if worker is None or job is None or worker.pk == request.user.pk:
        messages.error(request, "Приглашение невозможно: проверьте задание и профиль.")
        return redirect("core:worker_detail", user_id=user_id)
    try:
        with transaction.atomic():  # savepoint: дубль не роняет внешнюю транзакцию
            Invitation.objects.create(
                job=job, employer=request.user, worker=worker,
                message=(request.POST.get("message") or "")[:500],
            )
    except IntegrityError:
        messages.info(request, "Приглашение на это задание уже отправлено.")
        return redirect("core:worker_detail", user_id=user_id)
    messages.success(request, "Приглашение отправлено.")
    return redirect("core:worker_detail", user_id=user_id)


@login_required
def invitations(request):
    incoming = Invitation.objects.filter(worker=request.user).select_related("job", "job__employer").order_by("-created_at")
    my_job_ids = list(Job.objects.filter(employer=request.user).values_list("id", flat=True))
    outgoing = (
        Invitation.objects.filter(job_id__in=my_job_ids)
        .select_related("job", "worker").order_by("-created_at")
    ) if my_job_ids else Invitation.objects.none()
    return render(request, "core/invitations.html", {"incoming": incoming, "outgoing": outgoing})


@login_required
@require_POST
def invitation_respond(request, invitation_id, action):
    invitation = Invitation.objects.select_related("job").filter(
        pk=invitation_id, worker=request.user,
    ).first()
    if invitation is None or invitation.status != Invitation.Status.PENDING:
        messages.error(request, "Приглашение не найдено или уже обработано.")
        return redirect("core:invitations")
    if action == "accept":
        result = call_rpc("accept_invitation_atomic", invitation.pk, request.user.pk) or {}
        if result.get("success"):
            messages.success(request, "Приглашение принято — вы откликнулись на задание.")
        else:
            messages.error(request, "Не удалось принять: %s." % (result.get("code") or "ошибка"))
    elif action == "decline":
        invitation.status = Invitation.Status.REJECTED
        invitation.responded_at = timezone.now()
        invitation.save(update_fields=["status", "responded_at"])
        messages.info(request, "Приглашение отклонено.")
    else:
        messages.error(request, "Неизвестное действие.")
    return redirect("core:invitations")
