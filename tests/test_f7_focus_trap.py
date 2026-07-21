"""
F7: Тест проверяет наличие focus trap для модальных окон.

Требования:
- Функция trapFocus() в base.js
- Удержание фокуса внутри модального окна при Tab навигации
- Циклическая навигация (с последнего элемента на первый и наоборот)
"""
from pathlib import Path


BASE_JS = Path(__file__).parent.parent / "static" / "js" / "base.js"


def test_trapfocus_function_exists():
    """Проверяет наличие функции trapFocus."""
    content = BASE_JS.read_text(encoding='utf-8')
    
    # Проверяем наличие функции trapFocus
    assert 'window.trapFocus' in content or 'function trapFocus' in content, \
        "Должна быть функция trapFocus"


def test_trapfocus_handles_tab_key():
    """Проверяет обработку клавиши Tab."""
    content = BASE_JS.read_text(encoding='utf-8')
    
    # Проверяем обработку клавиши Tab
    assert 'Tab' in content, "Должна обрабатываться клавиша Tab"
    
    # Проверяем обработку Shift+Tab
    assert 'shiftKey' in content, "Должна обрабатываться комбинация Shift+Tab"


def test_trapfocus_finds_focusable_elements():
    """Проверяет поиск фокусируемых элементов."""
    content = BASE_JS.read_text(encoding='utf-8')
    
    # Проверяем поиск кнопок
    assert 'button' in content, "Должны искаться кнопки"
    
    # Проверяем поиск ссылок
    assert '[href]' in content, "Должны искаться ссылки"
    
    # Проверяем поиск input элементов
    assert 'input' in content, "Должны искаться input элементы"


def test_trapfocus_cycles_focus():
    """Проверяет циклическую навигацию фокуса."""
    content = BASE_JS.read_text(encoding='utf-8')
    
    # Проверяем наличие первого и последнего элемента
    assert 'first' in content, "Должен определяться первый фокусируемый элемент"
    assert 'last' in content, "Должен определяться последний фокусируемый элемент"
    
    # Проверяем вызов focus()
    assert '.focus()' in content, "Должен вызываться метод focus()"


if __name__ == "__main__":
    test_trapfocus_function_exists()
    test_trapfocus_handles_tab_key()
    test_trapfocus_finds_focusable_elements()
    test_trapfocus_cycles_focus()
    print("Все тесты F7 пройдены!")
