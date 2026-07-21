"""
F4: Тест проверяет наличие loading state для submit кнопок.

Требования:
- CSS класс .btn-loading в app.css
- JavaScript обработчик submit в base.html
- Автоматическое добавление класса btn-loading при submit
- Автоматическое отключение кнопки (disabled)
- Fallback восстановление через 10 секунд
"""
from pathlib import Path


APP_CSS = Path(__file__).parent.parent / "static" / "css" / "app.css"
BASE_HTML = Path(__file__).parent.parent / "templates" / "base.html"


def test_btn_loading_css_exists():
    """Проверяет наличие CSS класса .btn-loading."""
    content = APP_CSS.read_text(encoding='utf-8')
    
    # Проверяем наличие класса .btn-loading
    assert '.btn-loading' in content, \
        "Должен быть CSS класс .btn-loading"
    
    # Проверяем наличие pointer-events: none
    assert 'pointer-events: none' in content, \
        ".btn-loading должен иметь pointer-events: none"
    
    # Проверяем наличие opacity
    assert 'opacity: 0.7' in content, \
        ".btn-loading должен иметь opacity: 0.7"


def test_btn_loading_spinner_exists():
    """Проверяет наличие спиннера в .btn-loading::after."""
    content = APP_CSS.read_text(encoding='utf-8')
    
    # Проверяем наличие ::after псевдоэлемента
    assert '.btn-loading::after' in content, \
        "Должен быть псевдоэлемент .btn-loading::after"
    
    # Проверяем наличие анимации spin
    assert 'animation: spin' in content, \
        "Спиннер должен использовать анимацию spin"


def test_submit_handler_exists():
    """Проверяет наличие JavaScript обработчика submit."""
    content = BASE_HTML.read_text(encoding='utf-8')
    
    # Проверяем наличие обработчика submit
    assert "addEventListener('submit'" in content or 'addEventListener("submit"' in content, \
        "Должен быть обработчик события submit"
    
    # Проверяем добавление класса btn-loading
    assert 'btn.classList.add' in content and 'btn-loading' in content, \
        "Обработчик должен добавлять класс btn-loading"
    
    # Проверяем отключение кнопки
    assert 'btn.disabled = true' in content, \
        "Обработчик должен отключать кнопку (disabled = true)"


def test_fallback_timeout_exists():
    """Проверяет наличие fallback таймаута."""
    content = BASE_HTML.read_text(encoding='utf-8')
    
    # Проверяем наличие setTimeout
    assert 'setTimeout' in content, \
        "Должен быть setTimeout для fallback восстановления"
    
    # Проверяем удаление класса btn-loading
    assert 'btn.classList.remove' in content and 'btn-loading' in content, \
        "Fallback должен удалять класс btn-loading"


if __name__ == "__main__":
    test_btn_loading_css_exists()
    test_btn_loading_spinner_exists()
    test_submit_handler_exists()
    test_fallback_timeout_exists()
    print("Все тесты F4 пройдены!")
