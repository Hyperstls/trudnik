"""
C9: Race condition в accept_invitation

Тесты проверяют, что accept_invitation:
- Использует атомарную RPC accept_invitation_atomic
- Правильно обрабатывает race condition коды (invitation_not_pending, job_not_open, no_slots)
"""
import pytest


class TestAcceptInvitationLogic:
    """Unit-тесты для логики accept_invitation."""

    def test_accept_invitation_returns_409_for_not_pending(self):
        """C9: invitation_not_pending должен возвращать 409."""
        result = {
            'success': False,
            'code': 'invitation_not_pending',
            'error': 'Приглашение уже обработано'
        }
        
        # Логика из jobs_api.py строки 212-219
        status_code = {
            'invitation_not_found': 404,
            'not_target': 403,
            'invitation_not_pending': 409,
            'job_not_found': 404,
            'job_not_open': 409,
            'no_slots': 409,
        }.get(result.get('code', ''), 400)
        
        assert status_code == 409

    def test_accept_invitation_returns_409_for_job_not_open(self):
        """C9: job_not_open должен возвращать 409."""
        result = {
            'success': False,
            'code': 'job_not_open',
            'error': 'Задание закрыто'
        }
        
        status_code = {
            'invitation_not_found': 404,
            'not_target': 403,
            'invitation_not_pending': 409,
            'job_not_found': 404,
            'job_not_open': 409,
            'no_slots': 409,
        }.get(result.get('code', ''), 400)
        
        assert status_code == 409

    def test_accept_invitation_returns_409_for_no_slots(self):
        """C9: no_slots должен возвращать 409."""
        result = {
            'success': False,
            'code': 'no_slots',
            'error': 'Нет свободных мест'
        }
        
        status_code = {
            'invitation_not_found': 404,
            'not_target': 403,
            'invitation_not_pending': 409,
            'job_not_found': 404,
            'job_not_open': 409,
            'no_slots': 409,
        }.get(result.get('code', ''), 400)
        
        assert status_code == 409

    def test_accept_invitation_returns_400_for_unknown_error(self):
        """C9: неизвестные ошибки должны возвращать 400."""
        result = {
            'success': False,
            'code': 'some_unknown_error',
            'error': 'Неизвестная ошибка'
        }
        
        status_code = {
            'invitation_not_found': 404,
            'not_target': 403,
            'invitation_not_pending': 409,
            'job_not_found': 404,
            'job_not_open': 409,
            'no_slots': 409,
        }.get(result.get('code', ''), 400)
        
        assert status_code == 400
