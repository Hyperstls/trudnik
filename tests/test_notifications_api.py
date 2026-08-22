"""HTTP-тесты notifications API (docs/TEST_COVERAGE_MAP.md — пробел).

Покрывают:
- GET /api/notifications/unread-count, GET /api/notifications
- POST /api/notifications/read-all, delete, delete-all
- POST /notification/<id>/read (redirect-вариант)
- GET/POST /api/notifications/preferences (валидация типа/канала)
- Гость → redirect на /login

notification_service-функции мокаются на уровне модуля импорта в blueprint.
"""

from unittest.mock import MagicMock

import pytest


UID = '55555555-5555-5555-5555-555555555555'


def _login(client, role='worker'):
    from app.utils.auth import generate_jwt
    with client.session_transaction() as sess:
        sess['user_id'] = UID
        sess['role'] = role
        sess['access_token'] = generate_jwt(UID, role)


class TestNotificationsApi:
    def test_unread_count(self, app_client, monkeypatch):
        _login(app_client)
        monkeypatch.setattr(
            'app.blueprints.notifications.get_unread_count',
            lambda uid: 3)
        resp = app_client.get('/api/notifications/unread-count')
        assert resp.status_code == 200
        assert resp.get_json() == {'unread': 3}

    def test_list_notifications(self, app_client, monkeypatch):
        _login(app_client)
        monkeypatch.setattr(
            'app.blueprints.notifications.get_notifications',
            lambda uid, page, per_page: {'notifications': [], 'total': 0,
                                         'page': page, 'per_page': per_page})
        resp = app_client.get('/api/notifications?page=2&per_page=10')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['page'] == 2
        assert data['per_page'] == 10

    def test_read_all(self, app_client, monkeypatch):
        _login(app_client)
        spy = MagicMock()
        monkeypatch.setattr('app.blueprints.notifications.mark_all_read', spy)
        resp = app_client.post('/api/notifications/read-all')
        assert resp.status_code == 200
        assert resp.get_json() == {'success': True}
        spy.assert_called_once_with(UID)

    def test_delete_notification(self, app_client, monkeypatch):
        """DELETE через POST-роут: admin_request мокается детерминированно
        (в полном suite binding postgrest_admin_request нестабилен — см.
        заголовок test_favorites_api.py)."""
        from app.utils import PostgrestResponse

        def ok_admin(method=None, url=None, **kw):
            return PostgrestResponse(ok=True, status_code=204, data=[],
                                     text='')

        monkeypatch.setattr('app.blueprints.notifications.postgrest_admin_request',
                            ok_admin)
        _login(app_client)
        nid = '66666666-6666-6666-6666-666666666666'
        resp = app_client.post(f'/api/notifications/{nid}/delete')
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_delete_notification_bad_uuid(self, app_client):
        """Невалидный UUID → validate_uuid: flash + redirect (не 400/500)."""
        _login(app_client)
        resp = app_client.post('/api/notifications/not-a-uuid/delete',
                               follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_delete_all(self, app_client):
        _login(app_client)
        resp = app_client.post('/api/notifications/delete-all')
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_mark_read_redirect(self, app_client, monkeypatch):
        _login(app_client)
        spy = MagicMock()
        monkeypatch.setattr('app.blueprints.notifications.mark_read', spy)
        nid = '77777777-7777-7777-7777-777777777777'
        resp = app_client.post(f'/notification/{nid}/read',
                               follow_redirects=False)
        assert resp.status_code in (302, 303)
        spy.assert_called_once_with(nid, user_id=UID)

    def test_guest_redirected(self, app_client):
        for path in ('/api/notifications/unread-count', '/api/notifications'):
            resp = app_client.get(path, follow_redirects=False)
            assert resp.status_code in (302, 303), path


class TestNotificationPreferences:
    def test_get_preferences(self, app_client, monkeypatch):
        _login(app_client)
        monkeypatch.setattr(
            'app.services.notification_service.get_user_prefs',
            lambda uid: {})
        resp = app_client.get('/api/notifications/preferences')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        # все типы с дефолтами + каналы
        assert 'preferences' in data and 'channels' in data
        assert set(data['channels']) == {'email_enabled', 'push_enabled',
                                         'in_app_enabled'}

    def test_update_channel_ok(self, app_client, monkeypatch):
        """PATCH preferences: admin_request мокается (детерминированно)."""
        from app.utils import PostgrestResponse

        def ok_admin(method=None, url=None, **kw):
            return PostgrestResponse(ok=True, status_code=204, data=[],
                                     text='')

        monkeypatch.setattr('app.blueprints.notifications.postgrest_admin_request',
                            ok_admin)
        _login(app_client)
        resp = app_client.post('/api/notifications/preferences',
                               json={'type': 'email_enabled', 'enabled': False})
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_update_unknown_type_400(self, app_client):
        _login(app_client)
        resp = app_client.post('/api/notifications/preferences',
                               json={'type': 'no_such_type', 'enabled': True})
        assert resp.status_code == 400

    def test_update_non_bool_400(self, app_client):
        _login(app_client)
        resp = app_client.post('/api/notifications/preferences',
                               json={'type': 'email_enabled', 'enabled': 'yes'})
        assert resp.status_code == 400
