"""HTTP-тесты прочих пробелов (docs/TEST_COVERAGE_MAP.md).

Покрывают:
- POST /unapply-selected (без job_ids → flash; с ids → redirect)
- POST /profile/delete-photo (login → redirect)
- GET /profile/export-data (login → 200, JSON-структура)
- GET /health/circuit-breaker, /health/postgrest (200/503 с моками)
"""

import pytest


UID = 'ffffffff-6666-6666-6666-666666666666'


def _login(client, role='worker'):
    from app.utils.auth import generate_jwt
    with client.session_transaction() as sess:
        sess['user_id'] = UID
        sess['role'] = role
        sess['access_token'] = generate_jwt(UID, role)


class TestUnapplySelected:
    def test_no_ids_flash_redirect(self, app_client):
        """Без job_ids → flash «Не выбрано ни одного задания» + redirect на /."""
        _login(app_client)
        resp = app_client.post('/unapply-selected', data={},
                               follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_with_ids_redirects(self, app_client):
        """С ids → цикл по job_ids → redirect на / (мок PostgREST пуст)."""
        _login(app_client)
        resp = app_client.post(
            '/unapply-selected',
            data={'job_ids': ['11111111-aaaa-aaaa-aaaa-111111111111']},
            follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_guest_redirected(self, app_client):
        resp = app_client.post('/unapply-selected', data={},
                               follow_redirects=False)
        assert resp.status_code in (302, 303)


class TestProfileMisc:
    def test_delete_photo(self, app_client):
        """Удаление фото (файла нет) → redirect, не 500."""
        _login(app_client)
        resp = app_client.post('/profile/delete-photo', data={},
                               follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_export_data(self, app_client):
        """Экспорт ПДн (152-ФЗ): авторизован → JSON-ответ (или redirect), не 500."""
        _login(app_client)
        resp = app_client.get('/profile/export-data',
                              follow_redirects=False)
        assert resp.status_code in (200, 302, 303)
        if resp.status_code == 200:
            assert resp.get_json() is not None or resp.data

    def test_guest_denied(self, app_client):
        for path in ('/profile/delete-photo', '/profile/export-data'):
            resp = app_client.post(path, data={}, follow_redirects=False) \
                if 'delete' in path else app_client.get(path, follow_redirects=False)
            assert resp.status_code in (302, 303), path


class TestHealthSubroutes:
    def test_circuit_breaker(self, app_client):
        """Состояние обоих CB: 200, поля state/failure_count."""
        resp = app_client.get('/health/circuit-breaker')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'admin' in data and 'postgrest' in data
        for cb in data.values():
            assert cb['state'] in ('CLOSED', 'HALF_OPEN', 'OPEN')

    def test_postgrest_health_ok(self, app_client, monkeypatch):
        import requests as req_lib

        class _FakeResp:
            ok = True
            status_code = 200
            text = 'OK'

        monkeypatch.setattr(req_lib, 'get', lambda *a, **kw: _FakeResp())
        resp = app_client.get('/health/postgrest')
        assert resp.status_code == 200

    def test_postgrest_health_down(self, app_client, monkeypatch):
        import requests as req_lib

        def _raise(*a, **kw):
            raise req_lib.RequestException('refused')

        monkeypatch.setattr(req_lib, 'get', _raise)
        resp = app_client.get('/health/postgrest')
        assert resp.status_code in (502, 503, 504)
