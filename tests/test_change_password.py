"""T20 — change-password читает поле `current_password` (раньше `old_password`).

Регрессия: profile.py читал request.form.get('old_password'), а форма шлёт
`current_password` -> поле всегда было пустым -> flash «Укажите текущий пароль»
на любой попытке сменить пароль.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt as pyjwt


def _login(app_client, user_id='pw-user', role='worker'):
    secret = os.environ.get('PGRST_JWT_SECRET', '')
    assert secret
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


def _flashes(app_client):
    with app_client.session_transaction() as sess:
        return ' '.join(msg for _cat, msg in sess.get('_flashes', []))


def test_empty_current_password_flashes_prompt(app_client, monkeypatch):
    monkeypatch.setattr('app.utils.auth.is_jti_blacklisted', lambda jti: False)
    _login(app_client)
    resp = app_client.post('/profile/change-password', data={
        'current_password': '', 'new_password': 'NewPass1!', 'confirm_password': 'NewPass1!'})  # pragma: allowlist secret
    assert resp.status_code == 302
    assert 'Укажите текущий пароль' in _flashes(app_client)


def test_provided_current_password_skips_prompt(app_client, monkeypatch):
    """Если current_password передан — flash «Укажите текущий пароль» НЕ появляется
    (доказывает, что читается именно current_password, а не old_password)."""
    monkeypatch.setattr('app.utils.auth.is_jti_blacklisted', lambda jti: False)
    _login(app_client)
    resp = app_client.post('/profile/change-password', data={
        'current_password': 'something', 'new_password': 'NewPass1!', 'confirm_password': 'NewPass1!'})  # pragma: allowlist secret
    assert resp.status_code == 302
    assert 'Укажите текущий пароль' not in _flashes(app_client)
