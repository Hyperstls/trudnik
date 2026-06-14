"""
Общие fixtures и хелперы для тестов проекта «Трудник».
Pytest автоматически находит этот файл в корне проекта.

Запуск: python -m pytest -v --tb=short
"""

import os
import re

import pytest
import requests

# ──────────────────────────────────────────────
# Конфигурация из переменных окружения
# ──────────────────────────────────────────────

BASE_URL = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')
EMPLOYER_EMAIL = os.environ.get('EMPLOYER_EMAIL', 'org@test.ru')
EMPLOYER_PASSWORD = os.environ.get('EMPLOYER_PASSWORD', 'test123')
WORKER_EMAIL = os.environ.get('WORKER_EMAIL', 'trud@test.ru')
WORKER_PASSWORD = os.environ.get('WORKER_PASSWORD', 'test123')


# ──────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────

def extract_csrf_token(html: str) -> str | None:
    """Извлекает CSRF-токен из meta-тега HTML-страницы."""
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    return match.group(1) if match else None


def login_as(session: requests.Session, email: str, password: str) -> str | None:
    """Логинится под указанным пользователем и возвращает CSRF-токен.

    POST /login не требует CSRF (явно пропущен в csrf_check).
    """
    resp = session.get(f'{BASE_URL}/login', timeout=30)
    csrf = extract_csrf_token(resp.text)

    resp = session.post(
        f'{BASE_URL}/login',
        data={'email': email, 'password': password},
        timeout=30,
        allow_redirects=True,
    )
    if 'Ошибка входа' in resp.text:
        return None
    fresh_csrf = extract_csrf_token(resp.text)
    return fresh_csrf or csrf


def get_csrf_from_page(session: requests.Session, path: str = '/') -> str | None:
    """Получает CSRF-токен с указанной страницы."""
    resp = session.get(f'{BASE_URL}{path}', timeout=30)
    return extract_csrf_token(resp.text)


def csrf_headers(session: requests.Session) -> dict:
    """Возвращает заголовки с CSRF-токеном для AJAX-запросов."""
    csrf = get_csrf_from_page(session)
    return {
        'X-CSRF-Token': csrf or '',
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
    }


def form_with_csrf(session: requests.Session, **extra) -> dict:
    """Создаёт словарь данных формы с CSRF-токеном."""
    csrf = get_csrf_from_page(session)
    return {'_csrf_token': csrf or '', **extra}


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture(scope='module')
def employer_session():
    """Сессия работодателя (org@test.ru)."""
    sess = requests.Session()
    csrf = login_as(sess, EMPLOYER_EMAIL, EMPLOYER_PASSWORD)
    if csrf is None:
        pytest.fail('Не удалось войти как работодатель. Проверьте учётные данные.')
    return sess


@pytest.fixture(scope='module')
def worker_session():
    """Сессия трудника (trud3@test.ru)."""
    sess = requests.Session()
    csrf = login_as(sess, WORKER_EMAIL, WORKER_PASSWORD)
    if csrf is None:
        pytest.fail('Не удалось войти как трудник. Проверьте учётные данные.')
    return sess
