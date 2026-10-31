"""152-ФЗ: экспорт ПДн, удаление аккаунта, жалобы, настройки уведомлений,
загрузки (аватар, документ верификации) и раздача /uploads/.

Контракты сверены с Flask (origin/main-flask app/blueprints/profile.py,
notifications.py, storage_service.py):
- export: JSON-разделы profile/skills/applications/favorites/blacklist/ratings
  + applications_as_employer (через jobs пользователя), Content-Disposition;
- delete: RPC delete_user_cascade, rate-limit 1/час (кэш), session.clear;
- report: RPC file_report(p_reported, p_reason≤500);
- prefs: notification_prefs JSON — каналы email_enabled/push_enabled/
  in_app_enabled + типы уведомлений (true/false);
- uploads: magic-bytes JPEG/PNG/WebP, лимит MAX_PHOTO_SIZE_MB.
"""
import json
import mimetypes
import os
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    Application, Blacklist, Favorite, Job, Profile, Rating, UserReport, UserSkill,
)
from .rpc import call_rpc, call_rpc_as_user
from .storage import UploadError, save_upload


def _own_data(user) -> dict:
    """Собрать ПДн пользователя (контракт export_data Flask)."""
    profile = Profile.objects.filter(pk=user.pk).values().first() or {}
    # не отдаём хэш пароля даже в экспорте
    profile.pop("password", None)
    jobs_qs = Job.objects.filter(employer=user)
    job_ids = list(jobs_qs.values_list("id", flat=True))
    sections = {
        "profile": profile,
        "skills": list(UserSkill.objects.filter(user=user).values("user_id", "skill_id")),
        "applications_as_worker": list(
            Application.objects.filter(worker=user).values()
        ),
        "applications_as_employer": list(
            Application.objects.filter(job_id__in=job_ids).values()
        ) if job_ids else [],
        "favorites": list(Favorite.objects.filter(user=user).values()),
        "blacklist": list(Blacklist.objects.filter(user=user).values()),
        "ratings_given": list(Rating.objects.filter(rater_user=user).values()),
        "ratings_received": list(Rating.objects.filter(rated_user=user).values()),
        "reports_filed": list(UserReport.objects.filter(reporter=user).values()),
    }
    return sections


@login_required
def export_data(request):
    """152-ФЗ ст.14/15 — право на доступ/копию своих ПДн (JSON-файл)."""
    payload = {
        "exported_at": timezone.now().isoformat(),
        "user_id": str(request.user.pk),
        "legal_basis": "152-ФЗ ст.14, ст.15 — право субъекта на доступ к ПДн",
        **_own_data(request.user),
    }
    body = json.dumps(payload, ensure_ascii=False, default=str, indent=2)
    response = HttpResponse(body, content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = (
        'attachment; filename="trudnik_personal_data_%s.json"' % str(request.user.pk)[:8]
    )
    return response


@login_required
@require_POST
def delete_account(request):
    """Удаление аккаунта: RPC delete_user_cascade + выход. Rate-limit 1/час."""
    key = "delete_account:%s" % request.user.pk
    if not cache.add(key, "1", 3600):
        messages.warning(request, "Попробуйте позже (не чаще раза в час).")
        return redirect("core:profile")
    result = call_rpc("delete_user_cascade", request.user.pk) or {}
    if not result.get("success", True):
        cache.delete(key)
        messages.error(request, "Ошибка удаления аккаунта. Попробуйте позже.")
        return redirect("core:profile")
    auth_logout(request)
    messages.success(request, "Ваш аккаунт полностью удалён.")
    return redirect("core:login")


@login_required
@require_POST
def report_user(request, user_id):
    """Жалоба на пользователя → RPC file_report (антифрод)."""
    reason = (request.POST.get("reason") or "").strip()[:500]
    if not reason:
        messages.error(request, "Укажите причину жалобы.")
        return redirect("core:worker_detail", user_id=user_id)
    result = call_rpc_as_user("file_report", request.user.pk, user_id, reason) or {}
    if result.get("ok") or result.get("success"):
        messages.success(request, "Жалоба отправлена. Спасибо!")
    else:
        messages.error(request, "Не удалось отправить жалобу.")
    return redirect("core:worker_detail", user_id=user_id)


# ── Настройки уведомлений ──────────────────────────────────────────────────
CHANNEL_LABELS = (
    ("email_enabled", "Email-письма"),
    ("push_enabled", "Push-уведомления"),
    ("in_app_enabled", "Уведомления в приложении"),
)
TYPE_LABELS = (
    ("application", "Отклики на мои задания"),
    ("invitation", "Приглашения"),
    ("chat", "Сообщения в чате"),
    ("rating", "Оценки"),
    ("job", "Изменения моих заданий"),
)


@login_required
def notification_prefs(request):
    prefs = request.user.notification_prefs or {}
    if request.method == "POST":
        updated = dict(prefs)
        for key, _ in CHANNEL_LABELS + TYPE_LABELS:
            updated[key] = key in request.POST
        Profile.objects.filter(pk=request.user.pk).update(notification_prefs=updated)
        messages.success(request, "Настройки уведомлений сохранены.")
        return redirect("core:notification_prefs")
    context = {
        "channels": [(k, label, prefs.get(k, True)) for k, label in CHANNEL_LABELS],
        "types": [(k, label, prefs.get(k, True)) for k, label in TYPE_LABELS],
    }
    return render(request, "core/notification_settings.html", context)


@login_required
def notification_prefs_api(request):
    """JSON prefs (паритет /api/notifications/preferences)."""
    prefs = request.user.notification_prefs or {}
    return JsonResponse({
        "prefs": {k: prefs.get(k, True) for k, _ in CHANNEL_LABELS + TYPE_LABELS}
    })


# ── Загрузки ───────────────────────────────────────────────────────────────
@login_required
@require_POST
def upload_avatar(request):
    file = request.FILES.get("avatar")
    if file is None:
        messages.error(request, "Файл не выбран.")
        return redirect("core:profile")
    try:
        url = save_upload(file, "avatars")
    except UploadError as exc:
        messages.error(request, str(exc))
        return redirect("core:profile")
    Profile.objects.filter(pk=request.user.pk).update(avatar_url=url)
    messages.success(request, "Аватар обновлён.")
    return redirect("core:profile")


@login_required
@require_POST
def upload_verification_doc(request):
    file = request.FILES.get("document")
    if file is None:
        messages.error(request, "Файл не выбран.")
        return redirect("core:verify_employer")
    try:
        url = save_upload(file, "verification-docs")
    except UploadError as exc:
        messages.error(request, str(exc))
        return redirect("core:verify_employer")
    Profile.objects.filter(pk=request.user.pk).update(
        verification_doc_url=url,
        verification_status="pending",
        verification_provider="manual",
    )
    messages.success(request, "Документ отправлен на проверку.")
    return redirect("core:profile")


@login_required
def verify_employer(request):
    return render(request, "core/verify_employer.html")


def serve_upload(request, path: str):
    """/uploads/<path> — avatars/jobs публично, verification-docs только login."""
    if path.startswith("verification-docs/") and not request.user.is_authenticated:
        raise Http404()
    from .storage import resolve_upload_url

    file_path = resolve_upload_url(path)
    if file_path is None:
        raise Http404()
    content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    response = FileResponse(open(file_path, "rb"), content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "public, max-age=86400"
    return response
