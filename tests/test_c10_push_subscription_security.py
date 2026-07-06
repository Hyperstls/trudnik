"""
C10: Race condition в push_subscription

Тесты проверяют, что delete_subscription:
- Требует обязательный user_id
- Не позволяет удалить чужую подписку
"""
import pytest
from unittest.mock import MagicMock, patch
from app.services.push_service import PushService


class TestPushSubscriptionSecurity:
    """Тесты для безопасности push-подписок."""

    def test_delete_subscription_requires_user_id(self):
        """C10: delete_subscription должен требовать user_id."""
        push_service = PushService()
        
        # Попытка удалить без user_id должна вернуть False
        result = push_service.delete_subscription('https://example.com/push', user_id='')
        
        assert result is False

    def test_delete_subscription_requires_endpoint(self):
        """C10: delete_subscription должен требовать endpoint."""
        push_service = PushService()
        
        # Попытка удалить без endpoint должна вернуть False
        result = push_service.delete_subscription('', user_id='user-123')
        
        assert result is False

    @patch('app.services.push_service.postgrest_admin_request')
    def test_delete_subscription_includes_user_id_in_query(self, mock_request):
        """C10: delete_subscription должен включать user_id в запрос."""
        mock_request.return_value = MagicMock(ok=True)
        
        push_service = PushService()
        endpoint = 'https://example.com/push'
        user_id = 'user-123'
        
        push_service.delete_subscription(endpoint, user_id=user_id)
        
        # Проверяем, что запрос включает user_id
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        url = call_args[0][1]  # Второй аргумент - URL
        
        assert 'user_id=eq.user-123' in url
        assert 'endpoint=eq.' in url

    @patch('app.services.push_service.postgrest_admin_request')
    def test_delete_subscription_prevents_cross_user_deletion(self, mock_request):
        """C10: delete_subscription не должен позволять удалять чужие подписки."""
        # Мокаем успешное удаление
        mock_request.return_value = MagicMock(ok=True)
        
        push_service = PushService()
        
        # Пользователь A пытается удалить подписку
        endpoint = 'https://example.com/push'
        user_a = 'user-a'
        
        push_service.delete_subscription(endpoint, user_id=user_a)
        
        # Проверяем, что запрос фильтрует по user_a
        call_args = mock_request.call_args
        url = call_args[0][1]
        
        assert f'user_id=eq.{user_a}' in url
        # Это гарантирует, что даже если endpoint существует для другого пользователя,
        # он не будет удалён из-за фильтра user_id
