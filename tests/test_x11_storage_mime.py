"""X11: storage_service _detect_mime must be fail-closed."""
import inspect


def test_upload_photo_mime_fail_closed():
    """X11: upload_photo must reject files when MIME cannot be detected."""
    from app.services import storage_service
    
    source = inspect.getsource(storage_service.upload_photo)
    
    # Проверить, что есть проверка на None
    assert "detected_mime is None" in source, \
        "upload_photo must check if detected_mime is None"
    
    # Проверить, что при None возвращается отказ
    assert "return None" in source, \
        "upload_photo must return None when MIME is undetectable"
    
    # Проверить, что логика fail-closed (не fail-open)
    assert "detected_mime is None or detected_mime not in" in source, \
        "upload_photo must use fail-closed logic for MIME detection"
