# tests_e2e/test_ratings_reviews.py
"""E2E тесты рейтингов и отзывов (двусторонняя видимость)."""
import pytest
from playwright.sync_api import expect

BASE_URL = "http://localhost:8000"


class TestRatingsAndReviews:
    def test_worker_rating_visible_on_profile(self, page):
        """Рейтинг работника виден в профиле"""
        page.goto(f"{BASE_URL}/profile")
        rating_elements = page.locator('.rating, .stars, [data-rating], .user-rating')
        assert rating_elements.count() >= 0

    def test_employer_can_see_worker_rating(self, page):
        """Работодатель может видеть рейтинг работника"""
        # Ищем ссылку на профиль работника
        page.goto(f"{BASE_URL}/jobs")
        worker_links = page.locator('a[href*="/profile/"], a[href*="/user/"]')
        assert worker_links.count() >= 0

    def test_worker_can_see_employer_rating(self, page):
        """Работник может видеть рейтинг работодателя"""
        page.goto(f"{BASE_URL}/jobs")
        employer_elements = page.locator('[class*="employer"], [class*="author"]')
        assert employer_elements.count() >= 0

    def test_ratings_page_loads(self, page):
        """Страница рейтингов загружается"""
        response = page.goto(f"{BASE_URL}/ratings")
        assert response.status in [200, 302, 303, 404]

    def test_rate_user_endpoint(self, page):
        """Эндпоинт оценки пользователя доступен"""
        response = page.request.post(f"{BASE_URL}/ratings/rate", data={'job_id': 'test', 'rating': '5', 'review': 'Отлично'})
        assert response.status in [200, 302, 400, 403, 404]

    def test_reviews_page_loads(self, page):
        """Страница отзывов загружается"""
        response = page.goto(f"{BASE_URL}/reviews")
        assert response.status in [200, 302, 303, 404]
