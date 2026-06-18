"""
Конфигурационные фикстуры Playwright для E2E-тестов проекта «Трудник».
Используется тестами Блоков 2 и 3.

Фикстуры этого файла НЕ зависят от tests/conftest.py —
у них разная природа (browser vs requests).

Запуск: python -m pytest tests/ -m e2e --browser chromium
"""

import json
import os
import re
import time

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

# ──────────────────────────────────────────────
# Константы
# ──────────────────────────────────────────────

BASE_URL = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')
EMPLOYER_EMAIL = os.environ.get('EMPLOYER_EMAIL', 'org@test.ru')
EMPLOYER_PASSWORD = os.environ.get('EMPLOYER_PASSWORD', 'Step@1986')
WORKER_EMAIL = os.environ.get('WORKER_EMAIL', 'trud@test.ru')
WORKER_PASSWORD = os.environ.get('WORKER_PASSWORD', 'Step@1986')

VIEWPORTS = {
    'mobile': (320, 568),
    'tablet': (768, 1024),
    'desktop': (1024, 768),
}

# ──────────────────────────────────────────────
# Хелпер-функции
# ──────────────────────────────────────────────


def extract_csrf_token(page: Page) -> str | None:
    """Извлекает CSRF-токен из meta[name="csrf-token"] на текущей странице."""
    try:
        meta = page.locator('meta[name="csrf-token"]')
        if meta.count() > 0:
            return meta.get_attribute('content')
    except Exception:
        pass
    return None


def login_as(page: Page, email: str, password: str) -> None:
    """Логинится через форму /login и ждёт редирект.

    POST /login не требует CSRF (явно пропущен в csrf_check).
    При 429 (rate limit) — ждёт 5 сек и пробует снова (до 3 попыток).
    """
    for attempt in range(3):
        page.goto(f'{BASE_URL}/login', wait_until='domcontentloaded')
        page.wait_for_selector('form', timeout=10000)

        # Заполняем и отправляем форму
        page.fill('input[name="email"]', email)
        page.fill('input[name="password"]', password)
        page.click('button[type="submit"]')

        # Ждём завершения навигации после логина
        page.wait_for_load_state('networkidle', timeout=15000)

        # Если попали на rate-limit — ждём и пробуем снова
        if '429' in page.content() or 'Too Many Requests' in page.content():
            time.sleep(5)
            continue

        # Проверяем, что нет сообщения об ошибке входа
        if 'Ошибка входа' in page.content():
            time.sleep(2)
            continue

        # Успешный вход
        return

    raise RuntimeError(
        f'Не удалось залогиниться как {email} после 3 попыток'
    )


def relogin_if_expired(page: Page, email: str, password: str) -> None:
    """Проверяет валидность сессии и перелогинивается при необходимости.

    Если body отсутствует или страница вернула 401/редирект на логин —
    выполняет повторный вход.
    """
    try:
        # Проверяем, что страница жива и мы не на странице логина
        body = page.locator('body')
        if body.count() == 0:
            login_as(page, email, password)
            return

        current_url = page.url
        if '/login' in current_url:
            login_as(page, email, password)
            return

    except Exception:
        login_as(page, email, password)


# ──────────────────────────────────────────────
# Фикстуры (function scope)
# ──────────────────────────────────────────────


@pytest.fixture(scope='function')
def playwright_browser() -> Browser:
    """Запускает headed Chromium браузер для отладки E2E-тестов.

    headless=False — браузер видим (удобно при разработке).
    slow_mo=100 — замедление операций для наглядности.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            slow_mo=100,
        )
        yield browser
        browser.close()


@pytest.fixture(scope='function')
def employer_context(playwright_browser: Browser) -> tuple[BrowserContext, Page]:
    """Изолированный контекст с залогиненным работодателем.

    Returns:
        (BrowserContext, Page) — контекст и страница.
    """
    context = playwright_browser.new_context(
        viewport={'width': 1024, 'height': 768},
        locale='ru-RU',
    )
    page = context.new_page()
    login_as(page, EMPLOYER_EMAIL, EMPLOYER_PASSWORD)

    yield context, page

    page.close()
    context.close()


@pytest.fixture(scope='function')
def worker_context(playwright_browser: Browser) -> tuple[BrowserContext, Page]:
    """Изолированный контекст с залогиненным трудником.

    Returns:
        (BrowserContext, Page) — контекст и страница.
    """
    context = playwright_browser.new_context(
        viewport={'width': 1024, 'height': 768},
        locale='ru-RU',
    )
    page = context.new_page()
    login_as(page, WORKER_EMAIL, WORKER_PASSWORD)

    yield context, page

    page.close()
    context.close()


@pytest.fixture(scope='function')
def employer_page(employer_context: tuple[BrowserContext, Page]) -> Page:
    """Упрощённая фикстура — возвращает только page работодателя."""
    _ctx, page = employer_context
    return page


@pytest.fixture(scope='function')
def worker_page(worker_context: tuple[BrowserContext, Page]) -> Page:
    """Упрощённая фикстура — возвращает только page трудника."""
    _ctx, page = worker_context
    return page


@pytest.fixture(scope='function')
def browser_contexts(playwright_browser: Browser) -> dict:
    """Два изолированных контекста: работодатель + трудник.

    Ключевая фикстура для multi-context тестов Блока 3.
    Оба пользователя залогинены в отдельных контекстах.

    Returns:
        dict: {
            'employer': (BrowserContext, Page),
            'worker': (BrowserContext, Page),
        }
    """
    # Контекст работодателя
    ctx_a = playwright_browser.new_context(
        viewport={'width': 1024, 'height': 768},
        locale='ru-RU',
    )
    page_a = ctx_a.new_page()
    login_as(page_a, EMPLOYER_EMAIL, EMPLOYER_PASSWORD)

    # Контекст трудника
    ctx_b = playwright_browser.new_context(
        viewport={'width': 1024, 'height': 768},
        locale='ru-RU',
    )
    page_b = ctx_b.new_page()
    login_as(page_b, WORKER_EMAIL, WORKER_PASSWORD)

    result = {
        'employer': (ctx_a, page_a),
        'worker': (ctx_b, page_b),
    }

    yield result

    # Закрываем оба контекста
    page_a.close()
    ctx_a.close()
    page_b.close()
    ctx_b.close()


# ──────────────────────────────────────────────
# Accessibility (a11y) аудит
# ──────────────────────────────────────────────


def run_accessibility_audit(page: Page) -> list[dict]:
    """Запускает axe-core аудит страницы и возвращает критические/серьёзные нарушения.

    Требует: pip install axe-playwright-python

    Args:
        page: Playwright Page объект.

    Returns:
        Список violations с impact в ('critical', 'serious').
        Если модуль не установлен — возвращает [] с предупреждением в stdout.
    """
    try:
        from axe_playwright_python.sync_playwright import Axe

        axe = Axe()
        results = axe.run(page)

        violations = [
            v for v in results.get('violations', [])
            if v.get('impact') in ('critical', 'serious')
        ]
        return violations

    except ImportError:
        import warnings
        warnings.warn(
            'axe-playwright-python не установлен. '
            'Установите: pip install axe-playwright-python'
        )
        return []
