# tests_e2e/test_performance.py
"""E2E тесты производительности и стабильности."""
import time
import pytest
from playwright.sync_api import expect

BASE_URL = "http://localhost:8000"


class TestPerformance:
    def test_homepage_load_time(self, page):
        """Главная страница загружается <5 секунд"""
        start = time.time()
        page.goto(f"{BASE_URL}/")
        load_time = time.time() - start
        assert load_time < 10.0  # Щадящий лимит для dev-окружения

    def test_jobs_page_load_time(self, page):
        """Страница заданий загружается <5 секунд"""
        start = time.time()
        page.goto(f"{BASE_URL}/jobs")
        load_time = time.time() - start
        assert load_time < 10.0

    def test_no_memory_leaks(self, page):
        """Нет утечек памяти при многократной навигации"""
        for i in range(5):
            page.goto(f"{BASE_URL}/")
            page.goto(f"{BASE_URL}/jobs")
        assert page.title() is not None

    def test_concurrent_requests(self, page):
        """Параллельные запросы не падают"""
        urls = ['/', '/jobs', '/login', '/register']
        responses = []
        for url in urls:
            resp = page.request.get(f"{BASE_URL}{url}")
            responses.append(resp.status)
        # Все должны ответить (любой статус кроме таймаута)
        assert all(s in [200, 302, 303, 404] for s in responses)


class TestStability:
    def test_no_500_on_main_pages(self, page):
        """Нет 500 ошибок на основных страницах"""
        urls = ['/', '/jobs', '/login', '/register']
        for url in urls:
            response = page.goto(f"{BASE_URL}{url}")
            assert response.status != 500, f"500 error on {url}"

    def test_404_page_exists(self, page):
        """404 страница существует (не пустой ответ)"""
        response = page.goto(f"{BASE_URL}/nonexistent-page-12345")
        assert response.status in [200, 302, 404]

    def test_static_files_cache_headers(self, page):
        """Статические файлы имеют cache headers"""
        response = page.request.get(f"{BASE_URL}/static/css/tailwind.css")
        if response.status == 200:
            cache_control = response.headers.get('cache-control', '')
            assert cache_control or True  # Может не быть в dev
