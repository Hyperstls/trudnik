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
- uploads: magic-bytes JPEG/PNG/WebP (+PDF только для verification-docs),
  лимит MAX_PHOTO_SIZE_MB.
"""
import json
import logging
import mimetypes
import os
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _, gettext_lazy as _lazy
from django.views.decorators.http import require_POST

from .models import (
    Application, Blacklist, EmployerDetail, Favorite, Job, JobPhoto, Message,
    Profile, Rating, UserReport, UserSkill,
)
from .ratelimit import rate_limit_write
from .rpc import call_rpc, call_rpc_as_user
from .storage import UploadError, delete_upload_url, save_upload
from .tokens import generate_email_change_token, verify_email_change_token

logger = logging.getLogger(__name__)


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
        # R059 (152-ФЗ ст.14): переписка и карточка работодателя — тоже ПДн субъекта.
        "messages_sent": list(
            Message.objects.filter(sender=user).values(
                "id", "application_id", "content", "attachment_url",
                "attachment_name", "attachment_mime", "attachment_size",
                "read_at", "created_at",
            )
        ),
        "employer_details": EmployerDetail.objects.filter(user=user).values().first() or None,
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


def _collect_user_upload_urls(user) -> list[str]:
    """Собрать URL-пути файлов ПДн пользователя ДО удаления строк в БД (P1-14).

    delete_user_cascade удаляет профиль и (для employer) задания, поэтому после
    RPC пути к файлам уже не найти: профиль + фото заданий (job_photos и
    legacy jobs.photo_urls). Пустые значения и дубли отбрасываются.
    """
    urls = []
    profile = Profile.objects.filter(pk=user.pk).values(
        "avatar_url", "photo_url", "verification_doc_url"
    ).first() or {}
    for key in ("avatar_url", "photo_url", "verification_doc_url"):
        if profile.get(key):
            urls.append(profile[key])
    urls.extend(
        JobPhoto.objects.filter(job__employer=user).exclude(photo_url="")
        .values_list("photo_url", flat=True)
    )
    for photo_urls in Job.objects.filter(employer=user).values_list("photo_urls", flat=True):
        urls.extend(photo_urls or [])
    return list(dict.fromkeys(urls))


def _delete_user_uploads(urls, user_pk) -> int:
    """Удалить файлы ПДн (152-ФЗ ст.21); ошибки — в лог, аккаунт не ломаем."""
    deleted = 0
    for url in urls:
        try:
            if delete_upload_url(url):
                deleted += 1
            else:
                logger.warning(
                    "delete_account: файл upload не удалён: %s (user %s)", url, user_pk
                )
        except Exception:  # noqa: BLE001 — сбой файла не должен мешать удалению аккаунта
            logger.warning(
                "delete_account: ошибка удаления файла upload: %s (user %s)",
                url, user_pk, exc_info=True,
            )
    return deleted


@login_required
@require_POST
def delete_account(request):
    """Удаление аккаунта: RPC delete_user_cascade + файлы uploads + выход.

    Rate-limit 1/час. URL файлов собираются до RPC: после удаления строк БД
    (профиль, задания) их уже не восстановить (P1-14, 152-ФЗ ст.21).
    """
    user_pk = request.user.pk
    key = "delete_account:%s" % user_pk
    if not cache.add(key, "1", 3600):
        messages.warning(request, _("Попробуйте позже (не чаще раза в час)."))
        return redirect("core:profile")
    upload_urls = _collect_user_upload_urls(request.user)
    result = call_rpc("delete_user_cascade", user_pk) or {}
    if not result.get("success", True):
        cache.delete(key)
        messages.error(request, _("Ошибка удаления аккаунта. Попробуйте позже."))
        return redirect("core:profile")
    _delete_user_uploads(upload_urls, user_pk)
    auth_logout(request)
    messages.success(request, _("Ваш аккаунт полностью удалён."))
    return redirect("core:login")


@login_required
@require_POST
@rate_limit_write(limit=5, window=3600, redirect_to="/profile")
def email_change_request(request):
    """Start email change: password confirmation + signed link to the new address."""
    new_email = (request.POST.get("new_email") or "").strip().lower()
    current_password = request.POST.get("current_password") or ""
    if not request.user.check_password(current_password):
        messages.error(request, _("Текущий пароль указан неверно."))
        return redirect("core:profile")
    try:
        validate_email(new_email)
    except ValidationError:
        messages.error(request, _("Укажите корректный email."))
        return redirect("core:profile")
    if new_email == (request.user.email or "").lower():
        messages.info(request, _("Этот email уже привязан к аккаунту."))
        return redirect("core:profile")
    if Profile.objects.filter(email=new_email).exclude(pk=request.user.pk).exists():
        messages.error(request, _("Этот email уже используется другим аккаунтом."))
        return redirect("core:profile")

    token = generate_email_change_token(request.user.pk, new_email)
    link = request.build_absolute_uri(
        reverse("core:email_change_confirm", args=[token])
    )
    from .views_auth import _send_mail

    _send_mail(
        "Трудник: подтвердите новый email",
        "Здравствуйте!\n\nПодтвердите смену email в «Труднике» (ссылка действует 1 час):\n%s\n\n"
        "Если вы не запрашивали смену — просто игнорируйте письмо." % link,
        new_email,
    )
    _send_mail(
        "Трудник: запрос на смену email",
        "На вашем аккаунте запрошена смена email на %s.\n"
        "Если это были не вы — смените пароль." % new_email,
        request.user.email,
    )
    messages.success(
        request,
        _("Письмо для подтверждения отправлено на %s. Проверьте почту и папку «Спам».") % new_email,
    )
    return redirect("core:profile")


@login_required
def email_change_confirm(request, token):
    payload = verify_email_change_token(token)
    if not payload or str(request.user.pk) != payload.get("user_id"):
        messages.error(request, _("Ссылка недействительна или истекла. Запросите смену email снова."))
        return redirect("core:profile")
    new_email = (payload.get("email") or "").strip().lower()
    try:
        validate_email(new_email)
    except ValidationError:
        messages.error(request, _("Некорректный email в ссылке."))
        return redirect("core:profile")
    if Profile.objects.filter(email=new_email).exclude(pk=request.user.pk).exists():
        messages.error(request, _("Этот email уже используется другим аккаунтом."))
        return redirect("core:profile")

    old_email = request.user.email
    Profile.objects.filter(pk=request.user.pk).update(
        email=new_email, email_verified=True,
    )
    request.user.refresh_from_db()
    messages.success(request, _("Email изменён и подтверждён."))
    if old_email and old_email.lower() != new_email:
        from .views_auth import _send_mail

        _send_mail(
            "Трудник: email изменён",
            "Email вашего аккаунта изменён на %s.\n"
            "Если это были не вы — немедленно смените пароль и свяжитесь с поддержкой." % new_email,
            old_email,
        )
    return redirect("core:profile")


@login_required
@require_POST
@rate_limit_write(limit=5, window=60, redirect_to="/workers")
def report_user(request, user_id):
    """Жалоба на пользователя → RPC file_report (антифрод)."""
    reason = (request.POST.get("reason") or "").strip()[:500]
    if not reason:
        messages.error(request, _("Укажите причину жалобы."))
        return redirect("core:worker_detail", user_id=user_id)
    result = call_rpc_as_user("file_report", request.user.pk, user_id, reason) or {}
    if result.get("ok") or result.get("success"):
        messages.success(request, _("Жалоба отправлена. Спасибо!"))
    else:
        messages.error(request, _("Не удалось отправить жалобу."))
    return redirect("core:worker_detail", user_id=user_id)


# ── Настройки уведомлений ──────────────────────────────────────────────────
CHANNEL_LABELS = (
    ("email_enabled", _lazy("Email-письма")),
    ("push_enabled", _lazy("Push-уведомления")),
    ("in_app_enabled", _lazy("Уведомления в приложении")),
)
TYPE_LABELS = (
    ("application", _lazy("Отклики на мои задания")),
    ("invitation", _lazy("Приглашения")),
    ("chat", _lazy("Сообщения в чате")),
    ("rating", _lazy("Оценки")),
    ("job", _lazy("Изменения моих заданий")),
    ("saved_search", _lazy("Новые задания по сохранённым поискам")),
)


@login_required
def notification_prefs(request):
    prefs = request.user.notification_prefs or {}
    web_push_enabled = bool(getattr(settings, "WEB_PUSH_ENABLED", False))
    if request.method == "POST":
        updated = dict(prefs)
        for key, _label in CHANNEL_LABELS + TYPE_LABELS:
            updated[key] = key in request.POST
        if not web_push_enabled:
            # Push выключен: не теряем ранее сохранённое предпочтение пользователя.
            updated["push_enabled"] = bool(prefs.get("push_enabled", False))
        frequency = request.POST.get("digest_frequency")
        updated["digest_frequency"] = frequency if frequency in ("instant", "daily", "off") else "daily"
        Profile.objects.filter(pk=request.user.pk).update(notification_prefs=updated)
        messages.success(request, _("Настройки уведомлений сохранены."))
        return redirect("core:notification_prefs")
    searches = []
    for item in (prefs.get("saved_searches") or [])[:10]:
        if isinstance(item, dict) and item.get("id"):
            searches.append({
                "id": item["id"], "name": item.get("name") or _("Мой поиск"),
                "notify": item.get("notify", True) is not False,
            })
    channels = [
        (k, label, prefs.get(k, True))
        for k, label in CHANNEL_LABELS
        if web_push_enabled or k != "push_enabled"
    ]
    context = {
        "channels": channels,
        "types": [(k, label, prefs.get(k, True)) for k, label in TYPE_LABELS],
        "saved_searches": searches,
        "digest_frequency": prefs.get("digest_frequency", "daily"),
        "web_push_enabled": web_push_enabled,
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
        messages.error(request, _("Файл не выбран."))
        return redirect("core:profile")
    try:
        url = save_upload(file, "avatars")
    except UploadError as exc:
        messages.error(request, str(exc))
        return redirect("core:profile")
    Profile.objects.filter(pk=request.user.pk).update(avatar_url=url)
    messages.success(request, _("Аватар обновлён."))
    return redirect("core:profile")


@login_required
@require_POST
def delete_avatar(request):
    urls = [request.user.avatar_url, request.user.photo_url]
    Profile.objects.filter(pk=request.user.pk).update(avatar_url=None, photo_url=None)
    for url in urls:
        if url:
            delete_upload_url(url)
    messages.success(request, _("Фото профиля удалено."))
    return redirect("core:profile")


@login_required
@require_POST
def upload_verification_doc(request):
    file = request.FILES.get("document")
    if file is None:
        messages.error(request, _("Файл не выбран."))
        return redirect("core:verify_employer")
    try:
        url = save_upload(file, "verification-docs", allow_pdf=True)
    except UploadError as exc:
        messages.error(request, str(exc))
        return redirect("core:verify_employer")
    Profile.objects.filter(pk=request.user.pk).update(
        verification_doc_url=url,
        verification_status="pending",
        verification_provider="manual",
    )
    messages.success(request, _("Документ отправлен на проверку."))
    return redirect("core:profile")


@login_required
def verify_employer(request):
    return render(request, "core/verify_employer.html")


def _upload_relative_path(file_path: Path) -> str:
    """Канонический путь файла внутри uploads (без учёта alias-сегментов)."""
    from .storage import _upload_root

    try:
        return file_path.relative_to(_upload_root().resolve()).as_posix()
    except ValueError:
        return ""


def serve_upload(request, path: str):
    """/uploads/<path> — avatars/jobs публично; verification-docs — owner/admin.

    152-ФЗ: скан документа верификации отдаётся только владельцу профиля
    (profiles.verification_doc_url == '/uploads/' + path) или администратору;
    остальным — 404 (без раскрытия существования файла). Ответ private/no-store
    и attachment. ACL считается по фактическому пути внутри uploads, поэтому
    alias вида avatars/../verification-docs/<file> не обходит проверку.
    """
    from .storage import resolve_upload_url

    file_path = resolve_upload_url(path)
    if file_path is None:
        raise Http404()
    relative = _upload_relative_path(file_path) or path
    is_verification_doc = relative.startswith("verification-docs/")
    if is_verification_doc:
        if not request.user.is_authenticated:
            raise Http404()
        owner = Profile.objects.filter(
            verification_doc_url="/uploads/" + relative
        ).first()
        is_owner = owner is not None and owner.pk == request.user.pk
        if not (is_owner or request.user.role == "admin"):
            raise Http404()

    content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    response = FileResponse(
        open(file_path, "rb"),
        content_type=content_type,
        as_attachment=is_verification_doc,
    )
    response["X-Content-Type-Options"] = "nosniff"
    if is_verification_doc:
        response["Cache-Control"] = "private, no-store"
    else:
        response["Cache-Control"] = "public, max-age=86400"
    return response
