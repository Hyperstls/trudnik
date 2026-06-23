"""Unit-тесты безопасности: валидация паролей, санитизация, UUID."""

import pytest
from app.utils.validators import validate_password
from app.utils.security import sanitize_postgrest, validate_uuid


def test_validate_password_strong():
    """Валидный пароль проходит проверку."""
    result = validate_password('StrongP@ss1')
    assert result is None  # None означает валидный


def test_validate_password_short():
    """Короткий пароль отклоняется."""
    result = validate_password('Abc1!')
    assert result is not None


def test_validate_password_no_uppercase():
    """Пароль без заглавной отклоняется."""
    result = validate_password('weakp@ss1')
    assert result is not None


def test_validate_password_no_special():
    """Пароль без спецсимвола отклоняется."""
    result = validate_password('WeakPass1')
    assert result is not None


def test_validate_password_no_digit():
    """Пароль без цифры отклоняется."""
    result = validate_password('WeakP@ssword')
    assert result is not None


def test_validate_password_with_spaces():
    """Пароль с пробелами отклоняется."""
    result = validate_password('Strong P@ss1')
    assert result is not None


def test_sanitize_postgrest_removes_html():
    """sanitize_postgrest удаляет HTML-теги."""
    result = sanitize_postgrest('<script>alert(1)</script>')
    assert '<script>' not in result
    assert 'script' not in result.lower()


def test_sanitize_postgrest_preserves_cyrillic():
    """sanitize_postgrest сохраняет кириллицу."""
    result = sanitize_postgrest('Москва')
    assert 'Москва' in result


def test_sanitize_postgrest_removes_semicolon():
    """sanitize_postgrest удаляет точку с запятой."""
    result = sanitize_postgrest('test;DROP TABLE')
    assert ';' not in result


def test_validate_uuid_invalid():
    """Невалидный UUID отклоняется."""
    assert not validate_uuid('not-a-uuid')


def test_validate_uuid_valid():
    """Валидный UUID проходит."""
    assert validate_uuid('123e4567-e89b-12d3-a456-426614174000')


def test_validate_uuid_empty():
    """Пустая строка — невалидный UUID."""
    assert not validate_uuid('')


def test_validate_uuid_none():
    """None — невалидный UUID."""
    assert not validate_uuid(None)
