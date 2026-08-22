"""HTTP-тесты favorites API (docs/TEST_COVERAGE_MAP.md — пробел).

Покрывают:
- /api/favorites/{check,add,remove,remove-selected} (favorites.py, role_required employer)
- /api/employers/favorites/{check,add,remove} (employers.py, login_required)
- Валидация обязательных полей (worker_id/worker_ids)
- Роли: worker на favorites → redirect, гость → 302 login

⚠️ postgrest_request патчуется детерминированно в каждом тесте: смарт-фикстура
conftest патчит атрибуты ПАКЕТА app.utils, а blueprints держат прямые ссылки,
захваченные при импорте — в полном suite порядок импортов решает, попадёт ли
мок (binding-time lottery). Патчим точно то, что дёргает обработчик.
"""

import pytest


WID = '88888888-8888-8888-8888-888888888888'   # целевой трудник
EID = '99999999-9999-9999-9999-999999999999'   # целевой работодатель


def _login(client, role='employer', uid='aaaaaaaa-1111-1111-1111-111111111111'):
    from app.utils.auth import generate_jwt
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['role'] = role
        sess['access_token'] = generate_jwt(uid, role)


def _patch_postgrest(monkeypatch, module_name):
    """Патчит postgrest_request в конкретном blueprint на успешный мок."""
    from app.utils import PostgrestResponse

    def ok_request(method=None, url=None, **kw):
        # GET-проверки (check) → пустой список = не в избранном
        if (method or 'GET').upper() == 'GET':
            return PostgrestResponse(ok=True, status_code=200, data=[],
                                     text='[]')
        return PostgrestResponse(ok=True, status_code=200, data=[],
                                 text='[]')

    monkeypatch.setattr(f'{module_name}.postgrest_request', ok_request)


# ═══ /api/favorites/* (employer only) ═══

class TestFavoritesApi:
    def test_check(self, app_client, monkeypatch):
        _login(app_client, role='employer')
        _patch_postgrest(monkeypatch, 'app.blueprints.favorites')
        resp = app_client.post('/api/favorites/check', json={'worker_id': WID})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'is_favorited' in data

    def test_check_without_worker_id(self, app_client, monkeypatch):
        _login(app_client, role='employer')
        _patch_postgrest(monkeypatch, 'app.blueprints.favorites')
        resp = app_client.post('/api/favorites/check', json={})
        assert resp.get_json()['success'] is False

    def test_add(self, app_client, monkeypatch):
        _login(app_client, role='employer')
        _patch_postgrest(monkeypatch, 'app.blueprints.favorites')
        resp = app_client.post('/api/favorites/add', json={'worker_id': WID})
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_remove(self, app_client, monkeypatch):
        _login(app_client, role='employer')
        _patch_postgrest(monkeypatch, 'app.blueprints.favorites')
        resp = app_client.post('/api/favorites/remove', json={'worker_id': WID})
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_remove_selected(self, app_client, monkeypatch):
        _login(app_client, role='employer')
        _patch_postgrest(monkeypatch, 'app.blueprints.favorites')
        resp = app_client.post('/api/favorites/remove-selected',
                               json={'worker_ids': [WID]})
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_remove_selected_empty(self, app_client, monkeypatch):
        _login(app_client, role='employer')
        _patch_postgrest(monkeypatch, 'app.blueprints.favorites')
        resp = app_client.post('/api/favorites/remove-selected',
                               json={'worker_ids': []})
        assert resp.get_json()['success'] is False

    def test_worker_role_denied(self, app_client):
        """role_required('employer'): worker → redirect (не JSON success)."""
        _login(app_client, role='worker')
        resp = app_client.post('/api/favorites/check', json={'worker_id': WID},
                               follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_guest_redirected(self, app_client):
        resp = app_client.post('/api/favorites/add', json={'worker_id': WID},
                               follow_redirects=False)
        assert resp.status_code in (302, 303)


# ═══ /api/employers/favorites/* (любой авторизованный) ═══

class TestEmployerFavoritesApi:
    def test_add(self, app_client, monkeypatch):
        _login(app_client, role='worker')
        _patch_postgrest(monkeypatch, 'app.blueprints.employers')
        resp = app_client.post('/api/employers/favorites/add',
                               json={'employer_id': EID})
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_remove(self, app_client, monkeypatch):
        _login(app_client, role='worker')
        _patch_postgrest(monkeypatch, 'app.blueprints.employers')
        resp = app_client.post('/api/employers/favorites/remove',
                               json={'employer_id': EID})
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_check(self, app_client, monkeypatch):
        _login(app_client, role='worker')
        _patch_postgrest(monkeypatch, 'app.blueprints.employers')
        resp = app_client.post('/api/employers/favorites/check',
                               json={'employer_id': EID})
        assert resp.status_code == 200
        assert 'is_favorited' in resp.get_json()

    def test_guest_redirected(self, app_client):
        resp = app_client.post('/api/employers/favorites/check',
                               json={'employer_id': EID},
                               follow_redirects=False)
        assert resp.status_code in (302, 303)
