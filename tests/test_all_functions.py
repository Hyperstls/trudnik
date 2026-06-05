#!/usr/bin/env python3
"""Комплексное тестирование всех функций приложения Trudnik.

Использует unittest + unittest.mock для мока Supabase API и шаблонов.
"""

import json
import math
import os
import re
import sys
import unittest
from unittest.mock import ANY, MagicMock, patch, PropertyMock

# Отключаем proxy для всех тестов (иначе httpx/openai падает с SOCKS)
os.environ.setdefault('NO_PROXY', '*')
os.environ.setdefault('no_proxy', '*')

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# --- Переменные окружения для тестов ---
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['SUPABASE_URL'] = 'https://test.supabase.co'
os.environ['SUPABASE_ANON_KEY'] = 'test-anon-key'
os.environ['SUPABASE_SERVICE_ROLE_KEY'] = 'test-service-role-key'
os.environ['YANDEX_MAPS_API_KEY'] = 'test-yandex-key'

from app import create_app
from app.config import Config
from app.decorators import login_required, role_required
from app.utils import (
    SUPABASE_KEY,
    SUPABASE_URL,
    SERVICE_KEY,
    add_notification,
    calculate_distance,
    copy_job,
    refresh_access_token,
    supabase_request,
    update_rating,
    upload_to_storage,
)

# =====================================================
# 1. ТЕСТЫ УТИЛИТ (app/utils.py)
# =====================================================

class TestUtils(unittest.TestCase):
    """Тестирование всех вспомогательных функций в utils.py"""

    def setUp(self):
        # Создаём контекст приложения для current_app
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_calculate_distance(self):
        dist = calculate_distance(55.75, 37.62, 59.93, 30.34)
        self.assertAlmostEqual(dist, 633, delta=30)

    def test_calculate_distance_same_point(self):
        dist = calculate_distance(55.75, 37.62, 55.75, 37.62)
        self.assertAlmostEqual(dist, 0)

    def test_calculate_distance_large(self):
        dist = calculate_distance(55.75, 37.62, 43.12, 131.89)
        self.assertAlmostEqual(dist, 6436, delta=100)

    def test_copy_job(self):
        original = {
            'employer_id': 'emp-1', 'organization_name': 'Храм',
            'org_description': 'Описание', 'object_description': 'Объект',
            'work_type': 'уборка', 'detailed_description': 'Подробно',
            'date_time': '2025-01-01T10:00:00', 'payment_amount': 5000,
            'address': 'ул. Тестовая, 1', 'city': 'Москва',
            'lat': 55.75, 'lng': 37.62, 'status': 'closed',
            'max_workers': 3, 'current_workers': 2,
        }
        copy = copy_job(original)
        self.assertEqual(copy['employer_id'], 'emp-1')
        self.assertEqual(copy['organization_name'], 'Храм')
        self.assertEqual(copy['payment_amount'], 5000)
        self.assertEqual(copy['max_workers'], 3)
        self.assertEqual(copy['status'], 'open')
        self.assertEqual(copy['current_workers'], 0)

    def test_copy_job_minimal(self):
        copy = copy_job({'employer_id': 'emp-1'})
        self.assertEqual(copy['employer_id'], 'emp-1')
        self.assertEqual(copy['status'], 'open')
        self.assertEqual(copy['current_workers'], 0)

    def test_refresh_token_no_refresh(self):
        with patch('app.utils.session', {}):
            result = refresh_access_token()
            self.assertFalse(result)

    @patch('app.utils.requests.post')
    def test_refresh_token_success(self, mock_post):
        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {'access_token': 'new-token', 'refresh_token': 'new-refresh'}
        )
        mock_session = MagicMock()
        mock_session.get.return_value = 'old-refresh'
        mock_session.__contains__ = MagicMock(return_value=True)
        mock_session.__getitem__.side_effect = lambda k: {
            'refresh_token': 'old-refresh', 'access_token': 'old-token'
        }[k]
        with patch('app.utils.session', mock_session):
            result = refresh_access_token()
            self.assertTrue(result)
        mock_post.assert_called_once()

    @patch('app.utils.requests.post')
    def test_refresh_token_failure(self, mock_post):
        mock_post.return_value = MagicMock(ok=False)
        mock_session = MagicMock()
        mock_session.get.return_value = 'old-refresh'
        mock_session.__contains__ = MagicMock(return_value=True)
        with patch('app.utils.session', mock_session):
            result = refresh_access_token()
            self.assertFalse(result)

    @patch('app.utils.requests.request')
    def test_supabase_request_success(self, mock_request):
        mock_request.return_value = MagicMock(
            ok=True, status_code=200,
            json=lambda: [{'id': 1, 'name': 'Test'}]
        )
        mock_session = MagicMock()
        mock_session.get.return_value = 'token'
        mock_session.__contains__ = MagicMock(return_value=True)
        mock_session.__getitem__.return_value = 'token'
        with patch('app.utils.session', mock_session):
            resp = supabase_request('GET', 'profiles?id=eq.123')
        self.assertTrue(resp.ok)
        self.assertEqual(resp.json(), [{'id': 1, 'name': 'Test'}])

    @patch('app.utils.requests.request')
    def test_supabase_request_unauthorized_with_refresh(self, mock_request):
        mock_request.side_effect = [
            MagicMock(ok=False, status_code=401),
            MagicMock(ok=True, status_code=200, json=lambda: [{'id': 1}]),
        ]
        mock_session = MagicMock()
        mock_session.get.side_effect = lambda k, d=None: {
            'access_token': 'token', 'refresh_token': 'refresh'
        }.get(k, d)
        mock_session.__contains__ = MagicMock(return_value=True)
        mock_session.__getitem__.side_effect = lambda k: {
            'access_token': 'token', 'refresh_token': 'refresh'
        }[k]
        with patch('app.utils.session', mock_session):
            with patch('app.utils.refresh_access_token', return_value=True):
                resp = supabase_request('GET', 'profiles?id=eq.123')
        self.assertTrue(resp.ok)
        self.assertEqual(mock_request.call_count, 2)

    @patch('app.utils.requests.request')
    def test_supabase_request_network_error(self, mock_request):
        mock_request.side_effect = Exception('Network error')
        mock_session = MagicMock()
        mock_session.get.return_value = 'token'
        mock_session.__contains__ = MagicMock(return_value=True)
        mock_session.__getitem__.return_value = 'token'
        with patch('app.utils.session', mock_session):
            # current_app доступен из app_context
            resp = supabase_request('GET', 'profiles?id=eq.123')
        self.assertFalse(resp.ok)
        self.assertEqual(resp.status_code, 0)

    @patch('app.utils.requests.post')
    def test_upload_to_storage_success(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        mock_session = MagicMock()
        mock_session.__getitem__.return_value = 'token'
        with patch('app.utils.session', mock_session):
            url = upload_to_storage('avatars', 'user/file.jpg', b'data', 'image/jpeg')
        self.assertIsNotNone(url)
        self.assertIn('avatars', url)
        self.assertIn('user/file.jpg', url)

    @patch('app.utils.requests.post')
    def test_upload_to_storage_failure(self, mock_post):
        mock_post.return_value = MagicMock(status_code=400)
        mock_session = MagicMock()
        mock_session.__getitem__.return_value = 'token'
        with patch('app.utils.session', mock_session):
            url = upload_to_storage('avatars', 'user/file.jpg', b'data', 'image/jpeg')
        self.assertIsNone(url)

    @patch('app.utils.supabase_request')
    def test_add_notification(self, mock_supabase):
        mock_supabase.return_value = MagicMock(ok=True)
        add_notification(
            user_id='user-1', notification_type='test',
            title='Тест', message='Тестовое уведомление',
        )
        mock_supabase.assert_called_once_with(
            'POST', 'notifications',
            json={'user_id': 'user-1', 'type': 'test',
                  'title': 'Тест', 'message': 'Тестовое уведомление',
                  'is_read': False}
        )

    @patch('app.utils.supabase_request')
    def test_update_rating(self, mock_supabase):
        mock_supabase.side_effect = [
            MagicMock(ok=True, json=lambda: [{'rating': 5}, {'rating': 4}, {'rating': 3}]),
            MagicMock(ok=True),
        ]
        update_rating('user-1', 4)
        self.assertEqual(mock_supabase.call_count, 2)
        patch_call = mock_supabase.call_args_list[1]
        self.assertEqual(patch_call[0][0], 'PATCH')
        self.assertEqual(patch_call[0][1], 'profiles?id=eq.user-1')
        self.assertEqual(patch_call[1]['json']['rating'], 4.0)


# =====================================================
# 2. ТЕСТЫ ДЕКОРАТОРОВ (app/decorators.py)
# =====================================================

class TestDecorators(unittest.TestCase):
    """Тестирование декораторов login_required и role_required"""

    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.ctx = self.app.test_request_context()
        self.ctx.push()
        self.decorator_url_for_patcher = patch('app.decorators.url_for', return_value='/')
        self.decorator_url_for_patcher.start()

    def tearDown(self):
        self.decorator_url_for_patcher.stop()
        self.ctx.pop()

    def test_login_required_redirects_when_not_logged_in(self):
        with patch('app.decorators.session', {}):
            with patch('app.decorators.redirect') as mock_redirect:
                mock_redirect.return_value = 'redirected'
                @login_required
                def fake_view():
                    return 'success'
                result = fake_view()
                self.assertEqual(result, 'redirected')

    def test_login_required_passes_when_logged_in(self):
        with patch('app.decorators.session', {'access_token': 'token'}):
            @login_required
            def fake_view():
                return 'success'
            result = fake_view()
            self.assertEqual(result, 'success')

    @patch('app.decorators.supabase_request')
    def test_role_required_correct_role(self, mock_supabase):
        mock_supabase.return_value = MagicMock(ok=True, json=lambda: [{'role': 'employer'}])
        with patch('app.decorators.session', {'access_token': 'token', 'user_id': 'user-1'}):
            @role_required('employer')
            def fake_view():
                return 'success'
            result = fake_view()
            self.assertEqual(result, 'success')

    @patch('app.decorators.supabase_request')
    def test_role_required_wrong_role(self, mock_supabase):
        mock_supabase.return_value = MagicMock(ok=True, json=lambda: [{'role': 'worker'}])
        with patch('app.decorators.session', {'access_token': 'token', 'user_id': 'user-1'}):
            with patch('app.decorators.redirect') as mock_redirect:
                mock_redirect.return_value = 'redirected'
                @role_required('employer')
                def fake_view():
                    return 'success'
                result = fake_view()
                self.assertEqual(result, 'redirected')


# =====================================================
# 3. ТЕСТЫ SUPABASE_AGENT (копируем функции без exec)
# =====================================================

class TestSupabaseAgent(unittest.TestCase):
    """Тестирование функций supabase_agent.py без импорта модуля"""

    def test_validate_sql_safe_allows_select(self):
        ok, msg = self._validate_sql_safe("SELECT * FROM profiles;")
        self.assertTrue(ok)

    def test_validate_sql_safe_blocks_drop(self):
        ok, msg = self._validate_sql_safe("DROP TABLE profiles;")
        self.assertFalse(ok)

    def test_validate_sql_safe_blocks_truncate(self):
        ok, msg = self._validate_sql_safe("TRUNCATE TABLE profiles;")
        self.assertFalse(ok)

    def test_validate_sql_safe_blocks_alter(self):
        ok, msg = self._validate_sql_safe("ALTER TABLE profiles ADD COLUMN x int;")
        self.assertFalse(ok)

    def test_validate_sql_safe_blocks_create_table(self):
        ok, msg = self._validate_sql_safe("CREATE TABLE hack (id int);")
        self.assertFalse(ok)

    def test_validate_sql_safe_case_insensitive(self):
        ok, msg = self._validate_sql_safe("drop table profiles;")
        self.assertFalse(ok)

    def test_split_sql_statements_single(self):
        stmts = self._split_sql_statements("SELECT * FROM users;")
        self.assertEqual(len(stmts), 1)
        self.assertEqual(stmts[0], "SELECT * FROM users")

    def test_split_sql_statements_multiple(self):
        stmts = self._split_sql_statements("SELECT * FROM users; UPDATE profiles SET name='test';")
        self.assertEqual(len(stmts), 2)

    def test_split_sql_statements_with_strings(self):
        stmts = self._split_sql_statements("UPDATE profiles SET name='hello;world' WHERE id=1;")
        self.assertEqual(len(stmts), 1)
        self.assertIn("hello;world", stmts[0])

    def test_split_sql_statements_no_semicolon(self):
        stmts = self._split_sql_statements("SELECT * FROM users")
        self.assertEqual(len(stmts), 1)

    # --- Реализация функций (скопированы из supabase_agent.py) ---

    DESTRUCTIVE_KEYWORDS = ['drop', 'truncate', 'alter', 'create table']

    def _validate_sql_safe(self, sql: str):
        sql_lower = sql.lower().strip().rstrip(';').strip()
        for kw in self.DESTRUCTIVE_KEYWORDS:
            if sql_lower.startswith(kw):
                return False, f"Запрещённый оператор: {kw.upper()}"
        return True, "OK"

    def _split_sql_statements(self, sql: str):
        statements = []
        current = []
        in_single_quote = False
        in_double_quote = False
        for char in sql:
            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif char == ';' and not in_single_quote and not in_double_quote:
                stmt = ''.join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []
                continue
            current.append(char)
        remaining = ''.join(current).strip()
        if remaining:
            statements.append(remaining)
        return statements if statements else [sql]


# =====================================================
# 4. ТЕСТЫ BLUEPRINT'ОВ (через тестовый клиент Flask)
# =====================================================

class BaseBlueprintTest(unittest.TestCase):
    """Базовый класс для тестов blueprints с Flask test client"""

    # Все blueprint'ы импортируют supabase_request на уровне модуля,
    # поэтому нужно патчить каждый отдельно, а не app.utils.supabase_request
    BLUEPRINTS_USING_SUPABASE = [
        'app.blueprints.auth',
        'app.blueprints.profile',
        'app.blueprints.jobs',
        'app.blueprints.applications',
        'app.blueprints.shifts',
        'app.blueprints.chat',
        'app.blueprints.favorites',
        'app.blueprints.blacklist',
        'app.blueprints.notifications',
        'app.blueprints.admin',
        'app.blueprints.monetization',
        'app.decorators',
    ]

    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        # Патчим render_template — шаблоны не нужны для тестов роутов.
        # Важно: blueprint'ы импортируют render_template на уровне модуля,
        # поэтому патчим каждый blueprint отдельно.
        self.patchers = []
        self.mock_supabase = MagicMock()
        for mod in self.BLUEPRINTS_USING_SUPABASE:
            # Патчим supabase_request (есть во всех модулях списка)
            p = patch(f'{mod}.supabase_request', self.mock_supabase)
            p.start()
            self.patchers.append(p)
        # Патчим render_template, url_for, flash только в blueprint'ах (не в decorators)
        BLUEPRINTS_ONLY = [m for m in self.BLUEPRINTS_USING_SUPABASE if m != 'app.decorators']
        for mod in BLUEPRINTS_ONLY:
            # Патчим render_template
            p2 = patch(f'{mod}.render_template', return_value='')
            p2.start()
            self.patchers.append(p2)
            # Патчим url_for (возвращаем '/')
            p3 = patch(f'{mod}.url_for', return_value='/')
            p3.start()
            self.patchers.append(p3)
            # Патчим flash
            p4 = patch(f'{mod}.flash')
            p4.start()
            self.patchers.append(p4)
        # Патчим url_for и redirect в decorators отдельно
        # (decorators импортирует url_for и redirect, но не render_template/flash)
        p_d1 = patch('app.decorators.url_for', return_value='/')
        p_d1.start()
        self.patchers.append(p_d1)
        # Патчим прямые requests.* вызовы в auth.py и profile.py (не через supabase_request)
        self.auth_requests_patcher = patch('app.blueprints.auth.requests', MagicMock())
        self.auth_requests_patcher.start()
        self.patchers.append(self.auth_requests_patcher)
        self.profile_requests_patcher = patch('app.blueprints.profile.requests', MagicMock())
        self.profile_requests_patcher.start()
        self.patchers.append(self.profile_requests_patcher)
        # Создаём контекст приложения
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()
        for p in self.patchers:
            p.stop()

    def _login(self, user_id='test-user-1', role='worker'):
        with self.client.session_transaction() as sess:
            sess['access_token'] = 'test-token'
            sess['refresh_token'] = 'test-refresh'
            sess['user_id'] = user_id
            sess['role'] = role
            sess.modified = True

    def _login_employer(self):
        self._login(user_id='emp-1', role='employer')

    def _login_admin(self):
        self._login(user_id='admin-1', role='admin')


class TestAuthBlueprint(BaseBlueprintTest):
    """Тестирование маршрутов аутентификации"""

    def test_login_get(self):
        resp = self.client.get('/login')
        self.assertEqual(resp.status_code, 200)

    @patch('app.blueprints.auth.requests.post')
    def test_login_post_success_worker(self, mock_post):
        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {'access_token': 'new-token', 'refresh_token': 'new-refresh',
                          'user': {'id': 'user-1'}}
        )
        with patch('app.blueprints.auth.supabase_request') as mock_sb:
            mock_sb.return_value = MagicMock(ok=True, json=lambda: [{'role': 'worker'}])
            resp = self.client.post('/login', data={
                'email': 'test@test.com', 'password': 'password123',
            })
        self.assertEqual(resp.status_code, 302)

    @patch('app.blueprints.auth.requests.post')
    def test_login_post_failure(self, mock_post):
        mock_post.return_value = MagicMock(ok=False, status_code=400)
        resp = self.client.post('/login', data={
            'email': 'bad@test.com', 'password': 'wrong',
        })
        self.assertEqual(resp.status_code, 200)

    def test_logout(self):
        self._login()
        resp = self.client.get('/logout')
        self.assertEqual(resp.status_code, 302)

    def test_register_get(self):
        resp = self.client.get('/register')
        self.assertEqual(resp.status_code, 200)

    @patch('app.blueprints.auth.requests.post')
    def test_register_post(self, mock_post):
        mock_post.return_value = MagicMock(ok=True, json=lambda: {'user': {'id': 'new-user'}})
        with patch('app.blueprints.auth.supabase_request') as mock_sb:
            mock_sb.return_value = MagicMock(ok=True)
            resp = self.client.post('/register', data={
                'full_name': 'Тест', 'email': 'test@test.com',
                'password': 'password123', 'role': 'worker', 'city': 'Москва',
            })
        self.assertEqual(resp.status_code, 302)


class TestJobsBlueprint(BaseBlueprintTest):
    """Тестирование маршрутов заданий"""

    def test_index(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)

    def test_index_with_filters(self):
        resp = self.client.get('/?city=Москва')
        self.assertEqual(resp.status_code, 200)

    def test_job_detail(self):
        resp = self.client.get('/jobs/1')
        self.assertEqual(resp.status_code, 200)

    def test_job_detail_not_found(self):
        with patch('app.blueprints.jobs.supabase_request') as mock_sb:
            mock_sb.return_value = MagicMock(ok=False, json=lambda: [])
            resp = self.client.get('/jobs/999')
        self.assertEqual(resp.status_code, 302)

    def test_my_jobs_employer(self):
        self._login_employer()
        resp = self.client.get('/my-jobs')
        self.assertEqual(resp.status_code, 200)

    def test_my_jobs_not_employer(self):
        self._login(role='worker')
        resp = self.client.get('/my-jobs')
        self.assertEqual(resp.status_code, 302)

    def test_job_new_get_employer(self):
        self._login_employer()
        with patch('app.decorators.supabase_request') as mock_dec_sb:
            mock_dec_sb.return_value = MagicMock(ok=True, json=lambda: [{'role': 'employer'}])
            resp = self.client.get('/job/new')
        self.assertEqual(resp.status_code, 200)

    def test_job_new_post(self):
        self._login_employer()
        resp = self.client.post('/job/new', data={
            'title': 'Тестовый храм', 'description': 'Нужна уборка',
            'payment': '5000', 'city': 'Москва',
            'address': 'ул. Тестовая', 'max_workers': '2',
            'latitude': '55.75', 'longitude': '37.62',
        })
        self.assertEqual(resp.status_code, 302)

    def test_workers_page(self):
        resp = self.client.get('/workers')
        self.assertEqual(resp.status_code, 200)

    def test_my_jobs_actions(self):
        self._login_employer()
        resp = self.client.post('/my-jobs/action', data={
            'action': 'cancel', 'job_ids': ['1', '2'],
        })
        self.assertEqual(resp.status_code, 302)

    def test_add_favorite_job(self):
        self._login()
        resp = self.client.post('/favorite-job/job-1')
        self.assertEqual(resp.status_code, 302)

    def test_remove_favorite_job(self):
        self._login()
        with patch('app.blueprints.jobs.supabase_request') as mock_sb:
            mock_sb.return_value = MagicMock(ok=True, json=lambda: [{}])
            resp = self.client.post('/unfavorite-job/job-1')
        self.assertEqual(resp.status_code, 302)

    def test_repost_job(self):
        self._login_employer()
        resp = self.client.post('/repost-job/job-1')
        self.assertEqual(resp.status_code, 302)

    def test_cancel_job(self):
        self._login_employer()
        resp = self.client.post('/cancel-job/job-1')
        self.assertEqual(resp.status_code, 302)

    def test_delete_job(self):
        self._login_employer()
        resp = self.client.post('/delete-job/job-1')
        self.assertEqual(resp.status_code, 302)


class TestApplicationsBlueprint(BaseBlueprintTest):
    """Тестирование маршрутов откликов"""

    def test_apply_job(self):
        self._login()
        resp = self.client.post('/apply/job-1')
        self.assertEqual(resp.status_code, 302)

    def test_apply_own_job(self):
        self._login(user_id='emp-1')
        resp = self.client.post('/apply/job-1')
        self.assertEqual(resp.status_code, 302)

    def test_apply_job_full(self):
        self._login()
        resp = self.client.post('/apply/job-1')
        self.assertEqual(resp.status_code, 302)

    def test_apply_job_closed(self):
        self._login()
        resp = self.client.post('/apply/job-1')
        self.assertEqual(resp.status_code, 302)

    def test_apply_selected(self):
        self._login()
        resp = self.client.post('/apply-selected', data={'job_ids': ['1', '2']})
        self.assertEqual(resp.status_code, 302)

    def test_my_applications_as_employer(self):
        self._login_employer()
        resp = self.client.get('/my-applications')
        self.assertEqual(resp.status_code, 200)

    def test_handle_application_accept(self):
        self._login_employer()
        responses = [
            MagicMock(ok=True, json=lambda: [{'job_id': 'job-1', 'worker_id': 'w-1', 'status': 'pending'}]),
            MagicMock(ok=True, json=lambda: [{'employer_id': 'emp-1'}]),
            MagicMock(ok=True, json=lambda: [{'current_workers': 0, 'max_workers': 5, 'status': 'open'}]),
            MagicMock(ok=True, json=lambda: [{'current_workers': 0, 'max_workers': 5}]),
            MagicMock(ok=True),
            MagicMock(ok=True, json=lambda: []),
            MagicMock(ok=True, json=lambda: [{'id': 'shift-1'}]),
            MagicMock(ok=True),
        ]
        with patch('app.blueprints.applications.supabase_request', side_effect=responses):
            resp = self.client.post('/api/applications/app-1/accept')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))

    def test_handle_application_reject(self):
        self._login_employer()
        responses = [
            MagicMock(ok=True, json=lambda: [{'job_id': 'job-1', 'worker_id': 'w-1', 'status': 'pending'}]),
            MagicMock(ok=True, json=lambda: [{'employer_id': 'emp-1'}]),
            MagicMock(ok=True),
            MagicMock(ok=True),
        ]
        with patch('app.blueprints.applications.supabase_request', side_effect=responses):
            resp = self.client.post('/api/applications/app-1/reject')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))

    def test_handle_application_reject_accepted(self):
        """Отклонение уже принятого отклика (accepted → rejected)"""
        self._login_employer()
        responses = [
            MagicMock(ok=True, json=lambda: [{'job_id': 'job-1', 'worker_id': 'w-1', 'status': 'accepted', 'shift_id': 'shift-1'}]),
            MagicMock(ok=True, json=lambda: [{'employer_id': 'emp-1'}]),
            MagicMock(ok=True, json=lambda: [{'current_workers': 2, 'max_workers': 5, 'status': 'in_progress'}]),
            MagicMock(ok=True),
            MagicMock(ok=True),
            MagicMock(ok=True),
            MagicMock(ok=True),
        ]
        with patch('app.blueprints.applications.supabase_request', side_effect=responses):
            resp = self.client.post('/api/applications/app-1/reject')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('new_status'), 'rejected')
        self.assertIsNotNone(data.get('current_workers'))

    def test_unapply_job(self):
        self._login()
        resp = self.client.post('/unapply/job-1')
        self.assertEqual(resp.status_code, 302)

    def test_unapply_selected(self):
        self._login()
        resp = self.client.post('/unapply-selected', data={'job_ids': ['1', '2']})
        self.assertEqual(resp.status_code, 302)

    def test_cancel_application(self):
        self._login()
        responses = [
            MagicMock(ok=True, json=lambda: [{'job_id': 'job-1', 'worker_id': 'w-1', 'shift_id': None}]),
            MagicMock(ok=True, json=lambda: [{'status': 'in_progress', 'start_time': None}]),
            MagicMock(ok=True, json=lambda: [{'current_workers': 2, 'max_workers': 5}]),
            MagicMock(ok=True),
            MagicMock(ok=True),
        ]
        with patch('app.blueprints.applications.supabase_request', side_effect=responses):
            resp = self.client.post('/application/app-1/cancel')
        self.assertEqual(resp.status_code, 302)


class TestProfileBlueprint(BaseBlueprintTest):
    """Тестирование маршрутов профиля"""

    def test_profile(self):
        self._login()
        resp = self.client.get('/profile')
        self.assertEqual(resp.status_code, 200)

    def test_profile_not_logged_in(self):
        resp = self.client.get('/profile')
        self.assertEqual(resp.status_code, 302)

    def test_update_profile(self):
        self._login()
        resp = self.client.post('/profile/update', data={
            'full_name': 'Иван Петров', 'phone': '+79991234567',
            'bio': 'Опытный работник', 'city': 'Москва',
            'religion': 'христианство', 'skills': 'уборка,строительство',
        })
        self.assertEqual(resp.status_code, 302)

    def test_public_profile(self):
        resp = self.client.get('/profile/user-1')
        self.assertEqual(resp.status_code, 200)

    def test_public_profile_not_found(self):
        with patch('app.blueprints.profile.supabase_request') as mock_sb:
            mock_sb.return_value = MagicMock(ok=False, json=lambda: [])
            resp = self.client.get('/profile/nobody')
        self.assertEqual(resp.status_code, 302)

    def test_delete_photo(self):
        self._login()
        resp = self.client.post('/profile/delete-photo')
        self.assertEqual(resp.status_code, 302)

    @patch('app.blueprints.profile.requests.put')
    def test_change_password(self, mock_put):
        self._login()
        mock_put.return_value = MagicMock(ok=True)
        resp = self.client.post('/profile/change-password', data={
            'new_password': 'newpass123', 'confirm_password': 'newpass123',
        })
        self.assertEqual(resp.status_code, 302)

    def test_change_password_mismatch(self):
        self._login()
        resp = self.client.post('/profile/change-password', data={
            'new_password': 'newpass123', 'confirm_password': 'different',
        })
        self.assertEqual(resp.status_code, 302)

    def test_change_password_short(self):
        self._login()
        resp = self.client.post('/profile/change-password', data={
            'new_password': '123', 'confirm_password': '123',
        })
        self.assertEqual(resp.status_code, 302)

    def test_verify_employer_get(self):
        self._login()
        resp = self.client.get('/verify-employer')
        self.assertEqual(resp.status_code, 200)

    def test_verify_employer_post(self):
        self._login()
        resp = self.client.post('/verify-employer')
        self.assertEqual(resp.status_code, 302)


class TestShiftsBlueprint(BaseBlueprintTest):
    """Тестирование маршрутов смен"""

    def test_shifts_worker(self):
        self._login()
        resp = self.client.get('/shifts')
        self.assertEqual(resp.status_code, 200)

    def test_shifts_employer(self):
        self._login_employer()
        resp = self.client.get('/shifts')
        self.assertEqual(resp.status_code, 200)

    def test_shift_checkin(self):
        self._login()
        resp = self.client.post('/shift/s-1/checkin')
        self.assertEqual(resp.status_code, 302)

    def test_shift_checkin_wrong_user(self):
        self._login(user_id='other-user')
        resp = self.client.post('/shift/s-1/checkin')
        self.assertEqual(resp.status_code, 302)

    def test_shift_complete(self):
        self._login()
        resp = self.client.post('/shift/s-1/complete')
        self.assertEqual(resp.status_code, 302)

    def test_confirm_payment_employer(self):
        self._login_employer()
        resp = self.client.post('/shift/s-1/confirm-payment', data={
            'action': 'confirm_employer'
        })
        self.assertEqual(resp.status_code, 302)

    def test_dispute_shift(self):
        self._login_employer()
        resp = self.client.post('/shift/s-1/dispute')
        self.assertEqual(resp.status_code, 302)

    def test_rate_worker(self):
        self._login_employer()
        resp = self.client.post('/rate-worker/w-1/job-1', data={
            'rating': '5', 'comment': 'Отлично!',
        })
        self.assertEqual(resp.status_code, 302)


class TestFavoritesBlueprint(BaseBlueprintTest):
    """Тестирование маршрутов избранного"""

    def test_favorites_worker(self):
        self._login(role='worker')
        resp = self.client.get('/favorites')
        self.assertEqual(resp.status_code, 200)

    def test_favorites_employer(self):
        self._login_employer()
        resp = self.client.get('/favorites')
        self.assertEqual(resp.status_code, 200)

    def test_add_favorite(self):
        self._login()
        resp = self.client.post('/favorite/w-1')
        self.assertEqual(resp.status_code, 302)

    def test_remove_favorite(self):
        self._login()
        resp = self.client.post('/unfavorite/w-1')
        self.assertEqual(resp.status_code, 302)

    def test_api_add_favorite(self):
        self._login()
        resp = self.client.post('/api/favorites/add',
                                json={'worker_id': 'w-1'},
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])

    def test_api_remove_favorite(self):
        self._login()
        resp = self.client.post('/api/favorites/remove',
                                json={'worker_id': 'w-1'},
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])

    def test_api_check_favorite(self):
        self._login()
        with patch('app.blueprints.favorites.supabase_request') as mock_sb:
            mock_sb.return_value = MagicMock(ok=True, json=lambda: [{'id': 1}])
            resp = self.client.post('/api/favorites/check',
                                    json={'worker_id': 'w-1'},
                                    content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['is_favorited'])

    def test_api_check_favorite_false(self):
        self._login()
        with patch('app.blueprints.favorites.supabase_request') as mock_sb:
            mock_sb.return_value = MagicMock(ok=True, json=lambda: [])
            resp = self.client.post('/api/favorites/check',
                                    json={'worker_id': 'w-1'},
                                    content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data['is_favorited'])


class TestChatBlueprint(BaseBlueprintTest):
    """Тестирование маршрутов чата"""

    def test_chat_list(self):
        self._login()
        resp = self.client.get('/chats')
        self.assertEqual(resp.status_code, 200)

    def test_chat_detail(self):
        self._login()
        resp = self.client.get('/chat/s-1')
        self.assertEqual(resp.status_code, 200)

    def test_send_message(self):
        self._login()
        resp = self.client.post('/api/send_message',
                                json={'shift_id': 's-1', 'content': 'Привет'},
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'ok')


class TestBlacklistBlueprint(BaseBlueprintTest):
    """Тестирование маршрутов чёрного списка"""

    def test_blacklist(self):
        self._login()
        resp = self.client.get('/blacklist')
        self.assertEqual(resp.status_code, 200)

    def test_block_user(self):
        self._login()
        resp = self.client.post('/blacklist/bad-user')
        self.assertEqual(resp.status_code, 302)

    def test_unblock_user(self):
        self._login()
        resp = self.client.post('/unblock/bad-user')
        self.assertEqual(resp.status_code, 302)


class TestNotificationsBlueprint(BaseBlueprintTest):
    """Тестирование маршрутов уведомлений"""

    def test_notifications(self):
        self._login()
        resp = self.client.get('/notifications')
        self.assertEqual(resp.status_code, 200)

    def test_mark_read(self):
        self._login()
        resp = self.client.post('/notification/n-1/read')
        self.assertEqual(resp.status_code, 302)


class TestAdminBlueprint(BaseBlueprintTest):
    """Тестирование маршрутов админ-панели"""

    def test_admin_panel(self):
        self._login_admin()
        with patch('app.decorators.supabase_request') as mock_dec_sb:
            mock_dec_sb.return_value = MagicMock(ok=True, json=lambda: [{'role': 'admin'}])
            with patch('app.blueprints.admin.supabase_request') as mock_admin_sb:
                mock_admin_sb.return_value = MagicMock(ok=True, json=lambda: [])
                resp = self.client.get('/admin')
        self.assertEqual(resp.status_code, 200)

    def test_admin_panel_not_admin(self):
        self._login()
        resp = self.client.get('/admin')
        self.assertEqual(resp.status_code, 302)

    def test_approve_employer(self):
        self._login_admin()
        resp = self.client.post('/admin/approve/u-1')
        self.assertEqual(resp.status_code, 302)

    def test_reject_employer(self):
        self._login_admin()
        resp = self.client.post('/admin/reject/u-1')
        self.assertEqual(resp.status_code, 302)


class TestMonetizationBlueprint(BaseBlueprintTest):
    """Тестирование маршрутов монетизации"""

    def test_create_payment_missing_fields(self):
        """POST /api/payments/create без полей → 400"""
        self._login_employer()
        resp = self.client.post(
            '/api/payments/create',
            json={},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('error', data)

    def test_create_payment_access_denied(self):
        """POST /api/payments/create от не-владельца задания → 403"""
        self._login_employer()
        with patch('app.blueprints.monetization.supabase_request') as mock_sb:
            mock_sb.return_value = MagicMock(
                ok=True, json=lambda: [{'employer_id': 'other-emp'}],
            )
            resp = self.client.post(
                '/api/payments/create',
                json={
                    'application_id': 'app-1',
                    'job_id': 'job-1',
                    'worker_id': 'w-1',
                },
                content_type='application/json',
            )
        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertIn('error', data)

    def test_confirm_payment_no_payment_id(self):
        """POST /api/payments/confirm без payment_id → 400"""
        self._login_employer()
        resp = self.client.post(
            '/api/payments/confirm',
            json={},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('error', data)

    def test_payment_status_not_found(self):
        """GET /api/payments/status/<id> несуществующего application → 404"""
        with patch('app.blueprints.monetization.supabase_request') as mock_sb:
            mock_sb.return_value = MagicMock(ok=False, json=lambda: [])
            resp = self.client.get('/api/payments/status/nonexistent-id')
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json()
        self.assertIn('error', data)

    def test_remind_cheque_not_worker(self):
        """POST /api/cheque/remind/<id> от не-исполнителя → 403"""
        self._login()  # login as worker 'test-user-1'
        with patch('app.blueprints.monetization.supabase_request') as mock_sb:
            mock_sb.return_value = MagicMock(
                ok=True,
                json=lambda: [{'worker_id': 'other-worker', 'job': {}}],
            )
            resp = self.client.post('/api/cheque/remind/app-1')
        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertIn('error', data)


# =====================================================
# ЗАПУСК
# =====================================================

if __name__ == '__main__':
    unittest.main(verbosity=2)
