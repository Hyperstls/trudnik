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


def test_reset_request_known_email_queues_celery_task(app_client, monkeypatch):
    """Письмо сброса ставится в очередь Celery (send_email_notification.delay),
    а не отправляется синхронным SMTP в request-цикле."""
    import app.blueprints.auth as auth_mod
    from app.tasks.email_tasks import send_email_notification
    from app.utils import PostgrestResponse

    queued = []
    monkeypatch.setattr(send_email_notification, 'delay',
                        lambda *a, **kw: queued.append(kw))

    def fake_admin_request(method, endpoint, **kwargs):
        return PostgrestResponse(
            ok=True, status_code=200,
            data=[{'id': '66666666-6666-6666-6666-666666666666',
                   'password_changed_at': None}],
            text='[]')

    monkeypatch.setattr(auth_mod, 'postgrest_admin_request', fake_admin_request)
    resp = app_client.post(
        '/password-reset/request',
        data={'email': 'known@example.com'},
    )
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')
    assert len(queued) == 1
    assert queued[0]['user_email'] == 'known@example.com'
    assert queued[0]['notification_type'] == 'password_reset'
    assert '/password-reset/confirm/' in queued[0]['notification_url']


def test_reset_confirm_bad_token_redirects(app_client):
    """Невалидный токен -> redirect обратно к запросу сброса."""
    resp = app_client.get('/password-reset/confirm/not-a-valid-token')
    assert resp.status_code == 302
    assert 'request' in resp.headers.get('Location', '')
