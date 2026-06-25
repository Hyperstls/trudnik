"""Безопасность: санитизация ввода, валидация, CSRF-защита."""

import re
import urllib.parse
import uuid as _uuid
import secrets
from typing import Any, Optional

# Whitelist: разрешённые символы для PostgREST-параметров
_ALLOWED_CHARS = set(
    'abcdefghijklmnopqrstuvwxyz'
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    '0123456789'
    'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'
    'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ'
    ' -_./:*!?@#[]{}|+=\\`~%^$'
)

# Предкомпилированный pattern для удаления HTML-тегов (XSS-векторы)
_HTML_TAG_RE = re.compile(r'</?(script|style|iframe|svg)\b[^>]*>', re.IGNORECASE)


def sanitize_postgrest(value: Any) -> Any:
    """Экранировать спецсимволы PostgREST в пользовательском вводе.

    Этапы:
    1. URL-декодирование (%20 → пробел, %27 → ' и т.д.)
    2. Удаление HTML-тегов <script>, <style>, <iframe>, <svg> (XSS-векторы)
    3. Удаление опасных символов: ( ) , ; " ' & < >
    4. Экранирование спецсимволов PostgREST: . → \\., * → \\*
    5. Whitelist-проверка: только разрешённые символы
    6. Обрезка пробелов

    Args:
        value: строка (или не-строка — возвращается как есть).

    Returns:
        Очищенная строка, безопасная для использования в PostgREST-запросах.
    """
    if not isinstance(value, str):
        return value

    # 1. URL-декодирование
    try:
        value = urllib.parse.unquote(value)
    except Exception:
        pass

    # 2. Удаляем HTML-теги (XSS-векторы: <script>, <style>, <iframe>, <svg>)
    value = _HTML_TAG_RE.sub('', value)

    # 3. Удаляем опасные символы, которые могут изменить структуру запроса
    for ch in '(),;"\'&<>':
        value = value.replace(ch, '')

    # 4. Экранируем спецсимволы PostgREST (точка и звёздочка — через backslash)
    value = value.replace('.', '\\.').replace('*', '\\*')

    # 5. Whitelist-проверка: удаляем все символы не из разрешённого набора
    value = ''.join(ch for ch in value if ch in _ALLOWED_CHARS)

    return value.strip()


def sanitize_html(value: str) -> str:
    """Удалить все HTML-теги из строки (для безопасного отображения).

    Args:
        value: потенциально опасная строка.

    Returns:
        Очищенная строка без HTML-тегов.
    """
    if not value:
        return ''
    # Удаляем все HTML-теги
    clean = re.sub(r'<[^>]*>', '', str(value))
    return clean.strip()


def validate_uuid(value: Optional[str]) -> bool:
    """Проверить, является ли строка валидным UUID.

    Args:
        value: строка для проверки.

    Returns:
        True если значение — валидный UUID.
    """
    if not value:
        return False
    try:
        _uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


# Канонический предкомпилированный pattern для обнаружения SQL-инъекций.
# Включает полный набор ключевых слов и разделителей (URL-encoded в том числе).
_SQL_INJECTION_PATTERN = re.compile(
    r"(?:SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER|CREATE|EXEC|EXECUTE|TRUNCATE|DECLARE|WAITFOR|DELAY|OR|AND|HAVING|GROUP\s+BY|ORDER\s+BY)"
    r"(?:\s|%20|%0a|%0d|/\*|--|#|=|')",
    re.IGNORECASE
)

# Вариант без AND/OR — для валидации имён, email, где AND/OR могут быть легитимными
_SQL_INJECTION_PATTERN_NO_AND_OR = re.compile(
    r"(?:SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER|CREATE|EXEC|EXECUTE|TRUNCATE|DECLARE|WAITFOR|DELAY|HAVING|GROUP\s+BY|ORDER\s+BY)"
    r"(?:\s|%20|%0a|%0d|/\*|--|#|=|')",
    re.IGNORECASE
)


def has_sql_injection(value: str, include_and_or: bool = False, include_url_encoded: bool = True) -> bool:
    """Проверить, содержит ли строка признаки SQL-инъекции.

    Использует один канонический regex для обнаружения ключевых слов SQL
    в сочетании с разделителями (пробелы, комментарии, URL-encode).

    Args:
        value: строка для проверки.
        include_and_or: включить AND/OR в проверку (по умолчанию False, т.к. они
            наиболее вероятны в легитимных именах и названиях).
        include_url_encoded: включить URL-encoded разделители (%20, %0a и т.д.)
            в проверку (по умолчанию True).

    Returns:
        True если строка содержит признаки SQL-инъекции, иначе False.
    """
    if not value or not isinstance(value, str):
        return False

    if include_and_or and include_url_encoded:
        return bool(_SQL_INJECTION_PATTERN.search(value))
    elif not include_and_or:
        return bool(_SQL_INJECTION_PATTERN_NO_AND_OR.search(value))
    else:
        # include_and_or=True, include_url_encoded=False — собираем на лету
        pattern = re.compile(
            r"(?:SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER|CREATE|EXEC|EXECUTE|TRUNCATE|DECLARE|WAITFOR|DELAY|OR|AND|HAVING|GROUP\s+BY|ORDER\s+BY)"
            r"(?:\s|/\*|--|#|=|')",
            re.IGNORECASE
        )
        return bool(pattern.search(value))


def generate_csrf_token() -> str:
    """Сгенерировать CSRF-токен.

    Returns:
        Случайная hex-строка (32 байта).
    """
    return secrets.token_hex(32)
