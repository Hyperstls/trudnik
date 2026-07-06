"""F15: Кастомные интерактивные элементы должны иметь tabindex="0"."""
import os
import re
import pytest

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), '..', 'templates')


def _read_all_templates():
    """Считать все HTML-шаблоны (не email)."""
    result = {}
    for fname in os.listdir(TEMPLATES_DIR):
        if fname.endswith('.html') and 'email' not in fname:
            fpath = os.path.join(TEMPLATES_DIR, fname)
            with open(fpath, encoding='utf-8') as f:
                result[fname] = f.read()
    return result


def _find_custom_interactive_elements(html):
    """Найти div/span с cursor-pointer или clickable классом."""
    # Ищем div/span с cursor-pointer в class
    pattern = re.compile(
        r'<(div|span)\s[^>]*class="[^"]*(?:cursor-pointer|clickable)[^"]*"[^>]*>',
        re.IGNORECASE
    )
    return pattern.findall(html)


def _has_tabindex(tag):
    """Проверить, имеет ли тег tabindex атрибут."""
    return bool(re.search(r'tabindex=["\'][^"\']+["\']', tag, re.IGNORECASE))


def _is_label_wrapper(html, tag):
    """Проверить, является ли элемент label-обёрткой для input."""
    # Если это label, то не требует tabindex
    return tag.startswith('<label')


def test_custom_interactive_elements_have_tabindex():
    """Все кастомные интерактивные элементы (div/span с cursor-pointer) должны иметь tabindex.
    
    Исключения:
    - Контейнеры с вложенными кнопками/ссылками (app-card)
    - Backdrop элементы (для закрытия модальных окон)
    """
    templates = _read_all_templates()
    violations = []
    for fname, html in templates.items():
        # Ищем div/span с cursor-pointer
        elements = re.findall(
            r'<(?:div|span)\s[^>]*class="[^"]*(?:cursor-pointer|clickable)[^"]*"[^>]*>',
            html,
            re.IGNORECASE
        )
        for element in elements:
            # Исключаем контейнеры карточек (app-card)
            if 'app-card' in element:
                continue
            # Исключаем backdrop элементы
            if 'backdrop' in element.lower():
                continue
            if not _has_tabindex(element):
                short_tag = element[:100] + '...' if len(element) > 100 else element
                violations.append(f"{fname}: {short_tag}")
    assert not violations, (
        "Следующие кастомные интерактивные элементы не имеют tabindex:\n" +
        "\n".join(violations)
    )
