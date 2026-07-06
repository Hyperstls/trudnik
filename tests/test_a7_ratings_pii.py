"""
A7: Защита PII рейтингов от публичного доступа

Тесты проверяют, что публичный endpoint для рейтингов
не возвращает PII (email, phone) рейтера для анонимных пользователей.
"""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


class TestRatingsPIIProtection:
    """Тесты для защиты PII в рейтингах."""

    @patch('app.blueprints.ratings.postgrest_request')
    def test_anonymous_user_gets_stripped_rater_info(self, mock_postgrest, client):
        """A7: анонимный пользователь должен получать только safe поля rater."""
        user_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        
        # Mock PostgREST response с PII данными
        mock_postgrest.return_value = MagicMock(
            ok=True,
            json=lambda: [{
                'id': 'rating-1',
                'job_id': 'job-1',
                'rating': 5,
                'comment': 'Отличный работник',
                'rating_type': 'employer',
                'target_type': 'worker',
                'created_at': '2024-01-01T00:00:00Z',
                'rater': {
                    'full_name': 'Иван Иванов',
                    'photo_url': 'https://example.com/photo.jpg',
                    'email': 'ivan@example.com',  # PII
                    'phone': '+79991234567'  # PII
                }
            }]
        )

        response = client.get(f'/api/ratings/user/{user_id}/details')

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        # Проверяем что PII удалены
        rater = data['ratings'][0]['rater']
        assert 'full_name' in rater
        assert 'photo_url' in rater
        assert 'email' not in rater
        assert 'phone' not in rater

    @patch('app.blueprints.ratings.postgrest_request')
    def test_authenticated_user_gets_full_rater_info(self, mock_postgrest, client):
        """A7: авторизованный пользователь должен получать полные данные rater."""
        user_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
        
        # Создаём сессию авторизованного пользователя
        with client.session_transaction() as sess:
            sess['user_id'] = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
            sess['role'] = 'worker'
        
        # Mock PostgREST response
        mock_postgrest.return_value = MagicMock(
            ok=True,
            json=lambda: [{
                'id': 'rating-2',
                'job_id': 'job-2',
                'rating': 4,
                'comment': 'Хороший работник',
                'rating_type': 'employer',
                'target_type': 'worker',
                'created_at': '2024-01-02T00:00:00Z',
                'rater': {
                    'full_name': 'Пётр Петров',
                    'photo_url': 'https://example.com/photo2.jpg'
                }
            }]
        )

        response = client.get(f'/api/ratings/user/{user_id}/details')

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        # Проверяем что данные rater присутствуют
        rater = data['ratings'][0]['rater']
        assert 'full_name' in rater
        assert 'photo_url' in rater

    def test_endpoint_uses_column_allowlist(self):
        """A7: endpoint должен использовать явный allowlist колонок вместо select=*."""
        import inspect
        from app.blueprints.ratings import get_user_rating_details
        
        source = inspect.getsource(get_user_rating_details)
        
        # Проверяем что НЕ используется select=*
        assert 'select=*' not in source
        
        # Проверяем что используются конкретные колонки
        assert 'select=id,job_id,rating' in source or 'select=id,' in source
