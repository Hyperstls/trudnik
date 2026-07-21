"""
F5: Тест проверяет наличие confirm dialog для деструктивных действий.

Требования:
- JavaScript обработчик клика на элементы с data-confirm
- Использование нативного confirm() для подтверждения
- Предотвращение действия при отмене
"""
from pathlib import Path


BASE_HTML = Path(__file__).parent.parent / "templates" / "base.html"


def test_confirm_handler_exists():
    """Проверяет наличие JavaScript обработчика для data-confirm."""
    content = BASE_HTML.read_text(encoding='utf-8')
    
    # Проверяем наличие обработчика click
    assert "addEventListener('click'" in content or 'addEventListener("click"' in content, \
        "Должен быть обработчик события click"
    
    # Проверяем поиск элементов с data-confirm
    assert 'data-confirm' in content, \
        "Обработчик должен искать элементы с data-confirm"
    
    # Проверяем использование confirm()
    assert 'confirm(' in content, \
        "Обработчик должен использовать confirm()"
    
    # Проверяем preventDefault
    assert 'preventDefault' in content, \
        "Обработчик должен вызывать preventDefault при отмене"


def test_destructive_buttons_have_confirm():
    """Проверяет наличие data-confirm на деструктивных кнопках."""
    templates_dir = Path(__file__).parent.parent / "templates"
    
    # Список файлов с деструктивными действиями
    files_to_check = [
        'verify_employer.html',
        'admin.html',
    ]
    
    found_confirm = False
    for filename in files_to_check:
        filepath = templates_dir / filename
        if filepath.exists():
            content = filepath.read_text(encoding='utf-8')
            if 'data-confirm' in content:
                found_confirm = True
                break
    
    assert found_confirm, \
        "Хотя бы одна деструктивная кнопка должна иметь data-confirm"


if __name__ == "__main__":
    test_confirm_handler_exists()
    test_destructive_buttons_have_confirm()
    print("Все тесты F5 пройдены!")
