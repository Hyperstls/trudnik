"""
F9: Тест проверяет keyboard shortcuts в base.html.

Требования (обновлено 2026-08-27 по дизайн-аудиту Kimi3, раздел 5):
- Alt+H / Alt+N — УДАЛЕНЫ: конфликтуют с браузерными/скрин-ридерными
  хоткеями и нигде не анонсировались пользователю (аудит, B7).
- Escape — закрытие модальных окон: сохраняется.
"""
from pathlib import Path


BASE_HTML = Path(__file__).parent.parent / "templates" / "base.html"


def test_keyboard_shortcuts_exist():
    """Проверяет наличие обработчика keyboard shortcuts."""
    content = BASE_HTML.read_text(encoding='utf-8')

    # Проверяем наличие обработчика keydown
    assert "addEventListener('keydown'" in content or 'addEventListener("keydown"' in content, \
        "Должен быть обработчик события keydown"


def test_alt_shortcuts_removed():
    """Alt+H/Alt+N удалены (аудит: конфликт со скрин-ридерами, без анонса)."""
    content = BASE_HTML.read_text(encoding='utf-8')

    # Не должно остаться привязки навигации на Alt-комбинации
    assert "altKey && e.key === 'h'" not in content, \
        "Alt+H удалён по аудиту (2026-08-27)"
    assert "altKey && e.key === 'n'" not in content, \
        "Alt+N удалён по аудиту (2026-08-27)"


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
    test_alt_shortcuts_removed()
    test_escape_shortcut()
    print("Все тесты F9 пройдены!")
