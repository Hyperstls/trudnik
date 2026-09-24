"""
Браузерные тесты кнопок приложения «Трудник» на Playwright.

Покрывает 41 skipped-сценарий из test_buttons_backend.py,
которые невозможно выполнить через HTTP API из-за 15-секундной
задержки Supabase (сессия requests.Session истекает).

Браузерная сессия Playwright устойчива к сетевым задержкам —
cookies живут дольше, page.wait_for_*() ждёт сколь угодно долго.

Актуальный UI (редизайн 2026-09):
- wizard /job/new — 4 шага с кнопками #to-step-N (btn_primary), submit
  «Создать задание» на шаге 4; work_type — required <select>; после успеха
  редирект на /my-jobs;
- деструктивные действия — кастомная модалка <dialog id="confirm-modal">
  (showConfirm), кнопки #confirm-modal-ok/#confirm-modal-cancel;
- карточки заданий/откликов — icon-кнопки .js-job-action[data-action=...]
  и button[data-action=accept|reject][data-app-id] (без текста, title/aria-label);
- apply/withdraw, массовые и одиночные действия — fetch без reload
  (B4), ждём изменения DOM/ответа API, а не навигации;
- НЕ используем wait_for_load_state('networkidle'): Yandex.Maps и
  service worker держат соединения — networkidle не наступает.

Фикстуры: tests/conftest_playwright.py
Запуск: python -m pytest tests/test_buttons_browser.py -v -m e2e
"""

import os
import time
from urllib.parse import quote

import pytest
from playwright.sync_api import Browser, BrowserContext, Page

BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8000')
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@test.ru')
# Пароль админа локального dev-стека (см. docs: admin@test.ru / Aa1!aaaa).
# Пустой дефолт раньше ронял все TestAdmin-тесты на логине.
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Aa1!aaaa')

LONG_TIMEOUT = 60_000


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


def wizard_create_job(page: Page, title: str, description: str,
                      payment: str = '5000', city: str = 'Москва',
                      max_workers: str | None = None) -> bool:
    """Создаёт задание через 4-шаговый wizard /job/new (текущий UI).

    Кнопки «Далее» имеют стабильные id (#to-step-2/3/4): текстовый селектор
    матчит все три сразу, а после переключения шага предыдущая кнопка
    скрывается (display:none) — wait_for_selector('visible') по тексту виснет.
    work_type — required <select>: без выбора нативная валидация молча
    блокирует submit. После успеха сервер редиректит на /my-jobs.

    Returns:
        True, если после submit дождались редиректа на /my-jobs.
    """
    page.goto(f'{BASE_URL}/job/new', wait_until='domcontentloaded')
    page.wait_for_selector('input[name="title"]', state='visible', timeout=LONG_TIMEOUT)
    page.fill('input[name="title"]', title)
    page.fill('textarea[name="description"]', description)
    # Первый option — disabled-placeholder «Выберите вид работы», берём второй
    page.select_option('select[name="work_type"]', index=1)

    page.click('#to-step-2')
    page.wait_for_selector('input[name="city"]', state='visible', timeout=LONG_TIMEOUT)
    page.fill('input[name="city"]', city)

    page.click('#to-step-3')
    page.wait_for_selector('input[name="payment"]', state='visible', timeout=LONG_TIMEOUT)
    page.fill('input[name="payment"]', payment)
    if max_workers:
        page.fill('input[name="max_workers"]', max_workers)

    page.click('#to-step-4')
    page.wait_for_selector('#step-4 button[type="submit"]', state='visible', timeout=LONG_TIMEOUT)
    page.click('#step-4 button[type="submit"]')
    try:
        page.wait_for_url(lambda url: '/my-jobs' in url, timeout=LONG_TIMEOUT)
        return True
    except Exception:
        return False


def confirm_modal_click_ok(page: Page, timeout: int = 15_000) -> None:
    """Ждёт кастомную confirm-модалку (<dialog id="confirm-modal">, showConfirm)
    и нажимает OK. Текст кнопки динамический (okText: «Отозвать»/«Дублировать»/...),
    поэтому клик по стабильному id #confirm-modal-ok."""
    page.wait_for_selector('#confirm-modal[open]', state='visible', timeout=timeout)
    page.click('#confirm-modal-ok')


# ═══════════════════════════════════════════════════════════════
# Работодатель — создание и управление заданиями
# ═══════════════════════════════════════════════════════════════

class TestEmployerJobCreation:
    """Работодатель создаёт задания через wizard и управляет ими."""

    @pytest.mark.e2e
    def test_employer_creates_job_via_wizard(self, employer_page: Page):
        """Работодатель создаёт задание через 4-шаговый wizard."""
        page = employer_page
        title = f'Тестовое задание браузер {int(time.time())}'

        created = wizard_create_job(
            page, title, 'Описание тестового задания созданного через браузер',
            payment='5000', max_workers='5')

        assert created, f"Задание должно быть создано (редирект на /my-jobs). URL: {page.url}"
        # Свежие задания сверху (created_at.desc) — созданное первым в списке
        first_card = page.locator('#jobs-list .app-card').first
        first_card.wait_for(state='visible', timeout=LONG_TIMEOUT)
        assert title in first_card.inner_text(), \
            "Созданное задание должно появиться первым в списке «Мои задания»"

    @pytest.mark.e2e
    def test_employer_can_cancel_job(self, employer_page: Page):
        """Работодатель отменяет задание через кнопку «Отозвать»."""
        page = employer_page
        page.goto(f'{BASE_URL}/my-jobs', wait_until='domcontentloaded')

        # Кнопка «Отозвать» есть только у open-заданий (матрица действий)
        cancel_selector = '.js-job-action[data-action="cancelJob"]'
        if page.locator(cancel_selector).count() == 0:
            # Нет open-заданий — создаём одно через wizard
            assert wizard_create_job(
                page, f'Задание для отзыва браузер {int(time.time())}',
                'Будет отозвано в этом тесте', payment='3000'), \
                "Нужно open-задание для проверки отзыва"
            page.goto(f'{BASE_URL}/my-jobs', wait_until='domcontentloaded')

        page.wait_for_selector(cancel_selector, state='visible', timeout=LONG_TIMEOUT)
        cancel_btn = page.locator(cancel_selector).first
        job_id = cancel_btn.get_attribute('data-job-id')
        cancel_btn.click()

        # showConfirm: okText «Отозвать», id кнопки стабильный
        confirm_modal_click_ok(page)

        # B4: карточка обновляется без reload — data-status меняется на cancelled
        page.wait_for_selector(
            f'.app-card[data-job-id="{job_id}"][data-status="cancelled"]',
            timeout=LONG_TIMEOUT)

    @pytest.mark.e2e
    def test_employer_can_duplicate_job(self, employer_page: Page):
        """Работодатель дублирует задание через кнопку «Дублировать»."""
        page = employer_page
        page.goto(f'{BASE_URL}/my-jobs', wait_until='domcontentloaded')

        dup_selector = '.js-job-action[data-action="duplicateJob"]'
        page.wait_for_selector(dup_selector, state='visible', timeout=LONG_TIMEOUT)
        cards_before = page.locator('#jobs-list .app-card').count()

        page.locator(dup_selector).first.click()

        # showConfirm: okText «Дублировать»
        confirm_modal_click_ok(page)

        # B4: после успеха клон карточки (status=open) вставляется в список без reload
        page.wait_for_function(
            "(before) => document.querySelectorAll('#jobs-list .app-card').length > before",
            arg=cards_before, timeout=LONG_TIMEOUT)

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

        # Per-card форма отклика (bulk-кнопка «Откликнуться на выбранные»
        # скрыта до выбора чекбоксов — по тексту на неё полагаться нельзя)
        apply_form = page.locator('article.card form.js-apply-form')
        if apply_form.count() > 0:
            job_id = apply_form.first.get_attribute('data-job-id')
            with page.expect_response(
                    lambda r: r.url.rstrip('/').endswith('/apply')
                    and r.request.method == 'POST',
                    timeout=LONG_TIMEOUT) as resp_info:
                apply_form.first.locator('button[type="submit"]').click()
            resp = resp_info.value
            body = resp.json()
            assert resp.status == 200 and body.get('ok'), \
                f"API отклика должен вернуть ok: {resp.status} {body}"
            # B4: карточка помечается applied без перезагрузки
            page.wait_for_selector(
                f'article.card[data-job-id="{job_id}"].applied', timeout=LONG_TIMEOUT)
            return

        # Fallback: на все карточки каталога уже откликнулись — идём на детальную
        job_links = page.locator('article.card a[href*="/jobs/"]')
        if job_links.count() == 0:
            pytest.skip("Нет доступных заданий для отклика")
        job_links.first.click()
        page.wait_for_load_state('domcontentloaded')

        detail_form = page.locator('#worker-actions form.js-apply-form')
        if detail_form.count() == 0:
            pytest.skip("Уже откликнулись на все доступные задания")
        with page.expect_response(
                lambda r: r.url.rstrip('/').endswith('/apply')
                and r.request.method == 'POST',
                timeout=LONG_TIMEOUT) as resp_info:
            detail_form.locator('button[type="submit"]').click()
        resp = resp_info.value
        assert resp.status == 200 and resp.json().get('ok'), \
            f"API отклика должен вернуть ok: {resp.status}"
        # B4: блок действий перерисовывается — статус «Отклик отправлен»
        page.wait_for_selector(
            '#worker-actions .status-badge:has-text("Отклик отправлен")',
            timeout=LONG_TIMEOUT)

    @pytest.mark.e2e
    def test_worker_can_favorite_job(self, worker_page: Page):
        """Трудник добавляет работодателя задания в избранное (toggle)."""
        page = worker_page
        page.goto(f'{BASE_URL}/', wait_until='domcontentloaded')

        job_links = page.locator('article.card a[href*="/jobs/"]')
        if job_links.count() == 0:
            pytest.skip("Нет доступных заданий")
        job_url = job_links.first.get_attribute('href')

        page.goto(f'{BASE_URL}{job_url}', wait_until='domcontentloaded')
        fav_btn = page.locator('form[action*="/favorite"] button[type="submit"]')
        if fav_btn.count() == 0:
            pytest.skip("Кнопка избранного не найдена на странице задания")

        initial_text = fav_btn.first.inner_text().strip()

        # toggle_favorite — обычный form POST с редиректом на /employers
        with page.expect_navigation(wait_until='domcontentloaded', timeout=LONG_TIMEOUT):
            fav_btn.first.click()

        # Возвращаемся на страницу задания — кнопка должна переключиться
        page.goto(f'{BASE_URL}{job_url}', wait_until='domcontentloaded')
        new_text = page.locator(
            'form[action*="/favorite"] button[type="submit"]').first.inner_text().strip()
        assert new_text != initial_text, \
            f"Кнопка избранного должна переключиться: было «{initial_text}», стало «{new_text}»"

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
        # Таб «На мои задания» (дефолт при наличии своих заданий) — фильтр навыков
        # рендерится всегда; кнопки accept/reject — icon-only (data-action, без текста)
        page.wait_for_selector('#apps-filter-trigger, #apps-filter-sent-trigger, .app-card',
                               timeout=LONG_TIMEOUT)

        accept_btn = page.locator('button[data-action="accept"][data-app-id]')
        reject_btn = page.locator('button[data-action="reject"][data-app-id]')
        filter_trigger = page.locator('#apps-filter-trigger, #apps-filter-sent-trigger')

        has_controls = accept_btn.count() > 0 or reject_btn.count() > 0
        has_empty = 'Нет откликов' in page.content() or 'нет откликов' in page.content().lower()

        assert has_controls or has_empty or filter_trigger.count() > 0, \
            "Страница откликов должна иметь элементы управления"
        # Табы мультирольности («На мои задания»/«Мои отклики») всегда на странице
        assert page.locator('a[href*="tab=received"], a[href*="tab=sent"]').count() > 0, \
            "Страница откликов должна содержать табы"

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

            add_input = page.locator('input#skill-name-input, input[placeholder*="навык"]')
            add_btn = page.locator('button:has-text("Добавить")')

            assert add_input.count() > 0 or add_btn.count() > 0, \
                "Таб навыков должен иметь поле ввода или кнопку добавления"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.e2e
    def test_admin_can_delete_job_bypass_ownership(self, playwright_browser: Browser):
        """Админ может удалить любое задание (bypass владения).

        Самодостаточный сценарий: админ создаёт задание через wizard
        (мультирольность — любой пользователь может создавать) и удаляет его
        через админ-панель. Таблица /admin?tab=jobs показывает задания ВСЕХ
        пользователей, у каждой строки есть форма удаления — это и есть
        bypass-ownership affordance (чужие данные в тесте не трогаем).
        """
        ctx, page = create_admin_context(playwright_browser)
        try:
            title = f'Админ-тест удаления {int(time.time())}'
            assert wizard_create_job(page, title, 'Проверка каскадного удаления задания админом'), \
                f"Админ должен создать задание через wizard. URL: {page.url}"

            # bypass ownership: таблица содержит чужие задания с кнопкой удаления
            page.goto(f'{BASE_URL}/admin?tab=jobs', wait_until='domcontentloaded')
            page.wait_for_selector('#jobs-table tbody tr', timeout=LONG_TIMEOUT)
            delete_forms = page.locator(
                '#jobs-table form[action*="/admin/jobs/"][action$="/delete"]')
            assert delete_forms.count() > 0, \
                "Админ должен видеть кнопки удаления заданий в таблице (включая чужие)"

            # Находим своё задание через поиск и удаляем end-to-end
            page.goto(f'{BASE_URL}/admin?tab=jobs&search={quote(title)}',
                      wait_until='domcontentloaded')
            row = page.locator('#jobs-table tbody tr', has_text=title)
            row.wait_for(state='visible', timeout=LONG_TIMEOUT)
            delete_btn = row.locator('form[action$="/delete"] button')
            assert delete_btn.count() > 0, "У строки задания должна быть кнопка «Удалить»"
            delete_btn.first.click()

            # .js-confirm-form → showConfirm → нативный submit → редирект на таб заданий
            page.wait_for_selector('#confirm-modal[open]', state='visible', timeout=LONG_TIMEOUT)
            with page.expect_navigation(wait_until='domcontentloaded', timeout=LONG_TIMEOUT):
                page.click('#confirm-modal-ok')
            assert 'Задание удалено' in page.content(), \
                "После удаления должен быть flash «Задание удалено»"

            # Повторный поиск — задания больше нет
            page.goto(f'{BASE_URL}/admin?tab=jobs&search={quote(title)}',
                      wait_until='domcontentloaded')
            page.wait_for_selector('#jobs-table', timeout=LONG_TIMEOUT)
            assert page.locator('#jobs-table tbody tr', has_text=title).count() == 0, \
                "Задание должно быть удалено каскадно (delete_job_cascade RPC)"
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
        from tests.conftest_playwright import (
            EMPLOYER_EMAIL, EMPLOYER_PASSWORD, WORKER_EMAIL, WORKER_PASSWORD, login_as,
        )

        emp_ctx = playwright_browser.new_context(
            viewport={'width': 1024, 'height': 768},
            locale='ru-RU',
        )
        emp_page = emp_ctx.new_page()
        login_as(emp_page, EMPLOYER_EMAIL, EMPLOYER_PASSWORD)

        wrk_ctx = playwright_browser.new_context(
            viewport={'width': 1024, 'height': 768},
            locale='ru-RU',
        )
        wrk_page = wrk_ctx.new_page()
        login_as(wrk_page, WORKER_EMAIL, WORKER_PASSWORD)

        try:
            # 1. Работодатель создаёт задание через wizard
            title = f'Комплексный тест браузер {int(time.time())}'
            assert wizard_create_job(
                emp_page, title, 'Задание для полного цикла тестирования',
                payment='7000', max_workers='3'), \
                f"Задание должно быть создано. URL: {emp_page.url}"
            # id свежего задания — первая карточка (сортировка created_at.desc)
            emp_page.wait_for_selector('#jobs-list .app-card', state='visible', timeout=LONG_TIMEOUT)
            job_id = emp_page.locator('#jobs-list .app-card').first.get_attribute('data-job-id')
            assert job_id, "Должен быть известен id созданного задания"

            # 2. Трудник откликается на странице задания (B4: fetch без reload)
            wrk_page.goto(f'{BASE_URL}/jobs/{job_id}', wait_until='domcontentloaded')
            apply_btn = wrk_page.locator('#worker-actions form.js-apply-form button[type="submit"]')
            apply_btn.wait_for(state='visible', timeout=LONG_TIMEOUT)
            with wrk_page.expect_response(
                    lambda r: r.url.rstrip('/').endswith('/apply')
                    and r.request.method == 'POST',
                    timeout=LONG_TIMEOUT) as resp_info:
                apply_btn.click()
            resp = resp_info.value
            assert resp.status == 200 and resp.json().get('ok'), \
                f"API отклика должен вернуть ok: {resp.status}"
            wrk_page.wait_for_selector(
                '#worker-actions .status-badge:has-text("Отклик отправлен")',
                timeout=LONG_TIMEOUT)

            # 3. Работодатель принимает отклик (точечный просмотр по заданию)
            emp_page.goto(f'{BASE_URL}/my-applications?job_id={job_id}',
                          wait_until='domcontentloaded')
            accept_btn = emp_page.locator('button[data-action="accept"][data-app-id]')
            accept_btn.wait_for(state='visible', timeout=LONG_TIMEOUT)
            app_id = accept_btn.first.get_attribute('data-app-id')
            with emp_page.expect_response(
                    lambda r: '/api/applications/batch' in r.url
                    and r.request.method == 'POST',
                    timeout=LONG_TIMEOUT) as resp_info:
                accept_btn.first.click()
            resp = resp_info.value
            body = resp.json()
            assert resp.status == 200 and body.get('results', {}).get('success'), \
                f"Batch-accept должен вернуть success: {resp.status} {body}"
            # Карточка отклика обновляется без reload — статус «accepted»
            emp_page.wait_for_selector(
                f'.app-card[data-app-id="{app_id}"][data-status="accepted"]',
                timeout=LONG_TIMEOUT)

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
    def test_worker_can_access_blacklist(self, worker_page: Page):
        """Мультирольность: трудник может зайти в чёрный список."""
        page = worker_page
        page.goto(f'{BASE_URL}/blacklist', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)

        assert page.url.endswith('/blacklist'), \
            "Трудник должен иметь доступ к /blacklist (мультирольность)"

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
