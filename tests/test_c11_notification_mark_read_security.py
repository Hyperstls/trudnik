"""
C11: Race condition в notification mark_read

Тесты проверяют, что mark_read:
- Требует обязательный user_id
- Не позволяет пометить чужое уведомление как прочитанное
"""
import pytest
from unittest.mock import MagicMock, patch
from app.services.notification_service import mark_read


class TestNotificationMarkReadSecurity:
    """Тесты для безопасности mark_read."""

    def test_mark_read_requires_user_id(self):
        """C11: mark_read должен требовать user_id."""
        # Попытка пометить без user_id должна вернуть None (early return)
        result = mark_read('notification-123', user_id='')
        
        assert result is None

    @patch('app.services.notification_service.postgrest_request')
    def test_mark_read_includes_user_id_in_query(self, mock_request):
        """C11: mark_read должен включать user_id в запрос."""
        mock_request.return_value = MagicMock(ok=True)
        
        notification_id = 'notification-123'
        user_id = 'user-456'
        
        mark_read(notification_id, user_id=user_id)
        
        # Проверяем, что запрос включает user_id
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        url = call_args[0][1]  # Второй аргумент - URL
        
        assert f'user_id=eq.{user_id}' in url
        assert f'id=eq.{notification_id}' in url

    @patch('app.services.notification_service.postgrest_request')
    def test_mark_read_prevents_cross_user_access(self, mock_request):
        """C11: mark_read не должен позволять помечать чужие уведомления."""
        mock_request.return_value = MagicMock(ok=True)
        
        # Пользователь A пытается пометить уведомление
        notification_id = 'notification-123'
        user_a = 'user-a'
        
        mark_read(notification_id, user_id=user_a)
        
        # Проверяем, что запрос фильтрует по user_a
        call_args = mock_request.call_args
        url = call_args[0][1]
        
        assert f'user_id=eq.{user_a}' in url
        # Это гарантирует, что даже если уведомление существует для другого пользователя,
        # оно не будет помечено из-за фильтра user_id

    @patch('app.utils.redis_cache.redis_cache_delete')
    @patch('app.services.notification_service.postgrest_request')
    def test_mark_read_invalidates_cache(self, mock_request, mock_cache_delete):
        """C11: mark_read должен инвалидировать кэш непрочитанных."""
        mock_request.return_value = MagicMock(ok=True)
        
        notification_id = 'notification-123'
        user_id = 'user-456'
        
        mark_read(notification_id, user_id=user_id)
        
        # Проверяем, что кэш был инвалидирован
        mock_cache_delete.assert_called_once_with(f'unread:{user_id}')
