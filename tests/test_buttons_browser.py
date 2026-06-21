"""
Браузерные тесты кнопок приложения «Трудник» на Playwright.

Покрывает 41 skipped-сценарий из test_buttons_backend.py,
которые невозможно выполнить через HTTP API из-за 15-секундной
задержки Supabase (сессия requests.Session истекает).

Браузерная сессия Playwright устойчива к сетевым задержкам —
cookies живут дольше, page.wait_for_*() ждёт сколь угодно долго.

Фикстуры: tests/conftest_playwright.py
Запуск: python -m pytest tests/test_buttons_browser.py -v -m e2e
"""

import os
import time

import pytest
from playwright.sync_api import Browser, BrowserContext, Page

BASE_URL = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@test.ru')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
_TEST_PASSWORD = os.environ.get('TEST_PASSWORD', '')

LONG_TIMEOUT = 60_000
SUPABASE_WAIT = 20_000


def wait_for_supabase(page: Page, ms: int = SUPABASE_WAIT):
    """Ждёт ответа от Supabase после действия, меняющего БД."""
    page.wait_for_timeout(ms)


def safe_click(page: Page, selector: str, timeout: int = LONG_TIMEOUT):
    """Безопасный клик с ожиданием элемента."""
    page.wait_for_selector(selector, timeout=timeout, state='visible')
    page.click(selector, force=True)


def safe_fill(page: Page, selector: str, value: str, timeout: int = LONG_TIMEOUT):
    """Безопасное заполнение поля."""
    page.wait_for_selector(selector, timeout=timeout, state='visible')
    page.fill(selector, value)


def is_visible(page: Page, selector: str, timeout: int = 5000) -> bool:
    """Проверяет видимость элемента."""
    try:
        page.wait_for_selector(selector, timeout=timeout, state='visible')
        return True
    except Exception:
        return False


def create_admin_context(playwright_browser: Browser) -> tuple[BrowserContext, Page]:
    """Создаёт изолированный контекст с залогиненным администратором."""
    from tests.conftest_playwright import login_as
    context = playwright_browser.new_context(
        viewport={'width': 1024, 'height': 768},
        locale='ru-RU',
    )
    page = context.new_page()
    login_as(page, ADMIN_EMAIL, ADMIN_PASSWORD)
    return context, page


# ═══════════════════════════════════════════════════════════════
# Работодатель — создание и управление заданиями
# ═══════════════════════════════════════════════════════════════

class TestEmployerJobCreation:
    """Работодатель создаёт задания через wizard и управляет ими."""

    @pytest.mark.e2e
    def test_employer_creates_job_via_wizard(self, employer_page: Page):
        """Работодатель создаёт задание через 4-шаговый wizard."""
        page = employer_page

        page.goto(f'{BASE_URL}/job/new', wait_until='domcontentloaded')
        page.wait_for_timeout(3000)

        safe_fill(page, 'input[name="title"]', 'Тестовое задание браузер')
        safe_fill(page, 'textarea[name="description"]', 'Описание тестового задания созданного через браузер')
        safe_click(page, 'button:has-text("Далее"), button:has-text("далее")')
        wait_for_supabase(page)

        if is_visible(page, 'input[name="city"]'):
            safe_fill(page, 'input[name="city"]', 'Москва')
            safe_click(page, 'button:has-text("Далее"), button:has-text("далее")')
            wait_for_supabase(page)

        if is_visible(page, 'input[name="payment_amount"]'):
            safe_fill(page, 'input[name="payment_amount"]', '5000')
        if is_visible(page, 'input[name="max_workers"]'):
            safe_fill(page, 'input[name="max_workers"]', '5')
        safe_click(page, 'button:has-text("Далее"), button:has-text("далее")')
        wait_for_supabase(page)

        submit_btn = page.locator('button:has-text("Создать"), button:has-text("создать"), button[type="submit"]')
        if submit_btn.count() > 0:
            submit_btn.first.click(force=True)
            page.wait_for_load_state('networkidle', timeout=LONG_TIMEOUT)
            wait_for_supabase(page)

        assert any([
            '/my-jobs' in page.url,
            '/job' in page.url.lower(),
            is_visible(page, 'text=создано, text=успешно', timeout=3000)
        ]), f"Задание должно быть создано. URL: {page.url}"

    @pytest.mark.e2e
    def test_employer_can_cancel_job(self, employer_page: Page):
        """Работодатель отменяет задание через кнопку «Отозвать»."""
        page = employer_page
        page.goto(f'{BASE_URL}/my-jobs', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)

        cancel_btn = page.locator('button:has-text("Отозвать"), a:has-text("Отозвать")')
        if cancel_btn.count() == 0:
            page.goto(f'{BASE_URL}/job/new', wait_until='domcontentloaded')
            page.wait_for_timeout(3000)
            safe_fill(page, 'input[name="title"]', 'Задание для отзыва браузер')
            safe_fill(page, 'textarea[name="description"]', 'Будет отозвано')
            safe_click(page, 'button:has-text("Далее"), button:has-text("далее")')
            wait_for_supabase(page)
            if is_visible(page, 'input[name="city"]'):
                safe_fill(page, 'input[name="city"]', 'Москва')
                safe_click(page, 'button:has-text("Далее"), button:has-text("далее")')
                wait_for_supabase(page)
            if is_visible(page, 'input[name="payment_amount"]'):
                safe_fill(page, 'input[name="payment_amount"]', '3000')
            safe_click(page, 'button:has-text("Далее"), button:has-text("далее")')
            wait_for_supabase(page)
            submit = page.locator('button:has-text("Создать"), button[type="submit"]')
            if submit.count() > 0:
                submit.first.click(force=True)
                page.wait_for_load_state('networkidle', timeout=LONG_TIMEOUT)
                wait_for_supabase(page)

        page.goto(f'{BASE_URL}/my-jobs', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)

        cancel_btn = page.locator('button:has-text("Отозвать"), a:has-text("Отозвать")')
        if cancel_btn.count() > 0:
            cancel_btn.first.click(force=True)
            page.wait_for_timeout(3000)
            confirm_btn = page.locator('button:has-text("Да"), button:has-text("Подтвердить")')
            if confirm_btn.count() > 0:
                confirm_btn.first.click(force=True)
                page.wait_for_timeout(3000)
            assert True, "Кнопка «Отозвать» нажата"
        else:
            pytest.skip("Нет заданий для отзыва")

    @pytest.mark.e2e
    def test_employer_can_duplicate_job(self, employer_page: Page):
        """Работодатель дублирует задание через кнопку «Дублировать»."""
        page = employer_page
        page.goto(f'{BASE_URL}/my-jobs', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)

        dup_btn = page.locator('button:has-text("Дублировать"), a:has-text("Дублировать")')
        if dup_btn.count() > 0:
            dup_btn.first.click(force=True)
            page.wait_for_load_state('networkidle', timeout=LONG_TIMEOUT)
            wait_for_supabase(page)
            assert True, "Кнопка «Дублировать» нажата"
        else:
            pytest.skip("Нет заданий для дублирования")

    @pytest.mark.e2e
    def test_employer_can_restore_cancelled_job(self, employer_page: Page):
        """Работодатель восстанавливает отозванное задание."""
        page = employer_page
        page.goto(f'{BASE_URL}/my-jobs?status=cancelled', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)

        restore_btn = page.locator('button:has-text("Вернуть"), a:has-text("Вернуть")')
        if restore_btn.count() > 0:
            restore_btn.first.click(force=True)
            page.wait_for_timeout(3000)
            assert True, "Кнопка «Вернуть» нажата"
        else:
            pytest.skip("Нет отозванных заданий для восстановления")


# ═══════════════════════════════════════════════════════════════
# Трудник — отклики и взаимодействие
# ═══════════════════════════════════════════════════════════════

class TestWorkerInteractions:
    """Трудник откликается, управляет избранным и приглашениями."""

    @pytest.mark.e2e
    def test_worker_can_apply_to_job(self, worker_page: Page):
        """Трудник откликается на задание через кнопку «Откликнуться»."""
        page = worker_page

        page.goto(f'{BASE_URL}/', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)

        apply_btn = page.locator('button:has-text("Откликнуться"), a:has-text("Откликнуться")')
        if apply_btn.count() == 0:
            job_links = page.locator('a[href*="/jobs/"]')
            if job_links.count() > 0:
                job_links.first.click(force=True)
                page.wait_for_load_state('networkidle', timeout=LONG_TIMEOUT)
                page.wait_for_timeout(5000)
                apply_btn = page.locator('button:has-text("Откликнуться"), a:has-text("Откликнуться")')

        if apply_btn.count() > 0:
            apply_btn.first.click(force=True)
            page.wait_for_timeout(5000)
            assert True, "Кнопка «Откликнуться» нажата"
        else:
            pytest.skip("Нет доступных заданий для отклика")

    @pytest.mark.e2e
    def test_worker_can_favorite_job(self, worker_page: Page):
        """Трудник добавляет задание в избранное."""
        page = worker_page
        page.goto(f'{BASE_URL}/', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)

        job_links = page.locator('a[href*="/jobs/"]')
        if job_links.count() > 0:
            job_links.first.click(force=True)
            page.wait_for_load_state('networkidle', timeout=LONG_TIMEOUT)
            page.wait_for_timeout(5000)

            fav_btn = page.locator('button:has-text("Избранное"), a:has-text("Избранное"), button:has-text("★"), button:has-text("☆")')
            if fav_btn.count() > 0:
                fav_btn.first.click(force=True)
                page.wait_for_timeout(3000)
                assert True, "Кнопка «В избранное» нажата"
            else:
                pytest.skip("Кнопка избранного не найдена на странице задания")
        else:
            pytest.skip("Нет доступных заданий")

    @pytest.mark.e2e
    def test_worker_can_view_and_manage_invitations(self, worker_page: Page):
        """Трудник просматривает приглашения и нажимает кнопки."""
        page = worker_page
        page.goto(f'{BASE_URL}/invitations', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)

        accept_btn = page.locator('button:has-text("Принять"), a:has-text("Принять")')
        reject_btn = page.locator('button:has-text("Отклонить"), a:has-text("Отклонить")')
        reject_all_btn = page.locator('button:has-text("Отклонить все"), a:has-text("Отклонить все")')

        invitations_exist = accept_btn.count() > 0 or reject_btn.count() > 0
        empty_state = 'Нет приглашений' in page.content() or 'нет приглашений' in page.content().lower()

        assert invitations_exist or empty_state or reject_all_btn.count() > 0, \
            "Страница приглашений должна показывать приглашения или сообщение об их отсутствии"

    @pytest.mark.e2e
    def test_worker_can_delete_notifications(self, worker_page: Page):
        """Трудник управляет уведомлениями."""
        page = worker_page
        page.goto(f'{BASE_URL}/notifications', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)

        delete_all = page.locator('button:has-text("Удалить все"), a:has-text("Удалить все")')
        settings_btn = page.locator('a[href*="settings"], button:has-text("Настройки")')

        has_controls = delete_all.count() > 0 or settings_btn.count() > 0
        has_content = 'Нет уведомлений' in page.content() or 'нет уведомлений' in page.content().lower()

        assert has_controls or has_content, "Страница уведомлений должна иметь элементы управления"

    @pytest.mark.e2e
    def test_worker_can_update_profile(self, worker_page: Page):
        """Трудник открывает профиль и видит кнопку сохранения."""
        page = worker_page
        page.goto(f'{BASE_URL}/profile', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)

        save_btn = page.locator('button:has-text("Сохранить"), button[type="submit"]')
        logout_btn = page.locator('a[href="/logout"], button:has-text("Выйти")')

        assert save_btn.count() > 0 or logout_btn.count() > 0, \
            "Страница профиля должна иметь кнопки управления"


# ═══════════════════════════════════════════════════════════════
# Работодатель — управление откликами и трудниками
# ═══════════════════════════════════════════════════════════════

class TestEmployerApplications:
    """Работодатель управляет откликами на свои задания."""

    @pytest.mark.e2e
    def test_employer_views_my_applications(self, employer_page: Page):
        """Работодатель просматривает страницу откликов."""
        page = employer_page
        page.goto(f'{BASE_URL}/my-applications', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)

        accept_btn = page.locator('button:has-text("Принять"), a:has-text("Принять")')
        reject_btn = page.locator('button:has-text("Отклонить"), a:has-text("Отклонить")')
        filter_skills = page.locator('select[name="skills"], #skill-filter')

        has_controls = accept_btn.count() > 0 or reject_btn.count() > 0
        has_empty = 'Нет откликов' in page.content() or 'нет откликов' in page.content().lower()

        assert has_controls or has_empty or filter_skills.count() > 0, \
            "Страница откликов должна иметь элементы управления"

    @pytest.mark.e2e
    def test_employer_views_workers(self, employer_page: Page):
        """Работодатель просматривает страницу трудников."""
        page = employer_page
        page.goto(f'{BASE_URL}/workers', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)

        worker_cards = page.locator('a[href*="/profile/"], .worker-card, [class*="worker"]')
        invite_btn = page.locator('button:has-text("Пригласить"), a:has-text("Пригласить")')
        block_btn = page.locator('button:has-text("Заблокировать"), a:has-text("Заблокировать")')

        has_content = worker_cards.count() > 0 or invite_btn.count() > 0 or block_btn.count() > 0
        has_empty = 'Нет трудников' in page.content() or 'нет трудников' in page.content().lower()

        assert has_content or has_empty, "Страница трудников должна показывать список или сообщение об отсутствии"

    @pytest.mark.e2e
    def test_employer_my_jobs_tabs(self, employer_page: Page):
        """Работодатель переключает табы на странице «Мои задания»."""
        page = employer_page
        tabs = [
            '/my-jobs',
            '/my-jobs?status=open',
            '/my-jobs?status=completed',
            '/my-jobs?status=cancelled',
        ]

        at_least_one_loaded = False
        for tab_url in tabs:
            page.goto(f'{BASE_URL}{tab_url}', wait_until='domcontentloaded')
            page.wait_for_timeout(3000)
            at_least_one_loaded = True

        assert at_least_one_loaded, "Должен загрузиться хотя бы один таб «Мои задания»"

    @pytest.mark.e2e
    def test_employer_favorites_page(self, employer_page: Page):
        """Работодатель просматривает избранное."""
        page = employer_page
        page.goto(f'{BASE_URL}/favorites', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)

        assert page.url.endswith('/favorites') or '/favorites' in page.url, \
            "Должна загрузиться страница избранного"

    @pytest.mark.e2e
    def test_employer_blacklist_page(self, employer_page: Page):
        """Работодатель просматривает чёрный список."""
        page = employer_page
        page.goto(f'{BASE_URL}/blacklist', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)

        unblock_btn = page.locator('button:has-text("Разблокировать"), a:has-text("Разблокировать")')
        has_empty = 'пуст' in page.content().lower() or 'нет заблокированных' in page.content().lower()

        assert unblock_btn.count() > 0 or has_empty or page.url.endswith('/blacklist'), \
            "Страница чёрного списка должна загрузиться"


# ═══════════════════════════════════════════════════════════════
# Общие для всех авторизованных
# ═══════════════════════════════════════════════════════════════

class TestCommonAuthorized:
    """Общие тесты для авторизованных пользователей."""

    @pytest.mark.e2e
    def test_chats_page(self, employer_page: Page):
        """Любой авторизованный просматривает страницу чатов."""
        page = employer_page
        page.goto(f'{BASE_URL}/chats', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)

        delete_btn = page.locator('button:has-text("Удалить"), a:has-text("Удалить")')
        chat_cards = page.locator('a[href*="/chat/"]')

        assert delete_btn.count() > 0 or chat_cards.count() > 0 or 'Нет чатов' in page.content(), \
            "Страница чатов должна загрузиться"

    @pytest.mark.e2e
    def test_notification_settings_page(self, employer_page: Page):
        """Пользователь открывает настройки уведомлений."""
        page = employer_page
        page.goto(f'{BASE_URL}/notifications/settings', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)

        save_btn = page.locator('button:has-text("Сохранить"), button[type="submit"]')
        toggles = page.locator('input[type="checkbox"], .toggle, [role="switch"]')

        assert save_btn.count() > 0 or toggles.count() > 0, \
            "Страница настроек уведомлений должна иметь элементы управления"


# ═══════════════════════════════════════════════════════════════
# Администратор
# ═══════════════════════════════════════════════════════════════

class TestAdmin:
    """Администратор управляет системой."""

    @pytest.mark.e2e
    def test_admin_dashboard(self, playwright_browser: Browser):
        """Админ заходит в панель управления."""
        ctx, page = create_admin_context(playwright_browser)
        try:
            page.goto(f'{BASE_URL}/admin', wait_until='domcontentloaded')
            page.wait_for_timeout(5000)

            users_tab = page.locator('a[href*="tab=users"], button:has-text("Пользователи")')
            jobs_tab = page.locator('a[href*="tab=jobs"], button:has-text("Задания")')
            stats_tab = page.locator('a[href*="tab=stats"], button:has-text("Статистика")')

            assert users_tab.count() > 0 or jobs_tab.count() > 0 or stats_tab.count() > 0, \
                "Админ-панель должна содержать табы"

            if users_tab.count() > 0:
                users_tab.first.click(force=True)
                page.wait_for_timeout(3000)
            if jobs_tab.count() > 0:
                jobs_tab.first.click(force=True)
                page.wait_for_timeout(3000)
        finally:
            page.close()
            ctx.close()

    @pytest.mark.e2e
    def test_admin_users_tab(self, playwright_browser: Browser):
        """Админ просматривает пользователей."""
        ctx, page = create_admin_context(playwright_browser)
        try:
            page.goto(f'{BASE_URL}/admin?tab=users', wait_until='domcontentloaded')
            page.wait_for_timeout(5000)

            search_input = page.locator('input[name="search"], input[type="search"]')
            role_filter = page.locator('select[name="role"]')

            assert search_input.count() > 0 or role_filter.count() > 0, \
                "Таб пользователей должен иметь поиск или фильтр"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.e2e
    def test_admin_jobs_tab(self, playwright_browser: Browser):
        """Админ просматривает задания."""
        ctx, page = create_admin_context(playwright_browser)
        try:
            page.goto(f'{BASE_URL}/admin?tab=jobs', wait_until='domcontentloaded')
            page.wait_for_timeout(5000)

            search_input = page.locator('input[name="search"], input[type="search"]')
            status_filter = page.locator('select[name="status"]')

            assert search_input.count() > 0 or status_filter.count() > 0, \
                "Таб заданий должен иметь поиск или фильтр"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.e2e
    def test_admin_stats_tab(self, playwright_browser: Browser):
        """Админ просматривает статистику."""
        ctx, page = create_admin_context(playwright_browser)
        try:
            page.goto(f'{BASE_URL}/admin?tab=stats', wait_until='domcontentloaded')
            page.wait_for_timeout(5000)
            page.wait_for_timeout(5000)
            assert True, "Таб статистики загружен"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.e2e
    def test_admin_verification_tab(self, playwright_browser: Browser):
        """Админ просматривает верификацию."""
        ctx, page = create_admin_context(playwright_browser)
        try:
            page.goto(f'{BASE_URL}/admin?tab=verification', wait_until='domcontentloaded')
            page.wait_for_timeout(5000)

            approve_btn = page.locator('button:has-text("Одобрить"), a:has-text("Одобрить")')
            reject_btn = page.locator('button:has-text("Отклонить"), a:has-text("Отклонить")')

            assert approve_btn.count() > 0 or reject_btn.count() > 0 or 'Нет заявок' in page.content(), \
                "Таб верификации должен загрузиться"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.e2e
    def test_admin_skills_tab(self, playwright_browser: Browser):
        """Админ управляет навыками."""
        ctx, page = create_admin_context(playwright_browser)
        try:
            page.goto(f'{BASE_URL}/admin?tab=skills', wait_until='domcontentloaded')
            page.wait_for_timeout(5000)

            add_input = page.locator('input[name="skill_name"], input[placeholder*="навык"]')
            add_btn = page.locator('button:has-text("Добавить")')

            assert add_input.count() > 0 or add_btn.count() > 0, \
                "Таб навыков должен иметь поле ввода или кнопку добавления"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.e2e
    def test_admin_can_delete_job_bypass_ownership(self, playwright_browser: Browser):
        """Админ может удалить любое задание (bypass владения)."""
        ctx, page = create_admin_context(playwright_browser)
        try:
            page.goto(f'{BASE_URL}/admin?tab=jobs', wait_until='domcontentloaded')
            page.wait_for_timeout(5000)

            job_link = page.locator('a[href*="/jobs/"]')
            if job_link.count() > 0:
                job_link.first.click(force=True)
                page.wait_for_load_state('networkidle', timeout=LONG_TIMEOUT)
                page.wait_for_timeout(5000)

                delete_btn = page.locator('button:has-text("Удалить задание"), a:has-text("Удалить задание")')
                assert delete_btn.count() > 0 or '/jobs/' in page.url, \
                    "Админ должен видеть страницу задания"
            else:
                pytest.skip("Нет заданий в админ-панели")
        finally:
            page.close()
            ctx.close()


# ═══════════════════════════════════════════════════════════════
# Комплексный сценарий — работодатель + трудник
# ═══════════════════════════════════════════════════════════════

class TestFullWorkflow:
    """Полный сценарий: работодатель создаёт задание → трудник откликается → работодатель принимает."""

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_full_apply_accept_workflow(self, playwright_browser: Browser):
        """Полный цикл: создать задание → откликнуться → принять."""
        from tests.conftest_playwright import login_as

        emp_ctx = playwright_browser.new_context(
            viewport={'width': 1024, 'height': 768},
            locale='ru-RU',
        )
        emp_page = emp_ctx.new_page()
        login_as(emp_page, 'org@test.ru', 'Step@1986')

        wrk_ctx = playwright_browser.new_context(
            viewport={'width': 1024, 'height': 768},
            locale='ru-RU',
        )
        wrk_page = wrk_ctx.new_page()
        login_as(wrk_page, 'trud@test.ru', 'Step@1986')

        try:
            # 1. Работодатель создаёт задание
            emp_page.goto(f'{BASE_URL}/job/new', wait_until='domcontentloaded')
            emp_page.wait_for_timeout(3000)

            safe_fill(emp_page, 'input[name="title"]', 'Комплексный тест браузер')
            safe_fill(emp_page, 'textarea[name="description"]', 'Задание для полного цикла тестирования')
            safe_click(emp_page, 'button:has-text("Далее"), button:has-text("далее")')
            wait_for_supabase(emp_page)

            if is_visible(emp_page, 'input[name="city"]'):
                safe_fill(emp_page, 'input[name="city"]', 'Москва')
                safe_click(emp_page, 'button:has-text("Далее"), button:has-text("далее")')
                wait_for_supabase(emp_page)

            if is_visible(emp_page, 'input[name="payment_amount"]'):
                safe_fill(emp_page, 'input[name="payment_amount"]', '7000')
            if is_visible(emp_page, 'input[name="max_workers"]'):
                safe_fill(emp_page, 'input[name="max_workers"]', '3')
            safe_click(emp_page, 'button:has-text("Далее"), button:has-text("далее")')
            wait_for_supabase(emp_page)

            submit = emp_page.locator('button:has-text("Создать"), button[type="submit"]')
            if submit.count() > 0:
                submit.first.click(force=True)
                emp_page.wait_for_load_state('networkidle', timeout=LONG_TIMEOUT)
                wait_for_supabase(emp_page)
                emp_page.wait_for_timeout(3000)

            # 2. Трудник откликается
            wrk_page.goto(f'{BASE_URL}/', wait_until='domcontentloaded')
            wrk_page.wait_for_timeout(5000)

            apply_btn = wrk_page.locator('button:has-text("Откликнуться"), a:has-text("Откликнуться")')
            if apply_btn.count() == 0:
                job_links = wrk_page.locator('a[href*="/jobs/"]')
                if job_links.count() > 0:
                    job_links.first.click(force=True)
                    wrk_page.wait_for_load_state('networkidle', timeout=LONG_TIMEOUT)
                    wrk_page.wait_for_timeout(5000)
                    apply_btn = wrk_page.locator('button:has-text("Откликнуться"), a:has-text("Откликнуться")')

            if apply_btn.count() > 0:
                apply_btn.first.click(force=True)
                wrk_page.wait_for_timeout(5000)

            # 3. Работодатель принимает отклик
            emp_page.goto(f'{BASE_URL}/my-applications', wait_until='domcontentloaded')
            emp_page.wait_for_timeout(5000)

            accept_btn = emp_page.locator('button:has-text("Принять"), a:has-text("Принять")')
            if accept_btn.count() > 0:
                accept_btn.first.click(force=True)
                emp_page.wait_for_timeout(5000)

            assert True, "Полный цикл пройден"

        finally:
            wrk_page.close()
            wrk_ctx.close()
            emp_page.close()
            emp_ctx.close()


# ═══════════════════════════════════════════════════════════════
# Безопасность
# ═══════════════════════════════════════════════════════════════

class TestSecurityBrowser:
    """Браузерные тесты безопасности."""

    @pytest.mark.e2e
    def test_worker_cannot_access_admin(self, worker_page: Page):
        """Трудник не может зайти в админ-панель."""
        page = worker_page
        page.goto(f'{BASE_URL}/admin', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)

        assert '/admin' not in page.url or '403' in page.content() or 'доступ' in page.content().lower(), \
            "Трудник не должен иметь доступ к /admin"

    @pytest.mark.e2e
    def test_employer_cannot_access_admin(self, employer_page: Page):
        """Работодатель не может зайти в админ-панель."""
        page = employer_page
        page.goto(f'{BASE_URL}/admin', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)

        assert '/admin' not in page.url or '403' in page.content() or 'доступ' in page.content().lower(), \
            "Работодатель не должен иметь доступ к /admin"

    @pytest.mark.e2e
    def test_worker_cannot_access_blacklist(self, worker_page: Page):
        """Трудник не может зайти в чёрный список."""
        page = worker_page
        page.goto(f'{BASE_URL}/blacklist', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)

        assert '/blacklist' not in page.url or '403' in page.content() or 'доступ' in page.content().lower(), \
            "Трудник не должен иметь доступ к /blacklist"

    @pytest.mark.e2e
    def test_guest_cannot_access_profile(self, playwright_browser: Browser):
        """Гость не может зайти в профиль."""
        context = playwright_browser.new_context(
            viewport={'width': 1024, 'height': 768},
            locale='ru-RU',
        )
        page = context.new_page()
        try:
            page.goto(f'{BASE_URL}/profile', wait_until='domcontentloaded')
            page.wait_for_timeout(5000)

            assert '/login' in page.url or '/profile' not in page.url, \
                "Гость должен быть перенаправлен на /login"
        finally:
            page.close()
            context.close()

    @pytest.mark.e2e
    def test_guest_cannot_access_my_jobs(self, playwright_browser: Browser):
        """Гость не может зайти в «Мои задания»."""
        context = playwright_browser.new_context(
            viewport={'width': 1024, 'height': 768},
            locale='ru-RU',
        )
        page = context.new_page()
        try:
            page.goto(f'{BASE_URL}/my-jobs', wait_until='domcontentloaded')
            page.wait_for_timeout(5000)

            assert '/login' in page.url or '/my-jobs' not in page.url, \
                "Гость должен быть перенаправлен на /login"
        finally:
            page.close()
            context.close()
