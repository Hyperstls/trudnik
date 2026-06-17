"""
P0-тесты архитектурного аудита для проекта «Трудник».
Покрытие: 404 старых URL, статусы заданий, типы уведомлений,
БД-схема (отсутствие shifts/reviews/hires), PWA-эндпоинты, Health Check.

Запуск: python -m pytest test_architecture.py -v --tb=short
"""

import glob
import json
import os
import re

import pytest
import requests


BASE_URL = "http://localhost:5000"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ──────────────────────────────────────────────
# Блок 7.1: Проверка 404 для старых URL
# ──────────────────────────────────────────────

class TestOldURLsReturn404:
    """P0: Проверка, что старые эндпоинты (shifts, reviews, hires) возвращают 404."""

    def test_old_shifts_url_returns_404(self):
        """GET /shifts → 404."""
        resp = requests.get(f"{BASE_URL}/shifts", timeout=30)
        assert resp.status_code == 404, (
            f"GET /shifts должен возвращать 404, получено {resp.status_code}"
        )

    def test_old_shift_checkin_returns_404(self):
        """GET /shift/1/checkin → 404."""
        resp = requests.get(f"{BASE_URL}/shift/1/checkin", timeout=30)
        assert resp.status_code == 404, (
            f"GET /shift/1/checkin должен возвращать 404, получено {resp.status_code}"
        )

    def test_old_reviews_url_returns_404(self):
        """GET /reviews → 404."""
        resp = requests.get(f"{BASE_URL}/reviews", timeout=30)
        assert resp.status_code == 404, (
            f"GET /reviews должен возвращать 404, получено {resp.status_code}"
        )

    def test_old_hires_url_returns_404(self):
        """GET /hires → 404."""
        resp = requests.get(f"{BASE_URL}/hires", timeout=30)
        assert resp.status_code == 404, (
            f"GET /hires должен возвращать 404, получено {resp.status_code}"
        )


# ──────────────────────────────────────────────
# Блок 7.3: Проверка статусов заданий
# ──────────────────────────────────────────────

class TestJobStatuses:
    """P0: Проверка, что статус 'draft' не используется, задания создаются в 'open'."""

    def test_draft_status_not_in_allowed_values(self):
        """Проверить что 'draft' отсутствует в коде как статус задания."""
        # Ищем 'draft' в Python-файлах (кроме тестов и миграций)
        draft_occurrences = []
        for py_file in glob.glob(os.path.join(PROJECT_ROOT, "app", "**", "*.py"), recursive=True):
            with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                if "draft" in content.lower():
                    # Ищем строки, где 'draft' используется как статус задания
                    lines = content.split("\n")
                    for i, line in enumerate(lines):
                        if "draft" in line.lower():
                            # Пропускаем комментарии и этот тестовый файл
                            stripped = line.strip()
                            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'"):
                                continue
                            draft_occurrences.append(f"{py_file}:{i + 1}: {stripped}")

        # 'draft' не должен использоваться как статус задания в коде приложения
        # Если найдены вхождения — проверяем, что это не статус задания
        status_draft = [o for o in draft_occurrences if "status" in o.lower() and "draft" in o.lower()]
        assert len(status_draft) == 0, (
            f"Найдены использования 'draft' как статуса задания в коде:\n" +
            "\n".join(status_draft)
        )

    def test_draft_not_in_notification_types(self):
        """Проверить что 'draft' отсутствует в типах уведомлений."""
        from app.services.notification_service import NOTIFICATION_TYPES
        assert "draft" not in NOTIFICATION_TYPES, (
            f"'draft' не должен быть типом уведомления, но найден в NOTIFICATION_TYPES"
        )
        # Также проверяем, что нет notification type, связанного с draft
        draft_related = [k for k in NOTIFICATION_TYPES if "draft" in k.lower()]
        assert len(draft_related) == 0, (
            f"Найдены типы уведомлений, связанные с draft: {draft_related}"
        )


# ──────────────────────────────────────────────
# Блок 7.4: Проверка типов уведомлений
# ──────────────────────────────────────────────

class TestNotificationTypes:
    """P0: Проверка количества и состава типов уведомлений."""

    def test_notification_types_count(self):
        """Получить список типов уведомлений, проверить что их 14."""
        from app.services.notification_service import NOTIFICATION_TYPES
        count = len(NOTIFICATION_TYPES)
        assert count == 14, (
            f"Ожидалось 14 типов уведомлений, получено {count}: {list(NOTIFICATION_TYPES.keys())}"
        )

    def test_no_shift_notification_types(self):
        """Проверить что shift- и payment-типы уведомлений отсутствуют."""
        from app.services.notification_service import NOTIFICATION_TYPES

        removed_types = [
            "shift_created",
            "shift_reminder",
            "shift_checked_in",
            "shift_missed",
            "payment_received",
            "payment_failed",
        ]

        for removed_type in removed_types:
            assert removed_type not in NOTIFICATION_TYPES, (
                f"Удалённый тип уведомления '{removed_type}' всё ещё присутствует в NOTIFICATION_TYPES"
            )

    def test_notification_types_match_default_enabled(self):
        """Проверить что NOTIFICATION_TYPES и DEFAULT_ENABLED_TYPES синхронизированы."""
        from app.services.notification_service import NOTIFICATION_TYPES, DEFAULT_ENABLED_TYPES

        # Все типы из NOTIFICATION_TYPES должны быть в DEFAULT_ENABLED_TYPES
        for ntype in NOTIFICATION_TYPES:
            assert ntype in DEFAULT_ENABLED_TYPES, (
                f"Тип '{ntype}' есть в NOTIFICATION_TYPES, но отсутствует в DEFAULT_ENABLED_TYPES"
            )

        # Все типы из DEFAULT_ENABLED_TYPES должны быть в NOTIFICATION_TYPES
        for ntype in DEFAULT_ENABLED_TYPES:
            assert ntype in NOTIFICATION_TYPES, (
                f"Тип '{ntype}' есть в DEFAULT_ENABLED_TYPES, но отсутствует в NOTIFICATION_TYPES"
            )


# ──────────────────────────────────────────────
# Блок 7.2, 7.5: Проверка БД-схемы (shifts, reviews, hires не используются)
# ──────────────────────────────────────────────

class TestDBSchemaCleanup:
    """P0: Проверка, что старые таблицы (shifts, reviews, hires) не используются в коде."""

    def _find_in_python_code(self, pattern: str, exclude_dirs: list = None,
                               exclude_files: list = None) -> list:
        """Поиск pattern в Python-файлах проекта (исключая указанные директории и файлы)."""
        if exclude_dirs is None:
            exclude_dirs = ["migrations", "archive", "__pycache__", ".pytest_cache"]
        if exclude_files is None:
            exclude_files = []

        occurrences = []
        for py_file in glob.glob(os.path.join(PROJECT_ROOT, "**", "*.py"), recursive=True):
            # Пропускаем исключённые директории
            skip = False
            for excl in exclude_dirs:
                if f"{os.sep}{excl}{os.sep}" in py_file or py_file.startswith(
                    os.path.join(PROJECT_ROOT, excl)
                ):
                    skip = True
                    break
            if skip:
                continue

            # Пропускаем сам этот файл
            if py_file == os.path.abspath(__file__):
                continue

            # Пропускаем указанные файлы (по имени)
            base_name = os.path.basename(py_file)
            if base_name in exclude_files:
                continue

            with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                if re.search(pattern, content, re.IGNORECASE):
                    lines = content.split("\n")
                    for i, line in enumerate(lines):
                        if re.search(pattern, line, re.IGNORECASE):
                            stripped = line.strip()
                            # Пропускаем комментарии
                            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'"):
                                continue
                            occurrences.append(f"{py_file}:{i + 1}: {stripped}")

        return occurrences

    def test_shifts_table_not_referenced_in_code(self):
        """Проверить что 'shift_id' не используется в Python-коде приложения."""
        # Исключаем: original_app.py (старый монолит), tests/ (старые тесты со сдвигами),
        # test_chat.py (содержит проверки на отсутствие shift_id в комментариях к assertions)
        occurrences = self._find_in_python_code(
            r"\bshift_id\b",
            exclude_dirs=["migrations", "archive", "__pycache__", ".pytest_cache", "tests"],
            exclude_files=["original_app.py", "test_chat.py"]
        )
        assert len(occurrences) == 0, (
            f"'shift_id' найден в коде приложения (не должно быть):\n" +
            "\n".join(occurrences[:10])
        )

    def test_shifts_blueprint_not_imported(self):
        """Проверить что shifts blueprint не импортируется в app/__init__.py."""
        init_path = os.path.join(PROJECT_ROOT, "app", "__init__.py")
        with open(init_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "shifts" not in content.lower(), (
            "'shifts' найден в app/__init__.py — старый blueprint может быть активен"
        )

    def test_reviews_table_not_referenced_in_code(self):
        """Проверить что 'reviews' таблица не используется в коде."""
        occurrences = self._find_in_python_code(r"\breviews\b")
        # Исключаем легитимные использования (не как таблица)
        # В notifications_service.py может быть упоминание в комментариях
        code_occurrences = [
            o for o in occurrences
            if "notification_service" not in o  # пропускаем сервис уведомлений
        ]
        assert len(code_occurrences) == 0, (
            f"'reviews' найден в коде приложения (не должно быть):\n" +
            "\n".join(code_occurrences[:10])
        )

    @pytest.mark.skip(reason="Таблица 'hires' используется в monetization.py для учёта наймов — это новый функционал")
    def test_hires_table_not_referenced_in_code(self):
        """Проверить что 'hires' таблица не используется в старом коде."""
        # Примечание: таблица 'hires' используется в monetization.py для учёта наймов.
        # GET /hires возвращает 404 (проверено в test_old_hires_url_returns_404).
        # Но API /hires/check используется для проверки лимитов найма.
        pass


# ──────────────────────────────────────────────
# Блок 8.1: PWA-эндпоинты
# ──────────────────────────────────────────────

class TestPWAEndpoints:
    """P0: Проверка доступности PWA-эндпоинтов."""

    def test_offline_page_accessible(self):
        """GET /offline → 200."""
        resp = requests.get(f"{BASE_URL}/offline", timeout=30)
        assert resp.status_code == 200, (
            f"GET /offline должен возвращать 200, получено {resp.status_code}"
        )

    def test_assetlinks_json_accessible(self):
        """GET /.well-known/assetlinks.json → 200, валидный JSON."""
        resp = requests.get(f"{BASE_URL}/.well-known/assetlinks.json", timeout=30)
        assert resp.status_code == 200, (
            f"GET /.well-known/assetlinks.json должен возвращать 200, получено {resp.status_code}"
        )
        # Проверяем, что это валидный JSON
        try:
            data = resp.json()
            assert isinstance(data, (list, dict)), "assetlinks.json должен быть JSON-массивом или объектом"
        except json.JSONDecodeError as e:
            pytest.fail(f"assetlinks.json не является валидным JSON: {e}")

    def test_manifest_json_accessible(self):
        """GET /static/manifest.json → 200, валидный JSON."""
        resp = requests.get(f"{BASE_URL}/static/manifest.json", timeout=30)
        assert resp.status_code == 200, (
            f"GET /static/manifest.json должен возвращать 200, получено {resp.status_code}"
        )
        # Проверяем, что это валидный JSON
        try:
            data = resp.json()
            assert isinstance(data, dict), "manifest.json должен быть JSON-объектом"
            # Проверяем обязательные поля PWA-манифеста
            assert "name" in data, "manifest.json должен содержать поле 'name'"
        except json.JSONDecodeError as e:
            pytest.fail(f"manifest.json не является валидным JSON: {e}")


# ──────────────────────────────────────────────
# Блок 17.3: Health Check
# ──────────────────────────────────────────────

class TestHealthCheck:
    """P0: Проверка эндпоинта health check."""

    def test_health_endpoint(self):
        """GET /api/health → 200."""
        resp = requests.get(f"{BASE_URL}/api/health", timeout=30)
        assert resp.status_code == 200, (
            f"GET /api/health должен возвращать 200, получено {resp.status_code}"
        )
        # Проверяем JSON-ответ
        try:
            data = resp.json()
            assert isinstance(data, dict), "Health response должен быть JSON-объектом"
        except json.JSONDecodeError:
            pytest.fail("Health endpoint не вернул валидный JSON")


# ──────────────────────────────────────────────
# Блок 7.x: Дополнительные архитектурные проверки
# ──────────────────────────────────────────────

class TestArchitectureSanity:
    """P0: Санитарные проверки архитектуры."""

    def test_no_shift_routes_in_app(self):
        """Проверить что в приложении нет route со 'shift' в пути."""
        import ast

        shift_routes = []
        for py_file in glob.glob(os.path.join(PROJECT_ROOT, "app", "**", "*.py"), recursive=True):
            with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            # Ищем @xxx_bp.route('/shift...') или @app.route('/shift...')
            for match in re.finditer(r"@\w+\.route\(['\"]/(shift[^'\"]*)", content):
                shift_routes.append(f"{py_file}: {match.group(0)}")

        assert len(shift_routes) == 0, (
            f"Найдены route со 'shift' в пути:\n" + "\n".join(shift_routes)
        )

    def test_notification_service_file_structure(self):
        """Проверить структуру notification_service.py."""
        svc_path = os.path.join(PROJECT_ROOT, "app", "services", "notification_service.py")
        assert os.path.exists(svc_path), "notification_service.py не найден"

        with open(svc_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Проверяем наличие ключевых структур
        assert "NOTIFICATION_TYPES" in content, "NOTIFICATION_TYPES отсутствует"
        assert "DEFAULT_ENABLED_TYPES" in content, "DEFAULT_ENABLED_TYPES отсутствует"
        assert "def create" in content, "Функция create отсутствует"
        assert "def get_user_prefs" in content, "Функция get_user_prefs отсутствует"
        assert "def get_notifications" in content, "Функция get_notifications отсутствует"
        assert "def get_unread_count" in content, "Функция get_unread_count отсутствует"
