"""
Unit-тесты для утилит проекта «Трудник».

Тестирует:
- sanitize_postgrest() — очистка опасных символов
- calculate_distance() — формула гаверсинусов
- check_withdraw_window() — проверка 12-часового окна

Запуск: python -m pytest tests/test_utils_unit.py -v --tb=short
"""

import math
import time
from datetime import datetime, timezone, timedelta

import pytest

from app.utils import sanitize_postgrest, check_withdraw_window
from app.utils.geo import calculate_distance


# ═══════════════════════════════════════════════════════════════
# Тесты sanitize_postgrest()
# ═══════════════════════════════════════════════════════════════

class TestSanitizePostgrest:
    """P0: Проверка очистки опасных символов для PostgREST."""

    def test_sanitize_clean_string_passes_through(self):
        """Чистая строка без опасных символов возвращается без изменений."""
        result = sanitize_postgrest("hello world")
        assert result == "hello world"

    def test_sanitize_removes_semicolons(self):
        """Точка с запятой удаляется (может изменить структуру запроса)."""
        result = sanitize_postgrest("test;DROP TABLE")
        assert ";" not in result

    def test_sanitize_removes_parentheses(self):
        """Скобки удаляются."""
        result = sanitize_postgrest("func()")
        assert "(" not in result
        assert ")" not in result

    def test_sanitize_removes_quotes(self):
        """Кавычки удаляются."""
        result = sanitize_postgrest("it's \"quoted\"")
        assert "'" not in result
        assert '"' not in result

    def test_sanitize_removes_ampersand(self):
        """Амперсанд удаляется (разделитель параметров PostgREST)."""
        result = sanitize_postgrest("a&b=c")
        assert "&" not in result

    def test_sanitize_removes_commas(self):
        """Запятая удаляется (разделитель списков PostgREST)."""
        result = sanitize_postgrest("a,b,c")
        assert "," not in result

    def test_sanitize_escapes_dot(self):
        """Точка экранируется (PostgREST использует . как оператор)."""
        result = sanitize_postgrest("test.value")
        assert "." not in result or "\\." in result

    def test_sanitize_escapes_asterisk(self):
        """Звёздочка экранируется (wildcard в PostgREST)."""
        result = sanitize_postgrest("test*")
        assert "*" not in result or "\\*" in result

    def test_sanitize_strips_whitespace(self):
        """Пробелы по краям удаляются."""
        result = sanitize_postgrest("  hello  ")
        assert result == "hello"

    def test_sanitize_handles_russian_text(self):
        """Русский текст проходит без потерь."""
        result = sanitize_postgrest("Москва, ул. Тестовая")
        assert "Москва" in result
        assert "Тестовая" in result

    def test_sanitize_handles_url_encoded_input(self):
        """URL-декодирование: %20 → пробел, %27 → '."""
        result = sanitize_postgrest("hello%20world")
        assert "hello world" in result

    def test_sanitize_non_string_returns_as_is(self):
        """Не-строка (int, None) возвращается без изменений."""
        assert sanitize_postgrest(42) == 42
        assert sanitize_postgrest(None) is None
        assert sanitize_postgrest(3.14) == 3.14

    def test_sanitize_xss_vector(self):
        """XSS-вектор должен быть нейтрализован."""
        result = sanitize_postgrest("<script>alert(1)</script>")
        assert "<script>" not in result
        assert "alert" in result  # текст остаётся, теги вырезаются

    def test_sanitize_postgrest_reserved_keywords(self):
        """Ключевые слова PostgREST (eq, lt, gt) очищаются от спецсимволов."""
        result = sanitize_postgrest("eq.open")
        assert "." not in result or "\\." in result


# ═══════════════════════════════════════════════════════════════
# Тесты calculate_distance()
# ═══════════════════════════════════════════════════════════════

class TestCalculateDistance:
    """P0: Проверка формулы гаверсинусов для расчёта расстояний."""

    def test_distance_same_point_is_zero(self):
        """Расстояние между одинаковыми точками = 0."""
        d = calculate_distance(55.75, 37.61, 55.75, 37.61)
        assert d == pytest.approx(0.0, abs=0.01)

    def test_distance_moscow_to_spb(self):
        """Расстояние Москва → Санкт-Петербург ≈ 635 км."""
        # Москва: 55.75, 37.61
        # СПб: 59.93, 30.33
        d = calculate_distance(55.75, 37.61, 59.93, 30.33)
        # Ожидаем ~635 км (±20 км допустимая погрешность)
        assert d == pytest.approx(635.0, rel=0.05), f"Expected ~635 km, got {d}"

    def test_distance_symmetry(self):
        """Расстояние A→B равно B→A."""
        d1 = calculate_distance(55.0, 37.0, 56.0, 38.0)
        d2 = calculate_distance(56.0, 38.0, 55.0, 37.0)
        assert d1 == pytest.approx(d2, abs=0.001)

    def test_distance_positive_for_different_points(self):
        """Расстояние между разными точками > 0."""
        d = calculate_distance(55.0, 37.0, 55.1, 37.0)
        assert d > 0

    def test_distance_equation_line(self):
        """Точки на экваторе: 1 градус долготы ≈ 111.32 км."""
        # На экваторе: lat=0, lon=0 → lat=0, lon=1
        d = calculate_distance(0.0, 0.0, 0.0, 1.0)
        expected = 111.32  # км
        assert d == pytest.approx(expected, rel=0.01), f"Expected ~111.32 km, got {d}"

    def test_distance_returns_float(self):
        """Результат — float."""
        d = calculate_distance(55.0, 37.0, 56.0, 38.0)
        assert isinstance(d, float)


# ═══════════════════════════════════════════════════════════════
# Тесты check_withdraw_window()
# ═══════════════════════════════════════════════════════════════

class TestCheckWithdrawWindow:
    """P0: Проверка 12-часового окна отзыва отклика."""

    def test_window_allows_withdraw_far_future(self):
        """Задание через 24 часа — отзыв разрешён (> 12 часов)."""
        future = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        assert check_withdraw_window(future) is True

    def test_window_allows_withdraw_exactly_13_hours(self):
        """Задание через 13 часов — отзыв разрешён."""
        future = (datetime.now(timezone.utc) + timedelta(hours=13)).isoformat()
        assert check_withdraw_window(future) is True

    def test_window_blocks_withdraw_less_than_12_hours(self):
        """Задание через 6 часов — отзыв запрещён (< 12 часов)."""
        future = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
        assert check_withdraw_window(future) is False

    def test_window_blocks_withdraw_exactly_12_hours(self):
        """Задание ровно через 12 часов — отзыв запрещён (ровно 12 часов не >)."""
        future = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        assert check_withdraw_window(future) is False

    def test_window_blocks_withdraw_past(self):
        """Задание в прошлом — отзыв запрещён."""
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        assert check_withdraw_window(past) is False

    def test_window_allows_withdraw_none_datetime(self):
        """Отсутствие даты (None) — отзыв разрешён (нет ограничения)."""
        assert check_withdraw_window(None) is True

    def test_window_allows_withdraw_empty_string(self):
        """Пустая строка — отзыв разрешён."""
        assert check_withdraw_window("") is True

    def test_window_handles_invalid_format(self):
        """Некорректный формат даты — отзыв разрешён (fallback)."""
        assert check_withdraw_window("not-a-date") is True

    def test_window_handles_zulu_suffix(self):
        """ISO-формат с суффиксом 'Z' обрабатывается корректно."""
        future = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%SZ')
        assert check_withdraw_window(future) is True

    def test_window_handles_timezone_offset(self):
        """ISO-формат с '+00:00' обрабатывается корректно."""
        future = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        assert check_withdraw_window(future) is True
