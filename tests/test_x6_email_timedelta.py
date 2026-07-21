"""X6: email_service.py must use datetime.timedelta, not time.timedelta."""
import inspect


def test_email_service_uses_datetime_timedelta():
    """X6: email_service must import timedelta from datetime."""
    from app.services import email_service
    
    source = inspect.getsource(email_service)
    
    # Проверить, что НЕ используется _time_module.timedelta
    assert "_time_module.timedelta" not in source, \
        "email_service must not use _time_module.timedelta"
    
    # Проверить, что импортируется timedelta из datetime
    assert "from datetime import" in source and "timedelta" in source, \
        "email_service must import timedelta from datetime"
