"""Общие фикстуры для E2E/Playwright тестов в tests_e2e/.

Все тестовые файлы в этой директории используют ОДИН браузер на сессию,
чтобы избежать конфликта sync_playwright() с asyncio event loop.
"""
import os
import pytest
from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8000')


@pytest.fixture(scope="session")
def browser():
    """Один браузер на всю тестовую сессию (headless Chromium).

    Определён здесь ОДИН раз — все файлы tests_e2e/ используют его.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    """Новая изолированная страница для каждого теста с русской локалью."""
    context = browser.new_context(
        viewport={'width': 1440, 'height': 900},
        locale='ru-RU'
    )
    page = context.new_page()
    page.set_default_timeout(15000)
    yield page
    context.close()
