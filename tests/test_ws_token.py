"""T23 — WS JWT выдаётся через защищённый эндпоинт /api/ws/token.

Раньше токен встраивался в window.TRUDNIK_CONFIG каждой страницы (XSS-риск).
Теперь клиент запрашивает его через GET /api/ws/token (login_required).
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt as pyjwt


def _login(app_client, user_id='ws-user', role='worker'):
    """Установить валидную авторизованную сессию (JWT, декодируемый login_required)."""
    secret = os.environ.get('PGRST_JWT_SECRET', '')
    assert secret, 'PGRST_JWT_SECRET должен быть задан для теста'
    now = datetime.now(timezone.utc)
    token = pyjwt.encode(
        {'sub': user_id, 'role': 'authenticated', 'aud': 'authenticated',
         'app_role': role, 'user_id': user_id, 'iat': now,
         'exp': now + timedelta(hours=1), 'jti': str(uuid.uuid4())},
        secret, algorithm='HS256')
    with app_client.session_transaction() as sess:
        sess['access_token'] = token
        sess['user_id'] = user_id
        sess['role'] = role


def test_ws_token_unauthenticated_redirects(app_client):
    """Без авторизации -> redirect на login (302)."""
    resp = app_client.get('/api/ws/token')
    assert resp.status_code == 302


def test_ws_token_authenticated_returns_jwt(app_client, monkeypatch):
    """Авторизованный запрос -> JSON с короткоживущим token."""
    # Обходим X7 jti-blacklist: module-mock redis возвращает truthy MagicMock
    monkeypatch.setattr('app.utils.auth.is_jti_blacklisted', lambda jti: False)
    _login(app_client)

    resp = app_client.get('/api/ws/token')
    assert resp.status_code == 200, resp.data[:300]
    data = resp.get_json()
    assert isinstance(data, dict)
    assert 'token' in data and data['token']

    # Токен — валидный JWT, подписан WS-секретом (не PGRST_JWT_SECRET)
    from app.config import Config
    ws_secret = Config.WEBSOCKET_JWT_SECRET or Config.SECRET_KEY
    decoded = pyjwt.decode(data['token'], ws_secret,
                           algorithms=['HS256'], options={'verify_aud': False})
    assert decoded['user_id'] == 'ws-user'
    assert 'exp' in decoded and 'jti' in decoded
