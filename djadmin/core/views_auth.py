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
- письма — django.core.mail (SMTP из env); через Celery-очередь
  (TRANSACTIONAL_EMAIL_ASYNC), при недоступном брокере — синхронный fallback;
- cooldown сброса/ресенда и IP-лимиты register/reset/resend — в общем кэше
  (Redis в проде): cooldown в памяти процесса обходится вторым воркером.

Анти-паттерны по ревью: не раскрываем существование email (единые ответы),
состояние cooldown в памяти процесса, honeypot без объяснения причины.
Недоступный кэш = fail-closed с сообщением: лимит/cooldown не проверить.
"""
import logging
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .captcha import verify_captcha_token
from .forms_auth import (
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
    RegisterForm,
)
from .models import Profile
from .ratelimit import RateLimitExceeded, RateLimitUnavailable, enforce_ip_limit
from .rpc import call_rpc, sync_user_skills_raw
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


def _cooldown_active(key: str) -> bool:
    """True, если cooldown ещё живёт. Общий кэш: второй воркер тоже видит."""
    try:
        return bool(cache.get("auth_cd:%s" % key))
    except Exception as exc:
        # без кэша cooldown не проверить — fail-closed, а не молчаливая отправка
        raise RateLimitUnavailable("cooldown cache unavailable") from exc


def _set_cooldown(key: str, seconds: int) -> None:
    try:
        cache.set("auth_cd:%s" % key, 1, seconds)
    except Exception as exc:
        raise RateLimitUnavailable("cooldown cache unavailable") from exc


def _send_mail(subject: str, message: str, to_email: str) -> None:
    from django.core.mail import send_mail

    if getattr(settings, "TRANSACTIONAL_EMAIL_ASYNC", True):
        try:
            # импорт внутри try: сбой конфигурации Celery — тоже повод для fallback
            from .tasks import send_transactional_email

            send_transactional_email.delay(subject, message, to_email)
            return
        except Exception:
            # брокер/импорт недоступен: письмо важнее очереди — синхронный fallback
            logger.warning("transactional email enqueue failed to=%s", to_email, exc_info=True)
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
    if request.method == "POST":
        # per-IP лимит до любых проверок: fail-closed при недоступном кэше
        try:
            enforce_ip_limit(request, "register", 10, 3600)
        except RateLimitExceeded:
            messages.error(request, "Слишком много попыток регистрации. Попробуйте позже.")
            return render(request, "core/register.html", {"form": form, **captcha_ctx})
        except RateLimitUnavailable:
            messages.error(request, "Сервис временно недоступен. Попробуйте позже.")
            return render(request, "core/register.html", {"form": form, **captcha_ctx})
    if request.method == "POST" and form.is_valid():
        # виджет Yandex кладёт поле `smart-token`; `smart_token` — backward-compat
        captcha_token = request.POST.get("smart-token") or form.cleaned_data.get("smart_token", "")
        if not verify_captcha_token(captcha_token):
            messages.error(request, "Капча не пройдена. Попробуйте ещё раз.")
            return render(request, "core/register.html", {"form": form, **captcha_ctx})
        email = form.cleaned_data["email"]
        role, worker_visibility = form.role_and_visibility()
        try:
            # savepoint: IntegrityError (дубль email) не должен рушить внешнюю транзакцию
            with transaction.atomic():
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
            profile_fields = {
                "city": form.cleaned_data.get("city") or None,
                "portfolio_link": form.cleaned_data.get("portfolio_link") or "",
                "consented_at": timezone.now(),
            }
            attribution = request.session.pop("attribution", None)
            if isinstance(attribution, dict) and attribution:
                profile_fields["acquisition"] = attribution
            skills = []
            if role == Profile.Role.WORKER:
                profile_fields.update(
                    contact=form.cleaned_data.get("contact") or None,
                    experience=form.cleaned_data.get("experience") or None,
                    desired_payment=form.cleaned_data.get("desired_payment") or None,
                    inn=form.cleaned_data.get("inn") or "",
                    is_self_employed=bool(form.cleaned_data.get("is_self_employed")),
                )
                skills = [s.pk for s in form.cleaned_data.get("skills") or []]
            Profile.objects.filter(pk=user_id).update(**profile_fields)
            if role == Profile.Role.WORKER:
                try:
                    sync_user_skills_raw(user_id, skills)
                except Exception:
                    # навыки — не критичный для регистрации шаг: логируем, не роняем флоу
                    logger.exception("register: sync_user_skills_raw failed user_id=%s", user_id)
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
                "Аккаунт создан. Письмо отправлено на %s. Проверьте почту и папку «Спам»; "
                "если письма нет — отправьте его повторно." % email,
            )
            return redirect(
                "%s?email=%s"
                % (reverse("core:verify_email_resend"), quote(email))
            )
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
    email = (request.GET.get("email") or "").strip().lower()
    if request.method == "POST":
        try:
            enforce_ip_limit(request, "resend", 10, 3600)
        except RateLimitExceeded:
            messages.error(request, "Слишком много попыток. Попробуйте позже.")
            return redirect("core:login")
        except RateLimitUnavailable:
            messages.error(request, "Сервис временно недоступен. Попробуйте позже.")
            return redirect("core:login")
        email = (request.POST.get("email") or "").strip().lower()
        if not email:
            messages.error(request, "Укажите email.")
            return redirect("core:verify_email_resend")
        sent = False
        try:
            if not _cooldown_active("verify_resend:%s" % email):
                _set_cooldown("verify_resend:%s" % email, RESEND_COOLDOWN_SECONDS)
                sent = True
                profile = Profile.objects.filter(email=email).values_list("id", flat=True).first()
                if profile:
                    token = generate_email_verification_token(email)
                    link = "%s/verify-email/%s" % (_site_url(request), token)
                    _send_mail(
                        "Трудник: подтвердите email",
                        "Ссылка для подтверждения email (24 часа):\n%s" % link,
                        email,
                    )
        except RateLimitUnavailable:
            messages.error(request, "Сервис временно недоступен. Попробуйте позже.")
            return redirect("core:login")
        if sent:
            messages.success(request, "Письмо отправлено. Проверьте почту и папку «Спам».")
        else:
            messages.info(request, "Письмо уже отправлялось недавно. Повторить можно через 2 минуты.")
        return redirect(
            "%s?email=%s" % (reverse("core:verify_email_resend"), quote(email))
        )
    return render(request, "core/verify_email_resend.html", {"email": email})


# ── Сброс пароля ────────────────────────────────────────────────────────────
def password_reset_request(request):
    form = PasswordResetRequestForm(request.POST or None)
    captcha_ctx = {"captcha_client_key": settings.SMARTCAPTCHA_CLIENT_KEY}
    if request.method == "POST":
        # per-IP лимит до любых проверок: fail-closed при недоступном кэше
        try:
            enforce_ip_limit(request, "reset", 10, 3600)
        except RateLimitExceeded:
            messages.error(request, "Слишком много попыток. Попробуйте позже.")
            return render(request, "core/password_reset_request.html", {"form": form, **captcha_ctx})
        except RateLimitUnavailable:
            messages.error(request, "Сервис временно недоступен. Попробуйте позже.")
            return render(request, "core/password_reset_request.html", {"form": form, **captcha_ctx})
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        # виджет Yandex кладёт поле `smart-token`; `smart_token` — backward-compat
        captcha_token = request.POST.get("smart-token") or form.cleaned_data.get("smart_token", "")
        if not verify_captcha_token(captcha_token):
            messages.error(request, "Капча не пройдена. Попробуйте ещё раз.")
            return render(request, "core/password_reset_request.html", {"form": form, **captcha_ctx})
        try:
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
        except RateLimitUnavailable:
            messages.error(request, "Сервис временно недоступен. Попробуйте позже.")
            return redirect("core:login")
        # единый ответ: не раскрываем существование email
        messages.info(request, "Если аккаунт существует, письмо с инструкцией отправлено.")
        return redirect("core:login")
    return render(request, "core/password_reset_request.html", {"form": form, **captcha_ctx})


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
