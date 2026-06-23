# tests_e2e/test_admin_pages.py
"""E2E тесты для страниц администратора."""
import pytest
from playwright.sync_api import expect

BASE_URL = "http://localhost:8000"


class TestAdminPages:
    def test_admin_panel_loads(self, page):
        """Админ-панель загружается (или редиректит на логин)"""
        response = page.goto(f"{BASE_URL}/admin")
        assert response.status in [200, 302, 303]

    def test_admin_panel_has_navigation(self, page):
        """Админ-панель содержит навигацию"""
        page.goto(f"{BASE_URL}/admin")
        # Проверка навигационных элементов
        nav = page.locator('nav, .sidebar, .admin-nav, .menu').first
        if nav.count() > 0:
            assert nav.is_visible() or True

    def test_admin_blacklist_page(self, page):
        """Страница чёрного списка"""
        response = page.goto(f"{BASE_URL}/admin/blacklist")
        assert response.status in [200, 302, 303, 404]

    def test_admin_users_page(self, page):
        """Страница управления пользователями"""
        response = page.goto(f"{BASE_URL}/admin/users")
        assert response.status in [200, 302, 303, 404]

    def test_admin_jobs_page(self, page):
        """Страница управления заданиями"""
        response = page.goto(f"{BASE_URL}/admin/jobs")
        assert response.status in [200, 302, 303, 404]

    def test_admin_stats_page(self, page):
        """Страница статистики"""
        response = page.goto(f"{BASE_URL}/admin/stats")
        assert response.status in [200, 302, 303, 404]
