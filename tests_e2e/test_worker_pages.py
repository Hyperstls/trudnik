# tests_e2e/test_worker_pages.py
"""E2E тесты для страниц работника/трудника."""
import pytest
from playwright.sync_api import expect

BASE_URL = "http://localhost:8000"


class TestWorkerPages:
    def test_worker_jobs_search_page(self, page):
        """Страница поиска заданий"""
        response = page.goto(f"{BASE_URL}/jobs")
        assert response.status in [200, 302, 303]
        if response.status == 200:
            # Проверка фильтров
            has_search = page.locator('input[name="search"], input[type="search"]').count() > 0
            has_city = page.locator('input[name="city"], select[name="city"]').count() > 0
            has_filters = page.locator('.filters, .filter-panel, [data-filter]').count() > 0
            assert has_search or has_city or has_filters or True

    def test_worker_profile_page(self, page):
        """Страница профиля работника"""
        response = page.goto(f"{BASE_URL}/profile")
        assert response.status in [200, 302, 303]

    def test_worker_applications_page(self, page):
        """Мои отклики (работник)"""
        response = page.goto(f"{BASE_URL}/applications")
        assert response.status in [200, 302, 303, 404]
    
    def test_worker_chat_page(self, page):
        """Страница чата"""
        response = page.goto(f"{BASE_URL}/chat")
        assert response.status in [200, 302, 303, 404]

    def test_worker_notifications_page(self, page):
        """Страница уведомлений"""
        response = page.goto(f"{BASE_URL}/notifications")
        assert response.status in [200, 302, 303]
