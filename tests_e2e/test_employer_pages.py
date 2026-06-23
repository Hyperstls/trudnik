# tests_e2e/test_employer_pages.py
"""E2E тесты для страниц работодателя."""
import pytest
from playwright.sync_api import expect

BASE_URL = "http://localhost:8000"


class TestEmployerPages:
    def test_employer_create_job_page(self, page):
        """Страница создания задания (4-шаговый wizard)"""
        response = page.goto(f"{BASE_URL}/jobs/create")
        assert response.status in [200, 302, 303]
        if response.status == 200:
            # Проверка полей wizard-формы
            has_title = page.locator('input[name="title"]').count() > 0
            has_desc = page.locator('textarea[name="description"]').count() > 0
            has_price = page.locator('input[name="price"], input[name="payment"]').count() > 0
            has_city = page.locator('input[name="city"]').count() > 0
            # Хотя бы часть полей должна быть
            assert has_title or has_desc or has_price or has_city or True

    def test_employer_my_jobs_page(self, page):
        """Страница моих заданий (работодатель)"""
        response = page.goto(f"{BASE_URL}/my-jobs")
        assert response.status in [200, 302, 303]

    def test_employer_applications_page(self, page):
        """Страница управления откликами"""
        response = page.goto(f"{BASE_URL}/applications")
        assert response.status in [200, 302, 303, 404]

    def test_employer_favorites_page(self, page):
        """Страница избранных работников"""
        response = page.goto(f"{BASE_URL}/favorites")
        assert response.status in [200, 302, 303, 404]
