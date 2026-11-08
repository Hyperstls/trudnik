"""Приватность логов: маскировка email в сообщениях об ошибках (R058/R068, 152-ФЗ)."""
import re


def mask_email(email: str) -> str:
    """'user@example.com' → 'us***@example.com'; безопасно для любых входов.

    Локальная часть: первые 2 символа + '***'. Без '@' — маскируем как
    произвольную строку (первые 2 + '***'). Пустая — ''.
    """
    if not email:
        return ""
    email = str(email)
    if "@" in email:
        local, _, domain = email.partition("@")
        head = local[:2]
        return "%s***@%s" % (head, domain)
    return "%s***" % email[:2]


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def mask_text(text) -> str:
    """Маскирует все email внутри произвольного текста (логи, ошибки SMTP).

    SMTPRecipientsRefused печатает словарь {'user@example.com': (...)} — один
    mask_email на поле to= этого не закрывает (строгий аудит 2026-11-08, A1).
    """
    if not text:
        return ""
    return EMAIL_RE.sub(lambda m: mask_email(m.group(0)), str(text))
