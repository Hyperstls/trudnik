"""HTTP-тесты JSON-эндпоинтов apply/unapply и AJAX-вариантов bulk-действий (B4).

Покрывают:
- POST /api/jobs/<job_id>/apply — JSON-обёртка над apply_job_atomic
  (успех 200, duplicate 409 с my_app_status, blacklisted 403, RPC missing 503)
- POST /api/jobs/<job_id>/unapply — JSON-обёртка над withdraw_application_atomic
  (успех 200, not_found 404, already_withdrawn 409)
- /apply-selected и /unapply-selected с X-Requested-With → JSON-сводка
  с per-job списками (applied_job_ids / withdrawn_job_ids)
- /my-jobs/action с X-Requested-With → JSON с per-job результатами
- GET /?filter=new|applied — серверные фильтры каталога (B4)

Стиль — как в test_favorites_api.py / test_c4_apply_job_race.py: postgrest
патчится в неймспейсе блюпринта (binding-time lottery, см. test_favorites_api).
"""
from unittest.mock import MagicMock, patch

import pytest

JOB_ID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
JOB2_ID = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
APP_ID = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
EMPLOYER_ID = '99999999-9999-9999-9999-999999999999'
WORKER_ID = '33333333-3333-3333-3333-333333333333'


def _login(client, role='worker', uid=WORKER_ID):
    from app.utils.auth import generate_jwt
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['role'] = role
        sess['_csrf_token'] = 'test-csrf-token'
        sess['access_token'] = generate_jwt(uid, role)


def _resp(data, ok=True, status_code=200):
    return MagicMock(ok=ok, status_code=status_code, json=lambda: data, text=str(data))


# ═══ POST /api/jobs/<job_id>/apply ═══

class TestApiApplyJob:
    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.applications.enqueue_notification', return_value=True)
    @patch('app.blueprints.applications.postgrest_rpc')
    def test_apply_success(self, mock_rpc, mock_notify, mock_bl, app_client):
        """Успешный отклик: 200 + {ok, my_app_status, application_id}."""
        _login(app_client)
        mock_rpc.return_value = _resp({
            'success': True, 'application_id': APP_ID, 'employer_id': EMPLOYER_ID})

        resp = app_client.post(f'/api/jobs/{JOB_ID}/apply',
                               headers={'X-CSRF-Token': 'test-csrf-token'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['my_app_status'] == 'pending'
        assert data['application_id'] == APP_ID

        args, _ = mock_rpc.call_args
        assert args[0] == 'apply_job_atomic'
        assert args[1]['p_job_id'] == JOB_ID
        assert args[1]['p_worker_id'] == WORKER_ID
        mock_notify.assert_called_once()

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.applications.postgrest_request')
    @patch('app.blueprints.applications.postgrest_rpc')
    def test_apply_duplicate_409_with_status(self, mock_rpc, mock_req, mock_bl, app_client):
        """Duplicate (гонка): 409 + текущий отклик для самовосстановления UI."""
        _login(app_client)
        mock_rpc.return_value = _resp({
            'success': False, 'code': 'duplicate', 'error': 'duplicate'})
        mock_req.return_value = _resp([{'id': APP_ID, 'status': 'pending'}])

        resp = app_client.post(f'/api/jobs/{JOB_ID}/apply',
                               headers={'X-CSRF-Token': 'test-csrf-token'})
        assert resp.status_code == 409
        data = resp.get_json()
        assert data['ok'] is False
        assert data['code'] == 'duplicate'
        assert data['my_app_status'] == 'pending'
        assert data['application_id'] == APP_ID
        # Сырое 'duplicate' от RPC заменено человекочитаемым текстом
        assert data['error'] != 'duplicate'

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.applications.postgrest_rpc')
    def test_apply_blacklisted_403(self, mock_rpc, mock_bl, app_client):
        _login(app_client)
        mock_rpc.return_value = _resp({
            'success': False, 'code': 'blacklisted', 'error': 'blacklisted'})

        resp = app_client.post(f'/api/jobs/{JOB_ID}/apply',
                               headers={'X-CSRF-Token': 'test-csrf-token'})
        assert resp.status_code == 403
        assert resp.get_json()['ok'] is False

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.applications.postgrest_rpc')
    def test_apply_job_not_open_409(self, mock_rpc, mock_bl, app_client):
        _login(app_client)
        mock_rpc.return_value = _resp({
            'success': False, 'code': 'job_not_open', 'error': 'Задание недоступно'})

        resp = app_client.post(f'/api/jobs/{JOB_ID}/apply',
                               headers={'X-CSRF-Token': 'test-csrf-token'})
        assert resp.status_code == 409
        assert resp.get_json()['ok'] is False

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.applications.postgrest_rpc')
    def test_apply_rpc_missing_503(self, mock_rpc, mock_bl, app_client):
        _login(app_client)
        mock_rpc.return_value = _resp([], ok=False, status_code=404)

        resp = app_client.post(f'/api/jobs/{JOB_ID}/apply',
                               headers={'X-CSRF-Token': 'test-csrf-token'})
        assert resp.status_code == 503
        assert resp.get_json()['ok'] is False

    def test_apply_guest_redirected(self, app_client):
        resp = app_client.post(f'/api/jobs/{JOB_ID}/apply', follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_apply_invalid_uuid_redirects(self, app_client):
        _login(app_client)
        resp = app_client.post('/api/jobs/not-a-uuid/apply', follow_redirects=False)
        assert resp.status_code in (302, 303)


# ═══ POST /api/jobs/<job_id>/unapply ═══

class TestApiUnapplyJob:
    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.services.application_service.postgrest_rpc')
    @patch('app.blueprints.applications.postgrest_request')
    def test_unapply_success(self, mock_req, mock_rpc, mock_bl, app_client):
        """Успешный отзыв: 200 + {ok, my_app_status: null}."""
        _login(app_client)
        mock_req.return_value = _resp([{'id': APP_ID, 'status': 'pending'}])
        mock_rpc.return_value = _resp({
            'success': True, 'message': 'Заявка отозвана', 'new_status': 'withdrawn',
            'job_id': JOB_ID, 'employer_id': EMPLOYER_ID})

        resp = app_client.post(f'/api/jobs/{JOB_ID}/unapply',
                               headers={'X-CSRF-Token': 'test-csrf-token'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['my_app_status'] is None
        assert data['application_id'] == APP_ID

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.applications.postgrest_request')
    def test_unapply_not_found_404(self, mock_req, mock_bl, app_client):
        _login(app_client)
        mock_req.return_value = _resp([])

        resp = app_client.post(f'/api/jobs/{JOB_ID}/unapply',
                               headers={'X-CSRF-Token': 'test-csrf-token'})
        assert resp.status_code == 404
        assert resp.get_json()['ok'] is False

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.applications.postgrest_request')
    def test_unapply_already_withdrawn_409(self, mock_req, mock_bl, app_client):
        _login(app_client)
        mock_req.return_value = _resp([{'id': APP_ID, 'status': 'withdrawn'}])

        resp = app_client.post(f'/api/jobs/{JOB_ID}/unapply',
                               headers={'X-CSRF-Token': 'test-csrf-token'})
        assert resp.status_code == 409
        data = resp.get_json()
        assert data['ok'] is False
        assert data['code'] == 'already_withdrawn'

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.services.application_service.postgrest_rpc')
    @patch('app.blueprints.applications.postgrest_request')
    def test_unapply_window_conflict_409(self, mock_req, mock_rpc, mock_bl, app_client):
        """Отзыв accepted менее чем за 12ч до начала — 409."""
        _login(app_client)
        mock_req.return_value = _resp([{'id': APP_ID, 'status': 'accepted'}])
        mock_rpc.return_value = _resp({
            'success': False, 'code': 'too_close_to_start',
            'error': 'Нельзя отозвать менее чем за 12 часов до начала'})

        resp = app_client.post(f'/api/jobs/{JOB_ID}/unapply',
                               headers={'X-CSRF-Token': 'test-csrf-token'})
        assert resp.status_code == 409
        assert resp.get_json()['ok'] is False

    def test_unapply_guest_redirected(self, app_client):
        resp = app_client.post(f'/api/jobs/{JOB_ID}/unapply', follow_redirects=False)
        assert resp.status_code in (302, 303)


# ═══ /apply-selected и /unapply-selected (AJAX) ═══

class TestSelectedAjax:
    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.applications.enqueue_notification', return_value=True)
    @patch('app.blueprints.applications.postgrest_rpc')
    def test_apply_selected_json(self, mock_rpc, mock_notify, mock_bl, app_client):
        """AJAX-вариант: JSON со списком успешных job_id, без redirect."""
        _login(app_client)
        mock_rpc.return_value = _resp({
            'success': True, 'application_id': APP_ID, 'employer_id': EMPLOYER_ID})

        resp = app_client.post('/apply-selected',
                               data={'job_ids': [JOB_ID, JOB2_ID]},
                               headers={'X-Requested-With': 'XMLHttpRequest'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['applied'] == 2
        assert sorted(data['applied_job_ids']) == sorted([JOB_ID, JOB2_ID])

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.services.application_service.postgrest_rpc')
    @patch('app.blueprints.applications.postgrest_request')
    def test_unapply_selected_json(self, mock_req, mock_rpc, mock_bl, app_client):
        _login(app_client)
        mock_req.return_value = _resp([{'id': APP_ID}])
        mock_rpc.return_value = _resp({
            'success': True, 'message': 'Заявка отозвана', 'new_status': 'withdrawn'})

        resp = app_client.post('/unapply-selected',
                               data={'job_ids': [JOB_ID]},
                               headers={'X-Requested-With': 'XMLHttpRequest'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['withdrawn'] == 1
        assert data['withdrawn_job_ids'] == [JOB_ID]

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.applications.enqueue_notification', return_value=True)
    @patch('app.blueprints.applications.postgrest_rpc')
    def test_apply_selected_form_still_redirects(self, mock_rpc, mock_notify, mock_bl, app_client):
        """Без X-Requested-With — прежнее flash+redirect поведение (noscript)."""
        _login(app_client)
        mock_rpc.return_value = _resp({
            'success': True, 'application_id': APP_ID, 'employer_id': EMPLOYER_ID})

        resp = app_client.post('/apply-selected', data={'job_ids': [JOB_ID]},
                               follow_redirects=False)
        assert resp.status_code == 302


# ═══ /my-jobs/action (AJAX) ═══

class TestMyJobsActionAjax:
    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.jobs.postgrest_rpc')
    @patch('app.blueprints.jobs.check_job_owner')
    def test_bulk_cancel_json(self, mock_owner, mock_rpc, mock_bl, app_client):
        _login(app_client, role='employer', uid=EMPLOYER_ID)
        mock_owner.return_value = True
        mock_rpc.return_value = _resp({'success': True, 'new_status': 'cancelled'})

        resp = app_client.post('/my-jobs/action',
                               data={'action': 'cancel', 'job_ids': [JOB_ID]},
                               headers={'X-Requested-With': 'XMLHttpRequest'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['succeeded'] == [{'id': JOB_ID, 'new_status': 'cancelled'}]
        assert data['failed'] == []

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.jobs.postgrest_rpc')
    @patch('app.blueprints.jobs.check_job_owner')
    def test_bulk_cancel_conflict_json(self, mock_owner, mock_rpc, mock_bl, app_client):
        """has_accepted_workers → per-job ошибка в failed."""
        _login(app_client, role='employer', uid=EMPLOYER_ID)
        mock_owner.return_value = True
        mock_rpc.return_value = _resp({
            'success': False, 'code': 'has_accepted_workers',
            'error': 'Невозможно отменить задание с принятыми работниками'})

        resp = app_client.post('/my-jobs/action',
                               data={'action': 'cancel', 'job_ids': [JOB_ID]},
                               headers={'X-Requested-With': 'XMLHttpRequest'})
        data = resp.get_json()
        assert data['success'] is False
        assert len(data['failed']) == 1
        assert data['failed'][0]['id'] == JOB_ID

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.jobs.postgrest_request')
    @patch('app.blueprints.jobs.check_job_owner')
    def test_bulk_duplicate_returns_new_job_id(self, mock_owner, mock_req, mock_bl, app_client):
        _login(app_client, role='employer', uid=EMPLOYER_ID)
        mock_owner.return_value = True

        def fake_request(method, url, **kw):
            if method == 'GET':
                return _resp([{'id': JOB_ID, 'employer_id': EMPLOYER_ID,
                               'organization_name': 'Тест', 'payment_amount': 500}])
            # POST jobs с Prefer: return=representation → созданная строка
            assert 'return=representation' in (kw.get('headers') or {}).get('Prefer', '')
            return _resp([{'id': JOB2_ID}], status_code=201)

        mock_req.side_effect = fake_request
        resp = app_client.post('/my-jobs/action',
                               data={'action': 'duplicate', 'job_ids': [JOB_ID]},
                               headers={'X-Requested-With': 'XMLHttpRequest'})
        data = resp.get_json()
        assert data['success'] is True
        assert data['succeeded'][0]['new_job_id'] == JOB2_ID

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    def test_bulk_no_jobs_400(self, mock_bl, app_client):
        _login(app_client, role='employer', uid=EMPLOYER_ID)
        resp = app_client.post('/my-jobs/action', data={'action': 'cancel'},
                               headers={'X-Requested-With': 'XMLHttpRequest'})
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False


# ═══ GET /?filter=new|applied (серверные фильтры каталога, B4) ═══

class TestIndexServerFilter:
    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.jobs.postgrest_request')
    def test_filter_applied_uses_inner_join(self, mock_req, mock_bl, app_client):
        """filter=applied → applications!inner.worker_id=eq.<uid> в запросе jobs."""
        _login(app_client)
        mock_req.return_value = _resp([])

        resp = app_client.get('/?filter=applied')
        assert resp.status_code == 200
        jobs_calls = [c for c in mock_req.call_args_list
                      if len(c[0]) >= 2 and str(c[0][1]).startswith('jobs?')]
        assert jobs_calls, 'Запрос к jobs не выполнялся'
        url = jobs_calls[0][0][1]
        assert f'applications!inner.worker_id=eq.{WORKER_ID}' in url

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.jobs.postgrest_request')
    def test_filter_new_excludes_applied(self, mock_req, mock_bl, app_client):
        """filter=new → id=not.in.(<отклики пользователя>) в запросе jobs."""
        _login(app_client)

        def fake_request(method, url, **kw):
            if str(url).startswith('applications?'):
                return _resp([{'job_id': JOB_ID}])
            return _resp([])

        mock_req.side_effect = fake_request
        resp = app_client.get('/?filter=new')
        assert resp.status_code == 200
        jobs_calls = [c for c in mock_req.call_args_list
                      if len(c[0]) >= 2 and str(c[0][1]).startswith('jobs?')]
        assert jobs_calls
        url = jobs_calls[0][0][1]
        assert f'id=not.in.({JOB_ID})' in url

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.jobs.postgrest_request')
    def test_no_filter_has_no_extra_clauses(self, mock_req, mock_bl, app_client):
        """Без filter — ни !inner, ни not.in в запросе jobs (регрессия)."""
        _login(app_client)
        mock_req.return_value = _resp([])

        resp = app_client.get('/')
        assert resp.status_code == 200
        jobs_calls = [c for c in mock_req.call_args_list
                      if len(c[0]) >= 2 and str(c[0][1]).startswith('jobs?')]
        assert jobs_calls
        url = jobs_calls[0][0][1]
        assert 'applications!inner' not in url
        assert 'not.in' not in url

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.jobs.postgrest_request')
    def test_filter_pills_keep_query_params(self, mock_req, mock_bl, app_client):
        """Пилюли — ссылки, сохраняющие q/sort и выставляющие filter."""
        _login(app_client)
        mock_req.return_value = _resp([])

        resp = app_client.get('/?q=грузчик&sort=price_asc&filter=new')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'filter=applied' in html
        assert 'q=%D0%B3%D1%80%D1%83%D0%B7%D1%87%D0%B8%D0%BA' in html or 'q=грузчик' in html
        assert 'sort=price_asc' in html
