"""
F2: Тест проверяет, что toast-уведомления имеют правильные ARIA-атрибуты.

Требования:
- role="alert" для error/danger (assertive)
- role="status" для success/warning/info (polite)
- aria-live атрибуты для screen readers
"""
import re
from pathlib import Path


BASE_JS = Path(__file__).parent.parent / "static" / "js" / "base.js"


def test_toast_has_role_attribute():
    """Проверяет, что showToast() устанавливает role атрибут."""
    content = BASE_JS.read_text(encoding='utf-8')
    
    # Проверяем наличие role="alert" для ошибок
    assert 'role", "alert"' in content or "role', 'alert'" in content, \
        "showToast() должен устанавливать role='alert' для error/danger"
    
    # Проверяем наличие role="status" для остальных типов
    assert 'role", "status"' in content or "role', 'status'" in content, \
        "showToast() должен устанавливать role='status' для success/warning/info"


def test_toast_has_aria_live():
    """Проверяет, что showToast() устанавливает aria-live атрибут."""
    content = BASE_JS.read_text(encoding='utf-8')
    
    # Проверяем наличие aria-live="assertive" для ошибок
    assert 'aria-live", "assertive"' in content or "aria-live', 'assertive'" in content, \
        "showToast() должен устанавливать aria-live='assertive' для error/danger"
    
    # Проверяем наличие aria-live="polite" для остальных типов
    assert 'aria-live", "polite"' in content or "aria-live', 'polite'" in content, \
        "showToast() должен устанавливать aria-live='polite' для success/warning/info"


def test_toast_container_has_aria_live():
    """Проверяет, что toast-контейнер имеет aria-live."""
    components_html = Path(__file__).parent.parent / "templates" / "_components.html"
    content = components_html.read_text(encoding='utf-8')
    
    # Toast-контейнер должен иметь aria-live
    assert 'aria-live="polite"' in content or "aria-live='polite'" in content, \
        "Toast-контейнер должен иметь aria-live='polite'"


if __name__ == "__main__":
    test_toast_has_role_attribute()
    test_toast_has_aria_live()
    test_toast_container_has_aria_live()
    print("Все тесты F2 пройдены!")
