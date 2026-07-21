"""X8: admin_required must be fail-closed on DB errors."""
import inspect


def test_admin_required_fail_closed():
    """X8: admin_required must not fallback to session on DB errors."""
    from app import decorators
    
    source = inspect.getsource(decorators.admin_required)
    
    # Проверить, что нет fallback на session.get('role')
    assert "session.get('role')" not in source, \
        "admin_required must not fallback to session.get('role') on DB errors"
    
    # Проверить, что есть обработка исключений с fail-closed
    assert "except Exception" in source, \
        "admin_required must handle exceptions"
    
    # Проверить, что при ошибке возвращается redirect (не pass)
    assert "return redirect" in source, \
        "admin_required must redirect on errors"
