"""Unit-тесты blueprint messenger_verify (Phase 3A: MAX deep-link верификация).

2026-08: Telegram-провайдер отключён (152-ФЗ ст. 12 — трансграничная передача);
остался только MAX. Тесты фиксируют новое поведение: telegram → 400/404.

Покрывает эндпоинты:
- GET  /messenger/start/<platform>  — генерация deep-link (login_required)
- POST /messenger/webhook/max       — webhook MAX (CSRF-exempt, middleware.py:49)
- GET  /messenger/diagnose          — диагностика API MAX

⚠️ Примечание по безопасности (задокументировано тестом
test_webhooks_have_no_signature_check): текущая реализация webhook'ов НЕ
проверяет подпись/секрет вебхука — любой POST получает 200. Тесты отражают
фактическое поведение; добавление проверки подписи — отдельная задача.

Webhook'и EXEMPT от CSRF (правило 13) — CSRF-токен в запросы НЕ добавляется.
Redis замокан stateful-моком (conftest._mock_redis_store), RPC — мок.
"""

import uuid

import pytest


TEST_USER_ID = '11111111-1111-1111-1111-111111111111'


# ── Хелперы ────────────────────────────────────────────────────────

def _login(client, user_id=TEST_USER_ID, role='worker'):
    """Авторизует тестового пользователя через сессию (access_token в session)."""
    from app.utils.auth import generate_jwt
    with client.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['role'] = role
        sess['access_token'] = generate_jwt(user_id, role)
    return client


def _seed_verify_token(user_id=TEST_USER_ID):
    """Кладёт одноразовый токен верификации в redis-мок. Возвращает токен."""
    from tests.conftest import _mock_redis_store
    token = uuid.uuid4().hex
    _mock_redis_store[f'msg_verify:{token}'] = user_id
    return token


def _rpc_spy(monkeypatch):
    """Подменяет postgrest_rpc в blueprint'е на шпион. Возвращает (spy, calls)."""
    from app.utils import PostgrestResponse
    calls = []

    def spy(function_name, params, use_admin=False):
        calls.append({'function': function_name, 'params': params,
                      'use_admin': use_admin})
        return PostgrestResponse(ok=True, status_code=200,
                                 data={'success': True},
                                 text='{"success": true}')

    monkeypatch.setattr('app.blueprints.messenger_verify.postgrest_rpc', spy)
    return spy, calls


# ── GET /messenger/start/<platform> ────────────────────────────────

class TestStartVerification:
    def test_requires_login(self, app_client):
        """Без сессии — редирект на /login."""
        resp = app_client.get('/messenger/start/max', follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_max_link(self, app_client):
        """Авторизованный пользователь получает deep-link MAX."""
        _login(app_client)
        resp = app_client.get('/messenger/start/max')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['platform'] == 'max'
        assert 'max.ru/' in data['link']
        assert '?start=' in data['link']

    def test_telegram_disabled(self, app_client):
        """Telegram отключён (152-ФЗ ст. 12, трансграничная передача) → 400."""
        _login(app_client)
        resp = app_client.get('/messenger/start/telegram')
        assert resp.status_code == 400
        assert resp.get_json()['error'] == 'unknown_platform'

    def test_unknown_platform(self, app_client):
        """Неизвестная платформа → 400."""
        _login(app_client)
        resp = app_client.get('/messenger/start/whatsapp')
        assert resp.status_code == 400
        assert resp.get_json()['error'] == 'unknown_platform'

    def test_token_stored_in_redis(self, app_client):
        """Токен из deep-link сохраняется в redis с user_id."""
        from tests.conftest import _mock_redis_store
        _login(app_client)
        resp = app_client.get('/messenger/start/max')
        token = resp.get_json()['link'].split('?start=')[1]
        assert _mock_redis_store.get(f'msg_verify:{token}') == TEST_USER_ID


# ── POST /messenger/webhook/max ────────────────────────────────────

class TestMaxWebhook:
    def test_bot_started_completes_verification(self, app_client, monkeypatch):
        """bot_started с валидным payload → RPC verify_via_messenger + токен удалён.

        requests.post мокается: бот-токен может быть задан в .env, и без мока
        тест ходил бы реальным HTTPS-запросом в MAX API.
        """
        _, calls = _rpc_spy(monkeypatch)
        monkeypatch.setattr('app.blueprints.messenger_verify.requests.post',
                            lambda *a, **kw: None)
        token = _seed_verify_token()
        from tests.conftest import _mock_redis_store

        resp = app_client.post('/messenger/webhook/max', json={
            'update_type': 'bot_started',
            'payload': token,
            'user': {'user_id': 999111},
            'chat_id': 555000,
        })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

        # RPC вызван с корректными параметрами
        assert len(calls) == 1
        assert calls[0]['function'] == 'verify_via_messenger'
        assert calls[0]['params']['p_user_id'] == TEST_USER_ID
        assert calls[0]['params']['p_provider'] == 'max'
        assert calls[0]['params']['p_messenger_uid'] == '999111'
        assert calls[0]['use_admin'] is True

        # Одноразовый токен удалён
        assert f'msg_verify:{token}' not in _mock_redis_store

    def test_expired_token_no_rpc(self, app_client, monkeypatch):
        """Неизвестный/истёкший токен → 200 ok, RPC не вызывается."""
        _, calls = _rpc_spy(monkeypatch)
        resp = app_client.post('/messenger/webhook/max', json={
            'update_type': 'bot_started',
            'payload': 'nonexistent-token-xyz',
            'user': {'user_id': 1},
            'chat_id': 2,
        })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True
        assert calls == []

    def test_ignores_other_update_types(self, app_client, monkeypatch):
        """Чужие update_type (message_created и пр.) игнорируются."""
        _, calls = _rpc_spy(monkeypatch)
        resp = app_client.post('/messenger/webhook/max', json={
            'update_type': 'message_created',
            'text': 'hello',
        })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True
        assert calls == []

    def test_empty_payload(self, app_client, monkeypatch):
        """Пустой payload → 200 ok без вызова RPC."""
        _, calls = _rpc_spy(monkeypatch)
        resp = app_client.post('/messenger/webhook/max', json={
            'update_type': 'bot_started',
            'payload': '',
        })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True
        assert calls == []

    def test_invalid_json_body(self, app_client, monkeypatch):
        """Невалидный/отсутствующий JSON → 200 ok (silent=True)."""
        _, calls = _rpc_spy(monkeypatch)
        resp = app_client.post('/messenger/webhook/max',
                               data='not-json',
                               content_type='application/json')
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True
        assert calls == []


# ── POST /messenger/webhook/telegram — ENDPOINT УДАЛЁН ─────────────

class TestTelegramWebhookRemoved:
    def test_endpoint_removed(self, app_client, monkeypatch):
        """Webhook Telegram удалён (152-ФЗ ст. 12) → 404, RPC не вызывается."""
        _, calls = _rpc_spy(monkeypatch)
        resp = app_client.post('/messenger/webhook/telegram', json={
            'message': {'text': '/start whatever', 'from': {'id': 1},
                        'chat': {'id': 2}}
        })
        assert resp.status_code == 404
        assert calls == []


# ── GET /messenger/diagnose ────────────────────────────────────────

class TestDiagnose:
    def test_requires_admin(self, app_client):
        """Гость и не-админ не имеют доступа (исправление 2026-08-16:
        эндпоинт был публичным и раскрывал статус bot-токенов)."""
        # Гость → редирект на /login
        resp = app_client.get('/messenger/diagnose', follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert '/login' in resp.headers.get('Location', '')

        # Авторизованный worker → flash «требуются права администратора» + redirect
        _login(app_client, role='worker')
        resp = app_client.get('/messenger/diagnose', follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert '/login' not in resp.headers.get('Location', '')

    def test_diagnose_no_tokens_set(self, app_client, monkeypatch):
        """Админ без bot-токена MAX в Config — token_set: False, API не дёргается.

        Токены читаются из Config (загружается при импорте из env), поэтому
        патчим атрибуты Config, а не переменные окружения.
        """
        _login(app_client, role='admin')
        monkeypatch.setattr('app.blueprints.messenger_verify.Config.MAX_BOT_TOKEN', '')
        resp = app_client.get('/messenger/diagnose')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['max']['token_set'] is False
        assert 'telegram' not in data, 'Telegram-провайдер отключён (152-ФЗ ст. 12)'


# ── Документирование CSRF/webhook-политики ─────────────────────────

class TestWebhookPolicy:
    def test_webhooks_have_no_signature_check(self, app_client, monkeypatch):
        """ДОКУМЕНТИРУЕТ ФАКТИЧЕСКОЕ ПОВЕДЕНИЕ: webhook не требует подпись/секрет.

        Любой анонимный POST (без auth-заголовков и без CSRF — webhook exempt)
        получает 200. Если будет добавлена проверка подписи — этот тест нужно
        обновить на ожидание 403 без подписи.
        """
        _, calls = _rpc_spy(monkeypatch)
        resp = app_client.post('/messenger/webhook/max',
                               json={'update_type': 'ping'})
        assert resp.status_code == 200
        assert calls == []

    def test_webhook_exempt_from_csrf(self, app_client):
        """POST webhook'а без CSRF-токена не отклоняется CSRF-middleware."""
        # CSRF-exempt: middleware.py пропускает пути /messenger/webhook/*
        resp = app_client.post('/messenger/webhook/max', json={})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True
