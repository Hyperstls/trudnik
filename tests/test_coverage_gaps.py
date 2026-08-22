"""Тесты пробелов покрытия (docs/TEST_COVERAGE_MAP.md, топ-5 рисков).

Закрывают ранее непокрытые pytest-набором маршруты:
- /uploads/avatars/<f> и /uploads/verification-docs/<f> (path traversal, IDOR)
- /verify-email/<token> и /verify-email/resend (auth-флоу)
- публичные страницы: /terms, /privacy, /pricing, /faq, /robots.txt
- /ready и /metrics (healthcheck Dockerfile + Prometheus)
- /profile/delete-account (доступ без сессии)

Все запросы идут через app_client (mock PostgREST, TESTING-режим).
"""

import uuid

import pytest


OWNER_ID = '22222222-2222-2222-2222-222222222222'
OTHER_ID = '33333333-3333-3333-3333-333333333333'


def _login(client, user_id=OTHER_ID, role='worker'):
    """Авторизовать пользователя через сессию."""
    from app.utils.auth import generate_jwt
    with client.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['role'] = role
        sess['access_token'] = generate_jwt(user_id, role)


@pytest.fixture()
def uploads_folder(app_client, tmp_path):
    """Подменяет UPLOAD_FOLDER на tmp_path с тестовым файлом аватара и документа."""
    import os
    (tmp_path / 'avatars').mkdir(exist_ok=True)
    (tmp_path / 'verification-docs' / 'verification' / OWNER_ID).mkdir(parents=True, exist_ok=True)
    (tmp_path / 'avatars' / 'test-avatar.jpg').write_bytes(b'\xff\xd8\xff\xe0fakejpg')
    doc = tmp_path / 'verification-docs' / 'verification' / OWNER_ID / 'doc.pdf'
    doc.write_bytes(b'%PDF-1.4 fake')
    app_client.application.config['UPLOAD_FOLDER'] = str(tmp_path)
    return tmp_path


# ═══════════════════════════════════════════════════════════════
# /uploads/* — path traversal + IDOR
# ═══════════════════════════════════════════════════════════════

class TestUploadsSecurity:
    def test_avatar_public_served(self, app_client, uploads_folder):
        """Аватары публичны: существующий файл → 200 с nosniff."""
        resp = app_client.get('/uploads/avatars/test-avatar.jpg')
        assert resp.status_code == 200
        assert resp.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_avatar_missing_404_not_500(self, app_client, uploads_folder):
        """Несуществующий аватар → 404, не 500."""
        resp = app_client.get('/uploads/avatars/nope.jpg')
        assert resp.status_code == 404

    def test_avatar_path_traversal_blocked(self, app_client, uploads_folder):
        """Path traversal в имени аватара → 404 (safe_join), не 500 и не содержимое."""
        for malicious in (
            '..%2F..%2F..%2Fconfig.py',
            '..%5C..%5Cconfig.py',
            'sub/../../config.py',
        ):
            resp = app_client.get(f'/uploads/avatars/{malicious}')
            assert resp.status_code in (404, 400), f'{malicious}: {resp.status_code}'
            assert b'SECRET' not in resp.data

    def test_verification_doc_guest_redirect(self, app_client, uploads_folder):
        """Гость за документом верификации → redirect на /login (не отдаём файл)."""
        resp = app_client.get(
            f'/uploads/verification-docs/verification/{OWNER_ID}/doc.pdf',
            follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_verification_doc_other_user_forbidden(self, app_client, uploads_folder):
        """IDOR: авторизованный НЕ-владелец (и не админ) → 403, файл не отдан."""
        _login(app_client, user_id=OTHER_ID, role='worker')
        resp = app_client.get(
            f'/uploads/verification-docs/verification/{OWNER_ID}/doc.pdf')
        assert resp.status_code == 403

    def test_verification_doc_owner_served(self, app_client, uploads_folder):
        """Владелец получает свой документ → 200 + nosniff + as_attachment."""
        _login(app_client, user_id=OWNER_ID, role='employer')
        resp = app_client.get(
            f'/uploads/verification-docs/verification/{OWNER_ID}/doc.pdf')
        assert resp.status_code == 200
        assert resp.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_verification_doc_traversal_404(self, app_client, uploads_folder):
        """Traversal в пути документа → 404/400, не 500."""
        _login(app_client, user_id=OWNER_ID, role='employer')
        resp = app_client.get(
            '/uploads/verification-docs/verification/..%2F..%2F..%2Fdoc.pdf')
        assert resp.status_code in (404, 400, 403)


# ═══════════════════════════════════════════════════════════════
# /verify-email — auth-флоу
# ═══════════════════════════════════════════════════════════════

class TestVerifyEmailFlow:
    def test_invalid_token_redirects_to_register(self, app_client):
        """Невалидный/истёкший токен → flash + redirect на /register."""
        resp = app_client.get('/verify-email/not-a-real-token', follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert '/register' in resp.headers.get('Location', '')

    def test_valid_token_marks_verified(self, app_client, monkeypatch):
        """Валидный токен → PATCH profiles.email_verified=True + redirect на /login."""
        calls = []

        def fake_verify(token):
            return 'user@example.com'

        monkeypatch.setattr(
            'app.blueprints.auth._verify_email_verification_token', fake_verify)

        from app.utils import PostgrestResponse

        def spy_admin(method=None, url=None, **kw):
            calls.append({'method': method, 'url': url, 'json': kw.get('json')})
            return PostgrestResponse(ok=True, status_code=204, data=[], text='')

        monkeypatch.setattr('app.blueprints.auth.postgrest_admin_request', spy_admin)

        resp = app_client.get('/verify-email/good-token', follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert '/login' in resp.headers.get('Location', '')
        assert len(calls) == 1
        assert calls[0]['method'] == 'PATCH'
        assert 'email=eq.user@example.com' in calls[0]['url']
        assert calls[0]['json'] == {'email_verified': True}

    def test_resend_page_renders(self, app_client):
        """GET /verify-email/resend → 200 HTML."""
        resp = app_client.get('/verify-email/resend')
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════
# Публичкие страницы и системные эндпоинты
# ═══════════════════════════════════════════════════════════════

class TestPublicPages:
    @pytest.mark.parametrize('path,marker', [
        ('/terms', 'условия'),
        ('/privacy', 'конфиденциальн'),
        ('/pricing', ''),
        ('/faq', 'Вопросы и ответы'),
    ])
    def test_public_page_200(self, app_client, path, marker):
        resp = app_client.get(path)
        assert resp.status_code == 200
        if marker:
            assert marker.lower() in resp.get_data(as_text=True).lower()

    def test_robots_txt(self, app_client):
        resp = app_client.get('/robots.txt')
        assert resp.status_code == 200
        assert 'User-agent' in resp.get_data(as_text=True)


class TestSystemEndpoints:
    def test_ready_200_json(self, app_client, monkeypatch):
        """/ready — Dockerfile HEALTHCHECK прода.

        /ready делает РЕАЛЬНЫЕ проверки зависимостей (requests.get к PostgREST +
        Redis ping), минуя mock PostgREST-клиента. Поэтому мокаем оба вызова:
        при живых зависимостях — 200 {'status':'ready'}.
        """
        import requests as req_lib

        class _FakeResp:
            ok = True
            status_code = 200

        monkeypatch.setattr(req_lib, 'get', lambda *a, **kw: _FakeResp())

        from unittest.mock import MagicMock
        fake_redis = MagicMock()
        fake_redis.ping.return_value = True
        # ready_check импортирует get_redis_client внутри функции — патчим источник
        import app.utils.redis_client as rc_mod
        monkeypatch.setattr(rc_mod, 'get_redis_client', lambda: fake_redis)

        resp = app_client.get('/ready')
        assert resp.status_code == 200
        assert resp.get_json() == {'status': 'ready'}

    def test_ready_503_when_postgrest_down(self, app_client, monkeypatch):
        """/ready при недоступном PostgREST → 503 с reason (защита от ложного трафика)."""
        import requests as req_lib

        def _raise(*a, **kw):
            raise req_lib.RequestException('connection refused')

        monkeypatch.setattr(req_lib, 'get', _raise)
        resp = app_client.get('/ready')
        assert resp.status_code == 503
        assert 'PostgREST' in resp.get_json().get('reason', '')

    def test_metrics_prometheus(self, app_client):
        """/metrics — Prometheus: 200, содержит базовые trudnik_* метрики."""
        resp = app_client.get('/metrics')
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'trudnik_http_requests_total' in body or 'trudnik_circuit_breaker_state' in body


# ═══════════════════════════════════════════════════════════════
# /profile/delete-account — 152-ФЗ, деструктивная операция
# ═══════════════════════════════════════════════════════════════

class TestDeleteAccountAccess:
    def test_guest_redirected_to_login(self, app_client):
        """Гость не может удалить аккаунт → redirect на /login (152-ФЗ защита)."""
        resp = app_client.post('/profile/delete-account',
                               data={'confirm': 'DELETE'}, follow_redirects=False)
        assert resp.status_code in (302, 303)
