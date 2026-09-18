"""Unit-тесты app.services.chat_access.check_participant (B5: дедупликация chat.py).

request_fn подменяется stub'ом — реальный PostgREST не вызывается.
"""
from unittest.mock import MagicMock

import pytest

from app.services.chat_access import check_participant

WORKER_ID = '11111111-1111-1111-1111-111111111111'
EMPLOYER_ID = '22222222-2222-2222-2222-222222222222'
OUTSIDER_ID = '99999999-9999-9999-9999-999999999999'
APP_ID = '44444444-4444-4444-4444-444444444444'

APP_DATA = {
    'worker_id': WORKER_ID,
    'job_id': '33333333-3333-3333-3333-333333333333',
    'status': 'accepted',
    'job': {'employer_id': EMPLOYER_ID},
}


def _stub(payload, ok=True):
    """request_fn-заглушка, возвращающая заданный payload."""
    resp = MagicMock()
    resp.ok = ok
    resp.json = lambda: payload
    calls = []

    def request_fn(method, endpoint, **kwargs):
        calls.append((method, endpoint, kwargs))
        return resp

    request_fn.calls = calls
    return request_fn


class TestCheckParticipant:
    def test_worker_is_participant(self):
        allowed, app_data = check_participant(APP_ID, WORKER_ID, request_fn=_stub([APP_DATA]))
        assert allowed is True
        assert app_data == APP_DATA

    def test_employer_is_participant(self):
        allowed, app_data = check_participant(APP_ID, EMPLOYER_ID, request_fn=_stub([APP_DATA]))
        assert allowed is True
        assert app_data == APP_DATA

    def test_outsider_is_not_participant(self):
        """Заявка найдена, но доступа нет: (False, app_data) — не None."""
        allowed, app_data = check_participant(APP_ID, OUTSIDER_ID, request_fn=_stub([APP_DATA]))
        assert allowed is False
        assert app_data == APP_DATA  # отличие «нет доступа» от «не найдено»

    def test_application_not_found(self):
        allowed, app_data = check_participant(APP_ID, WORKER_ID, request_fn=_stub([]))
        assert allowed is False
        assert app_data is None

    def test_request_error_returns_not_found(self):
        allowed, app_data = check_participant(APP_ID, WORKER_ID, request_fn=_stub([APP_DATA], ok=False))
        assert allowed is False
        assert app_data is None

    def test_request_exception_returns_not_found(self):
        def boom(method, endpoint, **kwargs):
            raise ConnectionError('postgrest down')
        allowed, app_data = check_participant(APP_ID, WORKER_ID, request_fn=boom)
        assert allowed is False
        assert app_data is None

    def test_missing_job_join_not_participant_for_employer(self):
        """Без join jobs(employer_id) владелец задания участником не признаётся."""
        data = {'worker_id': WORKER_ID, 'job': None}
        allowed, _ = check_participant(APP_ID, EMPLOYER_ID, request_fn=_stub([data]))
        assert allowed is False
        allowed, _ = check_participant(APP_ID, WORKER_ID, request_fn=_stub([data]))
        assert allowed is True

    def test_query_contains_application_id_and_select(self):
        req = _stub([APP_DATA])
        check_participant(APP_ID, WORKER_ID, select='worker_id,job:jobs(employer_id)', request_fn=req)
        method, endpoint, _ = req.calls[0]
        assert method == 'GET'
        assert f'id=eq.{APP_ID}' in endpoint
        assert 'select=worker_id,job:jobs(employer_id)' in endpoint

    def test_default_request_fn_used_when_not_passed(self, monkeypatch):
        """Без request_fn используется app.utils.postgrest_request."""
        stub = _stub([APP_DATA])
        import app.services.chat_access as chat_access
        monkeypatch.setattr(chat_access, '_default_request', stub)
        allowed, app_data = check_participant(APP_ID, WORKER_ID)
        assert allowed is True
        assert app_data == APP_DATA


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
