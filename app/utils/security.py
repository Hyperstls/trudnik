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


def generate_csrf_token() -> str:
    """Сгенерировать CSRF-токен.

    Returns:
        Случайная hex-строка (32 байта).
    """
    return secrets.token_hex(32)
