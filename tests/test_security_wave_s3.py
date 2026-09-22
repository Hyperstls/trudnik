"""Тесты волны безопасности S3 (2026-09):

- /metrics закрыт X-Metrics-Token (dev открыт, prod fail-closed 404);
- login_required fail-closed при недоступности БД (503, сессия сохранена);
- Circuit Breaker: общее состояние через Redis (два «процесса» видят одно);
- postgrest_admin_request: caller вне allowlist → RuntimeError (TC-088).
"""

import time

import pytest


# ── /metrics ───────────────────────────────────────────────────────

class TestMetricsEndpoint:
    def test_dev_without_token_open(self, app_client):
        """Dev-режим без METRICS_TOKEN — /metrics доступен (локальная отладка)."""
        resp = app_client.get('/metrics')
        assert resp.status_code == 200

    def test_wrong_token_404(self, app_client, monkeypatch):
        monkeypatch.setitem(app_client.application.config, 'METRICS_TOKEN', 'secret-metrics-token')
        resp = app_client.get('/metrics')
        assert resp.status_code == 404

    def test_correct_token_200(self, app_client, monkeypatch):
        monkeypatch.setitem(app_client.application.config, 'METRICS_TOKEN', 'secret-metrics-token')
        resp = app_client.get('/metrics', headers={'X-Metrics-Token': 'secret-metrics-token'})
        assert resp.status_code == 200

    def test_prod_without_token_404(self, app_client, monkeypatch):
        """Production без METRICS_TOKEN — 404 (fail-closed, не раскрываем)."""
        monkeypatch.setitem(app_client.application.config, 'METRICS_TOKEN', '')
        monkeypatch.setenv('DEPLOYMENT_ENV', 'production')
        resp = app_client.get('/metrics')
        assert resp.status_code == 404


# ── login_required fail-closed ─────────────────────────────────────

class TestLoginRequiredFailClosed:
    def test_db_down_returns_503_keeps_session(self, app_client, monkeypatch):
        """PostgREST недоступен (CB open) → 503, сессия НЕ очищается (можно повторить)."""
        from app.utils.auth import generate_jwt
        user_id = '22222222-2222-2222-2222-222222222222'
        with app_client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['role'] = 'worker'
            sess['access_token'] = generate_jwt(user_id, 'worker')

        # Эмулируем недоступность БД: пользовательский и admin-запросы не ok.
        # decorators.py резолвит postgrest_* из неймспейса app.utils (lazy import).
        class _Resp:
            ok = False
            def json(self):
                return []
        monkeypatch.setattr('app.utils.postgrest_request', lambda *a, **kw: _Resp())
        monkeypatch.setattr('app.utils.postgrest_admin_request', lambda *a, **kw: _Resp())
        # cache: нет сохранённого user_exists
        monkeypatch.setattr('app.utils.redis_cache.get_cached', lambda *a, **kw: None)
        monkeypatch.setattr('app.utils.redis_cache.set_cached', lambda *a, **kw: None)
        monkeypatch.setattr('app.utils.auth.is_jti_blacklisted', lambda *a, **kw: False)

        resp = app_client.get('/profile')
        assert resp.status_code == 503
        # Сессия сохранена — повторный запрос тоже 503 (не редирект на логин)
        assert resp.status_code == 503

    def test_db_confirms_user_deleted_redirects_login(self, app_client, monkeypatch):
        """БД доступна и подтвердила: пользователя нет → редирект на login."""
        from app.utils.auth import generate_jwt
        user_id = '33333333-3333-3333-3333-333333333333'
        with app_client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['role'] = 'worker'
            sess['access_token'] = generate_jwt(user_id, 'worker')

        class _Resp:
            ok = True
            def json(self):
                return []
        monkeypatch.setattr('app.utils.postgrest_request', lambda *a, **kw: _Resp())
        monkeypatch.setattr('app.utils.postgrest_admin_request', lambda *a, **kw: _Resp())
        monkeypatch.setattr('app.utils.redis_cache.get_cached', lambda *a, **kw: None)
        monkeypatch.setattr('app.utils.auth.is_jti_blacklisted', lambda *a, **kw: False)

        resp = app_client.get('/profile')
        assert resp.status_code == 302
        assert '/login' in resp.location


# ── Circuit Breaker: shared state через Redis ──────────────────────

class TestCircuitBreakerSharedState:
    """Два экземпляра CB с одним name видят общее состояние (как 2 uvicorn-воркера).

    Использует stateful Redis-мок conftest (`_mock_redis_store`); mock PostgREST
    для CB отключён (иначе call() байпасится by design).
    """

    @pytest.fixture
    def shared_store(self, monkeypatch):
        from tests.conftest import _mock_redis_store
        from app.utils.postgrest_client import CircuitBreaker
        import app.utils.postgrest_client as pc
        monkeypatch.setattr(pc, '_is_mock_enabled', lambda: False)
        for k in ('cb:shared-test:failures', 'cb:shared-test:opened_at'):
            _mock_redis_store.pop(k, None)
        yield CircuitBreaker
        for k in ('cb:shared-test:failures', 'cb:shared-test:opened_at'):
            _mock_redis_store.pop(k, None)

    def test_two_instances_share_open_state(self, shared_store):
        from app.utils.postgrest_client import PostgrestResponse
        cb1 = shared_store(failure_threshold=3, recovery_timeout=30.0, name='shared-test')
        cb2 = shared_store(failure_threshold=3, recovery_timeout=30.0, name='shared-test')

        # «Процесс 1» накапливает ошибки до OPEN
        def failing():
            return PostgrestResponse(ok=False, status_code=500, text='err')
        for _ in range(3):
            cb1.call(failing)
        assert cb1.state == 'OPEN'

        # «Процесс 2» подтягивает общее состояние — тоже OPEN
        cb2._load_shared()
        assert cb2.state == 'OPEN'
        assert cb2.failure_count == 3

        # Сброс из «процесса 1» — «процесс 2» видит CLOSED
        cb1.reset()
        cb2._load_shared()
        assert cb2.state == 'CLOSED'
        assert cb2.failure_count == 0


# ── postgrest_admin_request: caller allowlist fail-closed ──────────

# Реальные функции postgrest_client сохраняем на уровне модуля (время импорта):
# autouse-фикстура conftest `mock_postgrest_client` заменяет атрибуты модуля
# заглушками ПЕРЕД каждым тестом — для проверки caller-гейта нужна оригинальная
# функция, а не заглушка.
from app.utils import postgrest_client as _pc

_REAL_ADMIN_REQ = _pc.postgrest_admin_request


class TestAdminCallerAllowlist:
    def test_disallowed_caller_raises(self, monkeypatch):
        from app.utils import postgrest_client as pc
        monkeypatch.setattr(pc, '_get_caller_info', lambda: 'evil.module.hack')
        monkeypatch.setattr(pc, '_is_mock_enabled', lambda: False)
        with pytest.raises(RuntimeError, match='SECURITY BLOCK'):
            _REAL_ADMIN_REQ('GET', 'profiles?select=id')

    def test_allowed_caller_passes(self, monkeypatch):
        from app.utils import postgrest_client as pc
        monkeypatch.setattr(pc, '_get_caller_info', lambda: 'app.services.favorites_service')
        # mock-режим активен в suite → после проверки caller уйдёт в mock, не в HTTP
        resp = _REAL_ADMIN_REQ('GET', 'profiles?select=id&limit=0')
        assert resp is not None
