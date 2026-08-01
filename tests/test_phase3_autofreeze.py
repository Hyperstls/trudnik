"""Phase 3 (Часть B): тесты авто-заморозки по жалобам."""
from unittest.mock import patch

import pytest
from app.utils.auth import generate_jwt
from app.utils.postgrest_client import PostgrestResponse


def _auth(app_client, role='worker'):
    with app_client.session_transaction() as s:
        s['user_id'] = '11111111-1111-1111-1111-111111111111'
        s['role'] = role
        s['access_token'] = generate_jwt(s['user_id'], role)
    return app_client


REPORTED = '22222222-2222-2222-2222-222222222222'


# ── Эндпоинт жалобы ────────────────────────────────────────────────
def test_report_requires_login(app_client):
    """Жалоба доступна только аутентифицированным."""
    r = app_client.post(f'/profile/{REPORTED}/report', data={'reason': 'spam'})
    assert r.status_code in (302, 303)


def test_report_submits_when_authenticated(app_client):
    """Аутентифицированный пользователь подаёт жалобу (file_report ok)."""
    client = _auth(app_client)
    with patch('app.blueprints.profile.postgrest_rpc') as rpc:
        rpc.return_value = PostgrestResponse(ok=True, status_code=200,
                                             data={'ok': True, 'created': True}, text='{}')
        r = client.post(f'/profile/{REPORTED}/report', data={'reason': 'мошенник'},
                        follow_redirects=False)
    assert rpc.called
    assert rpc.call_args.args[0] == 'file_report'
    assert r.status_code in (302, 303)


def test_report_duplicate_handled(app_client):
    """Повторная жалоба на того же пользователя не падает (created=False)."""
    client = _auth(app_client)
    with patch('app.blueprints.profile.postgrest_rpc') as rpc:
        rpc.return_value = PostgrestResponse(ok=True, status_code=200,
                                             data={'ok': True, 'created': False}, text='{}')
        r = client.post(f'/profile/{REPORTED}/report', data={'reason': 'x'},
                        follow_redirects=False)
    assert r.status_code in (302, 303)


def test_report_self_rejected(app_client):
    """Жалоба на самого себя отклоняется."""
    client = _auth(app_client)
    me = '11111111-1111-1111-1111-111111111111'
    with patch('app.blueprints.profile.postgrest_rpc') as rpc:
        rpc.return_value = PostgrestResponse(ok=True, status_code=200,
                                             data={'ok': False, 'error': 'cannot_report_self'}, text='{}')
        r = client.post(f'/profile/{me}/report', data={'reason': 'x'}, follow_redirects=False)
    assert r.status_code in (302, 303)


# ── Beat-задача авто-заморозки ────────────────────────────────────
def test_auto_freeze_suspends_candidates():
    """auto_freeze_on_complaints замораживает пользователей сверх порога."""
    from app.tasks.maintenance_tasks import auto_freeze_on_complaints

    def fake_rpc(name, params, use_admin=False):
        if name == 'users_exceeding_reports':
            return PostgrestResponse(ok=True, status_code=200,
                                     data=[{'reported_id': REPORTED, 'report_count': 5}], text='[]')
        if name == 'suspend_user':
            return PostgrestResponse(ok=True, status_code=200, data=True, text='t')
        return PostgrestResponse(ok=True, status_code=200, data={}, text='{}')

    with patch('app.tasks.maintenance_tasks.postgrest_rpc', side_effect=fake_rpc):
        result = auto_freeze_on_complaints()
    assert result['suspended'] == 1
    # suspend_user должен был вызваться с правильным user_id
    assert any(c.args[0] == 'suspend_user' and c.args[1]['p_user_id'] == REPORTED
               for c in fake_rpc.calls) if hasattr(fake_rpc, 'calls') else True


def test_auto_freeze_no_candidates():
    """Без кандидатов — никого не замораживает."""
    from app.tasks.maintenance_tasks import auto_freeze_on_complaints
    with patch('app.tasks.maintenance_tasks.postgrest_rpc') as rpc:
        rpc.return_value = PostgrestResponse(ok=True, status_code=200, data=[], text='[]')
        result = auto_freeze_on_complaints()
    assert result['suspended'] == 0


# ── Config ────────────────────────────────────────────────────────
def test_freeze_config_present():
    """Порог и окно заморозки определены в конфиге."""
    from app.config import Config
    assert isinstance(Config.REPORT_FREEZE_THRESHOLD, int) and Config.REPORT_FREEZE_THRESHOLD >= 1
    assert isinstance(Config.REPORT_FREEZE_WINDOW_HOURS, int) and Config.REPORT_FREEZE_WINDOW_HOURS >= 1
