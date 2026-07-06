"""
F6: Тест проверяет наличие toast notifications системы.

Требования:
- Функция showToast() в base.js
- Поддержка разных типов (success, error, warning, info)
- Автоматическое скрытие через 3.5 секунды
- Кнопка закрытия
- Accessibility атрибуты (role, aria-live)
"""
from pathlib import Path


BASE_JS = Path(__file__).parent.parent / "static" / "js" / "base.js"


def test_showtoast_function_exists():
    """Проверяет наличие функции showToast."""
    content = BASE_JS.read_text(encoding='utf-8')
    
    # Проверяем наличие функции showToast
    assert 'window.showToast' in content or 'function showToast' in content, \
        "Должна быть функция showToast"


def test_toast_supports_multiple_types():
    """Проверяет поддержку разных типов toast."""
    content = BASE_JS.read_text(encoding='utf-8')
    
    # Проверяем наличие разных типов
    assert 'success' in content, "Должен поддерживаться тип success"
    assert 'error' in content, "Должен поддерживаться тип error"
    assert 'warning' in content, "Должен поддерживаться тип warning"
    assert 'info' in content, "Должен поддерживаться тип info"


def test_toast_has_auto_hide():
    """Проверяет наличие автоматического скрытия."""
    content = BASE_JS.read_text(encoding='utf-8')
    
    # Проверяем наличие setTimeout для скрытия
    assert 'setTimeout' in content, "Должен быть setTimeout для автоматического скрытия"
    
    # Проверяем изменение opacity
    assert 'opacity' in content, "Должно изменяться opacity для анимации скрытия"


def test_toast_has_close_button():
    """Проверяет наличие кнопки закрытия."""
    content = BASE_JS.read_text(encoding='utf-8')
    
    # Проверяем наличие кнопки закрытия
    assert 'toast-close-btn' in content or 'closeBtn' in content, \
        "Должна быть кнопка закрытия toast"


def test_toast_has_accessibility_attributes():
    """Проверяет наличие accessibility атрибутов."""
    content = BASE_JS.read_text(encoding='utf-8')
    
    # Проверяем наличие role атрибута
    assert 'role' in content, "Должен быть role атрибут для accessibility"
    
    # Проверяем наличие aria-live атрибута
    assert 'aria-live' in content, "Должен быть aria-live атрибут для accessibility"


if __name__ == "__main__":
    test_showtoast_function_exists()
    test_toast_supports_multiple_types()
    test_toast_has_auto_hide()
    test_toast_has_close_button()
    test_toast_has_accessibility_attributes()
    print("Все тесты F6 пройдены!")
