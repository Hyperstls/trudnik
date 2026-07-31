"""
C5: Race condition в favorites

Тесты проверяют, что add_favorite:
- Правильно обрабатывает duplicate (race condition при параллельных запросах)
- Возвращает success для дубликатов в API
"""
import pytest
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed


@pytest.fixture
def employer_session(app_client):
    """Сессия авторизованного работодателя."""
    import jwt
    from app.config import Config
    import time
    
    payload = {
        'user_id': '44444444-4444-4444-4444-444444444444',
        'role': 'employer',
        'exp': int(time.time()) + 3600,
        'jti': 'test-jti-fav'
    }
    token = jwt.encode(payload, Config.PGRST_JWT_SECRET, algorithm='HS256')
    
    with app_client.session_transaction() as sess:
        sess['user_id'] = '44444444-4444-4444-4444-444444444444'
        sess['role'] = 'employer'
        sess['_csrf_token'] = 'test-csrf-token'
        sess['access_token'] = token
        sess['jti'] = 'test-jti-fav'
    return app_client


class TestFavoritesRaceCondition:
    """Тесты для favorites без race condition."""

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.favorites.postgrest_request')
    def test_add_favorite_success(
        self, mock_request, mock_blacklist, employer_session
    ):
        """C5: add_favorite должен успешно добавлять в избранное."""
        mock_request.return_value = MagicMock(ok=True)

        target_id = '55555555-5555-5555-5555-555555555555'
        response = employer_session.post(
            f'/favorite/{target_id}',
            headers={'X-CSRF-Token': 'test-csrf-token'},
            follow_redirects=False
        )

        assert response.status_code == 302

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.favorites.postgrest_request')
    def test_add_favorite_handles_duplicate(
        self, mock_request, mock_blacklist, employer_session
    ):
        """C5: add_favorite должен обрабатывать duplicate (race condition)."""
        mock_request.return_value = MagicMock(
            ok=False,
            status_code=409,
            text='duplicate key value violates unique constraint'
        )

        target_id = '55555555-5555-5555-5555-555555555555'
        response = employer_session.post(
            f'/favorite/{target_id}',
            headers={'X-CSRF-Token': 'test-csrf-token'},
            follow_redirects=False
        )

        # Должен редиректить (не падать)
        assert response.status_code == 302

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.favorites.postgrest_request')
    def test_api_add_favorite_handles_duplicate(
        self, mock_request, mock_blacklist, employer_session
    ):
        """C5: API add_favorite должен возвращать success для дубликатов."""
        # B12: PostgREST v14 возвращает 400 + code=23505 для unique-violation (не 409)
        mock_request.return_value = MagicMock(
            ok=False,
            status_code=400,
            json=lambda: {'code': '23505', 'message': 'duplicate key value violates unique constraint'}
        )

        response = employer_session.post(
            '/api/favorites/add',
            json={'worker_id': '55555555-5555-5555-5555-555555555555'},
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'уже в избранном' in data['message']

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.favorites.postgrest_request')
    def test_concurrent_add_favorite(
        self, mock_request, mock_blacklist, employer_session
    ):
        """C5: при concurrent add_favorite оба должны succeed."""
        target_id = '55555555-5555-5555-5555-555555555555'
        
        # Счётчик вызовов
        call_count = [0]
        
        def mock_request_side_effect(method, path, **kwargs):
            call_count[0] += 1
            # Первый вызов succeeds, второй — duplicate
            if call_count[0] == 1:
                return MagicMock(ok=True)
            else:
                return MagicMock(
                    ok=False,
                    status_code=409,
                    text='duplicate key value violates unique constraint'
                )
        
        mock_request.side_effect = mock_request_side_effect

        def make_favorite_request():
            return employer_session.post(
                f'/api/favorites/add',
                json={'worker_id': target_id},
                headers={'X-CSRF-Token': 'test-csrf-token'}
            )

        # Запускаем два параллельных запроса
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(make_favorite_request) for _ in range(2)]
            results = [f.result() for f in as_completed(futures)]

        # Оба должны вернуть 200 (один успех, один duplicate → success)
        status_codes = [r.status_code for r in results]
        assert all(code == 200 for code in status_codes)
