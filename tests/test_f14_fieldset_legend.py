"""F14: Группы radio/checkbox должны быть обёрнуты в fieldset с legend."""
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


def _find_radio_groups(html):
    """Найти группы radio-кнопок (одинаковое name)."""
    # Ищем все input type="radio" с name
    radios = re.findall(r'<input[^>]*type=["\']radio["\'][^>]*name=["\']([^"\']+)["\'][^>]*>', html, re.IGNORECASE)
    # Группируем по name
    groups = {}
    for name in radios:
        groups[name] = groups.get(name, 0) + 1
    # Возвращаем только группы с 2+ элементами
    return {name: count for name, count in groups.items() if count >= 2}


def _is_in_fieldset(html, radio_name):
    """Проверить, находится ли radio-группа внутри fieldset."""
    # Ищем fieldset, содержащий radio с данным name
    pattern = re.compile(
        r'<fieldset[^>]*>.*?<input[^>]*type=["\']radio["\'][^>]*name=["\']' + 
        re.escape(radio_name) + r'["\'][^>]*>.*?</fieldset>',
        re.IGNORECASE | re.DOTALL
    )
    return bool(pattern.search(html))


def _has_legend_in_fieldset(html, radio_name):
    """Проверить, есть ли legend внутри fieldset с radio-группой."""
    pattern = re.compile(
        r'<fieldset[^>]*>\s*<legend[^>]*>.*?</legend>.*?<input[^>]*type=["\']radio["\'][^>]*name=["\']' + 
        re.escape(radio_name) + r'["\'][^>]*>.*?</fieldset>',
        re.IGNORECASE | re.DOTALL
    )
    return bool(pattern.search(html))


def test_radio_groups_have_fieldset_legend():
    """Все группы radio-кнопок должны быть обёрнуты в fieldset с legend."""
    templates = _read_all_templates()
    violations = []
    for fname, html in templates.items():
        radio_groups = _find_radio_groups(html)
        for name, count in radio_groups.items():
            if not _is_in_fieldset(html, name):
                violations.append(f"{fname}: radio-группа '{name}' не обёрнута в fieldset")
            elif not _has_legend_in_fieldset(html, name):
                violations.append(f"{fname}: fieldset для radio-группы '{name}' не содержит legend")
    assert not violations, (
        "Следующие radio-группы не соответствуют требованиям:\n" +
        "\n".join(violations)
    )
