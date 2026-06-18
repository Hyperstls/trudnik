"""
P0-тесты Чата проекта «Трудник».
Тестируют доступность чата, отправку сообщений, polling и ограничения.

Запуск: python -m pytest test_chat.py -v --tb=short
"""

import re
import time

import pytest
import requests

from tests.conftest import (
    login_as, extract_csrf_token, csrf_headers, get_csrf_from_page, form_with_csrf,
    BASE_URL, EMPLOYER_EMAIL, EMPLOYER_PASSWORD, WORKER_EMAIL, WORKER_PASSWORD,
)


def _get_application_id_for_job(employer_sess, job_id) -> str | None:
    """Получить ID отклика на задание (от работодателя через my-applications)."""
    resp = employer_sess.get(f"{BASE_URL}/my-applications", timeout=30)
    if resp.status_code != 200:
        return None

    # Ищем application_id в HTML (ссылки вида /chat/<id> или data-app-id)
    # В HTML могут быть ссылки на чат
    chat_links = re.findall(r'/chat/([a-f0-9\-]+)', resp.text)
    if chat_links:
        return chat_links[0]

    # Альтернативно: ищем data-атрибуты
    app_ids = re.findall(r'data-app-id="([^"]+)"', resp.text)
    if app_ids:
        return app_ids[0]

    # Попробуем найти в JSON-блоках
    app_ids_json = re.findall(r'"application_id"\s*:\s*"([^"]+)"', resp.text)
    if app_ids_json:
        return app_ids_json[0]

    return None


# ──────────────────────────────────────────────
# Тесты Чата
# ──────────────────────────────────────────────

class TestChatBasic:
    """P0: Базовые тесты чата (не требуют accepted-отклика)."""

    def test_chat_list_endpoint(self, employer_session):
        """GET /chats → 200, список чатов пользователя."""
        resp = employer_session.get(f"{BASE_URL}/chats", timeout=30)
        assert resp.status_code == 200, (
            f"Chats list should return 200, got {resp.status_code}"
        )

    def test_chat_list_endpoint_worker(self, worker_session):
        """GET /chats → 200 для трудника."""
        resp = worker_session.get(f"{BASE_URL}/chats", timeout=30)
        assert resp.status_code == 200, (
            f"Chats list should return 200 for worker, got {resp.status_code}"
        )

    def test_chat_not_available_for_nonexistent_application(self, employer_session):
        """GET /chat/nonexistent-id → редирект на список чатов."""
        resp = employer_session.get(
            f"{BASE_URL}/chat/00000000-0000-0000-0000-000000000000",
            timeout=30,
            allow_redirects=True,
        )
        assert resp.status_code == 200
        # Должен быть редирект на /chats с сообщением об ошибке
        assert "Чат не найден" in resp.text or "chats" in resp.url.lower(), (
            f"Expected redirect to chats list, got URL: {resp.url}"
        )

    def test_chat_uses_application_id_not_shift_id(self):
        """Проверить что в коде chat.py все эндпоинты используют application_id, а не shift_id."""
        with open("app/blueprints/chat.py", "r", encoding="utf-8") as f:
            code = f.read()

        # Не должно быть упоминаний shift_id в параметрах маршрутов или запросов
        assert "shift_id" not in code, (
            "Код chat.py содержит shift_id — должен использовать только application_id"
        )
        # Должны быть упоминания application_id
        assert "application_id" in code, (
            "Код chat.py не содержит application_id"
        )


class TestChatFullChain:
    """P0: Тесты чата, требующие полной цепочки: задание → отклик → accept → чат.
    Использует accepted_application_id из conftest.py."""

    def test_chat_available_after_accept(self, accepted_application_id):
        """После accept отклика, GET /chat/<application_id> → 200."""
        app_id, job_id = accepted_application_id
        if not app_id:
            pytest.skip(
                "Не удалось создать полную цепочку (задание → publish → apply → accept). "
                "Проверьте тестовые учётные данные и доступность Supabase."
            )

        # Используем новую сессию работодателя, чтобы видеть актуальный CSRF
        e_sess = requests.Session()
        login_as(e_sess, EMPLOYER_EMAIL, EMPLOYER_PASSWORD)

        resp = e_sess.get(f"{BASE_URL}/chat/{app_id}", timeout=30, allow_redirects=False)
        assert resp.status_code == 200, (
            f"Chat page should return 200 after accept, got {resp.status_code}. "
            f"Body: {resp.text[:300]}"
        )

    def test_chat_available_for_worker_after_accept(self, accepted_application_id):
        """Трудник также может открыть чат после accept."""
        app_id, job_id = accepted_application_id
        if not app_id:
            pytest.skip(
                "Не удалось создать полную цепочку (задание → publish → apply → accept)."
            )

        w_sess = requests.Session()
        login_as(w_sess, WORKER_EMAIL, WORKER_PASSWORD)

        resp = w_sess.get(f"{BASE_URL}/chat/{app_id}", timeout=30, allow_redirects=False)
        assert resp.status_code == 200, (
            f"Chat page should return 200 for worker, got {resp.status_code}"
        )

    def test_send_message_via_api(self, accepted_application_id):
        """POST /api/send_message с application_id и message → 200, сообщение сохраняется."""
        app_id, job_id = accepted_application_id
        if not app_id:
            pytest.skip(
                "Не удалось создать полную цепочку (задание → publish → apply → accept)."
            )

        e_sess = requests.Session()
        login_as(e_sess, EMPLOYER_EMAIL, EMPLOYER_PASSWORD)

        test_message = f"Тестовое сообщение чата {int(time.time())}"
        resp = e_sess.post(
            f"{BASE_URL}/api/send_message",
            headers=csrf_headers(e_sess),
            json={
                "application_id": app_id,
                "content": test_message,
            },
            timeout=30,
        )
        assert resp.status_code == 200, (
            f"Send message failed: {resp.status_code}, body: {resp.text[:300]}"
        )
        data = resp.json()
        assert data.get("status") == "ok", (
            f"Expected status=ok, got: {data}"
        )

    def test_chat_messages_polling(self, accepted_application_id):
        """GET /api/messages/<application_id>/poll?since_id=0 → возвращает список сообщений."""
        app_id, job_id = accepted_application_id
        if not app_id:
            pytest.skip(
                "Не удалось создать полную цепочку (задание → publish → apply → accept)."
            )

        w_sess = requests.Session()
        login_as(w_sess, WORKER_EMAIL, WORKER_PASSWORD)

        resp = w_sess.get(
            f"{BASE_URL}/api/messages/{app_id}/poll?since_id=0",
            timeout=30,
        )
        assert resp.status_code == 200, (
            f"Polling failed: {resp.status_code}, body: {resp.text[:300]}"
        )
        data = resp.json()
        assert "messages" in data, f"Expected 'messages' key, got: {list(data.keys())}"
        assert isinstance(data["messages"], list), (
            f"Messages should be a list, got: {type(data['messages'])}"
        )
        assert "user_id" in data, f"Expected 'user_id' key, got: {list(data.keys())}"

    def test_chat_not_available_for_pending_application(
        self, employer_session, worker_session
    ):
        """GET /chat/<pending_application_id> → редирект или 403, чат недоступен."""
        e_sess = employer_session
        w_sess = worker_session

        # 1. Создать задание
        form = form_with_csrf(
            e_sess,
            title="Задание для pending-чата",
            description="Тест недоступности чата при pending",
            work_type="Доставка",
            payment="400",
            address="Москва, ул. Pending, 1",
            city="Москва",
            latitude="55.75",
            longitude="37.61",
            max_workers="1",
        )
        create_resp = e_sess.post(
            f"{BASE_URL}/job/new", data=form, timeout=30, allow_redirects=False
        )
        if create_resp.status_code not in (301, 302):
            pytest.skip("Не удалось создать задание для pending-теста")

        location = create_resp.headers.get("Location", "")
        parts = location.strip("/").split("/")
        job_id = parts[1] if len(parts) >= 2 else None
        if not job_id:
            pytest.skip("Не удалось извлечь job_id")

        # 2. Задания создаются с is_paid=True по умолчанию — публикация не требуется

        # 3. Трудник откликается (pending статус)
        w_sess.post(
            f"{BASE_URL}/apply/{job_id}",
            data=form_with_csrf(w_sess),
            timeout=30,
            allow_redirects=True,
        )

        # 4. Получить ID отклика
        my_apps = e_sess.get(f"{BASE_URL}/my-applications", timeout=30)
        app_ids = re.findall(r'/api/applications/([a-f0-9\-]+)/accept', my_apps.text)
        if not app_ids:
            app_ids = re.findall(r'data-app-id="([^"]+)"', my_apps.text)
        if not app_ids:
            pytest.skip("Не удалось получить application_id для pending-отклика")

        app_id = app_ids[0]

        # 5. Пытаемся открыть чат (отклик ещё pending, не accepted)
        # Пробуем от имени работодателя
        e_resp = e_sess.get(
            f"{BASE_URL}/chat/{app_id}",
            timeout=30,
            allow_redirects=True,
        )
        # Чат должен быть недоступен: либо редирект, либо сообщение об ошибке
        assert (
            "Чат не найден" in e_resp.text
            or "Нет доступа" in e_resp.text
            or "chats" in e_resp.url.lower()
        ), (
            f"Chat should not be available for pending application, "
            f"got status={e_resp.status_code}, body: {e_resp.text[:300]}"
        )
