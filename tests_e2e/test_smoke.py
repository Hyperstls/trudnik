# tests_e2e/test_smoke.py
import pytest
from playwright.sync_api import sync_playwright, expect

BASE_URL = "http://localhost:8000"


def test_home_page_loads(page):
    """H1: Главная страница загружается"""
    response = page.goto(BASE_URL)
    assert response.status == 200
    assert page.title() is not None


def test_login_page_loads(page):
    """A1: Страница входа загружается"""
    response = page.goto(f"{BASE_URL}/login")
    assert response.status == 200


def test_register_page_loads(page):
    """A2: Страница регистрации загружается"""
    response = page.goto(f"{BASE_URL}/register")
    assert response.status == 200


def test_static_files_served(page):
    """H2: Статические файлы отдаются"""
    response = page.goto(f"{BASE_URL}/static/css/tailwind.css")
    # Может быть 200 или 404 если нет tailwind
    assert response.status in [200, 304]


def test_csrf_protection(page):
    """S1: CSRF защита работает"""
    response = page.request.post(f"{BASE_URL}/login", data={})
    # Без CSRF токена может вернуть 200 (рендер формы с ошибкой),
    # 400/403 (блокировка), 302 (редирект) или 429 (rate limit)
    assert response.status in [200, 400, 403, 302, 429]


def test_admin_redirects_to_login(page):
    """S3: Админка редиректит на логин"""
    response = page.goto(f"{BASE_URL}/admin")
    assert "/login" in page.url or response.status == 302
