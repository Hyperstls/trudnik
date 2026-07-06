"""
F9: Тест проверяет наличие keyboard shortcuts в base.html.

Требования:
- Alt+H — переход на главную страницу
- Alt+N — переход к уведомлениям
- Escape — закрытие модальных окон
"""
from pathlib import Path


BASE_HTML = Path(__file__).parent.parent / "templates" / "base.html"


def test_keyboard_shortcuts_exist():
    """Проверяет наличие обработчика keyboard shortcuts."""
    content = BASE_HTML.read_text(encoding='utf-8')
    
    # Проверяем наличие обработчика keydown
    assert "addEventListener('keydown'" in content or 'addEventListener("keydown"' in content, \
        "Должен быть обработчик события keydown"


def test_alt_h_shortcut():
    """Проверяет наличие shortcut Alt+H для главной страницы."""
    content = BASE_HTML.read_text(encoding='utf-8')
    
    # Проверяем наличие проверки altKey
    assert 'altKey' in content, \
        "Должна проверяться клавиша Alt"
    
    # Проверяем наличие проверки клавиши h
    assert "key === 'h'" in content or 'key === "h"' in content, \
        "Должна проверяться клавиша h"
    
    # Проверяем переход на главную
    assert "location.href = '/'" in content or 'location.href = "/"' in content, \
        "Должен быть переход на главную страницу"


def test_alt_n_shortcut():
    """Проверяет наличие shortcut Alt+N для уведомлений."""
    content = BASE_HTML.read_text(encoding='utf-8')
    
    # Проверяем наличие проверки клавиши n
    assert "key === 'n'" in content or 'key === "n"' in content, \
        "Должна проверяться клавиша n"
    
    # Проверяем переход к уведомлениям
    assert '/notifications' in content, \
        "Должен быть переход к уведомлениям"


def test_escape_shortcut():
    """Проверяет наличие shortcut Escape для закрытия модальных окон."""
    content = BASE_HTML.read_text(encoding='utf-8')
    
    # Проверяем наличие проверки клавиши Escape
    assert "key === 'Escape'" in content or 'key === "Escape"' in content, \
        "Должна проверяться клавиша Escape"
    
    # Проверяем поиск модальных окон
    assert '[data-modal]' in content or 'data-modal' in content, \
        "Должен быть поиск модальных окон"


if __name__ == "__main__":
    test_keyboard_shortcuts_exist()
    test_alt_h_shortcut()
    test_alt_n_shortcut()
    test_escape_shortcut()
    print("Все тесты F9 пройдены!")
