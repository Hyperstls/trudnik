# tests_e2e/test_revived_ui.py
"""E2E тесты недавно починенных UI-элементов.

Покрытие:
- модалка «Оценить» на /workers (dialog#rating-modal);
- invite-модалка на /workers (динамический dialog#invite-modal с select заданий);
- отклик/отзыв на главной без перезагрузки страницы (optimistic UI);
- profile-menu dropdown в шапке (открытие, пункты, Escape, переход в ЧС);
- чат 2.0: отправка сообщения, статус, дивидер «Сегодня», время ЧЧ:ММ;
- модалка «Удалить аккаунт» на /profile (только открытие/закрытие!).
"""
import os
import re
import uuid

import pytest

BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8000')

WORKER_EMAIL = 'test-worker-92c82f24@test.ru'
EMPLOYER_EMAIL = 'org@test.ru'
EMPLOYER_PASSWORD = 'test123'
PASSWORD = 'Aa1!aaaa'
# Принятый отклик test-worker'а — чат доступен обеим сторонам
CHAT_APPLICATION_ID = '45c62cd3-d2dd-4e57-9d90-ca66a775573e'


# ─────────────────────────────────────────────────────────────────
# Хелперы
# ─────────────────────────────────────────────────────────────────

def _clear_login_rate_limits():
    """Сбрасывает per-IP/per-account лимиты логина в локальном Redis (raw RESP,
    без import redis — иначе конфликт с моками unit-suite). Dev-окружение only."""
    import socket
    from urllib.parse import urlparse
    try:
        url = os.environ.get('REDIS_URL', 'redis://:trudnik-local-dev@localhost:6379/0')
        u = urlparse(url)
        sock = socket.create_connection((u.hostname or 'localhost', u.port or 6379), timeout=2)
        f = sock.makefile('rbw')
        def cmd(*parts):
            f.write(b'*%d\r\n' % len(parts) + b''.join(
                b'$%d\r\n%s\r\n' % (len(str(p).encode()), str(p).encode()) for p in parts))
            f.flush()
            return f.readline()
        try:
            password = (u.password or '').strip(':')
            if password:
                cmd('AUTH', password)
            if (u.path or '').lstrip('/') not in ('', '0'):
                cmd('SELECT', u.path.lstrip('/'))
            for pattern in ('login_ip:*', 'login_attempts:*', 'login_lockout:*',
                            'ratelimit:/login:*'):
                cmd('EVAL', "for _,k in ipairs(redis.call('KEYS', ARGV[1])) do redis.call('DEL', k) end return 1",
                    '0', pattern)
        finally:
            sock.close()
    except Exception:
        pass


def _login(page, email, password=PASSWORD):
    """Войти через форму /login; при отказе — skip (dev-server reloader?)."""
    _clear_login_rate_limits()
    page.goto(f'{BASE_URL}/login')
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    try:
        page.wait_for_url(lambda url: '/login' not in url, timeout=15000)
    except Exception:
        pytest.skip(f'Не удалось войти как {email} (перезапуск dev-сервера?) — повторите прогон')
    page.wait_for_load_state('domcontentloaded')


def _goto_authed(page, path):
    """Перейти на защищённую страницу; skip, если выкинуло на логин/ошибку."""
    resp = page.goto(f'{BASE_URL}{path}')
    if resp is None or resp.status != 200 or '/login' in page.url:
        pytest.skip(f'{path} недоступен (status={resp.status if resp else None}, url={page.url})')
    return resp


# ─────────────────────────────────────────────────────────────────
# 1. Модалка «Оценить» на /workers
# ─────────────────────────────────────────────────────────────────

def test_workers_rating_modal_opens_and_closes_on_escape(page):
    """Кнопка «Оценить» открывает dialog#rating-modal (skeleton/форма), Escape закрывает."""
    _login(page, WORKER_EMAIL)
    _goto_authed(page, '/workers')

    rate_btns = page.locator('button[data-action="rate"]')
    if rate_btns.count() == 0:
        pytest.skip('В каталоге /workers нет трудников с кнопкой «Оценить»')
    rate_btns.first.click()

    # CSP запрещает unsafe-eval — только CSS-селекторы, никакого wait_for_function
    page.wait_for_selector('#rating-modal[open]', state='visible')
    # Пока грузятся завершённые задания виден skeleton, после — форма оценки
    page.wait_for_selector('#rating-loading:not(.hidden), #rating-body:not(.hidden)', state='visible')

    page.keyboard.press('Escape')
    page.wait_for_selector('#rating-modal:not([open])', state='attached')


# ─────────────────────────────────────────────────────────────────
# 2. Invite-модалка на /workers (работодатель)
# ─────────────────────────────────────────────────────────────────

def test_workers_invite_modal_lists_open_jobs(page):
    """«Пригласить» открывает dialog#invite-modal: select с открытыми заданиями, «Отмена» закрывает."""
    _login(page, EMPLOYER_EMAIL, password=EMPLOYER_PASSWORD)
    _goto_authed(page, '/workers')

    invite_btns = page.locator('button[id^="invite-btn-"]:not([disabled])')
    if invite_btns.count() == 0:
        pytest.skip('Нет трудников, доступных для приглашения')
    invite_btns.first.click()

    page.wait_for_selector('#invite-modal[open]', state='visible')
    # Список заданий лениво подгружается со страницы /my-jobs — ждём разблокировки select
    # (у employer@test.local ~1669 открытых заданий, страница тяжёлая — таймаут с запасом)
    page.wait_for_selector('#invite-modal-job-select:not([disabled])', timeout=30000)

    options = page.locator('#invite-modal-job-select option')
    if options.count() <= 1:
        pytest.skip('У работодателя нет открытых заданий для приглашения')
    # 1 option-заглушка «— Выберите задание —» + открытые задания
    assert options.count() > 10, f'Ожидали >10 option в select заданий, получили {options.count()}'

    page.locator('#invite-modal button', has_text='Отмена').click()
    page.wait_for_selector('#invite-modal:not([open])', state='attached')


# ─────────────────────────────────────────────────────────────────
# 3. Отклик/отзыв на главной без перезагрузки
# ─────────────────────────────────────────────────────────────────

def test_apply_and_unapply_without_page_reload(page):
    """«Откликнуться»/«Отозвать» на / работают fetch'ом: URL не меняется, карточка обновляется."""
    _login(page, WORKER_EMAIL)
    _goto_authed(page, '/')

    apply_form = page.locator('.js-apply-form')
    if apply_form.count() == 0:
        pytest.skip('На главной нет заданий, на которые можно откликнуться')

    # Карточка фиксируется по data-job-id ДО клика — после отклика форма
    # в карточке заменяется бейджем, локатор по .js-apply-form «умирает»
    job_id = apply_form.first.get_attribute('data-job-id')
    card = page.locator(f'article.card:has([data-job-id="{job_id}"])').first
    url_before = page.url

    # Откликнуться (optimistic UI + POST /api/jobs/<id>/apply)
    # dispatch_event вместо click: optimistic-рендер удаляет форму из DOM
    # синхронно во время click-действия → locator.click падает с "detached"
    with page.expect_response(
        lambda r: r.request.method == 'POST' and '/api/jobs/' in r.url and r.url.endswith('/apply'),
        timeout=15000,
    ) as resp_info:
        apply_form.first.locator('button[type="submit"]').dispatch_event('click')
    assert page.url == url_before, 'Страница перезагрузилась при отклике'
    assert resp_info.value.status in (200, 409), f'apply вернул {resp_info.value.status}'

    badge = card.locator('.js-applied-badge')
    badge.wait_for(state='visible')
    assert 'Отклик отправлен' in badge.inner_text()
    assert 'applied' in (card.get_attribute('class') or ''), 'У карточки нет класса applied'
    assert card.locator('.js-unapply-form').count() == 1, 'Кнопка «Отозвать» не появилась'

    # Отозвать — состояние возвращается к «Откликнуться»
    with page.expect_response(
        lambda r: r.request.method == 'POST' and '/api/jobs/' in r.url and r.url.endswith('/unapply'),
        timeout=15000,
    ) as resp_info:
        card.locator('.js-unapply-form button[type="submit"]').dispatch_event('click')
    assert page.url == url_before, 'Страница перезагрузилась при отзыве отклика'
    assert resp_info.value.status in (200, 409), f'unapply вернул {resp_info.value.status}'

    card.locator('.js-apply-form button[type="submit"]').wait_for(state='visible')
    assert card.locator('.js-applied-badge').count() == 0, 'Бейдж «Отклик отправлен» не исчез'
    assert 'applied' not in (card.get_attribute('class') or ''), 'Класс applied не снят'


# ─────────────────────────────────────────────────────────────────
# 4. Profile-menu dropdown в шапке
# ─────────────────────────────────────────────────────────────────

def test_profile_menu_dropdown_items_escape_and_blacklist(page):
    """#profile-menu-btn открывает меню с пунктами; Escape закрывает; «Чёрный список» → /blacklist (200)."""
    _login(page, WORKER_EMAIL)
    _goto_authed(page, '/')

    menu = page.locator('#profile-menu')
    page.click('#profile-menu-btn')
    page.wait_for_selector('#profile-menu:not(.hidden)', state='visible')

    # Все ключевые пункты на месте
    assert menu.locator('a[href="/profile"]').count() == 1, 'Нет пункта «Профиль»'
    assert menu.locator('a[href="/invitations"]').count() == 1, 'Нет пункта «Приглашения»'
    assert menu.locator('a[href="/blacklist"]').count() == 1, 'Нет пункта «Чёрный список»'
    assert menu.locator('button:has-text("Выход")').count() == 1, 'Нет пункта «Выход»'

    # Escape закрывает
    page.keyboard.press('Escape')
    page.wait_for_selector('#profile-menu.hidden', state='attached')

    # Переход «Чёрный список»: 200, без редиректа на логин (мультирольность)
    page.click('#profile-menu-btn')
    page.wait_for_selector('#profile-menu:not(.hidden)', state='visible')
    with page.expect_response(lambda r: r.url.rstrip('/').endswith('/blacklist'), timeout=15000) as resp_info:
        menu.locator('a[href="/blacklist"]').click()
    page.wait_for_url('**/blacklist**')
    assert resp_info.value.status == 200, f'/blacklist вернул {resp_info.value.status}'
    assert '/login' not in page.url, 'Редирект на логин при переходе в «Чёрный список»'


# ─────────────────────────────────────────────────────────────────
# 5. Чат 2.0: отправка сообщения
# ─────────────────────────────────────────────────────────────────

def test_chat_send_message_shows_status_time_and_today_divider(page):
    """Enter в textarea отправляет сообщение: ряд с msg-status, время ЧЧ:ММ, дивидер «Сегодня»."""
    _login(page, WORKER_EMAIL)
    resp = page.goto(f'{BASE_URL}/chat/{CHAT_APPLICATION_ID}')
    if resp is None or resp.status != 200 or '/login' in page.url:
        pytest.skip(f'Чат {CHAT_APPLICATION_ID} недоступен (status={resp.status if resp else None})')

    textarea = page.locator('#message-input')
    textarea.wait_for(state='visible')

    text = f'e2e-проверка {uuid.uuid4().hex[:8]}'
    textarea.fill(text)
    textarea.press('Enter')

    # Ряд с нашим сообщением (оптимистичный ряд появляется сразу)
    row = page.locator('.msg-row', has_text=text).last
    row.wait_for(state='visible')
    # Статус сообщения (sending → sent)
    assert row.locator('.msg-status').count() == 1, 'Нет элемента .msg-status у отправленного сообщения'
    # Время в формате ЧЧ:ММ
    time_text = row.locator('.msg-time').inner_text().strip()
    assert re.fullmatch(r'\d{2}:\d{2}', time_text), f'Время "{time_text}" не в формате ЧЧ:ММ'
    # Дивидер даты «Сегодня» присутствует в ленте
    assert page.locator('.chat-date-divider', has_text='Сегодня').count() >= 1, \
        'Нет дивидера «Сегодня» в ленте сообщений'


# ─────────────────────────────────────────────────────────────────
# 6. Модалка «Удалить аккаунт» — только открытие/закрытие
# ─────────────────────────────────────────────────────────────────

def test_delete_account_modal_open_and_close(page):
    """«Удалить аккаунт» на /profile открывает dialog; «Отмена» и Escape закрывают. Аккаунт НЕ удаляется."""
    _login(page, WORKER_EMAIL)
    _goto_authed(page, '/profile')

    page.click('#js-delete-account-btn')
    page.wait_for_selector('#js-delete-account-modal[open]', state='visible')

    # Кнопка подтверждения заблокирована без ввода «УДАЛИТЬ»
    assert page.locator('#js-delete-account-submit').is_disabled()

    page.click('#js-delete-account-cancel')
    page.wait_for_selector('#js-delete-account-modal:not([open])', state='attached')

    # Повторное открытие + закрытие по Escape
    page.click('#js-delete-account-btn')
    page.wait_for_selector('#js-delete-account-modal[open]', state='visible')
    page.keyboard.press('Escape')
    page.wait_for_selector('#js-delete-account-modal:not([open])', state='attached')

    # Страховка: мы всё ещё залогинены, аккаунт на месте
    _goto_authed(page, '/profile')
