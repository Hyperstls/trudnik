"""T13 — password-reset flow (публичные маршруты, без авторизации).

Маршруты /password-reset/request и /password-reset/confirm/<token> публичные
(не @login_required). Раньше соответствующих шаблонов не существовало —
посещение страницы падало с TemplateNotFound -> 500.
"""
import re

_CSRF = re.compile(rb'name="_csrf_token"')


def test_reset_request_get_renders_form(app_client):
    resp = app_client.get('/password-reset/request')
    assert resp.status_code == 200
    assert _CSRF.search(resp.data), 'форма должна содержать скрытый CSRF-токен'


def test_reset_request_post_unknown_email_redirects(app_client):
    """Email-оракул не раскрывается: всегда одинаковый redirect на /login."""
    resp = app_client.post(
        '/password-reset/request',
        data={'email': 'nobody@example.com'},
    )
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')


def test_reset_confirm_bad_token_redirects(app_client):
    """Невалидный токен -> redirect обратно к запросу сброса."""
    resp = app_client.get('/password-reset/confirm/not-a-valid-token')
    assert resp.status_code == 302
    assert 'request' in resp.headers.get('Location', '')
