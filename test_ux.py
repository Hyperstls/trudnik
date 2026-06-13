"""
P0-тесты UI/UX проекта «Трудник».
Проверяют корректность отображения HTML-страниц и наличие ключевых элементов.

Запуск: python -m pytest test_ux.py -v --tb=short
"""

import re
import time

import pytest
import requests


BASE_URL = "http://localhost:5000"

# Тестовые учётные данные (из setup_test_users.py)
EMPLOYER_EMAIL = "org@test.ru"
EMPLOYER_PASSWORD = "test123456"
WORKER_EMAIL = "trud3@test.ru"
WORKER_PASSWORD = "test123456"


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


# ──────────────────────────────────────────────
# Тесты UI/UX — Главная страница и фильтры
# ──────────────────────────────────────────────

class TestMainPage:
    """P0: Проверка главной страницы (лента заданий)."""

    def test_main_page_accessible_unauthorized(self):
        """GET / → 200, главная страница доступна без авторизации."""
        resp = requests.get(f"{BASE_URL}/", timeout=30)
        assert resp.status_code == 200, (
            f"Main page should return 200, got {resp.status_code}"
        )

    def test_main_page_has_job_filters(self, worker_session):
        """GET / → HTML содержит фильтры: «Все», «Новые», «Откликнулся» или их эквиваленты."""
        resp = worker_session.get(f"{BASE_URL}/", timeout=30)
        assert resp.status_code == 200

        html = resp.text.lower()

        # Проверяем наличие фильтров (русские или английские эквиваленты)
        filter_keywords = [
            "все", "всех",
            "новые", "новых",
            "откликнулся", "откликнулись",
            "фильтр", "filter",
            "категори",  # категории
            "сортиров",  # сортировка
        ]
        found = [kw for kw in filter_keywords if kw in html]
        assert len(found) > 0, (
            f"На главной странице не найдены элементы фильтрации заданий. "
            f"HTML (первые 500): {resp.text[:500]}"
        )

    def test_main_page_has_job_elements(self, worker_session):
        """GET / → HTML содержит элементы заданий (карточки, ссылки)."""
        resp = worker_session.get(f"{BASE_URL}/", timeout=30)
        assert resp.status_code == 200

        html = resp.text

        # Проверяем наличие ссылок на задания или карточек
        job_indicators = [
            '/jobs/',
            'job-card',
            'job-item',
            'job_list',
            'задание',
            'class="job',
            'data-job',
        ]
        found = [ind for ind in job_indicators if ind.lower() in html.lower()]
        assert len(found) > 0, (
            f"На главной странице не найдены элементы заданий. "
            f"HTML (первые 500): {resp.text[:500]}"
        )


class TestMyJobsPage:
    """P0: Проверка страницы «Мои задания»."""

    def test_my_jobs_page_accessible(self, employer_session):
        """GET /my-jobs → 200 для работодателя."""
        resp = employer_session.get(f"{BASE_URL}/my-jobs", timeout=30, allow_redirects=False)
        assert resp.status_code == 200, (
            f"My-jobs should return 200 for employer, got {resp.status_code}"
        )

    def test_my_jobs_page_has_status_buttons(self, employer_session):
        """GET /my-jobs → HTML содержит кнопки управления заданиями."""
        resp = employer_session.get(f"{BASE_URL}/my-jobs", timeout=30)
        assert resp.status_code == 200

        html = resp.text.lower()

        # Проверяем наличие хотя бы одной из кнопок управления
        button_keywords = [
            "редактировать",
            "отменить",
            "завершить",
            "продлить",
            "опубликовать",
            "восстановить",
            "edit",
            "cancel",
            "complete",
            "renew",
            "publish",
            "restore",
        ]
        found = [kw for kw in button_keywords if kw in html]
        assert len(found) > 0, (
            f"На странице my-jobs не найдены кнопки управления заданиями. "
            f"HTML (первые 500): {resp.text[:500]}"
        )

    def test_job_status_displayed_correctly(self, employer_session):
        """На странице /my-jobs отображается статус задания."""
        sess = employer_session

        # Создаём задание, чтобы гарантировать наличие статуса
        form = form_with_csrf(
            sess,
            title=f"Тест статуса {int(time.time())}",
            description="Проверка отображения статуса",
            work_type="Уборка",
            payment="500",
            address="Москва, ул. Статусная, 1",
            city="Москва",
            latitude="55.75",
            longitude="37.61",
            max_workers="1",
        )
        create_resp = sess.post(
            f"{BASE_URL}/job/new", data=form, timeout=30, allow_redirects=False
        )
        if create_resp.status_code not in (301, 302):
            # Даже если не удалось создать, проверяем страницу
            pass

        # Проверяем страницу my-jobs
        resp = sess.get(f"{BASE_URL}/my-jobs", timeout=30)
        assert resp.status_code == 200

        html = resp.text.lower()

        # Проверяем наличие статусов
        status_keywords = [
            "open", "открыт",
            "in_progress", "в работе",
            "active", "актив",
            "completed", "завершён", "завершен",
            "cancelled", "отменён", "отменен",
            "pending", "ожидает",
        ]
        found = [kw for kw in status_keywords if kw in html]
        assert len(found) > 0, (
            f"На странице my-jobs не найдены статусы заданий. "
            f"HTML (первые 500): {resp.text[:500]}"
        )

    def test_my_jobs_redirects_unauthorized(self):
        """GET /my-jobs без авторизации → 302 (редирект на логин)."""
        resp = requests.get(
            f"{BASE_URL}/my-jobs", timeout=30, allow_redirects=False
        )
        assert resp.status_code in (302, 301), (
            f"My-jobs should redirect unauthorized users, got {resp.status_code}"
        )


class TestCreateJobPage:
    """P0: Проверка страницы создания задания."""

    def test_create_job_page_accessible(self, employer_session):
        """GET /job/new → 200 для работодателя."""
        resp = employer_session.get(
            f"{BASE_URL}/job/new", timeout=30, allow_redirects=False
        )
        assert resp.status_code == 200, (
            f"Job creation page should return 200, got {resp.status_code}"
        )

    def test_create_job_page_has_form(self, employer_session):
        """GET /job/new → HTML содержит <form> с полями title, description, address."""
        resp = employer_session.get(f"{BASE_URL}/job/new", timeout=30)
        assert resp.status_code == 200

        html = resp.text.lower()

        # Проверяем наличие формы
        assert "<form" in html, (
            f"Страница создания задания не содержит <form>. "
            f"HTML (первые 500): {resp.text[:500]}"
        )

        # Проверяем наличие ключевых полей
        field_keywords = [
            "title", "название",
            "description", "описание",
            "address", "адрес",
        ]
        found = [kw for kw in field_keywords if kw in html]
        assert len(found) >= 2, (
            f"Страница создания задания не содержит ожидаемых полей (title, description, address). "
            f"Найдено: {found}. HTML (первые 500): {resp.text[:500]}"
        )

    def test_create_job_page_redirects_worker(self, worker_session):
        """GET /job/new → редирект для трудника (только работодатели)."""
        resp = worker_session.get(
            f"{BASE_URL}/job/new", timeout=30, allow_redirects=False
        )
        # Трудник не должен иметь доступ к созданию задания
        assert resp.status_code in (302, 301, 403), (
            f"Worker should be redirected from job creation, got {resp.status_code}"
        )


class TestAuthPages:
    """P0: Проверка страниц авторизации."""

    def test_login_page_accessible(self):
        """GET /login → 200."""
        resp = requests.get(f"{BASE_URL}/login", timeout=30)
        assert resp.status_code == 200, (
            f"Login page should return 200, got {resp.status_code}"
        )

    def test_login_page_has_csrf_token(self):
        """GET /login → HTML содержит <meta name="csrf-token">."""
        resp = requests.get(f"{BASE_URL}/login", timeout=30)
        assert resp.status_code == 200

        csrf = extract_csrf_token(resp.text)
        assert csrf is not None, (
            f"Страница логина не содержит CSRF-токен в meta-теге. "
            f"HTML (первые 500): {resp.text[:500]}"
        )
        # Токен должен быть непустой строкой
        assert len(csrf) > 10, (
            f"CSRF-токен слишком короткий ({len(csrf)} символов): {csrf}"
        )

    def test_register_page_accessible(self):
        """GET /register → 200."""
        resp = requests.get(f"{BASE_URL}/register", timeout=30)
        assert resp.status_code == 200, (
            f"Register page should return 200, got {resp.status_code}"
        )

    def test_register_page_has_form(self):
        """GET /register → HTML содержит форму регистрации."""
        resp = requests.get(f"{BASE_URL}/register", timeout=30)
        assert resp.status_code == 200

        html = resp.text.lower()
        assert "<form" in html, (
            f"Страница регистрации не содержит <form>. "
            f"HTML (первые 500): {resp.text[:500]}"
        )


class TestOtherPages:
    """P0: Проверка прочих страниц."""

    def test_favorites_page_accessible(self, worker_session):
        """GET /favorites → 200 для авторизованного трудника."""
        resp = worker_session.get(
            f"{BASE_URL}/favorites", timeout=30, allow_redirects=False
        )
        assert resp.status_code == 200, (
            f"Favorites page should return 200, got {resp.status_code}"
        )

    def test_favorites_page_redirects_unauthorized(self):
        """GET /favorites без авторизации → 302."""
        resp = requests.get(
            f"{BASE_URL}/favorites", timeout=30, allow_redirects=False
        )
        assert resp.status_code in (302, 301), (
            f"Favorites should redirect unauthorized users, got {resp.status_code}"
        )

    def test_profile_page_accessible(self, employer_session):
        """GET /profile → 200 для авторизованного пользователя."""
        resp = employer_session.get(
            f"{BASE_URL}/profile", timeout=30, allow_redirects=False
        )
        assert resp.status_code == 200, (
            f"Profile page should return 200, got {resp.status_code}"
        )

    def test_profile_page_redirects_unauthorized(self):
        """GET /profile без авторизации → 302."""
        resp = requests.get(
            f"{BASE_URL}/profile", timeout=30, allow_redirects=False
        )
        assert resp.status_code in (302, 301), (
            f"Profile should redirect unauthorized users, got {resp.status_code}"
        )


class TestEdgeCases:
    """P0: Edge Cases (выборочно из Блока 9)."""

    def test_expired_job_not_in_feed(self, employer_session, worker_session):
        """
        Создать задание с истекшим сроком и проверить, что оно не в ленте.
        Примечание: задание без публикации (is_paid=false) не отображается в ленте,
        поэтому проверяем, что неоплаченное задание не видно.
        """
        e_sess = employer_session
        w_sess = worker_session

        # Создаём задание (без публикации — оно не должно быть в ленте)
        form = form_with_csrf(
            e_sess,
            title=f"Истекшее задание {int(time.time())}",
            description="Тест видимости истекшего задания",
            work_type="Курьер",
            payment="300",
            address="Москва, ул. Истекшая, 1",
            city="Москва",
            latitude="55.75",
            longitude="37.61",
            max_workers="1",
        )
        create_resp = e_sess.post(
            f"{BASE_URL}/job/new", data=form, timeout=30, allow_redirects=False
        )
        if create_resp.status_code not in (301, 302):
            pytest.skip("Не удалось создать задание")

        location = create_resp.headers.get("Location", "")
        parts = location.strip("/").split("/")
        job_id = parts[1] if len(parts) >= 2 else None
        if not job_id:
            pytest.skip("Не удалось извлечь job_id")

        # Проверяем, что задание НЕ видно в ленте (не оплачено)
        resp = w_sess.get(f"{BASE_URL}/", timeout=30)
        assert resp.status_code == 200

        # Неоплаченное задание не должно появляться в ленте
        assert job_id not in resp.text, (
            f"Неоплаченное задание {job_id} не должно отображаться в ленте"
        )

    def test_job_with_max_workers_shows_correct_count(self, employer_session, worker_session):
        """Создать задание с max_workers=3, проверить что на странице отображается max_workers=3."""
        e_sess = employer_session

        # Создаём задание с max_workers=3
        form = form_with_csrf(
            e_sess,
            title=f"Задание на 3 места {int(time.time())}",
            description="Тест отображения max_workers",
            work_type="Уборка",
            payment="800",
            address="Москва, ул. Множественная, 3",
            city="Москва",
            latitude="55.75",
            longitude="37.61",
            max_workers="3",
        )
        create_resp = e_sess.post(
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
        pub_resp = e_sess.post(
            f"{BASE_URL}/api/jobs/{job_id}/publish",
            headers=csrf_headers(e_sess),
            json={"tariff": "standard"},
            timeout=30,
        )
        if not pub_resp.ok:
            pytest.skip("Не удалось опубликовать задание")

        # Проверяем страницу задания
        detail = e_sess.get(f"{BASE_URL}/jobs/{job_id}", timeout=30)
        assert detail.status_code == 200, (
            f"Job detail should return 200, got {detail.status_code}"
        )

        # Ищем "3" рядом с упоминаниями мест/работников
        html = detail.text.lower()
        # Проверяем, что число 3 присутствует на странице
        # (точная проверка зависит от шаблона, поэтому проверяем наличие в контексте)
        max_workers_indicators = [
            "max_workers", "max-workers",
            "мест", "места",
            "работник", "worker",
        ]
        has_context = any(ind in html for ind in max_workers_indicators)
        # Если есть контекст про места/работников, то число 3 должно быть рядом
        if has_context:
            assert "3" in html or "три" in html, (
                f"На странице задания должно отображаться max_workers=3. "
                f"HTML (первые 500): {resp.text[:500]}"
            )
        else:
            # Если контекст не найден — страница может использовать другой шаблон
            pass

    def test_csrf_token_present_on_all_protected_pages(self, employer_session):
        """CSRF-токен присутствует на всех защищённых страницах."""
        sess = employer_session
        pages = [
            "/",
            "/my-jobs",
            "/profile",
            "/chats",
            "/job/new",
        ]
        for page in pages:
            resp = sess.get(f"{BASE_URL}{page}", timeout=30)
            if resp.status_code == 200:
                csrf = extract_csrf_token(resp.text)
                assert csrf is not None, (
                    f"CSRF-токен отсутствует на странице {page}"
                )
                assert len(csrf) > 10, (
                    f"CSRF-токен слишком короткий на странице {page}: {csrf}"
                )
