"""Серверные валидации задания (паритет с Flask `jobs.py`).

Юридически значимо: стоп-слова (ст. 15 ТК РФ) не дают переквалифицировать
разовую услугу в трудовые отношения; дата/диапазоны проверяются на сервере,
а не только в HTML-атрибутах виджетов.
"""
from datetime import date, datetime

# Признаки трудовых отношений (ст. 15 ТК РФ).
STOP_WORDS = ('ставка', 'зарплата', 'штат', 'трудовая', 'график', 'постоянная работа', 'вахта')

PAYMENT_MIN = 0
PAYMENT_MAX = 1_000_000
WORKERS_MIN = 1
WORKERS_MAX = 100


def find_stop_words(*texts) -> list:
    """Найти стоп-слова в переданных текстах (в порядке STOP_WORDS, без повторов)."""
    lowered = [str(text).lower() for text in texts if text]
    return [word for word in STOP_WORDS if any(word in text for text in lowered)]


def validate_payment(value) -> str | None:
    """Оплата 0..1 000 000; None — поле необязательное и допустимо."""
    if value is None:
        return None
    if PAYMENT_MIN <= value <= PAYMENT_MAX:
        return None
    return "Оплата должна быть от 0 до 1 000 000 ₽"


def validate_workers(value) -> str | None:
    """Количество работников 1..100; None — поле необязательное и допустимо."""
    if value is None:
        return None
    if WORKERS_MIN <= value <= WORKERS_MAX:
        return None
    return "Количество работников должно быть от 1 до 100"


def validate_deadline(value: date | datetime | None, today: date) -> str | None:
    """Дата выполнения не может быть в прошлом (сегодня — допустимо)."""
    if value is None:
        return None
    deadline = value.date() if isinstance(value, datetime) else value
    if deadline < today:
        return "Дата выполнения не может быть в прошлом"
    return None
