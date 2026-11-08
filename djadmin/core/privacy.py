"""Приватность логов: маскировка email в сообщениях об ошибках (R058, 152-ФЗ)."""


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
