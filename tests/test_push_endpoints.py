"""HTTP-тесты push-эндпоинтов (docs/TEST_COVERAGE_MAP.md — пробел #4).

Закрывают HTTP-слой /push/* (service-слой покрыт test_c10 и test_push_service):
- GET /push/vapid-public-key (+alias) — публичный ключ из env
- POST /push/subscription — валидная подписка / мусор
- DELETE /push/subscription — без endpoint → 400
- GET /push/subscription — список подписок

PushService мокается на уровне модуля (blueprint импортирует его внутри функции).
"""

from unittest.mock import MagicMock

import pytest


def _login(client, role='worker'):
    from app.utils.auth import generate_jwt
    with client.session_transaction() as sess:
        sess['user_id'] = '44444444-4444-4444-4444-444444444444'
        sess['role'] = role
        sess['access_token'] = generate_jwt(sess['user_id'], role)


VALID_SUB = {
    'endpoint': 'https://fcm.googleapis.com/fcm/send/abc123',
    'keys': {'p256dh': 'BPublicKey...', 'auth': 'authSecret...'},
}


class TestVapidPublicKey:
    def test_returns_env_key(self, app_client, monkeypatch):
        """Публичный ключ читается из env VAPID_PUBLIC_KEY (не из Config)."""
        monkeypatch.setenv('VAPID_PUBLIC_KEY', 'test-vapid-key-123')
        resp = app_client.get('/push/vapid-public-key')
        assert resp.status_code == 200
        assert resp.get_json() == {'public_key': 'test-vapid-key-123'}

    def test_empty_key_when_not_set(self, app_client, monkeypatch):
        monkeypatch.delenv('VAPID_PUBLIC_KEY', raising=False)
        resp = app_client.get('/push/vapid-public-key')
        assert resp.status_code == 200
        assert resp.get_json()['public_key'] == ''

    def test_alias_redirects(self, app_client):
        """/notifications/push/vapid-public-key — 302 на основной путь (публично)."""
        resp = app_client.get('/notifications/push/vapid-public-key',
                              follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert '/push/vapid-public-key' in resp.headers.get('Location', '')


class TestPushSubscribe:
    def test_valid_subscription(self, app_client, monkeypatch):
        _login(app_client)
        svc = MagicMock()
        svc.save_subscription.return_value = True
        monkeypatch.setattr('app.services.push_service.PushService',
                            lambda: svc)
        resp = app_client.post('/push/subscription', json=VALID_SUB)
        assert resp.status_code == 200
        assert resp.get_json() == {'success': True}
        # save_subscription вызван с user_id из сессии и исходным payload
        args = svc.save_subscription.call_args[0]
        assert args[0] == '44444444-4444-4444-4444-444444444444'
        assert args[1] == VALID_SUB

    def test_empty_body_400(self, app_client):
        """Пустое тело → 400 (Flask отвечает HTML-страницей на пустой JSON)."""
        _login(app_client)
        resp = app_client.post('/push/subscription', data='',
                               content_type='application/json')
        assert resp.status_code == 400

    def test_guest_redirected(self, app_client):
        resp = app_client.post('/push/subscription', json=VALID_SUB,
                               follow_redirects=False)
        assert resp.status_code in (302, 303)


class TestPushUnsubscribe:
    def test_delete_ok(self, app_client, monkeypatch):
        _login(app_client)
        svc = MagicMock()
        svc.delete_subscription.return_value = True
        monkeypatch.setattr('app.services.push_service.PushService',
                            lambda: svc)
        resp = app_client.delete('/push/subscription',
                                 json={'endpoint': VALID_SUB['endpoint']})
        assert resp.status_code == 200
        assert resp.get_json() == {'success': True}

    def test_missing_endpoint_400(self, app_client):
        _login(app_client)
        resp = app_client.delete('/push/subscription', json={'endpoint': ''})
        assert resp.status_code == 400
        assert 'endpoint' in resp.get_json()['error']

    def test_empty_body_400(self, app_client):
        _login(app_client)
        resp = app_client.delete('/push/subscription', data='',
                                 content_type='application/json')
        assert resp.status_code == 400


class TestPushGetSubscriptions:
    def test_list_returns(self, app_client, monkeypatch):
        _login(app_client)
        svc = MagicMock()
        svc.get_user_subscriptions.return_value = [
            {'endpoint': VALID_SUB['endpoint']}]
        monkeypatch.setattr('app.services.push_service.PushService',
                            lambda: svc)
        resp = app_client.get('/push/subscription')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['subscriptions'] == [{'endpoint': VALID_SUB['endpoint']}]

    def test_guest_redirected(self, app_client):
        resp = app_client.get('/push/subscription', follow_redirects=False)
        assert resp.status_code in (302, 303)
