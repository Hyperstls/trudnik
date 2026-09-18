"""
F5: Тест проверяет наличие confirm dialog для деструктивных действий.

Архитектура (обновлено 2026-09-05):
- Кастомный showConfirm (модальный <dialog>) — в static/js/base.js:
  глобальный обработчик submit на формах .js-confirm-form[data-confirm].
- Нативный confirm() по [data-confirm] в base.html УДАЛЁН — на формах с обоими
  атрибутами он давал двойное подтверждение (нативный + кастомный).
"""
from pathlib import Path


BASE_HTML = Path(__file__).parent.parent / "templates" / "base.html"
BASE_JS = Path(__file__).parent.parent / "static" / "js" / "base.js"


def test_confirm_handler_exists():
    """Проверяет наличие кастомного confirm-обработчика в base.js."""
    content = BASE_JS.read_text(encoding='utf-8')

    # Проверяем наличие обработчика submit
    assert "addEventListener('submit'" in content or 'addEventListener("submit"' in content, \
        "Должен быть обработчик события submit"

    # Проверяем поиск форм .js-confirm-form с data-confirm
    assert 'js-confirm-form' in content, \
        "Обработчик должен искать формы .js-confirm-form"
    assert 'data-confirm' in content, \
        "Текст подтверждения должен браться из атрибута data-confirm"

    # Проверяем использование кастомного showConfirm
    assert 'showConfirm' in content, \
        "Обработчик должен использовать кастомный showConfirm"

    # Проверяем preventDefault
    assert 'preventDefault' in content, \
        "Обработчик должен вызывать preventDefault"


def test_no_native_confirm_handler_in_base_html():
    """В base.html не должно быть нативного confirm() по [data-confirm].

    Нативный обработчик удалён 2026-09-05: на формах .js-confirm-form[data-confirm]
    он срабатывал вместе с кастомным showConfirm — двойное подтверждение.
    """
    content = BASE_HTML.read_text(encoding='utf-8')

    assert 'if (!confirm(' not in content, \
        "Нативный confirm() по [data-confirm] удалён — используется showConfirm из base.js"
    assert "closest('[data-confirm]')" not in content, \
        "Click-обработчик по [data-confirm] удалён из base.html"


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
    test_no_native_confirm_handler_in_base_html()
    test_destructive_buttons_have_confirm()
    print("Все тесты F5 пройдены!")
