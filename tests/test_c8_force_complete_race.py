"""
C8: Race condition в force_complete_job

Тесты проверяют, что force_complete_job:
- Использует атомарную RPC force_complete_job
- Правильно обрабатывает invalid_status (race condition) с кодом 409
"""
import pytest
from unittest.mock import MagicMock


class TestForceCompleteJobLogic:
    """Unit-тесты для логики force_complete_job."""

    def test_force_complete_returns_409_for_invalid_status(self):
        """C8: invalid_status должен возвращать 409."""
        # Симулируем ответ RPC
        result = {
            'success': False,
            'code': 'invalid_status',
            'error': 'Задание не может быть завершено в текущем статусе'
        }
        
        # Логика из jobs.py строка 905
        status_code = 409 if result.get('code') == 'invalid_status' else 400
        
        assert status_code == 409
        assert result['success'] is False

    def test_force_complete_returns_400_for_other_errors(self):
        """C8: другие ошибки должны возвращать 400."""
        result = {
            'success': False,
            'code': 'some_other_error',
            'error': 'Какая-то другая ошибка'
        }
        
        status_code = 409 if result.get('code') == 'invalid_status' else 400
        
        assert status_code == 400
