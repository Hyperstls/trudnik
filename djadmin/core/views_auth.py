"""Фаза 2б: регистрация, подтверждение email, сброс пароля.

Контракты (сверены с живой БД и Flask-кодом 2026-10-30):
- register_user(p_email, p_password, p_full_name, p_role, p_worker_visibility) → uuid
  (email_verified=False внутри RPC; доп. поля — прямым UPDATE, как Flask через PATCH);
- change_password(p_email, p_new_password) → boolean (перегрузка из миграции 149,
  чинит и Flask-reset: раньше вызов уходил в несуществующую сигнатуру → PostgREST 404);
- токены: itsdangerous, соли 'password-reset' (3600с) / 'email-verify' (86400с),
  payload {email, pwd_changed_at} — кросс-совместимы с Flask в обе стороны;
- SmartCaptcha: POST {secret, token} → status=ok; включена при наличии
  SMARTCAPTCHA_SERVER_KEY, тогда fail-closed (см. core/captcha.py);
- письма — django.core.mail (SMTP из env; volume низкий, синхронно, без Celery).

Анти-паттерны по ревью: не раскрываем существование email (единые ответы),
cooldown в памяти процесса, honeypot без объяснения причины.
"""
import logging
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .captcha import verify_captcha_token
from .forms_auth import (
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
    RegisterForm,
)
from .models import Profile
from .rpc import call_rpc
from .tokens import (
    generate_email_verification_token,
    generate_reset_token,
    verify_email_verification_token,
    verify_reset_token,
)

logger = logging.getLogger(__name__)
User = get_user_model()

RESEND_COOLDOWN_SECONDS = 120
RESET_COOLDOWN_SECONDS = 300
_COOLDOWNS: dict[str, float] = {}  # key -> until_ts; in-process, масштаб приложения мал


def _cooldown_active(key: str) -> bool:
    until = _COOLDOWNS.get(key, 0.0)
    if until > time.monotonic():
        return True
    _COOLDOWNS.pop(key, None)
    return False


def _set_cooldown(key: str, seconds: int) -> None:
    _COOLDOWNS[key] = time.monotonic() + seconds


def _send_mail(subject: str, message: str, to_email: str) -> None:
    from django.core.mail import send_mail

    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)
    except Exception:
        # сбой SMTP не должен ронять флоу: ссылка продублируется через resend
        logger.exception("email send failed to=%s", to_email)


def _site_url(request) -> str:
    base = getattr(settings, "WORKER_SITE_URL", "")
    if base:
        return base
    scheme = "https" if request.is_secure() else "http"
    return "%s://%s" % (scheme, request.get_host())


# ── Регистрация ─────────────────────────────────────────────────────────────
def register(request):
    if request.user.is_authenticated:
        return redirect("/")
    form = RegisterForm(request.POST or None)
    captcha_ctx = {"captcha_client_key": settings.SMARTCAPTCHA_CLIENT_KEY}
    if request.method == "POST" and form.is_valid():
        if not verify_captcha_token(form.cleaned_data.get("smart_token", "")):
            messages.error(request, "Капча не пройдена. Попробуйте ещё раз.")
            return render(request, "core/register.html", {"form": form, **captcha_ctx})
        email = form.cleaned_data["email"]
        role, worker_visibility = form.role_and_visibility()
        try:
            result = call_rpc(
                "register_user",
                email, form.cleaned_data["password"], form.cleaned_data["full_name"],
                role, worker_visibility,
            )
        except IntegrityError:
            result = None
        except Exception:
            logger.exception("register_user rpc failed")
            result = None
        user_id = None
        if isinstance(result, dict):
            raw = result.get("register_user")
            user_id = str(raw) if raw else None
        if user_id is None:
            # единый ответ: не подтверждаем, существует ли email
            form.add_error(None, "Регистрация не выполнена. Проверьте данные: возможно, такой email уже зарегистрирован.")
        else:
            Profile.objects.filter(pk=user_id).update(
                city=form.cleaned_data.get("city") or None,
                consented_at=timezone.now(),
            )
            token = generate_email_verification_token(email)
            link = "%s/verify-email/%s" % (_site_url(request), token)
            _send_mail(
                "Трудник: подтвердите email",
                "Здравствуйте!\n\nПерейдите по ссылке для подтверждения email (24 часа):\n%s\n\n"
                "Если вы не регистрировались на «Трудник» — просто игнорируйте письмо." % link,
                email,
            )
            messages.success(
                request,
                "Аккаунт создан. Мы отправили письмо со ссылкой подтверждения — проверьте почту.",
            )
            return redirect("core:login")
    return render(request, "core/register.html", {"form": form, **captcha_ctx})


# ── Подтверждение email ─────────────────────────────────────────────────────
def verify_email(request, token: str):
    email = verify_email_verification_token(token)
    if email:
        updated = Profile.objects.filter(email=email).update(email_verified=True)
        if updated:
            messages.success(request, "Email подтверждён. Теперь можно войти.")
            return redirect("core:login")
    messages.error(request, "Ссылка недействительна или истекла. Запросите новую.")
    return redirect("core:verify_email_resend")


def verify_email_resend(request):
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        if email and not _cooldown_active("verify_resend:%s" % email):
            _set_cooldown("verify_resend:%s" % email, RESEND_COOLDOWN_SECONDS)
            profile = Profile.objects.filter(email=email).values_list("id", flat=True).first()
            if profile:
                token = generate_email_verification_token(email)
                link = "%s/verify-email/%s" % (_site_url(request), token)
                _send_mail(
                    "Трудник: подтвердите email",
                    "Ссылка для подтверждения email (24 часа):\n%s" % link,
                    email,
                )
        messages.info(request, "Если аккаунт существует, письмо отправлено (не чаще раза в 2 минуты).")
        return redirect("core:login")
    return render(request, "core/verify_email_resend.html")


# ── Сброс пароля ────────────────────────────────────────────────────────────
def password_reset_request(request):
    form = PasswordResetRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        if not verify_captcha_token(form.cleaned_data.get("smart_token", "")):
            messages.error(request, "Капча не пройдена. Попробуйте ещё раз.")
            return render(request, "core/password_reset_request.html", {"form": form})
        if not _cooldown_active("reset:%s" % email):
            _set_cooldown("reset:%s" % email, RESET_COOLDOWN_SECONDS)
            profile = Profile.objects.filter(email=email).values_list(
                "id", "password_changed_at"
            ).first()
            if profile:
                pwd_changed_at = profile[1].isoformat() if profile[1] else ""
                token = generate_reset_token(email, pwd_changed_at)
                link = "%s/password-reset/confirm/%s" % (_site_url(request), token)
                _send_mail(
                    "Трудник: сброс пароля",
                    "Для смены пароля перейдите по ссылке (1 час):\n%s\n\n"
                    "Если вы не запрашивали сброс — игнорируйте письмо." % link,
                    email,
                )
        # единый ответ: не раскрываем существование email
        messages.info(request, "Если аккаунт существует, письмо с инструкцией отправлено.")
        return redirect("core:login")
    return render(request, "core/password_reset_request.html", {"form": form})


def password_reset_confirm(request, token: str):
    payload = verify_reset_token(token)
    profile = None
    if payload:
        profile = Profile.objects.filter(email=payload["email"]).values_list(
            "id", "password_changed_at"
        ).first()
        # B11: после смены пароля старый токен мёртв
        if profile and payload.get("pwd_changed_at"):
            current = profile[1].isoformat() if profile[1] else ""
            if current != payload["pwd_changed_at"]:
                payload = None
    if not payload or not profile:
        messages.error(request, "Ссылка недействительна или истекла. Запросите сброс заново.")
        return redirect("core:password_reset_request")
    form = PasswordResetConfirmForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ok = False
        try:
            ok = bool(call_rpc("change_password", payload["email"], form.cleaned_data["new_password"]))
        except Exception:
            logger.exception("change_password(2-arg) rpc failed")
        if ok:
            messages.success(request, "Пароль изменён. Войдите с новым паролем.")
            return redirect("core:login")
        form.add_error(None, "Не удалось изменить пароль. Попробуйте позже.")
    return render(request, "core/password_reset_confirm.html", {"form": form, "token": token})
