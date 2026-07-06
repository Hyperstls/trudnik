"""
F3: Тест проверяет наличие skip-to-content link для keyboard navigation.

Требования:
- Ссылка "Перейти к основному содержимому" в начале body
- Ссылка имеет href="#main-content"
- Ссылка скрыта по умолчанию (sr-only)
- Ссылка видна при фокусе (focus:not-sr-only)
- Тег <main> имеет id="main-content"
"""
from pathlib import Path


BASE_HTML = Path(__file__).parent.parent / "templates" / "base.html"


def test_skip_link_exists():
    """Проверяет наличие skip-to-content ссылки."""
    content = BASE_HTML.read_text(encoding='utf-8')
    
    # Проверяем наличие ссылки с href="#main-content"
    assert 'href="#main-content"' in content, \
        "Должна быть ссылка с href='#main-content'"
    
    # Проверяем текст ссылки
    assert 'Перейти к основному содержимому' in content, \
        "Ссылка должна содержать текст 'Перейти к основному содержимому'"


def test_skip_link_is_hidden_by_default():
    """Проверяет, что ссылка скрыта по умолчанию."""
    content = BASE_HTML.read_text(encoding='utf-8')
    
    # Проверяем наличие класса sr-only (screen reader only)
    assert 'sr-only' in content, \
        "Skip-link должна иметь класс sr-only для скрытия"


def test_skip_link_visible_on_focus():
    """Проверяет, что ссылка видна при фокусе."""
    content = BASE_HTML.read_text(encoding='utf-8')
    
    # Проверяем наличие focus:not-sr-only для показа при фокусе
    assert 'focus:not-sr-only' in content, \
        "Skip-link должна иметь focus:not-sr-only для показа при фокусе"


def test_main_has_id():
    """Проверяет, что тег main имеет id='main-content'."""
    content = BASE_HTML.read_text(encoding='utf-8')
    
    # Проверяем наличие id="main-content" у тега main
    assert '<main id="main-content"' in content or '<main id="main-content" ' in content, \
        "Тег <main> должен иметь id='main-content'"


if __name__ == "__main__":
    test_skip_link_exists()
    test_skip_link_is_hidden_by_default()
    test_skip_link_visible_on_focus()
    test_main_has_id()
    print("Все тесты F3 пройдены!")
