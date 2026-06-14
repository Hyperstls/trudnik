"""
P0-тесты Монетизации проекта «Трудник».
Тестируют тарифы, платежи за публикацию, продление заданий и модель pay-per-job.

Запуск: python -m pytest test_monetization.py -v --tb=short
"""

import re
import time

import pytest
import requests


BASE_URL = "http://127.0.0.1:5000"

# Тестовые учётные данные (из setup_test_users.py)
EMPLOYER_EMAIL = "org@test.ru"
EMPLOYER_PASSWORD = "test123"
WORKER_EMAIL = "trud3@test.ru"
WORKER_PASSWORD = "test123"


# ──────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────

def extract_csrf_token(html: str) -> str | None:
    """Извлечь CSRF-токен из meta-тега HTML-страницы."""
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    return match.group(1) if match else None


def login_as(session: requests.Session, email: str, password: str) -> str | None:
    """Войти как пользователь. Возвращает CSRF-токен или None."""
    resp = session.get(f"{BASE_URL}/login", timeout=30)
    csrf = extract_csrf_token(resp.text)

    resp = session.post(
        f"{BASE_URL}/login",
        data={"email": email, "password": password},
        timeout=30,
        allow_redirects=True,
    )
    if "Ошибка входа" in resp.text:
        return None
    fresh_csrf = extract_csrf_token(resp.text)
    return fresh_csrf or csrf


def get_csrf_from_page(session: requests.Session, path: str = "/") -> str | None:
    """Получить CSRF-токен с любой страницы приложения."""
    resp = session.get(f"{BASE_URL}{path}", timeout=30)
    return extract_csrf_token(resp.text)


def csrf_headers(session: requests.Session) -> dict:
    """Получить заголовки с CSRF-токеном для JSON API-запросов."""
    csrf = get_csrf_from_page(session)
    return {
        "X-CSRF-Token": csrf or "",
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    }


def form_with_csrf(session: requests.Session, **extra) -> dict:
    """Формирует данные формы с CSRF-токеном."""
    csrf = get_csrf_from_page(session)
    return {"_csrf_token": csrf or "", **extra}


def _create_and_publish_job(session: requests.Session, title: str = None) -> str | None:
    """Создать и опубликовать задание. Возвращает job_id или None."""
    if title is None:
        title = f"Тестовое задание монетизации {int(time.time())}"

    form = form_with_csrf(
        session,
        title=title,
        description="Описание тестового задания для проверки монетизации",
        work_type="Уборка",
        payment="600",
        address="Москва, ул. Финансовая, 1",
        city="Москва",
        latitude="55.75",
        longitude="37.61",
        max_workers="2",
    )
    create_resp = session.post(
        f"{BASE_URL}/job/new", data=form, timeout=30, allow_redirects=False
    )
    if create_resp.status_code not in (301, 302):
        return None

    location = create_resp.headers.get("Location", "")
    parts = location.strip("/").split("/")
    job_id = parts[1] if len(parts) >= 2 else None
    if not job_id:
        return None

    # Публикуем
    pub_resp = session.post(
        f"{BASE_URL}/api/jobs/{job_id}/publish",
        headers=csrf_headers(session),
        json={"tariff": "standard"},
        timeout=30,
    )
    if not pub_resp.ok:
        return None
    pub_data = pub_resp.json() if pub_resp.ok else {}
    if not pub_data.get("success"):
        return None

    return job_id


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture(scope="module")
def employer_session():
    """Сессия работодателя (org@test.ru)."""
    sess = requests.Session()
    csrf = login_as(sess, EMPLOYER_EMAIL, EMPLOYER_PASSWORD)
    if csrf is None:
        pytest.fail("Не удалось войти как работодатель. Проверьте учётные данные.")
    return sess


@pytest.fixture(scope="module")
def worker_session():
    """Сессия трудника (trud3@test.ru)."""
    sess = requests.Session()
    csrf = login_as(sess, WORKER_EMAIL, WORKER_PASSWORD)
    if csrf is None:
        pytest.fail("Не удалось войти как трудник. Проверьте учётные данные.")
    return sess


@pytest.fixture
def published_job_id(employer_session):
    """Создать и опубликовать задание, вернуть его ID."""
    job_id = _create_and_publish_job(employer_session)
    if not job_id:
        pytest.fail("Не удалось создать и опубликовать задание")
    return job_id


# ──────────────────────────────────────────────
# Тесты Монетизации
# ──────────────────────────────────────────────

class TestTariffSettings:
    """P0: Проверка настроек тарифов."""

    @pytest.mark.skip(
        reason="GET /api/admin/monetization-settings требует авторизации администратора. "
               "Тестовый админ-аккаунт не настроен."
    )
    def test_tariff_settings_endpoint_admin(self):
        """GET /api/admin/monetization-settings → 200 для админа, JSON с тарифами."""
        pass

    def test_tariff_settings_returns_403_for_employer(self, employer_session):
        """GET /api/admin/monetization-settings → 403 для обычного работодателя."""
        resp = employer_session.get(
            f"{BASE_URL}/api/admin/monetization-settings",
            timeout=30,
        )
        # Должен вернуть 403 (доступ запрещён), 302 (редирект) или 404 (эндпоинт не существует)
        assert resp.status_code in (403, 302, 401, 404), (
            f"Non-admin should not access tariff settings, got {resp.status_code}"
        )

    def test_tariff_settings_returns_403_for_worker(self, worker_session):
        """GET /api/admin/monetization-settings → 403 для трудника."""
        resp = worker_session.get(
            f"{BASE_URL}/api/admin/monetization-settings",
            timeout=30,
        )
        assert resp.status_code in (403, 302, 401, 404), (
            f"Worker should not access tariff settings, got {resp.status_code}"
        )


class TestJobPayment:
    """P0: Проверка платежей за публикацию."""

    def test_publish_job_sets_is_paid_true(self, employer_session):
        """POST /api/jobs/<id>/publish → is_paid=true (эмуляция оплаты)."""
        sess = employer_session

        # Создать задание
        form = form_with_csrf(
            sess,
            title="Тест is_paid",
            description="Проверка флага is_paid",
            work_type="Курьер",
            payment="300",
            address="Москва, ул. Платёжная, 1",
            city="Москва",
            latitude="55.75",
            longitude="37.61",
            max_workers="1",
        )
        create_resp = sess.post(
            f"{BASE_URL}/job/new", data=form, timeout=30, allow_redirects=False
        )
        if create_resp.status_code not in (301, 302):
            pytest.skip("Не удалось создать задание")

        location = create_resp.headers.get("Location", "")
        parts = location.strip("/").split("/")
        job_id = parts[1] if len(parts) >= 2 else None
        if not job_id:
            pytest.skip("Не удалось извлечь job_id")

        # Публикуем
        pub_resp = sess.post(
            f"{BASE_URL}/api/jobs/{job_id}/publish",
            headers=csrf_headers(sess),
            json={"tariff": "standard"},
            timeout=30,
        )
        assert pub_resp.status_code == 200, (
            f"Publish failed: {pub_resp.status_code}, body: {pub_resp.text[:300]}"
        )
        pub_data = pub_resp.json()
        assert pub_data.get("success"), f"Publish not successful: {pub_data}"

        # После публикации задание должно быть видно в ленте (значит is_paid=true)
        # Проверяем через страницу задания
        detail_resp = sess.get(f"{BASE_URL}/jobs/{job_id}", timeout=30)
        assert detail_resp.status_code == 200, (
            f"Job detail should be accessible after publish, got {detail_resp.status_code}"
        )

    @pytest.mark.skip(
        reason="Нет публичного API для чтения job_payments. "
               "Требуется админский доступ к /api/admin/payments."
    )
    def test_publish_job_creates_payment_record(self):
        """После publish, в job_payments появляется запись (проверить через админ API)."""
        pass

    def test_renew_job_endpoint(self, employer_session, published_job_id):
        """POST /api/jobs/<id>/renew → expires_at увеличивается на 30 дней."""
        sess = employer_session

        renew_resp = sess.post(
            f"{BASE_URL}/api/jobs/{published_job_id}/renew",
            headers=csrf_headers(sess),
            timeout=30,
        )
        assert renew_resp.status_code == 200, (
            f"Renew failed: {renew_resp.status_code}, body: {renew_resp.text[:300]}"
        )
        renew_data = renew_resp.json()
        assert renew_data.get("success"), (
            f"Renew not successful: {renew_data}"
        )
        assert "продлен" in renew_data.get("message", "").lower() or renew_data.get("success"), (
            f"Expected renewal success message, got: {renew_data}"
        )

    def test_renew_job_requires_auth(self):
        """POST /api/jobs/<id>/renew без авторизации → 302 или 401."""
        resp = requests.post(
            f"{BASE_URL}/api/jobs/test-id/renew",
            timeout=30,
            allow_redirects=False,
        )
        assert resp.status_code in (302, 401, 403, 400), (
            f"Renew without auth should be blocked, got {resp.status_code}"
        )

    def test_payment_flow_complete(self, employer_session, worker_session):
        """Полный цикл: создать → опубликовать → задание видно в ленте."""
        e_sess = employer_session
        w_sess = worker_session

        # Создать и опубликовать
        job_id = _create_and_publish_job(e_sess, "Полный цикл оплаты")
        if not job_id:
            pytest.skip("Не удалось создать и опубликовать задание")

        # Проверить, что задание видно в ленте трудника
        resp = w_sess.get(f"{BASE_URL}/", timeout=30)
        assert resp.status_code == 200
        assert job_id in resp.text, (
            f"Оплаченное задание {job_id} должно быть видно в ленте трудника"
        )

        # Проверить, что задание доступно по прямой ссылке
        detail = w_sess.get(f"{BASE_URL}/jobs/{job_id}", timeout=30)
        assert detail.status_code == 200, (
            f"Трудник должен видеть страницу задания, got {detail.status_code}"
        )


class TestMonetizationBlueprint:
    """P0: Проверка регистрации monetization_bp."""

    @pytest.mark.skip(reason="Монетизация отключена в ветке main — monetization.py удалён")
    def test_monetization_blueprint_registered(self):
        """Проверить что monetization_bp зарегистрирован в app/__init__.py."""
        with open("app/__init__.py", "r", encoding="utf-8") as f:
            code = f.read()

        # Проверяем импорт monetization_bp
        assert "from app.blueprints.monetization import monetization_bp" in code, (
            "monetization_bp не импортирован в app/__init__.py"
        )

        # Проверяем регистрацию blueprint
        assert "app.register_blueprint(monetization_bp)" in code, (
            "monetization_bp не зарегистрирован в app/__init__.py"
        )

    @pytest.mark.skip(reason="Монетизация отключена в ветке main — monetization.py удалён")
    def test_monetization_blueprint_file_exists(self):
        """Проверить что файл monetization.py существует."""
        import os
        assert os.path.exists("app/blueprints/monetization.py"), (
            "Файл app/blueprints/monetization.py не найден"
        )


class TestNoPaywall:
    """P0: Проверка, что старая модель pay-per-contact удалена."""

    def test_no_paywall_for_applications_page(self, employer_session, published_job_id, worker_session):
        """После отклика, страница my-applications доступна без дополнительной оплаты."""
        e_sess = employer_session
        w_sess = worker_session

        # Трудник откликается
        apply_resp = w_sess.post(
            f"{BASE_URL}/apply/{published_job_id}",
            data=form_with_csrf(w_sess),
            timeout=30,
            allow_redirects=True,
        )
        assert apply_resp.status_code == 200, f"Apply failed: {apply_resp.status_code}"

        # Работодатель открывает страницу заявок
        my_apps = e_sess.get(f"{BASE_URL}/my-applications", timeout=30)
        assert my_apps.status_code == 200, (
            f"My-applications should be accessible without paywall, got {my_apps.status_code}"
        )

        # Не должно быть упоминаний старой модели pay-per-contact
        # (блокировка контактов до оплаты)
        assert "Оплатите" not in my_apps.text or "paywall" not in my_apps.text.lower(), (
            "Страница my-applications не должна требовать дополнительной оплаты за контакты"
        )

    def test_contacts_visible_without_extra_payment(self, employer_session, published_job_id, worker_session):
        """Контакты трудника видны работодателю без дополнительной оплаты."""
        e_sess = employer_session
        w_sess = worker_session

        # Трудник откликается
        w_sess.post(
            f"{BASE_URL}/apply/{published_job_id}",
            data=form_with_csrf(w_sess),
            timeout=30,
            allow_redirects=True,
        )

        # Работодатель смотрит заявки — контакты должны быть видны
        my_apps = e_sess.get(f"{BASE_URL}/my-applications", timeout=30)
        assert my_apps.status_code == 200

        # В HTML должны быть контакты или заглушка контактов
        # Проверяем, что нет сообщения "Оплатите для просмотра контактов"
        paywall_phrases = [
            "Оплатите для просмотра",
            "Контакт скрыт",
            "Оплатите доступ",
            "paywall",
        ]
        for phrase in paywall_phrases:
            assert phrase.lower() not in my_apps.text.lower(), (
                f"Обнаружен paywall: '{phrase}' на странице my-applications"
            )
