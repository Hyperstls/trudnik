"""R029: opt-in staff-2FA — код на email при входе в админку.

Код живёт в общем кэше 10 минут (Redis в проде — второй воркер видит его),
счётчик неверных попыток — там же. Сессионная отметка ``admin_2fa_ok``
хранит pk пользователя, прошедшего проверку: смена пользователя в той же
сессии не переиспользует чужую отметку.

Экран ввода кода и включение флага — R030; здесь только сервис и middleware.
"""
import hmac
import logging
import secrets
from urllib.parse import quote

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import redirect

logger = logging.getLogger(__name__)

from .privacy import mask_email

CODE_TTL = 600
MAX_ATTEMPTS = 5
SESSION_KEY = "admin_2fa_ok"

_CODE_KEY = "admin_2fa_code:%s"
_TRIES_KEY = "admin_2fa_tries:%s"
_ADMIN_PREFIX = "/admin/"


def _send_mail(subject: str, message: str, to_email: str) -> None:
    """Письмо через общую транзакционную очередь; сбой брокера — синхронно.

    Сбой SMTP не роняет issue_code: пользователь запросит код повторно.
    """
    from django.core.mail import send_mail

    if getattr(settings, "TRANSACTIONAL_EMAIL_ASYNC", True):
        try:
            from .tasks import send_transactional_email

            send_transactional_email.delay(subject, message, to_email)
            return
        except Exception:
            logger.warning(
                "admin 2fa email enqueue failed to=%s", mask_email(to_email),
                exc_info=True,
            )
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)
    except Exception as exc:
        # SMTPRecipientsRefused печатает адрес в str(exc) — маскируем (R078)
        from .privacy import mask_text

        logger.warning(
            "admin 2fa email send failed to=%s (%s): %s",
            mask_email(to_email), type(exc).__name__, mask_text(str(exc))[:300],
        )


def _is_six_ascii_digits(code) -> bool:
    return (
        isinstance(code, str)
        and len(code) == 6
        and code.isascii()
        and code.isdigit()
    )


def issue_code(user) -> bool:
    """Выдать новый код: старый код и счётчик попыток сбрасываются."""
    code = "%06d" % secrets.randbelow(10 ** 6)
    cache.set(_CODE_KEY % user.pk, code, CODE_TTL)
    cache.delete(_TRIES_KEY % user.pk)
    _send_mail(
        "Трудник: код входа в админку",
        "Код: %s\n\nКод действует 10 минут. Если вы не запрашивали вход в админку — "
        "смените пароль." % code,
        user.email,
    )
    return True


def verify_code(user, code) -> bool:
    """Проверить код. Только 6 ASCII-цифр; сравнение — constant-time.

    5 неверных попыток сбрасывают код и счётчик: повторный ввод невозможен
    без нового issue_code.
    """
    if not _is_six_ascii_digits(code):
        return False
    stored = cache.get(_CODE_KEY % user.pk)
    if not stored:
        return False
    if hmac.compare_digest(code.encode("ascii"), str(stored).encode("ascii")):
        cache.delete(_CODE_KEY % user.pk)
        cache.delete(_TRIES_KEY % user.pk)
        return True
    tries = (cache.get(_TRIES_KEY % user.pk) or 0) + 1
    if tries >= MAX_ATTEMPTS:
        cache.delete(_CODE_KEY % user.pk)
        cache.delete(_TRIES_KEY % user.pk)
    else:
        cache.set(_TRIES_KEY % user.pk, tries, CODE_TTL)
    return False


def is_verified(request) -> bool:
    """Отметка в сессии привязана к pk: чужой/старый pk не проходит."""
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return request.session.get(SESSION_KEY) == str(user.pk)


def mark_verified(request) -> None:
    request.session[SESSION_KEY] = str(request.user.pk)


def clear_verified(request) -> None:
    request.session.pop(SESSION_KEY, None)


def needs_admin_2fa(request) -> bool:
    """Staff без отметки на /admin/ при включённом ADMIN_2FA_REQUIRED."""
    if not getattr(settings, "ADMIN_2FA_REQUIRED", False):
        return False
    path = request.path
    if not (path == _ADMIN_PREFIX.rstrip("/") or path.startswith(_ADMIN_PREFIX)):
        return False
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if not getattr(user, "is_staff", False):
        return False
    return not is_verified(request)


class Admin2FAMiddleware:
    """Перенаправляет неверифицированных staff на экран ввода кода (R030).

    Exempt-пути обязаны проходить без кода: иначе login/2fa/static
    зацикливают редирект. Не-staff и анонимы не трогаются — их обрабатывает
    штатная админка (редирект на /admin/login/).
    """

    EXEMPT_PATHS = (
        "/admin/login/",
        "/admin/logout/",
        "/admin/2fa/",
        "/admin/jsi18n/",
        "/admin/static/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if any(request.path.startswith(prefix) for prefix in self.EXEMPT_PATHS):
            return self.get_response(request)
        if needs_admin_2fa(request):
            return redirect("/admin/2fa/?next=%s" % quote(request.get_full_path()))
        return self.get_response(request)
