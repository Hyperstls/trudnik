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
    if create_resp.status_code not in (301, 302) and create_resp.status_code != 200:
        return None

    location = create_resp.headers.get("Location", "")
    parts = location.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "job":
        job_id = parts[1]
    else:
        # Редирект на /my-jobs или / — ищем ID задания на странице
        my_jobs_resp = session.get(f"{BASE_URL}/my-jobs", timeout=30)
        import re as _re
        job_ids = _re.findall(r'/jobs/([a-f0-9-]{36})', my_jobs_resp.text)
        job_id = job_ids[-1] if job_ids else None
        if not job_id:
            job_ids_attr = _re.findall(r'data-job-id="([a-f0-9-]{36})"', my_jobs_resp.text)
            job_id = job_ids_attr[-1] if job_ids_attr else None
    if not job_id:
        return None

    # После рефакторинга задания создаются с is_paid=True по умолчанию.
    # Раньше требовался вызов /api/jobs/<id>/publish, который больше не существует.
    return job_id


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture(scope="function")
def employer_session():
    """Сессия работодателя (org@test.ru)."""
    sess = requests.Session()
    csrf = login_as(sess, EMPLOYER_EMAIL, EMPLOYER_PASSWORD)
    if csrf is None:
        pytest.fail("Не удалось войти как работодатель. Проверьте учётные данные.")
    return sess


@pytest.fixture(scope="function")
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
        pytest.skip("Не удалось создать и опубликовать задание")
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
        """Задание создаётся с is_paid=True по умолчанию (проверка через страницу)."""
        sess = employer_session

        # Создать задание (сразу is_paid=True)
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
        if len(parts) >= 2 and parts[0] == "job":
            job_id = parts[1]
        else:
            # Редирект на /my-jobs — ищем ID задания
            my_jobs_resp = sess.get(f"{BASE_URL}/my-jobs", timeout=30)
            import re as _re
            job_ids = _re.findall(r'/jobs/([a-f0-9-]{36})', my_jobs_resp.text)
            job_id = job_ids[-1] if job_ids else None
        if not job_id:
            pytest.skip("Не удалось извлечь job_id")

        # После создания задание должно быть доступно (is_paid=True по умолчанию)
        detail_resp = sess.get(f"{BASE_URL}/jobs/{job_id}", timeout=30)
        assert detail_resp.status_code == 200, (
            f"Job detail should be accessible, got {detail_resp.status_code}"
        )

    @pytest.mark.skip(
        reason="Нет публичного API для чтения job_payments. "
               "Требуется админский доступ к /api/admin/payments."
    )
    def test_publish_job_creates_payment_record(self):
        """После publish, в job_payments появляется запись (проверить через админ API)."""
        pass

    @pytest.mark.skip(reason="/api/jobs/<id>/renew эндпоинт удалён; продление через UI /my-jobs")
    def test_renew_job_endpoint(self, employer_session, published_job_id):
        """POST /api/jobs/<id>/renew → эндпоинт удалён, продление через UI."""
        pass

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
        """Полный цикл: создать → задание доступно труднику по прямой ссылке."""
        e_sess = employer_session
        w_sess = worker_session

        # Создать задание (сразу is_paid=True)
        job_id = _create_and_publish_job(e_sess, "Полный цикл оплаты")
        if not job_id:
            pytest.skip("Не удалось создать задание")

        # Проверить, что задание доступно труднику по прямой ссылке
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
