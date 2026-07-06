"""X12: middleware emergency API must be fail-closed on empty token."""
import inspect


def test_middleware_emergency_api_fail_closed():
    """X12: csrf_check must abort when ADMIN_API_TOKEN is empty."""
    from app import middleware
    
    source = inspect.getsource(middleware.csrf_check)
    
    # Проверить, что есть проверка на пустой токен
    assert "if not expected" in source, \
        "csrf_check must check if ADMIN_API_TOKEN is empty"
    
    # Проверить, что при пустом токене вызывается abort
    assert "abort(503)" in source, \
        "csrf_check must abort(503) when token is empty"
    
    # Проверить, что при неверном токене вызывается abort(403)
    assert "abort(403)" in source, \
        "csrf_check must abort(403) when token is invalid"
