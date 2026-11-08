"""Вход/выход и второй фактор (2FA).

Инварианты: пароль проверяется authenticate(); при включённом 2FA сессия входа
создаётся только после кода из письма; next/referer валидируются same-origin.
"""
import hmac
import secrets
from uuid import UUID

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .auth_backend import LOCKOUT_TEXT, ProfileBackend
from .forms import LoginForm
from .http import safe_next
from .models import Profile
from .ratelimit import RateLimitExceeded, RateLimitUnavailable, enforce_ip_limit


def _safe_next(request):
    """Только same-origin redirect (блокирует //evil.com и \\evil.com)."""
    return safe_next(request, settings.LOGIN_REDIRECT_URL)


# ── Вход / выход ────────────────────────────────────────────────────────────
TWOFA_CODE_TTL = 600
TWOFA_MAX_ATTEMPTS = 5
TWOFA_BACKEND = "core.auth_backend.ProfileBackend"


def _twofa_code_key(user_id) -> str:
    return "twofa_code:%s" % user_id


def _twofa_tries_key(user_id) -> str:
    return "twofa_tries:%s" % user_id


def _twofa_clear(request) -> None:
    """Сброс pending-сессии второго шага и связанного кода."""
    raw_id = request.session.pop("twofa_user", None)
    request.session.pop("twofa_next", None)
    if raw_id:
        cache.delete(_twofa_code_key(raw_id))
        cache.delete(_twofa_tries_key(raw_id))


def _twofa_pending(request):
    """Профиль из pending-сессии; невалидная сессия очищается."""
    raw_id = request.session.get("twofa_user")
    if not raw_id:
        return None
    try:
        user_id = UUID(str(raw_id))
    except (TypeError, ValueError):
        user_id = None
    user = Profile.objects.filter(pk=user_id).first() if user_id else None
    if user is None or not user.is_active or not user.two_factor_enabled:
        _twofa_clear(request)
        return None
    return user


def _twofa_start(request, user):
    """Второй шаг: код на email вместо немедленного auth_login."""
    # локальный импорт: _send_mail — канон отправки транзакционных писем
    from .views_auth import _send_mail

    code = "%06d" % secrets.randbelow(1000000)
    cache.set(_twofa_code_key(user.pk), code, TWOFA_CODE_TTL)
    cache.delete(_twofa_tries_key(user.pk))
    request.session["twofa_user"] = str(user.pk)
    request.session["twofa_next"] = _safe_next(request)
    _send_mail(
        "Трудник: код подтверждения входа",
        "Код подтверждения для входа: %s\n\n"
        "Код действует 10 минут. Если вы не пытались войти — смените пароль." % code,
        user.email,
    )
    messages.info(request, _("Мы отправили код подтверждения на %s.") % user.email)
    return render(request, "core/login.html", {
        "form": LoginForm(),
        "twofa": True,
        "twofa_email": user.email,
    })


def _twofa_code_view(request):
    """POST с кодом: успех → auth_login; иначе счётчик попыток и сброс после 5."""
    user = _twofa_pending(request)
    if user is None:
        messages.error(request, _("Сессия входа истекла. Войдите заново."))
        return render(request, "core/login.html", {"form": LoginForm()})
    submitted = (request.POST.get("code") or "").strip()
    stored = cache.get(_twofa_code_key(user.pk))
    # только ровно 6 ASCII-цифр; любой другой ввод — неверный код (без 500 на non-ASCII)
    submitted_ok = (
        len(submitted) == 6 and submitted.isascii() and submitted.isdigit()
    )
    if (
        stored
        and submitted_ok
        and hmac.compare_digest(str(stored).encode("utf-8"), submitted.encode("utf-8"))
    ):
        next_url = request.session.get("twofa_next") or settings.LOGIN_REDIRECT_URL
        _twofa_clear(request)
        auth_login(request, user, backend=TWOFA_BACKEND)
        return redirect(next_url)
    tries = int(cache.get(_twofa_tries_key(user.pk)) or 0) + 1
    if tries >= TWOFA_MAX_ATTEMPTS:
        _twofa_clear(request)
        messages.error(request, _("Слишком много неверных кодов. Вход отменён — попробуйте снова."))
        return render(request, "core/login.html", {"form": LoginForm()})
    cache.set(_twofa_tries_key(user.pk), tries, TWOFA_CODE_TTL)
    messages.error(
        request, _("Неверный код. Осталось попыток: %d.") % (TWOFA_MAX_ATTEMPTS - tries)
    )
    return render(request, "core/login.html", {
        "form": LoginForm(),
        "twofa": True,
        "twofa_email": user.email,
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect("/")
    # второй шаг: POST формы кода (без email/пароля)
    if request.method == "POST" and "code" in request.POST:
        return _twofa_code_view(request)
    form = LoginForm(request.POST or None)
    if request.method == "POST":
        # per-IP лимит до любых проверок: fail-closed при недоступном кэше
        try:
            enforce_ip_limit(request, "login", 20, 3600)
        except RateLimitExceeded:
            messages.error(request, _("Слишком много попыток с вашего IP. Попробуйте позже."))
            return render(request, "core/login.html", {"form": form})
        except RateLimitUnavailable:
            messages.error(request, _("Сервис входа временно недоступен. Попробуйте позже."))
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
                # второй фактор: пароль верный, но authenticated-сессии ещё нет
                if user.two_factor_enabled:
                    return _twofa_start(request, user)
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
                    messages.error(request, _("Неверный email или пароль, либо аккаунт заблокирован/не подтверждён."))
    pending = _twofa_pending(request) if request.method == "GET" else None
    if pending is not None:
        return render(request, "core/login.html", {
            "form": form,
            "twofa": True,
            "twofa_email": pending.email,
        })
    return render(request, "core/login.html", {"form": form})


@require_POST
def logout_view(request):
    auth_logout(request)
    messages.info(request, _("Вы вышли."))
    return redirect(settings.LOGOUT_REDIRECT_URL or "core:jobs")
