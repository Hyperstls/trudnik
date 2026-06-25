"""Валидация: validate_password, _SQL_INJECTION_PATTERNS."""

import re
from typing import Optional

from app.utils.security import has_sql_injection as _has_sql_injection

# Устаревший локальный pattern (оставлен для обратной ссылки).
# Используйте has_sql_injection() из app.utils.security.
_SQL_INJECTION_PATTERNS = re.compile(
    r"(?:SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER|CREATE|EXEC(?:UTE)?|TRUNCATE)"
    r"(?:\s|%20|%0a|%0d|/\*|--|#)",
    re.IGNORECASE,
)


def validate_password(password: str) -> Optional[str]:
    """Проверить пароль на соответствие требованиям безопасности.

    Требования:
      - Минимум 8 символов
      - Минимум одна заглавная буква (A-Z)
      - Минимум одна строчная буква (a-z)
      - Минимум одна цифра (0-9)
      - Минимум один специальный символ (!@#$%^&*()_+-=[]{}|;:,.<>?/)

    Args:
        password: строка пароля.

    Returns:
        None если пароль валиден, иначе строка с описанием ошибки.
    """
    if not password or len(password) < 8:
        return 'Пароль должен содержать минимум 8 символов.'

    if not re.search(r'[A-Z]', password):
        return 'Пароль должен содержать минимум одну заглавную букву (A-Z).'

    if not re.search(r'[a-z]', password):
        return 'Пароль должен содержать минимум одну строчную букву (a-z).'

    if not re.search(r'[0-9]', password):
        return 'Пароль должен содержать минимум одну цифру (0-9).'

    if not re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:,.<>?/]', password):
        return 'Пароль должен содержать минимум один специальный символ (!@#$%^&*()_+-=[]{}|;:,.<>?/).'

    if re.search(r'\s', password):
        return 'Пароль не должен содержать пробелы.'

    return None
