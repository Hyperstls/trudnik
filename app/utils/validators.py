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


def validate_inn_checksum(inn: str) -> bool:
    """Проверить контрольную сумму ИНН по алгоритму ФНС.

    Поддерживает 10-значный ИНН (юрлица) и 12-значный ИНН (физлица).

    Алгоритм:
      - 10-значный ИНН: n10 = ((2*n1+4*n2+10*n3+3*n4+5*n5+9*n6+4*n7+6*n8+8*n9) mod 11) mod 10
      - 12-значный ИНН: n11 по тем же коэффициентам, n12 с другими коэффициентами
        (7, 2, 4, 10, 3, 5, 9, 4, 6, 8, 0 для n1-n11)

    Args:
        inn: строка ИНН (только цифры).

    Returns:
        True если контрольная сумма валидна, иначе False.
    """
    if not inn or not inn.isdigit():
        return False

    length = len(inn)

    if length == 10:
        # Юрлица: n10 = ((2*n1+4*n2+10*n3+3*n4+5*n5+9*n6+4*n7+6*n8+8*n9) mod 11) mod 10
        coeffs = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        checksum = sum(coeffs[i] * int(inn[i]) for i in range(9))
        control = (checksum % 11) % 10
        return control == int(inn[9])

    elif length == 12:
        # Физлица: n11 с коэффициентами (7,2,4,10,3,5,9,4,6,8)
        coeffs_11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        checksum_11 = sum(coeffs_11[i] * int(inn[i]) for i in range(10))
        control_11 = (checksum_11 % 11) % 10
        if control_11 != int(inn[10]):
            return False

        # n12 с коэффициентами (3,7,2,4,10,3,5,9,4,6,8)
        coeffs_12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        checksum_12 = sum(coeffs_12[i] * int(inn[i]) for i in range(11))
        control_12 = (checksum_12 % 11) % 10
        return control_12 == int(inn[11])

    return False
