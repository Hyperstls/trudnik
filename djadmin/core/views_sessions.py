"""R007: страница активных сессий и отзыв сессий.

Тонкая UI-обёртка над ``core.sessions``: в контекст и шаблон попадает только
публичный HMAC-идентификатор, raw ``session_key`` наружу не отдаётся.
"""
from datetime import datetime, timezone as dt_timezone

from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .ratelimit import rate_limit_write
from .sessions import iter_user_sessions, revoke_user_session, session_public_id

EMPTY_DATETIME = "—"
DATETIME_FORMAT = "%d.%m.%Y %H:%M"


def _as_datetime(value):
    """ISO-строка из метаданных сессии → aware datetime (или None)."""
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = parse_datetime(str(value))
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _display_datetime(value):
    parsed = _as_datetime(value)
    if parsed is None:
        return EMPTY_DATETIME
    return timezone.localtime(parsed).strftime(DATETIME_FORMAT)


def _last_seen_timestamp(item):
    """Сортируемое значение last_seen; пусто/битое — в конец списка.

    Ordinal-арифметика вместо datetime.timestamp(): не падает на Windows
    для дат до 1970 года и корректна при разных tz-offset.
    """
    parsed = _as_datetime(item.get("last_seen"))
    if parsed is None:
        return 0.0
    utc = parsed.astimezone(dt_timezone.utc)
    return (
        utc.toordinal() * 86400
        + utc.hour * 3600
        + utc.minute * 60
        + utc.second
        + utc.microsecond / 1_000_000
    )


@login_required
def sessions_view(request):
    current_public_id = session_public_id(request.session.session_key)
    sessions = iter_user_sessions(request.user)
    for item in sessions:
        item["is_current"] = item.get("public_id") == current_public_id
        item["login_at_display"] = _display_datetime(item.get("login_at"))
        item["last_seen_display"] = _display_datetime(item.get("last_seen"))
    # Текущая сессия первой, остальные — по последней активности (свежие выше).
    sessions.sort(
        key=lambda item: (0 if item["is_current"] else 1, -_last_seen_timestamp(item))
    )
    return render(request, "core/sessions.html", {
        "sessions": sessions,
        "current_public_id": current_public_id,
    })


@login_required
@require_POST
@rate_limit_write(limit=10, window=60, redirect_to="/profile/sessions")
def session_revoke(request):
    current_public_id = session_public_id(request.session.session_key)

    if request.POST.get("scope") == "others":
        revoked = 0
        for item in iter_user_sessions(request.user):
            if item["public_id"] == current_public_id:
                continue
            if revoke_user_session(request.user, item["public_id"]):
                revoked += 1
        messages.success(request, _("Завершено других сессий: %d.") % revoked)
        return redirect("core:sessions")

    public_id = request.POST.get("public_id", "")
    if public_id and public_id == current_public_id:
        auth_logout(request)
        messages.info(request, _("Текущая сессия завершена. Войдите снова."))
        return redirect("core:login")

    if revoke_user_session(request.user, public_id):
        messages.success(request, _("Сессия завершена."))
    else:
        messages.error(request, _("Сессия не найдена или уже завершена."))
    return redirect("core:sessions")
