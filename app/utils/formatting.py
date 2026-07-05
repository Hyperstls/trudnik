"""Форматирование: даты, валюта, текст (русская локализация)."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

# Русские названия месяцев (родительный падеж)
_MONTHS_RU = [
    'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
]

# Московский часовой пояс (Europe/Moscow)
_MSK_TZ = ZoneInfo('Europe/Moscow')


def format_datetime(iso_string: Optional[str]) -> str:
    """Преобразовать ISO-строку даты в человеко-читаемый формат на русском.

    Поддерживаемые форматы:
      - '2026-06-16T00:47'       → '16 июня 2026, 00:47'
      - '2026-06-16T00:47:00'    → '16 июня 2026, 00:47'
      - '2026-06-16T00:47:00+00:00' → с учётом временной зоны
      - '2026-06-16'             → '16 июня 2026'
      - Сегодняшняя дата         → 'Сегодня, 14:30'
      - Вчерашняя дата           → 'Вчера, 09:15'

    Все даты без временной зоны считаются UTC и конвертируются в MSK (UTC+3).

    Args:
        iso_string: ISO-формат даты/времени или None/пустая строка.

    Returns:
        Отформатированная строка или '—' при невалидном вводе.
    """
    if not iso_string:
        return '—'

    try:
        dt = None
        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d'):
            try:
                dt = datetime.strptime(iso_string[:len(fmt)], fmt)
                break
            except (ValueError, IndexError):
                continue

        if dt is None:
            try:
                dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                return '—'

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        dt_msk = dt.astimezone(_MSK_TZ)
        now_msk = datetime.now(timezone.utc).astimezone(_MSK_TZ)

        has_time = 'T' in str(iso_string) and len(iso_string) > 10

        if has_time:
            if dt_msk.date() == now_msk.date():
                return f"Сегодня, {dt_msk.strftime('%H:%M')}"
            if dt_msk.date() == (now_msk - timedelta(days=1)).date():
                return f"Вчера, {dt_msk.strftime('%H:%M')}"

        month_name = _MONTHS_RU[dt_msk.month - 1]
        if has_time:
            return f"{dt_msk.day} {month_name} {dt_msk.year}, {dt_msk.strftime('%H:%M')}"
        else:
            return f"{dt_msk.day} {month_name} {dt_msk.year}"

    except Exception:
        return '—'


def format_date(iso_string: Optional[str]) -> str:
    """Синоним format_datetime для обратной совместимости."""
    return format_datetime(iso_string)


def format_currency(amount: float, currency: str = '₽') -> str:
    """Форматировать сумму с разделителями тысяч.

    Args:
        amount: сумма.
        currency: символ валюты (по умолчанию ₽).

    Returns:
        Строка вида '1 500 ₽'.
    """
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return f'0 {currency}'

    if amount == int(amount):
        formatted = f'{int(amount):,}'.replace(',', ' ')
    else:
        formatted = f'{amount:,.2f}'.replace(',', ' ')

    return f'{formatted} {currency}'


def truncate(text: str, max_length: int = 100, ellipsis: str = '…') -> str:
    """Обрезать текст до заданной длины с добавлением многоточия.

    Args:
        text: исходный текст.
        max_length: максимальная длина.
        ellipsis: символ(ы) многоточия.

    Returns:
        Обрезанный текст или исходный, если он короче лимита.
    """
    if not text or len(text) <= max_length:
        return text or ''
    return text[:max_length - len(ellipsis)].rstrip() + ellipsis


def pluralize(count: int, one: str, few: str, many: str) -> str:
    """Склонение существительного в зависимости от числа (русский язык).

    Args:
        count: число.
        one: форма для 1 (например, 'заявка').
        few: форма для 2-4 (например, 'заявки').
        many: форма для 5-0 и 11-19 (например, 'заявок').

    Returns:
        Подходящая форма слова.
    """
    n = abs(count) % 100
    if 11 <= n <= 19:
        return many
    n = n % 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many
