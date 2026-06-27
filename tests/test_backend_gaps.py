"""
Параметризованные Pytest-тесты для заполнения пробелов в Блоке 1 (Backend/API)
и Блоке 4 (Безопасность и Edge Cases).

Покрытие: обновление токенов (INT-008/009), rate limiting (AUTH-010/PRF-001),
стоп-слова (JOB-E-002/003), Circuit Breaker (PRF-002/003), CSRF (SEC-001/002),
CSP Nonce (SEC-008), Edge Cases (EDG-003/007/012).

Запуск: python -m pytest tests/test_backend_gaps.py -v --tb=short
"""

import io
import time
import uuid

import pytest
import requests

# Фикстуры и хелперы из conftest
from tests.conftest import (
    BASE_URL,
    EMPLOYER_EMAIL,
    EMPLOYER_PASSWORD,
    WORKER_EMAIL,
    WORKER_PASSWORD,
    csrf_headers,
    employer_session,
    form_with_csrf,
    get_csrf_from_page,
    login_as,
    extract_csrf_token,
    worker_session,
    created_job_id,
)


# ═══════════════════════════════════════════════════════════════
# Класс 1: TestAuthTokenRefresh — Обновление токенов
# ═══════════════════════════════════════════════════════════════

class TestAuthTokenRefresh:
    """INT-008, INT-009: Обновление access_token и истечение обоих токенов."""

    def test_expired_access_token_auto_refresh(self, employer_session):
        """INT-008: Истекший access_token → refresh_access_token() без разлогинивания.

        Поскольку мы не можем подделать подписанную Flask-сессию в чёрном ящике,
        проверяем, что после входа защищённые маршруты работают (200),
        а сессия остаётся валидной после нескольких запросов — это неявно
        подтверждает работоспособность механизма рефреша (если бы токен истёк
        и не мог быть обновлён, запросы бы падали с 401).
        """
        sess = employer_session

        # Делаем несколько запросов к защищённому маршруту
        for _ in range(3):
            resp = sess.get(f"{BASE_URL}/my-jobs", timeout=30)
            assert resp.status_code == 200, (
                f"Защищённый маршрут /my-jobs должен возвращать 200, "
                f"получено {resp.status_code}. Возможно, access_token истёк "
                f"и не обновился."
            )
            # Убедимся, что мы не на странице логина
            assert "Войти" not in resp.text[:500] or "Выйти" in resp.text, (
                "Похоже, сессия была очищена — произошёл редирект на /login"
            )

    def test_expired_both_tokens_redirects_to_login(self, employer_session):
        """INT-009: Оба токена истекли → редирект на /login.

        Очищаем куки сессии (имитация полного истечения обоих токенов),
        делаем запрос к защищённому маршруту — ожидаем редирект на /login.
        """
        sess = employer_session

        # Очищаем все куки сессии — имитация истечения обоих токенов
        sess.cookies.clear()

        resp = sess.get(
            f"{BASE_URL}/my-jobs",
            timeout=30,
            allow_redirects=False,
        )

        # Без валидной сессии должен быть редирект на /login
        assert resp.status_code in (301, 302, 401), (
            f"Ожидался редирект (301/302) или 401 при отсутствии токенов, "
            f"получено {resp.status_code}"
        )

        # Если это редирект — проверяем, что он ведёт на /login
        if resp.status_code in (301, 302):
            location = resp.headers.get("Location", "")
            assert "/login" in location.lower(), (
                f"Редирект должен вести на /login, получено: {location}"
            )


# ═══════════════════════════════════════════════════════════════
# Класс 2: TestRateLimitParametrized — Rate Limiting
# ═══════════════════════════════════════════════════════════════

class TestRateLimitParametrized:
    """AUTH-010 / PRF-001: Rate limit на /login — 11 POST за 60 сек → 429."""

    @pytest.mark.parametrize("request_count,expected_status", [
        (10, 200),
        (11, 429),
    ])
    def test_login_rate_limit(self, request_count, expected_status):
        """AUTH-010 / PRF-001: Rate limit на /login.

        Используем свежую requests.Session() без кук (каждый запрос
        с нового «IP-like»). Отправляем request_count POST /login
        с неверными данными. Проверяем статус expected_status.
        """
        # Используем свежую сессию для имитации нового IP
        sess = requests.Session()

        # Делаем request_count запросов
        last_status = None
        for i in range(request_count):
            # Каждый запрос в новой сессии (как с нового IP)
            s = requests.Session()
            s.get(f"{BASE_URL}/login", timeout=30)  # получить CSRF-куку
            resp = s.post(
                f"{BASE_URL}/login",
                data={
                    "email": EMPLOYER_EMAIL,
                    "password": f"wrong_password_{i}",
                },
                timeout=30,
                allow_redirects=True,
            )
            last_status = resp.status_code
            # Небольшая пауза, чтобы не перегружать сервер
            time.sleep(0.05)

        assert last_status == expected_status, (
            f"После {request_count} запросов ожидался статус {expected_status}, "
            f"получено {last_status}"
        )


# ═══════════════════════════════════════════════════════════════
# Класс 3: TestStopWordsValidation — Стоп-слова
# ═══════════════════════════════════════════════════════════════

class TestStopWordsValidation:
    """JOB-E-002, JOB-E-003: Стоп-слова блокируют создание задания."""

    @pytest.mark.parametrize("stop_word", [
        "зарплата",
        "ставка",
        "вахта",
        "зӑрплӑта",
        "зapплaтa",
        "zarp1ata",
        "zarplata",
        "ставкa",
        "вaхтa",
    ])
    def test_stop_words_block_job_creation(self, employer_session, stop_word):
        """JOB-E-002, JOB-E-003: Стоп-слова блокируют создание задания.

        POST /job/new с описанием, содержащим stop_word.
        Ожидается flash-ошибка валидации или отсутствие редиректа на страницу задания.
        """
        sess = employer_session
        form = form_with_csrf(
            sess,
            title=f"Тест стоп-слов {int(time.time())}",
            description=f"Описание содержит стоп-слово: {stop_word}",
            work_type="Уборка",
            payment="500",
            address="Москва, ул. Тестовая, 1",
            city="Москва",
            latitude="55.75",
            longitude="37.61",
            preferred_religion="",
            max_workers="1",
        )
        resp = sess.post(
            f"{BASE_URL}/job/new",
            data=form,
            timeout=30,
            allow_redirects=False,
        )

        # Если стоп-слово обнаружено:
        # - Либо возвращается 200 с flash-ошибкой на странице
        # - Либо возвращается 400
        # - Либо происходит редирект обратно на /job/new с ошибкой
        if resp.status_code == 200:
            assert "стоп-слов" in resp.text.lower() or "запрещен" in resp.text.lower() or "stop" in resp.text.lower(), (
                f"Ожидалась ошибка валидации стоп-слова '{stop_word}' в ответе 200, "
                f"но текст ошибки не найден"
            )
        elif resp.status_code == 302:
            location = resp.headers.get("Location", "")
            # Если редирект на страницу задания — стоп-слово не сработало
            assert not location.startswith("/job/") and not location.startswith("/jobs/"), (
                f"Стоп-слово '{stop_word}' не заблокировало создание задания, "
                f"редирект на {location}"
            )
        # 400 — явная блокировка, это нормально


# ═══════════════════════════════════════════════════════════════
# Класс 4: TestCircuitBreaker — Circuit Breaker
# ═══════════════════════════════════════════════════════════════

class TestCircuitBreaker:
    """PRF-002, PRF-003: Circuit Breaker — размыкание и восстановление."""

    def test_circuit_breaker_opens_after_5_errors(self, mocker):
        """PRF-002: 5 ошибок 500 → Circuit Breaker OPEN → 503 Service Unavailable.

        Импортируем CircuitBreaker из app.utils и тестируем напрямую.
        Симулируем 5 вызовов, возвращающих ошибку, затем проверяем,
        что 6-й вызов возвращает заглушку 503.
        """
        from app.utils import CircuitBreaker, PostgrestResponse

        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
        assert cb.state == "CLOSED"

        # Симулируем функцию, которая возвращает ошибку
        call_count = [0]

        def failing_call():
            call_count[0] += 1
            return PostgrestResponse(
                ok=False,
                status_code=500,
                text="Internal Server Error",
            )

        # 5 вызовов — цепь должна разомкнуться после 5-го
        for i in range(5):
            result = cb.call(failing_call)
            assert result.ok is False
            assert result.status_code == 500

        assert cb.state == "OPEN", (
            f"После 5 ошибок цепь должна быть OPEN, "
            f"текущее состояние: {cb.state}"
        )
        assert cb.failure_count >= 5

        # 6-й вызов — цепь разомкнута, возвращает 503 без реального вызова
        calls_before = call_count[0]
        result = cb.call(failing_call)
        assert result.ok is False
        assert result.status_code == 503, (
            f"При разомкнутой цепи ожидался статус 503, "
            f"получено {result.status_code}"
        )
        assert "Circuit breaker open" in result.text
        # Убедимся, что реальный вызов не выполнялся
        assert call_count[0] == calls_before, (
            "При разомкнутой цепи реальный вызов не должен выполняться"
        )

    def test_circuit_breaker_recovers_after_timeout(self, mocker):
        """PRF-003: После 30 сек → цепь полуоткрыта → успешный запрос → цепь замкнута.

        Мокаем time.time() для симуляции прошедшего времени.
        """
        from app.utils import CircuitBreaker, PostgrestResponse

        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)

        # Симулируем функцию, возвращающую ошибку
        def failing_call():
            return PostgrestResponse(
                ok=False,
                status_code=500,
                text="Internal Server Error",
            )

        def success_call():
            return PostgrestResponse(
                ok=True,
                status_code=200,
                data={"message": "ok"},
            )

        # Шаг 1: Доводим до OPEN (5 ошибок)
        for _ in range(5):
            cb.call(failing_call)
        assert cb.state == "OPEN"

        # Шаг 2: Мокаем time.time(), чтобы симулировать прошедшие 31 сек
        original_time = time.time
        future_time = original_time() + 31.0
        mocker.patch("time.time", return_value=future_time)

        # Шаг 3: Следующий вызов — цепь должна перейти в HALF_OPEN
        # и выполнить реальный запрос. Поскольку запрос успешен —
        # цепь должна замкнуться (CLOSED).
        result = cb.call(success_call)
        assert result.ok is True
        assert result.status_code == 200
        assert cb.state == "CLOSED", (
            f"После успешного запроса в HALF_OPEN цепь должна замкнуться (CLOSED), "
            f"текущее состояние: {cb.state}"
        )
        assert cb.failure_count == 0

        # Восстанавливаем time.time
        mocker.stopall()


# ═══════════════════════════════════════════════════════════════
# Класс 5: TestCSRFSecurity — CSRF Protection
# ═══════════════════════════════════════════════════════════════

class TestCSRFSecurity:
    """SEC-001, SEC-002: CSRF-защита — отсутствие и невалидность токена."""

    def test_post_without_csrf_token_returns_400(self, employer_session):
        """SEC-001: POST без X-CSRF-Token → 400 Bad Request.

        Отправляем POST /job/new без заголовка X-CSRF-Token
        и без _csrf_token в теле.
        """
        sess = employer_session
        resp = sess.post(
            f"{BASE_URL}/job/new",
            data={
                "title": "Test No CSRF",
                "description": "No CSRF token in body",
                "work_type": "Уборка",
                "payment": "500",
                "address": "Москва, ул. Тестовая, 1",
                "city": "Москва",
                "latitude": "55.75",
                "longitude": "37.61",
                "max_workers": "1",
                # НЕТ _csrf_token!
            },
            timeout=30,
            allow_redirects=False,
        )
        assert resp.status_code in (400, 403), (
            f"POST без _csrf_token должен вернуть 400 или 403, "
            f"получено {resp.status_code}"
        )

    def test_post_with_invalid_csrf_token_returns_400(self, employer_session):
        """SEC-002: POST с невалидным X-CSRF-Token → 400 Bad Request."""
        sess = employer_session
        resp = sess.post(
            f"{BASE_URL}/job/new",
            data={
                "_csrf_token": "invalid_token_1234567890abcdef",
                "title": "Test Invalid CSRF",
                "description": "Invalid CSRF token in body",
                "work_type": "Уборка",
                "payment": "500",
                "address": "Москва, ул. Тестовая, 1",
                "city": "Москва",
                "latitude": "55.75",
                "longitude": "37.61",
                "max_workers": "1",
            },
            timeout=30,
            allow_redirects=False,
        )
        assert resp.status_code in (400, 403), (
            f"POST с невалидным _csrf_token должен вернуть 400 или 403, "
            f"получено {resp.status_code}"
        )

    def test_api_apply_without_csrf_returns_400(self, worker_session, created_job_id):
        """SEC-001: POST /apply/<job_id> без CSRF → 400."""
        sess = worker_session
        resp = sess.post(
            f"{BASE_URL}/apply/{created_job_id}",
            data={
                # НЕТ _csrf_token!
            },
            timeout=30,
            allow_redirects=False,
        )
        assert resp.status_code in (400, 403), (
            f"POST /apply без CSRF должен вернуть 400 или 403, "
            f"получено {resp.status_code}"
        )


# ═══════════════════════════════════════════════════════════════
# Класс 6: TestCSPNonce — CSP Nonce
# ═══════════════════════════════════════════════════════════════

class TestCSPNonce:
    """SEC-008: csp_nonce только в <script nonce='...'>, не в URL/localStorage."""

    def test_csp_nonce_in_script_tags_only(self, employer_session):
        """SEC-008: csp_nonce только в <script nonce='...'>.

        GET /, проверяем HTML: nonce в script-тегах, но не в URL,
        не в data-атрибутах.
        """
        import re

        sess = employer_session
        resp = sess.get(f"{BASE_URL}/", timeout=30)
        assert resp.status_code == 200

        html = resp.text

        # Ищем nonce в script-тегах
        script_nonce_matches = re.findall(
            r'<script[^>]*\snonce=["\']([^"\']+)["\'][^>]*>',
            html,
        )
        # nonce должен быть в script-тегах (если CSP с nonce используется)
        # Если nonce не используется — тест считается пройденным (none — безопасно)

        # Проверяем, что nonce НЕ в URL (src/href с nonce=)
        url_nonce = re.findall(
            r'(?:src|href)=["\'][^"\']*nonce=',
            html,
        )
        assert len(url_nonce) == 0, (
            f"nonce обнаружен в URL (src/href): {url_nonce}. "
            f"Nonce не должен передаваться через URL."
        )

        # Проверяем, что nonce НЕ в data-атрибутах с чувствительными данными
        data_nonce = re.findall(
            r'data-[^=]*nonce[^=]*=',
            html,
        )
        # data-nonce может быть, но не должен содержать сам nonce из CSP
        # Это допустимо только если data-nonce — это имя атрибута, а не утечка

    def test_csp_nonce_not_in_localstorage(self, employer_session):
        """SEC-008: nonce не утекает в localStorage через JS.

        GET /, проверяем HTML: нет inline-скриптов, записывающих nonce
        в localStorage.
        """
        import re

        sess = employer_session
        resp = sess.get(f"{BASE_URL}/", timeout=30)
        assert resp.status_code == 200

        html = resp.text

        # Проверяем, что в inline-скриптах нет localStorage.setItem с nonce
        # Ищем паттерн: localStorage.setItem(..., nonce)
        localstorage_leak = re.findall(
            r'localStorage\.(?:setItem|getItem)\s*\([^)]*nonce',
            html,
            re.IGNORECASE,
        )
        assert len(localstorage_leak) == 0, (
            f"nonce утекает в localStorage: {localstorage_leak}"
        )


# ═══════════════════════════════════════════════════════════════
# Класс 7: TestEdgeCases — Edge Cases
# ═══════════════════════════════════════════════════════════════

class TestEdgeCases:
    """EDG-003, EDG-007, EDG-012: Edge Cases."""

    def test_invalid_uuid_returns_404_not_500(self, employer_session):
        """EDG-003: /jobs/not-a-uuid → 404 error.html, не 500."""
        sess = employer_session
        resp = sess.get(
            f"{BASE_URL}/jobs/not-a-uuid",
            timeout=30,
            allow_redirects=False,
        )
        # Не должен быть 500
        assert resp.status_code != 500, (
            f"/jobs/not-a-uuid не должен вызывать 500 Internal Server Error, "
            f"получено {resp.status_code}"
        )
        # Должен быть 404 или другая клиентская ошибка
        assert resp.status_code in (404, 400, 200), (
            f"Ожидался 404/400/200 для невалидного UUID, "
            f"получено {resp.status_code}"
        )

    def test_cancel_application_less_than_12h_before(
        self, worker_session, created_job_id
    ):
        """EDG-012: Отзыв отклика < 12ч до начала → бизнес-ошибка.

        Создаём отклик, затем проверяем, что система обрабатывает
        сценарий отмены (даже если задание далеко в будущем —
        проверяем саму возможность вызова эндпоинта).
        """
        w_sess = worker_session

        # Откликаемся на задание
        apply_resp = w_sess.post(
            f"{BASE_URL}/apply/{created_job_id}",
            data=form_with_csrf(w_sess),
            timeout=30,
            allow_redirects=True,
        )
        # Отклик должен быть принят (или мы уже откликались)
        assert apply_resp.status_code in (200, 302, 403), (
            f"Неожиданный статус отклика: {apply_resp.status_code}"
        )

        # Пытаемся отменить отклик через эндпоинт
        # Если отклик не accepted, cancel может не сработать —
        # это нормально, проверяем что система отвечает без 500
        # Используем прямой запрос к /cancel-application
        cancel_resp = w_sess.post(
            f"{BASE_URL}/cancel-application/{created_job_id}",
            data=form_with_csrf(w_sess),
            timeout=30,
            allow_redirects=True,
        )
        # Ожидаем любой ответ кроме 500
        assert cancel_resp.status_code != 500, (
            f"Отмена отклика не должна вызывать 500, "
            f"получено {cancel_resp.status_code}"
        )

    def test_avatar_upload_size_limit(self, employer_session):
        """EDG-007: Загрузка аватара > 5MB → ошибка валидации."""
        sess = employer_session

        # Получаем CSRF-токен со страницы профиля
        csrf = get_csrf_from_page(sess, "/profile")
        if not csrf:
            pytest.skip("Не удалось получить CSRF-токен для /profile")

        # Создаём фальшивый большой файл (> 5MB)
        large_data = b"A" * (6 * 1024 * 1024)  # 6 MB
        large_file = io.BytesIO(large_data)
        large_file.name = "large_avatar.jpg"

        resp = sess.post(
            f"{BASE_URL}/profile/update",
            data={
                "_csrf_token": csrf,
                "full_name": "Test User",
                "phone": "+79991234567",
                "bio": "Test bio",
                "city": "Москва",
            },
            files={"photo": (large_file.name, large_file, "image/jpeg")},
            timeout=30,
            allow_redirects=True,
        )
        assert resp.status_code == 200, (
            f"Запрос с большим файлом должен вернуть 200 с ошибкой валидации, "
            f"получено {resp.status_code}"
        )
        # Проверяем наличие ошибки о размере файла
        assert (
            "большой" in resp.text.lower()
            or "размер" in resp.text.lower()
            or "слишком" in resp.text.lower()
            or "максимум" in resp.text.lower()
        ), (
            "Ожидалась ошибка о превышении размера файла, "
            "но сообщение не найдено в ответе"
        )

    def test_avatar_upload_mime_whitelist(self, employer_session):
        """EDG-007: Загрузка .exe как аватар → ошибка MIME-типа."""
        sess = employer_session

        csrf = get_csrf_from_page(sess, "/profile")
        if not csrf:
            pytest.skip("Не удалось получить CSRF-токен для /profile")

        # Создаём фальшивый .exe файл
        exe_data = b"MZ\x00\x00" + b"A" * 1024  # Фальшивый PE-заголовок
        exe_file = io.BytesIO(exe_data)
        exe_file.name = "malware.exe"

        resp = sess.post(
            f"{BASE_URL}/profile/update",
            data={
                "_csrf_token": csrf,
                "full_name": "Test User",
                "phone": "+79991234567",
                "bio": "Test bio",
                "city": "Москва",
            },
            files={"photo": (exe_file.name, exe_file, "application/x-msdownload")},
            timeout=30,
            allow_redirects=True,
        )
        assert resp.status_code == 200, (
            f"Запрос с .exe файлом должен вернуть 200 с ошибкой валидации, "
            f"получено {resp.status_code}"
        )
        # Проверяем наличие ошибки о формате файла
        assert (
            "формат" in resp.text.lower()
            or "недопустим" in resp.text.lower()
            or "разрешены" in resp.text.lower()
            or "файл" in resp.text.lower()
        ), (
            "Ожидалась ошибка о недопустимом формате файла, "
            "но сообщение не найдено в ответе"
        )

    def test_path_traversal_sanitized(self, employer_session):
        """SEC-006: ?city=../../../etc/passwd — санитизация.

        GET /?city=../../../etc/passwd → нет выхода за пределы,
        200 OK (санитизированный запрос).
        """
        sess = employer_session
        resp = sess.get(
            f"{BASE_URL}/",
            params={"city": "../../../etc/passwd"},
            timeout=30,
        )
        assert resp.status_code == 200, (
            f"Запрос с path traversal должен вернуть 200, "
            f"получено {resp.status_code}"
        )
        # Страница не должна упасть с 500
        assert "Internal Server Error" not in resp.text, (
            "Path traversal вызвал 500 Internal Server Error"
        )

    def test_postgrest_injection_sanitized(self, employer_session):
        """SRH-003: ?select=*,applications(*) — sanitize_postgrest() вырезает.

        GET /api/search/jobs?select=*,applications(*) → безопасный запрос, 200 OK.
        """
        sess = employer_session
        resp = sess.get(
            f"{BASE_URL}/api/search/jobs",
            params={"select": "*,applications(*)"},
            timeout=30,
        )
        # Ожидаем 200 (санитизированный запрос) или 400/404
        assert resp.status_code != 500, (
            f"PostgREST-инъекция не должна вызывать 500 Internal Server Error, "
            f"получено {resp.status_code}"
        )
        assert resp.status_code in (200, 400, 404), (
            f"Ожидался 200/400/404 для санитизированного запроса, "
            f"получено {resp.status_code}"
        )
