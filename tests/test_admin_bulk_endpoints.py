"""HTTP-тесты admin bulk-операций и инструментов (docs/TEST_COVERAGE_MAP.md — пробел).

Покрывают:
- POST /admin/bulk-delete-users, /admin/bulk-delete-jobs
- POST /admin/bulk-delete-skills, /admin/bulk-delete-religions (+лимит 50)
- POST /admin/skills/reorder, /admin/religions/reorder (валидация items)
- GET/POST /admin/test-user, GET/POST /admin/content/terms
- Роли: worker → redirect, гость → 302 login
"""

import pytest


UID = 'bbbbbbbb-2222-2222-2222-222222222222'
SKILL_ID = 'cccccccc-3333-3333-3333-333333333333'


def _login_admin(client):
    from app.utils.auth import generate_jwt
    with client.session_transaction() as sess:
        sess['user_id'] = UID
        sess['role'] = 'admin'
        sess['access_token'] = generate_jwt(UID, 'admin')


def _login_worker(client):
    from app.utils.auth import generate_jwt
    with client.session_transaction() as sess:
        sess['user_id'] = 'dddddddd-4444-4444-4444-444444444444'
        sess['role'] = 'worker'
        sess['access_token'] = generate_jwt(sess['user_id'], 'worker')


def _patch_admin_deps(monkeypatch, module_name):
    """Детерминированный патч PostgREST-функций в конкретном blueprint.

    Смарт-фикстура conftest патчит атрибуты пакетов — но blueprint держит
    прямые ссылки, захваченные при импорте; в полном suite порядок импортов
    даёт то оригинал, то мок (binding-time lottery). Патчим точно те имена,
    которые использует обработчик.
    """
    from app.utils import PostgrestResponse

    def ok_rpc(function_name, params, use_admin=False):
        return PostgrestResponse(ok=True, status_code=200,
                                 data={'success': True},
                                 text='{"success": true}')

    def ok_admin(method=None, url=None, **kw):
        # profiles-проверка админов: возвращаем пустой список
        return PostgrestResponse(ok=True, status_code=200, data=[],
                                 text='[]')

    monkeypatch.setattr(f'{module_name}.postgrest_rpc', ok_rpc)
    monkeypatch.setattr(f'{module_name}.postgrest_admin_request', ok_admin)


class TestBulkDeletes:
    def test_bulk_delete_users(self, app_client, monkeypatch):
        _login_admin(app_client)
        _patch_admin_deps(monkeypatch, 'app.blueprints.admin_users')
        resp = app_client.post('/admin/bulk-delete-users',
                               json={'user_ids': [UID]})
        assert resp.status_code == 200
        # RPC-мок возвращает success → deleted=1
        assert resp.get_json()['deleted'] == 1

    def test_bulk_delete_jobs(self, app_client, monkeypatch):
        _login_admin(app_client)
        _patch_admin_deps(monkeypatch, 'app.blueprints.admin_jobs')
        resp = app_client.post('/admin/bulk-delete-jobs',
                               json={'job_ids': ['eeeeeeee-5555-5555-5555-555555555555']})
        assert resp.status_code == 200
        assert resp.get_json()['deleted'] == 1

    def test_bulk_delete_skills_empty_400(self, app_client):
        _login_admin(app_client)
        resp = app_client.post('/admin/bulk-delete-skills', json={'skill_ids': []})
        assert resp.status_code == 400
        assert resp.get_json()['deleted'] == 0

    def test_bulk_delete_skills_over_50_400(self, app_client):
        _login_admin(app_client)
        resp = app_client.post('/admin/bulk-delete-skills',
                               json={'skill_ids': [SKILL_ID] * 51})
        assert resp.status_code == 400
        assert 'Max 50' in resp.get_json()['errors'][0]

    def test_bulk_delete_religions_empty_400(self, app_client):
        _login_admin(app_client)
        resp = app_client.post('/admin/bulk-delete-religions', json={'religion_ids': []})
        assert resp.status_code == 400

    def test_worker_denied(self, app_client):
        """admin_required: worker → flash + redirect (не JSON)."""
        _login_worker(app_client)
        resp = app_client.post('/admin/bulk-delete-users',
                               json={'user_ids': [UID]},
                               follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_guest_redirected(self, app_client):
        resp = app_client.post('/admin/bulk-delete-jobs', json={'job_ids': []},
                               follow_redirects=False)
        assert resp.status_code in (302, 303)


class TestReorder:
    def test_skills_reorder_ok(self, app_client):
        _login_admin(app_client)
        resp = app_client.post('/admin/skills/reorder',
                               json={'items': [{'id': SKILL_ID, 'sort_order': 1}]})
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_skills_reorder_empty_400(self, app_client):
        _login_admin(app_client)
        resp = app_client.post('/admin/skills/reorder', json={'items': []})
        assert resp.status_code == 400

    def test_religions_reorder_empty_400(self, app_client):
        _login_admin(app_client)
        resp = app_client.post('/admin/religions/reorder', json={'items': []})
        assert resp.status_code == 400


class TestAdminTools:
    def test_test_user_page(self, app_client):
        _login_admin(app_client)
        resp = app_client.get('/admin/test-user')
        assert resp.status_code == 200
        assert 'Тестовый пользователь'.lower() in resp.get_data(as_text=True).lower() \
            or 'test-user' in resp.get_data(as_text=True).lower()

    def test_content_page(self, app_client):
        _login_admin(app_client)
        resp = app_client.get('/admin/content/terms')
        assert resp.status_code == 200
