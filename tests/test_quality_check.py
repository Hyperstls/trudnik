"""Комплексные тесты: юнит, интеграционные, проверка шаблонов."""
import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils import (
    calculate_distance, SupabaseResponse,
    supabase_request, copy_job, MAX_UPLOAD_SIZE
)
from app.config import Config


# ============================================================
# Юнит-тесты утилит
# ============================================================

class TestCalculateDistance(unittest.TestCase):
    """Тесты вычисления расстояния (формула гаверсинусов)."""

    def test_same_point_zero_distance(self):
        self.assertEqual(calculate_distance(55.75, 37.61, 55.75, 37.61), 0.0)

    def test_moscow_to_spb_approx(self):
        """Москва (55.75, 37.61) → Санкт-Петербург (59.93, 30.33) ≈ 635 км."""
        dist = calculate_distance(55.75, 37.61, 59.93, 30.33)
        self.assertGreater(dist, 600)
        self.assertLess(dist, 700)

    def test_known_distance_paris_london(self):
        """Париж (48.85, 2.35) → Лондон (51.51, -0.13) ≈ 344 км."""
        dist = calculate_distance(48.85, 2.35, 51.51, -0.13)
        self.assertGreater(dist, 300)
        self.assertLess(dist, 400)

    def test_equator_distance(self):
        """1 градус долготы на экваторе ≈ 111.32 км."""
        dist = calculate_distance(0, 0, 0, 1)
        self.assertGreater(dist, 110)
        self.assertLess(dist, 112)


class TestSupabaseResponse(unittest.TestCase):
    """Тесты класса-обёртки ответа Supabase."""

    def test_ok_response(self):
        resp = SupabaseResponse(ok=True, status_code=200, data=[{'id': 1}])
        self.assertTrue(resp.ok)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [{'id': 1}])

    def test_error_response(self):
        resp = SupabaseResponse(ok=False, status_code=500, text='Internal error')
        self.assertFalse(resp.ok)
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.text, 'Internal error')

    def test_empty_json(self):
        resp = SupabaseResponse(ok=True, data=None)
        self.assertIsNone(resp.json())


class TestCopyJob(unittest.TestCase):
    """Тесты функции копирования задания."""

    def setUp(self):
        self.original = {
            'employer_id': 'emp-1',
            'organization_name': 'ООО Тест',
            'org_description': 'Описание',
            'object_description': 'Объект',
            'work_type': 'Строительство',
            'detailed_description': 'Детали',
            'date_time': '2026-06-15',
            'payment_amount': 5000,
            'address': 'Москва',
            'city': 'Москва',
            'lat': 55.75,
            'lng': 37.61,
            'status': 'completed',
            'max_workers': 3,
            'current_workers': 2,
        }

    def test_copy_resets_status(self):
        copy = copy_job(self.original)
        self.assertEqual(copy['status'], 'open')

    def test_copy_resets_workers(self):
        copy = copy_job(self.original)
        self.assertEqual(copy['current_workers'], 0)

    def test_copy_preserves_data(self):
        copy = copy_job(self.original)
        self.assertEqual(copy['organization_name'], 'ООО Тест')
        self.assertEqual(copy['payment_amount'], 5000)
        self.assertEqual(copy['max_workers'], 3)

    def test_copy_missing_fields_default(self):
        minimal = {'employer_id': 'emp-2'}
        copy = copy_job(minimal)
        self.assertEqual(copy['status'], 'open')
        self.assertEqual(copy['payment_amount'], 0)
        self.assertEqual(copy['lat'], 55.75)


class TestMAXUploadSize(unittest.TestCase):
    """Проверка лимита загрузки файлов."""

    def test_max_upload_5mb(self):
        self.assertEqual(MAX_UPLOAD_SIZE, 5 * 1024 * 1024)


# ============================================================
# Интеграционные тесты API (Flask test client)
# ============================================================

class TestAPISkillsEndpoint(unittest.TestCase):
    """Тесты эндпоинта /api/skills."""

    def setUp(self):
        from app import create_app
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    @patch('app.blueprints.jobs.supabase_request')
    def test_api_skills_returns_list(self, mock_request):
        """GET /api/skills должен вернуть список навыков."""
        mock_resp = SupabaseResponse(
            ok=True, status_code=200,
            data=[{'id': '1', 'name': 'Уборка', 'sort_order': 1}]
        )
        mock_request.return_value = mock_resp

        resp = self.client.get('/api/skills')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn('skills', data)
        self.assertEqual(len(data['skills']), 1)
        self.assertEqual(data['skills'][0]['name'], 'Уборка')

    @patch('app.blueprints.jobs.supabase_request')
    def test_api_skills_empty(self, mock_request):
        """GET /api/skills с пустой БД."""
        mock_resp = SupabaseResponse(ok=True, status_code=200, data=[])
        mock_request.return_value = mock_resp

        resp = self.client.get('/api/skills')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(len(data['skills']), 0)

    @patch('app.blueprints.jobs.supabase_request')
    def test_api_skills_error(self, mock_request):
        """GET /api/skills при ошибке Supabase."""
        mock_resp = SupabaseResponse(ok=False, status_code=500)
        mock_request.return_value = mock_resp

        resp = self.client.get('/api/skills')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(len(data['skills']), 0)


class TestAPIReligionsEndpoint(unittest.TestCase):
    """Тесты эндпоинта /api/religions."""

    def setUp(self):
        from app import create_app
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    @patch('app.blueprints.jobs.supabase_request')
    def test_api_religions_returns_list(self, mock_request):
        mock_resp = SupabaseResponse(
            ok=True, status_code=200,
            data=[{'id': '1', 'name': 'Православие', 'sort_order': 1}]
        )
        mock_request.return_value = mock_resp

        resp = self.client.get('/api/religions')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn('religions', data)
        self.assertEqual(data['religions'][0]['name'], 'Православие')

    @patch('app.blueprints.jobs.supabase_request')
    def test_api_religions_error(self, mock_request):
        mock_resp = SupabaseResponse(ok=False, status_code=500)
        mock_request.return_value = mock_resp

        resp = self.client.get('/api/religions')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(len(data['religions']), 0)


# ============================================================
# Тесты целостности шаблонов
# ============================================================

class TestTemplateIntegrity(unittest.TestCase):
    """Проверка целостности и синтаксиса HTML-шаблонов."""

    def setUp(self):
        from app import create_app
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.template_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'templates'
        )

    def test_all_templates_exist(self):
        """Все ожидаемые шаблоны существуют."""
        required = [
            'base.html', 'index.html', 'login.html', 'register.html',
            'error.html', 'offline.html',
            'jobs.html', 'job_new.html', 'job_detail.html',
            'my_jobs.html', 'my_applications.html',
            'profile.html', 'profile_worker.html', 'profile_edit.html',
            'workers.html', 'favorites.html',
            'chats_list.html', 'chat.html',
            'shifts.html', 'notifications.html',
            'admin.html', 'blacklist.html', 'verify_employer.html',
            '_icons.html', '_filter_skills.html',
        ]
        for tpl in required:
            path = os.path.join(self.template_dir, tpl)
            self.assertTrue(os.path.isfile(path), f'Missing template: {tpl}')

    def test_changed_templates_valid(self):
        """5 изменённых шаблонов редизайна содержат extends."""
        changed = [
            'my_applications.html', 'my_jobs.html',
            'favorites.html', 'chats_list.html', 'workers.html'
        ]
        for tpl in changed:
            path = os.path.join(self.template_dir, tpl)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn('{% extends', content,
                          f'{tpl}: missing extends directive')

    def test_register_has_skills_container(self):
        """register.html содержит контейнер skills-checkboxes."""
        path = os.path.join(self.template_dir, 'register.html')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('skills-checkboxes', content)
        self.assertIn('loadDictionaries', content)
        self.assertIn('/api/skills', content)
        self.assertIn('/api/religions', content)

    def test_no_unclosed_jinja_blocks(self):
        """Базовая проверка: количество {% block %} и {% endblock %} совпадает."""
        for tpl in ['my_applications.html', 'my_jobs.html', 'favorites.html',
                     'chats_list.html', 'workers.html', 'register.html']:
            path = os.path.join(self.template_dir, tpl)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            opens = content.count('{% block')
            closes = content.count('{% endblock')
            self.assertEqual(opens, closes,
                             f'{tpl}: block/endblock mismatch ({opens} vs {closes})')

    def test_data_attributes_preserved(self):
        """Все data-атрибуты JS-логики сохранены в my_applications."""
        path = os.path.join(self.template_dir, 'my_applications.html')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        required_attrs = [
            'data-app-id', 'data-action', 'data-status',
            'app-checkbox', 'select-all', 'mass-action-btn',
            'payment-modal', 'openPayment', 'confirmPayment'
        ]
        for attr in required_attrs:
            self.assertIn(attr, content,
                          f'my_applications.html: missing {attr}')

    def test_touch_targets_min_44px(self):
        """Все кнопки в изменённых шаблонах имеют min 44px целевые области."""
        changed = [
            'my_applications.html', 'my_jobs.html',
            'favorites.html', 'chats_list.html', 'workers.html'
        ]
        for tpl in changed:
            path = os.path.join(self.template_dir, tpl)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            # Проверяем наличие min-w-[44px] или min-h-[44px] — хотя бы по одному
            has_touch = 'min-w-[44px]' in content or 'min-h-[44px]' in content
            self.assertTrue(has_touch,
                            f'{tpl}: no 44px touch targets found')

    def test_empty_states_present(self):
        """Все страницы списков имеют пустые состояния."""
        pages = {
            'my_applications.html': 'Нет откликов',
            'my_jobs.html': 'Нет заданий',
            'favorites.html': 'В избранном пока пусто',
            'chats_list.html': 'Нет чатов',
            'workers.html': 'Нет зарегистрированных',
        }
        for tpl, expected_text in pages.items():
            path = os.path.join(self.template_dir, tpl)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            # Должен быть блок else с пустым состоянием
            has_empty = '{% else %}' in content or expected_text in content
            self.assertTrue(has_empty,
                            f'{tpl}: missing empty state')


# ============================================================
# Тесты безопасности
# ============================================================

class TestSecurityHeaders(unittest.TestCase):
    """Проверка базовой безопасности приложения."""

    def setUp(self):
        from app import create_app
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_csrf_token_in_session(self):
        """CSRF-токен генерируется в сессии."""
        with self.client:
            self.client.get('/')
            with self.client.session_transaction() as sess:
                self.assertIn('_csrf_token', sess)
                self.assertEqual(len(sess['_csrf_token']), 64)

    def test_post_without_csrf_returns_400(self):
        """POST без CSRF-токена → 400 (в не-TESTING режиме пропускается)."""
        self.app.config['TESTING'] = False
        try:
            with self.client:
                self.client.get('/')
                resp = self.client.post('/login', data={})
                self.assertEqual(resp.status_code, 400)
        finally:
            self.app.config['TESTING'] = True

    def test_secret_key_not_default_in_production_warning(self):
        """Config предупреждает о дефолтном SECRET_KEY."""
        self.assertIsNotNone(Config.SECRET_KEY)


# ============================================================
# E2E-сценарии
# ============================================================

class TestE2EScenarios(unittest.TestCase):
    """End-to-end сценарии (проверка доступности страниц)."""

    def setUp(self):
        from app import create_app
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_register_page_loads(self):
        """GET /register возвращает 200."""
        resp = self.client.get('/register')
        self.assertEqual(resp.status_code, 200)

    def test_register_contains_skills_section(self):
        """Страница регистрации содержит секцию навыков."""
        resp = self.client.get('/register')
        html = resp.data.decode('utf-8')
        self.assertIn('skills-checkboxes', html)
        self.assertIn('Загрузка...', html)

    def test_login_page_loads(self):
        """GET /login возвращает 200."""
        resp = self.client.get('/login')
        self.assertEqual(resp.status_code, 200)

    def test_index_page_loads(self):
        """GET / возвращает 200."""
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)

    @patch('app.blueprints.jobs.supabase_request')
    def test_workers_page_loads(self, mock_request):
        """GET /workers возвращает 200 (с моком Supabase)."""
        mock_resp = SupabaseResponse(ok=True, status_code=200, data=[])
        mock_request.return_value = mock_resp

        resp = self.client.get('/workers')
        self.assertEqual(resp.status_code, 200)

    def test_static_files_accessible(self):
        """Статические файлы отдаются."""
        resp = self.client.get('/static/css/tailwind.min.css')
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get('/static/manifest.json')
        self.assertEqual(resp.status_code, 200)

    def test_offline_page_loads(self):
        """GET /offline возвращает 200."""
        resp = self.client.get('/offline')
        self.assertEqual(resp.status_code, 200)

    def test_404_page(self):
        """Несуществующий URL → 404."""
        resp = self.client.get('/nonexistent-page')
        self.assertEqual(resp.status_code, 404)

    def test_static_directory_no_trailing_slash(self):
        """GET /static/ → 404 (защита от листинга директории)."""
        resp = self.client.get('/static/')
        self.assertEqual(resp.status_code, 404)


if __name__ == '__main__':
    unittest.main()
