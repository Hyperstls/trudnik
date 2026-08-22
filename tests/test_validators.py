"""Unit-тесты для app/utils/validators.py.

Покрывает:
- validate_password() — требования к паролю (None = валиден)
- check_password_strength() — {score, max_score, feedback, is_strong}
- validate_inn_checksum() — контрольная сумма ИНН 10/12 цифр (алгоритм ФНС)
- _SQL_INJECTION_PATTERNS — устаревший regex (обратная совместимость)

Тестовый пароль 'Aa1!aaaa' — намеренно низкой энтропии (правило проекта:
НЕ флагируется GitGuardian/detect-secrets).

Запуск: python -m pytest tests/test_validators.py -v --tb=short
"""

import pytest

from app.utils.validators import (
    _SQL_INJECTION_PATTERNS,
    check_password_strength,
    parse_float,
    validate_inn_checksum,
    validate_password,
)


# ═══════════════════════════════════════════════════════════════
# validate_password()
# ═══════════════════════════════════════════════════════════════

class TestValidatePassword:
    """None = валиден, строка = текст ошибки."""

    # ── Happy path ──
    def test_valid_password(self):
        assert validate_password('Aa1!aaaa') is None

    def test_valid_long_password(self):
        assert validate_password('Str0ng!Passw0rd#2026') is None

    def test_boundary_exactly_8_chars(self):
        """Ровно 8 символов со всеми классами — валидно."""
        assert validate_password('Aa1!aaaa') is None

    # ── Edge cases ──
    def test_empty_string(self):
        assert validate_password('') == 'Пароль должен содержать минимум 8 символов.'

    def test_none(self):
        assert validate_password(None) == 'Пароль должен содержать минимум 8 символов.'

    def test_seven_chars(self):
        """7 символов (граничный случай) — ошибка длины."""
        assert validate_password('Aa1!aaa') == 'Пароль должен содержать минимум 8 символов.'

    def test_contains_space(self):
        """Пробел в пароле — отдельная ошибка."""
        assert validate_password('Aa1!aaa a') == 'Пароль не должен содержать пробелы.'

    # ── Negative cases ──
    def test_no_uppercase(self):
        assert 'заглавную' in validate_password('aa1!aaaa')

    def test_no_lowercase(self):
        assert 'строчную' in validate_password('AA1!AAAA')

    def test_no_digit(self):
        assert 'цифру' in validate_password('Aa!!aaaa')

    def test_no_special(self):
        assert 'специальный символ' in validate_password('Aa1aaaaa')


# ═══════════════════════════════════════════════════════════════
# check_password_strength()
# ═══════════════════════════════════════════════════════════════

class TestCheckPasswordStrength:
    """score 0..5, is_strong = score >= 4."""

    def test_strong_password(self):
        """8 символов + регистры + цифра + спец = score 4, is_strong."""
        result = check_password_strength('Aa1!aaaa')
        assert result['score'] == 4
        assert result['max_score'] == 5
        assert result['is_strong'] is True
        assert result['feedback'] == []

    def test_very_strong_password(self):
        """13+ символов со всеми классами = максимальный score 5."""
        result = check_password_strength('Aa1!aaaaaaaaaaa')
        assert result['score'] == 5
        assert result['is_strong'] is True

    def test_weak_password(self):
        """Только длина — score 1, не сильный, 3 подсказки."""
        result = check_password_strength('password')
        assert result['score'] == 1
        assert result['is_strong'] is False
        assert len(result['feedback']) == 3

    def test_empty_password(self):
        """Пустая строка — score 0, все подсказки."""
        result = check_password_strength('')
        assert result['score'] == 0
        assert result['is_strong'] is False
        assert len(result['feedback']) == 4

    def test_medium_password(self):
        """Регистры + цифра + спец, но 7 символов — score 3, не сильный."""
        result = check_password_strength('Aa1!xyz')
        assert result['score'] == 3
        assert result['is_strong'] is False
        assert 'Минимум 8 символов' in result['feedback']


# ═══════════════════════════════════════════════════════════════
# validate_inn_checksum()
# ═══════════════════════════════════════════════════════════════

class TestValidateInnChecksum:
    """Алгоритм ФНС: 10-значный (юрлица) и 12-значный (физлица)."""

    # ── Happy path (контрольные суммы проверены вручную) ──
    def test_valid_inn_10(self):
        """7707083893 — валидный 10-значный ИНН (юрлицо)."""
        assert validate_inn_checksum('7707083893') is True

    def test_valid_inn_12(self):
        """500100732259 — валидный 12-значный ИНН (физлицо)."""
        assert validate_inn_checksum('500100732259') is True

    # ── Negative cases ──
    def test_invalid_inn_10(self):
        """Последняя цифра изменена — контрольная сумма не сходится."""
        assert validate_inn_checksum('7707083894') is False

    def test_invalid_inn_12(self):
        assert validate_inn_checksum('500100732258') is False

    # ── Edge cases ──
    def test_empty_string(self):
        assert validate_inn_checksum('') is False

    def test_none(self):
        assert validate_inn_checksum(None) is False

    def test_letters(self):
        assert validate_inn_checksum('770708389a') is False

    def test_wrong_length_11(self):
        """11 цифр — не поддерживаемая длина."""
        assert validate_inn_checksum('12345678901') is False

    def test_wrong_length_9(self):
        assert validate_inn_checksum('123456789') is False

    def test_spaces_around_digits(self):
        """Пробелы не допускаются — isdigit() False."""
        assert validate_inn_checksum(' 7707083893 ') is False


# ═══════════════════════════════════════════════════════════════
# parse_float()
# ═══════════════════════════════════════════════════════════════

class TestParseFloat:
    """float или None при невалидном вводе / выходе за границы."""

    # ── Happy path ──
    def test_valid_float_string(self):
        assert parse_float('3.14') == 3.14

    def test_valid_integer_string(self):
        assert parse_float('10') == 10.0

    def test_negative_number(self):
        assert parse_float('-2.5') == -2.5

    def test_numeric_float_input(self):
        """float-ввод тоже парсится (float() принимает)."""
        assert parse_float(2.5) == 2.5

    # ── Границы ──
    def test_min_boundary_inclusive(self):
        assert parse_float('5', min_val=5) == 5.0

    def test_below_min(self):
        assert parse_float('4.99', min_val=5) is None

    def test_max_boundary_inclusive(self):
        assert parse_float('5', max_val=5) == 5.0

    def test_above_max(self):
        assert parse_float('5.01', max_val=5) is None

    def test_both_bounds(self):
        assert parse_float('7', min_val=1, max_val=10) == 7.0

    # ── Edge / negative cases ──
    def test_empty_string(self):
        assert parse_float('') is None

    def test_none_value(self):
        assert parse_float(None) is None

    def test_not_a_number(self):
        assert parse_float('abc') is None

    def test_inf_string(self):
        """'inf' парсится в бесконечность — за max_val → None."""
        assert parse_float('inf', max_val=100) is None

    def test_scientific_notation(self):
        assert parse_float('1e2') == 100.0


# ═══════════════════════════════════════════════════════════════
# _SQL_INJECTION_PATTERNS (устаревший, для обратной ссылки)
# ═══════════════════════════════════════════════════════════════

class TestSqlInjectionPattern:
    """Regex оставлен для обратной совместимости; активная проверка —
    app.utils.security.has_sql_injection."""

    def test_matches_select_with_space(self):
        assert _SQL_INJECTION_PATTERNS.search('SELECT * FROM users')

    def test_matches_url_encoded(self):
        assert _SQL_INJECTION_PATTERNS.search('DELETE%20FROM')

    def test_no_false_positive_on_word_start(self):
        """'selection' — SELECT без разделителя, не совпадение."""
        assert not _SQL_INJECTION_PATTERNS.search('selection box')

    def test_plain_text_no_match(self):
        assert not _SQL_INJECTION_PATTERNS.search('привет мир')
