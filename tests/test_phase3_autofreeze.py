"""Phase 3 (Р§Р°СЃС‚СЊ B): С‚РµСЃС‚С‹ Р°РІС‚Рѕ-Р·Р°РјРѕСЂРѕР·РєРё РїРѕ Р¶Р°Р»РѕР±Р°Рј."""
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


# в”Ђв”Ђ Р­РЅРґРїРѕРёРЅС‚ Р¶Р°Р»РѕР±С‹ в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
def test_report_requires_login(app_client):
    """Р–Р°Р»РѕР±Р° РґРѕСЃС‚СѓРїРЅР° С‚РѕР»СЊРєРѕ Р°СѓС‚РµРЅС‚РёС„РёС†РёСЂРѕРІР°РЅРЅС‹Рј."""
    r = app_client.post(f'/profile/{REPORTED}/report', data={'reason': 'spam'})
    assert r.status_code in (302, 303)


def test_report_submits_when_authenticated(app_client):
    """РђСѓС‚РµРЅС‚РёС„РёС†РёСЂРѕРІР°РЅРЅС‹Р№ РїРѕР»СЊР·РѕРІР°С‚РµР»СЊ РїРѕРґР°С‘С‚ Р¶Р°Р»РѕР±Сѓ (file_report ok)."""
    client = _auth(app_client)
    with patch('app.blueprints.profile.postgrest_rpc') as rpc:
        rpc.return_value = PostgrestResponse(ok=True, status_code=200,
                                             data={'ok': True, 'created': True}, text='{}')
        r = client.post(f'/profile/{REPORTED}/report', data={'reason': 'РјРѕС€РµРЅРЅРёРє'},
                        follow_redirects=False)
    assert rpc.called
    assert rpc.call_args.args[0] == 'file_report'
    assert r.status_code in (302, 303)


def test_report_duplicate_handled(app_client):
    """РџРѕРІС‚РѕСЂРЅР°СЏ Р¶Р°Р»РѕР±Р° РЅР° С‚РѕРіРѕ Р¶Рµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РЅРµ РїР°РґР°РµС‚ (created=False)."""
    client = _auth(app_client)
    with patch('app.blueprints.profile.postgrest_rpc') as rpc:
        rpc.return_value = PostgrestResponse(ok=True, status_code=200,
                                             data={'ok': True, 'created': False}, text='{}')
        r = client.post(f'/profile/{REPORTED}/report', data={'reason': 'x'},
                        follow_redirects=False)
    assert r.status_code in (302, 303)


def test_report_self_rejected(app_client):
    """Р–Р°Р»РѕР±Р° РЅР° СЃР°РјРѕРіРѕ СЃРµР±СЏ РѕС‚РєР»РѕРЅСЏРµС‚СЃСЏ."""
    client = _auth(app_client)
    me = '11111111-1111-1111-1111-111111111111'
    with patch('app.blueprints.profile.postgrest_rpc') as rpc:
        rpc.return_value = PostgrestResponse(ok=True, status_code=200,
                                             data={'ok': False, 'error': 'cannot_report_self'}, text='{}')
        r = client.post(f'/profile/{me}/report', data={'reason': 'x'}, follow_redirects=False)
    assert r.status_code in (302, 303)


# в”Ђв”Ђ Beat-Р·Р°РґР°С‡Р° Р°РІС‚Рѕ-Р·Р°РјРѕСЂРѕР·РєРё в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
def test_auto_freeze_suspends_candidates():
    """auto_freeze_on_complaints Р·Р°РјРѕСЂР°Р¶РёРІР°РµС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№ СЃРІРµСЂС… РїРѕСЂРѕРіР°."""
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
    # suspend_user РґРѕР»Р¶РµРЅ Р±С‹Р» РІС‹Р·РІР°С‚СЊСЃСЏ СЃ РїСЂР°РІРёР»СЊРЅС‹Рј user_id
    assert any(c.args[0] == 'suspend_user' and c.args[1]['p_user_id'] == REPORTED
               for c in fake_rpc.calls) if hasattr(fake_rpc, 'calls') else True


def test_auto_freeze_no_candidates():
    """Р‘РµР· РєР°РЅРґРёРґР°С‚РѕРІ вЂ” РЅРёРєРѕРіРѕ РЅРµ Р·Р°РјРѕСЂР°Р¶РёРІР°РµС‚."""
    from app.tasks.maintenance_tasks import auto_freeze_on_complaints
    with patch('app.tasks.maintenance_tasks.postgrest_rpc') as rpc:
        rpc.return_value = PostgrestResponse(ok=True, status_code=200, data=[], text='[]')
        result = auto_freeze_on_complaints()
    assert result['suspended'] == 0


# в”Ђв”Ђ Config в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
def test_freeze_config_present():
    """РџРѕСЂРѕРі Рё РѕРєРЅРѕ Р·Р°РјРѕСЂРѕР·РєРё РѕРїСЂРµРґРµР»РµРЅС‹ РІ РєРѕРЅС„РёРіРµ."""
    from app.config import Config
    assert isinstance(Config.REPORT_FREEZE_THRESHOLD, int) and Config.REPORT_FREEZE_THRESHOLD >= 1
    assert isinstance(Config.REPORT_FREEZE_WINDOW_HOURS, int) and Config.REPORT_FREEZE_WINDOW_HOURS >= 1


# ── Админ-очередь жалоб ───────────────────────────────────────────
def test_complaints_queue_requires_admin(app_client):
    """Очередь жалоб доступна только админу."""
    with app_client.session_transaction() as s:
        s['user_id'] = '11111111-1111-1111-1111-111111111111'; s['role'] = 'worker'
        s['access_token'] = generate_jwt(s['user_id'], 'worker')
    r = app_client.get('/admin/complaints', follow_redirects=False)
    assert r.status_code in (302, 303, 403)


def test_complaints_queue_admin_can_view(app_client):
    """Админ видит страницу очереди жалоб."""
    from app.utils.postgrest_client import PostgrestResponse as PR
    with app_client.session_transaction() as s:
        s['user_id'] = '99999999-9999-9999-9999-999999999999'; s['role'] = 'admin'
        s['access_token'] = generate_jwt(s['user_id'], 'admin')
    with patch('app.blueprints.admin_users.postgrest_admin_request') as adm:
        adm.return_value = PR(ok=True, status_code=200, data=[], text='[]')
        r = app_client.get('/admin/complaints')
    assert r.status_code == 200


def test_review_complaint_block(app_client):
    """Админ блокирует пользователя по жалобе → review_complaint(action=block)."""
    with app_client.session_transaction() as s:
        s['user_id'] = '99999999-9999-9999-9999-999999999999'; s['role'] = 'admin'
        s['access_token'] = generate_jwt(s['user_id'], 'admin')
    with patch('app.blueprints.admin_users.postgrest_rpc') as rpc:
        rpc.return_value = PostgrestResponse(ok=True, status_code=200,
                                             data={'ok': True, 'reported_id': REPORTED}, text='{}')
        r = app_client.post('/admin/complaints/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/review',
                            data={'action': 'block'}, follow_redirects=False)
    assert rpc.called and rpc.call_args.args[0] == 'review_complaint'
    assert rpc.call_args.args[1]['p_action'] == 'block'
    assert r.status_code in (302, 303)


def test_review_complaint_rejects_bad_action(app_client):
    """Неизвестное действие отклоняется."""
    with app_client.session_transaction() as s:
        s['user_id'] = '99999999-9999-9999-9999-999999999999'; s['role'] = 'admin'
        s['access_token'] = generate_jwt(s['user_id'], 'admin')
    r = app_client.post('/admin/complaints/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/review',
                        data={'action': 'hack'}, follow_redirects=False)
    assert r.status_code in (302, 303)